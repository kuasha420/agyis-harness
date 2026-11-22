# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Arafat Zahan (@kuasha420)
# Corporate Stewardship & Infrastructure: Purrfect Software Limited (PSL)
# Governed by: ICARO-42/b Ordinance (Company-Supported Personal IP Framework)

"""
Hermetic Regression Suite for Antigravity v2.34.0 Lifecycle Hooks Compatibility (Epic #118).
Validates DRIFT-P0-02, DRIFT-P0-03, DRIFT-P1-08, DRIFT-P2-01, and DRIFT-P2-02 invariants.
"""

from __future__ import annotations

import io
import json
import os
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import patch

from harness.hooks.anti_drift_hook import (
    _extract_target_file,
    _is_mutating_shell_command,
    check_auditor_write_block,
    check_plan_mode_lock,
)
from harness.hooks.command_safety_hook import (
    check_pause_safety,
    normalize_mcp_tool_call,
)
from harness.hooks.completion_fence_hook import (
    _handle_post_tool_run_command,
    _handle_tool_call_event,
)
from harness.hooks.fence_classifiers import (
    CODE_MUTATION_TOOLS,
    extract_exit_code,
    is_manifest_verified,
)
from harness.hooks.fence_gates import evaluate_stop
from harness.hooks.fence_state import get_brain_dir
from harness.hooks.output_compactor_hook import (
    READ_FILE_MAX_OUTPUT_CHARS,
    main as compactor_main,
    process_payload,
)
from harness.hooks.pre_invocation_hook import evaluate_pre_invocation
from harness.hooks.role_pinning import resolve_cid_state_dir
from harness.hooks.runner import is_post_tool_use_context, is_pre_invocation_context
from harness.hooks.token_proximity_guard import _velocity_from_telemetry_db

REPO_ROOT = Path(__file__).resolve().parent.parent


