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


if __name__ == "__main__":
    unittest.main()
