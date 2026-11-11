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
            self.assertFalse(traj["is_provisional"])
            breakdown = traj["token_breakdown"]
            self.assertEqual(breakdown["system_prompt"], 0)
            self.assertEqual(breakdown["tool_defs"], 0)
            self.assertEqual(breakdown["unattributed"], 49000)
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

            self.assertEqual(sys_slices, [])
            self.assertEqual(tool_slices, [])

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

    def test_sqlite_ssot_fallback_when_transcript_lacks_usage(self):
        """Falls back cleanly to SQLite SSOT metrics via AGYIS_CONVERSATIONS_DIR when transcript steps omit usage."""
        import os
        import sqlite3

        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            base_brain = root / "brain"
            db_dir = root / "convs"
            db_dir.mkdir(parents=True, exist_ok=True)
            convo_id = "test-convo-upc-fallback"
            convo_dir = base_brain / convo_id
            convo_dir.mkdir(parents=True, exist_ok=True)

            steps_data = [
                {"role": "user", "content": "Simple message", "tokens": 500},
                {"role": "assistant", "content": "Simple reply", "tokens": 500},
            ]
            with open(convo_dir / "transcript.jsonl", "w", encoding="utf-8") as f:
                for s in steps_data:
                    f.write(json.dumps(s) + "\n")

            conn = sqlite3.connect(db_dir / f"{convo_id}.db")
            conn.execute("CREATE TABLE gen_metadata (idx INTEGER PRIMARY KEY, data TEXT)")
            conn.execute(
                "INSERT INTO gen_metadata VALUES (1, ?)",
                (
                    json.dumps(
                        {
                            "chatStartMetadata": {
                                "contextWindowMetadata": {
                                    "estimatedTokensUsed": 60000,
                                    "maxContextTokens": 256000,
                                }
                            }
                        }
                    ),
                ),
            )
            conn.commit()
            conn.close()

            with patch.dict(os.environ, {"AGYIS_CONVERSATIONS_DIR": str(db_dir)}):
                traj = load_conversation_trajectory(convo_id, brain_dir=base_brain)

            self.assertEqual(traj["total_tokens"], 60000)
            self.assertTrue(traj["is_provisional"])
            self.assertEqual(traj["token_breakdown"]["system_prompt"], 0)
            self.assertEqual(traj["token_breakdown"]["tool_defs"], 0)
            self.assertEqual(traj["token_breakdown"]["unattributed"], 59000)

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

    def test_db_fallback_max_context_tokens_512k(self):
        """Falls back to get_active_conversation_context_window when transcript lacks maxContextTokens."""
        import os
        import sqlite3

        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            base_brain = root / "brain"
            db_dir = root / "convs"
            db_dir.mkdir(parents=True, exist_ok=True)
            convo_id = "convo-db-512k-fallback"
            convo_dir = base_brain / convo_id
            convo_dir.mkdir(parents=True, exist_ok=True)

            with open(convo_dir / "transcript.jsonl", "w", encoding="utf-8") as f:
                f.write(json.dumps({"role": "user", "content": "Hello", "tokens": 500}) + "\n")
                f.write(json.dumps({"role": "assistant", "content": "Hi", "tokens": 1000}) + "\n")

            db_path = db_dir / f"{convo_id}.db"
            conn = sqlite3.connect(db_path)
            conn.execute("CREATE TABLE gen_metadata (idx INTEGER PRIMARY KEY, data TEXT)")
            conn.execute(
                "INSERT INTO gen_metadata VALUES (1, ?)",
                (
                    json.dumps(
                        {
                            "chatStartMetadata": {
                                "contextWindowMetadata": {
                                    "estimatedTokensUsed": 374475,
                                    "maxContextTokens": 512000,
                                }
                            }
                        }
                    ),
                ),
            )
            conn.commit()
            conn.close()

            with patch.dict(os.environ, {"AGYIS_CONVERSATIONS_DIR": str(db_dir)}):
                traj = load_conversation_trajectory(convo_id, brain_dir=base_brain)

            self.assertEqual(traj["max_context_tokens"], 512000)
            self.assertEqual(traj["total_tokens"], 374475)

    def test_active_epoch_breakdown_excludes_pre_checkpoint_inflation(self):
        """When explicit_cum_tokens > 0 and checkpoints exist, token_breakdown only counts active epoch steps."""
        with tempfile.TemporaryDirectory() as tmpdir:
            base_brain = Path(tmpdir)
            convo_id = "convo-active-epoch-breakdown"
            convo_dir = base_brain / convo_id
            convo_dir.mkdir(parents=True, exist_ok=True)

            steps_data = [
                # Historical pre-checkpoint epoch (must NOT inflate active epoch breakdown)
                {"role": "user", "type": "USER_INPUT", "content": "Old prompt", "tokens": 150000},
                {"role": "assistant", "type": "TOOL_CALL", "tool_calls": [{"name": "run_command"}], "tokens": 80000},
                # Checkpoint
                {"role": "system", "type": "CHECKPOINT", "content": "<summary>Compacted</summary>", "tokens": 4000},
                # Active post-checkpoint epoch
                {"role": "user", "type": "USER_INPUT", "content": "New question", "tokens": 1000},
                {
                    "role": "assistant",
                    "type": "PLANNER_RESPONSE",
                    "content": "New answer",
                    "tokens": 2000,
                    "input_tokens": 20000,
                    "cache_read_tokens": 30000,
                },
            ]
            with open(convo_dir / "transcript.jsonl", "w", encoding="utf-8") as f:
                for s in steps_data:
                    f.write(json.dumps(s) + "\n")

            traj = load_conversation_trajectory(convo_id, brain_dir=base_brain)
            breakdown = traj["token_breakdown"]
            self.assertEqual(traj["total_tokens"], 50000)
            self.assertEqual(sum(breakdown.values()), 50000)
            self.assertEqual(breakdown["user"], 1000)
            self.assertEqual(breakdown["tool"], 0)
            self.assertEqual(breakdown["checkpoint"], 4000)
            self.assertEqual(breakdown["model"], 2000)
            self.assertEqual(breakdown["system_prompt"] + breakdown["tool_defs"], 0)
            self.assertEqual(breakdown["unattributed"], 43000)

    def test_cold_cache_explicit_user_input_tokens_honored(self):
        """USER_INPUT with explicit input_tokens > 0 and cache_read_tokens == 0 still populates total_tokens cleanly."""
        with tempfile.TemporaryDirectory() as tmpdir:
            base_brain = Path(tmpdir)
            convo_id = "convo-cold-cache-user-input"
            convo_dir = base_brain / convo_id
            convo_dir.mkdir(parents=True, exist_ok=True)

            steps_data = [
                {
                    "role": "user",
                    "type": "USER_INPUT",
                    "content": "Hi",
                    "tokens": 50,
                    "input_tokens": 25000,
                    "cache_read_tokens": 0,
                },
            ]
            with open(convo_dir / "transcript.jsonl", "w", encoding="utf-8") as f:
                for s in steps_data:
                    f.write(json.dumps(s) + "\n")

            traj = load_conversation_trajectory(convo_id, brain_dir=base_brain)
            self.assertEqual(traj["total_tokens"], 25000)
            self.assertEqual(traj["token_breakdown"]["user"], 50)
            self.assertEqual(sum(traj["token_breakdown"].values()), 25000)
            self.assertNotIn("_has_explicit_input_tokens", traj["steps"][0])

    def test_is_provisional_cache_tokens_and_chronological_sort(self):
        """Verifies provisional flag, cache_tokens extraction, and out-of-order step_index chronological sort."""
        with tempfile.TemporaryDirectory() as tmpdir:
            base_brain = Path(tmpdir)

            # Case A: estimatedTokensUsed only -> is_provisional == True
            cid_est = "convo-provisional-only"
            (base_brain / cid_est).mkdir(parents=True, exist_ok=True)
            (base_brain / cid_est / "transcript.jsonl").write_text(
                json.dumps(
                    {
                        "step_index": 0,
                        "role": "user",
                        "content": "Estimate check",
                        "tokens": 200,
                        "contextWindowMetadata": {"estimatedTokensUsed": 18000, "maxContextTokens": 256000},
                    }
                )
                + "\n",
                encoding="utf-8",
            )
            traj_est = load_conversation_trajectory(cid_est, brain_dir=base_brain)
            self.assertEqual(traj_est["total_tokens"], 18000)
            self.assertTrue(traj_est["is_provisional"])
            self.assertEqual(traj_est["cache_tokens"], 0)

            # Case B: authoritative inputTokens + cacheReadTokens + out-of-order step_index + checkpoint reset
            cid_auth = "convo-auth-chronological"
            (base_brain / cid_auth).mkdir(parents=True, exist_ok=True)
            out_of_order = [
                {
                    "step_index": 2,
                    "type": "PLANNER_RESPONSE",
                    "content": "Post-checkpoint reply",
                    "tokens": 600,
                    "metadata": {"modelUsage": {"inputTokens": 4000, "cacheReadTokens": 12000}},
                },
                {"step_index": 0, "type": "USER_INPUT", "content": "Initial message", "tokens": 9000},
                {"step_index": 1, "type": "CHECKPOINT", "content": "<summary>Compacted state</summary>", "tokens": 1500},
            ]
            (base_brain / cid_auth / "transcript.jsonl").write_text(
                "\n".join(json.dumps(s) for s in out_of_order) + "\n", encoding="utf-8"
            )
            traj_auth = load_conversation_trajectory(cid_auth, brain_dir=base_brain)
            self.assertEqual([s["step_index"] for s in traj_auth["steps"]], [0, 1, 2])
            self.assertEqual([s["cumulative_tokens"] for s in traj_auth["steps"]], [9000, 1500, 2100])
            self.assertFalse(traj_auth["is_provisional"])
            self.assertEqual(traj_auth["cache_tokens"], 12000)
            self.assertEqual(traj_auth["total_tokens"], 16000)

    def test_backslash_free_subagent_ids_from_escaped_output(self):
        """Escaped JSON inside tool output resolves clean child UUIDs without trailing backslashes."""
        with tempfile.TemporaryDirectory() as tmpdir:
            base_brain = Path(tmpdir)
            parent_id = "11111111-1111-4111-8111-111111111111"
            child_id = "aaaaaaaa-bbbb-4ccc-8ddd-eeeeeeeeeeee"
            (base_brain / parent_id).mkdir(parents=True, exist_ok=True)
            (base_brain / child_id).mkdir(parents=True, exist_ok=True)
            (base_brain / child_id / "transcript.jsonl").write_text(
                json.dumps({"step_index": 0, "type": "USER_INPUT", "content": "Child task", "tokens": 100}) + "\n",
                encoding="utf-8",
            )
            parent_step = {
                "step_index": 0,
                "type": "PLANNER_RESPONSE",
                "tool_calls": [
                    {
                        "name": "invoke_subagent",
                        "args": {"TypeName": "agyis_builder", "Role": "Builder"},
                        "output": json.dumps({"conversationId": child_id}),
                    }
                ],
            }
            (base_brain / parent_id / "transcript.jsonl").write_text(json.dumps(parent_step) + "\n", encoding="utf-8")

            traj = load_conversation_trajectory(parent_id, brain_dir=base_brain)
            self.assertEqual(traj["subagents"], [child_id])
            self.assertTrue(all("\\" not in sid for sid in traj["subagents"]))

    def test_non_checkpoint_summary_tags_do_not_split_epochs(self):
        """#107.1: <summary> and <CONTEXT_SUMMARY> inside tools/GENERIC/assistant prose do NOT split epochs."""
        with tempfile.TemporaryDirectory() as tmpdir:
            base_brain = Path(tmpdir)
            cid = "test-non-checkpoint-tags"
            (base_brain / cid).mkdir(parents=True, exist_ok=True)
            steps = [
                {"step_index": 0, "type": "USER_INPUT", "content": "Initial request", "tokens": 200},
                {"step_index": 1, "type": "GENERIC", "content": "<summary>Tool output summary</summary>"},
                {
                    "step_index": 2,
                    "type": "VIEW_FILE",
                    "viewFile": {
                        "absolutePathUri": "/tmp/doc.md",
                        "content": "<CONTEXT_SUMMARY>fake prose inside read_file</CONTEXT_SUMMARY>",
                    },
                },
                {
                    "step_index": 3,
                    "type": "RUN_COMMAND",
                    "runCommand": {
                        "commandLine": "cat transcript.jsonl",
                        "exitCode": 0,
                        "combinedOutput": {"full": "<CONTEXT_SUMMARY>\nquoted log line\n</CONTEXT_SUMMARY>"},
                    },
                },
                {
                    "step_index": 4,
                    "type": "PLANNER_RESPONSE",
                    "content": "Discussing <summary> and <CONTEXT_SUMMARY> tags in prose",
                    "tool_calls": [{"name": "view_file", "args": {}, "output": "<summary>nested</summary>"}],
                },
                {"step_index": 5, "type": "CHECKPOINT", "content": "<summary>Actual compaction checkpoint</summary>"},
                {"step_index": 6, "type": "PLANNER_RESPONSE", "content": "Resumed cleanly", "tokens": 350},
            ]
            (base_brain / cid / "transcript.jsonl").write_text(
                "\n".join(json.dumps(s) for s in steps) + "\n",
                encoding="utf-8",
            )
            traj = load_conversation_trajectory(cid, brain_dir=base_brain)
            self.assertEqual(traj["checkpoint_count"], 1)
            self.assertEqual(len(traj["epochs"]), 2)
            self.assertEqual((traj["epochs"][0]["start_index"], traj["epochs"][0]["end_index"]), (0, 5))
            self.assertEqual((traj["epochs"][1]["start_index"], traj["epochs"][1]["end_index"]), (5, 6))
            self.assertEqual(traj["epoch_index"], 1)

    def test_find_transcript_path_prefers_transcript_full(self):
        """#108.3: find_transcript_path prefers transcript_full.jsonl over compact transcript.jsonl."""
        from harness.trajectory.transcript_reader import find_transcript_path

        with tempfile.TemporaryDirectory() as tmpdir:
            base_brain = Path(tmpdir)
            cid = "test-prefer-full-transcript"
            logs_dir = base_brain / cid / ".system_generated" / "logs"
            logs_dir.mkdir(parents=True, exist_ok=True)
            compact_path = logs_dir / "transcript.jsonl"
            full_path = logs_dir / "transcript_full.jsonl"
            compact_path.write_text(
                json.dumps({"step_index": 0, "type": "PLANNER_RESPONSE", "content": "truncated", "truncated_fields": ["content"]}) + "\n",
                encoding="utf-8",
            )
            full_path.write_text(
                json.dumps({"step_index": 0, "type": "PLANNER_RESPONSE", "content": "FULL_UNTRUNCATED_" + ("z" * 400)}) + "\n",
                encoding="utf-8",
            )
            resolved, _src = find_transcript_path(cid, brain_dir=base_brain)
            self.assertEqual(resolved, full_path)
            traj = load_conversation_trajectory(cid, brain_dir=base_brain)
            self.assertEqual(Path(traj["transcript_path"]), full_path)
            self.assertIn("FULL_UNTRUNCATED_", traj["steps"][0]["content"])


if __name__ == "__main__":
    unittest.main()
