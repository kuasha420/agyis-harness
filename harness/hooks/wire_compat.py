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


def enqueue_pending_advisory(
    conv_id: str,
    msg: str,
    state_dir: Optional[Path] = None,
    *,
    max_items: int = MAX_PENDING_ADVISORIES,
) -> None:
    """Appends a bounded, deduplicated model-facing advisory to the CID one-shot queue."""
    text = str(msg or "").strip()
    if not text:
        return
    target = _pending_advisories_path(conv_id, state_dir=state_dir)
    cap = max(1, int(max_items))
    items: List[str] = []
    try:
        if target.is_file() and 0 < target.stat().st_size <= 65_536:
            parsed = json.loads(target.read_text(encoding="utf-8", errors="ignore"))
            if isinstance(parsed, list):
                items = [str(x).strip() for x in parsed if isinstance(x, str) and str(x).strip()]
    except (OSError, json.JSONDecodeError, ValueError, TypeError):
        items = []

    if "[CHECKPOINT HORIZON:" in text:
        items = [item for item in items if "[CHECKPOINT HORIZON:" not in item]
    elif text in items:
        items.remove(text)
    items.append(text)
    if len(items) > cap:
        items = items[-cap:]

    try:
        target.parent.mkdir(parents=True, exist_ok=True)
        atomic_write_json(target, items)
    except OSError:
        pass


def drain_pending_advisories(
    conv_id: str,
    state_dir: Optional[Path] = None,
) -> List[str]:
    """Atomically reads and clears all queued one-shot advisories for conv_id."""
    target = _pending_advisories_path(conv_id, state_dir=state_dir)
    if not target.is_file():
        return []
    items: List[str] = []
    try:
        if 0 < target.stat().st_size <= 65_536:
            parsed = json.loads(target.read_text(encoding="utf-8", errors="ignore"))
            if isinstance(parsed, list):
                items = [str(x).strip() for x in parsed if isinstance(x, str) and str(x).strip()]
    except (OSError, json.JSONDecodeError, ValueError, TypeError):
        items = []
    try:
        target.unlink(missing_ok=True)
    except OSError:
        pass
    return items


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
    "drain_pending_advisories",
    "emit_stderr_diagnostic",
    "enqueue_pending_advisory",
    "strip_wire_keys",
]
