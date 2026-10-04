"""
Client Sync Engine for PSL Telemetry (ADR-030).

Provides push and pull synchronization between local workstation SQLite telemetry
and the central telemetry aggregation service with client-side redaction.
"""

from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path
import sqlite3
from typing import Any, Dict, List, Optional, Union
import urllib.error
import urllib.parse
import urllib.request

from harness.telemetry import config
from harness.telemetry.redaction import (
    anonymize_paths,
    sanitize_intervention,
    sanitize_tool_call,
    strip_secrets,
)
from harness.telemetry.schema import SCHEMA_SQL


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


def push_local_sessions(
    endpoint: Optional[str] = None,
    token: Optional[str] = None,
    db_path: Optional[Union[str, Path]] = None,
    workspace_root: Optional[Union[str, Path]] = None,
    limit: Optional[int] = None,
    dry_run: bool = False,
) -> Dict[str, Any]:
    """Pushes unsynced local sessions to the remote telemetry service.

    Redacts secrets and anonymizes workspace paths prior to serialization.
    Updates remote_synced_at timestamp in SQLite upon successful transmission.
    """
    resolved_endpoint = endpoint or config.get_sync_endpoint()
    resolved_token = token or config.get_auth_token()

    if not resolved_endpoint:
        raise ValueError("Sync endpoint required for telemetry sync.")
    if not resolved_token:
        raise ValueError("Authentication token required for telemetry sync.")

    endpoint_clean = resolved_endpoint.rstrip("/")
    db_file = Path(db_path or "data/telemetry.db")
    db_file.parent.mkdir(parents=True, exist_ok=True)

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
        cfg = config.load_config()
        eligible_sessions = [
            s for s in raw_sessions
            if not (s.get("workspace_path") and config.is_workspace_denylisted(s["workspace_path"], cfg))
        ]

        if limit is not None and limit >= 0:
            eligible_sessions = eligible_sessions[:limit]

        if not eligible_sessions:
            return {
                "status": "success" if not dry_run else "dry_run",
                "sessions_pushed": 0,
                "steps_pushed": 0,
                "tool_calls_pushed": 0,
                "user_interventions_pushed": 0,
                "synced_at": datetime.now(timezone.utc).isoformat() if not dry_run else None,
                "dry_run": dry_run,
            }

        session_ids = [s["session_id"] for s in eligible_sessions]
        placeholders = ",".join(["?"] * len(session_ids))

        cur.execute(
            f"SELECT * FROM steps WHERE session_id IN ({placeholders}) ORDER BY session_id, step_index ASC",
            session_ids,
        )
        raw_steps = [dict(r) for r in cur.fetchall()]

        cur.execute(
            f"SELECT * FROM tool_calls WHERE session_id IN ({placeholders}) ORDER BY session_id, step_index ASC",
            session_ids,
        )
        raw_tools = [dict(r) for r in cur.fetchall()]

        cur.execute(
            f"SELECT * FROM user_interventions WHERE session_id IN ({placeholders}) ORDER BY session_id, step_index ASC",
            session_ids,
        )
        raw_interventions = [dict(r) for r in cur.fetchall()]

        # Per-session workspace mapping for path anonymization
        session_ws_map = {
            s["session_id"]: (workspace_root or s.get("workspace_path"))
            for s in eligible_sessions
        }

        # Sanitize client-side using redaction engine
        sanitized_sessions: List[Dict[str, Any]] = []
        for s in eligible_sessions:
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

        payload = {
            "client_version": "1.0.0",
            "sessions": sanitized_sessions,
            "steps": sanitized_steps,
            "tool_calls": sanitized_tools,
            "user_interventions": sanitized_interventions,
        }

        if dry_run:
            return {
                "status": "dry_run",
                "sessions_pushed": len(sanitized_sessions),
                "steps_pushed": len(sanitized_steps),
                "tool_calls_pushed": len(sanitized_tools),
                "user_interventions_pushed": len(sanitized_interventions),
                "synced_at": None,
                "dry_run": True,
            }

        primary_url = f"{endpoint_clean}/api/v1/sync/push"
        payload_bytes = json.dumps(payload).encode("utf-8")
        headers = {
            "Authorization": f"Bearer {resolved_token}",
            "Content-Type": "application/json",
            "User-Agent": "psl-harness/1.0.0",
        }
        req = urllib.request.Request(
            primary_url,
            data=payload_bytes,
            headers=headers,
            method="POST",
        )

        try:
            with urllib.request.urlopen(req, timeout=30.0) as resp:
                _ = resp.read()
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
            else:
                raise

        now_iso = datetime.now(timezone.utc).isoformat()
        cur.executemany(
            "UPDATE sessions SET remote_synced_at = ? WHERE session_id = ?",
            [(now_iso, s_id) for s_id in session_ids],
        )
        conn.commit()

        return {
            "status": "success",
            "sessions_pushed": len(sanitized_sessions),
            "steps_pushed": len(sanitized_steps),
            "tool_calls_pushed": len(sanitized_tools),
            "user_interventions_pushed": len(sanitized_interventions),
            "synced_at": now_iso,
            "dry_run": False,
        }
    finally:
        conn.close()


