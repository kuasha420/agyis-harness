"""
Client Sync Engine for PSL Telemetry (ADR-030).

Provides push and pull synchronization between local workstation SQLite telemetry
and the central telemetry aggregation service with client-side redaction.
"""

from __future__ import annotations

from datetime import datetime, timezone
import json
import os
from pathlib import Path
import re
import sqlite3
import sys
import time
from typing import Any, Callable, Dict, List, Optional, TextIO, Union
import urllib.error
import urllib.parse
import urllib.request

from harness.telemetry import config
from harness.telemetry.config import resolve_db_path
from harness.telemetry.redaction import (
    anonymize_paths,
    sanitize_intervention,
    sanitize_tool_call,
    strip_secrets,
)
from harness.telemetry.schema import SCHEMA_SQL

DEFAULT_BATCH_SESSION_LIMIT = 10
DEFAULT_BATCH_STEP_LIMIT = 2500


def _get_retry_backoff(custom: Optional[float] = None) -> float:
    if custom is not None:
        return custom
    env_val = os.environ.get("PSL_RETRY_BACKOFF")
    if env_val is not None:
        try:
            return float(env_val)
        except ValueError:
            pass
    return 1.0


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


def verify_auth_token(
    endpoint: Optional[str] = None,
    token: Optional[str] = None,
) -> Dict[str, Any]:
    """Verifies GitHub PAT against the centralized telemetry hub (/api/v1/auth/verify)."""
    resolved_endpoint = endpoint or config.get_sync_endpoint()
    resolved_token = token or config.get_auth_token()

    if not resolved_endpoint:
        raise ValueError("Sync endpoint required for token verification.")
    if not resolved_token:
        raise ValueError("Authentication token required for token verification.")

    endpoint_clean = resolved_endpoint.rstrip("/")
    url = f"{endpoint_clean}/api/v1/auth/verify"
    payload = json.dumps({"token": resolved_token}).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=payload,
        headers={
            "Authorization": f"Bearer {resolved_token}",
            "Content-Type": "application/json",
            "User-Agent": "psl-harness/1.0.0",
        },
        method="POST",
    )

    with urllib.request.urlopen(req, timeout=15.0) as resp:
        body = resp.read().decode("utf-8")
        return json.loads(body)


def interactive_select_sessions(
    sessions: List[Dict[str, Any]],
    input_stream: Optional[Any] = None,
    output_stream: Optional[Any] = None,
) -> List[Dict[str, Any]]:
    """Interactively prompts the user to select which sessions to push.

    Shows candidate sessions (ID, duration, steps, tools, workspace).
    Supports:
      - 'all', empty string, or '*' to accept all candidates.
      - 'none', 'q', 'quit', 'abort', or '0' to reject all and abort.
      - Comma-separated or space-separated numbers (e.g. '1,2', '1 3') to select specific sessions.
    Zero external dependencies (pure stdlib).
    """
    if not sessions:
        if output_stream is not None:
            output_stream.write("No candidate sessions available for selection.\n")
            output_stream.flush()
        return []

    out = output_stream if output_stream is not None else sys.stdout
    inp = input_stream if input_stream is not None else sys.stdin

    out.write(f"\nCandidate Sessions Pending Push ({len(sessions)} available):\n")
    out.write("=" * 80 + "\n")
    for idx, s in enumerate(sessions, 1):
        s_id = str(s.get("session_id", "unknown"))
        dur = s.get("duration_seconds")
        dur_str = f"{dur:.1f}s" if dur is not None else "N/A"
        steps = s.get("total_steps") or 0
        tools = s.get("tool_call_count") or 0
        ws = s.get("workspace_path") or "default"
        ws_short = Path(ws).name if ws and ws != "default" else ws
        out.write(
            f"  [{idx:2d}] ID: {s_id[:16]}... | Duration: {dur_str:>7} | Steps: {steps:>4} | "
            f"Tools: {tools:>3} | Workspace: {ws_short}\n"
        )
    out.write("=" * 80 + "\n")
    out.write("Select sessions to push (comma-separated indices e.g. '1,2', 'all' [default], 'none'/'q' to cancel): ")
    out.flush()

    raw_input = inp.readline()
    if raw_input is None:
        return []
    ans = raw_input.strip()

    if not ans or ans.lower() in ("all", "a", "*"):
        return list(sessions)

    if ans.lower() in ("none", "n", "q", "quit", "abort", "0"):
        return []

    # Parse 1-based indices
    parts = re.split(r"[,;\s]+", ans)
    selected_indices: List[int] = []
    for p in parts:
        if not p:
            continue
        try:
            val = int(p)
            if 1 <= val <= len(sessions):
                if val not in selected_indices:
                    selected_indices.append(val)
            else:
                out.write(f"Warning: Index {val} out of range (1..{len(sessions)}), ignored.\n")
        except ValueError:
            out.write(f"Warning: Invalid token '{p}' ignored.\n")
    out.flush()

    return [sessions[i - 1] for i in selected_indices]


