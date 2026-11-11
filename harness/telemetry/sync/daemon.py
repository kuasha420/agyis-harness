# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Arafat Zahan (@kuasha420)
# Corporate Stewardship & Infrastructure: Purrfect Software Limited (PSL)
# Governed by: ICARO-42/b Ordinance (Company-Supported Personal IP Framework)

"""
Continuous Watch, Incremental Harvest & Sync Daemon (ADR-030).
Uses canonical schema.py/extractor.py upserts, bounded backoff, and atomic health status.
"""

from __future__ import annotations

from datetime import datetime, timezone
import json
import os
from pathlib import Path
import sqlite3
import sys
import threading
import time
from typing import Any, Callable, Dict, List, Optional, Tuple, Union

from harness.telemetry import config
from harness.telemetry.db import compute_telemetry_lag, get_db_connection, iter_brain_transcripts
from harness.telemetry.extractor import ensure_telemetry_schema, extract_session, upsert_session_telemetry
from harness.utils.state import get_state_dir

_MAX_MTIME_CACHE = 2000
_MAX_RECENT_ERRORS = 5
_MAX_SESSION_ERRORS = 20


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def get_sync_status_path(state_dir: Optional[Path] = None) -> Path:
    """Returns path to the atomic daemon health status JSON file."""
    return (Path(state_dir) if state_dir is not None else get_state_dir()) / "telemetry_sync_status.json"


def read_sync_status(state_dir: Optional[Path] = None) -> Dict[str, Any]:
    """Reads latest daemon health status JSON, returning empty dict if unavailable."""
    path = get_sync_status_path(state_dir=state_dir)
    try:
        data = json.loads(path.read_text(encoding="utf-8")) if path.is_file() else {}
        return data if isinstance(data, dict) else {}
    except (json.JSONDecodeError, OSError):
        return {}


def _write_sync_status(payload: Dict[str, Any], state_dir: Optional[Path] = None) -> None:
    path = get_sync_status_path(state_dir=state_dir)
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(f".tmp.{os.getpid()}")
        tmp.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        os.replace(tmp, path)
    except OSError as exc:
        sys.stderr.write(f"[agyis-sync] Failed writing sync status {path}: {exc}\n")

def harvest_local_transcripts(
    db_path: Path, mtime_cache: Dict[str, Tuple[float, int]],
    brain_dir: Optional[Path] = None, error_sink: Optional[List[str]] = None,
) -> int:
    """Incrementally ingests local transcripts into SQLite using canonical schema upserts."""
    modified = sorted(
        ((p, str(p), m, s) for _, p, m, s in iter_brain_transcripts(brain_dir) if mtime_cache.get(str(p)) != (m, s)),
        key=lambda item: item[2],
    )
    if not modified:
        return 0
    conn, stored = get_db_connection(db_path, row_factory=False), 0
    try:
        ensure_telemetry_schema(conn)
        for p, p_str, mtime, size in modified:
            try:
                res = extract_session(p)
                if not res:
                    continue
                upsert_session_telemetry(conn, *res, commit=True)
                mtime_cache.pop(p_str, None)
                mtime_cache[p_str] = (mtime, size)
                if len(mtime_cache) > _MAX_MTIME_CACHE:
                    mtime_cache.pop(next(iter(mtime_cache)), None)
                stored += 1
            except Exception as exc:
                conn.rollback()
                sys.stderr.write(f"[agyis-sync] Harvest failed for {p}: {exc}\n")
                if error_sink is not None:
                    error_sink.append(f"{p.parts[-4]}: {exc}")
    finally:
        conn.close()
    return stored

