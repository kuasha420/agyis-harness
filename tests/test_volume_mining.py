#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Arafat Zahan (@kuasha420)
# Corporate Stewardship & Infrastructure: Purrfect Software Limited (PSL)
# Governed by: ICARO-42/b Ordinance (Company-Supported Personal IP Framework)

"""
Unit and contract tests for Telemetry Volume Mining and Character Analysis.
Verifies command categorization, schema migration, backfill idempotency,
and failure preservation invariants under sub-second execution (<1.0s).
"""

import io
import json
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import patch

from harness.cli import main as cli_main
from pipeline.analyze_volume_distributions import (
    analyze_volumes,
    calculate_percentiles,
    estimate_tokens,
    generate_markdown_report,
)
from pipeline.extract_transcripts import (
    SCHEMA_SQL,
    backfill_tool_volumes,
    classify_command,
    ensure_volume_columns,
)


class TestVolumeMining(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.dir_path = Path(self.temp_dir.name)
        self.db_path = self.dir_path / "test_telemetry.db"

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_classify_command(self):
        """Verifies operational classification of developer shell commands."""
        # Test runners
        self.assertEqual(classify_command("pytest -v tests/"), "test_runner")
        self.assertEqual(classify_command("python3 -m unittest discover"), "test_runner")
        self.assertEqual(classify_command("pnpm test"), "test_runner")
        self.assertEqual(classify_command("cargo test --all"), "test_runner")

        # Git
        self.assertEqual(classify_command("git status -s"), "git")
        self.assertEqual(classify_command("gh pr view 42"), "git")

        # Search & probes
        self.assertEqual(classify_command("grep -rn 'PATTERN' ."), "grep_search")
        self.assertEqual(classify_command("rg 'needle' src/"), "grep_search")
        self.assertEqual(classify_command("fd -e py"), "file_search")
        self.assertEqual(classify_command("ls -la /tmp"), "file_search")

        # Package managers & build
        self.assertEqual(classify_command("pnpm install"), "package_manager")
        self.assertEqual(classify_command("pip install uv"), "package_manager")
        self.assertEqual(classify_command("cargo build --release"), "build_compile")
        self.assertEqual(classify_command("tsc -p tsconfig.json"), "build_compile")

        # Python execution
        self.assertEqual(classify_command("python3 -c 'print(1)'"), "python_exec")

        # System & network
        self.assertEqual(classify_command("which python3"), "system_probe")
        self.assertEqual(classify_command("curl -s https://example.com"), "network")
        self.assertEqual(classify_command("cat file.txt"), "file_system")

        # Edge cases
        self.assertIsNone(classify_command(None))
        self.assertIsNone(classify_command(""))
        self.assertEqual(classify_command("custom_unknown_binary arg1"), "other")

    def test_ensure_volume_columns_idempotent(self):
        """Verifies schema migration safely adds new columns and is strictly idempotent."""
        conn = sqlite3.connect(self.db_path)
        cur = conn.cursor()

        # Create older schema without volume columns
        cur.execute("""
            CREATE TABLE tool_calls (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id TEXT,
                step_index INTEGER,
                tool_name TEXT,
                command_line TEXT,
                status TEXT
            )
        """)
        conn.commit()

        # First call adds columns
        ensure_volume_columns(conn)
        cur.execute("PRAGMA table_info(tool_calls)")
        cols_after_first = {row[1] for row in cur.fetchall()}
        self.assertIn("output_length_chars", cols_after_first)
        self.assertIn("output_lines", cols_after_first)
        self.assertIn("arguments_length_chars", cols_after_first)
        self.assertIn("command_category", cols_after_first)
        self.assertIn("is_truncated", cols_after_first)

        # Second call does not error (idempotent)
        ensure_volume_columns(conn)
        cur.execute("PRAGMA table_info(tool_calls)")
        cols_after_second = {row[1] for row in cur.fetchall()}
        self.assertEqual(cols_after_first, cols_after_second)
        conn.close()

    def test_calculate_percentiles_and_tokens(self):
        """Verifies statistical helper calculations."""
        self.assertEqual(estimate_tokens(400), 100)
        self.assertEqual(estimate_tokens(0), 0)

        # Empty list
        p_empty = calculate_percentiles([], [0.5, 0.9])
        self.assertEqual(p_empty["p50"], 0)
        self.assertEqual(p_empty["p90"], 0)

        # Sorted range 1..100
        vals = list(range(1, 101))
        pcts = calculate_percentiles(vals, [0.5, 0.9, 0.99])
        self.assertEqual(pcts["p50"], 50)
        self.assertEqual(pcts["p90"], 90)
        self.assertEqual(pcts["p99"], 99)

    def test_backfill_and_volume_analysis_pipeline(self):
        """Tests the full extraction, backfill, analysis, and compactor simulation loop."""
        conn = sqlite3.connect(self.db_path)
        cur = conn.cursor()
        cur.executescript(SCHEMA_SQL)
        ensure_volume_columns(conn)

        # Create dummy transcript file
        session_id = "test-session-001"
        transcript_dir = self.dir_path / "brain" / session_id / ".system_generated" / "logs"
        transcript_dir.mkdir(parents=True, exist_ok=True)
        transcript_file = transcript_dir / "transcript.jsonl"

        # Write simulated transcript lines:
        # Step 0: User prompt
        # Step 1: Model tool call (run_command pytest)
        # Step 2: Tool result with 5,000 chars output (SUCCESS)
        # Step 3: Model tool call (run_command fail_probe)
        # Step 4: Tool result with 3,000 chars output (FAILED exit 1)
        large_success_output = "Created At: 2026-10-02T10:00:00Z\nCompleted At: 2026-10-02T10:00:01Z\n" + ("x" * 4900)
        failure_output = "Created At: 2026-10-02T10:00:02Z\nCompleted At: 2026-10-02T10:00:03Z\nfailed with exit code: 1\n" + ("e" * 2900)

        transcript_data = [
            {"step_index": 0, "type": "USER_INPUT", "content": "run tests"},
            {
                "step_index": 1,
                "type": "PLANNER_RESPONSE",
                "tool_calls": [{"name": "run_command", "args": {"CommandLine": "pytest -v tests/"}}]
            },
            {"step_index": 2, "type": "RUN_COMMAND", "status": "DONE", "content": large_success_output},
            {
                "step_index": 3,
                "type": "PLANNER_RESPONSE",
                "tool_calls": [{"name": "run_command", "args": {"CommandLine": "grep -rn 'secret' ."}}]
            },
            {"step_index": 4, "type": "RUN_COMMAND", "status": "ERROR", "content": failure_output},
        ]

        with open(transcript_file, "w", encoding="utf-8") as f:
            for item in transcript_data:
                f.write(json.dumps(item) + "\n")

        # Insert session and tool calls with NULL volume columns to simulate historical data
        cur.execute("""
            INSERT INTO sessions (
                session_id, transcript_path, total_steps, tool_call_count
            ) VALUES (?, ?, ?, ?)
        """, (session_id, str(transcript_file), 5, 2))

        cur.execute("""
            INSERT INTO tool_calls (
                session_id, step_index, tool_name, command_line, status
            ) VALUES (?, ?, ?, ?, ?)
        """, (session_id, 1, "run_command", "pytest -v tests/", "SUCCESS"))

        cur.execute("""
            INSERT INTO tool_calls (
                session_id, step_index, tool_name, command_line, status
            ) VALUES (?, ?, ?, ?, ?)
        """, (session_id, 3, "run_command", "grep -rn 'secret' .", "FAILED"))

        conn.commit()
        conn.close()

        # Run backfill
        res = backfill_tool_volumes(self.db_path, verbose=False)
        self.assertEqual(res["sessions_processed"], 1)
        self.assertEqual(res["updated_tool_calls"], 2)

        # Verify columns populated in DB
        conn = sqlite3.connect(self.db_path)
        cur = conn.cursor()
        cur.execute("SELECT output_length_chars, command_category, status FROM tool_calls ORDER BY step_index")
        rows = cur.fetchall()
        conn.close()

        self.assertEqual(len(rows), 2)
        self.assertGreater(rows[0][0], 4000)
        self.assertEqual(rows[0][1], "test_runner")
        self.assertEqual(rows[0][2], "SUCCESS")

        self.assertGreater(rows[1][0], 2000)
        self.assertEqual(rows[1][1], "grep_search")
        self.assertEqual(rows[1][2], "FAILED")

        # Run volume analysis
        analysis = analyze_volumes(self.db_path, auto_backfill=False, verbose=False)
        self.assertEqual(analysis["summary"]["total_tool_calls"], 2)

        # Assert Compactor Simulation and ADR-008 Invariant:
        # Failure tool call MUST NOT be compacted
        sim_2k = next(s for s in analysis["compactor_simulations"] if s["threshold_bytes"] == 2048)
        self.assertEqual(sim_2k["impacted_calls"], 1)  # Only the success call is compacted
        self.assertEqual(sim_2k["failure_preservation_violations"], 0)  # 0 violations!
        self.assertGreater(sim_2k["saved_chars"], 2000)

        # Verify markdown report generation
        md_report = generate_markdown_report(analysis)
        self.assertIn("Empirical Tool & Command Character Volume Distribution Report", md_report)
        self.assertIn("Failure Preservation Audit (ADR-008)", md_report)

    def test_cli_audit_volume(self):
        """Verifies `psl audit volume` dispatches cleanly via CLI."""
        conn = sqlite3.connect(self.db_path)
        conn.executescript(SCHEMA_SQL)
        ensure_volume_columns(conn)
        conn.close()

        out_json = self.dir_path / "test_volume.json"
        out_report = self.dir_path / "test_report.md"

        with patch("sys.stdout", new_callable=io.StringIO) as mock_out:
            exit_code = cli_main([
                "audit", "volume",
                "--db", str(self.db_path),
                "--output-json", str(out_json),
                "--output-report", str(out_report),
            ])
            self.assertEqual(exit_code, 0)
            self.assertIn("TOOL & COMMAND VOLUME AUDIT COMPLETE", mock_out.getvalue())


if __name__ == "__main__":
    unittest.main()
