#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Arafat Zahan (@kuasha420)
# Corporate Stewardship & Infrastructure: Purrfect Software Limited (PSL)
# Governed by: ICARO-42/b Ordinance (Company-Supported Personal IP Framework)

"""
Hermetic Unit and Contract Tests for Telemetry Sync Coordination, Watch Daemon, and Packaging (ADR-030).
Split from test_telemetry_sync.py for sub-second ADR-015 verification.
"""

from __future__ import annotations

import contextlib
import io
import json
import os
from pathlib import Path
import sqlite3
import tempfile
import threading
from typing import Any, Dict
import unittest
from unittest.mock import patch

from harness.telemetry import sync
from pipeline import extract_transcripts


class _JsonHttpResponse:
    """Minimal context-manager HTTP response double for urllib.request.urlopen boundaries."""

    def __init__(self, payload: Dict[str, Any], status: int = 200) -> None:
        self._raw = json.dumps(payload).encode("utf-8")
        self.status = status

    def __enter__(self) -> "_JsonHttpResponse":
        return self

    def __exit__(self, *args: Any) -> bool:
        return False

    def read(self) -> bytes:
        return self._raw


class TestVerifyAuthToken(unittest.TestCase):
    """Verifies verify_auth_token behavior."""

    def test_verify_auth_token_success(self):
        resp = _JsonHttpResponse({"status": "ok", "authenticated": True, "username": "alice", "org": "purrfectsoft"})
        with patch("urllib.request.urlopen", return_value=resp):
            res = sync.verify_auth_token(endpoint="http://localhost:8000", token="valid-tok")
            self.assertTrue(res["authenticated"])
            self.assertEqual(res["username"], "alice")
            self.assertEqual(res["org"], "purrfectsoft")

    def test_verify_auth_token_missing_token_raises(self):
        with patch("harness.telemetry.config.get_auth_token", return_value=None):
            with self.assertRaises(ValueError):
                sync.verify_auth_token(endpoint="http://localhost:8000", token=None)


