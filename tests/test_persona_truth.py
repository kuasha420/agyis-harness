# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Arafat Zahan (@kuasha420)
# Corporate Stewardship & Infrastructure: Purrfect Software Limited (PSL)
# Governed by: ICARO-42/b Ordinance (Company-Supported Personal IP Framework)

"""
Hermetic Unit Tests for Persona Truth Enforcement & Anti-Code-Monkey Invariant (Issue #72).
Verifies:
- validate_transition_payload_truth schema & invariants
- evaluate_stop completion fence truth gate & anti-deadlock
- check_ledger_persona_truth anti-drift ledger milestone gate
- Sub-second benchmark SLA (<0.05s)
"""

from __future__ import annotations

import json
import os
from pathlib import Path
import tempfile
import time
import unittest
from unittest.mock import patch

from harness.hooks.anti_drift_hook import check_ledger_persona_truth
from harness.hooks.completion_fence_hook import evaluate_stop, save_state
from harness.subagents.routing import build_stage_transition_payload
from harness.subagents.truth import validate_transition_payload_truth


class TestPersonaTruthValidation(unittest.TestCase):
    """Test suite for validate_transition_payload_truth engine."""

    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.workspace = Path(self.temp_dir.name)
        self.brain = self.workspace / ".brain"
        self.brain.mkdir(parents=True, exist_ok=True)
        self.env_patch = patch.dict(os.environ, {"ANTIGRAVITY_BRAIN_DIR": str(self.brain)})
        self.env_patch.start()
        (self.workspace / ".agents" / "artifacts").mkdir(parents=True, exist_ok=True)
        (self.workspace / ".agents" / "teamwork").mkdir(parents=True, exist_ok=True)

    def tearDown(self) -> None:
        self.env_patch.stop()
        self.temp_dir.cleanup()

    def test_missing_payload_fails(self) -> None:
        valid, errors = validate_transition_payload_truth(self.workspace)
        self.assertFalse(valid)
        self.assertTrue(any("Missing stage transition payload" in err for err in errors))

    def test_status_not_pass_fails(self) -> None:
        plan_file = self.workspace / "plan.md"
        plan_file.write_text("# Plan", encoding="utf-8")
        payload = build_stage_transition_payload(
            task_id="TASK-1",
            phase="Phase 1",
            stage="BUILD",
            status="FAIL",
            plan_path=str(plan_file),
            exit_code=0,
            total_tests=10,
            passed_tests=10,
            failed_tests=0,
        )
        payload_file = self.workspace / "psl_stage_transition_payload.json"
        payload_file.write_text(json.dumps(payload), encoding="utf-8")

        valid, errors = validate_transition_payload_truth(self.workspace)
        self.assertFalse(valid)
        self.assertTrue(any("status must be 'PASS'" in err for err in errors))

    def test_verification_exit_code_and_failures(self) -> None:
        plan_file = self.workspace / "plan.md"
        plan_file.write_text("# Plan", encoding="utf-8")

        # exit_code != 0
        payload = build_stage_transition_payload(
            task_id="TASK-1",
            phase="Phase 1",
            stage="BUILD",
            status="PASS",
            plan_path=str(plan_file),
            exit_code=1,
            total_tests=10,
            passed_tests=9,
            failed_tests=1,
        )
        payload_file = self.workspace / "psl_stage_transition_payload.json"
        payload_file.write_text(json.dumps(payload), encoding="utf-8")

        valid, errors = validate_transition_payload_truth(self.workspace)
        self.assertFalse(valid)
        self.assertTrue(any("exit_code must be 0" in err for err in errors))
        self.assertTrue(any("failed tests" in err for err in errors))

    def test_missing_referenced_artifact_fails(self) -> None:
        payload = build_stage_transition_payload(
            task_id="TASK-1",
            phase="Phase 1",
            stage="BUILD",
            status="PASS",
            plan_path="non_existent_plan.md",
            exit_code=0,
            total_tests=10,
            passed_tests=10,
            failed_tests=0,
        )
        payload_file = self.workspace / "psl_stage_transition_payload.json"
        payload_file.write_text(json.dumps(payload), encoding="utf-8")

        valid, errors = validate_transition_payload_truth(self.workspace)
        self.assertFalse(valid)
        self.assertTrue(any("does not exist on disk" in err for err in errors))

    def test_dead_or_stale_delegate_fails(self) -> None:
        plan_file = self.workspace / "plan.md"
        plan_file.write_text("# Plan", encoding="utf-8")
        payload = build_stage_transition_payload(
            task_id="TASK-1",
            phase="Phase 1",
            stage="BUILD",
            status="PASS",
            plan_path=str(plan_file),
            exit_code=0,
            total_tests=10,
            passed_tests=10,
            failed_tests=0,
        )
        payload_file = self.workspace / "psl_stage_transition_payload.json"
        payload_file.write_text(json.dumps(payload), encoding="utf-8")

        # Add dead delegate
        worker_dir = self.workspace / ".agents" / "teamwork" / "builder_worker"
        worker_dir.mkdir(parents=True, exist_ok=True)
        prog = worker_dir / "progress.md"
        prog.write_text("- Last visited: 2026-01-01T00:00:00Z\n", encoding="utf-8")

        valid, errors = validate_transition_payload_truth(self.workspace)
        self.assertFalse(valid)
        self.assertTrue(any("in DEAD state" in err or "in STALE state" in err for err in errors))

    def test_valid_payload_and_healthy_delegate_passes(self) -> None:
        plan_file = self.workspace / "plan.md"
        plan_file.write_text("# Plan", encoding="utf-8")
        payload = build_stage_transition_payload(
            task_id="TASK-1",
            phase="Phase 1",
            stage="BUILD",
            status="PASS",
            plan_path=str(plan_file),
            exit_code=0,
            total_tests=10,
            passed_tests=10,
            failed_tests=0,
        )
        payload_file = self.workspace / "psl_stage_transition_payload.json"
        payload_file.write_text(json.dumps(payload), encoding="utf-8")

        # Healthy delegate with fresh heartbeat
        worker_dir = self.workspace / ".agents" / "teamwork" / "builder_worker"
        worker_dir.mkdir(parents=True, exist_ok=True)
        prog = worker_dir / "progress.md"
        now_iso = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        prog.write_text(f"- Last visited: {now_iso}\n", encoding="utf-8")

        valid, errors = validate_transition_payload_truth(self.workspace)
        self.assertTrue(valid)
        self.assertEqual(errors, [])


