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
    extract_exit_code,
    is_cleanroom_contract_file,
    is_ephemeral_scratch_path,
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


class TestCompletionFenceHardeningM2(unittest.TestCase):
    """
    Contract test suite for Milestone 2: Issues #42, #43, and #45.
    Governing ADRs: ADR-014, ADR-015, ADR-022.
    """

    def setUp(self):
        self.temp_state_dir = tempfile.TemporaryDirectory()
        self.state_dir = Path(self.temp_state_dir.name)
        self.orig_state_env = os.environ.get("PSL_HARNESS_STATE_DIR")
        os.environ["PSL_HARNESS_STATE_DIR"] = str(self.state_dir)

        self.temp_workspace_dir = tempfile.TemporaryDirectory()
        self.client_dir = Path(self.temp_workspace_dir.name)
        self.harness_root = Path(__file__).resolve().parent.parent

    def tearDown(self):
        if self.orig_state_env is not None:
            os.environ["PSL_HARNESS_STATE_DIR"] = self.orig_state_env
        else:
            os.environ.pop("PSL_HARNESS_STATE_DIR", None)
        self.temp_state_dir.cleanup()
        self.temp_workspace_dir.cleanup()

    # --- Issue #42: PostToolUse and Robust Exit Code Extraction ---

    def test_extract_exit_code_direct_and_nested(self):
        """extract_exit_code retrieves exit codes across direct and nested payload formats."""
        self.assertEqual(extract_exit_code({"exitCode": 0}), 0)
        self.assertEqual(extract_exit_code({"exit_code": 1}), 1)
        self.assertEqual(extract_exit_code({"returncode": 0}), 0)
        self.assertEqual(extract_exit_code({"returncode": 2}), 2)
        self.assertEqual(extract_exit_code({"toolResponse": {"exitCode": 0}}), 0)
        self.assertEqual(extract_exit_code({"toolResponse": {"result": {"exit_code": 2}}}), 2)
        self.assertEqual(extract_exit_code({"result": {"returncode": 101}}), 101)
        self.assertEqual(extract_exit_code({"toolResponse": '{"exitCode": 0}'}), 0)
        self.assertEqual(extract_exit_code({"toolResponse": "The command exited with code 0.\nOutput:\nok"}), 0)
        self.assertEqual(extract_exit_code({"toolResponse": "failed with exit code 1"}), 1)
        self.assertEqual(extract_exit_code({"output": "The command exited with code 0.\nOutput:\nok"}), 0)
        self.assertEqual(extract_exit_code({"output": "failed with exit code 1"}), 1)
        self.assertEqual(extract_exit_code({"stdout": "The command exited with code 0."}), 0)
        self.assertIsNone(extract_exit_code({}))
        self.assertIsNone(extract_exit_code({"toolCall": {"name": "run_command"}}))

    def test_post_tool_use_exit_code_zero_clears_code_dirty(self):
        """PostToolUse with run_command and exitCode: 0 auto-clears code_dirty."""
        conv_id = "test-post-tool-use-zero"
        record_edit("src/app.py", conv_id=conv_id, state_dir=self.state_dir, cwd=self.client_dir)
        self.assertTrue(load_state(conv_id=conv_id, state_dir=self.state_dir)["code_dirty"])

        payload = {
            "conversationId": conv_id,
            "toolCall": {
                "name": "run_command",
                "args": {"CommandLine": "pytest"},
            },
            "exitCode": 0,
        }
        buf = io.StringIO()
        with patch("sys.stdin", io.StringIO(json.dumps(payload))), patch("sys.stdout", buf):
            completion_fence_hook.main()

        out = json.loads(buf.getvalue().strip())
        self.assertEqual(out, {})
        state = load_state(conv_id=conv_id, state_dir=self.state_dir)
        self.assertFalse(state["code_dirty"])
        self.assertEqual(state["block_count"], 0)
        self.assertEqual(state["last_modified_files"], [])

    def test_post_tool_use_exit_code_nonzero_preserves_dirty(self):
        """PostToolUse with run_command and non-zero exit code preserves code_dirty."""
        conv_id = "test-post-tool-use-nonzero"
        record_edit("src/app.py", conv_id=conv_id, state_dir=self.state_dir, cwd=self.client_dir)

        payload = {
            "conversationId": conv_id,
            "toolCall": {
                "name": "run_command",
                "args": {"CommandLine": "pytest"},
            },
            "exitCode": 1,
        }
        buf = io.StringIO()
        with patch("sys.stdin", io.StringIO(json.dumps(payload))), patch("sys.stdout", buf):
            completion_fence_hook.main()

        state = load_state(conv_id=conv_id, state_dir=self.state_dir)
        self.assertTrue(state["code_dirty"])
        res = evaluate_stop(conv_id=conv_id, state_dir=self.state_dir, cwd=self.client_dir)
        self.assertEqual(res.get("decision"), "continue")

    def test_post_tool_use_nested_tool_response_clears_dirty(self):
        """PostToolUse with nested toolResponse exitCode 0 clears code_dirty."""
        conv_id = "test-post-tool-nested"
        record_edit("src/app.py", conv_id=conv_id, state_dir=self.state_dir, cwd=self.client_dir)

        payload = {
            "conversationId": conv_id,
            "toolCall": {
                "name": "run_command",
                "args": {"CommandLine": "pytest"},
            },
            "toolResponse": {
                "exitCode": 0,
                "output": "1 passed",
            },
        }
        buf = io.StringIO()
        with patch("sys.stdin", io.StringIO(json.dumps(payload))), patch("sys.stdout", buf):
            completion_fence_hook.main()

        state = load_state(conv_id=conv_id, state_dir=self.state_dir)
        self.assertFalse(state["code_dirty"])

    # --- Issue #43: Ephemeral Scratch Path Filtering & Workspace Isolation ---

    def test_is_ephemeral_scratch_path_unit(self):
        """is_ephemeral_scratch_path accurately identifies scratch paths and workspace boundaries."""
        # 1. Antigravity brain scratch path
        brain_scratch = "/home/kuasha/.gemini/antigravity/brain/session-123/scratch/tool.py"
        self.assertTrue(is_ephemeral_scratch_path(brain_scratch, cwd=self.client_dir))
        self.assertTrue(is_ephemeral_scratch_path(brain_scratch, cwd=None))

        # 2. Outside cwd when cwd is provided
        outside_path = "/tmp/scratch_test.py"
        workspace = Path("/home/kuasha/Dev/my-project")
        self.assertTrue(is_ephemeral_scratch_path(outside_path, cwd=workspace))

        # 3. Inside cwd when cwd is provided
        inside_path = self.client_dir / "src" / "index.ts"
        self.assertFalse(is_ephemeral_scratch_path(str(inside_path), cwd=self.client_dir))
        self.assertFalse(is_ephemeral_scratch_path("src/index.ts", cwd=self.client_dir))

        # 4. Outside cwd even if cwd is also inside /tmp
        other_temp = Path(tempfile.gettempdir()) / "other_scratch_dir" / "script.py"
        self.assertTrue(is_ephemeral_scratch_path(str(other_temp), cwd=self.client_dir))

        # 5. When cwd is None
        self.assertTrue(is_ephemeral_scratch_path("/tmp/test.py", cwd=None))
        self.assertTrue(is_ephemeral_scratch_path("/var/tmp/script.sh", cwd=None))
        self.assertFalse(is_ephemeral_scratch_path("src/app.py", cwd=None))

    def test_scratch_edit_does_not_mark_dirty(self):
        """Editing an ephemeral scratch file does not mark state dirty."""
        conv_id = "test-scratch-edit"
        scratch_file = "/tmp/scratch_test.py"
        record_edit(scratch_file, conv_id=conv_id, state_dir=self.state_dir, cwd=self.harness_root)

        state = load_state(conv_id=conv_id, state_dir=self.state_dir)
        self.assertFalse(state["code_dirty"])
        self.assertEqual(state["last_modified_files"], [])

        res = evaluate_stop(conv_id=conv_id, state_dir=self.state_dir, cwd=self.harness_root)
        self.assertEqual(res.get("decision"), "allow")

    def test_brain_scratch_edit_does_not_mark_dirty(self):
        """Editing a file in .gemini/antigravity/brain/.../scratch/... does not mark state dirty."""
        conv_id = "test-brain-scratch"
        brain_file = "/home/kuasha/.gemini/antigravity/brain/0e149e12-222e-4731-a96b-34d5026abdca/scratch/script.py"
        record_edit(brain_file, conv_id=conv_id, state_dir=self.state_dir, cwd=self.harness_root)

        state = load_state(conv_id=conv_id, state_dir=self.state_dir)
        self.assertFalse(state["code_dirty"])

        res = evaluate_stop(conv_id=conv_id, state_dir=self.state_dir, cwd=self.harness_root)
        self.assertEqual(res.get("decision"), "allow")

    def test_workspace_edit_in_temp_dir_marks_dirty(self):
        """Editing a code file inside the workspace (even in temp directory) DOES mark state dirty."""
        conv_id = "test-temp-workspace"
        inside_file = str(self.client_dir / "src" / "main.py")
        record_edit(inside_file, conv_id=conv_id, state_dir=self.state_dir, cwd=self.client_dir)

        state = load_state(conv_id=conv_id, state_dir=self.state_dir)
        self.assertTrue(state["code_dirty"])
        self.assertIn(inside_file, state["last_modified_files"])

    # --- Issue #45: Cleanroom Spec and Ledger Verification Gates ---

    def test_is_cleanroom_contract_file_unit(self):
        """is_cleanroom_contract_file matches docs/specs/** and .agents/ledger/** files."""
        self.assertTrue(is_cleanroom_contract_file("docs/specs/my_spec.md"))
        self.assertTrue(is_cleanroom_contract_file("docs/specs/v1/api.md"))
        self.assertTrue(is_cleanroom_contract_file(".agents/ledger/obligations.json"))
        self.assertTrue(is_cleanroom_contract_file(".agents/ledger/tasks.json"))
        self.assertTrue(is_cleanroom_contract_file("/home/user/repo/docs/specs/spec.md"))
        self.assertTrue(is_cleanroom_contract_file("/home/user/repo/.agents/ledger/obligations.json"))

        # Standard docs remain exempt
        self.assertFalse(is_cleanroom_contract_file("README.md"))
        self.assertFalse(is_cleanroom_contract_file("PROJECT.md"))
        self.assertFalse(is_cleanroom_contract_file("docs/architecture.md"))
        self.assertFalse(is_cleanroom_contract_file("docs/guide.md"))
        self.assertFalse(is_cleanroom_contract_file("docs/specs.md"))

    def test_cleanroom_spec_edit_dirties_state_and_blocks_stop(self):
        """Editing docs/specs/*.md marks spec_dirty = True (code_dirty = False) and blocks evaluate_stop with cleanroom message."""
        conv_id = "test-spec-contract"
        record_edit("docs/specs/my_spec.md", conv_id=conv_id, state_dir=self.state_dir, cwd=self.harness_root)

        state = load_state(conv_id=conv_id, state_dir=self.state_dir)
        self.assertFalse(state["code_dirty"])
        self.assertTrue(state["spec_dirty"])
        self.assertIn("docs/specs/my_spec.md", state["last_modified_files"])

        res = evaluate_stop(conv_id=conv_id, state_dir=self.state_dir, cwd=self.harness_root)
        self.assertEqual(res.get("decision"), "continue")
        reason = res.get("reason", "")
        self.assertEqual(
            reason,
            "Cleanroom Verification Required: Unverified cleanroom contract edits detected in: docs/specs/my_spec.md. "
            "Execute 'rea verify-reconstruction' or 'agyis verify --spec' before stopping."
        )

    def test_cleanroom_ledger_edit_dirties_state_and_blocks_stop(self):
        """Editing .agents/ledger/*.json marks spec_dirty = True (code_dirty = False) and blocks evaluate_stop."""
        conv_id = "test-ledger-contract"
        record_edit(".agents/ledger/obligations.json", conv_id=conv_id, state_dir=self.state_dir, cwd=self.harness_root)

        state = load_state(conv_id=conv_id, state_dir=self.state_dir)
        self.assertFalse(state["code_dirty"])
        self.assertTrue(state["spec_dirty"])
        self.assertIn(".agents/ledger/obligations.json", state["last_modified_files"])

        res = evaluate_stop(conv_id=conv_id, state_dir=self.state_dir, cwd=self.harness_root)
        self.assertEqual(res.get("decision"), "continue")
        reason = res.get("reason", "")
        self.assertEqual(
            reason,
            "Cleanroom Verification Required: Unverified cleanroom contract edits detected in: .agents/ledger/obligations.json. "
            "Execute 'rea verify-reconstruction' or 'agyis verify --spec' before stopping."
        )

    def test_mixed_code_and_contract_edits_refusal_message(self):
        """Mixed code and contract edits emit combined diagnostic refusal guidance."""
        conv_id = "test-mixed-edits"
        record_edit("harness/cli.py", conv_id=conv_id, state_dir=self.state_dir, cwd=self.harness_root)
        record_edit("docs/specs/my_spec.md", conv_id=conv_id, state_dir=self.state_dir, cwd=self.harness_root)

        res = evaluate_stop(conv_id=conv_id, state_dir=self.state_dir, cwd=self.harness_root)
        self.assertEqual(res.get("decision"), "continue")
        reason = res.get("reason", "")
        self.assertIn("Verification Required: Unverified code and cleanroom contract edits detected in: harness/cli.py, docs/specs/my_spec.md", reason)

    def test_standard_docs_remain_exempt(self):
        """Standard docs (README.md, PROJECT.md, docs/architecture.md, docs/guide.md) remain exempt."""
        conv_id = "test-standard-docs"
        for doc in ("README.md", "PROJECT.md", "docs/architecture.md", "docs/guide.md"):
            record_edit(doc, conv_id=conv_id, state_dir=self.state_dir, cwd=self.harness_root)

        state = load_state(conv_id=conv_id, state_dir=self.state_dir)
        self.assertFalse(state["code_dirty"])
        self.assertFalse(state["spec_dirty"])
        self.assertEqual(state["last_modified_files"], [])

        res = evaluate_stop(conv_id=conv_id, state_dir=self.state_dir, cwd=self.harness_root)
        self.assertEqual(res.get("decision"), "allow")

    def test_cleanroom_contract_cleared_by_test_command(self):
        """Cleanroom contract dirty state is cleared by successful test verification."""
        conv_id = "test-cleanroom-verify"
        record_edit("docs/specs/my_spec.md", conv_id=conv_id, state_dir=self.state_dir, cwd=self.harness_root)
        self.assertTrue(load_state(conv_id=conv_id, state_dir=self.state_dir)["spec_dirty"])

        matched = check_command_verification("agyis test", exit_code=0, conv_id=conv_id, state_dir=self.state_dir, cwd=self.harness_root)
        self.assertTrue(matched)

        state = load_state(conv_id=conv_id, state_dir=self.state_dir)
        self.assertFalse(state["code_dirty"])
        self.assertFalse(state["spec_dirty"])
        self.assertEqual(evaluate_stop(conv_id=conv_id, state_dir=self.state_dir, cwd=self.harness_root)["decision"], "allow")

    def test_cleanroom_contract_cleared_by_agyis_verify_spec(self):
        """Cleanroom contract dirty state is cleared by './agyis verify --spec' (DEF-02)."""
        conv_id = "test-cleanroom-verify-dot-slash-spec"
        record_edit("docs/specs/my_spec.md", conv_id=conv_id, state_dir=self.state_dir, cwd=self.harness_root)
        self.assertTrue(load_state(conv_id=conv_id, state_dir=self.state_dir)["spec_dirty"])

        self.assertTrue(is_test_command("./agyis verify --spec", cwd=self.harness_root))
        matched = check_command_verification(
            "./agyis verify --spec",
            exit_code=0,
            conv_id=conv_id,
            state_dir=self.state_dir,
            cwd=self.harness_root,
        )
        self.assertTrue(matched)

        state = load_state(conv_id=conv_id, state_dir=self.state_dir)
        self.assertFalse(state["code_dirty"])
        self.assertFalse(state["spec_dirty"])
        self.assertEqual(evaluate_stop(conv_id=conv_id, state_dir=self.state_dir, cwd=self.harness_root)["decision"], "allow")

    def test_workspace_paths_fallback_and_tool_args_cwd(self):
        """Verifies workspacePaths fallback in payload and lowercase cwd in tool args."""
        (self.client_dir / "package.json").write_text("{}", encoding="utf-8")
        (self.client_dir / "pnpm-lock.yaml").touch()

        conv_id = "test-ws-paths-fallback"

        # 1. Edit using lowercase 'cwd' in tool args
        payload_edit = {
            "conversationId": conv_id,
            "toolCall": {
                "name": "write_to_file",
                "args": {
                    "TargetFile": "src/Comp.tsx",
                    "cwd": str(self.client_dir),
                },
            },
        }
        buf_edit = io.StringIO()
        with patch("sys.stdin", io.StringIO(json.dumps(payload_edit))), patch("sys.stdout", buf_edit):
            completion_fence_hook.main()
        out_edit = json.loads(buf_edit.getvalue().strip())
        self.assertEqual(out_edit.get("decision"), "allow")

        state = load_state(conv_id=conv_id, state_dir=self.state_dir)
        self.assertTrue(state["code_dirty"])
        self.assertEqual(state.get("cwd"), str(self.client_dir))

        # 2. Evaluate stop with workspacePaths fallback (cwd/workspace omitted)
        payload_stop = {
            "conversationId": conv_id,
            "workspacePaths": [str(self.client_dir)],
        }
        buf_stop = io.StringIO()
        with patch("sys.stdin", io.StringIO(json.dumps(payload_stop))), patch("sys.stdout", buf_stop):
            completion_fence_hook.main()
        out_stop = json.loads(buf_stop.getvalue().strip())
        self.assertEqual(out_stop.get("decision"), "continue")
        self.assertIn("Execute your project test suite (pnpm test) before stopping.", out_stop.get("reason", ""))
        self.assertNotIn("agyis test", out_stop.get("reason", ""))

    # --- PostToolUse Empty Dict Invariant Across All Tools ---

    def test_post_tool_use_emits_empty_dict_across_all_tools(self):
        """
        Validates that all PostToolUse tool completions emit exact JSON {}
        across all tool types (run_command, write_to_file, replace_file_content,
        edit_file, view_file, grep_search, manage_task, rea_*, and MCP tools),
        preventing Antigravity protojson unmarshaling crashes.
        """
        tools_to_test = [
            ("run_command", {"CommandLine": "pytest tests/"}),
            ("write_to_file", {"TargetFile": "src/app.py", "CodeContent": "print('hello')"}),
            ("replace_file_content", {"TargetFile": "src/index.ts", "ReplacementContent": "export {}"}),
            ("edit_file", {"file_path": "src/module.py"}),
            ("view_file", {"AbsolutePath": "/home/user/repo/src/app.py"}),
            ("grep_search", {"Query": "TODO", "SearchPath": "/home/user/repo"}),
            ("manage_task", {"Action": "status", "TaskId": "task-1"}),
            ("rea_inspect_binary", {"binaryPath": "/bin/ls"}),
            ("read_resource", {"Uri": "custom://resource"}),
            ("unknown_custom_tool", {"foo": "bar"}),
        ]

        conv_id = "test-post-tool-all-tools"

        for tool_name, tool_args in tools_to_test:
            with self.subTest(tool=tool_name):
                payload = {
                    "hookEvent": "PostToolUse",
                    "conversationId": conv_id,
                    "toolCall": {
                        "name": tool_name,
                        "args": tool_args,
                    },
                    "toolResponse": {"status": "success", "exitCode": 0},
                }
                buf = io.StringIO()
                with patch("sys.stdin", io.StringIO(json.dumps(payload))), patch("sys.stdout", buf):
                    completion_fence_hook.main()

                out_str = buf.getvalue().strip()
                out_json = json.loads(out_str)
                self.assertEqual(
                    out_json,
                    {},
                    f"PostToolUse for '{tool_name}' must emit exact {{}}, got: {out_str}",
                )

    def test_post_tool_use_payload_event_variants_emit_empty_dict(self):
        """
        Validates that all variations of PostToolUse event signaling
        (hookEvent, hook_event, event, toolResponse, toolOutput) emit exact JSON {}.
        """
        event_payload_variants = [
            {"hookEvent": "PostToolUse", "toolCall": {"name": "write_to_file", "args": {"TargetFile": "a.py"}}},
            {"hook_event": "PostToolUse", "toolCall": {"name": "write_to_file", "args": {"TargetFile": "b.py"}}},
            {"event": "PostToolUse", "toolCall": {"name": "write_to_file", "args": {"TargetFile": "c.py"}}},
            {"hookEvent": "posttooluse", "toolCall": {"name": "view_file", "args": {"AbsolutePath": "d.py"}}},
            {"toolCall": {"name": "view_file", "args": {}}, "toolResponse": "some output"},
            {"toolCall": {"name": "run_command", "args": {"CommandLine": "ls"}}, "toolOutput": "file1\nfile2"},
            {"toolCall": {"name": "run_command", "args": {"CommandLine": "ls"}}, "exitCode": 0},
        ]

        for idx, payload in enumerate(event_payload_variants):
            with self.subTest(variant=idx):
                buf = io.StringIO()
                with patch("sys.stdin", io.StringIO(json.dumps(payload))), patch("sys.stdout", buf):
                    completion_fence_hook.main()

                out_json = json.loads(buf.getvalue().strip())
                self.assertEqual(out_json, {}, f"Variant {idx} must emit {{}}, got {out_json}")

    def test_pre_tool_use_contrast_emits_allow_decision(self):
        """
        Contrasts PostToolUse with PreToolUse:
        PreToolUse for write_to_file MUST emit {"decision": "allow"}.
        """
        payload = {
            "hookEvent": "PreToolUse",
            "conversationId": "test-pre-tool-contrast",
            "toolCall": {
                "name": "write_to_file",
                "args": {"TargetFile": "src/app.py"},
            },
        }
        buf = io.StringIO()
        with patch("sys.stdin", io.StringIO(json.dumps(payload))), patch("sys.stdout", buf):
            completion_fence_hook.main()

        out_json = json.loads(buf.getvalue().strip())
        self.assertEqual(out_json.get("decision"), "allow")

    # --- Ephemeral Scratch Path Isolation Inside /tmp ---

    def test_is_ephemeral_scratch_path_cwd_in_tmp_rejects_relative_paths(self):
        """
        Validates that when the process current working directory is inside /tmp
        (e.g., CI runners, worktrees, or containerized environments), relative
        workspace paths (e.g. 'src/app.py') are NOT resolved against process cwd
        and are NOT falsely marked as scratch paths when cwd is None.
        """
        orig_cwd = os.getcwd()
        try:
            os.chdir("/tmp")

            relative_paths = [
                "src/app.py",
                "harness/cli.py",
                "components/Button.tsx",
                "lib/core.rs",
                "tests/test_hook.py",
                "./src/main.go",
                "index.js",
            ]
            for rel_path in relative_paths:
                with self.subTest(rel_path=rel_path):
                    self.assertFalse(
                        is_ephemeral_scratch_path(rel_path, cwd=None),
                        f"Relative path '{rel_path}' must NOT be classified as scratch when running inside /tmp with cwd=None",
                    )
        finally:
            os.chdir(orig_cwd)

    def test_is_ephemeral_scratch_path_cwd_in_tmp_accepts_absolute_temp_paths(self):
        """
        Validates that genuine absolute temp files remain classified as ephemeral scratch
        paths even when process cwd is inside /tmp.
        """
        orig_cwd = os.getcwd()
        try:
            os.chdir("/tmp")

            absolute_scratch_paths = [
                "/tmp/scratch.py",
                "/tmp/test_dir/script.sh",
                "/var/tmp/temp_runner.py",
                os.path.join(tempfile.gettempdir(), "test_scratch.py"),
                "/home/kuasha/.gemini/antigravity/brain/session-123/scratch/tool.py",
            ]
            for abs_path in absolute_scratch_paths:
                with self.subTest(abs_path=abs_path):
                    self.assertTrue(
                        is_ephemeral_scratch_path(abs_path, cwd=None),
                        f"Absolute temp path '{abs_path}' MUST be classified as scratch",
                    )
        finally:
            os.chdir(orig_cwd)

    def test_tmp_worktree_record_edit_arms_completion_fence(self):
        """
        Simulates editing a relative production file inside a worktree rooted in /tmp.
        Asserts that the completion fence is properly armed (code_dirty = True)
        and evaluate_stop blocks exit.
        """
        temp_worktree = tempfile.TemporaryDirectory()
        orig_cwd = os.getcwd()
        try:
            os.chdir(temp_worktree.name)
            conv_id = "test-tmp-worktree-fence"

            # 1. Edit relative production file without explicit cwd
            record_edit("src/service.py", conv_id=conv_id, state_dir=self.state_dir, cwd=None)

            # 2. State must be marked dirty
            state = load_state(conv_id=conv_id, state_dir=self.state_dir)
            self.assertTrue(
                state.get("code_dirty"),
                "Editing relative code file inside /tmp worktree MUST set code_dirty = True",
            )
            self.assertIn("src/service.py", state.get("last_modified_files", []))

            # 3. Stop evaluation must be blocked
            res = evaluate_stop(conv_id=conv_id, state_dir=self.state_dir, cwd=Path(temp_worktree.name))
            self.assertEqual(res.get("decision"), "continue")
            self.assertIn("src/service.py", res.get("reason", ""))
        finally:
            os.chdir(orig_cwd)
            temp_worktree.cleanup()

    # --- Sub-second Benchmark Invariant ---

    def test_hardening_subsecond_benchmark(self):
        """Validates that Milestone 2 features execute in strictly <1.0s."""
        start = time.perf_counter()
        conv_id = "test-m2-perf"

        for _ in range(30):
            # Scratch edit (fast no-op)
            record_edit("/tmp/scratch.py", conv_id=conv_id, state_dir=self.state_dir, cwd=self.harness_root)
            # Code edit (marks dirty)
            record_edit("harness/cli.py", conv_id=conv_id, state_dir=self.state_dir, cwd=self.harness_root)
            # Contract edit (marks dirty)
            record_edit("docs/specs/my_spec.md", conv_id=conv_id, state_dir=self.state_dir, cwd=self.harness_root)
            evaluate_stop(conv_id=conv_id, state_dir=self.state_dir, cwd=self.harness_root)
            # Clear dirty state
            check_command_verification("agyis test", exit_code=0, conv_id=conv_id, state_dir=self.state_dir, cwd=self.harness_root)

        duration = time.perf_counter() - start
        self.assertLess(
            duration,
            1.0,
            f"Expected 30 M2 evaluation cycles to execute in <1.0s, took {duration:.4f}s",
        )


