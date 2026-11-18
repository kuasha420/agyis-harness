# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Arafat Zahan (@kuasha420)
# Corporate Stewardship & Infrastructure: Purrfect Software Limited (PSL)
# Governed by: ICARO-42/b Ordinance (Company-Supported Personal IP Framework)

"""
PE32/PE32+ Address Translation and Reverse Engineering Symbol Resolution (ADR-028).
Provides bi-directional VA <-> RVA <-> File Offset inspection and symbol database correlation.
"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import sqlite3
import struct
import sys
from typing import Any, Dict, List, Optional, Tuple, Union

from harness.re.scaffold import resolve_binary_path


def parse_pe_sections(binary_path: Path) -> Tuple[int, List[Dict[str, Any]]]:
    """Parses PE32/PE32+ header to extract ImageBase and Section Table.

    Returns:
        (image_base, sections_list)
    """
    with open(binary_path, "rb") as f:
        # Read enough for DOS and PE header + sections table
        hdr = f.read(8192)

    if len(hdr) < 0x40 or hdr[:2] != b"MZ":
        raise ValueError(f"File '{binary_path}' is not a valid PE executable (missing MZ signature)")

    e_lfanew = struct.unpack_from("<I", hdr, 0x3C)[0]
    if e_lfanew + 24 > len(hdr) or hdr[e_lfanew : e_lfanew + 4] != b"PE\x00\x00":
        raise ValueError(f"File '{binary_path}' is missing PE signature at offset 0x{e_lfanew:x}")

    num_sections = struct.unpack_from("<H", hdr, e_lfanew + 6)[0]
    opt_hdr_size = struct.unpack_from("<H", hdr, e_lfanew + 20)[0]
    opt_magic = struct.unpack_from("<H", hdr, e_lfanew + 24)[0]

    # OptionalHeader ImageBase offset:
    # PE32 (0x10B): 4-byte ImageBase at offset +28
    # PE32+ (0x20B): 8-byte ImageBase at offset +24
    if opt_magic == 0x10B:
        image_base = struct.unpack_from("<I", hdr, e_lfanew + 24 + 28)[0]
    elif opt_magic == 0x20B:
        image_base = struct.unpack_from("<Q", hdr, e_lfanew + 24 + 24)[0]
    else:
        image_base = struct.unpack_from("<Q", hdr, e_lfanew + 24 + 24)[0]

    sec_offset = e_lfanew + 24 + opt_hdr_size
    sections: List[Dict[str, Any]] = []

    for i in range(num_sections):
        sec_hdr = hdr[sec_offset + i * 40 : sec_offset + (i + 1) * 40]
        if len(sec_hdr) < 40:
            break
        name = sec_hdr[:8].rstrip(b"\x00").decode("latin-1", errors="replace")
        vsize, vaddr, raw_size, raw_offset = struct.unpack_from("<IIII", sec_hdr, 8)
        characteristics = struct.unpack_from("<I", sec_hdr, 36)[0]

        is_code = bool(characteristics & 0x20000020)
        is_execute = bool(characteristics & 0x20000000)
        is_read = bool(characteristics & 0x40000000)
        is_write = bool(characteristics & 0x80000000)
        perms = f"{'r' if is_read else '-'}{'w' if is_write else '-'}{'x' if is_execute else '-'}"

        sections.append({
            "name": name,
            "rva": vaddr,
            "virtual_size": vsize,
            "raw_offset": raw_offset,
            "raw_size": raw_size,
            "characteristics": characteristics,
            "permissions": perms,
            "is_code": is_code or is_execute,
            "is_data": not (is_code or is_execute),
        })

    return image_base, sections


def inspect_address(
    binary_path: Path,
    addr_input: Union[int, str],
    db_conn: Optional[sqlite3.Connection] = None,
) -> Dict[str, Any]:
    """Translates an address between VA, RVA, File Offset, containing PE section, and symbol cache.

    Args:
        binary_path: Path to PE binary executable
        addr_input: Input address (integer or hex/decimal string like '0x140bc8770')
        db_conn: Optional open SQLite connection to symbols database (paladins_symbols or dirtyroom.db)

    Returns:
        Structured breakdown containing VA, RVA, File Offset, Section info, and correlated symbol.
    """
    bin_path = Path(binary_path).resolve()
    if not bin_path.is_file():
        raise FileNotFoundError(f"Binary file not found: {bin_path}")

    # Parse address input
    if isinstance(addr_input, str):
        cleaned = addr_input.strip()
        addr_int = int(cleaned, 0)
    else:
        addr_int = int(addr_input)

    image_base, sections = parse_pe_sections(bin_path)

    # Classify input address type
    if addr_int >= image_base:
        input_type = "VA"
        va = addr_int
        rva = va - image_base
    else:
        matching_rva_sec = next(
            (s for s in sections if s["rva"] <= addr_int < s["rva"] + max(s["virtual_size"], s["raw_size"])),
            None,
        )
        matching_fo_sec = next(
            (s for s in sections if s["raw_offset"] <= addr_int < s["raw_offset"] + s["raw_size"] and s["raw_size"] > 0),
            None,
        )
        if matching_rva_sec and not matching_fo_sec:
            input_type = "RVA"
            rva = addr_int
            va = image_base + rva
        elif matching_fo_sec and not matching_rva_sec:
            input_type = "FileOffset"
            delta = addr_int - matching_fo_sec["raw_offset"]
            rva = matching_fo_sec["rva"] + delta
            va = image_base + rva
        else:
            # Default to RVA in reverse engineering context
            input_type = "RVA"
            rva = addr_int
            va = image_base + rva

    # Locate containing PE section
    sec = next(
        (s for s in sections if s["rva"] <= rva < s["rva"] + max(s["virtual_size"], s["raw_size"])),
        None,
    )

    file_offset: Optional[int] = None
    if sec:
        sec_delta = rva - sec["rva"]
        if sec["raw_size"] > 0 and sec_delta < sec["raw_size"]:
            file_offset = sec["raw_offset"] + sec_delta

    # Query Symbol Database
    symbol_info: Optional[Dict[str, Any]] = None
    own_conn = False
    conn = db_conn
    if conn is None:
        try:
            from harness.re.scaffold import get_dirtyroom_db
            conn = get_dirtyroom_db()
            own_conn = conn is not None
        except Exception:
            conn = None

    if conn is not None:
        try:
            cur = conn.cursor()
            # 1. Check for containing function: address <= va AND address + size > va
            cur.execute(
                "SELECT name, address, size FROM functions WHERE address <= ? AND address + size > ? ORDER BY address DESC LIMIT 1",
                (va, va),
            )
            fn_row = cur.fetchone()
            if fn_row:
                fn_name = fn_row[0]
                fn_addr = int(fn_row[1])
                fn_size = int(fn_row[2])
                delta = va - fn_addr
                symbol_info = {
                    "type": "function",
                    "name": fn_name,
                    "base_address": fn_addr,
                    "base_address_hex": f"0x{fn_addr:x}",
                    "size": fn_size,
                    "offset": delta,
                    "delta_str": f"+0x{delta:x}" if delta > 0 else "+0x0",
                }
            else:
                # 2. Check for string matches in data sections or exact string address
                try:
                    cur.execute(
                        "SELECT address, value, string_type, length FROM strings WHERE address = ? OR (address <= ? AND address + length > ?) LIMIT 1",
                        (va, va, va),
                    )
                    s_row = cur.fetchone()
                    if s_row:
                        s_addr = int(s_row[0])
                        symbol_info = {
                            "type": "string",
                            "address": s_addr,
                            "address_hex": f"0x{s_addr:x}",
                            "value": s_row[1],
                            "string_type": s_row[2],
                            "length": s_row[3],
                            "offset": va - s_addr,
                            "delta_str": f"+0x{va - s_addr:x}" if (va - s_addr) > 0 else "+0x0",
                        }
                except sqlite3.Error:
                    pass

                # 3. Check for RTTI class / vtable references
                if not symbol_info:
                    try:
                        cur.execute(
                            "SELECT class_name, demangled_name, vtable_addr, type_descriptor_addr FROM rtti_classes WHERE vtable_addr = ? OR type_descriptor_addr = ? OR (vtable_addr <= ? AND vtable_addr + 1024 > ?) LIMIT 1",
                            (va, va, va, va),
                        )
                        r_row = cur.fetchone()
                        if r_row:
                            vt_addr = int(r_row[2]) if r_row[2] else 0
                            symbol_info = {
                                "type": "rtti",
                                "class_name": r_row[0],
                                "demangled_name": r_row[1],
                                "vtable_addr": vt_addr,
                                "vtable_addr_hex": f"0x{vt_addr:x}" if vt_addr else None,
                                "type_descriptor_addr": int(r_row[3]) if r_row[3] else None,
                                "offset": (va - vt_addr) if vt_addr else 0,
                                "delta_str": f"+0x{(va - vt_addr):x}" if vt_addr and (va - vt_addr) > 0 else "+0x0",
                            }
                    except sqlite3.Error:
                        pass

                # 4. If in code section and not inside any function, find nearest preceding function
                if not symbol_info and sec and sec.get("is_code"):
                    try:
                        cur.execute(
                            "SELECT name, address, size FROM functions WHERE address <= ? ORDER BY address DESC LIMIT 1",
                            (va,),
                        )
                        near_row = cur.fetchone()
                        if near_row:
                            fn_name = near_row[0]
                            fn_addr = int(near_row[1])
                            fn_size = int(near_row[2])
                            delta = va - fn_addr
                            symbol_info = {
                                "type": "nearest_function",
                                "name": fn_name,
                                "base_address": fn_addr,
                                "base_address_hex": f"0x{fn_addr:x}",
                                "size": fn_size,
                                "offset": delta,
                                "delta_str": f"+0x{delta:x}" if delta > 0 else "+0x0",
                            }
                    except sqlite3.Error:
                        pass
        finally:
            if own_conn:
                conn.close()

    result: Dict[str, Any] = {
        "input": str(addr_input),
        "input_type": input_type,
        "va": va,
        "va_hex": f"0x{va:x}",
        "rva": rva,
        "rva_hex": f"0x{rva:x}",
        "file_offset": file_offset,
        "file_offset_hex": f"0x{file_offset:x}" if file_offset is not None else None,
        "image_base": image_base,
        "image_base_hex": f"0x{image_base:x}",
        "section": {
            "name": sec["name"],
            "permissions": sec["permissions"],
            "is_code": sec["is_code"],
            "is_data": sec["is_data"],
            "rva": sec["rva"],
            "rva_hex": f"0x{sec['rva']:x}",
            "virtual_size": sec["virtual_size"],
            "raw_offset": sec["raw_offset"],
            "raw_offset_hex": f"0x{sec['raw_offset']:x}",
            "raw_size": sec["raw_size"],
        }
        if sec
        else None,
        "symbol": symbol_info,
    }
    return result


def execute_cmd_addr(args: argparse.Namespace, conn: Optional[sqlite3.Connection] = None) -> int:
    """CLI execution handler for 'agyis re addr'."""
    addr_input = args.address
    binary = getattr(args, "binary", None)
    bin_path = resolve_binary_path(binary)
    if not bin_path:
        target_name = binary or "target binary"
        print(f"[!] Error: Binary '{target_name}' not found. Specify --binary or place in .dirtyroom/binaries/.", file=sys.stderr)
        if conn:
            conn.close()
        return 1

    close_conn = False
    if conn is None:
        try:
            from harness.re.scaffold import get_dirtyroom_db
            conn = get_dirtyroom_db()
            close_conn = conn is not None
        except Exception:
            conn = None

    try:
        info = inspect_address(bin_path, addr_input, db_conn=conn)
    except Exception as e:
        print(f"[!] Error inspecting address '{addr_input}': {e}", file=sys.stderr)
        return 1
    finally:
        if conn and close_conn:
            conn.close()

    if getattr(args, "json", False):
        print(json.dumps(info, indent=2))
        return 0

    print(f"=== Address Inspection: {info['input']} ({info['input_type']}) ===")
    print(f"  Binary:      {bin_path.name}")
    print(f"  VA:          {info['va_hex']} ({info['va']})")
    print(f"  RVA:         {info['rva_hex']} (+{info['rva']})")
    fo_str = f"{info['file_offset_hex']} ({info['file_offset']})" if info['file_offset'] is not None else "N/A (unmapped/virtual-only)"
    print(f"  File Offset: {fo_str}")
    if info.get("section"):
        sec = info["section"]
        print(f"  Section:     {sec['name']} [{sec['permissions']}] (RVA: {sec['rva_hex']}..0x{sec['rva'] + sec['virtual_size']:x})")
    else:
        print(f"  Section:     None (outside mapped sections)")

    sym = info.get("symbol")
    if sym:
        sym_type = sym.get("type", "symbol")
        if sym_type == "function":
            print(f"  Procedure:   {sym['name']} ({sym['delta_str']} from {sym['base_address_hex']}, size: {sym['size']} bytes)")
        elif sym_type == "nearest_function":
            print(f"  Nearest Fn:  {sym['name']} ({sym['delta_str']} from {sym['base_address_hex']}, size: {sym['size']} bytes)")
        elif sym_type == "string":
            print(f"  String:      \"{sym['value']}\" [{sym['string_type']}] (at {sym['address_hex']}, len: {sym['length']})")
        elif sym_type == "rtti":
            vt_hex = sym.get("vtable_addr_hex") or "0x0"
            print(f"  RTTI Class:  {sym['class_name']} ({sym['demangled_name']}) at vtable {vt_hex}")
        else:
            print(f"  Symbol:      {sym}")
    else:
        print(f"  Procedure:   (no symbol matched in dirtyroom symbol database)")

    return 0

