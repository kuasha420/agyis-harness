# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Arafat Zahan (@kuasha420)
# Corporate Stewardship & Infrastructure: Purrfect Software Limited (PSL)
# Governed by: ICARO-42/b Ordinance (Company-Supported Personal IP Framework)

"""
Centralized SQLite database connection factory for PSL Telemetry (ADR-014, ADR-030).
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path
import sqlite3
from typing import Any, Dict, Optional, Union


def get_db_connection(
    db_file: Union[str, Path],
    timeout: float = 30.0,
    row_factory: bool = True,
) -> sqlite3.Connection:
    """Connect to SQLite database with WAL mode, busy timeout, and integrity invariants.

    Parameters:
        db_file: Path to SQLite database file
        timeout: SQLite connection timeout in seconds (default: 30.0)
        row_factory: Whether to set conn.row_factory to sqlite3.Row (default: True)
    """
    path_str = str(db_file)
    if path_str != ":memory:":
        Path(path_str).parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path_str, timeout=timeout)
    if row_factory:
        conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode = WAL")
    conn.execute(f"PRAGMA busy_timeout = {int(timeout * 1000)}")
    conn.execute("PRAGMA synchronous = NORMAL")
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def prune_historical_tool_arguments(
    db_target: Union[str, Path, sqlite3.Connection],
    days: int = 90,
    dry_run: bool = False,
    reference_time: Optional[datetime] = None,
) -> Dict[str, Any]:
    """Compacts historical telemetry by pruning raw argument strings for old sessions (Issue #56).

    Prunes verbose arguments_json and arguments_snippet for tool calls belonging to sessions
    completed older than <days> ago, preserving session totals, tool names, error statuses,
    execution timestamps, and aggregate character counters. Executes VACUUM post-pruning
    to reclaim physical disk space.

    Parameters:
        db_target: Path to SQLite database file or active sqlite3.Connection
        days: Historical days retention threshold (default: 90)
        dry_run: If True, previews row and byte counts without modifying DB
        reference_time: Optional anchor datetime for deterministic time comparisons (default: now UTC)

    Returns:
        Dictionary summarizing pruning and disk compaction statistics.
    """
    import os

    if reference_time is None:
        reference_time = datetime.now(timezone.utc)
    elif reference_time.tzinfo is None:
        reference_time = reference_time.replace(tzinfo=timezone.utc)

    cutoff_dt = reference_time - timedelta(days=days)
    cutoff_iso = cutoff_dt.strftime("%Y-%m-%dT%H:%M:%SZ")

    is_conn = isinstance(db_target, sqlite3.Connection)
    is_memory = False
    size_before_bytes = 0
    path_str = ""

    if is_conn:
        conn = db_target
    else:
        path_str = str(db_target)
        is_memory = path_str == ":memory:"
        if not is_memory and Path(path_str).exists():
            size_before_bytes = os.path.getsize(path_str)
        conn = get_db_connection(db_target, row_factory=False)

    try:
        cur = conn.cursor()

        # Check for sessions and tool_calls tables
        cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name IN ('sessions', 'tool_calls')")
        existing_tables = {row[0] for row in cur.fetchall()}
        if "sessions" not in existing_tables or "tool_calls" not in existing_tables:
            return {
                "dry_run": dry_run,
                "days": days,
                "cutoff_iso": cutoff_iso,
                "sessions_affected": 0,
                "rows_affected": 0,
                "bytes_pruned": 0,
                "size_before_bytes": size_before_bytes,
                "size_after_bytes": size_before_bytes,
                "disk_bytes_reclaimed": 0,
                "vacuum_executed": False,
            }

        cur.execute("PRAGMA table_info(tool_calls)")
        tc_cols = {row[1] for row in cur.fetchall()}
        has_args_json = "arguments_json" in tc_cols
        has_args_snippet = "arguments_snippet" in tc_cols

        if not has_args_json and not has_args_snippet:
            return {
                "dry_run": dry_run,
                "days": days,
                "cutoff_iso": cutoff_iso,
                "sessions_affected": 0,
                "rows_affected": 0,
                "bytes_pruned": 0,
                "size_before_bytes": size_before_bytes,
                "size_after_bytes": size_before_bytes,
                "disk_bytes_reclaimed": 0,
                "vacuum_executed": False,
            }

        # Build column clauses dynamically
        clause_parts = []
        len_parts = []
        update_clause_parts = []
        if has_args_json:
            clause_parts.append("tc.arguments_json IS NOT NULL")
            update_clause_parts.append("arguments_json IS NOT NULL")
            len_parts.append("LENGTH(COALESCE(tc.arguments_json, ''))")
        if has_args_snippet:
            clause_parts.append("tc.arguments_snippet IS NOT NULL")
            update_clause_parts.append("arguments_snippet IS NOT NULL")
            len_parts.append("LENGTH(COALESCE(tc.arguments_snippet, ''))")

        where_cond = " OR ".join(clause_parts)
        update_where_cond = " OR ".join(update_clause_parts)
        sum_expr = " + ".join(len_parts)

        stats_sql = f"""
            SELECT
                COUNT(DISTINCT tc.session_id) AS sessions_count,
                COUNT(tc.id) AS rows_count,
                COALESCE(SUM({sum_expr}), 0) AS bytes_pruned
            FROM tool_calls tc
            JOIN sessions s ON tc.session_id = s.session_id
            WHERE datetime(COALESCE(s.end_time, s.start_time)) < datetime(?)
              AND ({where_cond})
        """
        cur.execute(stats_sql, (cutoff_iso,))
        stats = cur.fetchone()
        sessions_affected = stats[0] or 0
        rows_affected = stats[1] or 0
        bytes_pruned = stats[2] or 0

        vacuum_executed = False
        if not dry_run and rows_affected > 0:
            set_parts = []
            if has_args_json:
                set_parts.append("arguments_json = NULL")
            if has_args_snippet:
                set_parts.append("arguments_snippet = NULL")
            set_sql = ", ".join(set_parts)

            update_sql = f"""
                UPDATE tool_calls
                SET {set_sql}
                WHERE ({update_where_cond})
                  AND session_id IN (
                      SELECT session_id FROM sessions
                      WHERE datetime(COALESCE(end_time, start_time)) < datetime(?)
                  )
            """
            cur.execute(update_sql, (cutoff_iso,))
            conn.commit()


            conn.execute("VACUUM")
            conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
            vacuum_executed = True

    finally:
        if not is_conn:
            conn.close()

    size_after_bytes = size_before_bytes
    if not is_conn and not is_memory and Path(path_str).exists():
        size_after_bytes = os.path.getsize(path_str)

    disk_bytes_reclaimed = max(0, size_before_bytes - size_after_bytes) if not dry_run else 0

    return {
        "dry_run": dry_run,
        "days": days,
        "cutoff_iso": cutoff_iso,
        "sessions_affected": sessions_affected,
        "rows_affected": rows_affected,
        "bytes_pruned": bytes_pruned,
        "size_before_bytes": size_before_bytes,
        "size_after_bytes": size_after_bytes,
        "disk_bytes_reclaimed": disk_bytes_reclaimed,
        "vacuum_executed": vacuum_executed,
    }

