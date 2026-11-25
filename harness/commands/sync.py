# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Arafat Zahan (@kuasha420)
# Corporate Stewardship & Infrastructure: Purrfect Software Limited (PSL)
# Governed by: ICARO-42/b Ordinance (Company-Supported Personal IP Framework)

"""
Telemetry synchronization CLI command (ADR-014, ADR-030).
"""

from __future__ import annotations

import argparse
import json
import sys
from typing import Any, Dict


def cmd_sync(args: argparse.Namespace) -> int:
    """Synchronizes telemetry with the central hub (push, pull, or bi-directional)."""
    db_path = getattr(args, "db", None)

    if getattr(args, "systemd", False):
        from harness.telemetry.sync import generate_systemd_service
        interval = getattr(args, "interval", 5.0) or 5.0
        unit = generate_systemd_service(interval_sec=interval)
        print(unit)
        return 0

    service_action = getattr(args, "service", None)
    if service_action:
        from harness.telemetry.sync.systemd import manage_service
        interval = getattr(args, "interval", 5.0) or 5.0
        json_output = getattr(args, "json", False)
        return manage_service(
            action=service_action,
            interval=interval,
            json_output=json_output,
        )

    if getattr(args, "watch", False):
        from harness.telemetry.sync import watch_and_sync
        interval = getattr(args, "interval", 5.0) or 5.0
        endpoint = getattr(args, "remote", None)
        if not getattr(args, "json", False):
            print(f"[*] Starting background telemetry watch & sync daemon (interval={interval}s)...")
        watch_kwargs: Dict[str, Any] = {"interval_sec": interval, "db_path": db_path, "endpoint": endpoint}
        if getattr(args, "pull", False):
            watch_kwargs["pull_in_watch"] = True
        if getattr(args, "include_self", False):
            watch_kwargs["include_self"] = True
        if getattr(args, "developer", None):
            watch_kwargs["developer"] = args.developer
        if getattr(args, "machine", None):
            watch_kwargs["machine"] = args.machine
        res = watch_and_sync(**watch_kwargs)
        if getattr(args, "json", False):
            print(json.dumps(res, indent=2))
        else:
            print(f"[✓] Watch daemon stopped: {res.get('iterations', 0)} iterations, {res.get('total_sessions_pushed', 0)} sessions pushed.")
        return 0

    if getattr(args, "session_id", None):
        try:
            from harness.telemetry import config
            from harness.telemetry.db import get_db_connection
            from harness.telemetry.extractor import (
                ensure_telemetry_schema,
                extract_session,
                upsert_session_telemetry,
            )
            from harness.trajectory.transcript_reader import find_transcript_path

            t_file, _ = find_transcript_path(args.session_id)
            if t_file is None or not t_file.is_file():
                from pathlib import Path
                cli_brain = Path.home() / ".gemini" / "antigravity-cli" / "brain"
                if cli_brain.is_dir():
                    t_file, _ = find_transcript_path(args.session_id, brain_dir=cli_brain)
            if t_file and t_file.is_file():
                resolved_db = config.resolve_db_path(db_path)
                conn = get_db_connection(resolved_db)
                try:
                    ensure_telemetry_schema(conn)
                    res = extract_session(t_file)
                    if res:
                        upsert_session_telemetry(conn, *res, commit=True)
                finally:
                    conn.close()
        except Exception as exc:
            sys.stderr.write(f"Warning: Session ingestion failed: {exc}\n")

    push_flag = getattr(args, "push", False)
    pull_flag = getattr(args, "pull", False)
    if push_flag and not pull_flag:
        direction = "push"
    elif pull_flag and not push_flag:
        direction = "pull"
    else:
        direction = "both"

    endpoint = getattr(args, "remote", None)
    interactive = getattr(args, "interactive", False)
    review = getattr(args, "review", False)
    limit = getattr(args, "limit", None)
    dry_run = getattr(args, "dry_run", False)
    on_progress = None
    if not getattr(args, "json", False):
        def on_progress(batch_num: int, total_batches: int, stats: Dict[str, Any]) -> None:
            if stats.get("phase") == "pull":
                print(f"  • Pulling page {batch_num}/{total_batches} ({stats.get('sessions', 0)} sessions, {stats.get('steps', 0)} steps)...")
            elif total_batches > 1:
                print(f"  • Pushing batch {batch_num}/{total_batches} ({stats.get('sessions', 0)} sessions, {stats.get('steps', 0)} steps)...")

    from harness.telemetry.sync import sync_telemetry
    sync_kwargs: Dict[str, Any] = {
        "direction": direction,
        "interactive": interactive,
        "endpoint": endpoint,
        "db_path": db_path,
        "limit": limit,
        "dry_run": dry_run,
        "on_progress": on_progress,
    }
    if getattr(args, "all_developers", False):
        sync_kwargs["all_developers"] = True
    if getattr(args, "include_self", False):
        sync_kwargs["include_self"] = True
    if getattr(args, "developer", None):
        sync_kwargs["developer"] = args.developer
    if getattr(args, "machine", None):
        sync_kwargs["machine"] = args.machine
    if getattr(args, "batch_limit", None) is not None:
        sync_kwargs["batch_limit"] = args.batch_limit
    if getattr(args, "since", None):
        sync_kwargs["since"] = args.since
    if review:
        sync_kwargs["review"] = review

    try:
        res = sync_telemetry(**sync_kwargs)
    except Exception as exc:
        err_msg = str(exc)
        if "403" in err_msg or "Forbidden" in err_msg:
            sys.stderr.write(
                "✘ Telemetry sync authorization failed (HTTP 403: Forbidden).\n"
                "  • Your GitHub account is not an authorized member of 'purrfectsoft'.\n"
                "  • Action: Verify organization membership or contact your team administrator.\n"
            )
        elif "401" in err_msg or "Unauthorized" in err_msg or "Token verification failed" in err_msg:
            sys.stderr.write(
                "✘ Telemetry sync authentication failed (HTTP 401: Unauthorized).\n"
                "  • The telemetry hub rejected the provided authentication credentials.\n"
                "  • Action: Run 'agyis auth login --gh' to refresh your GitHub token or verify org membership in purrfectsoft.\n"
            )
        elif isinstance(exc, ConnectionError) or "Failed to connect" in err_msg or "urlopen error" in err_msg:
            resolved_ep = endpoint or "configured endpoint"
            sys.stderr.write(
                f"✘ Failed to connect to telemetry hub ({resolved_ep}).\n"
                "  • Network or DNS resolution failure.\n"
                "  • Action: Check internet connection or verify AGYIS_SYNC_ENDPOINT.\n"
            )
        elif "database is locked" in err_msg or "OperationalError" in err_msg:
            sys.stderr.write(
                f"✘ SQLite database error: {exc}\n"
                "  • The local telemetry database is locked or busy.\n"
                "  • Action: Wait for active background operations to complete or check database file permissions.\n"
            )
        else:
            sys.stderr.write(f"✘ Telemetry sync error: {exc}\n")
        return 1

    if getattr(args, "json", False):
        print(json.dumps(res, indent=2))
        return 0

    if res.get("status") == "aborted":
        print("✘ Sync aborted by user.")
        return 0

    mode_str = " (dry run)" if dry_run else ""
    print(f"✔ Telemetry sync completed successfully{mode_str}:")
    if res.get("push"):
        p = res["push"]
        if dry_run:
            print(f"  • Pending to push: {p.get('sessions_pushed', 0)} sessions, {p.get('steps_pushed', 0)} steps, {p.get('tool_calls_pushed', 0)} tools")
        else:
            print(f"  • Pushed: {p.get('sessions_pushed', 0)} sessions, {p.get('steps_pushed', 0)} steps, {p.get('tool_calls_pushed', 0)} tools")
    if res.get("pull"):
        pl = res["pull"]
        if dry_run:
            to_pull = pl.get("sessions_to_pull", pl.get("sessions_pulled", 0))
            print(f"  • Pending to pull: {to_pull} sessions")
        else:
            print(f"  • Pulled: {pl.get('sessions_inserted', pl.get('sessions_pulled', 0))} new sessions, {pl.get('steps_inserted', pl.get('steps_pulled', 0))} steps")
    return 0
