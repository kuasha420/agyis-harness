#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Arafat Zahan (@kuasha420)
# Corporate Stewardship & Infrastructure: Purrfect Software Limited (PSL)
# Governed by: ICARO-42/b Ordinance (Company-Supported Personal IP Framework)

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


from harness.telemetry.db import get_db_connection
from harness.telemetry.extractor import (
    SCHEMA_SQL,
    calculate_duration,
    classify_command,
    classify_intervention,
    ensure_sync_columns,
    ensure_telemetry_schema,
    ensure_volume_columns,
    extract_session,
    parse_iso_ts,
    upsert_session_telemetry,
)


def extract_and_store(paths: List[Path], db_path: Path) -> int:
    """Ingests transcript JSONLs and conversation SQLite DBs into db_path."""
    from pipeline.harvest_conversations import harvest_conversation_db

    conn = get_db_connection(db_path, row_factory=False)
    ensure_telemetry_schema(conn)
    conn.close()

    stored = 0
    for p in paths:
        if p.suffix == ".db":
            res = harvest_conversation_db(p, db_path)
            if res.get("status") == "harvested":
                stored += 1
        elif p.suffix == ".jsonl":
            res = extract_session(p)
            if not res:
                continue
            session_row, step_rows, tool_rows, interv_rows = res
            conn = get_db_connection(db_path, row_factory=False)
            try:
                upsert_session_telemetry(conn, session_row, step_rows, tool_rows, interv_rows)
                stored += 1
            finally:
                conn.close()
    return stored


def _canon_args_key(ajson: Optional[str], asnip: Optional[str], cmd_line: Optional[str]) -> str:
    raw = ajson or asnip or cmd_line or ""
    if not raw:
        return ""
    for parser in (json.loads,):
        try:
            d = parser(raw)
            if isinstance(d, dict):
                cleaned = {k: v for k, v in d.items() if k not in ("toolAction", "toolSummary")}
                return json.dumps(cleaned, sort_keys=True, ensure_ascii=False)[:160]
        except (json.JSONDecodeError, ValueError, TypeError):
            pass
    return re.sub(r"\s+", "", str(raw))[:120]


def _match_extracted_pending_rows(
    pending_rows: List[Tuple[Any, ...]],
    extracted_tools: List[Dict[str, Any]],
) -> Dict[int, Dict[str, Any]]:
    """Matches pending DB rows to extracted tools by running strict tiers in the outer loop."""
    prep_pending = [(row, _canon_args_key(row[4], row[5], row[6])) for row in pending_rows]
    prep_ext = [
        (idx, t, _canon_args_key(t.get("arguments_json"), t.get("arguments_snippet"), t.get("command_line")))
        for idx, t in enumerate(extracted_tools)
    ]
    matched_by_id: Dict[int, Dict[str, Any]] = {}
    used_indices: set[int] = set()
    tiers = (
        lambda sidx, ridx, tname, db_c, t, t_c: t.get("step_index") == sidx and ridx is not None and t.get("result_step_index") == ridx and t.get("tool_name") == tname and bool(db_c) and t_c == db_c,
        lambda sidx, ridx, tname, db_c, t, t_c: t.get("step_index") == sidx and ridx is not None and t.get("result_step_index") == ridx and t.get("tool_name") == tname,
        lambda sidx, ridx, tname, db_c, t, t_c: t.get("step_index") == sidx and t.get("tool_name") == tname and bool(db_c) and t_c == db_c,
        lambda sidx, ridx, tname, db_c, t, t_c: t.get("step_index") == sidx and t.get("tool_name") == tname,
    )
    for pred in tiers:
        for db_row, db_canon in prep_pending:
            row_id, sidx, ridx, tname = db_row[0], db_row[1], db_row[2], db_row[3]
            if row_id in matched_by_id:
                continue
            for idx, t, t_canon in prep_ext:
                if idx in used_indices:
                    continue
                if pred(sidx, ridx, tname, db_canon, t, t_canon):
                    used_indices.add(idx)
                    matched_by_id[row_id] = t
                    break
    return matched_by_id


