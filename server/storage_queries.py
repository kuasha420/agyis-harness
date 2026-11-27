# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Arafat Zahan (@kuasha420)
# Corporate Stewardship & Infrastructure: Purrfect Software Limited (PSL)
# Governed by: ICARO-42/b Ordinance (Company-Supported Personal IP Framework)

"""
Dual-engine query, migration, keyset pagination, and inventory helpers for Storage (ADR-030).
"""

from __future__ import annotations

from datetime import datetime, timezone
import sqlite3
from typing import Any, Dict, List, Optional, Sequence, Set, Tuple

_ADDITIVE_COLUMNS: Tuple[Tuple[str, str, str], ...] = (
    ("origin_machine", "TEXT", "TEXT"),
    ("client_surface", "TEXT", "TEXT"),
    ("source_kind", "TEXT", "TEXT"),
    ("model_slug", "TEXT", "TEXT"),
    ("model_display_name", "TEXT", "TEXT"),
    ("max_context_tokens", "INTEGER", "INTEGER"),
    ("total_input_tokens", "INTEGER", "BIGINT"),
    ("total_cache_read_tokens", "INTEGER", "BIGINT"),
    ("total_output_tokens", "INTEGER", "BIGINT"),
    ("total_thought_tokens", "INTEGER", "BIGINT"),
    ("peak_context_tokens", "INTEGER", "INTEGER"),
    ("server_seq", "INTEGER", "BIGINT"),
)

_SESSION_COLS: Tuple[str, ...] = (
    "session_id", "start_time", "end_time", "duration_seconds", "total_steps",
    "model", "workspace_path", "transcript_path", "file_size_bytes", "has_errors",
    "tool_call_count", "tool_error_count", "intervention_count",
    "origin_developer", "remote_synced_at",
    "origin_machine", "client_surface", "source_kind",
    "model_slug", "model_display_name", "max_context_tokens",
    "total_input_tokens", "total_cache_read_tokens", "total_output_tokens",
    "total_thought_tokens", "peak_context_tokens", "server_seq",
)

_STEP_COLS: Tuple[str, ...] = (
    "session_id", "step_index", "step_type", "source", "status", "created_at",
    "content_length", "content_snippet", "has_thinking", "thinking_length", "tool_count",
)

_TOOL_COLS: Tuple[str, ...] = (
    "session_id", "step_index", "result_step_index", "tool_name", "arguments_json",
    "arguments_snippet", "target_path", "command_line", "started_at", "completed_at",
    "duration_seconds", "status", "exit_code", "error_snippet", "is_loop_candidate",
    "output_length_chars", "output_lines", "arguments_length_chars", "command_category", "is_truncated",
)

_INTERV_COLS: Tuple[str, ...] = (
    "session_id", "step_index", "created_at", "prompt_text", "prompt_length",
    "preceding_tool_failed", "preceding_tool_name", "preceding_error_snippet", "intervention_type",
)


def normalize_utc_iso(ts: Optional[str]) -> Optional[str]:
    """Deterministically normalizes ISO-8601 strings to UTC 'YYYY-MM-DDTHH:MM:SSZ'."""
    if ts is None:
        return None
    if not isinstance(ts, str):
        ts = str(ts)
    cleaned = ts.strip()
    if not cleaned:
        return None
    iso_cand = cleaned[:-1] + "+00:00" if cleaned[-1] in ("Z", "z") else cleaned
    try:
        dt = datetime.fromisoformat(iso_cand)
    except ValueError:
        return cleaned
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    else:
        dt = dt.astimezone(timezone.utc)
    return dt.strftime("%Y-%m-%dT%H:%M:%SZ")


