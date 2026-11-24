# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Arafat Zahan (@kuasha420)
# Corporate Stewardship & Infrastructure: Purrfect Software Limited (PSL)
# Governed by: ICARO-42/b Ordinance (Company-Supported Personal IP Framework)

"""
Headless Ghidra Pre-Analysis Runner & Symbol Extractor (ADR-028, PSL-RE-001).
Populates pre-analyzed Ghidra project repositories (*.gpr, *.rep) so that REA
can decompile targeted procedures in <2s with -noanalysis -readOnly.
"""

from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import sqlite3
import subprocess
import sys
import tempfile
from typing import Any, Dict, Iterator, List, Optional, Tuple

from harness.re.address import detect_binary_architecture, parse_binary_sections
from harness.re.registry import resolve_nondot_ghidra_dir, try_register_dirtyroom
from harness.re.scaffold import get_dirtyroom_db, get_dirtyroom_root, scaffold_dirtyroom

_HEX_TOK_RE = re.compile(r"^[0-9a-fA-F]+$")


def find_ghidra_headless() -> Optional[Path]:
    """Discovers analyzeHeadless binary in PATH or standard installations."""
    cand = shutil.which("analyzeHeadless")
    if cand:
        return Path(cand).resolve()

    ghidra_home = os.environ.get("GHIDRA_INSTALL_DIR") or os.environ.get("GHIDRA_HOME")
    if ghidra_home:
        cand_path = Path(ghidra_home) / "support" / "analyzeHeadless"
        if cand_path.is_file() and os.access(cand_path, os.X_OK):
            return cand_path.resolve()

    for base in [
        Path("/opt/ghidra/support/analyzeHeadless"),
        Path("/usr/share/ghidra/support/analyzeHeadless"),
        Path.home() / ".local" / "share" / "ghidra" / "support" / "analyzeHeadless",
    ]:
        if base.is_file() and os.access(base, os.X_OK):
            return base.resolve()

    for cand_dir in Path.home().glob("ghidra_*"):
        if cand_dir.is_dir():
            cand_bin = cand_dir / "support" / "analyzeHeadless"
            if cand_bin.is_file() and os.access(cand_bin, os.X_OK):
                return cand_bin.resolve()

    return None


def calculate_file_sha256(path: Path) -> str:
    """Calculates SHA-256 digest of binary efficiently."""
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while chunk := f.read(65536):
            h.update(chunk)
    return h.hexdigest()


def _parse_objdump_functions(output: str, is_exported_flag: int) -> List[Tuple[int, str, int, int]]:
    """Extracts (addr_int, name, size_int, is_exported) from objdump -t/-T lines."""
    entries: List[Tuple[int, str, int, int]] = []
    for line in output.splitlines():
        if "*UND*" in line:
            continue
        parts = line.split()
        if len(parts) < 6 or not _HEX_TOK_RE.match(parts[0]):
            continue
        flags = set(parts[1:-2])
        if "F" not in flags and "DF" not in flags:
            continue
        try:
            addr_int = int(parts[0], 16)
        except ValueError:
            continue
        if addr_int == 0:
            continue
        name = parts[-1].strip()
        if not name:
            continue
        size_int = 0
        if len(parts) >= 2 and _HEX_TOK_RE.match(parts[-2]):
            try:
                size_int = int(parts[-2], 16)
            except ValueError:
                size_int = 0
        elif len(parts) >= 3 and _HEX_TOK_RE.match(parts[-3]):
            try:
                size_int = int(parts[-3], 16)
            except ValueError:
                size_int = 0
        entries.append((addr_int, name, size_int, is_exported_flag))
    return entries


def _file_offset_to_va(fo: int, sections: List[Dict[str, Any]], image_base: int) -> int:
    """Maps a file offset into a section virtual address when mapped, else returns file offset."""
    for sec in sections:
        raw_off = sec["raw_offset"]
        raw_sz = sec["raw_size"]
        if raw_sz > 0 and raw_off <= fo < raw_off + raw_sz:
            return image_base + sec["rva"] + (fo - raw_off)
    return fo


