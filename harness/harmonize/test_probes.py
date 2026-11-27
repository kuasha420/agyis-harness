# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Arafat Zahan (@kuasha420)
# Corporate Stewardship & Infrastructure: Purrfect Software Limited (PSL)
# Governed by: ICARO-42/b Ordinance (Company-Supported Personal IP Framework)

"""
Test Manifest & Capability Probes for Test Runner Harmonization (v1.1.2 / WS2).

Provides formatting-preserving JSON I/O, bounded nested Node manifest discovery,
Playwright/axe E2E/a11y detection, Python runner capability probing, and safe
tier script planning.
"""

from __future__ import annotations

import importlib.util
import json
import os
from pathlib import Path
import re
import shutil
from typing import Any, Dict, List, Optional, Tuple, Union

from harness.discovery_manifest import (
    pm_exec_prefix,
    pm_script_command,
    resolve_node_package_manager,
)

_SKIP_NODE_DIRS = frozenset({
    "node_modules",
    "dist",
    ".git",
    "build",
    ".next",
    ".turbo",
    ".venv",
    "venv",
    "__pycache__",
    ".agyis",
    "coverage",
    "out",
})
_VRT_PACKAGES = frozenset({
    "pixelmatch",
    "jest-image-snapshot",
    "reg-suit",
    "chromatic",
    "@percy/playwright",
    "@percy/cypress",
    "backstopjs",
    "loki",
})
_AXE_PACKAGES = frozenset({
    "axe-core",
    "vitest-axe",
    "@axe-core/playwright",
    "jest-axe",
    "@axe-core/react",
    "@axe-core/cli",
    "pa11y",
})


def read_json_formatting(path: Path) -> Tuple[Dict[str, Any], Union[str, int], bool]:
    """Read a JSON object while preserving indentation style and trailing newline."""
    text = path.read_text(encoding="utf-8")
    trailing_newline = text.endswith("\n")
    data = json.loads(text)
    if not isinstance(data, dict):
        raise ValueError(f"Expected JSON object in {path}")

    indent: Union[str, int] = 2
    for line in text.splitlines():
        if not line or not line[0].isspace():
            continue
        if line.startswith("\t"):
            indent = "\t"
            break
        spaces = len(line) - len(line.lstrip(" "))
        if spaces > 0:
            indent = spaces
            break

    return data, indent, trailing_newline


def format_json_with_style(
    data: Dict[str, Any],
    indent: Union[str, int],
    trailing_newline: bool,
) -> str:
    """Serialize JSON preserving unicode characters, indentation, and trailing newline."""
    rendered = json.dumps(data, indent=indent, ensure_ascii=False)
    return f"{rendered}\n" if trailing_newline else rendered


def discover_node_manifests(workspace_path: Path) -> List[Path]:
    """Discover root `package.json` and depth <= 2 nested manifests safely."""
    ws = Path(workspace_path)
    if not ws.is_dir():
        return []

    found: List[Path] = []
    root_pkg = ws / "package.json"
    if root_pkg.is_file():
        found.append(root_pkg)

    nested: List[Path] = []
    for dirpath, dirnames, filenames in os.walk(ws):
        rel_parts = Path(dirpath).relative_to(ws).parts
        dirnames[:] = sorted(
            d for d in dirnames
            if d not in _SKIP_NODE_DIRS and not d.startswith(".")
        )
        if len(rel_parts) >= 2:
            dirnames[:] = []
        if rel_parts and "package.json" in filenames:
            nested.append(Path(dirpath) / "package.json")

    nested.sort()
    found.extend(nested)
    return found


