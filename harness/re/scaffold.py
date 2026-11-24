# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Arafat Zahan (@kuasha420)
# Corporate Stewardship & Infrastructure: Purrfect Software Limited (PSL)
# Governed by: ICARO-42/b Ordinance (Company-Supported Personal IP Framework)

"""
Turnkey Dirty-Room Scaffolding & SQLite Symbol Database (ADR-028, PSL-RE-001).
Provisions quarantined .dirtyroom directories, SQLite symbol caches, and environment configs.
"""

from __future__ import annotations

import glob
import importlib.resources
import os
from pathlib import Path
import shlex
import sqlite3
from typing import Any, Dict, List, Optional

from harness.re.registry import try_register_dirtyroom

SCHEMA_SQL = importlib.resources.files("harness.re.assets").joinpath("schema.sql").read_text(encoding="utf-8")

DIRTYROOM_GITIGNORE = """# Dirty-Room Artifacts & Heavy Binaries Quarantine (PSL-RE-001)
dirtyroom
symbols/
pcaps/
ghidra/*.gpr
ghidra/*.rep/
ghidra/*.lock
dirtyroom.env
logs/*.log
cache/
*.tmp
*.bin
*.exe
*.dll
*.so
*.dylib
"""


def get_dirtyroom_root(start_path: Optional[Path] = None) -> Optional[Path]:
    """Resolves the active .dirtyroom directory for the current workspace."""
    # 1. Environment variable override
    for env_k in ("AGYIS_DIRTYROOM", "REA_DIRTYROOM"):
        val = os.environ.get(env_k)
        if val:
            p = Path(val).resolve()
            if p.is_dir():
                return p

    # 2. Search upwards from start_path or cwd
    curr = (start_path or Path.cwd()).resolve()
    for parent in [curr] + list(curr.parents):
        cand = parent / ".dirtyroom"
        if cand.is_dir():
            return cand.resolve()

    return None


def resolve_binary_path(binary_name: Optional[str] = None, dirtyroom_root: Optional[Path] = None) -> Optional[Path]:
    """Resolves a target binary in the dirtyroom environment or direct filesystem path (ADR-014, ADR-028)."""
    root = dirtyroom_root or get_dirtyroom_root()
    if binary_name:
        direct = Path(binary_name)
        if direct.is_file():
            return direct
        if root:
            root_resolved = root.resolve()
            bin_dir_resolved = (root / "binaries").resolve() if (root / "binaries").exists() else root_resolved
            if ".." not in Path(binary_name).parts and not Path(binary_name).is_absolute():
                candidates = [
                    root / "binaries" / binary_name,
                    root / binary_name,
                ]
                for c in candidates:
                    if c.is_file():
                        try:
                            c_res = c.resolve()
                            if c_res.is_relative_to(root_resolved) or c_res.is_relative_to(bin_dir_resolved):
                                return c
                        except OSError:
                            continue
                if binary_name == Path(binary_name).name:
                    escaped = glob.escape(binary_name)
                    for match in root.rglob(escaped):
                        if match.is_file():
                            try:
                                if match.resolve().is_relative_to(root_resolved):
                                    return match
                            except OSError:
                                continue
        return None

    # Auto-detect binary from dirtyroom if binary_name not provided
    if root:
        bin_dir = root / "binaries"
        if bin_dir.is_dir():
            candidates = sorted(
                c for c in bin_dir.iterdir()
                if c.is_file() and not c.name.startswith(".")
            )
            # Prefer executables over shared libraries (.dll/.so/.dylib)
            for c in candidates:
                if c.suffix.lower() not in (".dll", ".so", ".dylib"):
                    return c
            if candidates:
                return candidates[0]
        for c in sorted(root.iterdir()):
            if c.is_file() and not c.name.startswith("."):
                if c.suffix.lower() in (".exe", ".dll", ".so", ".dylib", ".bin"):
                    return c
                try:
                    with open(c, "rb") as bf:
                        if bf.read(4) == b"\x7fELF":
                            return c
                except OSError:
                    pass
    return None


