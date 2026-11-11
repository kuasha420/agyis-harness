#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Arafat Zahan (@kuasha420)
# Corporate Stewardship & Infrastructure: Purrfect Software Limited (PSL)
# Governed by: ICARO-42/b Ordinance (Company-Supported Personal IP Framework)

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
        """Assert window-scaled boundary conditions for HEALTHY, AMBER, and RED_ALERT."""
        # HEALTHY (<65% fill of 256k window AND <80 epoch steps)
        self.assertEqual(classify_context_health(0, 0), ("HEALTHY", "REUSE"))
        self.assertEqual(classify_context_health(39_999, 39), ("HEALTHY", "REUSE"))
        self.assertEqual(classify_context_health(166_399, 79), ("HEALTHY", "REUSE"))

        # AMBER (65%-80% fill OR >=80 epoch steps while <80% fill)
        self.assertEqual(classify_context_health(166_400, 10), ("AMBER", "COMPACT_SOON"))
        self.assertEqual(classify_context_health(10_000, 80), ("AMBER", "COMPACT_SOON"))
        self.assertEqual(classify_context_health(204_799, 95), ("AMBER", "COMPACT_SOON"))

        # RED_ALERT (>=80% fill of window, >=204,800 at 256k)
        self.assertEqual(classify_context_health(204_800, 10), ("RED_ALERT", "HANDOFF_OR_COMPACT"))
        self.assertEqual(classify_context_health(230_000, 150), ("RED_ALERT", "HANDOFF_OR_COMPACT"))

        # Scales proportionally on 1M context windows
        self.assertEqual(classify_context_health(500_000, 20, max_context_tokens=1_000_000), ("HEALTHY", "REUSE"))
        self.assertEqual(classify_context_health(650_000, 20, max_context_tokens=1_000_000), ("AMBER", "COMPACT_SOON"))
        self.assertEqual(classify_context_health(800_000, 20, max_context_tokens=1_000_000), ("RED_ALERT", "HANDOFF_OR_COMPACT"))

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
        """Transcripts >=80 active-epoch steps evaluate to AMBER and COMPACT_SOON."""
        t_path = self.tmp / "transcript.jsonl"
        lines = [
            json.dumps({"step_index": i, "content": f"Brief step {i}"})
            for i in range(85)
        ]
        t_path.write_text("\n".join(lines), encoding="utf-8")

        status = estimate_subagent_context(t_path)
        self.assertEqual(status.health_zone, "AMBER")
        self.assertEqual(status.recommendation, "COMPACT_SOON")
        self.assertEqual(status.step_count, 85)
        self.assertLess(status.latency_ms, 5.0)

    def test_estimate_subagent_context_amber_by_tokens(self) -> None:
        """Transcripts >=65% and <80% window fill evaluate to AMBER and COMPACT_SOON."""
        t_path = self.tmp / "transcript.jsonl"
        lines = [
            json.dumps({"step_index": i, "token_count": 17_000, "content": "ok"})
            for i in range(10)
        ]
        t_path.write_text("\n".join(lines), encoding="utf-8")

        status = estimate_subagent_context(t_path)
        self.assertEqual(status.health_zone, "AMBER")
        self.assertEqual(status.recommendation, "COMPACT_SOON")
        self.assertEqual(status.token_count, 170_000)
        self.assertLess(status.latency_ms, 5.0)

    def test_estimate_subagent_context_below_horizon_remains_healthy(self) -> None:
        """Transcripts at 45 steps and <65% tokens stay HEALTHY (no premature 40-step retirement)."""
        t_path = self.tmp / "transcript.jsonl"
        lines = [
            json.dumps({"step_index": i, "content": f"Step {i}"})
            for i in range(45)
        ]
        t_path.write_text("\n".join(lines), encoding="utf-8")

        status = estimate_subagent_context(t_path)
        self.assertEqual(status.health_zone, "HEALTHY")
        self.assertEqual(status.recommendation, "REUSE")
        self.assertEqual(status.step_count, 45)
        self.assertLess(status.latency_ms, 5.0)

    def test_estimate_subagent_context_red_alert_by_tokens(self) -> None:
        """Transcripts >=80% window fill evaluate to RED_ALERT and HANDOFF_OR_COMPACT."""
        t_path = self.tmp / "transcript.jsonl"
        lines = [
            json.dumps({"step_index": i, "token_count": 21_000, "content": "active"})
            for i in range(10)
        ]
        t_path.write_text("\n".join(lines), encoding="utf-8")

        status = estimate_subagent_context(t_path)
        self.assertEqual(status.health_zone, "RED_ALERT")
        self.assertEqual(status.recommendation, "HANDOFF_OR_COMPACT")
        self.assertEqual(status.token_count, 210_000)
        self.assertLess(status.latency_ms, 5.0)

    def test_estimate_subagent_context_size_heuristic_fallback(self) -> None:
        """Files >2MB read bounded head/tail steps quickly without bogus file_size // 4 inflation."""
        t_path = self.tmp / "titan_transcript.jsonl"
        head_step = json.dumps({
            "step_index": 0,
            "conversation_id": "titan-conv-1234",
            "content": "You are ladder_executioner, titan session implementer",
        })
        tail_step = json.dumps({
            "step_index": 200,
            "token_count": 215_000,
            "content": "Final active tail step",
        })
        with open(t_path, "w", encoding="utf-8") as f:
            f.write(head_step + "\n")
            f.seek(2 * 1024 * 1024 + 1024)
            f.write("\n" + tail_step + "\n")

        self.assertGreater(t_path.stat().st_size, 2 * 1024 * 1024)

        t0 = time.perf_counter()
        status = estimate_subagent_context(t_path)
        duration_ms = (time.perf_counter() - t0) * 1000.0

        self.assertEqual(status.conversation_id, "titan-conv-1234")
        self.assertEqual(status.role, "ladder_executioner")
        self.assertEqual(status.health_zone, "RED_ALERT")
        self.assertEqual(status.recommendation, "HANDOFF_OR_COMPACT")
        self.assertEqual(status.token_count, 215_000)
        self.assertLess(duration_ms, 10.0)
        self.assertLess(status.latency_ms, 10.0)

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
                for i in range(85)
            ])
        )

        statuses = list_active_subagent_statuses(brain_dir=mock_brain)
        self.assertEqual(len(statuses), 2)
        roles = {s.role for s in statuses}
        self.assertEqual(roles, {"harness_builder", "harness_reviewer"})

        zones = {s.health_zone for s in statuses}
        self.assertIn("HEALTHY", zones)
        self.assertIn("AMBER", zones)

    def test_list_active_subagent_statuses_strict_parent_filtering(self) -> None:
        """Issue #111: root_conv_id excludes other parents' children, orphans, and completed subagents."""
        mock_brain = self.tmp / "scoped_brain"
        mock_brain.mkdir()

        def _write_child(cid: str, parent_cid: str | None, completed: bool = False) -> None:
            logs = mock_brain / cid / ".system_generated" / "logs"
            logs.mkdir(parents=True)
            rows = [{"step_index": 0, "conversation_id": cid, "content": "You are agyis_builder"}]
            if parent_cid is not None:
                rows[0]["parent_conversation_id"] = parent_cid
            if completed:
                rows.append({"step_index": 1, "status": "DONE", "type": "PLANNER_RESPONSE", "content": "Done"})
            (logs / "transcript.jsonl").write_text("\n".join(json.dumps(r) for r in rows), encoding="utf-8")

        _write_child("child-a-active", "parent-a", completed=False)
        _write_child("child-a-done", "parent-a", completed=True)
        _write_child("child-b-active", "parent-b", completed=False)
        _write_child("orphan-active", None, completed=False)
        _write_child("child-foreign", "parent-b", completed=False)

        parent_logs = mock_brain / "parent-a" / ".system_generated" / "logs"
        parent_logs.mkdir(parents=True)
        (parent_logs / "transcript.jsonl").write_text(
            json.dumps({
                "step_index": 0,
                "tool_calls": [{"name": "invoke_subagent", "args": {"Role": "agyis_builder"}}],
                "content": "spawned child-foreign",
            })
            + "\n"
            + json.dumps({
                "step_index": 1,
                "content": "Subagent conversationId: child-foreign",
            }),
            encoding="utf-8",
        )

        active = list_active_subagent_statuses(brain_dir=mock_brain, root_conv_id="parent-a")
        self.assertEqual([s.conversation_id for s in active], ["child-a-active"])

    def test_parent_conversation_id_extraction(self) -> None:
        """estimate_subagent_context extracts parent_conversation_id from transcript."""
        # 1. Direct parent_conversation_id
        t_path = self.tmp / "subagent_parent.jsonl"
        line1 = json.dumps({
            "conversation_id": "child-conv-123",
            "parent_conversation_id": "parent-root-456",
            "content": "You are agyis_builder executing plan",
        })
        t_path.write_text(line1, encoding="utf-8")
        status = estimate_subagent_context(t_path)
        self.assertEqual(status.conversation_id, "child-conv-123")
        self.assertEqual(status.parent_conversation_id, "parent-root-456")

        # 2. _meta root_conversation_id
        t_path_meta = self.tmp / "subagent_meta.jsonl"
        line2 = json.dumps({
            "conversation_id": "child-conv-789",
            "_meta": {"antigravity.google/root_conversation_id": "root-meta-999"},
            "content": "You are agyis_reviewer auditing code",
        })
        t_path_meta.write_text(line2, encoding="utf-8")
        status_meta = estimate_subagent_context(t_path_meta)
        self.assertEqual(status_meta.conversation_id, "child-conv-789")
        self.assertEqual(status_meta.parent_conversation_id, "root-meta-999")


