#!/usr/bin/env python3
"""
PSL Harness for Google Antigravity™
Transcript & Telemetry Harvester

Extracts developer telemetry from:
~/.gemini/antigravity/brain/*/transcript.jsonl
into structured SQLite (data/telemetry.db).

Populates:
- sessions
- steps
- tool_calls
- user_interventions
"""

from __future__ import annotations

import argparse
from datetime import datetime
import glob
import json
import os
from pathlib import Path
import re
import sqlite3
import sys
import time
from typing import Any, Dict, List, Optional, Tuple


SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS sessions (
    session_id TEXT PRIMARY KEY,
    start_time TEXT,
    end_time TEXT,
    duration_seconds REAL,
    total_steps INTEGER,
    model TEXT,
    workspace_path TEXT,
    transcript_path TEXT,
    file_size_bytes INTEGER,
    has_errors INTEGER,
    tool_call_count INTEGER,
    tool_error_count INTEGER,
    intervention_count INTEGER
);

CREATE TABLE IF NOT EXISTS steps (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id TEXT,
    step_index INTEGER,
    step_type TEXT,
    source TEXT,
    status TEXT,
    created_at TEXT,
    content_length INTEGER,
    content_snippet TEXT,
    has_thinking INTEGER,
    thinking_length INTEGER,
    tool_count INTEGER,
    FOREIGN KEY(session_id) REFERENCES sessions(session_id)
);

CREATE TABLE IF NOT EXISTS tool_calls (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id TEXT,
    step_index INTEGER,
    result_step_index INTEGER,
    tool_name TEXT,
    arguments_json TEXT,
    arguments_snippet TEXT,
    target_path TEXT,
    command_line TEXT,
    started_at TEXT,
    completed_at TEXT,
    duration_seconds REAL,
    status TEXT, -- 'SUCCESS', 'FAILED', 'ERROR'
    exit_code INTEGER,
    error_snippet TEXT,
    is_loop_candidate INTEGER DEFAULT 0,
    FOREIGN KEY(session_id) REFERENCES sessions(session_id)
);

CREATE TABLE IF NOT EXISTS user_interventions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id TEXT,
    step_index INTEGER,
    created_at TEXT,
    prompt_text TEXT,
    prompt_length INTEGER,
    preceding_tool_failed INTEGER,
    preceding_tool_name TEXT,
    preceding_error_snippet TEXT,
    intervention_type TEXT, -- 'ERROR_RECOVERY', 'STEERING', 'CONFIRMATION', 'CREDENTIALS', 'CONTINUATION', 'OPERATOR_GUIDANCE'
    FOREIGN KEY(session_id) REFERENCES sessions(session_id)
);

