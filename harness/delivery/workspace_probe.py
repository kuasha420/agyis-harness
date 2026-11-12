# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Arafat Zahan (@kuasha420)
# Corporate Stewardship & Infrastructure: Purrfect Software Limited (PSL)
# Governed by: ICARO-42/b Ordinance (Company-Supported Personal IP Framework)

"""Workspace toolchain, test-runner, command-dictionary, and license probing."""

from __future__ import annotations

from pathlib import Path
import re
from typing import Any, Dict, Optional

STANDARD_VERB_DESCRIPTIONS: Dict[str, str] = {
    "test": "Run complete project test suite",
    "test:rust": "Run Rust / Cargo test suite",
    "test:node": "Run Node / TypeScript test suite",
    "test:diff": "Run fast tests for uncommitted changes",
    "test:watch": "Run tests in interactive watch mode",
    "test:affected": "Run tests affected by recent changes",
    "test:full": "Run complete test verification suite",
    "test:pkg": "Run targeted package test suite",
    "build": "Build project artifacts",
    "build:rust": "Build Rust native binaries",
    "clippy": "Run Cargo Clippy linter",
    "lint:rust": "Run Cargo Clippy linter",
    "lint": "Code quality & linting checks",
    "dev": "Start local development server",
    "start": "Launch production runtime",
    "check": "Verification & type check",
    "typecheck": "Static type checking",
    "format": "Code style & formatting",
    "clean": "Clean build artifacts & caches",
    "install": "Install project dependencies",
    "all": "Build all targets",
    "vet": "Go static analysis",
    "run": "Run project executable",
    "verify": "Execute project verification gates",
    "tauri:build": "Build Tauri desktop package & binaries",
    "tauri:dev": "Launch Tauri desktop application in dev mode",
}


def _has_python_files(dir_path: Path) -> bool:
    """Returns True if directory contains at least one Python (.py) file."""
    if not dir_path.is_dir():
        return False
    try:
        for p in dir_path.glob("*.py"):
            if p.is_file():
                return True
        for p in dir_path.rglob("*.py"):
            if p.is_file():
                return True
        return False
    except OSError:
        return False


