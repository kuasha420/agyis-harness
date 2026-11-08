# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Arafat Zahan (@kuasha420)
# Corporate Stewardship & Infrastructure: Purrfect Software Limited (PSL)
# Governed by: ICARO-42/b Ordinance (Company-Supported Personal IP Framework)

"""
Forensic Reverse Engineering & Cleanroom Toolchain Diagnostics (Issue #100, ADR-028, PSL-INV-009).
Provides context-aware probing of decompilers, disassemblers, packet triage, and input daemons.
"""

import json
import os
from pathlib import Path
import re
import shutil
import sqlite3
import subprocess
from typing import Any, Dict, List, Optional, Tuple

from harness.re.patcher import check_patch
from harness.re.preanalyze import find_ghidra_headless
from harness.re.scaffold import get_dirtyroom_db, get_dirtyroom_root
from harness.runtime.tool_checks import find_jdk21_path, find_rea_binary, parse_version, version_less_than

# Standard package mappings for distro package manager remediation
FORENSIC_PACKAGE_MAP = {
    "arch": {
        "tshark": "wireshark-cli",
        "objdump": "binutils",
        "ydotoold": "ydotool",
        "xdotool": "xdotool",
        "gpu-screen-recorder": "gpu-screen-recorder",
    },
    "debian": {
        "tshark": "tshark",
        "objdump": "binutils",
        "ydotoold": "ydotool",
        "xdotool": "xdotool",
        "gpu-screen-recorder": "gpu-screen-recorder",
    },
    "fedora": {
        "tshark": "wireshark-cli",
        "objdump": "binutils",
        "ydotoold": "ydotool",
        "xdotool": "xdotool",
        "gpu-screen-recorder": "gpu-screen-recorder",
    },
}


def is_re_workspace(workspace_dir: Optional[Path] = None) -> bool:
    """
    Context-aware detection of Reverse Engineering & Cleanroom workspaces.
    Returns True if .dirtyroom exists, cleanroom specifications are present,
    or RE environment variables are active.
    """
    for env_k in ("AGYIS_DIRTYROOM", "IMMORTAL_DIRTYROOM", "REA_DIRTYROOM", "AGYIS_RE_FORCE"):
        if os.environ.get(env_k):
            return True

    curr = (workspace_dir or Path.cwd()).resolve()
    for parent in [curr] + list(curr.parents):
        if (parent / ".dirtyroom").is_dir():
            return True
        if (
            (parent / "docs" / "specs" / "CLEANROOM_POLICY.md").is_file()
            or (parent / "docs" / "specs" / "cleanroom_policy.md").is_file()
        ):
            return True

    return False


def get_dirtyroom_profile(workspace_dir: Optional[Path] = None) -> str:
    """
    Extracts active forensic profile from .dirtyroom/dirtyroom.env.
    Supported profiles: 'static-cleanroom' (default), 'dynamic-game-harness', 'full'.
    """
    env_override = os.environ.get("AGYIS_RE_PROFILE") or os.environ.get("DIRTYROOM_PROFILE")
    if env_override:
        return env_override.strip().lower()

    root = get_dirtyroom_root(workspace_dir)
    if root:
        env_file = root / "dirtyroom.env"
        if env_file.is_file():
            try:
                for line in env_file.read_text(encoding="utf-8").splitlines():
                    clean = line.strip()
                    if clean.startswith("export PROFILE=") or clean.startswith("PROFILE="):
                        val = clean.split("=", 1)[1].strip().strip("'\"")
                        if val:
                            return val.lower()
            except Exception:
                pass

    return "static-cleanroom"


