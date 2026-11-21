# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Arafat Zahan (@kuasha420)
# Corporate Stewardship & Infrastructure: Purrfect Software Limited (PSL)
# Governed by: ICARO-42/b Ordinance (Company-Supported Personal IP Framework)

"""
Hermetic regression suite for Antigravity v2.34.0 / agy v1.5.14 compatibility
across Stream 3 (DRIFT-P1-02..07, DRIFT-P1-14, DRIFT-P2-01, DRIFT-P2-06).
"""

from __future__ import annotations

import fcntl
import json
import os
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import patch

from harness.discovery import is_non_interactive_context
from harness.telemetry.db import iter_brain_transcripts
from harness.telemetry.extractor import extract_session
from harness.trajectory.health import infer_model_context_window
from harness.trajectory.protobuf import (
    extract_token_breakdown_from_protobuf,
    extract_tool_from_protobuf,
    extract_usage_from_protobuf,
    iter_pb_strings,
)
from harness.trajectory.sqlite_reader import get_conversations_dir, read_db_trajectory_state
from harness.trajectory.transcript_reader import (
    build_measured_breakdown,
    discover_active_subagents,
    extract_role_from_text,
    extract_spawned_subagents,
    is_transcript_completed,
)
from harness.utils.context import detect_presence_conversation_id
from harness.utils.plan_parser import EXCLUDED_WORDS, find_active_plan
from pipeline.benchmark_reasoning_tiers import classify_session_tier
from pipeline.harvest_conversations import extract_conversation_db


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


def _pb_varint(fn: int, val: int) -> bytes:
    return _varint((fn << 3) | 0) + _varint(val)


def _pb_bytes(fn: int, payload: bytes) -> bytes:
    return _varint((fn << 3) | 2) + _varint(len(payload)) + payload


