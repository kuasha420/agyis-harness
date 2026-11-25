#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Arafat Zahan (@kuasha420)
# Corporate Stewardship & Infrastructure: Purrfect Software Limited (PSL)
# Governed by: ICARO-42/b Ordinance (Company-Supported Personal IP Framework)

"""
Hermetic regression tests for Stage 3 Hammer review remediations on G0.1-A.
"""

from __future__ import annotations

import inspect
import io
import json
import os
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import MagicMock, patch
import urllib.error

from harness.telemetry.db import get_sync_watermark
from harness.telemetry.extractor import ensure_telemetry_schema
from harness.telemetry.models import normalize_model
from harness.telemetry.schema import SCHEMA_SQL, init_db
from harness.telemetry.sync.pull import pull_remote_sessions
from server.storage import Storage


class _JsonResp:
    def __init__(self, payload: dict, status: int = 200) -> None:
        self._raw = json.dumps(payload).encode("utf-8")
        self.status = status

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def read(self) -> bytes:
        return self._raw


class TestG01AReviewRegressions(unittest.TestCase):
    """Verifies all 4 Hammer review defect fixes cleanly in <0.1s."""

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp = Path(self._tmp.name)
        self.cfg_dir = self.tmp / "cfg"
        self.cfg_dir.mkdir(parents=True)
        self.env_patch = patch.dict(os.environ, {
            "AGYIS_CONFIG_DIR": str(self.cfg_dir),
            "PSL_CONFIG_DIR": str(self.cfg_dir),
            "AGYIS_AUTH_TOKEN": "tok-test",
            "AGYIS_SYNC_ENDPOINT": "https://hub.example.test",
            "PSL_RETRY_BACKOFF": "0.0",
        })
        self.env_patch.start()

    def tearDown(self) -> None:
        self.env_patch.stop()
        self._tmp.cleanup()

    def test_since_scan_preserves_cursor_sort_key_and_defers_seq_watermark(self) -> None:
        db_abort = self.tmp / "abort.db"
        page1 = {
            "sessions": [{"session_id": "s1", "origin_developer": "bob", "remote_synced_at": "2026-11-25T10:00:00Z", "server_seq": 50}],
            "steps": [], "tool_calls": [], "user_interventions": [],
            "has_more": True, "next_after_seq": 50, "next_cursor": "2026-11-25T10:00:00Z|s1",
        }
        err_p2 = urllib.error.HTTPError("https://hub.example.test/api/v1/sync/pull", 500, "Err", MagicMock(), io.BytesIO(b"err"))
        seen_urls_abort = []

        def fake_abort(req, timeout=30.0):
            seen_urls_abort.append(req.full_url)
            if len(seen_urls_abort) == 1:
                return _JsonResp(page1)
            raise err_p2

        try:
            with patch("urllib.request.urlopen", side_effect=fake_abort):
                with self.assertRaises(urllib.error.HTTPError):
                    pull_remote_sessions(db_path=db_abort, developer="bob", retry_backoff=0.0)
        finally:
            err_p2.close()

        self.assertEqual(len(seen_urls_abort), 2)
        self.assertIn("cursor=2026-11-25T10%3A00%3A00Z%7Cs1", seen_urls_abort[1])
        self.assertNotIn("after_seq=", seen_urls_abort[1])
        conn = sqlite3.connect(db_abort)
        wm_mid = get_sync_watermark(conn, "dev:bob")
        conn.close()
        self.assertIsNotNone(wm_mid)
        self.assertEqual(wm_mid[1], 0)

        db_ok = self.tmp / "ok.db"
        page2 = {
            "sessions": [{"session_id": "s2", "origin_developer": "bob", "remote_synced_at": "2026-11-25T11:00:00Z", "server_seq": 40}],
            "steps": [], "tool_calls": [], "user_interventions": [],
            "has_more": False, "next_after_seq": 40, "next_cursor": "2026-11-25T11:00:00Z|s2",
        }
        seen_urls_ok = []

        def fake_ok(req, timeout=30.0):
            seen_urls_ok.append(req.full_url)
            return _JsonResp(page1 if len(seen_urls_ok) == 1 else page2)

        with patch("urllib.request.urlopen", side_effect=fake_ok):
            pull_remote_sessions(db_path=db_ok, developer="bob", batch_limit=1)

        self.assertIn("cursor=2026-11-25T10%3A00%3A00Z%7Cs1", seen_urls_ok[1])
        self.assertNotIn("after_seq=", seen_urls_ok[1])
        conn = sqlite3.connect(db_ok)
        wm_done = get_sync_watermark(conn, "dev:bob")
        conn.close()
        self.assertEqual(wm_done, ("2026-11-25T11:00:00Z", 50))

    def test_stale_metadata_never_overwrites_non_null_or_bumps_server_seq(self) -> None:
        storage = Storage("sqlite:///:memory:")
        try:
            storage.upsert_batch(
                sessions=[{
                    "session_id": "s-rich",
                    "start_time": "2026-11-25T10:00:00Z",
                    "end_time": "2026-11-25T10:30:00Z",
                    "duration_seconds": 1800.0,
                    "total_steps": 10,
                    "model": "gemini-4-argon",
                    "workspace_path": "[WS]/proj",
                    "transcript_path": "[WS]/logs/transcript_full.jsonl",
                    "has_errors": 1,
                    "origin_machine": "rich-box",
                    "client_surface": "cli",
                    "source_kind": "transcript_full",
                    "model_slug": "gemini-4-argon",
                }],
                steps=[{"session_id": "s-rich", "step_index": 0, "content_snippet": "rich"}],
                tool_calls=[], user_interventions=[], requesting_user="alice",
            )
            before = storage.fetch_delta(after_seq=0, all_developers=True)["sessions"][0]
            orig_seq = before["server_seq"]
            orig_synced = before["remote_synced_at"]
            self.assertGreaterEqual(orig_seq, 1)

            # Stale update 1: lower total_steps with conflicting non-null metadata
            storage.upsert_batch(
                sessions=[{
                    "session_id": "s-rich",
                    "end_time": "2026-01-01T00:00:00Z",
                    "duration_seconds": 1.0,
                    "total_steps": 3,
                    "has_errors": 0,
                    "origin_machine": "stale-box",
                    "client_surface": "ide",
                    "source_kind": "transcript",
                    "model_slug": "stale-model",
                }],
                steps=[{"session_id": "s-rich", "step_index": 0, "content_snippet": "stale"}],
                tool_calls=[], user_interventions=[], requesting_user="alice",
            )
            # Stale update 2: equal steps but strictly lower source richness
            storage.upsert_batch(
                sessions=[{
                    "session_id": "s-rich",
                    "total_steps": 10,
                    "end_time": "2026-01-02T00:00:00Z",
                    "origin_machine": "compact-box",
                    "source_kind": "transcript",
                }],
                steps=[], tool_calls=[], user_interventions=[], requesting_user="alice",
            )
            after = storage.fetch_delta(after_seq=0, all_developers=True)["sessions"][0]
            self.assertEqual(after["server_seq"], orig_seq)
            self.assertEqual(after["remote_synced_at"], orig_synced)
            self.assertEqual(after["end_time"], "2026-11-25T10:30:00Z")
            self.assertEqual(after["duration_seconds"], 1800.0)
            self.assertEqual(after["has_errors"], 1)
            self.assertEqual(after["origin_machine"], "rich-box")
            self.assertEqual(after["client_surface"], "cli")
            self.assertEqual(after["source_kind"], "transcript_full")
            self.assertEqual(after["model_slug"], "gemini-4-argon")
        finally:
            storage.close()

        # Verify pull_remote_sessions also preserves rich metadata on stale pull
        pull_db = self.tmp / "pull_stale.db"
        rich_pull = {
            "sessions": [{
                "session_id": "s-pull-rich",
                "origin_developer": "alice",
                "end_time": "2026-11-25T10:30:00Z",
                "duration_seconds": 600.0,
                "total_steps": 8,
                "has_errors": 1,
                "origin_machine": "rich-box",
                "client_surface": "cli",
                "source_kind": "transcript_full",
                "remote_synced_at": "2026-11-25T10:31:00Z",
                "server_seq": 7,
            }],
            "steps": [], "tool_calls": [], "user_interventions": [], "has_more": False,
        }
        stale_pull = {
            "sessions": [{
                "session_id": "s-pull-rich",
                "origin_developer": "alice",
                "end_time": "2026-01-01T00:00:00Z",
                "duration_seconds": 5.0,
                "total_steps": 2,
                "has_errors": 0,
                "origin_machine": "stale-box",
                "client_surface": "ide",
                "source_kind": "transcript",
                "remote_synced_at": "2026-11-25T12:00:00Z",
                "server_seq": 99,
            }],
            "steps": [], "tool_calls": [], "user_interventions": [], "has_more": False,
        }
        with patch("urllib.request.urlopen", side_effect=[_JsonResp(rich_pull), _JsonResp(stale_pull)]):
            pull_remote_sessions(db_path=pull_db)
            pull_remote_sessions(db_path=pull_db, since="1970-01-01T00:00:00Z")

        conn = sqlite3.connect(pull_db)
        row = conn.execute(
            "SELECT end_time, duration_seconds, has_errors, origin_machine, client_surface, source_kind, server_seq, remote_synced_at "
            "FROM sessions WHERE session_id = 's-pull-rich'"
        ).fetchone()
        conn.close()
        self.assertEqual(row, ("2026-11-25T10:30:00Z", 600.0, 1, "rich-box", "cli", "transcript_full", 7, "2026-11-25T10:31:00Z"))

    def test_legacy_pre_g01_sqlite_upgrade_paths(self) -> None:
        legacy_sql = """
            CREATE TABLE sessions (
                session_id TEXT PRIMARY KEY, start_time TEXT, end_time TEXT,
                duration_seconds REAL, total_steps INTEGER, model TEXT,
                workspace_path TEXT, transcript_path TEXT, file_size_bytes INTEGER,
                has_errors INTEGER, tool_call_count INTEGER, tool_error_count INTEGER,
                intervention_count INTEGER, origin_developer TEXT DEFAULT 'local',
                remote_synced_at TEXT DEFAULT NULL
            );
            INSERT INTO sessions (session_id, start_time, total_steps) VALUES ('old-1', '2026-01-01T00:00:00Z', 4);
        """
        # Path A: init_db on legacy DB
        p1 = self.tmp / "legacy_init.db"
        c1 = sqlite3.connect(p1)
        c1.executescript(legacy_sql)
        init_db(c1)
        cols1 = {r[1] for r in c1.execute("PRAGMA table_info(sessions)").fetchall()}
        self.assertIn("origin_machine", cols1)
        self.assertIn("server_seq", cols1)
        self.assertEqual(c1.execute("SELECT total_steps FROM sessions WHERE session_id = 'old-1'").fetchone()[0], 4)
        c1.close()

        # Path B: raw executescript(SCHEMA_SQL) before ensure_telemetry_schema (pipeline caller order)
        p2 = self.tmp / "legacy_raw.db"
        c2 = sqlite3.connect(p2)
        c2.executescript(legacy_sql)
        c2.executescript(SCHEMA_SQL)
        ensure_telemetry_schema(c2)
        idxs = {r[0] for r in c2.execute("SELECT name FROM sqlite_master WHERE type='index'").fetchall()}
        self.assertIn("idx_sessions_machine", idxs)
        self.assertIn("idx_sessions_server_seq", idxs)
        c2.close()

    def test_claude_opus_4_6_taxonomy_and_pull_signature(self) -> None:
        opus46 = normalize_model("claude-opus-4-6")
        self.assertEqual(opus46.canonical_model, "claude-opus-4-6")
        self.assertEqual(opus46.family, "claude-4.6")
        opus4 = normalize_model("claude-opus-4")
        self.assertEqual(opus4.canonical_model, "claude-opus-4")
        self.assertEqual(opus4.family, "claude-4")

        param_names = list(inspect.signature(pull_remote_sessions).parameters.keys())
        self.assertEqual(param_names[10], "retry_backoff")
        self.assertEqual(param_names[11], "machine")


if __name__ == "__main__":
    unittest.main()
