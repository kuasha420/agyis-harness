# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Arafat Zahan (@kuasha420)
# Corporate Stewardship & Infrastructure: Purrfect Software Limited (PSL)
# Governed by: ICARO-42/b Ordinance (Company-Supported Personal IP Framework)

"""
Antigravity 2.35.2 `exa.hooks_pb` Wire Compatibility & Bounded Advisory Queue (Wave 1.2).

Enforces strict `PreToolHookResult` / `StopHookResult` protojson contracts while routing
operational diagnostics to `sys.stderr` and model-facing nudges through a bounded,
one-shot CID-scoped queue drained by `PreInvocation` into `injectSteps`.
"""

from __future__ import annotations

import json
from pathlib import Path
import sys
from typing import Any, Dict, List, Optional

from harness.utils.state import atomic_write_json, get_state_dir, sanitize_conv_id

MAX_PENDING_ADVISORIES: int = 8
PRE_TOOL_WIRE_KEYS: frozenset[str] = frozenset({
    "decision",
    "reason",
    "overwrite",
    "permissionOverrides",
    "allowTool",
    "denyReason",
})
STOP_WIRE_KEYS: frozenset[str] = frozenset({"decision", "reason"})


def _pending_advisories_path(conv_id: str, state_dir: Optional[Path] = None) -> Path:
    """Returns CID-scoped path for queued one-shot PreInvocation advisories."""
    base = Path(state_dir) if state_dir is not None else get_state_dir()
    safe_cid = sanitize_conv_id(conv_id or "default")
    return base / f"pending_advisories_{safe_cid}.json"


def build_system_message_step(
    system_message: str = "",
    *,
    user_markdown: Optional[str] = None,
    metadata: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Builds a PreInvocation/SessionStart systemMessage step supporting optional metadata.user_markdown."""
    meta: Dict[str, Any] = dict(metadata) if isinstance(metadata, dict) else {}
    if isinstance(user_markdown, str) and user_markdown.strip():
        meta["user_markdown"] = user_markdown.strip()
    return {
        "systemMessage": {
            "systemMessage": str(system_message or ""),
            "metadata": meta,
        }
    }


def _parse_pending_entry(raw: Any) -> Optional[tuple[str, str]]:
    if isinstance(raw, str):
        text = raw.strip()
        return (text, "") if text else None
    if isinstance(raw, dict):
        sys_msg = str(raw.get("systemMessage") or raw.get("msg") or "").strip()
        umd = str(raw.get("user_markdown") or "").strip()
        if sys_msg or umd:
            return (sys_msg, umd)
    return None


def _read_pending_entries(target: Path) -> List[tuple[str, str]]:
    entries: List[tuple[str, str]] = []
    try:
        if target.is_file() and 0 < target.stat().st_size <= 65_536:
            parsed = json.loads(target.read_text(encoding="utf-8", errors="ignore"))
            if isinstance(parsed, list):
                for raw in parsed:
                    item = _parse_pending_entry(raw)
                    if item is not None:
                        entries.append(item)
    except (OSError, json.JSONDecodeError, ValueError, TypeError):
        return []
    return entries


def enqueue_pending_advisory(
    conv_id: str,
    msg: str = "",
    state_dir: Optional[Path] = None,
    *,
    user_markdown: Optional[str] = None,
    max_items: int = MAX_PENDING_ADVISORIES,
) -> None:
    """Appends a bounded, deduplicated advisory (plus optional user_markdown) to the CID one-shot queue."""
    text = str(msg or "").strip()
    umd = str(user_markdown or "").strip() if isinstance(user_markdown, str) else ""
    if not text and not umd:
        return
    target = _pending_advisories_path(conv_id, state_dir=state_dir)
    cap = max(1, int(max_items))
    entries = _read_pending_entries(target)

    if "[CHECKPOINT HORIZON:" in text:
        entries = [(s, u) for s, u in entries if "[CHECKPOINT HORIZON:" not in s]
    else:
        entries = [(s, u) for s, u in entries if (s, u) != (text, umd)]
    entries.append((text, umd))
    if len(entries) > cap:
        entries = entries[-cap:]

    serialized: List[Any] = [
        {"systemMessage": s, "user_markdown": u} if u else s for s, u in entries
    ]
    try:
        target.parent.mkdir(parents=True, exist_ok=True)
        atomic_write_json(target, serialized)
    except OSError:
        pass


def _consume_pending_entries(
    conv_id: str,
    state_dir: Optional[Path] = None,
) -> List[tuple[str, str]]:
    target = _pending_advisories_path(conv_id, state_dir=state_dir)
    if not target.is_file():
        return []
    entries = _read_pending_entries(target)
    try:
        target.unlink(missing_ok=True)
    except OSError:
        pass
    return entries


def drain_pending_advisories(
    conv_id: str,
    state_dir: Optional[Path] = None,
) -> List[str]:
    """Atomically reads and clears all queued one-shot advisories for conv_id as plain strings."""
    return [s or u for s, u in _consume_pending_entries(conv_id, state_dir=state_dir)]


def drain_pending_advisory_steps(
    conv_id: str,
    state_dir: Optional[Path] = None,
) -> List[Dict[str, Any]]:
    """Atomically drains queued one-shot advisories as injectSteps systemMessage envelopes."""
    return [
        build_system_message_step(s, user_markdown=u or None)
        for s, u in _consume_pending_entries(conv_id, state_dir=state_dir)
    ]


def emit_stderr_diagnostic(msg: str) -> None:
    """Writes a hook operational diagnostic line safely to sys.stderr."""
    text = str(msg or "").strip()
    if not text:
        return
    try:
        sys.stderr.write(text + "\n")
        sys.stderr.flush()
    except OSError:
        pass


def strip_wire_keys(
    result: Dict[str, Any],
    *,
    allowed_keys: frozenset[str] = PRE_TOOL_WIRE_KEYS,
) -> Dict[str, Any]:
    """Filters a hook return dict strictly to protojson-accepted wire fields."""
    if not isinstance(result, dict):
        return {}
    return {k: v for k, v in result.items() if k in allowed_keys}


__all__ = [
    "MAX_PENDING_ADVISORIES",
    "PRE_TOOL_WIRE_KEYS",
    "STOP_WIRE_KEYS",
    "build_system_message_step",
    "drain_pending_advisories",
    "drain_pending_advisory_steps",
    "emit_stderr_diagnostic",
    "enqueue_pending_advisory",
    "strip_wire_keys",
]