class TestHooksV234Compat(unittest.TestCase):
    """Hermetic verification of Antigravity v2.34.0 lifecycle hook drift fixes."""

    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.state_dir = Path(self.tmp.name)

    def tearDown(self) -> None:
        self.tmp.cleanup()

    # -------------------------------------------------------------------------
    # 1. Symlink & hooks.json Matchers (DRIFT-P0-02, DRIFT-P1-08)
    # -------------------------------------------------------------------------
    def test_hooks_json_symlink_and_matchers(self) -> None:
        root_hooks = REPO_ROOT / "hooks.json"
        self.assertTrue(root_hooks.is_symlink(), "Root hooks.json must be a symlink")
        self.assertEqual(os.readlink(root_hooks), "harness/hooks/hooks.json")

        hooks_target = REPO_ROOT / "harness" / "hooks" / "hooks.json"
        cfg = json.loads(hooks_target.read_text(encoding="utf-8"))

        drift_matcher = cfg["psl-anti-drift-guard"]["PreToolUse"][0]["matcher"]
        self.assertIn("write_file", drift_matcher)
        self.assertIn("edit_file", drift_matcher)
        self.assertIn("run_command", drift_matcher)

        loop_matcher = cfg["psl-anti-loop-guard"]["PreToolUse"][0]["matcher"]
        self.assertIn("read_file", loop_matcher)
        self.assertIn("swarm", loop_matcher)
        self.assertIn("run_workflow", loop_matcher)

        cmd_matcher = cfg["psl-command-safety-guard"]["PreToolUse"][0]["matcher"]
        self.assertIn("swarm", cmd_matcher)
        self.assertIn("run_workflow", cmd_matcher)
        self.assertIn("mcp_.*", cmd_matcher)

        compactor_matcher = cfg["psl-output-compactor"]["PostToolUse"][0]["matcher"]
        self.assertIn("read_file", compactor_matcher)

        fence_pre = cfg["psl-stop-verification-fence"]["PreToolUse"][0]["matcher"]
        self.assertIn("write_file", fence_pre)
        fence_post = cfg["psl-stop-verification-fence"]["PostToolUse"][0]["matcher"]
        self.assertIn("mcp_.*", fence_post)

    # -------------------------------------------------------------------------
    # 2. PreToolUse Tool Names, Uppercase Args & Q5 Read-Only Shell Guard (DRIFT-P0-02)
    # -------------------------------------------------------------------------
    def test_anti_drift_uppercase_path_and_plan_mode_lock(self) -> None:
        payload = {
            "mode": "plan",
            "toolCall": {
                "name": "write_file",
                "args": {"Path": "/workspace/src/main.py", "Content": "print('hello')"},
            },
        }
        self.assertEqual(_extract_target_file(payload), "/workspace/src/main.py")
        decision = check_plan_mode_lock(payload)
        self.assertIsNotNone(decision)
        self.assertEqual(decision["decision"], "deny")

    def test_q5_read_only_shell_guard_denials(self) -> None:
        mutating_commands = [
            "rm -rf build/",
            "mkdir -p dist",
            "touch foo.txt",
            "sed -i 's/a/b/g' file.txt",
            "git reset --hard HEAD~1",
            "cat foo > harness/bar.py",
            "echo 1 >> output.txt",
            "python3 -c \"import os; open('test.txt', 'w').write('x')\"",
            "node -e \"const fs = require('fs'); fs.writeFileSync('a.txt', 'b')\"",
        ]
        for cmd in mutating_commands:
            with self.subTest(cmd=cmd):
                self.assertTrue(_is_mutating_shell_command(cmd, allow_scratch=False))
                payload = {
                    "role": "agyis_reviewer",
                    "toolCall": {"name": "run_command", "args": {"CommandLine": cmd}},
                }
                block = check_auditor_write_block(payload)
                self.assertIsNotNone(block)
                self.assertEqual(block["decision"], "deny")

    def test_q5_read_only_shell_guard_safe_commands_allowed(self) -> None:
        safe_commands = [
            'rg "mkdir" harness/',
            'git log --grep="rm"',
            "git diff main",
            'echo "1 > 0"',
            "python3 -m harness.cli test",
            "pytest tests/ 2>&1 >/dev/null",
            "cat /dev/null > /tmp/test.log",
            "echo test > .agents/artifacts/report.md",
        ]
        for cmd in safe_commands:
            with self.subTest(cmd=cmd):
                self.assertFalse(_is_mutating_shell_command(cmd, allow_scratch=False))
                payload = {
                    "role": "agyis_reviewer",
                    "toolCall": {"name": "run_command", "args": {"CommandLine": cmd}},
                }
                self.assertIsNone(check_auditor_write_block(payload))

    def test_q5_investigator_scratch_allowance(self) -> None:
        scratch_cmd = "python3 scratch/repro.py > scratch/out.txt"
        self.assertFalse(_is_mutating_shell_command(scratch_cmd, allow_scratch=True))
        self.assertTrue(_is_mutating_shell_command(scratch_cmd, allow_scratch=False))

        payload = {
            "role": "agyis_investigator",
            "toolCall": {"name": "run_command", "args": {"CommandLine": scratch_cmd}},
        }
        self.assertIsNone(check_auditor_write_block(payload))

    def test_q5_custodian_commit_gate_exception(self) -> None:
        payload_git = {
            "role": "agyis_custodian",
            "toolCall": {"name": "run_command", "args": {"CommandLine": "git add -A && git commit -m 'test'"}},
        }
        self.assertIsNone(check_auditor_write_block(payload_git))

        payload_write = {
            "role": "agyis_custodian",
            "toolCall": {"name": "write_file", "args": {"Path": "/src/app.py", "Content": "code"}},
        }
        block = check_auditor_write_block(payload_write)
        self.assertIsNotNone(block)
        self.assertEqual(block["decision"], "deny")

    def test_command_safety_swarm_pause_and_eager_mcp(self) -> None:
        pause_file = self.state_dir / ".agents" / "artifacts" / "pause_gate.json"
        pause_file.parent.mkdir(parents=True, exist_ok=True)
        pause_file.write_text('{"status": "paused"}', encoding="utf-8")

        dec, reason = check_pause_safety("swarm", {"action": "kill", "name": "worker-1"}, workspace_dir=self.state_dir)
        self.assertEqual(dec, "deny")

        dec, _ = check_pause_safety("swarm", {"action": "status"}, workspace_dir=self.state_dir)
        self.assertEqual(dec, "allow")

        status, mod_args, rsn = normalize_mcp_tool_call(
            "mcp_rea_procedure_assembly",
            {"Address": "0x401000", "proc": "main"},
        )
        self.assertEqual(status, "allow")
        self.assertIsNotNone(mod_args)
        self.assertIn("procedure", mod_args)
        self.assertNotIn("Arguments", mod_args)

    # -------------------------------------------------------------------------
    # 3. PostToolUse Schema, Error Extraction & continuationActive (DRIFT-P0-03, DRIFT-P2-02)
    # -------------------------------------------------------------------------
    def test_runner_hook_event_name_recognition(self) -> None:
        self.assertTrue(is_pre_invocation_context("pre-invocation", json.dumps({"hookEventName": "PreInvocation"})))
        self.assertTrue(is_post_tool_use_context("verification-fence", json.dumps({"hookEventName": "PostToolUse"})))
        self.assertFalse(is_post_tool_use_context("verification-fence", json.dumps({"hookEventName": "PreToolUse"})))

    def test_completion_fence_error_payload_and_exit_code(self) -> None:
        self.assertEqual(extract_exit_code({"error": "Command failed with exit code 127"}), 127)
        self.assertEqual(extract_exit_code({"error": "process exited with code 2"}), 2)
        self.assertEqual(extract_exit_code({"error": "exit status 1"}), 1)
        self.assertEqual(extract_exit_code({"error": {"exitCode": 3}}), 3)

        payload_err = {
            "hookEventName": "PostToolUse",
            "toolCall": {"name": "run_command", "args": {"CommandLine": "python3 -m unittest"}},
            "error": "Command failed with exit code 1",
            "result": "AssertionError",
        }
        res = _handle_tool_call_event(payload_err, conv_id="test-err", state_dir=self.state_dir, cwd=self.state_dir, turn_id="t1")
        self.assertEqual(res, {})

    def test_completion_fence_success_clears_code_dirty(self) -> None:
        from harness.hooks.fence_state import load_state, save_state
        save_state({"code_dirty": True, "active_turn_id": "t1"}, conv_id="test-clean", state_dir=self.state_dir)

        payload_ok = {
            "hookEventName": "PostToolUse",
            "toolCall": {"name": "run_command", "args": {"CommandLine": "python3 -m harness.cli test"}},
            "result": "Ran 10 tests in 0.1s\n\nOK",
        }
        _handle_post_tool_run_command(
            "run_command",
            {"CommandLine": "python3 -m harness.cli test"},
            payload_ok,
            cmd="python3 -m harness.cli test",
            conv_id="test-clean",
            state_dir=self.state_dir,
            cwd=REPO_ROOT,
            turn_id="t1",
        )
        updated = load_state(conv_id="test-clean", state_dir=self.state_dir)
        self.assertFalse(updated.get("code_dirty", True))

    def test_continuation_active_allows_stop(self) -> None:
        payload = {"continuationActive": True}
        decision = evaluate_stop(conv_id="test-cont", state_dir=self.state_dir, payload=payload)
        self.assertEqual(decision, {"decision": "allow"})

    def test_rea_cleanroom_manifest_dispositions(self) -> None:
        from harness.cleanroom.obligation import scaffold_obligation_ledger
        ledger_path = self.state_dir / ".agents" / "ledger" / "obligation_ledger.json"
        scaffold_obligation_ledger(ledger_path)

        data = json.loads(ledger_path.read_text(encoding="utf-8"))
        data["reviewed_obligations"] = [
            {"obligation_id": "OBL-1", "title": "Test 1", "disposition": "active"},
            {"obligation_id": "OBL-2", "title": "Test 2", "disposition": "out-of-scope"},
        ]
        ledger_path.write_text(json.dumps(data), encoding="utf-8")
        self.assertTrue(is_manifest_verified(self.state_dir))

        data["reviewed_obligations"] = [
            {"obligation_id": "OBL-1", "title": "Test 1", "disposition": "satisfied"},
        ]
        ledger_path.write_text(json.dumps(data), encoding="utf-8")
        self.assertFalse(is_manifest_verified(self.state_dir))

    # -------------------------------------------------------------------------
    # 4. Output Compactor overwriteResult & Thresholds (DRIFT-P1-08)
    # -------------------------------------------------------------------------
    def test_output_compactor_thresholds_and_overwrite(self) -> None:
        self.assertEqual(READ_FILE_MAX_OUTPUT_CHARS, 32768)

        # >2KB run_command success -> overwriteResult emitted
        run_payload = {
            "conversationId": "comp-run",
            "toolCall": {"name": "run_command", "args": {"CommandLine": "cat big.txt"}},
            "output": "A" * 5000,
            "exitCode": 0,
        }
        with patch.dict(os.environ, {"PSL_HARNESS_STATE_DIR": str(self.state_dir)}):
            with patch("sys.stdin", io.StringIO(json.dumps(run_payload))), patch("sys.stdout", new_callable=io.StringIO) as out:
                compactor_main()
                res = json.loads(out.getvalue().strip())
                self.assertIn("overwriteResult", res)
                self.assertLess(len(res["overwriteResult"]), 5000)

        # run_command failure -> {} emitted verbatim
        err_payload = {
            "conversationId": "comp-err",
            "toolCall": {"name": "run_command", "args": {"CommandLine": "false"}},
            "output": "Error: " + ("E" * 5000),
            "exitCode": 1,
        }
        with patch.dict(os.environ, {"PSL_HARNESS_STATE_DIR": str(self.state_dir)}):
            with patch("sys.stdin", io.StringIO(json.dumps(err_payload))), patch("sys.stdout", new_callable=io.StringIO) as out:
                compactor_main()
                self.assertEqual(out.getvalue().strip(), "{}")

        # read_file <=32KB -> {} emitted verbatim
        rf_small_payload = {
            "conversationId": "comp-rf-small",
            "toolCall": {"name": "read_file", "args": {"Path": "/foo.txt"}},
            "output": "F" * 20000,
            "exitCode": 0,
        }
        with patch.dict(os.environ, {"PSL_HARNESS_STATE_DIR": str(self.state_dir)}):
            with patch("sys.stdin", io.StringIO(json.dumps(rf_small_payload))), patch("sys.stdout", new_callable=io.StringIO) as out:
                compactor_main()
                self.assertEqual(out.getvalue().strip(), "{}")

        # read_file >32KB -> overwriteResult emitted
        rf_big_payload = {
            "conversationId": "comp-rf-big",
            "toolCall": {"name": "read_file", "args": {"Path": "/large.txt"}},
            "output": "F" * 40000,
            "exitCode": 0,
        }
        with patch.dict(os.environ, {"PSL_HARNESS_STATE_DIR": str(self.state_dir)}):
            with patch("sys.stdin", io.StringIO(json.dumps(rf_big_payload))), patch("sys.stdout", new_callable=io.StringIO) as out:
                compactor_main()
                res = json.loads(out.getvalue().strip())
                self.assertIn("overwriteResult", res)
                self.assertLess(len(res["overwriteResult"]), 40000)

    # -------------------------------------------------------------------------
    # 5. Telemetry SQL Fix & systemMessage Migration (DRIFT-P2-01, DRIFT-P2-02)
    # -------------------------------------------------------------------------
    def test_token_proximity_real_telemetry_schema(self) -> None:
        db_path = self.state_dir / "telemetry.db"
        with sqlite3.connect(db_path) as conn:
            conn.execute("""
                CREATE TABLE sessions (
                    session_id TEXT PRIMARY KEY,
                    file_size_bytes INTEGER
                )
            """)
            conn.execute("""
                CREATE TABLE steps (
                    session_id TEXT,
                    step_index INTEGER,
                    created_at TEXT,
                    content_length INTEGER,
                    thinking_length INTEGER
                )
            """)
            conn.execute("INSERT INTO sessions VALUES ('sess-1', 40000)")
            conn.execute("INSERT INTO steps VALUES ('sess-1', 0, '2026-11-22T10:00:00Z', 1000, 200)")
            conn.execute("INSERT INTO steps VALUES ('sess-1', 1, '2026-11-22T10:01:00Z', 2000, 400)")

        metrics = _velocity_from_telemetry_db(db_path, "sess-1", window_seconds=300)
        self.assertIsNotNone(metrics)
        self.assertEqual(metrics["tokens"], (1200 + 2400) // 4)

    def test_app_data_dir_and_system_message_emitted(self) -> None:
        custom_brain = self.state_dir / "custom_app_data" / "brain"
        cid = "44444444-4444-4444-4444-444444444444"
        (custom_brain / cid / ".agyis").mkdir(parents=True, exist_ok=True)

        with patch.dict(os.environ, {"ANTIGRAVITY_APP_DATA_DIR": str(custom_brain.parent)}):
            resolved_brain = get_brain_dir(cid)
            self.assertEqual(resolved_brain, custom_brain / cid)
            resolved_state = resolve_cid_state_dir(cid)
            self.assertEqual(resolved_state, custom_brain / cid / ".agyis")

        payload = {"tokens": 245_000, "role": "deep_execution"}
        res = evaluate_pre_invocation(payload, threshold=230_000)
        inject_steps = res.get("injectSteps", [])
        self.assertEqual(len(inject_steps), 1)
        self.assertIn("systemMessage", inject_steps[0])
        self.assertNotIn("ephemeralMessage", inject_steps[0])
        self.assertIsInstance(inject_steps[0]["systemMessage"], dict)
        self.assertIn("COMPACTION IMMINENT", inject_steps[0]["systemMessage"]["systemMessage"])


if __name__ == "__main__":
    unittest.main()