def index_binary_symbols(
    binary_path: Path,
    db_conn: sqlite3.Connection,
    binary_id: int,
) -> Dict[str, int]:
    """
    Fast symbol and string extraction via objdump/strings to seed
    the dirtyroom SQLite symbol cache with integer VAs and non-zero sizes.
    """
    counts = {"functions": 0, "strings": 0}
    cursor = db_conn.cursor()
    now_iso = datetime.now(timezone.utc).isoformat()

    sections: List[Dict[str, Any]] = []
    image_base = 0
    try:
        pe_info = parse_binary_sections(binary_path)
        image_base, sections = pe_info[0], pe_info[1]
    except (ValueError, OSError):
        pass

    # 1. Function / Export extraction via objdump (-t static + -T dynamic)
    objdump = shutil.which("objdump") or shutil.which("llvm-objdump")
    if objdump:
        merged: Dict[Tuple[int, str], Tuple[int, int]] = {}
        objdump_ok = False
        for flag in ("-t", "-T"):
            is_exp = 1 if flag == "-T" else 0
            try:
                res = subprocess.run(
                    [objdump, flag, str(binary_path)],
                    capture_output=True,
                    text=True,
                    check=False,
                    timeout=15,
                )
                if res.returncode == 0:
                    objdump_ok = True
                    for addr_int, name, size_int, exp in _parse_objdump_functions(res.stdout, is_exp):
                        key = (addr_int, name)
                        prev_sz, prev_exp = merged.get(key, (0, 0))
                        merged[key] = (max(prev_sz, size_int), max(prev_exp, exp))
            except (subprocess.SubprocessError, OSError) as exc:
                sys.stderr.write(f"[!] Warning: objdump {flag} failed for {binary_path.name}: {exc}\n")

        if objdump_ok:
            sorted_keys = sorted(merged.keys(), key=lambda k: k[0])
            funcs_to_insert: List[Tuple[int, str, int, int, str, int, str]] = []
            for idx, (addr_int, name) in enumerate(sorted_keys):
                sz, exp = merged[(addr_int, name)]
                if sz <= 0:
                    next_addr = sorted_keys[idx + 1][0] if idx + 1 < len(sorted_keys) else 0
                    gap = next_addr - addr_int if next_addr > addr_int else 0
                    sz = min(gap, 65536) if gap > 0 else 16
                funcs_to_insert.append((binary_id, name, addr_int, sz, "", exp, now_iso))

            cursor.execute("DELETE FROM functions WHERE binary_id = ?", (binary_id,))
            if funcs_to_insert:
                cursor.executemany(
                    "INSERT INTO functions (binary_id, name, address, size, signature, is_exported, created_at) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?)",
                    funcs_to_insert,
                )
                counts["functions"] = len(funcs_to_insert)

    # 2. String extraction via strings utility (mapped from file offset -> VA)
    strings_bin = shutil.which("strings")
    if strings_bin:
        try:
            res = subprocess.run(
                [strings_bin, "-n", "8", "-t", "x", str(binary_path)],
                capture_output=True,
                text=True,
                check=False,
                timeout=15,
            )
            if res.returncode == 0:
                seen_strings: set[Tuple[int, str]] = set()
                strings_to_insert: List[Tuple[int, str, int, int, str]] = []
                for line in res.stdout.splitlines()[:50000]:
                    parts = line.strip().split(maxsplit=1)
                    if len(parts) != 2:
                        continue
                    addr_hex, val = parts[0], parts[1].strip()
                    if len(val) < 8:
                        continue
                    try:
                        fo = int(addr_hex, 16)
                    except ValueError:
                        continue
                    va = _file_offset_to_va(fo, sections, image_base) if sections else fo
                    key = (va, val)
                    if key in seen_strings:
                        continue
                    seen_strings.add(key)
                    strings_to_insert.append((binary_id, val, va, len(val), "utf-8"))

                cursor.execute("DELETE FROM strings WHERE binary_id = ?", (binary_id,))
                if strings_to_insert:
                    cursor.executemany(
                        "INSERT INTO strings (binary_id, value, address, length, encoding) "
                        "VALUES (?, ?, ?, ?, ?)",
                        strings_to_insert,
                    )
                    counts["strings"] = len(strings_to_insert)
        except (subprocess.SubprocessError, OSError) as exc:
            sys.stderr.write(f"[!] Warning: strings extraction failed for {binary_path.name}: {exc}\n")

    db_conn.commit()
    return counts


@contextmanager
def _nondot_ghidra_location(root: Path, ghidra_dir: Path) -> Iterator[Path]:
    """Provides a guaranteed leading-dot-free path for Ghidra without polluting workspace root."""
    nondot = resolve_nondot_ghidra_dir(root)
    if nondot is not None and not any(part.startswith(".") and part not in (".", "..") for part in nondot.parts):
        yield nondot
        return

    if not any(part.startswith(".") and part not in (".", "..") for part in ghidra_dir.parts):
        yield ghidra_dir
        return

    tmp_base = Path(tempfile.gettempdir())
    if any(part.startswith(".") and part not in (".", "..") for part in tmp_base.parts):
        tmp_base = Path("/tmp")

    with tempfile.TemporaryDirectory(prefix="agyis_ghidra_", dir=str(tmp_base)) as td:
        link_path = Path(td) / "ghidra"
        link_path.symlink_to(ghidra_dir.resolve(), target_is_directory=True)
        yield link_path