def strip_nul(obj: Any) -> Any:
    """Recursively strips NUL bytes from strings before PostgreSQL insertion."""
    if isinstance(obj, str):
        return obj.replace("\x00", "")
    if isinstance(obj, dict):
        return {k: strip_nul(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [strip_nul(v) for v in obj]
    return obj


def ensure_sync_columns(conn: Any, is_postgres: bool = False) -> None:
    """Non-destructively ensures additive federation columns, indexes, and server_seq exist."""
    if not is_postgres:
        cur = conn.cursor()
        cur.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='sessions'")
        if not cur.fetchone():
            return
        cur.execute("PRAGMA table_info(sessions)")
        existing = {row[1] for row in cur.fetchall()}
        for col, sqlite_t, _ in _ADDITIVE_COLUMNS:
            if col not in existing:
                try:
                    cur.execute(f"ALTER TABLE sessions ADD COLUMN {col} {sqlite_t}")
                except sqlite3.OperationalError:
                    pass
        cur.execute("CREATE INDEX IF NOT EXISTS idx_sessions_origin ON sessions(origin_developer)")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_sessions_synced ON sessions(remote_synced_at)")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_sessions_machine ON sessions(origin_machine)")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_sessions_server_seq ON sessions(server_seq)")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_sessions_cursor ON sessions(remote_synced_at, session_id)")
        cur.execute(
            "SELECT session_id FROM sessions WHERE server_seq IS NULL "
            "ORDER BY COALESCE(remote_synced_at, start_time, '') ASC, session_id ASC"
        )
        missing_seq_ids = [r[0] for r in cur.fetchall()]
        if missing_seq_ids:
            cur.execute("SELECT COALESCE(MAX(server_seq), 0) FROM sessions")
            next_seq = int(cur.fetchone()[0] or 0) + 1
            cur.executemany(
                "UPDATE sessions SET server_seq = ? WHERE session_id = ?",
                [(next_seq + idx, sid) for idx, sid in enumerate(missing_seq_ids)],
            )
        conn.commit()
        return

    with conn.cursor() as cur:
        cur.execute("CREATE SEQUENCE IF NOT EXISTS sessions_server_seq_seq")
        for col, _, pg_t in _ADDITIVE_COLUMNS:
            cur.execute(f"ALTER TABLE sessions ADD COLUMN IF NOT EXISTS {col} {pg_t}")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_sessions_origin ON sessions(origin_developer)")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_sessions_synced ON sessions(remote_synced_at)")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_sessions_machine ON sessions(origin_machine)")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_sessions_server_seq ON sessions(server_seq)")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_sessions_cursor ON sessions(remote_synced_at, session_id)")
        cur.execute(
            """
            WITH base AS (
                SELECT COALESCE(MAX(server_seq), 0) AS max_seq FROM sessions
            ),
            ordered AS (
                SELECT session_id,
                       ROW_NUMBER() OVER (ORDER BY COALESCE(remote_synced_at, start_time, '') ASC, session_id ASC) AS rn
                FROM sessions
                WHERE server_seq IS NULL
            )
            UPDATE sessions s
            SET server_seq = base.max_seq + ordered.rn
            FROM ordered, base
            WHERE s.session_id = ordered.session_id
            """
        )
        cur.execute(
            "SELECT setval('sessions_server_seq_seq', GREATEST(COALESCE((SELECT MAX(server_seq) FROM sessions), 0), 1))"
        )
    conn.commit()


def _session_fill_nulls_sql(ph: str) -> str:
    """Updates ONLY missing NULL session metadata on stale regressions without touching server_seq or remote_synced_at."""
    return f"""
        UPDATE sessions
        SET start_time = COALESCE(start_time, {ph}),
            end_time = COALESCE(end_time, {ph}),
            duration_seconds = COALESCE(duration_seconds, {ph}),
            model = CASE
                WHEN model IS NULL OR model = 'Unknown'
                THEN COALESCE({ph}, model) ELSE model END,
            workspace_path = COALESCE(workspace_path, {ph}),
            transcript_path = COALESCE(transcript_path, {ph}),
            has_errors = COALESCE(has_errors, {ph}),
            origin_developer = CASE
                WHEN origin_developer IS NULL OR origin_developer IN ('', 'local')
                THEN COALESCE({ph}, origin_developer) ELSE origin_developer END,
            origin_machine = COALESCE(origin_machine, {ph}),
            client_surface = COALESCE(client_surface, {ph}),
            source_kind = COALESCE(source_kind, {ph}),
            model_slug = COALESCE(model_slug, {ph}),
            model_display_name = COALESCE(model_display_name, {ph}),
            max_context_tokens = COALESCE(max_context_tokens, {ph})
        WHERE session_id = {ph}
    """


