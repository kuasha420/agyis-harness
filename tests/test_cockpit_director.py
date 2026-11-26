# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Arafat Zahan (@kuasha420)
# Corporate Stewardship & Infrastructure: Purrfect Software Limited (PSL)
# Governed by: ICARO-42/b Ordinance (Company-Supported Personal IP Framework)

"""
Hermetic unit and benchmark tests for Cockpit Flight Director & Subagent Router CLI Suite (Issue #92).

Verifies the 12 Canonical Routing Workflows, stage transition payload contracts,
CLI status/route/verify commands, and sub-second SLA (<0.20s).
Zero external dependencies (100% Python Standard Library).
"""

from __future__ import annotations

import argparse
import io
import json
import os
from pathlib import Path
import tempfile
import time
import unittest
from unittest.mock import MagicMock, patch

from harness.cli import build_parser, main
from harness.commands.cockpit import cmd_cockpit
from harness.subagents.routing import (
    CANONICAL_ROUTES,
    WorkflowMode,
    WorkflowRoute,
    build_stage_transition_payload,
    format_route_briefing,
    get_route,
    list_routes,
    validate_stage_transition_payload,
)


class TestSubagentRoutingEngine(unittest.TestCase):
    """Hermetic unit tests for the unified routing engine in harness/subagents/routing.py."""

    def test_all_12_canonical_routes_present(self) -> None:
        """Asserts all 12 canonical routes (A through L) are declared and unique."""
        routes = list_routes()
        self.assertEqual(len(routes), 12)
        letters = [r.letter for r in routes]
        expected_letters = ["A", "B", "C", "D", "E", "F", "G", "H", "I", "J", "K", "L"]
        self.assertEqual(letters, expected_letters)

    def test_route_field_invariants(self) -> None:
        """Every canonical route must have complete non-empty metadata."""
        for r in list_routes():
            self.assertTrue(r.letter)
            self.assertTrue(r.alias)
            self.assertGreaterEqual(len(r.mnemonic_aliases), 1)
            self.assertTrue(r.title)
            self.assertTrue(r.starting_specialist)
            self.assertTrue(r.pipeline_route)
            self.assertIsInstance(r.mode, WorkflowMode)
            self.assertTrue(r.critical_invariants)
            self.assertTrue(r.primary_deliverable)
            self.assertTrue(r.empirical_precedent)
            self.assertGreaterEqual(len(r.stage_sequence), 1)

    def test_route_lookup_by_letter_and_alias(self) -> None:
        """Verifies get_route lookup by uppercase letter, lowercase letter, primary alias, and mnemonic alias."""
        # Letter lookups
        route_a = get_route("A")
        self.assertIsNotNone(route_a)
        self.assertEqual(route_a.alias, "rca")
        self.assertEqual(get_route("a"), route_a)

        # Primary alias lookups
        self.assertEqual(get_route("rca"), route_a)
        self.assertEqual(get_route("feature"), get_route("B"))
        self.assertEqual(get_route("laser"), get_route("C"))
        self.assertEqual(get_route("overhaul"), get_route("D"))
        self.assertEqual(get_route("heisenbug"), get_route("E"))
        self.assertEqual(get_route("victory"), get_route("J"))

        # Mnemonic aliases
        self.assertEqual(get_route("bugfix"), route_a)
        self.assertEqual(get_route("fix"), route_a)
        self.assertEqual(get_route("discovery"), get_route("G"))
        self.assertEqual(get_route("custodian"), get_route("K"))
        self.assertEqual(get_route("hotfix"), get_route("C"))
        self.assertEqual(get_route("refactor"), get_route("D"))
        self.assertEqual(get_route("dual-audit"), get_route("J"))

        # Unknown route
        self.assertIsNone(get_route("Z"))
        self.assertIsNone(get_route("nonexistent_workflow"))

    def test_build_and_validate_stage_transition_payload(self) -> None:
        """Constructs and validates compliant psl_stage_transition_payload.json."""
        payload = build_stage_transition_payload(
            task_id="TASK-P6.1",
            phase="Phase 6: Cockpit Director",
            stage="INVESTIGATION",
            status="PASS",
            sender_role="cockpit_director",
            next_recommended_stage="PLANNING",
            git_commit_hash="abc1234",
            modified_files=["harness/commands/cockpit.py"],
            added_lines=50,
            deleted_lines=2,
            contiguous_chunks_count=1,
            command="./agyis test",
            exit_code=0,
            total_tests=1600,
            passed_tests=1600,
            failed_tests=0,
            benchmark_latency_s=0.15,
            plan_path="implementation_plan.md",
            report_path="rca_report.md",
        )

        is_valid, errors = validate_stage_transition_payload(payload)
        self.assertTrue(is_valid, f"Expected valid payload, got errors: {errors}")
        self.assertEqual(payload["protocol_version"], "2026.1")
        self.assertEqual(payload["task_id"], "TASK-P6.1")
        self.assertEqual(payload["stage"], "INVESTIGATION")

    def test_validate_stage_transition_payload_catches_invalid_payload(self) -> None:
        """Validates error detection on missing required keys or invalid schema."""
        # Non-dict
        is_valid, errors = validate_stage_transition_payload("not-a-dict")
        self.assertFalse(is_valid)

        # Missing protocol_version
        bad_payload = {"task_id": "T1"}
        is_valid, errors = validate_stage_transition_payload(bad_payload)
        self.assertFalse(is_valid)
        self.assertTrue(any("Missing required key" in e for e in errors))

    def test_format_route_briefing(self) -> None:
        """Verifies formatted briefing contains header, sequence, and json dispatch template."""
        route = get_route("A")
        self.assertIsNotNone(route)
        briefing = format_route_briefing(route, task_id="TASK-BUG-42")
        self.assertIn("ROUTE A: BUG REPORT", briefing)
        self.assertIn("agyis_investigator", briefing)
        self.assertIn("TASK-BUG-42", briefing)
        self.assertIn("psl_stage_transition_payload.json", briefing)


