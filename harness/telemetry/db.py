# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Arafat Zahan (@kuasha420)
# Corporate Stewardship & Infrastructure: Purrfect Software Limited (PSL)
# Governed by: ICARO-42/b Ordinance (Company-Supported Personal IP Framework)

"""
Centralized SQLite database connection factory for PSL Telemetry (ADR-014, ADR-030).
"""

from __future__ import annotations

from pathlib import Path
import sqlite3
from typing import Union


def get_db_connection(
    db_file: Union[str, Path],
    timeout: float = 30.0,
    row_factory: bool = True,
) -> sqlite3.Connection:
    """Connect to SQLite database with WAL mode, busy timeout, and integrity invariants.

    Parameters:
        db_file: Path to SQLite database file
        timeout: SQLite connection timeout in seconds (default: 30.0)
        row_factory: Whether to set conn.row_factory to sqlite3.Row (default: True)
    """
    path_str = str(db_file)
    if path_str != ":memory:":
        Path(path_str).parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path_str, timeout=timeout)
    if row_factory:
        conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode = WAL")
    conn.execute(f"PRAGMA busy_timeout = {int(timeout * 1000)}")
    conn.execute("PRAGMA synchronous = NORMAL")
    conn.execute("PRAGMA foreign_keys = ON")
    return conn
