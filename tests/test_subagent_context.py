#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Purrfect Software Limited (PSL)

"""
Unit tests for Zero-Token Subagent Context Estimator & Health Gauge (ADR-025).

Validates:
- SubagentContextStatus schema
- classify_context_health boundary thresholds
- estimate_subagent_context streaming & size-heuristic fallback
- Latency guarantees (<5ms)
- list_active_subagent_statuses discovery
"""

from __future__ import annotations

import json
from pathlib import Path
import tempfile
import time
import unittest

from harness.subagents import (
    SubagentContextStatus,
    classify_context_health,
    estimate_subagent_context,
    list_active_subagent_statuses,
)


class TestSubagentContext(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.tmp = Path(self.temp_dir.name)

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def test_classify_context_health_boundaries(self) -> None:
        """Assert exact boundary conditions for HEALTHY, AMBER, and RED_ALERT."""
        # HEALTHY (<40k tokens AND <40 steps)
        self.assertEqual(classify_context_health(0, 0), ("HEALTHY", "REUSE"))
        self.assertEqual(classify_context_health(39_999, 39), ("HEALTHY", "REUSE"))

        # AMBER (40k-80k tokens OR 40-80 steps)
        self.assertEqual(classify_context_health(40_000, 10), ("AMBER", "COMPACT_RECREATE"))
        self.assertEqual(classify_context_health(10_000, 40), ("AMBER", "COMPACT_RECREATE"))
        self.assertEqual(classify_context_health(80_000, 80), ("AMBER", "COMPACT_RECREATE"))

        # RED_ALERT (>80k tokens OR >80 steps)
        self.assertEqual(classify_context_health(80_001, 10), ("RED_ALERT", "RETIRE"))
        self.assertEqual(classify_context_health(10_000, 81), ("RED_ALERT", "RETIRE"))
        self.assertEqual(classify_context_health(150_000, 150), ("RED_ALERT", "RETIRE"))

    def test_estimate_subagent_context_healthy(self) -> None:
        """Transcripts <40k tokens and <40 steps evaluate to HEALTHY and REUSE."""
        t_path = self.tmp / "transcript.jsonl"
        lines = []
        for i in range(10):
            step = {
                "step_index": i,
                "role": "harness_builder",
                "content": f"Step content number {i} " + ("x" * 300),
            }
            lines.append(json.dumps(step))
        t_path.write_text("\n".join(lines), encoding="utf-8")

        status = estimate_subagent_context(t_path)
        self.assertIsInstance(status, SubagentContextStatus)
        self.assertEqual(status.health_zone, "HEALTHY")
        self.assertEqual(status.recommendation, "REUSE")
        self.assertEqual(status.step_count, 10)
        self.assertEqual(status.role, "harness_builder")
        self.assertLess(status.latency_ms, 5.0)

    def test_estimate_subagent_context_amber_by_steps(self) -> None:
        """Transcripts >=40 steps evaluate to AMBER and COMPACT_RECREATE."""
        t_path = self.tmp / "transcript.jsonl"
        lines = [
            json.dumps({"step_index": i, "content": f"Brief step {i}"})
            for i in range(45)
        ]
        t_path.write_text("\n".join(lines), encoding="utf-8")

        status = estimate_subagent_context(t_path)
        self.assertEqual(status.health_zone, "AMBER")
        self.assertEqual(status.recommendation, "COMPACT_RECREATE")
        self.assertEqual(status.step_count, 45)
        self.assertLess(status.latency_ms, 5.0)

    def test_estimate_subagent_context_amber_by_tokens(self) -> None:
        """Transcripts >=40k tokens evaluate to AMBER and COMPACT_RECREATE."""
        t_path = self.tmp / "transcript.jsonl"
        lines = [
            json.dumps({"step_index": i, "content": "a" * 20_000})
            for i in range(10)
        ]
        t_path.write_text("\n".join(lines), encoding="utf-8")

        status = estimate_subagent_context(t_path)
        self.assertEqual(status.health_zone, "AMBER")
        self.assertEqual(status.recommendation, "COMPACT_RECREATE")
        self.assertGreaterEqual(status.token_count, 40_000)
        self.assertLess(status.latency_ms, 5.0)

    def test_estimate_subagent_context_red_alert_by_steps(self) -> None:
        """Transcripts >80 steps evaluate to RED_ALERT and RETIRE."""
        t_path = self.tmp / "transcript.jsonl"
        lines = [
            json.dumps({"step_index": i, "content": f"Step {i}"})
            for i in range(85)
        ]
        t_path.write_text("\n".join(lines), encoding="utf-8")

        status = estimate_subagent_context(t_path)
        self.assertEqual(status.health_zone, "RED_ALERT")
        self.assertEqual(status.recommendation, "RETIRE")
        self.assertEqual(status.step_count, 85)
        self.assertLess(status.latency_ms, 5.0)

    def test_estimate_subagent_context_red_alert_by_tokens(self) -> None:
        """Transcripts >80k tokens evaluate to RED_ALERT and RETIRE."""
        t_path = self.tmp / "transcript.jsonl"
        lines = [
            json.dumps({"step_index": i, "content": "z" * 36_000})
            for i in range(10)
        ]
        t_path.write_text("\n".join(lines), encoding="utf-8")

        status = estimate_subagent_context(t_path)
        self.assertEqual(status.health_zone, "RED_ALERT")
        self.assertEqual(status.recommendation, "RETIRE")
        self.assertGreater(status.token_count, 80_000)
        self.assertLess(status.latency_ms, 5.0)

    def test_estimate_subagent_context_size_heuristic_fallback(self) -> None:
        """Files >2MB trigger fast size-stat heuristic without full line parsing."""
        t_path = self.tmp / "titan_transcript.jsonl"
        head_step = json.dumps({
            "step_index": 0,
            "conversation_id": "titan-conv-1234",
            "content": "You are ladder_executioner, titan session implementer",
        })
        with open(t_path, "w", encoding="utf-8") as f:
            f.write(head_step + "\n")
            f.seek(2 * 1024 * 1024 + 1024)
            f.write("x\n")

        self.assertGreater(t_path.stat().st_size, 2 * 1024 * 1024)

        t0 = time.perf_counter()
        status = estimate_subagent_context(t_path)
        duration_ms = (time.perf_counter() - t0) * 1000.0

        self.assertEqual(status.conversation_id, "titan-conv-1234")
        self.assertEqual(status.role, "ladder_executioner")
        self.assertEqual(status.health_zone, "RED_ALERT")
        self.assertEqual(status.recommendation, "RETIRE")
        self.assertGreater(status.token_count, 80_000)
        self.assertGreater(status.step_count, 80)
        self.assertLess(duration_ms, 5.0)
        self.assertLess(status.latency_ms, 5.0)

    def test_estimate_subagent_context_missing_or_empty_file(self) -> None:
        """Missing or empty files return safe default healthy status."""
        missing = self.tmp / "non_existent.jsonl"
        status = estimate_subagent_context(missing)
        self.assertEqual(status.step_count, 0)
        self.assertEqual(status.token_count, 0)
        self.assertEqual(status.health_zone, "HEALTHY")
        self.assertEqual(status.recommendation, "REUSE")
        self.assertLess(status.latency_ms, 5.0)

        empty = self.tmp / "empty.jsonl"
        empty.touch()
        status_empty = estimate_subagent_context(empty)
        self.assertEqual(status_empty.step_count, 0)
        self.assertEqual(status_empty.token_count, 0)

    def test_role_extraction_patterns(self) -> None:
        """Extracts subagent roles across prompt patterns."""
        cases = [
            ("You are ladder_executioner, the Stage 2 Executioner", "ladder_executioner"),
            ("You are the Stage 3 Hammer for Phase 3", "Stage 3 Hammer"),
            ("You are the Stage 4 Auditor for Phase 3", "Stage 4 Auditor"),
            ("You are harness_auditor, the dedicated QA Verifier", "harness_auditor"),
            ("You are harness_builder, the dedicated Executioner", "harness_builder"),
            ("You are harness_reviewer, the dedicated Hammer", "harness_reviewer"),
        ]
        for prompt, expected_role in cases:
            t = self.tmp / f"role_{expected_role.replace(' ', '_')}.jsonl"
            t.write_text(json.dumps({"step_index": 0, "content": prompt}))
            status = estimate_subagent_context(t)
            self.assertEqual(status.role, expected_role)

    def test_generic_message_role_masking(self) -> None:
        """Generic message roles ('user', 'assistant', etc.) do not mask subagent role extraction."""
        t_path = self.tmp / "masked_user_role.jsonl"
        line = json.dumps({
            "role": "user",
            "content": "You are harness_builder, working on task implementation",
        })
        t_path.write_text(line, encoding="utf-8")
        status = estimate_subagent_context(t_path)
        self.assertEqual(status.role, "harness_builder")

        # Verify fallback path with titan files also unmasks generic role
        t_titan = self.tmp / "masked_titan_role.jsonl"
        with open(t_titan, "w", encoding="utf-8") as f:
            f.write(line + "\n")
            f.seek(2 * 1024 * 1024 + 1024)
            f.write("x\n")
        status_titan = estimate_subagent_context(t_titan)
        self.assertEqual(status_titan.role, "harness_builder")

    def test_list_active_subagent_statuses(self) -> None:
        """list_active_subagent_statuses scans custom brain directory."""
        mock_brain = self.tmp / "brain"
        mock_brain.mkdir()

        self.assertEqual(list_active_subagent_statuses(self.tmp / "missing"), [])

        sub1 = mock_brain / "sub-1-builder"
        sub1_logs = sub1 / ".system_generated" / "logs"
        sub1_logs.mkdir(parents=True)
        (sub1_logs / "transcript.jsonl").write_text(
            json.dumps({"step_index": 0, "content": "You are harness_builder, working on task"})
        )

        sub2 = mock_brain / "sub-2-reviewer"
        sub2.mkdir()
        (sub2 / "transcript.jsonl").write_text(
            "\n".join([
                json.dumps({"step_index": i, "content": f"You are harness_reviewer reviewing step {i}"})
                for i in range(50)
            ])
        )

        statuses = list_active_subagent_statuses(brain_dir=mock_brain)
        self.assertEqual(len(statuses), 2)
        roles = {s.role for s in statuses}
        self.assertEqual(roles, {"harness_builder", "harness_reviewer"})

        zones = {s.health_zone for s in statuses}
        self.assertIn("HEALTHY", zones)
        self.assertIn("AMBER", zones)


if __name__ == "__main__":
    unittest.main()
