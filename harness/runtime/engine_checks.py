# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Arafat Zahan (@kuasha420)
# Corporate Stewardship & Infrastructure: Purrfect Software Limited (PSL)
# Governed by: ICARO-42/b Ordinance (Company-Supported Personal IP Framework)

"""
Node.js `package.json` engines & packageManager version mismatch checks.

Pure `harness.runtime` leaf helper (never imports `harness.commands` or `harness.cli`).
"""

from __future__ import annotations

import json
from pathlib import Path
import re
import shutil
import subprocess
from typing import Any, Dict, List, Optional, Tuple, Union

_ENGINE_KEYS = ("node", "pnpm", "yarn")
_PKG_MANAGER_RE = re.compile(r"^\s*([a-zA-Z0-9_-]+)@([^\s+]+)")
_VER_TUPLE_RE = re.compile(r"^v?(\d+)(?:\.(\d+|[xX*]))?(?:\.(\d+|[xX*]))?")
_VERSION_OUT_RE = re.compile(r"v?(\d+\.\d+\.\d+|\d+\.\d+|\d+)")


def _parse_semver_spec(raw: str) -> Optional[Tuple[Tuple[int, int, int], int]]:
    """Parse a version spec into ((major, minor, patch), concrete_part_count)."""
    clean = raw.strip()
    if not clean or clean in ("*", "x", "X", "latest"):
        return ((0, 0, 0), 0)
    clean_base = clean.split("+", 1)[0].split("-", 1)[0]
    m = _VER_TUPLE_RE.match(clean_base)
    if not m:
        return None
    maj = int(m.group(1))
    g2, g3 = m.group(2), m.group(3)
    if g2 is None or g2 in ("x", "X", "*"):
        return ((maj, 0, 0), 1)
    min_v = int(g2)
    if g3 is None or g3 in ("x", "X", "*"):
        return ((maj, min_v, 0), 2)
    return ((maj, min_v, int(g3)), 3)


def _token_satisfies(installed: Tuple[int, int, int], token: str) -> bool:
    """Evaluate a single semver comparator token against installed (major, minor, patch)."""
    tok = token.strip()
    if not tok or tok in ("*", "x", "X", "latest"):
        return True

    for op in (">=", "<=", ">", "<", "^", "~", "==", "="):
        if tok.startswith(op):
            parsed = _parse_semver_spec(tok[len(op):])
            if parsed is None:
                return False
            ver, parts = parsed
            maj, min_v, pat = ver
            if parts == 0:
                return True
            if op == ">=":
                return installed >= ver
            if op == "<":
                return installed < ver
            if op == ">":
                if parts == 1:
                    return installed >= (maj + 1, 0, 0)
                if parts == 2:
                    return installed >= (maj, min_v + 1, 0)
                return installed > ver
            if op == "<=":
                if parts == 1:
                    return installed < (maj + 1, 0, 0)
                if parts == 2:
                    return installed < (maj, min_v + 1, 0)
                return installed <= ver
            if op == "^":
                if parts == 1 or maj > 0:
                    upper = (maj + 1, 0, 0)
                elif min_v > 0 or parts == 2:
                    upper = (0, min_v + 1, 0)
                else:
                    upper = (0, 0, pat + 1)
                return ver <= installed < upper
            if op == "~":
                upper = (maj + 1, 0, 0) if parts == 1 else (maj, min_v + 1, 0)
                return ver <= installed < upper
            # "=" or "=="
            if parts == 1:
                return ver <= installed < (maj + 1, 0, 0)
            if parts == 2:
                return ver <= installed < (maj, min_v + 1, 0)
            return installed == ver

    parsed = _parse_semver_spec(tok)
    if parsed is None:
        return False
    ver, parts = parsed
    maj, min_v, _ = ver
    if parts == 0:
        return True
    if parts == 1:
        return ver <= installed < (maj + 1, 0, 0)
    if parts == 2:
        return ver <= installed < (maj, min_v + 1, 0)
    return installed == ver


def semver_satisfies(version_str: str, range_expr: str) -> bool:
    """Return True when concrete `version_str` satisfies a semver `range_expr`."""
    parsed_inst = _parse_semver_spec(version_str)
    if parsed_inst is None or parsed_inst[1] == 0:
        return False
    installed = parsed_inst[0]

    expr = (range_expr or "").strip()
    if not expr or expr in ("*", "latest"):
        return True

    for raw_branch in expr.split("||"):
        branch = raw_branch.strip()
        if not branch:
            continue
        hyphen = re.match(r"^(\S+)\s+-\s+(\S+)$", branch)
        if hyphen:
            tokens = [f">={hyphen.group(1)}", f"<={hyphen.group(2)}"]
        else:
            norm = re.sub(r"([<>]=?|[=~^])\s+", r"\1", branch)
            tokens = norm.split()
        if tokens and all(_token_satisfies(installed, tok) for tok in tokens):
            return True
    return False


