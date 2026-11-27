# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Arafat Zahan (@kuasha420)
# Corporate Stewardship & Infrastructure: Purrfect Software Limited (PSL)
# Governed by: ICARO-42/b Ordinance (Company-Supported Personal IP Framework)

"""
Centralized Context Engine for Agyis Harness (Issue #95 / ADR-031).
Provides single-source resolution for active conversation ID, brain directory,
and active workspace across all CLI commands and subagents.
"""

from __future__ import annotations

import errno
import fcntl
import json
import os
from pathlib import Path
import subprocess
import tempfile
from typing import List, Optional, Tuple, Union


def get_active_app_data_dir() -> Path:
    """Resolves the active Antigravity appDataDir (~/.gemini/antigravity or ~/.gemini/antigravity-cli)."""
    env_app_data = os.environ.get("ANTIGRAVITY_APP_DATA_DIR")
    if env_app_data and env_app_data.strip():
        return Path(env_app_data.strip())
    env_brain = os.environ.get("ANTIGRAVITY_BRAIN_DIR")
    if env_brain and env_brain.strip():
        return Path(env_brain.strip()).parent
    primary = Path.home() / ".gemini" / "antigravity"
    cli_fallback = Path.home() / ".gemini" / "antigravity-cli"
    if not primary.exists() and cli_fallback.exists():
        return cli_fallback
    return primary


def get_app_data_dir_candidates() -> List[Path]:
    """Returns ordered Antigravity appDataDir search candidates (respecting explicit env overrides)."""
    env_app_data = os.environ.get("ANTIGRAVITY_APP_DATA_DIR")
    if env_app_data and env_app_data.strip():
        return [Path(env_app_data.strip())]
    env_brain = os.environ.get("ANTIGRAVITY_BRAIN_DIR")
    if env_brain and env_brain.strip():
        return [Path(env_brain.strip()).parent]
    return [
        Path.home() / ".gemini" / "antigravity",
        Path.home() / ".gemini" / "antigravity-cli",
    ]


def detect_presence_conversation_id(
    presence_dir: Optional[Union[Path, str]] = None,
) -> Optional[str]:
    """
    Detects the active root conversation ID by probing flock() on
    <appDataDir>/presence/<cid>.lock without blocking or holding any lock.
    """
    if presence_dir is not None and str(presence_dir).strip():
        p_dirs = [Path(presence_dir)]
    else:
        env_presence = os.environ.get("ANTIGRAVITY_PRESENCE_DIR")
        if env_presence and env_presence.strip():
            p_dirs = [Path(env_presence.strip())]
        else:
            p_dirs = [d / "presence" for d in get_app_data_dir_candidates()]

    locked: List[Tuple[float, str]] = []
    for p_dir in p_dirs:
        if not p_dir.is_dir():
            continue
        try:
            entries = list(p_dir.glob("*.lock"))
        except OSError:
            continue

        for lock_file in entries:
            cid = lock_file.stem.strip()
            if not cid:
                continue
            fd = -1
            try:
                fd = os.open(str(lock_file), os.O_RDONLY)
                try:
                    fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
                    fcntl.flock(fd, fcntl.LOCK_UN)
                except BlockingIOError:
                    try:
                        mtime = lock_file.stat().st_mtime
                    except OSError:
                        mtime = 0.0
                    locked.append((mtime, cid))
                except OSError as exc:
                    if exc.errno in (errno.EAGAIN, errno.EWOULDBLOCK, errno.EACCES):
                        try:
                            mtime = lock_file.stat().st_mtime
                        except OSError:
                            mtime = 0.0
                        locked.append((mtime, cid))
            except OSError:
                continue
            finally:
                if fd >= 0:
                    try:
                        os.close(fd)
                    except OSError:
                        pass

    if not locked:
        return None
    locked.sort(key=lambda item: item[0], reverse=True)
    return locked[0][1]


def get_active_conversation_id(
    explicit_id: Optional[str] = None,
    *,
    check_presence: bool = False,
) -> Optional[str]:
    """
    Resolves the active conversation/session ID using the canonical priority hierarchy:
    1. Explicitly provided conversation ID argument
    2. ANTIGRAVITY_CONVERSATION_ID
    3. ANTIGRAVITY_SOURCE_METADATA JSON parsing (tool.conversationId / conversationId / conversation_id)
    4. AGYIS_CONVERSATION_ID
    5. GEMINI_CONVERSATION_ID
    6. Optional flock() probe on <appDataDir>/presence/<cid>.lock (when check_presence=True)
    7. None fallback
    """
    if explicit_id is not None and str(explicit_id).strip():
        return str(explicit_id).strip()

    env_ag = os.environ.get("ANTIGRAVITY_CONVERSATION_ID")
    if env_ag and env_ag.strip():
        return env_ag.strip()

    meta_raw = os.environ.get("ANTIGRAVITY_SOURCE_METADATA")
    if meta_raw and meta_raw.strip():
        try:
            meta = json.loads(meta_raw)
            if isinstance(meta, dict):
                tool_dict = meta.get("tool")
                cid = None
                if isinstance(tool_dict, dict):
                    cid = tool_dict.get("conversationId")
                if not cid:
                    cid = meta.get("conversationId") or meta.get("conversation_id")
                if cid and isinstance(cid, str) and cid.strip():
                    return cid.strip()
        except (json.JSONDecodeError, TypeError, ValueError):
            pass

    env_agyis = os.environ.get("AGYIS_CONVERSATION_ID")
    if env_agyis and env_agyis.strip():
        return env_agyis.strip()

    env_gemini = os.environ.get("GEMINI_CONVERSATION_ID")
    if env_gemini and env_gemini.strip():
        return env_gemini.strip()

    if check_presence:
        return detect_presence_conversation_id()

    return None