def discover_dirtyroom_dbs(dirtyroom_root: Path) -> List[Path]:
    """Discovers non-symlink SQLite symbol database candidates inside a dirtyroom."""
    cands: List[Path] = [dirtyroom_root / "symbols" / "dirtyroom.db"]
    sym_dir = dirtyroom_root / "symbols"
    if sym_dir.is_dir():
        try:
            cands.extend(sorted(sym_dir.glob("*.db")) + sorted(sym_dir.glob("*.sqlite")))
        except OSError:
            pass
    cands.extend([dirtyroom_root / "symbols.db", dirtyroom_root / "symbols.sqlite"])

    root_res = dirtyroom_root.resolve()
    seen: set[Path] = set()
    valid: List[Path] = []
    for c in cands:
        try:
            if c.is_symlink() or not c.is_file():
                continue
            rp = c.resolve()
            if rp in seen or not rp.is_relative_to(root_res):
                continue
            if c.stat().st_size > 0:
                seen.add(rp)
                valid.append(c)
        except OSError:
            continue
    return valid


def get_dirtyroom_db(dirtyroom_root: Optional[Path] = None) -> Optional[sqlite3.Connection]:
    """Returns an open SQLite connection to the dirtyroom symbols database.

    Evaluates candidates by size and schema content to prevent empty or 0-byte
    shadow files from masking populated symbols databases.
    """
    root = dirtyroom_root or get_dirtyroom_root()
    if not root:
        return None

    valid_cands = discover_dirtyroom_dbs(root)
    if not valid_cands:
        return None

    best_cand = None
    best_count = -1

    for c in valid_cands:
        conn = None
        try:
            conn = sqlite3.connect(c)
            cursor = conn.cursor()
            cursor.execute("SELECT count(*) FROM functions")
            cnt = cursor.fetchone()[0]
            if cnt > best_count:
                best_count = cnt
                best_cand = c
        except sqlite3.Error:
            if best_cand is None:
                best_cand = c
        finally:
            if conn:
                try:
                    conn.close()
                except sqlite3.Error:
                    pass

    if best_cand:
        return sqlite3.connect(best_cand)

    return None


def init_dirtyroom_db(db_path: Path) -> None:
    """Initializes the dirtyroom SQLite schema."""
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path)
    try:
        conn.executescript(SCHEMA_SQL)
        conn.commit()
    finally:
        conn.close()


def _ensure_dirtyroom_gitignore(gi_file: Path) -> None:
    """Creates or idempotently upgrades .dirtyroom/.gitignore with full quarantine rules."""
    if not gi_file.exists():
        gi_file.write_text(DIRTYROOM_GITIGNORE, encoding="utf-8")
        return

    gi_text = gi_file.read_text(encoding="utf-8")
    gi_lines = {line.strip() for line in gi_text.splitlines()}
    required = [
        ("dirtyroom", {"dirtyroom", "/dirtyroom", "dirtyroom/"}),
        ("symbols/", {"symbols/", "symbols"}),
        ("pcaps/", {"pcaps/", "pcaps"}),
        ("ghidra/*.gpr", {"ghidra/*.gpr"}),
        ("ghidra/*.rep/", {"ghidra/*.rep/", "ghidra/*.rep"}),
        ("ghidra/*.lock", {"ghidra/*.lock"}),
        ("dirtyroom.env", {"dirtyroom.env"}),
        ("logs/*.log", {"logs/*.log", "logs/", "logs"}),
        ("cache/", {"cache/", "cache"}),
    ]
    missing = [canonical for canonical, aliases in required if not (gi_lines & aliases)]
    if missing:
        sep = "" if (not gi_text or gi_text.endswith("\n")) else "\n"
        with open(gi_file, "a", encoding="utf-8") as f:
            f.write(f"{sep}" + "\n".join(missing) + "\n")