class TestSyncTelemetry(unittest.TestCase):
    """Verifies sync_telemetry bi-directional orchestration through real push/pull SQLite paths."""

    def setUp(self):
        self.tmpdir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.tmpdir.name) / "telemetry.db"
        self.config_dir = Path(self.tmpdir.name) / "config"
        self.config_dir.mkdir()
        self.patcher_env = patch.dict(os.environ, {"PSL_CONFIG_DIR": str(self.config_dir)})
        self.patcher_env.start()

        conn = sqlite3.connect(self.db_path)
        conn.executescript(extract_transcripts.SCHEMA_SQL)
        extract_transcripts.ensure_sync_columns(conn)
        conn.execute(
            """
            INSERT INTO sessions (
                session_id, start_time, duration_seconds, total_steps,
                workspace_path, transcript_path, origin_developer, remote_synced_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, NULL)
            """,
            ("s-local-1", "2026-11-10T10:00:00Z", 12.0, 1, "/tmp/ws", "/tmp/ws/t.jsonl", "local"),
        )
        conn.commit()
        conn.close()

    def tearDown(self):
        self.patcher_env.stop()
        self.tmpdir.cleanup()

    def _make_hub_urlopen(self, called_urls: list):
        remote_session = {
            "session_id": "s-remote-1",
            "start_time": "2026-11-10T11:00:00Z",
            "end_time": "2026-11-10T11:05:00Z",
            "duration_seconds": 300.0,
            "total_steps": 1,
            "model": "gemini-4-neon",
            "workspace_path": "$WORKSPACE",
            "transcript_path": "$WORKSPACE/logs/transcript.jsonl",
            "file_size_bytes": 512,
            "has_errors": 0,
            "tool_call_count": 0,
            "tool_error_count": 0,
            "intervention_count": 0,
            "origin_developer": "peer-dev",
            "remote_synced_at": "2026-11-10T11:06:00Z",
        }

        def fake_urlopen(req, timeout=10.0):
            url = req.full_url if hasattr(req, "full_url") else str(req)
            called_urls.append(url)
            if "/api/v1/auth/verify" in url:
                return _JsonHttpResponse({"status": "ok", "authenticated": True, "username": "alice"})
            if "/api/v1/sync/push" in url:
                return _JsonHttpResponse({"status": "accepted"})
            if "/api/v1/sync/pull" in url:
                return _JsonHttpResponse({
                    "sessions": [remote_session],
                    "steps": [],
                    "tool_calls": [],
                    "user_interventions": [],
                })
            raise AssertionError(f"Unexpected URL: {url}")

        return fake_urlopen

    def _session_sync_state(self, sid: str):
        conn = sqlite3.connect(self.db_path)
        row = conn.execute("SELECT remote_synced_at FROM sessions WHERE session_id = ?", (sid,)).fetchone()
        conn.close()
        return row[0] if row else "__MISSING__"

    def test_sync_telemetry_both_push_and_pull(self):
        called_urls = []
        with patch("urllib.request.urlopen", side_effect=self._make_hub_urlopen(called_urls)):
            res = sync.sync_telemetry(
                direction="both", db_path=self.db_path, token="tok", endpoint="https://hub.example.test", retry_backoff=0.0,
            )
        self.assertEqual(res["direction"], "both")
        self.assertEqual(res["push"]["sessions_pushed"], 1)
        self.assertEqual(res["pull"]["sessions_pulled"], 1)
        self.assertTrue(any("/api/v1/sync/push" in u for u in called_urls))
        self.assertTrue(any("/api/v1/sync/pull" in u for u in called_urls))
        self.assertNotIn(self._session_sync_state("s-local-1"), (None, "__MISSING__"))
        self.assertEqual(self._session_sync_state("s-remote-1"), "2026-11-10T11:06:00Z")

    def test_sync_telemetry_push_only(self):
        called_urls = []
        with patch("urllib.request.urlopen", side_effect=self._make_hub_urlopen(called_urls)):
            res = sync.sync_telemetry(
                direction="push", db_path=self.db_path, token="tok", endpoint="https://hub.example.test", retry_backoff=0.0,
            )
        self.assertEqual(res["direction"], "push")
        self.assertEqual(res["push"]["sessions_pushed"], 1)
        self.assertIsNone(res["pull"])
        self.assertFalse(any("/api/v1/sync/pull" in u for u in called_urls))
        self.assertEqual(self._session_sync_state("s-remote-1"), "__MISSING__")

    def test_sync_telemetry_pull_only(self):
        called_urls = []
        with patch("urllib.request.urlopen", side_effect=self._make_hub_urlopen(called_urls)):
            res = sync.sync_telemetry(
                direction="pull", db_path=self.db_path, token="tok", endpoint="https://hub.example.test", retry_backoff=0.0,
            )
        self.assertEqual(res["direction"], "pull")
        self.assertIsNone(res["push"])
        self.assertEqual(res["pull"]["sessions_pulled"], 1)
        self.assertFalse(any("/api/v1/sync/push" in u for u in called_urls))
        self.assertIsNone(self._session_sync_state("s-local-1"))
        self.assertEqual(self._session_sync_state("s-remote-1"), "2026-11-10T11:06:00Z")

    def test_sync_telemetry_dry_run(self):
        called_urls = []
        with patch("urllib.request.urlopen", side_effect=self._make_hub_urlopen(called_urls)):
            res = sync.sync_telemetry(
                direction="both", db_path=self.db_path, token="tok", endpoint="https://hub.example.test", dry_run=True, retry_backoff=0.0,
            )
        self.assertEqual(res["push"]["sessions_pushed"], 1)
        self.assertEqual(res["pull"]["sessions_to_pull"], 1)
        self.assertFalse(any("/api/v1/sync/push" in u for u in called_urls))
        self.assertIsNone(self._session_sync_state("s-local-1"))
        self.assertEqual(self._session_sync_state("s-remote-1"), "__MISSING__")

    def test_sync_telemetry_interactive_abort(self):
        called_urls = []
        with patch("builtins.input", return_value="n"), \
             contextlib.redirect_stdout(io.StringIO()), \
             patch("urllib.request.urlopen", side_effect=self._make_hub_urlopen(called_urls)):
            res = sync.sync_telemetry(
                direction="push", interactive=True, db_path=self.db_path, token="tok", endpoint="https://hub.example.test"
            )
        self.assertEqual(res["status"], "aborted")
        self.assertEqual(res["reason"], "user_cancelled")
        self.assertEqual(called_urls, [])


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
        self.empty_brain = Path(self.tmpdir.name) / "empty_brain"
        self.empty_brain.mkdir(parents=True, exist_ok=True)
        self.state_dir = Path(self.tmpdir.name) / "state"
        self.config_dir = Path(self.tmpdir.name) / "config"
        self.config_dir.mkdir(parents=True, exist_ok=True)
        self.patcher_env = patch.dict(os.environ, {"PSL_CONFIG_DIR": str(self.config_dir)})
        self.patcher_env.start()
        conn = sqlite3.connect(self.db_path)
        cur = conn.cursor()
        cur.executescript(extract_transcripts.SCHEMA_SQL)
        sync.ensure_sync_columns(conn)
        conn.commit()
        conn.close()

    def tearDown(self):
        self.patcher_env.stop()
        self.tmpdir.cleanup()

    def test_watch_and_sync_run_once(self):
        conn = sqlite3.connect(self.db_path)
        conn.execute(
            """
            INSERT INTO sessions (
                session_id, start_time, duration_seconds, total_steps,
                workspace_path, transcript_path, origin_developer, remote_synced_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, NULL)
            """,
            ("s-watch-1", "2026-11-10T10:00:00Z", 5.0, 1, "/tmp/ws", "/tmp/ws/t.jsonl", "local"),
        )
        conn.commit()
        conn.close()

        with patch("urllib.request.urlopen", return_value=_JsonHttpResponse({"status": "accepted"})):
            res = sync.watch_and_sync(
                interval_sec=0.01,
                db_path=self.db_path,
                run_once=True,
                endpoint="https://hub.example.test",
                token="test-token",
                brain_dir=self.empty_brain,
                state_dir=self.state_dir,
            )
            self.assertEqual(res["status"], "completed")
            self.assertEqual(res["iterations"], 1)
            self.assertEqual(res["total_sessions_pushed"], 1)

        health = sync.read_sync_status(state_dir=self.state_dir)
        self.assertEqual(health["status"], "ok")

    def test_watch_and_sync_max_iterations(self):
        calls = 0

        def real_urlopen(req, timeout=10.0):
            nonlocal calls
            calls += 1
            return _JsonHttpResponse({"status": "accepted"})

        conn = sqlite3.connect(self.db_path)
        conn.execute(
            "INSERT INTO sessions (session_id, start_time, duration_seconds, total_steps, origin_developer, remote_synced_at) VALUES (?, ?, ?, ?, ?, NULL)",
            ("s-max-1", "2026-11-10T10:00:00Z", 5.0, 1, "local"),
        )
        conn.commit()
        conn.close()

        with patch("urllib.request.urlopen", side_effect=real_urlopen):
            res = sync.watch_and_sync(
                interval_sec=0.001,
                db_path=self.db_path,
                max_iterations=3,
                endpoint="https://hub.example.test",
                token="test-token",
                brain_dir=self.empty_brain,
                state_dir=self.state_dir,
            )
        self.assertEqual(res["iterations"], 3)
        self.assertEqual(res["total_sessions_pushed"], 1)
        self.assertEqual(calls, 1)

    def test_watch_and_sync_stop_event(self):
        stop_ev = threading.Event()
        seen_iters = []

        def on_iter(idx, payload):
            seen_iters.append(idx)
            if idx >= 2:
                stop_ev.set()

        with patch("urllib.request.urlopen", return_value=_JsonHttpResponse({"status": "accepted"})):
            res = sync.watch_and_sync(
                interval_sec=0.001,
                db_path=self.db_path,
                stop_event=stop_ev,
                on_iteration=on_iter,
                endpoint="https://hub.example.test",
                token="test-token",
                brain_dir=self.empty_brain,
                state_dir=self.state_dir,
            )
        self.assertEqual(res["iterations"], 2)
        self.assertEqual(seen_iters, [1, 2])

    def test_harvest_local_transcripts_ingests_tool_calls_and_interventions(self):
        """Verifies harvest_local_transcripts populates sessions, steps, tool_calls, and user_interventions."""
        brain_dir = Path(self.tmpdir.name) / "brain"
        sess_id = "sess-harvest-001"
        t_dir = brain_dir / sess_id / ".system_generated" / "logs"
        t_dir.mkdir(parents=True, exist_ok=True)
        t_file = t_dir / "transcript.jsonl"
        steps = [
            {"step_index": 0, "type": "USER_INPUT", "source": "USER_EXPLICIT", "created_at": "2026-11-10T10:00:00Z", "content": "<USER_REQUEST>run tests</USER_REQUEST>"},
            {"step_index": 1, "type": "PLANNER_RESPONSE", "source": "MODEL", "created_at": "2026-11-10T10:00:05Z", "tool_calls": [{"name": "run_command", "args": {"CommandLine": "python3 -m unittest"}}]},
            {"step_index": 2, "type": "TOOL_RESULT", "status": "DONE", "created_at": "2026-11-10T10:00:07Z", "content": "Created At: 2026-11-10T10:00:05Z\nCompleted At: 2026-11-10T10:00:07Z\nRan 5 tests\nOK"},
            {"step_index": 3, "type": "USER_INPUT", "source": "USER_EXPLICIT", "created_at": "2026-11-10T10:00:10Z", "content": "<USER_REQUEST>proceed</USER_REQUEST>"},
        ]
        t_file.write_text("\n".join(json.dumps(s) for s in steps) + "\n", encoding="utf-8")

        lag_before = sync.compute_telemetry_lag(db_path=self.db_path, brain_dir=brain_dir)
        self.assertEqual(lag_before["unsynced_local"], 1)

        cache = {}
        stored = sync.harvest_local_transcripts(self.db_path, cache, brain_dir=brain_dir)
        self.assertEqual(stored, 1)
        self.assertIn(str(t_file), cache)
        self.assertEqual(sync.harvest_local_transcripts(self.db_path, cache, brain_dir=brain_dir), 0)

        conn = sqlite3.connect(self.db_path)
        cur = conn.cursor()
        cur.execute("SELECT tool_call_count, intervention_count FROM sessions WHERE session_id = ?", (sess_id,))
        self.assertEqual(cur.fetchone(), (1, 1))
        cur.execute("SELECT tool_name, command_category, status FROM tool_calls WHERE session_id = ?", (sess_id,))
        self.assertEqual(cur.fetchone(), ("run_command", "test_runner", "SUCCESS"))
        cur.execute("SELECT intervention_type, prompt_text FROM user_interventions WHERE session_id = ?", (sess_id,))
        self.assertEqual(cur.fetchone(), ("CONFIRMATION", "proceed"))
        conn.close()

        lag_after = sync.compute_telemetry_lag(db_path=self.db_path, brain_dir=brain_dir)
        self.assertEqual(lag_after["unsynced_local"], 0)
        self.assertEqual(lag_after["stale_local"], 0)

        with open(t_file, "a", encoding="utf-8") as f:
            f.write(json.dumps({"step_index": 4, "type": "PLANNER_RESPONSE", "content": "done"}) + "\n")
        lag_stale = sync.compute_telemetry_lag(db_path=self.db_path, brain_dir=brain_dir)
        self.assertEqual(lag_stale["stale_local"], 1)

    def test_harvest_local_transcripts_logs_errors_and_leaves_mtime_uncached(self):
        """Verifies harvest errors log to stderr, do not advance mtime_cache, and preserve clean DB."""
        brain_dir = Path(self.tmpdir.name) / "brain_err"
        t_dir = brain_dir / "sess-err-001" / ".system_generated" / "logs"
        t_dir.mkdir(parents=True, exist_ok=True)
        t_file = t_dir / "transcript.jsonl"
        t_file.write_text(json.dumps({"step_index": 0, "type": "USER_INPUT", "content": "hi"}) + "\n", encoding="utf-8")

        cache, err_sink, err_buf = {}, [], io.StringIO()
        with patch("harness.telemetry.sync.daemon.upsert_session_telemetry", side_effect=sqlite3.OperationalError("schema mismatch")), \
             contextlib.redirect_stderr(err_buf):
            stored = sync.harvest_local_transcripts(self.db_path, cache, brain_dir=brain_dir, error_sink=err_sink)
        self.assertEqual(stored, 0)
        self.assertEqual(cache, {})
        self.assertEqual(len(err_sink), 1)
        self.assertIn("schema mismatch", err_buf.getvalue())

    def test_watch_and_sync_exponential_backoff_and_health_status(self):
        """Verifies watch_and_sync backs off exponentially on repeated errors and records health JSON."""
        state_dir = Path(self.tmpdir.name) / "state"
        backoffs = []
        sleeps = []

        def on_iter(idx, payload):
            backoffs.append(payload["backoff_sec"])

        with patch("harness.telemetry.sync.daemon.harvest_local_transcripts", side_effect=RuntimeError("db locked")), \
             patch("harness.telemetry.sync.push_local_sessions", side_effect=ValueError("no token")), \
             patch("harness.telemetry.sync.daemon.time.sleep", side_effect=lambda s: sleeps.append(s)), \
             contextlib.redirect_stderr(io.StringIO()):
            res = sync.watch_and_sync(
                interval_sec=0.5,
                db_path=self.db_path,
                max_iterations=3,
                on_iteration=on_iter,
                state_dir=state_dir,
            )

        self.assertEqual(res["consecutive_failures"], 3)
        self.assertEqual(backoffs, [1.0, 2.0, 4.0])
        self.assertEqual(sleeps, [1.0, 2.0])
        health = sync.read_sync_status(state_dir=state_dir)
        self.assertEqual(health["status"], "degraded")
        self.assertEqual(health["consecutive_failures"], 3)
        self.assertIn("db locked", health["last_error"])


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
        import sys
        cmd = [
            sys.executable,
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
