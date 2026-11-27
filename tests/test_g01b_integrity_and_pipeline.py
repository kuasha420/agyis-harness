#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Arafat Zahan (@kuasha420)
# Corporate Stewardship & Infrastructure: Purrfect Software Limited (PSL)
# Governed by: ICARO-42/b Ordinance (Company-Supported Personal IP Framework)

"""
Hermetic Sub-Second Test Suite for Gate 0 Phase G0.1-B:
- Wheel-portable database integrity audit & repair (harness/telemetry/integrity.py)
- Harvester precedence, IDE/CLI discovery, fn=29, gen_metadata, backfill_tool_volumes
- Pipeline analyzer fixes (dynamics TOOL_CALL:*, cluster noise filter, tier normalization,
  reconciled errors, cognitive traces .db fallback, CLI artifacts, remote/local project configs)
- Dynamic Git Era x Model engine (pipeline/analyze_eras.py)
- Privacy-safe grounded website JSON exporter (pipeline/export_website_metrics.py)
"""

from __future__ import annotations

import io
import json
import os
from pathlib import Path
import sqlite3
import subprocess
import tempfile
import unittest
from unittest.mock import patch

from harness.cli import main as cli_main
from harness.telemetry.extractor import ensure_telemetry_schema, extract_session, upsert_session_telemetry
from harness.telemetry.integrity import audit_database_integrity, repair_database_integrity
from harness.telemetry.integrity_dedup import plan_session_dedup
from pipeline.analyze_context_dynamics import analyze_context_dynamics
from pipeline.analyze_eras import analyze_eras, derive_git_eras
from pipeline.analyze_failure_clusters import analyze_model_failures_and_interventions, generate_markdown_report as gen_cluster_md
from pipeline.analyze_ultra_deep_sessions import analyze_ultra_deep_sessions
from pipeline.analyze_volume_distributions import analyze_volumes
from pipeline.audit_artifacts import audit_artifacts
from pipeline.audit_project_configs import analyze_all_workspaces
from pipeline.benchmark_reasoning_tiers import classify_session_tier, evaluate_reasoning_tiers
from pipeline.classify_failures import run_classification_audit
from pipeline.export_website_metrics import export_website_metrics
from pipeline.extract_cognitive_traces import extract_cognitive_traces
from pipeline.extract_transcripts import backfill_tool_volumes
from pipeline.harvest_conversations import extract_conversation_db, harvest_all_conversations, harvest_conversation_db


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


def _create_conv_db(
    db_path: Path,
    cid: str,
    model_slug: str = "",
    model_display: str = "",
    use_fn29: bool = False,
) -> None:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()
    cur.execute("CREATE TABLE trajectory_meta (trajectory_id TEXT, cascade_id TEXT)")
    cur.execute("INSERT INTO trajectory_meta VALUES (?, ?)", (cid, cid))
    cur.execute("CREATE TABLE trajectory_metadata_blob (id TEXT, data BLOB)")
    ts_pb = _pb_varint(1, 1795000000) + _pb_varint(2, 0)
    cur.execute("INSERT INTO trajectory_metadata_blob VALUES ('main', ?)", (_pb_bytes(2, ts_pb) + _pb_bytes(18, b"/home/dev/proj"),))
    cur.execute("CREATE TABLE steps (idx INTEGER PRIMARY KEY, step_type INTEGER, status INTEGER, metadata BLOB, error_details BLOB, step_payload BLOB)")

    tc_orig = _pb_bytes(2, b"run_command") + _pb_bytes(3, b'{"CommandLine":"grep foo"}')
    tc_mod = _pb_bytes(2, b"run_command") + _pb_bytes(3, b'{"CommandLine":"grep foo || [ $? -eq 1 ]"}')
    meta_tc = _pb_bytes(1, ts_pb) + _pb_bytes(4, tc_orig) + (_pb_bytes(29, tc_mod) if use_fn29 else b"")
    cur.execute("INSERT INTO steps VALUES (0, 14, 3, ?, NULL, ?)", (_pb_bytes(1, ts_pb), _pb_bytes(19, _pb_bytes(2, b"Check tests"))))
    cur.execute("INSERT INTO steps VALUES (1, 15, 3, ?, NULL, ?)", (_pb_bytes(1, ts_pb), _pb_bytes(20, _pb_bytes(3, b"**Plan**\nRunning command."))))
    cur.execute("INSERT INTO steps VALUES (2, 132, 3, ?, NULL, ?)", (meta_tc, _pb_bytes(140, _pb_bytes(2, _pb_bytes(1, b"Command exited with code 0.")))))

    if model_slug or model_display:
        cur.execute("CREATE TABLE gen_metadata (idx INTEGER PRIMARY KEY, data BLOB)")
        cwm = _pb_varint(1, 12000) + _pb_varint(4, 512000)
        csm = _pb_varint(2, 1) + _pb_bytes(10, cwm)
        if model_slug:
            csm += _pb_bytes(19, model_slug.encode("utf-8"))
        if model_display:
            csm += _pb_bytes(21, model_display.encode("utf-8"))
        usage = _pb_varint(2, 1500) + _pb_varint(5, 4000) + _pb_varint(9, 120) + _pb_varint(10, 300)
        cur.execute("INSERT INTO gen_metadata VALUES (0, ?)", (_pb_bytes(1, _pb_bytes(9, csm) + _pb_bytes(4, usage)),))
    conn.commit()
    conn.close()