def pull_remote_sessions(
    endpoint: Optional[str] = None,
    token: Optional[str] = None,
    db_path: Optional[Union[str, Path]] = None,
    since: Optional[str] = None,
) -> Dict[str, Any]:
    """Pulls delta sessions from the remote telemetry service and ingests into SQLite.

    Idempotently inserts sessions, steps, tool calls, and user interventions.
    """
    resolved_endpoint = endpoint or config.get_sync_endpoint()
    resolved_token = token or config.get_auth_token()

    if not resolved_endpoint:
        raise ValueError("Sync endpoint required for telemetry sync.")
    if not resolved_token:
        raise ValueError("Authentication token required for telemetry sync.")

    endpoint_clean = resolved_endpoint.rstrip("/")
    db_file = Path(db_path or "data/telemetry.db")
    db_file.parent.mkdir(parents=True, exist_ok=True)

    conn = sqlite3.connect(db_file)
    conn.row_factory = sqlite3.Row
    try:
        ensure_sync_columns(conn)
        cur = conn.cursor()

        if since is None:
            cur.execute(
                "SELECT MAX(remote_synced_at) FROM sessions "
                "WHERE origin_developer != 'local' AND origin_developer IS NOT NULL"
            )
            row = cur.fetchone()
            if row and row[0]:
                since = row[0]
            else:
                since = "1970-01-01T00:00:00Z"

        primary_url = f"{endpoint_clean}/api/v1/sync/pull?since={urllib.parse.quote(str(since))}"
        headers = {
            "Authorization": f"Bearer {resolved_token}",
            "Accept": "application/json",
            "User-Agent": "psl-harness/1.0.0",
        }
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
                fallback_url = f"{endpoint_clean}/api/v1/telemetry/delta?since={urllib.parse.quote(str(since))}"
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

        now_iso = datetime.now(timezone.utc).isoformat()
        sessions_inserted = 0
        for s in pulled_sessions:
            origin_val = s.get("origin_developer")
            if not origin_val or origin_val == "local":
                origin_val = "remote"
            cur.execute("""
                INSERT OR IGNORE INTO sessions (
                    session_id, start_time, end_time, duration_seconds, total_steps,
                    model, workspace_path, transcript_path, file_size_bytes, has_errors,
                    tool_call_count, tool_error_count, intervention_count,
                    origin_developer, remote_synced_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                s.get("session_id"), s.get("start_time"), s.get("end_time"),
                s.get("duration_seconds"), s.get("total_steps"), s.get("model"),
                s.get("workspace_path"), s.get("transcript_path"), s.get("file_size_bytes"),
                s.get("has_errors"), s.get("tool_call_count"), s.get("tool_error_count"),
                s.get("intervention_count"),
                origin_val,
                s.get("remote_synced_at") or now_iso,
            ))
            if cur.rowcount > 0:
                sessions_inserted += 1

        steps_inserted = 0
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

        tools_inserted = 0
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

        interventions_inserted = 0
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

        return {
            "status": "success",
            "sessions_pulled": len(pulled_sessions),
            "steps_pulled": len(pulled_steps),
            "tool_calls_pulled": len(pulled_tools),
            "user_interventions_pulled": len(pulled_interventions),
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
    endpoint: Optional[str] = None,
    token: Optional[str] = None,
    db_path: Optional[Union[str, Path]] = None,
    limit: Optional[int] = None,
    dry_run: bool = False,
) -> Dict[str, Any]:
    """Coordinates bi-directional sync (push then pull), push-only, or pull-only.

    Parameters:
        direction: 'both', 'push', or 'pull'
        interactive: If True and direction includes push, prompts for user confirmation before pushing.
        endpoint: Telemetry hub URL (default from config/env)
        token: Authentication bearer token (default from credentials/env)
        db_path: Path to local SQLite telemetry database
        limit: Max sessions to push
        dry_run: If True, simulates push without sending or updating DB
    """
    if direction not in ("both", "push", "pull"):
        raise ValueError(f"Invalid sync direction: '{direction}'. Must be 'both', 'push', or 'pull'.")

    push_result = None
    pull_result = None

    if direction in ("both", "push"):
        if interactive and not dry_run:
            db_file = Path(db_path or "data/telemetry.db")
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

            resolved_endpoint = endpoint or config.get_sync_endpoint()
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
            limit=limit,
            dry_run=dry_run,
        )

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
            )

    return {
        "status": "success" if not dry_run else "dry_run",
        "direction": direction,
        "push": push_result,
        "pull": pull_result,
    }

