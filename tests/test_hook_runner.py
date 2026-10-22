#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Arafat Zahan (@kuasha420)
# Corporate Stewardship & Infrastructure: Purrfect Software Limited (PSL)
# Governed by: ICARO-42/b Ordinance (Company-Supported Personal IP Framework)

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
        self.old_psl_dir = os.environ.get("PSL_HARNESS_STATE_DIR")
        self.old_agyis_dir = os.environ.get("AGYIS_HARNESS_STATE_DIR")
        os.environ["PSL_HARNESS_STATE_DIR"] = self.temp_dir.name
        os.environ["AGYIS_HARNESS_STATE_DIR"] = self.temp_dir.name

    def tearDown(self):
        if self.old_psl_dir is not None:
            os.environ["PSL_HARNESS_STATE_DIR"] = self.old_psl_dir
        else:
            os.environ.pop("PSL_HARNESS_STATE_DIR", None)

        if self.old_agyis_dir is not None:
            os.environ["AGYIS_HARNESS_STATE_DIR"] = self.old_agyis_dir
        else:
            os.environ.pop("AGYIS_HARNESS_STATE_DIR", None)
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

    def test_inprocess_standalone_execution(self):
        """Hermetic in-process execution of runner via runner.main."""
        payload = json.dumps({
            "conversationId": "test-inprocess",
            "toolCall": {"name": "run_command", "args": {"CommandLine": "echo test"}},
        })
        with patch("sys.stdin", io.StringIO(payload)), patch("sys.stdout", new_callable=io.StringIO) as mock_out:
            ret = runner.main(["command-safety"])
            self.assertEqual(ret, 0)
            res = json.loads(mock_out.getvalue().strip())
            self.assertEqual(res["decision"], "allow")

    def test_inprocess_unknown_hook_fail_open(self):
        """In-process execution with invalid hook returns 0 and outputs fail-open allow JSON."""
        with patch("sys.stdin", io.StringIO("")), patch("sys.stdout", new_callable=io.StringIO) as mock_out, patch("sys.stderr", new_callable=io.StringIO) as mock_err:
            ret = runner.main(["invalid-hook-name"])
            self.assertEqual(ret, 0)
            res = json.loads(mock_out.getvalue().strip())
            self.assertEqual(res["decision"], "allow")
            self.assertIn("[PSL FAIL-OPEN HOOK RUNNER]", mock_err.getvalue())

    def test_subprocess_smoke_entrypoint(self):
        """Validates real subprocess invocation (python3 -m harness.hooks.runner <hook>)."""
        payload = json.dumps({
            "conversationId": "test-subprocess-smoke",
            "toolCall": {"name": "run_command", "args": {"CommandLine": "echo test"}},
        })
        sub_env = dict(
            os.environ,
            PSL_HARNESS_STATE_DIR=self.temp_dir.name,
            AGYIS_HARNESS_STATE_DIR=self.temp_dir.name,
        )
        # 1. Valid hook execution
        proc = subprocess.run(
            [sys.executable, "-m", "harness.hooks.runner", "command-safety"],
            input=payload,
            capture_output=True,
            text=True,
            cwd=str(Path(__file__).parent.parent),
            env=sub_env,
            timeout=5,
        )
        self.assertEqual(proc.returncode, 0)
        res = json.loads(proc.stdout.strip())
        self.assertEqual(res["decision"], "allow")

        # 2. Unknown hook fail-open execution
        proc_unknown = subprocess.run(
            [sys.executable, "-m", "harness.hooks.runner", "invalid-hook-name"],
            capture_output=True,
            text=True,
            cwd=str(Path(__file__).parent.parent),
            env=sub_env,
            timeout=5,
        )
        self.assertEqual(proc_unknown.returncode, 0)
        res_unknown = json.loads(proc_unknown.stdout.strip())
        self.assertEqual(res_unknown["decision"], "allow")
        # 3. Fail-open PostToolUse compactor execution emits {}
        proc_compactor = subprocess.run(
            [sys.executable, "-m", "harness.hooks.runner", "compactor"],
            input="INVALID_JSON",
            capture_output=True,
            text=True,
            cwd=str(Path(__file__).parent.parent),
            env=sub_env,
            timeout=5,
        )
        self.assertEqual(proc_compactor.returncode, 0)
        res_compactor = json.loads(proc_compactor.stdout.strip())
        self.assertEqual(res_compactor, {}, f"Subprocess fail-open compactor must emit {{}}, got: {res_compactor}")

    # --- PostToolUse Contract & Fail-Open Protection in Hook Runner ---

    def test_fail_open_post_tool_use_compactor_emits_empty_dict(self):
        """
        When compactor hook raises SyntaxError/ImportError/RuntimeError, runner MUST
        emit fail-open JSON {} (NOT {"decision": "allow"}), preventing protojson unmarshal errors.
        """
        for exc in (
            SyntaxError("syntax error in compactor"),
            ImportError("missing module in compactor"),
            RuntimeError("compactor buffer overflow"),
        ):
            with self.subTest(exc=type(exc).__name__):
                with patch("sys.stdout", new_callable=io.StringIO) as mock_out, \
                     patch("sys.stderr", new_callable=io.StringIO) as mock_err:
                    with patch("harness.hooks.runner.importlib.import_module", side_effect=exc):
                        code = runner.run_hook("compactor", payload_str="{}")
                        self.assertEqual(code, 0)
                        res = json.loads(mock_out.getvalue().strip())
                        self.assertEqual(
                            res,
                            {},
                            f"Fail-open compactor must emit {{}}, got: {res}",
                        )
                        self.assertIn("[PSL FAIL-OPEN HOOK RUNNER]", mock_err.getvalue())

    def test_fail_open_post_tool_use_verification_fence_emits_empty_dict(self):
        """
        When verification-fence hook crashes during a PostToolUse event,
        runner MUST emit fail-open JSON {} (NOT {"decision": "allow"}).
        """
        post_payloads = [
            json.dumps({"hookEvent": "PostToolUse", "toolCall": {"name": "run_command"}}),
            json.dumps({"toolCall": {"name": "run_command"}, "toolResponse": {"exitCode": 0}}),
            json.dumps({"toolCall": {"name": "run_command"}, "exitCode": 0}),
        ]

        for payload_str in post_payloads:
            with self.subTest(payload=payload_str):
                mock_mod = MagicMock()
                mock_mod.main.side_effect = RuntimeError("fence crashed in PostToolUse")

                with patch("sys.stdout", new_callable=io.StringIO) as mock_out, \
                     patch("sys.stderr", new_callable=io.StringIO) as mock_err:
                    with patch("harness.hooks.runner.importlib.import_module", return_value=mock_mod):
                        code = runner.run_hook("verification-fence", payload_str=payload_str)
                        self.assertEqual(code, 0)
                        res = json.loads(mock_out.getvalue().strip())
                        self.assertEqual(
                            res,
                            {},
                            f"Fail-open PostToolUse verification-fence must emit {{}}, got: {res}",
                        )

    def test_fail_open_pre_tool_use_retains_allow_decision(self):
        """
        Contrasts with PostToolUse: When a PreToolUse hook crashes,
        runner MUST emit fail-open {"decision": "allow"}.
        """
        pre_payload = json.dumps({
            "hookEvent": "PreToolUse",
            "toolCall": {"name": "write_to_file", "args": {"TargetFile": "test.py"}},
        })
        mock_mod = MagicMock()
        mock_mod.main.side_effect = RuntimeError("pre-tool hook crash")

        with patch("sys.stdout", new_callable=io.StringIO) as mock_out, \
             patch("sys.stderr", new_callable=io.StringIO):
            with patch("harness.hooks.runner.importlib.import_module", return_value=mock_mod):
                code = runner.run_hook("command-safety", payload_str=pre_payload)
                self.assertEqual(code, 0)
                res = json.loads(mock_out.getvalue().strip())
                self.assertEqual(res, {"decision": "allow"})

    # --- PreInvocation Contract & Fail-Open Protection in Hook Runner (Issue #82) ---

    def test_fail_open_pre_invocation_emits_inject_steps(self):
        """
        Issue #82 / AC1 & AC3: When a PreInvocation hook crashes (SyntaxError, ImportError, RuntimeError),
        runner MUST emit fail-open JSON {"injectSteps": []} (NOT {"decision": "allow"}),
        preventing language server protojson unmarshal errors.
        """
        for exc in (
            SyntaxError("syntax error in pre_invocation"),
            ImportError("missing module in pre_invocation"),
            RuntimeError("pre_invocation runtime crash"),
        ):
            with self.subTest(exc=type(exc).__name__):
                with patch("sys.stdout", new_callable=io.StringIO) as mock_out, \
                     patch("sys.stderr", new_callable=io.StringIO) as mock_err:
                    with patch("harness.hooks.runner.importlib.import_module", side_effect=exc):
                        code = runner.run_hook("pre-invocation", payload_str="{}")
                        self.assertEqual(code, 0)
                        res = json.loads(mock_out.getvalue().strip())
                        self.assertEqual(
                            res,
                            {"injectSteps": []},
                            f"Fail-open PreInvocation must emit {{'injectSteps': []}}, got: {res}",
                        )
                        self.assertIn("[PSL FAIL-OPEN HOOK RUNNER]", mock_err.getvalue())

    def test_fail_open_pre_invocation_from_payload_emits_inject_steps(self):
        """
        Issue #82: When hook_name is generic but payload indicates PreInvocation event,
        runner MUST emit {"injectSteps": []} on crash.
        """
        payloads = [
            json.dumps({"hookEvent": "PreInvocation"}),
            json.dumps({"event": "pre-invocation"}),
            json.dumps({"invocationNum": 42}),
        ]
        for payload_str in payloads:
            with self.subTest(payload=payload_str):
                mock_mod = MagicMock()
                mock_mod.main.side_effect = RuntimeError("hook crashed")

                with patch("sys.stdout", new_callable=io.StringIO) as mock_out, \
                     patch("sys.stderr", new_callable=io.StringIO):
                    with patch("harness.hooks.runner.importlib.import_module", return_value=mock_mod):
                        code = runner.run_hook("token-proximity", payload_str=payload_str)
                        self.assertEqual(code, 0)
                        res = json.loads(mock_out.getvalue().strip())
                        self.assertEqual(
                            res,
                            {"injectSteps": []},
                            f"Fail-open PreInvocation payload must emit {{'injectSteps': []}}, got: {res}",
                        )

    def test_subprocess_smoke_pre_invocation_fail_open(self):
        """
        Issue #82: Real subprocess execution of runner with 'pre-invocation'
        outputs {"injectSteps": []} with exit code 0.
        """
        sub_env = dict(os.environ)
        sub_env["PSL_HARNESS_STATE_DIR"] = self.temp_dir.name
        proc = subprocess.run(
            [sys.executable, "-m", "harness.hooks.runner", "pre-invocation"],
            input="{}",
            capture_output=True,
            text=True,
            cwd=str(Path(__file__).parent.parent),
            env=sub_env,
            timeout=5,
        )
        self.assertEqual(proc.returncode, 0)
        res = json.loads(proc.stdout.strip())
        self.assertEqual(res, {"injectSteps": []})


if __name__ == "__main__":
    unittest.main()
