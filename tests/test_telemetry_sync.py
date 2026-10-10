#!/usr/bin/env python3
"""
Hermetic Unit and Contract Tests for PSL Telemetry Sync Engine (ADR-030 Phase 3).

Covers:
- Schema migration & ensure_sync_columns idempotency.
- extract_session outputs origin_developer and remote_synced_at.
- Config management (load/save config & credentials, tempdir overrides, permissions, denylist matching).
- Sync push: unsynced filtering, denylist filtering, redaction, remote_synced_at update, dry_run, error propagation.
- Sync pull: delta querying, idempotent SQLite insertion, error propagation.
"""

from __future__ import annotations

from datetime import datetime, timezone
import io
import json
import os
from pathlib import Path
import sqlite3
import stat
import tempfile
from typing import Any, Dict
import unittest
from unittest.mock import MagicMock, patch
import urllib.error
import urllib.request

from harness.telemetry import config, sync
from pipeline import extract_transcripts


class TestSchemaMigration(unittest.TestCase):
    """Verifies schema evolution and ensure_sync_columns idempotency."""

    def test_ensure_sync_columns_on_legacy_db(self):
        """Verifies ensure_sync_columns adds origin_developer and remote_synced_at to legacy sessions table."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "legacy.db"
            conn = sqlite3.connect(db_path)
            cur = conn.cursor()
            # Create pre-migration sessions table without sync columns
            cur.execute("""
                CREATE TABLE sessions (
                    session_id TEXT PRIMARY KEY,
                    start_time TEXT,
                    end_time TEXT,
                    duration_seconds REAL,
                    total_steps INTEGER,
                    model TEXT,
                    workspace_path TEXT,
                    transcript_path TEXT,
                    file_size_bytes INTEGER,
                    has_errors INTEGER,
                    tool_call_count INTEGER,
                    tool_error_count INTEGER,
                    intervention_count INTEGER
                );
            """)
            # Insert a legacy session
            cur.execute("""
                INSERT INTO sessions (session_id, start_time, duration_seconds)
                VALUES ('sess-legacy-1', '2026-01-01T00:00:00Z', 10.0)
            """)
            conn.commit()

            # Execute ensure_sync_columns
            extract_transcripts.ensure_sync_columns(conn)

            # Verify columns exist
            cur.execute("PRAGMA table_info(sessions)")
            cols = {row[1]: row for row in cur.fetchall()}
            self.assertIn("origin_developer", cols)
            self.assertIn("remote_synced_at", cols)

            # Verify default value for pre-existing row
            cur.execute("SELECT origin_developer, remote_synced_at FROM sessions WHERE session_id = 'sess-legacy-1'")
            row = cur.fetchone()
            self.assertEqual(row[0], "local")
            self.assertIsNone(row[1])

            # Verify idempotency by calling again
            extract_transcripts.ensure_sync_columns(conn)
            sync.ensure_sync_columns(conn)

            # Verify indexes exist
            cur.execute("SELECT name FROM sqlite_master WHERE type='index' AND tbl_name='sessions'")
            indexes = {row[0] for row in cur.fetchall()}
            self.assertIn("idx_sessions_origin", indexes)
            self.assertIn("idx_sessions_synced", indexes)
            conn.close()

    def test_ensure_sync_columns_on_fresh_db(self):
        """Verifies ensure_sync_columns handles an uninitialized database safely."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "fresh.db"
            conn = sqlite3.connect(db_path)
            sync.ensure_sync_columns(conn)

            cur = conn.cursor()
            cur.execute("PRAGMA table_info(sessions)")
            cols = {row[1] for row in cur.fetchall()}
            self.assertIn("origin_developer", cols)
            self.assertIn("remote_synced_at", cols)
            conn.close()


