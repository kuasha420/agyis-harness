# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Arafat Zahan (@kuasha420)
# Corporate Stewardship & Infrastructure: Purrfect Software Limited (PSL)
# Governed by: ICARO-42/b Ordinance (Company-Supported Personal IP Framework)

"""
Background sync daemon watcher (ADR-030).
"""

from __future__ import annotations

from pathlib import Path
import time
from typing import Any, Callable, Dict, List, Optional, Union


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
                import harness.telemetry.sync as sync_mod

                push_res = sync_mod.push_local_sessions(
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