class TestDatabaseIntegrity(unittest.TestCase):
    """Validates audit_database_integrity, repair_database_integrity, and CLI db-integrity."""

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp = Path(self._tmp.name)

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def test_pre_g01_audit_and_repair_dedup_richest_timestamps_and_counters(self) -> None:
        db_path = self.tmp / "legacy.db"
        app_dir = self.tmp / "antigravity"
        sid_local = "11111111-1111-1111-1111-111111111111"
        tpath = app_dir / "brain" / sid_local / ".system_generated" / "logs" / "transcript.jsonl"
        tpath.parent.mkdir(parents=True)
        tpath.write_text(json.dumps({"step_index": 0, "type": "USER_INPUT", "content": "hi"}) + "\n", encoding="utf-8")
        _create_conv_db(app_dir / "conversations" / f"{sid_local}.db", sid_local, model_slug="gemini-4-hydrogen", model_display="Gemini 4 Hydrogen")

        conn = sqlite3.connect(db_path)
        conn.executescript(
            """
            CREATE TABLE sessions (
                session_id TEXT PRIMARY KEY, start_time TEXT, end_time TEXT,
                duration_seconds REAL, total_steps INTEGER, model TEXT,
                workspace_path TEXT, transcript_path TEXT, file_size_bytes INTEGER,
                has_errors INTEGER, tool_call_count INTEGER, tool_error_count INTEGER,
                intervention_count INTEGER, origin_developer TEXT DEFAULT 'local',
                remote_synced_at TEXT DEFAULT NULL
            );
            CREATE TABLE steps (
                id INTEGER PRIMARY KEY AUTOINCREMENT, session_id TEXT, step_index INTEGER,
                step_type TEXT, source TEXT, status TEXT, created_at TEXT,
                content_length INTEGER, content_snippet TEXT, has_thinking INTEGER,
                thinking_length INTEGER, tool_count INTEGER
            );
            CREATE TABLE tool_calls (
                id INTEGER PRIMARY KEY AUTOINCREMENT, session_id TEXT, step_index INTEGER,
                result_step_index INTEGER, tool_name TEXT, arguments_json TEXT,
                arguments_snippet TEXT, target_path TEXT, command_line TEXT,
                started_at TEXT, completed_at TEXT, duration_seconds REAL,
                status TEXT, exit_code INTEGER, error_snippet TEXT,
                is_loop_candidate INTEGER DEFAULT 0, output_length_chars INTEGER,
                output_lines INTEGER, arguments_length_chars INTEGER,
                command_category TEXT, is_truncated INTEGER DEFAULT 0
            );
            CREATE TABLE user_interventions (
                id INTEGER PRIMARY KEY AUTOINCREMENT, session_id TEXT, step_index INTEGER,
                created_at TEXT, prompt_text TEXT, prompt_length INTEGER,
                preceding_tool_failed INTEGER, preceding_tool_name TEXT,
                preceding_error_snippet TEXT, intervention_type TEXT
            );
            """
        )
        conn.execute(
            "INSERT INTO sessions VALUES (?, '2026-10-10T16:00:00+06:00', '2026-10-10T16:05:00+06:00', 300.0, 99, 'Gemini 3.5/Flash/Pro (Default)', '/home/dev/proj', ?, 100, 0, 99, 0, 99, 'local', NULL)",
            (sid_local, str(tpath)),
        )
        # Remote metadata-only session (positive total_steps preserved when steps=0; origin_machine stays NULL)
        conn.execute(
            "INSERT INTO sessions VALUES ('remote-meta', '2026-10-11T10:00:00+00:00', '2026-10-11T10:10:00+00:00', 600.0, 42, 'gemini-4-neon', '[WORKSPACE_ROOT]', '[WORKSPACE_ROOT]/t.jsonl', 200, 0, 0, 0, 0, 'teammate', '2026-10-11T10:15:00+00:00')"
        )
        # Zero-step orphan
        conn.execute(
            "INSERT INTO sessions VALUES ('orphan-zero', '2026-10-12T10:00:00Z', '2026-10-12T10:00:00Z', 0.0, 0, 'Unknown', '', '/tmp/antigravity-cli/conversations/o.db', 10, 0, 0, 0, 0, 'local', NULL)"
        )
        conn.execute("INSERT INTO steps (session_id, step_index, step_type, created_at) VALUES (?, 0, 'USER_INPUT', '2026-10-10T16:00:00+06:00')", (sid_local,))
        conn.execute("INSERT INTO steps (session_id, step_index, step_type, created_at) VALUES (?, 1, 'TOOL_CALL:grep_search', '2026-10-10T16:01:00+06:00')", (sid_local,))

        # Same-step dup: row 1 pyrepr with 0 output; row 2 json with 2400 chars & error_snippet -> row 2 MUST survive
        conn.execute(
            "INSERT INTO tool_calls (session_id, step_index, tool_name, arguments_json, arguments_snippet, started_at, status, exit_code, output_length_chars, error_snippet) VALUES (?, 1, 'grep_search', NULL, \"{'CaseInsensitive': True, 'SearchPath': '[USER_HOME]/proj/src'}\", '2026-10-10T10:01:00Z', 'SUCCESS', 0, 0, '')",
            (sid_local,),
        )
        conn.execute(
            "INSERT INTO tool_calls (session_id, step_index, tool_name, arguments_json, arguments_snippet, started_at, status, exit_code, output_length_chars, error_snippet) VALUES (?, 1, 'grep_search', '{\"CaseInsensitive\": true, \"SearchPath\": \"/home/dev/proj/src\"}', '{\"CaseInsensitive\": true}', '2026-10-10T16:01:00+06:00', 'FAILED', 1, 2400, 'exit 1')",
            (sid_local,),
        )
        # Cross-source dup at step 2 vs 3 (+06:00 vs Z, [WORKSPACE_ROOT] vs /home/dev/proj)
        conn.execute(
            "INSERT INTO tool_calls (session_id, step_index, tool_name, arguments_json, arguments_snippet, started_at, status, exit_code, output_length_chars) VALUES (?, 2, 'view_file', NULL, '{\"AbsolutePath\": \"/home[WORKSPACE_ROOT]/README.md\"}', '2026-10-10T16:02:00+06:00', 'SUCCESS', 0, 0)",
            (sid_local,),
        )
        conn.execute(
            "INSERT INTO tool_calls (session_id, step_index, tool_name, arguments_json, arguments_snippet, started_at, status, exit_code, output_length_chars) VALUES (?, 3, 'view_file', '{\"AbsolutePath\": \"/home/dev/proj/README.md\"}', '{\"AbsolutePath\": \"/home/dev/proj/README.md\"}', '2026-10-10T10:02:01Z', 'SUCCESS', 0, 500)",
            (sid_local,),
        )
        # Distinct genuine call at step 5
        conn.execute(
            "INSERT INTO tool_calls (session_id, step_index, tool_name, arguments_json, arguments_snippet, started_at, status, exit_code, output_length_chars) VALUES (?, 5, 'run_command', '{\"CommandLine\": \"pytest\"}', '{\"CommandLine\": \"pytest\"}', '2026-10-10T10:03:00Z', 'SUCCESS', 0, 120)",
            (sid_local,),
        )
        conn.execute("INSERT INTO user_interventions (session_id, step_index, created_at, prompt_text) VALUES (?, 0, '2026-10-10T16:00:00+06:00', 'go')", (sid_local,))
        conn.commit()
        conn.close()

        pre_audit = audit_database_integrity(db_path)
        self.assertFalse(pre_audit["healthy"])
        self.assertEqual(pre_audit["duplicate_tool_calls"]["total"], 2)
        self.assertGreater(pre_audit["non_utc_timestamps"]["total"], 0)
        self.assertIn("origin_machine", pre_audit["schema"]["missing_columns"])

        dry_res = repair_database_integrity(db_path, dry_run=True)
        self.assertTrue(dry_res["dry_run"])
        self.assertEqual(audit_database_integrity(db_path)["counts"]["tool_calls"], 5)

        with patch("sys.stdout", new_callable=io.StringIO) as out:
            rc = cli_main(["audit", "db-integrity", "--db", str(db_path), "--repair", "--json"])
        self.assertEqual(rc, 0)
        rep = json.loads(out.getvalue())
        self.assertTrue(rep["repaired"])
        self.assertEqual(rep["actions"]["tool_calls_dropped_total"], 2)
        self.assertEqual(rep["actions"]["zero_step_orphans_count"], 1)
        self.assertTrue(rep["audit_after"]["healthy"])

        conn = sqlite3.connect(db_path)
        row_local = conn.execute(
            "SELECT total_steps, tool_call_count, tool_error_count, intervention_count, has_errors, model, model_slug, max_context_tokens, origin_machine, client_surface, source_kind, start_time FROM sessions WHERE session_id = ?",
            (sid_local,),
        ).fetchone()
        self.assertEqual(row_local[:5], (2, 3, 1, 1, 1))
        self.assertEqual(row_local[5], "gemini-4-hydrogen")
        self.assertEqual(row_local[6], "gemini-4-hydrogen")
        self.assertEqual(row_local[7], 512000)
        self.assertTrue(bool(row_local[8]))
        self.assertEqual(row_local[9], "ide")
        self.assertEqual(row_local[10], "transcript")
        self.assertEqual(row_local[11], "2026-10-10T10:00:00Z")

        # Richest rows survived
        tc_rows = conn.execute("SELECT tool_name, output_length_chars, error_snippet FROM tool_calls WHERE session_id = ? ORDER BY step_index", (sid_local,)).fetchall()
        self.assertEqual(tc_rows, [("grep_search", 2400, "exit 1"), ("view_file", 500, None), ("run_command", 120, None)])

        # Remote positive step count preserved and origin_machine stays NULL
        row_rem = conn.execute("SELECT total_steps, origin_machine FROM sessions WHERE session_id = 'remote-meta'").fetchone()
        self.assertEqual(row_rem, (42, None))
        row_cli = conn.execute("SELECT client_surface, source_kind FROM sessions WHERE session_id = 'orphan-zero'").fetchone()
        self.assertEqual(row_cli, ("cli", "sqlite_db"))
        conn.close()

    def test_hammer_regressions_dedup_schema_null_and_failure_preservation(self) -> None:
        db_path = self.tmp / "regressions.db"
        conn = sqlite3.connect(db_path)
        conn.executescript(
            """
            CREATE TABLE sessions (
                session_id TEXT PRIMARY KEY, start_time TEXT, end_time TEXT,
                duration_seconds REAL, total_steps INTEGER, model TEXT,
                workspace_path TEXT, transcript_path TEXT, file_size_bytes INTEGER,
                has_errors INTEGER, tool_call_count INTEGER, tool_error_count INTEGER,
                intervention_count INTEGER, origin_developer TEXT DEFAULT 'local',
                remote_synced_at TEXT DEFAULT NULL
            );
            CREATE TABLE steps (
                id INTEGER PRIMARY KEY AUTOINCREMENT, session_id TEXT, step_index INTEGER,
                step_type TEXT, source TEXT, status TEXT, created_at TEXT,
                content_length INTEGER, content_snippet TEXT, has_thinking INTEGER,
                thinking_length INTEGER, tool_count INTEGER
            );
            CREATE TABLE tool_calls (
                id INTEGER PRIMARY KEY AUTOINCREMENT, session_id TEXT, step_index INTEGER,
                result_step_index INTEGER, tool_name TEXT, arguments_json TEXT,
                arguments_snippet TEXT, target_path TEXT, command_line TEXT,
                started_at TEXT, completed_at TEXT, duration_seconds REAL,
                status TEXT, exit_code INTEGER, error_snippet TEXT,
                is_loop_candidate INTEGER DEFAULT 0, output_length_chars INTEGER,
                output_lines INTEGER, arguments_length_chars INTEGER,
                command_category TEXT, is_truncated INTEGER DEFAULT 0
            );
            CREATE TABLE user_interventions (
                id INTEGER PRIMARY KEY AUTOINCREMENT, session_id TEXT, step_index INTEGER,
                created_at TEXT, prompt_text TEXT, prompt_length INTEGER,
                preceding_tool_failed INTEGER, preceding_tool_name TEXT,
                preceding_error_snippet TEXT, intervention_type TEXT
            );
            """
        )
        conn.execute(
            "INSERT INTO sessions VALUES ('s1', '2026-10-10T10:00:00Z', '2026-10-10T10:10:00Z', 600.0, 1200, 'gemini-4-argon', '/home/dev/proj', '/tmp/antigravity/conversations/s1.db', 100, 0, NULL, NULL, NULL, 'local', NULL)"
        )
        # Schema Defect #4: genuine parallel started_at IS NULL calls must survive ensure_telemetry_schema,
        # while exact non-NULL duplicates collapse cleanly.
        conn.executemany(
            "INSERT INTO tool_calls (session_id, step_index, tool_name, arguments_json, arguments_snippet, started_at, status, exit_code) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            [
                ("s1", 1, "read_file", '{"Path": "/a.py"}', "{}", None, "SUCCESS", 0),
                ("s1", 1, "read_file", '{"Path": "/b.py"}', "{}", None, "SUCCESS", 0),
                ("s1", 2, "run_command", '{"CommandLine": "ls"}', '{"CommandLine": "ls"}', "2026-10-10T10:01:00Z", "SUCCESS", 0),
                ("s1", 2, "run_command", '{"CommandLine": "ls"}', '{"CommandLine": "ls"}', "2026-10-10T10:01:00Z", "SUCCESS", 0),
            ],
        )
        conn.commit()
        ensure_telemetry_schema(conn)
        null_kept = conn.execute("SELECT COUNT(*) FROM tool_calls WHERE step_index = 1 AND started_at IS NULL").fetchone()[0]
        self.assertEqual(null_kept, 2)

        # Defect #1 (DELETE-before-UPDATE on unique index) + Defect #5 (Pass 1 -> Pass 2 transitive loser + FAILED propagation):
        # row A (pyrepr, FAILED exit 2 'boom', started_at NULL) + row B (pyrepr, SUCCESS, started_at='2026-10-10T10:02:00Z', olen=100)
        # collapse in Pass 1 to B, then Pass 2 absorbs B into C (json, SUCCESS, started_at NULL, olen=500).
        conn.executemany(
            "INSERT INTO tool_calls (session_id, step_index, tool_name, arguments_json, arguments_snippet, started_at, status, exit_code, error_snippet, output_length_chars) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            [
                ("s1", 3, "grep_search", None, "{'Query': 'alpha'}", None, "FAILED", 2, "boom", 0),
                ("s1", 3, "grep_search", None, "{'Query': 'alpha'}", "2026-10-10T10:02:00Z", "SUCCESS", 0, None, 100),
                ("s1", 3, "grep_search", '{"Query": "alpha"}', '{"Query": "alpha"}', None, "SUCCESS", 0, None, 500),
                # Defect #2: parallel calls differing past char 120 MUST NOT merge (even across Pass 2 tz offset)
                ("s1", 4, "run_command", None, "prefix_" + ("x" * 140) + "_alpha", "2026-10-10T10:03:00Z", "SUCCESS", 0, None, 10),
                ("s1", 4, "run_command", None, "prefix_" + ("x" * 140) + "_beta", "2026-10-10T16:03:00+06:00", "SUCCESS", 0, None, 20),
                # Defect #6: status IS NULL with exit_code=0 must reconcile identically -> audit_after.healthy == True
                ("s1", 5, "view_file", '{"AbsolutePath": "/x.py"}', '{"AbsolutePath": "/x.py"}', "2026-10-10T10:04:00Z", None, 0, None, 30),
                # Defect #3: idx_tool_calls_uniq collision on started_at normalization preserves richer/FAILED data
                ("s1", 6, "run_command", '{"CommandLine": "echo hi", "pad": "' + ("a" * 260) + '"}', '{"CommandLine":"echo hi"}', "2026-10-10T10:05:00Z", "SUCCESS", 0, None, 10),
                ("s1", 6, "run_command", '{"CommandLine": "echo hi", "pad": "' + ("b" * 260) + '"}', '{"CommandLine":"echo hi"}', "2026-10-10T16:05:00+06:00", "FAILED", 3, "ts_conflict_fail", 400),
            ],
        )
        conn.commit()
        conn.close()

        rep = repair_database_integrity(db_path)
        self.assertTrue(rep["audit_after"]["healthy"])
        self.assertEqual(rep["audit_after"]["counter_mismatches"]["tool_error_count"], 0)

        conn = sqlite3.connect(db_path)
        r3 = conn.execute("SELECT status, exit_code, error_snippet, started_at, output_length_chars FROM tool_calls WHERE session_id='s1' AND step_index=3").fetchall()
        self.assertEqual(len(r3), 1)
        self.assertEqual(r3[0], ("FAILED", 2, "boom", "2026-10-10T10:02:00Z", 500))
        self.assertEqual(conn.execute("SELECT COUNT(*) FROM tool_calls WHERE session_id='s1' AND step_index=4").fetchone()[0], 2)
        r6 = conn.execute("SELECT status, exit_code, error_snippet, started_at, output_length_chars FROM tool_calls WHERE session_id='s1' AND step_index=6").fetchall()
        self.assertEqual(r6, [("FAILED", 3, "ts_conflict_fail", "2026-10-10T10:05:00Z", 400)])
        conn.close()

        # Defect #7: analyze_ultra_deep_sessions handles NULL counters without TypeError
        ultra = analyze_ultra_deep_sessions(db_path)
        self.assertEqual(ultra["macro_summary"]["total_titan_sessions"], 1)

        # Minor #8a: O(N) bucketing keeps 2,500 tool calls sub-second
        bulk = [{"id": i + 1, "step_index": i, "tool_name": "run_command", "arguments_json": f'{{"i": {i}}}', "started_at": "2026-10-10T10:00:00Z"} for i in range(2500)]
        d_ids, _, _, _ = plan_session_dedup(bulk)
        self.assertEqual(d_ids, [])


