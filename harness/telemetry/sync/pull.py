# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Arafat Zahan (@kuasha420)
# Corporate Stewardship & Infrastructure: Purrfect Software Limited (PSL)
# Governed by: ICARO-42/b Ordinance (Company-Supported Personal IP Framework)

"""
Telemetry sync pull engine (ADR-030).
Supports per-scope watermarks, keyset cursor pagination, and atomic child-row replacement.
"""

from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path
import sqlite3
import time
from typing import Any, Callable, Dict, List, Optional, Set, Tuple, Union
import urllib.error
import urllib.parse
import urllib.request

from harness import __version__
from harness.telemetry import config
from harness.telemetry.config import resolve_db_path
from harness.telemetry.db import get_db_connection, get_sync_watermark, set_sync_watermark
from harness.telemetry.models import normalize_utc_iso
from harness.telemetry.schema import ensure_sync_columns
from harness.telemetry.sync.client import validate_sync_endpoint, verify_auth_token
from harness.telemetry.sync.constants import _get_retry_backoff


def _compute_pull_scope_key(
    developer: Optional[str],
    all_developers: bool,
    include_self: bool,
    machine: Optional[str],
) -> str:
    """Computes isolated watermark scope key so filtered pulls never starve other scopes."""
    if developer and developer != "*":
        base = f"dev:{developer}"
    elif include_self and not all_developers:
        base = "self"
    elif all_developers or developer == "*":
        base = "all"
    else:
        base = "peers"
    if machine and machine.strip():
        return f"{base}:machine:{machine.strip()}"
    return base


def _resolve_initial_watermark(
    conn: sqlite3.Connection,
    scope_key: str,
    explicit_since: Optional[str],
    developer: Optional[str],
    all_developers: bool,
    include_self: bool,
    machine: Optional[str],
) -> Tuple[str, Optional[int]]:
    """Resolves initial (since, after_seq) from explicit arg, sync_watermarks, or legacy fallback."""
    ensure_sync_columns(conn)
    if explicit_since is not None:
        return normalize_utc_iso(explicit_since) or explicit_since, None

    wm = get_sync_watermark(conn, scope_key)
    if wm is not None:
        wm_ts, wm_seq = wm
        resolved_ts = normalize_utc_iso(wm_ts) or "1970-01-01T00:00:00Z"
        return resolved_ts, (wm_seq if wm_seq > 0 else None)

    cur = conn.cursor()
    if developer and developer != "*":
        query = (
            "SELECT MAX(remote_synced_at) FROM sessions "
            "WHERE origin_developer = ? AND origin_developer != 'local' AND remote_synced_at IS NOT NULL"
        )
        params: List[Any] = [developer]
        if machine:
            query += " AND origin_machine = ?"
            params.append(machine)
        cur.execute(query, params)
        row = cur.fetchone()
        raw = row[0] if row else None
        return (normalize_utc_iso(raw) if raw else None) or "1970-01-01T00:00:00Z", None

    if not all_developers and not include_self:
        query = (
            "SELECT MAX(remote_synced_at) FROM sessions "
            "WHERE origin_developer != 'local' AND origin_developer IS NOT NULL AND remote_synced_at IS NOT NULL"
        )
        params = []
        if machine:
            query += " AND origin_machine = ?"
            params.append(machine)
        cur.execute(query, params)
        row = cur.fetchone()
        raw = row[0] if row else None
        return (normalize_utc_iso(raw) if raw else None) or "1970-01-01T00:00:00Z", None

    return "1970-01-01T00:00:00Z", None


def _count_children_for_sessions(
    cur: sqlite3.Cursor,
    session_ids: List[str],
) -> Tuple[int, int, int]:
    if not session_ids:
        return 0, 0, 0
    s_cnt = t_cnt = i_cnt = 0
    for i in range(0, len(session_ids), 500):
        chunk = session_ids[i : i + 500]
        ph = ",".join(["?"] * len(chunk))
        cur.execute(f"SELECT COUNT(*) FROM steps WHERE session_id IN ({ph})", chunk)
        s_cnt += cur.fetchone()[0]
        cur.execute(f"SELECT COUNT(*) FROM tool_calls WHERE session_id IN ({ph})", chunk)
        t_cnt += cur.fetchone()[0]
        cur.execute(f"SELECT COUNT(*) FROM user_interventions WHERE session_id IN ({ph})", chunk)
        i_cnt += cur.fetchone()[0]
    return s_cnt, t_cnt, i_cnt


