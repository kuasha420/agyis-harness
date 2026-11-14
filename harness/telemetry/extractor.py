# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Arafat Zahan (@kuasha420)
# Corporate Stewardship & Infrastructure: Purrfect Software Limited (PSL)
# Governed by: ICARO-42/b Ordinance (Company-Supported Personal IP Framework)

"""
Cleanroom Telemetry Extractor & Transcript Parser (ADR-014, ADR-030).
Decoupled into harness package core to allow standalone daemon execution without pipeline dependency.
"""

from __future__ import annotations

from datetime import datetime
import json
import os
from pathlib import Path
import re
import sqlite3
from typing import Any, Dict, List, Optional, Tuple

from harness.telemetry.schema import SCHEMA_SQL, ensure_sync_columns


def parse_iso_ts(ts_str: Optional[str]) -> Optional[datetime]:
    """Parses ISO timestamp string to datetime object."""
    if not ts_str:
        return None
    cleaned = ts_str.strip().replace("Z", "+00:00")
    try:
        return datetime.fromisoformat(cleaned)
    except Exception:
        return None


def calculate_duration(start_str: Optional[str], end_str: Optional[str]) -> Optional[float]:
    """Calculates elapsed seconds between two ISO timestamp strings."""
    t1 = parse_iso_ts(start_str)
    t2 = parse_iso_ts(end_str)
    if t1 and t2:
        return abs((t2 - t1).total_seconds())
    return None


_INTERVENTION_RULES: Tuple[Tuple[str, Tuple[str, ...]], ...] = (
    ("STEERING", ("stop", "don't", "dont", "wait", "no,", "no!", "wrong", "drifted", "cancel", "undo")),
    ("CONFIRMATION", ("lgtm", "looks good", "proceed", "approved", "go ahead", "yes, please", "sure", "approved this document")),
    ("CREDENTIALS", ("password", "token", "secret", "api_key", "credentials", "auth")),
    ("CONTINUATION", ("continue", "next", "keep going", "proceed with next")),
)


def classify_intervention(text: str, preceding_failed: bool) -> str:
    """Classifies user intervention prompt into behavioral category."""
    lower = text.lower().strip()
    if lower.startswith("/boost") or "/boost " in lower:
        return "BOOST_ORCHESTRATION"
    if lower.startswith("/plan") or "/plan " in lower:
        return "PLAN_INITIATION"
    if lower.startswith("/agent-builder") or "/agent-builder " in lower or "agent-builder" in lower:
        return "AGENT_BUILDER_INVOCATION"
    if preceding_failed:
        return "ERROR_RECOVERY"
    for label, keywords in _INTERVENTION_RULES:
        if any(k in lower for k in keywords):
            return label
    return "OPERATOR_GUIDANCE"


_COMMAND_SUBSTR_CATS: Tuple[Tuple[str, Tuple[str, ...]], ...] = (
    ("test_runner", (
        "pytest", "unittest", "test_", "-m unittest", "pnpm test", "npm test", "yarn test",
        "cargo test", "go test", "jest", "vitest", "mocha", "playwright", "cypress",
        "harness.cli test", "python3 -m unittest", "python -m unittest",
    )),
)

_COMMAND_PREFIX_CATS: Tuple[Tuple[str, Tuple[str, ...]], ...] = (
    ("git", ("git ", "gh ")),
    ("grep_search", ("grep ", "rg ", "ripgrep ", "ag ", "diff ")),
    ("file_search", ("find ", "fd ", "ls ", "tree ", "locate ")),
    ("package_manager", (
        "pnpm ", "npm ", "yarn ", "bun ", "pip ", "pip3 ", "uv ", "pacman ", "yay ",
        "apt ", "apt-get ", "cargo add", "cargo install",
    )),
    ("build_compile", ("tsc", "esbuild", "cargo build", "go build", "make", "gcc", "g++", "clang", "vite build", "webpack", "next build", "ninja")),
    ("python_exec", ("python ", "python3 ", "python3.12 ", "ipython ")),
    ("system_probe", ("which ", "command -v", "ps ", "top ", "htop ", "uname", "uptime", "whoami", "id ", "df ", "du ", "systemctl ", "journalctl ")),
    ("network", ("curl ", "wget ", "ping ", "ssh ", "scp ", "rsync ", "nc ")),
    ("file_system", ("cat ", "head ", "tail ", "mkdir ", "cp ", "mv ", "rm ", "touch ", "chmod ", "chown ", "sed ", "awk ")),
)