_SOURCE_KIND_RANK: Dict[str, int] = {
    "sqlite_db": 1,
    "transcript": 2,
    "transcript_full": 3,
}


def _session_upsert_sql(ph: str) -> str:
    placeholders = ", ".join([ph] * len(_SESSION_COLS))
    return f"""
        INSERT INTO sessions ({', '.join(_SESSION_COLS)}) VALUES ({placeholders})
        ON CONFLICT(session_id) DO UPDATE SET
            start_time = COALESCE(excluded.start_time, sessions.start_time),
            end_time = COALESCE(excluded.end_time, sessions.end_time),
            duration_seconds = COALESCE(excluded.duration_seconds, sessions.duration_seconds),
            total_steps = CASE
                WHEN excluded.total_steps IS NOT NULL AND (sessions.total_steps IS NULL OR excluded.total_steps >= sessions.total_steps)
                THEN excluded.total_steps ELSE sessions.total_steps END,
            model = CASE
                WHEN excluded.model IS NOT NULL AND excluded.model != 'Unknown'
                THEN excluded.model ELSE COALESCE(sessions.model, excluded.model) END,
            workspace_path = COALESCE(excluded.workspace_path, sessions.workspace_path),
            transcript_path = COALESCE(excluded.transcript_path, sessions.transcript_path),
            file_size_bytes = CASE
                WHEN excluded.file_size_bytes IS NOT NULL AND (sessions.file_size_bytes IS NULL OR excluded.file_size_bytes >= sessions.file_size_bytes)
                THEN excluded.file_size_bytes ELSE sessions.file_size_bytes END,
            has_errors = COALESCE(excluded.has_errors, sessions.has_errors),
            tool_call_count = CASE
                WHEN excluded.tool_call_count IS NOT NULL AND (sessions.tool_call_count IS NULL OR excluded.tool_call_count >= sessions.tool_call_count)
                THEN excluded.tool_call_count ELSE sessions.tool_call_count END,
            tool_error_count = CASE
                WHEN excluded.tool_error_count IS NOT NULL AND (sessions.tool_error_count IS NULL OR excluded.tool_error_count >= sessions.tool_error_count)
                THEN excluded.tool_error_count ELSE sessions.tool_error_count END,
            intervention_count = CASE
                WHEN excluded.intervention_count IS NOT NULL AND (sessions.intervention_count IS NULL OR excluded.intervention_count >= sessions.intervention_count)
                THEN excluded.intervention_count ELSE sessions.intervention_count END,
            origin_developer = CASE
                WHEN sessions.origin_developer IS NULL OR sessions.origin_developer IN ('', 'local')
                THEN excluded.origin_developer ELSE sessions.origin_developer END,
            origin_machine = COALESCE(excluded.origin_machine, sessions.origin_machine),
            client_surface = COALESCE(excluded.client_surface, sessions.client_surface),
            source_kind = COALESCE(excluded.source_kind, sessions.source_kind),
            model_slug = COALESCE(excluded.model_slug, sessions.model_slug),
            model_display_name = COALESCE(excluded.model_display_name, sessions.model_display_name),
            max_context_tokens = COALESCE(excluded.max_context_tokens, sessions.max_context_tokens),
            total_input_tokens = CASE
                WHEN excluded.total_input_tokens IS NOT NULL AND (sessions.total_input_tokens IS NULL OR excluded.total_input_tokens >= sessions.total_input_tokens)
                THEN excluded.total_input_tokens ELSE sessions.total_input_tokens END,
            total_cache_read_tokens = CASE
                WHEN excluded.total_cache_read_tokens IS NOT NULL AND (sessions.total_cache_read_tokens IS NULL OR excluded.total_cache_read_tokens >= sessions.total_cache_read_tokens)
                THEN excluded.total_cache_read_tokens ELSE sessions.total_cache_read_tokens END,
            total_output_tokens = CASE
                WHEN excluded.total_output_tokens IS NOT NULL AND (sessions.total_output_tokens IS NULL OR excluded.total_output_tokens >= sessions.total_output_tokens)
                THEN excluded.total_output_tokens ELSE sessions.total_output_tokens END,
            total_thought_tokens = CASE
                WHEN excluded.total_thought_tokens IS NOT NULL AND (sessions.total_thought_tokens IS NULL OR excluded.total_thought_tokens >= sessions.total_thought_tokens)
                THEN excluded.total_thought_tokens ELSE sessions.total_thought_tokens END,
            peak_context_tokens = CASE
                WHEN excluded.peak_context_tokens IS NOT NULL AND (sessions.peak_context_tokens IS NULL OR excluded.peak_context_tokens >= sessions.peak_context_tokens)
                THEN excluded.peak_context_tokens ELSE sessions.peak_context_tokens END,
            remote_synced_at = excluded.remote_synced_at,
            server_seq = excluded.server_seq
    """