class TestCockpitCliCommands(unittest.TestCase):
    """Hermetic CLI tests for agyis cockpit subcommands and aliases."""

    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.workspace = Path(self.temp_dir.name)

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def test_cockpit_status_plain_text(self) -> None:
        """Tests 'agyis cockpit status' standard output."""
        parser = build_parser()
        args = parser.parse_args(["cockpit", "status", "--workspace", str(self.workspace)])

        out = io.StringIO()
        with patch("sys.stdout", out):
            code = cmd_cockpit(args)

        self.assertEqual(code, 0)
        output = out.getvalue()
        self.assertIn("AGYIS COCKPIT FLIGHT DECK STATUS", output)
        self.assertIn("Proximity Zone", output)
        self.assertIn("Active Stage Role", output)
        self.assertIn("Git State", output)

    def test_cockpit_status_json_output(self) -> None:
        """Tests 'agyis cockpit status --json' structured payload."""
        parser = build_parser()
        args = parser.parse_args(["cockpit", "status", "--workspace", str(self.workspace), "--json"])

        out = io.StringIO()
        with patch("sys.stdout", out):
            code = cmd_cockpit(args)

        self.assertEqual(code, 0)
        payload = json.loads(out.getvalue())
        self.assertEqual(payload["status"], "ok")
        self.assertIn("flight_director", payload)
        self.assertIn("git", payload)
        self.assertIn("subagents", payload)

    def test_cockpit_route_valid(self) -> None:
        """Tests 'agyis cockpit route A' outputs dispatch briefing."""
        parser = build_parser()
        args = parser.parse_args(["cockpit", "route", "A", "--task-id", "TEST-TASK"])

        out = io.StringIO()
        with patch("sys.stdout", out):
            code = cmd_cockpit(args)

        self.assertEqual(code, 0)
        output = out.getvalue()
        self.assertIn("ROUTE A: BUG REPORT", output)
        self.assertIn("TEST-TASK", output)

    def test_cockpit_route_json(self) -> None:
        """Tests 'agyis cockpit route B --json' outputs structured route specification."""
        parser = build_parser()
        args = parser.parse_args(["cockpit", "route", "B", "--json"])

        out = io.StringIO()
        with patch("sys.stdout", out):
            code = cmd_cockpit(args)

        self.assertEqual(code, 0)
        payload = json.loads(out.getvalue())
        self.assertEqual(payload["status"], "ok")
        self.assertEqual(payload["letter"], "B")
        self.assertEqual(payload["alias"], "feature")
        self.assertIn("transition_payload_template", payload)

    def test_cockpit_route_unknown_fails_gracefully(self) -> None:
        """Tests unknown route letter/alias exits with code 1 and error message."""
        parser = build_parser()
        args = parser.parse_args(["cockpit", "route", "INVALID_ROUTE"])

        err = io.StringIO()
        with patch("sys.stderr", err):
            code = cmd_cockpit(args)

        self.assertEqual(code, 1)
        self.assertIn("Unknown workflow route", err.getvalue())

    def test_cockpit_verify_clean_workspace(self) -> None:
        """Tests 'agyis cockpit verify' on clean isolated directory."""
        # Create minimal git repo
        import subprocess
        subprocess.run(["git", "init"], cwd=str(self.workspace), capture_output=True, check=True)
        # Create checkpoint file
        cp_dir = self.workspace / ".agents" / "artifacts"
        cp_dir.mkdir(parents=True, exist_ok=True)
        (cp_dir / "compaction_checkpoint_latest.md").write_text("# Checkpoint", encoding="utf-8")

        parser = build_parser()
        args = parser.parse_args(["cockpit", "verify", "--workspace", str(self.workspace), "--allow-dirty"])

        out = io.StringIO()
        with patch("sys.stdout", out):
            code = cmd_cockpit(args)

        self.assertEqual(code, 0)
        output = out.getvalue()
        self.assertIn("AGYIS COCKPIT FLIGHT DECK INVARIANTS AUDIT", output)
        self.assertIn("Overall Result: PASSED", output)

    def test_router_and_ladder_aliases(self) -> None:
        """Asserts 'agyis router <route>' and 'agyis ladder <route>' route seamlessly."""
        for alias in ("router", "ladder"):
            out = io.StringIO()
            with patch("sys.stdout", out):
                code = main([alias, "builder"])
            self.assertEqual(code, 0)
            self.assertIn("ROUTE C: WELL-DEFINED SINGLE-PHASE TASK", out.getvalue())


