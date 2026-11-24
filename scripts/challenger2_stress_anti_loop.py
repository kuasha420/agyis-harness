#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Arafat Zahan (@kuasha420)
# Corporate Stewardship & Infrastructure: Purrfect Software Limited (PSL)
# Governed by: ICARO-42/b Ordinance (Company-Supported Personal IP Framework)

"""
Adversarial Stress Test Suite for Anti-Loop Hook (o13_m3_challenger_2)

Empirically challenges:
1. Boundary condition 8 vs 9 on idempotent commands (consecutive & sliding window).
2. Boundary condition 3 vs 4 on generic commands (consecutive & sliding window).
3. Heartbeat inspection exemption (progress.md and teamwork paths: 50+ executions).
4. Task log inspection hard limits vs manage_task status advisory.
5. Verification reset invariant under rapid alternation.
6. Cyclic pattern detection & idempotent cycle exemption.
7. Main / stdin fuzzed / malformed input resilience.
"""

from __future__ import annotations

import io
import json
from pathlib import Path
import sys
import tempfile
import time
import unittest
from unittest.mock import patch

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from harness.hooks.anti_loop_hook import (
    check_anti_loop,
    main as anti_loop_main,
    MAX_REPEATS,
    MAX_FREQUENCY_REPEATS,
    MAX_IDEMPOTENT_FREQUENCY_REPEATS,
    FREQUENCY_WINDOW,
    _is_idempotent_status_command,
    _is_peer_heartbeat,
)