def get_active_brain_dir(explicit_dir: Optional[Union[Path, str]] = None) -> Path:
    """
    Resolves the active brain directory using the canonical priority hierarchy:
    1. explicit_dir (if truthy, return Path(explicit_dir))
    2. ANTIGRAVITY_BRAIN_DIR
    3. ANTIGRAVITY_APP_DATA_DIR / "brain"
    4. GEMINI_BRAIN_DIR
    5. Fallback: Path.home() / ".gemini" / "antigravity" / "brain"
    """
    if explicit_dir is not None and str(explicit_dir).strip():
        return Path(explicit_dir)

    env_brain = os.environ.get("ANTIGRAVITY_BRAIN_DIR")
    if env_brain and env_brain.strip():
        return Path(env_brain.strip())

    env_app_data = os.environ.get("ANTIGRAVITY_APP_DATA_DIR")
    if env_app_data and env_app_data.strip():
        return Path(env_app_data.strip()) / "brain"

    env_gemini_brain = os.environ.get("GEMINI_BRAIN_DIR")
    if env_gemini_brain and env_gemini_brain.strip():
        return Path(env_gemini_brain.strip())

    primary = Path.home() / ".gemini" / "antigravity" / "brain"
    cli_fallback = Path.home() / ".gemini" / "antigravity-cli" / "brain"
    if not primary.exists() and cli_fallback.exists():
        return cli_fallback
    return primary


def get_brain_dir_candidates(explicit_dir: Optional[Union[Path, str]] = None) -> List[Path]:
    """Returns ordered brain directory search candidates (respecting explicit arg/env overrides)."""
    if explicit_dir is not None and str(explicit_dir).strip():
        return [Path(explicit_dir)]
    if any(
        (os.environ.get(k) or "").strip()
        for k in ("ANTIGRAVITY_BRAIN_DIR", "ANTIGRAVITY_APP_DATA_DIR", "GEMINI_BRAIN_DIR")
    ):
        return [get_active_brain_dir()]
    return [d / "brain" for d in get_app_data_dir_candidates()]


def is_in_temp_dir(path_val: Path) -> bool:
    """Returns True if path_val resolves to or inside the system temporary directory."""
    try:
        tmp_root = Path(tempfile.gettempdir()).resolve()
        res = path_val.resolve()
        return res == tmp_root or tmp_root in res.parents
    except OSError:
        return False


def is_in_live_home_gemini(path_val: Path) -> bool:
    """Returns True if path_val resolves to or inside Path.home() / '.gemini'."""
    try:
        home_gemini = (Path.home() / ".gemini").resolve()
        res = path_val.resolve()
        return res == home_gemini or home_gemini in res.parents
    except OSError:
        return True


def get_active_workspace(explicit_ws: Optional[Union[Path, str]] = None) -> Path:
    """
    Resolves the active workspace directory using canonical priority:
    1. explicit_ws (if truthy, return Path(explicit_ws).resolve())
    2. Git top-level via subprocess `git rev-parse --show-toplevel` (fallback to cwd if git fails)
    3. Fallback: Path.cwd().resolve()
    """
    if explicit_ws is not None and str(explicit_ws).strip():
        return Path(explicit_ws).resolve()

    try:
        res = subprocess.run(
            ["git", "rev-parse", "--show-toplevel"],
            capture_output=True,
            text=True,
            check=False,
        )
        if res.returncode == 0 and res.stdout.strip():
            top_level = Path(res.stdout.strip())
            if top_level.is_dir():
                return top_level.resolve()
    except (subprocess.SubprocessError, OSError):
        pass

    return Path.cwd().resolve()


__all__ = [
    "get_active_app_data_dir",
    "get_app_data_dir_candidates",
    "detect_presence_conversation_id",
    "get_active_conversation_id",
    "get_active_brain_dir",
    "get_brain_dir_candidates",
    "get_active_workspace",
    "is_in_temp_dir",
    "is_in_live_home_gemini",
]
