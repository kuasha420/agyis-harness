# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Arafat Zahan (@kuasha420)
# Corporate Stewardship & Infrastructure: Purrfect Software Limited (PSL)
# Governed by: ICARO-42/b Ordinance (Company-Supported Personal IP Framework)

"""
Telemetry sync pull engine (ADR-030).
"""

from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path
import sqlite3
from typing import Any, Callable, Dict, Optional, Union
import urllib.error
import urllib.parse
import urllib.request

from harness.telemetry import config
from harness.telemetry.config import resolve_db_path
from harness.telemetry.schema import ensure_sync_columns


def pull_remote_sessions(
    endpoint: Optional[str] = None,
    token: Optional[str] = None,
    db_path: Optional[Union[str, Path]] = None,
    since: Optional[str] = None,
    all_developers: bool = False,
    include_self: bool = False,
    developer: Optional[str] = None,
    batch_limit: int = 500,
    on_progress: Optional[Callable[[int, int, Dict[str, Any]], None]] = None,
) -> Dict[str, Any]:
    """Pulls delta sessions from the remote telemetry service and ingests into SQLite.

    Supports paginated pulls, all_developers/include_self bypass of anti-echo filter,
    and developer-specific filtering. Idempotently inserts sessions, steps, tool calls,
    and user interventions.
    """
    resolved_endpoint = endpoint or config.get_sync_endpoint()
    resolved_token = token or config.get_auth_token()

    if not resolved_endpoint:
        raise ValueError("Sync endpoint required for telemetry sync.")
    if not resolved_token:
        raise ValueError("Authentication token required for telemetry sync.")

    endpoint_clean = resolved_endpoint.rstrip("/")
    db_file = resolve_db_path(db_path, must_exist=False)
    db_file.parent.mkdir(parents=True, exist_ok=True)

    all_devs = all_developers or include_self

    conn = sqlite3.connect(db_file)
    conn.row_factory = sqlite3.Row
    try:
        ensure_sync_columns(conn)
        cur = conn.cursor()

        if since is None:
            if all_devs or developer:
                cur.execute(
                    "SELECT MAX(remote_synced_at) FROM sessions "
                    "WHERE remote_synced_at IS NOT NULL"
                )
                row = cur.fetchone()
                if row and row[0]:
                    since = row[0]
                else:
                    since = "1970-01-01T00:00:00Z"
            else:
                cur.execute(
                    "SELECT MAX(remote_synced_at) FROM sessions "
                    "WHERE origin_developer != 'local' AND origin_developer IS NOT NULL"
                )
                row = cur.fetchone()
                if row and row[0]:
                    since = row[0]
                else:
                    since = "1970-01-01T00:00:00Z"

        headers = {
            "Authorization": f"Bearer {resolved_token}",
            "Accept": "application/json",
            "User-Agent": "psl-harness/1.0.0",
        }

        offset = 0
        total_sessions_pulled = 0
        total_steps_pulled = 0
        total_tools_pulled = 0
        total_interventions_pulled = 0

        sessions_inserted = 0
        steps_inserted = 0
        tools_inserted = 0
        interventions_inserted = 0

        now_iso = datetime.now(timezone.utc).isoformat()

        while True:
            params = [
                f"since={urllib.parse.quote(str(since))}",
                f"limit={batch_limit}",
                f"offset={offset}",
            ]
            if all_devs:
                params.append("all_developers=true")
            if developer:
                params.append(f"developer={urllib.parse.quote(str(developer))}")

            query_str = "&".join(params)
            primary_url = f"{endpoint_clean}/api/v1/sync/pull?{query_str}"
            req = urllib.request.Request(
                primary_url,
                headers=headers,
                method="GET",
            )

            try:
                with urllib.request.urlopen(req, timeout=30.0) as resp:
                    body = resp.read().decode("utf-8")
            except urllib.error.HTTPError as err:
                if err.code == 404:
                    fallback_url = f"{endpoint_clean}/api/v1/telemetry/delta?{query_str}"
                    req_fallback = urllib.request.Request(
                        fallback_url,
                        headers=headers,
                        method="GET",
                    )
                    with urllib.request.urlopen(req_fallback, timeout=30.0) as resp:
                        body = resp.read().decode("utf-8")
                else:
                    raise
            data = json.loads(body)

            pulled_sessions = data.get("sessions", [])
            pulled_steps = data.get("steps", [])
            pulled_tools = data.get("tool_calls", [])
            pulled_interventions = data.get("user_interventions", [])

            if not pulled_sessions:
                break

            total_sessions_pulled += len(pulled_sessions)
            total_steps_pulled += len(pulled_steps)
            total_tools_pulled += len(pulled_tools)
            total_interventions_pulled += len(pulled_interventions)

            for s in pulled_sessions:
                s_id = s.get("session_id")
                origin_val = s.get("origin_developer")
                if not origin_val or origin_val == "local":
                    origin_val = "remote"
                remote_sync_time = s.get("remote_synced_at") or now_iso

                cur.execute("SELECT origin_developer, remote_synced_at FROM sessions WHERE session_id = ?", (s_id,))
                existing_row = cur.fetchone()

                if existing_row is None:
                    cur.execute("""
                        INSERT INTO sessions (
                            session_id, start_time, end_time, duration_seconds, total_steps,
                            model, workspace_path, transcript_path, file_size_bytes, has_errors,
                            tool_call_count, tool_error_count, intervention_count,
                            origin_developer, remote_synced_at
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """, (
                        s_id, s.get("start_time"), s.get("end_time"),
                        s.get("duration_seconds"), s.get("total_steps"), s.get("model"),
                        s.get("workspace_path"), s.get("transcript_path"), s.get("file_size_bytes"),
                        s.get("has_errors"), s.get("tool_call_count"), s.get("tool_error_count"),
                        s.get("intervention_count"),
                        origin_val,
                        remote_sync_time,
                    ))
                    sessions_inserted += 1
                else:
                    if existing_row["remote_synced_at"] is None or existing_row["origin_developer"] == "local":
                        cur.execute(
                            "UPDATE sessions SET remote_synced_at = ?, origin_developer = ? WHERE session_id = ?",
                            (remote_sync_time, origin_val, s_id),
                        )

            for st in pulled_steps:
                cur.execute("""
                    INSERT INTO steps (
                        session_id, step_index, step_type, source, status, created_at,
                        content_length, content_snippet, has_thinking, thinking_length, tool_count
                    )
                    SELECT ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?
                    WHERE NOT EXISTS (
                        SELECT 1 FROM steps WHERE session_id = ? AND step_index = ?
                    )
                """, (
                    st.get("session_id"), st.get("step_index"), st.get("step_type"),
                    st.get("source"), st.get("status"), st.get("created_at"),
                    st.get("content_length"), st.get("content_snippet"),
                    st.get("has_thinking"), st.get("thinking_length"), st.get("tool_count"),
                    st.get("session_id"), st.get("step_index"),
                ))
                if cur.rowcount > 0:
                    steps_inserted += 1

            for tc in pulled_tools:
                cur.execute("""
                    INSERT INTO tool_calls (
                        session_id, step_index, result_step_index, tool_name, arguments_json,
                        arguments_snippet, target_path, command_line, started_at, completed_at,
                        duration_seconds, status, exit_code, error_snippet, is_loop_candidate,
                        output_length_chars, output_lines, arguments_length_chars, command_category, is_truncated
                    )
                    SELECT ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?
                    WHERE NOT EXISTS (
                        SELECT 1 FROM tool_calls
                        WHERE session_id = ?
                          AND step_index = ?
                          AND tool_name = ?
                          AND (started_at = ? OR arguments_snippet = ?)
                    )
                """, (
                    tc.get("session_id"), tc.get("step_index"), tc.get("result_step_index"),
                    tc.get("tool_name"), tc.get("arguments_json"), tc.get("arguments_snippet"),
                    tc.get("target_path"), tc.get("command_line"), tc.get("started_at"),
                    tc.get("completed_at"), tc.get("duration_seconds"), tc.get("status"),
                    tc.get("exit_code"), tc.get("error_snippet"), tc.get("is_loop_candidate", 0),
                    tc.get("output_length_chars", 0), tc.get("output_lines", 0),
                    tc.get("arguments_length_chars", 0), tc.get("command_category"),
                    tc.get("is_truncated", 0),
                    tc.get("session_id"), tc.get("step_index"), tc.get("tool_name"),
                    tc.get("started_at"), tc.get("arguments_snippet"),
                ))
                if cur.rowcount > 0:
                    tools_inserted += 1

            for ui in pulled_interventions:
                cur.execute("""
                    INSERT INTO user_interventions (
                        session_id, step_index, created_at, prompt_text, prompt_length,
                        preceding_tool_failed, preceding_tool_name, preceding_error_snippet, intervention_type
                    )
                    SELECT ?, ?, ?, ?, ?, ?, ?, ?, ?
                    WHERE NOT EXISTS (
                        SELECT 1 FROM user_interventions WHERE session_id = ? AND step_index = ?
                    )
                """, (
                    ui.get("session_id"), ui.get("step_index"), ui.get("created_at"),
                    ui.get("prompt_text"), ui.get("prompt_length"),
                    ui.get("preceding_tool_failed"), ui.get("preceding_tool_name"),
                    ui.get("preceding_error_snippet"), ui.get("intervention_type"),
                    ui.get("session_id"), ui.get("step_index"),
                ))
                if cur.rowcount > 0:
                    interventions_inserted += 1

            conn.commit()

            offset += len(pulled_sessions)
            has_more = data.get("has_more", False)
            if not has_more or len(pulled_sessions) < batch_limit:
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
        }
    finally:
        conn.close()
