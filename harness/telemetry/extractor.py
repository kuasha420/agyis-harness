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


def classify_intervention(text: str, preceding_failed: bool) -> str:
    """Classifies user intervention prompt into behavioral category."""
    lower = text.lower().strip()
    # Native Antigravity slash commands (ADR-031)
    if lower.startswith("/boost") or "/boost " in lower:
        return "BOOST_ORCHESTRATION"
    if lower.startswith("/plan") or "/plan " in lower:
        return "PLAN_INITIATION"
    # PSL Harness Skill invocation via progressive skill dispatch (ADR-026)
    if lower.startswith("/agent-builder") or "/agent-builder " in lower or "agent-builder" in lower:
        return "AGENT_BUILDER_INVOCATION"
    if preceding_failed:
        return "ERROR_RECOVERY"
    if any(k in lower for k in ["stop", "don't", "dont", "wait", "no,", "no!", "wrong", "drifted", "cancel", "undo"]):
        return "STEERING"
    if any(k in lower for k in ["lgtm", "looks good", "proceed", "approved", "go ahead", "yes, please", "sure", "approved this document"]):
        return "CONFIRMATION"
    if any(k in lower for k in ["password", "token", "secret", "api_key", "credentials", "auth"]):
        return "CREDENTIALS"
    if any(k in lower for k in ["continue", "next", "keep going", "proceed with next"]):
        return "CONTINUATION"
    return "OPERATOR_GUIDANCE"