class TestCompletionFenceTruthGate(unittest.TestCase):
    """Test suite for evaluate_stop subagent truth verification."""

    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.workspace = Path(self.temp_dir.name)
        self.brain = self.workspace / ".brain"
        self.brain.mkdir(parents=True, exist_ok=True)
        self.env_patch = patch.dict(os.environ, {"ANTIGRAVITY_BRAIN_DIR": str(self.brain)})
        self.env_patch.start()
        self.state_dir = self.workspace / ".state"
        self.state_dir.mkdir(parents=True, exist_ok=True)

    def tearDown(self) -> None:
        self.env_patch.stop()
        self.temp_dir.cleanup()

    def test_orchestrator_denied_when_subagents_dispatched_without_payload(self) -> None:
        worker_dir = self.workspace / ".agents" / "teamwork" / "builder_worker"
        worker_dir.mkdir(parents=True, exist_ok=True)
        prog = worker_dir / "progress.md"
        prog.write_text("- Last visited: 2026-01-01T00:00:00Z\n", encoding="utf-8")

        payload = {"role": "agyis_coordinator"}
        res1 = evaluate_stop(
            conv_id="test_truth",
            state_dir=self.state_dir,
            cwd=self.workspace,
            payload=payload,
        )
        self.assertEqual(res1["decision"], "continue")
        self.assertIn("Persona Truth Violation", res1["reason"])
        self.assertIn("Anti-Code-Monkey Invariant", res1["reason"])

        # Second block
        res2 = evaluate_stop(
            conv_id="test_truth",
            state_dir=self.state_dir,
            cwd=self.workspace,
            payload=payload,
        )
        self.assertEqual(res2["decision"], "continue")

        # Third block trips anti-deadlock valve
        res3 = evaluate_stop(
            conv_id="test_truth",
            state_dir=self.state_dir,
            cwd=self.workspace,
            payload=payload,
        )
        self.assertEqual(res3["decision"], "allow")
        self.assertIn("Anti-deadlock valve tripped", res3.get("warning", ""))

    def test_orchestrator_allowed_when_verified_payload_present(self) -> None:
        plan_file = self.workspace / "plan.md"
        plan_file.write_text("# Plan", encoding="utf-8")
        tr_payload = build_stage_transition_payload(
            task_id="TASK-1",
            phase="Phase 1",
            stage="BUILD",
            status="PASS",
            plan_path=str(plan_file),
            exit_code=0,
            total_tests=10,
            passed_tests=10,
            failed_tests=0,
        )
        payload_file = self.workspace / "psl_stage_transition_payload.json"
        payload_file.write_text(json.dumps(tr_payload), encoding="utf-8")

        worker_dir = self.workspace / ".agents" / "teamwork" / "builder_worker"
        worker_dir.mkdir(parents=True, exist_ok=True)
        prog = worker_dir / "progress.md"
        now_iso = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        prog.write_text(f"- Last visited: {now_iso}\n", encoding="utf-8")

        payload = {"role": "agyis_coordinator"}
        res = evaluate_stop(
            conv_id="test_truth_ok",
            state_dir=self.state_dir,
            cwd=self.workspace,
            payload=payload,
        )
        self.assertEqual(res["decision"], "allow")