def detect_node_e2e_and_a11y(workspace_path: Path, pkg_data: Dict[str, Any]) -> Dict[str, Any]:
    """Detect Playwright E2E, visual regression, and axe accessibility runners."""
    ws = Path(workspace_path)
    raw_deps = pkg_data.get("dependencies") if isinstance(pkg_data.get("dependencies"), dict) else {}
    raw_dev = pkg_data.get("devDependencies") if isinstance(pkg_data.get("devDependencies"), dict) else {}
    deps = {**raw_deps, **raw_dev}
    scripts = pkg_data.get("scripts") if isinstance(pkg_data.get("scripts"), dict) else {}

    playwright_cfgs = sorted(ws.glob("playwright.config.*"))
    e2e_dir = next((d for d in (ws / "e2e", ws / "tests" / "e2e") if d.is_dir()), None)
    has_playwright = bool(
        "@playwright/test" in deps
        or "playwright" in deps
        or playwright_cfgs
        or e2e_dir is not None
        or any("playwright" in str(v) for v in scripts.values())
    )
    vrt_pixel_diff = bool(has_playwright or any(pkg in deps for pkg in _VRT_PACKAGES))
    a11y_axe = bool(
        any(pkg in deps for pkg in _AXE_PACKAGES)
        or any("axe" in str(v).lower() for v in scripts.values())
    )

    secondary_runners: List[Dict[str, Any]] = []
    if has_playwright:
        pm = resolve_node_package_manager(ws, pkg_data)
        if "test:e2e" in scripts:
            e2e_cmd = pm_script_command(pm, "test:e2e")
        elif "e2e" in scripts:
            e2e_cmd = pm_script_command(pm, "e2e")
        else:
            e2e_cmd = f"{pm_exec_prefix(pm)}playwright test"

        cfg_path = playwright_cfgs[0] if playwright_cfgs else (ws / "package.json")
        secondary_runners.append({
            "manifest_type": playwright_cfgs[0].name if playwright_cfgs else "package.json",
            "manifest_path": str(cfg_path),
            "test_framework": "playwright",
            "package_manager": pm,
            "command": e2e_cmd,
            "vrt_pixel_diff": vrt_pixel_diff,
            "a11y_axe": a11y_axe,
            "missing_scripts": [] if ("test:e2e" in scripts or "e2e" in scripts) else ["test:e2e"],
        })

    return {
        "has_playwright": has_playwright,
        "playwright_config": str(playwright_cfgs[0]) if playwright_cfgs else None,
        "e2e_dir": str(e2e_dir) if e2e_dir else None,
        "vrt_pixel_diff": vrt_pixel_diff,
        "a11y_axe": a11y_axe,
        "secondary_runners": secondary_runners,
    }


def _venv_has_package(workspace_path: Path, import_name: str, dist_prefix: str) -> bool:
    for venv_name in (".venv", "venv"):
        venv_dir = workspace_path / venv_name
        if not venv_dir.is_dir():
            continue
        for site_dir in list(venv_dir.glob("lib/python*/site-packages")) + [venv_dir / "Lib" / "site-packages"]:
            if not site_dir.is_dir():
                continue
            if (site_dir / import_name).is_dir() or (site_dir / f"{import_name}.py").is_file():
                return True
            if any(site_dir.glob(f"{dist_prefix}*.dist-info")):
                return True
    return False


def detect_python_runner_caps(workspace_path: Path) -> Dict[str, Any]:
    """Probe active env and workspace .venv for pytest-picked, testmon, and ptw."""
    ws = Path(workspace_path)
    has_picked = bool(
        importlib.util.find_spec("pytest_picked") is not None
        or _venv_has_package(ws, "pytest_picked", "pytest_picked")
    )
    has_testmon = bool(
        importlib.util.find_spec("testmon") is not None
        or _venv_has_package(ws, "testmon", "pytest_testmon")
    )
    has_ptw = bool(
        shutil.which("ptw") is not None
        or (ws / ".venv" / "bin" / "ptw").is_file()
        or (ws / "venv" / "bin" / "ptw").is_file()
        or importlib.util.find_spec("pytest_watch") is not None
        or _venv_has_package(ws, "pytest_watch", "pytest_watch")
    )

    diff_cmd = "pytest --picked" if has_picked else ("pytest --testmon" if has_testmon else "pytest")
    watch_cmd = "ptw" if has_ptw else "pytest"
    return {
        "has_pytest_picked": has_picked,
        "has_pytest_testmon": has_testmon,
        "has_ptw": has_ptw,
        "diff_command": diff_cmd,
        "affected_command": "pytest",
        "pkg_command": "pytest",
        "full_command": "pytest",
        "watch_command": watch_cmd,
    }


def detect_node_framework(pkg_data: Dict[str, Any], root: Path) -> str:
    """Detect primary Node test framework from dependencies, scripts, and configs."""
    scripts = pkg_data.get("scripts") if isinstance(pkg_data.get("scripts"), dict) else {}
    raw_deps = pkg_data.get("dependencies") if isinstance(pkg_data.get("dependencies"), dict) else {}
    raw_dev = pkg_data.get("devDependencies") if isinstance(pkg_data.get("devDependencies"), dict) else {}
    deps = {**raw_deps, **raw_dev}
    test_script = str(scripts.get("test", ""))

    if "turbo" in test_script:
        return "turbo"
    if "vitest" in deps or "vitest" in test_script or any(root.glob("vitest.config.*")):
        return "vitest"
    if "jest" in deps or "jest" in test_script or any(root.glob("jest.config.*")):
        return "jest"
    if "turbo" in deps:
        return "turbo"
    if (
        "@playwright/test" in deps
        or "playwright" in deps
        or "playwright" in test_script
        or any(root.glob("playwright.config.*"))
    ):
        return "playwright"
    return "node--test"


