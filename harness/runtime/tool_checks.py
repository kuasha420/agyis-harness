# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Arafat Zahan (@kuasha420)
# Corporate Stewardship & Infrastructure: Purrfect Software Limited (PSL)
# Governed by: ICARO-42/b Ordinance (Company-Supported Personal IP Framework)

"""
Toolchain and binary version checks for Agyis Harness (ADR-014 / Antigravity Immune System).
"""

from __future__ import annotations

import json
import os
from pathlib import Path
import platform
import re
import shutil
import subprocess
from typing import Any, Dict, List, Optional, Tuple

REPO_ROOT = Path(__file__).resolve().parent.parent.parent

__all__ = [
    "REPO_ROOT",
    "check_cli_binary",
    "check_psl_collision",
    "check_tool",
    "detect_os_family",
    "find_hermetic_uv_python",
    "parse_version",
    "version_less_than",
]


def parse_version(v_str: str) -> Tuple[int, ...]:
    """Parse version string into integer tuple for comparison."""
    parts = re.findall(r"\d+", v_str)
    return tuple(int(p) for p in parts) if parts else (0,)


def version_less_than(v1: Tuple[int, ...], v2: Tuple[int, ...]) -> bool:
    """Compare two version tuples with zero-padding for differing lengths."""
    max_len = max(len(v1), len(v2))
    v1_padded = v1 + (0,) * (max_len - len(v1))
    v2_padded = v2 + (0,) * (max_len - len(v2))
    return v1_padded < v2_padded


def detect_os_family() -> str:
    """Detect operating system family for package manager suggestions."""
    sys_name = platform.system().lower()
    if sys_name == "darwin":
        return "darwin"

    os_release = Path("/etc/os-release")
    if os_release.exists():
        content = os_release.read_text().lower()
        if "arch" in content or "endeavouros" in content or "manjaro" in content:
            return "arch"
        if "debian" in content or "ubuntu" in content or "pop" in content:
            return "debian"
        if "fedora" in content or "rhel" in content or "centos" in content:
            return "fedora"
    return "linux"


def find_hermetic_uv_python() -> Optional[Path]:
    """Find installed CPython 3.12+ in uv's toolchain directory."""
    uv_python_dir = Path.home() / ".local/share/uv/python"
    if not uv_python_dir.exists():
        return None

    for candidate in sorted(uv_python_dir.glob("cpython-3.1[2-9]*/bin/python3"), reverse=True):
        if candidate.is_file() and os.access(candidate, os.X_OK):
            return candidate
    return None


def check_psl_collision() -> Dict[str, Any]:
    """Audit host 'psl' binary to detect collisions with system libpsl or non-harness binaries."""
    psl_path = shutil.which("psl")
    if not psl_path:
        return {
            "status": "NOT_FOUND",
            "path": None,
            "collision": False,
            "details": "psl binary not found on PATH.",
            "remediation": "Deploy the PSL launcher via 'python3 -m harness.cli install' or ensure ~/.local/bin is on PATH.",
        }

    is_harness = False
    try:
        with open(psl_path, "r", encoding="utf-8", errors="ignore") as f:
            content = f.read(2048)
            if "harness" in content or "agyis" in content:
                is_harness = True
    except OSError:
        pass

    if psl_path in ("/usr/bin/psl", "/bin/psl"):
        return {
            "status": "WARNING",
            "path": psl_path,
            "collision": True,
            "details": f"Collision detected: 'psl' resolves to system libpsl ({psl_path}).",
            "remediation": (
                "Prepend user bin directory (~/.local/bin) to PATH before /usr/bin:\n"
                "    export PATH=\"$HOME/.local/bin:$PATH\"\n"
                "And ensure the launcher is installed via: python3 -m harness.cli install"
            ),
        }

    if not is_harness:
        return {
            "status": "WARNING",
            "path": psl_path,
            "collision": True,
            "details": f"Collision detected: 'psl' resolves to non-harness binary ({psl_path}).",
            "remediation": (
                "Ensure PSL harness bin directory is prioritized in PATH:\n"
                "    export PATH=\"$HOME/.local/bin:$PATH\"\n"
                "And ensure the launcher is installed via: python3 -m harness.cli install"
            ),
        }

    return {
        "status": "OK",
        "path": psl_path,
        "collision": False,
        "details": f"psl binary correctly resolves to PSL Harness launcher ({psl_path}).",
        "remediation": None,
    }


