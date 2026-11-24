# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Arafat Zahan (@kuasha420)
# Corporate Stewardship & Infrastructure: Purrfect Software Limited (PSL)
# Governed by: ICARO-42/b Ordinance (Company-Supported Personal IP Framework)

"""
Dual-Mode Cross-Reference Engine (ADR-028, PSL-RE-001).
Provides SQLite pre-analyzed xref queries and streaming PE/ELF binary scanning.
"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import sqlite3
import struct
import sys
from typing import Any, BinaryIO, Dict, Iterator, List, Optional, Tuple

from harness.re.address import parse_binary_sections, parse_int_address, parse_pe_sections  # noqa: F401
from harness.re.scaffold import resolve_binary_path

_STREAM_CHUNK_BYTES = 1024 * 1024  # 1 MiB streaming window


def _iter_section_chunks(
    f: BinaryIO,
    raw_offset: int,
    raw_size: int,
    file_size: int,
    overlap: int,
) -> Iterator[Tuple[int, bytes]]:
    """Yields (section_relative_offset, chunk_bytes) with bounded overlap across boundaries."""
    if raw_size <= 0 or raw_offset < 0 or raw_offset >= file_size:
        return
    available = min(raw_size, file_size - raw_offset)
    offset_in_sec = 0
    tail = b""
    f.seek(raw_offset)
    while offset_in_sec < available:
        to_read = min(_STREAM_CHUNK_BYTES, available - offset_in_sec)
        chunk = f.read(to_read)
        if not chunk:
            break
        buf = tail + chunk
        buf_rel_start = offset_in_sec - len(tail)
        yield buf_rel_start, buf
        offset_in_sec += len(chunk)
        if overlap > 0 and len(buf) >= overlap:
            tail = buf[-overlap:]
        else:
            tail = buf


def find_cross_references(
    bin_path: Path,
    target_va: int,
    xref_type_filter: str = "all",
    conn: Optional[sqlite3.Connection] = None,
) -> List[Dict[str, Any]]:
    """Finds cross-references to a virtual address via SQLite cache and streaming binary scan."""
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
                    from_addr = parse_int_address(fa)
                    if from_addr is None:
                        continue
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

    # 2. Mode B: Header parsing and streaming section scanning
    pe_info = parse_binary_sections(bin_path)
    image_base, sections = pe_info[0], pe_info[1]
    is_64bit = getattr(pe_info, "is_64bit", True)
    architecture = getattr(pe_info, "architecture", None)
    is_x86_family = architecture in ("x86", "x86_64", None, "unknown")

    with open(bin_path, "rb") as f:
        f.seek(0, os.SEEK_END)
        file_size = f.tell()

        # Code Scan: x86/x86_64 CALL (0xE8) and JMP (0xE9) in code sections only
        if xref_type_filter in ("all", "code") and is_x86_family:
            for sec in sections:
                if sec["name"] in (".text", "code") or sec.get("is_code"):
                    raw_offset = sec["raw_offset"]
                    raw_size = sec["raw_size"]
                    if raw_size <= 0 or raw_offset + raw_size > file_size:
                        continue
                    base_va = image_base + sec["rva"]
                    for chunk_rel, sec_data in _iter_section_chunks(f, raw_offset, raw_size, file_size, overlap=4):
                        limit_i = len(sec_data) - 4
                        for i in range(limit_i):
                            opcode = sec_data[i]
                            if opcode not in (0xE8, 0xE9):
                                continue
                            disp = struct.unpack_from("<i", sec_data, i + 1)[0]
                            instr_rel = chunk_rel + i
                            curr_va = base_va + instr_rel + 5
                            if curr_va + disp == target_va:
                                xref_addr = base_va + instr_rel
                                if xref_addr not in found_map:
                                    op_name = "CALL" if opcode == 0xE8 else "JMP"
                                    found_map[xref_addr] = {
                                        "from_address": xref_addr,
                                        "from_address_hex": f"0x{xref_addr:x}",
                                        "xref_type": f"code:{op_name}",
                                        "source": "code_scan",
                                        "section": sec["name"],
                                    }

        # Data Scan: 4-byte (<I) or 8-byte (<Q) pointer matches in data sections
        if xref_type_filter in ("all", "data"):
            ptr_fmt = "<Q" if is_64bit else "<I"
            ptr_size = 8 if is_64bit else 4
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
                        if raw_sz <= 0 or raw_off + raw_sz > file_size:
                            continue
                        base_va = image_base + sec["rva"]
                        for chunk_rel, sec_data in _iter_section_chunks(f, raw_off, raw_sz, file_size, overlap=ptr_size - 1):
                            pos = 0
                            while True:
                                pos = sec_data.find(pat, pos)
                                if pos == -1:
                                    break
                                xref_addr = base_va + chunk_rel + pos
                                if xref_addr not in found_map:
                                    found_map[xref_addr] = {
                                        "from_address": xref_addr,
                                        "from_address_hex": f"0x{xref_addr:x}",
                                        "xref_type": f"data_ptr ({sname})",
                                        "source": "data_scan",
                                        "section": sname,
                                    }
                                pos += ptr_size

    # Correlate with Symbol Database
    results = sorted(found_map.values(), key=lambda x: x["from_address"])
    for item in results:
        fa = item["from_address"]
        func_name = "unknown"
        if conn:
            try:
                c = conn.cursor()
                if binary_id is not None:
                    c.execute(
                        "SELECT name, address, COALESCE(size, 0) FROM functions "
                        "WHERE binary_id = ? AND ((COALESCE(size, 0) > 0 AND address <= ? AND address + COALESCE(size, 0) > ?) OR address = ?) "
                        "ORDER BY address DESC LIMIT 1",
                        (binary_id, fa, fa, fa),
                    )
                else:
                    c.execute(
                        "SELECT name, address, COALESCE(size, 0) FROM functions "
                        "WHERE ((COALESCE(size, 0) > 0 AND address <= ? AND address + COALESCE(size, 0) > ?) OR address = ?) "
                        "ORDER BY address DESC LIMIT 1",
                        (fa, fa, fa),
                    )
                r = c.fetchone()
                if r:
                    fn_name = r[0]
                    fn_addr = parse_int_address(r[1])
                    if fn_addr is not None:
                        func_name = f"{fn_name} + 0x{fa - fn_addr:x}"

                if "data" in item.get("xref_type", "") or item.get("section") in (".rdata", ".data", "_RDATA") or func_name == "unknown":
                    rtti_cols = [col[1] for col in c.execute("PRAGMA table_info(rtti_classes)").fetchall()]
                    if "class_name" in rtti_cols:
                        vt_col = "vtable_addr" if "vtable_addr" in rtti_cols else "vtable_address"
                        rtti_query = f"SELECT class_name, {vt_col} FROM rtti_classes WHERE "
                        if binary_id is not None and "binary_id" in rtti_cols:
                            rtti_query += f"binary_id = ? AND {vt_col} <= ? AND {vt_col} + 4096 > ? LIMIT 1"
                            rtti_params: Tuple[Any, ...] = (binary_id, fa, fa)
                        else:
                            rtti_query += f"{vt_col} <= ? AND {vt_col} + 4096 > ? LIMIT 1"
                            rtti_params = (fa, fa)
                        c.execute(rtti_query, rtti_params)
                        rtti_r = c.fetchone()
                        if rtti_r:
                            vt_base = parse_int_address(rtti_r[1], default=0) or 0
                            vt_off = (fa - vt_base) if vt_base else 0
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
                            vt_base = parse_int_address(rtti_r[1], default=0) or 0
                            vt_off = (fa - vt_base) if vt_base else 0
                            item["rtti_class"] = rtti_r[0]
                            func_name = f"vtable {rtti_r[0]} + 0x{vt_off:x}"
            except sqlite3.Error:
                pass
        item["symbol"] = func_name

    return results


def _safe_close_conn(conn: Optional[sqlite3.Connection]) -> None:
    if conn is not None:
        try:
            conn.close()
        except sqlite3.Error:
            pass


def execute_cmd_xrefs(args: argparse.Namespace, conn: Optional[sqlite3.Connection] = None) -> int:
    """CLI execution handler for 'agyis re xrefs'."""
    target = args.target
    target_va = parse_int_address(target)
    if target_va is None:
        print(f"[!] Error: Target must be a hex address (0x...): {target}", file=sys.stderr)
        _safe_close_conn(conn)
        return 1

    binary = getattr(args, "binary", None)
    bin_path = resolve_binary_path(binary)
    if not bin_path:
        target_name = binary or "target binary"
        print(f"[!] Error: Binary '{target_name}' not found. Specify --binary or place in .dirtyroom/binaries/.", file=sys.stderr)
        _safe_close_conn(conn)
        return 1

    if conn is None:
        try:
            from harness.re.scaffold import get_dirtyroom_db
            conn = get_dirtyroom_db()
        except (sqlite3.Error, OSError, ImportError) as exc:
            sys.stderr.write(f"[!] Warning: Could not open dirtyroom database: {exc}\n")
            conn = None

    xref_type_filter = getattr(args, "type", "all")
    as_json = getattr(args, "json", False)

    try:
        results = find_cross_references(bin_path, target_va, xref_type_filter, conn=conn)
    finally:
        _safe_close_conn(conn)

    if as_json:
        print(json.dumps(results, indent=2))
        return 0

    binary_label = bin_path.name
    print(f"[*] Found {len(results)} cross-reference(s) to 0x{target_va:x} in {binary_label} (filter: {xref_type_filter}):")
    for item in results:
        print(f"  {item['from_address_hex']}  [{item['xref_type']}]  ({item['symbol']})")

    return 0
