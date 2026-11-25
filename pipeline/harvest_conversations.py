#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Arafat Zahan (@kuasha420)
# Corporate Stewardship & Infrastructure: Purrfect Software Limited (PSL)
# Governed by: ICARO-42/b Ordinance (Company-Supported Personal IP Framework)

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
import logging
import os
from pathlib import Path
import re
import sqlite3
import sys
import time
from typing import Any, Dict, Iterable, List, Optional, Tuple, Union

_logger = logging.getLogger(__name__)

from harness.telemetry.config import infer_client_surface, resolve_machine_id
from harness.telemetry.db import get_db_connection
from harness.telemetry.extractor import (
    SCHEMA_SQL,
    calculate_duration,
    classify_command,
    classify_intervention,
    ensure_sync_columns,
    ensure_telemetry_schema,
    ensure_volume_columns,
    parse_iso_ts,
    upsert_session_telemetry,
)
from harness.telemetry.models import normalize_model, normalize_utc_iso
from harness.telemetry.sibling_db import read_sibling_gen_metadata
from harness.trajectory.protobuf import extract_tool_from_protobuf


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
        except (ValueError, IndexError, TypeError) as exc:
            _logger.debug("Protobuf field parse halted at offset %d: %s", offset, exc)
            break
    return fields


def parse_proto_timestamp(data: bytes) -> Optional[str]:
    """Extracts a UTC ISO 8601 ('...Z') timestamp from a google.protobuf.Timestamp message."""
    try:
        fields = parse_protobuf_fields(data)
        secs = None
        for fn, wt, val in fields:
            if fn == 1 and wt == 0:
                secs = val
                break
        if secs is not None and 1000000000 < secs < 3000000000:
            return normalize_utc_iso(datetime.fromtimestamp(secs, tz=timezone.utc).isoformat())
    except (ValueError, OverflowError, OSError, TypeError) as exc:
        _logger.debug("Invalid proto timestamp bytes: %s", exc)
    return None


