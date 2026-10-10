# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Purrfect Software Limited (PSL)

"""
Telemetry synchronization coordinator (ADR-030).
"""

from __future__ import annotations

from pathlib import Path
import sqlite3
from typing import Any, Callable, Dict, Optional, Union

from harness.telemetry import config
from harness.telemetry.config import resolve_db_path
from harness.telemetry.schema import ensure_sync_columns


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

        import harness.telemetry.sync as sync_mod

        push_result = sync_mod.push_local_sessions(
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
            import harness.telemetry.sync as sync_mod

            pull_result = sync_mod.pull_remote_sessions(
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
