#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Arafat Zahan (@kuasha420)
# Corporate Stewardship & Infrastructure: Purrfect Software Limited (PSL)
# Governed by: ICARO-42/b Ordinance (Company-Supported Personal IP Framework)

"""
Hermetic Contract Tests for Dynamic Repository Awareness (DRA) in completion_fence_hook.py.
Governing Specifications: PSL-SPEC-2026-DRA-001 (Phase 3).

Validates:
1. Non-harness client directories NEVER receive harness test commands in refusal messages.
2. Native test runner patterns (Cargo, pnpm, npm, pytest, make, shell scripts) are recognized
   and clear code-dirty markers in client repositories.
3. Harness repository retains strict harness test requirements (rejecting external runners).
4. Full execution benchmark strictly <1.0s under hermetic isolation.
"""

from __future__ import annotations

import io
import json
import os
from pathlib import Path
import tempfile
import time
import unittest
from unittest.mock import patch

from harness.hooks import completion_fence_hook
from harness.hooks.completion_fence_hook import (
    check_command_verification,
    evaluate_stop,
    is_test_command,
    load_state,
    record_edit,
    record_verification,
    reset_state,
)


class TestCompletionFenceHookDRA(unittest.TestCase):
    """Test suite verifying Dynamic Repository Awareness in the stop hook fence."""

    def setUp(self):
        self.temp_state_dir = tempfile.TemporaryDirectory()
        self.state_dir = Path(self.temp_state_dir.name)
        self.orig_state_env = os.environ.get("PSL_HARNESS_STATE_DIR")
        os.environ["PSL_HARNESS_STATE_DIR"] = str(self.state_dir)

        # Create mock directories for client projects
        self.temp_workspace_dir = tempfile.TemporaryDirectory()
        self.client_dir = Path(self.temp_workspace_dir.name)

        # Reference to real harness repo root
        self.harness_root = Path(__file__).resolve().parent.parent

    def tearDown(self):
        if self.orig_state_env is not None:
            os.environ["PSL_HARNESS_STATE_DIR"] = self.orig_state_env
        else:
            os.environ.pop("PSL_HARNESS_STATE_DIR", None)
        self.temp_state_dir.cleanup()
        self.temp_workspace_dir.cleanup()

    # --- 1. Client Refusal Messaging (Zero Harness Test Pollution) ---

    def test_client_pnpm_project_refusal_message(self):
        """pnpm project receives clean client guidance with (pnpm test) and zero harness commands."""
        (self.client_dir / "package.json").write_text("{}", encoding="utf-8")
        (self.client_dir / "pnpm-lock.yaml").touch()

        conv_id = "test-client-pnpm"
        record_edit("src/components/Button.tsx", conv_id=conv_id, state_dir=self.state_dir, cwd=self.client_dir)

        res = evaluate_stop(conv_id=conv_id, state_dir=self.state_dir, cwd=self.client_dir)
        self.assertEqual(res.get("decision"), "continue")
        reason = res.get("reason", "")

        # Must NOT leak harness commands
        self.assertNotIn("agyis test", reason)
        self.assertNotIn("harness.cli test", reason)
        self.assertNotIn("./agyis", reason)

        # Must contain client guidance
        self.assertIn("Verification Required: Unverified code edits detected in: src/components/Button.tsx", reason)
        self.assertIn("Execute your project test suite (pnpm test) before stopping.", reason)

    def test_client_cargo_project_refusal_message(self):
        """Cargo project receives clean client guidance with (cargo test) and zero harness commands."""
        (self.client_dir / "Cargo.toml").write_text("[package]\nname = 'rust-crate'\n", encoding="utf-8")

        conv_id = "test-client-cargo"
        record_edit("src/lib.rs", conv_id=conv_id, state_dir=self.state_dir, cwd=self.client_dir)

        res = evaluate_stop(conv_id=conv_id, state_dir=self.state_dir, cwd=self.client_dir)
        self.assertEqual(res.get("decision"), "continue")
        reason = res.get("reason", "")

        self.assertNotIn("agyis test", reason)
        self.assertNotIn("harness.cli test", reason)
        self.assertIn("Verification Required: Unverified code edits detected in: src/lib.rs", reason)
        self.assertIn("Execute your project test suite (cargo test) before stopping.", reason)

    def test_client_pytest_project_refusal_message(self):
        """Pytest project receives clean client guidance with (pytest) and zero harness commands."""
        (self.client_dir / "pyproject.toml").write_text("[tool.pytest]\n", encoding="utf-8")

        conv_id = "test-client-pytest"
        record_edit("app/server.py", conv_id=conv_id, state_dir=self.state_dir, cwd=self.client_dir)

        res = evaluate_stop(conv_id=conv_id, state_dir=self.state_dir, cwd=self.client_dir)
        self.assertEqual(res.get("decision"), "continue")
        reason = res.get("reason", "")

        self.assertNotIn("agyis test", reason)
        self.assertNotIn("harness.cli test", reason)
        self.assertIn("Verification Required: Unverified code edits detected in: app/server.py", reason)
        self.assertIn("Execute your project test suite (pytest) before stopping.", reason)

    def test_client_makefile_project_refusal_message(self):
        """Makefile project receives clean client guidance with (make test) and zero harness commands."""
        (self.client_dir / "Makefile").write_text("test:\n\t@echo ok\n", encoding="utf-8")

        conv_id = "test-client-makefile"
        record_edit("src/main.c", conv_id=conv_id, state_dir=self.state_dir, cwd=self.client_dir)

        res = evaluate_stop(conv_id=conv_id, state_dir=self.state_dir, cwd=self.client_dir)
        self.assertEqual(res.get("decision"), "continue")
        reason = res.get("reason", "")

        self.assertNotIn("agyis test", reason)
        self.assertNotIn("harness.cli test", reason)
        self.assertIn("Execute your project test suite (make test) before stopping.", reason)

    def test_client_shell_tests_project_refusal_message(self):
        """Shell tests project receives clean client guidance with (bash tests/*.sh)."""
        tests_dir = self.client_dir / "tests"
        tests_dir.mkdir(parents=True, exist_ok=True)
        (tests_dir / "test_runner.sh").touch()

        conv_id = "test-client-shell"
        record_edit("bin/tool.sh", conv_id=conv_id, state_dir=self.state_dir, cwd=self.client_dir)

        res = evaluate_stop(conv_id=conv_id, state_dir=self.state_dir, cwd=self.client_dir)
        self.assertEqual(res.get("decision"), "continue")
        reason = res.get("reason", "")

        self.assertNotIn("agyis test", reason)
        self.assertNotIn("harness.cli test", reason)
        self.assertIn("Execute your project test suite (bash tests/*.sh) before stopping.", reason)

    def test_client_shell_test_singular_refusal_message(self):
        """Shell tests project with test/ (singular) receives guidance with (bash test/*.sh)."""
        test_dir = self.client_dir / "test"
        test_dir.mkdir(parents=True, exist_ok=True)
        (test_dir / "test_runner.sh").touch()

        conv_id = "test-client-shell-singular"
        record_edit("bin/tool.sh", conv_id=conv_id, state_dir=self.state_dir, cwd=self.client_dir)

        res = evaluate_stop(conv_id=conv_id, state_dir=self.state_dir, cwd=self.client_dir)
        self.assertEqual(res.get("decision"), "continue")
        reason = res.get("reason", "")

        self.assertNotIn("agyis test", reason)
        self.assertNotIn("harness.cli test", reason)
        self.assertIn("Execute your project test suite (bash test/*.sh) before stopping.", reason)

    def test_client_generic_unrecognized_refusal_message(self):
        """Client workspace without recognized config falls back to generic native runners."""
        conv_id = "test-client-generic"
        record_edit("src/module.py", conv_id=conv_id, state_dir=self.state_dir, cwd=self.client_dir)

        res = evaluate_stop(conv_id=conv_id, state_dir=self.state_dir, cwd=self.client_dir)
        self.assertEqual(res.get("decision"), "continue")
        reason = res.get("reason", "")

        self.assertNotIn("agyis test", reason)
        self.assertNotIn("harness.cli test", reason)
        self.assertIn("Execute your project test suite (e.g. npm test, cargo test, pytest) before stopping.", reason)

    # --- 2. Harness Repository Enforces Harness Verification ---

    def test_harness_workspace_refusal_message(self):
        """Harness repository checkout strictly enforces harness test commands."""
        conv_id = "test-harness-refusal"
        record_edit("harness/cli.py", conv_id=conv_id, state_dir=self.state_dir, cwd=self.harness_root)

        res = evaluate_stop(conv_id=conv_id, state_dir=self.state_dir, cwd=self.harness_root)
        self.assertEqual(res.get("decision"), "continue")
        reason = res.get("reason", "")

        self.assertIn("Verification Required: Unverified code edits detected in: harness/cli.py", reason)
        self.assertIn("Execute 'agyis test' (or 'python3 -m harness.cli test') before stopping.", reason)

    # --- 3. Client Native Test Runners Clear Dirty Markers ---

    def test_client_native_runners_clear_code_dirty(self):
        """In client repos, all recognized native test runners clear code_dirty on exit code 0."""
        test_cases = [
            ("cargo test", "src/lib.rs"),
            ("cargo test --lib", "src/lib.rs"),
            ("pnpm test", "src/app.ts"),
            ("pnpm --filter @repo/web test", "apps/web/index.tsx"),
            ("pnpm test --run", "src/index.ts"),
            ("npm test", "src/index.js"),
            ("npm run test", "src/index.js"),
            ("pytest", "tests/test_mod.py"),
            ("pytest tests/", "src/mod.py"),
            ("make test", "src/main.c"),
            ("make check", "src/main.c"),
            ("make verify", "src/main.c"),
            ("bash tests/suite.sh", "scripts/deploy.sh"),
            ("sh tests/all.sh", "scripts/deploy.sh"),
            ("bash tests/*.sh", "scripts/deploy.sh"),
            ("./tests/run.sh", "scripts/deploy.sh"),
            ("bash test/suite.sh", "scripts/deploy.sh"),
            ("bash test/*.sh", "scripts/deploy.sh"),
        ]

        for cmd, file_edited in test_cases:
            with self.subTest(cmd=cmd, file_edited=file_edited):
                conv_id = f"test-clear-{cmd.replace(' ', '-').replace('/', '-')}"
                record_edit(file_edited, conv_id=conv_id, state_dir=self.state_dir, cwd=self.client_dir)
                self.assertTrue(load_state(conv_id=conv_id, state_dir=self.state_dir)["code_dirty"])

                # Command verification with exit code 0
                matched = check_command_verification(cmd, exit_code=0, conv_id=conv_id, state_dir=self.state_dir, cwd=self.client_dir)
                self.assertTrue(matched, f"Expected '{cmd}' to be recognized as test runner in client repo")

                # State must be clean
                state = load_state(conv_id=conv_id, state_dir=self.state_dir)
                self.assertFalse(state["code_dirty"], f"Expected '{cmd}' to clear code_dirty")
                self.assertEqual(state["last_modified_files"], [])

                # evaluate_stop must allow
                res = evaluate_stop(conv_id=conv_id, state_dir=self.state_dir, cwd=self.client_dir)
                self.assertEqual(res.get("decision"), "allow")

    def test_client_native_runner_failure_retains_dirty(self):
        """In client repos, test failure (exit code != 0) does not clear dirty state."""
        conv_id = "test-client-fail"
        record_edit("src/app.ts", conv_id=conv_id, state_dir=self.state_dir, cwd=self.client_dir)

        matched = check_command_verification("pnpm test", exit_code=1, conv_id=conv_id, state_dir=self.state_dir, cwd=self.client_dir)
        self.assertTrue(matched)
        state = load_state(conv_id=conv_id, state_dir=self.state_dir)
        self.assertTrue(state["code_dirty"])

        res = evaluate_stop(conv_id=conv_id, state_dir=self.state_dir, cwd=self.client_dir)
        self.assertEqual(res.get("decision"), "continue")

    # --- 4. Harness Repository Rejects Non-Harness Test Runners ---

    def test_harness_workspace_rejects_external_runners(self):
        """In harness repo, cargo/pnpm/make/shell test runners do NOT clear harness code dirty state."""
        unsupported_harness_runners = [
            "cargo test",
            "pnpm test",
            "make test",
            "bash tests/test.sh",
        ]

        for runner in unsupported_harness_runners:
            with self.subTest(runner=runner):
                slug = runner.replace(' ', '-').replace('/', '-')
                conv_id = f"test-harness-reject-{slug}"
                record_edit("harness/cli.py", conv_id=conv_id, state_dir=self.state_dir, cwd=self.harness_root)
                self.assertTrue(load_state(conv_id=conv_id, state_dir=self.state_dir)["code_dirty"])

                # Command verification with exit code 0 on an external runner
                matched = check_command_verification(runner, exit_code=0, conv_id=conv_id, state_dir=self.state_dir, cwd=self.harness_root)
                self.assertFalse(matched, f"Harness repo must NOT recognize '{runner}' as a valid harness verification runner")

                # State must remain dirty
                state = load_state(conv_id=conv_id, state_dir=self.state_dir)
                self.assertTrue(state["code_dirty"])

                # evaluate_stop must remain blocked
                res = evaluate_stop(conv_id=conv_id, state_dir=self.state_dir, cwd=self.harness_root)
                self.assertEqual(res.get("decision"), "continue")

    def test_harness_workspace_accepts_harness_runners(self):
        """In harness repo, harness test commands clear code dirty state."""
        harness_runners = [
            "./agyis test",
            "agyis test",
            "python3 -m harness.cli test",
            "python3 -m unittest discover -s tests -v",
            "pytest tests/",
        ]

        for runner in harness_runners:
            with self.subTest(runner=runner):
                conv_id = f"test-harness-accept-{runner.replace(' ', '-').replace('/', '-')}"
                record_edit("harness/cli.py", conv_id=conv_id, state_dir=self.state_dir, cwd=self.harness_root)

                matched = check_command_verification(runner, exit_code=0, conv_id=conv_id, state_dir=self.state_dir, cwd=self.harness_root)
                self.assertTrue(matched, f"Expected '{runner}' to be recognized as harness test runner")

                state = load_state(conv_id=conv_id, state_dir=self.state_dir)
                self.assertFalse(state["code_dirty"])

                res = evaluate_stop(conv_id=conv_id, state_dir=self.state_dir, cwd=self.harness_root)
                self.assertEqual(res.get("decision"), "allow")

    # --- 5. Stdin/Stdout Hook JSON Interface with CWD ---

    def test_stdin_hook_interface_with_client_cwd(self):
        """Verifies hook main() handles cwd in JSON payload and emits clean client refusal."""
        (self.client_dir / "package.json").write_text("{}", encoding="utf-8")
        (self.client_dir / "pnpm-lock.yaml").touch()

        conv_id = "test-stdin-dra"

        # 1. Edit via toolCall with Cwd
        payload_edit = {
            "conversationId": conv_id,
            "toolCall": {
                "name": "write_to_file",
                "args": {
                    "TargetFile": "src/App.tsx",
                    "Cwd": str(self.client_dir),
                },
            },
        }
        buf_edit = io.StringIO()
        with patch("sys.stdin", io.StringIO(json.dumps(payload_edit))), patch("sys.stdout", buf_edit):
            completion_fence_hook.main()
        out_edit = json.loads(buf_edit.getvalue().strip())
        self.assertEqual(out_edit.get("decision"), "allow")

        # 2. Evaluate stop with cwd in payload
        payload_stop = {
            "conversationId": conv_id,
            "cwd": str(self.client_dir),
        }
        buf_stop = io.StringIO()
        with patch("sys.stdin", io.StringIO(json.dumps(payload_stop))), patch("sys.stdout", buf_stop):
            completion_fence_hook.main()
        out_stop = json.loads(buf_stop.getvalue().strip())

        self.assertEqual(out_stop.get("decision"), "continue")
        self.assertNotIn("agyis test", out_stop.get("reason", ""))
        self.assertIn("Execute your project test suite (pnpm test) before stopping.", out_stop.get("reason", ""))

    # --- 6. Benchmark Invariant (<1.0s) ---

    def test_dra_subsecond_benchmark(self):
        """Validates that DRA evaluation and state transitions execute in strictly <1.0s."""
        start = time.perf_counter()
        conv_id = "test-dra-perf"

        for _ in range(25):
            record_edit("src/index.ts", conv_id=conv_id, state_dir=self.state_dir, cwd=self.client_dir)
            evaluate_stop(conv_id=conv_id, state_dir=self.state_dir, cwd=self.client_dir)
            check_command_verification("pnpm test", exit_code=0, conv_id=conv_id, state_dir=self.state_dir, cwd=self.client_dir)

        duration = time.perf_counter() - start
        self.assertLess(
            duration,
            1.0,
            f"Expected 25 DRA evaluation cycles to execute in <1.0s, took {duration:.4f}s",
        )


if __name__ == "__main__":
    unittest.main()