def scaffold_dirtyroom(
    target_path: Path,
    project_name: str = "DirtyProject",
) -> Dict[str, Any]:
    """
    Creates turnkey .dirtyroom directory scaffolding, SQLite schema,
    environment exports, and gitignore isolation fences.
    """
    target = Path(target_path).resolve()
    dirty_dir = target / ".dirtyroom"

    # 1. Directory Structure
    subdirs = ["ghidra", "symbols", "logs", "pcaps", "cache/decompile"]
    created_dirs: List[str] = []
    for s in subdirs:
        d = dirty_dir / s
        if not d.exists():
            d.mkdir(parents=True, exist_ok=True)
            created_dirs.append(str(d.relative_to(target)))

    # 2. Database Initialization
    db_file = dirty_dir / "symbols" / "dirtyroom.db"
    db_created = False
    if not db_file.exists():
        init_dirtyroom_db(db_file)
        db_created = True

    # Do NOT create an unhidden workspace-root 'dirtyroom -> .dirtyroom' symlink on init (PSL-RE-001).
    symlink_alias = target / "dirtyroom"
    existing_alias: Optional[str] = None
    try:
        if (symlink_alias.exists() or symlink_alias.is_symlink()) and symlink_alias.resolve() == dirty_dir.resolve():
            existing_alias = str(symlink_alias)
    except OSError:
        existing_alias = None

    # 3. Shell-safe Environment Export file
    env_file = dirty_dir / "dirtyroom.env"
    if not env_file.exists():
        ghidra_proj_dir = str(Path(existing_alias) / "ghidra") if existing_alias else str(dirty_dir / "ghidra")
        env_content = (
            "# Agyis Dirty-Room Environment Configuration (ADR-028, PSL-RE-001)\n"
            f"export AGYIS_DIRTYROOM={shlex.quote(str(dirty_dir))}\n"
            f"export REA_GHIDRA_PROJECT_DIR={shlex.quote(ghidra_proj_dir)}\n"
            f"export REA_GHIDRA_PROJECT_NAME={shlex.quote(project_name)}\n"
            'export REA_DISASSEMBLER="ghidra"\n'
            'export REA_GHIDRA_DIRECT_MOUNT="1"\n'
        )
        env_file.write_text(env_content, encoding="utf-8")

    # 4. .dirtyroom/.gitignore Quarantine
    _ensure_dirtyroom_gitignore(dirty_dir / ".gitignore")

    # 5. Top-level .gitignore check
    root_gi = target / ".gitignore"
    root_gi_updated = False
    if root_gi.is_file():
        text = root_gi.read_text(encoding="utf-8")
        existing_lines = {line.strip() for line in text.splitlines()}
        if ".dirtyroom/" not in existing_lines and ".dirtyroom" not in existing_lines:
            required_entries = [
                ("dirtyroom", {"dirtyroom", "/dirtyroom", "dirtyroom/"}),
                (".dirtyroom/symbols/", {".dirtyroom/symbols/", ".dirtyroom/symbols"}),
                (".dirtyroom/pcaps/", {".dirtyroom/pcaps/", ".dirtyroom/pcaps"}),
                (".dirtyroom/ghidra/*.gpr", {".dirtyroom/ghidra/*.gpr"}),
                (".dirtyroom/ghidra/*.rep/", {".dirtyroom/ghidra/*.rep/", ".dirtyroom/ghidra/*.rep"}),
                (".dirtyroom/logs/", {".dirtyroom/logs/", ".dirtyroom/logs"}),
                (".dirtyroom/cache/", {".dirtyroom/cache/", ".dirtyroom/cache"}),
                (".dirtyroom/dirtyroom.env", {".dirtyroom/dirtyroom.env"}),
            ]
            missing = [canonical for canonical, aliases in required_entries if not (existing_lines & aliases)]
            if missing:
                sep = "" if (not text or text.endswith("\n")) else "\n"
                header = "\n# Quarantined Dirty-Room Decompiler Caches (PSL-RE-001)\n" if len(missing) == len(required_entries) else ""
                with open(root_gi, "a", encoding="utf-8") as f:
                    f.write(f"{sep}{header}" + "\n".join(missing) + "\n")
                root_gi_updated = True

    _, reg_warn = try_register_dirtyroom(dirty_dir)

    result: Dict[str, Any] = {
        "success": True,
        "dirtyroom_root": str(dirty_dir),
        "symlink_alias": existing_alias,
        "created_dirs": created_dirs,
        "db_path": str(db_file),
        "db_created": db_created,
        "env_file": str(env_file),
        "root_gitignore_updated": root_gi_updated,
    }
    if reg_warn:
        result["registry_warning"] = reg_warn
    return result
