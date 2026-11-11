# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Arafat Zahan (@kuasha420)
# Corporate Stewardship & Infrastructure: Purrfect Software Limited (PSL)
# Governed by: ICARO-42/b Ordinance (Company-Supported Personal IP Framework)

"""
Hermetic verification suite for the Canonical Trajectory SSOT Engine (ADR-035).
Covers protobuf metadata decoding, epoch splitting, UsageMetadata precedence,
protobuf Timestamp velocity calculation, escaped-JSON subagent lineage resolution,
strict parent_conversation_id filtering, honest breakdown, and 256k health scaling.
"""

from __future__ import annotations

import json
from pathlib import Path
import sqlite3
import tempfile
import time
import unittest

from harness.trajectory import (
    build_measured_breakdown,
    classify_context_health,
    discover_active_subagents,
    extract_spawned_subagents,
    extract_timestamp_from_protobuf,
    extract_usage_from_protobuf,
    read_db_trajectory_state,
)


def _varint(val: int) -> bytes:
    out = bytearray()
    while True:
        b = val & 0x7F
        val >>= 7
        if val:
            out.append(b | 0x80)
        else:
            out.append(b)
            break
    return bytes(out)


def _pb_varint_field(fn: int, val: int) -> bytes:
    return _varint((fn << 3) | 0) + _varint(val)


def _pb_bytes_field(fn: int, payload: bytes) -> bytes:
    return _varint((fn << 3) | 2) + _varint(len(payload)) + payload


def _build_step_meta_pb(*, ts_sec: int, input_tok: int = 0, cache_tok: int = 0, out_tok: int = 0, thought_tok: int = 0) -> bytes:
    parts = [_pb_bytes_field(1, _pb_varint_field(1, ts_sec) + _pb_varint_field(2, 123456))]
    if input_tok or cache_tok:
        u = (
            _pb_varint_field(2, input_tok)
            + _pb_varint_field(3, out_tok + thought_tok)
            + _pb_varint_field(5, cache_tok)
            + _pb_varint_field(9, out_tok)
            + _pb_varint_field(10, thought_tok)
        )
        parts.append(_pb_bytes_field(9, u))
    return b"".join(parts)


def _build_gen_meta_pb(*, estimated: int, max_ctx: int, ckpt_idx: int = 0, model: str = "gemini-3.8-flash-k") -> bytes:
    cwm = _pb_varint_field(1, estimated) + _pb_varint_field(4, max_ctx)
    csm = (_pb_varint_field(1, ckpt_idx) if ckpt_idx > 0 else b"") + _pb_bytes_field(10, cwm)
    inner = _pb_bytes_field(9, csm) + _pb_bytes_field(19, model.encode("utf-8"))
    return _pb_bytes_field(1, inner)


