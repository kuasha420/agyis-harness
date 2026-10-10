#!/usr/bin/env python3
"""
Unit tests for harness/hooks/runner.py (ADR-016 / Issue #31)
Verifies fail-open deadlock prevention, lifecycle hook dispatch, and error telemetry.
"""

from __future__ import annotations

import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import MagicMock, patch

from harness.hooks import runner


class TestHookRunner(unittest.TestCase):
    def setUp(self):
        self.maxDiff = None
        self.temp_dir = tempfile.TemporaryDirectory()
        self.old_state_dir = os.environ.get("PSL_HARNESS_STATE_DIR")
        os.environ["PSL_HARNESS_STATE_DIR"] = self.temp_dir.name

    def tearDown(self):
        if self.old_state_dir is not None:
            os.environ["PSL_HARNESS_STATE_DIR"] = self.old_state_dir
        else:
            os.environ.pop("PSL_HARNESS_STATE_DIR", None)
        self.temp_dir.cleanup()

    def test_resolve_hook_module_canonical(self):
        """Verifies canonical hook names resolve to proper module paths."""
        self.assertEqual(runner.resolve_hook_module("anti-drift"), "harness.hooks.anti_drift_hook")
        self.assertEqual(runner.resolve_hook_module("anti-loop"), "harness.hooks.anti_loop_hook")
        self.assertEqual(runner.resolve_hook_module("command-safety"), "harness.hooks.command_safety_hook")
        self.assertEqual(runner.resolve_hook_module("compactor"), "harness.hooks.output_compactor_hook")
        self.assertEqual(runner.resolve_hook_module("verification-fence"), "harness.hooks.completion_fence_hook")

    def test_resolve_hook_module_aliases(self):
        """Verifies aliases and formatting (casing, underscores) normalize properly."""
        self.assertEqual(runner.resolve_hook_module("drift"), "harness.hooks.anti_drift_hook")
        self.assertEqual(runner.resolve_hook_module("ANTI_DRIFT"), "harness.hooks.anti_drift_hook")
        self.assertEqual(runner.resolve_hook_module("loop"), "harness.hooks.anti_loop_hook")
        self.assertEqual(runner.resolve_hook_module("safety"), "harness.hooks.command_safety_hook")
        self.assertEqual(runner.resolve_hook_module("output-compactor"), "harness.hooks.output_compactor_hook")
        self.assertEqual(runner.resolve_hook_module("fence"), "harness.hooks.completion_fence_hook")
        self.assertEqual(runner.resolve_hook_module("stop-fence"), "harness.hooks.completion_fence_hook")
        self.assertEqual(runner.resolve_hook_module("stop"), "harness.hooks.completion_fence_hook")

    def test_resolve_hook_module_unknown(self):
        """Unknown hook names raise ValueError."""
        with self.assertRaises(ValueError) as ctx:
            runner.resolve_hook_module("unrecognized-hook")
        self.assertIn("Unknown hook 'unrecognized-hook'", str(ctx.exception))

    def test_dispatch_command_safety(self):
        """Verifies normal execution of command-safety hook."""
        payload = {
            "conversationId": "test-runner-cs",
            "toolCall": {
                "name": "run_command",
                "args": {"CommandLine": "ls -la"},
            },
        }
        with patch("sys.stdout", new_callable=io.StringIO) as mock_out:
            code = runner.run_hook("command-safety", payload_str=json.dumps(payload))
            self.assertEqual(code, 0)
            res = json.loads(mock_out.getvalue().strip())
            self.assertEqual(res["decision"], "allow")

    def test_dispatch_anti_loop(self):
        """Verifies normal execution of anti-loop hook."""
        payload = {
            "conversationId": "test-runner-loop-new",
            "toolCall": {
                "name": "view_file",
                "args": {"AbsolutePath": "/workspace/main.py"},
            },
        }
        with patch("sys.stdout", new_callable=io.StringIO) as mock_out:
            code = runner.run_hook("anti-loop", payload_str=json.dumps(payload))
            self.assertEqual(code, 0)
            res = json.loads(mock_out.getvalue().strip())
            self.assertEqual(res["decision"], "allow")

    def test_dispatch_compactor(self):
        """Verifies normal execution of compactor hook (PostToolUse contract: {})."""
        payload = {
            "conversationId": "test-runner-compactor",
            "toolOutput": "sample short output",
            "exitCode": 0,
        }
        with patch("sys.stdout", new_callable=io.StringIO) as mock_out:
            code = runner.run_hook("compactor", payload_str=json.dumps(payload))
            self.assertEqual(code, 0)
            res = json.loads(mock_out.getvalue().strip())
            self.assertEqual(res, {})

    def test_dispatch_verification_fence(self):
        """Verifies normal execution of verification-fence hook."""
        payload = {
            "conversationId": "test-runner-fence",
            "action": "evaluate_stop",
        }
        with patch("sys.stdout", new_callable=io.StringIO) as mock_out:
            code = runner.run_hook("verification-fence", payload_str=json.dumps(payload))
            self.assertEqual(code, 0)
            res = json.loads(mock_out.getvalue().strip())
            self.assertEqual(res["decision"], "allow")

    def test_dispatch_anti_drift(self):
        """Verifies normal execution of anti-drift hook."""
        payload = {
            "conversationId": "test-runner-drift",
            "action": "check_drift",
            "target_file": "src/app.py",
            "plan_files": ["src/app.py"],
        }
        with patch("sys.stdout", new_callable=io.StringIO) as mock_out:
            code = runner.run_hook("anti-drift", payload_str=json.dumps(payload))
            self.assertEqual(code, 0)
            res = json.loads(mock_out.getvalue().strip())
            self.assertEqual(res["decision"], "allow")

    def test_fail_open_on_syntax_error(self):
        """When a hook module raises SyntaxError, runner emits allow and logs diagnostic trace."""
        with patch("sys.stdout", new_callable=io.StringIO) as mock_out, \
             patch("sys.stderr", new_callable=io.StringIO) as mock_err:
            with patch("harness.hooks.runner.importlib.import_module", side_effect=SyntaxError("invalid syntax at line 42")):
                code = runner.run_hook("command-safety", payload_str="{}")
                self.assertEqual(code, 0)
                res = json.loads(mock_out.getvalue().strip())
                self.assertEqual(res["decision"], "allow")
                err_text = mock_err.getvalue()
                self.assertIn("[PSL FAIL-OPEN HOOK RUNNER]", err_text)
                self.assertIn("SyntaxError", err_text)
                self.assertIn("invalid syntax at line 42", err_text)

    def test_fail_open_on_import_error(self):
        """When a hook module raises ImportError, runner emits allow and exits 0."""
        with patch("sys.stdout", new_callable=io.StringIO) as mock_out, \
             patch("sys.stderr", new_callable=io.StringIO) as mock_err:
            with patch("harness.hooks.runner.importlib.import_module", side_effect=ImportError("No module named 'missing_dependency'")):
                code = runner.run_hook("anti-drift", payload_str="{}")
                self.assertEqual(code, 0)
                res = json.loads(mock_out.getvalue().strip())
                self.assertEqual(res["decision"], "allow")
                err_text = mock_err.getvalue()
                self.assertIn("[PSL FAIL-OPEN HOOK RUNNER]", err_text)
                self.assertIn("ImportError", err_text)

    def test_fail_open_on_runtime_exception(self):
        """When a hook main() raises RuntimeError, runner emits allow and exits 0."""
        mock_mod = MagicMock()
        mock_mod.main.side_effect = RuntimeError("database or memory buffer corruption")

        with patch("sys.stdout", new_callable=io.StringIO) as mock_out, \
             patch("sys.stderr", new_callable=io.StringIO) as mock_err:
            with patch("harness.hooks.runner.importlib.import_module", return_value=mock_mod):
                code = runner.run_hook("anti-loop", payload_str="{}")
                self.assertEqual(code, 0)
                res = json.loads(mock_out.getvalue().strip())
                self.assertEqual(res["decision"], "allow")
                err_text = mock_err.getvalue()
                self.assertIn("[PSL FAIL-OPEN HOOK RUNNER]", err_text)
                self.assertIn("RuntimeError", err_text)

    def test_fail_open_on_missing_main_callable(self):
        """When a hook module lacks a callable main(), runner emits allow and exits 0."""
        mock_mod = MagicMock(spec=[])  # no attributes

        with patch("sys.stdout", new_callable=io.StringIO) as mock_out, \
             patch("sys.stderr", new_callable=io.StringIO) as mock_err:
            with patch("harness.hooks.runner.importlib.import_module", return_value=mock_mod):
                code = runner.run_hook("verification-fence", payload_str="{}")
                self.assertEqual(code, 0)
                res = json.loads(mock_out.getvalue().strip())
                self.assertEqual(res["decision"], "allow")
                err_text = mock_err.getvalue()
                self.assertIn("[PSL FAIL-OPEN HOOK RUNNER]", err_text)
                self.assertIn("AttributeError", err_text)

    def test_fail_open_on_non_zero_system_exit(self):
        """When a hook main() raises SystemExit(1), runner catches it, logs trace, and emits allow."""
        mock_mod = MagicMock()
        mock_mod.main.side_effect = SystemExit(1)

        with patch("sys.stdout", new_callable=io.StringIO) as mock_out, \
             patch("sys.stderr", new_callable=io.StringIO) as mock_err:
            with patch("harness.hooks.runner.importlib.import_module", return_value=mock_mod):
                code = runner.run_hook("command-safety", payload_str="{}")
                self.assertEqual(code, 0)
                res = json.loads(mock_out.getvalue().strip())
                self.assertEqual(res["decision"], "allow")
                err_text = mock_err.getvalue()
                self.assertIn("[PSL FAIL-OPEN HOOK RUNNER]", err_text)

    def test_fail_open_on_unknown_hook(self):
        """When unknown hook name is requested, runner logs error and emits allow without crashing."""
        with patch("sys.stdout", new_callable=io.StringIO) as mock_out, \
             patch("sys.stderr", new_callable=io.StringIO) as mock_err:
            code = runner.run_hook("nonexistent-hook-xyz")
            self.assertEqual(code, 0)
            res = json.loads(mock_out.getvalue().strip())
            self.assertEqual(res["decision"], "allow")
            err_text = mock_err.getvalue()
            self.assertIn("[PSL FAIL-OPEN HOOK RUNNER]", err_text)
            self.assertIn("Unknown hook 'nonexistent-hook-xyz'", err_text)

    def test_main_cli_entrypoint_no_args(self):
        """runner.main() without args writes usage and fail-open allow decision."""
        with patch("sys.stdout", new_callable=io.StringIO) as mock_out, \
             patch("sys.stderr", new_callable=io.StringIO) as mock_err:
            code = runner.main([])
            self.assertEqual(code, 0)
            res = json.loads(mock_out.getvalue().strip())
            self.assertEqual(res["decision"], "allow")
            self.assertIn("Usage:", mock_err.getvalue())

    def test_main_cli_entrypoint_valid_arg(self):
        """runner.main(['command-safety']) processes valid stdin payload cleanly."""
        payload = {
            "conversationId": "test-main-cs",
            "toolCall": {"name": "run_command", "args": {"CommandLine": "pwd"}},
        }
        with patch("sys.stdin", io.StringIO(json.dumps(payload))), \
             patch("sys.stdout", new_callable=io.StringIO) as mock_out:
            code = runner.main(["command-safety"])
            self.assertEqual(code, 0)
            res = json.loads(mock_out.getvalue().strip())
            self.assertEqual(res["decision"], "allow")

    def test_subprocess_standalone_execution(self):
        """Hermetic execution of runner via runner.main."""
        payload = json.dumps({
            "conversationId": "test-subprocess",
            "toolCall": {"name": "run_command", "args": {"CommandLine": "echo test"}},
        })
        with patch("sys.stdin", io.StringIO(payload)), patch("sys.stdout", new_callable=io.StringIO) as mock_out:
            ret = runner.main(["command-safety"])
            self.assertEqual(ret, 0)
            res = json.loads(mock_out.getvalue().strip())
            self.assertEqual(res["decision"], "allow")

    def test_subprocess_unknown_hook_fail_open(self):
        """Execution with invalid hook returns 0 and outputs fail-open allow JSON."""
        with patch("sys.stdin", io.StringIO("")), patch("sys.stdout", new_callable=io.StringIO) as mock_out, patch("sys.stderr", new_callable=io.StringIO) as mock_err:
            ret = runner.main(["invalid-hook-name"])
            self.assertEqual(ret, 0)
            res = json.loads(mock_out.getvalue().strip())
            self.assertEqual(res["decision"], "allow")
            self.assertIn("[PSL FAIL-OPEN HOOK RUNNER]", mock_err.getvalue())


if __name__ == "__main__":
    unittest.main()
