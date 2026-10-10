#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Purrfect Software Limited (PSL)

"""
Hermetic unit tests for pipeline/analyze_failure_clusters.py.

Validates:
1. Handling of missing databases.
2. Graceful processing of empty databases.
3. Multi-model failure clustering, exit code distributions, and domain signature extraction.
4. Steering intervention categorization and markdown report generation.
5. End-to-end CLI invocation.
"""

from __future__ import annotations

import io
import json
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import patch

from pipeline.analyze_failure_clusters import (
    analyze_model_failures_and_interventions,
    generate_markdown_report,
    main,
)


def init_test_schema(db_path: Path) -> None:
    conn = sqlite3.connect(db_path)
    c = conn.cursor()
    c.execute("""
        CREATE TABLE sessions (
            session_id TEXT PRIMARY KEY,
            model TEXT,
            total_steps INTEGER,
            tool_call_count INTEGER,
            tool_error_count INTEGER,
            intervention_count INTEGER,
            origin_developer TEXT,
            remote_synced_at TEXT
        )
    """)
    c.execute("""
        CREATE TABLE tool_calls (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id TEXT,
            step_index INTEGER,
            tool_name TEXT,
            command_line TEXT,
            arguments_json TEXT,
            status TEXT,
            exit_code INTEGER,
            error_snippet TEXT,
            is_loop_candidate INTEGER,
            command_category TEXT
        )
    """)
    c.execute("""
        CREATE TABLE user_interventions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id TEXT,
            step_index INTEGER,
            intervention_type TEXT,
            preceding_tool_failed INTEGER,
            preceding_tool_name TEXT,
            preceding_error_snippet TEXT,
            prompt_text TEXT
        )
    """)
    conn.commit()
    conn.close()


class TestAnalyzeFailureClusters(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.isolated_path = Path(self.temp_dir.name)
        self.db_path = self.isolated_path / "test_telemetry.db"

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def test_missing_database_returns_error(self) -> None:
        missing_db = self.isolated_path / "does_not_exist.db"
        with patch("sys.stdout", new_callable=io.StringIO), patch("sys.stderr", new_callable=io.StringIO):
            code = main(["--db", str(missing_db)])
        self.assertEqual(code, 1)

    def test_empty_database_handling(self) -> None:
        init_test_schema(self.db_path)
        data = analyze_model_failures_and_interventions(self.db_path)
        self.assertEqual(data["summary"]["total_models"], 0)
        self.assertEqual(data["summary"]["total_model_category_clusters"], 0)
        self.assertEqual(data["summary"]["total_failed_tool_interventions"], 0)
        self.assertEqual(data["summary"]["total_steering_interventions"], 0)

        report = generate_markdown_report(data)
        self.assertIn("Empirical Telemetry Analysis", report)
        self.assertIn("Cross-Model Profile", report)

    def test_full_failure_clusters_and_intervention_pipeline(self) -> None:
        init_test_schema(self.db_path)
        conn = sqlite3.connect(self.db_path)
        c = conn.cursor()

        # Seed sessions
        c.execute("""
            INSERT INTO sessions VALUES
            ('sess-1', 'gemini-3.8-flash-high', 100, 50, 5, 2, 'local', '2026-10-10T12:00:00Z'),
            ('sess-2', 'Gemini 3', 50, 20, 4, 1, 'local', '2026-10-10T12:00:00Z')
        """)

        # Seed tool calls
        c.execute("""
            INSERT INTO tool_calls (session_id, step_index, tool_name, command_line, status, exit_code, error_snippet, is_loop_candidate, command_category) VALUES
            ('sess-1', 1, 'run_command', 'git checkout main', 'FAILURE', 1, 'error: pathspec main did not match', 0, 'git'),
            ('sess-1', 2, 'run_command', 'ssh -o ConnectTimeout=2 knot-laptop "ls"', 'FAILURE', 255, 'ssh: connect to host knot-laptop: Connection refused', 0, 'network'),
            ('sess-1', 3, 'run_command', 'psql -U postgres -d app_db -c "SELECT 1"', 'FAILURE', 2, 'psql: error: connection to server on socket failed', 0, 'db'),
            ('sess-1', 4, 'view_file', NULL, 'SUCCESS', 0, NULL, 1, 'non_command'),
            ('sess-2', 1, 'run_command', 'pnpm dev', 'FAILURE', 127, 'command not found: pnpm', 0, 'build')
        """)

        # Seed user interventions
        c.execute("""
            INSERT INTO user_interventions (session_id, step_index, intervention_type, preceding_tool_failed, preceding_tool_name, preceding_error_snippet, prompt_text) VALUES
            ('sess-1', 2, 'STEERING', 1, 'run_command', 'Connection refused', 'Please check Tailscale and mesh routing for the laptop'),
            ('sess-1', 3, 'ERROR_RECOVERY', 1, 'run_command', 'connection failed', 'Run migration on the postgres container instead'),
            ('sess-2', 1, 'STEERING', 0, 'run_command', NULL, 'Use git worktree add for isolated testing')
        """)

        conn.commit()
        conn.close()

        data = analyze_model_failures_and_interventions(self.db_path)
        self.assertEqual(data["summary"]["total_models"], 2)

        # Verify model profiles
        models = {m["model"]: m for m in data["model_profiles"]}
        self.assertIn("gemini-3.8-flash-high", models)
        self.assertIn("Gemini 3", models)
        self.assertEqual(models["gemini-3.8-flash-high"]["total_steps"], 100)
        self.assertEqual(models["gemini-3.8-flash-high"]["error_rate_pct"], 10.0)

        # Verify domain failure signatures
        signatures = data["domain_failure_signatures"]
        self.assertTrue(len(signatures["git_failures"]) > 0)
        self.assertEqual(signatures["git_failures"][0]["exit_code"], 1)

        self.assertTrue(len(signatures["mesh_network_failures"]) > 0)
        self.assertEqual(signatures["mesh_network_failures"][0]["exit_code"], 255)

        self.assertTrue(len(signatures["db_docker_failures"]) > 0)
        self.assertEqual(signatures["db_docker_failures"][0]["exit_code"], 2)

        # Verify steering clusters
        steering = data["steering_correction_clusters"]
        self.assertGreaterEqual(steering["mesh_and_tailscale"], 1)
        self.assertGreaterEqual(steering["db_and_migration"], 1)
        self.assertGreaterEqual(steering["git_worktree_and_branches"], 1)

        # Verify report generation
        report = generate_markdown_report(data)
        self.assertIn("## 1. Cross-Model Profile & Operational Biases", report)
        self.assertIn("## 2. Top Failure Clusters by Model & Command Category", report)
        self.assertIn("## 3. Specialized Domain Failure Signatures", report)
        self.assertIn("## 4. Human-in-the-Loop Intervention Hotspots", report)
        self.assertIn("## 5. Architectural Synthesis: Three New Modular Skills", report)

    def test_main_cli_end_to_end(self) -> None:
        init_test_schema(self.db_path)
        json_out = self.isolated_path / "clusters.json"
        report_out = self.isolated_path / "clusters.md"

        with patch("sys.stdout", new_callable=io.StringIO):
            code = main([
                "--db", str(self.db_path),
                "--output-json", str(json_out),
                "--output-report", str(report_out),
            ])
        self.assertEqual(code, 0)
        self.assertTrue(json_out.exists())
        self.assertTrue(report_out.exists())

        loaded_json = json.loads(json_out.read_text(encoding="utf-8"))
        self.assertIn("summary", loaded_json)
        self.assertIn("model_profiles", loaded_json)


if __name__ == "__main__":
    unittest.main()
