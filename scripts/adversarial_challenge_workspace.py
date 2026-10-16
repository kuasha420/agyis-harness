#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Arafat Zahan (@kuasha420)
# Corporate Stewardship & Infrastructure: Purrfect Software Limited (PSL)

"""
Adversarial Challenge Suite for Workspace Test Runner Detection and Completion Fence Hook.
Milestone 3 — PR #40 Verification.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
import tempfile
import unittest

from harness.utils.workspace import (
    detect_project_test_runner,
    is_harness_workspace,
)
from harness.hooks.completion_fence_hook import (
    check_command_verification,
    evaluate_stop,
    is_test_command,
    load_state,
    record_edit,
    record_verification,
    reset_state,
    UNIVERSAL_TEST_RUNNER_PATTERNS,
)


class AdversarialWorkspaceTestRunnerTest(unittest.TestCase):
    """Adversarial stress-test cases for workspace test runner detection."""

    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.root = Path(self.temp_dir.name)
        self.state_temp_dir = tempfile.TemporaryDirectory()
        self.state_dir = Path(self.state_temp_dir.name)
        self.orig_state_env = os.environ.get("PSL_HARNESS_STATE_DIR")
        os.environ["PSL_HARNESS_STATE_DIR"] = str(self.state_dir)

    def tearDown(self):
        if self.orig_state_env is not None:
            os.environ["PSL_HARNESS_STATE_DIR"] = self.orig_state_env
        else:
            os.environ.pop("PSL_HARNESS_STATE_DIR", None)
        self.temp_dir.cleanup()
        self.state_temp_dir.cleanup()

    # =========================================================================
    # Category A: Core Directory Hierarchy & Exact Detection
    # =========================================================================

    def test_singular_test_directory_with_sh(self):
        """Projects with only test/ (singular) containing .sh files -> returns 'bash test/*.sh'."""
        test_dir = self.root / "test"
        test_dir.mkdir()
        (test_dir / "suite.sh").touch()

        runner = detect_project_test_runner(self.root)
        self.assertEqual(runner, "bash test/*.sh")

    def test_plural_tests_directory_with_sh(self):
        """Projects with only tests/ (plural) containing .sh files -> returns 'bash tests/*.sh'."""
        tests_dir = self.root / "tests"
        tests_dir.mkdir()
        (tests_dir / "test_all.sh").touch()

        runner = detect_project_test_runner(self.root)
        self.assertEqual(runner, "bash tests/*.sh")

    def test_both_exist_both_have_sh_precedence(self):
        """When both tests/ and test/ exist and both have .sh files, tests/ takes precedence."""
        tests_dir = self.root / "tests"
        tests_dir.mkdir()
        (tests_dir / "test_a.sh").touch()

        test_dir = self.root / "test"
        test_dir.mkdir()
        (test_dir / "test_b.sh").touch()

        runner = detect_project_test_runner(self.root)
        self.assertEqual(runner, "bash tests/*.sh")

    def test_both_exist_tests_has_no_sh_test_has_sh(self):
        """When tests/ exists with non-sh files, but test/ has .sh files -> returns 'bash test/*.sh'."""
        tests_dir = self.root / "tests"
        tests_dir.mkdir()
        (tests_dir / "README.md").touch()
        (tests_dir / "helper.py").touch()

        test_dir = self.root / "test"
        test_dir.mkdir()
        (test_dir / "run_test.sh").touch()

        runner = detect_project_test_runner(self.root)
        self.assertEqual(runner, "bash test/*.sh")

    def test_both_exist_test_has_no_sh_tests_has_sh(self):
        """When test/ exists with non-sh files, but tests/ has .sh files -> returns 'bash tests/*.sh'."""
        test_dir = self.root / "test"
        test_dir.mkdir()
        (test_dir / "README.md").touch()

        tests_dir = self.root / "tests"
        tests_dir.mkdir()
        (tests_dir / "run.sh").touch()

        runner = detect_project_test_runner(self.root)
        self.assertEqual(runner, "bash tests/*.sh")

    def test_both_exist_neither_has_sh(self):
        """When both test/ and tests/ exist without any .sh files -> returns None."""
        test_dir = self.root / "test"
        test_dir.mkdir()
        (test_dir / "helper.py").touch()

        tests_dir = self.root / "tests"
        tests_dir.mkdir()
        (tests_dir / "test_main.py").touch()

        runner = detect_project_test_runner(self.root)
        self.assertIsNone(runner)

    # =========================================================================
    # Category B: Directory Contents, Subdirectories, Edge Cases
    # =========================================================================

    def test_subdirectories_only_inside_test_no_toplevel_sh(self):
        """Subdirectories inside test/ (e.g. test/unit/test.sh) without top-level .sh returns None."""
        test_dir = self.root / "test" / "unit"
        test_dir.mkdir(parents=True)
        (test_dir / "test.sh").touch()

        runner = detect_project_test_runner(self.root)
        self.assertIsNone(runner)

    def test_subdirectories_plus_toplevel_sh(self):
        """Top-level .sh plus subdirectories inside test/ -> returns 'bash test/*.sh'."""
        test_dir = self.root / "test"
        test_dir.mkdir()
        (test_dir / "run.sh").touch()
        (test_dir / "unit").mkdir()
        (test_dir / "unit" / "unit_test.sh").touch()

        runner = detect_project_test_runner(self.root)
        self.assertEqual(runner, "bash test/*.sh")

    def test_non_shell_files_only_in_test(self):
        """test/ containing only non-shell files -> returns None."""
        test_dir = self.root / "test"
        test_dir.mkdir()
        (test_dir / "test.py").touch()
        (test_dir / "test.js").touch()
        (test_dir / "test.sh.bak").touch()
        (test_dir / "test.sh~").touch()
        (test_dir / "test.bash").touch()

        runner = detect_project_test_runner(self.root)
        self.assertIsNone(runner)

    def test_special_characters_in_filenames(self):
        """test/ containing spaces, hyphens, underscores in .sh filenames."""
        test_dir = self.root / "test"
        test_dir.mkdir()
        (test_dir / "run test-1_beta.sh").touch()

        runner = detect_project_test_runner(self.root)
        self.assertEqual(runner, "bash test/*.sh")

    def test_symlinked_sh_file(self):
        """test/ containing a symlink to a .sh file -> returns 'bash test/*.sh'."""
        target_dir = self.root / "scripts"
        target_dir.mkdir()
        target_file = target_dir / "real_test.sh"
        target_file.touch()

        test_dir = self.root / "test"
        test_dir.mkdir()
        (test_dir / "symlink_test.sh").symlink_to(target_file)

        runner = detect_project_test_runner(self.root)
        self.assertEqual(runner, "bash test/*.sh")

    def test_symlinked_test_directory(self):
        """test/ is itself a symlink to another directory with .sh files."""
        actual_test_dir = self.root / "my_tests"
        actual_test_dir.mkdir()
        (actual_test_dir / "suite.sh").touch()

        (self.root / "test").symlink_to(actual_test_dir)

        runner = detect_project_test_runner(self.root)
        self.assertEqual(runner, "bash test/*.sh")

    def test_test_as_regular_file_not_dir(self):
        """If 'test' or 'tests' is a file, not a directory -> returns None without crashing."""
        (self.root / "test").touch()
        (self.root / "tests").touch()

        runner = detect_project_test_runner(self.root)
        self.assertIsNone(runner)

    def test_hidden_file_glob_behavior(self):
        """Documents Python 3.12 pathlib.Path.glob behavior on hidden .sh files."""
        test_dir = self.root / "test"
        test_dir.mkdir()
        (test_dir / ".test.sh").touch()

        # In Python 3.12, Path.glob("*.sh") matches .test.sh
        runner = detect_project_test_runner(self.root)
        self.assertEqual(runner, "bash test/*.sh")

    def test_directory_ending_with_dot_sh_behavior(self):
        """Documents Path.glob behavior when a subdirectory itself is named '*.sh'."""
        test_dir = self.root / "test"
        test_dir.mkdir()
        (test_dir / "fixture.sh").mkdir()

        # In Python, Path.glob("*.sh") yields directories named *.sh as well
        runner = detect_project_test_runner(self.root)
        self.assertEqual(runner, "bash test/*.sh")

    def test_case_sensitivity_linux(self):
        """Directory named 'Test' or 'Tests' on Linux -> returns None."""
        test_dir = self.root / "Test"
        test_dir.mkdir()
        (test_dir / "suite.sh").touch()

        runner = detect_project_test_runner(self.root)
        self.assertIsNone(runner)

    # =========================================================================
    # Category C: Precedence Across Manifests
    # =========================================================================

    def test_package_json_over_test_sh(self):
        """package.json takes precedence over test/*.sh."""
        (self.root / "package.json").write_text(json.dumps({"scripts": {"test": "mocha"}}))
        test_dir = self.root / "test"
        test_dir.mkdir()
        (test_dir / "test.sh").touch()

        self.assertEqual(detect_project_test_runner(self.root), "npm test")

    def test_cargo_over_test_sh(self):
        """Cargo.toml takes precedence over test/*.sh."""
        (self.root / "Cargo.toml").write_text("[package]\nname = 'app'\n")
        test_dir = self.root / "test"
        test_dir.mkdir()
        (test_dir / "test.sh").touch()

        self.assertEqual(detect_project_test_runner(self.root), "cargo test")

    def test_pyproject_over_test_sh(self):
        """pyproject.toml takes precedence over test/*.sh."""
        (self.root / "pyproject.toml").write_text("[tool.pytest]\n")
        test_dir = self.root / "test"
        test_dir.mkdir()
        (test_dir / "test.sh").touch()

        self.assertEqual(detect_project_test_runner(self.root), "pytest")

    def test_makefile_over_test_sh(self):
        """Makefile takes precedence over test/*.sh."""
        (self.root / "Makefile").write_text("test:\n\t@bash test/test.sh\n")
        test_dir = self.root / "test"
        test_dir.mkdir()
        (test_dir / "test.sh").touch()

        self.assertEqual(detect_project_test_runner(self.root), "make test")

    # =========================================================================
    # Category D: Integration with completion_fence_hook.py
    # =========================================================================

    def test_completion_fence_refusal_singular_test(self):
        """completion_fence_hook evaluate_stop generates clean refusal with 'bash test/*.sh'."""
        test_dir = self.root / "test"
        test_dir.mkdir()
        (test_dir / "ci.sh").touch()

        conv_id = "adv-fence-singular"
        record_edit("src/core.py", conv_id=conv_id, state_dir=self.state_dir, cwd=self.root)

        res = evaluate_stop(conv_id=conv_id, state_dir=self.state_dir, cwd=self.root)
        self.assertEqual(res.get("decision"), "continue")
        reason = res.get("reason", "")

        # Verifications
        self.assertIn("Verification Required: Unverified code edits detected in: src/core.py", reason)
        self.assertIn("Execute your project test suite (bash test/*.sh) before stopping.", reason)
        self.assertNotIn("agyis test", reason)
        self.assertNotIn("harness.cli test", reason)
        self.assertNotIn("./agyis", reason)

    def test_completion_fence_refusal_plural_tests(self):
        """completion_fence_hook evaluate_stop generates clean refusal with 'bash tests/*.sh'."""
        tests_dir = self.root / "tests"
        tests_dir.mkdir()
        (tests_dir / "ci.sh").touch()

        conv_id = "adv-fence-plural"
        record_edit("src/core.py", conv_id=conv_id, state_dir=self.state_dir, cwd=self.root)

        res = evaluate_stop(conv_id=conv_id, state_dir=self.state_dir, cwd=self.root)
        self.assertEqual(res.get("decision"), "continue")
        reason = res.get("reason", "")

        self.assertIn("Execute your project test suite (bash tests/*.sh) before stopping.", reason)
        self.assertNotIn("agyis test", reason)

    def test_is_test_command_canonical_invocations(self):
        """Verify is_test_command recognizes all canonical shell test runner invocations."""
        valid_commands = [
            "bash test/*.sh",
            "bash tests/*.sh",
            "sh test/*.sh",
            "sh tests/*.sh",
            "bash test/run.sh",
            "bash tests/run.sh",
            "sh test/run.sh",
            "sh tests/run.sh",
            "./test/run.sh",
            "./tests/run.sh",
            "./test/sub/run.sh",
            "sudo bash test/*.sh",
            "nohup bash test/*.sh",
            "time bash test/*.sh",
            "git status; bash test/*.sh",
            "echo 'running'; bash tests/*.sh",
            "bash test/suite-1_2.sh",
        ]
        for cmd in valid_commands:
            with self.subTest(cmd=cmd):
                self.assertTrue(
                    is_test_command(cmd, cwd=self.root),
                    f"Command '{cmd}' should be recognized as a valid test runner"
                )

    def test_check_command_verification_clears_code_dirty_on_singular_test(self):
        """Running 'bash test/*.sh' with exit code 0 clears code_dirty state."""
        test_dir = self.root / "test"
        test_dir.mkdir()
        (test_dir / "run.sh").touch()

        conv_id = "adv-clear-dirty-singular"
        record_edit("src/handler.py", conv_id=conv_id, state_dir=self.state_dir, cwd=self.root)
        state = load_state(conv_id=conv_id, state_dir=self.state_dir)
        self.assertTrue(state["code_dirty"])

        # Execute test runner with exit code 0
        cleared = check_command_verification("bash test/*.sh", exit_code=0, conv_id=conv_id, state_dir=self.state_dir, cwd=self.root)
        self.assertTrue(cleared)

        state_after = load_state(conv_id=conv_id, state_dir=self.state_dir)
        self.assertFalse(state_after["code_dirty"])
        self.assertEqual(state_after["last_modified_files"], [])
        self.assertIsNotNone(state_after["last_verified_at"])

        # Stop evaluate should now allow
        res = evaluate_stop(conv_id=conv_id, state_dir=self.state_dir, cwd=self.root)
        self.assertEqual(res.get("decision"), "allow")

    def test_check_command_verification_does_not_clear_on_failure(self):
        """Running 'bash test/*.sh' with exit code != 0 does NOT clear code_dirty."""
        test_dir = self.root / "test"
        test_dir.mkdir()
        (test_dir / "run.sh").touch()

        conv_id = "adv-fail-singular"
        record_edit("src/handler.py", conv_id=conv_id, state_dir=self.state_dir, cwd=self.root)

        # Execute test runner with exit code 1
        recognized = check_command_verification("bash test/*.sh", exit_code=1, conv_id=conv_id, state_dir=self.state_dir, cwd=self.root)
        self.assertTrue(recognized)

        state_after = load_state(conv_id=conv_id, state_dir=self.state_dir)
        self.assertTrue(state_after["code_dirty"])

        # Stop evaluate should still continue (block)
        res = evaluate_stop(conv_id=conv_id, state_dir=self.state_dir, cwd=self.root)
        self.assertEqual(res.get("decision"), "continue")

    def test_anti_deadlock_valve_trips_after_two_blocks(self):
        """Anti-deadlock valve trips on third stop attempt in client test directory."""
        test_dir = self.root / "test"
        test_dir.mkdir()
        (test_dir / "run.sh").touch()

        conv_id = "adv-deadlock-valve"
        record_edit("src/app.py", conv_id=conv_id, state_dir=self.state_dir, cwd=self.root)

        # Block 1
        res1 = evaluate_stop(conv_id=conv_id, state_dir=self.state_dir, cwd=self.root)
        self.assertEqual(res1.get("decision"), "continue")

        # Block 2
        res2 = evaluate_stop(conv_id=conv_id, state_dir=self.state_dir, cwd=self.root)
        self.assertEqual(res2.get("decision"), "continue")

        # Block 3 -> trips valve
        res3 = evaluate_stop(conv_id=conv_id, state_dir=self.state_dir, cwd=self.root)
        self.assertEqual(res3.get("decision"), "allow")
        self.assertIn("Anti-deadlock valve tripped", res3.get("warning", ""))


if __name__ == "__main__":
    unittest.main()