def inspect_nested_node_manifests(
    workspace_path: Path,
    root_scripts: Dict[str, str],
) -> Tuple[List[str], List[Dict[str, Any]], Optional[str]]:
    """Inspect depth <= 2 nested package.json files for secondary/delegated runners."""
    ws = Path(workspace_path)
    root_pkg = ws / "package.json"
    nested_rel: List[str] = []
    nested_runners: List[Dict[str, Any]] = []
    delegated_framework: Optional[str] = None
    root_test_cmd = str(root_scripts.get("test", ""))

    for manifest in discover_node_manifests(ws):
        if manifest == root_pkg:
            continue
        rel = manifest.relative_to(ws).as_posix()
        nested_rel.append(rel)
        try:
            ndata = json.loads(manifest.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError, ValueError):
            continue
        if not isinstance(ndata, dict):
            continue

        nscripts = ndata.get("scripts") if isinstance(ndata.get("scripts"), dict) else {}
        nfrm = detect_node_framework(ndata, manifest.parent)
        npm_pm = resolve_node_package_manager(manifest.parent, ndata)
        rel_dir = manifest.parent.relative_to(ws).as_posix()
        if (
            delegated_framework is None
            and nfrm != "node--test"
            and re.search(rf"(?:--prefix\s+{re.escape(rel_dir)}\b|\bcd\s+{re.escape(rel_dir)}\b)", root_test_cmd)
        ):
            delegated_framework = nfrm

        has_tests = "test" in nscripts or any(k.startswith("test:") for k in nscripts) or nfrm != "node--test"
        if has_tests:
            nested_runners.append({
                "manifest_type": rel,
                "manifest_path": str(manifest),
                "test_framework": nfrm,
                "package_manager": npm_pm,
                "missing_scripts": [s for s in ("test:diff", "test:watch", "test:affected", "test:full") if s not in nscripts],
            })

    return nested_rel, nested_runners, delegated_framework


def build_node_scripts_to_inject(
    framework: str,
    pkg_manager: str,
    is_monorepo_flag: bool,
    existing_scripts: Dict[str, str],
) -> Dict[str, str]:
    """Compute safe tier script injections without invalid `-- --diff` or `test:pkg`."""
    if framework == "vitest":
        scripts = {
            "test:diff": "vitest related --run",
            "test:watch": "vitest",
            "test:affected": "vitest related --run",
            "test:full": "vitest run",
        }
        if is_monorepo_flag:
            scripts["test:pkg"] = "vitest --project"
        return scripts

    if framework == "jest":
        scripts = {
            "test:diff": "jest --findRelatedTests --passWithNoTests",
            "test:watch": "jest --watch",
            "test:affected": "jest --findRelatedTests --passWithNoTests",
            "test:full": "jest --runInBand",
        }
        if is_monorepo_flag:
            scripts["test:pkg"] = f"{pkg_manager} --filter"
        return scripts

    if framework == "turbo":
        full_cmd = f"{pkg_manager} test" if "test" in existing_scripts else "turbo run test"
        scripts = {
            "test:diff": "turbo run test --affected",
            "test:affected": "turbo run test --affected",
            "test:full": full_cmd,
        }
        if is_monorepo_flag:
            scripts["test:pkg"] = f"{pkg_manager} --filter"
        return scripts

    if framework == "playwright":
        if "test:e2e" in existing_scripts:
            base_cmd = pm_script_command(pkg_manager, "test:e2e")
        elif "e2e" in existing_scripts:
            base_cmd = pm_script_command(pkg_manager, "e2e")
        else:
            base_cmd = "playwright test"
        return {
            "test:diff": base_cmd,
            "test:watch": "playwright test --ui",
            "test:affected": base_cmd,
            "test:full": base_cmd,
        }

    test_body = str(existing_scripts.get("test", ""))
    full_cmd = f"{pkg_manager} test" if "test" in existing_scripts else "node --test"
    scripts = {
        "test:diff": full_cmd,
        "test:affected": full_cmd,
        "test:full": full_cmd,
    }
    if "node --test" in test_body and "tsx" not in test_body and "&&" not in test_body:
        scripts["test:watch"] = "node --test --watch"
    if is_monorepo_flag:
        scripts["test:pkg"] = f"{pkg_manager} --filter" if pkg_manager in ("pnpm", "yarn") else full_cmd
    return scripts


