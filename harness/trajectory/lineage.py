# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Arafat Zahan (@kuasha420)
# Corporate Stewardship & Infrastructure: Purrfect Software Limited (PSL)
# Governed by: ICARO-42/b Ordinance (Company-Supported Personal IP Framework)

"""
Read-Only Native Antigravity Subagent Lineage Resolver (ADR-035 / Wave 1.2).

Single Source of Truth querying `conversation_summaries.db` (?mode=ro) with
WAL-lag fallback across session metadata, early transcript headers, and parent
`extract_spawned_subagents` while strictly isolating hermetic test environments.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
import re
import sqlite3
from typing import Any, Dict, List, Optional, Tuple, Union

from harness.trajectory.sqlite_reader import normalize_cid
from harness.trajectory.sqlite_step_parser import _is_sdk_injection_text
from harness.trajectory.transcript_reader import (
    extract_role_from_text,
    extract_spawned_subagents,
    find_transcript_path,
)
from harness.utils.context import get_app_data_dir_candidates, is_in_live_home_gemini, is_in_temp_dir

_EPHEMERAL_CIDS: frozenset[str] = frozenset({"", "default", "test", "conv_test"})
_UUID_RE = re.compile(r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$")
_MESSAGE_SENDER_RE = re.compile(r"\[Message\][^\n]*?\bsender=([A-Za-z0-9][A-Za-z0-9_\-]{3,63})")


def _resolve_lineage_dirs(
    cid: str,
    *,
    app_data_dir: Optional[Union[Path, str]] = None,
    brain_dir: Optional[Union[Path, str]] = None,
    db_dir: Optional[Union[Path, str]] = None,
) -> Tuple[List[Path], List[Path]]:
    """Resolves deduplicated (app_data_dirs, brain_dirs) enforcing strict host-DB isolation."""
    if not cid:
        return [], []

    has_explicit = any(v is not None and str(v).strip() for v in (app_data_dir, brain_dir, db_dir))
    if not has_explicit and (cid in _EPHEMERAL_CIDS or cid.startswith("test-")):
        return [], []

    app_dirs: List[Path] = []
    brain_dirs: List[Path] = []

    def _add_app(p: Path) -> None:
        if p not in app_dirs:
            app_dirs.append(p)
        b = p / "brain"
        if b not in brain_dirs:
            brain_dirs.append(b)

    def _add_brain(p: Path) -> None:
        if p not in brain_dirs:
            brain_dirs.append(p)
        if p.parent not in app_dirs:
            app_dirs.append(p.parent)

    if has_explicit:
        if app_data_dir is not None and str(app_data_dir).strip():
            _add_app(Path(os.path.expanduser(str(app_data_dir).strip())))
        if brain_dir is not None and str(brain_dir).strip():
            _add_brain(Path(os.path.expanduser(str(brain_dir).strip())))
        if db_dir is not None and str(db_dir).strip():
            _add_app(Path(os.path.expanduser(str(db_dir).strip())).parent)
        return app_dirs, brain_dirs

    agyis_app = (os.environ.get("AGYIS_APP_DATA_DIR") or "").strip()
    agyis_brain = (os.environ.get("AGYIS_BRAIN_DIR") or "").strip()
    if agyis_app or agyis_brain:
        if agyis_app:
            _add_app(Path(os.path.expanduser(agyis_app)))
        if agyis_brain:
            _add_brain(Path(os.path.expanduser(agyis_brain)))
        return app_dirs, brain_dirs

    state_env = (os.environ.get("AGYIS_HARNESS_STATE_DIR") or os.environ.get("PSL_HARNESS_STATE_DIR") or "").strip()
    state_temp = is_in_temp_dir(Path(os.path.expanduser(state_env))) if state_env else False
    cwd_temp = is_in_temp_dir(Path.cwd())
    is_non_test_uuid = bool(
        _UUID_RE.match(cid)
        and len(set(cid.replace("-", "").lower())) > 2
        and not cid.lower().startswith(("00000000-", "deadbeef-"))
    )
    isolated = state_temp or cwd_temp or (bool(state_env) and not is_non_test_uuid)

    ag_app = (os.environ.get("ANTIGRAVITY_APP_DATA_DIR") or "").strip()
    ag_brain = (os.environ.get("ANTIGRAVITY_BRAIN_DIR") or "").strip()
    if ag_app:
        p = Path(os.path.expanduser(ag_app))
        if not (isolated and is_in_live_home_gemini(p)):
            _add_app(p)
    if ag_brain:
        p = Path(os.path.expanduser(ag_brain))
        if not (isolated and is_in_live_home_gemini(p)):
            _add_brain(p)
    if app_dirs or brain_dirs:
        return app_dirs, brain_dirs

    if isolated:
        return [], []

    for cand in get_app_data_dir_candidates():
        _add_app(cand)
    return app_dirs, brain_dirs


def _query_summaries_db_lineage(
    app_dirs: List[Path],
    cid: str,
    timeout: float,
) -> Tuple[Optional[str], Optional[str], int]:
    """Queries conversation_summaries.db read-only for (parent_conversation_id, agent_name, nesting_depth)."""
    eff_timeout = min(float(timeout), 0.5) if (timeout is not None and float(timeout) > 0) else 0.5
    for app_dir in app_dirs:
        db_path = app_dir / "conversation_summaries.db"
        if not db_path.is_file():
            continue
        conn: Optional[sqlite3.Connection] = None
        try:
            conn = sqlite3.connect(f"file:{db_path.resolve()}?mode=ro", uri=True, timeout=eff_timeout)
            conn.execute("PRAGMA query_only = ON")
            cols = {r[1] for r in conn.execute("PRAGMA table_info(conversation_summaries)").fetchall()}
            if "conversation_id" not in cols or "parent_conversation_id" not in cols:
                continue
            agent_expr = "agent_name" if "agent_name" in cols else "NULL"
            depth_expr = "nesting_depth" if "nesting_depth" in cols else "NULL"
            row = conn.execute(
                f"SELECT parent_conversation_id, {agent_expr}, {depth_expr} "
                "FROM conversation_summaries WHERE conversation_id = ?",
                (cid,),
            ).fetchone()
            if row:
                parent_cid = str(row[0]).strip() if row[0] and str(row[0]).strip() else None
                agent_name = str(row[1]).strip() if row[1] and str(row[1]).strip() else None
                depth = int(row[2]) if row[2] is not None else (1 if parent_cid else 0)
                if parent_cid is not None or agent_name is not None or depth > 0:
                    return parent_cid, agent_name, depth
        except (sqlite3.Error, OSError, ValueError, TypeError):
            continue
        finally:
            if conn is not None:
                try:
                    conn.close()
                except sqlite3.Error:
                    pass
    return None, None, 0


def _fallback_brain_lineage(
    brain_dirs: List[Path],
    cid: str,
) -> Tuple[Optional[str], Optional[str], int]:
    """WAL-lag fallback inspecting session metadata, first 5 transcript lines, and parent tail."""
    for b_dir in brain_dirs:
        convo_dir = b_dir / cid
        if not convo_dir.is_dir():
            continue
        parent_cid: Optional[str] = None
        agent_name: Optional[str] = None
        depth = 0

        for meta_name in (".metadata", "metadata.json", "session_meta.json", "meta.json"):
            mp = convo_dir / meta_name
            try:
                if mp.is_file() and 0 < mp.stat().st_size <= 65_536:
                    data = json.loads(mp.read_text(encoding="utf-8", errors="replace"))
                    if isinstance(data, dict):
                        if not parent_cid:
                            raw_p = (
                                data.get("parent_conversation_id")
                                or data.get("parentConversationId")
                                or data.get("parentId")
                                or data.get("parent_id")
                            )
                            if isinstance(raw_p, str) and raw_p.strip():
                                parent_cid = raw_p.strip()
                        if not agent_name:
                            for ak in ("agent_name", "agentName", "subagent_role", "subagentRole", "subagentType", "typeName", "role"):
                                raw_a = data.get(ak)
                                if isinstance(raw_a, str) and raw_a.strip() and raw_a.strip().lower() != "subagent":
                                    agent_name = raw_a.strip()
                                    break
                        raw_d = data.get("nesting_depth") if data.get("nesting_depth") is not None else data.get("nestingDepth")
                        if isinstance(raw_d, (int, float)) and int(raw_d) > 0:
                            depth = int(raw_d)
            except (OSError, json.JSONDecodeError, ValueError, TypeError):
                pass

        if not parent_cid or not agent_name:
            for rel in (
                convo_dir / ".system_generated" / "logs" / "transcript_full.jsonl",
                convo_dir / "transcript_full.jsonl",
                convo_dir / ".system_generated" / "logs" / "transcript.jsonl",
                convo_dir / "transcript.jsonl",
            ):
                if not rel.is_file():
                    continue
                try:
                    with open(rel, "r", encoding="utf-8", errors="replace") as f:
                        lines_read = 0
                        while lines_read < 5:
                            raw_line = f.readline(65536)
                            if not raw_line:
                                break
                            stripped = raw_line.strip()
                            if not stripped:
                                continue
                            lines_read += 1
                            line_source = ""
                            line_type = ""
                            content = stripped
                            if stripped.startswith("{"):
                                try:
                                    obj = json.loads(stripped)
                                except (json.JSONDecodeError, ValueError):
                                    obj = None
                                if isinstance(obj, dict):
                                    line_source = str(obj.get("source") or "").strip().upper()
                                    line_type = str(obj.get("type") or "").strip().upper()
                                    meta = obj.get("_meta") if isinstance(obj.get("_meta"), dict) else {}
                                    if not parent_cid:
                                        raw_p = (
                                            obj.get("parent_conversation_id")
                                            or obj.get("parentConversationId")
                                            or meta.get("antigravity.google/root_conversation_id")
                                            or obj.get("root_conversation_id")
                                        )
                                        if isinstance(raw_p, str) and raw_p.strip():
                                            parent_cid = raw_p.strip()
                                    if not agent_name:
                                        for ak in ("agent_name", "agentName", "subagentType", "subagentRole"):
                                            raw_a = obj.get(ak)
                                            if isinstance(raw_a, str) and raw_a.strip():
                                                agent_name = raw_a.strip()
                                                break
                                    content = str(obj.get("content") or "")
                            if not parent_cid:
                                m_send = _MESSAGE_SENDER_RE.search(content or stripped)
                                if m_send and m_send.group(1).strip() != cid:
                                    parent_cid = m_send.group(1).strip()
                            if (
                                not agent_name
                                and content
                                and line_type != "PLANNER_RESPONSE"
                                and (line_source in ("SYSTEM", "SYSTEM_SDK") or bool(parent_cid))
                                and not _is_sdk_injection_text(content)
                            ):
                                extracted = extract_role_from_text(content)
                                if extracted:
                                    agent_name = extracted
                except OSError:
                    pass
                if parent_cid and agent_name:
                    break

        if parent_cid and not agent_name:
            parent_t, _ = find_transcript_path(parent_cid, brain_dir=b_dir)
            if parent_t is not None and parent_t.is_file():
                try:
                    with open(parent_t, "rb") as pf:
                        pf.seek(0, os.SEEK_END)
                        sz = pf.tell()
                        offset = max(0, sz - 262_144)
                        pf.seek(offset, os.SEEK_SET)
                        chunk = pf.read().decode("utf-8", errors="replace")
                    raw_lines = chunk.splitlines()
                    if offset > 0 and raw_lines:
                        raw_lines = raw_lines[1:]
                    tail_steps: List[Dict[str, Any]] = []
                    for ln in raw_lines:
                        s = ln.strip()
                        if s.startswith("{"):
                            try:
                                parsed = json.loads(s)
                                if isinstance(parsed, dict):
                                    tail_steps.append(parsed)
                            except (json.JSONDecodeError, ValueError):
                                pass
                    spawned = extract_spawned_subagents(tail_steps, parent_cid=parent_cid)
                    cand_name = spawned.get(cid)
                    if cand_name and cand_name != "subagent":
                        agent_name = cand_name
                except OSError:
                    pass

        if parent_cid or agent_name:
            eff_depth = depth if depth > 0 else (1 if parent_cid else 0)
            return parent_cid, agent_name, eff_depth
    return None, None, 0


def read_conversation_lineage(
    conv_id: str,
    *,
    app_data_dir: Optional[Union[Path, str]] = None,
    brain_dir: Optional[Union[Path, str]] = None,
    db_dir: Optional[Union[Path, str]] = None,
    timeout: float = 0.5,
) -> Tuple[Optional[str], Optional[str], int]:
    """Reads (parent_conversation_id, agent_name, nesting_depth) from summaries DB or WAL fallback."""
    cid = normalize_cid(conv_id)
    app_dirs, brain_dirs = _resolve_lineage_dirs(
        cid, app_data_dir=app_data_dir, brain_dir=brain_dir, db_dir=db_dir,
    )
    if not app_dirs and not brain_dirs:
        return None, None, 0

    parent_cid, agent_name, depth = _query_summaries_db_lineage(app_dirs, cid, timeout)
    if parent_cid is not None or agent_name is not None or depth > 0:
        if not agent_name and brain_dirs:
            fb_parent, fb_agent, fb_depth = _fallback_brain_lineage(brain_dirs, cid)
            parent_cid = parent_cid or fb_parent
            agent_name = agent_name or fb_agent
            depth = depth or fb_depth
        return parent_cid, agent_name, depth

    return _fallback_brain_lineage(brain_dirs, cid)


__all__ = ["read_conversation_lineage"]