def push_local_sessions(
    endpoint: Optional[str] = None,
    token: Optional[str] = None,
    db_path: Optional[Union[str, Path]] = None,
    workspace_root: Optional[Union[str, Path]] = None,
    limit: Optional[int] = None,
    dry_run: bool = False,
    on_progress: Optional[Callable[[int, int, Dict[str, Any]], None]] = None,
    retry_backoff: Optional[float] = None,
    interactive: bool = False,
    review: bool = False,
    input_stream: Optional[Any] = None,
    output_stream: Optional[Any] = None,
) -> Dict[str, Any]:
    """Pushes unsynced local sessions to the remote telemetry service in bounded batches.

    Redacts secrets and anonymizes workspace paths prior to serialization.
    Updates remote_synced_at timestamp in SQLite upon successful transmission of each batch.
    Retries transient 5xx / network errors up to 2 times, failing fast on 4xx errors.
    """
    eff_backoff = _get_retry_backoff(retry_backoff)
    resolved_endpoint = endpoint or config.get_sync_endpoint(workspace_root=workspace_root)
    resolved_token = token or config.get_auth_token()

    if not resolved_endpoint:
        raise ValueError("Sync endpoint required for telemetry sync.")
    if not resolved_token:
        raise ValueError("Authentication token required for telemetry sync.")

    endpoint_clean = resolved_endpoint.rstrip("/")
    db_file = resolve_db_path(db_path, must_exist=True)

    conn = sqlite3.connect(db_file)
    conn.row_factory = sqlite3.Row
    try:
        ensure_sync_columns(conn)
        cur = conn.cursor()

        # Query unsynced local sessions
        cur.execute(
            "SELECT * FROM sessions "
            "WHERE (origin_developer = 'local' OR origin_developer IS NULL) "
            "  AND (remote_synced_at IS NULL OR remote_synced_at = '') "
            "ORDER BY start_time ASC"
        )
        raw_sessions = [dict(r) for r in cur.fetchall()]

        # Filter out denylisted workspaces
        cfg = config.load_config(workspace_root=workspace_root)
        eligible_sessions = [
            s for s in raw_sessions
            if not (s.get("workspace_path") and config.is_workspace_denylisted(s["workspace_path"], cfg))
        ]

        if limit is not None and limit >= 0:
            eligible_sessions = eligible_sessions[:limit]

        if (review or interactive) and not dry_run and eligible_sessions:
            eligible_sessions = interactive_select_sessions(
                eligible_sessions, input_stream=input_stream, output_stream=output_stream
            )
            if not eligible_sessions:
                return {
                    "status": "aborted",
                    "reason": "no_sessions_selected",
                    "sessions_pushed": 0,
                    "steps_pushed": 0,
                    "tool_calls_pushed": 0,
                    "user_interventions_pushed": 0,
                    "synced_at": None,
                    "dry_run": False,
                    "batches_count": 0,
                }

        # Partition into batches (max 10 sessions or max 2,500 steps per batch; single sessions exceeding 2,500 steps occupy a single batch)
        batches: List[List[Dict[str, Any]]] = []
        current_batch: List[Dict[str, Any]] = []
        current_batch_steps = 0

        for s in eligible_sessions:
            s_steps = s.get("total_steps") or 0
            if s_steps >= DEFAULT_BATCH_STEP_LIMIT:
                if current_batch:
                    batches.append(current_batch)
                    current_batch = []
                    current_batch_steps = 0
                batches.append([s])
                continue

            if current_batch and (
                len(current_batch) >= DEFAULT_BATCH_SESSION_LIMIT
                or (current_batch_steps + s_steps > DEFAULT_BATCH_STEP_LIMIT)
            ):
                batches.append(current_batch)
                current_batch = []
                current_batch_steps = 0

            current_batch.append(s)
            current_batch_steps += s_steps

        if current_batch:
            batches.append(current_batch)

        if not eligible_sessions:
            return {
                "status": "dry_run" if dry_run else "success",
                "sessions_pushed": 0,
                "steps_pushed": 0,
                "tool_calls_pushed": 0,
                "user_interventions_pushed": 0,
                "synced_at": None if dry_run else datetime.now(timezone.utc).isoformat(),
                "dry_run": dry_run,
                "batches_count": 0,
            }

        if dry_run:
            all_s_ids = [s["session_id"] for s in eligible_sessions]
            placeholders = ",".join(["?"] * len(all_s_ids))
            cur.execute(f"SELECT COUNT(*) FROM steps WHERE session_id IN ({placeholders})", all_s_ids)
            total_steps = cur.fetchone()[0]
            cur.execute(f"SELECT COUNT(*) FROM tool_calls WHERE session_id IN ({placeholders})", all_s_ids)
            total_tools = cur.fetchone()[0]
            cur.execute(f"SELECT COUNT(*) FROM user_interventions WHERE session_id IN ({placeholders})", all_s_ids)
            total_interventions = cur.fetchone()[0]

            return {
                "status": "dry_run",
                "sessions_pushed": len(eligible_sessions),
                "steps_pushed": total_steps,
                "tool_calls_pushed": total_tools,
                "user_interventions_pushed": total_interventions,
                "synced_at": None,
                "dry_run": True,
                "batches_count": len(batches),
            }

        def _strip_nul(obj: Any) -> Any:
            if isinstance(obj, str):
                return obj.replace("\x00", "")
            if isinstance(obj, dict):
                return {k: _strip_nul(v) for k, v in obj.items()}
            if isinstance(obj, list):
                return [_strip_nul(v) for v in obj]
            return obj

        total_sessions_pushed = 0
        total_steps_pushed = 0
        total_tools_pushed = 0
        total_interventions_pushed = 0
        last_synced_at = None

        headers = {
            "Authorization": f"Bearer {resolved_token}",
            "Content-Type": "application/json",
            "User-Agent": "psl-harness/1.0.0",
        }

        for batch_idx, batch_sessions in enumerate(batches):
            batch_session_ids = [s["session_id"] for s in batch_sessions]
            b_placeholders = ",".join(["?"] * len(batch_session_ids))

            cur.execute(
                f"SELECT * FROM steps WHERE session_id IN ({b_placeholders}) ORDER BY session_id, step_index ASC",
                batch_session_ids,
            )
            raw_steps = [dict(r) for r in cur.fetchall()]

            cur.execute(
                f"SELECT * FROM tool_calls WHERE session_id IN ({b_placeholders}) ORDER BY session_id, step_index ASC",
                batch_session_ids,
            )
            raw_tools = [dict(r) for r in cur.fetchall()]

            cur.execute(
                f"SELECT * FROM user_interventions WHERE session_id IN ({b_placeholders}) ORDER BY session_id, step_index ASC",
                batch_session_ids,
            )
            raw_interventions = [dict(r) for r in cur.fetchall()]

            session_ws_map = {
                s["session_id"]: (workspace_root or s.get("workspace_path"))
                for s in batch_sessions
            }

            sanitized_sessions: List[Dict[str, Any]] = []
            for s in batch_sessions:
                s_clean = dict(s)
                ws = session_ws_map.get(s["session_id"])
                if s_clean.get("workspace_path"):
                    s_clean["workspace_path"] = anonymize_paths(s_clean["workspace_path"], workspace_root=ws)
                if s_clean.get("transcript_path"):
                    s_clean["transcript_path"] = anonymize_paths(s_clean["transcript_path"], workspace_root=ws)
                sanitized_sessions.append(s_clean)

            sanitized_steps: List[Dict[str, Any]] = []
            for st in raw_steps:
                st_clean = dict(st)
                st_clean.pop("id", None)
                ws = session_ws_map.get(st_clean.get("session_id"))
                if st_clean.get("content_snippet"):
                    st_clean["content_snippet"] = anonymize_paths(
                        strip_secrets(st_clean["content_snippet"]), workspace_root=ws
                    )
                sanitized_steps.append(st_clean)

            sanitized_tools: List[Dict[str, Any]] = []
            for tc in raw_tools:
                tc_clean = dict(tc)
                tc_clean.pop("id", None)
                ws = session_ws_map.get(tc_clean.get("session_id"))
                sanitized_tools.append(sanitize_tool_call(tc_clean, workspace_root=ws))

            sanitized_interventions: List[Dict[str, Any]] = []
            for ui in raw_interventions:
                ui_clean = dict(ui)
                ui_clean.pop("id", None)
                ws = session_ws_map.get(ui_clean.get("session_id"))
                if ui_clean.get("prompt_text"):
                    ui_clean["prompt_text"] = sanitize_intervention(
                        ui_clean["prompt_text"], workspace_root=ws
                    )
                if ui_clean.get("preceding_error_snippet"):
                    ui_clean["preceding_error_snippet"] = anonymize_paths(
                        strip_secrets(ui_clean["preceding_error_snippet"]), workspace_root=ws
                    )
                sanitized_interventions.append(ui_clean)

            payload = _strip_nul({
                "client_version": "1.0.0",
                "sessions": sanitized_sessions,
                "steps": sanitized_steps,
                "tool_calls": sanitized_tools,
                "user_interventions": sanitized_interventions,
            })

            primary_url = f"{endpoint_clean}/api/v1/sync/push"
            payload_bytes = json.dumps(payload).encode("utf-8")
            req = urllib.request.Request(
                primary_url,
                data=payload_bytes,
                headers=headers,
                method="POST",
            )

            # Retry loop: up to 2 retries (3 attempts total) on transient errors
            max_attempts = 3
            for attempt in range(max_attempts):
                try:
                    try:
                        with urllib.request.urlopen(req, timeout=30.0) as resp:
                            _ = resp.read()
                        break
                    except urllib.error.HTTPError as err:
                        if err.code == 404:
                            fallback_url = f"{endpoint_clean}/api/v1/telemetry/batch"
                            req_fallback = urllib.request.Request(
                                fallback_url,
                                data=payload_bytes,
                                headers=headers,
                                method="POST",
                            )
                            with urllib.request.urlopen(req_fallback, timeout=30.0) as resp:
                                _ = resp.read()
                            break
                        raise
                except urllib.error.HTTPError as err:
                    # Fast fail on 4xx (400, 401, 403, 413, 422, etc.)
                    if 400 <= err.code < 500:
                        raise
                    # Retry on 502, 503, 504
                    if err.code in (502, 503, 504) and attempt < max_attempts - 1:
                        if eff_backoff > 0:
                            time.sleep(eff_backoff)
                        continue
                    raise
                except urllib.error.URLError as err:
                    # Retry transient network errors
                    if attempt < max_attempts - 1:
                        if eff_backoff > 0:
                            time.sleep(eff_backoff)
                        continue
                    raise

            now_iso = datetime.now(timezone.utc).isoformat()
            cur.executemany(
                "UPDATE sessions SET remote_synced_at = ? WHERE session_id = ?",
                [(now_iso, s_id) for s_id in batch_session_ids],
            )
            conn.commit()

            total_sessions_pushed += len(sanitized_sessions)
            total_steps_pushed += len(sanitized_steps)
            total_tools_pushed += len(sanitized_tools)
            total_interventions_pushed += len(sanitized_interventions)
            last_synced_at = now_iso

            if on_progress:
                on_progress(
                    batch_idx + 1,
                    len(batches),
                    {
                        "sessions": len(sanitized_sessions),
                        "steps": len(sanitized_steps),
                        "tool_calls": len(sanitized_tools),
                        "user_interventions": len(sanitized_interventions),
                    },
                )

        return {
            "status": "success",
            "sessions_pushed": total_sessions_pushed,
            "steps_pushed": total_steps_pushed,
            "tool_calls_pushed": total_tools_pushed,
            "user_interventions_pushed": total_interventions_pushed,
            "synced_at": last_synced_at,
            "dry_run": False,
            "batches_count": len(batches),
        }
    finally:
        conn.close()


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


