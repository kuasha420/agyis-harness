#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Arafat Zahan (@kuasha420)
# Corporate Stewardship & Infrastructure: Purrfect Software Limited (PSL)
# Governed by: ICARO-42/b Ordinance (Company-Supported Personal IP Framework)

"""
Hermetic Smoke Test Suite for PSL Development & Analysis Pipeline.
Exercises:
- pipeline/analyze_context_dynamics.py
- pipeline/classify_failures.py
- pipeline/inventory_customizations.py
against isolated in-memory and temporary SQLite databases and filesystems.
"""

from __future__ import annotations

import json
from pathlib import Path
import sqlite3
import tempfile
import unittest

from pipeline.analyze_context_dynamics import analyze_context_dynamics
from pipeline.classify_failures import run_classification_audit
from pipeline.inventory_customizations import (
    scan_mcp_environment,
    scan_plugins,
    scan_skills_directory,
)


from harness.telemetry.schema import SCHEMA_SQL


def _init_mock_telemetry_db(db_path: Path) -> None:
    """Creates tables using official SCHEMA_SQL and seeds realistic telemetry records."""
    conn = sqlite3.connect(db_path)
    conn.executescript(SCHEMA_SQL)
    c = conn.cursor()

    # Seed sessions
    c.execute("""
        INSERT INTO sessions (session_id, start_time, end_time, duration_seconds, total_steps, model, workspace_path, transcript_path, file_size_bytes, has_errors, tool_call_count, tool_error_count, intervention_count)
        VALUES
        ('s-001', '2026-10-01T10:00:00Z', '2026-10-01T10:05:00Z', 300.0, 15, 'claude-3-7-sonnet', '/ws1', 'transcript_1.jsonl', 50000, 1, 10, 1, 0),
        ('s-002', '2026-10-01T11:00:00Z', '2026-10-01T11:20:00Z', 1200.0, 220, 'claude-3-7-sonnet', '/ws2', 'transcript_2.jsonl', 250000, 1, 150, 25, 5)
    """)

    tool_records = [
        ('s-001', 1, 'run_command', 'echo ok', None, None, 0.2, 'SUCCESS', 0, 0),
        ('s-001', 2, 'view_file', None, 'harness/cli.py', None, 0.05, 'SUCCESS', 0, 0),
        ('s-001', 3, 'run_command', 'grep -r missing .', None, 'grep: missing: No such file', 0.1, 'ERROR', 1, 0),
        ('s-002', 1, 'run_command', 'ssh vps uptime', None, 'Connection timed out', 5.0, 'ERROR', 255, 0),
        ('s-002', 2, 'run_command', 'pnpm build', None, 'pnpm: command not found', 0.1, 'ERROR', 127, 0),
        ('s-002', 3, 'run_command', 'python3 -c "bad code"', None, 'SyntaxError: invalid syntax', 0.2, 'ERROR', 1, 0),
        ('s-002', 4, 'replace_file_content', None, 'app.py', 'TargetContent not found in file', 0.05, 'ERROR', None, 0),
        ('s-002', 5, 'view_file', None, 'harness/cli.py', None, 0.02, 'SUCCESS', 0, 1),
        ('s-002', 6, 'view_file', None, 'harness/cli.py', None, 0.02, 'SUCCESS', 0, 1),
    ]
    c.executemany("""
        INSERT INTO tool_calls (session_id, step_index, tool_name, command_line, target_path, error_snippet, duration_seconds, status, exit_code, is_loop_candidate)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, tool_records)

    c.execute("""
        INSERT INTO steps (session_id, step_index, step_type, content_length, thinking_length)
        VALUES
        ('s-001', 1, 'MODEL_TURN', 500, 200),
        ('s-001', 2, 'TOOL_USE', 1200, 0),
        ('s-002', 1, 'MODEL_TURN', 2500, 800),
        ('s-002', 2, 'TOOL_USE', 18000, 0)
    """)

    c.execute("""
        INSERT INTO user_interventions (session_id, step_index, intervention_type, prompt_text)
        VALUES
        ('s-002', 50, 'STOP_AND_HOLD', 'Wait, stop before deleting files')
    """)

    conn.commit()
    conn.close()


class TestPipelineAuditSmoke(unittest.TestCase):
    """Smoke test suite validating telemetry analysis and customization scanners."""

    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.isolated_path = Path(self.temp_dir.name)
        self.db_path = self.isolated_path / "mock_telemetry.db"
        _init_mock_telemetry_db(self.db_path)

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def test_pipeline_audit_tools_smoke(self) -> None:
        """
        Executes analyze_context_dynamics, run_classification_audit, and
        inventory_customizations scanners against isolated test fixtures.
        """
        # 1. Smoke test analyze_context_dynamics
        dynamics = analyze_context_dynamics(self.db_path)
        self.assertIsInstance(dynamics, dict)
        self.assertIn("top_bloaters", dynamics)
        self.assertIn("step_volumes", dynamics)
        self.assertIn("token_saturation_buckets", dynamics)
        self.assertIn("compaction_simulation", dynamics)
        self.assertGreater(len(dynamics["top_bloaters"]), 0)
        self.assertGreater(len(dynamics["step_volumes"]), 0)

        # 2. Smoke test run_classification_audit
        audit = run_classification_audit(self.db_path)
        self.assertIsInstance(audit, dict)
        self.assertIn("overview", audit)
        self.assertEqual(audit["overview"]["total_sessions"], 2)
        self.assertIn("tool_stats", audit)
        self.assertIn("exit_codes", audit)
        self.assertIn("depth_stats", audit)
        self.assertIn("exit_code_1_breakdown", audit)

        # Verify exit codes were cataloged
        found_exit_codes = {ec["exit_code"] for ec in audit["exit_codes"]}
        self.assertTrue({1, 127, 255}.issubset(found_exit_codes))

        # 3. Smoke test inventory_customizations scanners
        skills_root = self.isolated_path / "skills"
        skills_root.mkdir()
        skill_sample = skills_root / "sample-skill"
        skill_sample.mkdir()
        (skill_sample / "SKILL.md").write_text(
            "---\nname: sample-skill\ndescription: Test skill for inventory\n---\nBody here.",
            encoding="utf-8",
        )

        scanned_skills = scan_skills_directory(skills_root, scope="test-scope")
        self.assertEqual(len(scanned_skills), 1)
        self.assertEqual(scanned_skills[0]["name"], "sample-skill")
        self.assertEqual(scanned_skills[0]["scope"], "test-scope")
        self.assertIn("Test skill for inventory", scanned_skills[0]["description"])

        # Test scan_plugins
        plugins_root = self.isolated_path / "plugins"
        plugins_root.mkdir()
        plugin_sample = plugins_root / "sample-plugin"
        plugin_sample.mkdir()
        (plugin_sample / "plugin.json").write_text(
            json.dumps({"name": "sample-plugin", "version": "1.0.0"}),
            encoding="utf-8",
        )
        plugin_skills = plugin_sample / "skills"
        plugin_skills.mkdir()
        p_subskill = plugin_skills / "bundled"
        p_subskill.mkdir()
        (p_subskill / "SKILL.md").write_text(
            "---\nname: bundled\ndescription: Bundled in plugin\n---\nContent",
            encoding="utf-8",
        )

        scanned_plugins = scan_plugins(plugins_root)
        self.assertEqual(len(scanned_plugins), 1)
        self.assertEqual(scanned_plugins[0]["name"], "sample-plugin")
        self.assertEqual(len(scanned_plugins[0]["bundled_skills"]), 1)

        # Test scan_mcp_environment
        mcp_cfg = self.isolated_path / "mcp_config.json"
        mcp_cfg.write_text(
            json.dumps({"mcpServers": {"test_server": {"command": "node", "args": ["server.js"]}}}),
            encoding="utf-8",
        )
        mcp_schemas = self.isolated_path / "mcp_schemas"
        mcp_schemas.mkdir()
        (mcp_schemas / "test_server").mkdir()
        (mcp_schemas / "test_server" / "tool_a.json").write_text(
            json.dumps({"name": "tool_a", "description": "A tool"}),
            encoding="utf-8",
        )

        mcp_info = scan_mcp_environment(mcp_cfg, mcp_schemas)
        self.assertIn("configured_servers", mcp_info)
        self.assertIn("active_schemas", mcp_info)
        self.assertIn("test_server", mcp_info["configured_servers"])
        self.assertIn("test_server", mcp_info["active_schemas"])
        self.assertEqual(mcp_info["total_active_tools"], 1)
        self.assertEqual(mcp_info["active_schemas"]["test_server"]["tool_count"], 1)

        # 4. Smoke test audit_artifacts report generator SPDX header
        from pipeline.audit_artifacts import generate_markdown_report

        mock_data = {
            "timestamp": "2026-10-10 12:00:00Z",
            "total_markdown_artifacts": 10,
            "total_sessions_with_artifacts": 2,
            "artifacts_by_type": {"implementation_plan.md": 5, "walkthrough.md": 5},
            "planning_stats": {
                "implementation_plans": 5,
                "plans_with_feedback_requested": 4,
                "walkthroughs": 5,
                "paired_plan_walkthrough_sessions": 2,
                "average_plan_to_walkthrough_fidelity_pct": 80.0,
            },
            "drift_samples": [],
        }
        report_file = self.isolated_path / "test_report.md"
        generate_markdown_report(mock_data, report_file)

        content = report_file.read_text(encoding="utf-8")
        self.assertTrue(content.startswith("<!-- SPDX-License-Identifier: Apache-2.0 -->"))
        self.assertIn("<!-- Copyright (c) 2026 Arafat Zahan (@kuasha420) -->", content)
        self.assertIn("<!-- Corporate Stewardship & Infrastructure: Purrfect Software Limited (PSL) -->", content)
        self.assertIn("<!-- Governed by: ICARO-42/b Ordinance (Company-Supported Personal IP Framework) -->", content)


if __name__ == "__main__":
    unittest.main()
