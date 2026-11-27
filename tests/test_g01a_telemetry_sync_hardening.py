#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Arafat Zahan (@kuasha420)
# Corporate Stewardship & Infrastructure: Purrfect Software Limited (PSL)
# Governed by: ICARO-42/b Ordinance (Company-Supported Personal IP Framework)

"""
Hermetic sub-second verification suite for Gate 0 G0.1-A Telemetry & Sync Hardening.
Tests models, protobuf decoding, sibling .db enrichment, per-scope sync watermarks,
keyset pagination, atomic child replacement, watch-mode pull, CLI flags, and server Storage/endpoints.
"""

from __future__ import annotations

import asyncio
import io
import json
import os
from pathlib import Path
import sqlite3
import sys
import tempfile
import types
import unittest
from unittest.mock import MagicMock, patch
import urllib.error

from harness.cli import main as cli_main
from harness.telemetry import sync as sync_pkg
from harness.telemetry.db import get_sync_watermark, iter_brain_transcripts
from harness.telemetry.extractor import (
    ensure_telemetry_schema,
    extract_session,
    upsert_session_telemetry,
)
from harness.telemetry.models import normalize_model, normalize_utc_iso
from harness.telemetry.sync import pull_remote_sessions, push_local_sessions, sync_telemetry, watch_and_sync
from harness.trajectory.health import infer_model_context_window
from harness.trajectory.protobuf import extract_tool_from_protobuf, extract_usage_from_protobuf
from server.storage import Storage


def _varint(val: int) -> bytes:
    out = bytearray()
    while True:
        b = val & 0x7F
        val >>= 7
        if val:
            out.append(b | 0x80)
        else:
            out.append(b)
            break
    return bytes(out)


def _pb_varint(fn: int, val: int) -> bytes:
    return _varint((fn << 3) | 0) + _varint(val)


def _pb_bytes(fn: int, payload: bytes) -> bytes:
    return _varint((fn << 3) | 2) + _varint(len(payload)) + payload


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