class TestExtractSessionSyncFields(unittest.TestCase):
    """Verifies extract_session populates origin_developer and remote_synced_at."""

    def test_extract_session_returns_sync_fields(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            # Construct a realistic Antigravity transcript hierarchy:
            # <tmpdir>/<session_id>/.system_generated/logs/transcript.jsonl
            session_id = "test-session-uuid-123"
            t_dir = Path(tmpdir) / session_id / ".system_generated" / "logs"
            t_dir.mkdir(parents=True)
            t_file = t_dir / "transcript.jsonl"

            step_entry = {
                "step_index": 0,
                "type": "USER_INPUT",
                "source": "OPERATOR",
                "status": "DONE",
                "created_at": "2026-03-01T12:00:00Z",
                "content": "Please inspect database",
                "tool_calls": []
            }
            with open(t_file, "w", encoding="utf-8") as f:
                f.write(json.dumps(step_entry) + "\n")

            res = extract_transcripts.extract_session(t_file)
            self.assertIsNotNone(res)
            session_row, step_rows, tool_rows, interv_rows = res

            self.assertEqual(session_row["session_id"], session_id)
            self.assertEqual(session_row["origin_developer"], "local")
            self.assertIsNone(session_row["remote_synced_at"])


class TestConfigManagement(unittest.TestCase):
    """Verifies configuration, credentials, and denylist management."""

    def setUp(self):
        self.tmpdir = tempfile.TemporaryDirectory()
        self.config_dir = Path(self.tmpdir.name)
        self.patcher_env = patch.dict(os.environ, {
            "PSL_CONFIG_DIR": str(self.config_dir),
            "PSL_AUTH_TOKEN": "",
            "PSL_SYNC_ENDPOINT": "",
        })
        self.patcher_env.start()

    def tearDown(self):
        self.patcher_env.stop()
        self.tmpdir.cleanup()

    def test_config_load_defaults_and_save(self):
        cfg = config.load_config()
        self.assertEqual(cfg["endpoint"], "http://localhost:8000")
        self.assertEqual(cfg["denylist"], [])
        self.assertEqual(cfg["mode"], "opt-in")

        cfg["endpoint"] = "https://telemetry.example.com"
        cfg["denylist"] = ["/home/user/classified"]
        saved_path = config.save_config(cfg)
        self.assertTrue(saved_path.is_file())

        loaded_again = config.load_config()
        self.assertEqual(loaded_again["endpoint"], "https://telemetry.example.com")
        self.assertEqual(loaded_again["denylist"], ["/home/user/classified"])

    def test_credentials_load_defaults_and_save_permissions(self):
        creds = config.load_credentials()
        self.assertIsNone(creds["token"])
        self.assertIsNone(creds["github_username"])

        creds["token"] = "gho_testsecret1234567890abcdef"
        creds["github_username"] = "octocat"
        saved_path = config.save_credentials(creds)
        self.assertTrue(saved_path.is_file())

        # Check file permissions (0o600: read/write by owner only)
        file_stat = os.stat(saved_path)
        mode = stat.S_IMODE(file_stat.st_mode)
        self.assertEqual(mode, 0o600)

        loaded_creds = config.load_credentials()
        self.assertEqual(loaded_creds["token"], "gho_testsecret1234567890abcdef")
        self.assertEqual(loaded_creds["github_username"], "octocat")

    def test_clear_credentials(self):
        config.save_credentials({"token": "secret-to-clear", "github_username": "octocat"})
        loaded = config.load_credentials()
        self.assertEqual(loaded["token"], "secret-to-clear")

        cleared_path = config.clear_credentials()
        self.assertTrue(cleared_path.is_file())
        reloaded = config.load_credentials()
        self.assertIsNone(reloaded["token"])
        self.assertIsNone(reloaded["github_username"])

    def test_get_auth_token_precedence(self):
        # 1. No token set
        self.assertIsNone(config.get_auth_token())

        # 2. Token in credentials
        config.save_credentials({"token": "cred-token-123"})
        self.assertEqual(config.get_auth_token(), "cred-token-123")

        # 3. Environment override takes precedence
        with patch.dict(os.environ, {"PSL_AUTH_TOKEN": "env-token-456"}):
            self.assertEqual(config.get_auth_token(), "env-token-456")

    def test_get_sync_endpoint_precedence(self):
        # 1. Default endpoint
        self.assertEqual(config.get_sync_endpoint(), "http://localhost:8000")

        # 2. Configured endpoint
        config.save_config({"endpoint": "https://custom.telemetry.org"})
        self.assertEqual(config.get_sync_endpoint(), "https://custom.telemetry.org")

        # 3. Environment override takes precedence
        with patch.dict(os.environ, {"PSL_SYNC_ENDPOINT": "https://env.telemetry.org"}):
            self.assertEqual(config.get_sync_endpoint(), "https://env.telemetry.org")

    def test_denylist_matching_and_mutation(self):
        secret_dir = Path(self.tmpdir.name) / "secret-repo"
        secret_dir.mkdir()
        sub_dir = secret_dir / "submodule"
        sub_dir.mkdir()
        public_dir = Path(self.tmpdir.name) / "public-repo"
        public_dir.mkdir()

        # Add to denylist
        self.assertTrue(config.add_to_denylist(str(secret_dir)))
        self.assertFalse(config.add_to_denylist(str(secret_dir)))  # Duplicate returns False

        # Add wildcard pattern
        self.assertTrue(config.add_to_denylist("*/wildcard-secret/*"))

        # Check exact path
        self.assertTrue(config.is_workspace_denylisted(secret_dir))
        # Check subfolder of denylisted directory
        self.assertTrue(config.is_workspace_denylisted(sub_dir))
        # Check wildcard pattern
        self.assertTrue(config.is_workspace_denylisted("/opt/projects/wildcard-secret/app"))
        # Check public directory (not denylisted)
        self.assertFalse(config.is_workspace_denylisted(public_dir))

        # Remove from denylist
        self.assertTrue(config.remove_from_denylist(str(secret_dir)))
        self.assertFalse(config.remove_from_denylist(str(secret_dir)))  # Non-existent returns False
        self.assertFalse(config.is_workspace_denylisted(secret_dir))

        # Check parent folder of denylisted subfolder is NOT blocked (Defect 4)
        parent_workspace = Path(self.tmpdir.name) / "parent-workspace"
        child_secret = parent_workspace / "secret-sub"
        parent_workspace.mkdir()
        child_secret.mkdir()
        config.add_to_denylist(str(child_secret))
        self.assertTrue(config.is_workspace_denylisted(child_secret))
        self.assertFalse(config.is_workspace_denylisted(parent_workspace))

    def test_empty_string_in_denylist_rejected(self):
        """Verifies empty or whitespace-only paths are rejected from denylist (Defect 5)."""
        self.assertFalse(config.add_to_denylist(""))
        self.assertFalse(config.add_to_denylist("   "))
        self.assertFalse(config.remove_from_denylist(""))
        self.assertFalse(config.remove_from_denylist("   "))

    def test_resolve_db_path_hierarchy_and_no_pwd_probing(self):
        """Verifies resolve_db_path hierarchy and guarantees PWD is never probed."""
        custom_db = Path(self.tmpdir.name) / "custom.db"
        custom_db.touch()

        # 1. Explicit db_path flag
        self.assertEqual(config.resolve_db_path(custom_db), custom_db.resolve())

        # 2. PSL_TELEMETRY_DB env override
        with patch.dict(os.environ, {"PSL_TELEMETRY_DB": str(custom_db)}):
            self.assertEqual(config.resolve_db_path(), custom_db.resolve())

        # 3. must_exist=True raises FileNotFoundError when target absent
        missing_db = Path(self.tmpdir.name) / "does_not_exist.db"
        with self.assertRaises(FileNotFoundError):
            config.resolve_db_path(missing_db, must_exist=True)

        # 4. Strict invariant: never probe PWD/data/telemetry.db
        fake_pwd_dir = Path(self.tmpdir.name) / "alien_cwd"
        fake_pwd_data = fake_pwd_dir / "data"
        fake_pwd_data.mkdir(parents=True)
        fake_pwd_db = fake_pwd_data / "telemetry.db"
        fake_pwd_db.touch()

        with patch("pathlib.Path.cwd", return_value=fake_pwd_dir), \
             patch("os.getcwd", return_value=str(fake_pwd_dir)):
            # With repo data/telemetry.db mocked as non-existent
            with patch.object(Path, "is_file", autospec=True) as mock_is_file:
                # Let only fake_pwd_db exist if checked by mistake
                def fake_is_file(p):
                    return str(p) == str(fake_pwd_db.resolve())
                mock_is_file.side_effect = fake_is_file
                resolved = config.resolve_db_path()
                self.assertNotEqual(resolved, fake_pwd_db.resolve())

    def test_workspace_endpoint_precedence(self):
        """Verifies endpoint precedence: CLI > ENV > workspace > global > default."""
        ws_dir = Path(self.tmpdir.name) / "my_workspace"
        ws_dir.mkdir()
        (ws_dir / ".psl").mkdir()

        # Global config
        config.save_config({"endpoint": "https://global.telemetry.org"}, scope="global")
        # Workspace config
        config.save_config({"endpoint": "https://workspace.telemetry.org"}, scope="workspace", workspace_root=ws_dir)

        # 1. Global config resolved when no workspace
        self.assertEqual(config.get_sync_endpoint(), "https://global.telemetry.org")

        # 2. Workspace config overrides global
        self.assertEqual(config.get_sync_endpoint(workspace_root=ws_dir), "https://workspace.telemetry.org")

        # 3. PSL_SYNC_ENDPOINT overrides workspace
        with patch.dict(os.environ, {"PSL_SYNC_ENDPOINT": "https://env.telemetry.org"}):
            self.assertEqual(config.get_sync_endpoint(workspace_root=ws_dir), "https://env.telemetry.org")

        # 4. Explicit CLI argument overrides all
        self.assertEqual(config.get_sync_endpoint("https://cli.telemetry.org", workspace_root=ws_dir), "https://cli.telemetry.org")

    def test_get_gh_cli_token_lifting(self):
        """Verifies get_gh_cli_token extracts token or returns None safely."""
        # 1. Successful gh execution
        mock_proc_ok = MagicMock(returncode=0, stdout=" gho_supersecret_token123 \n")
        with patch("subprocess.run", return_value=mock_proc_ok) as mock_sub:
            token = config.get_gh_cli_token()
            self.assertEqual(token, "gho_supersecret_token123")
            mock_sub.assert_called_once_with(
                ["gh", "auth", "token"],
                timeout=5.0,
                capture_output=True,
                text=True,
                check=False,
            )

        # 2. Failed gh execution (e.g. not logged in, returncode != 0)
        mock_proc_err = MagicMock(returncode=1, stdout="")
        with patch("subprocess.run", return_value=mock_proc_err):
            self.assertIsNone(config.get_gh_cli_token())

        # 3. gh binary not found on system (FileNotFoundError)
        with patch("subprocess.run", side_effect=FileNotFoundError("gh not found")):
            self.assertIsNone(config.get_gh_cli_token())


class TestSyncPush(unittest.TestCase):
    """Verifies push_local_sessions filtering, redaction, SQLite state update, and dry_run."""

    def setUp(self):
        self.tmpdir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.tmpdir.name) / "telemetry.db"
        self.config_dir = Path(self.tmpdir.name) / "config"
        self.config_dir.mkdir()

        self.patcher_env = patch.dict(os.environ, {
            "PSL_CONFIG_DIR": str(self.config_dir),
            "PSL_AUTH_TOKEN": "test-bearer-token",
            "PSL_SYNC_ENDPOINT": "https://api.telemetry.test",
        })
        self.patcher_env.start()

        # Initialize SQLite DB schema
        conn = sqlite3.connect(self.db_path)
        cur = conn.cursor()
        cur.executescript(extract_transcripts.SCHEMA_SQL)
        extract_transcripts.ensure_sync_columns(conn)

        # Seed session 1: Unsynced local session with secrets and paths
        cur.execute("""
            INSERT INTO sessions (
                session_id, start_time, duration_seconds, total_steps,
                workspace_path, transcript_path, origin_developer, remote_synced_at
            ) VALUES (
                'sess-1', '2026-03-01T10:00:00Z', 60.0, 1,
                '/home/kuasha/Dev/project-alpha', '/home/kuasha/.gemini/antigravity/brain/sess-1/logs/transcript.jsonl',
                'local', NULL
            )
        """)
        cur.execute("""
            INSERT INTO steps (
                session_id, step_index, step_type, source, status, created_at,
                content_length, content_snippet, has_thinking, thinking_length, tool_count
            ) VALUES (
                'sess-1', 0, 'AGENT_OUTPUT', 'MODEL', 'DONE', '2026-03-01T10:01:00Z',
                50, 'Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.dummy_jwt in /home/kuasha/Dev/project-alpha/src',
                0, 0, 1
            )
        """)
        cur.execute("""
            INSERT INTO tool_calls (
                session_id, step_index, tool_name, arguments_json, arguments_snippet,
                target_path, command_line, status
            ) VALUES (
                'sess-1', 0, 'run_command',
                '{"cmd": "curl -H \\"Authorization: token ghp_1234567890abcdef1234567890abcdef\\" /home/kuasha/Dev/project-alpha"}',
                'curl -H Authorization: token ghp_1234567890abcdef1234567890abcdef',
                '/home/kuasha/Dev/project-alpha/deploy.sh',
                'bash --password mysecretpass123',
                'SUCCESS'
            )
        """)
        cur.execute("""
            INSERT INTO user_interventions (
                session_id, step_index, created_at, prompt_text, prompt_length,
                preceding_tool_failed, preceding_tool_name, preceding_error_snippet, intervention_type
            ) VALUES (
                'sess-1', 0, '2026-03-01T10:02:00Z',
                'Please use api_key="sk-proj-1234567890abcdef12345678" at /home/kuasha/Dev/project-alpha',
                70, 0, 'run_command', NULL, 'OPERATOR_GUIDANCE'
            )
        """)

        # Seed session 2: Already synced session (should be skipped)
        cur.execute("""
            INSERT INTO sessions (
                session_id, start_time, duration_seconds, total_steps,
                workspace_path, transcript_path, origin_developer, remote_synced_at
            ) VALUES (
                'sess-2', '2026-03-01T11:00:00Z', 30.0, 1,
                '/home/kuasha/Dev/project-beta', '/tmp/sess-2.jsonl',
                'local', '2026-03-01T11:30:00Z'
            )
        """)

        # Seed session 3: Denylisted workspace session (should be skipped)
        cur.execute("""
            INSERT INTO sessions (
                session_id, start_time, duration_seconds, total_steps,
                workspace_path, transcript_path, origin_developer, remote_synced_at
            ) VALUES (
                'sess-3', '2026-03-01T12:00:00Z', 45.0, 1,
                '/home/kuasha/Dev/classified-project', '/tmp/sess-3.jsonl',
                'local', NULL
            )
        """)
        conn.commit()
        conn.close()

        # Add classified project to denylist
        config.add_to_denylist("/home/kuasha/Dev/classified-project")

    def tearDown(self):
        self.patcher_env.stop()
        self.tmpdir.cleanup()

    def test_push_dry_run_mode(self):
        """Dry run returns summary without sending HTTP request or updating SQLite."""
        with patch("urllib.request.urlopen") as mock_urlopen:
            res = sync.push_local_sessions(
                db_path=self.db_path,
                workspace_root="/home/kuasha/Dev/project-alpha",
                dry_run=True,
            )
            mock_urlopen.assert_not_called()

            self.assertEqual(res["status"], "dry_run")
            self.assertTrue(res["dry_run"])
            self.assertEqual(res["sessions_pushed"], 1)
            self.assertEqual(res["steps_pushed"], 1)
            self.assertEqual(res["tool_calls_pushed"], 1)
            self.assertEqual(res["user_interventions_pushed"], 1)
            self.assertIsNone(res["synced_at"])

            # Verify SQLite remote_synced_at remained NULL
            conn = sqlite3.connect(self.db_path)
            cur = conn.cursor()
            cur.execute("SELECT remote_synced_at FROM sessions WHERE session_id = 'sess-1'")
            self.assertIsNone(cur.fetchone()[0])
            conn.close()

    def test_push_successful_transmission_and_redaction(self):
        """Verifies HTTP transmission, payload redaction, and remote_synced_at updating."""
        mock_response = MagicMock()
        mock_response.read.return_value = b'{"status": "accepted"}'
        mock_response.__enter__.return_value = mock_response

        with patch("urllib.request.urlopen", return_value=mock_response) as mock_urlopen:
            res = sync.push_local_sessions(
                db_path=self.db_path,
                workspace_root="/home/kuasha/Dev/project-alpha",
                dry_run=False,
            )

            self.assertEqual(res["status"], "success")
            self.assertFalse(res["dry_run"])
            self.assertEqual(res["sessions_pushed"], 1)
            self.assertIsNotNone(res["synced_at"])

            # Verify HTTP call arguments
            mock_urlopen.assert_called_once()
            req: urllib.request.Request = mock_urlopen.call_args[0][0]
            self.assertEqual(req.get_full_url(), "https://api.telemetry.test/api/v1/sync/push")
            self.assertEqual(req.get_header("Authorization"), "Bearer test-bearer-token")
            self.assertEqual(req.get_header("Content-type"), "application/json")

            # Parse sent payload and verify redaction
            payload = json.loads(req.data.decode("utf-8"))
            self.assertEqual(payload["client_version"], "1.0.0")

            # 1. Sessions: paths anonymized
            p_sess = payload["sessions"][0]
            self.assertEqual(p_sess["session_id"], "sess-1")
            self.assertEqual(p_sess["workspace_path"], "[WORKSPACE_ROOT]")
            self.assertNotIn("/home/kuasha", p_sess["workspace_path"])

            # 2. Steps: JWT redacted, paths anonymized
            p_step = payload["steps"][0]
            self.assertNotIn("eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.dummy_jwt", p_step["content_snippet"])
            self.assertIn("[REDACTED_SECRET]", p_step["content_snippet"])
            self.assertIn("[WORKSPACE_ROOT]/src", p_step["content_snippet"])

            # 3. Tool Calls: GitHub token redacted via auth header, password flag redacted
            p_tool = payload["tool_calls"][0]
            self.assertNotIn("ghp_1234567890abcdef1234567890abcdef", p_tool["arguments_json"])
            self.assertIn("[REDACTED_SECRET]", p_tool["arguments_json"])
            self.assertNotIn("mysecretpass123", p_tool["command_line"])
            self.assertIn("[REDACTED_PASSWORD]", p_tool["command_line"])
            self.assertEqual(p_tool["target_path"], "[WORKSPACE_ROOT]/deploy.sh")

            # 4. User Interventions: OpenAI key redacted via api_key assignment
            p_interv = payload["user_interventions"][0]
            self.assertNotIn("sk-proj-1234567890abcdef12345678", p_interv["prompt_text"])
            self.assertIn("[REDACTED_API_KEY]", p_interv["prompt_text"])
            self.assertIn("[WORKSPACE_ROOT]", p_interv["prompt_text"])

            # Verify SQLite database was updated with sync timestamp
            conn = sqlite3.connect(self.db_path)
            cur = conn.cursor()
            cur.execute("SELECT remote_synced_at FROM sessions WHERE session_id = 'sess-1'")
            synced_val = cur.fetchone()[0]
            self.assertIsNotNone(synced_val)
            self.assertEqual(synced_val, res["synced_at"])
            conn.close()

    def test_push_http_failure_propagates_and_rolls_back_sync(self):
        """Verifies zero error swallowing when HTTP request fails."""
        err = urllib.error.HTTPError(
            url="https://api.telemetry.test/api/v1/telemetry/batch",
            code=502,
            msg="Bad Gateway",
            hdrs=MagicMock(),
            fp=io.BytesIO(b"gateway error"),
        )
        try:
            with patch("urllib.request.urlopen", side_effect=err):
                with self.assertRaises(urllib.error.HTTPError):
                    sync.push_local_sessions(db_path=self.db_path, retry_backoff=0.0)
        finally:
            err.close()

            # Assert remote_synced_at remains unpopulated
            conn = sqlite3.connect(self.db_path)
            cur = conn.cursor()
            cur.execute("SELECT remote_synced_at FROM sessions WHERE session_id = 'sess-1'")
            self.assertIsNone(cur.fetchone()[0])
            conn.close()

    def test_push_missing_credentials_raises(self):
        with patch.dict(os.environ, {"PSL_AUTH_TOKEN": ""}):
            with self.assertRaises(ValueError):
                sync.push_local_sessions(db_path=self.db_path, token=None)

    def test_push_fallback_to_telemetry_batch_on_404(self):
        """Verifies push falls back to /api/v1/telemetry/batch when /api/v1/sync/push returns 404."""
        err_404 = urllib.error.HTTPError(
            url="https://api.telemetry.test/api/v1/sync/push",
            code=404,
            msg="Not Found",
            hdrs=MagicMock(),
            fp=io.BytesIO(b"Not Found"),
        )
        mock_success = MagicMock()
        mock_success.read.return_value = b'{"status": "accepted"}'
        mock_success.__enter__.return_value = mock_success

        try:
            with patch("urllib.request.urlopen", side_effect=[err_404, mock_success]) as mock_urlopen:
                res = sync.push_local_sessions(
                    db_path=self.db_path,
                    workspace_root="/home/kuasha/Dev/project-alpha",
                    dry_run=False,
                )
                self.assertEqual(res["status"], "success")
                self.assertEqual(mock_urlopen.call_count, 2)
                req1 = mock_urlopen.call_args_list[0][0][0]
                req2 = mock_urlopen.call_args_list[1][0][0]
                self.assertEqual(req1.get_full_url(), "https://api.telemetry.test/api/v1/sync/push")
                self.assertEqual(req2.get_full_url(), "https://api.telemetry.test/api/v1/telemetry/batch")
        finally:
            err_404.close()

    def test_push_local_sessions_chunking(self):
        """Verifies session chunking by session limit and step limit with progress updates."""
        conn = sqlite3.connect(self.db_path)
        cur = conn.cursor()
        # Clean previous test sessions to isolate chunking test
        cur.execute("DELETE FROM sessions")
        cur.execute("DELETE FROM steps")
        for i in range(15):
            cur.execute("""
                INSERT INTO sessions (session_id, start_time, duration_seconds, total_steps, origin_developer, remote_synced_at)
                VALUES (?, '2026-03-01T10:00:00Z', 10.0, 5, 'local', NULL)
            """, (f"sess-chunk-{i:02d}",))
            cur.execute("""
                INSERT INTO steps (session_id, step_index, step_type, source, status, created_at)
                VALUES (?, 0, 'AGENT_OUTPUT', 'MODEL', 'DONE', '2026-03-01T10:01:00Z')
            """, (f"sess-chunk-{i:02d}",))
        conn.commit()
        conn.close()

        mock_resp = MagicMock()
        mock_resp.read.return_value = b'{"status": "accepted"}'
        mock_resp.__enter__.return_value = mock_resp

        progress_log = []
        def on_prog(batch_idx, total_batches, stats):
            progress_log.append((batch_idx, total_batches, stats["sessions"]))

        with patch("urllib.request.urlopen", return_value=mock_resp) as mock_urlopen:
            res = sync.push_local_sessions(
                db_path=self.db_path,
                on_progress=on_prog,
                retry_backoff=0.0,
            )
            self.assertEqual(res["status"], "success")
            self.assertEqual(res["sessions_pushed"], 15)
            self.assertEqual(res["batches_count"], 2)
            self.assertEqual(mock_urlopen.call_count, 2)

            # Check batch sizes in requests
            req1 = mock_urlopen.call_args_list[0][0][0]
            req2 = mock_urlopen.call_args_list[1][0][0]
            payload1 = json.loads(req1.data.decode("utf-8"))
            payload2 = json.loads(req2.data.decode("utf-8"))
            self.assertEqual(len(payload1["sessions"]), 10)
            self.assertEqual(len(payload2["sessions"]), 5)

            # Check progress callback invocation
            self.assertEqual(progress_log, [(1, 2, 10), (2, 2, 5)])

    def test_push_batch_step_limit_threshold(self):
        """Verifies a single session exceeding DEFAULT_BATCH_STEP_LIMIT occupies its own batch."""
        conn = sqlite3.connect(self.db_path)
        cur = conn.cursor()
        cur.execute("DELETE FROM sessions")
        cur.execute("""
            INSERT INTO sessions (session_id, start_time, duration_seconds, total_steps, origin_developer, remote_synced_at)
            VALUES ('sess-huge-steps', '2026-03-01T10:00:00Z', 100.0, 2600, 'local', NULL)
        """)
        cur.execute("""
            INSERT INTO sessions (session_id, start_time, duration_seconds, total_steps, origin_developer, remote_synced_at)
            VALUES ('sess-small-steps', '2026-03-01T10:01:00Z', 10.0, 5, 'local', NULL)
        """)
        conn.commit()
        conn.close()

        mock_resp = MagicMock()
        mock_resp.read.return_value = b'{"status": "accepted"}'
        mock_resp.__enter__.return_value = mock_resp

        with patch("urllib.request.urlopen", return_value=mock_resp) as mock_urlopen:
            res = sync.push_local_sessions(
                db_path=self.db_path,
                retry_backoff=0.0,
            )
            self.assertEqual(res["batches_count"], 2)
            self.assertEqual(mock_urlopen.call_count, 2)
            req1 = mock_urlopen.call_args_list[0][0][0]
            req2 = mock_urlopen.call_args_list[1][0][0]
            p1 = json.loads(req1.data.decode("utf-8"))
            p2 = json.loads(req2.data.decode("utf-8"))
            self.assertEqual(len(p1["sessions"]), 1)
            self.assertEqual(p1["sessions"][0]["session_id"], "sess-huge-steps")
            self.assertEqual(len(p2["sessions"]), 1)
            self.assertEqual(p2["sessions"][0]["session_id"], "sess-small-steps")

    def test_batch_transactional_atomic_commit(self):
        """Verifies transactional atomicity: batch 1 remains committed when batch 2 fails."""
        conn = sqlite3.connect(self.db_path)
        cur = conn.cursor()
        cur.execute("DELETE FROM sessions")
        for i in range(12):
            cur.execute("""
                INSERT INTO sessions (session_id, start_time, duration_seconds, total_steps, origin_developer, remote_synced_at)
                VALUES (?, '2026-03-01T10:00:00Z', 10.0, 5, 'local', NULL)
            """, (f"sess-tx-{i:02d}",))
        conn.commit()
        conn.close()

        mock_resp_1 = MagicMock()
        mock_resp_1.read.return_value = b'{"status": "accepted"}'
        mock_resp_1.__enter__.return_value = mock_resp_1

        err_batch_2 = urllib.error.HTTPError(
            url="https://api.telemetry.test/api/v1/sync/push",
            code=500,
            msg="Internal Server Error",
            hdrs=MagicMock(),
            fp=io.BytesIO(b"Internal Server Error"),
        )

        try:
            with patch("urllib.request.urlopen", side_effect=[mock_resp_1, err_batch_2]):
                with self.assertRaises(urllib.error.HTTPError):
                    sync.push_local_sessions(
                        db_path=self.db_path,
                        retry_backoff=0.0,
                    )
        finally:
            err_batch_2.close()

        # Verify SQLite state: batch 1 sessions are synced, batch 2 sessions are still unsynced
        conn = sqlite3.connect(self.db_path)
        cur = conn.cursor()
        cur.execute("SELECT COUNT(*) FROM sessions WHERE remote_synced_at IS NOT NULL")
        synced_count = cur.fetchone()[0]
        cur.execute("SELECT COUNT(*) FROM sessions WHERE remote_synced_at IS NULL")
        unsynced_count = cur.fetchone()[0]
        conn.close()

        self.assertEqual(synced_count, 10, "Batch 1 must remain committed in SQLite")
        self.assertEqual(unsynced_count, 2, "Batch 2 must remain unsynced in SQLite")

    def test_transient_retry_and_fast_failure(self):
        """Verifies transient 503 retry succeeds and 403 fails fast without retry."""
        mock_resp_ok = MagicMock()
        mock_resp_ok.read.return_value = b'{"status": "accepted"}'
        mock_resp_ok.__enter__.return_value = mock_resp_ok

        err_503 = urllib.error.HTTPError(
            url="https://api.telemetry.test/api/v1/sync/push",
            code=503,
            msg="Service Unavailable",
            hdrs=MagicMock(),
            fp=io.BytesIO(b"Service Unavailable"),
        )

        # 1. Transient 503: retry succeeds on second attempt
        try:
            with patch("urllib.request.urlopen", side_effect=[err_503, mock_resp_ok]) as mock_call:
                res = sync.push_local_sessions(
                    db_path=self.db_path,
                    retry_backoff=0.0,
                )
                self.assertEqual(res["status"], "success")
                self.assertEqual(mock_call.call_count, 2)
        finally:
            err_503.close()

        # 2. Fast failure on 403: zero retries
        conn = sqlite3.connect(self.db_path)
        cur = conn.cursor()
        cur.execute("UPDATE sessions SET remote_synced_at = NULL")
        conn.commit()
        conn.close()

        err_403 = urllib.error.HTTPError(
            url="https://api.telemetry.test/api/v1/sync/push",
            code=403,
            msg="Forbidden",
            hdrs=MagicMock(),
            fp=io.BytesIO(b"Forbidden"),
        )
        try:
            with patch("urllib.request.urlopen", side_effect=err_403) as mock_call:
                with self.assertRaises(urllib.error.HTTPError):
                    sync.push_local_sessions(
                        db_path=self.db_path,
                        retry_backoff=0.0,
                    )
                self.assertEqual(mock_call.call_count, 1, "403 must fail immediately with zero retries")
        finally:
            err_403.close()