def extract_execution_result(step_payload_bytes: bytes) -> Tuple[int, str]:
    """
    Decodes tool execution result and exit code from Antigravity protobuf payload.
    Supports modern Antigravity format (fn 140 -> sfn 2 -> ssfn 1) with regex extraction
    of exit codes, while maintaining backward-compatible fallback to legacy fn 28.
    """
    if not step_payload_bytes or not isinstance(step_payload_bytes, bytes):
        return 0, ""

    try:
        fields = {fn: val for fn, wt, val in parse_protobuf_fields(step_payload_bytes)}

        # Check modern Antigravity payload (fn 140 -> sfn 2 -> ssfn 1)
        if 140 in fields and isinstance(fields[140], bytes):
            subfields = {fn: val for fn, wt, val in parse_protobuf_fields(fields[140])}
            if 2 in subfields and isinstance(subfields[2], bytes):
                ssubfields = {fn: val for fn, wt, val in parse_protobuf_fields(subfields[2])}
                if 1 in ssubfields and isinstance(ssubfields[1], bytes):
                    raw_text = ssubfields[1].decode("utf-8", errors="replace")
                    # Extract: "The command exited with code <N>." or "Command exited with code <N>"
                    match = re.search(r"(?:The\s+)?[Cc]ommand exited with code (\d+)", raw_text)
                    exit_code = int(match.group(1)) if match else 0
                    return exit_code, raw_text

        # Fallback to legacy Antigravity payload (fn 28)
        if 28 in fields and isinstance(fields[28], bytes):
            subfields = {fn: val for fn, wt, val in parse_protobuf_fields(fields[28])}
            exit_code = subfields.get(6, 0)
            output_val = subfields.get(21, b"")
            output = output_val.decode("utf-8", errors="replace") if isinstance(output_val, bytes) else str(output_val)
            return exit_code, output
    except (ValueError, TypeError, AttributeError) as exc:
        _logger.debug("Failed decoding execution result payload: %s", exc)

    return 0, ""


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
    except OSError as exc:
        _logger.warning("Cannot stat conversation db %s: %s", db_path, exc)
        return None

    conn: Optional[sqlite3.Connection] = None
    try:
        conn = sqlite3.connect(f"file:{db_path.resolve()}?mode=ro", uri=True, timeout=0.5)
        conn.execute("PRAGMA query_only = ON")
        cur = conn.cursor()

        # Check required tables
        cur.execute("SELECT name FROM sqlite_master WHERE type='table'")
        tables = {r[0] for r in cur.fetchall()}
        if "steps" not in tables:
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
                    elif fn == 18 and wt == 2 and isinstance(val, bytes):
                        cand_ws = val.decode("utf-8", errors="replace")
                        if "/" in cand_ws or cand_ws.startswith("file://"):
                            workspace_detected = cand_ws

        # 3. Model detection from gen_metadata (protobuf) first, then executor_metadata (never fallback to Default)
        exec_model = ""
        if "executor_metadata" in tables:
            cur.execute("SELECT data FROM executor_metadata WHERE data IS NOT NULL ORDER BY rowid DESC")
            for (ex_data,) in cur.fetchall():
                if isinstance(ex_data, bytes):
                    ex_str = ex_data.decode("latin1", errors="replace")
                    m = re.search(
                        r"(gemini-[a-zA-Z0-9.\-_]+|gpt-[a-zA-Z0-9.\-_]+|claude-[a-zA-Z0-9.\-_]+)",
                        ex_str,
                        re.IGNORECASE,
                    )
                    if m:
                        cand = m.group(1).strip().rstrip(".-_")
                        info = normalize_model(cand)
                        if info.attribution_status == "attributed":
                            exec_model = cand
                            break

        # 4. Fetch all steps
        cur.execute("""
            SELECT idx, step_type, status, metadata, error_details, step_payload
            FROM steps
            ORDER BY idx ASC
        """)
        raw_steps = cur.fetchall()
    except Exception as exc:
        sys.stderr.write(f"Warning: Failed to read conversation db {db_path}: {exc}\n")
        return None
    finally:
        if conn is not None:
            conn.close()

    gen_meta = read_sibling_gen_metadata(db_path)
    model_slug = gen_meta.get("model_slug")
    model_display_name = gen_meta.get("model_display_name")
    model_detected = model_slug or model_display_name or exec_model or "Unknown"
    norm_model = normalize_model(model_detected, model_slug=model_slug, model_display_name=model_display_name)
    if norm_model.attribution_status == "unattributed_legacy":
        model_detected = "Unknown"
    if not model_slug and norm_model.attribution_status == "attributed":
        model_slug = model_detected if (" " not in model_detected and "(" not in model_detected) else norm_model.canonical_model
    if not model_display_name and model_detected != "Unknown" and (" " in model_detected or "(" in model_detected):
        model_display_name = model_detected

    meta_start_time = normalize_utc_iso(meta_start_time)
    base_meta = {
        "origin_machine": resolve_machine_id(workspace_detected or None),
        "client_surface": infer_client_surface(db_path),
        "source_kind": "sqlite_db",
        "model_slug": model_slug,
        "model_display_name": model_display_name,
        "max_context_tokens": gen_meta.get("max_context_tokens") or norm_model.context_window_tokens,
        "total_input_tokens": gen_meta.get("total_input_tokens"),
        "total_cache_read_tokens": gen_meta.get("total_cache_read_tokens"),
        "total_output_tokens": gen_meta.get("total_output_tokens"),
        "total_thought_tokens": gen_meta.get("total_thought_tokens"),
        "peak_context_tokens": gen_meta.get("peak_context_tokens"),
    }

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
            **base_meta,
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

        # Parse metadata protobuf (fn=1 created_at, fn=29 modified_tool_call > fn=4 tool_call, fn=6/7/8/22/32 ts)
        if metadata_bytes and isinstance(metadata_bytes, bytes):
            m_fields = parse_protobuf_fields(metadata_bytes)
            for fn, wt, val in m_fields:
                if fn == 1 and wt == 2:
                    created_at = parse_proto_timestamp(val)
                elif fn in (6, 7) and wt == 2 and not tool_start_ts:
                    tool_start_ts = parse_proto_timestamp(val)
                elif fn in (8, 22, 32) and wt == 2:
                    tool_end_ts = parse_proto_timestamp(val)
            pb_tname, pb_targs_str = extract_tool_from_protobuf(metadata_bytes)
            if pb_tname:
                tool_name = pb_tname
                tool_args_str = pb_targs_str
                if tool_args_str:
                    try:
                        parsed_args = json.loads(tool_args_str)
                        if isinstance(parsed_args, dict):
                            tool_args = parsed_args
                    except (json.JSONDecodeError, TypeError) as exc:
                        _logger.debug("Invalid tool args JSON at step %s in %s: %s", idx, db_path, exc)
                        tool_args = {}

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
            tool_exit_code, tool_output_text = extract_execution_result(payload_bytes)
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
                        if sfn == 2 and isinstance(sval, bytes) and not workspace_detected:
                            cwd_val = sval.decode("utf-8", errors="replace").strip()
                            if (
                                (cwd_val.startswith("/") or cwd_val.startswith("file://") or bool(re.match(r"^[A-Za-z]:[/\\]", cwd_val)))
                                and len(cwd_val) > 1
                                and "\n" not in cwd_val
                                and "\r" not in cwd_val
                            ):
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

        if step_type == 14:
            s_type = "USER_INPUT"
            source = "USER"
        elif step_type == 15:
            s_type = "AGENT_OUTPUT"
            source = "MODEL"
        elif step_type == 23:
            s_type = "CHECKPOINT"
            source = "SYSTEM"
        elif step_type == 90:
            s_type = "EPHEMERAL_MESSAGE"
            source = "SYSTEM"
        elif step_type == 101:
            s_type = "SYSTEM_MESSAGE"
            source = "SYSTEM"
        elif step_type == 17:
            s_type = "TASK_BOUNDARY"
            source = "SYSTEM"
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
                tool_args.get("Path")
                or tool_args.get("TargetFile")
                or tool_args.get("AbsolutePath")
                or tool_args.get("FilePath")
                or tool_args.get("Target")
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
    start_time = normalize_utc_iso(first_step_time or meta_start_time)
    end_time = normalize_utc_iso(last_step_time or start_time)
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
        **base_meta,
    }

    return session_row, step_rows, tool_calls_extracted, interventions_extracted


