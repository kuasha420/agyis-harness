# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Arafat Zahan (@kuasha420)
# Corporate Stewardship & Infrastructure: Purrfect Software Limited (PSL)
# Governed by: ICARO-42/b Ordinance (Company-Supported Personal IP Framework)

"""
Test Manifest & Package-Manager Discovery Helpers (v1.1.2 / WS2).

Leaf module providing `.agyis/test_manifest.json` loading, Node package-manager
precedence (`packageManager` -> lockfiles), non-Python test surface probing, and
script-aware non-interactive guard decisions without circular dependencies.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
import re
from typing import Any, Dict, Optional, Tuple, Union

_NODE_LOCKFILES = (
    "pnpm-lock.yaml",
    ".pnpm-lock.yaml",
    "yarn.lock",
    "bun.lockb",
    "bun.lock",
    "bunfig.toml",
    "package-lock.json",
    "npm-shrinkwrap.json",
)
_IGNORED_SCAN_DIRS = frozenset({
    ".git",
    "node_modules",
    ".venv",
    "venv",
    "dist",
    "build",
    ".next",
    ".turbo",
    ".agyis",
    "__pycache__",
    "coverage",
    "out",
})
_NON_PYTHON_MANIFESTS = (
    "package.json",
    "Cargo.toml",
    "go.mod",
    "pom.xml",
    "build.gradle",
    "build.gradle.kts",
    "CMakeLists.txt",
    "mix.exs",
)
_NON_PYTHON_TEST_RE = re.compile(
    r"(?:\.(?:test|spec)\.(?:ts|tsx|js|jsx|mts|mjs|cts|cjs)|_test\.go)$"
)
_NON_WATCH_DIRECT_RE = re.compile(
    r"(?:\bturbo\b|\bnode\b[^\n]*--test\b|\btsx\b|\bplaywright\b)"
)
_NON_WATCH_BODY_RE = re.compile(
    r"(?:&&|;|\|\||\bturbo\b|\bnode\b[^\n]*--test\b|\btsx\b|\bplaywright\b"
    r"|\bmocha\b|\bava\b|\btap\b|\bvitest\s+run\b"
    r"|(?:^|\s)(?:--run|--no-watch|--watch=false|--watchAll=false|--watchAll=0)(?:\s|$)"
    r"|\b(?:npm|pnpm|yarn|bun)\s+)"
)
_COMPOUND_SHELL_RE = re.compile(r"(?:&&|\|\||;)")
_PM_TEST_CMD_RE = re.compile(
    r"\b(?P<pm>pnpm|npm|yarn|bun)\b(?![^\n]*\b(?:exec|dlx|x)\b).*?"
    r"\b(?:run\s+)?(?P<script>test(?::[\w-]+)?|e2e)\b"
)


def read_test_manifest(workspace_path: Union[Path, str]) -> Optional[Dict[str, Any]]:
    """Read and parse `.agyis/test_manifest.json` if present and valid."""
    manifest_path = Path(workspace_path) / ".agyis" / "test_manifest.json"
    if not manifest_path.is_file():
        return None
    try:
        data = json.loads(manifest_path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else None
    except (OSError, json.JSONDecodeError, ValueError):
        return None


def _extract_command_entry(entry: Any) -> Optional[str]:
    if isinstance(entry, str) and entry.strip():
        return entry.strip()
    if isinstance(entry, dict) and entry.get("supported") is not False:
        cmd = entry.get("command")
        if isinstance(cmd, str) and cmd.strip():
            return cmd.strip()
    return None


def resolve_manifest_full_command(
    workspace_path: Union[Path, str],
    manifest: Optional[Dict[str, Any]] = None,
) -> Optional[str]:
    """Resolve the full-suite executable command from `.agyis/test_manifest.json`."""
    data = manifest if manifest is not None else read_test_manifest(workspace_path)
    if not isinstance(data, dict):
        return None

    direct = _extract_command_entry(data.get("tier_3_full"))
    if direct:
        return direct

    tiers = data.get("tiers")
    if isinstance(tiers, dict):
        for key in ("tier_2b_full", "tier_3_full"):
            cmd = _extract_command_entry(tiers.get(key))
            if cmd:
                return cmd

    scripts = data.get("scripts")
    if isinstance(scripts, dict):
        cmd = _extract_command_entry(scripts.get("test:full"))
        if cmd:
            return cmd
    return None


def _load_package_json(root: Path) -> Optional[Dict[str, Any]]:
    pkg_path = root / "package.json"
    if not pkg_path.is_file():
        return None
    try:
        data = json.loads(pkg_path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else None
    except (OSError, json.JSONDecodeError, ValueError):
        return None


def resolve_node_package_manager(
    workspace_path: Union[Path, str],
    pkg_data: Optional[Dict[str, Any]] = None,
) -> str:
    """Resolve Node package manager (`packageManager` -> lockfiles -> `npm`)."""
    root = Path(workspace_path)
    data = pkg_data if pkg_data is not None else _load_package_json(root)

    if isinstance(data, dict):
        raw_pm = data.get("packageManager")
        if isinstance(raw_pm, str) and raw_pm.strip():
            norm = raw_pm.strip().lower()
            if norm.startswith("corepack+"):
                norm = norm[len("corepack+"):]
            pm_name = norm.split("@", 1)[0].strip()
            if pm_name in ("pnpm", "yarn", "bun", "npm"):
                return pm_name

    if (root / "pnpm-lock.yaml").exists() or (root / ".pnpm-lock.yaml").exists():
        return "pnpm"
    if (root / "yarn.lock").exists():
        return "yarn"
    if (root / "bun.lockb").exists() or (root / "bun.lock").exists() or (root / "bunfig.toml").exists():
        return "bun"
    if (root / "package-lock.json").exists() or (root / "npm-shrinkwrap.json").exists():
        return "npm"
    return "npm"


def pm_exec_prefix(pm: str) -> str:
    """Return binary execution prefix for a resolved Node package manager."""
    if pm == "pnpm":
        return "pnpm exec "
    if pm == "bun":
        return "bun x "
    if pm == "yarn":
        return "yarn "
    return "npx "


def pm_script_command(pm: str, script_name: str) -> str:
    """Build valid package-manager command for a package.json script name."""
    if script_name == "test":
        return f"{pm} test"
    if pm in ("pnpm", "yarn"):
        return f"{pm} {script_name}"
    return f"{pm} run {script_name}"


def detect_node_runner_command(root: Path) -> Optional[str]:
    """Detect executable Node/JS/TS/Playwright test command when manifest lacks override."""
    has_marker = (root / "package.json").is_file() or any((root / lf).exists() for lf in _NODE_LOCKFILES)
    if not has_marker:
        return None

    data = _load_package_json(root)
    pm = resolve_node_package_manager(root, data)
    scripts = data.get("scripts") if isinstance(data, dict) and isinstance(data.get("scripts"), dict) else {}
    raw_deps = data.get("dependencies") if isinstance(data, dict) and isinstance(data.get("dependencies"), dict) else {}
    raw_dev = data.get("devDependencies") if isinstance(data, dict) and isinstance(data.get("devDependencies"), dict) else {}
    deps = {**raw_deps, **raw_dev}

    if "test" in scripts and str(scripts["test"]).strip():
        return f"{pm} test"

    for alt_script in ("test:full", "test:unit", "test:e2e", "e2e"):
        if alt_script in scripts and str(scripts[alt_script]).strip():
            return pm_script_command(pm, alt_script)

    if "@playwright/test" in deps or "playwright" in deps or any(root.glob("playwright.config.*")):
        return f"{pm_exec_prefix(pm)}playwright test"
    if "vitest" in deps or any(root.glob("vitest.config.*")):
        return f"{pm_exec_prefix(pm)}vitest run"
    if "jest" in deps or any(root.glob("jest.config.*")):
        return f"{pm_exec_prefix(pm)}jest --runInBand"

    if not scripts:
        if (root / "pnpm-lock.yaml").exists() or (root / ".pnpm-lock.yaml").exists():
            return "pnpm test"
        if (root / "bun.lockb").exists() or (root / "bun.lock").exists() or (root / "bunfig.toml").exists():
            return "bun test"
        if (root / "yarn.lock").exists():
            return "yarn test"
    return None


def detect_non_node_runner(root: Path) -> Optional[str]:
    """Detect non-Node test runners (Cargo, Python, Go, JVM, .NET, CMake, Make, Elixir, Shell)."""
    if (root / "Cargo.toml").exists():
        return "cargo test"
    if (root / "pyproject.toml").exists() or (root / "pytest.ini").exists() or (root / "setup.cfg").exists():
        return "pytest"
    if (root / "go.mod").exists():
        return "go test ./..."
    if (root / "gradlew").exists():
        return "./gradlew test"
    if (root / "build.gradle").exists() or (root / "build.gradle.kts").exists():
        return "gradle test"
    if (root / "mvnw").exists():
        return "./mvnw test"
    if (root / "pom.xml").exists():
        return "mvn test"
    if any(root.glob("*.sln")) or any(root.glob("*.csproj")) or any(root.glob("*.fsproj")):
        return "dotnet test"
    if (root / "CMakeLists.txt").exists():
        return "ctest"
    if (root / "Makefile").exists() or (root / "makefile").exists():
        return "make test"
    if (root / "mix.exs").exists():
        return "mix test"
    for test_dirname in ("tests", "test"):
        test_dir = root / test_dirname
        if test_dir.is_dir() and any(test_dir.glob("*.sh")):
            return f"bash {test_dirname}/*.sh"
    return None


def has_python_unittest_files(tests_dir: Path) -> bool:
    """Return True if `tests_dir` contains at least one discoverable Python test module."""
    if not tests_dir.is_dir():
        return False
    try:
        for p in tests_dir.rglob("*.py"):
            if "__pycache__" in p.parts:
                continue
            if p.name.startswith("test_") or p.name.endswith("_test.py"):
                return True
    except OSError:
        return False
    return False


def has_non_python_test_surface(workspace_path: Union[Path, str]) -> bool:
    """Return True when non-Python manifests or JS/TS/Playwright/Go test files exist."""
    root = Path(workspace_path)
    if not root.is_dir():
        return False

    if any((root / m).exists() for m in _NON_PYTHON_MANIFESTS):
        return True
    if any(root.glob("*.sln")) or any(root.glob("*.csproj")) or any(root.glob("*.fsproj")):
        return True

    try:
        for dirpath, dirnames, filenames in os.walk(root):
            rel_parts = Path(dirpath).relative_to(root).parts
            dirnames[:] = [
                d for d in dirnames
                if d not in _IGNORED_SCAN_DIRS and not d.startswith(".")
            ]
            if len(rel_parts) >= 3:
                dirnames[:] = []
            for fname in filenames:
                if _NON_PYTHON_TEST_RE.search(fname):
                    return True
                if rel_parts and rel_parts[-1] == "e2e" and fname.endswith((".ts", ".tsx", ".js", ".jsx", ".mjs")):
                    return True
    except OSError:
        return False
    return False


def guard_package_manager_cmd(clean_cmd: str, cwd: Union[Path, str, None] = None) -> str:
    """Apply non-interactive flags only when the target command/script supports watch mode."""
    if _COMPOUND_SHELL_RE.search(clean_cmd) or _NON_WATCH_DIRECT_RE.search(clean_cmd):
        return clean_cmd

    if re.search(r"\bvitest\b", clean_cmd):
        if not re.search(r"(?:^|\s)(?:run|--run|--no-watch)(?:\s|$)", clean_cmd):
            return clean_cmd + " --run"
        return clean_cmd

    if re.search(r"\bjest\b", clean_cmd):
        if not re.search(r"(?:--watchAll=false|--no-watch|--watch=false|--watchAll=0)", clean_cmd):
            return clean_cmd + " --watchAll=false"
        return clean_cmd

    pm_match = _PM_TEST_CMD_RE.search(clean_cmd)
    if not pm_match:
        return clean_cmd

    if any(tok in clean_cmd for tok in ("--no-watch", "--watch=false", "--watchAll=false", "--watchAll=0")):
        return clean_cmd

    script_name = pm_match.group("script")
    script_body = ""
    if cwd is not None:
        pkg_data = _load_package_json(Path(cwd))
        if isinstance(pkg_data, dict):
            scripts = pkg_data.get("scripts")
            if isinstance(scripts, dict):
                script_body = str(scripts.get(script_name, ""))

    if script_body:
        if re.search(r"\b(?:jest|react-scripts)\b", script_body):
            if re.search(r"(?:--watchAll=false|--no-watch|--watch=false|--watchAll=0)", script_body):
                return clean_cmd
            return clean_cmd + (" -- --watchAll=false" if " -- " not in clean_cmd else " --watchAll=false")
        if _NON_WATCH_BODY_RE.search(script_body):
            return clean_cmd

    if pm_match.group("pm") == "npm" and " -- " in clean_cmd:
        return clean_cmd

    return clean_cmd + (" -- --no-watch" if " -- " not in clean_cmd else " --no-watch")
