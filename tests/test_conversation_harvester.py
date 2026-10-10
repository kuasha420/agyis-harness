#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Purrfect Software Limited (PSL)

"""
Hermetic Unit Tests for Conversation Harvester and Reasoning Benchmark Matrix (ADR-030 Ladder 5).

Covers:
- Pure stdlib protobuf decoder (varint, length-delimited, wire types, timestamps).
- Native SQLite conversation DB parsing (trajectory_meta, trajectory_metadata_blob, executor_metadata, steps).
- Extraction of session metadata, steps, tool calls, and user interventions.
- Ingestion into target telemetry.db and idempotency.
- harvest_all_conversations directory discovery.
- Reasoning effort vs accuracy benchmark evaluation matrix (Issue #3).
"""

from __future__ import annotations

import json
from pathlib import Path
import sqlite3
import tempfile
from typing import Any, Dict, List
import unittest

from pipeline import benchmark_reasoning_tiers
from pipeline.harvest_conversations import (
    decode_varint,
    extract_conversation_db,
    harvest_all_conversations,
    harvest_conversation_db,
    parse_proto_timestamp,
    parse_protobuf_fields,
)


def _encode_varint(val: int) -> bytes:
    res = bytearray()
    while val > 0x7F:
        res.append((val & 0x7F) | 0x80)
        val >>= 7
    res.append(val & 0x7F)
    return bytes(res)


def _encode_field(field_num: int, wire_type: int, val: Any) -> bytes:
    tag = (field_num << 3) | wire_type
    res = bytearray(_encode_varint(tag))
    if wire_type == 0:
        res.extend(_encode_varint(int(val)))
    elif wire_type == 1:
        res.extend(val if isinstance(val, bytes) else b"\x00" * 8)
    elif wire_type == 2:
        if isinstance(val, str):
            val = val.encode("utf-8")
        res.extend(_encode_varint(len(val)))
        res.extend(val)
    elif wire_type == 5:
        res.extend(val if isinstance(val, bytes) else b"\x00" * 4)
    return bytes(res)


def _encode_timestamp(epoch_seconds: int) -> bytes:
    return _encode_field(1, 0, epoch_seconds) + _encode_field(2, 0, 0)


class TestProtobufParsing(unittest.TestCase):
    """Verifies low-level protobuf decoding routines."""

    def test_decode_varint(self):
        val, off = decode_varint(b"\x00")
        self.assertEqual(val, 0)
        self.assertEqual(off, 1)

        val, off = decode_varint(b"\x01")
        self.assertEqual(val, 1)

        val, off = decode_varint(b"\xac\x02")  # 300
        self.assertEqual(val, 300)

    def test_parse_protobuf_fields(self):
        # field 1: varint 42
        # field 2: string 'hello'
        data = _encode_field(1, 0, 42) + _encode_field(2, 2, "hello")
        fields = parse_protobuf_fields(data)
        self.assertEqual(len(fields), 2)
        self.assertEqual(fields[0], (1, 0, 42))
        self.assertEqual(fields[1], (2, 2, b"hello"))

    def test_parse_corrupt_protobuf_graceful(self):
        # Truncated data should not throw unhandled exception
        fields = parse_protobuf_fields(b"\xff\xff\xff")
        self.assertIsInstance(fields, list)

    def test_parse_proto_timestamp(self):
        # Valid timestamp: 1720674677 -> 2024-07-11
        ts_bytes = _encode_timestamp(1720674677)
        iso = parse_proto_timestamp(ts_bytes)
        self.assertIsNotNone(iso)
        self.assertTrue(iso.startswith("2024-07-11"))

        # Out-of-range timestamp
        self.assertIsNone(parse_proto_timestamp(_encode_timestamp(0)))
        # Empty/corrupt bytes
        self.assertIsNone(parse_proto_timestamp(b""))


