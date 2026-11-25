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


class TestCliSyncAuthRemote(unittest.TestCase):
    """CLI auth, sync, subagents, remote, and deprecated psl alias tests."""

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
        dummy_t = Path(self.temp_dir.name) / "transcript.jsonl"
        dummy_t.write_text('{"step_index": 0, "type": "USER_INPUT", "content": "hi"}\n', encoding="utf-8")
        with patch("harness.trajectory.transcript_reader.find_transcript_path", return_value=(dummy_t, None)) as mock_find, \
             patch("harness.telemetry.config.resolve_db_path", return_value=Path(self.temp_dir.name) / "test.db"), \
             patch("harness.telemetry.extractor.extract_session", return_value=None) as mock_extract, \
             patch("harness.telemetry.sync.sync_telemetry", return_value=mock_res) as mock_sync, \
             patch("sys.stdout", new_callable=io.StringIO):
            code = main(["sync", "--session-id", "test-sess-123"])
            self.assertEqual(code, 0)
            mock_find.assert_called_once_with("test-sess-123")
            mock_extract.assert_called_once_with(dummy_t)
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


if __name__ == "__main__":
    unittest.main()
