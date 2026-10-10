#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Purrfect Software Limited (PSL)

"""
PSL Harness for Google Antigravity™
Native SQLite Conversation Harvester (ADR-030 / Issue #15)

Ingests Antigravity conversation databases:
~/.gemini/antigravity/conversations/*.db
into structured SQLite (data/telemetry.db).

Populates:
- sessions
- steps
- tool_calls
- user_interventions
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import glob
import json
import os
from pathlib import Path
import re
import sqlite3
import sys
import time
from typing import Any, Dict, List, Optional, Tuple

from pipeline.extract_transcripts import (
    SCHEMA_SQL,
    calculate_duration,
    classify_command,
    classify_intervention,
    ensure_sync_columns,
    ensure_volume_columns,
    parse_iso_ts,
)


def decode_varint(data: bytes, offset: int = 0) -> Tuple[int, int]:
    """Decodes a protobuf varint from binary data starting at offset."""
    val = 0
    shift = 0
    n = len(data)
    while offset < n:
        b = data[offset]
        offset += 1
        val |= (b & 0x7F) << shift
        if not (b & 0x80):
            break
        shift += 7
    return val, offset


def parse_protobuf_fields(data: bytes) -> List[Tuple[int, int, Any]]:
    """Decodes a protobuf wire stream into a list of (field_number, wire_type, value) tuples."""
    if not data:
        return []
    offset = 0
    fields: List[Tuple[int, int, Any]] = []
    n = len(data)
    while offset < n:
        try:
            key, offset = decode_varint(data, offset)
            wire_type = key & 0x07
            field_num = key >> 3
            if field_num == 0:
                break
            if wire_type == 0:  # varint
                val, offset = decode_varint(data, offset)
                fields.append((field_num, wire_type, val))
            elif wire_type == 1:  # 64-bit
                val_bytes = data[offset : offset + 8]
                offset += 8
                fields.append((field_num, wire_type, val_bytes))
            elif wire_type == 2:  # length-delimited
                length, offset = decode_varint(data, offset)
                if offset + length > n:
                    break
                val_bytes = data[offset : offset + length]
                offset += length
                fields.append((field_num, wire_type, val_bytes))
            elif wire_type == 5:  # 32-bit
                val_bytes = data[offset : offset + 4]
                offset += 4
                fields.append((field_num, wire_type, val_bytes))
            else:
                break
        except Exception:
            break
    return fields


def parse_proto_timestamp(data: bytes) -> Optional[str]:
    """Extracts an ISO 8601 UTC timestamp from a protobuf google.protobuf.Timestamp message."""
    try:
        fields = parse_protobuf_fields(data)
        secs = None
        for fn, wt, val in fields:
            if fn == 1 and wt == 0:
                secs = val
                break
        if secs is not None and 1000000000 < secs < 3000000000:
            return datetime.fromtimestamp(secs, tz=timezone.utc).isoformat()
    except Exception:
        pass
    return None


def extract_conversation_db(
    db_path: Path,
) -> Optional[Tuple[Dict[str, Any], List[Dict[str, Any]], List[Dict[str, Any]], List[Dict[str, Any]]]]:
    """Parses a native Antigravity conversation database into telemetry tuples.

    Returns:
        (session_row, step_rows, tool_calls_extracted, interventions_extracted) or None if invalid.
    """
    if not db_path.exists() or not db_path.is_file():
        return None

    try:
        raw_size = db_path.stat().st_size
    except Exception:
        return None

    try:
        conn = sqlite3.connect(db_path)
        cur = conn.cursor()

        # Check required tables
        cur.execute("SELECT name FROM sqlite_master WHERE type='table'")
        tables = {r[0] for r in cur.fetchall()}
        if "steps" not in tables:
            conn.close()
            return None

        # 1. Parse trajectory_meta
        trajectory_id = ""
        cascade_id = ""
        if "trajectory_meta" in tables:
            cur.execute("SELECT trajectory_id, cascade_id FROM trajectory_meta LIMIT 1")
            meta_row = cur.fetchone()
            if meta_row:
                trajectory_id = meta_row[0] or ""
                cascade_id = meta_row[1] or ""

        # Default session_id is cascade_id, fallback to trajectory_id, fallback to filename stem
        session_id = cascade_id or trajectory_id or db_path.stem

        # 2. Parse trajectory_metadata_blob
        workspace_detected = ""
        meta_start_time = None
        if "trajectory_metadata_blob" in tables:
            cur.execute("SELECT data FROM trajectory_metadata_blob WHERE id='main' LIMIT 1")
            blob_row = cur.fetchone()
            if blob_row and blob_row[0]:
                for fn, wt, val in parse_protobuf_fields(blob_row[0]):
                    if fn == 2 and wt == 2:
                        meta_start_time = parse_proto_timestamp(val)
                    elif fn == 18 and wt == 2:
                        try:
                            workspace_detected = val.decode("utf-8", errors="replace")
                        except Exception:
                            pass

        # 3. Model detection from executor_metadata or steps
        model_detected = "Gemini 3.5/Flash/Pro (Default)"
        if "executor_metadata" in tables:
            cur.execute("SELECT data FROM executor_metadata WHERE data IS NOT NULL")
            for (ex_data,) in cur.fetchall():
                if isinstance(ex_data, bytes):
                    ex_str = ex_data.decode("latin1", errors="replace")
                    m = re.search(r"(gemini-[a-zA-Z0-9.\-_]+|gpt-[a-zA-Z0-9.\-_]+)", ex_str, re.IGNORECASE)
                    if m:
                        model_detected = m.group(1).strip()
                        break

        # 4. Fetch all steps
        cur.execute("""
            SELECT idx, step_type, status, metadata, error_details, step_payload
            FROM steps
            ORDER BY idx ASC
        """)
        raw_steps = cur.fetchall()
        conn.close()
    except Exception as exc:
        sys.stderr.write(f"Warning: Failed to read conversation db {db_path}: {exc}\n")
        return None

    if not raw_steps:
        # DB exists but has 0 steps
        session_row = {
            "session_id": session_id,
            "start_time": meta_start_time,
            "end_time": meta_start_time,
            "duration_seconds": 0.0,
            "total_steps": 0,
            "model": model_detected,
            "workspace_path": workspace_detected,
            "transcript_path": str(db_path),
            "file_size_bytes": raw_size,
            "has_errors": 0,
            "tool_call_count": 0,
            "tool_error_count": 0,
            "intervention_count": 0,
            "origin_developer": "local",
            "remote_synced_at": None,
        }
        return session_row, [], [], []

    step_rows: List[Dict[str, Any]] = []
    tool_calls_extracted: List[Dict[str, Any]] = []
    interventions_extracted: List[Dict[str, Any]] = []

    has_errors = False
    tool_error_count = 0
    recent_tool_failed = False
    recent_tool_name = ""
    recent_error_snippet = ""

    last_tool_sig = None
    repeated_tool_count = 0

    first_step_time = None
    last_step_time = None

    for idx, step_type, status_val, metadata_bytes, error_bytes, payload_bytes in raw_steps:
        created_at = None
        tool_name = ""
        tool_args: Dict[str, Any] = {}
        tool_args_str = ""
        tool_start_ts = None
        tool_end_ts = None

        # Parse metadata protobuf
        if metadata_bytes and isinstance(metadata_bytes, bytes):
            m_fields = parse_protobuf_fields(metadata_bytes)
            for fn, wt, val in m_fields:
                if fn == 1 and wt == 2:
                    created_at = parse_proto_timestamp(val)
                elif fn == 4 and wt == 2:
                    sub_fields = parse_protobuf_fields(val)
                    sub_dict = {sfn: sval for sfn, swt, sval in sub_fields}
                    if 2 in sub_dict and isinstance(sub_dict[2], bytes):
                        tool_name = sub_dict[2].decode("utf-8", errors="replace")
                    if 3 in sub_dict and isinstance(sub_dict[3], bytes):
                        tool_args_str = sub_dict[3].decode("utf-8", errors="replace")
                        try:
                            tool_args = json.loads(tool_args_str)
                        except Exception:
                            tool_args = {}
                elif fn in (6, 7) and wt == 2 and not tool_start_ts:
                    tool_start_ts = parse_proto_timestamp(val)
                elif fn in (8, 22, 32) and wt == 2:
                    tool_end_ts = parse_proto_timestamp(val)

        if not created_at and meta_start_time:
            created_at = meta_start_time

        if created_at:
            if not first_step_time:
                first_step_time = created_at
            last_step_time = created_at

        # Parse step payload
        content_text = ""
        thinking_text = ""
        tool_output_text = ""
        tool_exit_code = 0

        if payload_bytes and isinstance(payload_bytes, bytes):
            p_fields = parse_protobuf_fields(payload_bytes)
            for fn, wt, val in p_fields:
                if fn == 19 and wt == 2:  # User prompt field
                    sub_fields = parse_protobuf_fields(val)
                    for sfn, swt, sval in sub_fields:
                        if sfn == 2 and isinstance(sval, bytes):
                            content_text = sval.decode("utf-8", errors="replace")
                elif fn == 20 and wt == 2:  # Agent thought / output field
                    sub_fields = parse_protobuf_fields(val)
                    for sfn, swt, sval in sub_fields:
                        if sfn == 3 and isinstance(sval, bytes):
                            msg = sval.decode("utf-8", errors="replace")
                            content_text = msg
                            if msg.startswith("**") and "**" in msg[2:]:
                                thinking_text = msg[: msg.find("**", 2) + 2]
                elif fn == 28 and wt == 2:  # Tool execution payload (e.g. run_command)
                    sub_fields = parse_protobuf_fields(val)
                    for sfn, swt, sval in sub_fields:
                        if sfn == 6 and swt == 0:
                            tool_exit_code = sval
                        elif sfn == 21 and isinstance(sval, bytes):
                            tool_output_text = sval.decode("utf-8", errors="replace")
                        elif sfn == 2 and isinstance(sval, bytes) and not workspace_detected:
                            cwd_val = sval.decode("utf-8", errors="replace")
                            if "/Dev/" in cwd_val:
                                workspace_detected = cwd_val

        # Check errors
        err_snippet = ""
        if error_bytes and isinstance(error_bytes, bytes):
            err_snippet = error_bytes.decode("utf-8", errors="replace")
            err_snippet = re.sub(r"[\x00-\x1f]+", " ", err_snippet).strip()

        # Step type & source classification
        s_type = "UNKNOWN"
        source = "SYSTEM"
        s_status = "DONE"

        if status_val == 7 or err_snippet:
            s_status = "ERROR"
        elif status_val == 2:
            s_status = "IN_PROGRESS"
        elif status_val == 3:
            s_status = "DONE"

        if step_type == 14 or (content_text and not tool_name and s_status != "ERROR" and idx == 0):
            s_type = "USER_INPUT"
            source = "USER"
        elif step_type == 15:
            s_type = "AGENT_OUTPUT"
            source = "MODEL"
        elif tool_name or step_type in (5, 8, 9, 21, 132):
            s_type = f"TOOL_CALL:{tool_name}" if tool_name else "TOOL_CALL"
            source = "TOOL"
        elif step_type == 98:
            s_type = "CONTEXT"
            source = "SYSTEM"

        # Record step row
        step_rows.append({
            "session_id": session_id,
            "step_index": idx,
            "step_type": s_type,
            "source": source,
            "status": s_status,
            "created_at": created_at,
            "content_length": len(content_text),
            "content_snippet": content_text[:200] if content_text else None,
            "has_thinking": 1 if thinking_text else 0,
            "thinking_length": len(thinking_text),
            "tool_count": 1 if tool_name else 0,
        })

        # Process user intervention
        if s_type == "USER_INPUT" and content_text:
            clean_prompt = re.sub(
                r"<USER_REQUEST>|\</USER_REQUEST\>|<ADDITIONAL_METADATA>[\s\S]*?</ADDITIONAL_METADATA>",
                "",
                content_text,
            ).strip()
            if clean_prompt:
                itype = classify_intervention(clean_prompt, recent_tool_failed)
                interventions_extracted.append({
                    "session_id": session_id,
                    "step_index": idx,
                    "created_at": created_at,
                    "prompt_text": clean_prompt,
                    "prompt_length": len(clean_prompt),
                    "preceding_tool_failed": 1 if recent_tool_failed else 0,
                    "preceding_tool_name": recent_tool_name,
                    "preceding_error_snippet": recent_error_snippet[:500],
                    "intervention_type": itype,
                })

        # Process tool calls
        if tool_name:
            target_path = (
                tool_args.get("TargetFile")
                or tool_args.get("AbsolutePath")
                or tool_args.get("SearchPath")
                or tool_args.get("DirectoryPath")
            )
            cmd_line = tool_args.get("CommandLine")

            tool_sig = (tool_name, str(target_path or cmd_line or tool_args_str))
            is_loop = 0
            if tool_sig == last_tool_sig:
                repeated_tool_count += 1
                if repeated_tool_count >= 2:
                    is_loop = 1
            else:
                last_tool_sig = tool_sig
                repeated_tool_count = 1

            t_status = "SUCCESS"
            if s_status == "ERROR" or err_snippet or tool_exit_code != 0:
                t_status = "FAILED" if tool_exit_code != 0 else "ERROR"
                has_errors = True
                tool_error_count += 1
                recent_tool_failed = True
                recent_tool_name = tool_name
                recent_error_snippet = err_snippet or f"Exited with code {tool_exit_code}"
            else:
                recent_tool_failed = False
                recent_tool_name = ""
                recent_error_snippet = ""

            t_dur = calculate_duration(tool_start_ts, tool_end_ts)

            out_len = len(tool_output_text) if tool_output_text else 0
            out_lines = (tool_output_text.count("\n") + 1) if tool_output_text else 0
            args_len = len(tool_args_str) if tool_args_str else 0
            cmd_cat = classify_command(cmd_line) if cmd_line else None

            tool_calls_extracted.append({
                "session_id": session_id,
                "step_index": idx,
                "result_step_index": idx + 1,
                "tool_name": tool_name,
                "arguments_json": tool_args_str,
                "arguments_snippet": tool_args_str[:250],
                "target_path": str(target_path) if target_path else None,
                "command_line": str(cmd_line) if cmd_line else None,
                "started_at": tool_start_ts or created_at,
                "completed_at": tool_end_ts or created_at,
                "duration_seconds": t_dur,
                "status": t_status,
                "exit_code": tool_exit_code,
                "error_snippet": err_snippet[:800],
                "is_loop_candidate": is_loop,
                "output_length_chars": out_len,
                "output_lines": out_lines,
                "arguments_length_chars": args_len,
                "command_category": cmd_cat,
                "is_truncated": 1 if "<truncated" in tool_output_text else 0,
            })

    # Finalize session durations
    start_time = first_step_time or meta_start_time
    end_time = last_step_time or start_time
    duration_s = calculate_duration(start_time, end_time) or 0.0

    session_row = {
        "session_id": session_id,
        "start_time": start_time,
        "end_time": end_time,
        "duration_seconds": duration_s,
        "total_steps": len(step_rows),
        "model": model_detected,
        "workspace_path": workspace_detected,
        "transcript_path": str(db_path),
        "file_size_bytes": raw_size,
        "has_errors": 1 if has_errors else 0,
        "tool_call_count": len(tool_calls_extracted),
        "tool_error_count": tool_error_count,
        "intervention_count": len(interventions_extracted),
        "origin_developer": "local",
        "remote_synced_at": None,
    }

    return session_row, step_rows, tool_calls_extracted, interventions_extracted


def harvest_conversation_db(db_path: Path, target_db: Path) -> Dict[str, Any]:
    """Ingests a single conversation DB into target_db (telemetry.db)."""
    target_db.parent.mkdir(parents=True, exist_ok=True)
    res = extract_conversation_db(db_path)
    if not res:
        return {"status": "skipped", "file": str(db_path)}

    session_row, step_rows, tool_rows, interv_rows = res
    s_id = session_row["session_id"]

    conn = sqlite3.connect(target_db)
    cur = conn.cursor()
    cur.executescript(SCHEMA_SQL)
    ensure_volume_columns(conn)
    ensure_sync_columns(conn)

    # Ensure idempotence by deleting previous session records
    cur.execute("DELETE FROM steps WHERE session_id = ?", (s_id,))
    cur.execute("DELETE FROM tool_calls WHERE session_id = ?", (s_id,))
    cur.execute("DELETE FROM user_interventions WHERE session_id = ?", (s_id,))

    cur.execute("""
        INSERT OR REPLACE INTO sessions (
            session_id, start_time, end_time, duration_seconds, total_steps,
            model, workspace_path, transcript_path, file_size_bytes, has_errors,
            tool_call_count, tool_error_count, intervention_count,
            origin_developer, remote_synced_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        session_row["session_id"],
        session_row["start_time"],
        session_row["end_time"],
        session_row["duration_seconds"],
        session_row["total_steps"],
        session_row["model"],
        session_row["workspace_path"],
        session_row["transcript_path"],
        session_row["file_size_bytes"],
        session_row["has_errors"],
        session_row["tool_call_count"],
        session_row["tool_error_count"],
        session_row["intervention_count"],
        session_row["origin_developer"],
        session_row["remote_synced_at"],
    ))

    if step_rows:
        cur.executemany("""
            INSERT INTO steps (
                session_id, step_index, step_type, source, status, created_at,
                content_length, content_snippet, has_thinking, thinking_length, tool_count
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, [
            (
                s["session_id"],
                s["step_index"],
                s["step_type"],
                s["source"],
                s["status"],
                s["created_at"],
                s["content_length"],
                s["content_snippet"],
                s["has_thinking"],
                s["thinking_length"],
                s["tool_count"],
            )
            for s in step_rows
        ])

    if tool_rows:
        cur.executemany("""
            INSERT INTO tool_calls (
                session_id, step_index, result_step_index, tool_name, arguments_json,
                arguments_snippet, target_path, command_line, started_at, completed_at,
                duration_seconds, status, exit_code, error_snippet, is_loop_candidate,
                output_length_chars, output_lines, arguments_length_chars, command_category, is_truncated
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, [
            (
                t["session_id"],
                t["step_index"],
                t["result_step_index"],
                t["tool_name"],
                t["arguments_json"],
                t["arguments_snippet"],
                t["target_path"],
                t["command_line"],
                t["started_at"],
                t["completed_at"],
                t["duration_seconds"],
                t["status"],
                t["exit_code"],
                t["error_snippet"],
                t["is_loop_candidate"],
                t["output_length_chars"],
                t["output_lines"],
                t["arguments_length_chars"],
                t["command_category"],
                t["is_truncated"],
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
                u["session_id"],
                u["step_index"],
                u["created_at"],
                u["prompt_text"],
                u["prompt_length"],
                u["preceding_tool_failed"],
                u["preceding_tool_name"],
                u["preceding_error_snippet"],
                u["intervention_type"],
            )
            for u in interv_rows
        ])

    conn.commit()
    conn.close()

    return {
        "status": "harvested",
        "session_id": s_id,
        "total_steps": len(step_rows),
        "tool_call_count": len(tool_rows),
        "tool_error_count": session_row["tool_error_count"],
        "intervention_count": len(interv_rows),
        "duration_seconds": session_row["duration_seconds"],
    }


def harvest_all_conversations(conv_dir: Path, target_db: Path) -> int:
    """Discovers and ingests all conversation DBs from conv_dir into target_db."""
    if not conv_dir.exists() or not conv_dir.is_dir():
        return 0

    db_files = sorted(conv_dir.glob("*.db"), key=lambda p: os.path.getmtime(p), reverse=True)
    harvested = 0
    for p in db_files:
        res = harvest_conversation_db(p, target_db)
        if res.get("status") == "harvested":
            harvested += 1

    return harvested


def main(argv: Optional[List[str]] = None) -> None:
    parser = argparse.ArgumentParser(description="Harvest Antigravity SQLite conversation DBs into telemetry.db.")
    parser.add_argument("--db", default="data/telemetry.db", help="Path to SQLite telemetry database")
    parser.add_argument(
        "--conv-dir",
        default=str(Path.home() / ".gemini" / "antigravity" / "conversations"),
        help="Path to conversations directory containing .db files",
    )
    args = parser.parse_args(argv)

    conv_dir = Path(args.conv_dir)
    target_db = Path(args.db)

    print(f"[*] Scanning conversation databases in {conv_dir}...")
    t0 = time.time()
    count = harvest_all_conversations(conv_dir, target_db)
    dt = time.time() - t0
    print(f"[✓] Harvested {count} conversation databases into {target_db} in {dt:.2f}s")


if __name__ == "__main__":
    main()
