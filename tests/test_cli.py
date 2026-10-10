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
from unittest.mock import MagicMock, patch

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
            self.assertEqual(len(data), 7)

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

        ws_cfg_path = ws_root / ".psl" / "config.json"
        self.assertTrue(ws_cfg_path.exists())
        ws_data = json.loads(ws_cfg_path.read_text())
        self.assertEqual(ws_data["endpoint"], "https://ws.example.com")

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
            self.assertIn("PSL Active Subagents", out)
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


if __name__ == "__main__":
    unittest.main()