class TestSubagentLargeTranscriptBoundedScan(unittest.TestCase):
    """#110.2: Reverse chunked scan locates checkpoints beyond 256 KB without loading full file."""

    def test_reverse_chunk_scan_stops_at_checkpoint_beyond_256kb(self):
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "transcript.jsonl"
            pre_line = json.dumps({
                "type": "PLANNER_RESPONSE",
                "content": "OLD_PRE_COMPACT_" + ("x" * 10000),
            }) + "\n"
            cp_line = json.dumps({
                "type": "CHECKPOINT",
                "content": "<CONTEXT_SUMMARY>Compacted checkpoint</CONTEXT_SUMMARY>",
            }) + "\n"
            tail_line = json.dumps({
                "type": "PLANNER_RESPONSE",
                "content": "NEW_TAIL_" + ("y" * 2000),
            }) + "\n"
            with open(p, "w", encoding="utf-8") as f:
                # Write ~2.0 MB pre-checkpoint padding, then checkpoint, then ~420 KB tail (> 256 KB chunk)
                for _ in range(200):
                    f.write(pre_line)
                f.write(cp_line)
                for _ in range(210):
                    f.write(tail_line)

            t0 = time.perf_counter()
            status = estimate_subagent_context(p, max_context_tokens=256000)
            elapsed = time.perf_counter() - t0
            self.assertGreater(p.stat().st_size, 2 * 1024 * 1024)
            self.assertEqual(status.epoch_step_count, 210)
            self.assertLess(status.step_count, 250)
            self.assertLess(status.token_count, 200_000)
            self.assertLess(elapsed, 0.5)


if __name__ == "__main__":
    unittest.main()
