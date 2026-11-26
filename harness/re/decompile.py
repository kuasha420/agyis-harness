# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Arafat Zahan (@kuasha420)
# Corporate Stewardship & Infrastructure: Purrfect Software Limited (PSL)
# Governed by: ICARO-42/b Ordinance (Company-Supported Personal IP Framework)

"""
RE decompilation pipeline helpers (ADR-028, PSL-INV-009).
Routes decompile queries through Tier 1 disk cache -> active rea_mcp.sock daemon -> direct rea CLI.
"""

from __future__ import annotations

import argparse
import os
from pathlib import Path
import shutil
import sqlite3
import subprocess
import sys
from typing import Any, Callable, Dict, Optional

from harness.re.cache import compute_cache_key, record_cache_hit, record_cache_miss
from harness.re.daemon import get_socket_file, query_daemon_tool
from harness.re.registry import try_register_dirtyroom
from harness.re.scaffold import get_dirtyroom_root, resolve_binary_path


def _extract_mcp_text(result: Optional[Dict[str, Any]]) -> Optional[str]:
    """Extract non-empty pseudocode text from an MCP tools/call result object."""
    if not isinstance(result, dict) or result.get("isError"):
        return None
    content = result.get("content")
    if isinstance(content, list):
        texts = [
            item.get("text", "")
            for item in content
            if isinstance(item, dict) and isinstance(item.get("text"), str)
        ]
        joined = "\n".join(t for t in texts if t).strip()
        if joined:
            return joined
    for key in ("pseudo_code", "pseudocode", "code", "text"):
        val = result.get(key)
        if isinstance(val, str) and val.strip():
            return val
    return None


def decompile_via_daemon(
    target_path: str,
    procedure: str,
    root: Optional[Path] = None,
    timeout: float = 10.0,
) -> Optional[str]:
    """Query an active rea_mcp.sock bridge daemon for procedure pseudocode, else return None."""
    sock_path = get_socket_file(root)
    if sock_path.is_symlink() or not sock_path.exists():
        return None
    req_timeout = min(max(float(timeout), 1.0), 10.0)
    open_res = query_daemon_tool(
        "open_binary",
        {"path": str(Path(target_path).resolve())},
        root=root,
        timeout=req_timeout,
    )
    if open_res is None:
        return None
    if open_res.get("isError"):
        sys.stderr.write(f"[!] Warning: REA daemon open_binary reported error for {target_path}; falling back to CLI.\n")
        return None
    proc_res = query_daemon_tool(
        "procedure_pseudo_code",
        {"procedure": str(procedure), "detail": "complete"},
        root=root,
        timeout=req_timeout,
    )
    if proc_res is None:
        return None
    if proc_res.get("isError"):
        sys.stderr.write(f"[!] Warning: REA daemon procedure_pseudo_code reported error for {procedure}; falling back to CLI.\n")
        return None
    text_out = _extract_mcp_text(proc_res)
    if not text_out:
        sys.stderr.write(f"[!] Warning: REA daemon returned empty pseudocode for {procedure}; falling back to CLI.\n")
    return text_out


