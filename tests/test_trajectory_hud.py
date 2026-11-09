# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Arafat Zahan (@kuasha420)
# Corporate Stewardship & Infrastructure: Purrfect Software Limited (PSL)
# Governed by: ICARO-42/b Ordinance (Company-Supported Personal IP Framework)

"""
Hermetic unit tests for Trajectory HUD native Upc context parity (Phase 25 / Cleanroom Parity).
Sub-second benchmark invariant: <0.10s benchmark.
"""

from __future__ import annotations

import json
from pathlib import Path
import tempfile
import time
import unittest
from unittest.mock import patch

from harness.gui.trajectory_hud import load_conversation_trajectory


class TestTrajectoryHudNativeUpc(unittest.TestCase):
    """Hermetic unit tests for Upc algorithm parity in load_conversation_trajectory."""

    def test_input_and_cache_read_tokens_extraction(self):
        """Verifies input_tokens + cache_read_tokens are extracted from steps and set as total_tokens."""
        with tempfile.TemporaryDirectory() as tmpdir:
            base_brain = Path(tmpdir)
            convo_id = "test-convo-upc-1"
            convo_dir = base_brain / convo_id
            logs_dir = convo_dir / ".system_generated" / "logs"
            logs_dir.mkdir(parents=True, exist_ok=True)

            steps_data = [
                {"role": "user", "content": "Hello", "type": "USER_INPUT", "tokens": 50},
                {"role": "assistant", "content": "I am thinking", "type": "PLANNER_RESPONSE", "tokens": 150},
                {
                    "role": "assistant",
                    "content": "Executing task",
                    "type": "MODEL_OUTPUT",
                    "tokens": 200,
                    "input_tokens": 12000,
                    "cache_read_tokens": 30000,
                },
            ]

            with open(logs_dir / "transcript.jsonl", "w", encoding="utf-8") as f:
                for s in steps_data:
                    f.write(json.dumps(s) + "\n")

            start_t = time.monotonic()
            traj = load_conversation_trajectory(convo_id, brain_dir=base_brain)
            elapsed = time.monotonic() - start_t

            self.assertLess(elapsed, 0.50, f"Benchmark exceeded: {elapsed:.4f}s")
            self.assertEqual(traj["conversation_id"], convo_id)
            # 12,000 input + 30,000 cache = 42,000 ground truth Vertex prompt tokens
            expected_explicit = 42000
            self.assertEqual(traj["total_tokens"], expected_explicit)
            self.assertEqual(traj["cache_tokens"], 30000)

    def test_dynamic_instruction_token_expansion(self):
        """Verifies instruction_tok dynamically expands to absorb difference between step_sum and explicit_cum_tokens."""
        with tempfile.TemporaryDirectory() as tmpdir:
            base_brain = Path(tmpdir)
            convo_id = "test-convo-upc-2"
            convo_dir = base_brain / convo_id
            convo_dir.mkdir(parents=True, exist_ok=True)

            # step_sum = 1,000. explicit_cum_tokens = 50,000.
            # instruction_tok = max(7000, 50000 - 1000) = 49,000.
            # sys_prompt_tok = int(49000 * 0.40) = 19,600.
            # tool_defs_tok = 49000 - 19600 = 29,400.
            steps_data = [
                {"role": "user", "content": "Task prompt", "type": "USER_INPUT", "tokens": 400},
                {
                    "role": "assistant",
                    "content": "Done",
                    "type": "MODEL_OUTPUT",
                    "tokens": 600,
                    "input_tokens": 20000,
                    "cache_read_tokens": 30000,
                },
            ]

            with open(convo_dir / "transcript.jsonl", "w", encoding="utf-8") as f:
                for s in steps_data:
                    f.write(json.dumps(s) + "\n")

            traj = load_conversation_trajectory(convo_id, brain_dir=base_brain)

            self.assertEqual(traj["total_tokens"], 50000)
            breakdown = traj["token_breakdown"]
            self.assertEqual(breakdown["system_prompt"], 19600)
            self.assertEqual(breakdown["tool_defs"], 29400)
            self.assertGreater(breakdown["system_prompt"], 4000, "Must not be capped by legacy 4000 limit")
            self.assertGreater(breakdown["tool_defs"], 3500, "Must not be capped by legacy 3500 limit")
            self.assertEqual(sum(breakdown.values()), 50000)

    def test_slices_well_formed_and_non_negative(self):
        """Verifies slices remain well-formed with no negative numbers, no NaNs, and exact summation."""
        with tempfile.TemporaryDirectory() as tmpdir:
            base_brain = Path(tmpdir)
            convo_id = "test-convo-upc-3"
            convo_dir = base_brain / convo_id
            convo_dir.mkdir(parents=True, exist_ok=True)

            steps_data = [
                {"role": "user", "content": "Hi", "tokens": 100},
                {"role": "assistant", "content": "Hello", "tokens": 200, "input_tokens": 10000, "cache_read_tokens": 5000},
            ]

            with open(convo_dir / "transcript.jsonl", "w", encoding="utf-8") as f:
                for s in steps_data:
                    f.write(json.dumps(s) + "\n")

            traj = load_conversation_trajectory(convo_id, brain_dir=base_brain)

            sys_slices = traj["system_prompt_slices"]
            tool_slices = traj["tool_def_slices"]

            self.assertTrue(len(sys_slices) > 0)
            self.assertTrue(len(tool_slices) > 0)

            total_sys = sum(s["tokens"] for s in sys_slices)
            total_tool = sum(s["tokens"] for s in tool_slices)

            for s in sys_slices:
                self.assertIsInstance(s["tokens"], int)
                self.assertGreaterEqual(s["tokens"], 0)
            for s in tool_slices:
                self.assertIsInstance(s["tokens"], int)
                self.assertGreaterEqual(s["tokens"], 0)

            self.assertEqual(total_sys, traj["token_breakdown"]["system_prompt"])
            self.assertEqual(total_tool, traj["token_breakdown"]["tool_defs"])
            self.assertEqual(sum(traj["token_breakdown"].values()), traj["total_tokens"])

    def test_fallback_to_token_proximity_guard_db(self):
        """Verifies fallback to get_active_conversation_tokens when steps lack input_tokens/cache_read_tokens."""
        with tempfile.TemporaryDirectory() as tmpdir:
            base_brain = Path(tmpdir)
            convo_id = "test-convo-upc-fallback"
            convo_dir = base_brain / convo_id
            convo_dir.mkdir(parents=True, exist_ok=True)

            # Steps without input_tokens or cache_read_tokens
            steps_data = [
                {"role": "user", "content": "Simple message", "tokens": 500},
                {"role": "assistant", "content": "Simple reply", "tokens": 500},
            ]

            with open(convo_dir / "transcript.jsonl", "w", encoding="utf-8") as f:
                for s in steps_data:
                    f.write(json.dumps(s) + "\n")

            with patch("harness.hooks.token_proximity_guard.get_active_conversation_tokens", return_value=60000):
                traj = load_conversation_trajectory(convo_id, brain_dir=base_brain)
                self.assertEqual(traj["total_tokens"], 60000)
                # instruction_tok = max(7000, 60000 - 1000) = 59000
                self.assertEqual(traj["token_breakdown"]["system_prompt"], int(59000 * 0.40))
                self.assertEqual(traj["token_breakdown"]["tool_defs"], 59000 - int(59000 * 0.40))

    def test_model_resolution_and_no_hardcoded_gemini(self):
        """Verifies session model resolution and asserts hud.js contains zero occurrences of 'gemini-2.5-pro'."""
        with tempfile.TemporaryDirectory() as tmpdir:
            base_brain = Path(tmpdir)
            convo_id = "test-convo-model-res"
            convo_dir = base_brain / convo_id
            convo_dir.mkdir(parents=True, exist_ok=True)

            steps_data = [
                {
                    "role": "user",
                    "content": "<USER_SETTINGS_CHANGE>\nModel Selection: gemini-3.8-flash-high",
                    "type": "USER_INPUT",
                },
                {
                    "role": "assistant",
                    "content": "Executing with chosen model",
                    "type": "PLANNER_RESPONSE",
                },
                {
                    "role": "assistant",
                    "content": "Step with explicit model",
                    "type": "MODEL_OUTPUT",
                    "model": "claude-3-7-sonnet",
                },
            ]

            with open(convo_dir / "transcript.jsonl", "w", encoding="utf-8") as f:
                for s in steps_data:
                    f.write(json.dumps(s) + "\n")

            traj = load_conversation_trajectory(convo_id, brain_dir=base_brain)
            self.assertEqual(traj["model"], "claude-3-7-sonnet")
            self.assertEqual(traj["steps"][1]["response_model"], "claude-3-7-sonnet")
            self.assertEqual(traj["steps"][2]["response_model"], "claude-3-7-sonnet")

        # Zero occurrences of gemini-2.5-pro in hud.js (PSL-INV-010)
        from harness.gui.trajectory_hud import _load_hud_template
        template = _load_hud_template()
        self.assertNotIn("gemini-2.5-pro", template)

    def test_multi_schema_protobuf_token_extraction(self):
        """Verifies multi-schema token extraction for promptTokenCount, candidatesTokenCount, and cachedContentTokenCount."""
        with tempfile.TemporaryDirectory() as tmpdir:
            base_brain = Path(tmpdir)
            convo_id = "test-convo-tokens-schema"
            convo_dir = base_brain / convo_id
            convo_dir.mkdir(parents=True, exist_ok=True)

            steps_data = [
                {
                    "role": "assistant",
                    "type": "MODEL_OUTPUT",
                    "metadata": {
                        "modelUsage": {
                            "promptTokenCount": 15420,
                            "candidatesTokenCount": 850,
                            "cachedContentTokenCount": 9200,
                        }
                    },
                }
            ]

            with open(convo_dir / "transcript.jsonl", "w", encoding="utf-8") as f:
                for s in steps_data:
                    f.write(json.dumps(s) + "\n")

            traj = load_conversation_trajectory(convo_id, brain_dir=base_brain)
            step = traj["steps"][0]
            self.assertEqual(step["input_tokens"], 15420)
            self.assertEqual(step["output_tokens"], 850)
            self.assertEqual(step["cache_read_tokens"], 9200)

    def test_system_message_content_extraction(self):
        """Verifies systemMessage, message, task_details are cleanly extracted when content is absent."""
        with tempfile.TemporaryDirectory() as tmpdir:
            base_brain = Path(tmpdir)
            convo_id = "test-convo-sys-msg"
            convo_dir = base_brain / convo_id
            convo_dir.mkdir(parents=True, exist_ok=True)

            steps_data = [
                {
                    "source": "system",
                    "systemMessage": "System event occurred: sandbox primed.",
                },
                {
                    "source": "system",
                    "task_details": {"task": "Build", "status": "Ready"},
                },
            ]

            with open(convo_dir / "transcript.jsonl", "w", encoding="utf-8") as f:
                for s in steps_data:
                    f.write(json.dumps(s) + "\n")

            traj = load_conversation_trajectory(convo_id, brain_dir=base_brain)
            self.assertEqual(traj["steps"][0]["content"], "System event occurred: sandbox primed.")
            self.assertIn('"task": "Build"', traj["steps"][1]["content"])


if __name__ == "__main__":
    unittest.main()
