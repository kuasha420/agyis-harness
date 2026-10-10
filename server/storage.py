"""
Storage Abstraction Layer for PSL Telemetry Hub (ADR-030).

Provides a dual-engine database abstraction supporting SQLite (for hermetic testing
and local workstation development) and PostgreSQL (for production VPS deployment).
Idempotently initializes schemas, indexes, and handles upserts and delta queries.
"""

from __future__ import annotations

from datetime import datetime, timezone
import os
from pathlib import Path
import sqlite3
import threading
from typing import Any, Dict, List, Optional, Union

# Dual-engine DDL
SQLITE_SCHEMA_SQL = """
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
    status TEXT,
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
    intervention_type TEXT,
    FOREIGN KEY(session_id) REFERENCES sessions(session_id)
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_steps_uniq ON steps(session_id, step_index);
CREATE UNIQUE INDEX IF NOT EXISTS idx_interventions_uniq ON user_interventions(session_id, step_index);
CREATE UNIQUE INDEX IF NOT EXISTS idx_tool_calls_uniq ON tool_calls(session_id, step_index, tool_name, started_at, arguments_snippet);
CREATE INDEX IF NOT EXISTS idx_sessions_origin ON sessions(origin_developer);
CREATE INDEX IF NOT EXISTS idx_sessions_synced ON sessions(remote_synced_at);
CREATE INDEX IF NOT EXISTS idx_steps_session ON steps(session_id);
CREATE INDEX IF NOT EXISTS idx_tools_session ON tool_calls(session_id);
CREATE INDEX IF NOT EXISTS idx_interventions_session ON user_interventions(session_id);
"""

POSTGRES_SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS sessions (
    session_id TEXT PRIMARY KEY,
    start_time TEXT,
    end_time TEXT,
    duration_seconds DOUBLE PRECISION,
    total_steps INTEGER,
    model TEXT,
    workspace_path TEXT,
    transcript_path TEXT,
    file_size_bytes BIGINT,
    has_errors INTEGER,
    tool_call_count INTEGER,
    tool_error_count INTEGER,
    intervention_count INTEGER,
    origin_developer TEXT DEFAULT 'local',
    remote_synced_at TEXT DEFAULT NULL
);

CREATE TABLE IF NOT EXISTS steps (
    id SERIAL PRIMARY KEY,
    session_id TEXT REFERENCES sessions(session_id),
    step_index INTEGER,
    step_type TEXT,
    source TEXT,
    status TEXT,
    created_at TEXT,
    content_length INTEGER,
    content_snippet TEXT,
    has_thinking INTEGER,
    thinking_length INTEGER,
    tool_count INTEGER
);

CREATE TABLE IF NOT EXISTS tool_calls (
    id SERIAL PRIMARY KEY,
    session_id TEXT REFERENCES sessions(session_id),
    step_index INTEGER,
    result_step_index INTEGER,
    tool_name TEXT,
    arguments_json TEXT,
    arguments_snippet TEXT,
    target_path TEXT,
    command_line TEXT,
    started_at TEXT,
    completed_at TEXT,
    duration_seconds DOUBLE PRECISION,
    status TEXT,
    exit_code INTEGER,
    error_snippet TEXT,
    is_loop_candidate INTEGER DEFAULT 0,
    output_length_chars INTEGER,
    output_lines INTEGER,
    arguments_length_chars INTEGER,
    command_category TEXT,
    is_truncated INTEGER DEFAULT 0
);