def _normalize_batch_payload(
    sessions: List[Dict[str, Any]],
    steps: List[Dict[str, Any]],
    tool_calls: List[Dict[str, Any]],
    user_interventions: List[Dict[str, Any]],
    now_iso: str,
    clean_nul: bool = False,
) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]], List[Dict[str, Any]], List[Dict[str, Any]]]:
    norm_s: List[Dict[str, Any]] = []
    for s in sessions:
        sc = strip_nul(s) if clean_nul else dict(s)
        sc["start_time"] = normalize_utc_iso(sc.get("start_time"))
        sc["end_time"] = normalize_utc_iso(sc.get("end_time"))
        sc["remote_synced_at"] = now_iso
        norm_s.append(sc)

    norm_st: List[Dict[str, Any]] = []
    for st in steps:
        sc = strip_nul(st) if clean_nul else dict(st)
        sc["created_at"] = normalize_utc_iso(sc.get("created_at"))
        norm_st.append(sc)

    norm_tc: List[Dict[str, Any]] = []
    for tc in tool_calls:
        sc = strip_nul(tc) if clean_nul else dict(tc)
        sc["started_at"] = normalize_utc_iso(sc.get("started_at"))
        sc["completed_at"] = normalize_utc_iso(sc.get("completed_at"))
        norm_tc.append(sc)

    norm_ui: List[Dict[str, Any]] = []
    for ui in user_interventions:
        sc = strip_nul(ui) if clean_nul else dict(ui)
        sc["created_at"] = normalize_utc_iso(sc.get("created_at"))
        norm_ui.append(sc)

    return norm_s, norm_st, norm_tc, norm_ui