class TestAntiDriftLedgerGate(unittest.TestCase):
    """Test suite for check_ledger_persona_truth validator."""

    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.workspace = Path(self.temp_dir.name)
        self.brain = self.workspace / ".brain"
        self.brain.mkdir(parents=True, exist_ok=True)
        self.env_patch = patch.dict(os.environ, {"ANTIGRAVITY_BRAIN_DIR": str(self.brain)})
        self.env_patch.start()

    def tearDown(self) -> None:
        self.env_patch.stop()
        self.temp_dir.cleanup()

    def test_ledger_modification_denied_on_dead_subagent(self) -> None:
        worker_dir = self.workspace / ".agents" / "teamwork" / "builder_worker"
        worker_dir.mkdir(parents=True, exist_ok=True)
        prog = worker_dir / "progress.md"
        prog.write_text("- Last visited: 2026-01-01T00:00:00Z\n", encoding="utf-8")

        block = check_ledger_persona_truth(
            target_file="docs/taxonomy/project-ledger.md",
            content="## Phase 25 Complete",
            workspace=self.workspace,
        )
        self.assertIsNotNone(block)
        self.assertEqual(block.get("decision"), "deny")
        self.assertIn("Persona Truth Violation", block.get("reason", ""))
        self.assertIn("Anti-Code-Monkey Invariant", block.get("reason", ""))

    def test_ledger_modification_allowed_when_subagents_healthy(self) -> None:
        worker_dir = self.workspace / ".agents" / "teamwork" / "builder_worker"
        worker_dir.mkdir(parents=True, exist_ok=True)
        prog = worker_dir / "progress.md"
        now_iso = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        prog.write_text(f"- Last visited: {now_iso}\n", encoding="utf-8")

        block = check_ledger_persona_truth(
            target_file="docs/taxonomy/project-ledger.md",
            content="## Phase 25 Complete",
            workspace=self.workspace,
        )
        self.assertIsNone(block)


class TestPersonaTruthBenchmarkSLA(unittest.TestCase):
    """Asserts sub-second benchmark SLA (<0.05s) for truth validation."""

    def test_benchmark_sla(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            ws = Path(tmp)
            plan_file = ws / "plan.md"
            plan_file.write_text("# Plan", encoding="utf-8")
            payload = build_stage_transition_payload(
                task_id="BENCHMARK",
                phase="Phase Bench",
                stage="BUILD",
                status="PASS",
                plan_path=str(plan_file),
                exit_code=0,
                total_tests=5,
                passed_tests=5,
                failed_tests=0,
            )
            payload_file = ws / "psl_stage_transition_payload.json"
            payload_file.write_text(json.dumps(payload), encoding="utf-8")

            t0 = time.perf_counter()
            for _ in range(25):
                valid, errors = validate_transition_payload_truth(ws, allow_synthetic=True)
                self.assertTrue(valid)
            elapsed = time.perf_counter() - t0
            self.assertLess(elapsed, 0.05, f"Expected 25 iterations in <0.05s, got {elapsed:.4f}s")


if __name__ == "__main__":
    unittest.main()
