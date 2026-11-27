# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Arafat Zahan (@kuasha420)
# Corporate Stewardship & Infrastructure: Purrfect Software Limited (PSL)
# Governed by: ICARO-42/b Ordinance (Company-Supported Personal IP Framework)

"""
Canonical state directory helper and atomic persistence for Agyis Harness (ADR-014 / ADR-015).
"""

from __future__ import annotations

import json
import os
from pathlib import Path
import re
import sys
import tempfile
from typing import Any, List, Optional

_SAFE_CONV_ID_RE = re.compile(r"[^a-zA-Z0-9_\-]+")


def sanitize_conv_id(conv_id: Any, default: str = "default") -> str:
    """Normalizes a conversation ID into a path-safe filename stem."""
    raw = str(conv_id or "").strip()
    if not raw:
        return default
    cleaned = _SAFE_CONV_ID_RE.sub("_", raw)
    if not cleaned or not cleaned.strip("_"):
        return default
    return cleaned


def get_state_dir(default_name: Optional[str] = None) -> Path:
    """
    Returns the harness state directory respecting AGYIS_HARNESS_STATE_DIR and PSL_HARNESS_STATE_DIR.
    Defaults to /tmp/agyis_harness_state_{uid} using os.getuid() when not set.
    Hardened with try...except OSError for directory creation.
    """
    env_dir = os.environ.get("AGYIS_HARNESS_STATE_DIR") or os.environ.get("PSL_HARNESS_STATE_DIR")
    if env_dir and env_dir.strip():
        path = Path(env_dir.strip())
    else:
        uid = os.getuid() if hasattr(os, "getuid") else 0
        if default_name:
            path = Path(f"/tmp/{default_name}")
        else:
            path = Path(f"/tmp/agyis_harness_state_{uid}")
    try:
        path.mkdir(parents=True, exist_ok=True)
    except OSError:
        pass
    return path


def atomic_write_text(path: Path | str, content: str, encoding: str = "utf-8") -> None:
    """
    Atomically writes text to target path using NamedTemporaryFile in the same directory and os.replace.
    """
    target = Path(path).resolve()
    parent = target.parent
    try:
        parent.mkdir(parents=True, exist_ok=True)
    except OSError:
        pass

    with tempfile.NamedTemporaryFile(
        "w",
        dir=parent,
        prefix=f".{target.name}.tmp_",
        delete=False,
        encoding=encoding,
    ) as tf:
        tf.write(content)
        tf.flush()
        os.fsync(tf.fileno())
        temp_name = tf.name

    os.replace(temp_name, target)


def atomic_write_json(path: Path | str, data: Any, indent: Optional[int] = None) -> None:
    """
    Atomically serializes data to JSON and persists to path.
    """
    content = json.dumps(data, indent=indent)
    atomic_write_text(path, content)


def save_history(conv_id: str, history: List[Any], target_dir: Optional[Path] = None) -> Path:
    """
    Atomically persists session history to history_{conv_id}.json in target_dir or get_state_dir().
    Eliminates file corruption under concurrent operations.
    """
    state_dir = target_dir or get_state_dir()
    safe_id = sanitize_conv_id(conv_id)
    history_file = state_dir / f"history_{safe_id}.json"
    atomic_write_json(history_file, history)
    return history_file


def load_history(conv_id: str, target_dir: Optional[Path] = None) -> List[Any]:
    """
    Loads session history from history_{conv_id}.json. Returns empty list if missing or corrupted.
    """
    state_dir = target_dir or get_state_dir()
    safe_id = sanitize_conv_id(conv_id)
    history_file = state_dir / f"history_{safe_id}.json"
    if not history_file.exists():
        return []
    try:
        data = json.loads(history_file.read_text(encoding="utf-8"))
        return data if isinstance(data, list) else []
    except (OSError, json.JSONDecodeError, ValueError) as exc:
        sys.stderr.write(f"[AGYIS STATE] Warning: Failed to load history '{history_file}': {exc}\n")
        return []


__all__ = [
    "get_state_dir",
    "sanitize_conv_id",
    "atomic_write_text",
    "atomic_write_json",
    "save_history",
    "load_history",
]