def detect_test_command(workspace_path: Path | str) -> Optional[str]:
    """
    Detects the native test command for a Python workspace (GAP-06, GAP-07).

    Inspects in order:
    1. pyproject.toml: [tool.pytest] or pytest in dependencies
    2. pytest.ini
    3. setup.cfg: content check for [tool:pytest], [pytest], or pytest
    4. setup.py: content check for pytest
    5. requirements*.txt: content check for pytest
    6. tests/ or test/ directory: fallback to standard unittest discovery if .py files present

    Returns the executable test command (with package manager prefix if detected) or None.
    """
    ws = Path(workspace_path).resolve()
    if not ws.exists() or not ws.is_dir():
        return None

    # Detect package manager runner prefix
    if (ws / "poetry.lock").is_file():
        prefix = "poetry run "
    elif (ws / "uv.lock").is_file():
        prefix = "uv run "
    elif (ws / "Pipfile.lock").is_file() or (ws / "Pipfile").is_file():
        prefix = "pipenv run "
    else:
        prefix = ""

    pyproj = ws / "pyproject.toml"
    setup_py = ws / "setup.py"
    setup_cfg = ws / "setup.cfg"
    pytest_ini = ws / "pytest.ini"
    tests_dir = ws / "tests"
    test_dir = ws / "test"

    has_pytest = False

    # 1. pyproject.toml
    if pyproj.is_file():
        try:
            import tomllib

            toml_data = tomllib.loads(pyproj.read_text(encoding="utf-8", errors="replace"))
            if isinstance(toml_data, dict):
                tools = toml_data.get("tool", {})
                if isinstance(tools, dict) and "pytest" in tools:
                    has_pytest = True
        except Exception:
            pass

        if not has_pytest:
            try:
                pyproj_text = pyproj.read_text(encoding="utf-8", errors="replace")
                if re.search(r"['\"]pytest(?:[<>=!~].*)?['\"]", pyproj_text) or re.search(
                    r"(?im)^\s*pytest\s*=", pyproj_text
                ):
                    has_pytest = True
            except OSError:
                pass

    # 2. pytest.ini
    if not has_pytest and pytest_ini.is_file():
        has_pytest = True

    # 3. setup.cfg (content check for [tool:pytest], [pytest], or pytest)
    if not has_pytest and setup_cfg.is_file():
        try:
            cfg_text = setup_cfg.read_text(encoding="utf-8", errors="replace")
            if re.search(r"(?im)^\s*\[(?:tool:)?pytest\]", cfg_text) or re.search(
                r"(?im)^\s*pytest\b", cfg_text
            ):
                has_pytest = True
        except OSError:
            pass

    # 4. setup.py (content check for pytest)
    if not has_pytest and setup_py.is_file():
        try:
            setup_text = setup_py.read_text(encoding="utf-8", errors="replace")
            if re.search(r"\bpytest\b", setup_text, re.IGNORECASE):
                has_pytest = True
        except OSError:
            pass

    # 5. requirements*.txt (content check for pytest)
    if not has_pytest:
        req_candidates = [
            ws / "requirements.txt",
            ws / "requirements-dev.txt",
            ws / "test-requirements.txt",
            ws / "requirements_dev.txt",
            ws / "requirements_test.txt",
            ws / "requirements" / "test.txt",
            ws / "requirements" / "dev.txt",
        ]
        for req_f in req_candidates:
            if req_f.is_file():
                try:
                    req_text = req_f.read_text(encoding="utf-8", errors="replace")
                    if re.search(r"(?im)^\s*pytest\b", req_text):
                        has_pytest = True
                        break
                except OSError:
                    pass

    # If pytest detected, return pytest command with prefix
    if has_pytest:
        return f"{prefix}pytest"

    # 6. Fallback to standard unittest discovery if Python test files are present
    if _has_python_files(tests_dir):
        return f"{prefix}python3 -m unittest discover -s tests -v"
    elif _has_python_files(test_dir):
        return f"{prefix}python3 -m unittest discover -s test -v"

    return None


