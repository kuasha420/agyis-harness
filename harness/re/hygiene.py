# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Arafat Zahan (@kuasha420)
# Corporate Stewardship & Infrastructure: Purrfect Software Limited (PSL)
# Governed by: ICARO-42/b Ordinance (Company-Supported Personal IP Framework)

"""
Dirty-Room Hygiene, Orphan Lock Pruning & Database Optimization Engine (ADR-028, PSL-INV-009).
Safely purges stale Ghidra .lock files, prunes old logs, and reclaims SQLite storage via VACUUM.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sqlite3
import sys
from typing import Any, Dict, List, Optional

from harness.re.cache import _format_size
from harness.re.daemon import _is_pid_alive, _read_pid
from harness.re.scaffold import get_dirtyroom_root


def _safe_stat_size(p: Path) -> int:
    try:
        return p.stat().st_size
    except (OSError, PermissionError):
        return 0


def _is_ghidra_running() -> bool:
    """Checks if any active Ghidra or analyzeHeadless process is running on the host."""
    try:
        proc_dir = Path("/proc")
        if not proc_dir.is_dir():
            return False
        self_pid = ""
        try:
            self_pid = (proc_dir / "self").resolve().name
        except (OSError, PermissionError):
            self_pid = ""
        for pid_entry in proc_dir.iterdir():
            if not pid_entry.name.isdigit() or pid_entry.name == self_pid:
                continue
            cmdline_file = pid_entry / "cmdline"
            if cmdline_file.is_file():
                try:
                    cmdline = cmdline_file.read_bytes().replace(b"\x00", b" ").decode("latin-1", errors="ignore")
                    if "analyzeHeadless" in cmdline or "ghidraRun" in cmdline or "GhidraLauncher" in cmdline:
                        return True
                except (OSError, PermissionError):
                    continue
    except (OSError, PermissionError):
        return False
    return False


def clean_locks(
    dirtyroom_root: Path,
    dry_run: bool = False,
    force: bool = False,
) -> Dict[str, Any]:
    """Finds and safely purges stale Ghidra lock files (*.lock, *.lock~, .lock*)."""
    ghidra_dir = dirtyroom_root / "ghidra"
    if not ghidra_dir.is_dir():
        return {"count": 0, "bytes": 0, "files": [], "ghidra_running": False}

    ghidra_running = _is_ghidra_running()
    if ghidra_running and not force:
        return {
            "count": 0,
            "bytes": 0,
            "files": [],
            "ghidra_running": True,
            "skipped_reason": "Active Ghidra process detected. Lock files preserved for safety (override with force).",
        }

    lock_files: List[Path] = []
    patterns = ["*.lock", "*.lock~", ".lock*", "*db.lock", "~*.lock"]
    for pat in patterns:
        for p in ghidra_dir.rglob(pat):
            if p.is_file():
                lock_files.append(p)

    # Deduplicate paths
    unique_locks = sorted(list(set(lock_files)))

    if dry_run:
        total_bytes = sum(_safe_stat_size(p) for p in unique_locks if p.is_file())
        return {
            "count": len(unique_locks),
            "bytes": total_bytes,
            "files": [str(p) for p in unique_locks],
            "ghidra_running": ghidra_running,
        }

    removed_files: List[str] = []
    removed_bytes = 0
    errors: List[str] = []
    for p in unique_locks:
        sz = _safe_stat_size(p)
        try:
            p.unlink(missing_ok=True)
            removed_files.append(str(p))
            removed_bytes += sz
        except OSError as e:
            errors.append(f"{p}: {e}")

    res: Dict[str, Any] = {
        "count": len(removed_files),
        "bytes": removed_bytes,
        "files": removed_files,
        "ghidra_running": ghidra_running,
    }
    if errors:
        res["failed_count"] = len(errors)
        res["errors"] = errors
    return res


def clean_logs(
    dirtyroom_root: Path,
    dry_run: bool = False,
) -> Dict[str, Any]:
    """Prunes old logs and temporary trace files, preserving active daemon logs."""
    logs_dir = dirtyroom_root / "logs"
    if not logs_dir.is_dir():
        return {"count": 0, "bytes": 0, "files": []}

    # Identify active daemon PID
    daemon_pid = _read_pid(dirtyroom_root)
    preserve_names = set()
    if daemon_pid and _is_pid_alive(daemon_pid):
        preserve_names.add("rea_daemon.log")
        preserve_names.add("rea_daemon.pid")
        preserve_names.add("rea_daemon_status.json")

    candidates: List[Path] = []
    for pat in ["*.log", "*.tmp"]:
        for p in logs_dir.rglob(pat):
            if p.is_file() and p.name not in preserve_names and not p.name.startswith("."):
                candidates.append(p)

    unique_logs = sorted(list(set(candidates)))

    if dry_run:
        total_bytes = sum(_safe_stat_size(p) for p in unique_logs if p.is_file())
        return {
            "count": len(unique_logs),
            "bytes": total_bytes,
            "files": [str(p) for p in unique_logs],
        }

    removed_files: List[str] = []
    removed_bytes = 0
    errors: List[str] = []
    for p in unique_logs:
        sz = _safe_stat_size(p)
        try:
            p.unlink(missing_ok=True)
            removed_files.append(str(p))
            removed_bytes += sz
        except OSError as e:
            errors.append(f"{p}: {e}")

    res: Dict[str, Any] = {
        "count": len(removed_files),
        "bytes": removed_bytes,
        "files": removed_files,
    }
    if errors:
        res["failed_count"] = len(errors)
        res["errors"] = errors
    return res


def vacuum_database(
    dirtyroom_root: Path,
    dry_run: bool = False,
) -> Dict[str, Any]:
    """Runs VACUUM, REINDEX, and ANALYZE on SQLite symbol database."""
    candidates = [
        dirtyroom_root / "symbols" / "dirtyroom.db",
        dirtyroom_root / "symbols" / "paladins_symbols.sqlite",
        dirtyroom_root / "symbols.db",
        dirtyroom_root / "symbols.sqlite",
    ]
    target_dbs = [c for c in candidates if c.is_file() and _safe_stat_size(c) > 0]
    if not target_dbs:
        return {
            "success": False,
            "error": "No symbols database found to vacuum.",
            "not_found": True,
            "reclaimed_bytes": 0,
        }

    total_size_before = sum(_safe_stat_size(c) for c in target_dbs)
    db_paths_str = ", ".join(str(c) for c in target_dbs)

    if dry_run:
        return {
            "success": True,
            "db_path": db_paths_str,
            "size_before": total_size_before,
            "size_after": total_size_before,
            "reclaimed_bytes": 0,
            "reclaimed_human": "0 B",
            "dry_run": True,
        }

    for db_file in target_dbs:
        try:
            # Set isolation_level=None for autocommit mode so VACUUM runs outside any transaction
            conn = sqlite3.connect(db_file, isolation_level=None)
            try:
                conn.execute("PRAGMA wal_checkpoint(TRUNCATE);")
                conn.execute("PRAGMA optimize;")
                conn.execute("VACUUM;")
                conn.execute("REINDEX;")
                conn.execute("ANALYZE;")
            finally:
                conn.close()
        except (sqlite3.Error, OSError) as e:
            return {
                "success": False,
                "db_path": str(db_file),
                "error": f"VACUUM execution failed on {db_file.name}: {e}",
                "reclaimed_bytes": 0,
            }

    total_size_after = sum(_safe_stat_size(c) for c in target_dbs)
    reclaimed = max(0, total_size_before - total_size_after)

    return {
        "success": True,
        "db_path": db_paths_str,
        "size_before": total_size_before,
        "size_after": total_size_after,
        "reclaimed_bytes": reclaimed,
        "reclaimed_human": _format_size(reclaimed),
        "dry_run": False,
    }


def clean_dirtyroom(
    locks: bool = False,
    logs: bool = False,
    vacuum: bool = False,
    dry_run: bool = False,
    force: bool = False,
    dirtyroom_root: Optional[Path] = None,
) -> Dict[str, Any]:
    """Orchestrates comprehensive dirtyroom hygiene and space reclamation."""
    root = dirtyroom_root or get_dirtyroom_root()
    if not root:
        return {"success": False, "error": "No active dirtyroom found. Run 'agyis re init' first."}

    # If no specific scope was selected, perform all cleanups
    do_all = not (locks or logs or vacuum)
    do_locks = locks or do_all
    do_logs = logs or do_all
    do_vacuum = vacuum or do_all

    report: Dict[str, Any] = {
        "success": True,
        "dirtyroom_root": str(root),
        "dry_run": dry_run,
        "locks": None,
        "logs": None,
        "vacuum": None,
        "total_reclaimed_bytes": 0,
    }

    total_bytes = 0

    if do_locks:
        lock_res = clean_locks(root, dry_run=dry_run, force=force)
        report["locks"] = lock_res
        total_bytes += lock_res.get("bytes", 0)
        if lock_res.get("failed_count", 0) > 0:
            report["success"] = False
            report["error"] = f"Failed to remove {lock_res['failed_count']} lock file(s): {lock_res['errors'][0]}"

    if do_logs:
        log_res = clean_logs(root, dry_run=dry_run)
        report["logs"] = log_res
        total_bytes += log_res.get("bytes", 0)
        if log_res.get("failed_count", 0) > 0:
            report["success"] = False
            if "error" not in report:
                report["error"] = f"Failed to prune {log_res['failed_count']} log file(s): {log_res['errors'][0]}"

    if do_vacuum:
        vac_res = vacuum_database(root, dry_run=dry_run)
        report["vacuum"] = vac_res
        total_bytes += vac_res.get("reclaimed_bytes", 0)
        if not vac_res.get("success"):
            is_missing_db = vac_res.get("not_found", False) or (
                "No symbols database found" in str(vac_res.get("error", ""))
            )
            if vacuum or not is_missing_db:
                report["success"] = False
                report["error"] = vac_res.get("error") or "Database vacuum failed."

    report["total_reclaimed_bytes"] = total_bytes
    report["total_reclaimed_human"] = _format_size(total_bytes)
    return report


def cmd_clean(args: argparse.Namespace) -> int:
    """CLI dispatcher for 'agyis re clean'."""
    locks = getattr(args, "locks", False)
    logs = getattr(args, "logs", False)
    vacuum = getattr(args, "vacuum", False)
    dry_run = getattr(args, "dry_run", False)
    force = getattr(args, "force", False)

    res = clean_dirtyroom(
        locks=locks,
        logs=logs,
        vacuum=vacuum,
        dry_run=dry_run,
        force=force,
    )

    if getattr(args, "json", False):
        print(json.dumps(res, indent=2))
        return 0 if res.get("success") else 1

    if not res.get("success"):
        print(f"[!] Error: {res.get('error')}", file=sys.stderr)
        return 1

    prefix = "[DRY-RUN] Dirty-Room Hygiene Preview:" if dry_run else "[+] Dirty-Room Hygiene Complete:"
    print(prefix)
    print(f"    - Dirty-Room Root: {res['dirtyroom_root']}")

    if res.get("locks"):
        l = res["locks"]
        if l.get("skipped_reason"):
            print(f"    - Ghidra Locks:    [SKIPPED] {l['skipped_reason']}")
        else:
            action = "Would remove" if dry_run else "Removed"
            print(f"    - Ghidra Locks:    {action} {l['count']} stale lock file(s) ({_format_size(l['bytes'])})")

    if res.get("logs"):
        lg = res["logs"]
        action = "Would prune" if dry_run else "Pruned"
        print(f"    - Log Files:       {action} {lg['count']} file(s) ({_format_size(lg['bytes'])})")

    if res.get("vacuum"):
        v = res["vacuum"]
        if v.get("success"):
            action = "Target" if dry_run else "Optimized"
            print(f"    - SQLite Database: {action} {v.get('db_path')} (Reclaimed: {v.get('reclaimed_human', '0 B')})")
        else:
            print(f"    - SQLite Database: [!] {v.get('error')}")

    print(f"    - Total Reclaimed: {res['total_reclaimed_human']}")
    return 0
