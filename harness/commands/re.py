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
import json
from pathlib import Path
import shutil
import sqlite3
import subprocess
import sys
from typing import Any, Dict, List, Optional

from harness.re.patcher import apply_patch, check_patch, revert_patch
from harness.re.preanalyze import find_ghidra_headless, preanalyze_binary
from harness.re.registry import try_register_dirtyroom
from harness.re.scaffold import (
    get_dirtyroom_db,
    get_dirtyroom_root,
    resolve_binary_path,
    scaffold_dirtyroom,
)


def cmd_status(args: argparse.Namespace) -> int:
    """Prints dirtyroom, Ghidra project, database, and REA patch health."""
    root = get_dirtyroom_root()
    reg_warn: Optional[str] = None
    if root and root.is_dir():
        _, reg_warn = try_register_dirtyroom(root)
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
    if reg_warn:
        status_data["registry_warning"] = reg_warn

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
        except (sqlite3.Error, TypeError):
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
    print(f"    - Quarantined: .dirtyroom/ghidra/*.rep/, logs/, cache/")
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
            cols = [col[1] for col in cursor.execute("PRAGMA table_info(rtti_classes)").fetchall()]
            if "class_name" in cols:
                vt_col = "vtable_addr" if "vtable_addr" in cols else "vtable_address"
                cursor.execute(
                    f"SELECT demangled_name, class_name, {vt_col} FROM rtti_classes WHERE demangled_name LIKE ? OR class_name LIKE ? LIMIT ?",
                    (query, query, limit),
                )
                for row in cursor.fetchall():
                    results["rtti_classes"].append({"name": row[0] or row[1], "vtable": row[2]})
            elif "name" in cols:
                vt_col = "vtable_address" if "vtable_address" in cols else "vtable_addr"
                cursor.execute(
                    f"SELECT name, {vt_col} FROM rtti_classes WHERE name LIKE ? LIMIT ?",
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
    def fmt_addr(val: Any) -> str:
        if isinstance(val, int):
            return f"0x{val:016x}"
        return str(val) if val is not None else "-"

    if results["functions"]:
        print("\nFunctions:")
        for fn in results["functions"]:
            print(f"  {fmt_addr(fn['address']):<18} {fn['name']}")
    if results["strings"]:
        print("\nStrings:")
        for s in results["strings"]:
            print(f"  {fmt_addr(s['address']):<18} {s['value']}")
    if results["rtti_classes"]:
        print("\nRTTI Classes:")
        for r in results["rtti_classes"]:
            print(f"  {fmt_addr(r['vtable']):<18} {r['name']}")

    return 0


def cmd_decompile(args: argparse.Namespace) -> int:
    """Decompiles a function or address via active REA bridge daemon or CLI with project acceleration."""
    from harness.re.decompile import execute_cmd_decompile

    conn = get_dirtyroom_db()
    try:
        return execute_cmd_decompile(
            args,
            conn=conn,
            root=get_dirtyroom_root(),
            get_root_fn=get_dirtyroom_root,
            resolve_binary_fn=resolve_binary_path,
            register_fn=try_register_dirtyroom,
        )
    finally:
        if conn:
            try:
                conn.close()
            except (OSError, sqlite3.Error):
                pass


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
    except (subprocess.SubprocessError, OSError) as e:
        print(f"[!] Error executing tshark: {e}", file=sys.stderr)
        return 1


def cmd_disasm(args: argparse.Namespace) -> int:
    """Disassembles instructions at symbol or virtual address via native objdump."""
    objdump = shutil.which("objdump")
    if not objdump:
        print("[!] 'objdump' not found in PATH.", file=sys.stderr)
        return 1

    binary = getattr(args, "binary", None)
    bin_path = resolve_binary_path(binary)
    if not bin_path:
        target_name = binary or "target binary"
        print(f"[!] Error: Binary '{target_name}' not found. Specify --binary or place in .dirtyroom/binaries/.", file=sys.stderr)
        return 1

    target = args.target
    try:
        addr = int(target, 0)
    except ValueError:
        conn = get_dirtyroom_db()
        addr = None
        if conn:
            c = conn.cursor()
            c.execute("SELECT address FROM functions WHERE name = ? LIMIT 1", (target,))
            row = c.fetchone()
            if row:
                addr = row[0]
            conn.close()
        if addr is None:
            print(f"[!] Error: Could not resolve target symbol/address: {target}", file=sys.stderr)
            return 1

    start_addr = addr
    stop_addr = addr + (getattr(args, "bytes", 128) or 128)
    limit = getattr(args, "limit", 50) or 50

    cmd = [
        objdump,
        "-d",
        "-M",
        "intel",
        f"--start-address={hex(start_addr)}",
        f"--stop-address={hex(stop_addr)}",
        str(bin_path),
    ]
    try:
        proc = subprocess.run(cmd, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        if proc.returncode != 0:
            err_msg = (proc.stderr or proc.stdout or "").strip()
            print(
                f"[!] objdump exited with code {proc.returncode}"
                + (f": {err_msg}" if err_msg else ""),
                file=sys.stderr,
            )
            return proc.returncode
        lines = proc.stdout.splitlines()
        code_lines = [
            l
            for l in lines
            if l.strip()
            and not l.startswith("Disassembly of section")
            and not l.endswith(":")
        ]
        print(f"[*] Disassembly for {binary} at {hex(start_addr)}..{hex(stop_addr)}:")
        for l in code_lines[:limit]:
            print(l)
        return 0
    except (subprocess.SubprocessError, OSError) as e:
        print(f"[!] Error executing objdump: {e}", file=sys.stderr)
        return 1


def cmd_addr(args: argparse.Namespace) -> int:
    """Inspects and translates a virtual address, RVA, or file offset with symbol resolution."""
    from harness.re.address import execute_cmd_addr

    conn = get_dirtyroom_db()
    try:
        return execute_cmd_addr(args, conn=conn)
    finally:
        if conn:
            try:
                conn.close()
            except (OSError, sqlite3.Error):
                pass


def cmd_xrefs(args: argparse.Namespace) -> int:
    """Finds cross-references to a virtual address via SQLite pre-analyzed cache and binary scanning."""
    from harness.re.xrefs import execute_cmd_xrefs

    conn = get_dirtyroom_db()
    try:
        return execute_cmd_xrefs(args, conn=conn)
    finally:
        if conn:
            try:
                conn.close()
            except (OSError, sqlite3.Error):
                pass


def main(argv: Optional[List[str]] = None) -> int:
    """CLI dispatcher for 'agyis re'."""
    parser = argparse.ArgumentParser(
        prog="agyis re",
        description="Agyis Cleanroom Reverse Engineering & Dirty-Room Toolsuite (ADR-028, PSL-RE-001)",
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
    p_pre = sub.add_parser("pre-analyze", aliases=["preanalyze"], help="Pre-analyze binary with headless Ghidra")
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
    p_dec.add_argument("--timeout", type=float, default=180.0, help="Decompilation SLA timeout in seconds (default: 180.0)")
    p_dec.add_argument("--no-cache", action="store_true", help="Bypass and refresh decompiler query cache")

    # pcap
    p_pcap = sub.add_parser("pcap", help="Inspect packet capture frames")
    p_pcap.add_argument("file", help="Path to .pcap or .pcapng file")
    p_pcap.add_argument("--limit", type=int, default=50)
    p_pcap.add_argument("--filter", help="Wireshark display filter expression")

    # disasm
    p_disasm = sub.add_parser("disasm", help="Disassemble instructions via native objdump")
    p_disasm.add_argument("target", help="Virtual address (hex) or function name")
    p_disasm.add_argument("--binary", help="Target binary filename or path (auto-detects from .dirtyroom/binaries/ if omitted)")
    p_disasm.add_argument("--bytes", type=int, default=128, help="Number of bytes to disassemble")
    p_disasm.add_argument("--limit", type=int, default=50, help="Max assembly lines to display")

    # xrefs
    p_xrefs = sub.add_parser("xrefs", help="Find cross-references to a virtual address")
    p_xrefs.add_argument("target", help="Target virtual address (hex 0x...)")
    p_xrefs.add_argument("--type", choices=["all", "code", "data"], default="all", help="Xref type filter (default: all)")
    p_xrefs.add_argument("--binary", help="Target binary filename or path (auto-detects from .dirtyroom/binaries/ if omitted)")
    p_xrefs.add_argument("--json", action="store_true", help="Output JSON")

    # addr
    p_addr = sub.add_parser("addr", help="Inspect and translate VA <-> RVA <-> File Offset with symbol resolution")
    p_addr.add_argument("address", help="Address to translate (hex 0x... or decimal)")
    p_addr.add_argument("--binary", help="Target binary filename or path (auto-detects from dirtyroom if omitted)")
    p_addr.add_argument("--json", action="store_true", help="Output JSON")

    # cache (Issue #113)
    p_cache = sub.add_parser("cache", help="Inspect or clear decompiler query cache (Issue #113)")
    p_cache.add_argument("cache_action", choices=["status", "clear"], nargs="?", default="status", help="Cache action (default: status)")
    p_cache.add_argument("--type", choices=["all", "decompile"], default="all", help="Cache category (default: all)")
    p_cache.add_argument("--dry-run", action="store_true", help="Preview files to be cleared without deleting")
    p_cache.add_argument("--json", action="store_true", help="Output JSON")

    # daemon (Issue #113)
    p_daemon = sub.add_parser("daemon", help="Manage background REA MCP bridge daemon (Issue #113)")
    p_daemon.add_argument("daemon_action", choices=["status", "start", "stop"], nargs="?", default="status", help="Daemon action (default: status)")
    p_daemon.add_argument("--foreground", action="store_true", help="Run daemon in foreground")
    p_daemon.add_argument("--json", action="store_true", help="Output JSON")

    # seed
    p_seed = sub.add_parser("seed", help="Ingest PCAP frames into database and link to binary runs")
    p_seed.add_argument("--pcap", help="Path to .pcap or .pcapng file")
    p_seed.add_argument("--binary", help="Target binary filename or path")
    p_seed.add_argument("--limit", type=int, default=None, help="Maximum number of packets to ingest")
    p_seed.add_argument("--json", action="store_true", help="Output JSON")

    # prime
    p_prime = sub.add_parser("prime", help="Pre-warm decompiler query cache on priority functions")
    p_prime.add_argument("--top", type=int, default=20, help="Number of top priority functions to prime (default: 20)")
    p_prime.add_argument("--file", help="Path to symbols file listing priority functions")
    p_prime.add_argument("--binary", help="Target binary filename or path")
    p_prime.add_argument("--timeout", type=float, default=60.0, help="Per-function SLA timeout in seconds (default: 60.0)")
    p_prime.add_argument("--dry-run", action="store_true", help="Preview functions to prime without calling decompiler")
    p_prime.add_argument("--json", action="store_true", help="Output JSON")

    # clean
    p_clean = sub.add_parser("clean", help="Hygiene and maintenance for locks, logs, and database")
    p_clean.add_argument("--locks", action="store_true", help="Remove stale Ghidra .lock files")
    p_clean.add_argument("--logs", action="store_true", help="Prune old log files")
    p_clean.add_argument("--vacuum", action="store_true", help="Vacuum and optimize SQLite symbol database")
    p_clean.add_argument("--force", action="store_true", help="Force lock removal even if Ghidra process detected")
    p_clean.add_argument("--dry-run", action="store_true", help="Preview cleanup actions without deleting files")
    p_clean.add_argument("--json", action="store_true", help="Output JSON")

    args = parser.parse_args(argv)
    if not args.re_cmd or args.re_cmd == "status":
        return cmd_status(args)
    if args.re_cmd == "init":
        return cmd_init(args)
    if args.re_cmd == "patch-rea":
        return cmd_patch_rea(args)
    if args.re_cmd in ("pre-analyze", "preanalyze"):
        return cmd_preanalyze(args)
    if args.re_cmd == "find":
        return cmd_find(args)
    if args.re_cmd == "decompile":
        return cmd_decompile(args)
    if args.re_cmd == "pcap":
        return cmd_pcap(args)
    if args.re_cmd == "disasm":
        return cmd_disasm(args)
    if args.re_cmd == "xrefs":
        return cmd_xrefs(args)
    if args.re_cmd == "addr":
        return cmd_addr(args)
    if args.re_cmd == "cache":
        from harness.re.cache import cmd_cache
        return cmd_cache(args)
    if args.re_cmd == "daemon":
        from harness.re.daemon import cmd_daemon
        return cmd_daemon(args)
    if args.re_cmd == "seed":
        from harness.re.seeding import cmd_seed
        return cmd_seed(args)
    if args.re_cmd == "prime":
        from harness.re.priming import cmd_prime
        return cmd_prime(args)
    if args.re_cmd == "clean":
        from harness.re.hygiene import cmd_clean
        return cmd_clean(args)

    parser.print_help()
    return 1


if __name__ == "__main__":
    sys.exit(main())
