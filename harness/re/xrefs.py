# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Arafat Zahan (@kuasha420)
# Corporate Stewardship & Infrastructure: Purrfect Software Limited (PSL)
# Governed by: ICARO-42/b Ordinance (Company-Supported Personal IP Framework)

"""
Dual-Mode Cross-Reference Engine (ADR-028, PSL-INV-007, PSL-INV-009).
Provides SQLite pre-analyzed xref queries and PE binary direct scanning.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sqlite3
import struct
import sys
from typing import Any, Dict, List, Optional

from harness.re.address import parse_binary_sections, parse_pe_sections  # noqa: F401
from harness.re.scaffold import resolve_binary_path


def find_cross_references(
    bin_path: Path,
    target_va: int,
    xref_type_filter: str = "all",
    conn: Optional[sqlite3.Connection] = None,
) -> List[Dict[str, Any]]:
    """Finds cross-references to a virtual address via SQLite cache and binary scanning.

    Args:
        bin_path: Path to the binary executable.
        target_va: Target virtual address (integer).
        xref_type_filter: 'all', 'code', or 'data'.
        conn: Optional SQLite connection to dirtyroom database.

    Returns:
        List of correlated cross-reference dictionaries sorted by from_address.
    """
    found_map: Dict[int, Dict[str, Any]] = {}

    binary_id: Optional[int] = None
    if conn:
        try:
            c = conn.cursor()
            c.execute("SELECT id FROM binaries WHERE name = ? LIMIT 1", (bin_path.name,))
            brow = c.fetchone()
            if brow:
                binary_id = brow[0]
        except sqlite3.Error:
            binary_id = None

    # 1. Mode A: SQLite pre-analyzed cross-references (sub-millisecond)
    if conn:
        try:
            c = conn.cursor()
            c.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='xrefs'")
            if c.fetchone():
                xref_cols = [col[1] for col in c.execute("PRAGMA table_info(xrefs)").fetchall()]
                if binary_id is not None and "binary_id" in xref_cols:
                    c.execute(
                        "SELECT from_addr, xref_type FROM xrefs WHERE binary_id = ? AND to_addr = ? ORDER BY from_addr",
                        (binary_id, target_va),
                    )
                else:
                    c.execute(
                        "SELECT from_addr, xref_type FROM xrefs WHERE to_addr = ? ORDER BY from_addr",
                        (target_va,),
                    )
                rows = c.fetchall()
                for fa, xt in rows:
                    from_addr = int(fa)
                    is_code = any(k in str(xt).lower() for k in ("call", "jump", "branch", "code"))
                    if xref_type_filter == "code" and not is_code:
                        continue
                    if xref_type_filter == "data" and is_code:
                        continue
                    found_map[from_addr] = {
                        "from_address": from_addr,
                        "from_address_hex": f"0x{from_addr:x}",
                        "xref_type": f"sqlite:{xt}",
                        "source": "sqlite",
                    }
        except sqlite3.Error:
            pass

    # 2. Mode B: Binary parsing and direct scanning
    with open(bin_path, "rb") as f:
        buf = f.read()

    pe_info = parse_binary_sections(bin_path)
    image_base, sections = pe_info[0], pe_info[1]
    is_64bit = getattr(pe_info, "is_64bit", True)

    # Code Scan: CALL (0xE8) and JMP (0xE9) in .text (0-based iteration: Defect 2)
    if xref_type_filter in ("all", "code"):
        for sec in sections:
            if sec["name"] in (".text", "code") or sec.get("is_code"):
                raw_offset = sec["raw_offset"]
                raw_size = sec["raw_size"]
                if raw_size > 0 and raw_offset + raw_size <= len(buf):
                    sec_data = buf[raw_offset : raw_offset + raw_size]
                    base_va = image_base + sec["rva"]
                    for i in range(len(sec_data) - 4):
                        opcode = sec_data[i]
                        if opcode not in (0xE8, 0xE9):
                            continue
                        disp = struct.unpack_from("<i", sec_data, i + 1)[0]
                        curr_va = base_va + i + 5
                        if curr_va + disp == target_va:
                            xref_addr = base_va + i
                            if xref_addr not in found_map:
                                op_name = "CALL" if opcode == 0xE8 else "JMP"
                                found_map[xref_addr] = {
                                    "from_address": xref_addr,
                                    "from_address_hex": f"0x{xref_addr:x}",
                                    "xref_type": f"code:{op_name}",
                                    "source": "code_scan",
                                    "section": sec["name"],
                                }

    # Data Scan: 4-byte (<I) or 8-byte (<Q) pointer matches in .rdata, .data, etc. (Defect 6)
    if xref_type_filter in ("all", "data"):
        ptr_fmt = "<Q" if is_64bit else "<I"
        ptr_size = 8 if is_64bit else 4
        pat = None
        try:
            pat = struct.pack(ptr_fmt, target_va)
        except (struct.error, OverflowError):
            pat = None

        if pat is not None:
            for sec in sections:
                sname = sec["name"]
                if sname in (".rdata", ".data", "_RDATA", "rdata", "data") or "data" in sname.lower() or sec.get("is_data"):
                    raw_off = sec["raw_offset"]
                    raw_sz = sec["raw_size"]
                    if raw_sz > 0 and raw_off + raw_sz <= len(buf):
                        sec_data = buf[raw_off : raw_off + raw_sz]
                        base_va = image_base + sec["rva"]
                        pos = 0
                        while True:
                            pos = sec_data.find(pat, pos)
                            if pos == -1:
                                break
                            xref_addr = base_va + pos
                            if xref_addr not in found_map:
                                found_map[xref_addr] = {
                                    "from_address": xref_addr,
                                    "from_address_hex": f"0x{xref_addr:x}",
                                    "xref_type": f"data_ptr ({sname})",
                                    "source": "data_scan",
                                    "section": sname,
                                }
                            pos += ptr_size

    # Correlate with Symbol Database (Defect 3, 4, 7)
    results = sorted(found_map.values(), key=lambda x: x["from_address"])
    for item in results:
        fa = item["from_address"]
        func_name = "unknown"
        if conn:
            try:
                c = conn.cursor()
                # Check functions table: Guard with size boundary check & binary_id scoping (Defect 3 & 7)
                if binary_id is not None:
                    c.execute(
                        "SELECT name, address, size FROM functions WHERE binary_id = ? AND address <= ? AND address + size > ? ORDER BY address DESC LIMIT 1",
                        (binary_id, fa, fa),
                    )
                else:
                    c.execute(
                        "SELECT name, address, size FROM functions WHERE address <= ? AND address + size > ? ORDER BY address DESC LIMIT 1",
                        (fa, fa),
                    )
                r = c.fetchone()
                if r:
                    fn_name = r[0]
                    fn_addr = int(r[1])
                    func_name = f"{fn_name} + 0x{fa - fn_addr:x}"

                # If in data section or symbol is still unknown, check rtti_classes for vtable match (Defect 4)
                if "data" in item.get("xref_type", "") or item.get("section") in (".rdata", ".data", "_RDATA") or func_name == "unknown":
                    rtti_cols = [col[1] for col in c.execute("PRAGMA table_info(rtti_classes)").fetchall()]
                    if "class_name" in rtti_cols:
                        vt_col = "vtable_addr" if "vtable_addr" in rtti_cols else "vtable_address"
                        rtti_query = f"SELECT class_name, {vt_col} FROM rtti_classes WHERE "
                        if binary_id is not None and "binary_id" in rtti_cols:
                            rtti_query += f"binary_id = ? AND {vt_col} <= ? AND {vt_col} + 4096 > ? LIMIT 1"
                            rtti_params = (binary_id, fa, fa)
                        else:
                            rtti_query += f"{vt_col} <= ? AND {vt_col} + 4096 > ? LIMIT 1"
                            rtti_params = (fa, fa)
                        c.execute(rtti_query, rtti_params)
                        rtti_r = c.fetchone()
                        if rtti_r:
                            vt_off = fa - int(rtti_r[1]) if rtti_r[1] else 0
                            item["rtti_class"] = rtti_r[0]
                            func_name = f"vtable {rtti_r[0]} + 0x{vt_off:x}"
                    elif "name" in rtti_cols:
                        vt_col = "vtable_address" if "vtable_address" in rtti_cols else "vtable_addr"
                        rtti_query = f"SELECT name, {vt_col} FROM rtti_classes WHERE "
                        if binary_id is not None and "binary_id" in rtti_cols:
                            rtti_query += f"binary_id = ? AND {vt_col} <= ? AND {vt_col} + 4096 > ? LIMIT 1"
                            rtti_params = (binary_id, fa, fa)
                        else:
                            rtti_query += f"{vt_col} <= ? AND {vt_col} + 4096 > ? LIMIT 1"
                            rtti_params = (fa, fa)
                        c.execute(rtti_query, rtti_params)
                        rtti_r = c.fetchone()
                        if rtti_r:
                            vt_off = fa - int(rtti_r[1]) if rtti_r[1] else 0
                            item["rtti_class"] = rtti_r[0]
                            func_name = f"vtable {rtti_r[0]} + 0x{vt_off:x}"
            except sqlite3.Error:
                pass
        item["symbol"] = func_name

    return results


def execute_cmd_xrefs(args: argparse.Namespace, conn: Optional[sqlite3.Connection] = None) -> int:
    """CLI execution handler for 'agyis re xrefs'."""
    target = args.target
    try:
        target_va = int(target, 0)
    except ValueError:
        print(f"[!] Error: Target must be a hex address (0x...): {target}", file=sys.stderr)
        if conn:
            try:
                conn.close()
            except Exception:
                pass
        return 1

    binary = getattr(args, "binary", None)
    bin_path = resolve_binary_path(binary)
    if not bin_path:
        target_name = binary or "target binary"
        print(f"[!] Error: Binary '{target_name}' not found. Specify --binary or place in .dirtyroom/binaries/.", file=sys.stderr)
        if conn:
            try:
                conn.close()
            except Exception:
                pass
        return 1

    if conn is None:
        try:
            from harness.re.scaffold import get_dirtyroom_db
            conn = get_dirtyroom_db()
        except Exception:
            conn = None

    xref_type_filter = getattr(args, "type", "all")
    as_json = getattr(args, "json", False)

    try:
        results = find_cross_references(bin_path, target_va, xref_type_filter, conn=conn)
    finally:
        if conn:
            try:
                conn.close()
            except Exception:
                pass

    if as_json:
        print(json.dumps(results, indent=2))
        return 0

    binary_label = bin_path.name
    print(f"[*] Found {len(results)} cross-reference(s) to 0x{target_va:x} in {binary_label} (filter: {xref_type_filter}):")
    for item in results:
        print(f"  {item['from_address_hex']}  [{item['xref_type']}]  ({item['symbol']})")

    return 0