def check_cli_binary() -> Dict[str, Any]:
    """Audit host CLI binaries: probes 'agyis' as primary binary and checks 'psl' availability/collision."""
    agyis_path = shutil.which("agyis")
    psl_info = check_psl_collision()

    is_agyis_harness = False
    if agyis_path:
        try:
            with open(agyis_path, "r", encoding="utf-8", errors="ignore") as f:
                content = f.read(2048)
                if "harness" in content or "agyis" in content:
                    is_agyis_harness = True
        except OSError:
            pass

    psl_collision_flag = psl_info.get("collision", False)

    if not agyis_path:
        agyis_status = "WARNING"
        if psl_info.get("status") == "OK":
            agyis_details = (
                f"'agyis' primary binary not found on PATH (legacy 'psl' detected at {psl_info.get('path')})."
            )
            remediation = (
                "Deploy the primary 'agyis' launcher via 'python3 -m harness.cli install' or ensure ~/.local/bin is on PATH."
            )
        else:
            agyis_details = "'agyis' binary not found on PATH."
            remediation = (
                "Deploy the Agyis launcher via 'python3 -m harness.cli install' or ensure ~/.local/bin is on PATH."
            )
        status = "WARNING"
        collision = psl_collision_flag
        details = agyis_details
    elif not is_agyis_harness:
        agyis_status = "WARNING"
        collision = True
        status = "WARNING"
        agyis_details = f"Collision detected: 'agyis' resolves to non-harness binary ({agyis_path})."
        details = agyis_details
        remediation = (
            "Ensure Agyis harness bin directory is prioritized in PATH:\n"
            "    export PATH=\"$HOME/.local/bin:$PATH\"\n"
            "And ensure the launcher is installed via: python3 -m harness.cli install"
        )
    elif psl_collision_flag:
        agyis_status = "OK"
        collision = True
        status = "WARNING"
        agyis_details = f"'agyis' binary correctly resolves to Agyis Harness launcher ({agyis_path})."
        details = (
            f"'agyis' launcher verified ({agyis_path}), but legacy 'psl' collision detected: {psl_info.get('details')}"
        )
        remediation = psl_info.get("remediation")
    else:
        agyis_status = "OK"
        collision = False
        status = "OK"
        agyis_details = f"'agyis' binary correctly resolves to Agyis Harness launcher ({agyis_path})."
        details = agyis_details
        remediation = None

    return {
        "status": status,
        "primary_binary": "agyis",
        "path": agyis_path,
        "agyis_path": agyis_path,
        "agyis_status": agyis_status,
        "agyis_details": agyis_details,
        "psl_path": psl_info.get("path"),
        "collision": collision,
        "details": details,
        "remediation": remediation,
        "psl_details": psl_info,
        "psl_collision": psl_info,
    }


def check_tool(
    name: str,
    spec: Dict[str, Any],
    hermetic_python_path: Optional[Path] = None
) -> Dict[str, Any]:
    """Audit an individual tool against its matrix specification."""
    binary = spec.get("binary", name)
    fallback = spec.get("fallback_binary")
    min_version_str = spec.get("min_version")
    optional = spec.get("optional", False)

    # 1. Resolve binary in PATH
    resolved_path = shutil.which(binary)
    if not resolved_path and fallback:
        resolved_path = shutil.which(fallback)
        if resolved_path:
            binary = fallback

    # For "uv", probe candidate user paths (~/.local/bin/uv, ~/.cargo/bin/uv) if not found on PATH
    if not resolved_path and (name == "uv" or binary == "uv"):
        for cand in (Path.home() / ".local/bin/uv", Path.home() / ".cargo/bin/uv"):
            if cand.exists() and os.access(cand, os.X_OK):
                resolved_path = str(cand)
                break

    # Check for pyenv/conda shim hijacking
    is_shim = False
    shim_details = None
    if resolved_path:
        p_lower = resolved_path.lower()
        if ".pyenv/shims" in p_lower or ".pyenv/versions" in p_lower:
            is_shim = True
            shim_details = "pyenv shim active in PATH"
        elif "conda" in p_lower or "miniconda" in p_lower:
            is_shim = True
            shim_details = "conda environment active in PATH"

    # Check for libpsl / non-harness collision if auditing psl or agyis
    is_collision = False
    collision_details = None
    if (name in ("psl", "agyis") or binary in ("psl", "agyis")) and resolved_path:
        is_harness = False
        try:
            with open(resolved_path, "r", encoding="utf-8", errors="ignore") as f:
                content = f.read(2048)
                if "harness" in content or "agyis" in content:
                    is_harness = True
        except OSError:
            pass
        if (binary == "psl" and resolved_path in ("/usr/bin/psl", "/bin/psl")) or not is_harness:
            is_collision = True
            collision_details = f"Collision detected: '{binary}' resolves to non-harness binary ({resolved_path})"

    if not resolved_path:
        return {
            "name": name,
            "binary": binary,
            "status": "OPTIONAL_MISSING" if optional else "MISSING",
            "path": None,
            "version": None,
            "min_version": min_version_str,
            "is_shim": False,
            "shim_details": None,
            "is_collision": False,
            "collision_details": None,
            "spec": spec,
        }

    # 2. Extract version
    version_str = None
    cmd = spec.get("version_command", f"{binary} --version")
    if resolved_path:
        if cmd.startswith(f"{binary} "):
            cmd = f'"{resolved_path}" ' + cmd[len(binary) + 1:]
        elif cmd == binary:
            cmd = f'"{resolved_path}"'
    regex = spec.get("version_regex", r"([0-9]+\.[0-9]+(?:\.[0-9]+)?)")
    try:
        proc = subprocess.run(
            cmd,
            shell=True,
            capture_output=True,
            text=True,
            timeout=3,
        )
        combined_out = (proc.stdout + " " + proc.stderr).strip()
        m = re.search(regex, combined_out)
        if m:
            version_str = m.group(1)
    except Exception:
        version_str = None

    # 3. Version comparison
    status = "OK"
    if not version_str:
        status = "UNKNOWN_VERSION"
    elif min_version_str:
        current_v = parse_version(version_str)
        required_v = parse_version(min_version_str)
        if version_less_than(current_v, required_v):
            status = "OUTDATED"
        elif is_shim or is_collision:
            status = "WARNING"
        else:
            status = "OK"
    elif is_shim or is_collision:
        status = "WARNING"

    return {
        "name": name,
        "binary": binary,
        "status": status,
        "path": resolved_path,
        "version": version_str,
        "min_version": min_version_str,
        "is_shim": is_shim,
        "shim_details": shim_details,
        "is_collision": is_collision,
        "collision_details": collision_details,
        "spec": spec,
    }

