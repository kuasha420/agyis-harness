# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Arafat Zahan (@kuasha420)
# Corporate Stewardship & Infrastructure: Purrfect Software Limited (PSL)
# Governed by: ICARO-42/b Ordinance (Company-Supported Personal IP Framework)

"""
Decompiler Query Cache Pre-Warming & Priming Engine (ADR-028, PSL-INV-009, Issue #113).
Pre-populates decompiler query cache on priority functions to guarantee sub-millisecond retrieval.
"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import shutil
import sqlite3
import subprocess
import sys
import time
from typing import Any, Dict, List, Optional

from harness.re.cache import compute_cache_key, get_cache_dir
from harness.re.scaffold import get_dirtyroom_db, get_dirtyroom_root, resolve_binary_path


def get_priority_functions(
    conn: sqlite3.Connection,
    binary_id: Optional[int] = None,
    limit: int = 20,
) -> List[str]:
    """Retrieves top priority functions sorted by export status and function size."""
    if limit <= 0:
        return []
    cursor = conn.cursor()
    functions: List[str] = []
    if binary_id is not None:
        cursor.execute(
            """
            SELECT name FROM functions
            WHERE binary_id = ?
            ORDER BY is_exported DESC, (CASE WHEN size IS NULL THEN 0 ELSE size END) DESC, id ASC
            LIMIT ?
            """,
            (binary_id, limit),
        )
    else:
        cursor.execute(
            """
            SELECT name FROM functions
            ORDER BY is_exported DESC, (CASE WHEN size IS NULL THEN 0 ELSE size END) DESC, id ASC
            LIMIT ?
            """,
            (limit,),
        )
    for row in cursor.fetchall():
        if row[0]:
            functions.append(row[0])
    return functions


def prime_cache(
    top: int = 20,
    symbols_file: Optional[Path] = None,
    binary_name: Optional[str] = None,
    timeout: float = 60.0,
    dry_run: bool = False,
    dirtyroom_root: Optional[Path] = None,
) -> Dict[str, Any]:
    """Pre-warms the decompiler query cache on priority functions."""
    if not symbols_file and top <= 0:
        return {"success": False, "error": "Parameter 'top' must be a positive integer.", "candidates": 0}
    if timeout <= 0:
        return {"success": False, "error": "Parameter 'timeout' must be a positive number.", "candidates": 0}

    root = dirtyroom_root or get_dirtyroom_root()
    if not root:
        return {"success": False, "error": "No active dirtyroom found. Run 'agyis re init' first."}

    bin_path = resolve_binary_path(binary_name, dirtyroom_root=root)
    resolved_bin_name = bin_path.name if bin_path else (Path(binary_name).name if binary_name else "target")

    # Connect to DB to resolve binary_id and symbols
    targets: List[str] = []
    conn = get_dirtyroom_db(root)
    binary_id: Optional[int] = None

    if conn:
        try:
            cursor = conn.cursor()
            if binary_name:
                cursor.execute(
                    "SELECT id, name FROM binaries WHERE name = ? OR name = ? LIMIT 1",
                    (resolved_bin_name, Path(binary_name).name),
                )
                r = cursor.fetchone()
                if r:
                    binary_id = r[0]
                    resolved_bin_name = r[1]
                else:
                    return {
                        "success": False,
                        "error": f"Binary '{resolved_bin_name}' not found in dirtyroom database. Run 'agyis re pre-analyze' first.",
                        "binary": resolved_bin_name,
                        "candidates": 0,
                    }
            elif not bin_path:
                # Mirror cmd_decompile fallback to primary registered binary
                cursor.execute(
                    "SELECT id, name FROM binaries ORDER BY (CASE WHEN name NOT LIKE '%.dll' AND name NOT LIKE '%.so' AND name NOT LIKE '%.dylib' THEN 0 ELSE 1 END), id LIMIT 1"
                )
                r = cursor.fetchone()
                if r:
                    binary_id = r[0]
                    resolved_bin_name = r[1]
                    bin_path = resolve_binary_path(resolved_bin_name, dirtyroom_root=root)
            else:
                cursor.execute("SELECT id FROM binaries WHERE name = ? LIMIT 1", (resolved_bin_name,))
                r = cursor.fetchone()
                if r:
                    binary_id = r[0]

            if not symbols_file:
                targets = get_priority_functions(conn, binary_id=binary_id, limit=top)
        except sqlite3.Error as e:
            return {
                "success": False,
                "error": f"Database error resolving binary/functions: {e}",
            }
        finally:
            conn.close()

    if symbols_file:
        sym_p = Path(symbols_file).resolve()
        if not sym_p.is_file():
            return {"success": False, "error": f"Symbols file not found: {sym_p}"}
        for line in sym_p.read_text(encoding="utf-8").splitlines():
            s = line.strip()
            if s and not s.startswith("#"):
                targets.append(s)

    if targets:
        targets = list(dict.fromkeys(targets))

    if not targets:
        return {
            "success": False,
            "error": f"No priority functions found for binary '{resolved_bin_name}'. Run 'agyis re pre-analyze' first or specify --file.",
            "binary": resolved_bin_name,
            "candidates": 0,
        }

    cache_dir = get_cache_dir(root, "decompile")
    cache_dir.mkdir(parents=True, exist_ok=True)

    rea_bin = shutil.which("rea")
    env = os.environ.copy()
    ghidra_dir = root / "ghidra"
    if ghidra_dir.is_dir():
        env["REA_GHIDRA_PROJECT_DIR"] = str(ghidra_dir)
        gprs = sorted(ghidra_dir.glob("*.gpr"))
        if gprs:
            env["REA_GHIDRA_PROJECT_NAME"] = gprs[0].stem
            env["REA_GHIDRA_PROJECT_PATH"] = str(gprs[0])
    env["AGYIS_DIRTYROOM"] = str(root)
    env["REA_GHIDRA_DIRECT_MOUNT"] = "1"
    env["REA_GHIDRA_PROGRAM_NAME"] = resolved_bin_name

    cached_count = 0
    primed_count = 0
    failed_count = 0
    results: List[Dict[str, Any]] = []

    start_time = time.monotonic()

    for proc in targets:
        cache_key = compute_cache_key(bin_path, resolved_bin_name, proc)
        cache_file = cache_dir / f"{cache_key}.c"

        if cache_file.is_file() and cache_file.stat().st_size > 0:
            cached_count += 1
            results.append({"procedure": proc, "status": "cached", "key": cache_key})
            continue

        if dry_run:
            results.append({"procedure": proc, "status": "would_prime", "key": cache_key})
            continue

        if not rea_bin:
            failed_count += 1
            results.append({"procedure": proc, "status": "failed", "error": "rea CLI not found in PATH"})
            continue

        # Invoke REA decompile
        target_arg = str(bin_path) if bin_path else resolved_bin_name
        cmd = [rea_bin, "decompile", target_arg, "--procedure", str(proc)]
        try:
            proc_res = subprocess.run(
                cmd,
                env=env,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                check=False,
                timeout=timeout,
            )
            if proc_res.returncode == 0 and proc_res.stdout.strip():
                tmp_file = cache_file.with_suffix(f".c.tmp.{os.getpid()}")
                tmp_file.write_text(proc_res.stdout, encoding="utf-8")
                os.replace(tmp_file, cache_file)
                primed_count += 1
                results.append({"procedure": proc, "status": "primed", "key": cache_key})
            else:
                failed_count += 1
                err = proc_res.stderr.strip() or f"exit code {proc_res.returncode}"
                results.append({"procedure": proc, "status": "failed", "error": err})
        except subprocess.TimeoutExpired:
            failed_count += 1
            results.append({"procedure": proc, "status": "timeout", "error": f"Exceeded {timeout}s SLA"})
        except (subprocess.SubprocessError, OSError) as e:
            failed_count += 1
            results.append({"procedure": proc, "status": "failed", "error": str(e)})

    elapsed_s = round(time.monotonic() - start_time, 2)

    success = True
    error_msg: Optional[str] = None
    if not dry_run and failed_count > 0:
        if not rea_bin:
            success = False
            error_msg = "rea CLI not found in PATH"
        elif primed_count == 0 and cached_count == 0:
            success = False
            error_msg = f"All {failed_count} decompilation target(s) failed."

    payload: Dict[str, Any] = {
        "success": success,
        "binary": resolved_bin_name,
        "dry_run": dry_run,
        "candidates": len(targets),
        "already_cached": cached_count,
        "primed": primed_count,
        "failed": failed_count,
        "elapsed_seconds": elapsed_s,
        "results": results,
    }
    if error_msg:
        payload["error"] = error_msg
    return payload


def cmd_prime(args: argparse.Namespace) -> int:
    """CLI dispatcher for 'agyis re prime'."""
    raw_top = getattr(args, "top", None)
    top_arg = 20 if raw_top is None else raw_top
    file_arg = getattr(args, "file", None)
    binary_arg = getattr(args, "binary", None)
    raw_timeout = getattr(args, "timeout", None)
    timeout_arg = 60.0 if raw_timeout is None else raw_timeout
    dry_run = getattr(args, "dry_run", False)

    res = prime_cache(
        top=top_arg,
        symbols_file=Path(file_arg) if file_arg else None,
        binary_name=binary_arg,
        timeout=timeout_arg,
        dry_run=dry_run,
    )

    if getattr(args, "json", False):
        print(json.dumps(res, indent=2))
        return 0 if res.get("success") else 1

    if not res.get("success"):
        print(f"[!] Error: {res.get('error')}", file=sys.stderr)
        return 1

    mode_label = "[DRY-RUN] Cache Priming Preview:" if dry_run else "[+] Decompiler Cache Priming Complete:"
    print(mode_label)
    print(f"    - Target Binary:     {res['binary']}")
    print(f"    - Candidates Scanned: {res['candidates']}")
    print(f"    - Already Cached:    {res['already_cached']}")
    if not dry_run:
        print(f"    - Newly Primed:      {res['primed']}")
        print(f"    - Failed / Timeout:  {res['failed']}")
        print(f"    - Elapsed Time:      {res['elapsed_seconds']}s")
    else:
        would_prime = len([r for r in res.get("results", []) if r.get("status") == "would_prime"])
        print(f"    - Would Prime:       {would_prime}")

    return 0