def execute_upsert_batch(
    cur: Any,
    sessions: List[Dict[str, Any]],
    steps: List[Dict[str, Any]],
    tool_calls: List[Dict[str, Any]],
    user_interventions: List[Dict[str, Any]],
    now_iso: str,
    is_postgres: bool = False,
) -> Dict[str, int]:
    """Executes atomic batch upsert with monotonic guards and child-row replacement."""
    ph = "%s" if is_postgres else "?"
    norm_s, norm_st, norm_tc, norm_ui = _normalize_batch_payload(
        sessions, steps, tool_calls, user_interventions, now_iso, clean_nul=is_postgres
    )
    incoming_child_sids: Set[str] = {
        r["session_id"] for r in (norm_st + norm_tc + norm_ui) if r.get("session_id")
    }

    existing_meta_map: Dict[str, Tuple[Optional[int], Optional[str]]] = {}
    s_ids = [s["session_id"] for s in norm_s if s.get("session_id")]
    if s_ids:
        for i in range(0, len(s_ids), 500):
            chunk = s_ids[i : i + 500]
            c_ph = ",".join([ph] * len(chunk))
            cur.execute(f"SELECT session_id, total_steps, source_kind FROM sessions WHERE session_id IN ({c_ph})", chunk)
            for row in cur.fetchall():
                existing_meta_map[row[0]] = (row[1], row[2])

    if not is_postgres:
        cur.execute("SELECT COALESCE(MAX(server_seq), 0) FROM sessions")
        next_seq = int(cur.fetchone()[0] or 0) + 1
    else:
        next_seq = 0

    stale_sids: Set[str] = set()
    replace_sids: List[str] = []
    max_seq_assigned = 0
    upsert_sql = _session_upsert_sql(ph)
    fill_nulls_sql = _session_fill_nulls_sql(ph)

    for s in norm_s:
        s_id = s.get("session_id")
        if not s_id:
            continue

        is_stale = False
        if s_id in existing_meta_map:
            ex_steps, ex_sk = existing_meta_map[s_id]
            in_steps = s.get("total_steps")
            in_sk = s.get("source_kind")
            ex_rank = _SOURCE_KIND_RANK.get(ex_sk or "", 0)
            in_rank = _SOURCE_KIND_RANK.get(in_sk or "", 0)
            lower_richness = ex_rank > 0 and in_rank > 0 and in_rank < ex_rank
            if (ex_steps is not None and in_steps is not None and int(in_steps) < int(ex_steps)) or lower_richness:
                is_stale = True
                stale_sids.add(s_id)
            elif s_id in incoming_child_sids:
                replace_sids.append(s_id)

        if is_stale:
            cur.execute(
                fill_nulls_sql,
                (
                    s.get("start_time"), s.get("end_time"), s.get("duration_seconds"),
                    s.get("model"), s.get("workspace_path"), s.get("transcript_path"),
                    s.get("has_errors"), s.get("origin_developer"),
                    s.get("origin_machine"), s.get("client_surface"), s.get("source_kind"),
                    s.get("model_slug"), s.get("model_display_name"), s.get("max_context_tokens"),
                    s_id,
                ),
            )
            continue

        if is_postgres:
            cur.execute("SELECT nextval('sessions_server_seq_seq')")
            seq_val = int(cur.fetchone()[0])
        else:
            seq_val = next_seq
            next_seq += 1
        s["server_seq"] = seq_val
        max_seq_assigned = max(max_seq_assigned, seq_val)
        cur.execute(upsert_sql, tuple(s.get(c) for c in _SESSION_COLS))

    for i in range(0, len(replace_sids), 500):
        chunk = replace_sids[i : i + 500]
        c_ph = ",".join([ph] * len(chunk))
        for tbl in ("tool_calls", "user_interventions", "steps"):
            cur.execute(f"DELETE FROM {tbl} WHERE session_id IN ({c_ph})", chunk)

    step_prefix = "INSERT INTO steps" if is_postgres else "INSERT OR IGNORE INTO steps"
    step_suffix = " ON CONFLICT (session_id, step_index) DO NOTHING" if is_postgres else ""
    step_sql = f"{step_prefix} ({', '.join(_STEP_COLS)}) VALUES ({', '.join([ph] * len(_STEP_COLS))}){step_suffix}"
    steps_inserted = 0
    for st in norm_st:
        if st.get("session_id") in stale_sids:
            continue
        cur.execute(step_sql, tuple(st.get(c) for c in _STEP_COLS))
        if cur.rowcount > 0:
            steps_inserted += 1

    tool_prefix = "INSERT INTO tool_calls" if is_postgres else "INSERT OR IGNORE INTO tool_calls"
    tool_suffix = (
        " ON CONFLICT (session_id, step_index, tool_name, started_at, arguments_snippet) DO NOTHING"
        if is_postgres
        else ""
    )
    tool_sql = f"{tool_prefix} ({', '.join(_TOOL_COLS)}) VALUES ({', '.join([ph] * len(_TOOL_COLS))}){tool_suffix}"
    tool_defaults = {
        "is_loop_candidate": 0, "output_length_chars": 0, "output_lines": 0,
        "arguments_length_chars": 0, "is_truncated": 0,
    }
    tools_inserted = 0
    for tc in norm_tc:
        if tc.get("session_id") in stale_sids:
            continue
        cur.execute(tool_sql, tuple(tc.get(c, tool_defaults.get(c)) for c in _TOOL_COLS))
        if cur.rowcount > 0:
            tools_inserted += 1

    interv_prefix = "INSERT INTO user_interventions" if is_postgres else "INSERT OR IGNORE INTO user_interventions"
    interv_suffix = " ON CONFLICT (session_id, step_index) DO NOTHING" if is_postgres else ""
    interv_sql = f"{interv_prefix} ({', '.join(_INTERV_COLS)}) VALUES ({', '.join([ph] * len(_INTERV_COLS))}){interv_suffix}"
    intervs_inserted = 0
    for ui in norm_ui:
        if ui.get("session_id") in stale_sids:
            continue
        cur.execute(interv_sql, tuple(ui.get(c) for c in _INTERV_COLS))
        if cur.rowcount > 0:
            intervs_inserted += 1

    return {
        "sessions_upserted": len(norm_s),
        "steps_inserted": steps_inserted,
        "tool_calls_inserted": tools_inserted,
        "user_interventions_inserted": intervs_inserted,
        "max_server_seq": max_seq_assigned,
    }


