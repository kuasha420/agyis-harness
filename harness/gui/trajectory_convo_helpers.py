# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Arafat Zahan (@kuasha420)
# Corporate Stewardship & Infrastructure: Purrfect Software Limited (PSL)
# Governed by: ICARO-42/b Ordinance (Company-Supported Personal IP Framework)

"""
Conversation discovery and transcript metadata extraction helpers for Trajectory HUD.
"""

from __future__ import annotations

import json
from pathlib import Path
import re
from typing import Any, Dict, List, Optional

from harness.trajectory.transcript_reader import _load_meta_parent, find_transcript_path
from harness.utils.context import get_active_brain_dir

__all__ = [
    "_extract_conversation_summary",
    "_scan_transcript_parent_id",
    "get_recent_conversations",
]


def _scan_transcript_parent_id(transcript_path: Path) -> Optional[str]:
    """Scans initial lines of transcript for parent conversation ID metadata (DEF-BB-045)."""
    if not transcript_path.is_file():
        return None
    try:
        with open(transcript_path, "r", encoding="utf-8", errors="replace") as f:
            for _ in range(5):
                line = f.readline(16384).strip()
                if not line:
                    break
                if line.startswith("{"):
                    try:
                        obj = json.loads(line)
                        if isinstance(obj, dict):
                            meta = obj.get("_meta") if isinstance(obj.get("_meta"), dict) else {}
                            found_pid = (
                                obj.get("parent_conversation_id")
                                or obj.get("parentConversationId")
                                or obj.get("parentId")
                                or obj.get("parent_id")
                                or meta.get("antigravity.google/root_conversation_id")
                                or obj.get("root_conversation_id")
                            )
                            if found_pid:
                                return str(found_pid).strip()
                    except json.JSONDecodeError:
                        pass
    except OSError:
        pass
    return None


def _extract_conversation_summary(convo_dir: Path, transcript_path: Path) -> str:
    """Extracts a short human-readable summary for a conversation."""
    meta_path = convo_dir / "meta.json"
    if meta_path.is_file():
        try:
            data = json.loads(meta_path.read_text(encoding="utf-8", errors="replace"))
            summary = data.get("summary") or data.get("title")
            if summary:
                return str(summary).strip()
        except (json.JSONDecodeError, OSError, ValueError, KeyError):
            pass
    if transcript_path.is_file():
        try:
            with open(transcript_path, "r", encoding="utf-8", errors="replace") as f:
                for line in f:
                    if not line.strip():
                        continue
                    try:
                        s = json.loads(line)
                        if (s.get("type") == "USER_INPUT" or "user" in str(s.get("source") or s.get("role") or "").lower()) and s.get("content"):
                            raw = str(s["content"]).strip()
                            m = re.search(r"<USER_REQUEST>(.*?)(?:</USER_REQUEST>|$)", raw, re.DOTALL)
                            clean = (m.group(1) if m else raw).strip()
                            if clean:
                                first_line = clean.splitlines()[0][:60].strip()
                                if first_line:
                                    return first_line
                    except (json.JSONDecodeError, ValueError, KeyError):
                        continue
        except OSError:
            pass
    return f"Session {convo_dir.name[:8]}"


def get_recent_conversations(brain_dir: Optional[Path] = None, limit: Optional[int] = 100) -> List[Dict[str, Any]]:
    """Discovers recent Antigravity conversations sorted by modification time (DEF-BB-041 / DEF-BB-045)."""
    base_brain = get_active_brain_dir(brain_dir)
    if not base_brain.is_dir():
        return []

    conversations: List[Dict[str, Any]] = []
    for d in base_brain.iterdir():
        if d.is_dir() and d.name != ".system_generated":
            t_log, _ = find_transcript_path(d)
            if t_log and t_log.is_file():
                try:
                    summary = _extract_conversation_summary(d, t_log)
                    pid, _ = _load_meta_parent(d)
                    if not pid:
                        pid = _scan_transcript_parent_id(t_log)

                    item: Dict[str, Any] = {
                        "id": d.name,
                        "summary": summary,
                        "mtime": t_log.stat().st_mtime,
                    }
                    if pid:
                        item["parent_id"] = pid
                        item["parentConversationId"] = pid
                    conversations.append(item)
                except OSError:
                    continue

    conversations.sort(key=lambda c: c["mtime"], reverse=True)
    return conversations[:limit] if limit is not None else conversations