class TestAntiLoopAdversarialBoundaries(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.state_dir = Path(self.temp_dir.name)

    def tearDown(self):
        self.temp_dir.cleanup()

    # =========================================================================
    # 1. Idempotent Command Boundary Stress: Exactly 8 allowed, 9th denied
    # =========================================================================
    def test_idempotent_consecutive_boundary_strictly_8_allow_9_deny(self):
        """Verify that exactly 8 consecutive executions are ALLOWED, and the 9th is DENIED."""
        commands = [
            "git status",
            "git status -s",
            "git branch",
            "git branch -a",
            "stat /workspace/file.py",
            "pwd",
            "PAGER=cat git status",
            "PAGER=cat  git branch",
        ]
        for cmd_idx, cmd in enumerate(commands):
            conv_id = f"idempotent-consec-{cmd_idx}"
            sig_args = {"CommandLine": cmd}

            # 1 to 8 MUST be allowed
            for i in range(1, 9):
                res = check_anti_loop("run_command", sig_args, conv_id=conv_id, state_dir=self.state_dir)
                self.assertEqual(
                    res.get("decision"),
                    "allow",
                    f"Command '{cmd}' call {i}/8 was unexpectedly denied: {res}",
                )

            # 9th MUST be denied
            tripped = check_anti_loop("run_command", sig_args, conv_id=conv_id, state_dir=self.state_dir)
            self.assertEqual(
                tripped.get("decision"),
                "deny",
                f"Command '{cmd}' 9th call was unexpectedly ALLOWED instead of denied!",
            )
            self.assertIn("PSL Anti-Loop Guard", tripped.get("reason", ""))

    def test_idempotent_window_boundary_strictly_8_allow_9_deny(self):
        """Verify rolling window of 15 allows exactly 8 occurrences of idempotent command, 9th denied."""
        conv_id = "idempotent-window-test"
        cmd = "git status"
        sig_args = {"CommandLine": cmd}

        # Interleave pairs of cmd with unique dummy calls to keep consecutive repeats <= 2
        # Calls 1..8 of cmd should all be allowed
        for i in range(1, 9):
            res = check_anti_loop("run_command", sig_args, conv_id=conv_id, state_dir=self.state_dir)
            self.assertEqual(
                res.get("decision"),
                "allow",
                f"Idempotent command '{cmd}' execution {i}/8 was unexpectedly denied: {res}",
            )
            # Add an interleaved command every 2 calls (unless on last)
            if i % 2 == 0 and i < 8:
                check_anti_loop(
                    "run_command",
                    {"CommandLine": f"echo 'interleaved-{i}'"},
                    conv_id=conv_id,
                    state_dir=self.state_dir,
                )

        # 9th execution of cmd within window of 15 calls must be DENIED
        tripped = check_anti_loop("run_command", sig_args, conv_id=conv_id, state_dir=self.state_dir)
        self.assertEqual(
            tripped.get("decision"),
            "deny",
            f"9th execution within frequency window was expected to deny, but got: {tripped}",
        )
        self.assertIn("sliding window", tripped.get("reason", ""))
        self.assertIn(f"threshold is {MAX_IDEMPOTENT_FREQUENCY_REPEATS}", tripped.get("reason", ""))

    # =========================================================================
    # 2. Generic Command Boundary Stress: Exactly 3 allowed, 4th denied
    # =========================================================================
    def test_generic_consecutive_boundary_strictly_3_allow_4_deny(self):
        """Verify generic commands allow exactly 3 consecutive calls and deny on the 4th."""
        test_tools = [
            ("read_file", {"Path": "/workspace/src/app.py"}),
            ("run_command", {"CommandLine": "rg TODO /workspace/src"}),
            ("run_command", {"CommandLine": "cargo build"}),
            ("run_command", {"CommandLine": "python3 script.py"}),
            ("run_command", {"CommandLine": "ls -la /tmp"}),
        ]
        for tool_idx, (name, args) in enumerate(test_tools):
            conv_id = f"generic-consec-{tool_idx}"

            # Calls 1, 2, 3 MUST be allowed
            for i in range(1, 4):
                res = check_anti_loop(name, args, conv_id=conv_id, state_dir=self.state_dir)
                self.assertEqual(
                    res.get("decision"),
                    "allow",
                    f"Generic tool {name} call {i}/3 was unexpectedly denied: {res}",
                )

            # Call 4 MUST be denied
            tripped = check_anti_loop(name, args, conv_id=conv_id, state_dir=self.state_dir)
            self.assertEqual(
                tripped.get("decision"),
                "deny",
                f"Generic tool {name} 4th call was unexpectedly ALLOWED!",
            )
            self.assertIn("PSL Anti-Loop Guard", tripped.get("reason", ""))

    def test_generic_window_boundary_strictly_3_allow_4_deny(self):
        """Verify rolling window of 15 allows 3 occurrences of generic command, 4th denied."""
        conv_id = "generic-window-test"
        name = "read_file"
        args = {"Path": "/workspace/find_me.py"}

        # Call 1
        res1 = check_anti_loop(name, args, conv_id=conv_id, state_dir=self.state_dir)
        self.assertEqual(res1.get("decision"), "allow")
        # Interleave dummy
        check_anti_loop("run_command", {"CommandLine": "echo 1"}, conv_id=conv_id, state_dir=self.state_dir)

        # Call 2
        res2 = check_anti_loop(name, args, conv_id=conv_id, state_dir=self.state_dir)
        self.assertEqual(res2.get("decision"), "allow")
        # Interleave dummy
        check_anti_loop("run_command", {"CommandLine": "echo 2"}, conv_id=conv_id, state_dir=self.state_dir)

        # Call 3
        res3 = check_anti_loop(name, args, conv_id=conv_id, state_dir=self.state_dir)
        self.assertEqual(res3.get("decision"), "allow")
        # Interleave dummy
        check_anti_loop("run_command", {"CommandLine": "echo 3"}, conv_id=conv_id, state_dir=self.state_dir)

        # Call 4: within window of 15 calls -> MUST be denied (freq_count >= 4)
        res4 = check_anti_loop(name, args, conv_id=conv_id, state_dir=self.state_dir)
        self.assertEqual(
            res4.get("decision"),
            "deny",
            f"4th occurrence in rolling window was expected to deny, got {res4}",
        )
        self.assertIn("sliding window", res4.get("reason", ""))
        self.assertIn(f"threshold is {MAX_FREQUENCY_REPEATS}", res4.get("reason", ""))

    # =========================================================================
    # 3. Heartbeat Inspection Exemption: Never Blocked
    # =========================================================================
    def test_heartbeat_stress_50_consecutive_executions_never_blocked(self):
        """Assert that read_file on progress.md or teamwork paths can be called 50+ times without denial."""
        conv_id = "heartbeat-stress-50"
        heartbeat_targets = [
            {"Path": "/workspace/agyis-harness/.agents/teamwork/worker_1/progress.md"},
            {"Path": ".agents/teamwork/orchestrator/plan.md"},
            {"Path": "/workspace/.agents/teamwork/challenger_2/DISPATCH.md"},
            {"Path": "/workspace/subproject/progress.md"},
        ]

        for target in heartbeat_targets:
            for i in range(50):
                res = check_anti_loop("read_file", target, conv_id=conv_id, state_dir=self.state_dir)
                self.assertEqual(
                    res.get("decision"),
                    "allow",
                    f"Heartbeat target {target} was denied at iteration {i+1}: {res}",
                )

    # =========================================================================
    # 4. Background Task Polling & Advisory Boundaries
    # =========================================================================
    def test_manage_task_status_strict_rate_limit(self):
        """manage_task(Action='status') emits advisory on calls 1-2 and denies on call 3."""
        conv_id = "manage-task-advisory-stress"
        args = {"Action": "status", "TaskId": "task-999"}
        for i in range(2):
            res = check_anti_loop("manage_task", args, conv_id=conv_id, state_dir=self.state_dir)
            self.assertEqual(res.get("decision"), "allow", f"Call {i+1} unexpectedly denied: {res}")
            self.assertIn("Advisory", res.get("reason", ""))
        tripped = check_anti_loop("manage_task", args, conv_id=conv_id, state_dir=self.state_dir)
        self.assertEqual(tripped.get("decision"), "deny")
        self.assertIn("background task inspections", tripped.get("reason", ""))

    def test_task_log_inspection_hard_denial_boundary(self):
        """Directly reading background task logs (.system_generated/tasks/...log) is denied after 2 consecutive."""
        conv_id = "task-log-consec"
        log_args = {"Path": "/home/user/.gemini/brain/session/.system_generated/tasks/task-1.log"}

        # Calls 1 and 2 allow
        res1 = check_anti_loop("read_file", log_args, conv_id=conv_id, state_dir=self.state_dir)
        self.assertEqual(res1["decision"], "allow")
        res2 = check_anti_loop("read_file", log_args, conv_id=conv_id, state_dir=self.state_dir)
        self.assertEqual(res2["decision"], "allow")

        # Call 3 is DENIED by task log check (MAX_TASK_INSPECTION_CONSECUTIVE = 2)
        res3 = check_anti_loop("read_file", log_args, conv_id=conv_id, state_dir=self.state_dir)
        self.assertEqual(res3["decision"], "deny")
        self.assertIn("consecutive background task inspections", res3["reason"])

    # =========================================================================
    # 5. Verification Reset Invariant Stress
    # =========================================================================
    def test_verification_reset_invariant_stress_cycle(self):
        """Alternate code edit and test runner 20 times: must NEVER trip loop denial."""
        conv_id = "verify-reset-stress"
        for i in range(20):
            # Code edit
            edit_res = check_anti_loop(
                "edit_file",
                {
                    "Path": "/workspace/lib.py",
                    "Target": f"x = {i}",
                    "Replacement": f"x = {i+1}",
                },
                conv_id=conv_id,
                state_dir=self.state_dir,
            )
            self.assertEqual(edit_res["decision"], "allow")

            # Test run
            test_res = check_anti_loop(
                "run_command",
                {"CommandLine": "python3 -m harness.cli test"},
                conv_id=conv_id,
                state_dir=self.state_dir,
            )
            self.assertEqual(
                test_res["decision"],
                "allow",
                f"Test verification command denied at iteration {i+1} despite preceding edit: {test_res}",
            )

    # =========================================================================
    # 6. Cyclic Pattern Detection & Idempotent Cycle Exemption
    # =========================================================================
    def test_cyclic_pattern_generic_denied(self):
        """A repeating 2-tool cycle (A -> B -> A -> B) of generic tools is denied."""
        conv_id = "cyclic-generic"
        tool_a = ("run_command", {"CommandLine": "ls -l /tmp"})
        tool_b = ("read_file", {"Path": "/tmp/pattern.txt"})

        # Cycle 1: A -> B
        check_anti_loop(tool_a[0], tool_a[1], conv_id=conv_id, state_dir=self.state_dir)
        check_anti_loop(tool_b[0], tool_b[1], conv_id=conv_id, state_dir=self.state_dir)

        # Cycle 2: A -> B (B should trigger cycle denial)
        check_anti_loop(tool_a[0], tool_a[1], conv_id=conv_id, state_dir=self.state_dir)
        res = check_anti_loop(tool_b[0], tool_b[1], conv_id=conv_id, state_dir=self.state_dir)
        self.assertEqual(res["decision"], "deny")
        self.assertIn("cyclic tool execution pattern", res["reason"])

    def test_cyclic_pattern_idempotent_exempt(self):
        """A cycle of purely idempotent commands (e.g. git status -> git branch -> git status -> git branch) is NOT denied by cyclic checker."""
        conv_id = "cyclic-idempotent"
        cmd_a = ("run_command", {"CommandLine": "git status"})
        cmd_b = ("run_command", {"CommandLine": "git branch"})

        # Cycle 1: A -> B
        r1 = check_anti_loop(cmd_a[0], cmd_a[1], conv_id=conv_id, state_dir=self.state_dir)
        r2 = check_anti_loop(cmd_b[0], cmd_b[1], conv_id=conv_id, state_dir=self.state_dir)
        self.assertEqual(r1["decision"], "allow")
        self.assertEqual(r2["decision"], "allow")

        # Cycle 2: A -> B (must still be allowed because both are idempotent)
        r3 = check_anti_loop(cmd_a[0], cmd_a[1], conv_id=conv_id, state_dir=self.state_dir)
        r4 = check_anti_loop(cmd_b[0], cmd_b[1], conv_id=conv_id, state_dir=self.state_dir)
        self.assertEqual(r3["decision"], "allow")
        self.assertEqual(r4["decision"], "allow")

    # =========================================================================
    # 7. Hook main() Stdin Robustness & Malformed Inputs
    # =========================================================================
    def test_hook_main_stdin_fail_open_on_non_json_or_empty(self):
        """Verify hook main() fails open (decision: allow) on non-json, empty, or non-dict payloads."""
        valid_fallback_inputs = [
            "",
            "   ",
            "not-json",
            "[]",
            "123",
            "null",
        ]
        for raw in valid_fallback_inputs:
            with patch("sys.stdin", io.StringIO(raw)), patch("sys.stdout", new_callable=io.StringIO) as mock_out:
                anti_loop_main()
                out = mock_out.getvalue().strip()
                parsed = json.loads(out)
                self.assertEqual(
                    parsed.get("decision"),
                    "allow",
                    f"Expected fallback allow on input '{raw}', got {parsed}",
                )

    def test_hook_main_null_tool_call_fails_open(self):
        """
        Verify that when payload is a valid JSON dict with null toolCall or null args,
        anti_loop_hook main() coalesces safely and fails open (decision: allow).
        """
        edge_inputs = [
            '{"conversationId": "test", "toolCall": null}',
            '{"conversationId": "test", "toolCall": {"name": "run_command", "args": null}}',
        ]
        for raw in edge_inputs:
            with patch("sys.stdin", io.StringIO(raw)), patch("sys.stdout", new_callable=io.StringIO) as mock_out:
                anti_loop_main()
                parsed = json.loads(mock_out.getvalue().strip())
                self.assertEqual(parsed.get("decision"), "allow")


if __name__ == "__main__":
    unittest.main()