def resolve_node_manifest_commands(
    pkg_manager: str,
    framework: str,
    is_monorepo_flag: bool,
    all_scripts: Dict[str, str],
    assume_scripts_injected: bool,
) -> Tuple[str, str, Optional[str], str, Optional[str]]:
    """Resolve tier commands for Node manifests honoring mutate_package_json mode."""
    scripts = dict(all_scripts)
    if assume_scripts_injected:
        planned = build_node_scripts_to_inject(framework, pkg_manager, is_monorepo_flag, scripts)
        scripts = {**planned, **scripts}

    if "test:full" in scripts:
        full_cmd = pm_script_command(pkg_manager, "test:full")
    elif "test" in scripts:
        full_cmd = f"{pkg_manager} test"
    elif "test:unit" in scripts:
        full_cmd = pm_script_command(pkg_manager, "test:unit")
    elif "test:e2e" in scripts:
        full_cmd = pm_script_command(pkg_manager, "test:e2e")
    elif "e2e" in scripts:
        full_cmd = pm_script_command(pkg_manager, "e2e")
    elif framework == "vitest":
        full_cmd = f"{pm_exec_prefix(pkg_manager)}vitest run"
    elif framework == "jest":
        full_cmd = f"{pm_exec_prefix(pkg_manager)}jest --runInBand"
    elif framework == "playwright":
        full_cmd = f"{pm_exec_prefix(pkg_manager)}playwright test"
    elif framework == "turbo":
        full_cmd = f"{pm_exec_prefix(pkg_manager)}turbo run test"
    else:
        full_cmd = f"{pkg_manager} test"

    if "test:diff" in scripts:
        diff_cmd = pm_script_command(pkg_manager, "test:diff")
    elif framework == "vitest":
        diff_cmd = f"{pm_exec_prefix(pkg_manager)}vitest related --run"
    elif framework == "jest":
        diff_cmd = f"{pm_exec_prefix(pkg_manager)}jest --findRelatedTests --passWithNoTests"
    elif framework == "turbo":
        diff_cmd = f"{pm_exec_prefix(pkg_manager)}turbo run test --affected"
    else:
        diff_cmd = full_cmd

    affected_cmd = pm_script_command(pkg_manager, "test:affected") if "test:affected" in scripts else diff_cmd

    if "test:watch" in scripts:
        watch_cmd: Optional[str] = pm_script_command(pkg_manager, "test:watch")
    elif framework == "vitest":
        watch_cmd = f"{pm_exec_prefix(pkg_manager)}vitest"
    elif framework == "jest":
        watch_cmd = f"{pm_exec_prefix(pkg_manager)}jest --watch"
    elif framework == "playwright":
        watch_cmd = f"{pm_exec_prefix(pkg_manager)}playwright test --ui"
    else:
        watch_cmd = None

    pkg_cmd: Optional[str] = None
    if is_monorepo_flag:
        if pkg_manager in ("pnpm", "yarn"):
            pkg_cmd = f"{pkg_manager} --filter"
        elif "test:pkg" in scripts:
            pkg_cmd = pm_script_command(pkg_manager, "test:pkg")

    return diff_cmd, affected_cmd, pkg_cmd, full_cmd, watch_cmd


def _makefile_has_target(make_text: str, target_name: str) -> bool:
    """Return True if Makefile text defines an explicit rule for `target_name`."""
    if ":" in target_name:
        pattern = rf"^(?:[^:\n#=]+\s+)?{re.escape(target_name)}(?:\s*:|\s+[^:\n]*:)(?!=)"
    else:
        pattern = rf"^(?:[^:\n#=]+\s+)?{re.escape(target_name)}\s*:(?!=)(?!\S*:)"
    return bool(re.search(pattern, make_text, re.M))


def resolve_makefile_manifest_commands(
    make_path: Optional[Path],
    is_monorepo_flag: bool,
    assume_scripts_injected: bool,
) -> Tuple[str, str, Optional[str], str, Optional[str]]:
    """Resolve tier commands for Makefile manifests honoring non-mutating mode."""
    if assume_scripts_injected:
        return (
            "make test:diff",
            "make test:affected",
            "make test:pkg" if is_monorepo_flag else None,
            "make test:full",
            "make test:watch",
        )

    make_text = ""
    if make_path is not None and make_path.is_file():
        try:
            make_text = make_path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            make_text = ""

    has_test = _makefile_has_target(make_text, "test")
    has_check = _makefile_has_target(make_text, "check")
    fallback_cmd = "make check" if (not has_test and has_check) else "make test"

    full_cmd = "make test:full" if _makefile_has_target(make_text, "test:full") else fallback_cmd
    diff_cmd = "make test:diff" if _makefile_has_target(make_text, "test:diff") else full_cmd
    affected_cmd = "make test:affected" if _makefile_has_target(make_text, "test:affected") else diff_cmd
    pkg_cmd = "make test:pkg" if (is_monorepo_flag and _makefile_has_target(make_text, "test:pkg")) else None
    watch_cmd = "make test:watch" if _makefile_has_target(make_text, "test:watch") else None
    return diff_cmd, affected_cmd, pkg_cmd, full_cmd, watch_cmd


