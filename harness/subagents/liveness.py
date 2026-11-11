# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Arafat Zahan (@kuasha420)
# Corporate Stewardship & Infrastructure: Purrfect Software Limited (PSL)
# Governed by: ICARO-42/b Ordinance (Company-Supported Personal IP Framework)

"""
Subagent Liveness Inspection Engine (Issue #78, ADR-025, Issue #111).
Delegates transcript parsing, completion tail inspection, and parent-child lineage
discovery to `harness.trajectory.transcript_reader`.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import re
import time
from typing import Dict, List, Optional, Set, Tuple

from harness.trajectory.transcript_reader import (
    extract_role_from_text,
    extract_spawned_subagents,
    find_transcript_path,
    is_conversation_completed,
    is_transcript_completed as _is_transcript_completed,
    load_transcript_steps,
)
from harness.utils.context import get_active_brain_dir, get_active_conversation_id

_GENERIC_ROLES = frozenset({"user", "assistant", "system", "tool", "model"})


@dataclass(frozen=True)
class SubagentLivenessStatus:
    """Delegate subagent liveness and heartbeat status."""

    conversation_id: str
    role: str
    last_heartbeat_iso: Optional[str]
    heartbeat_age_seconds: float
    liveness_state: str  # "ACTIVE" | "STALE" | "PARKED" | "COMPLETED" | "DEAD"
    progress_file: Optional[str]
    is_parked: bool


def _parse_iso_to_epoch(iso_str: str) -> Optional[float]:
    try:
        clean_str = iso_str.strip().rstrip("Z")
        dt = datetime.fromisoformat(iso_str.strip()) if ("+" in clean_str or clean_str.count("-") > 2) else datetime.fromisoformat(clean_str).replace(tzinfo=timezone.utc)
        return dt.timestamp()
    except Exception:
        return None


def _format_epoch_to_iso(epoch: float) -> str:
    return datetime.fromtimestamp(epoch, tz=timezone.utc).isoformat().replace("+00:00", "Z")


def _is_globally_parked(workspace: Path) -> Tuple[bool, Set[str]]:
    """Checks workspace pause gates and PARKED_STATE.md ledgers with 24h expiration TTL."""
    is_paused = False
    parked_ids: Set[str] = set()
    cutoff = time.time() - 86400

    for p in (workspace / ".agents" / "artifacts" / "pause_gate.json", workspace / ".agents" / "teamwork" / "pause_gate.json"):
        if p.is_file():
            try:
                if p.stat().st_mtime >= cutoff and json.loads(p.read_text(encoding="utf-8")).get("status") in ("paused", "pausing"):
                    is_paused = True
            except Exception:
                pass

    for p in (workspace / ".agents" / "artifacts" / "PARKED_STATE.md", workspace / ".agents" / "teamwork" / "PARKED_STATE.md"):
        if p.is_file():
            try:
                if p.stat().st_mtime < cutoff:
                    continue
                content = p.read_text(encoding="utf-8", errors="replace")
                if "PARKED" in content or "status: paused" in content.lower():
                    is_paused = True
                for line in content.splitlines():
                    if "PARKED" in line:
                        parked_ids.update(tok.strip() for tok in re.findall(r"([0-9a-fA-F\-]{8,36}|[a-zA-Z0-9_-]+(?:_[a-zA-Z0-9]+)+)", line))
            except Exception:
                pass
    return is_paused, parked_ids


def _discover_active_session_subagents(b_dir: Path, active_conv_id: str) -> Set[str]:
    """Discovers child subagent IDs/roles from decoded JSON steps of active_conv_id."""
    t_path, resolved_id = find_transcript_path(active_conv_id, brain_dir=b_dir)
    if t_path is None:
        return set()
    steps, _, _ = load_transcript_steps(t_path)
    spawned = extract_spawned_subagents(steps, parent_cid=resolved_id)
    tokens: Set[str] = set(spawned.keys())
    for role in spawned.values():
        if role and role.lower() not in _GENERIC_ROLES | {"subagent"}:
            tokens.add(role)
    return tokens


def _parse_transcript_header(t_path: Path, default_cid: str) -> Tuple[str, str, str]:
    """Extracts (conv_id, role, first_chunk) from the head of a JSONL transcript."""
    conv_id_str = default_cid
    role = "subagent"
    first_chunk = ""
    try:
        with open(t_path, "r", encoding="utf-8", errors="replace") as f:
            first_line = f.readline()
            if first_line:
                try:
                    obj1 = json.loads(first_line.strip())
                    if isinstance(obj1, dict):
                        conv_id_str = str(obj1.get("conversation_id") or obj1.get("conversationId") or conv_id_str)
                        r = str(obj1.get("role") or obj1.get("Role") or "").strip()
                        if r.lower() in _GENERIC_ROLES:
                            r = ""
                        role = r or extract_role_from_text(str(obj1.get("content") or "")) or role
                except Exception:
                    role = extract_role_from_text(first_line) or role
            first_chunk = first_line + (f.read(4096) if len(first_line) < 4096 else "")
    except Exception:
        pass
    return conv_id_str, role, first_chunk


def _classify_liveness_state(
    is_explicit_parked: bool,
    is_completed: bool,
    is_paused_global: bool,
    age_seconds: float,
    stale_threshold: int,
    dead_threshold: int,
) -> str:
    """Precedence: explicit PARKED -> COMPLETED -> global PARKED -> ACTIVE -> STALE -> DEAD."""
    if is_explicit_parked:
        return "PARKED"
    if is_completed:
        return "COMPLETED"
    if is_paused_global:
        return "PARKED"
    if age_seconds <= stale_threshold:
        return "ACTIVE"
    if age_seconds <= dead_threshold:
        return "STALE"
    return "DEAD"


def _scan_teamwork_progress(
    ws: Path,
    now: float,
    active_conv_id: Optional[str],
    active_child_tokens: Set[str],
    parked_tokens: Set[str],
    show_all: bool,
    is_custom_brain: bool,
    dead_threshold: int,
) -> Dict[str, Tuple[float, str, Optional[str], bool, bool]]:
    teamwork_dir = ws / ".agents" / "teamwork"
    teamwork_map: Dict[str, Tuple[float, str, Optional[str], bool, bool]] = {}
    if not teamwork_dir.is_dir():
        return teamwork_map
    try:
        for folder in teamwork_dir.iterdir():
            if not folder.is_dir() or folder.name.startswith("."):
                continue
            prog_file = folder / "progress.md"
            if not prog_file.is_file():
                continue
            epoch = prog_file.stat().st_mtime
            iso_str: Optional[str] = None
            is_parked = folder.name in parked_tokens
            is_completed = False
            content = ""
            try:
                content = prog_file.read_text(encoding="utf-8", errors="replace")
                if "PARKED" in content or "status: parked" in content.lower():
                    is_parked = True
                in_prog = bool(re.search(r"^\s*[-*]?\s*Status:\s*IN[_ ]PROGRESS\b", content, re.I | re.M))
                if not is_parked and not in_prog and re.search(r"^\s*[-*]?\s*Status:\s*(?:Complete|Completed|Done)\b", content, re.I | re.M):
                    is_completed = True
                m_visit = re.search(r"Last visited:\s*([0-9T:\-\+Z\.]+)", content)
                if m_visit:
                    parsed = _parse_iso_to_epoch(m_visit.group(1).strip())
                    if parsed is not None:
                        epoch, iso_str = parsed, m_visit.group(1).strip()
            except Exception:
                pass

            age = max(0.0, round(now - epoch, 1))
            if active_conv_id and not show_all:
                matches = folder.name in active_child_tokens or any(tok in folder.name for tok in active_child_tokens)
                if not matches and content and active_conv_id in content:
                    matches = True
                    active_child_tokens.add(folder.name)
                if not matches:
                    continue
            elif not show_all and not is_custom_brain and age > dead_threshold:
                continue

            teamwork_map[folder.name] = (epoch, iso_str or _format_epoch_to_iso(epoch), str(prog_file), is_parked, is_completed)
    except Exception:
        pass
    return teamwork_map


def probe_subagent_liveness(
    workspace_dir: Optional[Path] = None,
    brain_dir: Optional[Path] = None,
    conv_id: Optional[str] = None,
    show_all: bool = False,
    stale_threshold: int = 300,
    dead_threshold: int = 1800,
) -> List[SubagentLivenessStatus]:
    """Probe and classify liveness of delegate subagents cleanly under sub-second SLA."""
    ws = Path(workspace_dir) if workspace_dir else Path.cwd()
    is_paused_global, parked_tokens = _is_globally_parked(ws)
    now = time.time()

    b_dir = get_active_brain_dir(brain_dir)
    is_custom_brain = (brain_dir is not None) or (b_dir != Path.home() / ".gemini" / "antigravity" / "brain")
    if conv_id is not None and str(conv_id).strip():
        active_conv_id: Optional[str] = str(conv_id).strip()
    else:
        env_conv = get_active_conversation_id()
        active_conv_id = env_conv if (env_conv and b_dir.is_dir() and (b_dir / env_conv).is_dir()) else None

    active_child_tokens = _discover_active_session_subagents(b_dir, active_conv_id) if (active_conv_id and not show_all) else set()
    teamwork_map = _scan_teamwork_progress(ws, now, active_conv_id, active_child_tokens, parked_tokens, show_all, is_custom_brain, dead_threshold)

    statuses: List[SubagentLivenessStatus] = []
    seen_ids: Set[str] = set()
    entries: List[Path] = []

    if b_dir.is_dir():
        try:
            if brain_dir is not None:
                entries = [e for e in b_dir.iterdir() if e.is_dir() and not e.name.startswith(".")]
            else:
                raw = sorted((e for e in os.scandir(b_dir) if e.is_dir() and not e.name.startswith(".")), key=lambda e: e.stat().st_mtime, reverse=True)
                for entry in raw:
                    if not active_conv_id and (now - entry.stat().st_mtime > max(14400, dead_threshold * 2)):
                        break
                    entries.append(Path(entry.path))
        except OSError:
            entries = []

        for item in entries:
            t_path, _ = find_transcript_path(item, brain_dir=b_dir)
            if t_path is None:
                continue
            conv_id_str, role, first_chunk = _parse_transcript_header(t_path, item.name)
            last_ts = t_path.stat().st_mtime
            age = max(0.0, round(now - last_ts, 1))

            if active_conv_id and not show_all:
                if conv_id_str == active_conv_id or item.name == active_conv_id:
                    continue
                is_child = conv_id_str in active_child_tokens or item.name in active_child_tokens
                if not is_child and first_chunk and active_conv_id in first_chunk:
                    is_child = True
                    active_child_tokens.update((conv_id_str, item.name))
                if not is_child:
                    continue
                if not is_custom_brain and age > max(14400, dead_threshold * 2):
                    continue
            elif not show_all and not is_custom_brain and age > dead_threshold:
                continue

            prog_path: Optional[str] = None
            iso_ts: Optional[str] = None
            is_exp_parked = conv_id_str in parked_tokens or role in parked_tokens
            is_tw_done = False
            for tw_k, (tw_ep, tw_iso, tw_p, tw_pk, tw_dn) in list(teamwork_map.items()):
                if tw_k in conv_id_str or conv_id_str in tw_k or tw_k.lower() in role.lower():
                    if tw_ep > last_ts:
                        last_ts, iso_ts = tw_ep, tw_iso
                    prog_path = tw_p
                    is_exp_parked = is_exp_parked or tw_pk
                    is_tw_done = is_tw_done or tw_dn
                    del teamwork_map[tw_k]
                    break

            age = max(0.0, round(now - last_ts, 1))
            state = _classify_liveness_state(is_exp_parked, _is_transcript_completed(t_path) or is_tw_done, is_paused_global, age, stale_threshold, dead_threshold)
            seen_ids.update((conv_id_str, item.name))
            statuses.append(SubagentLivenessStatus(conv_id_str, role, iso_ts or _format_epoch_to_iso(last_ts), age, state, prog_path, state == "PARKED"))

    for tw_name, (tw_ep, tw_iso, tw_p, tw_pk, tw_dn) in teamwork_map.items():
        if tw_name in seen_ids:
            continue
        age = max(0.0, round(now - tw_ep, 1))
        state = _classify_liveness_state(tw_pk or tw_name in parked_tokens, tw_dn, is_paused_global, age, stale_threshold, dead_threshold)
        seen_ids.add(tw_name)
        statuses.append(SubagentLivenessStatus(tw_name, tw_name, tw_iso, age, state, tw_p, state == "PARKED"))

    if not statuses and conv_id and active_conv_id:
        for item in entries:
            if item.name == active_conv_id:
                t_path, _ = find_transcript_path(item, brain_dir=b_dir)
                if t_path is not None:
                    last_ts = t_path.stat().st_mtime
                    _, role, _ = _parse_transcript_header(t_path, active_conv_id)
                    age = max(0.0, round(now - last_ts, 1))
                    state = _classify_liveness_state(active_conv_id in parked_tokens, _is_transcript_completed(t_path), is_paused_global, age, stale_threshold, dead_threshold)
                    statuses.append(SubagentLivenessStatus(active_conv_id, role, _format_epoch_to_iso(last_ts), age, state, None, state == "PARKED"))
                break
    return statuses


__all__ = ["SubagentLivenessStatus", "_is_transcript_completed", "is_conversation_completed", "probe_subagent_liveness"]
