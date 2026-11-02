# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Arafat Zahan (@kuasha420)
# Corporate Stewardship & Infrastructure: Purrfect Software Limited (PSL)
# Governed by: ICARO-42/b Ordinance (Company-Supported Personal IP Framework)

"""
Unified Reverse Engineering & Cleanroom CLI Command (ADR-028, PSL-INV-007, PSL-INV-009).
Provides sub-millisecond SQLite symbol queries, turnkey dirtyroom scaffolding,
Ghidra pre-analysis, and REA MCP patch governance.
"""

import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import shutil
import sqlite3
import subprocess
import sys
from typing import Any, Dict, List, Optional

from harness.re.patcher import apply_patch, check_patch, revert_patch
from harness.re.preanalyze import find_ghidra_headless, preanalyze_binary
from harness.re.scaffold import get_dirtyroom_db, get_dirtyroom_root, scaffold_dirtyroom


def cmd_status(args: argparse.Namespace) -> int:
    """Prints dirtyroom, Ghidra project, database, and REA patch health."""
    root = get_dirtyroom_root()
    patch_info = check_patch()

    status_data: Dict[str, Any] = {
        "dirtyroom_root": str(root) if root else None,
        "dirtyroom_exists": root is not None and root.is_dir(),
        "ghidra_projects": [],
        "binaries": [],
        "metrics": {"functions": 0, "strings": 0, "rtti_classes": 0},
        "rea_patch": patch_info,
        "headless_ghidra": str(find_ghidra_headless()) if find_ghidra_headless() else None,
    }

    if root and (root / "ghidra").is_dir():
        for gpr in (root / "ghidra").glob("*.gpr"):
            status_data["ghidra_projects"].append({
                "name": gpr.stem,
                "path": str(gpr),
                "has_rep": (root / "ghidra" / f"{gpr.stem}.rep").is_dir(),
            })

    conn = get_dirtyroom_db(root)
    if conn:
        try:
            cursor = conn.cursor()
            cursor.execute("SELECT name, sha256, file_size FROM binaries")
            for row in cursor.fetchall():
                status_data["binaries"].append({
                    "name": row[0],
                    "sha256": row[1],
                    "size_mb": round(row[2] / (1024 * 1024), 2),
                })
            cursor.execute("SELECT count(*) FROM functions")
            status_data["metrics"]["functions"] = cursor.fetchone()[0]
            cursor.execute("SELECT count(*) FROM strings")
            status_data["metrics"]["strings"] = cursor.fetchone()[0]
            cursor.execute("SELECT count(*) FROM rtti_classes")
            status_data["metrics"]["rtti_classes"] = cursor.fetchone()[0]
        except Exception:
            pass
        finally:
            conn.close()

    if getattr(args, "json", False):
        print(json.dumps(status_data, indent=2))
        return 0

    print("=== Agyis Cleanroom Reverse Engineering & Dirty-Room Status ===")
    if root:
        print(f"Dirty-Room Root: {root}")
    else:
        print("Dirty-Room Root: [!] Not scaffolded (Run: agyis re init)")

    print(f"\nREA MCP Acceleration Patch (PSL-INV-009):")
    status_label = patch_info["status"].upper()
    if patch_info["status"] == "applied":
        print(f"  Status:  \033[1;32m{status_label}\033[0m - {patch_info['message']}")
    else:
        print(f"  Status:  \033[1;33m{status_label}\033[0m - {patch_info['message']}")
    print(f"  REA Root: {patch_info.get('rea_root') or 'Not found'}")

    print(f"\nGhidra Headless Analyzer:")
    print(f"  Binary:  {status_data['headless_ghidra'] or 'Not found in PATH / GHIDRA_HOME'}")
    if status_data["ghidra_projects"]:
        print("  Projects:")
        for p in status_data["ghidra_projects"]:
            rep_status = "READY" if p["has_rep"] else "GPR ONLY"
            print(f"    - {p['name']} ({rep_status}) -> {p['path']}")
    else:
        print("  Projects: None")

    print(f"\nIndexed Database Metrics:")
    print(f"  Binaries:     {len(status_data['binaries'])}")
    for b in status_data["binaries"]:
        print(f"    - {b['name']}: {b['size_mb']} MB (SHA: {b['sha256'][:10]}...)")
    print(f"  Functions:    {status_data['metrics']['functions']:,}")
    print(f"  Strings:      {status_data['metrics']['strings']:,}")
    print(f"  RTTI Classes: {status_data['metrics']['rtti_classes']:,}")

    return 0


