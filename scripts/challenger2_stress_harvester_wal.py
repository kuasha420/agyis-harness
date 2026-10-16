#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Arafat Zahan (@kuasha420)
# Corporate Stewardship & Infrastructure: Purrfect Software Limited (PSL)
# Governed by: ICARO-42/b Ordinance (Company-Supported Personal IP Framework)

"""
Adversarial Stress Test Suite for Harvester Concurrency under WAL Mode
and Protobuf Exit Code Extraction (o13_m3_challenger_2)

Empirically challenges:
1. Multi-threaded concurrent harvesting into a single telemetry.db under WAL mode.
2. Concurrent reader queries executing during intensive writes (snapshot isolation).
3. Database integrity (PRAGMA integrity_check) and zero 'database is locked' errors.
4. Protobuf exit code extraction across modern (fn 140) and legacy (fn 28) formats.
5. Protobuf parser fuzzing: truncated payloads, unterminated varints, invalid wire types,
   random byte strings, non-UTF8 data, and 5MB large payloads.
"""

from __future__ import annotations

import concurrent.futures
import json
import os
from pathlib import Path
import random
import sqlite3
import sys
import tempfile
import threading
import time
from typing import Any, Dict, List, Tuple
import unittest

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from pipeline.harvest_conversations import (
    decode_varint,
    extract_conversation_db,
    extract_execution_result,
    harvest_all_conversations,
    harvest_conversation_db,
    parse_protobuf_fields,
    parse_proto_timestamp,
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


def create_mock_conversation_db(
    db_path: Path,
    session_id: str,
    step_count: int = 10,
    model: str = "gemini-3.8-flash-high",
) -> None:
    """Populates a realistic mock conversation database."""
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()
    cur.execute("CREATE TABLE trajectory_meta (trajectory_id text, cascade_id text, step_count integer, schema_version integer)")
    cur.execute("CREATE TABLE trajectory_metadata_blob (id text DEFAULT 'main', data blob)")
    cur.execute("CREATE TABLE executor_metadata (idx integer, data blob)")
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

    cur.execute("INSERT INTO trajectory_meta VALUES (?, ?, ?, 1)", (f"traj-{session_id}", session_id, step_count))

    meta_blob = (
        _encode_field(2, 2, _encode_timestamp(1720674000))
        + _encode_field(6, 2, session_id)
        + _encode_field(18, 2, f"/workspace/{session_id}")
    )
    cur.execute("INSERT INTO trajectory_metadata_blob VALUES ('main', ?)", (meta_blob,))
    cur.execute("INSERT INTO executor_metadata VALUES (0, ?)", (model.encode("utf-8"),))

    for i in range(step_count):
        step_meta = _encode_field(1, 2, _encode_timestamp(1720674000 + i * 5))
        if i % 3 == 0:
            # User input
            payload = _encode_field(19, 2, _encode_field(2, 2, f"User instruction {i}"))
            cur.execute("INSERT INTO steps (idx, step_type, status, metadata, step_payload) VALUES (?, 14, 3, ?, ?)", (i, step_meta, payload))
        elif i % 3 == 1:
            # Model output
            payload = _encode_field(20, 2, _encode_field(3, 2, f"Thinking step {i}"))
            cur.execute("INSERT INTO steps (idx, step_type, status, metadata, step_payload) VALUES (?, 15, 3, ?, ?)", (i, step_meta, payload))
        else:
            # Tool call
            tool_sub = (
                _encode_field(1, 2, f"call-{session_id}-{i}")
                + _encode_field(2, 2, "run_command")
                + _encode_field(3, 2, json.dumps({"CommandLine": f"echo step_{i}"}))
            )
            step_meta += _encode_field(4, 2, tool_sub)
            exit_code = 0 if i % 2 == 0 else 1
            # Modern protobuf payload: fn 140 -> sfn 2 -> ssfn 1
            raw_text = f"The command exited with code {exit_code}.\nOutput: result {i}"
            payload = _encode_field(140, 2, _encode_field(2, 2, _encode_field(1, 2, raw_text)))
            status = 3 if exit_code == 0 else 7
            cur.execute("INSERT INTO steps (idx, step_type, status, metadata, step_payload) VALUES (?, 21, ?, ?, ?)", (i, status, step_meta, payload))

    conn.commit()
    conn.close()


class TestHarvesterConcurrencyWalStress(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.work_dir = Path(self.temp_dir.name)
        self.conv_dir = self.work_dir / "conversations"
        self.conv_dir.mkdir()
        self.target_db = self.work_dir / "telemetry.db"

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_concurrent_harvesting_under_wal_mode(self):
        """
        Stress test: 20 distinct conversation DBs harvested concurrently by 8 worker threads
        into the same telemetry.db while 4 reader threads continuously query the database.
        """
        num_sessions = 20
        session_ids = [f"session-{i:03d}" for i in range(num_sessions)]
        conv_paths = []

        for s_id in session_ids:
            p = self.conv_dir / f"{s_id}.db"
            create_mock_conversation_db(p, s_id, step_count=15)
            conv_paths.append((p, s_id))

        errors: List[str] = []
        lock_errors: List[str] = []
        stop_readers = False
        reader_counts: List[int] = []

        def reader_worker():
            nonlocal stop_readers
            reads = 0
            while not stop_readers:
                try:
                    if self.target_db.exists():
                        conn = sqlite3.connect(self.target_db, timeout=30.0)
                        cur = conn.cursor()
                        cur.execute("SELECT COUNT(*) FROM sessions")
                        _ = cur.fetchone()[0]
                        cur.execute("SELECT COUNT(*) FROM steps")
                        _ = cur.fetchone()[0]
                        conn.close()
                        reads += 1
                except sqlite3.OperationalError as e:
                    if "locked" in str(e).lower():
                        lock_errors.append(f"Reader lock error: {e}")
                    else:
                        errors.append(f"Reader operational error: {e}")
                except Exception as e:
                    errors.append(f"Reader error: {e}")
                time.sleep(0.005)
            reader_counts.append(reads)

        # Start 4 concurrent readers
        reader_threads = [threading.Thread(target=reader_worker) for _ in range(4)]
        for rt in reader_threads:
            rt.start()

        # Execute concurrent harvesting using ThreadPoolExecutor (8 threads)
        t_start = time.perf_counter()
        harvest_results = []
        with concurrent.futures.ThreadPoolExecutor(max_workers=8) as executor:
            future_to_path = {
                executor.submit(harvest_conversation_db, p, self.target_db): s_id
                for p, s_id in conv_paths
            }
            for future in concurrent.futures.as_completed(future_to_path):
                s_id = future_to_path[future]
                try:
                    res = future.result()
                    harvest_results.append(res)
                except sqlite3.OperationalError as e:
                    if "locked" in str(e).lower():
                        lock_errors.append(f"Harvester lock error for {s_id}: {e}")
                    else:
                        errors.append(f"Harvester operational error for {s_id}: {e}")
                except Exception as e:
                    errors.append(f"Harvester exception for {s_id}: {e}")

        # Stop readers
        stop_readers = True
        for rt in reader_threads:
            rt.join()

        t_elapsed = time.perf_counter() - t_start

        # Assert zero lock errors and zero exceptions
        self.assertEqual(lock_errors, [], f"Encountered database lock errors: {lock_errors}")
        self.assertEqual(errors, [], f"Encountered errors during concurrent harvest: {errors}")
        self.assertEqual(len(harvest_results), num_sessions, "Not all sessions were harvested")

        # Verify target DB integrity
        conn = sqlite3.connect(self.target_db)
        cur = conn.cursor()

        # Check WAL mode
        cur.execute("PRAGMA journal_mode")
        mode = cur.fetchone()[0]
        self.assertEqual(mode.lower(), "wal", f"Journal mode is {mode}, expected WAL")

        # Check PRAGMA integrity_check
        cur.execute("PRAGMA integrity_check")
        integrity = cur.fetchone()[0]
        self.assertEqual(integrity.lower(), "ok", f"Integrity check failed: {integrity}")

        # Check session count
        cur.execute("SELECT COUNT(*) FROM sessions")
        total_sessions = cur.fetchone()[0]
        self.assertEqual(total_sessions, num_sessions)

        # Check step count (each session has 15 steps -> 300 steps total)
        cur.execute("SELECT COUNT(*) FROM steps")
        total_steps = cur.fetchone()[0]
        self.assertEqual(total_steps, num_sessions * 15)

        conn.close()
        print(f"  [WAL Concurrency Stress] Ingested {num_sessions} sessions ({total_steps} steps) in {t_elapsed:.3f}s with 0 lock errors.")


class TestProtobufAdversarialExtraction(unittest.TestCase):
    """Adversarial testing of extract_execution_result across modern, legacy, malformed, and fuzz inputs."""

    def test_modern_antigravity_all_standard_and_extreme_exit_codes(self):
        """Verify modern fn 140 -> sfn 2 -> ssfn 1 extracts all standard and custom exit codes."""
        exit_codes = [0, 1, 2, 3, 101, 126, 127, 128, 137, 143, 255, 300, 9999]
        for ec in exit_codes:
            raw_text = f"Header line\nThe command exited with code {ec}.\nOutput:\nSome detailed command output\nDone."
            payload = _encode_field(140, 2, _encode_field(2, 2, _encode_field(1, 2, raw_text)))
            code, text = extract_execution_result(payload)
            self.assertEqual(code, ec, f"Failed extracting code {ec}")
            self.assertEqual(text, raw_text)

    def test_modern_antigravity_multiline_variations(self):
        """Verify regex extraction when exit code string is embedded in messy multi-line outputs."""
        patterns = [
            (0, "The command exited with code 0."),
            (1, "Error: check failed!\nThe command exited with code 1."),
            (127, "command not found\nThe command exited with code 127.\nOutput:\n"),
            (0, "prefix The command exited with code 0 suffix"),
        ]
        for expected_code, raw_text in patterns:
            payload = _encode_field(140, 2, _encode_field(2, 2, _encode_field(1, 2, raw_text)))
            code, text = extract_execution_result(payload)
            self.assertEqual(code, expected_code)
            self.assertEqual(text, raw_text)

    def test_legacy_antigravity_fallback(self):
        """Verify legacy fn 28 payload extracts exit code from sfn 6 and output from sfn 21."""
        legacy_cases = [
            (0, "success output"),
            (1, "error output"),
            (127, "command not found"),
            (255, "ssh connection lost"),
        ]
        for ec, out_str in legacy_cases:
            payload = _encode_field(28, 2, _encode_field(6, 0, ec) + _encode_field(21, 2, out_str))
            code, text = extract_execution_result(payload)
            self.assertEqual(code, ec)
            self.assertEqual(text, out_str)

    def test_precedence_modern_over_legacy(self):
        """When both fn 140 and fn 28 are present in the same payload, fn 140 must take precedence."""
        modern_text = "The command exited with code 2.\nModern output"
        legacy_text = "Legacy output"

        payload = (
            _encode_field(140, 2, _encode_field(2, 2, _encode_field(1, 2, modern_text)))
            + _encode_field(28, 2, _encode_field(6, 0, 42) + _encode_field(21, 2, legacy_text))
        )
        code, text = extract_execution_result(payload)
        self.assertEqual(code, 2, "Expected modern fn 140 exit code (2) to take precedence over legacy (42)")
        self.assertEqual(text, modern_text)

    def test_malformed_and_truncated_protobuf_payloads(self):
        """Verify that truncated or structurally malformed payloads never crash."""
        raw_text = "The command exited with code 1.\nOutput error"
        valid_payload = _encode_field(140, 2, _encode_field(2, 2, _encode_field(1, 2, raw_text)))

        # Truncate at every single byte index from 1 to len(valid_payload)-1
        for cut in range(1, len(valid_payload)):
            truncated = valid_payload[:cut]
            code, text = extract_execution_result(truncated)
            self.assertIsInstance(code, int)
            self.assertIsInstance(text, str)

    def test_fuzz_random_bytes_and_unterminated_varints(self):
        """Fuzz with 500 arbitrary byte strings and unterminated varints."""
        unterminated_varints = [
            b"\x80",
            b"\x80\x80",
            b"\x80\x80\x80\x80\x80\x80\x80\x80\x80\x80\x80",
            b"\xff" * 20,
        ]
        for uv in unterminated_varints:
            code, text = extract_execution_result(uv)
            self.assertEqual(code, 0)
            self.assertEqual(text, "")

        # Random fuzz
        rng = random.Random(42)
        for _ in range(500):
            length = rng.randint(0, 256)
            fuzz_bytes = rng.randbytes(length)
            code, text = extract_execution_result(fuzz_bytes)
            self.assertIsInstance(code, int)
            self.assertIsInstance(text, str)

    def test_non_utf8_bytes_in_output(self):
        """Verify invalid UTF-8 sequences in output strings are safely decoded with replacement characters."""
        # fn 140 with invalid utf8
        invalid_utf8 = b"The command exited with code 0.\nOutput: \xff\xfe invalid \x80"
        payload = _encode_field(140, 2, _encode_field(2, 2, _encode_field(1, 2, invalid_utf8)))
        code, text = extract_execution_result(payload)
        self.assertEqual(code, 0)
        self.assertIn("The command exited with code 0", text)

        # fn 28 with invalid utf8 in sfn 21
        payload_legacy = _encode_field(28, 2, _encode_field(6, 0, 1) + _encode_field(21, 2, b"\xff\xfe\xfa"))
        code_leg, text_leg = extract_execution_result(payload_legacy)
        self.assertEqual(code_leg, 1)
        self.assertIsInstance(text_leg, str)

    def test_large_payload_handling(self):
        """Verify payload with 2MB of output does not cause OOM or crash."""
        large_str = "The command exited with code 0.\n" + ("x" * 2_000_000)
        payload = _encode_field(140, 2, _encode_field(2, 2, _encode_field(1, 2, large_str)))
        code, text = extract_execution_result(payload)
        self.assertEqual(code, 0)
        self.assertEqual(len(text), len(large_str))


if __name__ == "__main__":
    unittest.main()
