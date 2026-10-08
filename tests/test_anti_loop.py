#!/usr/bin/env python3
"""
Unit and integration tests for harness/hooks/anti_loop_hook.py
"""

import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from harness.hooks.anti_loop_hook import check_anti_loop


class TestAntiLoopHook(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.state_dir = Path(self.temp_dir.name)

    def tearDown(self):
        self.temp_dir.cleanup()

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
        """Verify the script executed as a subprocess correctly consumes stdin and emits valid JSON."""
        hook_script = Path(__file__).parent.parent / "harness/hooks/anti_loop_hook.py"

        payload = {
            "conversationId": "cli-test-conv",
            "toolCall": {
                "name": "view_file",
                "args": {"AbsolutePath": "/workspace/main.py"},
            },
        }

        env = {"PSL_HARNESS_STATE_DIR": str(self.state_dir)}
        proc = subprocess.run(
            [sys.executable, str(hook_script)],
            input=json.dumps(payload),
            text=True,
            capture_output=True,
            env={**env, "PATH": "/usr/bin:/bin"},
        )
        self.assertEqual(proc.returncode, 0)
        out = json.loads(proc.stdout.strip())
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


if __name__ == "__main__":
    unittest.main()
