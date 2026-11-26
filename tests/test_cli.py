#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Arafat Zahan (@kuasha420)
# Corporate Stewardship & Infrastructure: Purrfect Software Limited (PSL)
# Governed by: ICARO-42/b Ordinance (Company-Supported Personal IP Framework)

"""
Unit and integration tests for harness/cli.py
"""

import io
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import MagicMock, patch

from harness.cli import main

DYNAMIC_TEST_MODULES = (
    "test_sample",
    "test_clear_state_sample",
    "test_dual_cli_sample",
)


class TestPslCli(unittest.TestCase):
    """Core CLI dispatch, hooks, test runner, and audit subcommand tests."""

    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.orig_state_dir = os.environ.get("PSL_HARNESS_STATE_DIR")
        self.orig_agyis_state_dir = os.environ.get("AGYIS_HARNESS_STATE_DIR")
        self.orig_brain_dir = os.environ.get("ANTIGRAVITY_BRAIN_DIR")
        self.orig_gemini_brain_dir = os.environ.get("GEMINI_BRAIN_DIR")
        os.environ["PSL_HARNESS_STATE_DIR"] = self.temp_dir.name
        os.environ["AGYIS_HARNESS_STATE_DIR"] = self.temp_dir.name
        default_brain = Path(self.temp_dir.name) / "default_brain"
        default_brain.mkdir(parents=True, exist_ok=True)
        os.environ["ANTIGRAVITY_BRAIN_DIR"] = str(default_brain)
        os.environ["GEMINI_BRAIN_DIR"] = str(default_brain)

    def tearDown(self):
        for mod in DYNAMIC_TEST_MODULES:
            sys.modules.pop(mod, None)
        if self.orig_state_dir is not None:
            os.environ["PSL_HARNESS_STATE_DIR"] = self.orig_state_dir
        else:
            os.environ.pop("PSL_HARNESS_STATE_DIR", None)
        if self.orig_agyis_state_dir is not None:
            os.environ["AGYIS_HARNESS_STATE_DIR"] = self.orig_agyis_state_dir
        else:
            os.environ.pop("AGYIS_HARNESS_STATE_DIR", None)
        if self.orig_brain_dir is not None:
            os.environ["ANTIGRAVITY_BRAIN_DIR"] = self.orig_brain_dir
        else:
            os.environ.pop("ANTIGRAVITY_BRAIN_DIR", None)
        if self.orig_gemini_brain_dir is not None:
            os.environ["GEMINI_BRAIN_DIR"] = self.orig_gemini_brain_dir
        else:
            os.environ.pop("GEMINI_BRAIN_DIR", None)
        self.temp_dir.cleanup()

    def test_cli_help(self):
        """Verifies --help outputs usage and exits cleanly with 0 and clean stderr."""
        with patch("sys.stdout", new_callable=io.StringIO) as mock_out, \
             patch("sys.stderr", new_callable=io.StringIO) as mock_err:
            with self.assertRaises(SystemExit) as cm:
                main(["--help"], prog="agyis")
            self.assertEqual(cm.exception.code, 0)
            self.assertEqual(mock_err.getvalue(), "")
            self.assertIn("Agyis Harness for Google Antigravity", mock_out.getvalue())
            self.assertNotIn("PSL Harness", mock_out.getvalue())
            self.assertIn("usage: agyis", mock_out.getvalue())

    def test_cli_psl_help_description(self):
        """Verifies legacy 'psl --help' shows Agyis Harness alias description and deprecation warning."""
        with patch("sys.stdout", new_callable=io.StringIO) as mock_out, \
             patch("sys.stderr", new_callable=io.StringIO) as mock_err:
            with self.assertRaises(SystemExit) as cm:
                main(["--help"], prog="psl")
            self.assertEqual(cm.exception.code, 0)
            self.assertIn("Agyis Harness (Legacy 'psl' CLI Alias", mock_out.getvalue())
            self.assertIn("DeprecationWarning", mock_err.getvalue())

    def test_cli_version(self):
        """Verifies --version prints package version with clean stderr on agyis."""
        from harness import __version__

        with patch("sys.stdout", new_callable=io.StringIO) as mock_out, \
             patch("sys.stderr", new_callable=io.StringIO) as mock_err:
            with self.assertRaises(SystemExit) as cm:
                main(["--version"], prog="agyis")
            self.assertEqual(cm.exception.code, 0)
            self.assertEqual(mock_err.getvalue(), "")
            self.assertRegex(__version__, r"^1\.0\.0(?:-rc\d+)?$")
            self.assertIn(f"agyis-harness {__version__}", mock_out.getvalue())

    def test_cli_status(self):
        """Verifies `psl status` prints repository, skills, agents, and hook status."""
        with patch("sys.stdout", new_callable=io.StringIO) as mock_out:
            code = main(["status"])
            self.assertEqual(code, 0)
            out = mock_out.getvalue()
            self.assertTrue(
                "Agyis Harness for Google Antigravity" in out
                or "PSL Harness for Google Antigravity" in out
            )
            self.assertIn("Active Lifecycle Hooks", out)
            self.assertIn("anti-drift", out)
            self.assertIn("Cognitive Attention Horizon Gauge", out)
            self.assertIn("Modular Skills:", out)
            self.assertIn("Specialist Subagents:", out)

    def test_cli_status_json(self):
        """Verifies `agyis status --json` emits structured JSON report with expected keys (DEF-BB-004)."""
        with patch("sys.stdout", new_callable=io.StringIO) as mock_out:
            code = main(["status", "--json"])
            self.assertEqual(code, 0)
            data = json.loads(mock_out.getvalue())
            self.assertIn("version", data)
            self.assertIn("repository_root", data)
            self.assertIn("platform", data)
            self.assertIn("skills_count", data)
            self.assertIn("subagents_count", data)
            self.assertIn("telemetry_sync", data)
            self.assertIn("active_hooks", data)
            self.assertIn("token_metrics", data)
            self.assertIn("command-safety", data["active_hooks"])
            self.assertIsInstance(data["skills_count"], int)
            self.assertIsInstance(data["subagents_count"], int)

    def test_cli_status_renders_telemetry_sync_lag_and_health(self):
        """Verifies `agyis status` surfaces daemon sync errors and unsynced transcript lag."""
        import sqlite3
        from harness.telemetry.schema import SCHEMA_SQL

        with tempfile.TemporaryDirectory() as td:
            td_path = Path(td)
            fake_db = td_path / "telemetry.db"
            conn = sqlite3.connect(fake_db)
            conn.executescript(SCHEMA_SQL)
            conn.commit()
            conn.close()

            brain_dir = td_path / "brain"
            t_dir = brain_dir / "sess-lag-01" / ".system_generated" / "logs"
            t_dir.mkdir(parents=True, exist_ok=True)
            (t_dir / "transcript.jsonl").write_text('{"step_index": 0}\n', encoding="utf-8")

            state_dir = td_path / "state"
            state_dir.mkdir(parents=True, exist_ok=True)
            (state_dir / "telemetry_sync_status.json").write_text(
                json.dumps({
                    "status": "error",
                    "last_harvest_at": "2026-11-08T00:00:00Z",
                    "consecutive_failures": 2,
                    "last_error": "no such column",
                }),
                encoding="utf-8",
            )

            env_patch = {
                "AGYIS_HARNESS_STATE_DIR": str(state_dir),
                "ANTIGRAVITY_BRAIN_DIR": str(brain_dir),
            }
            with patch.dict(os.environ, env_patch), \
                 patch("harness.commands.status.DEFAULT_DB", fake_db), \
                 patch("sys.stdout", new_callable=io.StringIO) as mock_out:
                code = main(["status"])
            self.assertEqual(code, 0)
            out = mock_out.getvalue()
            self.assertIn("Telemetry Sync:", out)
            self.assertIn("state=error", out)
            self.assertIn("failures=2", out)
            self.assertIn("lag=1 unsynced / 0 stale", out)
            self.assertIn("no such column", out)

    def test_cli_skills_subcommand(self):
        """Verifies `psl skills` lists skills and inspects details."""
        with patch("sys.stdout", new_callable=io.StringIO) as mock_out:
            code = main(["skills"])
            self.assertEqual(code, 0)
            out = mock_out.getvalue()
            self.assertTrue("Agyis Modular Skills" in out or "PSL Modular Skills" in out)
            self.assertIn("psl-stack-shell", out)

        with patch("sys.stdout", new_callable=io.StringIO) as mock_out:
            code = main(["skills", "psl-stack-python"])
            self.assertEqual(code, 0)
            out = mock_out.getvalue()
            self.assertIn("Skill: psl-stack-python", out)

        with patch("sys.stdout", new_callable=io.StringIO) as mock_out:
            code = main(["skills", "--json"])
            self.assertEqual(code, 0)
            data = json.loads(mock_out.getvalue().strip())
            self.assertIsInstance(data, list)
            self.assertGreaterEqual(len(data), 8)

    def test_cli_agents_subcommand(self):
        """Verifies `psl agents` lists agents and inspects details."""
        with patch("sys.stdout", new_callable=io.StringIO) as mock_out:
            code = main(["agents"])
            self.assertEqual(code, 0)
            out = mock_out.getvalue()
            self.assertTrue("Agyis Specialist Subagents" in out or "PSL Specialist Subagents" in out)
            self.assertIn("agyis_builder", out)

        with patch("sys.stdout", new_callable=io.StringIO) as mock_out:
            code = main(["agents", "harness_reviewer"])
            self.assertEqual(code, 0)
            out = mock_out.getvalue()
            self.assertIn("Agent:       agyis_reviewer", out)
            self.assertIn("Archetype:   hammer", out)

        with patch("sys.stdout", new_callable=io.StringIO) as mock_out:
            code = main(["agents", "--json"])
            self.assertEqual(code, 0)
            data = json.loads(mock_out.getvalue().strip())
            self.assertIsInstance(data, list)
            self.assertEqual(len(data), 8)

    def test_cli_agents_workspace_root_override(self):
        """Verifies `_get_repo_root()` and `psl agents` respect _TEST_WORKSPACE_ROOT."""
        import harness.cli
        from harness.commands.agents import _get_repo_root

        custom_root = Path(self.temp_dir.name) / "custom_ws"
        custom_root.mkdir(parents=True)

        with patch.object(harness.cli, "_TEST_WORKSPACE_ROOT", custom_root):
            self.assertEqual(_get_repo_root(), custom_root)

            with patch("sys.stdout", new_callable=io.StringIO) as mock_out:
                code = main(["agents", "--sync"])
                self.assertEqual(code, 0)
                out = mock_out.getvalue()
                self.assertIn(str(custom_root / ".agents" / "agents"), out)
                self.assertTrue((custom_root / ".agents" / "agents" / "agyis_builder.md").exists())

        self.assertNotEqual(_get_repo_root(), custom_root)
        self.assertIsNone(harness.cli._TEST_WORKSPACE_ROOT)

    def test_cli_agents_archetype_help_and_create(self):
        """Verifies `agyis agents --help` documents custodian and investigator archetypes."""
        with patch("sys.stdout", new_callable=io.StringIO) as mock_out:
            with self.assertRaises(SystemExit) as cm:
                main(["agents", "--help"], prog="agyis")
            self.assertEqual(cm.exception.code, 0)
            out = mock_out.getvalue()
            self.assertIn("custodian", out)
            self.assertIn("investigator", out)

        import harness.cli
        custom_root = Path(self.temp_dir.name) / "create_ws"
        custom_root.mkdir(parents=True)
        with patch.object(harness.cli, "_TEST_WORKSPACE_ROOT", custom_root):
            with patch("sys.stdout", new_callable=io.StringIO) as mock_out:
                code = main(["agents", "create", "test_custodian", "--archetype", "custodian", "--bundle", "verifier"])
                self.assertEqual(code, 0)
                out = mock_out.getvalue()
                self.assertIn("Created agent 'test_custodian'", out)
                self.assertTrue((custom_root / ".agents" / "agents" / "test_custodian.md").exists())

            with patch("sys.stdout", new_callable=io.StringIO) as mock_out:
                code = main(["agents", "create", "test_investigator", "--archetype", "investigator", "--bundle", "verifier"])
                self.assertEqual(code, 0)
                out = mock_out.getvalue()
                self.assertIn("Created agent 'test_investigator'", out)
                self.assertTrue((custom_root / ".agents" / "agents" / "test_investigator.md").exists())

    def test_cli_hook_dispatch_safety(self):
        """Verifies `psl hook safety` dispatches to command_safety_hook."""
        payload = {
            "conversationId": "test-cli-hook",
            "toolCall": {
                "name": "run_command",
                "args": {"CommandLine": "ls -la"},
            },
        }
        with patch("sys.stdin", io.StringIO(json.dumps(payload))), \
             patch("sys.stdout", new_callable=io.StringIO) as mock_out:
            code = main(["hook", "safety"])
            self.assertEqual(code, 0)
            res = json.loads(mock_out.getvalue().strip())
            self.assertEqual(res["decision"], "allow")

    def test_cli_hook_dispatch_anti_loop(self):
        """Verifies `psl hook anti-loop` dispatches to anti_loop_hook."""
        payload = {
            "conversationId": "test-cli-anti-loop",
            "toolCall": {
                "name": "view_file",
                "args": {"AbsolutePath": "/workspace/test.py"},
            },
        }
        with patch("sys.stdin", io.StringIO(json.dumps(payload))), \
             patch("sys.stdout", new_callable=io.StringIO) as mock_out:
            code = main(["hook", "anti-loop"])
            self.assertEqual(code, 0)
            res = json.loads(mock_out.getvalue().strip())
            self.assertEqual(res["decision"], "allow")

    def test_cli_hook_dispatch_compactor(self):
        """Verifies `psl hook compactor` dispatches to output_compactor_hook."""
        payload = {
            "conversationId": "test-cli-compactor",
            "toolOutput": "Short output",
            "exitCode": 0,
        }
        with patch("sys.stdin", io.StringIO(json.dumps(payload))), \
             patch("sys.stdout", new_callable=io.StringIO) as mock_out:
            code = main(["hook", "compactor"])
            self.assertEqual(code, 0)
            res = json.loads(mock_out.getvalue().strip())
            self.assertEqual(res, {})

    def test_cli_hook_dispatch_verification_fence(self):
        """Verifies `psl hook verification-fence` dispatches cleanly to completion_fence_hook."""
        payload = {
            "conversationId": "test-cli-fence",
            "action": "evaluate_stop",
        }
        with patch("sys.stdin", io.StringIO(json.dumps(payload))), \
             patch("sys.stdout", new_callable=io.StringIO) as mock_out:
            code = main(["hook", "verification-fence"])
            self.assertEqual(code, 0)
            res = json.loads(mock_out.getvalue().strip())
            self.assertEqual(res["decision"], "allow")

    def test_cli_hook_dispatch_anti_drift(self):
        """Verifies `psl hook anti-drift` and its aliases dispatch to anti_drift_hook."""
        payload = {
            "conversationId": "test-cli-drift",
            "action": "check_drift",
            "target_file": "main.py",
            "plan_files": ["main.py"],
        }
        for alias in ("anti-drift", "drift", "anti_drift"):
            with patch("sys.stdin", io.StringIO(json.dumps(payload))), \
                 patch("sys.stdout", new_callable=io.StringIO) as mock_out:
                code = main(["hook", alias])
                self.assertEqual(code, 0)
                res = json.loads(mock_out.getvalue().strip())
                self.assertEqual(res["decision"], "allow")

    def test_cli_test_runner(self):
        """Verifies `psl test` runs discovery against an isolated test folder without self-recursion."""
        sample_test = (
            "import unittest\n"
            "class Sample(unittest.TestCase):\n"
            "    def test_ok(self):\n"
            "        self.assertTrue(True)\n"
        )
        sample_file = Path(self.temp_dir.name) / "test_sample.py"
        sample_file.write_text(sample_test, encoding="utf-8")

        with patch("sys.stdout", new_callable=io.StringIO), \
             patch("sys.stderr", new_callable=io.StringIO):
            code = main(["test", "-s", self.temp_dir.name])
            self.assertEqual(code, 0)

    def test_cli_test_runner_clears_verification_states(self):
        """Verifies `psl test` clears dirty flags across active state files."""
        from harness.hooks import completion_fence_hook
        # Record dirty states in multiple conversation files
        completion_fence_hook.record_edit("src/file1.py", conv_id="conv-1")
        completion_fence_hook.record_edit("src/file2.py", conv_id="conv-2")

        state1 = completion_fence_hook.load_state(conv_id="conv-1")
        self.assertTrue(state1["code_dirty"])

        sample_test = (
            "import unittest\n"
            "class Sample(unittest.TestCase):\n"
            "    def test_ok(self):\n"
            "        self.assertTrue(True)\n"
        )
        sample_file = Path(self.temp_dir.name) / "test_clear_state_sample.py"
        sample_file.write_text(sample_test, encoding="utf-8")

        with patch("sys.stdout", new_callable=io.StringIO), \
             patch("sys.stderr", new_callable=io.StringIO):
            code = main(["test", "-s", self.temp_dir.name])
            self.assertEqual(code, 0)

        # Both states should now have code_dirty = False
        state1_after = completion_fence_hook.load_state(conv_id="conv-1")
        state2_after = completion_fence_hook.load_state(conv_id="conv-2")
        self.assertFalse(state1_after["code_dirty"])
        self.assertFalse(state2_after["code_dirty"])
        self.assertEqual(state1_after["block_count"], 0)
        self.assertEqual(state2_after["block_count"], 0)

    def test_cli_audit_session_json(self):
        """Verifies `psl audit session --json` parses and emits report."""
        dummy_report = {
            "session_id": "test-session-1234",
            "coordinator": {
                "compacted_transcript": {"total_steps": 10},
                "full_transcript": {"total_steps": 10, "total_chars": 500, "estimated_tokens": 125, "tool_errors": 0},
                "compaction_savings_chars": 0,
                "compaction_savings_pct": 0.0,
            },
            "subagents": [],
            "collective_pipeline": {"total_steps": 10, "total_tools": 5, "total_tokens": 125, "offload_step_pct": 0, "offload_tool_pct": 0, "offload_token_pct": 0}
        }
        with patch("pipeline.analyze_live_session.find_latest_session_dir", return_value=Path(self.temp_dir.name)), \
             patch("pipeline.analyze_live_session.analyze_session", return_value=dummy_report), \
             patch("sys.stdout", new_callable=io.StringIO) as mock_out:
            code = main(["audit", "session", "--json"])
            self.assertEqual(code, 0)
            data = json.loads(mock_out.getvalue())
            self.assertEqual(data["session_id"], "test-session-1234")

    def test_cli_audit_benchmark(self):
        """Verifies `psl audit benchmark` dispatches to benchmark_reasoning_tiers.main."""
        with patch("pipeline.benchmark_reasoning_tiers.main") as mock_bench:
            code = main(["audit", "benchmark"])
            self.assertEqual(code, 0)
            mock_bench.assert_called_once_with([])

    def test_cli_audit_clusters(self):
        """Verifies `psl audit clusters` dispatches to analyze_failure_clusters.main."""
        with patch("pipeline.analyze_failure_clusters.main", return_value=0) as mock_clusters:
            code = main(["audit", "clusters"])
            self.assertEqual(code, 0)
            mock_clusters.assert_called_once_with([])

    def test_cli_audit_clusters_with_custom_flags(self):
        """Verifies `psl audit clusters --db ...` forwards custom flags cleanly."""
        with patch("pipeline.analyze_failure_clusters.main", return_value=0) as mock_clusters:
            code = main(["audit", "clusters", "--db", "custom.db", "--output-json", "out.json", "--output-report", "out.md"])
            self.assertEqual(code, 0)
            mock_clusters.assert_called_once_with([
                "--db", "custom.db",
                "--output-json", "out.json",
                "--output-report", "out.md",
            ])

    def test_cli_audit_artifacts(self):
        """Verifies `psl audit artifacts` dispatches to audit_artifacts.main."""
        with patch("pipeline.audit_artifacts.main") as mock_artifacts:
            code = main(["audit", "artifacts"])
            self.assertEqual(code, 0)
            mock_artifacts.assert_called_once_with([])

    def test_cli_audit_configs(self):
        """Verifies `psl audit configs` dispatches to audit_project_configs.main."""
        with patch("pipeline.audit_project_configs.main") as mock_configs:
            code = main(["audit", "configs"])
            self.assertEqual(code, 0)
            mock_configs.assert_called_once_with([])

    def test_cli_audit_configs_aliases(self):
        """Verifies `psl audit project_configs` and `psl audit project-configs` dispatch cleanly."""
        with patch("pipeline.audit_project_configs.main") as mock_configs:
            code1 = main(["audit", "project_configs"])
            self.assertEqual(code1, 0)
            code2 = main(["audit", "project-configs"])
            self.assertEqual(code2, 0)
            self.assertEqual(mock_configs.call_count, 2)

    def test_cli_audit_session_with_db_flag(self):
        """Verifies `psl audit session --save-db --db <path>` saves into specified database."""
        sess_dir = Path(self.temp_dir.name) / "sess_dir"
        log_dir = sess_dir / ".system_generated" / "logs"
        log_dir.mkdir(parents=True)
        (log_dir / "transcript.jsonl").write_text(json.dumps({"step_index": 0}) + "\n")

        dummy_report = {
            "session_id": "test-session-5678",
            "coordinator": {},
            "subagents": [],
            "collective_pipeline": {}
        }
        custom_db = Path(self.temp_dir.name) / "audit_target.db"

        with patch("pipeline.analyze_live_session.find_latest_session_dir", return_value=sess_dir), \
             patch("pipeline.analyze_live_session.analyze_session", return_value=dummy_report), \
             patch("pipeline.extract_transcripts.extract_session", return_value=({
                 "session_id": "test-session-5678", "start_time": "2026-01-01", "end_time": "2026-01-01",
                 "duration_seconds": 1.0, "total_steps": 1, "model": "gemini",
                 "workspace_path": "/ws", "transcript_path": str(log_dir / "transcript.jsonl"),
                 "file_size_bytes": 10, "has_errors": 0, "tool_call_count": 0,
                 "tool_error_count": 0, "intervention_count": 0
             }, [], [], [])), \
             patch("sys.stdout", new_callable=io.StringIO):
            code = main(["audit", "session", "--save-db", "--db", str(custom_db), "--json"])
            self.assertEqual(code, 0)
            self.assertTrue(custom_db.exists())


if __name__ == "__main__":
    unittest.main()
