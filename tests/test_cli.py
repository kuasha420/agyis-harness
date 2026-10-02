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
        """Verifies `psl status` prints repository and hook status."""
        with patch("sys.stdout", new_callable=io.StringIO) as mock_out:
            code = main(["status"])
            self.assertEqual(code, 0)
            out = mock_out.getvalue()
            self.assertIn("PSL Harness for Google Antigravity", out)
            self.assertIn("Active Lifecycle Hooks", out)

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


if __name__ == "__main__":
    unittest.main()
