#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Arafat Zahan (@kuasha420)
# Corporate Stewardship & Infrastructure: Purrfect Software Limited (PSL)
# Governed by: ICARO-42/b Ordinance (Company-Supported Personal IP Framework)

"""
Unit and integration contract tests for harness/hooks/completion_fence_hook.py
Governing ADRs: ADR-014, ADR-015, ADR-022
"""

import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import unittest
from unittest.mock import patch

from harness.hooks import completion_fence_hook
from harness.hooks.completion_fence_hook import (
    check_command_verification,
    evaluate_stop,
    get_state_file,
    is_code_file,
    is_test_command,
    load_state,
    record_edit,
    record_verification,
    reset_state,
    save_state,
)


class TestCompletionFenceHook(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.state_dir = Path(self.temp_dir.name)
        self.orig_state_env = os.environ.get("PSL_HARNESS_STATE_DIR")
        os.environ["PSL_HARNESS_STATE_DIR"] = str(self.state_dir)

    def tearDown(self):
        if self.orig_state_env is not None:
            os.environ["PSL_HARNESS_STATE_DIR"] = self.orig_state_env
        else:
            os.environ.pop("PSL_HARNESS_STATE_DIR", None)
        self.temp_dir.cleanup()

    def test_is_code_file_exemptions(self):
        """Verifies documentation, assets, lockfiles, and git configs are exempt."""
        exempt_paths = [
            "README.md",
            "docs/architecture.md",
            "guide.markdown",
            "notes.txt",
            "spec.rst",
            "doc.adoc",
            "logo.png",
            "banner.jpg",
            "photo.jpeg",
            "icon.ico",
            "illustration.svg",
            "anim.gif",
            "preview.webp",
            ".gitignore",
            ".gitattributes",
            ".editorconfig",
            "package-lock.json",
            "uv.lock",
            "poetry.lock",
            "Cargo.lock",
            "yarn.lock",
            "pnpm-lock.yaml",
            "custom.lock",
        ]
        for path in exempt_paths:
            with self.subTest(path=path):
                self.assertFalse(
                    is_code_file(path),
                    f"Expected {path} to be exempt from code verification",
                )

    def test_is_code_file_code_detection(self):
        """Verifies code file extensions are correctly flagged as code."""
        code_paths = [
            "harness/cli.py",
            "types/index.ts",
            "components/App.tsx",
            "src/index.js",
            "src/component.jsx",
            "src/main.rs",
            "cmd/main.go",
            "native/lib.c",
            "native/lib.cpp",
            "native/header.h",
            "native/header.hpp",
            "src/Main.java",
            "src/App.kt",
            "scripts/deploy.sh",
            "scripts/build.bash",
            "styles/main.css",
            "styles/app.scss",
            "templates/page.html",
        ]
        for path in code_paths:
            with self.subTest(path=path):
                self.assertTrue(
                    is_code_file(path),
                    f"Expected {path} to be recognized as code",
                )

    def test_clean_state_evaluate_stop_allows(self):
        """An initial clean state must allow stopping immediately."""
        conv_id = "test-clean-conv"
        res = evaluate_stop(conv_id=conv_id, state_dir=self.state_dir)
        self.assertEqual(res.get("decision"), "allow")

    def test_exempt_file_edit_does_not_dirty_state(self):
        """Editing an exempt file (e.g. .md, .png) does not mark state dirty."""
        conv_id = "test-exempt-conv"
        record_edit("README.md", conv_id=conv_id, state_dir=self.state_dir)
        record_edit("assets/logo.png", conv_id=conv_id, state_dir=self.state_dir)

        state = load_state(conv_id=conv_id, state_dir=self.state_dir)
        self.assertFalse(state["code_dirty"])
        self.assertEqual(state["last_modified_files"], [])

        res = evaluate_stop(conv_id=conv_id, state_dir=self.state_dir)
        self.assertEqual(res.get("decision"), "allow")

    def test_code_edit_dirties_state_and_blocks_stop(self):
        """Editing code marks state dirty and stops are blocked up to 2 times."""
        conv_id = "test-dirty-conv"
        record_edit("harness/cli.py", conv_id=conv_id, state_dir=self.state_dir)

        state = load_state(conv_id=conv_id, state_dir=self.state_dir)
        self.assertTrue(state["code_dirty"])
        self.assertIn("harness/cli.py", state["last_modified_files"])
        self.assertEqual(state["block_count"], 0)

        # First stop evaluation: blocked
        res1 = evaluate_stop(conv_id=conv_id, state_dir=self.state_dir)
        self.assertEqual(res1.get("decision"), "continue")
        self.assertIn("Verification Required", res1.get("reason", ""))
        self.assertIn("harness/cli.py", res1.get("reason", ""))

        state1 = load_state(conv_id=conv_id, state_dir=self.state_dir)
        self.assertEqual(state1["block_count"], 1)

        # Second stop evaluation: blocked
        res2 = evaluate_stop(conv_id=conv_id, state_dir=self.state_dir)
        self.assertEqual(res2.get("decision"), "continue")
        self.assertIn("Verification Required", res2.get("reason", ""))

        state2 = load_state(conv_id=conv_id, state_dir=self.state_dir)
        self.assertEqual(state2["block_count"], 2)

    def test_anti_deadlock_valve_trips_after_two_blocks(self):
        """After 2 blocked stops, the 3rd attempt must trip the anti-deadlock valve and allow exit."""
        conv_id = "test-anti-deadlock"
        record_edit("harness/hooks/completion_fence_hook.py", conv_id=conv_id, state_dir=self.state_dir)

        # Block 1
        res1 = evaluate_stop(conv_id=conv_id, state_dir=self.state_dir)
        self.assertEqual(res1.get("decision"), "continue")

        # Block 2
        res2 = evaluate_stop(conv_id=conv_id, state_dir=self.state_dir)
        self.assertEqual(res2.get("decision"), "continue")

        # Block 3: Anti-deadlock valve trips!
        res3 = evaluate_stop(conv_id=conv_id, state_dir=self.state_dir)
        self.assertEqual(res3.get("decision"), "allow")
        self.assertIn("warning", res3)
        self.assertIn("Anti-deadlock valve tripped after 2 verification blocks", res3["warning"])

    def test_record_edit_rearms_fence_by_resetting_block_count(self):
        """A new code edit resets block_count to 0 so the fence re-arms."""
        conv_id = "test-rearm"
        record_edit("src/a.py", conv_id=conv_id, state_dir=self.state_dir)

        # Block once
        res1 = evaluate_stop(conv_id=conv_id, state_dir=self.state_dir)
        self.assertEqual(res1.get("decision"), "continue")
        state1 = load_state(conv_id=conv_id, state_dir=self.state_dir)
        self.assertEqual(state1["block_count"], 1)

        # New edit must reset block_count to 0
        record_edit("src/b.py", conv_id=conv_id, state_dir=self.state_dir)
        state2 = load_state(conv_id=conv_id, state_dir=self.state_dir)
        self.assertEqual(state2["block_count"], 0)
        self.assertIn("src/b.py", state2["last_modified_files"])

    def test_verification_success_clears_dirty_and_resets_block_count(self):
        """Successful verification clears code_dirty, resets block_count, and sets timestamp."""
        conv_id = "test-verify-success"
        record_edit("harness/cli.py", conv_id=conv_id, state_dir=self.state_dir)

        # Trip 1 block
        evaluate_stop(conv_id=conv_id, state_dir=self.state_dir)
        state_blocked = load_state(conv_id=conv_id, state_dir=self.state_dir)
        self.assertEqual(state_blocked["block_count"], 1)

        # Record successful test run
        record_verification(success=True, conv_id=conv_id, state_dir=self.state_dir)

        state_cleared = load_state(conv_id=conv_id, state_dir=self.state_dir)
        self.assertFalse(state_cleared["code_dirty"])
        self.assertEqual(state_cleared["last_modified_files"], [])
        self.assertEqual(state_cleared["block_count"], 0)
        self.assertIsNotNone(state_cleared["last_verified_at"])

        # Stop should now be allowed
        res = evaluate_stop(conv_id=conv_id, state_dir=self.state_dir)
        self.assertEqual(res.get("decision"), "allow")

    def test_verification_failure_preserves_dirty(self):
        """Failed verification keeps code_dirty = True and does not clear block_count."""
        conv_id = "test-verify-fail"
        record_edit("harness/cli.py", conv_id=conv_id, state_dir=self.state_dir)

        record_verification(success=False, conv_id=conv_id, state_dir=self.state_dir)

        state = load_state(conv_id=conv_id, state_dir=self.state_dir)
        self.assertTrue(state["code_dirty"])
        self.assertIn("harness/cli.py", state["last_modified_files"])

        # Stop must remain blocked
        res = evaluate_stop(conv_id=conv_id, state_dir=self.state_dir)
        self.assertEqual(res.get("decision"), "continue")

    def test_reset_state(self):
        """reset_state returns state to initial clean baseline."""
        conv_id = "test-reset"
        record_edit("harness/cli.py", conv_id=conv_id, state_dir=self.state_dir)
        reset_state(conv_id=conv_id, state_dir=self.state_dir)

        state = load_state(conv_id=conv_id, state_dir=self.state_dir)
        self.assertFalse(state["code_dirty"])
        self.assertEqual(state["last_modified_files"], [])
        self.assertEqual(state["block_count"], 0)
        self.assertIsNone(state["last_verified_at"])

    def test_conversation_isolation(self):
        """Edits in conversation A do not affect conversation B."""
        record_edit("harness/cli.py", conv_id="conv-a", state_dir=self.state_dir)

        res_b = evaluate_stop(conv_id="conv-b", state_dir=self.state_dir)
        self.assertEqual(res_b.get("decision"), "allow")

        res_a = evaluate_stop(conv_id="conv-a", state_dir=self.state_dir)
        self.assertEqual(res_a.get("decision"), "continue")

    def test_corrupted_state_recovers_gracefully(self):
        """Corrupted JSON in state file does not raise an exception."""
        conv_id = "test-corrupted"
        state_file = get_state_file(conv_id, self.state_dir)
        state_file.parent.mkdir(parents=True, exist_ok=True)
        state_file.write_text("{corrupt-json", encoding="utf-8")

        state = load_state(conv_id=conv_id, state_dir=self.state_dir)
        self.assertFalse(state["code_dirty"])
        self.assertEqual(state["block_count"], 0)

        res = evaluate_stop(conv_id=conv_id, state_dir=self.state_dir)
        self.assertEqual(res.get("decision"), "allow")

    def test_pre_tool_use_protojson_contract(self):
        """Defect 3 Contract Test: passes real Antigravity PreToolUse payload, marks state dirty, emits allow."""
        payload = {
            "conversationId": "pre-tool-conv-123",
            "toolCall": {
                "name": "write_to_file",
                "args": {
                    "TargetFile": "src/app.py",
                },
            },
        }
        buf = io.StringIO()
        with patch("sys.stdin", io.StringIO(json.dumps(payload))), patch("sys.stdout", buf):
            completion_fence_hook.main()

        out = json.loads(buf.getvalue().strip())
        self.assertEqual(out.get("decision"), "allow")

        # Verify state is marked dirty
        state = load_state(conv_id="pre-tool-conv-123", state_dir=self.state_dir)
        self.assertTrue(state.get("code_dirty"))
        self.assertIn("src/app.py", state.get("last_modified_files", []))

        # Stop is now blocked
        res_stop = evaluate_stop(conv_id="pre-tool-conv-123", state_dir=self.state_dir)
        self.assertEqual(res_stop.get("decision"), "continue")
        self.assertIn("src/app.py", res_stop.get("reason", ""))

    def test_null_conversation_id_handling(self):
        """Defect 6: Null or missing conversationId falls back cleanly to 'default'."""
        payload = {
            "conversationId": None,
            "toolCall": {
                "name": "replace_file_content",
                "args": {
                    "TargetFile": "src/index.ts",
                },
            },
        }
        buf = io.StringIO()
        with patch("sys.stdin", io.StringIO(json.dumps(payload))), patch("sys.stdout", buf):
            completion_fence_hook.main()

        out = json.loads(buf.getvalue().strip())
        self.assertEqual(out.get("decision"), "allow")

        state = load_state(conv_id="default", state_dir=self.state_dir)
        self.assertTrue(state.get("code_dirty"))
        self.assertIn("src/index.ts", state.get("last_modified_files", []))

    def test_cli_hook_stdin_stdout_contract(self):
        """Validates the CLI hook entrypoint executes correctly via stdin/stdout."""
        # 1. Clean stop evaluates to allow
        buf1 = io.StringIO()
        with patch("sys.stdin", io.StringIO(json.dumps({"conversationId": "cli-contract-conv"}))), patch("sys.stdout", buf1):
            completion_fence_hook.main()
        out1 = json.loads(buf1.getvalue().strip())
        self.assertEqual(out1.get("decision"), "allow")

        # 2. Record edit via action
        buf2 = io.StringIO()
        with patch("sys.stdin", io.StringIO(json.dumps({
            "conversationId": "cli-contract-conv",
            "action": "record_edit",
            "file_path": "src/main.py",
        }))), patch("sys.stdout", buf2):
            completion_fence_hook.main()
        out2 = json.loads(buf2.getvalue().strip())
        self.assertEqual(out2.get("status"), "ok")

        # 3. Stop now blocked
        buf3 = io.StringIO()
        with patch("sys.stdin", io.StringIO(json.dumps({"conversationId": "cli-contract-conv"}))), patch("sys.stdout", buf3):
            completion_fence_hook.main()
        out3 = json.loads(buf3.getvalue().strip())
        self.assertEqual(out3.get("decision"), "continue")
        self.assertIn("Verification Required", out3.get("reason", ""))

    def test_subsecond_execution(self):
        """Enforces ADR-015 requirement that hook execution latency is sub-second (<1.0s)."""
        start = time.perf_counter()
        conv_id = "test-perf"
        for _ in range(20):
            record_edit("harness/cli.py", conv_id=conv_id, state_dir=self.state_dir)
            evaluate_stop(conv_id=conv_id, state_dir=self.state_dir)
            record_verification(success=True, conv_id=conv_id, state_dir=self.state_dir)

        duration = time.perf_counter() - start
        self.assertLess(
            duration,
            1.0,
            f"Expected 20 state cycles to complete in <1.0s, took {duration:.4f}s",
        )

    def test_universal_test_runner_detection(self):
        """Verifies universal test runner commands across Python, Node, Rust, Go, C/C++, and Agyis/PSL harnesses are recognized."""
        recognized_cmds = [
            "pytest",
            "pytest tests/",
            "python3 -m unittest",
            "python -m unittest discover",
            "python3 -m pytest tests/",
            "python3 -m harness.cli test",
            "agyis test",
            "./agyis test",
            "agyis test -v",
            "agyis test --verbose",
            "sudo agyis test",
            "time agyis test",
            "nohup agyis test",
            "psl test",
            "./psl test",
            "psl test -v",
            "psl test --verbose",
            "sudo psl test",
            "time psl test",
            "nohup psl test",
            "pnpm test",
            "pnpm run test",
            "npm test",
            "npm run test",
            "yarn test",
            "bun test",
            "vitest run",
            "jest",
            "turbo run test",
            "cargo test",
            "cargo test --lib",
            "go test ./...",
            "go test -v",
            "ctest",
        ]
        for cmd in recognized_cmds:
            with self.subTest(cmd=cmd):
                self.assertTrue(is_test_command(cmd), f"Expected '{cmd}' to be recognized as test runner")

        unrecognized_cmds = [
            "ls -la",
            "echo 'running tests'",
            "cat test.py",
            "git commit -m 'add test'",
            "python script.py",
            "node index.js",
            "agyis status",
            "agyis skills",
            "psl status",
            "psl skills",
            "agyis testing_false",
        ]
        for cmd in unrecognized_cmds:
            with self.subTest(cmd=cmd):
                self.assertFalse(is_test_command(cmd), f"Expected '{cmd}' NOT to be recognized as test runner")

    def test_command_verification_auto_clears_code_dirty_on_exit_zero(self):
        """Exit code 0 on universal test runners auto-clears code_dirty and allows stopping."""
        conv_id = "test-cmd-verify-clean"
        for runner_cmd in (
            "pytest",
            "pnpm test",
            "cargo test",
            "go test",
            "agyis test",
            "./agyis test",
            "psl test",
            "./psl test",
        ):
            with self.subTest(runner_cmd=runner_cmd):
                # Dirty state with edit
                record_edit("src/core.py", conv_id=conv_id, state_dir=self.state_dir)
                state_before = load_state(conv_id=conv_id, state_dir=self.state_dir)
                self.assertTrue(state_before["code_dirty"])

                # Run test runner with exit code 0
                matched = check_command_verification(runner_cmd, exit_code=0, conv_id=conv_id, state_dir=self.state_dir)
                self.assertTrue(matched)

                # State must now be clean
                state_after = load_state(conv_id=conv_id, state_dir=self.state_dir)
                self.assertFalse(state_after["code_dirty"])
                self.assertEqual(state_after["last_modified_files"], [])
                self.assertIsNotNone(state_after["last_verified_at"])

                # Stop evaluation allows
                res = evaluate_stop(conv_id=conv_id, state_dir=self.state_dir)
                self.assertEqual(res["decision"], "allow")

    def test_command_verification_preserves_dirty_on_nonzero_exit(self):
        """Exit code != 0 on test runners leaves code_dirty True and blocks stopping."""
        conv_id = "test-cmd-verify-fail"
        for runner_cmd, exit_code in (("cargo test", 101), ("agyis test", 1), ("psl test", 2)):
            with self.subTest(runner_cmd=runner_cmd, exit_code=exit_code):
                record_edit("src/core.py", conv_id=conv_id, state_dir=self.state_dir)

                matched = check_command_verification(runner_cmd, exit_code=exit_code, conv_id=conv_id, state_dir=self.state_dir)
                self.assertTrue(matched)

                state = load_state(conv_id=conv_id, state_dir=self.state_dir)
                self.assertTrue(state["code_dirty"])
                self.assertIn("src/core.py", state["last_modified_files"])

                res = evaluate_stop(conv_id=conv_id, state_dir=self.state_dir)
                self.assertEqual(res["decision"], "continue")

    def test_non_test_command_does_not_clear_dirty(self):
        """Non-test command returns False and does not clear code_dirty."""
        conv_id = "test-cmd-non-test"
        record_edit("src/core.py", conv_id=conv_id, state_dir=self.state_dir)

        matched = check_command_verification("git status", exit_code=0, conv_id=conv_id, state_dir=self.state_dir)
        self.assertFalse(matched)

        state = load_state(conv_id=conv_id, state_dir=self.state_dir)
        self.assertTrue(state["code_dirty"])

    def test_cli_hook_command_verification_payloads(self):
        """Contract test: main() processes command verification action and toolCall run_command."""
        conv_id = "test-cli-cmd-verify"

        # 1. Edit code
        record_edit("src/feature.ts", conv_id=conv_id, state_dir=self.state_dir)

        # 2. Process check_command_verification via action
        payload1 = {
            "conversationId": conv_id,
            "action": "check_command_verification",
            "command": "pnpm test",
            "exit_code": 0,
        }
        buf1 = io.StringIO()
        with patch("sys.stdin", io.StringIO(json.dumps(payload1))), patch("sys.stdout", buf1):
            completion_fence_hook.main()

        out1 = json.loads(buf1.getvalue().strip())
        self.assertEqual(out1["status"], "ok")
        self.assertTrue(out1["matched"])
        self.assertFalse(out1["state"]["code_dirty"])

        # 3. Edit code again
        record_edit("src/feature.ts", conv_id=conv_id, state_dir=self.state_dir)

        # PreToolUse event (no exitCode) should NOT mark command as verified
        payload_pre = {
            "conversationId": conv_id,
            "toolCall": {
                "name": "run_command",
                "args": {"CommandLine": "pytest tests/"},
            },
        }
        buf_pre = io.StringIO()
        with patch("sys.stdin", io.StringIO(json.dumps(payload_pre))), patch("sys.stdout", buf_pre):
            completion_fence_hook.main()

        out_pre = json.loads(buf_pre.getvalue().strip())
        self.assertEqual(out_pre, {})
        state_pre = load_state(conv_id=conv_id, state_dir=self.state_dir)
        self.assertTrue(state_pre["code_dirty"])

        # 4. Process toolCall run_command with exitCode 0
        payload2 = {
            "conversationId": conv_id,
            "toolCall": {
                "name": "run_command",
                "args": {"CommandLine": "pytest tests/"},
            },
            "exitCode": 0,
        }
        buf2 = io.StringIO()
        with patch("sys.stdin", io.StringIO(json.dumps(payload2))), patch("sys.stdout", buf2):
            completion_fence_hook.main()

        out2 = json.loads(buf2.getvalue().strip())
        self.assertEqual(out2, {})
        state2 = load_state(conv_id=conv_id, state_dir=self.state_dir)
        self.assertFalse(state2["code_dirty"])

    def test_completion_fence_exemptions(self):
        """
        Asserts modifying non-code extensions (.md, .png, .jpg, .svg, uv.lock,
        package-lock.json, .pnpm-lock.yaml) leaves code_dirty = False and does NOT trip the fence.
        """
        conv_id = "test-exemptions-clean"
        exempt_paths = [
            "docs/README.md",
            "assets/architecture.png",
            "images/screenshot.jpg",
            "ui/icons/logo.svg",
            "uv.lock",
            "package-lock.json",
            ".pnpm-lock.yaml",
            "subfolder/pnpm-lock.yaml",
        ]

        for p in exempt_paths:
            self.assertFalse(completion_fence_hook.is_code_file(p), f"Expected {p} to be exempt from code verification")
            state = record_edit(p, conv_id=conv_id, state_dir=self.state_dir)
            self.assertFalse(state["code_dirty"], f"Editing {p} should not mark code_dirty = True")
            self.assertEqual(state["last_modified_files"], [], f"Editing {p} should not be tracked in last_modified_files")

        # Evaluate pre-tool-use via main() with write_to_file for an exempt file
        payload = {
            "conversationId": conv_id,
            "toolCall": {
                "name": "write_to_file",
                "args": {"TargetFile": "/workspace/docs/guide.md"},
            },
        }
        buf = io.StringIO()
        with patch("sys.stdin", io.StringIO(json.dumps(payload))), patch("sys.stdout", buf):
            completion_fence_hook.main()
        res = json.loads(buf.getvalue().strip())
        self.assertEqual(res.get("decision"), "allow")
        state = load_state(conv_id=conv_id, state_dir=self.state_dir)
        self.assertFalse(state["code_dirty"])

        # Stop decision must be allow
        stop_res = evaluate_stop(conv_id=conv_id, state_dir=self.state_dir)
        self.assertEqual(stop_res.get("decision"), "allow")
        self.assertNotIn("reason", stop_res)


class TestCompletionFenceDualRunners(unittest.TestCase):
    """Hermetic contract test suite validating dual runner triggers ('agyis test' and 'psl test')."""

    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.state_dir = Path(self.temp_dir.name)
        self.orig_env = os.environ.get("PSL_HARNESS_STATE_DIR")
        self.orig_agyis_env = os.environ.get("AGYIS_HARNESS_STATE_DIR")
        os.environ["PSL_HARNESS_STATE_DIR"] = str(self.state_dir)
        os.environ["AGYIS_HARNESS_STATE_DIR"] = str(self.state_dir)

    def tearDown(self):
        if self.orig_env is not None:
            os.environ["PSL_HARNESS_STATE_DIR"] = self.orig_env
        else:
            os.environ.pop("PSL_HARNESS_STATE_DIR", None)
        if self.orig_agyis_env is not None:
            os.environ["AGYIS_HARNESS_STATE_DIR"] = self.orig_agyis_env
        else:
            os.environ.pop("AGYIS_HARNESS_STATE_DIR", None)
        self.temp_dir.cleanup()

    def test_agyis_test_runner_clears_fence_on_success(self):
        """Dirty code edit followed by successful 'agyis test' clears fence and permits exit."""
        conv_id = "conv-agyis-clean"
        record_edit("harness/cli.py", conv_id=conv_id, state_dir=self.state_dir)
        self.assertTrue(load_state(conv_id=conv_id, state_dir=self.state_dir)["code_dirty"])

        matched = check_command_verification("agyis test", exit_code=0, conv_id=conv_id, state_dir=self.state_dir)
        self.assertTrue(matched)
        state = load_state(conv_id=conv_id, state_dir=self.state_dir)
        self.assertFalse(state["code_dirty"])
        self.assertEqual(evaluate_stop(conv_id=conv_id, state_dir=self.state_dir)["decision"], "allow")

    def test_psl_test_runner_clears_fence_on_success(self):
        """Dirty code edit followed by successful 'psl test' clears fence and permits exit."""
        conv_id = "conv-psl-clean"
        record_edit("harness/delivery/workspace.py", conv_id=conv_id, state_dir=self.state_dir)
        self.assertTrue(load_state(conv_id=conv_id, state_dir=self.state_dir)["code_dirty"])

        matched = check_command_verification("psl test", exit_code=0, conv_id=conv_id, state_dir=self.state_dir)
        self.assertTrue(matched)
        state = load_state(conv_id=conv_id, state_dir=self.state_dir)
        self.assertFalse(state["code_dirty"])
        self.assertEqual(evaluate_stop(conv_id=conv_id, state_dir=self.state_dir)["decision"], "allow")

    def test_agyis_and_psl_failure_blocks_stop(self):
        """Non-zero exit on 'agyis test' and 'psl test' retains dirty state and blocks stop."""
        conv_id = "conv-fail-block"
        record_edit("harness/commands/test.py", conv_id=conv_id, state_dir=self.state_dir)

        # agyis test exit code 1
        m1 = check_command_verification("agyis test", exit_code=1, conv_id=conv_id, state_dir=self.state_dir)
        self.assertTrue(m1)
        self.assertTrue(load_state(conv_id=conv_id, state_dir=self.state_dir)["code_dirty"])
        self.assertEqual(evaluate_stop(conv_id=conv_id, state_dir=self.state_dir)["decision"], "continue")

        # psl test exit code 2
        m2 = check_command_verification("psl test", exit_code=2, conv_id=conv_id, state_dir=self.state_dir)
        self.assertTrue(m2)
        self.assertTrue(load_state(conv_id=conv_id, state_dir=self.state_dir)["code_dirty"])
        self.assertEqual(evaluate_stop(conv_id=conv_id, state_dir=self.state_dir)["decision"], "continue")


class TestPhase1CompletionFenceModernization(unittest.TestCase):
    """
    Acceptance test suite for Epic #51 Phase 1 Completion Fence Modernization:
    - Issue #79: Async Background Task Ledger Interception
    - Issue #80: Turn-Scoped Mutation Sensitivity
    - Issue #81: Dynamic Project Discovery & Polyglot Regex Union
    """

    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.state_dir = Path(self.temp_dir.name)
        self.orig_state_env = os.environ.get("PSL_HARNESS_STATE_DIR")
        os.environ["PSL_HARNESS_STATE_DIR"] = str(self.state_dir)
        self.workspace_dir = tempfile.TemporaryDirectory()
        self.cwd = Path(self.workspace_dir.name)

    def tearDown(self):
        if self.orig_state_env is not None:
            os.environ["PSL_HARNESS_STATE_DIR"] = self.orig_state_env
        else:
            os.environ.pop("PSL_HARNESS_STATE_DIR", None)
        self.temp_dir.cleanup()
        self.workspace_dir.cleanup()

    # --- Category A: Async Background Test Completion Clearing code_dirty (Issue #79) ---

    def test_background_task_exit_zero_clears_code_dirty_via_ledger(self):
        """
        Issue #79: When a long-running test command is backgrounded into an async task,
        its eventual completion with exit code 0 automatically clears code_dirty.
        """
        conv_id = "test-async-task-exit-zero"
        # 1. Edit code file -> marks code_dirty = True
        record_edit("src/service.py", conv_id=conv_id, state_dir=self.state_dir, cwd=self.cwd)
        state_before = load_state(conv_id=conv_id, state_dir=self.state_dir)
        self.assertTrue(state_before["code_dirty"])

        # 2. Simulate launch of background task (PostToolUse with background notification)
        bg_launch_payload = {
            "conversationId": conv_id,
            "hookEvent": "PostToolUse",
            "toolCall": {
                "name": "run_command",
                "args": {"CommandLine": "python3 -m unittest discover -s tests", "Cwd": str(self.cwd)},
            },
            "toolResponse": "Tool is running as a background task with task id: conv-123/task-99\nTask logs are available at: ...",
        }
        buf_launch = io.StringIO()
        with patch("sys.stdin", io.StringIO(json.dumps(bg_launch_payload))), patch("sys.stdout", buf_launch):
            completion_fence_hook.main()

        # State remains dirty while task is running
        state_running = load_state(conv_id=conv_id, state_dir=self.state_dir)
        self.assertTrue(state_running["code_dirty"])
        self.assertIn("conv-123/task-99", state_running["pending_background_tests"])

        # 3. Simulate task completion notification (via action: task_completed / ledger hook)
        bg_complete_payload = {
            "conversationId": conv_id,
            "action": "task_completed",
            "task_id": "conv-123/task-99",
            "command": "python3 -m unittest discover -s tests",
            "exit_code": 0,
            "cwd": str(self.cwd),
        }
        buf_complete = io.StringIO()
        with patch("sys.stdin", io.StringIO(json.dumps(bg_complete_payload))), patch("sys.stdout", buf_complete):
            completion_fence_hook.main()

        out_complete = json.loads(buf_complete.getvalue().strip())
        self.assertEqual(out_complete.get("status"), "ok")
        self.assertTrue(out_complete.get("matched"))

        # State must now be clean
        state_after = load_state(conv_id=conv_id, state_dir=self.state_dir)
        self.assertFalse(state_after["code_dirty"])
        self.assertEqual(state_after["last_modified_files"], [])
        self.assertIsNotNone(state_after["last_verified_at"])

        # Stop evaluation must now be allowed
        res_stop = evaluate_stop(conv_id=conv_id, state_dir=self.state_dir, cwd=self.cwd)
        self.assertEqual(res_stop["decision"], "allow")

    def test_background_system_message_exit_zero_clears_code_dirty(self):
        """
        Issue #79: Ingesting Antigravity <SYSTEM_MESSAGE> task finished notification
        with exit code 0 clears code_dirty upon reactive wakeup.
        """
        conv_id = "test-async-sysmsg-exit-zero"
        record_edit("src/handler.go", conv_id=conv_id, state_dir=self.state_dir, cwd=self.cwd)
        self.assertTrue(load_state(conv_id=conv_id, state_dir=self.state_dir)["code_dirty"])

        sysmsg_payload = {
            "conversationId": conv_id,
            "action": "check_command_verification",
            "command": "go test ./...",
            "content": "Task id \"task-42\" finished with result:\n\nThe command exited with code 0.\nOutput:\nPASS",
            "cwd": str(self.cwd),
        }
        buf = io.StringIO()
        with patch("sys.stdin", io.StringIO(json.dumps(sysmsg_payload))), patch("sys.stdout", buf):
            completion_fence_hook.main()

        state = load_state(conv_id=conv_id, state_dir=self.state_dir)
        self.assertFalse(state["code_dirty"])
        self.assertEqual(evaluate_stop(conv_id=conv_id, state_dir=self.state_dir, cwd=self.cwd)["decision"], "allow")

    def test_background_task_ledger_sync_clears_via_messages_dir(self):
        """
        Issue #79: sync_background_tasks scanning .system_generated/messages/
        automatically discovers exit 0 message and clears code_dirty.
        """
        conv_id = "test-sync-messages-dir"
        brain_dir = Path(self.temp_dir.name) / "brain"
        messages_dir = brain_dir / ".system_generated" / "messages"
        messages_dir.mkdir(parents=True, exist_ok=True)

        record_edit("src/compute.py", conv_id=conv_id, state_dir=self.state_dir, cwd=self.cwd)
        state = load_state(conv_id=conv_id, state_dir=self.state_dir)
        self.assertTrue(state["code_dirty"])
        # Explicitly pin last_dirtied_at to decouple test from system wall-clock time
        state["last_dirtied_at"] = "2026-10-21T10:00:00Z"
        save_state(state, conv_id=conv_id, state_dir=self.state_dir)

        # Create mock Antigravity message JSON (timestamp newer than last_dirtied_at)
        msg_payload = {
            "id": "msg-001",
            "recipient": conv_id,
            "sender": f"{conv_id}/task-500",
            "priority": "MESSAGE_PRIORITY_HIGH",
            "timestamp": "2026-10-21T10:05:00Z",
            "content": "Task id \"task-500\" finished with result:\n\nThe command exited with code 0.\nOutput:\nRan 10 tests in 1.2s\nOK",
            "sourceMetadata": {
                "tool": {
                    "conversationId": conv_id,
                    "stepIndex": 50,
                    "toolCall": {
                        "name": "run_command",
                        "argumentsJson": json.dumps({"CommandLine": "python3 -m unittest discover", "Cwd": str(self.cwd)}),
                    },
                }
            },
        }
        (messages_dir / "msg-001.json").write_text(json.dumps(msg_payload), encoding="utf-8")

        # evaluate_stop should scan messages_dir and clear dirty state
        res = evaluate_stop(conv_id=conv_id, state_dir=self.state_dir, cwd=self.cwd, brain_dir=brain_dir)
        self.assertEqual(res["decision"], "allow")
        self.assertFalse(load_state(conv_id=conv_id, state_dir=self.state_dir)["code_dirty"])

    def test_background_task_ledger_sync_ignores_stale_message_predating_edit(self):
        """
        Issue #79: sync_background_tasks ignores message files whose timestamp
        predates last_dirtied_at, preserving code_dirty = True.
        """
        conv_id = "test-sync-messages-stale"
        brain_dir = Path(self.temp_dir.name) / "brain"
        messages_dir = brain_dir / ".system_generated" / "messages"
        messages_dir.mkdir(parents=True, exist_ok=True)

        record_edit("src/compute.py", conv_id=conv_id, state_dir=self.state_dir, cwd=self.cwd)
        state = load_state(conv_id=conv_id, state_dir=self.state_dir)
        self.assertTrue(state["code_dirty"])
        state["last_dirtied_at"] = "2026-10-21T10:10:00Z"
        save_state(state, conv_id=conv_id, state_dir=self.state_dir)

        # Create mock message with timestamp older than last_dirtied_at
        msg_payload = {
            "id": "msg-stale-001",
            "recipient": conv_id,
            "sender": f"{conv_id}/task-501",
            "priority": "MESSAGE_PRIORITY_HIGH",
            "timestamp": "2026-10-21T10:05:00Z",
            "content": "Task id \"task-501\" finished with result:\n\nThe command exited with code 0.\nOutput:\nRan 10 tests in 1.2s\nOK",
            "sourceMetadata": {
                "tool": {
                    "conversationId": conv_id,
                    "stepIndex": 45,
                    "toolCall": {
                        "name": "run_command",
                        "argumentsJson": json.dumps({"CommandLine": "python3 -m unittest discover", "Cwd": str(self.cwd)}),
                    },
                }
            },
        }
        (messages_dir / "msg-stale-001.json").write_text(json.dumps(msg_payload), encoding="utf-8")

        # evaluate_stop should ignore stale message and keep code_dirty = True
        res = evaluate_stop(conv_id=conv_id, state_dir=self.state_dir, cwd=self.cwd, brain_dir=brain_dir)
        self.assertEqual(res["decision"], "continue")
        self.assertTrue(load_state(conv_id=conv_id, state_dir=self.state_dir)["code_dirty"])

    # --- Category B: Async Background Test Failure Retaining code_dirty (Issue #79) ---

    def test_background_task_exit_nonzero_preserves_code_dirty(self):
        """
        Issue #79: When an async background test exits with non-zero code,
        code_dirty MUST remain True and the stop gate continues to block.
        """
        conv_id = "test-async-task-fail"
        record_edit("src/parser.rs", conv_id=conv_id, state_dir=self.state_dir, cwd=self.cwd)

        bg_complete_payload = {
            "conversationId": conv_id,
            "action": "task_completed",
            "task_id": "conv-123/task-100",
            "command": "cargo test",
            "exit_code": 101,
            "cwd": str(self.cwd),
        }
        buf = io.StringIO()
        with patch("sys.stdin", io.StringIO(json.dumps(bg_complete_payload))), patch("sys.stdout", buf):
            completion_fence_hook.main()

        state = load_state(conv_id=conv_id, state_dir=self.state_dir)
        self.assertTrue(state["code_dirty"])
        self.assertIn("src/parser.rs", state["last_modified_files"])

        # Stop remains blocked
        res = evaluate_stop(conv_id=conv_id, state_dir=self.state_dir, cwd=self.cwd)
        self.assertEqual(res["decision"], "continue")

    def test_background_non_test_command_does_not_clear_code_dirty(self):
        """
        Issue #79: Background task completion for a non-test command (e.g. sleep 10)
        with exit code 0 does NOT clear code_dirty.
        """
        conv_id = "test-async-non-test"
        record_edit("src/main.py", conv_id=conv_id, state_dir=self.state_dir, cwd=self.cwd)

        bg_payload = {
            "conversationId": conv_id,
            "action": "task_completed",
            "task_id": "conv-123/task-101",
            "command": "sleep 10",
            "exit_code": 0,
            "cwd": str(self.cwd),
        }
        buf = io.StringIO()
        with patch("sys.stdin", io.StringIO(json.dumps(bg_payload))), patch("sys.stdout", buf):
            completion_fence_hook.main()

        state = load_state(conv_id=conv_id, state_dir=self.state_dir)
        self.assertTrue(state["code_dirty"])

    def test_background_in_progress_blocks_with_tailored_message(self):
        """
        Issue #79: When code is dirty and a background test task is in progress,
        evaluate_stop provides tailored guidance to await reactive wakeup.
        """
        conv_id = "test-bg-in-progress"
        record_edit("src/core.py", conv_id=conv_id, state_dir=self.state_dir, cwd=self.cwd)

        # Register pending background test
        completion_fence_hook.check_background_task_detachment(
            "run_command",
            {"CommandLine": "pytest tests/", "Cwd": str(self.cwd)},
            "Tool is running as a background task with task id: conv/task-77",
            conv_id=conv_id,
            state_dir=self.state_dir,
            cwd=self.cwd,
        )

        res = evaluate_stop(conv_id=conv_id, state_dir=self.state_dir, cwd=self.cwd)
        self.assertEqual(res["decision"], "continue")
        self.assertIn("Background Test In Progress", res["reason"])
        self.assertIn("task-77", res["reason"])

    # --- Category C: Turn-Scoped Mutation Sensitivity: Read-Only / Conversational Turns (Issue #80) ---

    def test_read_only_turn_allows_stop_without_verification_block(self):
        """
        Issue #80: Purely conversational turns or turns executing only read-only
        tools (view_file, grep_search, list_dir, find_by_name) do NOT trigger
        the completion fence stop block.
        """
        conv_id = "test-turn-read-only"
        turn_id = "turn-001"

        read_only_calls = [
            ("view_file", {"AbsolutePath": "/workspace/src/app.py"}),
            ("grep_search", {"Query": "class App", "SearchPath": "/workspace"}),
            ("list_dir", {"DirectoryPath": "/workspace/src"}),
            ("find_by_name", {"Pattern": "*.py", "SearchDirectory": "/workspace"}),
        ]

        for tool_name, args in read_only_calls:
            payload = {
                "conversationId": conv_id,
                "turnId": turn_id,
                "hookEvent": "PreToolUse",
                "toolCall": {"name": tool_name, "args": args},
            }
            buf = io.StringIO()
            with patch("sys.stdin", io.StringIO(json.dumps(payload))), patch("sys.stdout", buf):
                completion_fence_hook.main()
            out = json.loads(buf.getvalue().strip())
            self.assertEqual(out.get("decision"), "allow")

        # Evaluate stop for this turn: must be allowed immediately
        stop_payload = {
            "conversationId": conv_id,
            "turnId": turn_id,
            "cwd": str(self.cwd),
        }
        buf_stop = io.StringIO()
        with patch("sys.stdin", io.StringIO(json.dumps(stop_payload))), patch("sys.stdout", buf_stop):
            completion_fence_hook.main()
        out_stop = json.loads(buf_stop.getvalue().strip())
        self.assertEqual(out_stop["decision"], "allow")

    def test_conversational_turn_after_unverified_turn_allows_turn_completion(self):
        """
        Issue #80: If Turn 1 had unverified edits, but Turn 2 is a purely conversational
        triage/explanation turn without tool mutations, Turn 2 is allowed to finish cleanly.
        """
        conv_id = "test-multiturn-sensitivity"
        turn1_id = "turn-001"
        turn2_id = "turn-002"

        # Turn 1: code edit performed
        record_edit("src/logic.py", conv_id=conv_id, state_dir=self.state_dir, cwd=self.cwd, turn_id=turn1_id)
        # Turn 1 stop is blocked
        res_t1 = evaluate_stop(conv_id=conv_id, state_dir=self.state_dir, cwd=self.cwd, turn_id=turn1_id)
        self.assertEqual(res_t1["decision"], "continue")

        # Turn 2: conversational turn without mutations
        res_t2 = evaluate_stop(conv_id=conv_id, state_dir=self.state_dir, cwd=self.cwd, turn_id=turn2_id)
        self.assertEqual(res_t2["decision"], "allow")

    # --- Category D: Turn-Scoped Mutation Sensitivity: Code Edits & Mutating Bash (Issue #80) ---

    def test_mutating_tool_calls_arm_turn_fence(self):
        """
        Issue #80: write_to_file and replace_file_content in the active turn arm the fence
        and block turn completion until verified.
        """
        conv_id = "test-turn-mutating-tools"
        turn_id = "turn-mutate"

        payload_write = {
            "conversationId": conv_id,
            "turnId": turn_id,
            "hookEvent": "PreToolUse",
            "toolCall": {"name": "write_to_file", "args": {"TargetFile": "src/api.ts"}},
        }
        buf = io.StringIO()
        with patch("sys.stdin", io.StringIO(json.dumps(payload_write))), patch("sys.stdout", buf):
            completion_fence_hook.main()

        res1 = evaluate_stop(conv_id=conv_id, state_dir=self.state_dir, cwd=self.cwd, turn_id=turn_id)
        self.assertEqual(res1["decision"], "continue")

    def test_mutating_bash_commands_arm_turn_fence(self):
        """
        Issue #80: Code-mutating shell commands (echo > file, sed -i, cat <<EOF, tee)
        in run_command arm the completion fence and block stop until verified.
        """
        conv_id = "test-mutating-bash"
        turn_id = "turn-bash"

        mutating_commands = [
            "echo 'x = 1' > src/module.py",
            "echo 'y = 2' >> src/module.py",
            "sed -i 's/foo/bar/' src/core.py",
            "cat <<EOF > src/config.py\nDEBUG = True\nEOF",
            "cat << 'EOF' | tee src/util.ts\nexport const x = 1;\nEOF",
        ]

        for idx, cmd in enumerate(mutating_commands):
            with self.subTest(cmd=cmd):
                conv = f"{conv_id}-{idx}"
                payload = {
                    "conversationId": conv,
                    "turnId": turn_id,
                    "hookEvent": "PreToolUse",
                    "toolCall": {"name": "run_command", "args": {"CommandLine": cmd, "Cwd": str(self.cwd)}},
                }
                buf = io.StringIO()
                with patch("sys.stdin", io.StringIO(json.dumps(payload))), patch("sys.stdout", buf):
                    completion_fence_hook.main()

                # Stop evaluation must block
                res = evaluate_stop(conv_id=conv, state_dir=self.state_dir, cwd=self.cwd, turn_id=turn_id)
                self.assertEqual(res["decision"], "continue")
                self.assertIn("Verification Required", res.get("reason", ""))

    # --- Category E: Polyglot Test Runner Recognition (Issue #81) ---

    def test_polyglot_test_runners_matrix(self):
        """
        Issue #81: Broadened regex recognizes all 12 modern test runner ecosystems:
        Vitest, Playwright, Bun, Node --test, Cargo, Go, Pytest, Unittest, Dotnet, Maven, Gradle, CTest.
        """
        polyglot_runners = [
            # Vitest
            "vitest",
            "vitest run",
            "npx vitest",
            "pnpm vitest",
            "bunx vitest",
            "yarn vitest run",
            "vitest --run",
            # Playwright
            "playwright test",
            "npx playwright test",
            "pnpm exec playwright test",
            "bunx playwright test",
            "yarn playwright test",
            "playwright test tests/e2e",
            # Bun test
            "bun test",
            "bun test tests/",
            "bun run test",
            # Node --test
            "node --test",
            "node --test tests/*.test.js",
            # Cargo
            "cargo test",
            "cargo test --lib",
            "cargo test --all",
            "cargo nextest",
            "cargo nextest run",
            # Go
            "go test",
            "go test ./...",
            "go test -v ./...",
            "go test -race ./...",
            # Pytest
            "pytest",
            "pytest tests/",
            "python3 -m pytest",
            "python -m pytest",
            # Unittest
            "python3 -m unittest",
            "python -m unittest discover",
            # Dotnet
            "dotnet test",
            "dotnet test MySolution.sln",
            # Maven
            "mvn test",
            "mvn verify",
            "./mvnw test",
            # Gradle
            "gradle test",
            "./gradlew test",
            "gradle check",
            "./gradlew check",
            # CTest
            "ctest",
            "ctest --verbose",
            "ctest -V",
            # Agyis / PSL
            "agyis test",
            "./agyis test",
            "python3 -m harness.cli test",
        ]

        for cmd in polyglot_runners:
            with self.subTest(cmd=cmd):
                self.assertTrue(
                    completion_fence_hook.is_test_command(cmd, cwd=self.cwd),
                    f"Expected '{cmd}' to be recognized as test runner",
                )

        negative_commands = [
            "ls -la",
            "echo 'testing 123'",
            "cat test.py",
            "git commit -m 'add test runner'",
            "python test_script.py",
            "node test_server.js",
            "cargo build",
            "go build",
            "mvn compile",
            "gradle build",
            "dotnet build",
        ]

        for cmd in negative_commands:
            with self.subTest(cmd=cmd):
                self.assertFalse(
                    completion_fence_hook.is_test_command(cmd, cwd=self.cwd),
                    f"Expected '{cmd}' NOT to be recognized as test runner",
                )

    # --- Category F: Dynamic Project Runner Discovery Integration (Issue #81) ---

    def test_dynamic_project_runner_integration(self):
        """
        Issue #81: Integrates detect_project_test_runner with is_test_command and refusal messages.
        If workspace specifies a custom test script (e.g. vitest in package.json),
        the detected runner clears code_dirty upon execution.
        """
        pkg_json = self.cwd / "package.json"
        pkg_json.write_text(json.dumps({"scripts": {"test": "vitest"}}), encoding="utf-8")

        conv_id = "test-dyn-vitest"
        record_edit("src/comp.tsx", conv_id=conv_id, state_dir=self.state_dir, cwd=self.cwd)

        # Refusal message cites project test suite
        res_block = evaluate_stop(conv_id=conv_id, state_dir=self.state_dir, cwd=self.cwd)
        self.assertEqual(res_block["decision"], "continue")
        self.assertIn("npm test", res_block["reason"])

        # Running npm test with exit code 0 clears code_dirty
        matched = check_command_verification("npm test", exit_code=0, conv_id=conv_id, state_dir=self.state_dir, cwd=self.cwd)
        self.assertTrue(matched)
        self.assertFalse(load_state(conv_id=conv_id, state_dir=self.state_dir)["code_dirty"])

    # --- Category G: Worker 2 Phase 1 Remediations ---

    def test_benign_dev_null_redirections_do_not_arm_fence(self):
        """
        Worker 2 Remediation: Verifies that command -v, > /dev/null, 2>&1,
        and /tmp redirections NEVER mark code dirty or arm the fence.
        """
        conv_id = "test-benign-redirs"
        reset_state(conv_id=conv_id, state_dir=self.state_dir)

        benign_commands = [
            "command -v node > /dev/null",
            "which cargo > /dev/null",
            "echo 'test' > /dev/null",
            "git status > /dev/null 2>&1",
            "ls -la > /tmp/listing.txt",
            "command -v pytest > /dev/null 2>&1",
        ]
        for cmd in benign_commands:
            with self.subTest(cmd=cmd):
                mutated = completion_fence_hook.check_shell_command_mutation(
                    cmd, cwd=self.cwd, conv_id=conv_id, state_dir=self.state_dir
                )
                self.assertFalse(mutated, f"Expected '{cmd}' NOT to mutate state")

        state = load_state(conv_id=conv_id, state_dir=self.state_dir)
        self.assertFalse(state["code_dirty"])
        self.assertFalse(state["turn_mutated"])
        self.assertEqual(state["last_modified_files"], [])

        res = evaluate_stop(conv_id=conv_id, state_dir=self.state_dir, cwd=self.cwd)
        self.assertEqual(res["decision"], "allow")

    def test_sync_background_tasks_none_tool_metadata(self):
        """
        Worker 2 Remediation: Verifies that sourceMetadata.tool being None
        or non-dict does not crash sync_background_tasks.
        """
        conv_id = "test-none-tool-meta"
        reset_state(conv_id=conv_id, state_dir=self.state_dir)
        record_edit("src/service.py", conv_id=conv_id, state_dir=self.state_dir, cwd=self.cwd)

        brain_dir = self.cwd / "brain"
        msg_dir = brain_dir / ".system_generated" / "messages"
        msg_dir.mkdir(parents=True, exist_ok=True)

        bad_msg = {
            "sender": f"{conv_id}/task-bad",
            "content": 'Task id "task-bad" finished with result:\n\nThe command exited with code 0.',
            "sourceMetadata": {"tool": None},
        }
        (msg_dir / "msg_none_tool.json").write_text(json.dumps(bad_msg), encoding="utf-8")

        # Must evaluate gracefully without AttributeError
        res = evaluate_stop(conv_id=conv_id, state_dir=self.state_dir, cwd=self.cwd, brain_dir=brain_dir)
        self.assertEqual(res["decision"], "continue")

    def test_sync_background_tasks_temporal_event_ordering(self):
        """
        Worker 2 Remediation: Verifies that message files are processed in ascending
        chronological timestamp order so that a passing task followed by a failing
        task leaves code_dirty = True regardless of filesystem directory order.
        """
        conv_id = "test-temporal-ordering"
        reset_state(conv_id=conv_id, state_dir=self.state_dir)
        record_edit("src/app.py", conv_id=conv_id, state_dir=self.state_dir, cwd=self.cwd)
        state = load_state(conv_id=conv_id, state_dir=self.state_dir)
        state["last_dirtied_at"] = "2026-10-21T10:00:00Z"
        save_state(state, conv_id=conv_id, state_dir=self.state_dir)

        brain_dir = self.cwd / "brain"
        msg_dir = brain_dir / ".system_generated" / "messages"
        msg_dir.mkdir(parents=True, exist_ok=True)

        # z_msg has older timestamp (10:01), passes (exit 0)
        (msg_dir / "z_msg.json").write_text(json.dumps({
            "sender": f"{conv_id}/task-1",
            "content": f'Task id "{conv_id}/task-1" finished with result:\n\nThe command exited with code 0.',
            "timestamp": "2026-10-21T10:01:00Z",
            "sourceMetadata": {"tool": {"toolCall": {"argumentsJson": json.dumps({"CommandLine": "pytest"})}}},
        }), encoding="utf-8")

        # a_msg has newer timestamp (10:05), fails (exit 1)
        (msg_dir / "a_msg.json").write_text(json.dumps({
            "sender": f"{conv_id}/task-2",
            "content": f'Task id "{conv_id}/task-2" finished with result:\n\nThe command exited with code 1.',
            "timestamp": "2026-10-21T10:05:00Z",
            "sourceMetadata": {"tool": {"toolCall": {"argumentsJson": json.dumps({"CommandLine": "pytest"})}}},
        }), encoding="utf-8")

        completion_fence_hook.sync_background_tasks(
            conv_id=conv_id, state_dir=self.state_dir, cwd=self.cwd, brain_dir=brain_dir
        )
        final_state = load_state(conv_id=conv_id, state_dir=self.state_dir)
        self.assertTrue(final_state["code_dirty"], "Failing task outcome must determine state")

    def test_polyglot_runner_inline_env_and_workspace_flags(self):
        """
        Worker 2 Remediation: Verifies that direct inline POSIX env vars,
        workspace flags (-w), and parenthesized / chained commands are recognized.
        """
        valid_commands = [
            "CI=true npx vitest run --coverage",
            "pnpm -w test",
            "(pytest)",
            "RUST_BACKTRACE=1 cargo test",
            "CGO_ENABLED=0 go test ./...",
            "PYTHONPATH=. pytest",
            "pytest; echo done",
            "ctest; echo done",
        ]
        for cmd in valid_commands:
            with self.subTest(cmd=cmd):
                self.assertTrue(
                    completion_fence_hook.is_test_command(cmd, cwd=self.cwd),
                    f"Expected '{cmd}' to be recognized as test runner",
                )

    def test_informational_and_scaffolding_commands_rejected(self):
        """
        Worker 2 Remediation: Verifies that --help, -h, --version, and
        scaffolding subcommands like 'vitest init' are strictly rejected.
        """
        rejected_commands = [
            "vitest --help",
            "vitest --version",
            "pytest --help",
            "cargo test --help",
            "go test --help",
            "ctest --help",
            "vitest init",
        ]
        for cmd in rejected_commands:
            with self.subTest(cmd=cmd):
                self.assertFalse(
                    completion_fence_hook.is_test_command(cmd, cwd=self.cwd),
                    f"Expected '{cmd}' NOT to be recognized as test runner",
                )

    def test_discovery_cargo_with_package_json_no_test_script(self):
        """
        Worker 2 Remediation: Verifies that a package.json without a 'test' script
        does not shadow Cargo.toml in a polyglot repository.
        """
        cargo_toml = self.cwd / "Cargo.toml"
        cargo_toml.write_text("[package]\nname = 'polyglot'\n", encoding="utf-8")
        pkg_json = self.cwd / "package.json"
        pkg_json.write_text(json.dumps({"scripts": {"format": "prettier"}}), encoding="utf-8")

        from harness.discovery import detect_project_test_runner
        detected = detect_project_test_runner(self.cwd)
        self.assertEqual(detected, "cargo test")


if __name__ == "__main__":
    unittest.main()