CREATE TABLE IF NOT EXISTS user_interventions (
    id SERIAL PRIMARY KEY,
    session_id TEXT REFERENCES sessions(session_id),
    step_index INTEGER,
    created_at TEXT,
    prompt_text TEXT,
    prompt_length INTEGER,
    preceding_tool_failed INTEGER,
    preceding_tool_name TEXT,
    preceding_error_snippet TEXT,
    intervention_type TEXT
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_steps_uniq ON steps(session_id, step_index);
CREATE UNIQUE INDEX IF NOT EXISTS idx_interventions_uniq ON user_interventions(session_id, step_index);
CREATE UNIQUE INDEX IF NOT EXISTS idx_tool_calls_uniq ON tool_calls(session_id, step_index, tool_name, started_at, arguments_snippet);
CREATE INDEX IF NOT EXISTS idx_sessions_origin ON sessions(origin_developer);
CREATE INDEX IF NOT EXISTS idx_sessions_synced ON sessions(remote_synced_at);
CREATE INDEX IF NOT EXISTS idx_steps_session ON steps(session_id);
CREATE INDEX IF NOT EXISTS idx_tools_session ON tool_calls(session_id);
CREATE INDEX IF NOT EXISTS idx_interventions_session ON user_interventions(session_id);
"""


class Storage:
    """Database storage engine supporting SQLite and PostgreSQL."""

    def __init__(self, database_url: Optional[str] = None):
        self.url = database_url or os.environ.get("DATABASE_URL") or "sqlite:///data/telemetry_hub.db"
        self.is_postgres = self.url.startswith("postgresql://") or self.url.startswith("postgres://")
        self._lock = threading.Lock()
        self._sqlite_mem_conn: Optional[sqlite3.Connection] = None
        self._pg_conn = None

        if not self.is_postgres:
            self._init_sqlite_path()
        self.init_db()

    def _init_sqlite_path(self) -> None:
        if self.url.startswith("sqlite:///"):
            self.sqlite_path = self.url[len("sqlite:///"):]
        elif self.url.startswith("sqlite://"):
            self.sqlite_path = self.url[len("sqlite://"):]
        else:
            self.sqlite_path = self.url

        if self.sqlite_path != ":memory:":
            p = Path(self.sqlite_path)
            p.parent.mkdir(parents=True, exist_ok=True)

    def close(self) -> None:
        """Closes any persistent database connections."""
        with self._lock:
            if self._sqlite_mem_conn is not None:
                self._sqlite_mem_conn.close()
                self._sqlite_mem_conn = None
            if self._pg_conn is not None:
                self._pg_conn.close()
                self._pg_conn = None

    def _get_sqlite_conn(self) -> sqlite3.Connection:
        if self.sqlite_path == ":memory:":
            if self._sqlite_mem_conn is None:
                self._sqlite_mem_conn = sqlite3.connect(":memory:", check_same_thread=False)
                self._sqlite_mem_conn.row_factory = sqlite3.Row
            return self._sqlite_mem_conn

        conn = sqlite3.connect(self.sqlite_path, timeout=30.0)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA synchronous=NORMAL")
        return conn

    def _get_pg_conn(self):
        try:
            import psycopg
            return psycopg.connect(self.url)
        except ImportError:
            try:
                import psycopg2
                return psycopg2.connect(self.url)
            except ImportError as exc:
                raise RuntimeError(
                    "PostgreSQL driver (psycopg or psycopg2) not installed."
                ) from exc

    def init_db(self) -> None:
        """Idempotently initializes schemas and indexes."""
        with self._lock:
            if self.is_postgres:
                conn = self._get_pg_conn()
                try:
                    with conn.cursor() as cur:
                        cur.execute(POSTGRES_SCHEMA_SQL)
                    conn.commit()
                finally:
                    conn.close()
            else:
                conn = self._get_sqlite_conn()
                try:
                    conn.executescript(SQLITE_SCHEMA_SQL)
                    conn.commit()
                finally:
                    if self.sqlite_path != ":memory:":
                        conn.close()

    def ping(self) -> bool:
        """Health check probe verifying database connectivity."""
        try:
            with self._lock:
                if self.is_postgres:
                    conn = self._get_pg_conn()
                    try:
                        with conn.cursor() as cur:
                            cur.execute("SELECT 1")
                            _ = cur.fetchone()
                        return True
                    finally:
                        conn.close()
                else:
                    conn = self._get_sqlite_conn()
                    try:
                        cur = conn.cursor()
                        cur.execute("SELECT 1")
                        _ = cur.fetchone()
                        return True
                    finally:
                        if self.sqlite_path != ":memory:":
                            conn.close()
        except Exception:
            return False

    def upsert_batch(
        self,
        sessions: List[Dict[str, Any]],
        steps: List[Dict[str, Any]],
        tool_calls: List[Dict[str, Any]],
        user_interventions: List[Dict[str, Any]],
        requesting_user: str,
    ) -> Dict[str, int]:
        """Upserts sessions and idempotently inserts steps, tool calls, and user interventions.

        Sets origin_developer = requesting_user if not set, and updates remote_synced_at.
        """
        now_iso = datetime.now(timezone.utc).isoformat()

        # Sanitize session fields & set origin_developer / remote_synced_at
        sanitized_sessions: List[Dict[str, Any]] = []
        for s in sessions:
            s_copy = dict(s)
            if not s_copy.get("origin_developer") or s_copy.get("origin_developer") == "local":
                s_copy["origin_developer"] = requesting_user
            s_copy["remote_synced_at"] = now_iso
            sanitized_sessions.append(s_copy)

        with self._lock:
            if self.is_postgres:
                return self._upsert_batch_pg(
                    sanitized_sessions, steps, tool_calls, user_interventions
                )
            else:
                return self._upsert_batch_sqlite(
                    sanitized_sessions, steps, tool_calls, user_interventions
                )

    def _upsert_batch_sqlite(
        self,
        sessions: List[Dict[str, Any]],
        steps: List[Dict[str, Any]],
        tool_calls: List[Dict[str, Any]],
        user_interventions: List[Dict[str, Any]],
    ) -> Dict[str, int]:
        conn = self._get_sqlite_conn()
        try:
            cur = conn.cursor()

            # 1. Upsert sessions
            upsert_session_sql = """
                INSERT INTO sessions (
                    session_id, start_time, end_time, duration_seconds, total_steps,
                    model, workspace_path, transcript_path, file_size_bytes, has_errors,
                    tool_call_count, tool_error_count, intervention_count,
                    origin_developer, remote_synced_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(session_id) DO UPDATE SET
                    start_time = COALESCE(excluded.start_time, sessions.start_time),
                    end_time = COALESCE(excluded.end_time, sessions.end_time),
                    duration_seconds = COALESCE(excluded.duration_seconds, sessions.duration_seconds),
                    total_steps = COALESCE(excluded.total_steps, sessions.total_steps),
                    model = COALESCE(excluded.model, sessions.model),
                    workspace_path = COALESCE(excluded.workspace_path, sessions.workspace_path),
                    transcript_path = COALESCE(excluded.transcript_path, sessions.transcript_path),
                    file_size_bytes = COALESCE(excluded.file_size_bytes, sessions.file_size_bytes),
                    has_errors = COALESCE(excluded.has_errors, sessions.has_errors),
                    tool_call_count = COALESCE(excluded.tool_call_count, sessions.tool_call_count),
                    tool_error_count = COALESCE(excluded.tool_error_count, sessions.tool_error_count),
                    intervention_count = COALESCE(excluded.intervention_count, sessions.intervention_count),
                    origin_developer = COALESCE(sessions.origin_developer, excluded.origin_developer),
                    remote_synced_at = excluded.remote_synced_at
            """
            for s in sessions:
                cur.execute(upsert_session_sql, (
                    s.get("session_id"), s.get("start_time"), s.get("end_time"),
                    s.get("duration_seconds"), s.get("total_steps"), s.get("model"),
                    s.get("workspace_path"), s.get("transcript_path"), s.get("file_size_bytes"),
                    s.get("has_errors"), s.get("tool_call_count"), s.get("tool_error_count"),
                    s.get("intervention_count"), s.get("origin_developer"), s.get("remote_synced_at"),
                ))

            # 2. Insert steps (idempotent)
            insert_step_sql = """
                INSERT OR IGNORE INTO steps (
                    session_id, step_index, step_type, source, status, created_at,
                    content_length, content_snippet, has_thinking, thinking_length, tool_count
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """
            steps_inserted = 0
            for st in steps:
                cur.execute(insert_step_sql, (
                    st.get("session_id"), st.get("step_index"), st.get("step_type"),
                    st.get("source"), st.get("status"), st.get("created_at"),
                    st.get("content_length"), st.get("content_snippet"),
                    st.get("has_thinking"), st.get("thinking_length"), st.get("tool_count"),
                ))
                if cur.rowcount > 0:
                    steps_inserted += 1

            # 3. Insert tool_calls (idempotent)
            insert_tool_sql = """
                INSERT OR IGNORE INTO tool_calls (
                    session_id, step_index, result_step_index, tool_name, arguments_json,
                    arguments_snippet, target_path, command_line, started_at, completed_at,
                    duration_seconds, status, exit_code, error_snippet, is_loop_candidate,
                    output_length_chars, output_lines, arguments_length_chars, command_category, is_truncated
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """
            tools_inserted = 0
            for tc in tool_calls:
                cur.execute(insert_tool_sql, (
                    tc.get("session_id"), tc.get("step_index"), tc.get("result_step_index"),
                    tc.get("tool_name"), tc.get("arguments_json"), tc.get("arguments_snippet"),
                    tc.get("target_path"), tc.get("command_line"), tc.get("started_at"),
                    tc.get("completed_at"), tc.get("duration_seconds"), tc.get("status"),
                    tc.get("exit_code"), tc.get("error_snippet"), tc.get("is_loop_candidate", 0),
                    tc.get("output_length_chars", 0), tc.get("output_lines", 0),
                    tc.get("arguments_length_chars", 0), tc.get("command_category"),
                    tc.get("is_truncated", 0),
                ))
                if cur.rowcount > 0:
                    tools_inserted += 1

            # 4. Insert user_interventions (idempotent)
            insert_interv_sql = """
                INSERT OR IGNORE INTO user_interventions (
                    session_id, step_index, created_at, prompt_text, prompt_length,
                    preceding_tool_failed, preceding_tool_name, preceding_error_snippet, intervention_type
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """
            intervs_inserted = 0
            for ui in user_interventions:
                cur.execute(insert_interv_sql, (
                    ui.get("session_id"), ui.get("step_index"), ui.get("created_at"),
                    ui.get("prompt_text"), ui.get("prompt_length"),
                    ui.get("preceding_tool_failed"), ui.get("preceding_tool_name"),
                    ui.get("preceding_error_snippet"), ui.get("intervention_type"),
                ))
                if cur.rowcount > 0:
                    intervs_inserted += 1

            conn.commit()
            return {
                "sessions_upserted": len(sessions),
                "steps_inserted": steps_inserted,
                "tool_calls_inserted": tools_inserted,
                "user_interventions_inserted": intervs_inserted,
            }
        finally:
            if self.sqlite_path != ":memory:":
                conn.close()

    def _upsert_batch_pg(
        self,
        sessions: List[Dict[str, Any]],
        steps: List[Dict[str, Any]],
        tool_calls: List[Dict[str, Any]],
        user_interventions: List[Dict[str, Any]],
    ) -> Dict[str, int]:
        def _strip_nul(obj: Any) -> Any:
            if isinstance(obj, str):
                return obj.replace("\x00", "")
            if isinstance(obj, dict):
                return {k: _strip_nul(v) for k, v in obj.items()}
            if isinstance(obj, list):
                return [_strip_nul(v) for v in obj]
            return obj

        sessions = [_strip_nul(s) for s in sessions]
        steps = [_strip_nul(st) for st in steps]
        tool_calls = [_strip_nul(tc) for tc in tool_calls]
        user_interventions = [_strip_nul(ui) for ui in user_interventions]

        conn = self._get_pg_conn()
        try:
            with conn.cursor() as cur:
                upsert_session_sql = """
                    INSERT INTO sessions (
                        session_id, start_time, end_time, duration_seconds, total_steps,
                        model, workspace_path, transcript_path, file_size_bytes, has_errors,
                        tool_call_count, tool_error_count, intervention_count,
                        origin_developer, remote_synced_at
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    ON CONFLICT(session_id) DO UPDATE SET
                        start_time = COALESCE(EXCLUDED.start_time, sessions.start_time),
                        end_time = COALESCE(EXCLUDED.end_time, sessions.end_time),
                        duration_seconds = COALESCE(EXCLUDED.duration_seconds, sessions.duration_seconds),
                        total_steps = COALESCE(EXCLUDED.total_steps, sessions.total_steps),
                        model = COALESCE(EXCLUDED.model, sessions.model),
                        workspace_path = COALESCE(EXCLUDED.workspace_path, sessions.workspace_path),
                        transcript_path = COALESCE(EXCLUDED.transcript_path, sessions.transcript_path),
                        file_size_bytes = COALESCE(EXCLUDED.file_size_bytes, sessions.file_size_bytes),
                        has_errors = COALESCE(EXCLUDED.has_errors, sessions.has_errors),
                        tool_call_count = COALESCE(EXCLUDED.tool_call_count, sessions.tool_call_count),
                        tool_error_count = COALESCE(EXCLUDED.tool_error_count, sessions.tool_error_count),
                        intervention_count = COALESCE(EXCLUDED.intervention_count, sessions.intervention_count),
                        origin_developer = COALESCE(sessions.origin_developer, EXCLUDED.origin_developer),
                        remote_synced_at = EXCLUDED.remote_synced_at
                """
                for s in sessions:
                    cur.execute(upsert_session_sql, (
                        s.get("session_id"), s.get("start_time"), s.get("end_time"),
                        s.get("duration_seconds"), s.get("total_steps"), s.get("model"),
                        s.get("workspace_path"), s.get("transcript_path"), s.get("file_size_bytes"),
                        s.get("has_errors"), s.get("tool_call_count"), s.get("tool_error_count"),
                        s.get("intervention_count"), s.get("origin_developer"), s.get("remote_synced_at"),
                    ))

                insert_step_sql = """
                    INSERT INTO steps (
                        session_id, step_index, step_type, source, status, created_at,
                        content_length, content_snippet, has_thinking, thinking_length, tool_count
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    ON CONFLICT (session_id, step_index) DO NOTHING
                """
                steps_inserted = 0
                for st in steps:
                    cur.execute(insert_step_sql, (
                        st.get("session_id"), st.get("step_index"), st.get("step_type"),
                        st.get("source"), st.get("status"), st.get("created_at"),
                        st.get("content_length"), st.get("content_snippet"),
                        st.get("has_thinking"), st.get("thinking_length"), st.get("tool_count"),
                    ))
                    if cur.rowcount > 0:
                        steps_inserted += 1

                insert_tool_sql = """
                    INSERT INTO tool_calls (
                        session_id, step_index, result_step_index, tool_name, arguments_json,
                        arguments_snippet, target_path, command_line, started_at, completed_at,
                        duration_seconds, status, exit_code, error_snippet, is_loop_candidate,
                        output_length_chars, output_lines, arguments_length_chars, command_category, is_truncated
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    ON CONFLICT (session_id, step_index, tool_name, started_at, arguments_snippet) DO NOTHING
                """
                tools_inserted = 0
                for tc in tool_calls:
                    cur.execute(insert_tool_sql, (
                        tc.get("session_id"), tc.get("step_index"), tc.get("result_step_index"),
                        tc.get("tool_name"), tc.get("arguments_json"), tc.get("arguments_snippet"),
                        tc.get("target_path"), tc.get("command_line"), tc.get("started_at"),
                        tc.get("completed_at"), tc.get("duration_seconds"), tc.get("status"),
                        tc.get("exit_code"), tc.get("error_snippet"), tc.get("is_loop_candidate", 0),
                        tc.get("output_length_chars", 0), tc.get("output_lines", 0),
                        tc.get("arguments_length_chars", 0), tc.get("command_category"),
                        tc.get("is_truncated", 0),
                    ))
                    if cur.rowcount > 0:
                        tools_inserted += 1

                insert_interv_sql = """
                    INSERT INTO user_interventions (
                        session_id, step_index, created_at, prompt_text, prompt_length,
                        preceding_tool_failed, preceding_tool_name, preceding_error_snippet, intervention_type
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                    ON CONFLICT (session_id, step_index) DO NOTHING
                """
                intervs_inserted = 0
                for ui in user_interventions:
                    cur.execute(insert_interv_sql, (
                        ui.get("session_id"), ui.get("step_index"), ui.get("created_at"),
                        ui.get("prompt_text"), ui.get("prompt_length"),
                        ui.get("preceding_tool_failed"), ui.get("preceding_tool_name"),
                        ui.get("preceding_error_snippet"), ui.get("intervention_type"),
                    ))
                    if cur.rowcount > 0:
                        intervs_inserted += 1

            conn.commit()
            return {
                "sessions_upserted": len(sessions),
                "steps_inserted": steps_inserted,
                "tool_calls_inserted": tools_inserted,
                "user_interventions_inserted": intervs_inserted,
            }
        finally:
            conn.close()

    def query_delta(
        self,
        since: str,
        requesting_user: Optional[str] = None,
        limit: int = 100,
        all_developers: bool = False,
        developer: Optional[str] = None,
        offset: int = 0,
    ) -> Dict[str, Any]:
        """Queries telemetry delta since watermark, applying anti-echo filter for requesting_user unless all_developers is True."""
        with self._lock:
            if self.is_postgres:
                return self._query_delta_pg(
                    since, requesting_user, limit, all_developers, developer, offset
                )
            else:
                return self._query_delta_sqlite(
                    since, requesting_user, limit, all_developers, developer, offset
                )

    def _query_delta_sqlite(
        self,
        since: str,
        requesting_user: Optional[str] = None,
        limit: int = 100,
        all_developers: bool = False,
        developer: Optional[str] = None,
        offset: int = 0,
    ) -> Dict[str, Any]:
        conn = self._get_sqlite_conn()
        try:
            cur = conn.cursor()

            query = (
                "SELECT * FROM sessions "
                "WHERE ((remote_synced_at IS NOT NULL AND remote_synced_at > ?) "
                "    OR (start_time IS NOT NULL AND start_time > ?))"
            )
            params: List[Any] = [since, since]

            if developer:
                if developer != "*":
                    query += " AND origin_developer = ?"
                    params.append(developer)
            elif not all_developers and requesting_user:
                query += " AND (origin_developer IS NULL OR origin_developer != ?)"
                params.append(requesting_user)

            count_query = f"SELECT COUNT(*) FROM ({query})"
            cur.execute(count_query, params)
            total_matching = cur.fetchone()[0]

            query += " ORDER BY start_time ASC LIMIT ? OFFSET ?"
            params.extend([limit, offset])

            cur.execute(query, params)
            sessions = [dict(r) for r in cur.fetchall()]

            if not sessions:
                return {
                    "sessions": [],
                    "steps": [],
                    "tool_calls": [],
                    "user_interventions": [],
                    "total_matching": total_matching,
                    "has_more": False,
                }

            session_ids = [s["session_id"] for s in sessions]
            placeholders = ",".join(["?"] * len(session_ids))

            cur.execute(
                f"SELECT * FROM steps WHERE session_id IN ({placeholders}) ORDER BY session_id, step_index ASC",
                session_ids,
            )
            steps = [dict(r) for r in cur.fetchall()]

            cur.execute(
                f"SELECT * FROM tool_calls WHERE session_id IN ({placeholders}) ORDER BY session_id, step_index ASC",
                session_ids,
            )
            tool_calls = [dict(r) for r in cur.fetchall()]

            cur.execute(
                f"SELECT * FROM user_interventions WHERE session_id IN ({placeholders}) ORDER BY session_id, step_index ASC",
                session_ids,
            )
            interventions = [dict(r) for r in cur.fetchall()]

            return {
                "sessions": sessions,
                "steps": steps,
                "tool_calls": tool_calls,
                "user_interventions": interventions,
                "total_matching": total_matching,
                "has_more": (offset + len(sessions)) < total_matching,
            }
        finally:
            if self.sqlite_path != ":memory:":
                conn.close()

    def _query_delta_pg(
        self,
        since: str,
        requesting_user: Optional[str] = None,
        limit: int = 100,
        all_developers: bool = False,
        developer: Optional[str] = None,
        offset: int = 0,
    ) -> Dict[str, Any]:
        conn = self._get_pg_conn()
        try:
            with conn.cursor() as cur:
                query = (
                    "SELECT * FROM sessions "
                    "WHERE ((remote_synced_at IS NOT NULL AND remote_synced_at > %s) "
                    "    OR (start_time IS NOT NULL AND start_time > %s))"
                )
                params: List[Any] = [since, since]

                if developer:
                    if developer != "*":
                        query += " AND origin_developer = %s"
                        params.append(developer)
                elif not all_developers and requesting_user:
                    query += " AND (origin_developer IS NULL OR origin_developer != %s)"
                    params.append(requesting_user)

                count_query = f"SELECT COUNT(*) FROM ({query}) AS matching_sessions"
                cur.execute(count_query, params)
                total_matching = cur.fetchone()[0]

                query += " ORDER BY start_time ASC LIMIT %s OFFSET %s"
                params.extend([limit, offset])

                cur.execute(query, params)
                columns = [desc[0] for desc in cur.description]
                sessions = [dict(zip(columns, row)) for row in cur.fetchall()]

                if not sessions:
                    return {
                        "sessions": [],
                        "steps": [],
                        "tool_calls": [],
                        "user_interventions": [],
                        "total_matching": total_matching,
                        "has_more": False,
                    }

                session_ids = [s["session_id"] for s in sessions]
                placeholders = ",".join(["%s"] * len(session_ids))

                cur.execute(
                    f"SELECT * FROM steps WHERE session_id IN ({placeholders}) ORDER BY session_id, step_index ASC",
                    session_ids,
                )
                columns_st = [desc[0] for desc in cur.description]
                steps = [dict(zip(columns_st, row)) for row in cur.fetchall()]

                cur.execute(
                    f"SELECT * FROM tool_calls WHERE session_id IN ({placeholders}) ORDER BY session_id, step_index ASC",
                    session_ids,
                )
                columns_tc = [desc[0] for desc in cur.description]
                tool_calls = [dict(zip(columns_tc, row)) for row in cur.fetchall()]

                cur.execute(
                    f"SELECT * FROM user_interventions WHERE session_id IN ({placeholders}) ORDER BY session_id, step_index ASC",
                    session_ids,
                )
                columns_ui = [desc[0] for desc in cur.description]
                interventions = [dict(zip(columns_ui, row)) for row in cur.fetchall()]

                return {
                    "sessions": sessions,
                    "steps": steps,
                    "tool_calls": tool_calls,
                    "user_interventions": interventions,
                    "total_matching": total_matching,
                    "has_more": (offset + len(sessions)) < total_matching,
                }
        finally:
            conn.close()


# Default singleton storage instance
_DEFAULT_STORAGE: Optional[Storage] = None
_STORAGE_LOCK = threading.Lock()


def get_storage(database_url: Optional[str] = None) -> Storage:
    """Returns the singleton or newly initialized Storage instance."""
    global _DEFAULT_STORAGE
    with _STORAGE_LOCK:
        if database_url is not None:
            return Storage(database_url)
        if _DEFAULT_STORAGE is None:
            _DEFAULT_STORAGE = Storage()
        return _DEFAULT_STORAGE


def init_db(database_url: Optional[str] = None) -> None:
    """Module-level convenience function for initializing schemas."""
    storage = get_storage(database_url)
    storage.init_db()


def ping() -> bool:
    """Module-level convenience function for checking database connectivity."""
    return get_storage().ping()


def upsert_batch(
    sessions: List[Dict[str, Any]],
    steps: List[Dict[str, Any]],
    tool_calls: List[Dict[str, Any]],
    user_interventions: List[Dict[str, Any]],
    requesting_user: str,
) -> Dict[str, int]:
    """Module-level convenience function for batch upserts."""
    return get_storage().upsert_batch(
        sessions=sessions,
        steps=steps,
        tool_calls=tool_calls,
        user_interventions=user_interventions,
        requesting_user=requesting_user,
    )


def query_delta(
    since: str,
    requesting_user: Optional[str] = None,
    limit: int = 100,
) -> Dict[str, Any]:
    """Module-level convenience function for delta queries."""
    return get_storage().query_delta(
        since=since,
        requesting_user=requesting_user,
        limit=limit,
    )