def preanalyze_binary(
    binary_path: Path,
    dirtyroom_dir: Optional[Path] = None,
    project_name: Optional[str] = None,
    overwrite: bool = False,
    timeout_seconds: int = 600,
) -> Dict[str, Any]:
    """
    Runs headless Ghidra to pre-analyze a target binary and saves the
    Ghidra project (.gpr and .rep) into .dirtyroom/ghidra/.
    """
    b_path = Path(binary_path).resolve()
    if not b_path.is_file():
        return {"success": False, "error": f"Binary not found: {b_path}"}

    root = dirtyroom_dir or get_dirtyroom_root(b_path.parent)
    if not root:
        scaffold_res = scaffold_dirtyroom(b_path.parent, project_name=project_name or "DirtyProject")
        root = Path(scaffold_res["dirtyroom_root"])

    ghidra_dir = root / "ghidra"
    ghidra_dir.mkdir(parents=True, exist_ok=True)

    proj_name = project_name or os.environ.get("REA_GHIDRA_PROJECT_NAME") or "DirtyProject"
    gpr_file = ghidra_dir / f"{proj_name}.gpr"

    file_size = b_path.stat().st_size
    sha256 = calculate_file_sha256(b_path)
    now_iso = datetime.now(timezone.utc).isoformat()
    bin_format, bin_arch = detect_binary_architecture(b_path)

    counts = {"functions": 0, "strings": 0}
    conn = get_dirtyroom_db(root)
    if conn:
        try:
            cursor = conn.cursor()
            cursor.execute(
                "INSERT INTO binaries (name, sha256, file_size, architecture, format, created_at) "
                "VALUES (?, ?, ?, ?, ?, ?) "
                "ON CONFLICT(name) DO UPDATE SET "
                "sha256=excluded.sha256, file_size=excluded.file_size, "
                "architecture=excluded.architecture, format=excluded.format",
                (b_path.name, sha256, file_size, bin_arch, bin_format, now_iso),
            )
            conn.commit()
            cursor.execute("SELECT id FROM binaries WHERE name = ?", (b_path.name,))
            row = cursor.fetchone()
            binary_id = row[0] if row else None
            if binary_id is not None:
                counts = index_binary_symbols(b_path, conn, binary_id)
        except sqlite3.Error as exc:
            sys.stderr.write(f"[!] Warning: SQLite indexing failed for {b_path.name}: {exc}\n")
        finally:
            conn.close()

    _, reg_warn = try_register_dirtyroom(root)

    headless = find_ghidra_headless()
    if not headless:
        result: Dict[str, Any] = {
            "success": False,
            "error": "analyzeHeadless not found. Set GHIDRA_INSTALL_DIR or install Ghidra.",
            "binary": b_path.name,
            "sha256": sha256,
            "architecture": bin_arch,
            "size_mb": round(file_size / (1024 * 1024), 2),
            "indexed_symbols": counts,
        }
        if reg_warn:
            result["registry_warning"] = reg_warn
        return result

    log_path = root / "logs" / f"ghidra_preanalyze_{b_path.name}.log"
    log_path.parent.mkdir(parents=True, exist_ok=True)

    try:
        with _nondot_ghidra_location(root, ghidra_dir) as ghidra_project_location:
            cmd = [
                str(headless),
                str(ghidra_project_location),
                proj_name,
            ]
            has_gpr = gpr_file.exists() or (ghidra_project_location / f"{proj_name}.gpr").exists()
            if overwrite or not has_gpr:
                cmd.extend(["-import", str(b_path), "-overwrite"])
            else:
                cmd.extend(["-process", b_path.name])

            with open(log_path, "w", encoding="utf-8") as log_f:
                proc = subprocess.run(
                    cmd,
                    stdout=log_f,
                    stderr=subprocess.STDOUT,
                    timeout=timeout_seconds,
                    check=False,
                )
    except subprocess.TimeoutExpired:
        return {
            "success": False,
            "error": f"Headless Ghidra pre-analysis timed out after {timeout_seconds}s.",
            "ghidra_project": str(gpr_file),
            "binary": b_path.name,
            "sha256": sha256,
            "architecture": bin_arch,
            "size_mb": round(file_size / (1024 * 1024), 2),
            "log_path": str(log_path),
            "indexed_symbols": counts,
        }
    except OSError as exc:
        return {
            "success": False,
            "error": f"Failed to execute analyzeHeadless: {exc}",
            "ghidra_project": str(gpr_file),
            "binary": b_path.name,
            "sha256": sha256,
            "architecture": bin_arch,
            "size_mb": round(file_size / (1024 * 1024), 2),
            "log_path": str(log_path),
            "indexed_symbols": counts,
        }

    _, reg_warn = try_register_dirtyroom(root)

    result = {
        "success": proc.returncode == 0,
        "exit_code": proc.returncode,
        "ghidra_project": str(gpr_file),
        "binary": b_path.name,
        "sha256": sha256,
        "architecture": bin_arch,
        "size_mb": round(file_size / (1024 * 1024), 2),
        "log_path": str(log_path),
        "indexed_symbols": counts,
    }
    if reg_warn:
        result["registry_warning"] = reg_warn
    return result