def sync_telemetry(
    direction: str = "both",
    interactive: bool = False,
    review: bool = False,
    endpoint: Optional[str] = None,
    token: Optional[str] = None,
    db_path: Optional[Union[str, Path]] = None,
    workspace_root: Optional[Union[str, Path]] = None,
    limit: Optional[int] = None,
    dry_run: bool = False,
    on_progress: Optional[Callable[[int, int, Dict[str, Any]], None]] = None,
    input_stream: Optional[Any] = None,
    output_stream: Optional[Any] = None,
    all_developers: bool = False,
    include_self: bool = False,
    developer: Optional[str] = None,
    since: Optional[str] = None,
) -> Dict[str, Any]:
    """Coordinates bi-directional sync (push then pull), push-only, or pull-only.

    Parameters:
        direction: 'both', 'push', or 'pull'
        interactive: If True and direction includes push, prompts for user confirmation before pushing.
        review: If True, prompts for interactive selection of sessions to push.
        endpoint: Telemetry hub URL (default from config/env)
        token: Authentication bearer token (default from credentials/env)
        db_path: Path to local SQLite telemetry database
        workspace_root: Workspace root for config and path anonymization
        limit: Max sessions to push
        dry_run: If True, simulates push without sending or updating DB
        on_progress: Optional progress callback for batch push progress
        input_stream: Optional input stream for interactive review
        output_stream: Optional output stream for interactive review
        all_developers: If True, bypasses anti-echo filter when pulling
        include_self: Alias for all_developers
        developer: Optional developer username to filter pulled telemetry
        since: Optional ISO timestamp watermark to pull from
    """
    if direction not in ("both", "push", "pull"):
        raise ValueError(f"Invalid sync direction: '{direction}'. Must be 'both', 'push', or 'pull'.")

    push_result = None
    pull_result = None

    if direction in ("both", "push"):
        if interactive and not dry_run:
            db_file = resolve_db_path(db_path, must_exist=False)
            pending_count = 0
            if db_file.exists():
                conn = sqlite3.connect(db_file)
                try:
                    ensure_sync_columns(conn)
                    cur = conn.cursor()
                    cur.execute(
                        "SELECT COUNT(*) FROM sessions "
                        "WHERE (origin_developer = 'local' OR origin_developer IS NULL) "
                        "  AND (remote_synced_at IS NULL OR remote_synced_at = '')"
                    )
                    row = cur.fetchone()
                    pending_count = row[0] if row else 0
                finally:
                    conn.close()

            resolved_endpoint = endpoint or config.get_sync_endpoint(workspace_root=workspace_root)
            print(f"Pending local sessions to push: {pending_count} -> {resolved_endpoint}")
            prompt_res = input(f"Proceed to push {pending_count} session(s)? [y/N]: ").strip().lower()
            if prompt_res not in ("y", "yes"):
                return {
                    "status": "aborted",
                    "direction": direction,
                    "reason": "user_cancelled",
                    "push": None,
                    "pull": None,
                }

        push_result = push_local_sessions(
            endpoint=endpoint,
            token=token,
            db_path=db_path,
            workspace_root=workspace_root,
            limit=limit,
            dry_run=dry_run,
            on_progress=on_progress,
            review=review,
            input_stream=input_stream,
            output_stream=output_stream,
        )

        if push_result and push_result.get("status") == "aborted":
            return {
                "status": "aborted",
                "direction": direction,
                "reason": push_result.get("reason", "user_cancelled"),
                "push": push_result,
                "pull": None,
            }

    if direction in ("both", "pull"):
        if dry_run:
            pull_result = {
                "status": "dry_run",
                "sessions_pulled": 0,
                "steps_pulled": 0,
                "tool_calls_pulled": 0,
                "user_interventions_pulled": 0,
            }
        else:
            pull_result = pull_remote_sessions(
                endpoint=endpoint,
                token=token,
                db_path=db_path,
                since=since,
                all_developers=all_developers,
                include_self=include_self,
                developer=developer,
            )

    return {
        "status": "success" if not dry_run else "dry_run",
        "direction": direction,
        "push": push_result,
        "pull": pull_result,
    }


