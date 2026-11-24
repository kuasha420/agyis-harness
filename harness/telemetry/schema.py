# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Arafat Zahan (@kuasha420)
# Corporate Stewardship & Infrastructure: Purrfect Software Limited (PSL)
# Governed by: ICARO-42/b Ordinance (Company-Supported Personal IP Framework)

"""
Hermetic SQLite Database Schema Definition for PSL Telemetry (ADR-014 / ADR-030).

Provides self-contained table and index DDL for sessions, steps,
tool_calls, and user_interventions without any dependencies on pipeline/.
"""

from __future__ import annotations

import importlib.resources
import sqlite3


def _load_schema_sql() -> str:
    """Loads canonical telemetry DDL from externalized SQL asset (PSL-INV-008)."""
    return (
        importlib.resources.files("harness.telemetry.assets")
        .joinpath("schema.sql")
        .read_text(encoding="utf-8")
    )


SCHEMA_SQL = _load_schema_sql()


def init_db(conn: sqlite3.Connection) -> None:
    """Initializes tables and indexes on a connection."""
    cur = conn.cursor()
    cur.executescript(SCHEMA_SQL)
    conn.commit()


def ensure_sync_columns(conn: sqlite3.Connection) -> None:
    """Non-destructively ensures sync & federation columns exist on sessions table."""
    cur = conn.cursor()
    cur.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='sessions'")
    if not cur.fetchone():
        cur.executescript(SCHEMA_SQL)
        conn.commit()
        return

    cur.execute("PRAGMA table_info(sessions)")
    existing_cols = {row[1] for row in cur.fetchall()}

    new_cols = [
        ("origin_developer", "TEXT DEFAULT 'local'"),
        ("remote_synced_at", "TEXT DEFAULT NULL"),
    ]
    for col_name, col_type in new_cols:
        if col_name not in existing_cols:
            try:
                cur.execute(f"ALTER TABLE sessions ADD COLUMN {col_name} {col_type}")
            except sqlite3.OperationalError:
                pass

    cur.execute("CREATE INDEX IF NOT EXISTS idx_sessions_origin ON sessions(origin_developer)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_sessions_synced ON sessions(remote_synced_at)")

    cur.execute("SELECT name FROM sqlite_master WHERE type='table'")
    existing_tables = {row[0] for row in cur.fetchall()}

    cur.execute("SELECT name FROM sqlite_master WHERE type='index'")
    existing_indexes = {row[0] for row in cur.fetchall()}

    if "steps" in existing_tables and "idx_steps_uniq" not in existing_indexes:
        cur.execute("DELETE FROM steps WHERE id NOT IN (SELECT MIN(id) FROM steps GROUP BY session_id, step_index)")
        cur.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_steps_uniq ON steps(session_id, step_index)")

    if "user_interventions" in existing_tables and "idx_interventions_uniq" not in existing_indexes:
        cur.execute("DELETE FROM user_interventions WHERE id NOT IN (SELECT MIN(id) FROM user_interventions GROUP BY session_id, step_index)")
        cur.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_interventions_uniq ON user_interventions(session_id, step_index)")

    if "tool_calls" in existing_tables and "idx_tool_calls_uniq" not in existing_indexes:
        cur.execute("DELETE FROM tool_calls WHERE id NOT IN (SELECT MIN(id) FROM tool_calls GROUP BY session_id, step_index, tool_name, started_at, arguments_snippet)")
        cur.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_tool_calls_uniq ON tool_calls(session_id, step_index, tool_name, started_at, arguments_snippet)")

    conn.commit()