def classify_command(cmd_line: Optional[str]) -> Optional[str]:
    """Classifies a shell command into high-level operational categories."""
    if not cmd_line or not isinstance(cmd_line, str) or not cmd_line.strip():
        return None
    lower = cmd_line.strip().lower()
    for cat, kws in _COMMAND_SUBSTR_CATS:
        if any(k in lower for k in kws):
            return cat
    for cat, kws in _COMMAND_PREFIX_CATS:
        if any(lower.startswith(k) or f" {k}" in lower for k in kws):
            return cat
    return "other"


def ensure_volume_columns(conn: sqlite3.Connection) -> None:
    """Non-destructively ensures volume & character distribution columns exist."""
    cur = conn.cursor()
    cur.execute("PRAGMA table_info(tool_calls)")
    existing_cols = {row[1] for row in cur.fetchall()}

    new_cols = [
        ("output_length_chars", "INTEGER"),
        ("output_lines", "INTEGER"),
        ("arguments_length_chars", "INTEGER"),
        ("command_category", "TEXT"),
        ("is_truncated", "INTEGER DEFAULT 0"),
    ]
    for col_name, col_type in new_cols:
        if col_name not in existing_cols:
            try:
                cur.execute(f"ALTER TABLE tool_calls ADD COLUMN {col_name} {col_type}")
            except sqlite3.OperationalError:
                pass

    cur.execute("CREATE INDEX IF NOT EXISTS idx_tools_category ON tool_calls(command_category)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_tools_output_len ON tool_calls(output_length_chars)")
    conn.commit()


def ensure_telemetry_schema(conn: sqlite3.Connection) -> None:
    """Ensures all canonical telemetry tables, columns, and unique indexes exist."""
    conn.cursor().executescript(SCHEMA_SQL)
    ensure_volume_columns(conn)
    ensure_sync_columns(conn)


def upsert_session_telemetry(
    conn: sqlite3.Connection,
    session_row: Dict[str, Any],
    step_rows: List[Dict[str, Any]],
    tool_rows: List[Dict[str, Any]],
    interv_rows: List[Dict[str, Any]],
    commit: bool = True,
) -> None:
    """Atomically upserts session, steps, tool_calls, and user_interventions via schema.py."""
    cur = conn.cursor()
    s_id = session_row["session_id"]

    # Preserve remote sync metadata unless new steps arrived locally.
    cur.execute("SELECT remote_synced_at, origin_developer, total_steps FROM sessions WHERE session_id = ?", (s_id,))
    existing = cur.fetchone()
    if existing:
        existing_synced_at, existing_origin, existing_steps = existing[0], existing[1], existing[2]
        if existing_steps is not None and (session_row.get("total_steps") or 0) > existing_steps:
            session_row["remote_synced_at"] = None
        elif existing_synced_at and not session_row.get("remote_synced_at"):
            session_row["remote_synced_at"] = existing_synced_at
        if existing_origin and existing_origin != "local":
            session_row["origin_developer"] = existing_origin

    for tbl in ("steps", "tool_calls", "user_interventions"):
        cur.execute(f"DELETE FROM {tbl} WHERE session_id = ?", (s_id,))

    sess_cols = (
        "session_id", "start_time", "end_time", "duration_seconds", "total_steps",
        "model", "workspace_path", "transcript_path", "file_size_bytes", "has_errors",
        "tool_call_count", "tool_error_count", "intervention_count",
        "origin_developer", "remote_synced_at",
    )
    sess_defaults = {
        "has_errors": 0, "tool_call_count": 0, "tool_error_count": 0,
        "intervention_count": 0, "origin_developer": "local",
    }
    sess_vals = tuple(session_row.get(c, sess_defaults.get(c)) for c in sess_cols)
    updates = ", ".join(f"{c}=excluded.{c}" for c in sess_cols[1:])
    cur.execute(
        f"INSERT INTO sessions ({', '.join(sess_cols)}) VALUES ({', '.join(['?'] * len(sess_cols))}) "
        f"ON CONFLICT(session_id) DO UPDATE SET {updates}",
        sess_vals,
    )

    child_specs = (
        (
            "steps",
            ("session_id", "step_index", "step_type", "source", "status", "created_at",
             "content_length", "content_snippet", "has_thinking", "thinking_length", "tool_count"),
            {},
            step_rows,
        ),
        (
            "tool_calls",
            ("session_id", "step_index", "result_step_index", "tool_name", "arguments_json",
             "arguments_snippet", "target_path", "command_line", "started_at", "completed_at",
             "duration_seconds", "status", "exit_code", "error_snippet", "is_loop_candidate",
             "output_length_chars", "output_lines", "arguments_length_chars", "command_category", "is_truncated"),
            {"is_loop_candidate": 0, "output_length_chars": 0, "output_lines": 0, "arguments_length_chars": 0, "is_truncated": 0},
            tool_rows,
        ),
        (
            "user_interventions",
            ("session_id", "step_index", "created_at", "prompt_text", "prompt_length",
             "preceding_tool_failed", "preceding_tool_name", "preceding_error_snippet", "intervention_type"),
            {"prompt_length": 0, "preceding_tool_failed": 0, "preceding_tool_name": "", "preceding_error_snippet": ""},
            interv_rows,
        ),
    )
    for tbl, cols, defaults, rows in child_specs:
        if rows:
            cur.executemany(
                f"INSERT OR IGNORE INTO {tbl} ({', '.join(cols)}) VALUES ({', '.join(['?'] * len(cols))})",
                [tuple(r.get(c, defaults.get(c)) for c in cols) for r in rows],
            )

    if commit:
        conn.commit()