def extract_command_dictionary(workspace_dir: Path) -> Dict[str, str]:
    """
    Extracts an explicit project command dictionary from workspace configuration.

    Inspects in order:
    1. package.json scripts (Node / TypeScript)
    2. Python test runner configs (pyproject.toml, setup.py, setup.cfg, requirements.txt, tests/)
    3. Cargo.toml (Rust)
    4. go.mod (Go)
    5. Makefile targets (Systems / C / Shell)

    Returns a mapping of semantic actions/verbs (e.g. 'test', 'build', 'lint', 'dev')
    to their executable command strings (e.g. 'pnpm test', 'make build', 'pytest').
    """
    ws = Path(workspace_dir).resolve()
    if not ws.exists() or not ws.is_dir():
        return {}

    commands: Dict[str, str] = {}

    # 1. Node / TypeScript (package.json)
    pkg_json = ws / "package.json"
    if pkg_json.is_file():
        try:
            import json

            data = json.loads(pkg_json.read_text(encoding="utf-8"))
            raw_scripts = data.get("scripts", {})
            if isinstance(raw_scripts, dict):
                # Detect package manager
                if (ws / "pnpm-lock.yaml").is_file() or (ws / "pnpm-workspace.yaml").is_file():
                    pm = "pnpm"
                elif (ws / "yarn.lock").is_file():
                    pm = "yarn"
                elif (ws / "bun.lockb").is_file() or (ws / "bun.lock").is_file():
                    pm = "bun"
                else:
                    pm = "npm"

                def format_node_cmd(script_name: str) -> str:
                    if pm == "pnpm":
                        return f"pnpm {script_name}"
                    elif pm == "yarn":
                        return f"yarn {script_name}"
                    elif pm == "bun":
                        return "bun test" if script_name == "test" else f"bun run {script_name}"
                    else:
                        if script_name in ("test", "start"):
                            return f"npm {script_name}"
                        return f"npm run {script_name}"

                priority_verbs = [
                    "test",
                    "build",
                    "lint",
                    "dev",
                    "start",
                    "check",
                    "format",
                    "typecheck",
                    "clean",
                    "verify",
                    "test:diff",
                    "test:watch",
                    "test:affected",
                    "test:full",
                    "test:pkg",
                    "test:rust",
                    "test:node",
                    "clippy",
                    "tauri:build",
                    "tauri:dev",
                ]
                for v in priority_verbs:
                    if v in raw_scripts and v not in commands:
                        commands[v] = format_node_cmd(v)
                for k in raw_scripts:
                    if k not in commands and len(commands) < 24:
                        commands[k] = format_node_cmd(k)
        except Exception:
            pass

    # 2. Python (pyproject.toml, setup.py, setup.cfg, requirements.txt, tests/, test/)
    pyproj = ws / "pyproject.toml"
    setup_py = ws / "setup.py"
    setup_cfg = ws / "setup.cfg"
    req_txt = ws / "requirements.txt"
    tests_dir = ws / "tests"
    test_dir = ws / "test"

    has_py_manifest = (
        pyproj.is_file()
        or setup_py.is_file()
        or setup_cfg.is_file()
        or req_txt.is_file()
        or (ws / "requirements-dev.txt").is_file()
        or (ws / "test-requirements.txt").is_file()
        or (ws / "pytest.ini").is_file()
        or (ws / "Pipfile").is_file()
        or (ws / "Pipfile.lock").is_file()
        or (ws / "poetry.lock").is_file()
        or (ws / "uv.lock").is_file()
    )
    has_py_tests = _has_python_files(tests_dir) or _has_python_files(test_dir)

    if has_py_manifest or has_py_tests:
        if (ws / "poetry.lock").is_file():
            prefix = "poetry run "
        elif (ws / "uv.lock").is_file():
            prefix = "uv run "
        elif (ws / "Pipfile.lock").is_file() or (ws / "Pipfile").is_file():
            prefix = "pipenv run "
        else:
            prefix = ""

        tools: Dict[str, Any] = {}
        if pyproj.is_file():
            try:
                import tomllib

                toml_data = tomllib.loads(pyproj.read_text(encoding="utf-8"))
                tools = toml_data.get("tool", {}) if isinstance(toml_data, dict) else {}
            except Exception:
                pass

        if "test" not in commands:
            test_cmd = detect_test_command(ws)
            if test_cmd:
                commands["test"] = test_cmd

        cfg_text = ""
        if setup_cfg.is_file():
            try:
                cfg_text = setup_cfg.read_text(encoding="utf-8", errors="replace")
            except OSError:
                pass

        if "lint" not in commands:
            if "ruff" in tools or (ws / "ruff.toml").is_file() or (ws / ".ruff.toml").is_file():
                commands["lint"] = f"{prefix}ruff check ."
            elif "flake8" in tools or (ws / ".flake8").is_file() or "[flake8]" in cfg_text:
                commands["lint"] = f"{prefix}flake8"

        if "format" not in commands:
            if "ruff" in tools or (ws / "ruff.toml").is_file() or (ws / ".ruff.toml").is_file():
                commands["format"] = f"{prefix}ruff format ."
            elif "black" in tools or (ws / ".black").is_file():
                commands["format"] = f"{prefix}black ."

        if "check" not in commands and "typecheck" not in commands:
            if "mypy" in tools or (ws / "mypy.ini").is_file() or (ws / ".mypy.ini").is_file() or "[mypy" in cfg_text:
                commands["check"] = f"{prefix}mypy ."
            elif "pyright" in tools or (ws / "pyrightconfig.json").is_file():
                commands["check"] = f"{prefix}pyright"

    # 3. Rust (Cargo.toml or src-tauri/Cargo.toml or native/Cargo.toml)
    cargo_root = ws / "Cargo.toml"
    cargo_tauri = ws / "src-tauri" / "Cargo.toml"
    cargo_native = ws / "native" / "Cargo.toml"

    if cargo_root.is_file():
        if "test" not in commands:
            commands["test"] = "cargo test"
        elif "test:rust" not in commands:
            commands["test:rust"] = "cargo test"

        if "build" not in commands:
            commands["build"] = "cargo build"
        elif "build:rust" not in commands:
            commands["build:rust"] = "cargo build"

        if "lint" not in commands:
            commands["lint"] = "cargo clippy"
        elif "lint:rust" not in commands and "clippy" not in commands:
            commands["lint:rust"] = "cargo clippy"

    elif cargo_tauri.is_file():
        manifest_arg = "--manifest-path src-tauri/Cargo.toml"
        if "test" not in commands:
            commands["test"] = f"cargo test {manifest_arg}"
        if "test:rust" not in commands:
            commands["test:rust"] = f"cargo test {manifest_arg}"

        if "build" not in commands:
            commands["build"] = f"cargo build {manifest_arg}"
        if "build:rust" not in commands:
            commands["build:rust"] = f"cargo build {manifest_arg}"

        if "clippy" not in commands and "lint:rust" not in commands:
            commands["lint:rust"] = f"cargo clippy {manifest_arg}"
        if "lint" not in commands:
            commands["lint"] = f"cargo clippy {manifest_arg}"

    elif cargo_native.is_file():
        manifest_arg = "--manifest-path native/Cargo.toml"
        if "test" not in commands:
            commands["test"] = f"cargo test {manifest_arg}"
        if "test:rust" not in commands:
            commands["test:rust"] = f"cargo test {manifest_arg}"

        if "build" not in commands:
            commands["build"] = f"cargo build {manifest_arg}"
        if "build:rust" not in commands:
            commands["build:rust"] = f"cargo build {manifest_arg}"

        if "clippy" not in commands and "lint:rust" not in commands:
            commands["lint:rust"] = f"cargo clippy {manifest_arg}"
        if "lint" not in commands:
            commands["lint"] = f"cargo clippy {manifest_arg}"

    # 4. Go (go.mod)
    if (ws / "go.mod").is_file():
        if "test" not in commands:
            commands["test"] = "go test ./..."
        if "build" not in commands:
            commands["build"] = "go build ./..."
        if "vet" not in commands:
            commands["vet"] = "go vet ./..."

    # 5. Systems / C / Shell (Makefile)
    makefile = ws / "Makefile"
    if makefile.is_file():
        try:
            content = makefile.read_text(encoding="utf-8", errors="replace")
            targets = re.findall(r"^([a-zA-Z0-9_\.-]+)\s*:(?!=)", content, re.MULTILINE)
            valid_targets = [
                t
                for t in targets
                if not t.startswith(".") and not t.startswith("_") and "%" not in t
            ]
            common_make = [
                "test",
                "build",
                "lint",
                "check",
                "clean",
                "all",
                "install",
                "dev",
                "run",
                "format",
            ]
            for ct in common_make:
                if ct in valid_targets and ct not in commands:
                    commands[ct] = f"make {ct}"
            for t in valid_targets:
                if t not in commands and len(commands) < 24:
                    commands[t] = f"make {t}"
        except Exception:
            pass

    return commands