class TestHarvesterAndAnalyzers(unittest.TestCase):
    """Validates harvester precedence, fn=29, backfill_tool_volumes, and all pipeline analyzers."""

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp = Path(self._tmp.name)

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def test_harvester_precedence_fn29_cli_surface_and_parallel_backfill(self) -> None:
        target_db = self.tmp / "telemetry.db"
        ide_app = self.tmp / "antigravity"
        cli_app = self.tmp / "antigravity-cli"
        sid = "22222222-2222-2222-2222-222222222222"

        # 1. Seed richer transcript_full.jsonl with Unknown model & parallel tool calls at step 1
        t_full = ide_app / "brain" / sid / ".system_generated" / "logs" / "transcript_full.jsonl"
        t_full.parent.mkdir(parents=True)
        t_full.write_text(
            "\n".join([
                json.dumps({"step_index": 0, "type": "USER_INPUT", "created_at": "2026-11-20T10:00:00Z", "content": "Run parallel reads"}),
                json.dumps({"step_index": 1, "type": "PLANNER_RESPONSE", "created_at": "2026-11-20T10:00:05Z", "tool_calls": [
                    {"name": "read_file", "args": {"Path": "/repo/a.py"}},
                    {"name": "read_file", "args": {"Path": "/repo/b.py"}},
                ]}),
                json.dumps({"step_index": 2, "type": "GENERIC", "status": "DONE", "content": "Created At: 2026-11-20T10:00:05Z\nCompleted At: 2026-11-20T10:00:06Z\n" + ("A" * 100)}),
                json.dumps({"step_index": 3, "type": "GENERIC", "status": "DONE", "content": "Created At: 2026-11-20T10:00:06Z\nCompleted At: 2026-11-20T10:00:07Z\n" + ("B" * 400)}),
            ]) + "\n",
            encoding="utf-8",
        )
        conn = sqlite3.connect(target_db)
        ensure_telemetry_schema(conn)
        ext = extract_session(t_full)
        self.assertIsNotNone(ext)
        upsert_session_telemetry(conn, *ext)
        # Clear output_length_chars to test backfill_tool_volumes on parallel calls
        conn.execute("UPDATE tool_calls SET output_length_chars = NULL WHERE session_id = ?", (sid,))
        conn.commit()
        conn.close()

        bf_res = backfill_tool_volumes(target_db, verbose=False)
        self.assertEqual(bf_res["updated_tool_calls"], 2)
        conn = sqlite3.connect(target_db)
        olens = [r[0] for r in conn.execute("SELECT output_length_chars FROM tool_calls WHERE session_id = ? ORDER BY result_step_index", (sid,)).fetchall()]
        conn.close()
        self.assertNotEqual(olens[0], olens[1])
        self.assertLess(olens[0], olens[1])

        # Verify Minor #8b: outer-loop tier matching prevents an earlier Tier-3 row (ridx=None) from stealing Tier-0 exact (ridx=3)
        conn = sqlite3.connect(target_db)
        conn.execute("DELETE FROM tool_calls WHERE session_id = ?", (sid,))
        conn.executemany(
            "INSERT INTO tool_calls (session_id, step_index, result_step_index, tool_name, arguments_json, arguments_snippet) VALUES (?, 1, ?, 'read_file', ?, ?)",
            [
                (sid, None, '{"Path": "/repo/a.py"}', '{"Path": "/repo/a.py"}'),
                (sid, 3, '{"Path": "/repo/b.py"}', '{"Path": "/repo/b.py"}'),
            ],
        )
        conn.commit()
        conn.close()
        backfill_tool_volumes(target_db, verbose=False)
        conn = sqlite3.connect(target_db)
        rows_ord = conn.execute("SELECT result_step_index, output_length_chars FROM tool_calls WHERE session_id = ? ORDER BY id", (sid,)).fetchall()
        conn.close()
        self.assertGreater(rows_ord[1][1], rows_ord[0][1])

        # Verify Minor #8c: analyze_volumes(..., auto_backfill=False) stays strictly read-only even on chmod 0444 DB
        target_db.chmod(0o444)
        try:
            ro_vol = analyze_volumes(target_db, auto_backfill=False, verbose=False)
            self.assertEqual(ro_vol["summary"]["total_tool_calls"], 2)
            self.assertFalse(Path(f"{target_db}-shm").exists())
            self.assertFalse(Path(f"{target_db}-wal").exists())
        finally:
            target_db.chmod(0o644)

        # 2. Harvest sibling .db -> must NOT clobber transcript_full.jsonl, MUST enrich model_slug/tokens
        sib_db = ide_app / "conversations" / f"{sid}.db"
        _create_conv_db(sib_db, sid, model_slug="gemini-4-argon", model_display="Gemini 4 Argon (High)", use_fn29=True)
        res = harvest_conversation_db(sib_db, target_db)
        self.assertEqual(res["status"], "enriched")
        conn = sqlite3.connect(target_db)
        row = conn.execute("SELECT transcript_path, source_kind, model, model_slug, total_steps, total_input_tokens FROM sessions WHERE session_id = ?", (sid,)).fetchone()
        conn.close()
        self.assertEqual(row[0], str(t_full))
        self.assertEqual(row[1], "transcript_full")
        self.assertEqual(row[2], "gemini-4-argon")
        self.assertEqual(row[3], "gemini-4-argon")
        self.assertEqual(row[4], 4)
        self.assertEqual(row[5], 1500)

        # 3. CLI conversation DB with fn=29 and NO gen_metadata -> model='Unknown' (never Default), client_surface='cli'
        cli_sid = "33333333-3333-3333-3333-333333333333"
        cli_db = cli_app / "conversations" / f"{cli_sid}.db"
        _create_conv_db(cli_db, cli_sid, use_fn29=True)
        ext_cli = extract_conversation_db(cli_db)
        self.assertIsNotNone(ext_cli)
        s_cli, _, tc_cli, _ = ext_cli
        self.assertEqual(s_cli["model"], "Unknown")
        self.assertEqual(s_cli["client_surface"], "cli")
        self.assertEqual(s_cli["source_kind"], "sqlite_db")
        self.assertIn("|| [ $? -eq 1 ]", tc_cli[0]["command_line"])
        self.assertTrue(s_cli["start_time"].endswith("Z"))

        # 4. harvest_all_conversations(None, ...) scans both IDE and CLI defaults
        with patch("harness.utils.context.get_app_data_dir_candidates", return_value=[ide_app, cli_app]):
            cnt = harvest_all_conversations(None, target_db)
        self.assertEqual(cnt, 2)

    def test_analyzers_noise_filter_tier_isolation_dynamics_and_configs(self) -> None:
        db_path = self.tmp / "analyzers.db"
        conn = sqlite3.connect(db_path)
        ensure_telemetry_schema(conn)
        conn.executemany(
            """
            INSERT INTO sessions (
                session_id, start_time, end_time, duration_seconds, total_steps,
                model, workspace_path, transcript_path, has_errors,
                tool_call_count, tool_error_count, intervention_count,
                origin_developer, client_surface, total_input_tokens, total_cache_read_tokens
            ) VALUES (?, ?, ?, 120.0, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                ("s-g4a", "2026-11-20T10:00:00Z", "2026-11-20T10:02:00Z", 50, "gemini-4-argon-medium", "[WORKSPACE_ROOT]", "/x/transcript.jsonl", 0, 1, 0, 0, "teammate", "cli", 5000, 10000),
                ("s-c55", "2026-11-21T10:00:00Z", "2026-11-21T10:02:00Z", 40, "claude-sonnet-5-5-medium", "/tmp/local_ws", "/x/c.db", 1, 1, 1, 0, "local", "ide", 2000, 3000),
                ("s-leg", "2026-10-05T10:00:00Z", "2026-10-05T10:02:00Z", 30, "Gemini 3.5/Flash/Pro (Default)", "/tmp/local_ws", "/x/l.db", 0, 0, 0, 0, "local", "ide", None, None),
                ("s-bad", "2026-10-05T10:00:00Z", "2026-10-05T10:02:00Z", 10, '"([^"', "/tmp/local_ws", "/x/b.db", 0, 0, 0, 0, "local", "ide", None, None),
            ],
        )
        conn.execute(
            "INSERT INTO steps (session_id, step_index, step_type, content_length, has_thinking, thinking_length, content_snippet) VALUES ('s-g4a', 1, 'TOOL_CALL:run_command', 0, 1, 200, '**Thinking** retry')"
        )
        conn.execute(
            "INSERT INTO tool_calls (session_id, step_index, tool_name, status, exit_code, output_length_chars) VALUES ('s-g4a', 1, 'run_command', 'SUCCESS', 0, 4096)"
        )
        conn.execute(
            "INSERT INTO tool_calls (session_id, step_index, tool_name, status, exit_code, output_length_chars) VALUES ('s-c55', 1, 'run_command', 'FAILED', 1, 512)"
        )
        conn.commit()
        conn.close()

        # Dynamics counts TOOL_CALL:* and tool_calls.output_length_chars + persisted protobuf tokens
        dyn = analyze_context_dynamics(db_path)
        self.assertEqual(dyn["compaction_simulation"]["steps_exceeding_2kb"], 1)
        self.assertEqual(dyn["protobuf_token_summary"]["sessions_with_protobuf_tokens"], 2)

        # Classify failures reconciles total_tool_errors from tool_calls
        clf = run_classification_audit(db_path)
        self.assertEqual(clf["overview"]["total_tool_errors"], sum(t["fails"] for t in clf["tool_stats"]))

        # Failure clusters filters corrupt regex noise and removes hardcoded 2026-10-10 date
        cl = analyze_model_failures_and_interventions(db_path)
        profile_models = {m["model"] for m in cl["model_profiles"]}
        self.assertNotIn('"([^"', profile_models)
        self.assertNotIn("2026-10-10", gen_cluster_md(cl))

        # Benchmark isolates unattributed_legacy and maps Gemini 4 Argon / Claude 5.5
        self.assertEqual(classify_session_tier("Gemini 3.5/Flash/Pro (Default)", True, 5000), "unattributed_legacy")
        self.assertEqual(classify_session_tier("gemini-4-argon-medium", False, 0), "gemini-4-argon")
        self.assertEqual(classify_session_tier("claude-sonnet-5-5-medium", False, 0), "claude-sonnet-5-5")
        bench = evaluate_reasoning_tiers(db_path, write_files=False)
        self.assertEqual(bench["tiers"]["gemini-4-argon"]["session_count"], 1)
        self.assertEqual(bench["tiers"]["claude-sonnet-5-5"]["session_count"], 1)
        self.assertEqual(bench["tiers"]["gemini-3.1-pro"]["session_count"], 0)
        self.assertEqual(bench["isolated_unattributed"]["unattributed_legacy"]["session_count"], 1)

        # Cognitive traces processes .db-sourced sessions without crashing
        cog = extract_cognitive_traces(db_path)
        self.assertEqual(cog["total_sessions"], 4)
        self.assertGreaterEqual(cog["top_100_worst_trajectories_count"], 1)

        # Project configs keeps remote [WORKSPACE_ROOT] separate from local workspaces
        local_ws = self.tmp / "local_ws_real"
        local_ws.mkdir()
        (local_ws / "AGENTS.md").write_text("# Rules\n", encoding="utf-8")
        conn = sqlite3.connect(db_path)
        conn.execute("UPDATE sessions SET workspace_path = ? WHERE session_id = 's-c55'", (str(local_ws),))
        conn.commit()
        conn.close()
        ws_res = analyze_all_workspaces(db_path)
        self.assertEqual(ws_res["redacted_remote_summary"]["session_count"], 1)
        self.assertFalse(any(w["workspace_path"] == "[WORKSPACE_ROOT]" for w in ws_res["workspaces"]))

        # Audit artifacts scans both IDE & CLI brains
        ide_b = self.tmp / "antigravity" / "brain" / "s1"
        cli_b = self.tmp / "antigravity-cli" / "brain" / "s2"
        ide_b.mkdir(parents=True)
        cli_b.mkdir(parents=True)
        (ide_b / "task.md").write_text("# Task\n", encoding="utf-8")
        (cli_b / "walkthrough.md").write_text("# Done\n", encoding="utf-8")
        with patch("pipeline.audit_artifacts.get_brain_dir_candidates", return_value=[ide_b.parent, cli_b.parent]):
            art = audit_artifacts()
        self.assertEqual(art["total_markdown_artifacts"], 2)
        self.assertEqual(art["surfaces"]["ide"]["artifacts"], 1)
        self.assertEqual(art["surfaces"]["cli"]["artifacts"], 1)


class TestErasAndWebsiteExporter(unittest.TestCase):
    """Validates dynamic Git eras and privacy-safe grounded website JSON exporter."""

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp = Path(self._tmp.name)

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def test_derive_git_eras_dynamic_and_fallback(self) -> None:
        # 1. Fallback when .git unavailable
        no_git = self.tmp / "no_git"
        no_git.mkdir()
        fallback = derive_git_eras(no_git)
        self.assertEqual(fallback[0]["era_id"], "0_Pre-Harness")
        self.assertEqual(fallback[0]["source"], "default_milestones")

        # 2. Dynamic derivation from real temp git repo with annotated tags
        repo = self.tmp / "git_repo"
        repo.mkdir()
        env = dict(os.environ, GIT_AUTHOR_NAME="Test", GIT_AUTHOR_EMAIL="t@example.com", GIT_COMMITTER_NAME="Test", GIT_COMMITTER_EMAIL="t@example.com")
        subprocess.run(["git", "init"], cwd=repo, env=env, capture_output=True, check=True)
        (repo / "README.md").write_text("init\n", encoding="utf-8")
        subprocess.run(["git", "add", "README.md"], cwd=repo, env=env, capture_output=True, check=True)
        subprocess.run(["git", "commit", "-m", "init"], cwd=repo, env={**env, "GIT_AUTHOR_DATE": "2026-10-02T12:00:00Z", "GIT_COMMITTER_DATE": "2026-10-02T12:00:00Z"}, capture_output=True, check=True)
        subprocess.run(["git", "tag", "-a", "v1.0.0", "-m", "release"], cwd=repo, env={**env, "GIT_AUTHOR_DATE": "2026-10-15T12:00:00Z", "GIT_COMMITTER_DATE": "2026-10-15T12:00:00Z"}, capture_output=True, check=True)
        (repo / "README.md").write_text("v1.1\n", encoding="utf-8")
        subprocess.run(["git", "commit", "-am", "post"], cwd=repo, env={**env, "GIT_AUTHOR_DATE": "2026-11-01T12:00:00Z", "GIT_COMMITTER_DATE": "2026-11-01T12:00:00Z"}, capture_output=True, check=True)

        dyn_eras = derive_git_eras(repo)
        self.assertEqual(dyn_eras[0]["era_id"], "0_Pre-Harness")
        self.assertEqual(dyn_eras[0]["source"], "git")
        self.assertTrue(any(e["tag"] == "v1.0.0" for e in dyn_eras))
        self.assertEqual(dyn_eras[-1]["tag"], "HEAD")

    def test_eras_cli_and_privacy_safe_website_export(self) -> None:
        db_path = self.tmp / "site_test.db"
        conn = sqlite3.connect(db_path)
        ensure_telemetry_schema(conn)
        conn.executemany(
            """
            INSERT INTO sessions (
                session_id, start_time, end_time, duration_seconds, total_steps,
                model, workspace_path, transcript_path, has_errors,
                tool_call_count, tool_error_count, intervention_count,
                origin_developer, client_surface, origin_machine
            ) VALUES (?, ?, ?, 300.0, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                ("pre-1", "2026-09-15T10:00:00Z", "2026-09-15T10:05:00Z", 1200, "Gemini 3", "/home/secretuser/Dev/agyis-harness", "/home/secretuser/.gemini/antigravity/conversations/pre.db", 1, 2, 1, 1, "local", "ide", "corp-workstation.internal"),
                ("titan-home", "2026-11-24T09:00:00Z", "2026-11-24T09:10:00Z", 1050, "gemini-4-argon", "/home/secretuser", "/home/secretuser/.gemini/antigravity/conversations/th.db", 0, 1, 0, 0, "local", "ide", "corp-workstation.internal"),
                ("ga-1", "2026-11-24T10:00:00Z", "2026-11-24T10:05:00Z", 100, "gemini-4-hydrogen", "/home/secretuser", "/home/secretuser/.gemini/antigravity-cli/conversations/ga.db", 0, 2, 0, 0, "private_dev_handle", "cli", None),
                ("leg-1", "2026-10-05T10:00:00Z", "2026-10-05T10:05:00Z", 40, "Gemini 3.5/Flash/Pro (Default)", "/tmp/private-client-finops", "/home/secretuser/.gemini/antigravity/conversations/leg.db", 0, 1, 0, 0, os.environ.get("USER", "local"), "ide", "corp-workstation.internal"),
            ],
        )
        conn.execute(
            "INSERT INTO steps (session_id, step_index, step_type, content_length, content_snippet) VALUES ('pre-1', 1, 'RUN_COMMAND', 4096, 'SECRET_CONTENT_SNIPPET_NEVER_EXPORT')"
        )
        conn.execute(
            "INSERT INTO tool_calls (session_id, step_index, tool_name, command_line, status, exit_code, output_length_chars, is_loop_candidate) VALUES ('pre-1', 1, 'run_command', 'curl https://user@example.com --token ghp_1234567890abcdefghijklmnop', 'FAILED', 1, 4096, 1)"
        )
        conn.execute(
            "INSERT INTO tool_calls (session_id, step_index, tool_name, command_line, status, exit_code, output_length_chars, is_loop_candidate) VALUES ('ga-1', 1, 'run_command', 'pytest', 'SUCCESS', 0, 40000, 0)"
        )
        conn.execute(
            "INSERT INTO user_interventions (session_id, step_index, prompt_text, intervention_type) VALUES ('pre-1', 2, 'SECRET_PROMPT_LEAK_TOKEN_ghp_abcdefghijklmnopqrstuv email alice@secret.org /home/kuasha/private', 'STEERING')"
        )
        conn.commit()
        conn.close()

        # Verify eras CLI
        era_json = self.tmp / "era_out.json"
        era_md = self.tmp / "era_out.md"
        with patch("sys.stdout", new_callable=io.StringIO) as out_buf:
            rc_era = cli_main(["audit", "eras", "--db", str(db_path), "--json", "--output-json", str(era_json), "--output-report", str(era_md)])
        self.assertEqual(rc_era, 0)
        era_payload = json.loads(out_buf.getvalue())
        self.assertGreaterEqual(era_payload["summary"]["total_eras"], 2)
        self.assertEqual(era_payload["eras"][0]["era_id"], "0_Pre-Harness")
        self.assertEqual(era_payload["eras"][0]["titan_sessions"], 1)

        # Verify export-site CLI writes 6 clean JSON bundles without leaking secrets/prompts/emails/home paths
        site_out = self.tmp / "website_data"
        with patch("sys.stdout", new_callable=io.StringIO) as site_buf:
            rc_site = cli_main(["audit", "export-site", "--db", str(db_path), "--out", str(site_out), "--json"])
        self.assertEqual(rc_site, 0)
        site_res = json.loads(site_buf.getvalue())
        self.assertEqual(site_res["bundle_count"], 6)

        expected_files = {"manifest.json", "overview.json", "eras.json", "models.json", "fleet_and_team.json", "deep_metrics.json"}
        self.assertEqual({p.name for p in site_out.glob("*.json")}, expected_files)

        for jf in site_out.glob("*.json"):
            raw = jf.read_text(encoding="utf-8")
            for forbidden in (
                "SECRET_PROMPT_LEAK_TOKEN", "SECRET_CONTENT_SNIPPET_NEVER_EXPORT",
                "alice@secret.org", "/home/secretuser",
                "ghp_", "corp-workstation.internal", "private_dev_handle",
                "private-client-finops", "secretuser",
                '"content_snippet"', '"thinking_snippet"', '"arguments_json"', '"arguments_snippet"',
            ):
                self.assertNotIn(forbidden, raw)
            parsed = json.loads(raw)
            self.assertIsInstance(parsed, dict)

        fleet = json.loads((site_out / "fleet_and_team.json").read_text(encoding="utf-8"))
        self.assertEqual(fleet["machine_count"], 1)
        self.assertTrue(all(k.startswith("node-") for k in fleet["machines"]))
        self.assertIn("local", fleet["developers"])
        self.assertTrue(any(k.startswith("contributor-") for k in fleet["developers"]))
        repo_names = {r["repo_name"] for r in fleet["workspaces"]["top_local_repositories"]}
        self.assertIn("agyis-harness", repo_names)
        self.assertIn("[USER_HOME]", repo_names)
        self.assertTrue(any(r.startswith("workspace-") for r in repo_names))

        deep = json.loads((site_out / "deep_metrics.json").read_text(encoding="utf-8"))
        ws_names = [s["workspace_name"] for s in deep["titan_sessions"]["sessions"]]
        self.assertEqual(ws_names[0], "agyis-harness")
        self.assertIn("[USER_HOME]", ws_names)


if __name__ == "__main__":
    unittest.main()