CREATE INDEX IF NOT EXISTS idx_steps_session ON steps(session_id);
CREATE INDEX IF NOT EXISTS idx_tools_session ON tool_calls(session_id);
CREATE INDEX IF NOT EXISTS idx_tools_name ON tool_calls(tool_name);
CREATE INDEX IF NOT EXISTS idx_tools_status ON tool_calls(status);
CREATE INDEX IF NOT EXISTS idx_interventions_session ON user_interventions(session_id);
CREATE INDEX IF NOT EXISTS idx_interventions_type ON user_interventions(intervention_type);
"""


def parse_iso_ts(ts_str: Optional[str]) -> Optional[datetime]:
    if not ts_str:
        return None
    cleaned = ts_str.strip().replace("Z", "+00:00")
    try:
        return datetime.fromisoformat(cleaned)
    except Exception:
        return None


def calculate_duration(start_str: Optional[str], end_str: Optional[str]) -> Optional[float]:
    t1 = parse_iso_ts(start_str)
    t2 = parse_iso_ts(end_str)
    if t1 and t2:
        return abs((t2 - t1).total_seconds())
    return None


def classify_intervention(text: str, preceding_failed: bool) -> str:
    lower = text.lower()
    if preceding_failed:
        return "ERROR_RECOVERY"
    if any(k in lower for k in ["stop", "don't", "dont", "wait", "no,", "no!", "wrong", "drifted", "cancel", "undo"]):
        return "STEERING"
    if any(k in lower for k in ["lgtm", "looks good", "proceed", "approved", "go ahead", "yes, please", "sure"]):
        return "CONFIRMATION"
    if any(k in lower for k in ["password", "token", "secret", "api_key", "credentials", "auth"]):
        return "CREDENTIALS"
    if any(k in lower for k in ["continue", "next", "keep going", "proceed with next"]):
        return "CONTINUATION"
    return "OPERATOR_GUIDANCE"


def extract_session(transcript_path: Path) -> Optional[Tuple[Dict[str, Any], List[Dict[str, Any]], List[Dict[str, Any]], List[Dict[str, Any]]]]:
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

        if not workspace_detected and "/home/kuasha/Dev/" in content:
            m = re.search(r"(/home/kuasha/Dev/[a-zA-Z0-9_\-]+)", content)
            if m:
                workspace_detected = m.group(1)

        if s_idx > 0 and (s_type == "USER_INPUT" or source == "USER_EXPLICIT"):
            clean_prompt = re.sub(r"<USER_REQUEST>|\</USER_REQUEST\>|<ADDITIONAL_METADATA>[\s\S]*?</ADDITIONAL_METADATA>", "", content).strip()
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
                    "intervention_type": itype
                })

        raw_tools = s.get("tool_calls", [])
        if raw_tools and isinstance(raw_tools, list):
            for t_idx, tc in enumerate(raw_tools):
                if not isinstance(tc, dict):
                    continue
                t_name = tc.get("name", "unknown")
                t_args = tc.get("args", {})
                
                target_path = t_args.get("TargetFile") or t_args.get("AbsolutePath") or t_args.get("SearchPath") or t_args.get("DirectoryPath")
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
                    "is_loop_candidate": is_loop
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
            "tool_count": len(s.get("tool_calls", [])) if isinstance(s.get("tool_calls"), list) else 0
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
        "intervention_count": len(interventions_extracted)
    }

    return session_row, step_rows, tool_calls_extracted, interventions_extracted


def main() -> None:
    parser = argparse.ArgumentParser(description="Harvest Antigravity transcripts into SQLite.")
    parser.add_argument("--db", default="data/telemetry.db", help="Path to SQLite database")
    parser.add_argument("--limit", type=int, default=None, help="Limit number of sessions processed")
    parser.add_argument("--reset", action="store_true", help="Reset/rebuild database tables")
    args = parser.parse_args()

    db_path = Path(args.db)
    db_path.parent.mkdir(parents=True, exist_ok=True)

    if args.reset and db_path.exists():
        db_path.unlink()

    conn = sqlite3.connect(db_path)
    cur = conn.cursor()
    cur.executescript(SCHEMA_SQL)
    conn.commit()

    pattern = str(Path.home() / ".gemini" / "antigravity" / "brain" / "*" / ".system_generated" / "logs" / "transcript.jsonl")
    transcript_paths = sorted(glob.glob(pattern), key=lambda p: os.path.getmtime(p), reverse=True)

    if args.limit:
        transcript_paths = transcript_paths[:args.limit]

    print(f"[*] Found {len(transcript_paths)} session transcripts to harvest.")
    t0 = time.time()

    total_sessions = 0
    total_steps = 0
    total_tools = 0
    total_interventions = 0
    total_tool_errors = 0

    cur.execute("PRAGMA synchronous = OFF")
    cur.execute("PRAGMA journal_mode = MEMORY")

    for i, p_str in enumerate(transcript_paths, 1):
        res = extract_session(Path(p_str))
        if not res:
            continue
        session_row, step_rows, tool_rows, interv_rows = res
        s_id = session_row["session_id"]

        # Ensure idempotence by clearing existing rows for this session
        cur.execute("DELETE FROM steps WHERE session_id = ?", (s_id,))
        cur.execute("DELETE FROM tool_calls WHERE session_id = ?", (s_id,))
        cur.execute("DELETE FROM user_interventions WHERE session_id = ?", (s_id,))

        cur.execute("""
            INSERT OR REPLACE INTO sessions (
                session_id, start_time, end_time, duration_seconds, total_steps,
                model, workspace_path, transcript_path, file_size_bytes, has_errors,
                tool_call_count, tool_error_count, intervention_count
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            session_row["session_id"], session_row["start_time"], session_row["end_time"],
            session_row["duration_seconds"], session_row["total_steps"], session_row["model"],
            session_row["workspace_path"], session_row["transcript_path"], session_row["file_size_bytes"],
            session_row["has_errors"], session_row["tool_call_count"], session_row["tool_error_count"],
            session_row["intervention_count"]
        ))

        cur.executemany("""
            INSERT INTO steps (
                session_id, step_index, step_type, source, status, created_at,
                content_length, content_snippet, has_thinking, thinking_length, tool_count
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, [
            (
                s["session_id"], s["step_index"], s["step_type"], s["source"], s["status"],
                s["created_at"], s["content_length"], s["content_snippet"], s["has_thinking"],
                s["thinking_length"], s["tool_count"]
            )
            for s in step_rows
        ])

        if tool_rows:
            cur.executemany("""
                INSERT INTO tool_calls (
                    session_id, step_index, result_step_index, tool_name, arguments_json,
                    arguments_snippet, target_path, command_line, started_at, completed_at,
                    duration_seconds, status, exit_code, error_snippet, is_loop_candidate
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, [
                (
                    t["session_id"], t["step_index"], t["result_step_index"], t["tool_name"],
                    t["arguments_json"], t["arguments_snippet"], t["target_path"], t["command_line"],
                    t["started_at"], t["completed_at"], t["duration_seconds"], t["status"],
                    t["exit_code"], t["error_snippet"], t["is_loop_candidate"]
                )
                for t in tool_rows
            ])

        if interv_rows:
            cur.executemany("""
                INSERT INTO user_interventions (
                    session_id, step_index, created_at, prompt_text, prompt_length,
                    preceding_tool_failed, preceding_tool_name, preceding_error_snippet, intervention_type
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, [
                (
                    u["session_id"], u["step_index"], u["created_at"], u["prompt_text"],
                    u["prompt_length"], u["preceding_tool_failed"], u["preceding_tool_name"],
                    u["preceding_error_snippet"], u["intervention_type"]
                )
                for u in interv_rows
            ])

        total_sessions += 1
        total_steps += len(step_rows)
        total_tools += len(tool_rows)
        total_interventions += len(interv_rows)
        total_tool_errors += session_row["tool_error_count"]

        if i % 50 == 0 or i == len(transcript_paths):
            conn.commit()
            print(f"  [{i}/{len(transcript_paths)}] Ingested {total_sessions} sessions, {total_steps} steps, {total_tools} tool calls...")

    conn.commit()
    conn.close()

    dt = time.time() - t0
    print("=" * 70)
    print(" 🚀 HARVEST COMPLETE")
    print("=" * 70)
    print(f"Database:             {db_path}")
    print(f"Ingestion Duration:   {dt:.2f}s")
    print(f"Sessions Harvested:   {total_sessions}")
    print(f"Steps Stored:         {total_steps}")
    print(f"Tool Calls Stored:    {total_tools}")
    print(f"Tool Errors Flagged:  {total_tool_errors}")
    print(f"Interventions Mined:  {total_interventions}")
    print("=" * 70)


if __name__ == "__main__":
    main()
