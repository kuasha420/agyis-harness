# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Arafat Zahan (@kuasha420)
# Corporate Stewardship & Infrastructure: Purrfect Software Limited (PSL)
# Governed by: ICARO-42/b Ordinance (Company-Supported Personal IP Framework)

"""
Canonical Streaming JSONL Transcript Reader & Subagent Lineage Resolver (ADR-035).

Single Source of Truth replacing duplicated transcript parsers across subagents,
liveness, checkpointing, pre-invocation hooks, and Trajectory HUD.
"""

from __future__ import annotations

from collections import OrderedDict
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import re
import time
from typing import Any, Dict, List, Optional, Tuple, Union

from harness.trajectory.health import (
    DEFAULT_CONTEXT_WINDOW_TOKENS,
    SubagentContextStatus,
    TokenBreakdown,
    classify_context_health,
    is_transcript_checkpoint_step,
)
from harness.trajectory.sqlite_reader import parse_step_timestamp, read_db_trajectory_state
from harness.utils.context import get_active_brain_dir
from harness.utils.tokens import estimate_tokens

MAX_TRANSCRIPT_CACHE: int = 64
_TRANSCRIPT_CACHE: "OrderedDict[Tuple[str, int, int], Tuple[List[Dict[str, Any]], List[int], Dict[int, float]]]" = OrderedDict()