def _rows_to_dicts(cur: Any, rows: Sequence[Any], is_postgres: bool) -> List[Dict[str, Any]]:
    if not rows:
        return []
    if is_postgres:
        cols = [desc[0] for desc in cur.description]
        return [dict(zip(cols, r)) for r in rows]
    return [dict(r) for r in rows]


def execute_fetch_delta(
    cur: Any,
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
    is_postgres: bool = False,
) -> Dict[str, Any]:
    """Queries delta sessions and children supporting both keyset cursor/after_seq and since+offset."""
    ph = "%s" if is_postgres else "?"
    clauses: List[str] = []
    params: List[Any] = []
    use_keyset = False

    if after_seq is not None and int(after_seq) >= 0:
        use_keyset = True
        clauses.append(f"server_seq > {ph}")
        params.append(int(after_seq))
        order_clause = "ORDER BY server_seq ASC, session_id ASC"
    elif cursor and "|" in cursor:
        use_keyset = True
        raw_ts, raw_sid = cursor.split("|", 1)
        c_ts = normalize_utc_iso(raw_ts) or raw_ts
        clauses.append(
            f"(COALESCE(remote_synced_at, start_time, '') > {ph} "
            f"OR (COALESCE(remote_synced_at, start_time, '') = {ph} AND session_id > {ph}))"
        )
        params.extend([c_ts, c_ts, raw_sid])
        order_clause = "ORDER BY COALESCE(remote_synced_at, start_time, '') ASC, session_id ASC"
    else:
        norm_since = normalize_utc_iso(since) or "1970-01-01T00:00:00Z"
        clauses.append(
            f"((remote_synced_at IS NOT NULL AND remote_synced_at > {ph}) "
            f"OR (start_time IS NOT NULL AND start_time > {ph}))"
        )
        params.extend([norm_since, norm_since])
        order_clause = "ORDER BY COALESCE(remote_synced_at, start_time, '') ASC, session_id ASC"

    dev_list = [d.strip() for d in (developers or []) if isinstance(d, str) and d.strip() and d.strip() != "*"]
    if dev_list:
        d_ph = ",".join([ph] * len(dev_list))
        clauses.append(f"origin_developer IN ({d_ph})")
        params.extend(dev_list)
    elif developer:
        if developer != "*":
            clauses.append(f"origin_developer = {ph}")
            params.append(developer)
    elif not all_developers and requesting_user:
        clauses.append(f"(origin_developer IS NULL OR origin_developer != {ph})")
        params.append(requesting_user)

    if machine and machine.strip():
        clauses.append(f"origin_machine = {ph}")
        params.append(machine.strip())

    where_sql = " AND ".join(clauses)
    base_sql = f"SELECT * FROM sessions WHERE {where_sql}"
    count_sql = f"SELECT COUNT(*) FROM ({base_sql}) AS matching_sessions"
    cur.execute(count_sql, params)
    total_matching = int(cur.fetchone()[0] or 0)

    eff_offset = 0 if use_keyset else max(0, int(offset))
    page_sql = f"{base_sql} {order_clause} LIMIT {ph} OFFSET {ph}"
    cur.execute(page_sql, params + [int(limit), eff_offset])
    sessions = _rows_to_dicts(cur, cur.fetchall(), is_postgres)

    if not sessions:
        return {
            "sessions": [],
            "steps": [],
            "tool_calls": [],
            "user_interventions": [],
            "total_matching": total_matching,
            "has_more": False,
            "next_after_seq": after_seq or 0,
            "next_cursor": None,
        }

    session_ids = [s["session_id"] for s in sessions]
    s_ph = ",".join([ph] * len(session_ids))

    cur.execute(
        f"SELECT * FROM steps WHERE session_id IN ({s_ph}) ORDER BY session_id, step_index ASC",
        session_ids,
    )
    steps = _rows_to_dicts(cur, cur.fetchall(), is_postgres)

    cur.execute(
        f"SELECT * FROM tool_calls WHERE session_id IN ({s_ph}) ORDER BY session_id, step_index ASC",
        session_ids,
    )
    tool_calls = _rows_to_dicts(cur, cur.fetchall(), is_postgres)

    cur.execute(
        f"SELECT * FROM user_interventions WHERE session_id IN ({s_ph}) ORDER BY session_id, step_index ASC",
        session_ids,
    )
    interventions = _rows_to_dicts(cur, cur.fetchall(), is_postgres)

    last_s = sessions[-1]
    last_ts = last_s.get("remote_synced_at") or last_s.get("start_time") or ""
    next_cursor = f"{last_ts}|{last_s['session_id']}"
    next_after_seq = max((int(s.get("server_seq") or 0) for s in sessions), default=int(after_seq or 0))
    has_more = (eff_offset + len(sessions)) < total_matching

    return {
        "sessions": sessions,
        "steps": steps,
        "tool_calls": tool_calls,
        "user_interventions": interventions,
        "total_matching": total_matching,
        "has_more": has_more,
        "next_after_seq": next_after_seq,
        "next_cursor": next_cursor,
    }


