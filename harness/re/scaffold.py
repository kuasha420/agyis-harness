# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Arafat Zahan (@kuasha420)
# Corporate Stewardship & Infrastructure: Purrfect Software Limited (PSL)
# Governed by: ICARO-42/b Ordinance (Company-Supported Personal IP Framework)

"""
Turnkey Dirty-Room Scaffolding & SQLite Symbol Database (ADR-028, PSL-INV-007, PSL-INV-009).
Provisions quarantined .dirtyroom directories, SQLite symbol caches, and environment configs.
"""

from datetime import datetime, timezone
import json
import os
from pathlib import Path
import sqlite3
from typing import Any, Dict, Optional

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS binaries (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT UNIQUE NOT NULL,
    sha256 TEXT NOT NULL,
    file_size INTEGER NOT NULL,
    architecture TEXT,
    format TEXT,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS functions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    binary_id INTEGER NOT NULL,
    name TEXT NOT NULL,
    address TEXT NOT NULL,
    size INTEGER,
    signature TEXT,
    is_exported INTEGER DEFAULT 0,
    created_at TEXT NOT NULL,
    FOREIGN KEY(binary_id) REFERENCES binaries(id)
);

CREATE TABLE IF NOT EXISTS strings (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    binary_id INTEGER NOT NULL,
    value TEXT NOT NULL,
    address TEXT,
    length INTEGER,
    encoding TEXT DEFAULT 'utf-8',
    FOREIGN KEY(binary_id) REFERENCES binaries(id)
);

CREATE TABLE IF NOT EXISTS rtti_classes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    binary_id INTEGER NOT NULL,
    name TEXT NOT NULL,
    vtable_address TEXT,
    base_classes TEXT,
    FOREIGN KEY(binary_id) REFERENCES binaries(id)
);

CREATE TABLE IF NOT EXISTS packets (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    pcap_name TEXT NOT NULL,
    frame_number INTEGER NOT NULL,
    timestamp REAL,
    proto TEXT,
    src_ip TEXT,
    dst_ip TEXT,
    src_port INTEGER,
    dst_port INTEGER,
    payload_len INTEGER,
    summary TEXT
);

CREATE TABLE IF NOT EXISTS runs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    command TEXT NOT NULL,
    started_at TEXT NOT NULL,
    finished_at TEXT,
    exit_code INTEGER,
    log_path TEXT
);

CREATE INDEX IF NOT EXISTS idx_functions_name ON functions(name);
CREATE INDEX IF NOT EXISTS idx_functions_address ON functions(address);
CREATE INDEX IF NOT EXISTS idx_strings_value ON strings(value);
CREATE INDEX IF NOT EXISTS idx_rtti_name ON rtti_classes(name);
CREATE INDEX IF NOT EXISTS idx_packets_pcap ON packets(pcap_name);
"""

DIRTYROOM_GITIGNORE = """# Dirty-Room Artifacts & Heavy Binaries Quarantine (PSL-INV-007 §1)
ghidra/*.rep/
ghidra/*.lock
logs/*.log
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
    for env_k in ("AGYIS_DIRTYROOM", "IMMORTAL_DIRTYROOM", "REA_DIRTYROOM"):
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


def get_dirtyroom_db(dirtyroom_root: Optional[Path] = None) -> Optional[sqlite3.Connection]:
    """Returns an open SQLite connection to the dirtyroom symbols database."""
    root = dirtyroom_root or get_dirtyroom_root()
    if not root:
        return None

    # Check candidates
    cands = [
        root / "symbols" / "dirtyroom.db",
        root / "symbols" / "paladins_symbols.sqlite",
        root / "symbols.db",
        root / "symbols.sqlite",
    ]
    for c in cands:
        if c.is_file():
            return sqlite3.connect(c)

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
    subdirs = ["ghidra", "symbols", "logs", "pcaps"]
    created_dirs: list[str] = []
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

    # 2b. Non-dot symlink for Ghidra compatibility (DEF-BB-038)
    # Ghidra rejects any path component starting with '.' in project locations
    symlink_alias = target / "dirtyroom"
    if not symlink_alias.exists() and not symlink_alias.is_symlink():
        try:
            symlink_alias.symlink_to(".dirtyroom", target_is_directory=True)
        except OSError:
            pass

    # 3. Environment Export file
    env_file = dirty_dir / "dirtyroom.env"
    if not env_file.exists():
        ghidra_proj_dir = f"{target}/dirtyroom/ghidra" if (symlink_alias.exists() or symlink_alias.is_symlink()) else f"{dirty_dir}/ghidra"
        env_content = f"""# Agyis Dirty-Room Environment Configuration (ADR-028, PSL-INV-009)
export AGYIS_DIRTYROOM="{dirty_dir}"
export REA_GHIDRA_PROJECT_DIR="{ghidra_proj_dir}"
export REA_GHIDRA_PROJECT_NAME="{project_name}"
export REA_DISASSEMBLER="ghidra"
"""
        env_file.write_text(env_content, encoding="utf-8")

    # 4. .gitignore Quarantine
    gi_file = dirty_dir / ".gitignore"
    if not gi_file.exists():
        gi_file.write_text(DIRTYROOM_GITIGNORE, encoding="utf-8")

    # 5. Top-level .gitignore check
    root_gi = target / ".gitignore"
    root_gi_updated = False
    if root_gi.is_file():
        text = root_gi.read_text(encoding="utf-8")
        if ".dirtyroom/ghidra/*.rep" not in text and ".dirtyroom/" not in text:
            with open(root_gi, "a", encoding="utf-8") as f:
                f.write("\n# Quarantined Dirty-Room Decompiler Caches (PSL-INV-007)\n.dirtyroom/ghidra/*.rep/\n.dirtyroom/logs/\n")
            root_gi_updated = True

    return {
        "success": True,
        "dirtyroom_root": str(dirty_dir),
        "symlink_alias": str(symlink_alias) if (symlink_alias.exists() or symlink_alias.is_symlink()) else None,
        "created_dirs": created_dirs,
        "db_path": str(db_file),
        "db_created": db_created,
        "env_file": str(env_file),
        "root_gitignore_updated": root_gi_updated,
    }
