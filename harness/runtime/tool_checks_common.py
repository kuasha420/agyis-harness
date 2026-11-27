# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Arafat Zahan (@kuasha420)
# Corporate Stewardship & Infrastructure: Purrfect Software Limited (PSL)
# Governed by: ICARO-42/b Ordinance (Company-Supported Personal IP Framework)

"""Shared version parsing and Node.js toolchain leaf helpers (breaks tool_checks <-> tool_checks_rea cycle)."""

from __future__ import annotations

import argparse
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
from typing import Any, Dict, Optional, Tuple


_CPYTHON_DIR_VER_RE = re.compile(r"^cpython-(\d+)\.(\d+)(?:\.(\d+))?(?:[^0-9].*)?$")


def _parse_cpython_version(name: str) -> Optional[Tuple[int, int, int]]:
    """Parse CPython version tuple (major, minor, patch) from a uv directory name."""
    match = _CPYTHON_DIR_VER_RE.match(name)
    if not match:
        return None
    return (int(match.group(1)), int(match.group(2)), int(match.group(3) or 0))


def find_hermetic_uv_python() -> Optional[Path]:
    """Find installed CPython 3.12+ in uv's toolchain directory via numeric version sort."""
    uv_python_dir = Path.home() / ".local/share/uv/python"
    if not uv_python_dir.is_dir():
        return None
    candidates: list[Tuple[Tuple[int, int, int], str, Path]] = []
    try:
        entries = list(uv_python_dir.iterdir())
    except OSError:
        return None
    for entry in entries:
        if not entry.is_dir():
            continue
        ver = _parse_cpython_version(entry.name)
        if ver is None or (ver[0], ver[1]) < (3, 12):
            continue
        python_bin = entry / "bin" / "python3"
        if python_bin.is_file() and os.access(python_bin, os.X_OK):
            candidates.append((ver, entry.name, python_bin))
    if not candidates:
        return None
    candidates.sort(key=lambda item: (item[0], item[1]), reverse=True)
    return candidates[0][2]

REA_DEPRECATION_WARNING = (
    "DeprecationWarning: '--experimental-rea' is deprecated; "
    "use '--rea' (or '--re' on doctor).\n"
)


class _DeprecatedReaAction(argparse.Action):
    """Argparse action enabling --rea while warning to stderr when --experimental-rea is passed."""

    def __init__(self, option_strings: Any, dest: str, **kwargs: Any) -> None:
        kwargs.setdefault("nargs", 0)
        kwargs.setdefault("default", False)
        super().__init__(option_strings, dest, **kwargs)

    def __call__(
        self,
        parser: argparse.ArgumentParser,
        namespace: argparse.Namespace,
        values: Any,
        option_string: Optional[str] = None,
    ) -> None:
        sys.stderr.write(REA_DEPRECATION_WARNING)
        setattr(namespace, self.dest, True)
        setattr(namespace, "rea", True)


def register_rea_flags(
    parser: argparse.ArgumentParser,
    help_text: str,
) -> None:
    """Register primary --rea flag and deprecated --experimental-rea compatibility alias."""
    parser.add_argument(
        "--rea",
        dest="rea",
        action="store_true",
        help=help_text,
    )
    parser.add_argument(
        "--experimental-rea",
        dest="experimental_rea",
        action=_DeprecatedReaAction,
        help="Deprecated alias for --rea",
    )


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


def is_rea_node_compatible(version_str: str) -> bool:
    """
    Validates Node.js version against REA 6.8+ / 6.9+ compatibility requirements:
    - 22.x: >= 22.23.4
    - 24.x: >= 24.22.1
    - 26.x+: >= 26.12.1
    """
    if not version_str or not isinstance(version_str, str):
        return False
    clean = version_str.strip().lstrip("v")
    m = re.match(r"^(\d+)\.(\d+)(?:\.(\d+))?", clean)
    if not m:
        return False
    major = int(m.group(1))
    minor = int(m.group(2))
    patch = int(m.group(3)) if m.group(3) is not None else 0
    v = (major, minor, patch)
    if major == 22:
        return v >= (22, 23, 4)
    elif major == 24:
        return v >= (24, 22, 1)
    elif major >= 26:
        return v >= (26, 12, 1)
    return False


def check_node_toolchain(
    node_bin: Optional[str | Path] = None,
    timeout: float = 2.0,
) -> Dict[str, Any]:
    """Audit host Node.js version and compatibility with REA."""
    tc_mod = sys.modules.get("harness.runtime.tool_checks")
    shutil_mod = getattr(tc_mod, "shutil", shutil) if tc_mod is not None else shutil
    sub_mod = getattr(tc_mod, "subprocess", subprocess) if tc_mod is not None else subprocess

    resolved = shutil_mod.which(str(node_bin)) if node_bin else shutil_mod.which("node")
    if not resolved:
        return {
            "status": "MISSING",
            "binary": None,
            "version": None,
            "rea_compatible": False,
            "details": "Node.js binary not found on PATH.",
            "remediation": "Install Node 24 LTS via: pnpm env use --global 24",
        }
    version_str = None
    try:
        proc = sub_mod.run(
            [str(resolved), "-v"],
            capture_output=True,
            text=True,
            errors="replace",
            timeout=timeout,
        )
        if proc.returncode == 0 and isinstance(proc.stdout, str) and proc.stdout.strip():
            raw_out = proc.stdout.strip()
            if not raw_out.lower().startswith("rea"):
                m = re.search(r"v?(\d+\.\d+(?:\.\d+)?)", raw_out)
                if m:
                    version_str = m.group(1)
    except (subprocess.TimeoutExpired, subprocess.SubprocessError, OSError):
        version_str = None

    if version_str is None:
        return {
            "status": "UNKNOWN_VERSION",
            "binary": str(resolved),
            "version": None,
            "rea_compatible": False,
            "details": f"Node.js binary detected at {resolved}, but version could not be determined.",
            "remediation": "Switch to Node 24 LTS via: pnpm env use --global 24",
        }

    compat = is_rea_node_compatible(version_str)
    if not compat:
        return {
            "status": "WARNING",
            "binary": str(resolved),
            "version": version_str,
            "rea_compatible": False,
            "details": f"Node.js {version_str} does not meet REA requirements (22.x >= 22.23.4, 24.x >= 24.22.1, or >= 26.12.1).",
            "remediation": "Switch to Node 24 LTS via: pnpm env use --global 24",
        }

    return {
        "status": "OK",
        "binary": str(resolved),
        "version": version_str,
        "rea_compatible": True,
        "details": f"Node.js {version_str} meets REA requirements.",
        "remediation": None,
    }