_UUID_RE = re.compile(r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$")
_CID_PAIR_RE = re.compile(
    r'(?:conversation_?[iI]d|Recipient)\\?["\']?\s*:\s*\\?["\']?([A-Za-z0-9][A-Za-z0-9\-_]{7,63})'
)
_EXCLUDED_CIDS = frozenset({
    "Optional",
    "conversation_id",
    "conversationId",
    "target_conv_id",
    "parent_id",
    "active_id",
    "string",
    "object",
})


def extract_role_from_text(text: str) -> Optional[str]:
    """Extracts subagent or agent persona role identifier from prompt prose."""
    if not text or not isinstance(text, str):
        return None
    if "continuing work" in text or "resuming work" in text:
        return None
    m_bracket = re.search(r"<([A-Za-z0-9_\s\-]+)\s*\([A-Za-z0-9_\s\-]+\)>", text)
    if m_bracket:
        return m_bracket.group(1).strip()
    m_stage = re.search(r"You are\s+(?:the\s+)?(Stage\s+\d+\s+[A-Za-z0-9_]+)", text)
    if m_stage:
        return m_stage.group(1).strip()
    m = re.search(r"You are\s+(?:a\s+|an\s+|the\s+)?['`\"]?([A-Za-z0-9_:]+(?:-[A-Za-z0-9_:]+)*)['`\"]?", text)
    if m:
        cand = m.group(1).strip()
        if cand.lower() not in ("a", "an", "the", "now", "here"):
            return cand
    return None


def find_transcript_path(
    conv_id_or_path: Union[str, Path],
    brain_dir: Optional[Union[str, Path]] = None,
) -> Tuple[Optional[Path], str]:
    """Resolves (transcript_path, conversation_id) for either a path or conversation ID."""
    raw = str(conv_id_or_path or "").strip()
    if not raw:
        return None, "unknown"
    p = Path(raw)
    if p.is_file():
        cid = p.parent.name
        if ".system_generated" in p.parts:
            idx = p.parts.index(".system_generated")
            if idx > 0:
                cid = p.parts[idx - 1]
        return p, cid

    b_dir = get_active_brain_dir(brain_dir)
    convo_dir = p if p.is_dir() else (b_dir / raw)
    cid = convo_dir.name
    for rel in (
        convo_dir / ".system_generated" / "logs" / "transcript_full.jsonl",
        convo_dir / "transcript_full.jsonl",
        convo_dir / ".system_generated" / "logs" / "transcript.jsonl",
        convo_dir / "transcript.jsonl",
    ):
        if rel.is_file():
            return rel, cid
    return None, cid


def load_transcript_steps(
    transcript_path: Path,
) -> Tuple[List[Dict[str, Any]], List[int], Dict[int, float]]:
    """
    Parses transcript JSONL with a bounded stat-keyed LRU cache.
    Returns (ordered_steps, raw_line_sizes, {step_index: unix_ts}).
    """
    try:
        st = transcript_path.stat()
    except OSError:
        return [], [], {}

    cache_key = (str(transcript_path), int(st.st_mtime_ns), int(st.st_size))
    cached = _TRANSCRIPT_CACHE.get(cache_key)
    if cached is not None:
        _TRANSCRIPT_CACHE.move_to_end(cache_key)
        return cached

    steps: List[Dict[str, Any]] = []
    sizes: List[int] = []
    ts_map: Dict[int, float] = {}
    try:
        with open(transcript_path, "rb") as f:
            for idx, raw_line in enumerate(f):
                stripped = raw_line.strip()
                if not stripped:
                    continue
                try:
                    obj = json.loads(stripped.decode("utf-8", errors="replace"))
                except (json.JSONDecodeError, ValueError):
                    continue
                if not isinstance(obj, dict):
                    continue
                s_idx = int(obj.get("step_index", idx) if isinstance(obj.get("step_index"), (int, float)) else idx)
                ts_val = parse_step_timestamp(obj.get("created_at") or obj.get("timestamp"))
                if ts_val is not None:
                    ts_map[s_idx] = ts_val
                steps.append(obj)
                sizes.append(len(stripped))
    except OSError:
        return [], [], {}

    result = (steps, sizes, ts_map)
    if len(_TRANSCRIPT_CACHE) >= MAX_TRANSCRIPT_CACHE:
        _TRANSCRIPT_CACHE.popitem(last=False)
    _TRANSCRIPT_CACHE[cache_key] = result
    return result


def is_transcript_completed(transcript_path: Path) -> bool:
    """O(1) tail reader detecting completed PLANNER_RESPONSE or fatal error markers."""
    if not transcript_path.is_file():
        return False
    try:
        with open(transcript_path, "rb") as f:
            f.seek(0, os.SEEK_END)
            file_size = f.tell()
            if file_size == 0:
                return False
            f.seek(max(0, file_size - 65536), os.SEEK_SET)
            chunk = f.read().decode("utf-8", errors="replace")
    except OSError:
        return False

    for raw_line in reversed(chunk.splitlines()):
        stripped = raw_line.strip()
        if not stripped:
            continue
        try:
            obj = json.loads(stripped)
        except (json.JSONDecodeError, ValueError):
            continue
        if not isinstance(obj, dict):
            continue
        obj_type = obj.get("type")
        if obj_type == "EPHEMERAL_MESSAGE":
            continue
        if obj_type == "SYSTEM_MESSAGE":
            content_str = str(obj.get("content") or "")
            if any(k in content_str for k in ("RESOURCE_EXHAUSTED", "stopped", "killed", "failed", "execution error")):
                return True
            continue
        if obj_type == "PLANNER_RESPONSE":
            return obj.get("status") == "DONE" and not (obj.get("tool_calls") or obj.get("toolCalls"))
        return False
    return False


def is_conversation_completed(conv_id: str, brain_dir: Optional[Path] = None) -> bool:
    """Returns True if the target conversation transcript ended cleanly."""
    t_path, _ = find_transcript_path(conv_id, brain_dir=brain_dir)
    return is_transcript_completed(t_path) if t_path is not None else False


def extract_spawned_subagents(steps: List[Dict[str, Any]], parent_cid: str = "") -> Dict[str, str]:
    """
    Extracts {child_conversation_id: role} strictly from decoded JSON tool calls and outputs.
    Eliminates escaped-quote regex failures such as ['\\'] captures.
    """
    children: Dict[str, str] = {}
    pending_role = ""

    for step in steps:
        if step.get("type") == "PLANNER_RESPONSE":
            pending_role = ""

        raw_tcs = step.get("tool_calls") or step.get("toolCalls") or []
        if isinstance(raw_tcs, list):
            for tc in raw_tcs:
                if not isinstance(tc, dict):
                    continue
                t_name = str(tc.get("name") or "")
                t_args = tc.get("args") or tc.get("arguments") or {}
                if isinstance(t_args, str):
                    try:
                        t_args = json.loads(t_args)
                    except (json.JSONDecodeError, ValueError):
                        t_args = {}
                if t_name == "invoke_subagent" and isinstance(t_args, dict):
                    pending_role = str(t_args.get("TypeName") or t_args.get("Role") or "subagent").strip()
                    arg_cid = str(t_args.get("conversationId") or t_args.get("conversation_id") or "").strip()
                    if arg_cid and arg_cid != parent_cid and "\\" not in arg_cid and arg_cid not in _EXCLUDED_CIDS:
                        children[arg_cid] = pending_role or children.get(arg_cid, "subagent")
                elif t_name == "send_message" and isinstance(t_args, dict):
                    recip = str(t_args.get("Recipient") or "").strip()
                    if (_UUID_RE.match(recip) or (len(recip) >= 6 and "\\" not in recip and "/" not in recip)) and recip != parent_cid and recip not in _EXCLUDED_CIDS:
                        children.setdefault(recip, "subagent")
                res = tc.get("result") or tc.get("output")
                if res:
                    if isinstance(res, str):
                        try:
                            res_parsed = json.loads(res)
                            if isinstance(res_parsed, dict):
                                res = res_parsed
                        except (json.JSONDecodeError, ValueError):
                            pass
                    if isinstance(res, dict):
                        res_cid = str(res.get("conversationId") or res.get("conversation_id") or "").strip()
                        if res_cid and res_cid != parent_cid and "\\" not in res_cid and res_cid not in _EXCLUDED_CIDS:
                            children[res_cid] = pending_role or children.get(res_cid, "subagent")
                    res_str = json.dumps(res) if isinstance(res, dict) else str(res)
                    for cid in _CID_PAIR_RE.findall(res_str):
                        if cid != parent_cid and "\\" not in cid and cid not in _EXCLUDED_CIDS:
                            children[cid] = pending_role or children.get(cid, "subagent")

        content_str = str(step.get("content") or "")
        if "Created the following subagent" in content_str or (
            pending_role and ("conversationId" in content_str or "conversation_id" in content_str)
        ):
            if not content_str.startswith("Created At:") or "Command output:" not in content_str:
                for cid in _CID_PAIR_RE.findall(content_str):
                    if cid != parent_cid and "\\" not in cid and cid not in _EXCLUDED_CIDS:
                        children[cid] = pending_role or children.get(cid, "subagent")
                        pending_role = ""

    return children


def _load_meta_parent(
    convo_dir: Path, cutoff: Optional[float] = None
) -> Tuple[Optional[str], Optional[str]]:
    """Reads optional (parent_id, role) from recent session metadata or transcript header line."""
    for name in ("meta.json", "metadata.json", "session_meta.json", ".metadata"):
        mp = convo_dir / name
        if not mp.is_file():
            continue
        try:
            st = mp.stat()
            if cutoff is not None and st.st_mtime < cutoff:
                continue
            data = json.loads(mp.read_text(encoding="utf-8", errors="replace")[:16384])
            if isinstance(data, dict):
                pid = data.get("parent_conversation_id") or data.get("parentConversationId") or data.get("parentId") or data.get("parent_id")
                role = data.get("role")
                if pid:
                    return str(pid).strip(), (str(role).strip() if role else None)
        except (OSError, json.JSONDecodeError, ValueError):
            pass

    for t_cand in (
        convo_dir / ".system_generated" / "logs" / "transcript.jsonl",
        convo_dir / "transcript.jsonl",
    ):
        if not t_cand.is_file():
            continue
        try:
            if cutoff is not None and t_cand.stat().st_mtime < cutoff:
                continue
            with open(t_cand, "r", encoding="utf-8", errors="replace") as f:
                first_line = f.readline(65536).strip()
            if first_line.startswith("{"):
                obj = json.loads(first_line)
                if isinstance(obj, dict):
                    meta = obj.get("_meta") if isinstance(obj.get("_meta"), dict) else {}
                    pid = (
                        obj.get("parent_conversation_id")
                        or obj.get("parentConversationId")
                        or meta.get("antigravity.google/root_conversation_id")
                        or obj.get("root_conversation_id")
                    )
                    if pid:
                        return str(pid).strip(), extract_role_from_text(str(obj.get("content") or ""))
        except (OSError, json.JSONDecodeError, ValueError):
            pass
    return None, None


def build_measured_breakdown(
    steps: List[Dict[str, Any]],
    total_tokens: int,
    system_prompt_tokens: int = 0,
    tool_defs_tokens: int = 0,
) -> TokenBreakdown:
    """
    Computes measured per-epoch token buckets plus honest `unattributed` remainder.
    Never applies synthetic 40/60 system/tool percentages or dumps unattributed gaps into `model`.
    """
    user_t = model_t = thought_t = tool_t = cp_t = sys_t = 0
    for s in steps:
        stype = str(s.get("type") or "").upper()
        content = str(s.get("content") or "")
        thinking = str(s.get("thinking") or "")
        explicit_step_tok = int(s.get("tokens") or 0)

        if thinking:
            t_tok = estimate_tokens(thinking)
            thought_t += t_tok
        else:
            t_tok = 0

        if is_transcript_checkpoint_step(s):
            cp_t += explicit_step_tok or estimate_tokens(content)
        elif stype == "USER_INPUT":
            user_t += explicit_step_tok or estimate_tokens(content)
        elif stype in ("SYSTEM", "SYSTEM_MESSAGE", "EPHEMERAL_MESSAGE"):
            sys_t += explicit_step_tok or estimate_tokens(content)
        elif stype in ("PLANNER_RESPONSE", "MODEL_OUTPUT"):
            has_tools = bool(s.get("tool_calls") or s.get("toolCalls"))
            if has_tools:
                tool_t += estimate_tokens(json.dumps(s.get("tool_calls") or s.get("toolCalls")))
            body_tok = max(0, (explicit_step_tok - t_tok) if explicit_step_tok > 0 else estimate_tokens(content))
            model_t += body_tok
        else:
            tool_t += explicit_step_tok or estimate_tokens(content)

    effective_sys = max(sys_t, int(system_prompt_tokens or 0))
    effective_tool_defs = int(tool_defs_tokens or 0)
    measured = user_t + model_t + thought_t + tool_t + cp_t + effective_sys + effective_tool_defs
    if total_tokens <= 0:
        unattributed = 0
    else:
        unattributed = max(0, int(total_tokens) - measured)

    return TokenBreakdown(
        user=user_t,
        model=model_t,
        thought=thought_t,
        tool=tool_t,
        tool_defs=effective_tool_defs,
        checkpoint=cp_t,
        system=effective_sys,
        unattributed=unattributed,
    )


def discover_active_subagents(
    parent_cid: Optional[str] = None,
    brain_dir: Optional[Union[str, Path]] = None,
    db_dir: Optional[Path] = None,
    max_age_hours: float = 4.0,
    include_completed: bool = False,
) -> List[SubagentContextStatus]:
    """
    Discovers live subagent sessions scoped strictly to parent_cid.
    When parent_cid is None, returns [] to prevent cross-session contamination.
    """
    if not parent_cid or not str(parent_cid).strip():
        return []

    b_dir = get_active_brain_dir(brain_dir)
    if not b_dir.is_dir():
        return []

    norm_parent = str(parent_cid).strip()
    parent_t_path, _ = find_transcript_path(norm_parent, brain_dir=b_dir)
    spawned_map: Dict[str, str] = {}
    if parent_t_path is not None:
        p_steps, _, _ = load_transcript_steps(parent_t_path)
        spawned_map = extract_spawned_subagents(p_steps, parent_cid=norm_parent)

    cutoff = time.time() - (max_age_hours * 3600.0)
    statuses: List[SubagentContextStatus] = []

    candidate_ids = set(spawned_map.keys())
    try:
        for entry in b_dir.iterdir():
            if not entry.is_dir() or entry.name == norm_parent:
                continue
            meta_pid, _ = _load_meta_parent(entry, cutoff=cutoff)
            if meta_pid == norm_parent:
                candidate_ids.add(entry.name)
    except OSError:
        pass

    for cid in sorted(candidate_ids):
        t0 = time.perf_counter()
        t_path, resolved_cid = find_transcript_path(cid, brain_dir=b_dir)
        convo_dir = b_dir / resolved_cid
        if t_path is None:
            continue
        try:
            mtime = t_path.stat().st_mtime
            if mtime < cutoff:
                continue
        except OSError:
            continue

        if not include_completed and is_transcript_completed(t_path):
            continue

        steps, _, ts_map = load_transcript_steps(t_path)
        db_metrics = read_db_trajectory_state(resolved_cid, db_dir=db_dir, transcript_timestamps=ts_map)

        meta_pid, meta_role = _load_meta_parent(convo_dir)
        if meta_pid and meta_pid != norm_parent:
            continue
        role = spawned_map.get(resolved_cid) or meta_role or "subagent"
        if role == "subagent" and steps:
            detected_role = extract_role_from_text(str(steps[0].get("content") or ""))
            if detected_role:
                role = detected_role

        # Active-epoch token/step count: DB authoritative first, else transcript active-epoch text
        cp_indices = [i for i, s in enumerate(steps) if is_transcript_checkpoint_step(s)]
        active_slice = steps[cp_indices[-1] :] if cp_indices else steps
        epoch_steps = db_metrics.epoch_steps if db_metrics.total_steps > 0 else len(active_slice)
        max_ctx = db_metrics.max_context_tokens or DEFAULT_CONTEXT_WINDOW_TOKENS

        if db_metrics.tokens > 0:
            token_count = db_metrics.tokens
            is_prov = db_metrics.is_provisional
        else:
            token_count = sum(
                int(s.get("tokens") or 0) or (estimate_tokens(str(s.get("content") or "")) + estimate_tokens(str(s.get("thinking") or "")))
                for s in active_slice
            )
            is_prov = token_count > 0

        health_zone, recommendation = classify_context_health(token_count, epoch_steps, max_context_tokens=max_ctx)
        latency_ms = round((time.perf_counter() - t0) * 1000.0, 3)
        last_iso = datetime.fromtimestamp(mtime, tz=timezone.utc).isoformat().replace("+00:00", "Z")

        statuses.append(
            SubagentContextStatus(
                conversation_id=resolved_cid,
                role=role,
                step_count=len(steps) or db_metrics.total_steps,
                token_count=token_count,
                health_zone=health_zone,
                recommendation=recommendation,
                latency_ms=latency_ms,
                parent_conversation_id=meta_pid or norm_parent,
                max_context_tokens=max_ctx,
                epoch_step_count=epoch_steps,
                is_provisional=is_prov,
                transcript_path=str(t_path),
                last_updated=last_iso,
            )
        )

    statuses.sort(key=lambda s: s.last_updated or "", reverse=True)
    return statuses
