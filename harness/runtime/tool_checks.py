# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Purrfect Software Limited (PSL)

"""
Toolchain and binary version checks for PSL Harness (ADR-014).
"""

from __future__ import annotations

import os
from pathlib import Path
import platform
import re
import shutil
import subprocess
from typing import Any, Dict, Optional, Tuple

REPO_ROOT = Path(__file__).resolve().parent.parent.parent


def parse_version(v_str: str) -> Tuple[int, ...]:
    """Parse version string into integer tuple for comparison."""
    parts = re.findall(r"\d+", v_str)
    return tuple(int(p) for p in parts) if parts else (0,)


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
            if "harness" in content:
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

    # Check for libpsl / non-harness collision if auditing psl
    is_collision = False
    collision_details = None
    if (name == "psl" or binary == "psl") and resolved_path:
        is_harness = False
        try:
            with open(resolved_path, "r", encoding="utf-8", errors="ignore") as f:
                if "harness" in f.read(2048):
                    is_harness = True
        except OSError:
            pass
        if resolved_path in ("/usr/bin/psl", "/bin/psl") or not is_harness:
            is_collision = True
            collision_details = f"Collision detected: 'psl' resolves to non-harness binary ({resolved_path})"

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
        if current_v < required_v:
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