class TestModelsProtobufAndExtractor(unittest.TestCase):
    """Verifies UTC normalization, model taxonomy, protobuf decoding, and sibling DB enrichment."""

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp = Path(self._tmp.name)

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def test_utc_iso_normalization_and_model_taxonomy(self) -> None:
        self.assertEqual(normalize_utc_iso("2026-11-26T03:30:00+06:00"), "2026-11-25T21:30:00Z")
        self.assertEqual(normalize_utc_iso("2026-11-26T03:30:00.123456z"), "2026-11-26T03:30:00Z")
        self.assertEqual(normalize_utc_iso("2026-11-26T03:30:00"), "2026-11-26T03:30:00Z")
        self.assertIsNone(normalize_utc_iso("   "))

        expected = {
            "gemini-4-argon": ("gemini-4-argon", 512_000, "attributed"),
            "claude-sonnet-5-5": ("claude-sonnet-5-5", 840_000, "attributed"),
            "claude-sonnet-4-6": ("claude-sonnet-4-6", 160_000, "attributed"),
            "gpt-oss-120b": ("gpt-oss-120b", 80_000, "attributed"),
            "Unknown": ("unknown", 256_000, "unknown"),
            "Gemini 3.5/Flash/Pro (Default)": ("unattributed_legacy", 256_000, "unattributed_legacy"),
        }
        for raw, (canon, win, status) in expected.items():
            info = normalize_model(raw)
            self.assertEqual(info.canonical_model, canon)
            self.assertEqual(info.context_window_tokens, win)
            self.assertEqual(info.attribution_status, status)
            if status == "attributed":
                self.assertEqual(infer_model_context_window(raw), win)

    def test_protobuf_model_slug_display_name_and_modified_tool(self) -> None:
        cwm = _pb_varint(1, 22000) + _pb_varint(4, 512000)
        csm = _pb_varint(2, 3) + _pb_bytes(10, cwm) + _pb_bytes(19, b"gemini-4-argon") + _pb_bytes(21, b"Gemini 4 Argon (High)")
        usage = _pb_varint(2, 1200) + _pb_varint(5, 8000) + _pb_varint(9, 150) + _pb_varint(10, 450)
        blob = _pb_bytes(1, _pb_bytes(9, csm) + _pb_bytes(4, usage))
        metrics = extract_usage_from_protobuf(blob)
        self.assertEqual(metrics.model_slug, "gemini-4-argon")
        self.assertEqual(metrics.model_display_name, "Gemini 4 Argon (High)")
        self.assertEqual(metrics.max_context_tokens, 512000)
        self.assertEqual(metrics.input_tokens, 1200)
        self.assertEqual(metrics.cache_read_tokens, 8000)
        self.assertEqual(metrics.output_tokens, 450)
        self.assertEqual(metrics.thought_tokens, 150)

        tc_orig = _pb_bytes(2, b"run_command") + _pb_bytes(3, b'{"CommandLine":"rm old"}')
        tc_mod = _pb_bytes(2, b"run_command") + _pb_bytes(3, b'{"CommandLine":"echo safe"}')
        t_name, t_args = extract_tool_from_protobuf(_pb_bytes(4, tc_orig) + _pb_bytes(29, tc_mod))
        self.assertEqual(t_name, "run_command")
        self.assertIn("echo safe", t_args)

    def test_extractor_sibling_enrichment_unknown_fallback_and_atomic_conflict(self) -> None:
        app_dir = self.tmp / "antigravity-cli"
        sid = "sess-cli-argon-01"
        logs_dir = app_dir / "brain" / sid / ".system_generated" / "logs"
        conv_dir = app_dir / "conversations"
        logs_dir.mkdir(parents=True)
        conv_dir.mkdir(parents=True)

        t_path = logs_dir / "transcript_full.jsonl"
        steps_jsonl = [
            {
                "step_index": 0,
                "type": "USER_INPUT",
                "source": "USER_EXPLICIT",
                "created_at": "2026-11-26T03:00:00+06:00",
                "content": "Inspect repo",
            },
            {
                "step_index": 1,
                "type": "PLANNER_RESPONSE",
                "created_at": "2026-11-26T03:05:00+06:00",
                "tool_calls": [{"name": "read_file", "args": {"Path": "/tmp/a.py"}}],
            },
            {
                "step_index": 2,
                "type": "GENERIC",
                "created_at": "2026-11-26T03:05:02+06:00",
                "content": "Created At: 2026-11-26T03:05:00+06:00\nCompleted At: 2026-11-26T03:05:02+06:00\nok",
            },
        ]
        t_path.write_text("\n".join(json.dumps(s) for s in steps_jsonl) + "\n", encoding="utf-8")

        # Sibling DB enriches model + tokens without transcript model field
        cwm = _pb_varint(1, 30000) + _pb_varint(4, 512000)
        csm = _pb_bytes(10, cwm)
        usage = _pb_varint(2, 2000) + _pb_varint(5, 14000) + _pb_varint(9, 100) + _pb_varint(10, 500)
        gm_blob = _pb_bytes(1, _pb_bytes(9, csm) + _pb_bytes(4, usage) + _pb_bytes(19, b"gemini-4-argon") + _pb_bytes(21, b"Gemini 4 Argon"))
        db_sib = sqlite3.connect(conv_dir / f"{sid}.db")
        db_sib.execute("CREATE TABLE gen_metadata (idx INTEGER PRIMARY KEY, data BLOB)")
        db_sib.execute("INSERT INTO gen_metadata VALUES (0, ?)", (gm_blob,))
        db_sib.commit()
        db_sib.close()

        extracted = extract_session(t_path)
        self.assertIsNotNone(extracted)
        s_row, st_rows, tc_rows, _ = extracted
        self.assertEqual(s_row["start_time"], "2026-11-25T21:00:00Z")
        self.assertEqual(s_row["end_time"], "2026-11-25T21:05:02Z")
        self.assertEqual(s_row["client_surface"], "cli")
        self.assertEqual(s_row["source_kind"], "transcript_full")
        self.assertEqual(s_row["model_slug"], "gemini-4-argon")
        self.assertEqual(s_row["max_context_tokens"], 512000)
        self.assertEqual(s_row["total_input_tokens"], 2000)
        self.assertEqual(s_row["total_cache_read_tokens"], 14000)
        self.assertEqual(tc_rows[0]["started_at"], "2026-11-25T21:05:00Z")

        # Modern unknown transcript without sibling DB yields "Unknown", not Gemini 3.5 default
        unk_t = app_dir / "brain" / "sess-unknown-01" / ".system_generated" / "logs" / "transcript.jsonl"
        unk_t.parent.mkdir(parents=True)
        unk_t.write_text(json.dumps({"step_index": 0, "type": "USER_INPUT", "content": "hi"}) + "\n", encoding="utf-8")
        unk_row, _, _, _ = extract_session(unk_t)
        self.assertEqual(unk_row["model"], "Unknown")
        self.assertNotIn("Gemini 3.5", unk_row["model"])

        # Upsert + sibling sqlite_db non-clobbering enrichment + atomic child replacement
        telem_db = sqlite3.connect(self.tmp / "telemetry.db")
        ensure_telemetry_schema(telem_db)
        upsert_session_telemetry(telem_db, s_row, st_rows, tc_rows, [])

        sib_clobber_attempt = dict(s_row)
        sib_clobber_attempt.update({
            "source_kind": "sqlite_db",
            "transcript_path": str(conv_dir / f"{sid}.db"),
            "file_size_bytes": 9999999,
            "total_input_tokens": 5000,
        })
        upsert_session_telemetry(telem_db, sib_clobber_attempt, [], [], [])
        row_after = telem_db.execute(
            "SELECT transcript_path, file_size_bytes, total_input_tokens FROM sessions WHERE session_id = ?",
            (sid,),
        ).fetchone()
        self.assertEqual(row_after[0], str(t_path))
        self.assertEqual(row_after[1], s_row["file_size_bytes"])
        self.assertEqual(row_after[2], 5000)
        self.assertEqual(telem_db.execute("SELECT COUNT(*) FROM tool_calls WHERE session_id = ?", (sid,)).fetchone()[0], 1)

        # Conflict replacement on same source_kind replaces stale child rows cleanly
        new_tc = dict(tc_rows[0])
        new_tc["tool_name"] = "view_file"
        upsert_session_telemetry(telem_db, s_row, st_rows, [new_tc], [])
        names = [r[0] for r in telem_db.execute("SELECT tool_name FROM tool_calls WHERE session_id = ?", (sid,)).fetchall()]
        self.assertEqual(names, ["view_file"])
        telem_db.close()