def backfill_tool_volumes(db_path: Path, verbose: bool = True) -> Dict[str, int]:
    """Backfills output_length_chars, output_lines, arguments_length_chars, command_category,
    and is_truncated for all existing rows in tool_calls that lack volume data without clobbering parallel calls.
    """
    from pipeline.harvest_conversations import extract_conversation_db

    conn = get_db_connection(db_path, row_factory=False)
    ensure_telemetry_schema(conn)
    cur = conn.cursor()

    cur.execute("SELECT COUNT(*) FROM tool_calls WHERE output_length_chars IS NULL")
    unpopulated_count = cur.fetchone()[0]
    if unpopulated_count == 0:
        if verbose:
            print("[✓] All tool calls already have volume metrics populated.")
        conn.close()
        return {"updated_tool_calls": 0, "sessions_processed": 0}

    cur.execute("""
        SELECT DISTINCT s.session_id, s.transcript_path
        FROM sessions s
        JOIN tool_calls t ON s.session_id = t.session_id
        WHERE t.output_length_chars IS NULL
    """)
    target_sessions = cur.fetchall()

    if verbose:
        print(f"[*] Backfilling volume metrics for {unpopulated_count} tool calls across {len(target_sessions)} sessions...")

    total_updated = 0
    sessions_processed = 0
    user_home = str(Path.home())

    for s_id, t_path_str in target_sessions:
        cur.execute(
            """
            SELECT id, step_index, result_step_index, tool_name, arguments_json, arguments_snippet, command_line
            FROM tool_calls
            WHERE session_id = ? AND output_length_chars IS NULL
            ORDER BY step_index, id
            """,
            (s_id,),
        )
        pending_rows = cur.fetchall()
        if not pending_rows:
            continue

        extracted_tools: Optional[List[Dict[str, Any]]] = None
        if t_path_str:
            t_path = Path(str(t_path_str).replace("[USER_HOME]", user_home))
            if t_path.is_file():
                res = extract_conversation_db(t_path) if t_path.suffix == ".db" else extract_session(t_path)
                if res:
                    extracted_tools = res[2]

        updates = []
        if extracted_tools is not None:
            matched_map = _match_extracted_pending_rows(pending_rows, extracted_tools)
            for db_row in pending_rows:
                matched = matched_map.get(db_row[0])
                if matched is not None:
                    updates.append((
                        matched.get("output_length_chars", 0),
                        matched.get("output_lines", 0),
                        matched.get("arguments_length_chars", 0),
                        matched.get("command_category"),
                        matched.get("is_truncated", 0),
                        db_row[0],
                    ))
                else:
                    updates.append((0, 0, 0, classify_command(db_row[6]), 0, db_row[0]))
        else:
            for db_row in pending_rows:
                updates.append((0, 0, 0, classify_command(db_row[6]), 0, db_row[0]))

        if updates:
            cur.executemany(
                """
                UPDATE tool_calls
                SET output_length_chars=?, output_lines=?, arguments_length_chars=?, command_category=?, is_truncated=?
                WHERE id=?
                """,
                updates,
            )
            total_updated += len(updates)
            sessions_processed += 1

        if verbose and (sessions_processed % 50 == 0 or sessions_processed == len(target_sessions)):
            conn.commit()
            print(f"  ... processed {sessions_processed}/{len(target_sessions)} sessions ({total_updated} tool calls updated)")

    conn.commit()
    conn.close()
    if verbose:
        print(f"[✓] Backfill complete: updated {total_updated} tool calls across {sessions_processed} sessions.")
    return {"updated_tool_calls": total_updated, "sessions_processed": sessions_processed}


def main(argv: Optional[List[str]] = None) -> None:
    parser = argparse.ArgumentParser(description="Harvest Antigravity transcripts into SQLite.")
    parser.add_argument("--db", default="data/telemetry.db", help="Path to SQLite database")
    parser.add_argument("--limit", type=int, default=None, help="Limit number of sessions processed")
    parser.add_argument("--reset", action="store_true", help="Reset/rebuild database tables")
    parser.add_argument("--backfill-volumes", action="store_true", help="Backfill character volume metrics on existing database")
    parser.add_argument(
        "--conv-dir",
        default=None,
        help="Path to conversations directory containing .db files (default: IDE and CLI dirs)",
    )
    args = parser.parse_args(argv)

    db_path = Path(args.db)
    db_path.parent.mkdir(parents=True, exist_ok=True)

    if args.reset and db_path.exists():
        db_path.unlink()

    conn = get_db_connection(db_path, row_factory=False)
    ensure_telemetry_schema(conn)
    conn.commit()

    if args.backfill_volumes:
        conn.close()
        backfill_tool_volumes(db_path, verbose=True)
        return

    from harness.telemetry.db import iter_brain_transcripts

    transcript_paths = [
        str(p)
        for _, p, _, _ in sorted(iter_brain_transcripts(), key=lambda item: item[2], reverse=True)
    ]

    if args.limit:
        transcript_paths = transcript_paths[:args.limit]

    print(f"[*] Found {len(transcript_paths)} session transcripts to harvest.")
    t0 = time.time()

    total_sessions = 0
    total_steps = 0
    total_tools = 0
    total_interventions = 0
    total_tool_errors = 0

    for i, p_str in enumerate(transcript_paths, 1):
        res = extract_session(Path(p_str))
        if not res:
            continue
        session_row, step_rows, tool_rows, interv_rows = res
        upsert_session_telemetry(conn, session_row, step_rows, tool_rows, interv_rows, commit=False)

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

    from pipeline.harvest_conversations import get_default_conversation_dirs, harvest_all_conversations
    conv_dirs = [Path(args.conv_dir)] if getattr(args, "conv_dir", None) else get_default_conversation_dirs()
    existing_conv_dirs = [d for d in conv_dirs if d.exists() and d.is_dir()]
    if existing_conv_dirs:
        print(f"[*] Harvesting conversation DBs from {', '.join(str(d) for d in existing_conv_dirs)}...")
        conv_cnt = harvest_all_conversations(existing_conv_dirs, db_path)
        print(f"[✓] Harvested {conv_cnt} conversation databases into {db_path}")

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
