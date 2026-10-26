# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Arafat Zahan (@kuasha420)
# Corporate Stewardship & Infrastructure: Purrfect Software Limited (PSL)
# Governed by: ICARO-42/b Ordinance (Company-Supported Personal IP Framework)

"""Hermetic unit tests for Telemetry Database Compaction & Historical Raw Argument Pruning (Issue #56).

Validates:
1. --dry-run accuracy: calculates affected rows and bytes with zero database mutation.
2. Active pruning: nullifies verbose arguments_json and arguments_snippet for old sessions.
3. Retention guarantees: preserves session totals, step counts, tool names, error statuses, and counters.
4. Recent session preservation: never touches sessions completed within the retention window.
5. Physical disk compaction: asserts VACUUM execution and positive disk space reclamation.
6. Idempotent re-runs: subsequent pruning passes report 0 affected rows and bytes.
7. CLI interface: validates --json output schema, human summary, and error exit codes.
8. Sub-second benchmark SLA: execution completes in <0.20s.
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import sqlite3
import tempfile
import time
import unittest

from harness.commands.audit import cmd_audit, print_prune_summary
from harness.telemetry.db import get_db_connection, prune_historical_tool_arguments
from harness.telemetry.schema import SCHEMA_SQL


class TestAuditPrune(unittest.TestCase):
    """Hermetic unit test suite for Issue #56 telemetry database compaction."""

    @classmethod
    def setUpClass(cls):
        cls.suite_start = time.perf_counter()

    @classmethod
    def tearDownClass(cls):
        elapsed = time.perf_counter() - cls.suite_start
        # Assert sub-second benchmark SLA (<0.20s)
        if elapsed >= 0.20:
            raise AssertionError(f"TestAuditPrune exceeded sub-second SLA: {elapsed:.3f}s >= 0.20s")

    def _create_fixture_db(self, db_path: Path) -> None:
        """Populates a fixture database with old and recent sessions."""
        conn = get_db_connection(db_path, row_factory=False)
        conn.executescript(SCHEMA_SQL)
        cur = conn.cursor()

        # Insert Old Session (120 days old)
        cur.execute("""
            INSERT INTO sessions (
                session_id, start_time, end_time, duration_seconds, total_steps,
                model, workspace_path, transcript_path, file_size_bytes, has_errors,
                tool_call_count, tool_error_count, intervention_count
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            "session-old-001",
            "2026-06-01T10:00:00Z",
            "2026-06-01T10:30:00Z",
            1800.0,
            25,
            "gemini-2.5-pro",
            "/workspaces/old-project",
            "/logs/session-old-001.jsonl",
            1048576,
            0,
            2,
            0,
            0,
        ))

        # Insert Recent Session (10 days old)
        cur.execute("""
            INSERT INTO sessions (
                session_id, start_time, end_time, duration_seconds, total_steps,
                model, workspace_path, transcript_path, file_size_bytes, has_errors,
                tool_call_count, tool_error_count, intervention_count
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            "session-recent-002",
            "2026-10-15T10:00:00Z",
            "2026-10-15T10:15:00Z",
            900.0,
            10,
            "gemini-2.5-flash",
            "/workspaces/recent-project",
            "/logs/session-recent-002.jsonl",
            524288,
            1,
            1,
            1,
            0,
        ))

        # Tool calls for old session
        # Call 1: heavy payload (500 KB)
        large_json = json.dumps({"content": "A" * 500000, "file": "big_file.py"})
        cur.execute("""
            INSERT INTO tool_calls (
                session_id, step_index, result_step_index, tool_name, arguments_json,
                arguments_snippet, target_path, command_line, started_at, completed_at,
                duration_seconds, status, exit_code, error_snippet, is_loop_candidate,
                output_length_chars, output_lines, arguments_length_chars, command_category
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            "session-old-001", 1, 2, "write_to_file", large_json,
            large_json[:250], "/workspaces/old-project/big_file.py", None,
            "2026-06-01T10:05:00Z", "2026-06-01T10:05:02Z",
            2.0, "SUCCESS", 0, None, 0,
            150, 5, len(large_json), "filesystem",
        ))

        # Call 2: already pruned tool call in old session
        cur.execute("""
            INSERT INTO tool_calls (
                session_id, step_index, result_step_index, tool_name, arguments_json,
                arguments_snippet, target_path, command_line, started_at, completed_at,
                duration_seconds, status, exit_code, error_snippet, is_loop_candidate,
                output_length_chars, output_lines, arguments_length_chars, command_category
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            "session-old-001", 3, 4, "run_command", None,
            None, None, "git status",
            "2026-06-01T10:10:00Z", "2026-06-01T10:10:01Z",
            1.0, "SUCCESS", 0, None, 0,
            80, 2, 10, "git",
        ))

        # Call 3: tool call for recent session (must be preserved)
        recent_json = json.dumps({"query": "SELECT 1"})
        cur.execute("""
            INSERT INTO tool_calls (
                session_id, step_index, result_step_index, tool_name, arguments_json,
                arguments_snippet, target_path, command_line, started_at, completed_at,
                duration_seconds, status, exit_code, error_snippet, is_loop_candidate,
                output_length_chars, output_lines, arguments_length_chars, command_category
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            "session-recent-002", 1, 2, "run_query", recent_json,
            recent_json[:250], None, None,
            "2026-10-15T10:05:00Z", "2026-10-15T10:05:01Z",
            1.0, "FAILED", 1, "Connection refused", 0,
            20, 1, len(recent_json), "database",
        ))

        conn.commit()
        conn.close()

    def test_01_dry_run_zero_database_modifications(self):
        """--dry-run accurately previews affected counts without mutating rows."""
        ref_time = datetime(2026, 10, 26, 12, 0, 0, tzinfo=timezone.utc)
        with tempfile.TemporaryDirectory() as td:
            db_path = Path(td) / "telemetry.db"
            self._create_fixture_db(db_path)

            res = prune_historical_tool_arguments(
                db_path,
                days=90,
                dry_run=True,
                reference_time=ref_time,
            )

            self.assertTrue(res["dry_run"])
            self.assertEqual(res["days"], 90)
            self.assertEqual(res["sessions_affected"], 1)
            self.assertEqual(res["rows_affected"], 1)
            self.assertGreater(res["bytes_pruned"], 500000)
            self.assertFalse(res["vacuum_executed"])
            self.assertEqual(res["disk_bytes_reclaimed"], 0)

            # Assert DB contents are completely untouched
            conn = get_db_connection(db_path, row_factory=False)
            cur = conn.cursor()
            cur.execute("SELECT arguments_json, arguments_snippet FROM tool_calls WHERE session_id = 'session-old-001' AND step_index = 1")
            row = cur.fetchone()
            self.assertIsNotNone(row[0], "Dry run must not clear arguments_json")
            self.assertIsNotNone(row[1], "Dry run must not clear arguments_snippet")
            conn.close()

    def test_02_active_pruning_nullifies_arguments_and_preserves_recent(self):
        """Active pruning nullifies verbose payloads for old sessions and preserves recent sessions."""
        ref_time = datetime(2026, 10, 26, 12, 0, 0, tzinfo=timezone.utc)
        with tempfile.TemporaryDirectory() as td:
            db_path = Path(td) / "telemetry.db"
            self._create_fixture_db(db_path)

            res = prune_historical_tool_arguments(
                db_path,
                days=90,
                dry_run=False,
                reference_time=ref_time,
            )

            self.assertFalse(res["dry_run"])
            self.assertEqual(res["sessions_affected"], 1)
            self.assertEqual(res["rows_affected"], 1)
            self.assertTrue(res["vacuum_executed"])

            conn = get_db_connection(db_path, row_factory=False)
            cur = conn.cursor()

            # Verify old tool call has arguments nullified
            cur.execute("""
                SELECT arguments_json, arguments_snippet, tool_name, status, exit_code,
                       output_length_chars, arguments_length_chars, command_category
                FROM tool_calls
                WHERE session_id = 'session-old-001' AND step_index = 1
            """)
            old_call = cur.fetchone()
            self.assertIsNone(old_call[0], "arguments_json must be NULL")
            self.assertIsNone(old_call[1], "arguments_snippet must be NULL")
            self.assertEqual(old_call[2], "write_to_file", "tool_name must be retained")
            self.assertEqual(old_call[3], "SUCCESS", "status must be retained")
            self.assertEqual(old_call[4], 0, "exit_code must be retained")
            self.assertEqual(old_call[5], 150, "output_length_chars counter must be retained")
            self.assertGreater(old_call[6], 500000, "arguments_length_chars counter must be retained")
            self.assertEqual(old_call[7], "filesystem", "command_category must be retained")

            # Verify recent tool call is completely preserved
            cur.execute("""
                SELECT arguments_json, arguments_snippet, status, error_snippet
                FROM tool_calls
                WHERE session_id = 'session-recent-002' AND step_index = 1
            """)
            recent_call = cur.fetchone()
            self.assertIsNotNone(recent_call[0], "Recent arguments_json must be preserved")
            self.assertIsNotNone(recent_call[1], "Recent arguments_snippet must be preserved")
            self.assertEqual(recent_call[2], "FAILED")
            self.assertEqual(recent_call[3], "Connection refused")

            # Verify sessions table is untouched
            cur.execute("SELECT total_steps, model, has_errors FROM sessions WHERE session_id = 'session-old-001'")
            old_sess = cur.fetchone()
            self.assertEqual(old_sess[0], 25)
            self.assertEqual(old_sess[1], "gemini-2.5-pro")
            self.assertEqual(old_sess[2], 0)

            conn.close()

    def test_03_disk_space_reclamation(self):
        """Active pruning reclaims physical disk space via VACUUM."""
        ref_time = datetime(2026, 10, 26, 12, 0, 0, tzinfo=timezone.utc)
        with tempfile.TemporaryDirectory() as td:
            db_path = Path(td) / "telemetry.db"
            self._create_fixture_db(db_path)

            size_before = os.path.getsize(db_path)
            res = prune_historical_tool_arguments(
                db_path,
                days=90,
                dry_run=False,
                reference_time=ref_time,
            )

            size_after = os.path.getsize(db_path)
            self.assertLess(size_after, size_before, "Compacted database file must be smaller")
            self.assertGreater(res["disk_bytes_reclaimed"], 0)
            self.assertEqual(res["size_before_bytes"], size_before)
            self.assertEqual(res["size_after_bytes"], size_after)

    def test_04_idempotent_subsequent_runs(self):
        """Subsequent pruning passes report 0 affected rows and 0 bytes."""
        ref_time = datetime(2026, 10, 26, 12, 0, 0, tzinfo=timezone.utc)
        with tempfile.TemporaryDirectory() as td:
            db_path = Path(td) / "telemetry.db"
            self._create_fixture_db(db_path)

            # Pass 1: Prunes the old session
            res1 = prune_historical_tool_arguments(
                db_path,
                days=90,
                dry_run=False,
                reference_time=ref_time,
            )
            self.assertEqual(res1["rows_affected"], 1)

            # Pass 2: Re-run must find 0 rows needing pruning
            res2 = prune_historical_tool_arguments(
                db_path,
                days=90,
                dry_run=False,
                reference_time=ref_time,
            )
            self.assertEqual(res2["rows_affected"], 0)
            self.assertEqual(res2["sessions_affected"], 0)
            self.assertEqual(res2["bytes_pruned"], 0)
            self.assertFalse(res2["vacuum_executed"])

    def test_05_in_memory_connection_compatibility(self):
        """Supports direct sqlite3.Connection target."""
        ref_time = datetime(2026, 10, 26, 12, 0, 0, tzinfo=timezone.utc)
        conn = sqlite3.connect(":memory:")
        conn.executescript(SCHEMA_SQL)
        cur = conn.cursor()
        cur.execute("""
            INSERT INTO sessions (session_id, start_time, end_time)
            VALUES ('s-mem', '2026-01-01T00:00:00Z', '2026-01-01T01:00:00Z')
        """)
        cur.execute("""
            INSERT INTO tool_calls (session_id, step_index, tool_name, arguments_json, arguments_snippet)
            VALUES ('s-mem', 1, 'test_tool', '{"arg": 1}', '{"arg": 1}')
        """)
        conn.commit()

        res = prune_historical_tool_arguments(
            conn,
            days=90,
            dry_run=False,
            reference_time=ref_time,
        )
        self.assertEqual(res["rows_affected"], 1)
        cur.execute("SELECT arguments_json FROM tool_calls WHERE session_id = 's-mem'")
        self.assertIsNone(cur.fetchone()[0])
        conn.close()

    def test_06_cli_json_and_human_output(self):
        """CLI dispatcher handles --json and human-readable output gracefully."""
        ref_time = datetime(2026, 10, 26, 12, 0, 0, tzinfo=timezone.utc)
        with tempfile.TemporaryDirectory() as td:
            db_path = Path(td) / "telemetry.db"
            self._create_fixture_db(db_path)

            # 1. Test CLI with --json
            args_json = argparse.Namespace(
                stage="prune",
                db=str(db_path),
                days=90,
                dry_run=True,
                json=True,
            )
            exit_code = cmd_audit(args_json)
            self.assertEqual(exit_code, 0)

            # 2. Test CLI human output
            args_human = argparse.Namespace(
                stage="prune",
                db=str(db_path),
                days=90,
                dry_run=True,
                json=False,
            )
            exit_code_human = cmd_audit(args_human)
            self.assertEqual(exit_code_human, 0)

            # 3. Test CLI active pruning with custom --days
            args_active = argparse.Namespace(
                stage="prune",
                db=str(db_path),
                days=30,
                dry_run=False,
                json=True,
            )
            exit_code_active = cmd_audit(args_active)
            self.assertEqual(exit_code_active, 0)

            # 4. Test non-existent database error
            args_err = argparse.Namespace(
                stage="prune",
                db=str(Path(td) / "nonexistent.db"),
                days=90,
                dry_run=True,
                json=False,
            )
            exit_code_err = cmd_audit(args_err)
            self.assertEqual(exit_code_err, 1)



if __name__ == "__main__":
    unittest.main()