def extract_command_descriptions(workspace_dir: Path) -> Dict[str, str]:
    """
    Infers context-aware, semantic descriptions for commands based on actual script content.
    Prevents inaccurate static mappings (e.g. mapping 'clean' to cache cleaning when it terminates processes).
    """
    ws = Path(workspace_dir).resolve()
    if not ws.exists() or not ws.is_dir():
        return {}

    descriptions: Dict[str, str] = {}

    # 1. Node / TypeScript (package.json scripts inspection)
    pkg_json = ws / "package.json"
    if pkg_json.is_file():
        try:
            import json

            data = json.loads(pkg_json.read_text(encoding="utf-8"))
            raw_scripts = data.get("scripts", {})
            if isinstance(raw_scripts, dict):
                for verb, script_cmd in raw_scripts.items():
                    if not isinstance(script_cmd, str):
                        continue
                    cmd_lower = script_cmd.lower()
                    if verb == "clean":
                        if any(kw in cmd_lower for kw in ["pkill", "killall", "kill", "fuser", "taskkill", "zombie"]):
                            descriptions["clean"] = "Terminate zombie sidecar/app processes"
                        elif any(kw in cmd_lower for kw in ["rimraf", "rm -rf", "clean", "cache", "dist", "build"]):
                            descriptions["clean"] = "Clean build artifacts & caches"
                    elif verb == "dev":
                        if any(kw in cmd_lower for kw in ["tauri dev", "electron", "flutter", "react-native"]):
                            descriptions["dev"] = "Start local desktop/mobile development application"
                    elif verb == "build":
                        if "tauri build" in cmd_lower:
                            descriptions["build"] = "Build application package & native binaries"
                    elif verb == "install":
                        if any(kw in cmd_lower for kw in ["/bin", "/usr", "~/.local", "cp "]):
                            descriptions["install"] = "Install binary into system / user path"
        except Exception:
            pass

    # 2. Makefile inspection
    makefile = ws / "Makefile"
    if makefile.is_file():
        try:
            content = makefile.read_text(encoding="utf-8", errors="replace")
            target_matches = re.finditer(
                r"^([a-zA-Z0-9_\.-]+)\s*:(?!=)[^\n]*\n((?:[ \t]+[^\n]*\n?)*)",
                content,
                re.MULTILINE,
            )
            for m in target_matches:
                t = m.group(1)
                recipe = m.group(2).lower()
                if t == "clean" and "clean" not in descriptions:
                    if any(kw in recipe for kw in ["pkill", "killall", "kill", "fuser", "zombie"]):
                        descriptions["clean"] = "Terminate zombie processes & clean artifacts"
                elif t == "install" and "install" not in descriptions:
                    if any(kw in recipe for kw in ["/bin", "/usr", "~/.local", "install -m", "cp "]):
                        descriptions["install"] = "Install binary into system path"
                elif t == "dev" and "dev" not in descriptions:
                    if any(kw in recipe for kw in ["cargo run", "go run", "python", "watch"]):
                        descriptions["dev"] = "Run local development instance"
        except Exception:
            pass

    return descriptions