def cmd_init(args: argparse.Namespace) -> int:
    """Scaffolds a turnkey .dirtyroom workspace."""
    target = Path(args.path).resolve() if getattr(args, "path", None) else Path.cwd()
    project_name = getattr(args, "project", None) or "DirtyProject"

    res = scaffold_dirtyroom(target, project_name=project_name)
    if getattr(args, "json", False):
        print(json.dumps(res, indent=2))
        return 0

    print(f"[*] Initialized Dirty-Room at {res['dirtyroom_root']}")
    print(f"    - Database: {res['db_path']} ({'created' if res['db_created'] else 'retained'})")
    print(f"    - Environment: {res['env_file']}")
    print(f"    - Quarantined: .dirtyroom/ghidra/*.rep/, logs/")
    return 0


def cmd_patch_rea(args: argparse.Namespace) -> int:
    """Checks, applies, or reverts the REA acceleration patch."""
    if getattr(args, "apply", False):
        res = apply_patch()
        if getattr(args, "json", False):
            print(json.dumps(res, indent=2))
        else:
            if res.get("success"):
                print(f"[+] {res['message']}")
                for f in res.get("applied_files", []):
                    print(f"    - {f}")
            else:
                print(f"[!] Error: {res.get('error')}", file=sys.stderr)
        return 0 if res.get("success") else 1

    if getattr(args, "revert", False):
        res = revert_patch()
        if getattr(args, "json", False):
            print(json.dumps(res, indent=2))
        else:
            if res.get("success"):
                print(f"[+] {res['message']}")
                for f in res.get("reverted_files", []):
                    print(f"    - {f}")
            else:
                print(f"[!] Error: {res.get('error')}", file=sys.stderr)
        return 0 if res.get("success") else 1

    # Default: check status
    status = check_patch()
    if getattr(args, "json", False):
        print(json.dumps(status, indent=2))
    else:
        print(f"REA MCP Acceleration Status: {status['status'].upper()}")
        print(f"  Message:  {status['message']}")
        print(f"  Package:  {status.get('rea_root')}")
        print(f"  Launcher: {status.get('launcher_path')}")
        print(f"  MCP:      {status.get('mcp_path')}")
    return 0


def cmd_preanalyze(args: argparse.Namespace) -> int:
    """Runs headless Ghidra pre-analysis on a target binary."""
    binary_path = Path(args.binary).resolve()
    project = getattr(args, "project", None)
    overwrite = getattr(args, "overwrite", False)

    print(f"[*] Pre-analyzing binary '{binary_path.name}' with headless Ghidra...")
    res = preanalyze_binary(binary_path, project_name=project, overwrite=overwrite)

    if getattr(args, "json", False):
        print(json.dumps(res, indent=2))
        return 0 if res.get("success") else 1

    if res.get("success"):
        print(f"[+] Pre-analysis complete in project: {res.get('ghidra_project')}")
        print(f"    - Size: {res.get('size_mb')} MB | SHA: {res.get('sha256')[:12]}...")
        print(f"    - Symbols: {res.get('indexed_symbols', {}).get('functions', 0)} functions, {res.get('indexed_symbols', {}).get('strings', 0)} strings")
        print(f"    - Log: {res.get('log_path')}")
        return 0
    else:
        print(f"[!] Pre-analysis failed: {res.get('error')}", file=sys.stderr)
        return 1