def harvest_conversation_db(db_path: Path, target_db: Path) -> Dict[str, Any]:
    """Ingests a single conversation DB into target_db without clobbering richer .jsonl transcripts."""
    target_db.parent.mkdir(parents=True, exist_ok=True)
    res = extract_conversation_db(db_path)
    if not res:
        return {"status": "skipped", "file": str(db_path)}

    session_row, step_rows, tool_rows, interv_rows = res
    s_id = session_row["session_id"]

    conn = get_db_connection(target_db, row_factory=False)
    try:
        ensure_telemetry_schema(conn)
        cur = conn.cursor()
        cur.execute("SELECT source_kind, transcript_path FROM sessions WHERE session_id = ?", (s_id,))
        existing = cur.fetchone()
        was_richer = bool(
            existing and (
                existing[0] in ("transcript_full", "transcript")
                or str(existing[1] or "").lower().endswith(".jsonl")
            )
        )
        upsert_session_telemetry(conn, session_row, step_rows, tool_rows, interv_rows, commit=True)
    finally:
        conn.close()

    return {
        "status": "enriched" if was_richer else "harvested",
        "session_id": s_id,
        "total_steps": len(step_rows),
        "tool_call_count": len(tool_rows),
        "tool_error_count": session_row["tool_error_count"],
        "intervention_count": len(interv_rows),
        "duration_seconds": session_row["duration_seconds"],
    }


def get_default_conversation_dirs() -> List[Path]:
    """Returns ordered IDE and CLI Antigravity conversation directories (respecting explicit env overrides)."""
    from harness.utils.context import get_app_data_dir_candidates

    env_dir = (
        os.environ.get("AGYIS_CONVERSATIONS_DIR")
        or os.environ.get("ANTIGRAVITY_CONVERSATIONS_DIR")
        or os.environ.get("GEMINI_CONVERSATIONS_DIR")
    )
    if env_dir and env_dir.strip():
        return [Path(env_dir.strip()).expanduser()]
    return [app_dir / "conversations" for app_dir in get_app_data_dir_candidates()]


def harvest_all_conversations(
    conv_dir: Optional[Union[Path, Iterable[Path]]],
    target_db: Path,
) -> int:
    """Discovers and ingests all conversation DBs from conv_dir (or IDE+CLI defaults) into target_db."""
    if conv_dir is None:
        dirs = get_default_conversation_dirs()
    elif isinstance(conv_dir, (str, Path)):
        dirs = [Path(conv_dir)]
    else:
        dirs = [Path(d) for d in conv_dir]

    db_files: List[Path] = []
    for d in dirs:
        if d.exists() and d.is_dir():
            db_files.extend(d.glob("*.db"))
    if not db_files:
        return 0

    db_files.sort(key=lambda p: os.path.getmtime(p), reverse=True)
    harvested = 0
    for p in db_files:
        res = harvest_conversation_db(p, target_db)
        if res.get("status") in ("harvested", "enriched"):
            harvested += 1
    return harvested


def main(argv: Optional[List[str]] = None) -> None:
    parser = argparse.ArgumentParser(description="Harvest Antigravity SQLite conversation DBs into telemetry.db.")
    parser.add_argument("--db", default="data/telemetry.db", help="Path to SQLite telemetry database")
    parser.add_argument(
        "--conv-dir",
        default=None,
        help="Path to conversations directory containing .db files (default: both IDE and CLI dirs)",
    )
    args = parser.parse_args(argv)

    conv_dirs: Optional[Union[Path, List[Path]]] = Path(args.conv_dir) if args.conv_dir else None
    target_db = Path(args.db)

    desc = str(conv_dirs) if conv_dirs else ", ".join(str(d) for d in get_default_conversation_dirs())
    print(f"[*] Scanning conversation databases in {desc}...")
    t0 = time.time()
    count = harvest_all_conversations(conv_dirs, target_db)
    dt = time.time() - t0
    print(f"[✓] Harvested {count} conversation databases into {target_db} in {dt:.2f}s")


if __name__ == "__main__":
    main()
