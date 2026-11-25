# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Arafat Zahan (@kuasha420)
# Corporate Stewardship & Infrastructure: Purrfect Software Limited (PSL)
# Governed by: ICARO-42/b Ordinance (Company-Supported Personal IP Framework)

"""
Storage Abstraction Layer for PSL Telemetry Hub (ADR-030).

Provides a dual-engine database abstraction supporting SQLite (for hermetic testing
and local workstation development) and PostgreSQL (for production VPS deployment).
"""

from __future__ import annotations

from datetime import datetime, timezone
import importlib.resources
import os
from pathlib import Path
import sqlite3
import threading
from typing import Any, Dict, List, Optional

from server.storage_queries import (
    ensure_sync_columns as _ensure_sync_columns_impl,
    execute_fetch_delta,
    execute_query_inventory,
    execute_upsert_batch,
    normalize_utc_iso,
)


def _load_sql_asset(filename: str) -> str:
    """Loads externalized DDL asset from server.assets (PSL-INV-008)."""
    return (
        importlib.resources.files("server.assets")
        .joinpath(filename)
        .read_text(encoding="utf-8")
    )


SQLITE_SCHEMA_SQL = _load_sql_asset("sqlite_schema.sql")
POSTGRES_SCHEMA_SQL = _load_sql_asset("postgres_schema.sql")


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
            Path(self.sqlite_path).parent.mkdir(parents=True, exist_ok=True)

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
        """Idempotently initializes schemas, indexes, and additive sync columns."""
        with self._lock:
            if self.is_postgres:
                conn = self._get_pg_conn()
                try:
                    with conn.cursor() as cur:
                        cur.execute("SELECT to_regclass('sessions')")
                        has_sessions = cur.fetchone()[0] is not None
                    if has_sessions:
                        _ensure_sync_columns_impl(conn, is_postgres=True)
                    with conn.cursor() as cur:
                        cur.execute(POSTGRES_SCHEMA_SQL)
                    conn.commit()
                    _ensure_sync_columns_impl(conn, is_postgres=True)
                finally:
                    conn.close()
            else:
                conn = self._get_sqlite_conn()
                try:
                    cur = conn.cursor()
                    cur.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='sessions'")
                    if cur.fetchone():
                        _ensure_sync_columns_impl(conn, is_postgres=False)
                    conn.executescript(SQLITE_SCHEMA_SQL)
                    conn.commit()
                    _ensure_sync_columns_impl(conn, is_postgres=False)
                finally:
                    if self.sqlite_path != ":memory:":
                        conn.close()

    def ensure_sync_columns(self) -> None:
        """Non-destructively ensures additive federation columns and server_seq exist."""
        with self._lock:
            if self.is_postgres:
                conn = self._get_pg_conn()
                try:
                    _ensure_sync_columns_impl(conn, is_postgres=True)
                finally:
                    conn.close()
            else:
                conn = self._get_sqlite_conn()
                try:
                    _ensure_sync_columns_impl(conn, is_postgres=False)
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
        """Atomically upserts sessions and replaces child rows on non-stale updates."""
        sanitized_sessions: List[Dict[str, Any]] = []
        for s in sessions:
            s_copy = dict(s)
            if not s_copy.get("origin_developer") or s_copy.get("origin_developer") == "local":
                s_copy["origin_developer"] = requesting_user
            sanitized_sessions.append(s_copy)

        with self._lock:
            now_iso = normalize_utc_iso(datetime.now(timezone.utc).isoformat()) or datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
            if self.is_postgres:
                conn = self._get_pg_conn()
                try:
                    with conn.cursor() as cur:
                        res = execute_upsert_batch(
                            cur, sanitized_sessions, steps, tool_calls, user_interventions, now_iso, is_postgres=True
                        )
                    conn.commit()
                    return res
                finally:
                    conn.close()

            conn = self._get_sqlite_conn()
            try:
                cur = conn.cursor()
                res = execute_upsert_batch(
                    cur, sanitized_sessions, steps, tool_calls, user_interventions, now_iso, is_postgres=False
                )
                conn.commit()
                return res
            finally:
                if self.sqlite_path != ":memory:":
                    conn.close()

    def fetch_delta(
        self,
        since: str = "1970-01-01T00:00:00Z",
        requesting_user: Optional[str] = None,
        limit: int = 100,
        all_developers: bool = False,
        developer: Optional[str] = None,
        offset: int = 0,
        after_seq: Optional[int] = None,
        cursor: Optional[str] = None,
        machine: Optional[str] = None,
        developers: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        """Queries telemetry delta with keyset cursor/after_seq or since+offset pagination."""
        with self._lock:
            if self.is_postgres:
                conn = self._get_pg_conn()
                try:
                    with conn.cursor() as cur:
                        return execute_fetch_delta(
                            cur, since=since, requesting_user=requesting_user, limit=limit,
                            all_developers=all_developers, developer=developer, offset=offset,
                            after_seq=after_seq, cursor=cursor, machine=machine, developers=developers,
                            is_postgres=True,
                        )
                finally:
                    conn.close()

            conn = self._get_sqlite_conn()
            try:
                cur = conn.cursor()
                return execute_fetch_delta(
                    cur, since=since, requesting_user=requesting_user, limit=limit,
                    all_developers=all_developers, developer=developer, offset=offset,
                    after_seq=after_seq, cursor=cursor, machine=machine, developers=developers,
                    is_postgres=False,
                )
            finally:
                if self.sqlite_path != ":memory:":
                    conn.close()

    def query_delta(
        self,
        since: str = "1970-01-01T00:00:00Z",
        requesting_user: Optional[str] = None,
        limit: int = 100,
        all_developers: bool = False,
        developer: Optional[str] = None,
        offset: int = 0,
        after_seq: Optional[int] = None,
        cursor: Optional[str] = None,
        machine: Optional[str] = None,
        developers: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        """Backwards-compatible alias for fetch_delta."""
        return self.fetch_delta(
            since=since, requesting_user=requesting_user, limit=limit,
            all_developers=all_developers, developer=developer, offset=offset,
            after_seq=after_seq, cursor=cursor, machine=machine, developers=developers,
        )

    def get_inventory(
        self,
        developer: Optional[str] = None,
        machine: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Returns anonymized per-developer, per-machine, and per-surface inventory statistics."""
        with self._lock:
            if self.is_postgres:
                conn = self._get_pg_conn()
                try:
                    with conn.cursor() as cur:
                        return execute_query_inventory(cur, developer=developer, machine=machine, is_postgres=True)
                finally:
                    conn.close()

            conn = self._get_sqlite_conn()
            try:
                cur = conn.cursor()
                return execute_query_inventory(cur, developer=developer, machine=machine, is_postgres=False)
            finally:
                if self.sqlite_path != ":memory:":
                    conn.close()


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
    get_storage(database_url).init_db()


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
    **kwargs: Any,
) -> Dict[str, Any]:
    """Module-level convenience function for delta queries."""
    return get_storage().fetch_delta(
        since=since,
        requesting_user=requesting_user,
        limit=limit,
        **kwargs,
    )


def fetch_delta(
    since: str = "1970-01-01T00:00:00Z",
    requesting_user: Optional[str] = None,
    limit: int = 100,
    **kwargs: Any,
) -> Dict[str, Any]:
    """Module-level convenience function for keyset/delta queries."""
    return get_storage().fetch_delta(
        since=since,
        requesting_user=requesting_user,
        limit=limit,
        **kwargs,
    )