class TestSyncPull(unittest.TestCase):
    """Verifies pull_remote_sessions delta querying, idempotent insertion, and error handling."""

    def setUp(self):
        self.tmpdir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.tmpdir.name) / "telemetry_pull.db"
        self.config_dir = Path(self.tmpdir.name) / "config"
        self.config_dir.mkdir()

        self.patcher_env = patch.dict(os.environ, {
            "PSL_CONFIG_DIR": str(self.config_dir),
            "PSL_AUTH_TOKEN": "pull-bearer-token",
            "PSL_SYNC_ENDPOINT": "https://api.telemetry.test",
        })
        self.patcher_env.start()

        conn = sqlite3.connect(self.db_path)
        cur = conn.cursor()
        cur.executescript(extract_transcripts.SCHEMA_SQL)
        extract_transcripts.ensure_sync_columns(conn)
        conn.commit()
        conn.close()

    def tearDown(self):
        self.patcher_env.stop()
        self.tmpdir.cleanup()

    def test_pull_delta_and_idempotent_insertion(self):
        """Verifies delta querying and idempotent insertion into local SQLite."""
        remote_data = {
            "sessions": [{
                "session_id": "remote-sess-100",
                "start_time": "2026-03-02T10:00:00Z",
                "end_time": "2026-03-02T10:05:00Z",
                "duration_seconds": 300.0,
                "total_steps": 2,
                "model": "gemini-2.5-pro",
                "workspace_path": "$WORKSPACE",
                "transcript_path": "$WORKSPACE/logs/transcript.jsonl",
                "file_size_bytes": 1024,
                "has_errors": 0,
                "tool_call_count": 1,
                "tool_error_count": 0,
                "intervention_count": 0,
                "origin_developer": "peer-developer-42",
                "remote_synced_at": "2026-03-02T10:06:00Z",
            }],
            "steps": [{
                "session_id": "remote-sess-100",
                "step_index": 0,
                "step_type": "AGENT_OUTPUT",
                "source": "MODEL",
                "status": "DONE",
                "created_at": "2026-03-02T10:01:00Z",
                "content_length": 25,
                "content_snippet": "Executing remote script",
                "has_thinking": 0,
                "thinking_length": 0,
                "tool_count": 1,
            }],
            "tool_calls": [{
                "session_id": "remote-sess-100",
                "step_index": 0,
                "result_step_index": 1,
                "tool_name": "run_command",
                "arguments_json": '{"cmd": "pytest"}',
                "arguments_snippet": "pytest",
                "target_path": None,
                "command_line": "pytest",
                "started_at": "2026-03-02T10:01:05Z",
                "completed_at": "2026-03-02T10:01:10Z",
                "duration_seconds": 5.0,
                "status": "SUCCESS",
                "exit_code": 0,
                "error_snippet": None,
                "is_loop_candidate": 0,
                "output_length_chars": 50,
                "output_lines": 3,
                "arguments_length_chars": 15,
                "command_category": "testing",
                "is_truncated": 0,
            }],
            "user_interventions": [],
        }

        mock_resp = MagicMock()
        mock_resp.read.return_value = json.dumps(remote_data).encode("utf-8")
        mock_resp.__enter__.return_value = mock_resp

        with patch("urllib.request.urlopen", return_value=mock_resp) as mock_urlopen:
            # 1. First pull
            summary = sync.pull_remote_sessions(
                db_path=self.db_path,
                since="2026-03-01T00:00:00Z",
            )
            self.assertEqual(summary["status"], "success")
            self.assertEqual(summary["sessions_pulled"], 1)
            self.assertEqual(summary["sessions_inserted"], 1)
            self.assertEqual(summary["steps_pulled"], 1)
            self.assertEqual(summary["steps_inserted"], 1)
            self.assertEqual(summary["tool_calls_pulled"], 1)
            self.assertEqual(summary["tool_calls_inserted"], 1)

            # Verify SQLite row
            conn = sqlite3.connect(self.db_path)
            cur = conn.cursor()
            cur.execute("SELECT session_id, origin_developer FROM sessions WHERE session_id = 'remote-sess-100'")
            row = cur.fetchone()
            self.assertIsNotNone(row)
            self.assertEqual(row[1], "peer-developer-42")

            cur.execute("SELECT COUNT(*) FROM steps WHERE session_id = 'remote-sess-100'")
            self.assertEqual(cur.fetchone()[0], 1)

            cur.execute("SELECT COUNT(*) FROM tool_calls WHERE session_id = 'remote-sess-100'")
            self.assertEqual(cur.fetchone()[0], 1)
            conn.close()

            # 2. Second pull with identical payload: assert idempotency (no duplicate rows)
            summary_again = sync.pull_remote_sessions(
                db_path=self.db_path,
                since="2026-03-01T00:00:00Z",
            )
            self.assertEqual(summary_again["sessions_inserted"], 0)
            self.assertEqual(summary_again["steps_inserted"], 0)
            self.assertEqual(summary_again["tool_calls_inserted"], 0)

            conn = sqlite3.connect(self.db_path)
            cur = conn.cursor()
            cur.execute("SELECT COUNT(*) FROM sessions WHERE session_id = 'remote-sess-100'")
            self.assertEqual(cur.fetchone()[0], 1)
            cur.execute("SELECT COUNT(*) FROM steps WHERE session_id = 'remote-sess-100'")
            self.assertEqual(cur.fetchone()[0], 1)
            cur.execute("SELECT COUNT(*) FROM tool_calls WHERE session_id = 'remote-sess-100'")
            self.assertEqual(cur.fetchone()[0], 1)
            conn.close()

    def test_pull_http_error_propagates(self):
        """Verifies URLError is raised cleanly on network failure."""
        with patch("urllib.request.urlopen", side_effect=urllib.error.URLError("Connection refused")):
            with self.assertRaises(urllib.error.URLError):
                sync.pull_remote_sessions(db_path=self.db_path)

    def test_multi_tool_calls_in_single_step_preserved(self):
        """Verifies multiple tool calls in a single step with the same tool name are preserved."""
        remote_data = {
            "sessions": [{
                "session_id": "remote-multi-tool",
                "start_time": "2026-03-02T10:00:00Z",
                "origin_developer": "peer-developer-88",
                "remote_synced_at": "2026-03-02T10:05:00Z",
            }],
            "steps": [{
                "session_id": "remote-multi-tool",
                "step_index": 0,
                "step_type": "AGENT_OUTPUT",
                "source": "MODEL",
                "status": "DONE",
                "created_at": "2026-03-02T10:01:00Z",
                "content_length": 50,
                "tool_count": 2,
            }],
            "tool_calls": [
                {
                    "session_id": "remote-multi-tool",
                    "step_index": 0,
                    "tool_name": "run_command",
                    "arguments_json": '{"cmd": "pytest"}',
                    "arguments_snippet": "pytest",
                    "started_at": "2026-03-02T10:01:05Z",
                    "status": "SUCCESS",
                },
                {
                    "session_id": "remote-multi-tool",
                    "step_index": 0,
                    "tool_name": "run_command",
                    "arguments_json": '{"cmd": "git status"}',
                    "arguments_snippet": "git status",
                    "started_at": "2026-03-02T10:01:15Z",
                    "status": "SUCCESS",
                },
            ],
            "user_interventions": [],
        }

        mock_resp = MagicMock()
        mock_resp.read.return_value = json.dumps(remote_data).encode("utf-8")
        mock_resp.__enter__.return_value = mock_resp

        with patch("urllib.request.urlopen", return_value=mock_resp):
            # 1. Pull multi-tool session
            summary = sync.pull_remote_sessions(
                db_path=self.db_path,
                since="2026-03-01T00:00:00Z",
            )
            self.assertEqual(summary["tool_calls_pulled"], 2)
            self.assertEqual(summary["tool_calls_inserted"], 2)

            conn = sqlite3.connect(self.db_path)
            cur = conn.cursor()
            cur.execute("SELECT COUNT(*) FROM tool_calls WHERE session_id = 'remote-multi-tool'")
            self.assertEqual(cur.fetchone()[0], 2)
            conn.close()

            # 2. Idempotent re-pull: both tool calls recognized as existing
            summary_again = sync.pull_remote_sessions(
                db_path=self.db_path,
                since="2026-03-01T00:00:00Z",
            )
            self.assertEqual(summary_again["tool_calls_inserted"], 0)

            conn = sqlite3.connect(self.db_path)
            cur = conn.cursor()
            cur.execute("SELECT COUNT(*) FROM tool_calls WHERE session_id = 'remote-multi-tool'")
            self.assertEqual(cur.fetchone()[0], 2)
            conn.close()

    def test_since_watermark_ignores_local_pushed_sessions(self):
        """Verifies watermark calculation ignores local pushed sessions and defaults to 1970."""
        conn = sqlite3.connect(self.db_path)
        cur = conn.cursor()
        cur.execute("""
            INSERT INTO sessions (
                session_id, start_time, origin_developer, remote_synced_at
            ) VALUES (
                'local-sess-pushed', '2026-03-05T10:00:00Z', 'local', '2026-03-05T10:05:00Z'
            )
        """)
        cur.execute("""
            INSERT INTO steps (session_id, step_index, created_at)
            VALUES ('local-sess-pushed', 0, '2026-03-05T10:01:00Z')
        """)
        conn.commit()
        conn.close()

        mock_resp = MagicMock()
        mock_resp.read.return_value = b'{"sessions": [], "steps": [], "tool_calls": [], "user_interventions": []}'
        mock_resp.__enter__.return_value = mock_resp

        with patch("urllib.request.urlopen", return_value=mock_resp) as mock_urlopen:
            # When no remote sessions exist, since must be 1970-01-01T00:00:00Z
            summary = sync.pull_remote_sessions(db_path=self.db_path, since=None)
            self.assertEqual(summary["since"], "1970-01-01T00:00:00Z")
            req = mock_urlopen.call_args[0][0]
            self.assertIn("since=1970-01-01T00%3A00%3A00Z", req.get_full_url())

        # Now insert a remote session with remote_synced_at
        conn = sqlite3.connect(self.db_path)
        cur = conn.cursor()
        cur.execute("""
            INSERT INTO sessions (
                session_id, start_time, origin_developer, remote_synced_at
            ) VALUES (
                'remote-sess-earlier', '2026-03-02T10:00:00Z', 'remote-peer', '2026-03-02T10:05:00Z'
            )
        """)
        conn.commit()
        conn.close()

        with patch("urllib.request.urlopen", return_value=mock_resp) as mock_urlopen:
            # Watermark should now advance to remote session's remote_synced_at
            summary = sync.pull_remote_sessions(db_path=self.db_path, since=None)
            self.assertEqual(summary["since"], "2026-03-02T10:05:00Z")
            req = mock_urlopen.call_args[0][0]
            self.assertIn("since=2026-03-02T10%3A05%3A00Z", req.get_full_url())

    def test_pull_fallback_to_telemetry_delta_on_404(self):
        """Verifies pull falls back to /api/v1/telemetry/delta when /api/v1/sync/pull returns 404."""
        err_404 = urllib.error.HTTPError(
            url="https://api.telemetry.test/api/v1/sync/pull",
            code=404,
            msg="Not Found",
            hdrs=MagicMock(),
            fp=io.BytesIO(b"Not Found"),
        )
        mock_success = MagicMock()
        mock_success.read.return_value = b'{"sessions": [], "steps": [], "tool_calls": [], "user_interventions": []}'
        mock_success.__enter__.return_value = mock_success

        try:
            with patch("urllib.request.urlopen", side_effect=[err_404, mock_success]) as mock_urlopen:
                res = sync.pull_remote_sessions(db_path=self.db_path)
                self.assertEqual(res["status"], "success")
                self.assertEqual(mock_urlopen.call_count, 2)
                req1 = mock_urlopen.call_args_list[0][0][0]
                req2 = mock_urlopen.call_args_list[1][0][0]
                self.assertIn("/api/v1/sync/pull", req1.get_full_url())
                self.assertIn("/api/v1/telemetry/delta", req2.get_full_url())
        finally:
            err_404.close()

    def test_pull_with_all_developers_and_developer_filter(self):
        """Verifies pull_remote_sessions passes all_developers and developer query parameters."""
        mock_resp = MagicMock()
        mock_resp.read.return_value = b'{"sessions": [], "steps": [], "tool_calls": [], "user_interventions": []}'
        mock_resp.__enter__.return_value = mock_resp

        with patch("urllib.request.urlopen", return_value=mock_resp) as mock_urlopen:
            # 1. all_developers=True
            res_all = sync.pull_remote_sessions(db_path=self.db_path, all_developers=True)
            self.assertEqual(res_all["status"], "success")
            req_all = mock_urlopen.call_args_list[0][0][0]
            self.assertIn("all_developers=true", req_all.get_full_url())

            # 2. developer='developer_x'
            res_dev = sync.pull_remote_sessions(db_path=self.db_path, developer="developer_x")
            self.assertEqual(res_dev["status"], "success")
            req_dev = mock_urlopen.call_args_list[1][0][0]
            self.assertIn("developer=developer_x", req_dev.get_full_url())

    def test_pull_pagination_multiple_pages(self):
        """Verifies pull_remote_sessions loops through multiple pages until has_more is False."""
        page1 = {
            "has_more": True,
            "sessions": [{
                "session_id": "page1-sess",
                "start_time": "2026-03-01T10:00:00Z",
                "origin_developer": "dev1",
                "remote_synced_at": "2026-03-01T10:05:00Z",
            }],
            "steps": [],
            "tool_calls": [],
            "user_interventions": [],
        }
        page2 = {
            "has_more": False,
            "sessions": [{
                "session_id": "page2-sess",
                "start_time": "2026-03-01T11:00:00Z",
                "origin_developer": "dev2",
                "remote_synced_at": "2026-03-01T11:05:00Z",
            }],
            "steps": [],
            "tool_calls": [],
            "user_interventions": [],
        }

        mock_resp1 = MagicMock()
        mock_resp1.read.return_value = json.dumps(page1).encode("utf-8")
        mock_resp1.__enter__.return_value = mock_resp1

        mock_resp2 = MagicMock()
        mock_resp2.read.return_value = json.dumps(page2).encode("utf-8")
        mock_resp2.__enter__.return_value = mock_resp2

        with patch("urllib.request.urlopen", side_effect=[mock_resp1, mock_resp2]) as mock_urlopen:
            res = sync.pull_remote_sessions(db_path=self.db_path, batch_limit=1)
            self.assertEqual(res["status"], "success")
            self.assertEqual(res["sessions_pulled"], 2)
            self.assertEqual(res["sessions_inserted"], 2)
            self.assertEqual(mock_urlopen.call_count, 2)

            conn = sqlite3.connect(self.db_path)
            cur = conn.cursor()
            cur.execute("SELECT COUNT(*) FROM sessions WHERE session_id IN ('page1-sess', 'page2-sess')")
            self.assertEqual(cur.fetchone()[0], 2)
            conn.close()


