#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Arafat Zahan (@kuasha420)
# Corporate Stewardship & Infrastructure: Purrfect Software Limited (PSL)
# Governed by: ICARO-42/b Ordinance (Company-Supported Personal IP Framework)

"""
Unit and contract tests for Ultra-Deep Horizon Telemetry Microscope.
Verifies survival archetype classification, step bracket profiling,
Knot inception autopsy, report formatting, and CLI integration under <1.0s benchmark.
"""

import io
import json
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import patch

from harness.cli import main as cli_main
from pipeline.analyze_ultra_deep_sessions import (
    analyze_ultra_deep_sessions,
    autopsy_knot_inception,
    classify_survival_archetype,
    estimate_tokens,
    generate_markdown_report,
    profile_session_phases,
)


class TestUltraDeepAnalyzer(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.dir_path = Path(self.temp_dir.name)
        self.db_path = self.dir_path / "test_telemetry.db"

        # Initialize test database
        self.conn = sqlite3.connect(self.db_path)
        cur = self.conn.cursor()
        cur.executescript("""
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

            CREATE TABLE tool_calls (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id TEXT,
                step_index INTEGER,
                tool_name TEXT,
                command_line TEXT,
                status TEXT,
                output_length_chars INTEGER,
                output_lines INTEGER,
                arguments_length_chars INTEGER,
                command_category TEXT,
                is_truncated INTEGER
            );

            CREATE TABLE user_interventions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id TEXT,
                step_index INTEGER,
                timestamp TEXT,
                prompt_text TEXT,
                is_rescue INTEGER,
                interrupted_tool TEXT
            );
        """)
        self.conn.commit()

    def tearDown(self):
        self.conn.close()
        self.temp_dir.cleanup()

    def test_estimate_tokens(self):
        """Verifies character to token estimation heuristic."""
        self.assertEqual(estimate_tokens(0), 0)
        self.assertEqual(estimate_tokens(100), 25)
        self.assertEqual(estimate_tokens(4000), 1000)

    def test_classify_survival_archetype(self):
        """Verifies 3-tier archetype classification logic."""
        # Type A: Low intervention (<0.9/100s) and low error (<5.5%)
        # 1600 steps, 700 calls, 20 errors (2.8%), 5 interventions (0.31/100s)
        self.assertEqual(
            classify_survival_archetype(1600, 700, 20, 5, "/workspaces/sunshine-physio"),
            "TYPE_A_SURVIVOR"
        )

        # Type B: Systems workspace keywords (knot, purr, mesh, 8-ball)
        # Even with moderate errors/interventions
        self.assertEqual(
            classify_survival_archetype(3000, 1500, 70, 30, "/home/user/Dev/knot-mesh"),
            "TYPE_B_SYSTEMS_BREAKTHROUGH"
        )
        self.assertEqual(
            classify_survival_archetype(3357, 1616, 80, 36, "/home/user/Dev/8-Ball-Pool-Guide-Line"),
            "TYPE_B_SYSTEMS_BREAKTHROUGH"
        )

        # Type C: High interventions (>=1.5/100s) or high errors (>=5.0%)
        # 2000 steps, 1000 calls, 80 errors (8.0%), 40 interventions (2.0/100s) in generic workspace
        self.assertEqual(
            classify_survival_archetype(2000, 1000, 80, 40, "/workspaces/generic-app"),
            "TYPE_C_THRASHING_TRAP"
        )

    def test_profile_session_phases(self):
        """Verifies step bracket aggregation across trajectory."""
        cur = self.conn.cursor()
        s_id = "test-session-123"

        # Populate tool calls across different brackets
        # Bracket 0-100: 2 calls, 0 errors, 200 chars
        cur.execute("INSERT INTO tool_calls (session_id, step_index, tool_name, status, output_length_chars) VALUES (?, 10, 'run_command', 'SUCCESS', 100)", (s_id,))
        cur.execute("INSERT INTO tool_calls (session_id, step_index, tool_name, status, output_length_chars) VALUES (?, 50, 'view_file', 'SUCCESS', 100)", (s_id,))

        # Bracket 101-500: 2 calls, 1 error, 500 chars
        cur.execute("INSERT INTO tool_calls (session_id, step_index, tool_name, status, output_length_chars) VALUES (?, 150, 'run_command', 'ERROR', 300)", (s_id,))
        cur.execute("INSERT INTO tool_calls (session_id, step_index, tool_name, status, output_length_chars) VALUES (?, 200, 'replace_file_content', 'SUCCESS', 200)", (s_id,))

        # Interventions
        cur.execute("INSERT INTO user_interventions (session_id, step_index, prompt_text) VALUES (?, 20, 'Start setup')", (s_id,))
        cur.execute("INSERT INTO user_interventions (session_id, step_index, prompt_text) VALUES (?, 160, 'Fix the error')", (s_id,))
        self.conn.commit()

        phases = profile_session_phases(self.conn, s_id)
        self.assertEqual(len(phases), 2)

        # First bracket (0000-0100)
        self.assertEqual(phases[0]["bracket"], "0000-0100")
        self.assertEqual(phases[0]["tool_calls"], 2)
        self.assertEqual(phases[0]["tool_errors"], 0)
        self.assertEqual(phases[0]["interventions"], 1)
        self.assertEqual(phases[0]["output_chars"], 200)

        # Second bracket (0101-0500)
        self.assertEqual(phases[1]["bracket"], "0101-0500")
        self.assertEqual(phases[1]["tool_calls"], 2)
        self.assertEqual(phases[1]["tool_errors"], 1)
        self.assertEqual(phases[1]["error_rate_pct"], 50.0)
        self.assertEqual(phases[1]["interventions"], 1)

    def test_autopsy_knot_inception_present_and_absent(self):
        """Verifies Knot autopsy when session exists vs. when absent."""
        # 1. When absent
        res_absent = autopsy_knot_inception(self.conn)
        self.assertFalse(res_absent["found"])

        # 2. When present
        cur = self.conn.cursor()
        knot_id = "8cbe936a-0e60-40e9-bacf-9ce78b89a274"
        cur.execute("""
            INSERT INTO sessions (
                session_id, total_steps, tool_call_count, tool_error_count, intervention_count,
                duration_seconds, start_time, workspace_path
            ) VALUES (?, 3357, 1616, 80, 36, 78120.0, '2026-09-04 12:00:00', '/home/kuasha/Dev/8-Ball-Pool-Guide-Line')
        """, (knot_id,))
        cur.execute("INSERT INTO tool_calls (session_id, step_index, tool_name, status) VALUES (?, 1, 'search_web', 'SUCCESS')", (knot_id,))
        cur.execute("INSERT INTO user_interventions (session_id, step_index, prompt_text) VALUES (?, 0, 'Is it possible to use KDE connect...')", (knot_id,))
        self.conn.commit()

        res_present = autopsy_knot_inception(self.conn)
        self.assertTrue(res_present["found"])
        self.assertEqual(res_present["session_id"], knot_id)
        self.assertEqual(res_present["total_steps"], 3357)
        self.assertEqual(res_present["duration_hours"], 21.7)
        self.assertEqual(len(res_present["tool_mix"]), 1)
        self.assertEqual(res_present["tool_mix"][0]["tool_name"], "search_web")
        self.assertGreater(len(res_present["milestones"]), 0)

    def test_analyze_ultra_deep_sessions_and_report_generation(self):
        """Verifies end-to-end data analysis and markdown report generation."""
        cur = self.conn.cursor()
        # Insert a 1500-step titan session
        cur.execute("""
            INSERT INTO sessions (
                session_id, total_steps, tool_call_count, tool_error_count, intervention_count,
                duration_seconds, start_time, workspace_path
            ) VALUES ('titan-1', 1500, 700, 20, 5, 7200.0, '2026-09-10 10:00:00', '/home/kuasha/Dev/sunshine-physio')
        """)
        # Insert a 200-step standard session (not titan)
        cur.execute("""
            INSERT INTO sessions (
                session_id, total_steps, tool_call_count, tool_error_count, intervention_count,
                duration_seconds, start_time, workspace_path
            ) VALUES ('small-1', 200, 80, 5, 2, 900.0, '2026-09-11 10:00:00', '/home/kuasha/Dev/test-app')
        """)
        self.conn.commit()

        results = analyze_ultra_deep_sessions(self.db_path)
        m = results["macro_summary"]

        self.assertEqual(m["total_titan_sessions"], 1)
        self.assertEqual(m["total_titan_steps"], 1500)
        self.assertEqual(m["all_sessions_count"], 2)
        self.assertEqual(m["all_steps_count"], 1700)
        self.assertAlmostEqual(m["titan_steps_share_pct"], round(1500 * 100.0 / 1700, 1))

        # Markdown report rendering
        md = generate_markdown_report(results)
        self.assertIn("# 🔬 The Ultra-Deep Horizon Microscope", md)
        self.assertIn("titan-1", md)
        self.assertIn("🟢 Type A (Survivor)", md)
        self.assertIn("TITAN CORPUS CONCENTRATION MATRIX", md)

    def test_cli_audit_deep_integration(self):
        """Verifies ./psl audit deep CLI dispatch with custom database and output paths."""
        cur = self.conn.cursor()
        cur.execute("""
            INSERT INTO sessions (
                session_id, total_steps, tool_call_count, tool_error_count, intervention_count,
                duration_seconds, start_time, workspace_path
            ) VALUES ('titan-cli', 1200, 600, 10, 3, 3600.0, '2026-09-12 12:00:00', '/home/kuasha/Dev/knot')
        """)
        self.conn.commit()

        json_out = self.dir_path / "out.json"
        report_out = self.dir_path / "out.md"

        buf = io.StringIO()
        with patch("sys.stdout", buf):
            code = cli_main([
                "audit", "deep",
                "--db", str(self.db_path),
                "--output-json", str(json_out),
                "--output-report", str(report_out),
                "--quiet"
            ])

        self.assertEqual(code, 0)
        self.assertTrue(json_out.exists())
        self.assertTrue(report_out.exists())

        with open(json_out, "r", encoding="utf-8") as f:
            data = json.load(f)
        self.assertEqual(data["macro_summary"]["total_titan_sessions"], 1)

        with open(report_out, "r", encoding="utf-8") as f:
            report_text = f.read()
        self.assertIn("titan-cl", report_text)


if __name__ == "__main__":
    unittest.main()
