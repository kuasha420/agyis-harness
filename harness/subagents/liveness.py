# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Arafat Zahan (@kuasha420)
# Corporate Stewardship & Infrastructure: Purrfect Software Limited (PSL)
# Governed by: ICARO-42/b Ordinance (Company-Supported Personal IP Framework)

"""
Subagent Liveness Inspection Engine (Issue #78, ADR-025, Epic #74).
Provides sub-second determinism for delegate heartbeat freshness and state classification.
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

from harness.subagents.context import extract_role_from_text


@dataclass(frozen=True)
class SubagentLivenessStatus:
    """Delegate subagent liveness and heartbeat status."""

    conversation_id: str
    role: str
    last_heartbeat_iso: Optional[str]
    heartbeat_age_seconds: float
    liveness_state: str  # "ACTIVE" | "STALE" | "PARKED" | "DEAD"
    progress_file: Optional[str]
    is_parked: bool


def _parse_iso_to_epoch(iso_str: str) -> Optional[float]:
    """Parse ISO8601 string to UNIX epoch seconds."""
    try:
        clean_str = iso_str.strip().rstrip("Z")
        if "+" in clean_str or clean_str.count("-") > 2:
            dt = datetime.fromisoformat(iso_str.strip())
        else:
            dt = datetime.fromisoformat(clean_str).replace(tzinfo=timezone.utc)
        return dt.timestamp()
    except Exception:
        return None


def _format_epoch_to_iso(epoch: float) -> str:
    """Format UNIX epoch seconds to ISO8601 UTC string."""
    dt = datetime.fromtimestamp(epoch, tz=timezone.utc)
    return dt.isoformat().replace("+00:00", "Z")


def _is_globally_parked(workspace: Path) -> Tuple[bool, Set[str]]:
    """Check workspace pause gates and PARKED_STATE.md ledgers."""
    is_paused = False
    parked_ids: Set[str] = set()

    for p in [
        workspace / ".agents" / "artifacts" / "pause_gate.json",
        workspace / ".agents" / "teamwork" / "pause_gate.json",
    ]:
        if p.is_file():
            try:
                with open(p, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    if data.get("status") in ("paused", "pausing"):
                        is_paused = True
            except Exception:
                pass

    for p in [
        workspace / ".agents" / "artifacts" / "PARKED_STATE.md",
        workspace / ".agents" / "teamwork" / "PARKED_STATE.md",
    ]:
        if p.is_file():
            try:
                content = p.read_text(encoding="utf-8", errors="replace")
                if "PARKED" in content or "status: paused" in content.lower():
                    is_paused = True
                # Match parked subagent IDs or roles
                for line in content.splitlines():
                    if "PARKED" in line:
                        m = re.findall(r"([0-9a-fA-F\-]{8,36}|[a-zA-Z0-9_-]+(?:_[a-zA-Z0-9]+)+)", line)
                        for token in m:
                            parked_ids.add(token.strip())
            except Exception:
                pass

    return is_paused, parked_ids


def probe_subagent_liveness(
    workspace_dir: Optional[Path] = None,
    brain_dir: Optional[Path] = None,
    stale_threshold: int = 300,
    dead_threshold: int = 1800,
) -> List[SubagentLivenessStatus]:
    """
    Probe and classify liveness of delegate subagents in sub-second benchmark (<10ms).

    State Classifications:
    - PARKED: Explicitly marked parked in PARKED_STATE.md, pause_gate.json, or progress file.
    - ACTIVE: Heartbeat age <= stale_threshold (default 300s).
    - STALE: stale_threshold < Heartbeat age <= dead_threshold (default 1800s).
    - DEAD: Heartbeat age > dead_threshold or missing.
    """
    ws = Path(workspace_dir) if workspace_dir else Path.cwd()
    is_paused_global, parked_tokens = _is_globally_parked(ws)
    now = time.time()

    teamwork_dir = ws / ".agents" / "teamwork"
    teamwork_map: Dict[str, Tuple[float, str, Optional[str], bool]] = {}

    if teamwork_dir.is_dir():
        try:
            for agent_folder in teamwork_dir.iterdir():
                if not agent_folder.is_dir() or agent_folder.name.startswith("."):
                    continue
                prog_file = agent_folder / "progress.md"
                if not prog_file.is_file():
                    continue

                mtime = prog_file.stat().st_mtime
                iso_str: Optional[str] = None
                epoch = mtime
                is_file_parked = False

                try:
                    content = prog_file.read_text(encoding="utf-8", errors="replace")
                    if "PARKED" in content or "status: parked" in content.lower():
                        is_file_parked = True
                    m_visit = re.search(r"Last visited:\s*([0-9T:\-\+Z\.]+)", content)
                    if m_visit:
                        parsed_epoch = _parse_iso_to_epoch(m_visit.group(1).strip())
                        if parsed_epoch is not None:
                            epoch = parsed_epoch
                            iso_str = m_visit.group(1).strip()
                except Exception:
                    pass

                if iso_str is None:
                    iso_str = _format_epoch_to_iso(epoch)

                teamwork_map[agent_folder.name] = (
                    epoch,
                    iso_str,
                    str(prog_file),
                    is_file_parked or is_paused_global or (agent_folder.name in parked_tokens),
                )
        except Exception:
            pass

    b_dir = brain_dir or Path(
        os.environ.get(
            "ANTIGRAVITY_BRAIN_DIR",
            os.environ.get(
                "GEMINI_BRAIN_DIR", Path.home() / ".gemini" / "antigravity" / "brain"
            ),
        )
    )

    statuses: List[SubagentLivenessStatus] = []
    seen_ids: Set[str] = set()

    if b_dir.exists() and b_dir.is_dir():
        # Scan candidate session directories
        entries = []
        try:
            if brain_dir is not None:
                entries = [e for e in b_dir.iterdir() if e.is_dir() and not e.name.startswith(".")]
            else:
                raw_entries = [e for e in os.scandir(b_dir) if e.is_dir() and not e.name.startswith(".")]
                raw_entries.sort(key=lambda e: e.stat().st_mtime, reverse=True)
                for entry in raw_entries:
                    if now - entry.stat().st_mtime > max(14400, dead_threshold * 2):
                        break
                    entries.append(Path(entry.path))
        except OSError:
            entries = []

        for item in entries:
            t_path = item / ".system_generated" / "logs" / "transcript.jsonl"
            if not t_path.is_file():
                t_path = item / "transcript.jsonl"
            if not t_path.is_file():
                continue

            conv_id = item.name
            role = "subagent"
            last_timestamp: float = t_path.stat().st_mtime
            iso_timestamp: Optional[str] = None

            try:
                with open(t_path, "r", encoding="utf-8", errors="replace") as f:
                    first_line = f.readline()
                    if first_line:
                        try:
                            obj1 = json.loads(first_line.strip())
                            if isinstance(obj1, dict):
                                conv_id = obj1.get("conversation_id") or obj1.get("conversationId") or conv_id
                                r = obj1.get("role") or obj1.get("Role") or ""
                                if str(r).strip().lower() in ("user", "assistant", "system", "tool", "model"):
                                    r = ""
                                role = r or extract_role_from_text(str(obj1.get("content") or "")) or role
                        except Exception:
                            r_extracted = extract_role_from_text(first_line)
                            if r_extracted:
                                role = r_extracted
            except Exception:
                pass

            prog_path: Optional[str] = None
            is_subagent_parked = is_paused_global or (conv_id in parked_tokens) or (role in parked_tokens)

            # Link with teamwork directory if matching
            matched_key = None
            for tw_key, (tw_epoch, tw_iso, tw_path, tw_parked) in teamwork_map.items():
                if tw_key in conv_id or conv_id in tw_key or tw_key.lower() in role.lower():
                    matched_key = tw_key
                    if tw_epoch > last_timestamp:
                        last_timestamp = tw_epoch
                        iso_timestamp = tw_iso
                    prog_path = tw_path
                    if tw_parked:
                        is_subagent_parked = True
                    break

            if matched_key:
                del teamwork_map[matched_key]

            if iso_timestamp is None:
                iso_timestamp = _format_epoch_to_iso(last_timestamp)

            age_seconds = max(0.0, round(now - last_timestamp, 1))

            if is_subagent_parked:
                state = "PARKED"
            elif age_seconds <= stale_threshold:
                state = "ACTIVE"
            elif age_seconds <= dead_threshold:
                state = "STALE"
            else:
                state = "DEAD"

            seen_ids.add(conv_id)
            statuses.append(
                SubagentLivenessStatus(
                    conversation_id=conv_id,
                    role=role,
                    last_heartbeat_iso=iso_timestamp,
                    heartbeat_age_seconds=age_seconds,
                    liveness_state=state,
                    progress_file=prog_path,
                    is_parked=is_subagent_parked,
                )
            )

    # Any remaining teamwork progress files not attached to a brain transcript
    for tw_name, (tw_epoch, tw_iso, tw_path, tw_parked) in teamwork_map.items():
        if tw_name in seen_ids:
            continue
        age_seconds = max(0.0, round(now - tw_epoch, 1))
        is_subagent_parked = tw_parked or is_paused_global or (tw_name in parked_tokens)

        if is_subagent_parked:
            state = "PARKED"
        elif age_seconds <= stale_threshold:
            state = "ACTIVE"
        elif age_seconds <= dead_threshold:
            state = "STALE"
        else:
            state = "DEAD"

        seen_ids.add(tw_name)
        statuses.append(
            SubagentLivenessStatus(
                conversation_id=tw_name,
                role=tw_name,
                last_heartbeat_iso=tw_iso,
                heartbeat_age_seconds=age_seconds,
                liveness_state=state,
                progress_file=tw_path,
                is_parked=is_subagent_parked,
            )
        )

    return statuses
