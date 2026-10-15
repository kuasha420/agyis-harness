#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Arafat Zahan (@kuasha420)
# Corporate Stewardship & Infrastructure: Purrfect Software Limited (PSL)
# Governed by: ICARO-42/b Ordinance (Company-Supported Personal IP Framework)

"""
Hermetic Unit Tests for harness/utils/workspace.py (PSL-SPEC-2026-DRA-001 Phase 3).

Validates:
1. is_harness_workspace detects harness repository markers and distinguishes client repos.
2. detect_project_test_runner accurately identifies test runners across mock client directory trees.
"""

from __future__ import annotations

import json
from pathlib import Path
import tempfile
import unittest

from harness.utils.workspace import (
    detect_project_test_runner,
    is_harness_workspace,
)


class TestWorkspaceDetection(unittest.TestCase):
    """Hermetic unit tests for workspace identification and test runner discovery."""

    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.workspace_dir = Path(self.temp_dir.name)

    def tearDown(self):
        self.temp_dir.cleanup()

    # --- is_harness_workspace tests ---

    def test_is_harness_workspace_on_actual_repo(self):
        """The actual psl-agy-harness repository checkout is detected as a harness workspace."""
        repo_root = Path(__file__).resolve().parent.parent
        self.assertTrue(is_harness_workspace(repo_root))
        self.assertTrue(is_harness_workspace(str(repo_root)))

    def test_is_harness_workspace_mock_with_hooks_json(self):
        """Mock directory with harness/cli.py, harvest_conversations.py, and hooks.json matches."""
        cli_file = self.workspace_dir / "harness" / "cli.py"
        cli_file.parent.mkdir(parents=True, exist_ok=True)
        cli_file.touch()

        harvest_file = self.workspace_dir / "pipeline" / "harvest_conversations.py"
        harvest_file.parent.mkdir(parents=True, exist_ok=True)
        harvest_file.touch()

        hooks_file = self.workspace_dir / "harness" / "hooks" / "hooks.json"
        hooks_file.parent.mkdir(parents=True, exist_ok=True)
        hooks_file.touch()

        self.assertTrue(is_harness_workspace(self.workspace_dir))
        self.assertTrue(is_harness_workspace(str(self.workspace_dir)))

    def test_is_harness_workspace_mock_with_manifest_json(self):
        """Mock directory with harness/cli.py, harvest_conversations.py, and manifest.json matches."""
        cli_file = self.workspace_dir / "harness" / "cli.py"
        cli_file.parent.mkdir(parents=True, exist_ok=True)
        cli_file.touch()

        harvest_file = self.workspace_dir / "pipeline" / "harvest_conversations.py"
        harvest_file.parent.mkdir(parents=True, exist_ok=True)
        harvest_file.touch()

        manifest_file = self.workspace_dir / "harness" / "manifest.json"
        manifest_file.parent.mkdir(parents=True, exist_ok=True)
        manifest_file.touch()

        self.assertTrue(is_harness_workspace(self.workspace_dir))

    def test_is_harness_workspace_negative_cases(self):
        """Missing any required marker file returns False."""
        # 1. Empty directory
        self.assertFalse(is_harness_workspace(self.workspace_dir))

        # 2. Only harness/cli.py
        cli_file = self.workspace_dir / "harness" / "cli.py"
        cli_file.parent.mkdir(parents=True, exist_ok=True)
        cli_file.touch()
        self.assertFalse(is_harness_workspace(self.workspace_dir))

        # 3. Only pipeline/harvest_conversations.py and cli.py (no hooks.json or manifest.json)
        harvest_file = self.workspace_dir / "pipeline" / "harvest_conversations.py"
        harvest_file.parent.mkdir(parents=True, exist_ok=True)
        harvest_file.touch()
        self.assertFalse(is_harness_workspace(self.workspace_dir))

        # 4. Non-existent path
        self.assertFalse(is_harness_workspace(self.workspace_dir / "does_not_exist"))

        # 5. File instead of directory
        dummy_file = self.workspace_dir / "somefile.txt"
        dummy_file.touch()
        self.assertFalse(is_harness_workspace(dummy_file))

    # --- detect_project_test_runner tests ---

    def test_detect_pnpm_test_runner(self):
        """pnpm-lock.yaml or .pnpm-lock.yaml triggers 'pnpm test'."""
        pkg_json = self.workspace_dir / "package.json"
        pkg_json.write_text(json.dumps({"scripts": {"test": "vitest"}}), encoding="utf-8")
        (self.workspace_dir / "pnpm-lock.yaml").touch()

        self.assertEqual(detect_project_test_runner(self.workspace_dir), "pnpm test")
        self.assertEqual(detect_project_test_runner(str(self.workspace_dir)), "pnpm test")

    def test_detect_pnpm_test_runner_alt_lock(self):
        """.pnpm-lock.yaml triggers 'pnpm test' even without scripts."""
        (self.workspace_dir / "package.json").write_text("{}", encoding="utf-8")
        (self.workspace_dir / ".pnpm-lock.yaml").touch()

        self.assertEqual(detect_project_test_runner(self.workspace_dir), "pnpm test")

    def test_detect_npm_test_runner_with_test_script(self):
        """package.json with test script triggers 'npm test'."""
        pkg_json = self.workspace_dir / "package.json"
        pkg_json.write_text(json.dumps({"scripts": {"test": "jest"}}), encoding="utf-8")

        self.assertEqual(detect_project_test_runner(self.workspace_dir), "npm test")

    def test_detect_npm_test_runner_with_yarn_lock(self):
        """package.json with yarn.lock triggers 'npm test'."""
        (self.workspace_dir / "package.json").write_text("{}", encoding="utf-8")
        (self.workspace_dir / "yarn.lock").touch()

        self.assertEqual(detect_project_test_runner(self.workspace_dir), "npm test")

    def test_detect_cargo_test_runner(self):
        """Cargo.toml triggers 'cargo test'."""
        (self.workspace_dir / "Cargo.toml").write_text("[package]\nname = 'test-pkg'\n", encoding="utf-8")
        self.assertEqual(detect_project_test_runner(self.workspace_dir), "cargo test")

    def test_detect_pytest_runner_pyproject(self):
        """pyproject.toml triggers 'pytest'."""
        (self.workspace_dir / "pyproject.toml").write_text("[tool.pytest]\n", encoding="utf-8")
        self.assertEqual(detect_project_test_runner(self.workspace_dir), "pytest")

    def test_detect_pytest_runner_pytest_ini(self):
        """pytest.ini triggers 'pytest'."""
        (self.workspace_dir / "pytest.ini").write_text("[pytest]\n", encoding="utf-8")
        self.assertEqual(detect_project_test_runner(self.workspace_dir), "pytest")

    def test_detect_pytest_runner_setup_cfg(self):
        """setup.cfg triggers 'pytest'."""
        (self.workspace_dir / "setup.cfg").write_text("[tool:pytest]\n", encoding="utf-8")
        self.assertEqual(detect_project_test_runner(self.workspace_dir), "pytest")

    def test_detect_makefile_runner(self):
        """Makefile triggers 'make test'."""
        (self.workspace_dir / "Makefile").write_text("test:\n\t@echo ok\n", encoding="utf-8")
        self.assertEqual(detect_project_test_runner(self.workspace_dir), "make test")

    def test_detect_shell_tests_runner(self):
        """Shell test scripts in tests/*.sh trigger 'bash tests/*.sh'."""
        tests_dir = self.workspace_dir / "tests"
        tests_dir.mkdir(parents=True, exist_ok=True)
        (tests_dir / "test_suite.sh").touch()

        self.assertEqual(detect_project_test_runner(self.workspace_dir), "bash tests/*.sh")

    def test_detect_shell_test_runner_singular(self):
        """Shell test scripts in test/*.sh (singular) trigger 'bash test/*.sh'."""
        test_dir = self.workspace_dir / "test"
        test_dir.mkdir(parents=True, exist_ok=True)
        (test_dir / "suite.sh").touch()

        self.assertEqual(detect_project_test_runner(self.workspace_dir), "bash test/*.sh")
        self.assertEqual(detect_project_test_runner(str(self.workspace_dir)), "bash test/*.sh")

    def test_detect_shell_tests_runner_plural_precedence(self):
        """When both tests/ and test/ contain .sh scripts, tests/ takes precedence."""
        tests_dir = self.workspace_dir / "tests"
        tests_dir.mkdir(parents=True, exist_ok=True)
        (tests_dir / "suite_a.sh").touch()

        test_dir = self.workspace_dir / "test"
        test_dir.mkdir(parents=True, exist_ok=True)
        (test_dir / "suite_b.sh").touch()

        self.assertEqual(detect_project_test_runner(self.workspace_dir), "bash tests/*.sh")

    def test_detect_shell_test_runner_no_sh_files(self):
        """Directories named test or tests without .sh files return None."""
        test_dir = self.workspace_dir / "test"
        test_dir.mkdir(parents=True, exist_ok=True)
        (test_dir / "helper.py").touch()

        self.assertIsNone(detect_project_test_runner(self.workspace_dir))

    def test_detect_runner_precedence(self):
        """Project manifest (Cargo.toml, package.json) takes precedence over generic Makefile."""
        (self.workspace_dir / "Makefile").write_text("test:\n\t@echo ok\n", encoding="utf-8")
        (self.workspace_dir / "Cargo.toml").write_text("[package]\nname = 'rust-pkg'\n", encoding="utf-8")

        # Cargo.toml should take priority over Makefile
        self.assertEqual(detect_project_test_runner(self.workspace_dir), "cargo test")

    def test_detect_runner_empty_or_missing(self):
        """Empty or missing directory returns None."""
        self.assertIsNone(detect_project_test_runner(self.workspace_dir))
        self.assertIsNone(detect_project_test_runner(self.workspace_dir / "nonexistent"))


if __name__ == "__main__":
    unittest.main()