class TestVerifyAuthToken(unittest.TestCase):
    """Verifies verify_auth_token behavior."""

    def test_verify_auth_token_success(self):
        mock_resp = MagicMock()
        mock_resp.read.return_value = b'{"status": "ok", "authenticated": true, "username": "alice", "org": "purrfectsoft"}'
        mock_resp.__enter__.return_value = mock_resp

        with patch("urllib.request.urlopen", return_value=mock_resp):
            res = sync.verify_auth_token(endpoint="http://localhost:8000", token="valid-tok")
            self.assertTrue(res["authenticated"])
            self.assertEqual(res["username"], "alice")
            self.assertEqual(res["org"], "purrfectsoft")

    def test_verify_auth_token_missing_token_raises(self):
        with patch("harness.telemetry.config.get_auth_token", return_value=None):
            with self.assertRaises(ValueError):
                sync.verify_auth_token(endpoint="http://localhost:8000", token=None)


class TestSyncTelemetry(unittest.TestCase):
    """Verifies sync_telemetry bi-directional orchestration."""

    def setUp(self):
        self.tmpdir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.tmpdir.name) / "telemetry.db"
        conn = sqlite3.connect(self.db_path)
        extract_transcripts.ensure_sync_columns(conn)
        conn.close()

    def tearDown(self):
        self.tmpdir.cleanup()

    def test_sync_telemetry_both_push_and_pull(self):
        with patch("harness.telemetry.sync.push_local_sessions", return_value={"status": "success", "sessions_pushed": 2}) as mock_push, \
             patch("harness.telemetry.sync.pull_remote_sessions", return_value={"status": "success", "sessions_pulled": 1}) as mock_pull:
            res = sync.sync_telemetry(direction="both", db_path=self.db_path, token="tok", endpoint="http://hub")
            self.assertEqual(res["status"], "success")
            self.assertEqual(res["direction"], "both")
            self.assertEqual(res["push"]["sessions_pushed"], 2)
            self.assertEqual(res["pull"]["sessions_pulled"], 1)
            mock_push.assert_called_once()
            mock_pull.assert_called_once()

    def test_sync_telemetry_push_only(self):
        with patch("harness.telemetry.sync.push_local_sessions", return_value={"status": "success", "sessions_pushed": 1}) as mock_push, \
             patch("harness.telemetry.sync.pull_remote_sessions") as mock_pull:
            res = sync.sync_telemetry(direction="push", db_path=self.db_path, token="tok", endpoint="http://hub")
            self.assertEqual(res["status"], "success")
            self.assertEqual(res["direction"], "push")
            self.assertIsNotNone(res["push"])
            self.assertIsNone(res["pull"])
            mock_push.assert_called_once()
            mock_pull.assert_not_called()

    def test_sync_telemetry_pull_only(self):
        with patch("harness.telemetry.sync.push_local_sessions") as mock_push, \
             patch("harness.telemetry.sync.pull_remote_sessions", return_value={"status": "success", "sessions_pulled": 3}) as mock_pull:
            res = sync.sync_telemetry(direction="pull", db_path=self.db_path, token="tok", endpoint="http://hub")
            self.assertEqual(res["status"], "success")
            self.assertEqual(res["direction"], "pull")
            self.assertIsNone(res["push"])
            self.assertIsNotNone(res["pull"])
            mock_push.assert_not_called()
            mock_pull.assert_called_once()

    def test_sync_telemetry_dry_run(self):
        with patch("harness.telemetry.sync.push_local_sessions", return_value={"status": "dry_run", "sessions_pushed": 0}) as mock_push:
            res = sync.sync_telemetry(direction="both", db_path=self.db_path, token="tok", endpoint="http://hub", dry_run=True)
            self.assertEqual(res["status"], "dry_run")
            self.assertEqual(res["pull"]["status"], "dry_run")

    def test_sync_telemetry_interactive_abort(self):
        conn = sqlite3.connect(self.db_path)
        cur = conn.cursor()
        cur.execute("INSERT INTO sessions (session_id, origin_developer, remote_synced_at) VALUES ('s1', 'local', NULL)")
        conn.commit()
        conn.close()

        with patch("builtins.input", return_value="n"), \
             patch("sys.stdout", new_callable=io.StringIO), \
             patch("harness.telemetry.sync.push_local_sessions") as mock_push:
            res = sync.sync_telemetry(direction="push", interactive=True, db_path=self.db_path, token="tok", endpoint="http://hub")
            self.assertEqual(res["status"], "aborted")
            self.assertEqual(res["reason"], "user_cancelled")
            mock_push.assert_not_called()


