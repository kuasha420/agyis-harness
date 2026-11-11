# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Arafat Zahan (@kuasha420)
# Corporate Stewardship & Infrastructure: Purrfect Software Limited (PSL)
# Governed by: ICARO-42/b Ordinance (Company-Supported Personal IP Framework)

"""
Zero-Token Subagent Context Estimator & Health Gauge (ADR-025, Issue #109, #111).

Thin subagent-domain adapter backed by `harness.trajectory`:
- Uses active-epoch SQLite UsageMetadata / structured JSONL steps (no `file_size // 4`).
- Grades health by model context window percentage (<65% HEALTHY, 65-80% AMBER, >=80% RED_ALERT).
- Filters child subagents strictly by active parent conversation ID and non-completed status.
"""

from __future__ import annotations

import json
from pathlib import Path
import time
from typing import Any, Dict, List, Optional

from harness.trajectory.health import (
    DEFAULT_CONTEXT_WINDOW_TOKENS,
    SubagentContextStatus,
    classify_context_health,
)
from harness.trajectory.sqlite_reader import read_db_trajectory_state
from harness.trajectory.transcript_reader import (
    discover_active_subagents,
    extract_role_from_text,
    find_transcript_path,
    is_transcript_completed,
    load_transcript_steps,
)
from harness.utils.context import get_active_brain_dir, get_active_conversation_id
from harness.utils.tokens import estimate_tokens

_GENERIC_MSG_ROLES = frozenset({"user", "assistant", "system", "tool", "model"})


def _read_bounded_steps(p: Path, file_size: int) -> List[Dict[str, Any]]:
    """Reads structured JSON lines hermetically within bounded memory/time even on >2MB files."""
    if file_size <= 2 * 1024 * 1024:
        steps, _, _ = load_transcript_steps(p)
        return steps
    chunks: List[str] = []
    with open(p, "rb") as f:
        chunks.extend(f.read(65536).decode("utf-8", errors="replace").splitlines())
        if file_size > 327680:
            f.seek(file_size - 262144)
        tail_lines = f.read().decode("utf-8", errors="replace").splitlines()
        if file_size > 327680 and len(tail_lines) > 1:
            tail_lines = tail_lines[1:]
        chunks.extend(tail_lines)
    parsed: List[Dict[str, Any]] = []
    for raw in chunks:
        s = raw.strip("\x00 \t\r\n")
        if s.startswith("{"):
            try:
                obj = json.loads(s)
                if isinstance(obj, dict):
                    parsed.append(obj)
            except (json.JSONDecodeError, ValueError):
                pass
    return parsed


