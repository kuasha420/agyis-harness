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


class PESectionInfo(tuple):
    """Tuple of (image_base, sections) with is_64bit and binary_format properties."""

    def __new__(
        cls,
        image_base: int,
        sections: List[Dict[str, Any]],
        is_64bit: bool = True,
        binary_format: str = "PE",
    ):
        obj = super().__new__(cls, (image_base, sections))
        obj.image_base = image_base
        obj.sections = sections
        obj.is_64bit = is_64bit
        obj.binary_format = binary_format
        return obj


def parse_pe_sections(binary_path: Path) -> PESectionInfo:
    """Parses PE32/PE32+ header to extract ImageBase and Section Table.

    Returns:
        PESectionInfo (image_base, sections_list) with .is_64bit attribute.
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
        is_64bit = False
    elif opt_magic == 0x20B:
        image_base = struct.unpack_from("<Q", hdr, e_lfanew + 24 + 24)[0]
        is_64bit = True
    else:
        image_base = struct.unpack_from("<Q", hdr, e_lfanew + 24 + 24)[0]
        is_64bit = True

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

    return PESectionInfo(image_base, sections, is_64bit=is_64bit, binary_format="PE")


def parse_elf_sections(binary_path: Path) -> PESectionInfo:
    """Parses ELF32/ELF64 headers and section table using pure Python stdlib."""
    with open(binary_path, "rb") as f:
        ehdr = f.read(64)
        if len(ehdr) < 52 or ehdr[:4] != b"\x7fELF":
            raise ValueError(f"File '{binary_path}' is not a valid ELF executable (missing ELF magic)")

        ei_class = ehdr[4]
        ei_data = ehdr[5]
        endian = "<" if ei_data == 1 else ">" if ei_data == 2 else "<"

        if ei_class == 2:
            if len(ehdr) < 64:
                raise ValueError(f"Truncated ELF64 header in '{binary_path}'")
            is_64bit = True
            e_phoff = struct.unpack_from(endian + "Q", ehdr, 32)[0]
            e_shoff = struct.unpack_from(endian + "Q", ehdr, 40)[0]
            e_phentsize, e_phnum, e_shentsize, e_shnum, e_shstrndx = struct.unpack_from(
                endian + "HHHHH", ehdr, 54
            )
        elif ei_class == 1:
            is_64bit = False
            e_phoff = struct.unpack_from(endian + "I", ehdr, 28)[0]
            e_shoff = struct.unpack_from(endian + "I", ehdr, 32)[0]
            e_phentsize, e_phnum, e_shentsize, e_shnum, e_shstrndx = struct.unpack_from(
                endian + "HHHHH", ehdr, 42
            )
        else:
            raise ValueError(f"Unsupported ELF class {ei_class} in '{binary_path}'")

        # Determine image_base from lowest PT_LOAD p_vaddr
        load_vaddrs: List[int] = []
        if e_phoff > 0 and e_phnum > 0 and e_phentsize >= (56 if is_64bit else 32):
            f.seek(e_phoff)
            ph_data = f.read(e_phnum * e_phentsize)
            for i in range(e_phnum):
                off = i * e_phentsize
                if off + e_phentsize > len(ph_data):
                    break
                p_type = struct.unpack_from(endian + "I", ph_data, off)[0]
                if p_type == 1:  # PT_LOAD
                    p_vaddr = struct.unpack_from(
                        endian + ("Q" if is_64bit else "I"), ph_data, off + (16 if is_64bit else 8)
                    )[0]
                    load_vaddrs.append(p_vaddr)
        image_base = min(load_vaddrs) if load_vaddrs else 0

        sections: List[Dict[str, Any]] = []
        if e_shoff > 0 and e_shnum > 0 and e_shentsize >= (64 if is_64bit else 40):
            f.seek(e_shoff)
            sh_data = f.read(e_shnum * e_shentsize)

            def _read_shdr(idx: int) -> Tuple[int, int, int, int, int, int]:
                off = idx * e_shentsize
                if is_64bit:
                    sh_name, sh_type, sh_flags, sh_addr, sh_offset, sh_size = struct.unpack_from(
                        endian + "IIQQQQ", sh_data, off
                    )
                else:
                    sh_name, sh_type, sh_flags, sh_addr, sh_offset, sh_size = struct.unpack_from(
                        endian + "IIIIII", sh_data, off
                    )
                return sh_name, sh_type, sh_flags, sh_addr, sh_offset, sh_size

            shstrtab = b""
            if 0 <= e_shstrndx < e_shnum and (e_shstrndx + 1) * e_shentsize <= len(sh_data):
                _, _, _, _, str_off, str_sz = _read_shdr(e_shstrndx)
                if str_sz > 0:
                    f.seek(str_off)
                    shstrtab = f.read(str_sz)

            for i in range(e_shnum):
                if (i + 1) * e_shentsize > len(sh_data):
                    break
                sh_name, sh_type, sh_flags, sh_addr, sh_offset, sh_size = _read_shdr(i)
                if sh_type == 0:  # SHT_NULL
                    continue
                if not (sh_flags & 0x2) and sh_addr == 0:
                    continue
                name = ""
                if shstrtab and sh_name < len(shstrtab):
                    end = shstrtab.find(b"\x00", sh_name)
                    raw_name = shstrtab[sh_name:end] if end != -1 else shstrtab[sh_name:]
                    name = raw_name.decode("latin-1", errors="replace")

                is_alloc = bool(sh_flags & 0x2)
                is_write = bool(sh_flags & 0x1)
                is_exec = bool(sh_flags & 0x4)
                perms = f"{'r' if is_alloc else '-'}{'w' if is_write else '-'}{'x' if is_exec else '-'}"
                raw_size = 0 if sh_type == 8 else sh_size  # SHT_NOBITS == 8
                rva = sh_addr - image_base if sh_addr >= image_base else sh_addr
                sections.append({
                    "name": name,
                    "rva": rva,
                    "virtual_size": sh_size,
                    "raw_offset": sh_offset,
                    "raw_size": raw_size,
                    "characteristics": sh_flags,
                    "permissions": perms,
                    "is_code": is_exec,
                    "is_data": is_alloc and not is_exec,
                })

    return PESectionInfo(image_base, sections, is_64bit=is_64bit, binary_format="ELF")


def parse_binary_sections(binary_path: Path) -> PESectionInfo:
    """Auto-detects PE32/PE32+ or ELF32/ELF64 and parses its sections."""
    with open(binary_path, "rb") as f:
        magic = f.read(4)
    if magic[:2] == b"MZ":
        return parse_pe_sections(binary_path)
    if magic[:4] == b"\x7fELF":
        return parse_elf_sections(binary_path)
    raise ValueError(f"File '{binary_path}' is neither a PE (MZ) nor an ELF (\\x7fELF) executable")


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

    pe_info = parse_binary_sections(bin_path)
    image_base, sections = pe_info[0], pe_info[1]
    is_64bit = getattr(pe_info, "is_64bit", True)
    binary_format = getattr(pe_info, "binary_format", "PE")

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
            binary_id: Optional[int] = None
            try:
                cur.execute("SELECT id FROM binaries WHERE name = ? LIMIT 1", (bin_path.name,))
                brow = cur.fetchone()
                if brow:
                    binary_id = brow[0]
            except sqlite3.Error:
                binary_id = None

            # 1. Check for containing function: address <= va AND address + size > va
            if binary_id is not None:
                cur.execute(
                    "SELECT name, address, size FROM functions WHERE binary_id = ? AND address <= ? AND address + size > ? ORDER BY address DESC LIMIT 1",
                    (binary_id, va, va),
                )
            else:
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
                    str_cols = [col[1] for col in cur.execute("PRAGMA table_info(strings)").fetchall()]
                    st_col = "string_type" if "string_type" in str_cols else ("encoding" if "encoding" in str_cols else "'ascii'")
                    if binary_id is not None and "binary_id" in str_cols:
                        cur.execute(
                            f"SELECT address, value, {st_col}, length FROM strings WHERE binary_id = ? AND (address = ? OR (address <= ? AND address + length > ?)) LIMIT 1",
                            (binary_id, va, va, va),
                        )
                    else:
                        cur.execute(
                            f"SELECT address, value, {st_col}, length FROM strings WHERE address = ? OR (address <= ? AND address + length > ?) LIMIT 1",
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

                # 3. Check for RTTI class / vtable references (Schema Reflection: Defect 4)
                if not symbol_info:
                    try:
                        rtti_cols = [col[1] for col in cur.execute("PRAGMA table_info(rtti_classes)").fetchall()]
                        if "class_name" in rtti_cols:
                            vt_col = "vtable_addr" if "vtable_addr" in rtti_cols else "vtable_address"
                            td_col = "type_descriptor_addr" if "type_descriptor_addr" in rtti_cols else None
                            td_expr = td_col if td_col else "NULL"
                            if td_col:
                                cond = f"({vt_col} = ? OR {td_col} = ? OR ({vt_col} <= ? AND {vt_col} + 1024 > ?))"
                                params = [va, va, va, va]
                            else:
                                cond = f"({vt_col} = ? OR ({vt_col} <= ? AND {vt_col} + 1024 > ?))"
                                params = [va, va, va]
                            if binary_id is not None and "binary_id" in rtti_cols:
                                cond = f"binary_id = ? AND {cond}"
                                params.insert(0, binary_id)
                            cur.execute(
                                f"SELECT class_name, demangled_name, {vt_col}, {td_expr} FROM rtti_classes WHERE {cond} LIMIT 1",
                                tuple(params),
                            )
                            r_row = cur.fetchone()
                            if r_row:
                                vt_addr = int(r_row[2]) if r_row[2] else 0
                                td_addr = int(r_row[3]) if r_row[3] is not None else None
                                symbol_info = {
                                    "type": "rtti",
                                    "class_name": r_row[0],
                                    "demangled_name": r_row[1] or r_row[0],
                                    "vtable_addr": vt_addr,
                                    "vtable_addr_hex": f"0x{vt_addr:x}" if vt_addr else None,
                                    "type_descriptor_addr": td_addr,
                                    "offset": (va - vt_addr) if vt_addr else 0,
                                    "delta_str": f"+0x{(va - vt_addr):x}" if vt_addr and (va - vt_addr) > 0 else "+0x0",
                                }
                        elif "name" in rtti_cols:
                            vt_col = "vtable_address" if "vtable_address" in rtti_cols else "vtable_addr"
                            cond = f"({vt_col} = ? OR ({vt_col} <= ? AND {vt_col} + 1024 > ?))"
                            params = [va, va, va]
                            if binary_id is not None and "binary_id" in rtti_cols:
                                cond = f"binary_id = ? AND {cond}"
                                params.insert(0, binary_id)
                            cur.execute(
                                f"SELECT name, {vt_col} FROM rtti_classes WHERE {cond} LIMIT 1",
                                tuple(params),
                            )
                            r_row = cur.fetchone()
                            if r_row:
                                vt_addr = int(r_row[1]) if r_row[1] else 0
                                symbol_info = {
                                    "type": "rtti",
                                    "class_name": r_row[0],
                                    "demangled_name": r_row[0],
                                    "vtable_addr": vt_addr,
                                    "vtable_addr_hex": f"0x{vt_addr:x}" if vt_addr else None,
                                    "type_descriptor_addr": None,
                                    "offset": (va - vt_addr) if vt_addr else 0,
                                    "delta_str": f"+0x{(va - vt_addr):x}" if vt_addr and (va - vt_addr) > 0 else "+0x0",
                                }
                    except sqlite3.Error:
                        pass

                # 4. If in code section and not inside any function, find nearest preceding function
                if not symbol_info and sec and sec.get("is_code"):
                    try:
                        if binary_id is not None:
                            cur.execute(
                                "SELECT name, address, size FROM functions WHERE binary_id = ? AND address <= ? ORDER BY address DESC LIMIT 1",
                                (binary_id, va),
                            )
                        else:
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
        "is_64bit": is_64bit,
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

    try:
        info = inspect_address(bin_path, addr_input, db_conn=conn)
    except Exception as e:
        print(f"[!] Error inspecting address '{addr_input}': {e}", file=sys.stderr)
        return 1
    finally:
        if conn:
            try:
                conn.close()
            except Exception:
                pass

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