def classify_command(cmd_line: Optional[str]) -> Optional[str]:
    """Classifies a shell command into high-level operational categories."""
    if not cmd_line or not isinstance(cmd_line, str):
        return None
    cleaned = cmd_line.strip()
    if not cleaned:
        return None
    lower = cleaned.lower()

    # Test runners
    if any(k in lower for k in [
        "pytest", "unittest", "test_", "-m unittest", "pnpm test", "npm test", "yarn test",
        "cargo test", "go test", "jest", "vitest", "mocha", "playwright", "cypress",
        "harness.cli test", "python3 -m unittest", "python -m unittest"
    ]):
        return "test_runner"

    # Git & GitHub CLI
    if lower.startswith("git ") or " git " in lower or lower.startswith("gh ") or " gh " in lower:
        return "git"

    # Grep & text search
    if any(lower.startswith(k) or f" {k}" in lower for k in ["grep ", "rg ", "ripgrep ", "ag ", "diff "]):
        return "grep_search"

    # File search & listing
    if any(lower.startswith(k) or f" {k}" in lower for k in ["find ", "fd ", "ls ", "tree ", "locate "]):
        return "file_search"

    # Package managers
    if any(lower.startswith(k) or f" {k}" in lower for k in [
        "pnpm ", "npm ", "yarn ", "bun ", "pip ", "pip3 ", "uv ", "pacman ", "yay ",
        "apt ", "apt-get ", "cargo add", "cargo install"
    ]):
        return "package_manager"

    # Build & compilers
    if any(lower.startswith(k) or f" {k}" in lower for k in [
        "tsc", "esbuild", "cargo build", "go build", "make", "gcc", "g++", "clang",
        "vite build", "webpack", "next build", "ninja"
    ]):
        return "build_compile"

    # Python scripts & one-liners
    if any(lower.startswith(k) or f" {k}" in lower for k in ["python ", "python3 ", "python3.12 ", "ipython "]):
        return "python_exec"

    # System probes
    if any(lower.startswith(k) or f" {k}" in lower for k in [
        "which ", "command -v", "ps ", "top ", "htop ", "uname", "uptime", "whoami",
        "id ", "df ", "du ", "systemctl ", "journalctl "
    ]):
        return "system_probe"

    # Network probes
    if any(lower.startswith(k) or f" {k}" in lower for k in ["curl ", "wget ", "ping ", "ssh ", "scp ", "rsync ", "nc "]):
        return "network"

    # Filesystem operations
    if any(lower.startswith(k) or f" {k}" in lower for k in [
        "cat ", "head ", "tail ", "mkdir ", "cp ", "mv ", "rm ", "touch ", "chmod ", "chown ", "sed ", "awk "
    ]):
        return "file_system"

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
            cur.execute(f"ALTER TABLE tool_calls ADD COLUMN {col_name} {col_type}")

    # Ensure indexes
    cur.execute("CREATE INDEX IF NOT EXISTS idx_tools_category ON tool_calls(command_category)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_tools_output_len ON tool_calls(output_length_chars)")
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

    steps: List[Dict[str, Any]] = []
    with open(transcript_path, encoding="utf-8", errors="replace") as f:
        for line in f:
            if not line.strip():
                continue
            try:
                steps.append(json.loads(line))
            except Exception:
                continue

    if not steps:
        return None

    steps.sort(key=lambda s: s.get("step_index", 0))

    start_time = steps[0].get("created_at")
    end_time = steps[-1].get("created_at")
    duration_s = calculate_duration(start_time, end_time)

    model_detected = "Gemini 3.5/Flash/Pro (Default)"
    workspace_detected = ""
    tool_calls_extracted: List[Dict[str, Any]] = []
    interventions_extracted: List[Dict[str, Any]] = []
    has_errors = False
    tool_error_count = 0

    step_by_idx = {s.get("step_index", 0): s for s in steps}

    recent_tool_failed = False
    recent_tool_name = ""
    recent_error_snippet = ""

    last_tool_sig = None
    repeated_tool_count = 0

    for i, s in enumerate(steps):
        s_idx = s.get("step_index", i)
        s_type = s.get("type", "UNKNOWN")
        source = s.get("source", "UNKNOWN")
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
                "",
                content,
            ).strip()
            if clean_prompt:
                itype = classify_intervention(clean_prompt, recent_tool_failed)
                interventions_extracted.append({
                    "session_id": session_id,
                    "step_index": s_idx,
                    "created_at": s.get("created_at"),
                    "prompt_text": clean_prompt,
                    "prompt_length": len(clean_prompt),
                    "preceding_tool_failed": 1 if recent_tool_failed else 0,
                    "preceding_tool_name": recent_tool_name,
                    "preceding_error_snippet": recent_error_snippet[:500],
                    "intervention_type": itype,
                })

        raw_tools = s.get("tool_calls", [])
        if raw_tools and isinstance(raw_tools, list):
            for t_idx, tc in enumerate(raw_tools):
                if not isinstance(tc, dict):
                    continue
                t_name = tc.get("name", "unknown")
                t_args = tc.get("args", {})

                target_path = (
                    t_args.get("TargetFile")
                    or t_args.get("AbsolutePath")
                    or t_args.get("SearchPath")
                    or t_args.get("DirectoryPath")
                )
                cmd_line = t_args.get("CommandLine")

                tool_sig = (t_name, str(target_path or cmd_line or t_args))
                is_loop = 0
                if tool_sig == last_tool_sig:
                    repeated_tool_count += 1
                    if repeated_tool_count >= 2:
                        is_loop = 1
                else:
                    last_tool_sig = tool_sig
                    repeated_tool_count = 1

                res_step = step_by_idx.get(s_idx + 1)
                t_status = "SUCCESS"
                exit_code = 0
                err_snippet = ""
                res_content = str(res_step.get("content", "")) if res_step else ""
                started_at = None
                completed_at = None
                tool_duration = None

                if res_content:
                    m_created = re.search(r"Created At:\s*([^\n\r]+)", res_content)
                    m_completed = re.search(r"Completed At:\s*([^\n\r]+)", res_content)
                    if m_created and m_completed:
                        started_at = m_created.group(1).strip()
                        completed_at = m_completed.group(1).strip()
                        tool_duration = calculate_duration(started_at, completed_at)

                    m_exit = re.search(r"(?:failed with exit code:|exited with code)\s*(\d+)", res_content)
                    if m_exit:
                        exit_code = int(m_exit.group(1))
                        if exit_code != 0:
                            t_status = "FAILED"
                            has_errors = True
                            tool_error_count += 1
                            err_snippet = res_content[:800]
                    elif "Encountered error in tool execution:" in res_content:
                        t_status = "ERROR"
                        exit_code = -1
                        has_errors = True
                        tool_error_count += 1
                        err_snippet = res_content[:800]
                    elif res_step.get("status") == "ERROR":
                        t_status = "ERROR"
                        exit_code = -1
                        has_errors = True
                        tool_error_count += 1
                        err_snippet = res_content[:800]

                if t_status in ["FAILED", "ERROR"]:
                    recent_tool_failed = True
                    recent_tool_name = t_name
                    recent_error_snippet = err_snippet
                else:
                    recent_tool_failed = False
                    recent_tool_name = ""
                    recent_error_snippet = ""

                out_len = len(res_content) if res_content else 0
                out_lines = (res_content.count("\n") + 1) if res_content else 0
                args_len = len(json.dumps(t_args)) if isinstance(t_args, dict) else len(str(t_args))
                cmd_cat = classify_command(cmd_line) if cmd_line else None
                is_trunc = (
                    1
                    if (
                        res_content
                        and (
                            "<truncated" in res_content
                            or (
                                "truncated_fields" in (res_step or {})
                                and "content" in (res_step or {}).get("truncated_fields", [])
                            )
                        )
                    )
                    else 0
                )

                tool_calls_extracted.append({
                    "session_id": session_id,
                    "step_index": s_idx,
                    "result_step_index": s_idx + 1 if res_step else None,
                    "tool_name": t_name,
                    "arguments_json": json.dumps(t_args) if isinstance(t_args, dict) else str(t_args),
                    "arguments_snippet": str(t_args)[:250],
                    "target_path": str(target_path) if target_path else None,
                    "command_line": str(cmd_line) if cmd_line else None,
                    "started_at": started_at,
                    "completed_at": completed_at,
                    "duration_seconds": tool_duration,
                    "status": t_status,
                    "exit_code": exit_code,
                    "error_snippet": err_snippet,
                    "is_loop_candidate": is_loop,
                    "output_length_chars": out_len,
                    "output_lines": out_lines,
                    "arguments_length_chars": args_len,
                    "command_category": cmd_cat,
                    "is_truncated": is_trunc,
                })

    step_rows = []
    for s in steps:
        c = str(s.get("content", ""))
        thinking = str(s.get("thinking", ""))
        step_rows.append({
            "session_id": session_id,
            "step_index": s.get("step_index", 0),
            "step_type": s.get("type", "UNKNOWN"),
            "source": s.get("source", "UNKNOWN"),
            "status": s.get("status", "DONE"),
            "created_at": s.get("created_at"),
            "content_length": len(c),
            "content_snippet": c[:200] if c else None,
            "has_thinking": 1 if thinking else 0,
            "thinking_length": len(thinking),
            "tool_count": len(s.get("tool_calls", [])) if isinstance(s.get("tool_calls"), list) else 0,
        })

    session_row = {
        "session_id": session_id,
        "start_time": start_time,
        "end_time": end_time,
        "duration_seconds": duration_s,
        "total_steps": len(steps),
        "model": model_detected,
        "workspace_path": workspace_detected,
        "transcript_path": str(transcript_path),
        "file_size_bytes": raw_size,
        "has_errors": 1 if has_errors else 0,
        "tool_call_count": len(tool_calls_extracted),
        "tool_error_count": tool_error_count,
        "intervention_count": len(interventions_extracted),
        "origin_developer": "local",
        "remote_synced_at": None,
    }

    return session_row, step_rows, tool_calls_extracted, interventions_extracted


__all__ = [
    "SCHEMA_SQL",
    "calculate_duration",
    "classify_command",
    "classify_intervention",
    "ensure_sync_columns",
    "ensure_volume_columns",
    "extract_session",
    "parse_iso_ts",
]