def detect_repository_license(workspace_dir: Path) -> Optional[str]:
    """
    Detects repository license identifier (e.g. 'MIT', 'Apache-2.0', 'BSD-3-Clause').
    Inspects in order:
    1. package.json ("license" field)
    2. pyproject.toml (project.license or tool.poetry.license)
    3. Cargo.toml (package.license)
    4. LICENSE / LICENSE.md / LICENSE.txt / COPYING (SPDX tag or standard header match)
    """
    ws = Path(workspace_dir).resolve()
    if not ws.exists():
        return None

    # 1. package.json
    pkg_json = ws / "package.json"
    if pkg_json.is_file():
        try:
            import json

            data = json.loads(pkg_json.read_text(encoding="utf-8"))
            lic = data.get("license")
            if isinstance(lic, str) and lic.strip():
                return lic.strip()
            if isinstance(lic, dict) and lic.get("type"):
                return str(lic["type"]).strip()
        except Exception:
            pass

    # 2. pyproject.toml
    pyproj = ws / "pyproject.toml"
    if pyproj.is_file():
        try:
            import tomllib

            data = tomllib.loads(pyproj.read_text(encoding="utf-8"))
            proj = data.get("project", {})
            lic = proj.get("license")
            if isinstance(lic, str) and lic.strip():
                return lic.strip()
            if isinstance(lic, dict) and lic.get("text"):
                return str(lic["text"]).strip()
            poetry = data.get("tool", {}).get("poetry", {})
            if poetry.get("license"):
                return str(poetry["license"]).strip()
        except Exception:
            pass

    # 3. Cargo.toml
    cargo = ws / "Cargo.toml"
    if cargo.is_file():
        try:
            content = cargo.read_text(encoding="utf-8")
            m = re.search(r'license\s*=\s*"([^"]+)"', content)
            if m:
                return m.group(1).strip()
        except Exception:
            pass

    # 4. LICENSE / LICENSE.md / LICENSE.txt / COPYING
    for cand in [ws / "LICENSE", ws / "LICENSE.md", ws / "LICENSE.txt", ws / "COPYING"]:
        if cand.is_file():
            try:
                text = cand.read_text(encoding="utf-8", errors="replace")
                spdx_match = re.search(
                    r"SPDX-License-Identifier:\s*([^\r\n]+?)(?=\s*(?:-->|\*/|$))",
                    text,
                    re.IGNORECASE | re.MULTILINE,
                )
                if spdx_match:
                    return spdx_match.group(1).strip()
                if "MIT License" in text or "Permission is hereby granted, free of charge" in text:
                    return "MIT"
                if "Apache License" in text and ("Version 2.0" in text or "2.0" in text):
                    return "Apache-2.0"
                if "BSD 3-Clause" in text:
                    return "BSD-3-Clause"
                if "BSD 2-Clause" in text:
                    return "BSD-2-Clause"
                if "Mozilla Public License" in text:
                    return "MPL-2.0"
                if "GNU GENERAL PUBLIC LICENSE" in text:
                    if "Version 3" in text or "v3" in text:
                        return "GPL-3.0"
                    return "GPL-2.0"
                if "ISC License" in text or "permission to use, copy, modify, and/or distribute this software" in text.lower():
                    return "ISC"
            except Exception:
                pass

    return None