def watch_and_sync(
    interval_sec: float = 5.0, db_path: Optional[Union[str, Path]] = None,
    endpoint: Optional[str] = None, token: Optional[str] = None,
    run_once: bool = False, max_iterations: Optional[int] = None,
    stop_event: Optional[threading.Event] = None,
    on_iteration: Optional[Callable[[int, Dict[str, Any]], None]] = None,
    brain_dir: Optional[Path] = None, max_backoff_sec: float = 300.0, state_dir: Optional[Path] = None,
) -> Dict[str, Any]:
    """Continuously harvests local transcripts and pushes deltas with exponential backoff."""
    import harness.telemetry.sync as sync_mod

    target_db = config.resolve_db_path(db_path, must_exist=False)
    mtime_cache: Dict[str, Tuple[float, int]] = {}
    errors: List[str] = []
    iterations = total_pushed = total_harvested = consecutive_failures = 0
    last_success_at = last_harvest_at = last_error = None
    try:
        conn = get_db_connection(target_db, row_factory=False)
        try:
            ensure_telemetry_schema(conn)
        finally:
            conn.close()
    except Exception as init_exc:
        last_error = f"Schema init failed: {init_exc}"
        sys.stderr.write(f"[agyis-sync] {last_error}\n")
        errors.append(last_error)

    try:
        while True:
            iterations += 1
            iter_errors: List[str] = []
            harvested = pushed = 0
            push_unconfigured = False
            try:
                harvested = harvest_local_transcripts(target_db, mtime_cache, brain_dir=brain_dir, error_sink=iter_errors)
                total_harvested += harvested
                if harvested > 0:
                    last_harvest_at = _utc_now_iso()
            except Exception as h_exc:
                sys.stderr.write(f"[agyis-sync] Harvest iteration {iterations} error: {h_exc}\n")
                iter_errors.append(f"Harvest iteration {iterations} error: {h_exc}")
            try:
                push_res = sync_mod.push_local_sessions(endpoint=endpoint, token=token, db_path=target_db)
                if isinstance(push_res, dict):
                    pushed = int(push_res.get("sessions_pushed") or 0)
                    total_pushed += pushed
            except ValueError:
                push_unconfigured = True
            except Exception as p_exc:
                sys.stderr.write(f"[agyis-sync] Push iteration {iterations} error: {p_exc}\n")
                iter_errors.append(f"Push iteration {iterations} error: {p_exc}")

            now_iso, base_iv = _utc_now_iso(), max(0.0, float(interval_sec))
            if iter_errors:
                consecutive_failures += 1
                last_error, errors = iter_errors[-1], (errors + iter_errors)[-_MAX_SESSION_ERRORS:]
                sleep_sec = min(max_backoff_sec, max(base_iv, 0.5) * (2 ** min(consecutive_failures, 6)))
                status_str = "error" if (harvested == 0 and not push_unconfigured) else "degraded"
            else:
                consecutive_failures, last_success_at, sleep_sec, status_str = 0, now_iso, base_iv, "ok"

            backoff_val = sleep_sec if consecutive_failures > 0 else 0.0
            payload = {
                "iteration": iterations, "sessions_harvested": harvested, "sessions_pushed": pushed,
                "harvest_errors": len(iter_errors), "push_unconfigured": push_unconfigured,
                "consecutive_failures": consecutive_failures, "backoff_sec": backoff_val,
            }
            _write_sync_status({
                "status": status_str, "updated_at": now_iso, "last_success_at": last_success_at,
                "last_harvest_at": last_harvest_at or last_success_at, "last_harvested_sessions": harvested,
                "harvest_errors": len(iter_errors), "consecutive_failures": consecutive_failures,
                "backoff_sec": backoff_val, "last_error": last_error, "recent_errors": errors[-_MAX_RECENT_ERRORS:],
            }, state_dir=state_dir)
            if on_iteration is not None:
                on_iteration(iterations, payload)
            if run_once or (max_iterations is not None and iterations >= max_iterations):
                break
            if stop_event is not None:
                if stop_event.is_set() or stop_event.wait(timeout=sleep_sec):
                    break
            elif sleep_sec > 0:
                time.sleep(sleep_sec)
    except KeyboardInterrupt:
        pass
    return {
        "status": "completed", "iterations": iterations, "total_sessions_pushed": total_pushed,
        "total_sessions_harvested": total_harvested, "consecutive_failures": consecutive_failures, "errors": errors,
    }


__all__ = [
    "compute_telemetry_lag", "get_sync_status_path", "harvest_local_transcripts",
    "read_sync_status", "watch_and_sync",
]