def _merge_span(bucket: Dict[str, Any], start_t: Optional[str], end_t: Optional[str], sync_t: Optional[str], steps_cnt: int) -> None:
    bucket["session_count"] += 1
    bucket["total_steps"] += int(steps_cnt or 0)
    if start_t and (bucket["earliest_start_time"] is None or start_t < bucket["earliest_start_time"]):
        bucket["earliest_start_time"] = start_t
    if end_t and (bucket["latest_end_time"] is None or end_t > bucket["latest_end_time"]):
        bucket["latest_end_time"] = end_t
    if sync_t and (bucket["latest_synced_at"] is None or sync_t > bucket["latest_synced_at"]):
        bucket["latest_synced_at"] = sync_t


def execute_query_inventory(
    cur: Any,
    developer: Optional[str] = None,
    machine: Optional[str] = None,
    is_postgres: bool = False,
) -> Dict[str, Any]:
    """Returns anonymized per-developer, per-machine, and per-surface counts and date spans."""
    ph = "%s" if is_postgres else "?"
    clauses: List[str] = []
    params: List[Any] = []
    if developer and developer != "*":
        clauses.append(f"origin_developer = {ph}")
        params.append(developer)
    if machine and machine.strip():
        clauses.append(f"origin_machine = {ph}")
        params.append(machine.strip())

    where_sql = f" WHERE {' AND '.join(clauses)}" if clauses else ""
    cur.execute(
        f"SELECT origin_developer, origin_machine, client_surface, total_steps, "
        f"start_time, end_time, remote_synced_at, server_seq FROM sessions{where_sql}",
        params,
    )
    rows = cur.fetchall()

    total_sessions = 0
    max_seq = 0
    earliest_start: Optional[str] = None
    latest_end: Optional[str] = None
    latest_sync: Optional[str] = None
    dev_map: Dict[str, Dict[str, Any]] = {}
    mach_map: Dict[Tuple[str, str], Dict[str, Any]] = {}
    surf_map: Dict[str, Dict[str, Any]] = {}

    for dev_raw, mach_raw, surf_raw, steps_raw, st_raw, en_raw, sy_raw, seq_raw in rows:
        dev = dev_raw or "unknown"
        mach = mach_raw or "unknown"
        surf = surf_raw or "ide"
        steps_i = int(steps_raw or 0)
        st = normalize_utc_iso(st_raw)
        en = normalize_utc_iso(en_raw)
        sy = normalize_utc_iso(sy_raw)
        max_seq = max(max_seq, int(seq_raw or 0))
        total_sessions += 1

        if st and (earliest_start is None or st < earliest_start):
            earliest_start = st
        if en and (latest_end is None or en > latest_end):
            latest_end = en
        if sy and (latest_sync is None or sy > latest_sync):
            latest_sync = sy

        d_b = dev_map.setdefault(dev, {
            "origin_developer": dev, "session_count": 0, "total_steps": 0,
            "earliest_start_time": None, "latest_end_time": None, "latest_synced_at": None,
            "machines": set(), "surfaces": set(),
        })
        _merge_span(d_b, st, en, sy, steps_i)
        d_b["machines"].add(mach)
        d_b["surfaces"].add(surf)

        m_b = mach_map.setdefault((mach, dev), {
            "origin_machine": mach, "origin_developer": dev, "session_count": 0, "total_steps": 0,
            "earliest_start_time": None, "latest_end_time": None, "latest_synced_at": None,
            "surfaces": set(),
        })
        _merge_span(m_b, st, en, sy, steps_i)
        m_b["surfaces"].add(surf)

        s_b = surf_map.setdefault(surf, {
            "client_surface": surf, "session_count": 0, "total_steps": 0,
            "earliest_start_time": None, "latest_end_time": None, "latest_synced_at": None,
        })
        _merge_span(s_b, st, en, sy, steps_i)

    developers_out = []
    for key in sorted(dev_map):
        item = dict(dev_map[key])
        item["machines"] = sorted(item["machines"])
        item["surfaces"] = sorted(item["surfaces"])
        developers_out.append(item)

    machines_out = []
    for key in sorted(mach_map):
        item = dict(mach_map[key])
        item["surfaces"] = sorted(item["surfaces"])
        machines_out.append(item)

    surfaces_out = [dict(surf_map[k]) for k in sorted(surf_map)]

    return {
        "total_sessions": total_sessions,
        "max_server_seq": max_seq,
        "earliest_start_time": earliest_start,
        "latest_end_time": latest_end,
        "latest_synced_at": latest_sync,
        "developers": developers_out,
        "machines": machines_out,
        "surfaces": surfaces_out,
    }