class TestExtractConversationDb(unittest.TestCase):
    """Verifies extraction of native Antigravity conversation DBs."""

    def setUp(self):
        self.tmpdir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.tmpdir.name) / "test_conversation.db"

    def tearDown(self):
        self.tmpdir.cleanup()

    def _create_mock_conversation_db(self):
        conn = sqlite3.connect(self.db_path)
        cur = conn.cursor()
        cur.execute("""
            CREATE TABLE trajectory_meta (
                trajectory_id text,
                cascade_id text,
                trajectory_type integer,
                source integer
            )
        """)
        cur.execute("""
            CREATE TABLE trajectory_metadata_blob (
                id text DEFAULT "main",
                data blob
            )
        """)
        cur.execute("""
            CREATE TABLE executor_metadata (
                idx integer,
                data blob
            )
        """)
        cur.execute("""
            CREATE TABLE steps (
                idx integer PRIMARY KEY,
                step_type integer NOT NULL DEFAULT 0,
                status integer NOT NULL DEFAULT 0,
                has_subtrajectory numeric NOT NULL DEFAULT false,
                metadata blob,
                error_details blob,
                permissions blob,
                task_details blob,
                render_info blob,
                step_payload blob,
                step_format integer NOT NULL DEFAULT 0
            )
        """)

        # Insert trajectory_meta
        cur.execute(
            "INSERT INTO trajectory_meta VALUES ('traj-uuid-1', 'cascade-uuid-1', 4, 1)"
        )

        # Insert trajectory_metadata_blob: field 2 = start_time, field 6 = cascade_id, field 18 = workspace
        meta_blob = (
            _encode_field(2, 2, _encode_timestamp(1720674000))
            + _encode_field(6, 2, "cascade-uuid-1")
            + _encode_field(18, 2, "/home/psl/Dev/my-project")
        )
        cur.execute("INSERT INTO trajectory_metadata_blob VALUES ('main', ?)", (meta_blob,))

        # Insert executor_metadata with model info
        cur.execute(
            "INSERT INTO executor_metadata VALUES (0, ?)",
            (b"gemini-3.8-flash-high enabled with state accumulator",)
        )

        # Step 0: User Input
        # Metadata: field 1 = created_at
        step0_meta = _encode_field(1, 2, _encode_timestamp(1720674000))
        # Payload: field 19 (subfield 2 = text)
        step0_payload_sub = _encode_field(2, 2, "Please inspect the codebase for race conditions")
        step0_payload = _encode_field(19, 2, step0_payload_sub)
        cur.execute(
            "INSERT INTO steps (idx, step_type, status, metadata, step_payload) VALUES (0, 14, 3, ?, ?)",
            (step0_meta, step0_payload),
        )

        # Step 1: Agent Output / Deliberation
        step1_meta = _encode_field(1, 2, _encode_timestamp(1720674005))
        step1_payload_sub = _encode_field(3, 2, "**Analyzing Concurrency Patterns**\nI will scan test files.")
        step1_payload = _encode_field(20, 2, step1_payload_sub)
        cur.execute(
            "INSERT INTO steps (idx, step_type, status, metadata, step_payload) VALUES (1, 15, 3, ?, ?)",
            (step1_meta, step1_payload),
        )

        # Step 2: Successful Tool Call (run_command)
        # Metadata field 4: (1: id, 2: name, 3: args_json)
        tool_call_sub = (
            _encode_field(1, 2, "tool-call-1")
            + _encode_field(2, 2, "run_command")
            + _encode_field(3, 2, json.dumps({"CommandLine": "pytest -v", "Cwd": "/home/psl/Dev/my-project"}))
        )
        step2_meta = (
            _encode_field(1, 2, _encode_timestamp(1720674010))
            + _encode_field(4, 2, tool_call_sub)
            + _encode_field(6, 2, _encode_timestamp(1720674010))
            + _encode_field(8, 2, _encode_timestamp(1720674015))
        )
        # Payload field 28: (6: exit_code 0, 21: output)
        tool_res_sub = _encode_field(6, 0, 0) + _encode_field(21, 2, "================= 5 passed in 0.12s =================")
        step2_payload = _encode_field(28, 2, tool_res_sub)
        cur.execute(
            "INSERT INTO steps (idx, step_type, status, metadata, step_payload) VALUES (2, 21, 3, ?, ?)",
            (step2_meta, step2_payload),
        )

        # Step 3: Failed Tool Call (run_command)
        tool_call_err_sub = (
            _encode_field(1, 2, "tool-call-2")
            + _encode_field(2, 2, "run_command")
            + _encode_field(3, 2, json.dumps({"CommandLine": "git diff --check", "Cwd": "/home/psl/Dev/my-project"}))
        )
        step3_meta = (
            _encode_field(1, 2, _encode_timestamp(1720674020))
            + _encode_field(4, 2, tool_call_err_sub)
            + _encode_field(6, 2, _encode_timestamp(1720674020))
            + _encode_field(8, 2, _encode_timestamp(1720674022))
        )
        step3_payload = _encode_field(28, 2, _encode_field(6, 0, 1))
        cur.execute(
            "INSERT INTO steps (idx, step_type, status, metadata, error_details, step_payload) VALUES (3, 21, 7, ?, ?, ?)",
            (step3_meta, b"exit status 1: whitespace error", step3_payload),
        )

        # Step 4: User Intervention following failed tool
        step4_meta = _encode_field(1, 2, _encode_timestamp(1720674025))
        step4_payload_sub = _encode_field(2, 2, "Please fix the trailing whitespace error")
        step4_payload = _encode_field(19, 2, step4_payload_sub)
        cur.execute(
            "INSERT INTO steps (idx, step_type, status, metadata, step_payload) VALUES (4, 14, 3, ?, ?)",
            (step4_meta, step4_payload),
        )

        conn.commit()
        conn.close()

    def test_extract_nonexistent_returns_none(self):
        self.assertIsNone(extract_conversation_db(Path("/nonexistent/fake.db")))

    def test_extract_mock_conversation(self):
        self._create_mock_conversation_db()
        res = extract_conversation_db(self.db_path)
        self.assertIsNotNone(res)
        session_row, step_rows, tool_rows, interv_rows = res

        # Session verification
        self.assertEqual(session_row["session_id"], "cascade-uuid-1")
        self.assertEqual(session_row["total_steps"], 5)
        self.assertIn("flash", session_row["model"].lower())
        self.assertEqual(session_row["workspace_path"], "/home/psl/Dev/my-project")
        self.assertEqual(session_row["has_errors"], 1)
        self.assertEqual(session_row["tool_call_count"], 2)
        self.assertEqual(session_row["tool_error_count"], 1)
        self.assertEqual(session_row["intervention_count"], 2)

        # Step rows verification
        self.assertEqual(len(step_rows), 5)
        self.assertEqual(step_rows[0]["step_type"], "USER_INPUT")
        self.assertEqual(step_rows[1]["has_thinking"], 1)
        self.assertEqual(step_rows[3]["status"], "ERROR")

        # Tool calls verification
        self.assertEqual(len(tool_rows), 2)
        self.assertEqual(tool_rows[0]["tool_name"], "run_command")
        self.assertEqual(tool_rows[0]["status"], "SUCCESS")
        self.assertEqual(tool_rows[0]["exit_code"], 0)
        self.assertEqual(tool_rows[0]["command_category"], "test_runner")

        self.assertEqual(tool_rows[1]["status"], "FAILED")
        self.assertEqual(tool_rows[1]["exit_code"], 1)
        self.assertIn("whitespace error", tool_rows[1]["error_snippet"])

        # Interventions verification
        self.assertEqual(len(interv_rows), 2)
        # Step 4 intervention occurred after step 3 failed
        self.assertEqual(interv_rows[1]["preceding_tool_failed"], 1)
        self.assertEqual(interv_rows[1]["preceding_tool_name"], "run_command")
        self.assertEqual(interv_rows[1]["intervention_type"], "ERROR_RECOVERY")


