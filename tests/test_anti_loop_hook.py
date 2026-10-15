#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Arafat Zahan (@kuasha420)
# Corporate Stewardship & Infrastructure: Purrfect Software Limited (PSL)
# Governed by: ICARO-42/b Ordinance (Company-Supported Personal IP Framework)

"""
Unit tests for anti_loop_hook relaxations (PSL-SPEC-2026-DRA-001 Phase 2):
1. Peer Heartbeat Exemption (progress.md and teamwork files never denied).
2. Verification Reset Invariant (code edits reset test runner loop counters).
3. Non-Blocking Advisory for Background Tasks (manage_task status returns allow).
4. Read-Only Status Command Relaxation (git status, git branch, stat, pwd allow at least 8 executions).
5. Robust OSError handling on state directory creation.
"""

from __future__ import annotations

import io
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from harness.hooks.anti_loop_hook import (
    check_anti_loop,
    main as anti_loop_main,
    MAX_IDEMPOTENT_FREQUENCY_REPEATS,
)


class TestAntiLoopHookPhase2(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.state_dir = Path(self.temp_dir.name)

    def tearDown(self):
        self.temp_dir.cleanup()

    # 1. Peer Heartbeat Exemption
    def test_peer_heartbeat_progress_md_10_consecutive_denials_zero(self):
        """Reading progress.md 10 times consecutively produces 0 PreToolUse hook denials."""
        conv_id = "test-heartbeat-progress"
        tool_args = {"AbsolutePath": "/home/user/Dev/repo/.agents/teamwork/o12_m1_worker/progress.md"}

        denials = 0
        for i in range(10):
            res = check_anti_loop("view_file", tool_args, conv_id=conv_id, state_dir=self.state_dir)
            if res.get("decision") != "allow":
                denials += 1
            self.assertEqual(res.get("decision"), "allow", f"Call {i+1} was unexpectedly denied: {res}")

        self.assertEqual(denials, 0, "Reading progress.md 10 times consecutively produced denials")

    def test_peer_heartbeat_teamwork_paths_consecutive_denials_zero(self):
        """Inspections of files within /.agents/teamwork/ or .agents/teamwork/ produce 0 loop denials."""
        conv_id = "test-heartbeat-teamwork"
        paths = [
            "/home/user/Dev/psl-agy-harness/.agents/teamwork/o12_m1_worker/handoff.md",
            "/home/user/Dev/psl-agy-harness/.agents/teamwork/orchestrator_12/DISPATCH.md",
            ".agents/teamwork/o12_m2_worker/progress.md",
            ".agents/teamwork/shared_context.md",
        ]

        for p in paths:
            for _ in range(5):
                res = check_anti_loop("view_file", {"AbsolutePath": p}, conv_id=conv_id, state_dir=self.state_dir)
                self.assertEqual(res["decision"], "allow")

    def test_non_heartbeat_view_file_denies_after_threshold(self):
        """Reading standard non-heartbeat files repeatedly still triggers anti-loop denial after 3 repeats."""
        conv_id = "test-normal-file-loop"
        tool_args = {"AbsolutePath": "/workspace/src/app/main.py"}

        for _ in range(3):
            res = check_anti_loop("view_file", tool_args, conv_id=conv_id, state_dir=self.state_dir)
            self.assertEqual(res["decision"], "allow")

        # 4th identical call trips the breaker
        tripped = check_anti_loop("view_file", tool_args, conv_id=conv_id, state_dir=self.state_dir)
        self.assertEqual(tripped["decision"], "deny")
        self.assertIn("PSL Anti-Loop Guard", tripped["reason"])

    # 2. Verification Reset Invariant
    def test_verification_reset_invariant_agyis_test_with_write_to_file(self):
        """Repeated ./agyis test invocations preceded by write_to_file reset counters and do not trip sliding-window denials."""
        conv_id = "test-verify-reset-agyis"
        test_args = {"CommandLine": "./agyis test"}

        for i in range(10):
            # Code edit mutation occurs
            edit_args = {
                "TargetFile": f"/workspace/src/module_{i}.py",
                "CodeContent": f"# version {i}\n",
                "Overwrite": True,
            }
            res_edit = check_anti_loop("write_to_file", edit_args, conv_id=conv_id, state_dir=self.state_dir)
            self.assertEqual(res_edit["decision"], "allow")

            # Verification test following code edit must NEVER be blocked as a loop
            res_test = check_anti_loop("run_command", test_args, conv_id=conv_id, state_dir=self.state_dir)
            self.assertEqual(
                res_test["decision"],
                "allow",
                f"Iteration {i+1} ./agyis test was blocked despite preceding code edit: {res_test}",
            )

    def test_verification_reset_invariant_harness_cli_test_with_replace_file_content(self):
        """Repeated python3 -m harness.cli test preceded by replace_file_content never trip denials."""
        conv_id = "test-verify-reset-cli"
        test_args = {"CommandLine": "python3 -m harness.cli test"}

        for i in range(10):
            edit_args = {
                "TargetFile": "/workspace/src/core.py",
                "StartLine": 1,
                "EndLine": 2,
                "TargetContent": f"x = {i}\n",
                "ReplacementContent": f"x = {i + 1}\n",
            }
            res_edit = check_anti_loop("replace_file_content", edit_args, conv_id=conv_id, state_dir=self.state_dir)
            self.assertEqual(res_edit["decision"], "allow")

            res_test = check_anti_loop("run_command", test_args, conv_id=conv_id, state_dir=self.state_dir)
            self.assertEqual(
                res_test["decision"],
                "allow",
                f"Iteration {i+1} harness.cli test was blocked despite preceding replace_file_content: {res_test}",
            )

    def test_verification_reset_invariant_pytest(self):
        """Repeated pytest invocations preceded by write_to_file never trip sliding-window denials."""
        conv_id = "test-verify-reset-pytest"
        test_args = {"CommandLine": "pytest tests/ -v"}

        for i in range(10):
            res_edit = check_anti_loop(
                "write_to_file",
                {"TargetFile": f"/workspace/test_{i}.py", "CodeContent": "def test(): pass\n"},
                conv_id=conv_id,
                state_dir=self.state_dir,
            )
            self.assertEqual(res_edit["decision"], "allow")

            res_test = check_anti_loop("run_command", test_args, conv_id=conv_id, state_dir=self.state_dir)
            self.assertEqual(res_test["decision"], "allow")

    def test_verification_reset_invariant_cargo_and_pnpm(self):
        """Repeated cargo test and pnpm test invocations preceded by code edits never trip sliding-window denials."""
        conv_id = "test-verify-reset-cargo-pnpm"

        for i in range(5):
            # Cargo test following edit
            check_anti_loop(
                "replace_file_content",
                {"TargetFile": "/workspace/src/lib.rs", "TargetContent": f"// {i}", "ReplacementContent": f"// {i+1}"},
                conv_id=conv_id,
                state_dir=self.state_dir,
            )
            res_cargo = check_anti_loop("run_command", {"CommandLine": "cargo test --workspace"}, conv_id=conv_id, state_dir=self.state_dir)
            self.assertEqual(res_cargo["decision"], "allow")

            # Pnpm test following edit
            check_anti_loop(
                "write_to_file",
                {"TargetFile": f"/workspace/src/index_{i}.ts", "CodeContent": "export const x = 1;\n"},
                conv_id=conv_id,
                state_dir=self.state_dir,
            )
            res_pnpm = check_anti_loop("run_command", {"CommandLine": "pnpm test"}, conv_id=conv_id, state_dir=self.state_dir)
            self.assertEqual(res_pnpm["decision"], "allow")

    def test_verification_without_edits_trips_threshold(self):
        """Without preceding code edits, repeating the test command 4 times trips consecutive repeat denials."""
        conv_id = "test-verify-no-edits"
        test_args = {"CommandLine": "./agyis test"}

        for _ in range(3):
            res = check_anti_loop("run_command", test_args, conv_id=conv_id, state_dir=self.state_dir)
            self.assertEqual(res["decision"], "allow")

        tripped = check_anti_loop("run_command", test_args, conv_id=conv_id, state_dir=self.state_dir)
        self.assertEqual(tripped["decision"], "deny")

    # 3. Non-Blocking Advisory for Background Tasks
    def test_manage_task_status_returns_non_blocking_advisory(self):
        """manage_task(Action='status') returns a non-blocking advisory (decision: 'allow') instead of denying."""
        conv_id = "test-manage-task-advisory"
        task_args = {"Action": "status", "TaskId": "task-42"}

        expected_reason = "Advisory: Background tasks notify reactively upon exit. Avoid polling status to conserve steps."

        # Verify that multiple consecutive invocations all return allow with the non-blocking advisory
        for i in range(8):
            res = check_anti_loop("manage_task", task_args, conv_id=conv_id, state_dir=self.state_dir)
            self.assertEqual(
                res["decision"],
                "allow",
                f"Call {i+1} of manage_task status was denied instead of returning advisory allow: {res}",
            )
            self.assertEqual(res.get("reason"), expected_reason)

    def test_manage_task_non_status_checked_normally(self):
        """manage_task with Action != 'status' (e.g. Action='kill') is not given the status advisory and trips repeats."""
        conv_id = "test-manage-task-kill"
        kill_args = {"Action": "kill", "TaskId": "task-42"}

        for _ in range(3):
            res = check_anti_loop("manage_task", kill_args, conv_id=conv_id, state_dir=self.state_dir)
            self.assertEqual(res["decision"], "allow")

        tripped = check_anti_loop("manage_task", kill_args, conv_id=conv_id, state_dir=self.state_dir)
        self.assertEqual(tripped["decision"], "deny")

    # 4. Read-Only Status Command Relaxation
    def test_idempotent_inspection_commands_allow_at_least_8_executions(self):
        """Idempotent inspection commands (git status, git branch, stat, pwd) allow up to at least 8 executions within the sliding window."""
        commands = [
            "git status",
            "git status -s",
            "git branch",
            "git branch -a",
            "stat /workspace/main.py",
            "pwd",
            "PAGER=cat git status",
        ]

        for cmd in commands:
            conv_id = f"test-idempotent-{hash(cmd) % 100000}"
            # Execute 8 times within the 15-call window (using pairs of cmd and interleaved calls)
            # Pattern: cmd, cmd, dummy, cmd, cmd, dummy, cmd, cmd, dummy, cmd, cmd -> 8 cmd calls in 11 total calls
            for i in range(8):
                res = check_anti_loop("run_command", {"CommandLine": cmd}, conv_id=conv_id, state_dir=self.state_dir)
                self.assertEqual(
                    res["decision"],
                    "allow",
                    f"Command '{cmd}' execution {i+1} was unexpectedly denied within sliding window: {res}",
                )
                # Interleave after every pair of calls to keep consecutive repeats <= 2 and keep total calls <= 15
                if i % 2 == 1 and i < 7:
                    check_anti_loop("run_command", {"CommandLine": f"echo 'interleaved {i}'"}, conv_id=conv_id, state_dir=self.state_dir)

            # The 9th execution of cmd within the 15-call window (12 total calls) exceeds threshold of 8 and is denied
            tripped = check_anti_loop("run_command", {"CommandLine": cmd}, conv_id=conv_id, state_dir=self.state_dir)
            self.assertEqual(
                tripped["decision"],
                "deny",
                f"Command '{cmd}' 9th execution was expected to trip frequency window: {tripped}",
            )
            self.assertIn("PSL Anti-Loop Guard", tripped["reason"])
            self.assertIn(f"threshold is {MAX_IDEMPOTENT_FREQUENCY_REPEATS}", tripped["reason"])

    def test_non_idempotent_command_trips_at_threshold_4(self):
        """Standard non-idempotent commands still trip rolling frequency threshold at 4 appearances."""
        conv_id = "test-non-idempotent-freq"
        cmd = "make build"

        for i in range(3):
            res = check_anti_loop("run_command", {"CommandLine": cmd}, conv_id=conv_id, state_dir=self.state_dir)
            self.assertEqual(res["decision"], "allow")
            check_anti_loop("run_command", {"CommandLine": f"echo unique_{i}"}, conv_id=conv_id, state_dir=self.state_dir)

        # 4th occurrence trips standard threshold of 4
        tripped = check_anti_loop("run_command", {"CommandLine": cmd}, conv_id=conv_id, state_dir=self.state_dir)
        self.assertEqual(tripped["decision"], "deny")
        self.assertIn("threshold is 4", tripped["reason"])

    # 5. Robust Directory Creation
    def test_state_dir_mkdir_handles_oserror(self):
        """check_anti_loop gracefully handles OSError on directory creation without crashing."""
        conv_id = "test-oserror-dir"
        with patch.object(Path, "mkdir", side_effect=OSError("Read-only file system")):
            res = check_anti_loop("view_file", {"AbsolutePath": "/progress.md"}, conv_id=conv_id, state_dir=self.state_dir)
            self.assertEqual(res["decision"], "allow")

    # 6. CLI Main Contract
    def test_cli_main_peer_heartbeat(self):
        """anti_loop_main processes peer heartbeat inspection payload via stdin and outputs allow."""
        payload = {
            "conversationId": "cli-heartbeat-conv",
            "toolCall": {
                "name": "view_file",
                "args": {"AbsolutePath": "/workspace/.agents/teamwork/worker_1/progress.md"},
            },
        }

        with patch.dict(os.environ, {"PSL_HARNESS_STATE_DIR": str(self.state_dir)}):
            with patch("sys.stdin", io.StringIO(json.dumps(payload))), patch("sys.stdout", new_callable=io.StringIO) as mock_out:
                anti_loop_main()
                out = json.loads(mock_out.getvalue().strip())
                self.assertEqual(out["decision"], "allow")

    def test_cli_main_manage_task_advisory(self):
        """anti_loop_main processes manage_task status payload and outputs allow with advisory reason."""
        payload = {
            "conversationId": "cli-manage-task-conv",
            "toolCall": {
                "name": "manage_task",
                "args": {"Action": "status", "TaskId": "task-99"},
            },
        }

        with patch.dict(os.environ, {"PSL_HARNESS_STATE_DIR": str(self.state_dir)}):
            with patch("sys.stdin", io.StringIO(json.dumps(payload))), patch("sys.stdout", new_callable=io.StringIO) as mock_out:
                anti_loop_main()
                out = json.loads(mock_out.getvalue().strip())
                self.assertEqual(out["decision"], "allow")
                self.assertIn("Advisory: Background tasks notify reactively", out.get("reason", ""))


if __name__ == "__main__":
    unittest.main()