def cmd_find(args: argparse.Namespace) -> int:
    """Queries symbols/functions/strings from the SQLite cache (<2ms)."""
    conn = get_dirtyroom_db()
    if not conn:
        print("[!] No active dirtyroom database found. Run 'agyis re init' or check AGYIS_DIRTYROOM.", file=sys.stderr)
        return 1

    query = f"%{args.pattern}%"
    filter_type = getattr(args, "type", "all")
    limit = getattr(args, "limit", 50)
    results: Dict[str, List[Any]] = {"functions": [], "strings": [], "rtti_classes": []}

    try:
        cursor = conn.cursor()
        if filter_type in ("all", "func", "function"):
            cursor.execute(
                "SELECT name, address, size FROM functions WHERE name LIKE ? LIMIT ?",
                (query, limit),
            )
            for row in cursor.fetchall():
                results["functions"].append({"name": row[0], "address": row[1], "size": row[2]})

        if filter_type in ("all", "str", "string"):
            cursor.execute(
                "SELECT value, address, length FROM strings WHERE value LIKE ? LIMIT ?",
                (query, limit),
            )
            for row in cursor.fetchall():
                results["strings"].append({"value": row[0], "address": row[1], "length": row[2]})

        if filter_type in ("all", "rtti"):
            cursor.execute(
                "SELECT name, vtable_address FROM rtti_classes WHERE name LIKE ? LIMIT ?",
                (query, limit),
            )
            for row in cursor.fetchall():
                results["rtti_classes"].append({"name": row[0], "vtable": row[1]})
    finally:
        conn.close()

    if getattr(args, "json", False):
        print(json.dumps(results, indent=2))
        return 0

    total_hits = len(results["functions"]) + len(results["strings"]) + len(results["rtti_classes"])
    print(f"=== Query '{args.pattern}' ({total_hits} matches) ===")
    if results["functions"]:
        print("\nFunctions:")
        for fn in results["functions"]:
            print(f"  {fn['address']:<18} {fn['name']}")
    if results["strings"]:
        print("\nStrings:")
        for s in results["strings"]:
            print(f"  {s['address']:<18} {s['value']}")
    if results["rtti_classes"]:
        print("\nRTTI Classes:")
        for r in results["rtti_classes"]:
            print(f"  {r['vtable']:<18} {r['name']}")

    return 0


def cmd_decompile(args: argparse.Namespace) -> int:
    """Decompiles a function or address via REA CLI with project acceleration."""
    rea_bin = shutil.which("rea")
    if not rea_bin:
        print("[!] 'rea' CLI not found in PATH.", file=sys.stderr)
        return 1

    proc = args.procedure
    binary = getattr(args, "binary", None)
    if not binary:
        # Check if there is a binary in dirtyroom
        conn = get_dirtyroom_db()
        if conn:
            try:
                cur = conn.cursor()
                cur.execute("SELECT name FROM binaries LIMIT 1")
                row = cur.fetchone()
                if row:
                    binary = row[0]
            except Exception:
                pass
            finally:
                conn.close()

    if not binary:
        print("[!] No binary specified and no binary registered in dirtyroom. Use --binary <name>.", file=sys.stderr)
        return 1

    cmd = [rea_bin, "decompile", str(binary), "--procedure", str(proc)]
    try:
        res = subprocess.run(cmd, check=False)
        return res.returncode
    except Exception as e:
        print(f"[!] Error executing rea decompile: {e}", file=sys.stderr)
        return 1