class TestHarvestConversationDb(unittest.TestCase):
    """Verifies SQLite ingestion into telemetry.db."""

    def setUp(self):
        self.tmpdir = tempfile.TemporaryDirectory()
        self.conv_dir = Path(self.tmpdir.name) / "conversations"
        self.conv_dir.mkdir()
        self.target_db = Path(self.tmpdir.name) / "telemetry.db"

    def tearDown(self):
        self.tmpdir.cleanup()

    def test_harvest_conversation_db_and_idempotency(self):
        src_db = self.conv_dir / "sess1.db"
        t = TestExtractConversationDb()
        t.tmpdir = self.tmpdir
        t.db_path = src_db
        t._create_mock_conversation_db()

        # Ingest
        res = harvest_conversation_db(src_db, self.target_db)
        self.assertEqual(res["status"], "harvested")
        self.assertEqual(res["session_id"], "cascade-uuid-1")
        self.assertEqual(res["total_steps"], 5)
        self.assertEqual(res["tool_call_count"], 2)

        # Verify target DB contents
        conn = sqlite3.connect(self.target_db)
        cur = conn.cursor()
        cur.execute("SELECT COUNT(*) FROM sessions WHERE session_id = 'cascade-uuid-1'")
        self.assertEqual(cur.fetchone()[0], 1)
        cur.execute("SELECT COUNT(*) FROM steps WHERE session_id = 'cascade-uuid-1'")
        self.assertEqual(cur.fetchone()[0], 5)
        cur.execute("SELECT COUNT(*) FROM tool_calls WHERE session_id = 'cascade-uuid-1'")
        self.assertEqual(cur.fetchone()[0], 2)
        cur.execute("SELECT COUNT(*) FROM user_interventions WHERE session_id = 'cascade-uuid-1'")
        self.assertEqual(cur.fetchone()[0], 2)

        # Idempotence: harvest second time must not duplicate rows
        harvest_conversation_db(src_db, self.target_db)
        cur.execute("SELECT COUNT(*) FROM steps WHERE session_id = 'cascade-uuid-1'")
        self.assertEqual(cur.fetchone()[0], 5)
        cur.execute("SELECT COUNT(*) FROM tool_calls WHERE session_id = 'cascade-uuid-1'")
        self.assertEqual(cur.fetchone()[0], 2)
        conn.close()

    def test_harvest_all_conversations(self):
        # Create two conversation DBs
        for name in ["sess_a.db", "sess_b.db"]:
            p = self.conv_dir / name
            t = TestExtractConversationDb()
            t.tmpdir = self.tmpdir
            t.db_path = p
            t._create_mock_conversation_db()

        count = harvest_all_conversations(self.conv_dir, self.target_db)
        self.assertEqual(count, 2)

        conn = sqlite3.connect(self.target_db)
        cur = conn.cursor()
        cur.execute("SELECT COUNT(*) FROM sessions")
        self.assertGreaterEqual(cur.fetchone()[0], 1)
        conn.close()


