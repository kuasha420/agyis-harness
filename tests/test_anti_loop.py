#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Arafat Zahan (@kuasha420)
# Corporate Stewardship & Infrastructure: Purrfect Software Limited (PSL)
# Governed by: ICARO-42/b Ordinance (Company-Supported Personal IP Framework)

"""
Unit and integration tests for harness/hooks/anti_loop_hook.py
"""

import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from harness.hooks.anti_loop_hook import check_anti_loop, main as anti_loop_main


class TestAntiLoopHook(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.state_dir = Path(self.temp_dir.name)

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_state_dir_resolution_prefers_agyis_over_psl(self):
        """Verifies get_state_dir prefers AGYIS_HARNESS_STATE_DIR over PSL_HARNESS_STATE_DIR."""
        from harness.hooks.anti_loop_hook import get_state_dir
        with tempfile.TemporaryDirectory() as td_agyis, tempfile.TemporaryDirectory() as td_psl:
            with patch.dict(os.environ, {
                "AGYIS_HARNESS_STATE_DIR": td_agyis,
                "PSL_HARNESS_STATE_DIR": td_psl,
            }):
                self.assertEqual(get_state_dir(), Path(td_agyis))

            with patch.dict(os.environ, {
                "PSL_HARNESS_STATE_DIR": td_psl,
            }, clear=False):
                os.environ.pop("AGYIS_HARNESS_STATE_DIR", None)
                self.assertEqual(get_state_dir(), Path(td_psl))

    def test_under_threshold_allowed(self):
        """Calls 1, 2, and 3 with identical arguments must be allowed when max_repeats=3."""
        tool_name = "view_file"
        tool_args = {"AbsolutePath": "/workspace/file.py"}
        conv_id = "test-conv-1"

        # 1st call
        res1 = check_anti_loop(tool_name, tool_args, conv_id=conv_id, state_dir=self.state_dir)
        self.assertEqual(res1["decision"], "allow")

        # 2nd call
        res2 = check_anti_loop(tool_name, tool_args, conv_id=conv_id, state_dir=self.state_dir)
        self.assertEqual(res2["decision"], "allow")

        # 3rd call
        res3 = check_anti_loop(tool_name, tool_args, conv_id=conv_id, state_dir=self.state_dir)
        self.assertEqual(res3["decision"], "allow")

    def test_threshold_tripped_denies_execution(self):
        """When 3 identical previous calls exist, the 4th identical call must be denied."""
        tool_name = "grep_search"
        tool_args = {"Query": "def parse", "SearchPath": "/workspace"}
        conv_id = "test-conv-trip"

        for _ in range(3):
            res = check_anti_loop(tool_name, tool_args, conv_id=conv_id, state_dir=self.state_dir)
            self.assertEqual(res["decision"], "allow")

        # 4th call trips the breaker
        tripped = check_anti_loop(tool_name, tool_args, conv_id=conv_id, state_dir=self.state_dir)
        self.assertEqual(tripped["decision"], "deny")
        self.assertIn("PSL Anti-Loop Guard", tripped["reason"])
        self.assertIn("identical consecutive executions", tripped["reason"])
        self.assertIn("grep_search", tripped["reason"])

    def test_argument_mutation_resets_counter(self):
        """Mutating tool arguments breaks the consecutive repeat streak."""
        conv_id = "test-conv-mutate-args"

        # 2 identical calls
        check_anti_loop("view_file", {"AbsolutePath": "/workspace/a.py"}, conv_id=conv_id, state_dir=self.state_dir)
        check_anti_loop("view_file", {"AbsolutePath": "/workspace/a.py"}, conv_id=conv_id, state_dir=self.state_dir)

        # Mutate argument
        mutated = check_anti_loop("view_file", {"AbsolutePath": "/workspace/b.py"}, conv_id=conv_id, state_dir=self.state_dir)
        self.assertEqual(mutated["decision"], "allow")

        # Now calling a.py again should only have 1 repeat behind it
        res = check_anti_loop("view_file", {"AbsolutePath": "/workspace/a.py"}, conv_id=conv_id, state_dir=self.state_dir)
        self.assertEqual(res["decision"], "allow")

    def test_tool_name_mutation_resets_counter(self):
        """Changing tool name breaks consecutive repeat streak."""
        conv_id = "test-conv-mutate-tool"

        # 2 identical view_file calls
        args = {"Path": "/workspace/test.py"}
        check_anti_loop("view_file", args, conv_id=conv_id, state_dir=self.state_dir)
        check_anti_loop("view_file", args, conv_id=conv_id, state_dir=self.state_dir)

        # Call another tool
        other = check_anti_loop("run_command", {"CommandLine": "ls"}, conv_id=conv_id, state_dir=self.state_dir)
        self.assertEqual(other["decision"], "allow")

        # Resume view_file -> streak was broken
        res = check_anti_loop("view_file", args, conv_id=conv_id, state_dir=self.state_dir)
        self.assertEqual(res["decision"], "allow")

    def test_conversation_isolation(self):
        """Redundant executions in conv_1 do not trigger denials in conv_2."""
        tool_name = "manage_task"
        tool_args = {"Action": "status", "TaskId": "task-1"}

        # Trip conv_1
        for _ in range(3):
            check_anti_loop(tool_name, tool_args, conv_id="conv-1", state_dir=self.state_dir)
        trip_conv1 = check_anti_loop(tool_name, tool_args, conv_id="conv-1", state_dir=self.state_dir)
        self.assertEqual(trip_conv1["decision"], "deny")

        # conv_2 is clean
        res_conv2 = check_anti_loop(tool_name, tool_args, conv_id="conv-2", state_dir=self.state_dir)
        self.assertEqual(res_conv2["decision"], "allow")

    def test_corrupted_history_gracefully_handled(self):
        """Corrupted JSON in state file is safely recovered without crashing."""
        conv_id = "test-corrupt"
        history_file = self.state_dir / f"history_{conv_id}.json"
        self.state_dir.mkdir(parents=True, exist_ok=True)
        history_file.write_text("NOT_VALID_JSON{[[", encoding="utf-8")

        res = check_anti_loop("view_file", {"AbsolutePath": "/a.py"}, conv_id=conv_id, state_dir=self.state_dir)
        self.assertEqual(res["decision"], "allow")

    def test_cli_subprocess_contract(self):
        """Verify the script executed correctly consumes stdin and emits valid JSON."""
        payload = {
            "conversationId": "cli-test-conv",
            "toolCall": {
                "name": "view_file",
                "args": {"AbsolutePath": "/workspace/main.py"},
            },
        }

        with patch.dict(os.environ, {"PSL_HARNESS_STATE_DIR": str(self.state_dir)}):
            with patch("sys.stdin", io.StringIO(json.dumps(payload))), patch("sys.stdout", new_callable=io.StringIO) as mock_out:
                anti_loop_main()
                out = json.loads(mock_out.getvalue().strip())
                self.assertEqual(out["decision"], "allow")

    def test_rolling_frequency_window_detection(self):
        """Tool signature appearing >= 4 times within 15 calls is denied by frequency breaker."""
        conv_id = "test-freq-conv"
        tool_a = ("grep_search", {"Query": "pattern", "SearchPath": "/workspace"})

        # Call A 3 times interleaved with unique calls so consecutive repeat is not tripped
        res1 = check_anti_loop(tool_a[0], tool_a[1], conv_id=conv_id, state_dir=self.state_dir)
        self.assertEqual(res1["decision"], "allow")

        res_b1 = check_anti_loop("view_file", {"AbsolutePath": "/a.txt"}, conv_id=conv_id, state_dir=self.state_dir)
        self.assertEqual(res_b1["decision"], "allow")

        res2 = check_anti_loop(tool_a[0], tool_a[1], conv_id=conv_id, state_dir=self.state_dir)
        self.assertEqual(res2["decision"], "allow")

        res_b2 = check_anti_loop("view_file", {"AbsolutePath": "/b.txt"}, conv_id=conv_id, state_dir=self.state_dir)
        self.assertEqual(res_b2["decision"], "allow")

        res3 = check_anti_loop(tool_a[0], tool_a[1], conv_id=conv_id, state_dir=self.state_dir)
        self.assertEqual(res3["decision"], "allow")

        res_b3 = check_anti_loop("view_file", {"AbsolutePath": "/c.txt"}, conv_id=conv_id, state_dir=self.state_dir)
        self.assertEqual(res_b3["decision"], "allow")

        # 4th occurrence of tool_a within 7 calls trips rolling frequency window!
        res4 = check_anti_loop(tool_a[0], tool_a[1], conv_id=conv_id, state_dir=self.state_dir)
        self.assertEqual(res4["decision"], "deny")
        self.assertIn("PSL Anti-Loop Guard", res4["reason"])
        self.assertIn("sliding window", res4["reason"])
        self.assertIn("grep_search", res4["reason"])

    def test_ngram_cyclic_detection_period_2(self):
        """A -> B -> A -> B repeating sequence (period 2) is detected and denied on second B."""
        conv_id = "test-ngram-p2"
        tool_a = ("run_command", {"CommandLine": "git status"})
        tool_b = ("view_file", {"AbsolutePath": "/workspace/log.txt"})

        # 1. A
        res1 = check_anti_loop(tool_a[0], tool_a[1], conv_id=conv_id, state_dir=self.state_dir)
        self.assertEqual(res1["decision"], "allow")
        # 2. B
        res2 = check_anti_loop(tool_b[0], tool_b[1], conv_id=conv_id, state_dir=self.state_dir)
        self.assertEqual(res2["decision"], "allow")
        # 3. A
        res3 = check_anti_loop(tool_a[0], tool_a[1], conv_id=conv_id, state_dir=self.state_dir)
        self.assertEqual(res3["decision"], "allow")
        # 4. B completes 2nd cycle of [A, B] -> trips cyclic detector!
        res4 = check_anti_loop(tool_b[0], tool_b[1], conv_id=conv_id, state_dir=self.state_dir)
        self.assertEqual(res4["decision"], "deny")
        self.assertIn("PSL Anti-Loop Guard", res4["reason"])
        self.assertIn("cyclic tool execution pattern of period 2", res4["reason"])
        self.assertIn("run_command -> view_file", res4["reason"])

    def test_ngram_cyclic_detection_period_3(self):
        """A -> B -> C -> A -> B -> C repeating sequence (period 3) is detected and denied on second C."""
        conv_id = "test-ngram-p3"
        tool_a = ("grep_search", {"Query": "target"})
        tool_b = ("view_file", {"AbsolutePath": "/src/main.py"})
        tool_c = ("run_command", {"CommandLine": "python3 -m unittest"})

        # Cycle 1: A -> B -> C
        self.assertEqual(check_anti_loop(tool_a[0], tool_a[1], conv_id=conv_id, state_dir=self.state_dir)["decision"], "allow")
        self.assertEqual(check_anti_loop(tool_b[0], tool_b[1], conv_id=conv_id, state_dir=self.state_dir)["decision"], "allow")
        self.assertEqual(check_anti_loop(tool_c[0], tool_c[1], conv_id=conv_id, state_dir=self.state_dir)["decision"], "allow")

        # Cycle 2: A -> B -> C (trips on C)
        self.assertEqual(check_anti_loop(tool_a[0], tool_a[1], conv_id=conv_id, state_dir=self.state_dir)["decision"], "allow")
        self.assertEqual(check_anti_loop(tool_b[0], tool_b[1], conv_id=conv_id, state_dir=self.state_dir)["decision"], "allow")
        res_c2 = check_anti_loop(tool_c[0], tool_c[1], conv_id=conv_id, state_dir=self.state_dir)
        self.assertEqual(res_c2["decision"], "deny")
        self.assertIn("PSL Anti-Loop Guard", res_c2["reason"])
        self.assertIn("cyclic tool execution pattern of period 3", res_c2["reason"])
        self.assertIn("grep_search -> view_file -> run_command", res_c2["reason"])

    def test_history_window_expands_to_30(self):
        """Verifies history window holds up to 30 items."""
        conv_id = "test-history-30"
        for i in range(35):
            check_anti_loop("run_command", {"CommandLine": f"echo {i}"}, conv_id=conv_id, state_dir=self.state_dir)

        history_file = self.state_dir / f"history_{conv_id}.json"
        history = json.loads(history_file.read_text(encoding="utf-8"))
        self.assertEqual(len(history), 30)
        self.assertEqual(history[0]["args"]["CommandLine"], "echo 5")
        self.assertEqual(history[-1]["args"]["CommandLine"], "echo 34")

    def test_task_log_single_inspection_allowed(self):
        """Single or up to 2 task log inspections are permitted (e.g. for diagnosing failure)."""
        conv_id = "test-task-inspect-allow"
        cmd = "cat /home/kuasha/.gemini/antigravity/brain/123/.system_generated/tasks/task-1.log"

        res1 = check_anti_loop("run_command", {"CommandLine": cmd}, conv_id=conv_id, state_dir=self.state_dir)
        self.assertEqual(res1["decision"], "allow")

        res2 = check_anti_loop("run_command", {"CommandLine": cmd}, conv_id=conv_id, state_dir=self.state_dir)
        self.assertEqual(res2["decision"], "allow")

    def test_consecutive_task_log_polling_denied(self):
        """3 consecutive task log inspections trip the anti-polling breaker."""
        conv_id = "test-task-inspect-deny"
        cmd1 = "cat /workspace/.system_generated/tasks/task-1.log"
        cmd2 = "tail -n 10 /workspace/.system_generated/tasks/task-1.log"
        cmd3 = "python3 -c 'open(/workspace/.system_generated/tasks/task-1.log)'"

        self.assertEqual(check_anti_loop("run_command", {"CommandLine": cmd1}, conv_id=conv_id, state_dir=self.state_dir)["decision"], "allow")
        self.assertEqual(check_anti_loop("run_command", {"CommandLine": cmd2}, conv_id=conv_id, state_dir=self.state_dir)["decision"], "allow")

        res3 = check_anti_loop("run_command", {"CommandLine": cmd3}, conv_id=conv_id, state_dir=self.state_dir)
        self.assertEqual(res3["decision"], "deny")
        self.assertIn("PSL Anti-Loop Guard", res3["reason"])
        self.assertIn("consecutive background task inspections", res3["reason"])

    def test_rolling_task_log_polling_denied(self):
        """Interleaved task inspections appearing >= 3 times in 10 calls are denied."""
        conv_id = "test-task-rolling-deny"
        log_cmd = "tail -n 5 /workspace/.system_generated/tasks/task-2.log"

        # 1st inspection
        self.assertEqual(check_anti_loop("run_command", {"CommandLine": log_cmd}, conv_id=conv_id, state_dir=self.state_dir)["decision"], "allow")
        # Interleaved generic command
        self.assertEqual(check_anti_loop("run_command", {"CommandLine": "git status"}, conv_id=conv_id, state_dir=self.state_dir)["decision"], "allow")
        # 2nd inspection
        self.assertEqual(check_anti_loop("run_command", {"CommandLine": log_cmd}, conv_id=conv_id, state_dir=self.state_dir)["decision"], "allow")
        # Interleaved generic command
        self.assertEqual(check_anti_loop("run_command", {"CommandLine": "ls -l"}, conv_id=conv_id, state_dir=self.state_dir)["decision"], "allow")
        # 3rd inspection within sliding window of 10
        res = check_anti_loop("run_command", {"CommandLine": log_cmd}, conv_id=conv_id, state_dir=self.state_dir)
        self.assertEqual(res["decision"], "deny")
        self.assertIn("PSL Anti-Loop Guard", res["reason"])
        self.assertIn("sliding window", res["reason"])

    def test_view_file_task_log_polling_denied(self):
        """view_file tool calls targeting task logs are also intercepted."""
        conv_id = "test-task-view-deny"
        args = {"AbsolutePath": "/home/user/.gemini/antigravity/brain/session/.system_generated/tasks/task-9.log"}

        self.assertEqual(check_anti_loop("view_file", args, conv_id=conv_id, state_dir=self.state_dir)["decision"], "allow")
        self.assertEqual(check_anti_loop("view_file", args, conv_id=conv_id, state_dir=self.state_dir)["decision"], "allow")
        res3 = check_anti_loop("view_file", args, conv_id=conv_id, state_dir=self.state_dir)
        self.assertEqual(res3["decision"], "deny")
        self.assertIn("PSL Anti-Loop Guard", res3["reason"])

    def test_task_path_source_files_not_misclassified_as_task_logs(self):
        """Legitimate source files or commands referencing task directories without .log are not treated as background task logs."""
        conv_id = "test-task-source-files"

        # 3 consecutive distinct view_file calls on source files under /tasks/
        for fname in ["task-queue.ts", "task-worker.ts", "task-runner.ts"]:
            res = check_anti_loop("view_file", {"AbsolutePath": f"/workspace/src/tasks/{fname}"}, conv_id=conv_id, state_dir=self.state_dir)
            self.assertEqual(res["decision"], "allow", f"Failed to allow source file {fname}")

        # 3 consecutive distinct commands inspecting source files under /tasks/
        for fname in ["task-runner.py", "task-worker.py", "task-scheduler.py"]:
            res = check_anti_loop("run_command", {"CommandLine": f"cat /workspace/app/tasks/{fname}"}, conv_id=conv_id, state_dir=self.state_dir)
            self.assertEqual(res["decision"], "allow", f"Failed to allow source file command {fname}")

        # 3 consecutive commands containing .system_generated/tasks without .log (e.g. database query, directory check)
        for subcmd in ["COUNT(*)", "DISTINCT session_id", "MIN(step_index)"]:
            cmd = f"python3 -c \"SELECT {subcmd} FROM logs WHERE path LIKE '%.system_generated/tasks%'\""
            res = check_anti_loop("run_command", {"CommandLine": cmd}, conv_id=conv_id, state_dir=self.state_dir)
            self.assertEqual(res["decision"], "allow", f"Failed to allow SQL command {cmd}")

    def test_grep_search_task_log_polling_denied(self):
        """grep_search targeting task log paths or task directory is denied on 3 consecutive inspections."""
        conv_id = "test-task-grep-deny"
        args1 = {"SearchPath": "/home/user/.gemini/antigravity/brain/session/.system_generated/tasks/task-531.log", "Query": "server.js"}
        args2 = {"SearchPath": "/home/user/.gemini/antigravity/brain/session/.system_generated/tasks/task-531.log", "Query": "FAIL"}
        args3 = {"SearchPath": "/home/user/.gemini/antigravity/brain/session/.system_generated/tasks/task-531.log", "Query": "skip"}

        self.assertEqual(check_anti_loop("grep_search", args1, conv_id=conv_id, state_dir=self.state_dir)["decision"], "allow")
        self.assertEqual(check_anti_loop("grep_search", args2, conv_id=conv_id, state_dir=self.state_dir)["decision"], "allow")
        res3 = check_anti_loop("grep_search", args3, conv_id=conv_id, state_dir=self.state_dir)
        self.assertEqual(res3["decision"], "deny")
        self.assertIn("PSL Anti-Loop Guard", res3["reason"])

    def test_grep_search_repo_query_not_misclassified(self):
        """grep_search querying task string in repository source code is not treated as task log polling."""
        conv_id = "test-task-grep-repo-allow"
        for q in ["task-", ".system_generated/tasks", "background_task"]:
            args = {"SearchPath": "/workspace/harness/hooks", "Query": q}
            res = check_anti_loop("grep_search", args, conv_id=conv_id, state_dir=self.state_dir)
            self.assertEqual(res["decision"], "allow")


if __name__ == "__main__":
    unittest.main()