_SOURCE_KIND_RANK: Dict[str, int] = {
    "sqlite_db": 1,
    "transcript": 2,
    "transcript_full": 3,
}


def _upsert_pulled_session(
    cur: sqlite3.Cursor,
    s: Dict[str, Any],
    now_iso: str,
    incoming_child_sids: Set[str],
) -> Tuple[bool, bool, bool, Optional[str], int]:
    """Upserts one pulled session returning (inserted, replace_children, is_stale, synced_at, server_seq)."""
    s_id = s["session_id"]
    origin_val = s.get("origin_developer")
    if not origin_val or origin_val == "local":
        origin_val = "remote"
    remote_sync_time = normalize_utc_iso(s.get("remote_synced_at")) or now_iso
    s_start = normalize_utc_iso(s.get("start_time"))
    s_end = normalize_utc_iso(s.get("end_time"))
    s_seq = int(s.get("server_seq") or 0)

    cur.execute(
        "SELECT origin_developer, remote_synced_at, total_steps, source_kind FROM sessions WHERE session_id = ?",
        (s_id,),
    )
    existing_row = cur.fetchone()
    if existing_row is None:
        cur.execute(
            """
            INSERT INTO sessions (
                session_id, start_time, end_time, duration_seconds, total_steps,
                model, workspace_path, transcript_path, file_size_bytes, has_errors,
                tool_call_count, tool_error_count, intervention_count,
                origin_developer, remote_synced_at,
                origin_machine, client_surface, source_kind,
                model_slug, model_display_name, max_context_tokens,
                total_input_tokens, total_cache_read_tokens, total_output_tokens,
                total_thought_tokens, peak_context_tokens, server_seq
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                s_id, s_start, s_end,
                s.get("duration_seconds"), s.get("total_steps"), s.get("model"),
                s.get("workspace_path"), s.get("transcript_path"), s.get("file_size_bytes"),
                s.get("has_errors"), s.get("tool_call_count"), s.get("tool_error_count"),
                s.get("intervention_count"), origin_val, remote_sync_time,
                s.get("origin_machine"), s.get("client_surface"), s.get("source_kind"),
                s.get("model_slug"), s.get("model_display_name"), s.get("max_context_tokens"),
                s.get("total_input_tokens"), s.get("total_cache_read_tokens"),
                s.get("total_output_tokens"), s.get("total_thought_tokens"),
                s.get("peak_context_tokens"), s_seq or None,
            ),
        )
        return True, False, False, remote_sync_time, s_seq

    existing_steps = existing_row[2]
    existing_sk = existing_row[3]
    incoming_steps = s.get("total_steps")
    incoming_sk = s.get("source_kind")
    ex_rank = _SOURCE_KIND_RANK.get(existing_sk or "", 0)
    in_rank = _SOURCE_KIND_RANK.get(incoming_sk or "", 0)
    lower_richness = ex_rank > 0 and in_rank > 0 and in_rank < ex_rank
    is_stale = (
        (existing_steps is not None and incoming_steps is not None and int(incoming_steps) < int(existing_steps))
        or lower_richness
    )
    s_model = s.get("model")

    if is_stale:
        cur.execute(
            """
            UPDATE sessions
            SET start_time = COALESCE(start_time, ?),
                end_time = COALESCE(end_time, ?),
                duration_seconds = COALESCE(duration_seconds, ?),
                model = CASE
                    WHEN model IS NULL OR model = 'Unknown'
                    THEN COALESCE(?, model) ELSE model END,
                workspace_path = COALESCE(workspace_path, ?),
                transcript_path = COALESCE(transcript_path, ?),
                has_errors = COALESCE(has_errors, ?),
                origin_developer = CASE
                    WHEN origin_developer IS NULL OR origin_developer IN ('', 'remote')
                    THEN COALESCE(?, origin_developer) ELSE origin_developer END,
                origin_machine = COALESCE(origin_machine, ?),
                client_surface = COALESCE(client_surface, ?),
                source_kind = COALESCE(source_kind, ?),
                model_slug = COALESCE(model_slug, ?),
                model_display_name = COALESCE(model_display_name, ?),
                max_context_tokens = COALESCE(max_context_tokens, ?)
            WHERE session_id = ?
            """,
            (
                s_start, s_end, s.get("duration_seconds"),
                s_model, s.get("workspace_path"), s.get("transcript_path"),
                s.get("has_errors"), origin_val,
                s.get("origin_machine"), s.get("client_surface"), incoming_sk,
                s.get("model_slug"), s.get("model_display_name"), s.get("max_context_tokens"),
                s_id,
            ),
        )
        return False, False, True, None, 0

    cur.execute(
        """
        UPDATE sessions
        SET start_time = COALESCE(start_time, ?),
            end_time = COALESCE(?, end_time),
            duration_seconds = COALESCE(?, duration_seconds),
            total_steps = CASE
                WHEN ? IS NOT NULL AND (total_steps IS NULL OR ? >= total_steps)
                THEN ? ELSE total_steps END,
            model = CASE
                WHEN ? IS NOT NULL AND ? != 'Unknown'
                THEN ? ELSE COALESCE(model, ?) END,
            workspace_path = COALESCE(workspace_path, ?),
            transcript_path = COALESCE(transcript_path, ?),
            file_size_bytes = CASE
                WHEN ? IS NOT NULL AND (file_size_bytes IS NULL OR ? >= file_size_bytes)
                THEN ? ELSE file_size_bytes END,
            has_errors = COALESCE(?, has_errors),
            tool_call_count = CASE
                WHEN ? IS NOT NULL AND (tool_call_count IS NULL OR ? >= tool_call_count)
                THEN ? ELSE tool_call_count END,
            tool_error_count = CASE
                WHEN ? IS NOT NULL AND (tool_error_count IS NULL OR ? >= tool_error_count)
                THEN ? ELSE tool_error_count END,
            intervention_count = CASE
                WHEN ? IS NOT NULL AND (intervention_count IS NULL OR ? >= intervention_count)
                THEN ? ELSE intervention_count END,
            origin_developer = CASE
                WHEN origin_developer IS NULL OR origin_developer IN ('', 'remote')
                THEN COALESCE(?, origin_developer) ELSE origin_developer END,
            origin_machine = COALESCE(?, origin_machine),
            client_surface = COALESCE(?, client_surface),
            source_kind = COALESCE(?, source_kind),
            model_slug = COALESCE(?, model_slug),
            model_display_name = COALESCE(?, model_display_name),
            max_context_tokens = COALESCE(?, max_context_tokens),
            total_input_tokens = CASE
                WHEN ? IS NOT NULL AND (total_input_tokens IS NULL OR ? >= total_input_tokens)
                THEN ? ELSE total_input_tokens END,
            total_cache_read_tokens = CASE
                WHEN ? IS NOT NULL AND (total_cache_read_tokens IS NULL OR ? >= total_cache_read_tokens)
                THEN ? ELSE total_cache_read_tokens END,
            total_output_tokens = CASE
                WHEN ? IS NOT NULL AND (total_output_tokens IS NULL OR ? >= total_output_tokens)
                THEN ? ELSE total_output_tokens END,
            total_thought_tokens = CASE
                WHEN ? IS NOT NULL AND (total_thought_tokens IS NULL OR ? >= total_thought_tokens)
                THEN ? ELSE total_thought_tokens END,
            peak_context_tokens = CASE
                WHEN ? IS NOT NULL AND (peak_context_tokens IS NULL OR ? >= peak_context_tokens)
                THEN ? ELSE peak_context_tokens END,
            server_seq = CASE
                WHEN ? IS NOT NULL AND (server_seq IS NULL OR ? >= server_seq)
                THEN ? ELSE server_seq END,
            remote_synced_at = CASE
                WHEN ? IS NOT NULL AND (remote_synced_at IS NULL OR ? >= remote_synced_at)
                THEN ? ELSE remote_synced_at END
        WHERE session_id = ?
        """,
        (
            s_start,
            s_end,
            s.get("duration_seconds"),
            incoming_steps, incoming_steps, incoming_steps,
            s_model, s_model, s_model, s_model,
            s.get("workspace_path"),
            s.get("transcript_path"),
            s.get("file_size_bytes"), s.get("file_size_bytes"), s.get("file_size_bytes"),
            s.get("has_errors"),
            s.get("tool_call_count"), s.get("tool_call_count"), s.get("tool_call_count"),
            s.get("tool_error_count"), s.get("tool_error_count"), s.get("tool_error_count"),
            s.get("intervention_count"), s.get("intervention_count"), s.get("intervention_count"),
            origin_val,
            s.get("origin_machine"),
            s.get("client_surface"),
            s.get("source_kind"),
            s.get("model_slug"),
            s.get("model_display_name"),
            s.get("max_context_tokens"),
            s.get("total_input_tokens"), s.get("total_input_tokens"), s.get("total_input_tokens"),
            s.get("total_cache_read_tokens"), s.get("total_cache_read_tokens"), s.get("total_cache_read_tokens"),
            s.get("total_output_tokens"), s.get("total_output_tokens"), s.get("total_output_tokens"),
            s.get("total_thought_tokens"), s.get("total_thought_tokens"), s.get("total_thought_tokens"),
            s.get("peak_context_tokens"), s.get("peak_context_tokens"), s.get("peak_context_tokens"),
            s_seq or None, s_seq or None, s_seq or None,
            remote_sync_time, remote_sync_time, remote_sync_time,
            s_id,
        ),
    )
    should_replace = (not is_stale) and (
        s_id in incoming_child_sids
        or (incoming_steps == 0 and (s.get("tool_call_count") or 0) == 0)
    )
    return False, should_replace, is_stale, remote_sync_time, s_seq


def _ingest_pulled_page(
    conn: sqlite3.Connection,
    pulled_sessions: List[Dict[str, Any]],
    pulled_steps: List[Dict[str, Any]],
    pulled_tools: List[Dict[str, Any]],
    pulled_interventions: List[Dict[str, Any]],
    now_iso: str,
) -> Tuple[int, int, int, int, Optional[str], int]:
    """Atomically ingests one pulled page into SQLite, replacing updated sessions' child rows."""
    cur = conn.cursor()
    incoming_child_sids: Set[str] = {
        r["session_id"]
        for r in (pulled_steps + pulled_tools + pulled_interventions)
        if isinstance(r, dict) and r.get("session_id")
    }

    valid_session_ids: Set[str] = set()
    replace_children_sids: Set[str] = set()
    stale_skip_sids: Set[str] = set()
    sessions_inserted = 0
    max_page_ts: Optional[str] = None
    max_page_seq = 0

    for s in pulled_sessions:
        s_id = s.get("session_id")
        if not s_id:
            continue
        ins, rep, is_stale, r_ts, r_seq = _upsert_pulled_session(cur, s, now_iso, incoming_child_sids)
        if ins:
            sessions_inserted += 1
        if rep:
            replace_children_sids.add(s_id)
        if is_stale:
            stale_skip_sids.add(s_id)
        else:
            valid_session_ids.add(s_id)
        if r_ts and (max_page_ts is None or r_ts > max_page_ts):
            max_page_ts = r_ts
        if r_seq > max_page_seq:
            max_page_seq = r_seq

    candidate_sids: Set[str] = set()
    for r in (pulled_steps + pulled_tools + pulled_interventions):
        sid = r.get("session_id") if isinstance(r, dict) else None
        if sid and sid not in valid_session_ids and sid not in stale_skip_sids:
            candidate_sids.add(sid)

    if candidate_sids:
        cand_list = list(candidate_sids)
        for i in range(0, len(cand_list), 500):
            chunk = cand_list[i : i + 500]
            ph = ",".join(["?"] * len(chunk))
            cur.execute(f"SELECT session_id FROM sessions WHERE session_id IN ({ph})", chunk)
            valid_session_ids.update(row[0] for row in cur.fetchall())

    tracked_sids = sorted(valid_session_ids)
    before_steps, before_tools, before_intervs = _count_children_for_sessions(cur, tracked_sids)

    if replace_children_sids:
        rep_list = sorted(replace_children_sids)
        for i in range(0, len(rep_list), 500):
            chunk = rep_list[i : i + 500]
            ph = ",".join(["?"] * len(chunk))
            for tbl in ("tool_calls", "user_interventions", "steps"):
                cur.execute(f"DELETE FROM {tbl} WHERE session_id IN ({ph})", chunk)

    step_rows = [
        (
            st["session_id"], st.get("step_index"), st.get("step_type"),
            st.get("source"), st.get("status"), normalize_utc_iso(st.get("created_at")),
            st.get("content_length"), st.get("content_snippet"),
            st.get("has_thinking"), st.get("thinking_length"), st.get("tool_count"),
        )
        for st in pulled_steps
        if isinstance(st, dict) and st.get("session_id") in valid_session_ids
    ]
    for i in range(0, len(step_rows), 1000):
        cur.executemany(
            """
            INSERT OR IGNORE INTO steps (
                session_id, step_index, step_type, source, status, created_at,
                content_length, content_snippet, has_thinking, thinking_length, tool_count
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            step_rows[i : i + 1000],
        )

    tool_rows = [
        (
            tc["session_id"], tc.get("step_index"), tc.get("result_step_index"),
            tc.get("tool_name"), tc.get("arguments_json"), tc.get("arguments_snippet"),
            tc.get("target_path"), tc.get("command_line"),
            normalize_utc_iso(tc.get("started_at")), normalize_utc_iso(tc.get("completed_at")),
            tc.get("duration_seconds"), tc.get("status"), tc.get("exit_code"),
            tc.get("error_snippet"), tc.get("is_loop_candidate", 0),
            tc.get("output_length_chars", 0), tc.get("output_lines", 0),
            tc.get("arguments_length_chars", 0), tc.get("command_category"),
            tc.get("is_truncated", 0),
        )
        for tc in pulled_tools
        if isinstance(tc, dict) and tc.get("session_id") in valid_session_ids
    ]
    for i in range(0, len(tool_rows), 1000):
        cur.executemany(
            """
            INSERT OR IGNORE INTO tool_calls (
                session_id, step_index, result_step_index, tool_name, arguments_json,
                arguments_snippet, target_path, command_line, started_at, completed_at,
                duration_seconds, status, exit_code, error_snippet, is_loop_candidate,
                output_length_chars, output_lines, arguments_length_chars, command_category, is_truncated
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            tool_rows[i : i + 1000],
        )

    interv_rows = [
        (
            ui["session_id"], ui.get("step_index"), normalize_utc_iso(ui.get("created_at")),
            ui.get("prompt_text"), ui.get("prompt_length"),
            ui.get("preceding_tool_failed"), ui.get("preceding_tool_name"),
            ui.get("preceding_error_snippet"), ui.get("intervention_type"),
        )
        for ui in pulled_interventions
        if isinstance(ui, dict) and ui.get("session_id") in valid_session_ids
    ]
    for i in range(0, len(interv_rows), 1000):
        cur.executemany(
            """
            INSERT OR IGNORE INTO user_interventions (
                session_id, step_index, created_at, prompt_text, prompt_length,
                preceding_tool_failed, preceding_tool_name, preceding_error_snippet, intervention_type
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            interv_rows[i : i + 1000],
        )

    after_steps, after_tools, after_intervs = _count_children_for_sessions(cur, tracked_sids)
    return (
        sessions_inserted,
        max(0, after_steps - before_steps),
        max(0, after_tools - before_tools),
        max(0, after_intervs - before_intervs),
        max_page_ts,
        max_page_seq,
    )


def pull_remote_sessions(
    endpoint: Optional[str] = None,
    token: Optional[str] = None,
    db_path: Optional[Union[str, Path]] = None,
    since: Optional[str] = None,
    all_developers: bool = False,
    include_self: bool = False,
    developer: Optional[str] = None,
    batch_limit: int = 50,
    on_progress: Optional[Callable[[int, int, Dict[str, Any]], None]] = None,
    dry_run: bool = False,
    retry_backoff: Optional[float] = None,
    machine: Optional[str] = None,
) -> Dict[str, Any]:
    """Pulls delta sessions from the remote telemetry service and ingests into SQLite."""
    eff_backoff = _get_retry_backoff(retry_backoff)
    resolved_endpoint = endpoint or config.get_sync_endpoint()
    resolved_token = token or config.get_auth_token()

    if not resolved_endpoint:
        raise ValueError("Sync endpoint required for telemetry sync.")
    if not resolved_token:
        raise ValueError("Authentication token required for telemetry sync.")

    endpoint_clean = validate_sync_endpoint(resolved_endpoint)
    db_file = resolve_db_path(db_path, must_exist=False)
    db_file.parent.mkdir(parents=True, exist_ok=True)

    all_devs = all_developers or include_self
    scope_key = _compute_pull_scope_key(developer, all_developers, include_self, machine)
    explicit_since = since

    init_conn = get_db_connection(db_file)
    try:
        since, after_seq = _resolve_initial_watermark(
            init_conn, scope_key, explicit_since, developer, all_developers, include_self, machine
        )
    finally:
        init_conn.close()

    headers = {
        "Authorization": f"Bearer {resolved_token}",
        "Accept": "application/json",
        "User-Agent": f"psl-harness/{__version__}",
    }

    def _fetch_page(query_str: str) -> Dict[str, Any]:
        primary_url = f"{endpoint_clean}/api/v1/sync/pull?{query_str}"
        req = urllib.request.Request(primary_url, headers=headers, method="GET")
        max_attempts = 3
        for attempt in range(max_attempts):
            try:
                try:
                    with urllib.request.urlopen(req, timeout=30.0) as resp:
                        body = resp.read().decode("utf-8")
                    break
                except urllib.error.HTTPError as err:
                    if err.code == 404:
                        fallback_url = f"{endpoint_clean}/api/v1/telemetry/delta?{query_str}"
                        req_fb = urllib.request.Request(fallback_url, headers=headers, method="GET")
                        with urllib.request.urlopen(req_fb, timeout=30.0) as resp:
                            body = resp.read().decode("utf-8")
                        break
                    raise
            except urllib.error.HTTPError as err:
                if 400 <= err.code < 500:
                    raise
                if err.code in (502, 503, 504) and attempt < max_attempts - 1:
                    if eff_backoff > 0:
                        time.sleep(eff_backoff)
                    continue
                raise
            except urllib.error.URLError:
                if attempt < max_attempts - 1:
                    if eff_backoff > 0:
                        time.sleep(eff_backoff)
                    continue
                raise
        return json.loads(body)

    if dry_run:
        verify_auth_token(endpoint=resolved_endpoint, token=resolved_token)
        params = [f"since={urllib.parse.quote(str(since))}", "limit=1", "offset=0"]
        if after_seq is not None and after_seq >= 0:
            params.append(f"after_seq={after_seq}")
        if all_devs:
            params.append("all_developers=true")
        if include_self:
            params.append("include_self=true")
        if developer:
            params.append(f"developer={urllib.parse.quote(str(developer))}")
        if machine:
            params.append(f"machine={urllib.parse.quote(str(machine))}")
        data = _fetch_page("&".join(params))
        total_matching = data.get("total_matching")
        if total_matching is None:
            total_matching = len(data.get("sessions", []))
        return {
            "status": "dry_run",
            "sessions_pulled": total_matching,
            "sessions_to_pull": total_matching,
            "steps_pulled": 0,
            "tool_calls_pulled": 0,
            "user_interventions_pulled": 0,
            "sessions_inserted": 0,
            "steps_inserted": 0,
            "tool_calls_inserted": 0,
            "user_interventions_inserted": 0,
            "since": since,
            "scope_key": scope_key,
            "dry_run": True,
        }

    offset = 0
    cursor: Optional[str] = None
    page_num = 0
    started_with_after_seq = after_seq is not None and after_seq >= 0
    max_since_seq = 0
    total_sessions_pulled = total_steps_pulled = total_tools_pulled = total_interventions_pulled = 0
    sessions_inserted = steps_inserted = tools_inserted = interventions_inserted = 0
    now_iso = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    while True:
        page_num += 1
        params = [f"limit={batch_limit}"]
        if started_with_after_seq and after_seq is not None:
            params.append(f"after_seq={after_seq}")
            params.append("offset=0")
        elif cursor:
            params.append(f"cursor={urllib.parse.quote(cursor)}")
            params.append("offset=0")
        else:
            params.append(f"since={urllib.parse.quote(str(since))}")
            params.append(f"offset={offset}")

        if all_devs:
            params.append("all_developers=true")
        if include_self:
            params.append("include_self=true")
        if developer:
            params.append(f"developer={urllib.parse.quote(str(developer))}")
        if machine:
            params.append(f"machine={urllib.parse.quote(str(machine))}")

        data = _fetch_page("&".join(params))
        pulled_sessions = data.get("sessions", [])
        pulled_steps = data.get("steps", [])
        pulled_tools = data.get("tool_calls", [])
        pulled_interventions = data.get("user_interventions", [])

        if not pulled_sessions and not pulled_steps and not pulled_tools and not pulled_interventions:
            break

        total_sessions_pulled += len(pulled_sessions)
        total_steps_pulled += len(pulled_steps)
        total_tools_pulled += len(pulled_tools)
        total_interventions_pulled += len(pulled_interventions)
        has_more = bool(data.get("has_more", False))

        conn = get_db_connection(db_file)
        try:
            s_ins, st_ins, tc_ins, ui_ins, max_ts, max_seq = _ingest_pulled_page(
                conn, pulled_sessions, pulled_steps, pulled_tools, pulled_interventions, now_iso
            )
            sessions_inserted += s_ins
            steps_inserted += st_ins
            tools_inserted += tc_ins
            interventions_inserted += ui_ins

            resp_next_seq = data.get("next_after_seq")
            wm_seq = max(max_seq, int(resp_next_seq or 0) if isinstance(resp_next_seq, int) else 0)
            if wm_seq > max_since_seq:
                max_since_seq = wm_seq

            # Commit last_server_seq immediately when scanning via server_seq, or only after
            # a cursor/since scan finishes cleanly (not has_more) so mid-scan seq cannot drift.
            commit_seq = wm_seq if started_with_after_seq else (0 if has_more else max_since_seq)
            if max_ts is not None or commit_seq > 0:
                set_sync_watermark(
                    conn,
                    scope_key,
                    max_ts,
                    last_server_seq=commit_seq,
                    updated_at=now_iso,
                    commit=False,
                )
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

        if on_progress:
            on_progress(
                page_num,
                page_num + (1 if has_more else 0),
                {
                    "phase": "pull",
                    "sessions": len(pulled_sessions),
                    "steps": len(pulled_steps),
                    "tool_calls": len(pulled_tools),
                    "user_interventions": len(pulled_interventions),
                },
            )

        if not has_more:
            break
        resp_next_seq = data.get("next_after_seq")
        resp_next_cursor = data.get("next_cursor")
        if started_with_after_seq:
            if isinstance(resp_next_seq, int) and resp_next_seq > (after_seq or 0):
                after_seq = resp_next_seq
            elif max_seq > (after_seq or 0):
                after_seq = max_seq
            else:
                break
        elif isinstance(resp_next_cursor, str) and resp_next_cursor and resp_next_cursor != cursor:
            cursor = resp_next_cursor
        elif len(pulled_sessions) >= batch_limit and len(pulled_sessions) > 0:
            offset += len(pulled_sessions)
        else:
            break

    return {
        "status": "success",
        "sessions_pulled": total_sessions_pulled,
        "steps_pulled": total_steps_pulled,
        "tool_calls_pulled": total_tools_pulled,
        "user_interventions_pulled": total_interventions_pulled,
        "sessions_inserted": sessions_inserted,
        "steps_inserted": steps_inserted,
        "tool_calls_inserted": tools_inserted,
        "user_interventions_inserted": interventions_inserted,
        "since": since,
        "scope_key": scope_key,
    }