def generate_systemd_service(
    python_bin: Optional[str] = None,
    interval_sec: float = 5.0,
    working_dir: Optional[Union[str, Path]] = None,
) -> str:
    """Generates the systemd user service unit definition for psl-sync-watch."""
    py_path = python_bin or sys.executable or "/usr/bin/python3"
    work_dir = str(working_dir) if working_dir else str(Path.home())
    return f"""[Unit]
Description=PSL Telemetry Background Sync Watcher
Documentation=https://github.com/kuasha420/psl-agy-harness
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
WorkingDirectory={work_dir}
ExecStart={py_path} -m harness.cli sync --watch --interval {interval_sec}
Restart=on-failure
RestartSec=10s
Environment=PYTHONUNBUFFERED=1

[Install]
WantedBy=default.target
"""


def watch_and_sync(
    interval_sec: float = 5.0,
    db_path: Optional[Union[str, Path]] = None,
    run_once: bool = False,
    max_iterations: Optional[int] = None,
    stop_event: Optional[Any] = None,
    endpoint: Optional[str] = None,
    token: Optional[str] = None,
    workspace_root: Optional[Union[str, Path]] = None,
    on_iteration: Optional[Callable[[int, Dict[str, Any]], None]] = None,
) -> Dict[str, Any]:
    """Runs continuous background watching and pushing of unsynced telemetry.

    Parameters:
        interval_sec: Poll interval in seconds (default 5.0).
        db_path: Optional SQLite telemetry database path.
        run_once: If True, executes exactly one push attempt and returns.
        max_iterations: Optional upper bound on iteration count.
        stop_event: Optional threading.Event or object with is_set() and wait().
        endpoint: Telemetry hub endpoint.
        token: Authentication token.
        workspace_root: Workspace root for path anonymization.
        on_iteration: Optional callback(iteration_idx, push_result).
    """
    iterations = 0
    total_sessions_pushed = 0
    total_steps_pushed = 0
    last_synced_at = None
    errors: List[str] = []

    try:
        while True:
            if stop_event is not None and stop_event.is_set():
                break
            if max_iterations is not None and iterations >= max_iterations:
                break

            iterations += 1
            push_res = None
            try:
                push_res = push_local_sessions(
                    endpoint=endpoint,
                    token=token,
                    db_path=db_path,
                    workspace_root=workspace_root,
                    dry_run=False,
                )
                pushed = push_res.get("sessions_pushed", 0)
                total_sessions_pushed += pushed
                total_steps_pushed += push_res.get("steps_pushed", 0)
                if push_res.get("synced_at"):
                    last_synced_at = push_res["synced_at"]
                if on_iteration:
                    on_iteration(iterations, push_res)
            except Exception as exc:
                errors.append(f"Iteration {iterations} error: {exc}")
                if run_once:
                    raise

            if run_once:
                break

            # Sleep / wait for next iteration
            if stop_event is not None and hasattr(stop_event, "wait"):
                stopped = stop_event.wait(timeout=interval_sec)
                if stopped:
                    break
            else:
                time.sleep(interval_sec)

    except KeyboardInterrupt:
        pass

    return {
        "status": "completed",
        "iterations": iterations,
        "total_sessions_pushed": total_sessions_pushed,
        "total_steps_pushed": total_steps_pushed,
        "last_synced_at": last_synced_at,
        "errors": errors,
    }

