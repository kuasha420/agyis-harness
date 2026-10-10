# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Purrfect Software Limited (PSL)

"""
Hermetic SQLite Database Schema Definition for PSL Telemetry (ADR-014 / ADR-030).

Provides self-contained table and index DDL for sessions, steps,
tool_calls, and user_interventions without any dependencies on pipeline/.
"""

from __future__ import annotations

import sqlite3

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
    intervention_count INTEGER,
    origin_developer TEXT DEFAULT 'local',
    remote_synced_at TEXT DEFAULT NULL
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
    output_length_chars INTEGER,
    output_lines INTEGER,
    arguments_length_chars INTEGER,
    command_category TEXT,
    is_truncated INTEGER DEFAULT 0,
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
CREATE INDEX IF NOT EXISTS idx_tools_category ON tool_calls(command_category);
CREATE INDEX IF NOT EXISTS idx_tools_output_len ON tool_calls(output_length_chars);
CREATE INDEX IF NOT EXISTS idx_interventions_session ON user_interventions(session_id);
CREATE INDEX IF NOT EXISTS idx_interventions_type ON user_interventions(intervention_type);
CREATE INDEX IF NOT EXISTS idx_sessions_origin ON sessions(origin_developer);
CREATE INDEX IF NOT EXISTS idx_sessions_synced ON sessions(remote_synced_at);
"""


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
            cur.execute(f"ALTER TABLE sessions ADD COLUMN {col_name} {col_type}")

    cur.execute("CREATE INDEX IF NOT EXISTS idx_sessions_origin ON sessions(origin_developer)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_sessions_synced ON sessions(remote_synced_at)")
    conn.commit()