def probe_binary_with_version(
    binary_name: str,
    version_arg: str = "--version",
    timeout: float = 0.2,
) -> Tuple[Optional[str], Optional[str]]:
    """Fast which probe (<0.001s) with bounded version extraction (<0.2s)."""
    cand = shutil.which(binary_name)
    if not cand:
        return None, None

    version_str: Optional[str] = None
    try:
        proc = subprocess.run(
            [cand, version_arg],
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
        out = (proc.stdout + " " + proc.stderr).strip()
        m = re.search(r"([0-9]+(?:\.[0-9]+)+)", out)
        if m:
            version_str = m.group(1)
    except Exception:
        pass

    return cand, version_str


def audit_forensic_toolchain(
    workspace_dir: Optional[Path] = None,
    profile: Optional[str] = None,
    timeout: float = 0.2,
) -> Dict[str, Any]:
    """
    Performs context-aware diagnostic audit of the RE and dirtyroom forensic toolchain.
    Upholds the sub-second doctor benchmark (<0.05s execution SLA).
    """
    ws = (workspace_dir or Path.cwd()).resolve()
    active_profile = profile or get_dirtyroom_profile(ws)
    is_re = is_re_workspace(ws)

    # Dynamic tools are mandatory only if profile is dynamic or full
    dynamic_required = active_profile in ("dynamic-game-harness", "dynamic", "full")

    tools: List[Dict[str, Any]] = []
    missing_packages: List[str] = []
    remediation_lines: List[str] = []

    # 1. Ghidra Headless Analyzer (Static Core)
    ghidra_bin = find_ghidra_headless()
    if ghidra_bin:
        tools.append({
            "name": "ghidra",
            "category": "core",
            "status": "PASS",
            "path": str(ghidra_bin),
            "version": "headless-ready",
            "details": f"Ghidra analyzeHeadless verified at {ghidra_bin}",
        })
    else:
        tools.append({
            "name": "ghidra",
            "category": "core",
            "status": "WARN",
            "path": None,
            "version": None,
            "details": "Ghidra analyzeHeadless not found in PATH or GHIDRA_INSTALL_DIR",
        })
        remediation_lines.append("Install Ghidra 11+ and export GHIDRA_INSTALL_DIR=/opt/ghidra")

    # 2. Java 21+ Runtime (Static Core)
    jdk_path = find_jdk21_path()
    if jdk_path:
        tools.append({
            "name": "java",
            "category": "core",
            "status": "PASS",
            "path": str(jdk_path),
            "version": ">=21",
            "details": f"OpenJDK 21+ verified at {jdk_path}",
        })
    else:
        # Check standard java binary
        j_bin, j_ver = probe_binary_with_version("java", "-version", timeout=timeout)
        if j_bin:
            java_major = 0
            if j_ver:
                try:
                    java_major = int(j_ver.split(".")[0])
                except (ValueError, IndexError):
                    m_num = re.search(r"\d+", j_ver)
                    if m_num:
                        java_major = int(m_num.group(0))
            tools.append({
                "name": "java",
                "category": "core",
                "status": "PASS" if java_major >= 17 else "WARN",
                "path": str(j_bin),
                "version": j_ver,
                "details": f"Java runtime verified at {j_bin} (version {j_ver})",
            })
        else:
            tools.append({
                "name": "java",
                "category": "core",
                "status": "WARN",
                "path": None,
                "version": None,
                "details": "Java 21+ runtime required for Ghidra decompiler",
            })
            missing_packages.append("jdk21-openjdk")
            remediation_lines.append("Install OpenJDK 21+ (e.g. sudo pacman -S jdk21-openjdk)")

    # 3. Disassembler: objdump / llvm-objdump (Static Core)
    objdump_bin, objdump_ver = probe_binary_with_version("objdump", "--version", timeout=timeout)
    if not objdump_bin:
        objdump_bin, objdump_ver = probe_binary_with_version("llvm-objdump", "--version", timeout=timeout)

    if objdump_bin:
        tools.append({
            "name": "objdump",
            "category": "core",
            "status": "PASS",
            "path": str(objdump_bin),
            "version": objdump_ver,
            "details": f"Disassembler verified ({Path(objdump_bin).name} {objdump_ver or ''})",
        })
    else:
        tools.append({
            "name": "objdump",
            "category": "core",
            "status": "WARN",
            "path": None,
            "version": None,
            "details": "objdump/llvm-objdump not found in PATH",
        })
        missing_packages.append("objdump")
        remediation_lines.append("Install binutils (e.g. sudo pacman -S binutils)")

    # 4. REA MCP Acceleration Patch (PSL-INV-009)
    patch_info = check_patch()
    p_status = patch_info.get("status")
    launcher_path_str = str(patch_info["launcher_path"]) if patch_info.get("launcher_path") else None
    if p_status == "applied":
        tools.append({
            "name": "rea_patch",
            "category": "core",
            "status": "PASS",
            "path": launcher_path_str,
            "version": "active",
            "details": "REA pre-analyzed Ghidra project acceleration patch active (PSL-INV-009)",
        })
    elif p_status in ("unapplied", "partial"):
        tools.append({
            "name": "rea_patch",
            "category": "core",
            "status": "WARN",
            "path": launcher_path_str,
            "version": p_status,
            "details": "REA acceleration patch not applied (decompiler will timeout on >10MB targets)",
        })
        remediation_lines.append("Apply REA acceleration patch: agyis re patch-rea --apply (or agyis doctor --heal)")
    else:
        tools.append({
            "name": "rea_patch",
            "category": "core",
            "status": "INFO",
            "path": None,
            "version": "not_installed",
            "details": "REA (rea-agents) package not installed in global store",
        })

    # 5. Dirtyroom SQLite Symbol Cache (Static Core)
    dr_root = get_dirtyroom_root(ws)
    if dr_root:
        db_conn = get_dirtyroom_db(dr_root)
        if db_conn:
            db_conn.close()
            tools.append({
                "name": "dirtyroom_db",
                "category": "core",
                "status": "PASS",
                "path": str(dr_root / "symbols" / "dirtyroom.db"),
                "version": "schema-ready",
                "details": f"Dirty-room SQLite database verified at {dr_root}",
            })
        else:
            tools.append({
                "name": "dirtyroom_db",
                "category": "core",
                "status": "WARN",
                "path": str(dr_root),
                "version": "missing_db",
                "details": "Dirty-room directory exists but symbols database is not initialized",
            })
            remediation_lines.append("Initialize dirtyroom database: agyis re init (or agyis doctor --heal)")
    elif is_re:
        tools.append({
            "name": "dirtyroom_db",
            "category": "core",
            "status": "INFO",
            "path": None,
            "version": "unscaffolded",
            "details": "No .dirtyroom/ directory found in workspace",
        })
        remediation_lines.append("Scaffold dirty-room structure: agyis re init")

    # 6. Packet Capture: tshark (Dynamic Forensics)
    tshark_bin, tshark_ver = probe_binary_with_version("tshark", "--version", timeout=timeout)
    t_status = "PASS" if tshark_bin else ("WARN" if dynamic_required else "INFO")
    tools.append({
        "name": "tshark",
        "category": "dynamic",
        "status": t_status,
        "path": tshark_bin,
        "version": tshark_ver,
        "details": f"Wireshark CLI verified ({tshark_bin})" if tshark_bin else "tshark not found (network frame triage)",
    })
    if not tshark_bin and dynamic_required:
        missing_packages.append("tshark")
        remediation_lines.append("Install Wireshark CLI: sudo pacman -S wireshark-cli (or sudo apt install tshark)")

    # 7. Hardware Screen Recording: gpu-screen-recorder (Dynamic Forensics)
    gsr_bin, gsr_ver = probe_binary_with_version("gpu-screen-recorder", "--version", timeout=timeout)
    gsr_status = "PASS" if gsr_bin else ("WARN" if dynamic_required else "INFO")
    tools.append({
        "name": "gpu-screen-recorder",
        "category": "dynamic",
        "status": gsr_status,
        "path": gsr_bin,
        "version": gsr_ver,
        "details": f"GPU screen recorder verified ({gsr_bin})" if gsr_bin else "gpu-screen-recorder not found (Wayland KMS capture)",
    })
    if not gsr_bin and dynamic_required:
        missing_packages.append("gpu-screen-recorder")
        remediation_lines.append("Install gpu-screen-recorder: sudo pacman -S gpu-screen-recorder")

    # 8. Wayland Input Daemon: ydotoold (Dynamic Forensics)
    ydotool_bin, ydotool_ver = probe_binary_with_version("ydotool", "--version", timeout=timeout)
    yd_status = "PASS" if ydotool_bin else ("WARN" if dynamic_required else "INFO")
    tools.append({
        "name": "ydotoold",
        "category": "dynamic",
        "status": yd_status,
        "path": ydotool_bin,
        "version": ydotool_ver,
        "details": f"Wayland uinput automation verified ({ydotool_bin})" if ydotool_bin else "ydotool/ydotoold not found in PATH",
    })
    if not ydotool_bin and dynamic_required:
        missing_packages.append("ydotoold")
        remediation_lines.append("Install ydotool: sudo pacman -S ydotool (or sudo apt install ydotool)")

    # 9. X11 Input Automation: xdotool (Dynamic Forensics)
    xdotool_bin, xdotool_ver = probe_binary_with_version("xdotool", "--version", timeout=timeout)
    xd_status = "PASS" if xdotool_bin else ("WARN" if dynamic_required else "INFO")
    tools.append({
        "name": "xdotool",
        "category": "dynamic",
        "status": xd_status,
        "path": xdotool_bin,
        "version": xdotool_ver,
        "details": f"X11 automation verified ({xdotool_bin})" if xdotool_bin else "xdotool not found in PATH",
    })
    if not xdotool_bin and dynamic_required:
        missing_packages.append("xdotool")
        remediation_lines.append("Install xdotool: sudo pacman -S xdotool (or sudo apt install xdotool)")

    pass_count = sum(1 for t in tools if t["status"] == "PASS")
    warn_count = sum(1 for t in tools if t["status"] == "WARN")
    info_count = sum(1 for t in tools if t["status"] == "INFO")

    overall_status = "warning" if warn_count > 0 else "ok"

    return {
        "is_re_workspace": is_re,
        "profile": active_profile,
        "status": overall_status,
        "tools": tools,
        "summary": {
            "total": len(tools),
            "pass": pass_count,
            "warn": warn_count,
            "info": info_count,
        },
        "missing_packages": missing_packages,
        "remediation": remediation_lines,
    }