def _probe_cli_version(tool: str) -> Tuple[Optional[str], Optional[str]]:
    """Locate `tool` on PATH and extract its `--version` string."""
    binary = shutil.which(tool)
    if not binary:
        return None, None
    try:
        proc = subprocess.run(
            [binary, "--version"],
            capture_output=True,
            text=True,
            errors="replace",
            timeout=2.0,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return binary, None
    if proc.returncode != 0:
        return binary, None
    combined = f"{proc.stdout or ''} {proc.stderr or ''}".strip()
    match = _VERSION_OUT_RE.search(combined)
    return binary, (match.group(1) if match else None)


def _hints_for_tool(tool: str, constraint: str, pm_spec: Optional[Tuple[str, str]]) -> List[str]:
    """Build actionable remediation commands for an engine or packageManager mismatch."""
    hints: List[str] = []
    if pm_spec and pm_spec[0] in ("pnpm", "yarn"):
        hints.append("corepack enable")
        hints.append(f"corepack prepare {pm_spec[0]}@{pm_spec[1]} --activate")
    elif tool in ("pnpm", "yarn"):
        hints.append("corepack enable")

    if tool == "pnpm":
        hints.append("pnpm self-update")
        hints.append("npm install -g pnpm@latest")
    elif tool == "yarn":
        hints.append("yarn set version stable")
    elif tool == "node":
        m = re.search(r"(\d+)", constraint)
        target_maj = m.group(1) if m else "22"
        hints.append(f"pnpm env use --global {target_maj}")
    elif tool == "npm":
        hints.append("npm install -g npm@latest")
    return hints


def check_package_engines(workspace_root: Union[str, Path]) -> Dict[str, Any]:
    """Audit `package.json` `engines` and `packageManager` against active CLI binaries."""
    ws = Path(workspace_root).resolve()
    pkg_path = ws / "package.json"
    if not pkg_path.is_file():
        return {
            "status": "SKIPPED",
            "package_json": str(pkg_path),
            "package_manager": None,
            "checks": [],
            "issues": [],
            "fix_hints": [],
            "details": "No package.json found at workspace root.",
        }

    try:
        data = json.loads(pkg_path.read_text(encoding="utf-8", errors="replace"))
    except (OSError, json.JSONDecodeError):
        return {
            "status": "SKIPPED",
            "package_json": str(pkg_path),
            "package_manager": None,
            "checks": [],
            "issues": [],
            "fix_hints": [],
            "details": "Malformed or unreadable package.json.",
        }

    if not isinstance(data, dict):
        return {
            "status": "SKIPPED",
            "package_json": str(pkg_path),
            "package_manager": None,
            "checks": [],
            "issues": [],
            "fix_hints": [],
            "details": "Invalid package.json root object.",
        }

    engines = data.get("engines") if isinstance(data.get("engines"), dict) else {}
    raw_pm = data.get("packageManager")
    pm_str = raw_pm.strip() if isinstance(raw_pm, str) and raw_pm.strip() else None
    pm_spec: Optional[Tuple[str, str]] = None
    if pm_str:
        m_pm = _PKG_MANAGER_RE.match(pm_str)
        if m_pm:
            pm_spec = (m_pm.group(1).lower(), m_pm.group(2))

    constraints: List[Tuple[str, str, str]] = []
    for key in _ENGINE_KEYS:
        val = engines.get(key)
        if isinstance(val, str) and val.strip():
            constraints.append((key, "engines", val.strip()))
    if pm_spec is not None:
        constraints.append((pm_spec[0], "packageManager", f"^{pm_spec[1]}"))

    if not constraints:
        return {
            "status": "SKIPPED",
            "package_json": str(pkg_path),
            "package_manager": pm_str,
            "checks": [],
            "issues": [],
            "fix_hints": [],
            "details": "No engines or packageManager constraints declared in package.json.",
        }

    probed: Dict[str, Tuple[Optional[str], Optional[str]]] = {}
    checks: List[Dict[str, Any]] = []
    issues: List[str] = []
    fix_hints: List[str] = []
    has_error = False
    has_warning = False

    for tool, source, req_expr in constraints:
        if tool not in probed:
            probed[tool] = _probe_cli_version(tool)
        binary, inst_ver = probed[tool]
        disp_req = pm_str if (source == "packageManager" and pm_str) else req_expr

        if not binary:
            chk_status = "ERROR" if source == "engines" else "WARNING"
            msg = f"Required {tool} binary not found on PATH ({source} requires '{disp_req}')."
        elif not inst_ver:
            chk_status = "WARNING"
            msg = f"{tool} binary found at {binary}, but version could not be determined ({source} requires '{disp_req}')."
        elif semver_satisfies(inst_ver, req_expr):
            chk_status = "OK"
            msg = f"{tool} {inst_ver} satisfies {source} '{disp_req}'."
        else:
            chk_status = "ERROR" if source == "engines" else "WARNING"
            target_lbl = f"engines.{tool}" if source == "engines" else "packageManager"
            msg = f"{tool} {inst_ver} does not satisfy {target_lbl} '{disp_req}'."

        checks.append({
            "tool": tool,
            "source": source,
            "required": disp_req,
            "installed": inst_ver,
            "binary": binary,
            "status": chk_status,
            "message": msg,
        })
        if chk_status != "OK":
            issues.append(msg)
            if chk_status == "ERROR":
                has_error = True
            else:
                has_warning = True
            for hint in _hints_for_tool(tool, req_expr, pm_spec):
                if hint not in fix_hints:
                    fix_hints.append(hint)

    status = "ERROR" if has_error else ("WARNING" if has_warning else "OK")
    details = "; ".join(issues) if issues else f"All {len(checks)} package.json engine constraint(s) satisfied."
    return {
        "status": status,
        "package_json": str(pkg_path),
        "package_manager": pm_str,
        "checks": checks,
        "issues": issues,
        "fix_hints": fix_hints,
        "details": details,
    }