class TestInteractiveSelectSessions(unittest.TestCase):
    """Verifies interactive_select_sessions checklist and multi-selection (Issue #2)."""

    def setUp(self):
        self.sessions = [
            {"session_id": "sess-111", "duration_seconds": 12.5, "total_steps": 10, "tool_call_count": 4, "workspace_path": "/home/user/Dev/proj-a"},
            {"session_id": "sess-222", "duration_seconds": 45.0, "total_steps": 25, "tool_call_count": 8, "workspace_path": "/home/user/Dev/proj-b"},
            {"session_id": "sess-333", "duration_seconds": 5.2, "total_steps": 4, "tool_call_count": 1, "workspace_path": "/home/user/Dev/proj-c"},
        ]

    def test_empty_sessions_returns_empty(self):
        out = io.StringIO()
        res = sync.interactive_select_sessions([], output_stream=out)
        self.assertEqual(res, [])
        self.assertIn("No candidate sessions", out.getvalue())

    def test_default_all_on_empty_input(self):
        inp = io.StringIO("\n")
        out = io.StringIO()
        res = sync.interactive_select_sessions(self.sessions, input_stream=inp, output_stream=out)
        self.assertEqual(len(res), 3)
        self.assertEqual(res[0]["session_id"], "sess-111")
        self.assertEqual(res[2]["session_id"], "sess-333")

    def test_explicit_all_keyword(self):
        inp = io.StringIO("all\n")
        out = io.StringIO()
        res = sync.interactive_select_sessions(self.sessions, input_stream=inp, output_stream=out)
        self.assertEqual(len(res), 3)

    def test_cancel_or_none(self):
        for cancel_cmd in ["none\n", "q\n", "quit\n", "0\n"]:
            inp = io.StringIO(cancel_cmd)
            out = io.StringIO()
            res = sync.interactive_select_sessions(self.sessions, input_stream=inp, output_stream=out)
            self.assertEqual(res, [])

    def test_select_specific_indices(self):
        inp = io.StringIO("1, 3\n")
        out = io.StringIO()
        res = sync.interactive_select_sessions(self.sessions, input_stream=inp, output_stream=out)
        self.assertEqual(len(res), 2)
        self.assertEqual(res[0]["session_id"], "sess-111")
        self.assertEqual(res[1]["session_id"], "sess-333")

    def test_out_of_range_and_invalid_tokens_ignored(self):
        inp = io.StringIO("2, 99, foo\n")
        out = io.StringIO()
        res = sync.interactive_select_sessions(self.sessions, input_stream=inp, output_stream=out)
        self.assertEqual(len(res), 1)
        self.assertEqual(res[0]["session_id"], "sess-222")
        self.assertIn("Warning", out.getvalue())