def cmd_pcap(args: argparse.Namespace) -> int:
    """Inspects packet capture summary via tshark."""
    tshark = shutil.which("tshark")
    if not tshark:
        print("[!] 'tshark' not found in PATH.", file=sys.stderr)
        return 1

    pcap_path = Path(args.file).resolve()
    if not pcap_path.is_file():
        print(f"[!] PCAP file not found: {pcap_path}", file=sys.stderr)
        return 1

    cmd = [tshark, "-r", str(pcap_path), "-c", str(getattr(args, "limit", 50))]
    if getattr(args, "filter", None):
        cmd.extend(["-Y", args.filter])

    try:
        res = subprocess.run(cmd, check=False)
        return res.returncode
    except Exception as e:
        print(f"[!] Error executing tshark: {e}", file=sys.stderr)
        return 1


def main(argv: Optional[List[str]] = None) -> int:
    """CLI dispatcher for 'agyis re'."""
    parser = argparse.ArgumentParser(
        prog="agyis re",
        description="Agyis Cleanroom Reverse Engineering & Dirty-Room Toolsuite (ADR-028, PSL-INV-009)",
    )
    sub = parser.add_subparsers(dest="re_cmd", help="RE subcommand")

    # status
    p_status = sub.add_parser("status", help="Inspect dirtyroom and REA patch health")
    p_status.add_argument("--json", action="store_true", help="Output JSON")

    # init
    p_init = sub.add_parser("init", help="Scaffold turnkey .dirtyroom workspace")
    p_init.add_argument("path", nargs="?", default=".", help="Target workspace path")
    p_init.add_argument("--project", default="DirtyProject", help="Ghidra project name")
    p_init.add_argument("--json", action="store_true", help="Output JSON")

    # patch-rea
    p_patch = sub.add_parser("patch-rea", help="Manage REA Ghidra acceleration patch")
    p_patch.add_argument("--apply", action="store_true", help="Apply acceleration patch")
    p_patch.add_argument("--revert", action="store_true", help="Revert acceleration patch")
    p_patch.add_argument("--check", action="store_true", help="Check patch status (default)")
    p_patch.add_argument("--json", action="store_true", help="Output JSON")

    # pre-analyze
    p_pre = sub.add_parser("pre-analyze", help="Pre-analyze binary with headless Ghidra")
    p_pre.add_argument("binary", help="Target binary path (PE/ELF/Mach-O)")
    p_pre.add_argument("--project", help="Ghidra project name")
    p_pre.add_argument("--overwrite", action="store_true", help="Overwrite existing project entry")
    p_pre.add_argument("--json", action="store_true", help="Output JSON")

    # find
    p_find = sub.add_parser("find", help="Query symbols/functions/strings from cache")
    p_find.add_argument("pattern", help="Search pattern or wildcard")
    p_find.add_argument("--type", choices=["all", "func", "str", "rtti"], default="all")
    p_find.add_argument("--limit", type=int, default=50)
    p_find.add_argument("--json", action="store_true", help="Output JSON")

    # decompile
    p_dec = sub.add_parser("decompile", help="Decompile procedure with project acceleration")
    p_dec.add_argument("procedure", help="Function name or hex address")
    p_dec.add_argument("--binary", help="Target binary filename")

    # pcap
    p_pcap = sub.add_parser("pcap", help="Inspect packet capture frames")
    p_pcap.add_argument("file", help="Path to .pcap or .pcapng file")
    p_pcap.add_argument("--limit", type=int, default=50)
    p_pcap.add_argument("--filter", help="Wireshark display filter expression")

    args = parser.parse_args(argv)
    if not args.re_cmd or args.re_cmd == "status":
        return cmd_status(args)
    if args.re_cmd == "init":
        return cmd_init(args)
    if args.re_cmd == "patch-rea":
        return cmd_patch_rea(args)
    if args.re_cmd == "pre-analyze":
        return cmd_preanalyze(args)
    if args.re_cmd == "find":
        return cmd_find(args)
    if args.re_cmd == "decompile":
        return cmd_decompile(args)
    if args.re_cmd == "pcap":
        return cmd_pcap(args)

    parser.print_help()
    return 1


if __name__ == "__main__":
    sys.exit(main())