class TestClientSyncHardening(unittest.TestCase):
    """Verifies per-scope watermarks, keyset pull, atomic child replace, push fields, watch, and CLI."""

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp = Path(self._tmp.name)
        self.db_path = self.tmp / "telemetry.db"
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

    def test_per_scope_watermarks_prevent_starvation_and_abort_safe(self) -> None:
        # 1. HTTP 500 on pull leaves sync_watermarks untouched
        err_500 = urllib.error.HTTPError("https://hub.example.test/api/v1/sync/pull", 500, "Err", MagicMock(), io.BytesIO(b"err"))
        try:
            with patch("urllib.request.urlopen", side_effect=err_500):
                with self.assertRaises(urllib.error.HTTPError):
                    pull_remote_sessions(db_path=self.db_path, developer="bob", retry_backoff=0.0)
        finally:
            err_500.close()

        conn = sqlite3.connect(self.db_path)
        self.assertIsNone(get_sync_watermark(conn, "dev:bob"))
        conn.close()

        # 2. Pull dev:bob at 2026-11-25T10:00:00Z, then dev:charlie still defaults to 1970 (no starvation!)
        seen_urls = []

        def fake_urlopen(req, timeout=30.0):
            url = req.full_url
            seen_urls.append(url)
            if "developer=bob" in url:
                return _JsonResp({
                    "sessions": [{"session_id": "s-bob", "origin_developer": "bob", "remote_synced_at": "2026-11-25T10:00:00Z", "server_seq": 15}],
                    "steps": [], "tool_calls": [], "user_interventions": [], "has_more": False, "next_after_seq": 15,
                })
            return _JsonResp({
                "sessions": [{"session_id": "s-charlie", "origin_developer": "charlie", "remote_synced_at": "2026-11-20T08:00:00Z", "server_seq": 4}],
                "steps": [], "tool_calls": [], "user_interventions": [], "has_more": False, "next_after_seq": 4,
            })

        with patch("urllib.request.urlopen", side_effect=fake_urlopen):
            r_bob = pull_remote_sessions(db_path=self.db_path, developer="bob")
            r_charlie = pull_remote_sessions(db_path=self.db_path, developer="charlie")
            r_bob_2 = pull_remote_sessions(db_path=self.db_path, developer="bob")

        self.assertEqual(r_bob["scope_key"], "dev:bob")
        self.assertEqual(r_charlie["since"], "1970-01-01T00:00:00Z")
        self.assertIn("after_seq=15", seen_urls[-1])
        self.assertEqual(r_bob_2["since"], "2026-11-25T10:00:00Z")

    def test_pull_atomic_child_replacement_and_monotonic_guard(self) -> None:
        page_v1 = {
            "sessions": [{
                "session_id": "s-conflict",
                "origin_developer": "alice",
                "origin_machine": "desktop-1",
                "client_surface": "ide",
                "model": "gemini-4-argon",
                "model_slug": "gemini-4-argon",
                "total_steps": 5,
                "tool_call_count": 2,
                "remote_synced_at": "2026-11-25T10:00:00Z",
                "server_seq": 10,
            }],
            "steps": [{"session_id": "s-conflict", "step_index": 0, "content_snippet": "old"}],
            "tool_calls": [
                {"session_id": "s-conflict", "step_index": 0, "tool_name": "stale_tool_1", "started_at": "2026-11-25T10:00:00Z", "arguments_snippet": "a"},
                {"session_id": "s-conflict", "step_index": 1, "tool_name": "stale_tool_2", "started_at": "2026-11-25T10:00:01Z", "arguments_snippet": "b"},
            ],
            "user_interventions": [],
            "has_more": False,
        }
        page_v2_updated = {
            "sessions": [{
                "session_id": "s-conflict",
                "origin_developer": "alice",
                "origin_machine": "laptop-2",
                "client_surface": "cli",
                "model": "gemini-4-argon",
                "total_steps": 6,
                "tool_call_count": 1,
                "total_input_tokens": 9000,
                "remote_synced_at": "2026-11-25T11:00:00Z",
                "server_seq": 12,
            }],
            "steps": [{"session_id": "s-conflict", "step_index": 0, "content_snippet": "updated"}],
            "tool_calls": [
                {"session_id": "s-conflict", "step_index": 0, "tool_name": "clean_tool", "started_at": "2026-11-25T10:00:00Z", "arguments_snippet": "c"},
            ],
            "user_interventions": [],
            "has_more": False,
        }
        page_v3_stale = {
            "sessions": [{
                "session_id": "s-conflict",
                "origin_developer": "alice",
                "total_steps": 2,
                "tool_call_count": 0,
                "remote_synced_at": "2026-11-25T09:00:00Z",
                "server_seq": 5,
            }],
            "steps": [{"session_id": "s-conflict", "step_index": 0, "content_snippet": "stale"}],
            "tool_calls": [],
            "user_interventions": [],
            "has_more": False,
        }

        with patch("urllib.request.urlopen", side_effect=[_JsonResp(page_v1), _JsonResp(page_v2_updated), _JsonResp(page_v3_stale)]):
            pull_remote_sessions(db_path=self.db_path)
            pull_remote_sessions(db_path=self.db_path, since="1970-01-01T00:00:00Z")
            pull_remote_sessions(db_path=self.db_path, since="1970-01-01T00:00:00Z")

        conn = sqlite3.connect(self.db_path)
        s_row = conn.execute(
            "SELECT total_steps, tool_call_count, origin_machine, client_surface, total_input_tokens FROM sessions WHERE session_id = 's-conflict'"
        ).fetchone()
        self.assertEqual(s_row, (6, 2, "laptop-2", "cli", 9000))
        tools = [r[0] for r in conn.execute("SELECT tool_name FROM tool_calls WHERE session_id = 's-conflict'").fetchall()]
        self.assertEqual(tools, ["clean_tool"])
        step_snip = conn.execute("SELECT content_snippet FROM steps WHERE session_id = 's-conflict'").fetchone()[0]
        self.assertEqual(step_snip, "updated")
        conn.close()

    def test_push_normalizes_timestamps_and_includes_additive_fields(self) -> None:
        conn = sqlite3.connect(self.db_path)
        ensure_telemetry_schema(conn)
        conn.execute(
            """
            INSERT INTO sessions (
                session_id, start_time, end_time, total_steps, model, workspace_path,
                transcript_path, origin_developer, origin_machine, client_surface,
                source_kind, model_slug, max_context_tokens, total_input_tokens
            ) VALUES (
                's-push-1', '2026-11-26T03:00:00+06:00', '2026-11-26T03:10:00+06:00',
                1, 'gemini-4-argon', '/tmp/ws', '/home/u/.gemini/antigravity-cli/brain/s-push-1/logs/transcript.jsonl',
                'local', 'ws-host', 'cli', 'transcript_full', 'gemini-4-argon', 512000, 4200
            )
            """
        )
        conn.commit()
        conn.close()

        captured = {}

        def fake_urlopen(req, timeout=30.0):
            captured["payload"] = json.loads(req.data.decode("utf-8"))
            return _JsonResp({"status": "success"})

        with patch("urllib.request.urlopen", side_effect=fake_urlopen):
            res = push_local_sessions(db_path=self.db_path, workspace_root="/tmp/ws")

        self.assertEqual(res["sessions_pushed"], 1)
        sess = captured["payload"]["sessions"][0]
        self.assertEqual(sess["start_time"], "2026-11-25T21:00:00Z")
        self.assertEqual(sess["end_time"], "2026-11-25T21:10:00Z")
        self.assertEqual(sess["origin_machine"], "ws-host")
        self.assertEqual(sess["client_surface"], "cli")
        self.assertEqual(sess["model_slug"], "gemini-4-argon")
        self.assertEqual(sess["max_context_tokens"], 512000)
        self.assertEqual(sess["total_input_tokens"], 4200)

    def test_coordinator_wires_on_progress_through_pull_and_cli_flags(self) -> None:
        progress_calls = []

        def on_prog(idx, total, stats):
            progress_calls.append((idx, total, stats))

        pages = [
            _JsonResp({"sessions": [{"session_id": "p1", "origin_developer": "bob", "server_seq": 1}], "steps": [], "tool_calls": [], "user_interventions": [], "has_more": True, "next_after_seq": 1}),
            _JsonResp({"sessions": [{"session_id": "p2", "origin_developer": "bob", "server_seq": 2}], "steps": [], "tool_calls": [], "user_interventions": [], "has_more": False, "next_after_seq": 2}),
        ]
        with patch("urllib.request.urlopen", side_effect=pages):
            res = sync_telemetry(
                direction="pull",
                db_path=self.db_path,
                include_self=True,
                machine="laptop-1",
                batch_limit=1,
                on_progress=on_prog,
            )
        self.assertEqual(res["pull"]["sessions_pulled"], 2)
        self.assertEqual(len(progress_calls), 2)
        self.assertEqual(progress_calls[0][2]["phase"], "pull")

        with patch("harness.telemetry.sync.sync_telemetry", return_value={"status": "success", "direction": "pull", "push": None, "pull": {"sessions_inserted": 3, "steps_inserted": 7}}) as mock_sync, \
             patch("sys.stdout", new_callable=io.StringIO) as mock_out:
            rc = cli_main(["sync", "--pull", "--include-self", "--machine", "deck-1", "--batch-limit", "25"])
            self.assertEqual(rc, 0)
            self.assertIn("Pulled: 3 new sessions, 7 steps", mock_out.getvalue())
            mock_sync.assert_called_once_with(
                direction="pull",
                interactive=False,
                endpoint=None,
                db_path=None,
                limit=None,
                dry_run=False,
                on_progress=unittest.mock.ANY,
                include_self=True,
                machine="deck-1",
                batch_limit=25,
            )

    def test_daemon_pull_in_watch_and_dual_brain_discovery(self) -> None:
        fake_home = self.tmp / "home"
        ide_logs = fake_home / ".gemini" / "antigravity" / "brain" / "s-ide" / ".system_generated" / "logs"
        cli_logs = fake_home / ".gemini" / "antigravity-cli" / "brain" / "s-cli" / ".system_generated" / "logs"
        ide_logs.mkdir(parents=True)
        cli_logs.mkdir(parents=True)
        (ide_logs / "transcript.jsonl").write_text('{"step_index": 0, "content": "ide"}\n', encoding="utf-8")
        (cli_logs / "transcript.jsonl").write_text('{"step_index": 0, "content": "cli"}\n', encoding="utf-8")

        with patch.dict(os.environ, {"HOME": str(fake_home)}, clear=False), \
             patch.dict(os.environ, {"ANTIGRAVITY_BRAIN_DIR": "", "ANTIGRAVITY_APP_DATA_DIR": "", "GEMINI_BRAIN_DIR": ""}):
            found = iter_brain_transcripts(None)
            self.assertEqual({cid for cid, _, _, _ in found}, {"s-ide", "s-cli"})

        empty_brain = self.tmp / "empty_brain"
        empty_brain.mkdir()
        pull_calls = []

        def fake_urlopen(req, timeout=30.0):
            url = req.full_url
            if "/sync/pull" in url:
                pull_calls.append(url)
                return _JsonResp({"sessions": [{"session_id": "r1", "origin_developer": "peer", "server_seq": 1}], "steps": [], "tool_calls": [], "user_interventions": []})
            return _JsonResp({"status": "ok"})

        with patch("urllib.request.urlopen", side_effect=fake_urlopen):
            res_watch = watch_and_sync(
                interval_sec=0.0,
                db_path=self.db_path,
                run_once=True,
                brain_dir=empty_brain,
                state_dir=self.tmp / "state",
                pull_in_watch=True,
            )
        self.assertEqual(len(pull_calls), 1)
        self.assertEqual(res_watch["total_sessions_pulled"], 1)


