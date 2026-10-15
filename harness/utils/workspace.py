# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Arafat Zahan (@kuasha420)
# Corporate Stewardship & Infrastructure: Purrfect Software Limited (PSL)
# Governed by: ICARO-42/b Ordinance (Company-Supported Personal IP Framework)

"""
Workspace and Dynamic Repository Awareness (DRA) utilities (PSL-SPEC-2026-DRA-001).

Provides runtime detection of:
1. Whether a directory is the PSL/Agyis Harness development repository (`is_harness_workspace`).
2. Native project test runner commands across external client codebases (`detect_project_test_runner`).
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Optional, Union


def is_harness_workspace(cwd: Union[Path, str, None] = None) -> bool:
    """
    Returns True strictly if cwd is the psl-agy-harness / agyis-harness repository,
    detected by repository markers:
      - harness/cli.py
      - pipeline/harvest_conversations.py
      - harness/hooks/hooks.json (or harness/manifest.json)
    """
    if cwd is None:
        root = Path.cwd()
    else:
        root = Path(cwd)

    try:
        if not root.is_dir():
            return False
        has_cli = (root / "harness" / "cli.py").exists()
        has_harvest = (root / "pipeline" / "harvest_conversations.py").exists()
        has_hooks_json = (root / "harness" / "hooks" / "hooks.json").exists()
        has_manifest_json = (root / "harness" / "manifest.json").exists()
        return has_cli and has_harvest and (has_hooks_json or has_manifest_json)
    except OSError:
        return False


def detect_project_test_runner(cwd: Union[Path, str, None] = None) -> Optional[str]:
    """
    Inspects cwd for client project test runners:
      * package.json -> checks for 'test' script or pnpm-lock.yaml/yarn.lock -> returns 'pnpm test' or 'npm test'
      * Cargo.toml -> returns 'cargo test'
      * pyproject.toml / pytest.ini / setup.cfg -> returns 'pytest'
      * Makefile -> returns 'make test'
      * tests/*.sh or test/*.sh (shell test files) -> returns 'bash tests/*.sh' or 'bash test/*.sh'
    Returns None if no recognized test runner configuration is found.
    """
    if cwd is None:
        root = Path.cwd()
    else:
        root = Path(cwd)

    try:
        if not root.is_dir():
            return None

        # 1. Node / JavaScript / TypeScript projects
        package_json = root / "package.json"
        pnpm_lock = root / "pnpm-lock.yaml"
        alt_pnpm_lock = root / ".pnpm-lock.yaml"
        yarn_lock = root / "yarn.lock"

        if package_json.exists() or pnpm_lock.exists() or alt_pnpm_lock.exists() or yarn_lock.exists():
            if pnpm_lock.exists() or alt_pnpm_lock.exists():
                return "pnpm test"
            if yarn_lock.exists():
                return "npm test"
            if package_json.exists():
                try:
                    data = json.loads(package_json.read_text(encoding="utf-8"))
                    if isinstance(data, dict):
                        scripts = data.get("scripts", {})
                        if isinstance(scripts, dict) and "test" in scripts:
                            return "npm test"
                except (json.JSONDecodeError, OSError):
                    pass
                return "npm test"

        # 2. Rust projects
        if (root / "Cargo.toml").exists():
            return "cargo test"

        # 3. Python projects
        if (
            (root / "pyproject.toml").exists()
            or (root / "pytest.ini").exists()
            or (root / "setup.cfg").exists()
        ):
            return "pytest"

        # 4. Makefile projects
        if (root / "Makefile").exists() or (root / "makefile").exists():
            return "make test"

        # 5. Shell test suites
        for test_dirname in ("tests", "test"):
            test_dir = root / test_dirname
            if test_dir.is_dir():
                try:
                    if any(test_dir.glob("*.sh")):
                        return f"bash {test_dirname}/*.sh"
                except OSError:
                    pass

        return None
    except OSError:
        return None
