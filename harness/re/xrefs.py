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

from harness.re.address import parse_pe_sections
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

    # 1. Mode A: SQLite pre-analyzed cross-references (sub-millisecond)
    if conn:
        try:
            c = conn.cursor()
            c.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='xrefs'")
            if c.fetchone():
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

    image_base, sections = parse_pe_sections(bin_path)

    # Code Scan: CALL (0xE8) and JMP (0xE9) in .text
    if xref_type_filter in ("all", "code"):
        for sec in sections:
            if sec["name"] in (".text", "code") or sec.get("is_code"):
                raw_offset = sec["raw_offset"]
                raw_size = sec["raw_size"]
                if raw_size > 0 and raw_offset + raw_size <= len(buf):
                    sec_data = buf[raw_offset : raw_offset + raw_size]
                    base_va = image_base + sec["rva"]
                    for i in range(1, len(sec_data) - 4):
                        opcode = sec_data[i - 1]
                        if opcode not in (0xE8, 0xE9):
                            continue
                        disp = struct.unpack_from("<i", sec_data, i)[0]
                        curr_va = base_va + i + 4
                        if curr_va + disp == target_va:
                            xref_addr = base_va + i - 1
                            if xref_addr not in found_map:
                                op_name = "CALL" if opcode == 0xE8 else "JMP"
                                found_map[xref_addr] = {
                                    "from_address": xref_addr,
                                    "from_address_hex": f"0x{xref_addr:x}",
                                    "xref_type": f"code:{op_name}",
                                    "source": "code_scan",
                                    "section": sec["name"],
                                }

    # Data Scan: 8-byte pointer matches in .rdata, .data, etc.
    if xref_type_filter in ("all", "data"):
        pat = struct.pack("<Q", target_va)
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
                        pos += 8

    # Correlate with Symbol Database
    results = sorted(found_map.values(), key=lambda x: x["from_address"])
    for item in results:
        fa = item["from_address"]
        func_name = "unknown"
        if conn:
            try:
                c = conn.cursor()
                # Check functions table
                c.execute(
                    "SELECT name, address FROM functions WHERE address <= ? ORDER BY address DESC LIMIT 1",
                    (fa,),
                )
                r = c.fetchone()
                if r:
                    fn_name = r[0]
                    fn_addr = int(r[1])
                    func_name = f"{fn_name} + 0x{fa - fn_addr:x}"

                # If in data section, check rtti_classes for vtable match
                if "data" in item.get("xref_type", "") or item.get("section") in (".rdata", ".data", "_RDATA"):
                    c.execute(
                        "SELECT class_name, vtable_addr FROM rtti_classes WHERE vtable_addr <= ? AND vtable_addr + 4096 > ? LIMIT 1",
                        (fa, fa),
                    )
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
            conn.close()
        return 1

    binary = getattr(args, "binary", None)
    bin_path = resolve_binary_path(binary)
    if not bin_path:
        target_name = binary or "target binary"
        print(f"[!] Error: Binary '{target_name}' not found. Specify --binary or place in .dirtyroom/binaries/.", file=sys.stderr)
        if conn:
            conn.close()
        return 1

    xref_type_filter = getattr(args, "type", "all")
    as_json = getattr(args, "json", False)

    try:
        results = find_cross_references(bin_path, target_va, xref_type_filter, conn=conn)
    finally:
        if conn:
            conn.close()

    if as_json:
        print(json.dumps(results, indent=2))
        return 0

    binary_label = bin_path.name
    print(f"[*] Found {len(results)} cross-reference(s) to 0x{target_va:x} in {binary_label} (filter: {xref_type_filter}):")
    for item in results:
        print(f"  {item['from_address_hex']}  [{item['xref_type']}]  ({item['symbol']})")

    return 0