class TestReasoningTierBenchmark(unittest.TestCase):
    """Verifies automated reasoning effort vs accuracy benchmark matrix (Issue #3)."""

    def setUp(self):
        self.tmpdir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.tmpdir.name) / "telemetry.db"
        self.json_out = Path(self.tmpdir.name) / "benchmark.json"
        self.report_out = Path(self.tmpdir.name) / "benchmark.md"

    def tearDown(self):
        self.tmpdir.cleanup()

    def test_classify_session_tier(self):
        self.assertEqual(
            benchmark_reasoning_tiers.classify_session_tier("gemini-3.8-flash-low", False, 0),
            "gemini-3.8-flash-low",
        )
        self.assertEqual(
            benchmark_reasoning_tiers.classify_session_tier("gemini-3.8-flash-high", True, 2000),
            "gemini-3.8-flash-high",
        )
        self.assertEqual(
            benchmark_reasoning_tiers.classify_session_tier("gemini-3.1-pro", True, 4000),
            "gemini-3.1-pro",
        )

    def test_evaluate_reasoning_tiers_matrix(self):
        res = benchmark_reasoning_tiers.evaluate_reasoning_tiers(
            db_path=self.db_path,
            output_json=self.json_out,
            output_report=self.report_out,
        )

        self.assertIn("tiers", res)
        self.assertIn("gemini-3.8-flash-low", res["tiers"])
        self.assertIn("gemini-3.8-flash-high", res["tiers"])
        self.assertIn("gemini-3.1-pro", res["tiers"])

        # Check metrics computed
        for tier_id in ["gemini-3.8-flash-low", "gemini-3.8-flash-high", "gemini-3.1-pro"]:
            t = res["tiers"][tier_id]
            self.assertIn("accuracy_percent", t)
            self.assertIn("average_steps", t)
            self.assertIn("average_thinking_tokens", t)
            self.assertIn("average_wall_clock_seconds", t)
            self.assertGreater(t["accuracy_percent"], 0)
            self.assertGreater(t["average_wall_clock_seconds"], 0)

        # Check output files written
        self.assertTrue(self.json_out.is_file())
        self.assertTrue(self.report_out.is_file())

        with open(self.json_out, "r", encoding="utf-8") as f:
            saved_json = json.load(f)
            self.assertIn("tiers", saved_json)

        with open(self.report_out, "r", encoding="utf-8") as f:
            report_text = f.read()
            self.assertIn("Reasoning Effort vs. Accuracy Benchmark Matrix", report_text)
            self.assertIn("gemini-3.8-flash-low", report_text)
            self.assertIn("gemini-3.8-flash-high", report_text)
            self.assertIn("gemini-3.1-pro", report_text)


if __name__ == "__main__":
    unittest.main()
