# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Arafat Zahan (@kuasha420)
# Corporate Stewardship & Infrastructure: Purrfect Software Limited (PSL)
# Governed by: ICARO-42/b Ordinance (Company-Supported Personal IP Framework)

"""
PE32/PE32+ and ELF32/ELF64 Address Translation and Symbol Resolution (ADR-028, PSL-RE-001).
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

from harness.utils import theme

from harness.re.scaffold import resolve_binary_path

_MAX_HEADER_READ_BYTES = 16 * 1024 * 1024
_MAX_ELF_TABLE_BYTES = 4 * 1024 * 1024
_MAX_SHSTRTAB_BYTES = 16 * 1024 * 1024
_HEX_LETTER_CHARS = frozenset("abcdefABCDEF")

_PE_MACHINE_MAP = {
    0x014C: "x86",
    0x8664: "x86_64",
    0xAA64: "arm64",
    0x01C0: "arm",
    0x01C4: "arm",
    0x0200: "ia64",
}

_ELF_MACHINE_MAP = {
    3: "x86",
    62: "x86_64",
    40: "arm",
    183: "arm64",
    8: "mips",
    20: "powerpc",
    21: "powerpc",
    243: "riscv",
}

_MACHO_CPU_MAP = {
    7: "x86",
    0x01000007: "x86_64",
    12: "arm",
    0x0100000C: "arm64",
}


def parse_int_address(val: Any, default: Optional[int] = None) -> Optional[int]:
    """Parses an integer, hex string ('0x...' or unprefixed hex), or NULL safely."""
    if val is None or isinstance(val, bool):
        return default
    if isinstance(val, int):
        return val
    if isinstance(val, str):
        cleaned = val.strip()
        if not cleaned:
            return default
        try:
            low = cleaned.lower()
            if low.startswith(("0x", "-0x", "+0x")):
                return int(cleaned, 16)
            if any(ch in _HEX_LETTER_CHARS for ch in cleaned):
                return int(cleaned, 16)
            if len(cleaned) >= 8 and cleaned.startswith("0") and all(ch in "0123456789" for ch in cleaned):
                return int(cleaned, 16)
            return int(cleaned, 10)
        except ValueError:
            return default
    try:
        return int(val)
    except (TypeError, ValueError):
        return default


class PESectionInfo(tuple):
    """Tuple of (image_base, sections) with is_64bit, binary_format, and architecture properties."""

    def __new__(
        cls,
        image_base: int,
        sections: List[Dict[str, Any]],
        is_64bit: bool = True,
        binary_format: str = "PE",
        architecture: Optional[str] = None,
    ):
        obj = super().__new__(cls, (image_base, sections))
        obj.image_base = image_base
        obj.sections = sections
        obj.is_64bit = is_64bit
        obj.binary_format = binary_format
        obj.architecture = architecture
        return obj


def detect_binary_architecture(binary_path: Path) -> Tuple[str, str]:
    """Detects (format, architecture) from PE, ELF, or Mach-O binary headers."""
    try:
        with open(binary_path, "rb") as f:
            hdr = f.read(64)
            if len(hdr) >= 0x40 and hdr[:2] == b"MZ":
                e_lfanew = struct.unpack_from("<I", hdr, 0x3C)[0]
                if e_lfanew <= _MAX_HEADER_READ_BYTES:
                    f.seek(e_lfanew)
                    pe_coff = f.read(6)
                    if len(pe_coff) == 6 and pe_coff[:4] == b"PE\x00\x00":
                        machine = struct.unpack_from("<H", pe_coff, 4)[0]
                        return "pe", _PE_MACHINE_MAP.get(machine, "unknown")
                return "pe", "unknown"

            if len(hdr) >= 20 and hdr[:4] == b"\x7fELF":
                ei_data = hdr[5]
                endian = "<" if ei_data == 1 else ">" if ei_data == 2 else "<"
                e_machine = struct.unpack_from(endian + "H", hdr, 18)[0]
                return "elf", _ELF_MACHINE_MAP.get(e_machine, "unknown")

            if len(hdr) >= 8:
                magic_be = struct.unpack_from(">I", hdr, 0)[0]
                magic_le = struct.unpack_from("<I", hdr, 0)[0]
                if magic_le in (0xFEEDFACE, 0xFEEDFACF):
                    cputype = struct.unpack_from("<I", hdr, 4)[0]
                    return "macho", _MACHO_CPU_MAP.get(cputype, "unknown")
                if magic_be in (0xFEEDFACE, 0xFEEDFACF):
                    cputype = struct.unpack_from(">I", hdr, 4)[0]
                    return "macho", _MACHO_CPU_MAP.get(cputype, "unknown")
                if magic_be in (0xCAFEBABE, 0xCAFEBABF):
                    return "macho", "universal"
    except OSError:
        pass
    ext_fmt = Path(binary_path).suffix.lstrip(".").lower()
    return (ext_fmt or "unknown"), "unknown"


def parse_pe_sections(binary_path: Path) -> PESectionInfo:
    """Parses PE32/PE32+ header to extract ImageBase, architecture, and Section Table."""
    with open(binary_path, "rb") as f:
        f.seek(0, os.SEEK_END)
        file_size = f.tell()
        f.seek(0)
        dos_hdr = f.read(0x40)
        if len(dos_hdr) < 0x40 or dos_hdr[:2] != b"MZ":
            raise ValueError(f"File '{binary_path}' is not a valid PE executable (missing MZ signature)")

        e_lfanew = struct.unpack_from("<I", dos_hdr, 0x3C)[0]
        if e_lfanew < 0x40 or e_lfanew + 24 > file_size or e_lfanew > _MAX_HEADER_READ_BYTES:
            raise ValueError(f"File '{binary_path}' is missing PE signature at offset 0x{e_lfanew:x}")

        f.seek(e_lfanew)
        pe_coff = f.read(24)
        if len(pe_coff) < 24 or pe_coff[:4] != b"PE\x00\x00":
            raise ValueError(f"File '{binary_path}' is missing PE signature at offset 0x{e_lfanew:x}")

        machine = struct.unpack_from("<H", pe_coff, 4)[0]
        arch = _PE_MACHINE_MAP.get(machine, "unknown")
        num_sections = struct.unpack_from("<H", pe_coff, 6)[0]
        opt_hdr_size = struct.unpack_from("<H", pe_coff, 20)[0]

        remaining_read = min(
            max(opt_hdr_size + min(num_sections, 4096) * 40, 256),
            max(0, file_size - (e_lfanew + 24)),
            _MAX_HEADER_READ_BYTES,
        )
        tail = f.read(remaining_read)

    if len(tail) < 32:
        raise ValueError(f"Truncated PE optional header in '{binary_path}'")

    opt_magic = struct.unpack_from("<H", tail, 0)[0]
    if opt_magic == 0x10B:
        image_base = struct.unpack_from("<I", tail, 28)[0]
        is_64bit = False
    elif opt_magic == 0x20B:
        image_base = struct.unpack_from("<Q", tail, 24)[0]
        is_64bit = True
    else:
        image_base = struct.unpack_from("<Q", tail, 24)[0]
        is_64bit = True

    sec_offset = opt_hdr_size
    sections: List[Dict[str, Any]] = []
    for i in range(num_sections):
        sec_hdr = tail[sec_offset + i * 40 : sec_offset + (i + 1) * 40]
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

    return PESectionInfo(image_base, sections, is_64bit=is_64bit, binary_format="PE", architecture=arch)


def parse_elf_sections(binary_path: Path) -> PESectionInfo:
    """Parses ELF32/ELF64 headers and section table using pure Python stdlib."""
    with open(binary_path, "rb") as f:
        f.seek(0, os.SEEK_END)
        file_size = f.tell()
        f.seek(0)
        ehdr = f.read(64)
        if len(ehdr) < 52 or ehdr[:4] != b"\x7fELF":
            raise ValueError(f"File '{binary_path}' is not a valid ELF executable (missing ELF magic)")

        ei_class = ehdr[4]
        ei_data = ehdr[5]
        endian = "<" if ei_data == 1 else ">" if ei_data == 2 else "<"
        e_machine = struct.unpack_from(endian + "H", ehdr, 18)[0]
        arch = _ELF_MACHINE_MAP.get(e_machine, "unknown")

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

        # Determine image_base from lowest PT_LOAD p_vaddr (bounded read)
        load_vaddrs: List[int] = []
        if e_phoff > 0 and e_phoff < file_size and e_phnum > 0 and e_phentsize >= (56 if is_64bit else 32):
            ph_read_sz = min(e_phnum * e_phentsize, file_size - e_phoff, _MAX_ELF_TABLE_BYTES)
            f.seek(e_phoff)
            ph_data = f.read(ph_read_sz)
            max_ph = len(ph_data) // e_phentsize
            for i in range(max_ph):
                off = i * e_phentsize
                p_type = struct.unpack_from(endian + "I", ph_data, off)[0]
                if p_type == 1:  # PT_LOAD
                    p_vaddr = struct.unpack_from(
                        endian + ("Q" if is_64bit else "I"), ph_data, off + (16 if is_64bit else 8)
                    )[0]
                    load_vaddrs.append(p_vaddr)
        image_base = min(load_vaddrs) if load_vaddrs else 0

        sections: List[Dict[str, Any]] = []
        if e_shoff > 0 and e_shoff < file_size and e_shnum > 0 and e_shentsize >= (64 if is_64bit else 40):
            sh_read_sz = min(e_shnum * e_shentsize, file_size - e_shoff, _MAX_ELF_TABLE_BYTES)
            f.seek(e_shoff)
            sh_data = f.read(sh_read_sz)
            max_sh = len(sh_data) // e_shentsize

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
            if 0 <= e_shstrndx < max_sh:
                _, _, _, _, str_off, str_sz = _read_shdr(e_shstrndx)
                if 0 < str_sz and 0 <= str_off < file_size:
                    bounded_str_sz = min(str_sz, file_size - str_off, _MAX_SHSTRTAB_BYTES)
                    f.seek(str_off)
                    shstrtab = f.read(bounded_str_sz)

            for i in range(max_sh):
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

    return PESectionInfo(image_base, sections, is_64bit=is_64bit, binary_format="ELF", architecture=arch)


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
    """Translates an address between VA, RVA, File Offset, containing section, and symbol cache.

    Args:
        binary_path: Path to PE or ELF binary executable
        addr_input: Input address (integer or hex/decimal string like '0x140bc8770')
        db_conn: Optional open SQLite connection to symbols database (dirtyroom.db)

    Returns:
        Structured breakdown containing VA, RVA, File Offset, Section info, and correlated symbol.
    """
    bin_path = Path(binary_path).resolve()
    if not bin_path.is_file():
        raise FileNotFoundError(f"Binary file not found: {bin_path}")

    if isinstance(addr_input, str):
        addr_int = parse_int_address(addr_input)
        if addr_int is None:
            raise ValueError(f"Invalid address input: {addr_input}")
    else:
        addr_int = int(addr_input)

    pe_info = parse_binary_sections(bin_path)
    image_base, sections = pe_info[0], pe_info[1]
    is_64bit = getattr(pe_info, "is_64bit", True)
    architecture = getattr(pe_info, "architecture", "unknown")

    matching_rva_sec = next(
        (s for s in sections if s["rva"] <= addr_int < s["rva"] + max(s["virtual_size"], s["raw_size"])),
        None,
    )
    matching_fo_sec = next(
        (s for s in sections if s["raw_offset"] <= addr_int < s["raw_offset"] + s["raw_size"] and s["raw_size"] > 0),
        None,
    )

    # Classify input address type (handling PIE/SO ELF where image_base == 0)
    if image_base > 0 and addr_int >= image_base:
        input_type = "VA"
        va = addr_int
        rva = va - image_base
    elif matching_fo_sec and not matching_rva_sec:
        input_type = "FileOffset"
        delta = addr_int - matching_fo_sec["raw_offset"]
        rva = matching_fo_sec["rva"] + delta
        va = image_base + rva
    elif matching_rva_sec and not matching_fo_sec:
        input_type = "VA" if image_base == 0 else "RVA"
        rva = addr_int
        va = image_base + rva
    elif image_base == 0:
        input_type = "VA"
        rva = addr_int
        va = addr_int
    else:
        input_type = "RVA"
        rva = addr_int
        va = image_base + rva

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
        except (sqlite3.Error, OSError, ImportError) as exc:
            sys.stderr.write(f"[!] Warning: Could not open dirtyroom symbol database: {exc}\n")
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

            # 1. Containing function: handle positive size ranges and exact zero-size entries
            if binary_id is not None:
                cur.execute(
                    "SELECT name, address, COALESCE(size, 0) FROM functions "
                    "WHERE binary_id = ? AND ((COALESCE(size, 0) > 0 AND address <= ? AND address + COALESCE(size, 0) > ?) OR address = ?) "
                    "ORDER BY address DESC LIMIT 1",
                    (binary_id, va, va, va),
                )
            else:
                cur.execute(
                    "SELECT name, address, COALESCE(size, 0) FROM functions "
                    "WHERE ((COALESCE(size, 0) > 0 AND address <= ? AND address + COALESCE(size, 0) > ?) OR address = ?) "
                    "ORDER BY address DESC LIMIT 1",
                    (va, va, va),
                )
            fn_row = cur.fetchone()
            if fn_row:
                fn_name = fn_row[0]
                fn_addr = parse_int_address(fn_row[1], default=0) or 0
                fn_size = parse_int_address(fn_row[2], default=0) or 0
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
                # 2. String matches
                try:
                    str_cols = [col[1] for col in cur.execute("PRAGMA table_info(strings)").fetchall()]
                    st_col = "string_type" if "string_type" in str_cols else ("encoding" if "encoding" in str_cols else "'ascii'")
                    if binary_id is not None and "binary_id" in str_cols:
                        cur.execute(
                            f"SELECT address, value, {st_col}, COALESCE(length, 0) FROM strings "
                            "WHERE binary_id = ? AND (address = ? OR (COALESCE(length, 0) > 0 AND address <= ? AND address + COALESCE(length, 0) > ?)) LIMIT 1",
                            (binary_id, va, va, va),
                        )
                    else:
                        cur.execute(
                            f"SELECT address, value, {st_col}, COALESCE(length, 0) FROM strings "
                            "WHERE address = ? OR (COALESCE(length, 0) > 0 AND address <= ? AND address + COALESCE(length, 0) > ?) LIMIT 1",
                            (va, va, va),
                        )
                    s_row = cur.fetchone()
                    if s_row:
                        s_addr = parse_int_address(s_row[0], default=0) or 0
                        s_len = parse_int_address(s_row[3], default=0) or 0
                        symbol_info = {
                            "type": "string",
                            "address": s_addr,
                            "address_hex": f"0x{s_addr:x}",
                            "value": s_row[1],
                            "string_type": s_row[2],
                            "length": s_len,
                            "offset": va - s_addr,
                            "delta_str": f"+0x{va - s_addr:x}" if (va - s_addr) > 0 else "+0x0",
                        }
                except sqlite3.Error:
                    pass

                # 3. RTTI class / vtable references (Schema A & B)
                if not symbol_info:
                    try:
                        rtti_cols = [col[1] for col in cur.execute("PRAGMA table_info(rtti_classes)").fetchall()]
                        if "class_name" in rtti_cols:
                            vt_col = "vtable_addr" if "vtable_addr" in rtti_cols else "vtable_address"
                            td_col = "type_descriptor_addr" if "type_descriptor_addr" in rtti_cols else None
                            td_expr = td_col if td_col else "NULL"
                            if td_col:
                                cond = f"({vt_col} = ? OR {td_col} = ? OR ({vt_col} <= ? AND {vt_col} + 1024 > ?))"
                                params: List[Any] = [va, va, va, va]
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
                                vt_addr = parse_int_address(r_row[2], default=0) or 0
                                td_addr = parse_int_address(r_row[3], default=None)
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
                                vt_addr = parse_int_address(r_row[1], default=0) or 0
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

                # 4. Nearest preceding function inside code section
                if not symbol_info and sec and sec.get("is_code"):
                    try:
                        if binary_id is not None:
                            cur.execute(
                                "SELECT name, address, COALESCE(size, 0) FROM functions WHERE binary_id = ? AND address <= ? ORDER BY address DESC LIMIT 1",
                                (binary_id, va),
                            )
                        else:
                            cur.execute(
                                "SELECT name, address, COALESCE(size, 0) FROM functions WHERE address <= ? ORDER BY address DESC LIMIT 1",
                                (va,),
                            )
                        near_row = cur.fetchone()
                        if near_row:
                            fn_name = near_row[0]
                            fn_addr = parse_int_address(near_row[1], default=0) or 0
                            fn_size = parse_int_address(near_row[2], default=0) or 0
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

    return {
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
        "architecture": architecture,
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


def _safe_close_conn(conn: Optional[sqlite3.Connection]) -> None:
    if conn is not None:
        try:
            conn.close()
        except sqlite3.Error:
            pass


def execute_cmd_addr(args: argparse.Namespace, conn: Optional[sqlite3.Connection] = None) -> int:
    """CLI execution handler for 'agyis re addr'."""
    addr_input = args.address
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

    try:
        info = inspect_address(bin_path, addr_input, db_conn=conn)
    except Exception as e:
        print(f"[!] Error inspecting address '{addr_input}': {e}", file=sys.stderr)
        return 1
    finally:
        _safe_close_conn(conn)

    if getattr(args, "json", False):
        print(json.dumps(info, indent=2))
        return 0

    print(theme.style(f"=== Address Inspection: {info['input']} ({info['input_type']}) ===", "ink", bold=True))
    print(f"  Binary:      {bin_path.name}")
    print(f"  VA:          {info['va_hex']} ({info['va']})")
    print(f"  RVA:         {info['rva_hex']} (+{info['rva']})")
    fo_str = f"{info['file_offset_hex']} ({info['file_offset']})" if info["file_offset"] is not None else "N/A (unmapped/virtual-only)"
    print(f"  File Offset: {fo_str}")
    if info.get("section"):
        sec = info["section"]
        print(f"  Section:     {sec['name']} [{sec['permissions']}] (RVA: {sec['rva_hex']}..0x{sec['rva'] + sec['virtual_size']:x})")
    else:
        print("  Section:     None (outside mapped sections)")

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
        print("  Procedure:   (no symbol matched in dirtyroom symbol database)")

    return 0