def estimate_subagent_context(
    transcript_path: Path | str,
    max_context_tokens: int = DEFAULT_CONTEXT_WINDOW_TOKENS,
    db_dir: Optional[Path] = None,
) -> SubagentContextStatus:
    """Estimate active-epoch context consumption and health gauge with zero LLM tokens."""
    t0 = time.perf_counter()
    p = Path(transcript_path)
    if not p.is_file():
        return SubagentContextStatus(
            conversation_id="unknown",
            role="unknown",
            step_count=0,
            token_count=0,
            health_zone="HEALTHY",
            recommendation="REUSE",
            latency_ms=round((time.perf_counter() - t0) * 1000.0, 3),
        )

    try:
        file_size = p.stat().st_size
    except OSError:
        file_size = 0

    _, candidate_id = find_transcript_path(p)
    steps = _read_bounded_steps(p, file_size)

    detected_id = ""
    detected_parent_id = ""
    detected_role = ""
    explicit_tokens = 0
    total_chars = 0
    cp_idx = -1

    for idx, obj in enumerate(steps):
        if obj.get("type") == "CHECKPOINT" or "<CONTEXT_SUMMARY>" in str(obj.get("content") or ""):
            cp_idx = idx
        if not detected_id:
            detected_id = str(obj.get("conversation_id") or obj.get("conversationId") or "").strip()
        if not detected_parent_id:
            meta = obj.get("_meta") if isinstance(obj.get("_meta"), dict) else {}
            detected_parent_id = str(
                obj.get("parent_conversation_id")
                or obj.get("parentConversationId")
                or meta.get("antigravity.google/root_conversation_id")
                or obj.get("root_conversation_id")
                or ""
            ).strip()
        if not detected_role:
            raw_role = str(obj.get("role") or obj.get("Role") or "").strip()
            if raw_role.lower() in _GENERIC_MSG_ROLES:
                raw_role = ""
            detected_role = raw_role or extract_role_from_text(str(obj.get("content") or "")) or ""

    active_slice = steps[cp_idx:] if cp_idx >= 0 else steps
    for obj in active_slice:
        tok_val = obj.get("token_count") or obj.get("tokens") or 0
        if isinstance(tok_val, (int, float)) and tok_val > 0:
            explicit_tokens += int(tok_val)
        c_str = str(obj.get("content") or "")
        t_str = str(obj.get("thinking") or "")
        total_chars += len(c_str) + len(t_str) if (c_str or t_str) else len(json.dumps(obj))

    final_id = detected_id or candidate_id
    db_metrics = read_db_trajectory_state(final_id, db_dir=db_dir) if final_id and final_id != "unknown" else None
    eff_window = (db_metrics.max_context_tokens if db_metrics and db_metrics.max_context_tokens > 0 else max_context_tokens)
    epoch_steps = db_metrics.epoch_steps if (db_metrics and db_metrics.total_steps > 0) else len(active_slice)
    total_steps = max(len(steps), db_metrics.total_steps if db_metrics else 0)

    if db_metrics and db_metrics.tokens > 0:
        token_count = db_metrics.tokens
        is_prov = db_metrics.is_provisional
    elif explicit_tokens > 0:
        token_count = explicit_tokens
        is_prov = False
    else:
        token_count = estimate_tokens(total_chars)
        is_prov = token_count > 0

    health_zone, rec = classify_context_health(token_count, epoch_steps, max_context_tokens=eff_window)
    return SubagentContextStatus(
        conversation_id=final_id,
        role=detected_role or "subagent",
        step_count=total_steps,
        token_count=token_count,
        health_zone=health_zone,
        recommendation=rec,
        latency_ms=round((time.perf_counter() - t0) * 1000.0, 3),
        parent_conversation_id=detected_parent_id or None,
        max_context_tokens=eff_window,
        epoch_step_count=epoch_steps,
        is_provisional=is_prov,
        transcript_path=str(p),
    )


def list_active_subagent_statuses(
    brain_dir: Optional[Path] = None,
    root_conv_id: Optional[str] = None,
    db_dir: Optional[Path] = None,
    include_completed: bool = False,
) -> List[SubagentContextStatus]:
    """
    Discovers active subagent statuses scoped strictly to parent conversation when active.
    Never scrapes unrelated sessions from global brain directory without explicit fixture brain_dir.
    """
    b_dir = get_active_brain_dir(brain_dir)
    if not b_dir.is_dir():
        return []

    eff_parent = (
        root_conv_id
        if brain_dir is not None
        else (root_conv_id or get_active_conversation_id())
    )
    if eff_parent:
        return discover_active_subagents(
            parent_cid=eff_parent,
            brain_dir=b_dir,
            db_dir=db_dir,
            include_completed=include_completed,
        )

    if brain_dir is None:
        return []

    statuses: List[SubagentContextStatus] = []
    seen_ids: set[str] = set()
    for item in sorted(b_dir.iterdir()):
        if not item.is_dir() or item.name.startswith("."):
            continue
        t_path, _ = find_transcript_path(item, brain_dir=b_dir)
        if t_path is None:
            continue
        if not include_completed and is_transcript_completed(t_path):
            continue
        status = estimate_subagent_context(t_path, db_dir=db_dir)
        if status.conversation_id not in seen_ids:
            seen_ids.add(status.conversation_id)
            statuses.append(status)
    return statuses


__all__ = [
    "SubagentContextStatus",
    "classify_context_health",
    "estimate_subagent_context",
    "extract_role_from_text",
    "list_active_subagent_statuses",
]
