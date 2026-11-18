# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Arafat Zahan (@kuasha420)
# Corporate Stewardship & Infrastructure: Purrfect Software Limited (PSL)
# Governed by: ICARO-42/b Ordinance (Company-Supported Personal IP Framework)

"""
Turnkey Packet Capture Ingestion & Seed Engine (ADR-028, PSL-INV-007, PSL-INV-009).
Ingests PCAP frames into dirtyroom SQLite database and links frames to binary analysis runs.
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import shutil
import socket
import sqlite3
import struct
import subprocess
import sys
from typing import Any, Dict, List, Optional

from harness.re.registry import register_dirtyroom
from harness.re.scaffold import get_dirtyroom_db, get_dirtyroom_root, resolve_binary_path


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def ensure_db_schema_extended(conn: sqlite3.Connection) -> None:
    """Ensures packets and runs tables have binary_id and run_id columns."""
    from harness.re.scaffold import SCHEMA_SQL

    cursor = conn.cursor()
    tables = [r[0] for r in cursor.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()]
    if "packets" not in tables or "runs" not in tables:
        cursor.executescript(SCHEMA_SQL)
        conn.commit()
        return

    p_cols = [c[1] for c in cursor.execute("PRAGMA table_info(packets)").fetchall()]
    if "binary_id" not in p_cols:
        cursor.execute("ALTER TABLE packets ADD COLUMN binary_id INTEGER")
    if "run_id" not in p_cols:
        cursor.execute("ALTER TABLE packets ADD COLUMN run_id INTEGER")

    r_cols = [c[1] for c in cursor.execute("PRAGMA table_info(runs)").fetchall()]
    if "binary_id" not in r_cols:
        cursor.execute("ALTER TABLE runs ADD COLUMN binary_id INTEGER")

    cursor.execute("CREATE INDEX IF NOT EXISTS idx_packets_binary ON packets(binary_id)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_packets_run ON packets(run_id)")
    conn.commit()


def parse_pcap_packets_python(pcap_path: Path, limit: Optional[int] = None) -> List[Dict[str, Any]]:
    """Pure-Python libpcap reader. Hermetic, sub-millisecond, zero-dependency.

    Supports Ethernet (1), Linux SLL (113), Linux SLL2 (276), Loopback (0/108),
    and Raw IP (12/101), decoding IPv4 (TCP/UDP/ICMP), IPv6, and ARP frames.
    """
    if limit is not None and limit <= 0:
        return []
    with open(pcap_path, "rb") as f:
        magic = f.read(4)
        if len(magic) < 4:
            return []

        # Detect endianness & resolution
        # 0xa1b2c3d4: big-endian, microsecond
        # 0xd4c3b2a1: little-endian, microsecond
        # 0xa1b23c4d: big-endian, nanosecond
        # 0x4d3cb2a1: little-endian, nanosecond
        if magic == b"\xa1\xb2\xc3\xd4":
            endian = ">"
            ts_div = 1_000_000.0
        elif magic == b"\xd4\xc3\xb2\xa1":
            endian = "<"
            ts_div = 1_000_000.0
        elif magic == b"\xa1\xb2\x3c\x4d":
            endian = ">"
            ts_div = 1_000_000_000.0
        elif magic == b"\x4d\x3c\xb2\xa1":
            endian = "<"
            ts_div = 1_000_000_000.0
        else:
            # Not standard libpcap
            return []

        hdr_rest = f.read(20)
        if len(hdr_rest) < 20:
            return []
        link_type = struct.unpack(endian + "HHIIII", hdr_rest)[5]

        packets: List[Dict[str, Any]] = []
        frame_no = 0

        while True:
            if limit and frame_no >= limit:
                break
            rec_hdr = f.read(16)
            if len(rec_hdr) < 16:
                break
            ts_sec, ts_sub, incl_len, orig_len = struct.unpack(endian + "IIII", rec_hdr)
            if incl_len > 64 * 1024 * 1024:
                break
            data = f.read(incl_len)
            if len(data) < incl_len:
                break

            frame_no += 1
            ts = ts_sec + (ts_sub / ts_div)
            proto = "RAW"
            src_ip: Optional[str] = None
            dst_ip: Optional[str] = None
            src_port: Optional[int] = None
            dst_port: Optional[int] = None
            summary = f"Frame {frame_no} ({incl_len} bytes)"

            # Demux link-layer headers into eth_type and payload
            eth_type: Optional[int] = None
            payload = data

            if link_type == 1 and len(data) >= 14:  # Ethernet
                eth_type = struct.unpack(">H", data[12:14])[0]
                payload = data[14:]
            elif link_type == 113 and len(data) >= 16:  # Linux Cooked Capture (SLL)
                eth_type = struct.unpack(">H", data[14:16])[0]
                payload = data[16:]
            elif link_type == 276 and len(data) >= 20:  # Linux Cooked Capture v2 (SLL2)
                eth_type = struct.unpack(">H", data[0:2])[0]
                payload = data[20:]
            elif link_type in (0, 108) and len(data) >= 4:  # Loopback / Null
                family = struct.unpack("=I", data[:4])[0]
                eth_type = 0x0800 if family == 2 else (0x86DD if family in (10, 24, 28, 30) else None)
                payload = data[4:]
            elif link_type in (12, 101) and len(data) > 0:  # Raw IP
                v = data[0] >> 4
                eth_type = 0x0800 if v == 4 else (0x86DD if v == 6 else None)
                payload = data

            # Parse Network Layer
            if eth_type == 0x0800 and len(payload) >= 20 and (payload[0] >> 4) == 4:  # IPv4
                ihl = (payload[0] & 0x0F) * 4
                if ihl >= 20 and len(payload) >= ihl:
                    proto_num = payload[9]
                    src_ip = socket.inet_ntoa(payload[12:16])
                    dst_ip = socket.inet_ntoa(payload[16:20])

                    proto_names = {6: "TCP", 17: "UDP", 1: "ICMP"}
                    proto = proto_names.get(proto_num, f"IP-{proto_num}")

                    l4_data = payload[ihl:]
                    if proto_num in (6, 17) and len(l4_data) >= 4:
                        src_port, dst_port = struct.unpack(">HH", l4_data[:4])
                        summary = f"{proto} {src_ip}:{src_port} -> {dst_ip}:{dst_port} ({incl_len} bytes)"
                    else:
                        summary = f"{proto} {src_ip} -> {dst_ip} ({incl_len} bytes)"
            elif eth_type == 0x86DD and len(payload) >= 40 and (payload[0] >> 4) == 6:  # IPv6
                next_proto = payload[6]
                try:
                    src_ip = socket.inet_ntop(socket.AF_INET6, payload[8:24])
                    dst_ip = socket.inet_ntop(socket.AF_INET6, payload[24:40])
                except (ValueError, OSError):
                    src_ip = None
                    dst_ip = None

                proto_names = {6: "TCP", 17: "UDP", 58: "ICMPv6"}
                proto = proto_names.get(next_proto, f"IPv6-{next_proto}")

                l4_data = payload[40:]
                if next_proto in (6, 17) and len(l4_data) >= 4:
                    src_port, dst_port = struct.unpack(">HH", l4_data[:4])
                    summary = f"{proto} [{src_ip}]:{src_port} -> [{dst_ip}]:{dst_port} ({incl_len} bytes)"
                elif src_ip and dst_ip:
                    summary = f"{proto} [{src_ip}] -> [{dst_ip}] ({incl_len} bytes)"
                else:
                    summary = f"IPv6 packet ({incl_len} bytes)"
            elif eth_type == 0x0806 and len(payload) >= 28:  # ARP
                proto = "ARP"
                op = struct.unpack(">H", payload[6:8])[0]
                src_ip = socket.inet_ntoa(payload[14:18])
                dst_ip = socket.inet_ntoa(payload[24:28])
                if op == 1:
                    summary = f"ARP: Who has {dst_ip}? Tell {src_ip}"
                elif op == 2:
                    summary = f"ARP: {src_ip} is at reply"
                else:
                    summary = f"ARP packet ({incl_len} bytes)"

            packets.append({
                "frame_number": frame_no,
                "timestamp": ts,
                "proto": proto,
                "src_ip": src_ip,
                "dst_ip": dst_ip,
                "src_port": src_port,
                "dst_port": dst_port,
                "payload_len": incl_len,
                "summary": summary,
            })

        return packets


def parse_pcap_packets_tshark(pcap_path: Path, limit: Optional[int] = None) -> List[Dict[str, Any]]:
    """Extracts packet frames via tshark CLI when available."""
    if limit is not None and limit <= 0:
        return []
    tshark = shutil.which("tshark")
    if not tshark:
        return []

    cmd = [
        tshark,
        "-r", str(pcap_path),
        "-T", "fields",
        "-E", "separator=\t",
        "-e", "frame.number",
        "-e", "frame.time_epoch",
        "-e", "_ws.col.Protocol",
        "-e", "ip.src",
        "-e", "ipv6.src",
        "-e", "ip.dst",
        "-e", "ipv6.dst",
        "-e", "tcp.srcport",
        "-e", "udp.srcport",
        "-e", "tcp.dstport",
        "-e", "udp.dstport",
        "-e", "frame.len",
        "-e", "_ws.col.Info",
    ]
    if limit:
        cmd.extend(["-c", str(limit)])

    try:
        proc = subprocess.run(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            check=False,
            timeout=30.0,
        )
        if proc.returncode != 0:
            return []

        packets: List[Dict[str, Any]] = []
        for line in proc.stdout.splitlines():
            if not line.strip():
                continue
            parts = line.split("\t", 12)
            if len(parts) < 13:
                parts += [""] * (13 - len(parts))

            frame_no = int(parts[0]) if parts[0].isdigit() else len(packets) + 1
            ts = float(parts[1]) if parts[1] else 0.0
            proto = parts[2] or "UNKNOWN"
            src_ip = parts[3] or parts[4] or None
            dst_ip = parts[5] or parts[6] or None
            s_port_raw = parts[7] or parts[8]
            d_port_raw = parts[9] or parts[10]
            s_port = s_port_raw.split(",")[0] if s_port_raw else None
            d_port = d_port_raw.split(",")[0] if d_port_raw else None
            src_port = int(s_port) if s_port and s_port.isdigit() else None
            dst_port = int(d_port) if d_port and d_port.isdigit() else None
            p_len = int(parts[11]) if parts[11] and parts[11].isdigit() else 0
            summary = parts[12] or f"{proto} ({p_len} bytes)"

            packets.append({
                "frame_number": frame_no,
                "timestamp": ts,
                "proto": proto,
                "src_ip": src_ip,
                "dst_ip": dst_ip,
                "src_port": src_port,
                "dst_port": dst_port,
                "payload_len": p_len,
                "summary": summary,
            })
        return packets
    except (subprocess.SubprocessError, OSError, ValueError):
        return []


def parse_pcap(pcap_path: Path, limit: Optional[int] = None) -> List[Dict[str, Any]]:
    """Attempts pure-Python parsing first, falling back to tshark."""
    packets = parse_pcap_packets_python(pcap_path, limit=limit)
    if not packets:
        packets = parse_pcap_packets_tshark(pcap_path, limit=limit)
    return packets


def seed_packets(
    pcap_path: Optional[Path] = None,
    binary_name: Optional[str] = None,
    limit: Optional[int] = None,
    dirtyroom_root: Optional[Path] = None,
) -> Dict[str, Any]:
    """Ingests PCAP frames into dirtyroom.db packets table and links to runs."""
    if limit is not None and limit <= 0:
        return {"success": False, "error": "Parameter 'limit' must be a positive integer."}

    root = dirtyroom_root or get_dirtyroom_root()
    if not root:
        return {"success": False, "error": "No active dirtyroom found. Run 'agyis re init' first."}

    conn = get_dirtyroom_db(root)
    if not conn:
        return {"success": False, "error": f"Could not connect to dirtyroom database in {root}."}

    try:
        ensure_db_schema_extended(conn)

        # Resolve PCAP file
        resolved_pcap: Optional[Path] = None
        if pcap_path:
            direct = Path(pcap_path)
            if direct.is_file():
                resolved_pcap = direct
            elif (root / "pcaps" / pcap_path).is_file():
                resolved_pcap = root / "pcaps" / pcap_path
            elif (root / pcap_path).is_file():
                resolved_pcap = root / pcap_path
        else:
            # Auto-discover pcap
            pcaps_dir = root / "pcaps"
            if pcaps_dir.is_dir():
                candidates = sorted(
                    [p for p in pcaps_dir.glob("*.pcap*") if p.is_file()],
                    key=lambda p: p.stat().st_mtime,
                    reverse=True,
                )
                if candidates:
                    resolved_pcap = candidates[0]
            if not resolved_pcap:
                candidates = sorted(
                    [p for p in root.glob("*.pcap*") if p.is_file()],
                    key=lambda p: p.stat().st_mtime,
                    reverse=True,
                )
                if candidates:
                    resolved_pcap = candidates[0]

        if not resolved_pcap or not resolved_pcap.is_file():
            if pcap_path:
                return {"success": False, "error": f"No valid PCAP file found: {pcap_path}"}
            return {"success": False, "error": "No valid PCAP file found in dirtyroom. Specify --pcap <file>."}

        # Resolve Binary and Link to DB
        bin_path = resolve_binary_path(binary_name, dirtyroom_root=root)
        resolved_bin_name = bin_path.name if bin_path else (Path(binary_name).name if binary_name else "unknown_binary")
        binary_id: Optional[int] = None

        cursor = conn.cursor()
        cursor.execute("SELECT id FROM binaries WHERE name = ? LIMIT 1", (resolved_bin_name,))
        row = cursor.fetchone()
        if row:
            binary_id = row[0]
        else:
            # Register binary entry
            sha256 = "0" * 64
            file_size = 0
            if bin_path and bin_path.is_file():
                try:
                    st = bin_path.stat()
                    file_size = st.st_size
                    with open(bin_path, "rb") as bf:
                        sha256 = hashlib.file_digest(bf, "sha256").hexdigest()
                except OSError:
                    pass
            cursor.execute(
                "INSERT INTO binaries (name, sha256, file_size, created_at) VALUES (?, ?, ?, ?)",
                (resolved_bin_name, sha256, file_size, _utc_now_iso()),
            )
            binary_id = cursor.lastrowid

        # Create run record
        started_at = _utc_now_iso()
        cmd_repr = f"agyis re seed --pcap {resolved_pcap.name} --binary {resolved_bin_name}"
        cursor.execute(
            "INSERT INTO runs (command, started_at, exit_code, binary_id) VALUES (?, ?, ?, ?)",
            (cmd_repr, started_at, 0, binary_id),
        )
        run_id = cursor.lastrowid

        # Parse packets
        packets = parse_pcap(resolved_pcap, limit=limit)
        if not packets:
            finished_at = _utc_now_iso()
            cursor.execute("UPDATE runs SET finished_at = ?, exit_code = ? WHERE id = ?", (finished_at, 1, run_id))
            conn.commit()
            return {
                "success": False,
                "error": f"Failed to extract frames from {resolved_pcap}. Empty or unreadable capture.",
                "pcap": str(resolved_pcap),
                "binary_id": binary_id,
                "run_id": run_id,
            }

        # Ingest frames in batch
        pcap_stem = resolved_pcap.name
        rows = [
            (
                pcap_stem,
                p["frame_number"],
                p["timestamp"],
                p["proto"],
                p["src_ip"],
                p["dst_ip"],
                p["src_port"],
                p["dst_port"],
                p["payload_len"],
                p["summary"],
                binary_id,
                run_id,
            )
            for p in packets
        ]

        cursor.executemany(
            """
            INSERT INTO packets (
                pcap_name, frame_number, timestamp, proto,
                src_ip, dst_ip, src_port, dst_port,
                payload_len, summary, binary_id, run_id
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            rows,
        )

        # Finalize run
        finished_at = _utc_now_iso()
        cursor.execute("UPDATE runs SET finished_at = ? WHERE id = ?", (finished_at, run_id))
        conn.commit()

        try:
            register_dirtyroom(root)
        except OSError:
            pass

        return {
            "success": True,
            "pcap": str(resolved_pcap),
            "packets_ingested": len(packets),
            "binary_name": resolved_bin_name,
            "binary_id": binary_id,
            "run_id": run_id,
            "started_at": started_at,
            "finished_at": finished_at,
        }
    except sqlite3.Error as e:
        return {"success": False, "error": f"Database error seeding packets: {e}"}
    finally:
        conn.close()


def cmd_seed(args: argparse.Namespace) -> int:
    """CLI dispatcher for 'agyis re seed'."""
    pcap_arg = getattr(args, "pcap", None)
    binary_arg = getattr(args, "binary", None)
    limit_arg = getattr(args, "limit", None)

    res = seed_packets(
        pcap_path=Path(pcap_arg) if pcap_arg else None,
        binary_name=binary_arg,
        limit=limit_arg,
    )

    if getattr(args, "json", False):
        print(json.dumps(res, indent=2))
        return 0 if res.get("success") else 1

    if not res.get("success"):
        print(f"[!] Error: {res.get('error')}", file=sys.stderr)
        return 1

    print(f"[+] Successfully seeded PCAP into dirtyroom database:")
    print(f"    - Capture File:    {res['pcap']}")
    print(f"    - Packets Ingested: {res['packets_ingested']:,}")
    print(f"    - Linked Binary:    {res['binary_name']} (ID: {res['binary_id']})")
    print(f"    - Run ID:           {res['run_id']}")
    return 0
