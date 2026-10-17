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

from harness.delivery import (
    detect_test_command,
    extract_command_dictionary,
)
from harness.delivery.workspace import _has_python_files
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



class TestDeliveryWorkspacePythonCommandExtraction(unittest.TestCase):
    """
    Hermetic unit tests for Python test command extraction fallback (GAP-06, GAP-07).
    Validates detect_test_command and extract_command_dictionary across multi-manifest scenarios.
    """

    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.ws = Path(self.temp_dir.name)

    def tearDown(self):
        self.temp_dir.cleanup()

    # --- _has_python_files helper tests ---

    def test_has_python_files_empty_and_nonexistent(self):
        """Empty or nonexistent directory returns False."""
        self.assertFalse(_has_python_files(self.ws / "nonexistent"))
        empty_dir = self.ws / "empty"
        empty_dir.mkdir()
        self.assertFalse(_has_python_files(empty_dir))

    def test_has_python_files_shell_only(self):
        """Directory with only shell scripts returns False."""
        tests_dir = self.ws / "tests"
        tests_dir.mkdir()
        (tests_dir / "suite.sh").write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
        self.assertFalse(_has_python_files(tests_dir))

    def test_has_python_files_with_nested_py(self):
        """Directory with nested python files returns True."""
        nested = self.ws / "tests" / "unit"
        nested.mkdir(parents=True)
        (nested / "test_nested.py").write_text("import unittest\n", encoding="utf-8")
        self.assertTrue(_has_python_files(self.ws / "tests"))

    # --- detect_test_command manifest scenarios ---

    def test_detect_test_command_setup_py_unittest(self):
        """setup.py without pytest + tests/ extracts unittest discovery."""
        (self.ws / "setup.py").write_text(
            "from setuptools import setup\nsetup(name='myapp', version='0.1.0')\n",
            encoding="utf-8",
        )
        tests_dir = self.ws / "tests"
        tests_dir.mkdir()
        (tests_dir / "test_app.py").write_text("import unittest\n", encoding="utf-8")

        self.assertEqual(
            detect_test_command(self.ws),
            "python3 -m unittest discover -s tests -v",
        )
        self.assertEqual(
            detect_test_command(str(self.ws)),
            "python3 -m unittest discover -s tests -v",
        )

    def test_detect_test_command_setup_py_pytest(self):
        """setup.py mentioning pytest extracts pytest runner."""
        (self.ws / "setup.py").write_text(
            "from setuptools import setup\nsetup(name='myapp', tests_require=['pytest'])\n",
            encoding="utf-8",
        )
        tests_dir = self.ws / "tests"
        tests_dir.mkdir()
        (tests_dir / "test_app.py").write_text("import pytest\n", encoding="utf-8")

        self.assertEqual(detect_test_command(self.ws), "pytest")

    def test_detect_test_command_setup_cfg_flake8_unittest(self):
        """setup.cfg configuring only flake8/mypy falls back to unittest discovery (GAP-06 fix)."""
        (self.ws / "setup.cfg").write_text(
            "[flake8]\nmax-line-length = 88\n[mypy]\nignore_missing_imports = True\n",
            encoding="utf-8",
        )
        tests_dir = self.ws / "tests"
        tests_dir.mkdir()
        (tests_dir / "test_mod.py").write_text("import unittest\n", encoding="utf-8")

        self.assertEqual(
            detect_test_command(self.ws),
            "python3 -m unittest discover -s tests -v",
        )

    def test_detect_test_command_setup_cfg_tool_pytest(self):
        """setup.cfg configuring [tool:pytest] extracts pytest."""
        (self.ws / "setup.cfg").write_text(
            "[tool:pytest]\naddopts = -ra -q\n",
            encoding="utf-8",
        )
        tests_dir = self.ws / "tests"
        tests_dir.mkdir()
        (tests_dir / "test_mod.py").write_text("import pytest\n", encoding="utf-8")

        self.assertEqual(detect_test_command(self.ws), "pytest")

    def test_detect_test_command_setup_cfg_section_pytest(self):
        """setup.cfg configuring [pytest] extracts pytest."""
        (self.ws / "setup.cfg").write_text(
            "[pytest]\nminversion = 6.0\n",
            encoding="utf-8",
        )
        self.assertEqual(detect_test_command(self.ws), "pytest")

    def test_detect_test_command_requirements_txt_pytest(self):
        """requirements.txt containing pytest extracts pytest."""
        (self.ws / "requirements.txt").write_text(
            "requests==2.28.1\npytest>=7.4.0\nblack\n",
            encoding="utf-8",
        )
        tests_dir = self.ws / "tests"
        tests_dir.mkdir()
        (tests_dir / "test_req.py").write_text("import pytest\n", encoding="utf-8")

        self.assertEqual(detect_test_command(self.ws), "pytest")

    def test_detect_test_command_requirements_dev_txt_pytest(self):
        """requirements-dev.txt containing pytest extracts pytest."""
        (self.ws / "requirements-dev.txt").write_text(
            "pytest-cov==4.1.0\npytest\n",
            encoding="utf-8",
        )
        self.assertEqual(detect_test_command(self.ws), "pytest")

    def test_detect_test_command_test_requirements_txt_pytest(self):
        """test-requirements.txt containing pytest extracts pytest."""
        (self.ws / "test-requirements.txt").write_text(
            "pytest>=7.0\n",
            encoding="utf-8",
        )
        self.assertEqual(detect_test_command(self.ws), "pytest")

    def test_detect_test_command_pyproject_toml_pytest(self):
        """pyproject.toml configuring pytest extracts pytest."""
        (self.ws / "pyproject.toml").write_text(
            "[project]\nname = 'demo'\n[tool.pytest.ini_options]\naddopts = '-v'\n",
            encoding="utf-8",
        )
        self.assertEqual(detect_test_command(self.ws), "pytest")

    def test_detect_test_command_pyproject_toml_dependencies_pytest(self):
        """pyproject.toml listing pytest in dependencies extracts pytest."""
        (self.ws / "pyproject.toml").write_text(
            '[project]\nname = "demo"\ndependencies = ["pytest>=7.0"]\n',
            encoding="utf-8",
        )
        self.assertEqual(detect_test_command(self.ws), "pytest")

    def test_detect_test_command_pyproject_toml_unittest_fallback(self):
        """pyproject.toml without pytest falls back to unittest discovery."""
        (self.ws / "pyproject.toml").write_text(
            '[project]\nname = "demo"\nversion = "0.1.0"\n',
            encoding="utf-8",
        )
        tests_dir = self.ws / "tests"
        tests_dir.mkdir()
        (tests_dir / "test_core.py").write_text("import unittest\n", encoding="utf-8")

        self.assertEqual(
            detect_test_command(self.ws),
            "python3 -m unittest discover -s tests -v",
        )

    def test_detect_test_command_plain_tests_dir_unittest(self):
        """Plain tests/ directory with .py files without pyproject.toml extracts unittest."""
        tests_dir = self.ws / "tests"
        tests_dir.mkdir()
        (tests_dir / "test_simple.py").write_text("import unittest\n", encoding="utf-8")

        self.assertEqual(
            detect_test_command(self.ws),
            "python3 -m unittest discover -s tests -v",
        )

    def test_detect_test_command_singular_test_dir_unittest(self):
        """Singular test/ directory with .py files extracts unittest."""
        test_dir = self.ws / "test"
        test_dir.mkdir()
        (test_dir / "test_singular.py").write_text("import unittest\n", encoding="utf-8")

        self.assertEqual(
            detect_test_command(self.ws),
            "python3 -m unittest discover -s test -v",
        )

    def test_detect_test_command_shell_tests_ignored(self):
        """Directory with only shell scripts returns None (not Python unittest)."""
        tests_dir = self.ws / "tests"
        tests_dir.mkdir()
        (tests_dir / "run_all.sh").write_text("#!/bin/bash\npytest\n", encoding="utf-8")

        self.assertIsNone(detect_test_command(self.ws))

    def test_detect_test_command_package_manager_prefixes(self):
        """Package manager prefixes (poetry, uv, pipenv) are preserved."""
        # Poetry
        (self.ws / "poetry.lock").write_text("", encoding="utf-8")
        (self.ws / "pyproject.toml").write_text("[tool.pytest]\n", encoding="utf-8")
        self.assertEqual(detect_test_command(self.ws), "poetry run pytest")

        # Cleanup poetry
        (self.ws / "poetry.lock").unlink()

        # uv
        (self.ws / "uv.lock").write_text("", encoding="utf-8")
        self.assertEqual(detect_test_command(self.ws), "uv run pytest")

        # Cleanup uv
        (self.ws / "uv.lock").unlink()
        (self.ws / "pyproject.toml").unlink()

        # Pipfile with unittest
        (self.ws / "Pipfile").write_text("", encoding="utf-8")
        tests_dir = self.ws / "tests"
        tests_dir.mkdir(exist_ok=True)
        (tests_dir / "test_pip.py").write_text("import unittest\n", encoding="utf-8")
        self.assertEqual(
            detect_test_command(self.ws),
            "pipenv run python3 -m unittest discover -s tests -v",
        )

    # --- extract_command_dictionary integration tests ---

    def test_extract_command_dictionary_setup_py_fallback(self):
        """extract_command_dictionary extracts unittest command for setup.py repo."""
        (self.ws / "setup.py").write_text("from setuptools import setup\nsetup(name='pkg')\n", encoding="utf-8")
        tests_dir = self.ws / "tests"
        tests_dir.mkdir()
        (tests_dir / "test_pkg.py").write_text("import unittest\n", encoding="utf-8")

        cmds = extract_command_dictionary(self.ws)
        self.assertEqual(cmds.get("test"), "python3 -m unittest discover -s tests -v")

    def test_extract_command_dictionary_setup_cfg_tooling_fallbacks(self):
        """extract_command_dictionary extracts lint and check from setup.cfg without pyproject.toml."""
        (self.ws / "setup.cfg").write_text(
            "[flake8]\nmax-line-length = 100\n[mypy]\npython_version = 3.12\n",
            encoding="utf-8",
        )
        tests_dir = self.ws / "tests"
        tests_dir.mkdir()
        (tests_dir / "test_lint.py").write_text("import unittest\n", encoding="utf-8")

        cmds = extract_command_dictionary(self.ws)
        self.assertEqual(cmds.get("test"), "python3 -m unittest discover -s tests -v")
        self.assertEqual(cmds.get("lint"), "flake8")
        self.assertEqual(cmds.get("check"), "mypy .")

    def test_extract_command_dictionary_requirements_txt(self):
        """extract_command_dictionary extracts pytest command when requirements.txt specifies pytest."""
        (self.ws / "requirements.txt").write_text("pytest\n", encoding="utf-8")
        tests_dir = self.ws / "tests"
        tests_dir.mkdir()
        (tests_dir / "test_req.py").write_text("import pytest\n", encoding="utf-8")

        cmds = extract_command_dictionary(self.ws)
        self.assertEqual(cmds.get("test"), "pytest")

    def test_extract_command_dictionary_pure_shell_not_python_unittest(self):
        """extract_command_dictionary does not assign python unittest to a shell test suite."""
        tests_dir = self.ws / "tests"
        tests_dir.mkdir()
        (tests_dir / "test_sh.sh").write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")

        cmds = extract_command_dictionary(self.ws)
        self.assertNotIn("test", cmds)


if __name__ == "__main__":
    unittest.main()