def extract_session(
    transcript_path: Path,
) -> Optional[Tuple[Dict[str, Any], List[Dict[str, Any]], List[Dict[str, Any]], List[Dict[str, Any]]]]:
    """Extracts session, steps, tool calls, and user interventions from transcript JSONL."""
    session_id = transcript_path.parts[-4]
    try:
        raw_size = transcript_path.stat().st_size
    except Exception:
        return None

    with open(transcript_path, encoding="utf-8", errors="replace") as f:
        steps: List[Dict[str, Any]] = []
        for line in f:
            if line.strip():
                try:
                    obj = json.loads(line)
                    if isinstance(obj, dict):
                        steps.append(obj)
                except Exception:
                    continue

    if not steps:
        return None

    def _step_key(s: Any) -> int:
        if isinstance(s, dict):
            idx = s.get("step_index")
            if isinstance(idx, int):
                return idx
        return 0

    steps.sort(key=_step_key)
    start_time, end_time = steps[0].get("created_at"), steps[-1].get("created_at")
    duration_s = calculate_duration(start_time, end_time)

    model_detected = "Gemini 3.5/Flash/Pro (Default)"
    workspace_detected = ""
    tool_calls_extracted: List[Dict[str, Any]] = []
    interventions_extracted: List[Dict[str, Any]] = []
    has_errors, tool_error_count = False, 0
    step_by_idx = {
        s.get("step_index"): s
        for s in steps
        if isinstance(s, dict) and isinstance(s.get("step_index"), int)
    }
    recent_tool_failed, recent_tool_name, recent_error_snippet = False, "", ""
    last_tool_sig, repeated_tool_count = None, 0

    for i, s in enumerate(steps):
        if not isinstance(s, dict):
            continue
        raw_idx = s.get("step_index")
        s_idx = raw_idx if isinstance(raw_idx, int) else i
        s_type, source = s.get("type", "UNKNOWN"), s.get("source", "UNKNOWN")
        content = str(s.get("content", ""))

        if "Model Selection" in content:
            m = re.search(r"Model Selection` from .*? to ([^.\n\r]+)", content)
            if m:
                model_detected = m.group(1).strip()

        if not workspace_detected and "/Dev/" in content:
            m = re.search(r"(/[a-zA-Z0-9_\-]+/Dev/[a-zA-Z0-9_\-]+)", content)
            if m:
                workspace_detected = m.group(1)

        if s_idx > 0 and (s_type == "USER_INPUT" or source == "USER_EXPLICIT"):
            clean_prompt = re.sub(
                r"<USER_REQUEST>|\</USER_REQUEST\>|<ADDITIONAL_METADATA>[\s\S]*?</ADDITIONAL_METADATA>",
                "", content,
            ).strip()
            if clean_prompt:
                interventions_extracted.append({
                    "session_id": session_id, "step_index": s_idx, "created_at": s.get("created_at"),
                    "prompt_text": clean_prompt, "prompt_length": len(clean_prompt),
                    "preceding_tool_failed": 1 if recent_tool_failed else 0,
                    "preceding_tool_name": recent_tool_name,
                    "preceding_error_snippet": recent_error_snippet[:500],
                    "intervention_type": classify_intervention(clean_prompt, recent_tool_failed),
                })

        raw_tools = s.get("tool_calls", [])
        if raw_tools and isinstance(raw_tools, list):
            for tc in raw_tools:
                if not isinstance(tc, dict):
                    continue
                t_name, t_args = tc.get("name", "unknown"), tc.get("args", {})
                target_path = (
                    t_args.get("TargetFile") or t_args.get("AbsolutePath")
                    or t_args.get("SearchPath") or t_args.get("DirectoryPath")
                ) if isinstance(t_args, dict) else None
                cmd_line = t_args.get("CommandLine") if isinstance(t_args, dict) else None

                tool_sig = (t_name, str(target_path or cmd_line or t_args))
                is_loop = 0
                if tool_sig == last_tool_sig:
                    repeated_tool_count += 1
                    is_loop = 1 if repeated_tool_count >= 2 else 0
                else:
                    last_tool_sig, repeated_tool_count = tool_sig, 1

                res_step = step_by_idx.get(s_idx + 1) if isinstance(s_idx, int) else None
                t_status, exit_code, err_snippet = "SUCCESS", 0, ""
                res_content = str(res_step.get("content", "")) if isinstance(res_step, dict) else ""
                started_at = completed_at = tool_duration = None

                if res_content:
                    m_created = re.search(r"Created At:\s*([^\n\r]+)", res_content)
                    m_completed = re.search(r"Completed At:\s*([^\n\r]+)", res_content)
                    if m_created and m_completed:
                        started_at, completed_at = m_created.group(1).strip(), m_completed.group(1).strip()
                        tool_duration = calculate_duration(started_at, completed_at)

                    m_exit = re.search(r"(?:failed with exit code:|exited with code)\s*(\d+)", res_content)
                    if m_exit:
                        exit_code = int(m_exit.group(1))
                        if exit_code != 0:
                            t_status, has_errors = "FAILED", True
                            tool_error_count += 1
                            err_snippet = res_content[:800]
                    elif "Encountered error in tool execution:" in res_content or (isinstance(res_step, dict) and res_step.get("status") == "ERROR"):
                        t_status = "ERROR"
                        exit_code = -1
                        has_errors = True
                        tool_error_count += 1
                        err_snippet = res_content[:800]

                if t_status in ("FAILED", "ERROR"):
                    recent_tool_failed, recent_tool_name, recent_error_snippet = True, t_name, err_snippet
                else:
                    recent_tool_failed, recent_tool_name, recent_error_snippet = False, "", ""

                args_json = json.dumps(t_args) if isinstance(t_args, dict) else str(t_args)
                is_trunc = 1 if (
                    res_content and ("<truncated" in res_content or "content" in (res_step or {}).get("truncated_fields", ()))
                ) else 0
                tool_calls_extracted.append({
                    "session_id": session_id, "step_index": s_idx, "result_step_index": s_idx + 1 if res_step else None,
                    "tool_name": t_name, "arguments_json": args_json, "arguments_snippet": str(t_args)[:250],
                    "target_path": str(target_path) if target_path else None,
                    "command_line": str(cmd_line) if cmd_line else None,
                    "started_at": started_at, "completed_at": completed_at, "duration_seconds": tool_duration,
                    "status": t_status, "exit_code": exit_code, "error_snippet": err_snippet,
                    "is_loop_candidate": is_loop, "output_length_chars": len(res_content) if res_content else 0,
                    "output_lines": (res_content.count("\n") + 1) if res_content else 0,
                    "arguments_length_chars": len(args_json),
                    "command_category": classify_command(cmd_line) if cmd_line else None, "is_truncated": is_trunc,
                })

    step_rows = [
        {
            "session_id": session_id, "step_index": s.get("step_index", 0), "step_type": s.get("type", "UNKNOWN"),
            "source": s.get("source", "UNKNOWN"), "status": s.get("status", "DONE"), "created_at": s.get("created_at"),
            "content_length": len(str(s.get("content", ""))),
            "content_snippet": str(s.get("content", ""))[:200] if s.get("content") else None,
            "has_thinking": 1 if s.get("thinking") else 0, "thinking_length": len(str(s.get("thinking", ""))),
            "tool_count": len(s.get("tool_calls", [])) if isinstance(s.get("tool_calls"), list) else 0,
        }
        for s in steps
    ]

    session_row = {
        "session_id": session_id, "start_time": start_time, "end_time": end_time,
        "duration_seconds": duration_s, "total_steps": len(steps), "model": model_detected,
        "workspace_path": workspace_detected, "transcript_path": str(transcript_path),
        "file_size_bytes": raw_size, "has_errors": 1 if has_errors else 0,
        "tool_call_count": len(tool_calls_extracted), "tool_error_count": tool_error_count,
        "intervention_count": len(interventions_extracted), "origin_developer": "local", "remote_synced_at": None,
    }
    return session_row, step_rows, tool_calls_extracted, interventions_extracted


__all__ = [
    "SCHEMA_SQL", "calculate_duration", "classify_command", "classify_intervention",
    "ensure_sync_columns", "ensure_telemetry_schema", "ensure_volume_columns",
    "extract_session", "parse_iso_ts", "upsert_session_telemetry",
]
