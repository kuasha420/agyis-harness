#!/usr/bin/env python3
"""
Unit and integration tests for harness/cli.py
"""

import io
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

from harness.cli import main


class TestPslCli(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.orig_state_dir = os.environ.get("PSL_HARNESS_STATE_DIR")
        os.environ["PSL_HARNESS_STATE_DIR"] = self.temp_dir.name

    def tearDown(self):
        if self.orig_state_dir is not None:
            os.environ["PSL_HARNESS_STATE_DIR"] = self.orig_state_dir
        else:
            os.environ.pop("PSL_HARNESS_STATE_DIR", None)
        self.temp_dir.cleanup()

    def test_cli_help(self):
        """Verifies --help outputs usage and exits cleanly with 0."""
        with patch("sys.stdout", new_callable=io.StringIO) as mock_out:
            with self.assertRaises(SystemExit) as cm:
                main(["--help"])
            self.assertEqual(cm.exception.code, 0)
            self.assertIn("PSL Harness for Google Antigravity", mock_out.getvalue())

    def test_cli_version(self):
        """Verifies --version prints package version."""
        with patch("sys.stdout", new_callable=io.StringIO) as mock_out:
            with self.assertRaises(SystemExit) as cm:
                main(["--version"])
            self.assertEqual(cm.exception.code, 0)
            self.assertIn("psl-agy-harness 0.1.0", mock_out.getvalue())

    def test_cli_status(self):
        """Verifies `psl status` prints repository, skills, agents, and hook status."""
        with patch("sys.stdout", new_callable=io.StringIO) as mock_out:
            code = main(["status"])
            self.assertEqual(code, 0)
            out = mock_out.getvalue()
            self.assertIn("PSL Harness for Google Antigravity", out)
            self.assertIn("Active Lifecycle Hooks", out)
            self.assertIn("Modular Skills:", out)
            self.assertIn("Specialist Subagents:", out)

    def test_cli_skills_subcommand(self):
        """Verifies `psl skills` lists skills and inspects details."""
        with patch("sys.stdout", new_callable=io.StringIO) as mock_out:
            code = main(["skills"])
            self.assertEqual(code, 0)
            out = mock_out.getvalue()
            self.assertIn("PSL Modular Skills", out)
            self.assertIn("psl-stack-shell", out)

        with patch("sys.stdout", new_callable=io.StringIO) as mock_out:
            code = main(["skills", "psl-stack-python"])
            self.assertEqual(code, 0)
            out = mock_out.getvalue()
            self.assertIn("Skill: psl-stack-python", out)

        with patch("sys.stdout", new_callable=io.StringIO) as mock_out:
            code = main(["skills", "--json"])
            self.assertEqual(code, 0)
            data = json.loads(mock_out.getvalue().strip())
            self.assertIsInstance(data, list)
            self.assertGreaterEqual(len(data), 8)

    def test_cli_agents_subcommand(self):
        """Verifies `psl agents` lists agents and inspects details."""
        with patch("sys.stdout", new_callable=io.StringIO) as mock_out:
            code = main(["agents"])
            self.assertEqual(code, 0)
            out = mock_out.getvalue()
            self.assertIn("PSL Specialist Subagents", out)
            self.assertIn("harness_builder", out)

        with patch("sys.stdout", new_callable=io.StringIO) as mock_out:
            code = main(["agents", "harness_reviewer"])
            self.assertEqual(code, 0)
            out = mock_out.getvalue()
            self.assertIn("Agent:       harness_reviewer", out)
            self.assertIn("Archetype:   hammer", out)

        with patch("sys.stdout", new_callable=io.StringIO) as mock_out:
            code = main(["agents", "--json"])
            self.assertEqual(code, 0)
            data = json.loads(mock_out.getvalue().strip())
            self.assertIsInstance(data, list)
            self.assertEqual(len(data), 3)

    def test_cli_hook_dispatch_safety(self):
        """Verifies `psl hook safety` dispatches to command_safety_hook."""
        payload = {
            "conversationId": "test-cli-hook",
            "toolCall": {
                "name": "run_command",
                "args": {"CommandLine": "ls -la"},
            },
        }
        with patch("sys.stdin", io.StringIO(json.dumps(payload))), \
             patch("sys.stdout", new_callable=io.StringIO) as mock_out:
            code = main(["hook", "safety"])
            self.assertEqual(code, 0)
            res = json.loads(mock_out.getvalue().strip())
            self.assertEqual(res["decision"], "allow")

    def test_cli_hook_dispatch_anti_loop(self):
        """Verifies `psl hook anti-loop` dispatches to anti_loop_hook."""
        payload = {
            "conversationId": "test-cli-anti-loop",
            "toolCall": {
                "name": "view_file",
                "args": {"AbsolutePath": "/workspace/test.py"},
            },
        }
        with patch("sys.stdin", io.StringIO(json.dumps(payload))), \
             patch("sys.stdout", new_callable=io.StringIO) as mock_out:
            code = main(["hook", "anti-loop"])
            self.assertEqual(code, 0)
            res = json.loads(mock_out.getvalue().strip())
            self.assertEqual(res["decision"], "allow")

    def test_cli_hook_dispatch_compactor(self):
        """Verifies `psl hook compactor` dispatches to output_compactor_hook."""
        payload = {
            "conversationId": "test-cli-compactor",
            "toolOutput": "Short output",
            "exitCode": 0,
        }
        with patch("sys.stdin", io.StringIO(json.dumps(payload))), \
             patch("sys.stdout", new_callable=io.StringIO) as mock_out:
            code = main(["hook", "compactor"])
            self.assertEqual(code, 0)
            res = json.loads(mock_out.getvalue().strip())
            self.assertEqual(res, {})

    def test_cli_hook_dispatch_verification_fence(self):
        """Verifies `psl hook verification-fence` dispatches cleanly to completion_fence_hook."""
        payload = {
            "conversationId": "test-cli-fence",
            "action": "evaluate_stop",
        }
        with patch("sys.stdin", io.StringIO(json.dumps(payload))), \
             patch("sys.stdout", new_callable=io.StringIO) as mock_out:
            code = main(["hook", "verification-fence"])
            self.assertEqual(code, 0)
            res = json.loads(mock_out.getvalue().strip())
            self.assertEqual(res["decision"], "allow")

    def test_cli_test_runner(self):
        """Verifies `psl test` runs discovery against an isolated test folder without self-recursion."""
        sample_test = (
            "import unittest\n"
            "class Sample(unittest.TestCase):\n"
            "    def test_ok(self):\n"
            "        self.assertTrue(True)\n"
        )
        sample_file = Path(self.temp_dir.name) / "test_sample.py"
        sample_file.write_text(sample_test, encoding="utf-8")

        with patch("sys.stdout", new_callable=io.StringIO), \
             patch("sys.stderr", new_callable=io.StringIO):
            code = main(["test", "-s", self.temp_dir.name])
            self.assertEqual(code, 0)

    def test_cli_test_runner_clears_verification_states(self):
        """Verifies `psl test` clears dirty flags across active state files."""
        from harness.hooks import completion_fence_hook
        # Record dirty states in multiple conversation files
        completion_fence_hook.record_edit("src/file1.py", conv_id="conv-1")
        completion_fence_hook.record_edit("src/file2.py", conv_id="conv-2")

        state1 = completion_fence_hook.load_state(conv_id="conv-1")
        self.assertTrue(state1["code_dirty"])

        sample_test = (
            "import unittest\n"
            "class Sample(unittest.TestCase):\n"
            "    def test_ok(self):\n"
            "        self.assertTrue(True)\n"
        )
        sample_file = Path(self.temp_dir.name) / "test_clear_state_sample.py"
        sample_file.write_text(sample_test, encoding="utf-8")

        with patch("sys.stdout", new_callable=io.StringIO), \
             patch("sys.stderr", new_callable=io.StringIO):
            code = main(["test", "-s", self.temp_dir.name])
            self.assertEqual(code, 0)

        # Both states should now have code_dirty = False
        state1_after = completion_fence_hook.load_state(conv_id="conv-1")
        state2_after = completion_fence_hook.load_state(conv_id="conv-2")
        self.assertFalse(state1_after["code_dirty"])
        self.assertFalse(state2_after["code_dirty"])
        self.assertEqual(state1_after["block_count"], 0)
        self.assertEqual(state2_after["block_count"], 0)

    def test_cli_audit_session_json(self):
        """Verifies `psl audit session --json` parses and emits report."""
        dummy_report = {
            "session_id": "test-session-1234",
            "coordinator": {
                "compacted_transcript": {"total_steps": 10},
                "full_transcript": {"total_steps": 10, "total_chars": 500, "estimated_tokens": 125, "tool_errors": 0},
                "compaction_savings_chars": 0,
                "compaction_savings_pct": 0.0,
            },
            "subagents": [],
            "collective_pipeline": {"total_steps": 10, "total_tools": 5, "total_tokens": 125, "offload_step_pct": 0, "offload_tool_pct": 0, "offload_token_pct": 0}
        }
        with patch("pipeline.analyze_live_session.find_latest_session_dir", return_value=Path(self.temp_dir.name)), \
             patch("pipeline.analyze_live_session.analyze_session", return_value=dummy_report), \
             patch("sys.stdout", new_callable=io.StringIO) as mock_out:
            code = main(["audit", "session", "--json"])
            self.assertEqual(code, 0)
            data = json.loads(mock_out.getvalue())
            self.assertEqual(data["session_id"], "test-session-1234")

    def test_cli_sync(self):
        """Verifies `psl sync` dispatches session audit with save_db=True."""
        dummy_report = {
            "session_id": "test-session-sync",
            "coordinator": {
                "compacted_transcript": {"total_steps": 5},
                "full_transcript": {"total_steps": 5, "total_chars": 200, "estimated_tokens": 50, "tool_errors": 0},
                "compaction_savings_chars": 0,
                "compaction_savings_pct": 0.0,
            },
            "subagents": [],
            "collective_pipeline": {"total_steps": 5, "total_tools": 2, "total_tokens": 50, "offload_step_pct": 0, "offload_tool_pct": 0, "offload_token_pct": 0}
        }
        with patch("pipeline.analyze_live_session.find_latest_session_dir", return_value=Path(self.temp_dir.name)), \
             patch("pipeline.analyze_live_session.analyze_session", return_value=dummy_report), \
             patch("sys.stdout", new_callable=io.StringIO) as mock_out:
            code = main(["sync", "--json"])
            self.assertEqual(code, 0)
            data = json.loads(mock_out.getvalue())
            self.assertEqual(data["session_id"], "test-session-sync")


if __name__ == "__main__":
    unittest.main()