class TestCockpitBenchmark(unittest.TestCase):
    """Verifies sub-second SLA benchmark (<0.20s) for routing and CLI invocations."""

    def test_sub_second_benchmark_sla(self) -> None:
        """Asserts complete test run for all 12 routes and status inspection finishes under 0.20s."""
        t0 = time.perf_counter()

        # 1. Inspect all 12 routes
        for r in list_routes():
            self.assertIsNotNone(get_route(r.letter))
            briefing = format_route_briefing(r)
            self.assertGreater(len(briefing), 100)

        # 2. Build and validate 50 payloads
        for i in range(50):
            p = build_stage_transition_payload(f"TASK-{i}", "Phase", "EXECUTION")
            ok, _ = validate_stage_transition_payload(p)
            self.assertTrue(ok)

        # 3. CLI dispatch
        parser = build_parser()
        args = parser.parse_args(["cockpit", "route", "A", "--json"])
        out = io.StringIO()
        with patch("sys.stdout", out):
            cmd_cockpit(args)

        elapsed = time.perf_counter() - t0
        self.assertLess(elapsed, 0.20, f"Benchmark latency exceeded SLA: {elapsed:.4f}s >= 0.20s")


class TestCockpitCheckpointScoping(unittest.TestCase):
    """Regression tests for DRIFT-P1-14: checkpoint scoping and freshness in cockpit verify."""

    def test_cockpit_verify_rejects_stale_unscoped_checkpoint(self) -> None:
        import os
        import time as _time
        from harness.commands.cockpit import _audit_flight_director_invariants

        with tempfile.TemporaryDirectory() as tmp:
            ws = Path(tmp)
            cp_dir = ws / ".agents" / "artifacts" / "checkpoints"
            cp_dir.mkdir(parents=True, exist_ok=True)
            stale_cp = cp_dir / "unrelated-session-uuid.md"
            stale_cp.write_text("# Old Checkpoint", encoding="utf-8")
            old_ts = _time.time() - 90000
            os.utime(stale_cp, (old_ts, old_ts))

            with patch.dict(os.environ, {"ANTIGRAVITY_CONVERSATION_ID": "active-session-uuid"}):
                _, results = _audit_flight_director_invariants(ws, allow_dirty=True)
                inv4 = next(r for r in results if r["invariant"] == "Active Checkpoint Availability")
                self.assertFalse(inv4["passed"])

                # Now write fresh session-scoped checkpoint
                fresh_cp = cp_dir / "active-session-uuid.md"
                fresh_cp.write_text("# Fresh Checkpoint", encoding="utf-8")
                _, results2 = _audit_flight_director_invariants(ws, allow_dirty=True)
                inv4_2 = next(r for r in results2 if r["invariant"] == "Active Checkpoint Availability")
                self.assertTrue(inv4_2["passed"])

    def test_checkpoint_prefers_scoped_and_recent_over_stale_legacy(self) -> None:
        """_get_active_checkpoint_info prefers scoped/recent checkpoints/*.md before stale legacy global files."""
        import os
        import time as _time
        from harness.commands.cockpit import _get_active_checkpoint_info

        with tempfile.TemporaryDirectory() as tmp:
            ws = Path(tmp)
            art_dir = ws / ".agents" / "artifacts"
            cp_dir = art_dir / "checkpoints"
            cp_dir.mkdir(parents=True, exist_ok=True)

            stale_legacy = art_dir / "cockpit_checkpoint.md"
            stale_legacy.write_text("# Stale Legacy", encoding="utf-8")
            old_ts = _time.time() - 86400
            os.utime(stale_legacy, (old_ts, old_ts))

            recent_cp = cp_dir / "other-recent-root.md"
            recent_cp.write_text("# Recent Checkpoint", encoding="utf-8")

            # Without matching conv_id (e.g. conv_id=None), fresher recent cp_dir/*.md beats stale legacy
            with patch.dict(os.environ, {"AGYIS_HARNESS_STATE_DIR": str(ws / "state")}, clear=False):
                os.environ.pop("ANTIGRAVITY_CONVERSATION_ID", None)
                os.environ.pop("CONVERSATION_ID", None)
                os.environ.pop("AGYIS_CONVERSATION_ID", None)
                info_recent = _get_active_checkpoint_info(ws, conv_id=None)
                self.assertTrue(info_recent["exists"])
                self.assertTrue(info_recent["is_fresh"])
                self.assertEqual(Path(info_recent["path"]), recent_cp)

            # With explicit conv_id whose own file exists, scoped cp_dir/<cid>.md wins unconditionally
            scoped_cp = cp_dir / "root-session-123.md"
            scoped_cp.write_text("# Scoped Checkpoint", encoding="utf-8")
            older_ts = _time.time() - 600
            os.utime(scoped_cp, (older_ts, older_ts))
            info_scoped = _get_active_checkpoint_info(ws, conv_id="root-session-123")
            self.assertTrue(info_scoped["exists"])
            self.assertTrue(info_scoped["scoped_to_session"])
            self.assertEqual(Path(info_scoped["path"]), scoped_cp)

    def test_cockpit_invariants_exclude_backups_and_scratch_teamwork_dirs(self) -> None:
        """cockpit verify ignores .agents/teamwork/backups/ and scratch/ while catching real teamwork dispatches."""
        from harness.commands.cockpit import _audit_flight_director_invariants

        with tempfile.TemporaryDirectory() as tmp:
            ws = Path(tmp)
            app_dir = ws / "app"
            (app_dir / "brain").mkdir(parents=True)
            art_dir = ws / ".agents" / "artifacts"
            art_dir.mkdir(parents=True)
            (art_dir / "compaction_checkpoint_latest.md").write_text("# Checkpoint", encoding="utf-8")

            tw_dir = ws / ".agents" / "teamwork"
            backup_dir = tw_dir / "backups" / "powerloss_20261126"
            backup_dir.mkdir(parents=True)
            (backup_dir / "git_diff_backup.patch").write_text("diff --git a/a b/a\n", encoding="utf-8")
            (tw_dir / "scratch").mkdir(parents=True)
            (tw_dir / "scratch" / "probe.txt").write_text("tmp", encoding="utf-8")

            with patch.dict(os.environ, {"ANTIGRAVITY_APP_DATA_DIR": str(app_dir)}, clear=False):
                _, results = _audit_flight_director_invariants(ws, allow_dirty=False)
                inv5 = next(r for r in results if r["invariant"] == "Subagent Cognitive Health")
                self.assertTrue(inv5["passed"], f"backups/scratch falsely triggered truth check: {inv5}")
                self.assertEqual(inv5["violations"], [])

                # Adding a real teamwork task dir triggers transition payload truth check
                real_dir = tw_dir / "squad_1"
                real_dir.mkdir(parents=True)
                (real_dir / "DISPATCH.md").write_text("# Squad 1", encoding="utf-8")
                _, results_real = _audit_flight_director_invariants(ws, allow_dirty=False)
                inv5_real = next(r for r in results_real if r["invariant"] == "Subagent Cognitive Health")
                self.assertFalse(inv5_real["passed"])
                self.assertTrue(any("Missing stage transition payload" in v for v in inv5_real["violations"]))


if __name__ == "__main__":
    unittest.main()
