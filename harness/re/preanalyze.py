# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Arafat Zahan (@kuasha420)
# Corporate Stewardship & Infrastructure: Purrfect Software Limited (PSL)
# Governed by: ICARO-42/b Ordinance (Company-Supported Personal IP Framework)

"""
Headless Ghidra Pre-Analysis Runner & Symbol Extractor (ADR-028, PSL-INV-009).
Populates pre-analyzed Ghidra project repositories (*.gpr, *.rep) so that REA
can decompile targeted procedures in <2s with -noanalysis -readOnly.
"""

from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
from typing import Any, Dict, List, Optional

from harness.re.scaffold import get_dirtyroom_db, get_dirtyroom_root, scaffold_dirtyroom


def find_ghidra_headless() -> Optional[Path]:
    """Discovers analyzeHeadless binary in PATH or standard installations."""
    # 1. Direct which lookup
    cand = shutil.which("analyzeHeadless")
    if cand:
        return Path(cand).resolve()

    # 2. Check GHIDRA_INSTALL_DIR
    ghidra_home = os.environ.get("GHIDRA_INSTALL_DIR") or os.environ.get("GHIDRA_HOME")
    if ghidra_home:
        cand_path = Path(ghidra_home) / "support" / "analyzeHeadless"
        if cand_path.is_file() and os.access(cand_path, os.X_OK):
            return cand_path.resolve()

    # 3. Standard Linux system paths
    for base in [
        Path("/opt/ghidra/support/analyzeHeadless"),
        Path("/usr/share/ghidra/support/analyzeHeadless"),
        Path.home() / ".local" / "share" / "ghidra" / "support" / "analyzeHeadless",
    ]:
        if base.is_file() and os.access(base, os.X_OK):
            return base.resolve()

    # 4. Glob home directory for ghidra_* installations
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


def index_binary_symbols(
    binary_path: Path,
    db_conn,
    binary_id: int,
) -> Dict[str, int]:
    """
    Fast symbol and string extraction via objdump/strings to seed
    the dirtyroom SQLite symbol cache.
    """
    counts = {"functions": 0, "strings": 0}
    cursor = db_conn.cursor()
    now_iso = datetime.now(timezone.utc).isoformat()

    # 1. Function / Export extraction via objdump if available
    objdump = shutil.which("objdump") or shutil.which("llvm-objdump")
    if objdump:
        try:
            # -T for dynamic symbols / exports, -t for static
            res = subprocess.run(
                [objdump, "-T", str(binary_path)],
                capture_output=True,
                text=True,
                check=False,
                timeout=15,
            )
            if res.returncode == 0:
                funcs_to_insert = []
                for line in res.stdout.splitlines():
                    parts = line.split()
                    if len(parts) >= 6 and "F" in parts:
                        addr = parts[0]
                        name = parts[-1]
                        funcs_to_insert.append((binary_id, name, addr, 0, "", 1, now_iso))
                if funcs_to_insert:
                    cursor.executemany(
                        "INSERT INTO functions (binary_id, name, address, size, signature, is_exported, created_at) "
                        "VALUES (?, ?, ?, ?, ?, ?, ?)",
                        funcs_to_insert,
                    )
                    counts["functions"] = len(funcs_to_insert)
        except Exception:
            pass

    # 2. String extraction via strings utility
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
                strings_to_insert = []
                for line in res.stdout.splitlines()[:50000]:  # Cap at 50,000 for sub-second ingestion
                    parts = line.strip().split(maxsplit=1)
                    if len(parts) == 2:
                        addr, val = parts[0], parts[1].strip()
                        if len(val) >= 8:
                            strings_to_insert.append((binary_id, val, addr, len(val), "utf-8"))
                if strings_to_insert:
                    cursor.executemany(
                        "INSERT INTO strings (binary_id, value, address, length, encoding) "
                        "VALUES (?, ?, ?, ?, ?)",
                        strings_to_insert,
                    )
                    counts["strings"] = len(strings_to_insert)
        except Exception:
            pass

    db_conn.commit()
    return counts


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

    # Register in SQLite database
    conn = get_dirtyroom_db(root)
    binary_id = None
    if conn:
        try:
            cursor = conn.cursor()
            cursor.execute(
                "INSERT INTO binaries (name, sha256, file_size, architecture, format, created_at) "
                "VALUES (?, ?, ?, ?, ?, ?) "
                "ON CONFLICT(name) DO UPDATE SET sha256=excluded.sha256, file_size=excluded.file_size",
                (b_path.name, sha256, file_size, "x86_64", b_path.suffix.lstrip("."), now_iso),
            )
            conn.commit()
            cursor.execute("SELECT id FROM binaries WHERE name = ?", (b_path.name,))
            row = cursor.fetchone()
            if row:
                binary_id = row[0]
        except Exception:
            pass

    # Index quick symbols
    counts = {"functions": 0, "strings": 0}
    if conn and binary_id:
        counts = index_binary_symbols(b_path, conn, binary_id)
        conn.close()

    # Locate analyzeHeadless
    headless = find_ghidra_headless()
    if not headless:
        return {
            "success": False,
            "error": "analyzeHeadless not found. Set GHIDRA_INSTALL_DIR or install Ghidra.",
            "binary": b_path.name,
            "sha256": sha256,
            "size_mb": round(file_size / (1024 * 1024), 2),
            "indexed_symbols": counts,
        }

    # Build headless Ghidra command
    cmd = [
        str(headless),
        str(ghidra_dir),
        proj_name,
    ]
    if overwrite or not gpr_file.exists():
        cmd.extend(["-import", str(b_path), "-overwrite"])
    else:
        cmd.extend(["-process", b_path.name])

    log_path = root / "logs" / f"ghidra_preanalyze_{b_path.name}.log"
    log_path.parent.mkdir(parents=True, exist_ok=True)

    with open(log_path, "w", encoding="utf-8") as log_f:
        proc = subprocess.run(
            cmd,
            stdout=log_f,
            stderr=subprocess.STDOUT,
            timeout=timeout_seconds,
            check=False,
        )

    return {
        "success": proc.returncode == 0,
        "exit_code": proc.returncode,
        "ghidra_project": str(gpr_file),
        "binary": b_path.name,
        "sha256": sha256,
        "size_mb": round(file_size / (1024 * 1024), 2),
        "log_path": str(log_path),
        "indexed_symbols": counts,
    }