def build_secondary_runners_map(
    workspace_root: Path,
    secondary_runners: List[Dict[str, Any]],
    py_caps: Dict[str, Any],
    assume_scripts_injected: bool = True,
) -> Dict[str, Any]:
    """Build the `runners` entries for secondary polyglot/E2E/nested manifests."""
    runners: Dict[str, Any] = {}
    for sec in secondary_runners:
        sec_type = sec.get("manifest_type")
        sec_path = sec.get("manifest_path")
        sec_frm = sec.get("test_framework", "unknown")
        sec_pm = sec.get("package_manager", "unknown")
        rel_sec_path = Path(sec_path).relative_to(workspace_root).as_posix() if sec_path else sec_type
        if sec_frm == "playwright":
            e2e_cmd = sec.get("command") or f"{pm_exec_prefix(sec_pm)}playwright test"
            runners["playwright"] = {
                "manifest": rel_sec_path,
                "framework": "playwright",
                "package_manager": sec_pm,
                "diff": e2e_cmd,
                "affected": e2e_cmd,
                "full": e2e_cmd,
                "watch": "playwright test --ui",
            }
        elif sec_type and ("Cargo" in sec_type or "tauri" in sec_type):
            manifest_arg = f"--manifest-path {rel_sec_path}" if rel_sec_path != "Cargo.toml" else ""
            cmd_suffix = f" {manifest_arg}".rstrip()
            runners["cargo"] = {
                "manifest": rel_sec_path,
                "framework": sec_frm,
                "package_manager": sec_pm,
                "diff": f"cargo test{cmd_suffix}",
                "affected": f"cargo test{cmd_suffix}",
                "full": f"cargo test{cmd_suffix}",
                "watch": f"cargo watch -x test{cmd_suffix}",
            }
        elif sec_type == "pyproject.toml":
            runners["pytest"] = {
                "manifest": rel_sec_path,
                "framework": sec_frm,
                "package_manager": sec_pm,
                "diff": py_caps["diff_command"],
                "affected": py_caps["affected_command"],
                "full": py_caps["full_command"],
                "watch": py_caps["watch_command"],
            }
        elif sec_type == "Makefile":
            m_diff, m_affected, _, m_full, m_watch = resolve_makefile_manifest_commands(
                Path(sec_path) if sec_path else None,
                False,
                assume_scripts_injected,
            )
            runners["make"] = {
                "manifest": rel_sec_path,
                "framework": sec_frm,
                "package_manager": sec_pm,
                "diff": m_diff,
                "affected": m_affected,
                "full": m_full,
                "watch": m_watch,
            }
        elif sec_type and sec_type.endswith("package.json"):
            runners[sec_type] = {
                "manifest": rel_sec_path,
                "framework": sec_frm,
                "package_manager": sec_pm,
                "full": f"{sec_pm} test",
            }
    return runners


def collect_secondary_polyglot_runners(
    ws: Path,
    cargo_path: Optional[Path],
    cargo_type: Optional[str],
    pyproject_file: Path,
    make_file: Optional[Path],
    include_cargo: bool,
    include_py: bool,
) -> List[Dict[str, Any]]:
    """Collect secondary Cargo, Python, and Makefile test runner descriptors."""
    runners: List[Dict[str, Any]] = []
    if include_cargo and cargo_path and cargo_type:
        runners.append({
            "manifest_type": cargo_type,
            "manifest_path": str(cargo_path),
            "test_framework": "cargo",
            "package_manager": "cargo",
            "missing_scripts": ["test:diff", "test:watch", "test:affected", "test:pkg", "test:full"],
        })
    if include_py and pyproject_file.is_file():
        runners.append({
            "manifest_type": "pyproject.toml",
            "manifest_path": str(pyproject_file),
            "test_framework": "pytest",
            "package_manager": "uv" if (ws / "uv.lock").exists() else "pip",
            "missing_scripts": ["test:diff", "test:watch", "test:affected", "test:full"],
        })
    if make_file:
        runners.append({
            "manifest_type": "Makefile",
            "manifest_path": str(make_file),
            "test_framework": "make",
            "package_manager": "make",
            "missing_scripts": ["test:diff", "test:watch", "test:affected", "test:full"],
        })
    return runners