class TestServerStorageAndAppDirect(unittest.TestCase):
    """Direct non-skipping tests for server Storage upgrades and endpoint logic."""

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp = Path(self._tmp.name)

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def test_storage_migration_keyset_pagination_atomic_conflict_and_inventory(self) -> None:
        # 1. Create a legacy pre-G0.1 SQLite hub DB without additive columns
        db_file = self.tmp / "legacy_hub.db"
        conn = sqlite3.connect(db_file)
        conn.executescript("""
            CREATE TABLE sessions (
                session_id TEXT PRIMARY KEY, start_time TEXT, end_time TEXT,
                duration_seconds REAL, total_steps INTEGER, model TEXT,
                workspace_path TEXT, transcript_path TEXT, file_size_bytes INTEGER,
                has_errors INTEGER, tool_call_count INTEGER, tool_error_count INTEGER,
                intervention_count INTEGER, origin_developer TEXT DEFAULT 'local',
                remote_synced_at TEXT DEFAULT NULL
            );
            INSERT INTO sessions (session_id, start_time, total_steps, origin_developer, remote_synced_at)
            VALUES ('legacy-1', '2026-01-01T00:00:00Z', 3, 'alice', '2026-01-01T01:00:00Z');
        """)
        conn.commit()
        conn.close()

        storage = Storage(f"sqlite:///{db_file}")
        try:
            # Verify legacy row backfilled with server_seq = 1
            delta0 = storage.fetch_delta(since="1970-01-01T00:00:00Z", all_developers=True)
            self.assertEqual(delta0["sessions"][0]["server_seq"], 1)

            # 2. Upsert new sessions from multiple developers/machines/surfaces + backwards-compatible omit
            storage.upsert_batch(
                sessions=[
                    {
                        "session_id": "s-bob-1",
                        "start_time": "2026-11-26T03:00:00+06:00",
                        "end_time": "2026-11-26T03:10:00+06:00",
                        "total_steps": 4,
                        "tool_call_count": 2,
                        "origin_developer": None,
                        "origin_machine": "laptop-bob",
                        "client_surface": "cli",
                        "model": "gemini-4-argon",
                        "model_slug": "gemini-4-argon",
                    },
                    {
                        "session_id": "s-bob-old-client",
                        "start_time": "2026-11-25T12:00:00Z",
                        "total_steps": 2,
                    },
                ],
                steps=[
                    {"session_id": "s-bob-1", "step_index": 0, "content_snippet": "v1"},
                ],
                tool_calls=[
                    {"session_id": "s-bob-1", "step_index": 0, "tool_name": "old_tool", "started_at": "2026-11-26T03:01:00+06:00", "arguments_snippet": "x"},
                ],
                user_interventions=[],
                requesting_user="bob",
            )

            # Atomic conflict replacement (total_steps 4 -> 6) vs stale regression (total_steps 6 -> 1)
            storage.upsert_batch(
                sessions=[{"session_id": "s-bob-1", "total_steps": 6, "tool_call_count": 1, "total_input_tokens": 777}],
                steps=[{"session_id": "s-bob-1", "step_index": 0, "content_snippet": "v2"}],
                tool_calls=[{"session_id": "s-bob-1", "step_index": 0, "tool_name": "new_tool", "arguments_snippet": "y"}],
                user_interventions=[],
                requesting_user="bob",
            )
            storage.upsert_batch(
                sessions=[{"session_id": "s-bob-1", "total_steps": 1, "tool_call_count": 0}],
                steps=[{"session_id": "s-bob-1", "step_index": 0, "content_snippet": "stale"}],
                tool_calls=[],
                user_interventions=[],
                requesting_user="bob",
            )

            # Keyset pagination after_seq=1, limit=1, machine filter, developers multi-filter
            p1 = storage.fetch_delta(after_seq=1, limit=1, all_developers=True)
            self.assertEqual(len(p1["sessions"]), 1)
            self.assertTrue(p1["has_more"])
            p2 = storage.fetch_delta(after_seq=p1["next_after_seq"], limit=1, all_developers=True)
            self.assertEqual(len(p2["sessions"]), 1)
            self.assertFalse(p2["has_more"])

            bob_only = storage.fetch_delta(since="1970-01-01T00:00:00Z", developers=["bob"], machine="laptop-bob")
            self.assertEqual(len(bob_only["sessions"]), 1)
            b_sess = bob_only["sessions"][0]
            self.assertEqual(b_sess["start_time"], "2026-11-25T21:00:00Z")
            self.assertEqual(b_sess["total_steps"], 6)
            self.assertEqual(b_sess["tool_call_count"], 2)  # monotonic >= preserved!
            self.assertEqual([tc["tool_name"] for tc in bob_only["tool_calls"]], ["new_tool"])
            self.assertEqual(bob_only["steps"][0]["content_snippet"], "v2")

            # Inventory check
            inv = storage.get_inventory()
            self.assertEqual(inv["total_sessions"], 3)
            devs = {d["origin_developer"]: d for d in inv["developers"]}
            self.assertEqual(devs["bob"]["session_count"], 2)
            self.assertEqual(devs["alice"]["session_count"], 1)
            self.assertIn("laptop-bob", devs["bob"]["machines"])
        finally:
            storage.close()

    def test_server_app_inventory_and_pull_endpoints_without_starlette_skip(self) -> None:
        # Exercise server/app.py endpoint coroutines directly with a scoped minimal stub if starlette is absent
        fake_starlette_mods = {}
        try:
            import starlette  # noqa: F401
        except ImportError:
            class _StubJSONResponse:
                def __init__(self, content, status_code=200):
                    self.body = content
                    self.status_code = status_code

            class _StubApp:
                def __init__(self, routes=None, middleware=None):
                    self.routes = routes or []
                    self.state = types.SimpleNamespace()

            st_mod = types.ModuleType("starlette")
            st_apps = types.ModuleType("starlette.applications")
            st_apps.Starlette = _StubApp
            st_mw = types.ModuleType("starlette.middleware")
            st_mw.Middleware = lambda *a, **kw: None
            st_cors = types.ModuleType("starlette.middleware.cors")
            st_cors.CORSMiddleware = object
            st_req = types.ModuleType("starlette.requests")
            st_req.Request = object
            st_resp = types.ModuleType("starlette.responses")
            st_resp.JSONResponse = _StubJSONResponse
            st_rt = types.ModuleType("starlette.routing")
            st_rt.Route = lambda path, endpoint, methods=None: (path, endpoint, methods)
            fake_starlette_mods = {
                "starlette": st_mod,
                "starlette.applications": st_apps,
                "starlette.middleware": st_mw,
                "starlette.middleware.cors": st_cors,
                "starlette.requests": st_req,
                "starlette.responses": st_resp,
                "starlette.routing": st_rt,
            }

        with patch.dict(
            os.environ,
            {"PSL_HUB_TEST_AUTH": "1", "PSL_GITHUB_ORG": "purrfectsoft", "DATABASE_URL": "sqlite:///:memory:"},
        ), patch.dict(sys.modules, fake_starlette_mods):
            sys.modules.pop("server.app", None)
            import server.storage as storage_mod
            prev_default_storage = storage_mod._DEFAULT_STORAGE
            storage_mod._DEFAULT_STORAGE = None
            from server import auth
            auth.clear_auth_cache()
            import server.app as app_mod

            mem_storage = Storage("sqlite:///:memory:")
            mem_storage.upsert_batch(
                sessions=[{"session_id": "inv-1", "origin_developer": "alice", "origin_machine": "m1", "client_surface": "cli", "total_steps": 5}],
                steps=[], tool_calls=[], user_interventions=[], requesting_user="alice",
            )
            fake_app = types.SimpleNamespace(state=types.SimpleNamespace(storage=mem_storage))

            unauth_req = types.SimpleNamespace(headers={}, query_params={}, app=fake_app)
            r401 = asyncio.run(app_mod.sync_inventory_endpoint(unauth_req))
            self.assertEqual(r401.status_code, 401)

            auth_req = types.SimpleNamespace(headers={"Authorization": "Bearer test-token-bob"}, query_params={}, app=fake_app)
            r200 = asyncio.run(app_mod.sync_inventory_endpoint(auth_req))
            self.assertEqual(r200.status_code, 200)
            body = json.loads(r200.body.decode("utf-8")) if hasattr(r200, "body") and isinstance(r200.body, (bytes, bytearray)) else r200.body
            self.assertEqual(body["total_sessions"], 1)
            self.assertEqual(body["developers"][0]["origin_developer"], "alice")

            pull_req = types.SimpleNamespace(
                headers={"Authorization": "Bearer test-token-bob"},
                query_params={"since": "1970-01-01T00:00:00Z", "machine": "m1", "developers": "alice"},
                app=fake_app,
            )
            rp200 = asyncio.run(app_mod.sync_pull_endpoint(pull_req))
            self.assertEqual(rp200.status_code, 200)
            p_body = json.loads(rp200.body.decode("utf-8")) if hasattr(rp200, "body") and isinstance(rp200.body, (bytes, bytearray)) else rp200.body
            self.assertEqual(len(p_body["sessions"]), 1)
            self.assertIn("next_after_seq", p_body)

            mem_storage.close()
            if app_mod.app.state and getattr(app_mod.app.state, "storage", None):
                app_mod.app.state.storage.close()
            storage_mod._DEFAULT_STORAGE = prev_default_storage
            if fake_starlette_mods:
                sys.modules.pop("server.app", None)


if __name__ == "__main__":
    unittest.main()
