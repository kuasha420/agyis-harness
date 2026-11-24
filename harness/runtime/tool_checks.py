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
import shlex
import shutil
import subprocess
from typing import Any, Dict, List, Optional, Tuple

from .tool_checks_common import (
    check_node_toolchain,
    is_rea_node_compatible,
    parse_version,
    version_less_than,
)

REPO_ROOT = Path(__file__).resolve().parent.parent.parent

__all__ = [
    "REPO_ROOT",
    "check_cli_binary",
    "check_node_toolchain",
    "check_psl_collision",
    "check_rea_tooling",
    "check_tool",
    "configure_rea_mcp_server",
    "detect_os_family",
    "find_hermetic_uv_python",
    "find_jdk21_path",
    "find_rea_binary",
    "is_ghidra_12_2_installed",
    "is_rea_mcp_configured",
    "is_rea_node_compatible",
    "parse_version",
    "version_less_than",
]


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

    # For "python", honor hermetic_python_path if host python is missing
    hermetic_str: Optional[str] = None
    if hermetic_python_path is not None and (name == "python" or binary in ("python3", "python")):
        hp = Path(hermetic_python_path)
        if hp.is_file() and os.access(hp, os.X_OK):
            hermetic_str = str(hp)
            if not resolved_path:
                resolved_path = hermetic_str

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
        if is_shim and hermetic_str:
            shim_details = f"{shim_details} (hermetic uv Python ready at {hermetic_str})"

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

    # 2. Extract version (prefer argv list / shell=False; shlex.quote if shell pipeline required)
    version_str = None
    raw_cmd = spec.get("version_command", f"{binary} --version")
    needs_shell = any(tok in raw_cmd for tok in ("|", "&&", "||", ";", ">", "<", "`", "$("))
    regex = spec.get("version_regex", r"([0-9]+\.[0-9]+(?:\.[0-9]+)?)")
    try:
        if needs_shell:
            quoted_bin = shlex.quote(resolved_path)
            if raw_cmd.startswith(f"{binary} "):
                shell_cmd = f"{quoted_bin} " + raw_cmd[len(binary) + 1:]
            elif raw_cmd == binary:
                shell_cmd = quoted_bin
            else:
                shell_cmd = raw_cmd
            proc = subprocess.run(
                shell_cmd,
                shell=True,
                capture_output=True,
                text=True,
                timeout=3,
            )
        else:
            argv = shlex.split(raw_cmd)
            if argv and argv[0] == binary:
                argv[0] = resolved_path
            elif not argv:
                argv = [resolved_path, "--version"]
            proc = subprocess.run(
                argv,
                shell=False,
                capture_output=True,
                text=True,
                timeout=3,
            )
        stdout_s = proc.stdout if isinstance(proc.stdout, str) else ""
        stderr_s = proc.stderr if isinstance(proc.stderr, str) else ""
        combined_out = (stdout_s + " " + stderr_s).strip()
        m = re.search(regex, combined_out)
        if m:
            version_str = m.group(1)
    except (subprocess.SubprocessError, OSError, ValueError):
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

    result_dict = {
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
    if hermetic_str:
        result_dict["hermetic_python_path"] = hermetic_str
    return result_dict


from .tool_checks_rea import (  # noqa: E402, F401
    _is_jdk21_or_higher,
    _parse_rea_providers,
    check_rea_tooling,
    configure_rea_mcp_server,
    find_jdk21_path,
    find_rea_binary,
    is_ghidra_12_2_installed,
    is_rea_mcp_configured,
)