def _resolve_proc_and_binary(
    proc: Any,
    binary: Optional[str],
    conn: Optional[sqlite3.Connection],
) -> tuple[Any, Optional[str], bool]:
    """Resolve interior numeric address & default binary from a single dirtyroom SQLite connection."""
    binary_in_db = False
    try:
        proc_val = int(proc.strip(), 0) if isinstance(proc, str) else int(proc)
        is_numeric = True
    except (ValueError, TypeError):
        proc_val = None
        is_numeric = False

    if conn:
        try:
            c = conn.cursor()
            if is_numeric and proc_val is not None:
                c.execute(
                    "SELECT name, address, size FROM functions WHERE address <= ? AND address + size > ? ORDER BY address DESC LIMIT 1",
                    (proc_val, proc_val),
                )
                fn_row = c.fetchone()
                if not fn_row:
                    c.execute(
                        "SELECT name, address, size FROM functions WHERE address = ? LIMIT 1",
                        (proc_val,),
                    )
                    fn_row = c.fetchone()
                if fn_row:
                    resolved_name = fn_row[0]
                    base_addr = int(fn_row[1])
                    delta = proc_val - base_addr
                    print(f"[*] Auto-resolved interior address 0x{proc_val:x} to procedure {resolved_name} (+0x{delta:x}).")
                    proc = resolved_name

            if not binary:
                c.execute(
                    "SELECT name FROM binaries ORDER BY (CASE WHEN name NOT LIKE '%.dll' AND name NOT LIKE '%.so' AND name NOT LIKE '%.dylib' THEN 0 ELSE 1 END), id LIMIT 1"
                )
                row = c.fetchone()
                if row:
                    binary = row[0]

            check_target = Path(binary).name if binary else None
            if check_target:
                c.execute("SELECT 1 FROM binaries WHERE name = ? LIMIT 1", (check_target,))
                if c.fetchone():
                    binary_in_db = True
        except sqlite3.Error as exc:
            sys.stderr.write(f"[!] Warning: Dirtyroom SQLite lookup failed: {exc}\n")

    return proc, binary, binary_in_db


def _has_preanalyzed_gpr(
    bin_path: Path,
    binary_in_db: bool,
    get_root_fn: Callable[..., Optional[Path]],
) -> bool:
    """Return True if a Ghidra .gpr project exists covering bin_path (PSL-INV-009 §1)."""
    cand_dirs = []
    env_dir = os.environ.get("REA_GHIDRA_PROJECT_DIR")
    if env_dir:
        cand_dirs.append(Path(env_dir))
    root = get_root_fn(bin_path.parent) or get_root_fn(Path(os.getcwd()))
    if root:
        cand_dirs.append(root / "ghidra")
        if root.parent:
            cand_dirs.append(root.parent / "dirtyroom" / "ghidra")
    cwd_p = Path(os.getcwd())
    cand_dirs.extend([cwd_p / ".dirtyroom" / "ghidra", cwd_p / "dirtyroom" / "ghidra"])
    for cd in cand_dirs:
        if not cd.is_dir():
            continue
        gprs = list(cd.glob("*.gpr"))
        if not gprs:
            continue
        try:
            if bin_path.resolve().is_relative_to(cd.parent.resolve()) or (
                root and bin_path.resolve().is_relative_to(root.parent.resolve())
            ):
                return True
        except (ValueError, OSError):
            pass
        if any(g.stem.lower() == bin_path.stem.lower() for g in gprs) or binary_in_db:
            return True
        if env_dir and cd == Path(env_dir):
            return True
    return False


