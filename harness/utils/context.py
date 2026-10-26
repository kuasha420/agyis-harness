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

import json
import os
from pathlib import Path
import subprocess
from typing import Optional, Union


def get_active_conversation_id(explicit_id: Optional[str] = None) -> Optional[str]:
    """
    Resolves the active conversation/session ID using the canonical priority hierarchy:
    1. Explicitly provided conversation ID argument
    2. ANTIGRAVITY_CONVERSATION_ID
    3. ANTIGRAVITY_SOURCE_METADATA JSON parsing (tool.conversationId / conversationId / conversation_id)
    4. AGYIS_CONVERSATION_ID
    5. GEMINI_CONVERSATION_ID
    6. None fallback
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

    return Path.home() / ".gemini" / "antigravity" / "brain"


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
    except Exception:
        pass

    return Path.cwd().resolve()


__all__ = [
    "get_active_conversation_id",
    "get_active_brain_dir",
    "get_active_workspace",
]
