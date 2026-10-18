#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Arafat Zahan (@kuasha420)
# Corporate Stewardship & Infrastructure: Purrfect Software Limited (PSL)
# Governed by: ICARO-42/b Ordinance (Company-Supported Personal IP Framework)

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
from unittest.mock import MagicMock, patch

from harness.cli import main

DYNAMIC_TEST_MODULES = (
    "test_sample",
    "test_clear_state_sample",
    "test_dual_cli_sample",
)


class TestPslCli(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.orig_state_dir = os.environ.get("PSL_HARNESS_STATE_DIR")
        self.orig_agyis_state_dir = os.environ.get("AGYIS_HARNESS_STATE_DIR")
        self.orig_brain_dir = os.environ.get("ANTIGRAVITY_BRAIN_DIR")
        self.orig_gemini_brain_dir = os.environ.get("GEMINI_BRAIN_DIR")
        os.environ["PSL_HARNESS_STATE_DIR"] = self.temp_dir.name
        os.environ["AGYIS_HARNESS_STATE_DIR"] = self.temp_dir.name
        default_brain = Path(self.temp_dir.name) / "default_brain"
        default_brain.mkdir(parents=True, exist_ok=True)
        os.environ["ANTIGRAVITY_BRAIN_DIR"] = str(default_brain)
        os.environ["GEMINI_BRAIN_DIR"] = str(default_brain)

    def tearDown(self):
        for mod in DYNAMIC_TEST_MODULES:
            sys.modules.pop(mod, None)
        if self.orig_state_dir is not None:
            os.environ["PSL_HARNESS_STATE_DIR"] = self.orig_state_dir
        else:
            os.environ.pop("PSL_HARNESS_STATE_DIR", None)
        if self.orig_agyis_state_dir is not None:
            os.environ["AGYIS_HARNESS_STATE_DIR"] = self.orig_agyis_state_dir
        else:
            os.environ.pop("AGYIS_HARNESS_STATE_DIR", None)
        if self.orig_brain_dir is not None:
            os.environ["ANTIGRAVITY_BRAIN_DIR"] = self.orig_brain_dir
        else:
            os.environ.pop("ANTIGRAVITY_BRAIN_DIR", None)
        if self.orig_gemini_brain_dir is not None:
            os.environ["GEMINI_BRAIN_DIR"] = self.orig_gemini_brain_dir
        else:
            os.environ.pop("GEMINI_BRAIN_DIR", None)
        self.temp_dir.cleanup()

    def test_cli_help(self):
        """Verifies --help outputs usage and exits cleanly with 0 and clean stderr."""
        with patch("sys.stdout", new_callable=io.StringIO) as mock_out, \
             patch("sys.stderr", new_callable=io.StringIO) as mock_err:
            with self.assertRaises(SystemExit) as cm:
                main(["--help"], prog="agyis")
            self.assertEqual(cm.exception.code, 0)
            self.assertEqual(mock_err.getvalue(), "")
            self.assertIn("Agyis Harness for Google Antigravity", mock_out.getvalue())
            self.assertIn("usage: agyis", mock_out.getvalue())

    def test_cli_version(self):
        """Verifies --version prints package version with clean stderr on agyis."""
        with patch("sys.stdout", new_callable=io.StringIO) as mock_out, \
             patch("sys.stderr", new_callable=io.StringIO) as mock_err:
            with self.assertRaises(SystemExit) as cm:
                main(["--version"], prog="agyis")
            self.assertEqual(cm.exception.code, 0)
            self.assertEqual(mock_err.getvalue(), "")
            self.assertIn("agyis-harness 1.0.0-rc6", mock_out.getvalue())

    def test_cli_status(self):
        """Verifies `psl status` prints repository, skills, agents, and hook status."""
        with patch("sys.stdout", new_callable=io.StringIO) as mock_out:
            code = main(["status"])
            self.assertEqual(code, 0)
            out = mock_out.getvalue()
            self.assertTrue(
                "Agyis Harness for Google Antigravity" in out
                or "PSL Harness for Google Antigravity" in out
            )
            self.assertIn("Active Lifecycle Hooks", out)
            self.assertIn("anti-drift", out)
            self.assertIn("Cognitive Attention Horizon Gauge", out)
            self.assertIn("Modular Skills:", out)
            self.assertIn("Specialist Subagents:", out)

    def test_cli_skills_subcommand(self):
        """Verifies `psl skills` lists skills and inspects details."""
        with patch("sys.stdout", new_callable=io.StringIO) as mock_out:
            code = main(["skills"])
            self.assertEqual(code, 0)
            out = mock_out.getvalue()
            self.assertTrue("Agyis Modular Skills" in out or "PSL Modular Skills" in out)
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
            self.assertTrue("Agyis Specialist Subagents" in out or "PSL Specialist Subagents" in out)
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
            self.assertEqual(len(data), 7)

    def test_cli_agents_workspace_root_override(self):
        """Verifies `_get_repo_root()` and `psl agents` respect _TEST_WORKSPACE_ROOT."""
        import harness.cli
        from harness.commands.agents import _get_repo_root

        custom_root = Path(self.temp_dir.name) / "custom_ws"
        custom_root.mkdir(parents=True)

        with patch.object(harness.cli, "_TEST_WORKSPACE_ROOT", custom_root):
            self.assertEqual(_get_repo_root(), custom_root)

            with patch("sys.stdout", new_callable=io.StringIO) as mock_out:
                code = main(["agents", "--sync"])
                self.assertEqual(code, 0)
                out = mock_out.getvalue()
                self.assertIn(str(custom_root / ".agents" / "agents"), out)
                self.assertTrue((custom_root / ".agents" / "agents" / "harness_builder.md").exists())

        self.assertNotEqual(_get_repo_root(), custom_root)
        self.assertIsNone(harness.cli._TEST_WORKSPACE_ROOT)

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

    def test_cli_hook_dispatch_anti_drift(self):
        """Verifies `psl hook anti-drift` and its aliases dispatch to anti_drift_hook."""
        payload = {
            "conversationId": "test-cli-drift",
            "action": "check_drift",
            "target_file": "main.py",
            "plan_files": ["main.py"],
        }
        for alias in ("anti-drift", "drift", "anti_drift"):
            with patch("sys.stdin", io.StringIO(json.dumps(payload))), \
                 patch("sys.stdout", new_callable=io.StringIO) as mock_out:
                code = main(["hook", alias])
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

    def test_cli_audit_benchmark(self):
        """Verifies `psl audit benchmark` dispatches to benchmark_reasoning_tiers.main."""
        with patch("pipeline.benchmark_reasoning_tiers.main") as mock_bench:
            code = main(["audit", "benchmark"])
            self.assertEqual(code, 0)
            mock_bench.assert_called_once_with([])

    def test_cli_audit_clusters(self):
        """Verifies `psl audit clusters` dispatches to analyze_failure_clusters.main."""
        with patch("pipeline.analyze_failure_clusters.main", return_value=0) as mock_clusters:
            code = main(["audit", "clusters"])
            self.assertEqual(code, 0)
            mock_clusters.assert_called_once_with([])

    def test_cli_audit_clusters_with_custom_flags(self):
        """Verifies `psl audit clusters --db ...` forwards custom flags cleanly."""
        with patch("pipeline.analyze_failure_clusters.main", return_value=0) as mock_clusters:
            code = main(["audit", "clusters", "--db", "custom.db", "--output-json", "out.json", "--output-report", "out.md"])
            self.assertEqual(code, 0)
            mock_clusters.assert_called_once_with([
                "--db", "custom.db",
                "--output-json", "out.json",
                "--output-report", "out.md",
            ])

    def test_cli_audit_session_with_db_flag(self):
        """Verifies `psl audit session --save-db --db <path>` saves into specified database."""
        sess_dir = Path(self.temp_dir.name) / "sess_dir"
        log_dir = sess_dir / ".system_generated" / "logs"
        log_dir.mkdir(parents=True)
        (log_dir / "transcript.jsonl").write_text(json.dumps({"step_index": 0}) + "\n")

        dummy_report = {
            "session_id": "test-session-5678",
            "coordinator": {},
            "subagents": [],
            "collective_pipeline": {}
        }
        custom_db = Path(self.temp_dir.name) / "audit_target.db"

        with patch("pipeline.analyze_live_session.find_latest_session_dir", return_value=sess_dir), \
             patch("pipeline.analyze_live_session.analyze_session", return_value=dummy_report), \
             patch("pipeline.extract_transcripts.extract_session", return_value=({
                 "session_id": "test-session-5678", "start_time": "2026-01-01", "end_time": "2026-01-01",
                 "duration_seconds": 1.0, "total_steps": 1, "model": "gemini",
                 "workspace_path": "/ws", "transcript_path": str(log_dir / "transcript.jsonl"),
                 "file_size_bytes": 10, "has_errors": 0, "tool_call_count": 0,
                 "tool_error_count": 0, "intervention_count": 0
             }, [], [], [])), \
             patch("sys.stdout", new_callable=io.StringIO):
            code = main(["audit", "session", "--save-db", "--db", str(custom_db), "--json"])
            self.assertEqual(code, 0)
            self.assertTrue(custom_db.exists())

    def test_cli_auth_login(self):
        """Verifies `psl auth login` validates token and saves credentials."""
        with patch("harness.telemetry.sync.verify_auth_token", return_value={"status": "ok", "authenticated": True, "username": "alice", "org": "purrfectsoft"}), \
             patch("sys.stdout", new_callable=io.StringIO) as mock_out:
            code = main(["auth", "login", "--token", "test-token-123", "--endpoint", "https://hub.example.com"])
            self.assertEqual(code, 0)
            self.assertIn("Successfully authenticated as alice", mock_out.getvalue())

        from harness.telemetry import config
        creds = config.load_credentials()
        self.assertEqual(creds["token"], "test-token-123")
        self.assertEqual(creds["github_username"], "alice")
        cfg = config.load_config()
        self.assertEqual(cfg["endpoint"], "https://hub.example.com")

    def test_cli_auth_login_with_gh(self):
        """Verifies `psl auth login --gh` lifts token via gh CLI."""
        with patch("harness.telemetry.config.get_gh_cli_token", return_value="gho_cli_token_999") as mock_gh, \
             patch("harness.telemetry.sync.verify_auth_token", return_value={"status": "ok", "authenticated": True, "username": "gh-alice", "org": "mesh"}), \
             patch("sys.stdout", new_callable=io.StringIO) as mock_out:
            code = main(["auth", "login", "--gh"])
            self.assertEqual(code, 0)
            mock_gh.assert_called_once()
            self.assertIn("Successfully authenticated as gh-alice", mock_out.getvalue())

        from harness.telemetry import config
        creds = config.load_credentials()
        self.assertEqual(creds["token"], "gho_cli_token_999")
        self.assertEqual(creds["github_username"], "gh-alice")

    def test_cli_auth_login_workspace_scope(self):
        """Verifies `psl auth login --workspace` persists endpoint into workspace config."""
        ws_root = Path(self.temp_dir.name) / "workspace"
        (ws_root / ".git").mkdir(parents=True)

        with patch("harness.telemetry.config.find_workspace_root", return_value=ws_root), \
             patch("harness.telemetry.sync.verify_auth_token", return_value={"status": "ok", "authenticated": True, "username": "ws-alice"}), \
             patch("sys.stdout", new_callable=io.StringIO):
            code = main(["auth", "login", "--token", "tok-123", "--endpoint", "https://ws.example.com", "--workspace"])
            self.assertEqual(code, 0)

        ws_cfg_path = (ws_root / ".agyis" / "config.json") if (ws_root / ".agyis" / "config.json").exists() else (ws_root / ".psl" / "config.json")
        self.assertTrue(ws_cfg_path.exists())
        ws_data = json.loads(ws_cfg_path.read_text())
        self.assertEqual(ws_data["endpoint"], "https://ws.example.com")

        # Also test legacy workspace with pre-existing .psl directory
        legacy_ws = Path(self.temp_dir.name) / "legacy_workspace"
        (legacy_ws / ".psl").mkdir(parents=True)
        (legacy_ws / ".git").mkdir(parents=True)
        with patch("harness.telemetry.config.find_workspace_root", return_value=legacy_ws), \
             patch("harness.telemetry.sync.verify_auth_token", return_value={"status": "ok", "authenticated": True, "username": "ws-alice"}), \
             patch("sys.stdout", new_callable=io.StringIO):
            code = main(["auth", "login", "--token", "tok-123", "--endpoint", "https://legacy.example.com", "--workspace"])
            self.assertEqual(code, 0)
        self.assertTrue((legacy_ws / ".psl" / "config.json").exists())
        legacy_data = json.loads((legacy_ws / ".psl" / "config.json").read_text())
        self.assertEqual(legacy_data["endpoint"], "https://legacy.example.com")

    def test_cli_auth_status_and_logout(self):
        """Verifies `psl auth status` and `psl auth logout`."""
        from harness.telemetry import config
        config.save_credentials({"token": "ghp_1234567890abcdef", "github_username": "bob"})

        with patch("sys.stdout", new_callable=io.StringIO) as mock_out:
            code = main(["auth", "status"])
            self.assertEqual(code, 0)
            out = mock_out.getvalue()
            self.assertIn("Authenticated: Yes", out)
            self.assertIn("Username:      bob", out)
            self.assertIn("ghp_****cdef", out)

        with patch("sys.stdout", new_callable=io.StringIO) as mock_out:
            code = main(["auth", "logout"])
            self.assertEqual(code, 0)
            self.assertIn("Credentials cleared successfully", mock_out.getvalue())

        with patch("sys.stdout", new_callable=io.StringIO) as mock_out:
            code = main(["auth", "status", "--json"])
            self.assertEqual(code, 1)
            data = json.loads(mock_out.getvalue())
            self.assertFalse(data["authenticated"])

    def test_cli_sync_bi_directional_default(self):
        """Verifies `psl sync` defaults to bi-directional sync and formats output."""
        mock_res = {
            "status": "success",
            "direction": "both",
            "push": {"sessions_pushed": 2, "steps_pushed": 5, "tool_calls_pushed": 3},
            "pull": {"sessions_inserted": 1, "steps_inserted": 2, "sessions_pulled": 1, "steps_pulled": 2},
        }
        with patch("harness.telemetry.sync.sync_telemetry", return_value=mock_res) as mock_sync, \
             patch("sys.stdout", new_callable=io.StringIO) as mock_out:
            code = main(["sync"])
            self.assertEqual(code, 0)
            mock_sync.assert_called_once_with(
                direction="both",
                interactive=False,
                endpoint=None,
                db_path=None,
                limit=None,
                dry_run=False,
                on_progress=unittest.mock.ANY,
            )
            out = mock_out.getvalue()
            self.assertIn("Telemetry sync completed successfully", out)
            self.assertIn("Pushed: 2 sessions", out)
            self.assertIn("Pulled: 1 new sessions", out)

    def test_cli_sync_flags_and_json(self):
        """Verifies `psl sync` flag variations: --push, --pull, --dry-run, --json."""
        mock_res = {
            "status": "dry_run",
            "direction": "push",
            "push": {"status": "dry_run", "sessions_pushed": 1},
            "pull": None,
        }
        with patch("harness.telemetry.sync.sync_telemetry", return_value=mock_res) as mock_sync, \
             patch("sys.stdout", new_callable=io.StringIO) as mock_out:
            code = main(["sync", "--push", "--dry-run", "--json"])
            self.assertEqual(code, 0)
            mock_sync.assert_called_once_with(
                direction="push",
                interactive=False,
                endpoint=None,
                db_path=None,
                limit=None,
                dry_run=True,
                on_progress=None,
            )
            data = json.loads(mock_out.getvalue())
            self.assertEqual(data["status"], "dry_run")
            self.assertEqual(data["direction"], "push")

    def test_cli_sync_with_db_flag(self):
        """Verifies `psl sync --db <path>` passes custom db path to sync_telemetry."""
        mock_res = {"status": "success", "direction": "both", "push": None, "pull": None}
        custom_db = Path(self.temp_dir.name) / "custom.db"
        with patch("harness.telemetry.sync.sync_telemetry", return_value=mock_res) as mock_sync, \
             patch("sys.stdout", new_callable=io.StringIO):
            code = main(["sync", "--db", str(custom_db)])
            self.assertEqual(code, 0)
            mock_sync.assert_called_once_with(
                direction="both",
                interactive=False,
                endpoint=None,
                db_path=str(custom_db),
                limit=None,
                dry_run=False,
                on_progress=unittest.mock.ANY,
            )

    def test_cli_sync_with_session_id_ingestion(self):
        """Verifies `psl sync --session-id <id>` ingests session before synchronizing."""
        mock_res = {"status": "success", "direction": "both", "push": None, "pull": None}
        with patch("pipeline.analyze_live_session.find_session_dir", return_value=Path(self.temp_dir.name)) as mock_find, \
             patch("harness.telemetry.sync.sync_telemetry", return_value=mock_res) as mock_sync, \
             patch("sys.stdout", new_callable=io.StringIO):
            code = main(["sync", "--session-id", "test-sess-123"])
            self.assertEqual(code, 0)
            mock_find.assert_called_once_with("test-sess-123")
            mock_sync.assert_called_once()

    def test_cli_sync_systemd(self):
        """Verifies `psl sync --systemd` prints the systemd service file."""
        with patch("sys.stdout", new_callable=io.StringIO) as mock_out:
            code = main(["sync", "--systemd"])
            self.assertEqual(code, 0)
            out = mock_out.getvalue()
            self.assertIn("[Unit]", out)
            self.assertIn("ExecStart=", out)

    def test_cli_sync_review_flag(self):
        """Verifies `psl sync --review` passes review=True to sync_telemetry."""
        mock_res = {"status": "success", "direction": "both", "push": None, "pull": None}
        with patch("harness.telemetry.sync.sync_telemetry", return_value=mock_res) as mock_sync, \
             patch("sys.stdout", new_callable=io.StringIO):
            code = main(["sync", "--review"])
            self.assertEqual(code, 0)
            mock_sync.assert_called_once_with(
                direction="both",
                interactive=False,
                endpoint=None,
                db_path=None,
                limit=None,
                dry_run=False,
                on_progress=unittest.mock.ANY,
                review=True,
            )

    def test_cli_sync_developer_filter(self):
        """Verifies `agyis sync --pull --developer <user>` passes developer argument."""
        mock_res = {"status": "success", "direction": "pull", "push": None, "pull": {"sessions_inserted": 2}}
        with patch("harness.telemetry.sync.sync_telemetry", return_value=mock_res) as mock_sync, \
             patch("sys.stdout", new_callable=io.StringIO):
            code = main(["sync", "--pull", "--developer", "kuasha420"])
            self.assertEqual(code, 0)
            mock_sync.assert_called_once_with(
                direction="pull",
                interactive=False,
                endpoint=None,
                db_path=None,
                limit=None,
                dry_run=False,
                on_progress=unittest.mock.ANY,
                developer="kuasha420",
            )

    def test_cli_sync_all_developers(self):
        """Verifies `agyis sync --pull --all` passes all_developers=True."""
        mock_res = {"status": "success", "direction": "pull", "push": None, "pull": {"sessions_inserted": 5}}
        with patch("harness.telemetry.sync.sync_telemetry", return_value=mock_res) as mock_sync, \
             patch("sys.stdout", new_callable=io.StringIO):
            code = main(["sync", "--pull", "--all"])
            self.assertEqual(code, 0)
            mock_sync.assert_called_once_with(
                direction="pull",
                interactive=False,
                endpoint=None,
                db_path=None,
                limit=None,
                dry_run=False,
                on_progress=unittest.mock.ANY,
                all_developers=True,
            )

    def test_cli_sync_since(self):
        """Verifies `agyis sync --pull --since <timestamp>` passes since argument."""
        mock_res = {"status": "success", "direction": "pull", "push": None, "pull": {"sessions_inserted": 1}}
        with patch("harness.telemetry.sync.sync_telemetry", return_value=mock_res) as mock_sync, \
             patch("sys.stdout", new_callable=io.StringIO):
            code = main(["sync", "--pull", "--since", "2026-10-01T00:00:00Z"])
            self.assertEqual(code, 0)
            mock_sync.assert_called_once_with(
                direction="pull",
                interactive=False,
                endpoint=None,
                db_path=None,
                limit=None,
                dry_run=False,
                on_progress=unittest.mock.ANY,
                since="2026-10-01T00:00:00Z",
            )

    def test_cli_sync_watch_daemon(self):
        """Verifies `agyis sync --watch --interval 10.0` invokes watch_and_sync daemon."""
        mock_watch_res = {"iterations": 2, "total_sessions_pushed": 4}
        with patch("harness.telemetry.sync.watch_and_sync", return_value=mock_watch_res) as mock_watch, \
             patch("sys.stdout", new_callable=io.StringIO) as mock_out:
            code = main(["sync", "--watch", "--interval", "10.0"])
            self.assertEqual(code, 0)
            mock_watch.assert_called_once_with(interval_sec=10.0, db_path=None, endpoint=None)
            self.assertIn("Watch daemon stopped: 2 iterations, 4 sessions pushed", mock_out.getvalue())

    def test_cli_sync_watch_daemon_json(self):
        """Verifies `agyis sync --watch --json` outputs formatted json."""
        mock_watch_res = {"iterations": 1, "total_sessions_pushed": 2}
        with patch("harness.telemetry.sync.watch_and_sync", return_value=mock_watch_res), \
             patch("sys.stdout", new_callable=io.StringIO) as mock_out:
            code = main(["sync", "--watch", "--json"])
            self.assertEqual(code, 0)
            data = json.loads(mock_out.getvalue())
            self.assertEqual(data["iterations"], 1)
            self.assertEqual(data["total_sessions_pushed"], 2)

    def test_cli_sync_dry_run_pull_output(self):
        """Verifies human-readable formatting of pending pull counts in dry-run mode."""
        mock_res = {
            "status": "dry_run",
            "direction": "pull",
            "push": None,
            "pull": {"status": "dry_run", "sessions_to_pull": 1041, "sessions_pulled": 1041},
        }
        with patch("harness.telemetry.sync.sync_telemetry", return_value=mock_res), \
             patch("sys.stdout", new_callable=io.StringIO) as mock_out:
            code = main(["sync", "--pull", "--developer", "kuasha420", "--dry-run"])
            self.assertEqual(code, 0)
            out = mock_out.getvalue()
            self.assertIn("Telemetry sync completed successfully (dry run):", out)
            self.assertIn("Pending to pull: 1041 sessions", out)

    def test_cli_sync_error_auth_failure(self):
        """Verifies actionable stderr diagnostics on HTTP 401 unauthorized error."""
        with patch("harness.telemetry.sync.sync_telemetry", side_effect=ValueError("Token verification failed (HTTP 401): Unauthorized")), \
             patch("sys.stderr", new_callable=io.StringIO) as mock_err:
            code = main(["sync"])
            self.assertEqual(code, 1)
            err = mock_err.getvalue()
            self.assertIn("Telemetry sync authentication failed (HTTP 401: Unauthorized)", err)
            self.assertIn("agyis auth login --gh", err)

    def test_cli_sync_error_forbidden(self):
        """Verifies actionable stderr diagnostics on HTTP 403 forbidden error."""
        with patch("harness.telemetry.sync.sync_telemetry", side_effect=ValueError("Token verification failed (HTTP 403): Forbidden")), \
             patch("sys.stderr", new_callable=io.StringIO) as mock_err:
            code = main(["sync"])
            self.assertEqual(code, 1)
            err = mock_err.getvalue()
            self.assertIn("Telemetry sync authorization failed (HTTP 403: Forbidden)", err)
            self.assertIn("purrfectsoft", err)

    def test_cli_sync_error_connection(self):
        """Verifies actionable stderr diagnostics on network connection error."""
        with patch("harness.telemetry.sync.sync_telemetry", side_effect=ConnectionError("Failed to connect to telemetry hub")), \
             patch("sys.stderr", new_callable=io.StringIO) as mock_err:
            code = main(["sync"])
            self.assertEqual(code, 1)
            err = mock_err.getvalue()
            self.assertIn("Failed to connect to telemetry hub", err)
            self.assertIn("AGYIS_SYNC_ENDPOINT", err)

    def test_cli_sync_error_db_locked(self):
        """Verifies actionable stderr diagnostics on SQLite database locked error."""
        import sqlite3
        with patch("harness.telemetry.sync.sync_telemetry", side_effect=sqlite3.OperationalError("database is locked")), \
             patch("sys.stderr", new_callable=io.StringIO) as mock_err:
            code = main(["sync"])
            self.assertEqual(code, 1)
            err = mock_err.getvalue()
            self.assertIn("SQLite database error: database is locked", err)
            self.assertIn("Wait for active background operations to complete", err)

    def test_cli_subagents_subcommand(self):
        """Verifies `psl subagents` renders ASCII table and handles empty directories."""
        empty_brain = Path(self.temp_dir.name) / "empty_brain"
        empty_brain.mkdir()

        with patch("sys.stdout", new_callable=io.StringIO) as mock_out:
            code = main(["subagents", "--brain-dir", str(empty_brain)])
            self.assertEqual(code, 0)
            self.assertIn("No active subagents found", mock_out.getvalue())

        # Now create mock subagents
        mock_brain = Path(self.temp_dir.name) / "mock_brain"
        sub_dir = mock_brain / "mock-subagent-1" / ".system_generated" / "logs"
        sub_dir.mkdir(parents=True)
        (sub_dir / "transcript.jsonl").write_text(
            json.dumps({"step_index": 0, "content": "You are harness_builder to implement"})
        )

        with patch("sys.stdout", new_callable=io.StringIO) as mock_out:
            code = main(["subagents", "--brain-dir", str(mock_brain)])
            self.assertEqual(code, 0)
            out = mock_out.getvalue()
            self.assertTrue("Agyis Active Subagents" in out or "PSL Active Subagents" in out)
            self.assertIn("Conversation ID", out)
            self.assertIn("harness_builder", out)

    def test_cli_subagents_json(self):
        """Verifies `psl subagents --json` outputs structured JSON."""
        mock_brain = Path(self.temp_dir.name) / "json_brain"
        sub_dir = mock_brain / "mock-json-sub" / ".system_generated" / "logs"
        sub_dir.mkdir(parents=True)
        (sub_dir / "transcript.jsonl").write_text(
            json.dumps({"step_index": 0, "content": "You are harness_auditor, verifying"})
        )

        with patch("sys.stdout", new_callable=io.StringIO) as mock_out:
            code = main(["subagents", "--brain-dir", str(mock_brain), "--json"])
            self.assertEqual(code, 0)
            data = json.loads(mock_out.getvalue().strip())
            self.assertIsInstance(data, list)
            self.assertEqual(len(data), 1)
            self.assertEqual(data[0]["conversation_id"], "mock-json-sub")
            self.assertEqual(data[0]["role"], "harness_auditor")
            self.assertEqual(data[0]["health_zone"], "HEALTHY")
            self.assertEqual(data[0]["recommendation"], "REUSE")

    def test_cli_status_with_active_subagents(self):
        """Verifies `psl status` renders live subagents section when subagents are active."""
        from harness.subagents import SubagentContextStatus

        mock_status = SubagentContextStatus(
            conversation_id="test-sub-1234",
            role="ladder_executioner",
            step_count=25,
            token_count=12000,
            health_zone="HEALTHY",
            recommendation="REUSE",
            latency_ms=1.2,
        )
        with patch("harness.subagents.list_active_subagent_statuses", return_value=[mock_status]), \
             patch("sys.stdout", new_callable=io.StringIO) as mock_out:
            code = main(["status"])
            self.assertEqual(code, 0)
            out = mock_out.getvalue()
            self.assertIn("Live Active Subagents (1 active):", out)
            self.assertIn("ladder_executioner", out)
            self.assertIn("HEALTHY", out)

    def test_cli_remote_exec(self):
        """Verifies `psl remote exec` dispatches command to RemoteRunner."""
        from harness.remote import RemoteRunner
        mock_proc = MagicMock()
        mock_proc.returncode = 0
        mock_proc.stdout = "uptime 12:00:00\n"
        mock_proc.stderr = ""

        with patch.object(RemoteRunner, "run", return_value=mock_proc) as mock_run, \
             patch("sys.stdout", new_callable=io.StringIO) as mock_out:
            code = main(["remote", "exec", "user@target", "uptime"])
            self.assertEqual(code, 0)
            mock_run.assert_called_once()
            call_kwargs = mock_run.call_args[1]
            self.assertEqual(call_kwargs["target"], "user@target")
            self.assertEqual(call_kwargs["remote_cmd"], "uptime")
            self.assertIn("uptime 12:00:00", mock_out.getvalue())

    def test_cli_remote_script_streaming_and_staging(self):
        """Verifies `psl remote script` dispatches to ScriptStreamer stream and stage."""
        from harness.remote import ScriptStreamer
        mock_proc = MagicMock()
        mock_proc.returncode = 0
        mock_proc.stdout = "script done\n"
        mock_proc.stderr = ""

        script_file = Path(self.temp_dir.name) / "test_remote.sh"
        script_file.write_text("echo hi\n")

        with patch.object(ScriptStreamer, "stream_script", return_value=mock_proc) as mock_stream, \
             patch("sys.stdout", new_callable=io.StringIO) as mock_out:
            code = main(["remote", "script", "target-host", str(script_file)])
            self.assertEqual(code, 0)
            mock_stream.assert_called_once()
            self.assertIn("script done", mock_out.getvalue())

        with patch.object(ScriptStreamer, "stage_script", return_value=mock_proc) as mock_stage, \
             patch("sys.stdout", new_callable=io.StringIO) as mock_out:
            code = main(["remote", "script", "target-host", str(script_file), "--stage"])
            self.assertEqual(code, 0)
            mock_stage.assert_called_once()

    def test_cli_remote_triage(self):
        """Verifies `psl remote triage` dispatches to RemoteTriage and renders reports."""
        from harness.remote import RemoteTriage
        mock_report = {
            "target": "vps-box",
            "profile": "ports",
            "service": None,
            "exit_code": 0,
            "report_markdown": "### Triage Report\nListening on 80\n",
            "raw_output": "raw",
        }

        with patch.object(RemoteTriage, "run_triage", return_value=mock_report) as mock_triage, \
             patch("sys.stdout", new_callable=io.StringIO) as mock_out:
            code = main(["remote", "triage", "vps-box", "--profile", "ports"])
            self.assertEqual(code, 0)
            mock_triage.assert_called_once()
            self.assertIn("### Triage Report", mock_out.getvalue())

        # Test --json flag
        with patch.object(RemoteTriage, "run_triage", return_value=mock_report), \
             patch("sys.stdout", new_callable=io.StringIO) as mock_out:
            code = main(["remote", "triage", "vps-box", "--json"])
            self.assertEqual(code, 0)
            data = json.loads(mock_out.getvalue().strip())
            self.assertEqual(data["target"], "vps-box")

    def test_cli_remote_socket(self):
        """Verifies `psl remote socket status` and `psl remote socket cleanup`."""
        from harness.remote import RemoteRunner
        runner = RemoteRunner()
        sock = runner.socket_dir / "cm_test_socket"
        sock.write_text("socket")

        with patch("sys.stdout", new_callable=io.StringIO) as mock_out:
            code = main(["remote", "socket", "status"])
            self.assertEqual(code, 0)
            self.assertIn("Active OpenSSH ControlMaster sockets", mock_out.getvalue())
            self.assertIn("cm_test_socket", mock_out.getvalue())

        with patch("sys.stdout", new_callable=io.StringIO) as mock_out:
            code = main(["remote", "socket", "cleanup"])
            self.assertEqual(code, 0)
            self.assertIn("Cleaned up 1 active ControlMaster socket(s)", mock_out.getvalue())
            self.assertFalse(sock.exists())

    def test_cli_deprecated_psl_help(self):
        """Verifies deprecated `psl --help` outputs deprecation warning to stderr and psl usage to stdout."""
        from harness.cli import deprecated_psl_main, PSL_DEPRECATION_WARNING
        with patch("sys.stdout", new_callable=io.StringIO) as mock_out, \
             patch("sys.stderr", new_callable=io.StringIO) as mock_err:
            with self.assertRaises(SystemExit) as cm:
                deprecated_psl_main(["--help"])
            self.assertEqual(cm.exception.code, 0)
            self.assertIn(PSL_DEPRECATION_WARNING.strip(), mock_err.getvalue())
            self.assertIn("usage: psl", mock_out.getvalue())

    def test_cli_deprecated_psl_subcommand(self):
        """Verifies deprecated `psl status` emits deprecation warning to stderr while executing normally."""
        from harness.cli import deprecated_psl_main, PSL_DEPRECATION_WARNING
        with patch("sys.stdout", new_callable=io.StringIO) as mock_out, \
             patch("sys.stderr", new_callable=io.StringIO) as mock_err:
            code = deprecated_psl_main(["status"])
            self.assertEqual(code, 0)
            self.assertIn(PSL_DEPRECATION_WARNING.strip(), mock_err.getvalue())
            self.assertIn("Active Lifecycle Hooks", mock_out.getvalue())

    def test_cli_deprecated_psl_json_clean_stdout(self):
        """Verifies deprecated `psl skills --json` emits warning to stderr while keeping stdout 100% clean JSON."""
        from harness.cli import deprecated_psl_main, PSL_DEPRECATION_WARNING
        with patch("sys.stdout", new_callable=io.StringIO) as mock_out, \
             patch("sys.stderr", new_callable=io.StringIO) as mock_err:
            code = deprecated_psl_main(["skills", "--json"])
            self.assertEqual(code, 0)
            self.assertIn(PSL_DEPRECATION_WARNING.strip(), mock_err.getvalue())
            # Assert stdout is pure JSON without any warning prefix
            data = json.loads(mock_out.getvalue().strip())
            self.assertIsInstance(data, list)
            self.assertGreaterEqual(len(data), 8)

    def test_cli_prog_detection_from_argv0(self):
        """Verifies main() detects invocation name from sys.argv[0]."""
        from harness.cli import PSL_DEPRECATION_WARNING
        # Invocation as psl binary
        with patch("sys.argv", ["/usr/local/bin/psl", "status"]), \
             patch("sys.stdout", new_callable=io.StringIO), \
             patch("sys.stderr", new_callable=io.StringIO) as mock_err:
            code = main()
            self.assertEqual(code, 0)
            self.assertIn(PSL_DEPRECATION_WARNING.strip(), mock_err.getvalue())

        # Invocation as agyis binary
        with patch("sys.argv", ["/usr/local/bin/agyis", "status"]), \
             patch("sys.stdout", new_callable=io.StringIO), \
             patch("sys.stderr", new_callable=io.StringIO) as mock_err:
            code = main()
            self.assertEqual(code, 0)
            self.assertEqual(mock_err.getvalue(), "")


class TestAgyisPathAndConfigHierarchy(unittest.TestCase):
    """Hermetic unit tests for AGYIS_* and PSL_* path and config fallback hierarchies."""

    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.base = Path(self.temp_dir.name)

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def test_config_and_data_dir_hierarchy(self) -> None:
        from harness.telemetry.config import get_config_dir, get_data_dir
        agyis_cfg = self.base / "agyis_cfg"
        psl_cfg = self.base / "psl_cfg"

        # AGYIS_CONFIG_DIR takes precedence
        with patch.dict(os.environ, {"AGYIS_CONFIG_DIR": str(agyis_cfg), "PSL_CONFIG_DIR": str(psl_cfg)}, clear=False):
            self.assertEqual(get_config_dir(), agyis_cfg.resolve())

        # PSL_CONFIG_DIR honored when AGYIS_CONFIG_DIR is unset
        with patch.dict(os.environ, {"PSL_CONFIG_DIR": str(psl_cfg)}, clear=False):
            os.environ.pop("AGYIS_CONFIG_DIR", None)
            os.environ.pop("AGYIS_HARNESS_STATE_DIR", None)
            os.environ.pop("PSL_HARNESS_STATE_DIR", None)
            self.assertEqual(get_config_dir(), psl_cfg.resolve())

        # Data dir precedence
        agyis_data = self.base / "agyis_data"
        psl_data = self.base / "psl_data"
        with patch.dict(os.environ, {"AGYIS_DATA_DIR": str(agyis_data), "PSL_DATA_DIR": str(psl_data)}, clear=False):
            self.assertEqual(get_data_dir(), agyis_data.resolve())

        with patch.dict(os.environ, {"PSL_DATA_DIR": str(psl_data)}, clear=False):
            os.environ.pop("AGYIS_DATA_DIR", None)
            os.environ.pop("AGYIS_HARNESS_STATE_DIR", None)
            os.environ.pop("PSL_HARNESS_STATE_DIR", None)
            self.assertEqual(get_data_dir(), psl_data.resolve())

    def test_state_dir_hierarchy(self) -> None:
        from harness.utils.state import get_state_dir
        agyis_state = self.base / "agyis_state"
        psl_state = self.base / "psl_state"

        with patch.dict(os.environ, {"AGYIS_HARNESS_STATE_DIR": str(agyis_state), "PSL_HARNESS_STATE_DIR": str(psl_state)}, clear=False):
            self.assertEqual(get_state_dir(), agyis_state)

        with patch.dict(os.environ, {"PSL_HARNESS_STATE_DIR": str(psl_state)}, clear=False):
            os.environ.pop("AGYIS_HARNESS_STATE_DIR", None)
            self.assertEqual(get_state_dir(), psl_state)

    def test_auth_token_and_sync_endpoint_hierarchy(self) -> None:
        from harness.telemetry.config import get_auth_token, get_sync_endpoint

        with patch.dict(os.environ, {"AGYIS_AUTH_TOKEN": "agyis-tok", "PSL_AUTH_TOKEN": "psl-tok"}, clear=False):
            self.assertEqual(get_auth_token(), "agyis-tok")

        with patch.dict(os.environ, {"PSL_AUTH_TOKEN": "psl-tok"}, clear=False):
            os.environ.pop("AGYIS_AUTH_TOKEN", None)
            self.assertEqual(get_auth_token(), "psl-tok")

        with patch.dict(os.environ, {"AGYIS_SYNC_ENDPOINT": "https://agyis.hub", "PSL_SYNC_ENDPOINT": "https://psl.hub"}, clear=False):
            self.assertEqual(get_sync_endpoint(), "https://agyis.hub")

        with patch.dict(os.environ, {"PSL_SYNC_ENDPOINT": "https://psl.hub"}, clear=False):
            os.environ.pop("AGYIS_SYNC_ENDPOINT", None)
            self.assertEqual(get_sync_endpoint(), "https://psl.hub")

    def test_db_path_and_git_exclude_hierarchy(self) -> None:
        from harness.telemetry.config import resolve_db_path
        from harness.delivery.constants import GIT_EXCLUDE_PATTERNS
        agyis_db = self.base / "agyis_telemetry.db"
        psl_db = self.base / "psl_telemetry.db"

        with patch.dict(os.environ, {"AGYIS_TELEMETRY_DB": str(agyis_db), "PSL_TELEMETRY_DB": str(psl_db)}, clear=False):
            self.assertEqual(resolve_db_path(), agyis_db.resolve())

        with patch.dict(os.environ, {"PSL_TELEMETRY_DB": str(psl_db)}, clear=False):
            os.environ.pop("AGYIS_TELEMETRY_DB", None)
            self.assertEqual(resolve_db_path(), psl_db.resolve())

        self.assertIn(".agyis/", GIT_EXCLUDE_PATTERNS)
        self.assertIn(".psl/", GIT_EXCLUDE_PATTERNS)


class TestCliDualExecutionMatrix(unittest.TestCase):
    """
    Exhaustive dual assertion suite verifying that primary 'agyis' commands
    execute with clean stderr, while legacy 'psl' commands emit the active
    deprecation warning on stderr without corrupting stdout or JSON streams.
    """

    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.orig_state_dir = os.environ.get("PSL_HARNESS_STATE_DIR")
        self.orig_agyis_state_dir = os.environ.get("AGYIS_HARNESS_STATE_DIR")
        self.orig_brain_dir = os.environ.get("ANTIGRAVITY_BRAIN_DIR")
        self.orig_gemini_brain_dir = os.environ.get("GEMINI_BRAIN_DIR")
        os.environ["PSL_HARNESS_STATE_DIR"] = self.temp_dir.name
        os.environ["AGYIS_HARNESS_STATE_DIR"] = self.temp_dir.name
        default_brain = Path(self.temp_dir.name) / "default_brain"
        default_brain.mkdir(parents=True, exist_ok=True)
        os.environ["ANTIGRAVITY_BRAIN_DIR"] = str(default_brain)
        os.environ["GEMINI_BRAIN_DIR"] = str(default_brain)

    def tearDown(self):
        for mod in DYNAMIC_TEST_MODULES:
            sys.modules.pop(mod, None)
        if self.orig_state_dir is not None:
            os.environ["PSL_HARNESS_STATE_DIR"] = self.orig_state_dir
        else:
            os.environ.pop("PSL_HARNESS_STATE_DIR", None)
        if self.orig_agyis_state_dir is not None:
            os.environ["AGYIS_HARNESS_STATE_DIR"] = self.orig_agyis_state_dir
        else:
            os.environ.pop("AGYIS_HARNESS_STATE_DIR", None)
        if self.orig_brain_dir is not None:
            os.environ["ANTIGRAVITY_BRAIN_DIR"] = self.orig_brain_dir
        else:
            os.environ.pop("ANTIGRAVITY_BRAIN_DIR", None)
        if self.orig_gemini_brain_dir is not None:
            os.environ["GEMINI_BRAIN_DIR"] = self.orig_gemini_brain_dir
        else:
            os.environ.pop("GEMINI_BRAIN_DIR", None)
        self.temp_dir.cleanup()

    def test_dual_version_invocations(self):
        """Verifies agyis --version is clean, while psl --version emits deprecation warning."""
        from harness.cli import PSL_DEPRECATION_WARNING, deprecated_psl_main

        # agyis --version
        with patch("sys.stdout", new_callable=io.StringIO) as agyis_out, \
             patch("sys.stderr", new_callable=io.StringIO) as agyis_err:
            with self.assertRaises(SystemExit) as cm1:
                main(["--version"], prog="agyis")
            self.assertEqual(cm1.exception.code, 0)
            self.assertEqual(agyis_err.getvalue(), "")
            self.assertIn("agyis-harness 1.0.0-rc6", agyis_out.getvalue())

        # psl --version
        with patch("sys.stdout", new_callable=io.StringIO) as psl_out, \
             patch("sys.stderr", new_callable=io.StringIO) as psl_err:
            with self.assertRaises(SystemExit) as cm2:
                deprecated_psl_main(["--version"])
            self.assertEqual(cm2.exception.code, 0)
            self.assertIn(PSL_DEPRECATION_WARNING.strip(), psl_err.getvalue())
            self.assertIn("agyis-harness 1.0.0-rc6", psl_out.getvalue())

    def test_dual_bare_cli_help(self):
        """Verifies bare 'agyis' and 'psl' with no arguments print help with proper stderr isolation."""
        from harness.cli import PSL_DEPRECATION_WARNING, deprecated_psl_main

        # agyis (no args)
        with patch("sys.stdout", new_callable=io.StringIO) as agyis_out, \
             patch("sys.stderr", new_callable=io.StringIO) as agyis_err:
            code1 = main([], prog="agyis")
            self.assertEqual(code1, 0)
            self.assertEqual(agyis_err.getvalue(), "")
            self.assertIn("usage: agyis", agyis_out.getvalue())

        # psl (no args)
        with patch("sys.stdout", new_callable=io.StringIO) as psl_out, \
             patch("sys.stderr", new_callable=io.StringIO) as psl_err:
            code2 = deprecated_psl_main([])
            self.assertEqual(code2, 0)
            self.assertIn(PSL_DEPRECATION_WARNING.strip(), psl_err.getvalue())
            self.assertIn("usage: psl", psl_out.getvalue())

    def test_dual_status_invocations(self):
        """Verifies status subcommand outputs cleanly on agyis and emits deprecation warning on psl."""
        from harness.cli import PSL_DEPRECATION_WARNING, deprecated_psl_main

        with patch("sys.stdout", new_callable=io.StringIO) as agyis_out, \
             patch("sys.stderr", new_callable=io.StringIO) as agyis_err:
            code1 = main(["status"], prog="agyis")
            self.assertEqual(code1, 0)
            self.assertEqual(agyis_err.getvalue(), "")
            self.assertIn("Active Lifecycle Hooks", agyis_out.getvalue())

        with patch("sys.stdout", new_callable=io.StringIO) as psl_out, \
             patch("sys.stderr", new_callable=io.StringIO) as psl_err:
            code2 = deprecated_psl_main(["status"])
            self.assertEqual(code2, 0)
            self.assertIn(PSL_DEPRECATION_WARNING.strip(), psl_err.getvalue())
            self.assertIn("Active Lifecycle Hooks", psl_out.getvalue())

    def test_dual_skills_json_purity(self):
        """Verifies agyis skills --json and psl skills --json produce identical JSON stdout without contamination."""
        from harness.cli import PSL_DEPRECATION_WARNING, deprecated_psl_main

        with patch("sys.stdout", new_callable=io.StringIO) as agyis_out, \
             patch("sys.stderr", new_callable=io.StringIO) as agyis_err:
            code1 = main(["skills", "--json"], prog="agyis")
            self.assertEqual(code1, 0)
            self.assertEqual(agyis_err.getvalue(), "")
            data_agyis = json.loads(agyis_out.getvalue().strip())

        with patch("sys.stdout", new_callable=io.StringIO) as psl_out, \
             patch("sys.stderr", new_callable=io.StringIO) as psl_err:
            code2 = deprecated_psl_main(["skills", "--json"])
            self.assertEqual(code2, 0)
            self.assertIn(PSL_DEPRECATION_WARNING.strip(), psl_err.getvalue())
            data_psl = json.loads(psl_out.getvalue().strip())

        self.assertEqual(data_agyis, data_psl)
        self.assertGreaterEqual(len(data_agyis), 8)

    def test_dual_agents_json_purity(self):
        """Verifies agyis agents --json and psl agents --json produce identical JSON stdout."""
        from harness.cli import PSL_DEPRECATION_WARNING, deprecated_psl_main

        with patch("sys.stdout", new_callable=io.StringIO) as agyis_out, \
             patch("sys.stderr", new_callable=io.StringIO) as agyis_err:
            code1 = main(["agents", "--json"], prog="agyis")
            self.assertEqual(code1, 0)
            self.assertEqual(agyis_err.getvalue(), "")
            data_agyis = json.loads(agyis_out.getvalue().strip())

        with patch("sys.stdout", new_callable=io.StringIO) as psl_out, \
             patch("sys.stderr", new_callable=io.StringIO) as psl_err:
            code2 = deprecated_psl_main(["agents", "--json"])
            self.assertEqual(code2, 0)
            self.assertIn(PSL_DEPRECATION_WARNING.strip(), psl_err.getvalue())
            data_psl = json.loads(psl_out.getvalue().strip())

        self.assertEqual(data_agyis, data_psl)
        self.assertGreaterEqual(len(data_agyis), 6)

    def test_dual_subagents_json_purity(self):
        """Verifies agyis subagents --json and psl subagents --json produce identical JSON stdout."""
        from harness.cli import PSL_DEPRECATION_WARNING, deprecated_psl_main

        with patch("sys.stdout", new_callable=io.StringIO) as agyis_out, \
             patch("sys.stderr", new_callable=io.StringIO) as agyis_err:
            code1 = main(["subagents", "--json"], prog="agyis")
            self.assertEqual(code1, 0)
            self.assertEqual(agyis_err.getvalue(), "")
            data_agyis = json.loads(agyis_out.getvalue().strip())

        with patch("sys.stdout", new_callable=io.StringIO) as psl_out, \
             patch("sys.stderr", new_callable=io.StringIO) as psl_err:
            code2 = deprecated_psl_main(["subagents", "--json"])
            self.assertEqual(code2, 0)
            self.assertIn(PSL_DEPRECATION_WARNING.strip(), psl_err.getvalue())
            data_psl = json.loads(psl_out.getvalue().strip())

        self.assertEqual(data_agyis, data_psl)

    def test_dual_test_runner_invocations(self):
        """Verifies test runner executes with clean stderr on agyis, warning on psl."""
        from harness.cli import PSL_DEPRECATION_WARNING, deprecated_psl_main

        sample_test = "import unittest\nclass S(unittest.TestCase):\n    def test_p(self): self.assertTrue(True)\n"
        sample_file = Path(self.temp_dir.name) / "test_dual_cli_sample.py"
        sample_file.write_text(sample_test, encoding="utf-8")

        with patch("sys.stdout", new_callable=io.StringIO), \
             patch("sys.stderr", new_callable=io.StringIO) as agyis_err:
            code1 = main(["test", "-s", self.temp_dir.name], prog="agyis")
            self.assertEqual(code1, 0)
            self.assertNotIn(PSL_DEPRECATION_WARNING.strip(), agyis_err.getvalue())

        with patch("sys.stdout", new_callable=io.StringIO), \
             patch("sys.stderr", new_callable=io.StringIO) as psl_err:
            code2 = deprecated_psl_main(["test", "-s", self.temp_dir.name])
            self.assertEqual(code2, 0)
            self.assertIn(PSL_DEPRECATION_WARNING.strip(), psl_err.getvalue())

    def test_dual_init_dry_run(self):
        """Verifies init --dry-run executes with clean stderr on agyis, warning on psl."""
        from harness.cli import PSL_DEPRECATION_WARNING, deprecated_psl_main
        ws = Path(self.temp_dir.name) / "ws_init"
        ws.mkdir(parents=True)

        with patch("sys.stdout", new_callable=io.StringIO) as agyis_out, \
             patch("sys.stderr", new_callable=io.StringIO) as agyis_err:
            code1 = main(["init", str(ws), "--dry-run"], prog="agyis")
            self.assertEqual(code1, 0)
            self.assertEqual(agyis_err.getvalue(), "")

        with patch("sys.stdout", new_callable=io.StringIO) as psl_out, \
             patch("sys.stderr", new_callable=io.StringIO) as psl_err:
            code2 = deprecated_psl_main(["init", str(ws), "--dry-run"])
            self.assertEqual(code2, 0)
            self.assertIn(PSL_DEPRECATION_WARNING.strip(), psl_err.getvalue())

    def test_dual_harmonize_dry_run_json(self):
        """Verifies harmonize --dry-run --json runs cleanly on agyis and emits warning on psl."""
        from harness.cli import PSL_DEPRECATION_WARNING, deprecated_psl_main
        ws = Path(self.temp_dir.name) / "ws_harm"
        ws.mkdir(parents=True)

        with patch("sys.stdout", new_callable=io.StringIO) as agyis_out, \
             patch("sys.stderr", new_callable=io.StringIO) as agyis_err:
            code1 = main(["harmonize", str(ws), "--dry-run", "--json"], prog="agyis")
            self.assertEqual(code1, 0)
            self.assertEqual(agyis_err.getvalue(), "")
            res1 = json.loads(agyis_out.getvalue().strip())
            self.assertTrue(res1["dry_run"])

        with patch("sys.stdout", new_callable=io.StringIO) as psl_out, \
             patch("sys.stderr", new_callable=io.StringIO) as psl_err:
            code2 = deprecated_psl_main(["harmonize", str(ws), "--dry-run", "--json"])
            self.assertEqual(code2, 0)
            self.assertIn(PSL_DEPRECATION_WARNING.strip(), psl_err.getvalue())
            res2 = json.loads(psl_out.getvalue().strip())
            self.assertTrue(res2["dry_run"])

        self.assertEqual(res1["workspace_dir"], res2["workspace_dir"])

    def test_dual_doctor_subcommand(self):
        """Verifies doctor runs with clean stderr on agyis, warning on psl."""
        from harness.cli import PSL_DEPRECATION_WARNING, deprecated_psl_main

        mock_audit = {
            "summary": {"total": 5, "available": 5, "missing": 0, "outdated": 0},
            "tiers": {},
        }
        with patch("harness.runtime.doctor.run_doctor", return_value=mock_audit), \
             patch("harness.runtime.doctor.print_cli_report"):
            with patch("sys.stdout", new_callable=io.StringIO) as agyis_out, \
                 patch("sys.stderr", new_callable=io.StringIO) as agyis_err:
                code1 = main(["doctor"], prog="agyis")
                self.assertEqual(code1, 0)
                self.assertEqual(agyis_err.getvalue(), "")

            with patch("sys.stdout", new_callable=io.StringIO) as psl_out, \
                 patch("sys.stderr", new_callable=io.StringIO) as psl_err:
                code2 = deprecated_psl_main(["doctor"])
                self.assertEqual(code2, 0)
                self.assertIn(PSL_DEPRECATION_WARNING.strip(), psl_err.getvalue())

    def test_dual_remote_socket_status(self):
        """Verifies remote socket status runs with clean stderr on agyis, warning on psl."""
        from harness.cli import PSL_DEPRECATION_WARNING, deprecated_psl_main

        with patch("sys.stdout", new_callable=io.StringIO) as agyis_out, \
             patch("sys.stderr", new_callable=io.StringIO) as agyis_err:
            code1 = main(["remote", "socket", "status"], prog="agyis")
            self.assertEqual(code1, 0)
            self.assertEqual(agyis_err.getvalue(), "")

        with patch("sys.stdout", new_callable=io.StringIO) as psl_out, \
             patch("sys.stderr", new_callable=io.StringIO) as psl_err:
            code2 = deprecated_psl_main(["remote", "socket", "status"])
            self.assertEqual(code2, 0)
            self.assertIn(PSL_DEPRECATION_WARNING.strip(), psl_err.getvalue())

    def test_experimental_rea_flags_parsed(self):
        """Verifies --experimental-rea flag is accepted on doctor, init, onboard, and install."""
        from harness.cli import build_parser

        parser = build_parser()

        args_doc = parser.parse_args(["doctor", "--experimental-rea"])
        self.assertTrue(args_doc.experimental_rea)

        args_init = parser.parse_args(["init", "--experimental-rea"])
        self.assertTrue(args_init.experimental_rea)

        args_onb = parser.parse_args(["onboard", "--experimental-rea"])
        self.assertTrue(args_onb.experimental_rea)

        args_inst = parser.parse_args(["install", "--experimental-rea"])
        self.assertTrue(args_inst.experimental_rea)


if __name__ == "__main__":
    unittest.main()