def execute_cmd_decompile(
    args: argparse.Namespace,
    conn: Optional[sqlite3.Connection] = None,
    root: Optional[Path] = None,
    get_root_fn: Callable[..., Optional[Path]] = get_dirtyroom_root,
    resolve_binary_fn: Callable[[str], Optional[Path]] = resolve_binary_path,
    register_fn: Callable[[Path], Any] = try_register_dirtyroom,
) -> int:
    """Execute decompilation via cache -> rea_mcp.sock daemon -> direct rea CLI."""
    proc, binary, binary_in_db = _resolve_proc_and_binary(
        args.procedure,
        getattr(args, "binary", None),
        conn,
    )
    if not binary:
        print("[!] No binary specified and no binary registered in dirtyroom. Use --binary <name>.", file=sys.stderr)
        return 1

    bin_path = resolve_binary_fn(binary)
    if not bin_path and Path(binary).is_file():
        bin_path = Path(binary)

    if bin_path and bin_path.is_file():
        file_size = bin_path.stat().st_size
        if file_size > 10 * 1024 * 1024 and not _has_preanalyzed_gpr(bin_path, binary_in_db, get_root_fn):
            size_mb = file_size / (1024 * 1024)
            print(
                f"[!] PSL-INV-009 §1 Violation: Target binary '{binary}' exceeds 10MB ({size_mb:.1f}MB) and is not pre-analyzed. Run 'agyis re preanalyze {binary}' first to prevent decompiler timeout.",
                file=sys.stderr,
            )
            return 1

    env = os.environ.copy()
    if root:
        if root.is_dir():
            register_fn(root)
        ghidra_dir = root / "ghidra"
        if ghidra_dir.is_dir():
            env["REA_GHIDRA_PROJECT_DIR"] = str(ghidra_dir)
            gprs = list(ghidra_dir.glob("*.gpr"))
            if gprs:
                env["REA_GHIDRA_PROJECT_NAME"] = gprs[0].stem
                env["REA_GHIDRA_PROJECT_PATH"] = str(gprs[0])
        env["AGYIS_DIRTYROOM"] = str(root)

    target_target = str(bin_path) if bin_path else str(binary)
    if "REA_GHIDRA_DIRECT_MOUNT" not in env:
        env["REA_GHIDRA_DIRECT_MOUNT"] = "1"
    if "REA_GHIDRA_PROGRAM_NAME" not in env:
        env["REA_GHIDRA_PROGRAM_NAME"] = Path(target_target).name

    no_cache = getattr(args, "no_cache", False)
    cache_file = None
    cache_key = compute_cache_key(bin_path, Path(target_target).name, str(proc))

    if root:
        cache_dir = root / "cache" / "decompile"
        cache_dir.mkdir(parents=True, exist_ok=True)
        cache_file = cache_dir / f"{cache_key}.c"
        if not no_cache and cache_file.is_file() and cache_file.stat().st_size > 0:
            try:
                sys.stdout.write(cache_file.read_text(encoding="utf-8"))
                sys.stdout.flush()
                record_cache_hit(root, "decompile", key=cache_key)
                return 0
            except OSError:
                pass
        record_cache_miss(root, "decompile", key=cache_key)

    timeout_s = getattr(args, "timeout", None) or 180.0
    daemon_output = decompile_via_daemon(
        target_target,
        str(proc),
        root=root,
        timeout=min(float(timeout_s), 10.0),
    )
    if daemon_output:
        text_out = daemon_output if daemon_output.endswith("\n") else daemon_output + "\n"
        sys.stdout.write(text_out)
        sys.stdout.flush()
        if cache_file:
            try:
                cache_file.write_text(text_out, encoding="utf-8")
            except OSError:
                pass
        return 0

    rea_bin = shutil.which("rea")
    if not rea_bin:
        print("[!] 'rea' CLI not found in PATH.", file=sys.stderr)
        return 1

    cmd = [rea_bin, "decompile", target_target, "--procedure", str(proc)]
    if "REA_GHIDRA_STARTUP_TIMEOUT_MS" not in env:
        env["REA_GHIDRA_STARTUP_TIMEOUT_MS"] = str(int(timeout_s * 1000))

    try:
        res = subprocess.run(cmd, env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, check=False, timeout=timeout_s)
        if isinstance(res.stdout, str):
            sys.stdout.write(res.stdout)
            sys.stdout.flush()
            if res.returncode == 0 and cache_file:
                try:
                    cache_file.write_text(res.stdout, encoding="utf-8")
                except OSError:
                    pass
        if isinstance(res.stderr, str):
            sys.stderr.write(res.stderr)
            sys.stderr.flush()
        return res.returncode
    except subprocess.TimeoutExpired as e:
        actual_sla = getattr(e, "timeout", None) or timeout_s
        print(f"[!] PSL-INV-009 §2 Benchmark Violation: Decompilation exceeded {actual_sla:.0f}s SLA (potential cache bypass).", file=sys.stderr)
        return 1
    except (subprocess.SubprocessError, OSError) as e:
        print(f"[!] Error executing rea decompile: {e}", file=sys.stderr)
        return 1