class TestTrajectorySSOT(unittest.TestCase):
    """Sub-second hermetic tests for harness.trajectory."""

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp = Path(self._tmp.name)
        self.db_dir = self.tmp / "conversations"
        self.brain_dir = self.tmp / "brain"
        self.db_dir.mkdir(parents=True, exist_ok=True)
        self.brain_dir.mkdir(parents=True, exist_ok=True)

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def test_authoritative_usage_metadata_beats_inflated_gen_estimate(self) -> None:
        """UsageMetadata (input + cacheRead) must not be inflated by >100% gen_metadata estimates."""
        cid = "cid-usage-wins"
        db_path = self.db_dir / f"{cid}.db"
        conn = sqlite3.connect(db_path)
        conn.execute("CREATE TABLE steps (idx INTEGER PRIMARY KEY, step_type INTEGER, metadata BLOB, step_payload BLOB)")
        conn.execute("CREATE TABLE gen_metadata (idx INTEGER PRIMARY KEY, data BLOB)")
        prompt_payload = _pb_bytes_field(19, _pb_bytes_field(7, b"/cockpit-director audit RC10 telemetry"))
        conn.execute("INSERT INTO steps VALUES (0, 14, ?, ?)", (_build_step_meta_pb(ts_sec=1794400000), prompt_payload))
        conn.execute(
            "INSERT INTO steps VALUES (1, 15, ?, NULL)",
            (_build_step_meta_pb(ts_sec=1794400060, input_tok=4000, cache_tok=136000, out_tok=800, thought_tok=1200),),
        )
        conn.execute(
            "INSERT INTO gen_metadata VALUES (1, ?)",
            (_build_gen_meta_pb(estimated=353000, max_ctx=256000),),
        )
        conn.commit()
        conn.close()

        t0 = time.perf_counter()
        metrics = read_db_trajectory_state(cid, db_dir=self.db_dir)
        elapsed_ms = (time.perf_counter() - t0) * 1000.0

        self.assertLess(elapsed_ms, 50.0)
        self.assertEqual(metrics.tokens, 140000)
        self.assertFalse(metrics.is_provisional)
        self.assertEqual(metrics.cache_read_tokens, 136000)
        self.assertEqual(metrics.max_context_tokens, 256000)
        self.assertIn("/cockpit-director", metrics.turn0_prompt)

    def test_checkpoint_ignores_summarizer_usage_and_uses_provisional_summary(self) -> None:
        """
        Compaction step (step_type=23) carries ~258k summarizer UsageMetadata; new epoch
        must ignore pre-compaction summarizer tokens and use bounded provisional <summary> size
        until the first post-compaction LLM UsageMetadata arrives, plus compute real tok/min velocity.
        """
        cid = "cid-post-compaction"
        db_path = self.db_dir / f"{cid}.db"
        conn = sqlite3.connect(db_path)
        conn.execute("CREATE TABLE steps (idx INTEGER PRIMARY KEY, step_type INTEGER, metadata BLOB, step_payload BLOB)")
        conn.execute("CREATE TABLE gen_metadata (idx INTEGER PRIMARY KEY, data BLOB)")
        conn.execute(
            "INSERT INTO steps VALUES (10, 15, ?, NULL)",
            (_build_step_meta_pb(ts_sec=1794400100, input_tok=5000, cache_tok=225000),),
        )
        summary_text = "<summary>\n# Task Overview\n" + ("word " * 800) + "\n</summary>"
        cp_payload = _pb_bytes_field(30, _pb_bytes_field(5, summary_text.encode("utf-8")))
        cp_meta = _build_step_meta_pb(ts_sec=1794400200, input_tok=6200, cache_tok=252000)
        conn.execute("INSERT INTO steps VALUES (11, 23, ?, ?)", (cp_meta, cp_payload))
        conn.execute(
            "INSERT INTO gen_metadata VALUES (1, ?)",
            (_build_gen_meta_pb(estimated=258000, max_ctx=256000, ckpt_idx=5),),
        )
        conn.commit()
        conn.close()

        m_gap = read_db_trajectory_state(cid, db_dir=self.db_dir)
        self.assertTrue(m_gap.is_provisional)
        self.assertGreater(m_gap.tokens, 500)
        self.assertLess(m_gap.tokens, 50000)
        self.assertEqual(m_gap.checkpoint_count, 1)
        self.assertEqual(m_gap.epoch_steps, 0)
        self.assertEqual(m_gap.epoch_index, 1)

        # Two post-compaction turns arrive 120 seconds apart -> non-zero tok/min velocity!
        conn = sqlite3.connect(db_path)
        conn.execute(
            "INSERT INTO steps VALUES (12, 15, ?, NULL)",
            (_build_step_meta_pb(ts_sec=1794400260, input_tok=2000, cache_tok=20000),),
        )
        conn.execute("INSERT INTO steps VALUES (13, 132, ?, NULL)", (_build_step_meta_pb(ts_sec=1794400300),))
        conn.execute(
            "INSERT INTO steps VALUES (14, 15, ?, NULL)",
            (_build_step_meta_pb(ts_sec=1794400380, input_tok=3000, cache_tok=25000),),
        )
        conn.commit()
        conn.close()

        m_live = read_db_trajectory_state(cid, db_dir=self.db_dir)
        self.assertFalse(m_live.is_provisional)
        self.assertEqual(m_live.tokens, 28000)
        self.assertEqual(m_live.epoch_steps, 3)
        self.assertEqual(m_live.total_steps, 5)
        # 28,000 - 22,000 = 6,000 tokens over 120 seconds = 3,000 tok/min
        self.assertAlmostEqual(m_live.burn_rate_tokens_per_min, 3000.0, places=1)
        self.assertIsNotNone(extract_timestamp_from_protobuf(cp_meta))
        self.assertEqual(extract_usage_from_protobuf(cp_meta).total_prompt_tokens, 258200)

    def test_escaped_json_subagents_and_strict_parent_filtering(self) -> None:
        """
        Escaped JSON inside transcript tool outputs must resolve clean child UUIDs (no '\\'),
        and discover_active_subagents must exclude completed or foreign conversations.
        """
        parent_id = "11111111-1111-4111-8111-111111111111"
        active_child = "22222222-2222-4222-8222-222222222222"
        done_child = "33333333-3333-4333-8333-333333333333"
        foreign_id = "44444444-4444-4444-8444-444444444444"

        p_logs = self.brain_dir / parent_id / ".system_generated" / "logs"
        p_logs.mkdir(parents=True, exist_ok=True)
        p_steps = [
            {
                "step_index": 0,
                "type": "PLANNER_RESPONSE",
                "tool_calls": [
                    {
                        "name": "invoke_subagent",
                        "args": {"TypeName": "agyis_builder", "Role": "Builder"},
                        "result": json.dumps({"conversationId": active_child}),
                    },
                    {
                        "name": "invoke_subagent",
                        "args": {"TypeName": "agyis_reviewer", "Role": "Reviewer"},
                        "result": json.dumps({"conversationId": done_child}),
                    },
                ],
            }
        ]
        (p_logs / "transcript.jsonl").write_text("\n".join(json.dumps(s) for s in p_steps), encoding="utf-8")

        spawned = extract_spawned_subagents(p_steps, parent_cid=parent_id)
        self.assertEqual(spawned, {active_child: "agyis_builder", done_child: "agyis_reviewer"})
        self.assertNotIn("\\", spawned)

        # Active incomplete child
        a_dir = self.brain_dir / active_child
        a_dir.mkdir(parents=True, exist_ok=True)
        (a_dir / "transcript.jsonl").write_text(
            json.dumps({"step_index": 0, "type": "USER_INPUT", "content": "Implement Phase 1"}),
            encoding="utf-8",
        )
        # Completed child (PLANNER_RESPONSE DONE with no tool_calls)
        d_dir = self.brain_dir / done_child
        d_dir.mkdir(parents=True, exist_ok=True)
        (d_dir / "transcript.jsonl").write_text(
            json.dumps({"step_index": 0, "type": "PLANNER_RESPONSE", "status": "DONE", "content": "Done"}),
            encoding="utf-8",
        )
        # Foreign active conversation (unrelated parent)
        f_dir = self.brain_dir / foreign_id
        f_dir.mkdir(parents=True, exist_ok=True)
        (f_dir / "transcript.jsonl").write_text(
            json.dumps({"step_index": 0, "type": "USER_INPUT", "content": "Foreign session"}),
            encoding="utf-8",
        )

        # Without parent_cid -> strict isolation returns []
        self.assertEqual(discover_active_subagents(None, brain_dir=self.brain_dir, db_dir=self.db_dir), [])

        found = discover_active_subagents(parent_id, brain_dir=self.brain_dir, db_dir=self.db_dir)
        self.assertEqual([s.conversation_id for s in found], [active_child])
        self.assertEqual(found[0].role, "agyis_builder")
        self.assertEqual(found[0].health_zone, "HEALTHY")

    def test_256k_health_classification_and_honest_breakdown(self) -> None:
        """Subagent health scales to 256k/1M windows; TokenBreakdown uses explicit unattributed."""
        self.assertEqual(classify_context_health(85_000, 20), ("HEALTHY", "REUSE"))
        self.assertEqual(classify_context_health(175_000, 20), ("AMBER", "COMPACT_SOON"))
        self.assertEqual(classify_context_health(210_000, 20), ("RED_ALERT", "HANDOFF_OR_COMPACT"))
        self.assertEqual(classify_context_health(300_000, 20, max_context_tokens=1_000_000), ("HEALTHY", "REUSE"))

        steps = [
            {"type": "USER_INPUT", "content": "x" * 400, "tokens": 100},
            {"type": "PLANNER_RESPONSE", "content": "y" * 800, "thinking": "t" * 400, "tokens": 300},
        ]
        bd = build_measured_breakdown(steps, total_tokens=10_000).to_dict()
        self.assertEqual(bd["user"], 100)
        self.assertEqual(bd["thought"], 100)
        self.assertEqual(bd["model"], 200)
        self.assertEqual(bd["unattributed"], 9_600)
        self.assertEqual(sum(bd.values()), 10_000)


if __name__ == "__main__":
    unittest.main()
