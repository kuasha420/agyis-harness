# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Arafat Zahan (@kuasha420)
# Corporate Stewardship & Infrastructure: Purrfect Software Limited (PSL)
# Governed by: ICARO-42/b Ordinance (Company-Supported Personal IP Framework)

"""
Background sync daemon watcher & local telemetry harvester (ADR-030).
"""

from __future__ import annotations

import glob
import os
from pathlib import Path
import sqlite3
import time
from typing import Any, Callable, Dict, List, Optional, Tuple, Union

from harness.telemetry.config import resolve_db_path


def harvest_local_transcripts(
    db_path: Path,
    mtime_cache: Dict[str, Tuple[float, int]],
    brain_dir: Optional[Path] = None,
) -> int:
    """Incrementally ingests local conversation transcripts into SQLite db.

    Uses mtime & size stat cache for sub-millisecond change detection.
    """
    from pipeline.extract_transcripts import (
        SCHEMA_SQL,
        ensure_sync_columns,
        ensure_volume_columns,
        extract_session,
    )

    b_dir = brain_dir or (Path.home() / ".gemini" / "antigravity" / "brain")
    if not b_dir.is_dir():
        return 0

    pattern = str(b_dir / "*" / ".system_generated" / "logs" / "transcript.jsonl")
    paths = glob.glob(pattern)
    legacy_pattern = str(b_dir / "*" / "transcript.jsonl")
    paths.extend(glob.glob(legacy_pattern))

    modified_paths: List[Path] = []
    for p_str in paths:
        try:
            st = os.stat(p_str)
            mtime = st.st_mtime
            size = st.st_size
            cached = mtime_cache.get(p_str)
            if cached is None or cached[0] < mtime or cached[1] != size:
                modified_paths.append(Path(p_str))
                mtime_cache[p_str] = (mtime, size)
        except OSError:
            continue

    if not modified_paths:
        return 0

    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path)
    try:
        cur = conn.cursor()
        cur.executescript(SCHEMA_SQL)
        ensure_volume_columns(conn)
        ensure_sync_columns(conn)
        conn.commit()
    finally:
        conn.close()

    stored = 0
    for p in modified_paths:
        try:
            res = extract_session(p)
            if not res:
                continue
            session_row, step_rows, tool_rows, interv_rows = res
            s_id = session_row["session_id"]

            conn = sqlite3.connect(db_path)
            try:
                cur = conn.cursor()
                cur.execute("DELETE FROM steps WHERE session_id = ?", (s_id,))
                cur.execute("DELETE FROM tool_calls WHERE session_id = ?", (s_id,))
                cur.execute("DELETE FROM user_interventions WHERE session_id = ?", (s_id,))

                cur.execute(
                    "SELECT remote_synced_at, origin_developer, total_steps FROM sessions WHERE session_id = ?",
                    (s_id,),
                )
                existing_row = cur.fetchone()
                if existing_row:
                    existing_synced_at, existing_origin, existing_steps = (
                        existing_row[0],
                        existing_row[1],
                        existing_row[2],
                    )
                    new_steps = session_row.get("total_steps") or 0
                    if existing_steps is not None and new_steps > existing_steps:
                        session_row["remote_synced_at"] = None
                    elif existing_synced_at and not session_row.get("remote_synced_at"):
                        session_row["remote_synced_at"] = existing_synced_at
                    if existing_origin and existing_origin != "local":
                        session_row["origin_developer"] = existing_origin

                cur.execute(
                    """
                    INSERT OR REPLACE INTO sessions (
                        session_id, start_time, end_time, duration_seconds, total_steps,
                        model, workspace_path, transcript_path, file_size_bytes, has_errors,
                        tool_call_count, tool_error_count, intervention_count,
                        origin_developer, remote_synced_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        session_row["session_id"],
                        session_row["start_time"],
                        session_row["end_time"],
                        session_row["duration_seconds"],
                        session_row["total_steps"],
                        session_row["model"],
                        session_row["workspace_path"],
                        session_row["transcript_path"],
                        session_row["file_size_bytes"],
                        session_row["has_errors"],
                        session_row["tool_call_count"],
                        session_row["tool_error_count"],
                        session_row["intervention_count"],
                        session_row.get("origin_developer", "local"),
                        session_row.get("remote_synced_at", None),
                    ),
                )
                if step_rows:
                    cur.executemany(
                        """
                        INSERT OR IGNORE INTO steps (
                            session_id, step_index, step_type, source, status, created_at,
                            content_length, content_snippet, has_thinking, thinking_length, tool_count
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                        """,
                        [
                            (
                                s["session_id"],
                                s["step_index"],
                                s["step_type"],
                                s["source"],
                                s["status"],
                                s["created_at"],
                                s["content_length"],
                                s["content_snippet"],
                                s["has_thinking"],
                                s["thinking_length"],
                                s["tool_count"],
                            )
                            for s in step_rows
                        ],
                    )
                if tool_rows:
                    cur.executemany(
                        """
                        INSERT OR IGNORE INTO tool_calls (
                            session_id, step_index, tool_name, command_type, status,
                            args_snippet, error_message, latency_seconds, exit_code,
                            output_length, output_snippet
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                        """,
                        [
                            (
                                t["session_id"],
                                t["step_index"],
                                t["tool_name"],
                                t.get("command_type"),
                                t["status"],
                                t["args_snippet"],
                                t.get("error_message"),
                                t["latency_seconds"],
                                t.get("exit_code"),
                                t.get("output_length", 0),
                                t.get("output_snippet"),
                            )
                            for t in tool_rows
                        ],
                    )
                if interv_rows:
                    cur.executemany(
                        """
                        INSERT OR IGNORE INTO user_interventions (
                            session_id, step_index, intervention_type, text_snippet, created_at
                        ) VALUES (?, ?, ?, ?, ?)
                        """,
                        [
                            (
                                v["session_id"],
                                v["step_index"],
                                v["intervention_type"],
                                v["text_snippet"],
                                v["created_at"],
                            )
                            for v in interv_rows
                        ],
                    )
                conn.commit()
                stored += 1
            finally:
                conn.close()
        except Exception:
            continue

    return stored


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
    """Runs continuous background watching, local harvesting, and pushing of unsynced telemetry.

    Parameters:
        interval_sec: Poll interval in seconds (default 5.0).
        db_path: Optional SQLite telemetry database path.
        run_once: If True, executes exactly one harvesting/push attempt and returns.
        max_iterations: Optional upper bound on iteration count.
        stop_event: Optional threading.Event or object with is_set() and wait().
        endpoint: Telemetry hub endpoint.
        token: Authentication token.
        workspace_root: Workspace root for path anonymization.
        on_iteration: Optional callback(iteration_idx, iteration_result).
    """
    iterations = 0
    total_sessions_pushed = 0
    total_steps_pushed = 0
    total_sessions_harvested = 0
    last_synced_at = None
    errors: List[str] = []
    mtime_cache: Dict[str, Tuple[float, int]] = {}

    target_db = resolve_db_path(db_path, must_exist=False)

    try:
        while True:
            if stop_event is not None and stop_event.is_set():
                break
            if max_iterations is not None and iterations >= max_iterations:
                break

            iterations += 1
            harvested = 0
            iteration_payload: Dict[str, Any] = {"iteration": iterations}

            # 1. Incremental local transcript harvesting
            try:
                harvested = harvest_local_transcripts(target_db, mtime_cache)
                total_sessions_harvested += harvested
                iteration_payload["sessions_harvested"] = harvested
            except Exception as h_exc:
                errors.append(f"Harvest iteration {iterations} error: {h_exc}")

            # 2. Remote hub push (if configured)
            import harness.telemetry.config as sync_cfg
            import harness.telemetry.sync as sync_mod

            has_endpoint = bool(endpoint or sync_cfg.get_sync_endpoint(workspace_root=workspace_root))
            has_token = bool(token or sync_cfg.get_auth_token())

            if has_endpoint and has_token:
                try:
                    push_res = sync_mod.push_local_sessions(
                        endpoint=endpoint,
                        token=token,
                        db_path=target_db,
                        workspace_root=workspace_root,
                        dry_run=False,
                    )
                    pushed = push_res.get("sessions_pushed", 0)
                    total_sessions_pushed += pushed
                    total_steps_pushed += push_res.get("steps_pushed", 0)
                    if push_res.get("synced_at"):
                        last_synced_at = push_res["synced_at"]
                    iteration_payload.update(push_res)
                except Exception as exc:
                    errors.append(f"Push iteration {iterations} error: {exc}")
                    if run_once:
                        raise

            # Memory safety: cap errors history to 20 items to prevent unbounded heap growth
            if len(errors) > 20:
                errors = errors[-20:]

            if on_iteration:
                on_iteration(iterations, iteration_payload)

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
        "total_sessions_harvested": total_sessions_harvested,
        "total_sessions_pushed": total_sessions_pushed,
        "total_steps_pushed": total_steps_pushed,
        "last_synced_at": last_synced_at,
        "errors": errors,
    }