def adapt_spdx_license(text: str, target_license: str) -> str:
    """
    Replaces the SPDX-License-Identifier in text with target_license.
    Handles single, compound (e.g. 'MIT OR Apache-2.0'), parenthesized, and exception SPDX expressions.
    Example: '<!-- SPDX-License-Identifier: Apache-2.0 -->' -> '<!-- SPDX-License-Identifier: MIT -->'
    """
    if not target_license:
        return text
    return re.sub(
        r"(SPDX-License-Identifier:\s*)[^\r\n]+?(?=\s*(?:-->|\*/|$))",
        rf"\g<1>{target_license}",
        text,
        flags=re.MULTILINE,
    )


def format_command_dictionary(
    cmd_dict: Dict[str, str],
    descriptions: Optional[Dict[str, str]] = None,
    workspace_dir: Optional[Path] = None,
) -> str:
    """Formats the command dictionary into shell code block annotations."""
    if not cmd_dict:
        return ""
    inferred_desc: Dict[str, str] = {}
    if workspace_dir:
        inferred_desc = extract_command_descriptions(workspace_dir)
    if descriptions:
        inferred_desc.update(descriptions)

    lines = ["# 🧪 Project Verification & Native Toolchain"]
    for verb, cmd in cmd_dict.items():
        desc = inferred_desc.get(verb) or STANDARD_VERB_DESCRIPTIONS.get(verb, f"Execute {verb}")
        lines.append(f"{cmd:<46} # {desc}".rstrip())
    return "\n".join(lines)


def normalize_tagged_rules(text: str) -> str:
    """Normalizes Markdown whitespace, blank lines, and emphasis for idempotent tagged block diffing."""
    lines = [line.rstrip() for line in text.replace("\r\n", "\n").split("\n")]
    norm = "\n".join(lines).strip()
    norm = re.sub(r"\n{3,}", "\n\n", norm)
    # Normalize standalone italics (*text* -> _text_) without touching **bold**
    norm = re.sub(r"(?<!\*)\*([^\*\n]+)\*(?!\*)", r"_\1_", norm)
    return norm
