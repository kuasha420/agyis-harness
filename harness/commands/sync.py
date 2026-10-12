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

    if getattr(args, "watch", False):
        from harness.telemetry.sync import watch_and_sync
        interval = getattr(args, "interval", 5.0) or 5.0
        endpoint = getattr(args, "remote", None)
        print(f"[*] Starting background telemetry watch & sync daemon (interval={interval}s)...")
        res = watch_and_sync(interval_sec=interval, db_path=db_path, endpoint=endpoint)
        if getattr(args, "json", False):
            print(json.dumps(res, indent=2))
        else:
            print(f"[✓] Watch daemon stopped: {res.get('iterations', 0)} iterations, {res.get('total_sessions_pushed', 0)} sessions pushed.")
        return 0

    if getattr(args, "session_id", None):
        try:
            from pipeline import analyze_live_session
            s_dir = analyze_live_session.find_session_dir(args.session_id)
            if s_dir and s_dir.exists():
                t_file = s_dir / ".system_generated" / "logs" / "transcript.jsonl"
                if t_file.exists():
                    from pipeline import extract_transcripts
                    from harness.telemetry import config
                    resolved_db = config.resolve_db_path(db_path)
                    extract_transcripts.extract_and_store([t_file], db_path=resolved_db)
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
            if total_batches > 1:
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
    if getattr(args, "developer", None):
        sync_kwargs["developer"] = args.developer
    if getattr(args, "since", None):
        sync_kwargs["since"] = args.since
    if review:
        sync_kwargs["review"] = review

    try:
        res = sync_telemetry(**sync_kwargs)
    except Exception as exc:
        sys.stderr.write(f"Sync error: {exc}\n")
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
        print(f"  • Pushed: {p.get('sessions_pushed', 0)} sessions, {p.get('steps_pushed', 0)} steps, {p.get('tool_calls_pushed', 0)} tools")
    if res.get("pull"):
        pl = res["pull"]
        print(f"  • Pulled: {pl.get('sessions_inserted', pl.get('sessions_pulled', 0))} new sessions, {pl.get('steps_inserted', pl.get('steps_pulled', 0))} steps")
    return 0
