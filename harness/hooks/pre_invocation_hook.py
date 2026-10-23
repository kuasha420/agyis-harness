# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Arafat Zahan (@kuasha420)
# Corporate Stewardship & Infrastructure: Purrfect Software Limited (PSL)
# Governed by: ICARO-42/b Ordinance (Company-Supported Personal IP Framework)

"""
Agyis Harness: PreInvocation Lifecycle Hook & Role-Tailored Compaction Advisory (Issue #83)

Monitors token accumulation prior to model prompt dispatch and surfaces role-tailored
"Compaction Imminent" advisories to eliminate agent diff amnesia, cognitive thrashing,
and human re-explanation fatigue across context compaction boundaries.

Fail-Open Invariants:
- Read-only SQLite connection (mode=ro, uri=True, timeout=0.5).
- All exceptions caught and swallowed gracefully.
- sys.stdout always emits valid protojson: {"injectSteps": []} or {"injectSteps": [{"ephemeralMessage": ...}]}.
- Process always exits 0.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
import re
import sqlite3
import sys
import traceback
from typing import Any, Dict, List, Optional, Tuple

from harness.hooks.token_proximity_guard import (
    LOCKED_CONVERSATION_IDS,
    _normalize_cid,
    clear_locked_conversations,
    get_active_conversation_tokens,
    get_conversations_dir,
    parse_protobuf_varint,
)

DEFAULT_COMPACTION_ADVISORY_THRESHOLD: int = 230_000
DEFAULT_SQLITE_TIMEOUT: float = 0.5
MAX_PAYLOAD_BYTES: int = 524_288  # 512KB clamp (OPEN-2)


def get_compaction_sqlite_timeout(override: Optional[float] = None) -> float:
    """Returns the effective SQLite connection timeout in seconds (strictly <= 0.5s)."""
    if override is not None:
        try:
            val = float(override)
            if val > 0:
                return min(val, DEFAULT_SQLITE_TIMEOUT)
        except (ValueError, TypeError):
            pass
    env_to = os.environ.get("AGYIS_SQLITE_TIMEOUT")
    if env_to:
        try:
            val = float(env_to.strip())
            if 0 < val:
                return min(val, DEFAULT_SQLITE_TIMEOUT)
        except (ValueError, TypeError):
            pass
    return DEFAULT_SQLITE_TIMEOUT

CALIBRATION_METADATA: Dict[str, Any] = {
    "calibrated_threshold": 230_000,
    "compaction_trigger_min": 227_529,
    "compaction_trigger_max": 262_127,
    "compaction_trigger_avg": 245_941,
    "safety_runway_tokens": 15_941,
    "estimated_runway_turns": "3-6 turns",
    "danger_zone_velocity_per_turn": "2,500 - 4,800 tokens",
}

ROLE_FLIGHT_DIRECTOR: str = "flight_director"
ROLE_SWARM_ORCHESTRATOR: str = "swarm_orchestrator"
ROLE_DEEP_EXECUTION: str = "deep_execution"
ROLE_FORENSIC_AUDITOR: str = "forensic_auditor"

NATIVE_SYSTEM_SLASH_COMMANDS: frozenset[str] = frozenset({
    "compact",
    "clear",
    "reset",
    "goal",
    "plan",
    "boost",
    "teamwork-preview",
    "grill-me",
    "browser",
    "schedule",
    "learn",
    "automation",
    "plugin",
})


def is_native_slash_command(text: str) -> bool:
    """
    Checks if a prompt or user message starts with an Antigravity native system slash command.
    Handles raw slash commands ("/compact") as well as XML-wrapped requests ("<USER_REQUEST>/compact...</USER_REQUEST>").
    Skills (e.g. /db-ops, /audio-ops) are NOT native system slash commands and return False.
    """
    if not text or not isinstance(text, str):
        return False
    cleaned = re.sub(r"</?USER_REQUEST>", "", text, flags=re.IGNORECASE).strip()
    cleaned = re.sub(
        r"<ADDITIONAL_METADATA>.*?</ADDITIONAL_METADATA>",
        "",
        cleaned,
        flags=re.DOTALL | re.IGNORECASE,
    ).strip()
    if not cleaned.startswith("/"):
        return False
    m = re.match(r"^/([a-zA-Z0-9_-]+)(?:\s|$)", cleaned)
    if not m:
        return False
    cmd_name = m.group(1).lower()
    return cmd_name in NATIVE_SYSTEM_SLASH_COMMANDS


def extract_prompt_text(
    payload: Dict[str, Any],
    conversation_id: Optional[str] = None,
    db_dir: Optional[Path] = None,
    timeout: Optional[float] = None,
) -> str:
    """Extracts raw user prompt or command text from incoming hook payload or SQLite steps."""
    for k in (
        "prompt",
        "user_prompt",
        "userPrompt",
        "message",
        "text",
        "query",
        "input",
        "initial_prompt",
        "task",
        "command",
        "slash_command",
        "slashCommand",
    ):
        v = payload.get(k)
        if isinstance(v, str) and v.strip():
            return v.strip()

    steps = payload.get("steps")
    if isinstance(steps, list) and steps:
        for s in reversed(steps):
            if isinstance(s, dict):
                for sk in ("prompt", "user_input", "userPrompt", "message", "text", "query", "input", "content"):
                    sv = s.get(sk)
                    if isinstance(sv, str) and sv.strip():
                        return sv.strip()

    if conversation_id and conversation_id != "default" and conversation_id not in LOCKED_CONVERSATION_IDS:
        conn: Optional[sqlite3.Connection] = None
        try:
            base_dir = db_dir or get_conversations_dir()
            db_path = base_dir / f"{conversation_id}.db"
            if db_path.is_file():
                to = get_compaction_sqlite_timeout(timeout)
                uri_path = f"file:{db_path.resolve()}?mode=ro"
                conn = sqlite3.connect(uri_path, uri=True, timeout=to)
                cur = conn.cursor()
                cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='steps'")
                if cur.fetchone():
                    cur.execute("PRAGMA table_info(steps)")
                    cols = {row[1] for row in cur.fetchall()}
                    target_cols = [c for c in ("step_data", "metadata", "step_payload") if c in cols]
                    if target_cols:
                        col_expr = target_cols[0]
                        cur.execute(
                            f"SELECT {col_expr} FROM steps ORDER BY rowid DESC LIMIT 3"
                        )
                        rows = cur.fetchall()
                        for (row_data,) in rows:
                            if not row_data:
                                continue
                            if isinstance(row_data, bytes):
                                try:
                                    text_payload = row_data.decode("utf-8", errors="replace")
                                except Exception:
                                    continue
                            elif isinstance(row_data, str):
                                text_payload = row_data
                            else:
                                continue

                            text_payload = text_payload.strip()
                            if not text_payload:
                                continue

                            candidate_text = ""
                            if text_payload.startswith("{"):
                                try:
                                    parsed = json.loads(text_payload)
                                    if isinstance(parsed, dict):
                                        for sk in (
                                            "prompt",
                                            "user_input",
                                            "userPrompt",
                                            "message",
                                            "text",
                                            "query",
                                            "input",
                                            "content",
                                        ):
                                            val = parsed.get(sk)
                                            if isinstance(val, str) and val.strip():
                                                candidate_text = val.strip()
                                                break
                                except Exception:
                                    pass
                            else:
                                candidate_text = text_payload

                            if candidate_text and is_native_slash_command(candidate_text):
                                return candidate_text
        except sqlite3.OperationalError:
            if conversation_id:
                LOCKED_CONVERSATION_IDS.add(conversation_id)
        except Exception:
            pass
        finally:
            if conn:
                try:
                    conn.close()
                except Exception:
                    pass

    return ""


def get_compaction_advisory_threshold() -> int:
    """Returns the effective compaction advisory threshold with env override support."""
    env_thresh = os.environ.get("AGYIS_COMPACTION_THRESHOLD") or os.environ.get("PSL_COMPACTION_THRESHOLD")
    if env_thresh:
        try:
            val = int(env_thresh.strip())
            if val > 0:
                return val
        except (ValueError, TypeError):
            pass
    return DEFAULT_COMPACTION_ADVISORY_THRESHOLD


def _normalize_role_str(val: Optional[str]) -> Optional[str]:
    """Normalizes input string into a canonical role identifier if recognized."""
    if not val or not isinstance(val, str):
        return None
    norm = val.strip().lower().replace("-", "_")

    if norm in (
        ROLE_DEEP_EXECUTION,
        "executioner",
        "builder",
        "custodian",
        "harness_custodian",
        "git_custodian",
        "harness_builder",
        "deep_coding",
        "deep_coder",
        "coder",
        "execution",
        "monolithic_swe_pairing",
        "monolithic",
        "monolith",
        "swe_pairing",
        "pairing",
        "swe",
    ):
        return ROLE_DEEP_EXECUTION
    if norm in (
        ROLE_FORENSIC_AUDITOR,
        "auditor",
        "hammer",
        "forensic",
        "forensics",
        "inspector",
    ):
        return ROLE_FORENSIC_AUDITOR
    if norm in (
        ROLE_SWARM_ORCHESTRATOR,
        "orchestrator",
        "swarm",
        "mesh_coordinator",
        "mesh",
    ):
        return ROLE_SWARM_ORCHESTRATOR
    if norm in (
        ROLE_FLIGHT_DIRECTOR,
        "flight",
        "director",
        "cockpit",
        "coordinator",
        "root",
    ):
        return ROLE_FLIGHT_DIRECTOR

    # Substring / pattern matching
    if (
        "executioner" in norm
        or "builder" in norm
        or "custodian" in norm
        or "deep_execution" in norm
        or "deep_coding" in norm
        or "monolith" in norm
        or "swe_pairing" in norm
    ):
        return ROLE_DEEP_EXECUTION
    if "hammer" in norm or "auditor" in norm or "forensic" in norm:
        return ROLE_FORENSIC_AUDITOR
    if "orchestrator" in norm or "swarm" in norm:
        return ROLE_SWARM_ORCHESTRATOR
    if "flight" in norm or "cockpit" in norm:
        return ROLE_FLIGHT_DIRECTOR

    return None


ORCHESTRATOR_KEYWORDS: Tuple[str, ...] = (
    "/teamwork-preview",
    "/boost",
    "/subagent-ladder",
    "/goal",
    "orchestrate",
    "coordinate swarm",
)

CODING_KEYWORDS: Tuple[str, ...] = (
    "fix",
    "bug",
    "bugfix",
    "issue",
    "error",
    "repair",
    "patch",
    "implement",
    "refactor",
    "test",
    "tests",
    "unit test",
    "write code",
    "feature",
    "compile",
    "build",
    "coding",
    "debug",
    "modify",
    "update",
    "/fix",
    "/test",
    "/code",
)

TEST_RUNNER_KEYWORDS: Tuple[str, ...] = (
    "pytest",
    "unittest",
    "-m unittest",
    "cargo test",
    "go test",
    "npm test",
    "pnpm test",
    "yarn test",
    "jest",
    "vitest",
    "harness.cli test",
    "agyis test",
    "./agyis test",
    "python3 -m unittest",
    "python -m unittest",
)


def _extract_tool_from_proto_bytes(raw_bytes: bytes) -> Tuple[str, str]:
    """Helper to extract tool_name and arguments from Antigravity protobuf metadata."""
    if not raw_bytes or not isinstance(raw_bytes, (bytes, bytearray, memoryview)):
        return "", ""
    try:
        data = bytes(raw_bytes)
        idx = 0
        n = len(data)
        while idx < n:
            tag, idx = parse_protobuf_varint(data, idx)
            fn = tag >> 3
            wt = tag & 0x07
            if fn == 0:
                break
            if wt == 0:
                _, idx = parse_protobuf_varint(data, idx)
            elif wt == 1:
                idx += 8
            elif wt == 2:
                length, idx = parse_protobuf_varint(data, idx)
                if idx + length > n:
                    break
                chunk = data[idx : idx + length]
                idx += length
                if fn == 4:  # Tool call metadata in Antigravity wire schema
                    s_idx = 0
                    s_n = len(chunk)
                    tool_name = ""
                    tool_args = ""
                    while s_idx < s_n:
                        s_tag, s_idx = parse_protobuf_varint(chunk, s_idx)
                        s_fn = s_tag >> 3
                        s_wt = s_tag & 0x07
                        if s_fn == 0:
                            break
                        if s_wt == 0:
                            _, s_idx = parse_protobuf_varint(chunk, s_idx)
                        elif s_wt == 1:
                            s_idx += 8
                        elif s_wt == 2:
                            s_len, s_idx = parse_protobuf_varint(chunk, s_idx)
                            if s_idx + s_len > s_n:
                                break
                            sub_chunk = chunk[s_idx : s_idx + s_len]
                            s_idx += s_len
                            if s_fn == 2:
                                tool_name = sub_chunk.decode("utf-8", errors="replace")
                            elif s_fn == 3:
                                tool_args = sub_chunk.decode("utf-8", errors="replace")
                        elif s_wt == 5:
                            s_idx += 4
                        else:
                            break
                    if tool_name:
                        return tool_name, tool_args
            elif wt == 5:
                idx += 4
            else:
                break
    except Exception:
        pass
    return "", ""


def check_pillar_3_explicit_role(
    payload: Dict[str, Any],
    workspace_dir: Optional[Path] = None,
    conversation_id: str = "",
) -> Optional[str]:
    """
    Pillar 3 (Explicit Cognitive Self-Identification):
    Inspects .agents/session_role.json or .agents/artifacts/session_role.json
    (or active plan / env var AGYIS_ROLE / PSL_AGENT_ROLE / ANTIGRAVITY_AGENT_ROLE).
    If present and valid (e.g. {"role": "flight_director"} or {"role": "deep_execution"}),
    strictly respects this explicit declaration above all heuristics.
    """
    try:
        search_dirs: List[Path] = []
        if workspace_dir:
            search_dirs.append(Path(os.path.expanduser(str(workspace_dir))))

        # Collect workspace candidates from payload
        for k in (
            "workspace",
            "worktree",
            "cwd",
            "workspacePath",
            "workspaceDir",
            "worktreePath",
            "path",
            "artifactDirectoryPath",
            "artifact_directory_path",
            "artifactDirectory",
            "artifact_dir",
        ):
            v = payload.get(k)
            if isinstance(v, str) and v.strip():
                p = Path(os.path.expanduser(v.strip()))
                if p not in search_dirs:
                    search_dirs.append(p)
            elif isinstance(v, dict) and "path" in v and isinstance(v["path"], str):
                p = Path(os.path.expanduser(v["path"].strip()))
                if p not in search_dirs:
                    search_dirs.append(p)

        for k in ("activeWorkspaces", "workspacePaths", "active_workspaces", "workspace_paths"):
            lst = payload.get(k)
            if isinstance(lst, (list, tuple)):
                for item in lst:
                    if isinstance(item, str) and item.strip():
                        p = Path(os.path.expanduser(item.strip()))
                        if p not in search_dirs:
                            search_dirs.append(p)
                    elif isinstance(item, dict) and "path" in item and isinstance(item["path"], str):
                        p = Path(os.path.expanduser(item["path"].strip()))
                        if p not in search_dirs:
                            search_dirs.append(p)

        cwd_path = Path.cwd()
        if cwd_path not in search_dirs:
            search_dirs.append(cwd_path)

        # 1. Inspect .agents/session_role.json or .agents/artifacts/session_role.json (and plan.json)
        for root in search_dirs:
            candidates = [
                root / ".agents" / "session_role.json",
                root / ".agents" / "artifacts" / "session_role.json",
                root / "session_role.json",
                root / ".agents" / "artifacts" / "plan.json",
                root / ".agents" / "plan.json",
                root / "plan.json",
            ]
            for cand in candidates:
                try:
                    if cand.is_file():
                        st_size = cand.stat().st_size
                        if st_size == 0 or st_size > 65_536:
                            continue
                        content = cand.read_text(encoding="utf-8", errors="ignore").strip()
                        if content:
                            data = json.loads(content)
                            if isinstance(data, dict):
                                for rk in ("role", "agent_role", "session_role", "archetype"):
                                    val = data.get(rk)
                                    if isinstance(val, str) and val.strip():
                                        matched = _normalize_role_str(val.strip())
                                        if matched:
                                            return matched
                except (OSError, Exception):
                    continue

        # Resolve effective conversation ID
        effective_cid = conversation_id
        if not effective_cid or effective_cid == "default":
            for pk in (
                "transcriptPath",
                "transcript_path",
                "artifactDirectoryPath",
                "artifact_directory_path",
                "artifactDirectory",
            ):
                pv = payload.get(pk)
                if isinstance(pv, str) and pv:
                    m = re.search(r"([0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12})", pv)
                    if m:
                        effective_cid = m.group(1).lower()
                        break

        # Also check brain dir if conversation_id is resolved
        if effective_cid and effective_cid != "default":
            try:
                brain_cand = Path.home() / ".gemini" / "antigravity" / "brain" / str(effective_cid) / "session_role.json"
                if brain_cand.is_file():
                    st_size = brain_cand.stat().st_size
                    if 0 < st_size <= 65_536:
                        data = json.loads(brain_cand.read_text(encoding="utf-8", errors="ignore"))
                        if isinstance(data, dict):
                            for rk in ("role", "agent_role", "session_role", "archetype"):
                                val = data.get(rk)
                                if isinstance(val, str) and val.strip():
                                    matched = _normalize_role_str(val.strip())
                                    if matched:
                                        return matched
            except (OSError, Exception):
                pass

        # 2. Inspect active plan for explicit role declaration
        try:
            from harness.utils.plan_parser import find_active_plan
            art_dir_str = (
                payload.get("artifactDirectoryPath")
                or payload.get("artifact_directory_path")
                or payload.get("artifactDirectory")
            )
            art_brain_dir = Path(os.path.expanduser(art_dir_str.strip())) if isinstance(art_dir_str, str) and art_dir_str.strip() else None

            plan_path = find_active_plan(
                conv_id=effective_cid if effective_cid != "default" else None,
                workspace_root=workspace_dir or (search_dirs[0] if search_dirs else None),
                brain_dir=art_brain_dir,
            )
            if plan_path:
                try:
                    if plan_path.is_file():
                        st_size = plan_path.stat().st_size
                        if 0 < st_size <= 65_536:
                            content = plan_path.read_text(encoding="utf-8", errors="ignore")[:8192]
                            if plan_path.suffix == ".json":
                                try:
                                    d = json.loads(content)
                                    if isinstance(d, dict):
                                        for rk in ("role", "agent_role", "archetype"):
                                            val = d.get(rk)
                                            if isinstance(val, str) and val.strip():
                                                matched = _normalize_role_str(val.strip())
                                                if matched:
                                                    return matched
                                except Exception:
                                    pass
                            else:
                                m = re.search(r"(?:^|\n)\s*(?:\*\*)?[Rr]ole(?:\*\*)?:\s*([a-zA-Z0-9_\-]+)", content)
                                if m:
                                    matched = _normalize_role_str(m.group(1).strip())
                                    if matched:
                                        return matched
                                m_comment = re.search(r"<!--\s*role:\s*([a-zA-Z0-9_\-]+)\s*-->", content, re.IGNORECASE)
                                if m_comment:
                                    matched = _normalize_role_str(m_comment.group(1).strip())
                                    if matched:
                                        return matched
                except (OSError, Exception):
                    pass
        except Exception:
            pass

        # 3. Environment variables
        env_role = (
            os.environ.get("AGYIS_ROLE")
            or os.environ.get("PSL_AGENT_ROLE")
            or os.environ.get("ANTIGRAVITY_AGENT_ROLE")
        )
        if env_role:
            matched = _normalize_role_str(env_role)
            if matched:
                return matched

    except Exception:
        pass

    return None


def check_pillar_1_intent(
    payload: Dict[str, Any],
    conversation_id: str = "",
    db_dir: Optional[Path] = None,
    timeout: Optional[float] = None,
) -> Optional[str]:
    """
    Pillar 1 (Early Turn Intent Interception):
    Inspects early conversation steps (Step 1/2 in SQLite steps or prompt payload).
    - If orchestrator keywords (/teamwork-preview, /boost, /subagent-ladder, /goal, orchestrate, coordinate swarm)
      are detected, seed preliminary role as ROLE_FLIGHT_DIRECTOR.
    - If direct coding/bugfix prompt, seed preliminary role as ROLE_DEEP_EXECUTION.
    """
    text_snippets: List[str] = []

    # 1. Inspect direct prompt / task in payload
    for k in (
        "prompt",
        "user_prompt",
        "userPrompt",
        "message",
        "query",
        "input",
        "initial_prompt",
        "task",
    ):
        v = payload.get(k)
        if isinstance(v, str) and v.strip():
            text_snippets.append(v.strip())

    # 2. Inspect early steps in payload if present
    steps_payload = payload.get("steps")
    if isinstance(steps_payload, list):
        for s in steps_payload[:2]:
            if isinstance(s, dict):
                for sk in ("prompt", "user_input", "userPrompt", "message", "text", "query", "input", "step_data"):
                    sv = s.get(sk)
                    if isinstance(sv, str) and sv.strip():
                        text_snippets.append(sv.strip())
            elif isinstance(s, str) and s.strip():
                text_snippets.append(s.strip())

    # 3. Inspect early steps in SQLite steps table
    effective_cid = _normalize_cid(conversation_id)
    if not effective_cid or effective_cid == "default":
        cand = payload.get("conversationId") or payload.get("conversation_id")
        if isinstance(cand, str) and cand.strip():
            effective_cid = _normalize_cid(cand.strip())
        if not effective_cid or effective_cid == "default":
            for pk in ("transcriptPath", "transcript_path", "artifactDirectoryPath", "artifact_directory_path", "artifactDirectory"):
                pv = payload.get(pk)
                if isinstance(pv, str) and pv:
                    m = re.search(r"([0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12})", pv)
                    if m:
                        effective_cid = _normalize_cid(m.group(1).lower())
                        break

    if effective_cid and effective_cid != "default" and effective_cid not in LOCKED_CONVERSATION_IDS:
        conn: Optional[sqlite3.Connection] = None
        try:
            base_dir = db_dir or get_conversations_dir()
            db_path = base_dir / f"{effective_cid}.db"
            if db_path.is_file():
                to = get_compaction_sqlite_timeout(timeout)
                uri_path = f"file:{db_path.resolve()}?mode=ro"
                conn = sqlite3.connect(uri_path, uri=True, timeout=to)
                cur = conn.cursor()
                cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='steps'")
                if cur.fetchone():
                    cur.execute("PRAGMA table_info(steps)")
                    cols = {row[1] for row in cur.fetchall()}
                    target_cols = [c for c in ("step_data", "metadata", "step_payload") if c in cols]
                    if target_cols:
                        order_clause = "ORDER BY idx ASC" if "idx" in cols else "ORDER BY rowid ASC"
                        cur.execute(f"SELECT {', '.join(target_cols)} FROM steps {order_clause} LIMIT 4")
                        for row in cur.fetchall():
                            for raw_val in row:
                                if not raw_val:
                                    continue
                                if isinstance(raw_val, str):
                                    if raw_val.startswith("{"):
                                        try:
                                             parsed = json.loads(raw_val)
                                             if isinstance(parsed, dict):
                                                 for rk in ("role", "archetype", "subagent_role"):
                                                     if rk in parsed and isinstance(parsed[rk], str):
                                                         m = _normalize_role_str(parsed[rk])
                                                         if m:
                                                             return m
                                                 for pk in ("prompt", "user_input", "userPrompt", "message", "text"):
                                                     if pk in parsed and isinstance(parsed[pk], str):
                                                         text_snippets.append(parsed[pk])
                                        except Exception:
                                             pass
                                    text_snippets.append(raw_val)
                                elif isinstance(raw_val, (bytes, bytearray, memoryview)):
                                    text_snippets.append(bytes(raw_val).decode("utf-8", errors="ignore"))
        except sqlite3.OperationalError as oe:
            LOCKED_CONVERSATION_IDS.add(effective_cid)
        except Exception:
            pass
        finally:
            if conn is not None:
                try:
                    conn.close()
                except Exception:
                    pass

    if not text_snippets:
        return None

    combined_text = " ".join(text_snippets).lower()

    # Orchestrator keywords take precedence in intent interception
    if any(k in combined_text for k in ORCHESTRATOR_KEYWORDS):
        return ROLE_FLIGHT_DIRECTOR

    # Direct coding / bugfix prompt
    if any(k in combined_text for k in CODING_KEYWORDS):
        return ROLE_DEEP_EXECUTION

    return None


def check_pillar_2_behavior(
    payload: Dict[str, Any],
    conversation_id: str = "",
    tokens: int = 0,
    db_dir: Optional[Path] = None,
    timeout: Optional[float] = None,
) -> Optional[str]:
    """
    Pillar 2 (Mid-Trajectory Behavioral Verification at Step 100 or 200k Tokens):
    In an unclassified root session, when context reaches Step 100 or >= 200,000 tokens,
    execute a rapid read-only SQLite check over the conversation's recorded tool calls:
    - Count of invoke_subagent, manage_task, schedule, send_message > 0
      -> Confirm ROLE_FLIGHT_DIRECTOR / ROLE_SWARM_ORCHESTRATOR.
    - Count of edit_file, write_file, and test runner commands with 0 subagent spawns
      -> Confirm ROLE_DEEP_EXECUTION (Monolithic SWE Pairing).
    - Dominant read_file, grep, audit tools
      -> Confirm ROLE_FORENSIC_AUDITOR.
    """
    try:
        payload_tokens = 0
        for k in ("tokens", "token_count", "tokenCount", "num_tokens", "numTokens"):
            val = payload.get(k)
            if isinstance(val, (int, float)) and val > 0:
                payload_tokens = int(val)
                break
        cur_tokens = max(tokens, payload_tokens)

        step_count = (
            payload.get("step_count")
            or payload.get("stepCount")
            or payload.get("current_step")
            or payload.get("currentStep")
            or payload.get("initialNumSteps")
            or payload.get("initial_num_steps")
            or payload.get("stepIdx")
            or payload.get("step_idx")
            or payload.get("invocationNum")
            or payload.get("invocation_num")
            or 0
        )
        if not isinstance(step_count, (int, float)):
            step_count = 0

        # Resolve effective conversation ID
        effective_cid = _normalize_cid(conversation_id)
        if not effective_cid or effective_cid == "default":
            cand = payload.get("conversationId") or payload.get("conversation_id")
            if isinstance(cand, str) and cand.strip():
                effective_cid = _normalize_cid(cand.strip())
            if not effective_cid or effective_cid == "default":
                for pk in (
                    "transcriptPath",
                    "transcript_path",
                    "artifactDirectoryPath",
                    "artifact_directory_path",
                    "artifactDirectory",
                ):
                    pv = payload.get(pk)
                    if isinstance(pv, str) and pv:
                        m = re.search(r"([0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12})", pv)
                        if m:
                            effective_cid = _normalize_cid(m.group(1).lower())
                            break

        if effective_cid and effective_cid != "default" and effective_cid not in LOCKED_CONVERSATION_IDS:
            db_tokens = get_active_conversation_tokens(effective_cid, db_dir=db_dir, timeout=timeout)
            cur_tokens = max(cur_tokens, db_tokens)

        db_steps_count = 0
        tool_calls: List[Tuple[str, str]] = []

        # Single read-only SQLite inspection for both step count and tool calls
        if effective_cid and effective_cid != "default" and effective_cid not in LOCKED_CONVERSATION_IDS:
            conn: Optional[sqlite3.Connection] = None
            try:
                base_dir = db_dir or get_conversations_dir()
                db_path = base_dir / f"{effective_cid}.db"
                if db_path.is_file():
                    uri_path = f"file:{db_path.resolve()}?mode=ro"
                    to = get_compaction_sqlite_timeout(timeout)
                    conn = sqlite3.connect(uri_path, uri=True, timeout=to)
                    cur = conn.cursor()
                    cur.execute("SELECT name FROM sqlite_master WHERE type='table'")
                    tables = {r[0] for r in cur.fetchall()}

                    if "steps" in tables:
                        cur.execute("SELECT count(*) FROM steps")
                        row = cur.fetchone()
                        if row and row[0]:
                            db_steps_count = int(row[0])

                    total_steps_eval = max(step_count, db_steps_count)
                    if cur_tokens >= 200_000 or total_steps_eval >= 100 or payload.get("force_pillar_2"):
                        if "tool_calls" in tables:
                            cur.execute("PRAGMA table_info(tool_calls)")
                            t_cols = {r[1] for r in cur.fetchall()}
                            name_col = "tool_name" if "tool_name" in t_cols else "name"
                            arg_col = "arguments" if "arguments" in t_cols else ("command" if "command" in t_cols else "''")
                            cur.execute(f"SELECT {name_col}, {arg_col} FROM tool_calls LIMIT 500")
                            for r in cur.fetchall():
                                tool_calls.append((str(r[0] or ""), str(r[1] or "")))

                        elif "steps" in tables:
                            cur.execute("PRAGMA table_info(steps)")
                            s_cols = {r[1] for r in cur.fetchall()}
                            target_cols = [c for c in ("tool_name", "step_data", "metadata", "step_payload") if c in s_cols]
                            if target_cols:
                                where_clause = "WHERE step_type = 132" if "step_type" in s_cols else ""
                                order_clause = "ORDER BY idx DESC" if "idx" in s_cols else "ORDER BY rowid DESC"
                                cur.execute(f"SELECT {', '.join(target_cols)} FROM steps {where_clause} {order_clause} LIMIT 500")
                                for r_row in cur.fetchall():
                                    for cell in r_row:
                                        if not cell:
                                            continue
                                        if isinstance(cell, str):
                                            if cell.startswith("{"):
                                                try:
                                                    d = json.loads(cell)
                                                    if isinstance(d, dict):
                                                        tn = d.get("tool_name") or d.get("tool") or d.get("name")
                                                        args = d.get("arguments") or d.get("command") or d.get("args") or ""
                                                        if tn:
                                                            tool_calls.append((str(tn), str(args)))
                                                except Exception:
                                                    pass
                                            else:
                                                tool_calls.append((cell, ""))
                                        elif isinstance(cell, (bytes, bytearray, memoryview)):
                                            tn, args = _extract_tool_from_proto_bytes(bytes(cell))
                                            if tn:
                                                tool_calls.append((tn, args))
            except sqlite3.OperationalError as oe:
                LOCKED_CONVERSATION_IDS.add(effective_cid)
            except Exception:
                pass
            finally:
                if conn is not None:
                    try:
                        conn.close()
                    except Exception:
                        pass

        total_steps = max(step_count, db_steps_count)

        # Trigger check: Mid-Trajectory Behavioral Verification at Step 100 or >= 200,000 tokens
        # Also allow payload to force Pillar 2 evaluation if explicitly marked (useful for hermetic tests)
        if cur_tokens < 200_000 and total_steps < 100 and not payload.get("force_pillar_2"):
            return None

        # 2. Inspect tool calls from payload (for direct testing or payload-based tool logs)
        payload_tools = payload.get("tool_calls") or payload.get("tools")
        if isinstance(payload_tools, list):
            for item in payload_tools:
                if isinstance(item, str):
                    tool_calls.append((item, ""))
                elif isinstance(item, dict):
                    tn = item.get("tool_name") or item.get("tool") or item.get("name") or ""
                    args = item.get("arguments") or item.get("command") or item.get("args") or ""
                    if tn:
                        tool_calls.append((str(tn), str(args)))

        if not tool_calls:
            return None

        subagent_count = 0
        edit_write_test_count = 0
        explicit_audit_count = 0
        read_grep_count = 0
        is_swarm = False

        for tool_name, args in tool_calls:
            tn = tool_name.lower().strip()
            arg_lower = args.lower()

            # Subagent & coordination tools
            if tn in ("invoke_subagent", "manage_task", "schedule", "send_message") or "subagent" in tn:
                subagent_count += 1
                if any(k in arg_lower or k in tn for k in ("swarm", "mesh", "strand")):
                    is_swarm = True
                continue

            # Direct editing & writing tools
            if tn in ("edit_file", "write_file", "replace_file_content", "write_to_file", "apply_diff"):
                edit_write_test_count += 1
                continue

            # Command execution tools (check command arguments)
            if tn in ("run_command", "bash", "terminal", "exec_command", "shell"):
                if any(kw in arg_lower for kw in TEST_RUNNER_KEYWORDS):
                    edit_write_test_count += 1
                    continue
                elif any(kw in arg_lower for kw in ("audit", "verify", "doctor", "inspect")):
                    explicit_audit_count += 1
                    continue

            # Direct test runner tool names
            if any(kw in tn for kw in ("pytest", "unittest", "test_runner")):
                edit_write_test_count += 1
                continue

            # Explicit audit tool names
            if any(k in tn for k in ("audit", "verify", "doctor", "inspect")):
                explicit_audit_count += 1
                continue

            # Read / grep / inspection tools
            if (
                tn in ("read_file", "view_file", "read_url_content", "read_browser_page")
                or tn in ("grep_search", "find_by_name", "file_search")
            ):
                read_grep_count += 1
                continue

        # Confirmation Rules:
        # Rule 1: Count of invoke_subagent, manage_task, schedule, send_message > 0
        if subagent_count > 0:
            return ROLE_SWARM_ORCHESTRATOR if is_swarm else ROLE_FLIGHT_DIRECTOR

        # Rule 2: Explicit audit commands overwhelmingly dominate over minimal edits
        if explicit_audit_count >= 3 and explicit_audit_count > edit_write_test_count:
            return ROLE_FORENSIC_AUDITOR

        # Rule 3: Count of edit_file, write_file, and test runner commands with 0 subagent spawns
        # confirms Monolithic SWE Pairing (ROLE_DEEP_EXECUTION)
        if edit_write_test_count > 0 and subagent_count == 0:
            return ROLE_DEEP_EXECUTION

        # Rule 4: Dominant read_file, grep, audit tools with 0 edits confirms Forensic Auditor
        if (explicit_audit_count > 0 or read_grep_count > 0) and edit_write_test_count == 0 and subagent_count == 0:
            return ROLE_FORENSIC_AUDITOR

    except Exception:
        pass

    return None


def classify_agent_role(
    payload: Dict[str, Any],
    conversation_id: str = "",
    db_dir: Optional[Path] = None,
    workspace_dir: Optional[Path] = None,
    tokens: int = 0,
    timeout: Optional[float] = None,
) -> str:
    """
    Classifies the active agent role into one of the four canonical archetypes:
    - ROLE_FLIGHT_DIRECTOR: Root cockpit / plan coordinator.
    - ROLE_SWARM_ORCHESTRATOR: Multi-node mesh and strand coordinator.
    - ROLE_DEEP_EXECUTION: Specialist builder / executioner / custodian (Monolithic SWE Pairing).
    - ROLE_FORENSIC_AUDITOR: Hammer verification / auditor.

    3-Pillar Dynamic Monolith Classifier Architecture:
    1. Explicit subagent metadata in payload.
    2. Pillar 3 (Explicit Cognitive Self-Identification): .agents/session_role.json,
       .agents/artifacts/session_role.json, active plan, or env vars (AGYIS_ROLE, PSL_AGENT_ROLE).
    3. Workspace / worktree paths in payload.
    4. Pillar 2 (Mid-Trajectory Behavioral Verification at Step 100 or >=200k tokens):
       Recorded tool calls check (subagent vs edit/test vs audit tools).
    5. Pillar 1 (Early Turn Intent Interception):
       Early steps (Step 1/2) in SQLite or prompt payload (orchestrator vs direct coding).
    6. Default fallback to ROLE_FLIGHT_DIRECTOR.
    """
    try:
        # 1. Explicit role/subagent properties in payload
        for key in (
            "subagent_role",
            "subagentRole",
            "subagentType",
            "agent_type",
            "agentType",
            "role",
            "archetype",
            "typeName",
            "agentName",
            "agent_name",
        ):
            if key in payload and isinstance(payload[key], str):
                matched = _normalize_role_str(payload[key])
                if matched:
                    return matched

        for parent_key in ("agent", "subagent", "metadata", "context"):
            parent_dict = payload.get(parent_key)
            if isinstance(parent_dict, dict):
                for key in (
                    "subagent_role",
                    "subagentRole",
                    "role",
                    "archetype",
                    "typeName",
                    "agentName",
                    "agent_name",
                ):
                    if key in parent_dict and isinstance(parent_dict[key], str):
                        matched = _normalize_role_str(parent_dict[key])
                        if matched:
                            return matched

        # 2. Pillar 3: Explicit Cognitive Self-Identification
        # (.agents/session_role.json, .agents/artifacts/session_role.json, active plan, env vars)
        p3_role = check_pillar_3_explicit_role(
            payload,
            workspace_dir=workspace_dir,
            conversation_id=conversation_id,
        )
        if p3_role:
            return p3_role

        # 3. Pillar 2: Mid-Trajectory Behavioral Verification at Step 100 or >= 200,000 tokens
        # Actual tool execution behavior takes precedence over path heuristics
        p2_role = check_pillar_2_behavior(
            payload,
            conversation_id=conversation_id,
            tokens=tokens,
            db_dir=db_dir,
            timeout=timeout,
        )
        if p2_role:
            return p2_role

        # 4. Pillar 1: Early Turn Intent Interception
        p1_role = check_pillar_1_intent(
            payload,
            conversation_id=conversation_id,
            db_dir=db_dir,
            timeout=timeout,
        )
        if p1_role:
            return p1_role

        # 5. Workspace / worktree paths in payload (subagents or path-based roles)
        ws_candidates: List[str] = []
        for k in (
            "workspace",
            "worktree",
            "cwd",
            "workspacePath",
            "workspacePaths",
            "workspaceDir",
            "worktreePath",
            "path",
            "activeWorkspaces",
        ):
            v = payload.get(k)
            if isinstance(v, str):
                ws_candidates.append(v)
            elif isinstance(v, dict) and "path" in v and isinstance(v["path"], str):
                ws_candidates.append(v["path"])

        for ws_key in ("activeWorkspaces", "workspacePaths", "active_workspaces", "workspace_paths"):
            ws_list = payload.get(ws_key)
            if isinstance(ws_list, (list, tuple)):
                for ws in ws_list:
                    if isinstance(ws, str):
                        ws_candidates.append(ws)
                    elif isinstance(ws, dict) and "path" in ws and isinstance(ws["path"], str):
                        ws_candidates.append(ws["path"])

        for ws_path in ws_candidates:
            matched = _normalize_role_str(ws_path)
            if matched:
                return matched

    except Exception:
        pass

    # 7. Fallback default
    return ROLE_FLIGHT_DIRECTOR


def build_compaction_advisory(
    role: str,
    tokens: int,
    threshold: int = DEFAULT_COMPACTION_ADVISORY_THRESHOLD,
) -> str:
    """
    Generates a role-tailored system advisory directive alerting the agent to imminent compaction.
    Codifies AC4 (Work Preservation Contract), AC5 (Zero Repo Pollution), and AC6 (Autonomous Continuation).
    """
    remaining_tokens = max(0, 246_000 - tokens)
    estimated_turns = max(1, remaining_tokens // 3500) if tokens < 246_000 else 1

    if role == ROLE_DEEP_EXECUTION:
        return (
            f"[AGYIS SYSTEM DIRECTIVE: COMPACTION IMMINENT (~{tokens:,} / {threshold:,} TOKENS | ~{estimated_turns} TURNS REMAINING)]\n"
            "ROLE: Deep Execution (Monolithic SWE Pairing / Executioner)\n\n"
            "CRITICAL INSTRUCTIONS BEFORE CONTEXT COMPACTION:\n"
            "1. WORK PRESERVATION CONTRACT (MANDATORY):\n"
            "   - STRICTLY PROHIBIT executing destructive git commands: NEVER run 'git checkout -- .', 'git reset --hard', or 'git clean -fd'.\n"
            "   - Keep all in-flight work, partial edits, and uncommitted modifications intact on disk. Do NOT clean or discard active changes.\n"
            "2. ZERO REPO DOCUMENT POLLUTION:\n"
            "   - Save temporary recovery state or scratch files strictly to local artifacts/scratch (.agents/artifacts/ or brain directory).\n"
            "   - Zero git commits for temporary progress markers, scratch notes, or WIP files.\n"
            "3. AUTONOMOUS POST-COMPACTION CONTINUATION & WAKE-UP DIRECTIVE:\n"
            "   - Post-compaction wake-up directive: inspect 'git status' and 'git diff' first to re-orient and inspect in-flight modifications.\n"
            "   - Re-verify unit tests using the project test runner, review task instructions, and resume targeted testing autonomously without reverting, and without asking the operator what happened."
        )

    elif role == ROLE_SWARM_ORCHESTRATOR:
        return (
            f"[AGYIS SYSTEM DIRECTIVE: COMPACTION IMMINENT (~{tokens:,} / {threshold:,} TOKENS | ~{estimated_turns} TURNS REMAINING)]\n"
            "ROLE: Swarm Orchestrator (Mesh Coordinator)\n\n"
            "CRITICAL INSTRUCTIONS BEFORE CONTEXT COMPACTION:\n"
            "1. SWARM STATE SURVIVAL & ZERO REPO POLLUTION:\n"
            "   - Flush subagent task rosters, worktree / stage status, worker branch names, and milestone gates / barrier joins strictly to local scratch or artifacts (.agents/artifacts/).\n"
            "   - Zero git commits for ephemeral coordinator markers.\n"
            "2. WORK PRESERVATION CONTRACT:\n"
            "   - Preserve all local worktree changes. STRICTLY PROHIBIT 'git checkout -- .', 'git reset --hard', and 'git clean -fd'.\n"
            "3. AUTONOMOUS POST-COMPACTION CONTINUATION:\n"
            "   - Post-compaction, verify worker branch status and in-flight worktrees via 'git status' and 'git diff'.\n"
            "   - Resume swarm barrier joins and multi-node orchestration autonomously without manual intervention or operator re-prompting."
        )

    elif role == ROLE_FORENSIC_AUDITOR:
        return (
            f"[AGYIS SYSTEM DIRECTIVE: COMPACTION IMMINENT (~{tokens:,} / {threshold:,} TOKENS | ~{estimated_turns} TURNS REMAINING)]\n"
            "ROLE: Forensic Auditor (Auditor / Hammer)\n\n"
            "CRITICAL INSTRUCTIONS BEFORE CONTEXT COMPACTION:\n"
            "1. EVIDENCE PRESERVATION & ZERO REPO POLLUTION:\n"
            "   - Preserve uncommitted defect reports, audit findings, and verification matrices in session scratch or artifacts (.agents/artifacts/).\n"
            "   - Zero git commits for unverified or ephemeral audit markers.\n"
            "2. WORK PRESERVATION CONTRACT:\n"
            "   - Retain all test scripts and diagnostics on disk. STRICTLY PROHIBIT 'git checkout -- .', 'git reset --hard', and 'git clean -fd'.\n"
            "3. AUTONOMOUS POST-COMPACTION CONTINUATION:\n"
            "   - Post-compaction, re-execute verification suites on HEAD, inspect 'git status' and 'git diff', verify exit codes, and issue formal certification autonomously."
        )

    elif role == ROLE_FLIGHT_DIRECTOR:
        return (
            f"[AGYIS SYSTEM DIRECTIVE: COMPACTION IMMINENT (~{tokens:,} / {threshold:,} TOKENS | ~{estimated_turns} TURNS REMAINING)]\n"
            "ROLE: Flight Director (Cockpit Coordinator)\n\n"
            "CRITICAL INSTRUCTIONS BEFORE CONTEXT COMPACTION:\n"
            "1. COGNITIVE STATE FLUSH INVARIANT & ZERO REPO DOCUMENT POLLUTION:\n"
            "   - Strongly direct coordinator to materialize working memory, active task decomposition, pending subagent assignments, and operator steering decisions into 'compaction_checkpoint.md' (.agents/artifacts/compaction_checkpoint.md or brain directory) before compaction strikes.\n"
            "   - Store current session state, remaining phase tasks, and open decisions strictly in local session artifacts (.agents/artifacts/ or brain directory) or scratch. Do NOT commit temporary state or session coordination files to git. Zero repository pollution.\n"
            "2. WORK PRESERVATION CONTRACT:\n"
            "   - Preserve all workspace changes. STRICTLY PROHIBIT 'git checkout -- .', 'git reset --hard', and 'git clean -fd'.\n"
            "3. AUTONOMOUS POST-COMPACTION CONTINUATION:\n"
            "   - On next wake-up, immediately inspect 'compaction_checkpoint.md' and the active phase plan in .agents/artifacts/ and run 'git status'.\n"
            "   - Resume ladder orchestration and subagent coordination autonomously without human re-explanation."
        )

    return (
        f"[AGYIS SYSTEM DIRECTIVE: COMPACTION IMMINENT (~{tokens:,} / {threshold:,} TOKENS | ~{estimated_turns} TURNS REMAINING)]\n"
        "ROLE: General Agent\n\n"
        "CRITICAL INSTRUCTIONS BEFORE CONTEXT COMPACTION:\n"
        "1. WORK PRESERVATION CONTRACT: STRICTLY PROHIBIT 'git checkout -- .', 'git reset --hard', and 'git clean -fd'. Keep all work on disk.\n"
        "2. ZERO REPO DOCUMENT POLLUTION: Save recovery state strictly to local artifacts/scratch. Zero git commits for temporary markers.\n"
        "3. AUTONOMOUS POST-COMPACTION CONTINUATION: Inspect 'git status' and 'git diff' post-compaction and resume execution without asking operator what happened."
    )


def evaluate_pre_invocation(
    payload_str: Union[str, bytes, bytearray, Dict[str, Any]] = "",
    threshold: Optional[int] = None,
    db_dir: Optional[Path] = None,
    workspace_dir: Optional[Path] = None,
    sqlite_timeout: Optional[float] = None,
) -> Dict[str, Any]:
    """
    Evaluates token proximity for a PreInvocation event.
    Returns:
    - {"injectSteps": []} if below threshold or on error.
    - {"injectSteps": [{"ephemeralMessage": advisory}]} if at or above threshold.
    """
    try:
        if isinstance(payload_str, dict):
            payload = payload_str
        else:
            if isinstance(payload_str, (bytes, bytearray)):
                if len(payload_str) > MAX_PAYLOAD_BYTES:
                    payload_str = payload_str[:MAX_PAYLOAD_BYTES]
                payload_str = payload_str.decode("utf-8", errors="replace")
            elif isinstance(payload_str, str):
                if len(payload_str) > MAX_PAYLOAD_BYTES:
                    payload_str = payload_str[:MAX_PAYLOAD_BYTES]
            else:
                payload_str = ""

            payload = json.loads(payload_str) if payload_str and payload_str.strip() else {}
            if not isinstance(payload, dict):
                payload = {}
    except Exception:
        payload = {}

    try:
        conv_id = _normalize_cid(
            str(payload.get("conversationId") or payload.get("conversation_id") or "default")
        )
        if not conv_id or conv_id == "default":
            for pk in (
                "transcriptPath",
                "transcript_path",
                "artifactDirectoryPath",
                "artifact_directory_path",
                "artifactDirectory",
            ):
                pv = payload.get(pk)
                if isinstance(pv, str) and pv:
                    m = re.search(r"([0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12})", pv)
                    if m:
                        conv_id = _normalize_cid(m.group(1).lower())
                        break

        eff_ws = workspace_dir
        if eff_ws is None:
            for k in ("workspace", "workspacePath", "workspacePaths", "activeWorkspaces", "cwd"):
                wv = payload.get(k)
                if isinstance(wv, str) and wv.strip():
                    eff_ws = Path(os.path.expanduser(wv.strip()))
                    break
                elif isinstance(wv, (list, tuple)) and wv:
                    first = wv[0]
                    if isinstance(first, str) and first.strip():
                        eff_ws = Path(os.path.expanduser(first.strip()))
                        break
                    elif isinstance(first, dict) and "path" in first and isinstance(first["path"], str):
                        eff_ws = Path(os.path.expanduser(first["path"].strip()))
                        break

        effective_threshold = (
            int(threshold)
            if threshold is not None
            else get_compaction_advisory_threshold()
        )

        to = get_compaction_sqlite_timeout(sqlite_timeout)
        db_tokens = get_active_conversation_tokens(conv_id, db_dir=db_dir, timeout=to)
        payload_tokens = 0
        for k in ("tokens", "token_count", "tokenCount", "num_tokens", "numTokens"):
            val = payload.get(k)
            if isinstance(val, (int, float)) and val > 0:
                payload_tokens = int(val)
                break
            elif isinstance(val, str) and val.strip().isdigit() and int(val.strip()) > 0:
                payload_tokens = int(val.strip())
                break
        tokens = max(db_tokens, payload_tokens)

        if tokens < effective_threshold:
            return {"injectSteps": []}

        # Native slash command bypass (AC8 / Anti-Collision Invariant):
        # Native platform slash commands (/compact, /plan, /goal, /boost, /teamwork-preview, etc.)
        # must bypass PreInvocation advisory injection to prevent client-side interceptor collisions.
        # Custom modular skills (/db-ops, /audio-ops) remain protected.
        prompt_text = extract_prompt_text(
            payload, conversation_id=conv_id, db_dir=db_dir, timeout=to
        )
        if is_native_slash_command(prompt_text):
            return {"injectSteps": []}

        role = classify_agent_role(
            payload,
            conversation_id=conv_id,
            db_dir=db_dir,
            workspace_dir=eff_ws,
            tokens=tokens,
            timeout=to,
        )
        advisory = build_compaction_advisory(role, tokens, effective_threshold)
        return {"injectSteps": [{"ephemeralMessage": advisory}]}
    except Exception:
        return {"injectSteps": []}


def main(argv: Optional[List[str]] = None) -> int:
    """Fail-open CLI entrypoint for PreInvocation lifecycle hook."""
    try:
        if hasattr(sys.stdin, "isatty") and sys.stdin.isatty():
            raw_stdin = ""
        elif hasattr(sys.stdin, "buffer"):
            raw_bytes = sys.stdin.buffer.read(MAX_PAYLOAD_BYTES)
            raw_stdin = raw_bytes.decode("utf-8", errors="replace")
        else:
            raw_stdin = sys.stdin.read(MAX_PAYLOAD_BYTES)
    except Exception:
        raw_stdin = ""

    try:
        res = evaluate_pre_invocation(raw_stdin)
    except Exception as exc:
        sys.stderr.write(f"[PSL PRE-INVOCATION HOOK] Error during evaluation: {exc}\n")
        traceback.print_exc(file=sys.stderr)
        sys.stderr.flush()
        res = {"injectSteps": []}

    try:
        sys.stdout.write(json.dumps(res) + "\n")
        sys.stdout.flush()
    except Exception:
        pass

    return 0


if __name__ == "__main__":
    sys.exit(main())
