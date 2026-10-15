# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Arafat Zahan (@kuasha420)
# Corporate Stewardship & Infrastructure: Purrfect Software Limited (PSL)
# Governed by: ICARO-42/b Ordinance (Company-Supported Personal IP Framework)

"""
Telemetry sync push engine (ADR-030).
"""

from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path
import sqlite3
import time
from typing import Any, Callable, Dict, List, Optional, Union
import urllib.error
import urllib.request

from harness.telemetry import config
from harness.telemetry.config import resolve_db_path
from harness.telemetry.db import get_db_connection
from harness.telemetry.redaction import (
    anonymize_paths,
    sanitize_intervention,
    sanitize_tool_call,
    strip_secrets,
)
from harness.telemetry.schema import ensure_sync_columns
from harness.telemetry.sync.client import verify_auth_token
from harness.telemetry.sync.constants import (
    DEFAULT_BATCH_SESSION_LIMIT,
    DEFAULT_BATCH_STEP_LIMIT,
    _get_retry_backoff,
)
from harness.telemetry.sync.ui import interactive_select_sessions


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

    if dry_run:
        verify_auth_token(endpoint=resolved_endpoint, token=resolved_token)

    conn = get_db_connection(db_file)
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

        # Pre-load all batch records before closing DB connection
        batch_data: List[Dict[str, Any]] = []
        for batch_sessions in batches:
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

            batch_data.append({
                "sessions": batch_sessions,
                "session_ids": batch_session_ids,
                "raw_steps": raw_steps,
                "raw_tools": raw_tools,
                "raw_interventions": raw_interventions,
            })
    finally:
        conn.close()

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

    for batch_idx, item in enumerate(batch_data):
        batch_sessions = item["sessions"]
        batch_session_ids = item["session_ids"]
        raw_steps = item["raw_steps"]
        raw_tools = item["raw_tools"]
        raw_interventions = item["raw_interventions"]

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
        update_conn = get_db_connection(db_file)
        try:
            update_cur = update_conn.cursor()
            update_cur.executemany(
                "UPDATE sessions SET remote_synced_at = ? WHERE session_id = ?",
                [(now_iso, s_id) for s_id in batch_session_ids],
            )
            update_conn.commit()
        finally:
            update_conn.close()

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
