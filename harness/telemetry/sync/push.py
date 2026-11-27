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
import random
import sqlite3
import time
from typing import Any, Callable, Dict, List, Optional, Tuple, Union
import urllib.error
import urllib.request

from harness import __version__
from harness.telemetry import config
from harness.telemetry.config import infer_client_surface, resolve_db_path, resolve_machine_id
from harness.telemetry.db import get_db_connection
from harness.telemetry.models import normalize_utc_iso
from harness.telemetry.redaction import (
    anonymize_paths,
    sanitize_intervention,
    sanitize_tool_call,
    strip_secrets,
)
from harness.telemetry.schema import ensure_sync_columns
from harness.telemetry.sync.client import validate_sync_endpoint, verify_auth_token
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

    endpoint_clean = validate_sync_endpoint(resolved_endpoint)
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
                "synced_at": None if dry_run else datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
                "dry_run": dry_run,
                "batches_count": 0,
            }

        if dry_run:
            all_s_ids = [s["session_id"] for s in eligible_sessions]
            total_steps = 0
            total_tools = 0
            total_interventions = 0
            chunk_size = 500
            for i in range(0, len(all_s_ids), chunk_size):
                chunk = all_s_ids[i:i + chunk_size]
                placeholders = ",".join(["?"] * len(chunk))
                cur.execute(f"SELECT COUNT(*) FROM steps WHERE session_id IN ({placeholders})", chunk)
                total_steps += cur.fetchone()[0]
                cur.execute(f"SELECT COUNT(*) FROM tool_calls WHERE session_id IN ({placeholders})", chunk)
                total_tools += cur.fetchone()[0]
                cur.execute(f"SELECT COUNT(*) FROM user_interventions WHERE session_id IN ({placeholders})", chunk)
                total_interventions += cur.fetchone()[0]

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
        "User-Agent": f"psl-harness/{__version__}",
    }

    for batch_idx, batch_sessions in enumerate(batches):
        batch_session_ids = [s["session_id"] for s in batch_sessions]
        b_placeholders = ",".join(["?"] * len(batch_session_ids))

        # Fetch child records for ONLY this batch using a short-lived connection
        fetch_conn = get_db_connection(db_file)
        try:
            fetch_cur = fetch_conn.cursor()
            fetch_cur.execute(
                f"SELECT * FROM steps WHERE session_id IN ({b_placeholders}) ORDER BY session_id, step_index ASC",
                batch_session_ids,
            )
            raw_steps = [dict(r) for r in fetch_cur.fetchall()]

            fetch_cur.execute(
                f"SELECT * FROM tool_calls WHERE session_id IN ({b_placeholders}) ORDER BY session_id, step_index ASC",
                batch_session_ids,
            )
            raw_tools = [dict(r) for r in fetch_cur.fetchall()]

            fetch_cur.execute(
                f"SELECT * FROM user_interventions WHERE session_id IN ({b_placeholders}) ORDER BY session_id, step_index ASC",
                batch_session_ids,
            )
            raw_interventions = [dict(r) for r in fetch_cur.fetchall()]
        finally:
            fetch_conn.close()

        def _anonymize_for_roots(
            text: str, roots: Tuple[Optional[Union[str, Path]], ...]
        ) -> str:
            cleaned = text
            for root in roots:
                if root:
                    cleaned = anonymize_paths(cleaned, workspace_root=root)
            return cleaned if roots else anonymize_paths(cleaned)

        session_ws_roots: Dict[str, Tuple[Optional[Union[str, Path]], ...]] = {}
        for s in batch_sessions:
            roots_list: List[Union[str, Path]] = []
            s_ws = s.get("workspace_path")
            if s_ws:
                roots_list.append(s_ws)
            if workspace_root and str(workspace_root) != str(s_ws or ""):
                roots_list.append(workspace_root)
            session_ws_roots[s["session_id"]] = tuple(roots_list)

        _ADDITIVE_SESSION_KEYS = (
            "origin_machine", "client_surface", "source_kind",
            "model_slug", "model_display_name", "max_context_tokens",
            "total_input_tokens", "total_cache_read_tokens", "total_output_tokens",
            "total_thought_tokens", "peak_context_tokens",
        )
        sanitized_sessions: List[Dict[str, Any]] = []
        for s in batch_sessions:
            s_clean = dict(s)
            raw_transcript = s.get("transcript_path")
            raw_ws = s.get("workspace_path")
            if not s_clean.get("origin_machine"):
                s_clean["origin_machine"] = resolve_machine_id(raw_ws or workspace_root)
            if not s_clean.get("client_surface"):
                s_clean["client_surface"] = infer_client_surface(raw_transcript)
            for ts_key in ("start_time", "end_time", "remote_synced_at"):
                if s_clean.get(ts_key) is not None:
                    s_clean[ts_key] = normalize_utc_iso(s_clean[ts_key])
            for add_key in _ADDITIVE_SESSION_KEYS:
                s_clean.setdefault(add_key, None)
            roots = session_ws_roots.get(s["session_id"], ())
            if s_clean.get("workspace_path"):
                s_clean["workspace_path"] = _anonymize_for_roots(s_clean["workspace_path"], roots)
            if s_clean.get("transcript_path"):
                s_clean["transcript_path"] = _anonymize_for_roots(s_clean["transcript_path"], roots)
            sanitized_sessions.append(s_clean)

        sanitized_steps: List[Dict[str, Any]] = []
        for st in raw_steps:
            st_clean = dict(st)
            st_clean.pop("id", None)
            if st_clean.get("created_at") is not None:
                st_clean["created_at"] = normalize_utc_iso(st_clean["created_at"])
            roots = session_ws_roots.get(st_clean.get("session_id"), ())
            if st_clean.get("content_snippet"):
                st_clean["content_snippet"] = _anonymize_for_roots(
                    strip_secrets(st_clean["content_snippet"]), roots
                )
            sanitized_steps.append(st_clean)

        sanitized_tools: List[Dict[str, Any]] = []
        for tc in raw_tools:
            tc_clean = dict(tc)
            tc_clean.pop("id", None)
            for ts_key in ("started_at", "completed_at"):
                if tc_clean.get(ts_key) is not None:
                    tc_clean[ts_key] = normalize_utc_iso(tc_clean[ts_key])
            roots = session_ws_roots.get(tc_clean.get("session_id"), ())
            primary_ws = roots[0] if roots else None
            scrubbed_tc = sanitize_tool_call(tc_clean, workspace_root=primary_ws)
            for extra_ws in roots[1:]:
                scrubbed_tc = sanitize_tool_call(scrubbed_tc, workspace_root=extra_ws)
            sanitized_tools.append(scrubbed_tc)

        sanitized_interventions: List[Dict[str, Any]] = []
        for ui in raw_interventions:
            ui_clean = dict(ui)
            ui_clean.pop("id", None)
            if ui_clean.get("created_at") is not None:
                ui_clean["created_at"] = normalize_utc_iso(ui_clean["created_at"])
            roots = session_ws_roots.get(ui_clean.get("session_id"), ())
            if ui_clean.get("prompt_text"):
                cleaned_prompt = sanitize_intervention(
                    ui_clean["prompt_text"], workspace_root=roots[0] if roots else None
                )
                for extra_ws in roots[1:]:
                    cleaned_prompt = anonymize_paths(cleaned_prompt, workspace_root=extra_ws)
                ui_clean["prompt_text"] = cleaned_prompt
            if ui_clean.get("preceding_error_snippet"):
                ui_clean["preceding_error_snippet"] = _anonymize_for_roots(
                    strip_secrets(ui_clean["preceding_error_snippet"]), roots
                )
            sanitized_interventions.append(ui_clean)

        payload = _strip_nul({
            "client_version": __version__,
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
                        jitter = random.uniform(0.0, min(1.0, eff_backoff))
                        backoff_sec = min(30.0, eff_backoff * (2 ** attempt) + jitter)
                        time.sleep(backoff_sec)
                    continue
                raise
            except urllib.error.URLError as err:
                # Retry transient network errors
                if attempt < max_attempts - 1:
                    if eff_backoff > 0:
                        jitter = random.uniform(0.0, min(1.0, eff_backoff))
                        backoff_sec = min(30.0, eff_backoff * (2 ** attempt) + jitter)
                        time.sleep(backoff_sec)
                    continue
                raise

        now_iso = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
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