class TestTrajectoryV234Compat(unittest.TestCase):
    """Sub-second hermetic tests for Stream 3 v2.34.0 compatibility fixes."""

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp = Path(self._tmp.name)

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def test_presence_flock_detection(self) -> None:
        """DRIFT-P1-02: detect_presence_conversation_id detects flock-held <cid>.lock."""
        pdir = self.tmp / "presence"
        pdir.mkdir()
        unlocked = pdir / "00000000-0000-0000-0000-000000000001.lock"
        unlocked.write_text("", encoding="utf-8")
        locked = pdir / "b3f551ca-7cb4-49ad-a4ea-e43f8fb4929f.lock"
        locked.write_text("", encoding="utf-8")

        fd = os.open(str(locked), os.O_RDWR)
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            self.assertEqual(detect_presence_conversation_id(pdir), locked.stem)
        finally:
            fcntl.flock(fd, fcntl.LOCK_UN)
            os.close(fd)

        self.assertIsNone(detect_presence_conversation_id(pdir))

    def test_swarm_lineage_and_completion_and_role_stopwords(self) -> None:
        """DRIFT-P1-02: /swarm extraction, parked completion, conversation_summaries.db, stopwords."""
        steps = [
            {
                "type": "PLANNER_RESPONSE",
                "tool_calls": [
                    {"name": "swarm", "args": json.dumps({"action": "add", "name": "fix-trajectory"})}
                ],
            },
            {
                "type": "GENERIC",
                "content": json.dumps({
                    "status": "added",
                    "name": "fix-trajectory",
                    "conversation_id": "3207ee60-85e2-4921-8440-7bd0e1a1a177",
                }),
            },
        ]
        spawned = extract_spawned_subagents(steps, parent_cid="root-cid")
        self.assertEqual(spawned.get("3207ee60-85e2-4921-8440-7bd0e1a1a177"), "fix-trajectory")

        parked_t = self.tmp / "parked.jsonl"
        parked_t.write_text(
            json.dumps({
                "type": "PLANNER_RESPONSE",
                "status": "DONE",
                "tool_calls": [{"name": "post_message"}, {"name": "swarm_wait"}],
            }) + "\n" + json.dumps({"type": "GENERIC", "content": "posted"}) + "\n",
            encoding="utf-8",
        )
        self.assertTrue(is_transcript_completed(parked_t))

        for bad in ("You are this agent", "You are operating independently", "You are executing tasks"):
            self.assertIsNone(extract_role_from_text(bad))
        self.assertEqual(extract_role_from_text("You are agyis_builder."), "agyis_builder")

        # conversation_summaries.db lineage + killed=1 filtering
        app_dir = self.tmp / "appdata"
        brain_dir = app_dir / "brain"
        brain_dir.mkdir(parents=True)
        for cid in ("child-active", "child-killed"):
            cdir = brain_dir / cid / ".system_generated" / "logs"
            cdir.mkdir(parents=True)
            (cdir / "transcript_full.jsonl").write_text(
                json.dumps({"type": "USER_INPUT", "content": "work", "input_tokens": 1200, "cache_read_tokens": 300}) + "\n",
                encoding="utf-8",
            )
        cs_db = app_dir / "conversation_summaries.db"
        conn = sqlite3.connect(cs_db)
        conn.execute(
            "CREATE TABLE conversation_summaries ("
            "conversation_id TEXT PRIMARY KEY, agent_name TEXT, parent_conversation_id TEXT, "
            "nesting_depth INTEGER, not_fully_idle INTEGER, killed INTEGER)"
        )
        conn.execute("INSERT INTO conversation_summaries VALUES ('child-active', 'verifier', 'parent-1', 1, 1, 0)")
        conn.execute("INSERT INTO conversation_summaries VALUES ('child-killed', 'old-worker', 'parent-1', 1, 0, 1)")
        conn.commit()
        conn.close()

        active = discover_active_subagents(parent_cid="parent-1", brain_dir=brain_dir, db_dir=self.tmp / "no_dbs")
        self.assertEqual([a.conversation_id for a in active], ["child-active"])
        self.assertEqual(active[0].role, "verifier")
        self.assertEqual(active[0].token_count, 1500)

    def test_protobuf_usage_tokens_breakdown_and_csm(self) -> None:
        """DRIFT-P1-03 & P2-06: fn=9 thought vs fn=10 output, TokenType 8..10, recursive TokenGroup, CSM fn=2."""
        usage = _pb_varint(2, 1000) + _pb_varint(3, 829) + _pb_varint(5, 5000) + _pb_varint(9, 77) + _pb_varint(10, 752)
        csm = _pb_varint(1, 3) + _pb_varint(2, 5)
        meta_pb = _pb_bytes(1, _pb_bytes(9, csm)) + _pb_bytes(9, usage)
        metrics = extract_usage_from_protobuf(meta_pb)
        self.assertEqual(metrics.thought_tokens, 77)
        self.assertEqual(metrics.output_tokens, 752)
        self.assertEqual(metrics.checkpoint_idx, 5)

        nested_leaf = _pb_bytes(1, b"leaf-plugin") + _pb_varint(3, 400)
        child_group = _pb_bytes(1, b"plugin-sub") + _pb_bytes(2, nested_leaf) + _pb_varint(3, 400)
        g_plugins = _pb_bytes(1, b"Plugins") + _pb_varint(2, 9) + _pb_varint(4, 1631) + _pb_bytes(5, child_group)
        g_workflows = _pb_bytes(1, b"Workflows") + _pb_varint(2, 8) + _pb_varint(4, 200)
        g_flows = _pb_bytes(1, b"Flows") + _pb_varint(2, 10) + _pb_varint(4, 100)
        tb = _pb_bytes(1, g_plugins) + _pb_bytes(1, g_workflows) + _pb_bytes(1, g_flows) + _pb_varint(2, 1931)
        cwm = _pb_bytes(3, tb)
        bd = extract_token_breakdown_from_protobuf(_pb_bytes(10, cwm))
        self.assertIsNotNone(bd)
        assert bd is not None
        self.assertEqual(bd.plugins_tokens, 1631)
        self.assertEqual(bd.workflows_tokens, 200)
        self.assertEqual(bd.flows_tokens, 100)
        self.assertEqual(bd.groups[0].children[1].name, "leaf-plugin")

    def test_sqlite_step_type_filtering_pb_items_and_modified_tool_call(self) -> None:
        """DRIFT-P1-04: filter 132/101 prompt fallback, strip items prefix byte, fn=29 modified_tool_call."""
        # iter_pb_strings on CortexStepUserInput.items (0x0a <len> <text>) where len >= 32 (printable ASCII)
        user_text = b"Let's get up to speed on the current repository state and recent changes."
        item_msg = _pb_bytes(1, user_text)  # starts with 0x0a 'G' ...
        payload = _pb_bytes(19, _pb_bytes(3, item_msg))
        strings = iter_pb_strings(payload, min_len=3)
        self.assertEqual(strings, [user_text.decode("utf-8")])

        # modified_tool_call (fn=29) beats tool_call (fn=4)
        tc_orig = _pb_bytes(2, b"run_command") + _pb_bytes(3, b'{"CommandLine":"grep foo"}')
        tc_mod = _pb_bytes(2, b"run_command") + _pb_bytes(3, b'{"CommandLine":"grep foo || [ $? -eq 1 ]"}')
        t_name, t_args = extract_tool_from_protobuf(_pb_bytes(4, tc_orig) + _pb_bytes(29, tc_mod))
        self.assertEqual(t_name, "run_command")
        self.assertIn("|| [ $? -eq 1 ]", t_args)

        # sqlite_reader filters step_type 132/101/15 in prompt fallback
        db_dir = self.tmp / "conversations"
        db_dir.mkdir()
        db_path = db_dir / "cid-swarm.db"
        conn = sqlite3.connect(db_path)
        conn.execute("CREATE TABLE steps (idx INTEGER PRIMARY KEY, step_type INTEGER, metadata BLOB, step_payload BLOB)")
        conn.execute("INSERT INTO steps VALUES (0, 101, NULL, ?)", (_pb_bytes(1, b"SYSTEM_MESSAGE brief"),))
        conn.execute("INSERT INTO steps VALUES (1, 132, NULL, ?)", (_pb_bytes(1, b'{"CommandLine":"ls"}'),))
        conn.commit()
        conn.close()
        metrics = read_db_trajectory_state("cid-swarm", db_dir=db_dir)
        self.assertEqual(metrics.turn0_prompt, "")
        self.assertEqual(metrics.latest_user_prompt, "")

        # harvest_conversations.py fixes
        h_db = db_dir / "cid-harvest.db"
        conn = sqlite3.connect(h_db)
        conn.execute("CREATE TABLE steps (idx INTEGER PRIMARY KEY, step_type INTEGER, status INTEGER, metadata BLOB, error_details BLOB, step_payload BLOB)")
        conn.execute("CREATE TABLE trajectory_metadata_blob (id TEXT PRIMARY KEY, data BLOB)")
        conn.execute("INSERT INTO trajectory_metadata_blob VALUES ('main', ?)", (_pb_bytes(18, b"4eacf503-1111-2222-3333-444444444444"),))
        tool_meta = _pb_bytes(4, _pb_bytes(2, b"read_file") + _pb_bytes(3, b'{"Path":"/home/kuasha/Dev/agyis-harness/README.md"}'))
        err_payload = _pb_bytes(140, _pb_bytes(2, _pb_bytes(1, b"Command exited with code 2")))
        conn.execute("INSERT INTO steps VALUES (0, 132, 3, ?, NULL, ?)", (tool_meta, err_payload))
        conn.commit()
        conn.close()
        harvested = extract_conversation_db(h_db)
        self.assertIsNotNone(harvested)
        assert harvested is not None
        s_row, st_rows, tc_rows, _ = harvested
        self.assertEqual(s_row["workspace_path"], "")
        self.assertEqual(st_rows[0]["step_type"], "TOOL_CALL:read_file")
        self.assertEqual(tc_rows[0]["target_path"], "/home/kuasha/Dev/agyis-harness/README.md")
        self.assertEqual(tc_rows[0]["exit_code"], 2)

    def test_extractor_full_transcript_multitool_and_model_path(self) -> None:
        """DRIFT-P1-05: transcript_full.jsonl priority, args.Path, model, error, workspace, multi-tool."""
        brain = self.tmp / "brain"
        sdir = brain / "sess-1" / ".system_generated" / "logs"
        sdir.mkdir(parents=True)
        (sdir / "transcript.jsonl").write_text(json.dumps({"step_index": 0, "type": "USER_INPUT", "content": "hi"}) + "\n", encoding="utf-8")
        full_p = sdir / "transcript_full.jsonl"
        lines = [
            {"step_index": 0, "type": "USER_INPUT", "content": "Check /home/kuasha/Dev/agyis-harness"},
            {
                "step_index": 1,
                "type": "PLANNER_RESPONSE",
                "model": "gemini-4-hydrogen",
                "input_tokens": 1000,
                "cache_read_tokens": 2000,
                "tool_calls": [
                    {"name": "read_file", "args": {"Path": "/home/kuasha/Dev/agyis-harness/a.py"}},
                    {"name": "edit_file", "args": {"Path": "/home/kuasha/Dev/agyis-harness/b.py"}},
                ],
            },
            {"step_index": 2, "type": "GENERIC", "status": "DONE", "content": "ok"},
            {"step_index": 3, "type": "GENERIC", "status": "DONE", "content": "", "error": "Target not found"},
        ]
        full_p.write_text("\n".join(json.dumps(x) for x in lines) + "\n", encoding="utf-8")

        found = iter_brain_transcripts(brain_dir=brain)
        self.assertEqual(len(found), 1)
        self.assertEqual(found[0][1].name, "transcript_full.jsonl")

        res = extract_session(full_p)
        self.assertIsNotNone(res)
        assert res is not None
        s_row, _, tc_rows, _ = res
        self.assertEqual(s_row["model"], "gemini-4-hydrogen")
        self.assertEqual(s_row["workspace_path"], "/home/kuasha/Dev/agyis-harness")
        self.assertEqual(tc_rows[0]["result_step_index"], 2)
        self.assertEqual(tc_rows[0]["target_path"], "/home/kuasha/Dev/agyis-harness/a.py")
        self.assertEqual(tc_rows[1]["result_step_index"], 3)
        self.assertEqual(tc_rows[1]["status"], "ERROR")
        self.assertIn("Target not found", tc_rows[1]["error_snippet"])

        bd = build_measured_breakdown(lines, total_tokens=5000)
        self.assertEqual(bd.model, 3000)

    def test_app_data_dir_context_windows_plan_parser_and_env(self) -> None:
        """DRIFT-P1-06, P1-07, P1-14, P2-06: ANTIGRAVITY_APP_DATA_DIR, 512k models, plan_parser, env."""
        with patch.dict(os.environ, {"ANTIGRAVITY_APP_DATA_DIR": str(self.tmp / "cli-app")}, clear=True):
            self.assertEqual(get_conversations_dir(), self.tmp / "cli-app" / "conversations")

            plan_dir = self.tmp / "cli-app" / "brain" / "cid-plan-99"
            plan_dir.mkdir(parents=True)
            plan_file = plan_dir / "implementation_plan.md"
            plan_file.write_text("# Plan\n- [ ] Task A\n", encoding="utf-8")

            with patch.dict(os.environ, {"ANTIGRAVITY_CONVERSATION_ID": "cid-plan-99"}):
                ws_empty = self.tmp / "empty_ws"
                ws_empty.mkdir()
                self.assertEqual(find_active_plan(ws_empty), plan_file)

        self.assertEqual(infer_model_context_window("gemini-4-hydrogen"), 512_000)
        self.assertEqual(infer_model_context_window("gemini-4-neon"), 512_000)
        self.assertEqual(infer_model_context_window("gemini-3.8-flash-s"), 512_000)
        self.assertEqual(infer_model_context_window("gemini-3.8-flash-h"), 512_000)
        self.assertEqual(infer_model_context_window("gemini-4-1m"), 1_000_000)

        self.assertIn("read_file", EXCLUDED_WORDS)
        self.assertIn("write_file", EXCLUDED_WORDS)
        self.assertIn("swarm", EXCLUDED_WORDS)

        with patch.dict(os.environ, {"ANTIGRAVITY_AGENT": "1"}, clear=True):
            self.assertTrue(is_non_interactive_context())

        self.assertEqual(classify_session_tier("gemini-4-hydrogen", True, 2000), "gemini-3.8-flash-high")
        self.assertEqual(classify_session_tier("gemini-4-neon", True, 5000), "gemini-3.1-pro")


if __name__ == "__main__":
    unittest.main()