class TestWatchAndSync(unittest.TestCase):
    """Verifies continuous background watch and sync daemon (Issue #1)."""

    def setUp(self):
        self.tmpdir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.tmpdir.name) / "watch_telemetry.db"
        conn = sqlite3.connect(self.db_path)
        cur = conn.cursor()
        cur.executescript(extract_transcripts.SCHEMA_SQL)
        sync.ensure_sync_columns(conn)
        conn.commit()
        conn.close()

    def tearDown(self):
        self.tmpdir.cleanup()

    def test_watch_and_sync_run_once(self):
        with patch("harness.telemetry.sync.push_local_sessions", return_value={"sessions_pushed": 2, "steps_pushed": 10}) as mock_push:
            res = sync.watch_and_sync(
                interval_sec=0.01,
                db_path=self.db_path,
                run_once=True,
                endpoint="http://mock-hub",
                token="test-token",
            )
            self.assertEqual(res["status"], "completed")
            self.assertEqual(res["iterations"], 1)
            self.assertEqual(res["total_sessions_pushed"], 2)
            mock_push.assert_called_once()

    def test_watch_and_sync_max_iterations(self):
        with patch("harness.telemetry.sync.push_local_sessions", return_value={"sessions_pushed": 1, "steps_pushed": 5}) as mock_push:
            res = sync.watch_and_sync(
                interval_sec=0.001,
                db_path=self.db_path,
                max_iterations=3,
                endpoint="http://mock-hub",
                token="test-token",
            )
            self.assertEqual(res["iterations"], 3)
            self.assertEqual(res["total_sessions_pushed"], 3)
            self.assertEqual(mock_push.call_count, 3)

    def test_watch_and_sync_stop_event(self):
        import threading
        stop_ev = threading.Event()

        def on_iter(idx, push_res):
            if idx >= 2:
                stop_ev.set()

        with patch("harness.telemetry.sync.push_local_sessions", return_value={"sessions_pushed": 1, "steps_pushed": 2}):
            res = sync.watch_and_sync(
                interval_sec=0.001,
                db_path=self.db_path,
                stop_event=stop_ev,
                on_iteration=on_iter,
                endpoint="http://mock-hub",
                token="test-token",
            )
            self.assertEqual(res["iterations"], 2)