class TestCleanroomHarmonizationM4(unittest.TestCase):
    """Hermetic unit tests validating REA cleanroom completion fence harmonization (Milestone 4)."""

    def setUp(self):
        self.temp_state_dir = tempfile.TemporaryDirectory()
        self.state_dir = Path(self.temp_state_dir.name)
        self.temp_workspace_dir = tempfile.TemporaryDirectory()
        self.workspace_dir = Path(self.temp_workspace_dir.name)

    def tearDown(self):
        self.temp_state_dir.cleanup()
        self.temp_workspace_dir.cleanup()

    def test_code_in_specs_triggers_code_dirty_def01(self):
        """Non-declarative code files (.py, .ts, .sh) inside docs/specs/** trigger code_dirty = True (DEF-01)."""
        conv_id = "test-code-in-specs"
        record_edit("docs/specs/helper.py", conv_id=conv_id, state_dir=self.state_dir, cwd=self.workspace_dir)

        state = load_state(conv_id=conv_id, state_dir=self.state_dir)
        self.assertTrue(state["code_dirty"], "Code files in docs/specs/ MUST trigger code_dirty")
        self.assertTrue(state["spec_dirty"], "Code files in docs/specs/ MUST trigger spec_dirty")

        res = evaluate_stop(conv_id=conv_id, state_dir=self.state_dir, cwd=self.workspace_dir)
        self.assertEqual(res.get("decision"), "continue")
        # Must require project test execution, not spec verification
        self.assertIn("Verification Required: Unverified code and cleanroom contract edits detected in: docs/specs/helper.py", res.get("reason", ""))

    def test_declarative_spec_files_set_only_spec_dirty(self):
        """Declarative spec extensions (.md, .json, .yaml, .proto) trigger only spec_dirty = True (code_dirty = False)."""
        conv_id = "test-decl-specs"
        for spec in ("docs/specs/api.proto", "docs/specs/types.schema", "docs/specs/config.yaml", ".agents/ledger/tasks.json"):
            record_edit(spec, conv_id=conv_id, state_dir=self.state_dir, cwd=self.workspace_dir)

        state = load_state(conv_id=conv_id, state_dir=self.state_dir)
        self.assertFalse(state["code_dirty"])
        self.assertTrue(state["spec_dirty"])

        res = evaluate_stop(conv_id=conv_id, state_dir=self.state_dir, cwd=self.workspace_dir)
        self.assertEqual(res.get("decision"), "continue")
        self.assertIn("Cleanroom Verification Required: Unverified cleanroom contract edits detected in:", res.get("reason", ""))
        self.assertIn("Execute 'rea verify-reconstruction' or 'agyis verify --spec' before stopping.", res.get("reason", ""))

    def test_mcp_post_tool_use_clearance_def03(self):
        """Successful verify_reconstruction MCP tool clears spec_dirty state (DEF-03)."""
        from harness.hooks.completion_fence_hook import handle_post_tool_use
        conv_id = "test-mcp-clear"
        record_edit("docs/specs/spec.md", conv_id=conv_id, state_dir=self.state_dir, cwd=self.workspace_dir)
        self.assertTrue(load_state(conv_id=conv_id, state_dir=self.state_dir)["spec_dirty"])

        # Call MCP verifier
        handle_post_tool_use(
            "call_mcp_tool",
            {"ToolName": "verify_reconstruction", "Arguments": {}},
            {"status": "ok", "evidence_verified": True},
            conv_id=conv_id,
            state_dir=self.state_dir,
        )

        state = load_state(conv_id=conv_id, state_dir=self.state_dir)
        self.assertFalse(state["spec_dirty"])
        self.assertEqual(evaluate_stop(conv_id=conv_id, state_dir=self.state_dir, cwd=self.workspace_dir)["decision"], "allow")

    def test_direct_mcp_post_tool_use_clearance_def03(self):
        """Direct evaluate_reconstruction_coverage tool call clears spec_dirty state."""
        from harness.hooks.completion_fence_hook import handle_post_tool_use
        conv_id = "test-direct-clear"
        record_edit("docs/specs/spec.md", conv_id=conv_id, state_dir=self.state_dir, cwd=self.workspace_dir)

        handle_post_tool_use(
            "evaluate_reconstruction_coverage",
            {},
            {"status": "ok", "coverage": 1.0},
            conv_id=conv_id,
            state_dir=self.state_dir,
        )

        state = load_state(conv_id=conv_id, state_dir=self.state_dir)
        self.assertFalse(state["spec_dirty"])

    def test_manifest_clearance_valid_def06(self):
        """Valid .agents/ledger/manifest.json clears spec_dirty and permits stop (DEF-06)."""
        ledger_dir = self.workspace_dir / ".agents" / "ledger"
        ledger_dir.mkdir(parents=True, exist_ok=True)
        manifest_data = {
            "status": "verified",
            "evidence_hash": "a" * 64,
            "target": "binary_target",
            "verified_at": "2026-10-15T20:00:00Z",
            "verifier": "rea-agents",
            "obligations": [
                {"id": "ob-1", "status": "satisfied", "proof": "ev-001"}
            ],
        }
        (ledger_dir / "manifest.json").write_text(json.dumps(manifest_data), encoding="utf-8")

        conv_id = "test-manifest-valid"
        record_edit("docs/specs/cleanroom.md", conv_id=conv_id, state_dir=self.state_dir, cwd=self.workspace_dir)

        # evaluate_stop detects verified manifest and allows exit
        res = evaluate_stop(conv_id=conv_id, state_dir=self.state_dir, cwd=self.workspace_dir)
        self.assertEqual(res["decision"], "allow")

    def test_manifest_clearance_invalid_fails(self):
        """Invalid manifest (unverified status or unsatisfied obligation) does not clear fence."""
        ledger_dir = self.workspace_dir / ".agents" / "ledger"
        ledger_dir.mkdir(parents=True, exist_ok=True)
        manifest_data = {
            "status": "in_progress",
            "evidence_hash": "a" * 64,
            "target": "binary_target",
            "verified_at": "2026-10-15T20:00:00Z",
            "verifier": "rea-agents",
            "obligations": [
                {"id": "ob-1", "status": "pending", "proof": ""}
            ],
        }
        (ledger_dir / "manifest.json").write_text(json.dumps(manifest_data), encoding="utf-8")

        conv_id = "test-manifest-invalid"
        record_edit("docs/specs/cleanroom.md", conv_id=conv_id, state_dir=self.state_dir, cwd=self.workspace_dir)

        res = evaluate_stop(conv_id=conv_id, state_dir=self.state_dir, cwd=self.workspace_dir)
        self.assertEqual(res["decision"], "continue")
        self.assertIn("Cleanroom Verification Required", res["reason"])

    def test_ephemeral_scratch_paths_exempt(self):
        """Scratch files in .rea/**, decompiled/**, and artifacts/rea/** are exempt from dirty state."""
        conv_id = "test-rea-scratch"
        scratch_files = [
            ".rea/analysis.txt",
            "decompiled/com/example/App.java",
            "artifacts/rea/strings.json",
            "/workspace/.rea/dump.bin",
        ]
        for f in scratch_files:
            record_edit(f, conv_id=conv_id, state_dir=self.state_dir, cwd=self.workspace_dir)

        state = load_state(conv_id=conv_id, state_dir=self.state_dir)
        self.assertFalse(state["code_dirty"])
        self.assertFalse(state["spec_dirty"])
        self.assertEqual(state["last_modified_files"], [])
        self.assertEqual(evaluate_stop(conv_id=conv_id, state_dir=self.state_dir, cwd=self.workspace_dir)["decision"], "allow")


if __name__ == "__main__":
    unittest.main()