class TestSystemdServiceGenerator(unittest.TestCase):
    """Verifies systemd unit definition generator (Issue #1)."""

    def test_generate_systemd_service_content(self):
        unit = sync.generate_systemd_service(python_bin="/usr/bin/python3", interval_sec=10.0, working_dir="/opt/work")
        self.assertIn("[Unit]", unit)
        self.assertIn("[Service]", unit)
        self.assertIn("[Install]", unit)
        self.assertIn("ExecStart=/usr/bin/python3 -m harness.cli sync --watch --interval 10.0", unit)
        self.assertIn("WorkingDirectory=/opt/work", unit)
        self.assertIn("Restart=on-failure", unit)


class TestProductProjectSeparation(unittest.TestCase):
    """Verifies ADR-014 product-to-project boundary invariants."""

    def test_harness_imports_cleanly_without_pipeline_in_sys_modules(self):
        """Verifies harness/ has zero imports from pipeline/."""
        import subprocess
        cmd = [
            "python3",
            "-c",
            (
                "import sys\n"
                "import harness.cli\n"
                "import harness.runtime.doctor\n"
                "import harness.telemetry.sync\n"
                "import harness.telemetry.config\n"
                "import harness.telemetry.schema\n"
                "pipeline_mods = [m for m in sys.modules if m.startswith('pipeline')]\n"
                "assert len(pipeline_mods) == 0, f'pipeline modules imported: {pipeline_mods}'\n"
            ),
        ]
        proc = subprocess.run(cmd, capture_output=True, text=True)
        self.assertEqual(
            proc.returncode,
            0,
            f"harness.telemetry imported pipeline modules:\nStdout: {proc.stdout}\nStderr: {proc.stderr}",
        )


if __name__ == "__main__":
    unittest.main()
