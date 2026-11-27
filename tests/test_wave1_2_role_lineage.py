# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Arafat Zahan (@kuasha420)
# Corporate Stewardship & Infrastructure: Purrfect Software Limited (PSL)
# Governed by: ICARO-42/b Ordinance (Company-Supported Personal IP Framework)

"""
Hermetic Regression Suite for Wave 1.2 Track 1:
- Strict host-DB isolated `read_conversation_lineage()` + WAL-race fallbacks
- Turn-0 native subagent role pinning across agyis_* & custom agent names
- Poisoned `role_state_<cid>.json` self-healing & root plan isolation
- `step_type=101` [Message] extraction vs SYSTEM_SDK PreInvocation exclusion
- `REVIEWER_AUDITOR_KEYWORDS` & `normalize_role_str()` precedence
- Shared `resolve_hook_role_and_agent()` exact agent_name propagation
- `wire_compat` bounded advisory queue & one-shot PreInvocation drain
- Antigravity 2.35.2 model taxonomy (`max` effort, 512k/840k windows)
"""

from __future__ import annotations

import io
import json
import os
from pathlib import Path
import sqlite3
import tempfile
import time
import unittest
from unittest.mock import patch

from harness.hooks.pre_invocation_hook import evaluate_pre_invocation
from harness.hooks.role_lineage import resolve_hook_role_and_agent
from harness.hooks.role_pinning import (
    _collect_search_paths,
    check_pillar_1_intent,
    check_pillar_3_explicit_role,
    classify_agent_role,
    has_parent_conversation,
    load_sticky_role_state,
    resolve_cid_state_dir,
    resolve_conv_and_brain,
)
from harness.hooks.wire_compat import (
    PRE_TOOL_WIRE_KEYS,
    STOP_WIRE_KEYS,
    drain_pending_advisories,
    emit_stderr_diagnostic,
    enqueue_pending_advisory,
    strip_wire_keys,
)
from harness.telemetry.extractor import extract_session
from harness.telemetry.models import normalize_model
from harness.trajectory import (
    ROLE_DEEP_EXECUTION,
    ROLE_FLIGHT_DIRECTOR,
    ROLE_FORENSIC_AUDITOR,
    infer_model_context_window,
    normalize_role_str,
    read_conversation_lineage,
    read_db_trajectory_state,
)
from harness.trajectory.sqlite_step_parser import _is_sdk_injection_text


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


def _pb_bytes(fn: int, payload: bytes) -> bytes:
    return _varint((fn << 3) | 2) + _varint(len(payload)) + payload


def _create_summaries_db(db_path: Path, rows: list[tuple[str, str, str, int]], *, with_depth: bool = True) -> None:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path)
    if with_depth:
        conn.execute(
            "CREATE TABLE IF NOT EXISTS conversation_summaries ("
            "conversation_id TEXT PRIMARY KEY, agent_name TEXT, parent_conversation_id TEXT, nesting_depth INTEGER)"
        )
        conn.executemany("INSERT OR REPLACE INTO conversation_summaries VALUES (?, ?, ?, ?)", rows)
    else:
        conn.execute(
            "CREATE TABLE IF NOT EXISTS conversation_summaries ("
            "conversation_id TEXT PRIMARY KEY, agent_name TEXT, parent_conversation_id TEXT)"
        )
        conn.executemany(
            "INSERT OR REPLACE INTO conversation_summaries VALUES (?, ?, ?)",
            [(c, a, p) for c, a, p, _ in rows],
        )
    conn.commit()
    conn.close()


class TestLineageAndHostIsolation(unittest.TestCase):
    """Verifies read_conversation_lineage(), strict host-DB isolation, and WAL-race fallbacks."""

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        self.app_dir = self.root / "appdata"
        self.brain_dir = self.app_dir / "brain"
        self.db_dir = self.app_dir / "conversations"
        self.state_dir = self.root / "state"
        self.brain_dir.mkdir(parents=True)
        self.db_dir.mkdir(parents=True)
        self.state_dir.mkdir(parents=True)

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def test_ephemeral_and_temp_state_isolation(self) -> None:
        fake_host = self.root / "fake_host"
        real_uuid = "f58b53fe-9644-4f7b-88c2-104f38e3f0fd"
        _create_summaries_db(
            fake_host / "conversation_summaries.db",
            [
                ("default", "agyis_builder", "parent-1", 1),
                ("test", "agyis_builder", "parent-1", 1),
                ("conv_test", "agyis_builder", "parent-1", 1),
                ("test-123", "agyis_builder", "parent-1", 1),
                (real_uuid, "agyis_builder", "9bbbcf1e-cefe-4948-af78-c7224ed40592", 1),
            ],
        )

        with patch("harness.trajectory.lineage.get_app_data_dir_candidates", return_value=[fake_host]):
            for eph in ("", "default", "test", "conv_test", "test-123"):
                self.assertEqual(read_conversation_lineage(eph), (None, None, 0))

            # Temp AGYIS_HARNESS_STATE_DIR / PSL_HARNESS_STATE_DIR skips host candidates even for real UUIDs
            for env_key in ("AGYIS_HARNESS_STATE_DIR", "PSL_HARNESS_STATE_DIR"):
                with patch.dict(os.environ, {env_key: str(self.state_dir)}, clear=True):
                    self.assertEqual(read_conversation_lineage(real_uuid), (None, None, 0))

            # Explicit brain_dir / db_dir checks ONLY .parent and never leaks to host candidates
            isolated_brain = self.root / "isolated" / "brain"
            isolated_brain.mkdir(parents=True)
            self.assertEqual(read_conversation_lineage(real_uuid, brain_dir=isolated_brain), (None, None, 0))
            self.assertEqual(read_conversation_lineage(real_uuid, db_dir=self.root / "isolated" / "convs"), (None, None, 0))

            # Explicit app_data_dir works even for test-* IDs
            self.assertEqual(
                read_conversation_lineage("test-123", app_data_dir=fake_host),
                ("parent-1", "agyis_builder", 1),
            )

            # Env var precedence (AGYIS_APP_DATA_DIR overrides fake_host)
            env_app = self.root / "env_app"
            _create_summaries_db(
                env_app / "conversation_summaries.db",
                [(real_uuid, "agyis_reviewer", "parent-env", 2)],
            )
            with patch.dict(os.environ, {"AGYIS_APP_DATA_DIR": str(env_app)}, clear=True):
                self.assertEqual(read_conversation_lineage(real_uuid), ("parent-env", "agyis_reviewer", 2))

            # Non-temp state dir with non-test UUID queries default candidates cleanly
            non_temp_state = Path.home() / ".cache" / "agyis_non_temp_probe"
            with patch.dict(os.environ, {"AGYIS_HARNESS_STATE_DIR": str(non_temp_state)}, clear=True):
                self.assertEqual(
                    read_conversation_lineage(real_uuid),
                    ("9bbbcf1e-cefe-4948-af78-c7224ed40592", "agyis_builder", 1),
                )

    def test_minimal_db_schema_without_nesting_depth(self) -> None:
        cid = "aaaaaaaa-1111-4111-8111-111111111111"
        _create_summaries_db(
            self.app_dir / "conversation_summaries.db",
            [(cid, "agyis_custodian", "parent-0", 0)],
            with_depth=False,
        )
        self.assertEqual(read_conversation_lineage(cid, app_data_dir=self.app_dir), ("parent-0", "agyis_custodian", 1))

    def test_wal_race_metadata_transcript_and_parent_tail_fallbacks(self) -> None:
        parent_uuid = "9bbbcf1e-cefe-4948-af78-c7224ed40592"
        child_meta = "child-meta-001"
        c1_dir = self.brain_dir / child_meta
        c1_dir.mkdir(parents=True)
        (c1_dir / "metadata.json").write_text(
            json.dumps({"parentConversationId": parent_uuid, "agentName": "agyis_investigator", "nestingDepth": 1}),
            encoding="utf-8",
        )
        self.assertEqual(
            read_conversation_lineage(child_meta, brain_dir=self.brain_dir),
            (parent_uuid, "agyis_investigator", 1),
        )

        # Transcript [Message] sender fallback + parent tail extract_spawned_subagents lookup
        child_tx = "child-tx-002"
        c2_logs = self.brain_dir / child_tx / ".system_generated" / "logs"
        c2_logs.mkdir(parents=True)
        (c2_logs / "transcript_full.jsonl").write_text(
            "\n".join([
                json.dumps({
                    "step_index": 0,
                    "source": "SYSTEM_SDK",
                    "content": "The following system message was injected by a PreInvocation hook:\n[AGYIS ROLE PINNING: FLIGHT DIRECTOR]",
                }),
                json.dumps({
                    "step_index": 1,
                    "source": "SYSTEM",
                    "content": f"[Message] timestamp=2026-11-26T10:00:00Z sender={parent_uuid} content=Fix bug",
                }),
            ]) + "\n",
            encoding="utf-8",
        )
        p_logs = self.brain_dir / parent_uuid / ".system_generated" / "logs"
        p_logs.mkdir(parents=True)
        (p_logs / "transcript_full.jsonl").write_text(
            json.dumps({
                "step_index": 10,
                "type": "PLANNER_RESPONSE",
                "tool_calls": [
                    {
                        "name": "invoke_subagent",
                        "args": {"TypeName": "DeepCoder-1", "Role": "Worker"},
                        "result": {"conversationId": child_tx},
                    }
                ],
            }) + "\n",
            encoding="utf-8",
        )
        self.assertEqual(
            read_conversation_lineage(child_tx, brain_dir=self.brain_dir),
            (parent_uuid, "DeepCoder-1", 1),
        )

    def test_ambient_run_command_and_explicit_null_cid_not_hijacked(self) -> None:
        caller_cid = "bc6243cc-7cf3-41fb-b3b7-fc27efa24c63"
        meta_run_cmd = json.dumps({
            "tool": {"conversationId": caller_cid, "toolCall": {"name": "run_command"}},
        })
        env_run = {
            "ANTIGRAVITY_CONVERSATION_ID": caller_cid,
            "ANTIGRAVITY_SOURCE_METADATA": meta_run_cmd,
        }
        with patch.dict(os.environ, env_run, clear=True):
            self.assertEqual(
                resolve_conv_and_brain({"initialNumSteps": 105, "tool_calls": ["edit_file"]})[0],
                "default",
            )
            self.assertEqual(
                resolve_conv_and_brain({"hookEventName": "PreToolUse", "toolCall": {"name": "edit_file"}})[0],
                "default",
            )
            self.assertEqual(
                resolve_conv_and_brain({"conversationId": None, "toolCall": {"name": "edit_file"}})[0],
                "default",
            )
            self.assertEqual(
                resolve_conv_and_brain({"conversation_id": None, "hookEventName": "PreToolUse"})[0],
                "default",
            )

        with patch.dict(os.environ, {"ANTIGRAVITY_CONVERSATION_ID": caller_cid}, clear=True):
            self.assertEqual(
                resolve_conv_and_brain({"conversationId": None, "toolCall": {"name": "edit_file"}})[0],
                "default",
            )
            self.assertEqual(resolve_conv_and_brain({"conversation_id": None})[0], "default")
            self.assertEqual(resolve_conv_and_brain({"initialNumSteps": 105})[0], caller_cid)

    def test_home_gemini_ambient_ignored_under_temp_isolation(self) -> None:
        fake_home = self.root / "fake_home"
        live_ag = fake_home / ".gemini" / "antigravity"
        live_brain = live_ag / "brain"
        real_uuid = "e1111111-2222-4333-8444-555555555555"
        _create_summaries_db(
            live_ag / "conversation_summaries.db",
            [(real_uuid, "agyis_reviewer", "parent-host", 1)],
        )
        (live_brain / real_uuid / ".agyis").mkdir(parents=True)
        (live_brain / real_uuid / ".agyis" / "session_role.json").write_text(
            json.dumps({"role": "forensic_auditor"}), encoding="utf-8",
        )

        _create_summaries_db(
            self.app_dir / "conversation_summaries.db",
            [(real_uuid, "agyis_builder", "parent-agyis", 1)],
        )
        (self.brain_dir / real_uuid).mkdir(parents=True)
        (self.brain_dir / real_uuid / "session_role.json").write_text(
            json.dumps({"role": "deep_execution"}), encoding="utf-8",
        )

        with patch.object(Path, "home", return_value=fake_home):
            env_host = {
                "AGYIS_HARNESS_STATE_DIR": str(self.state_dir),
                "ANTIGRAVITY_APP_DATA_DIR": str(live_ag),
                "ANTIGRAVITY_BRAIN_DIR": str(live_brain),
            }
            with patch.dict(os.environ, env_host, clear=True):
                self.assertEqual(read_conversation_lineage(real_uuid), (None, None, 0))
                self.assertEqual(resolve_cid_state_dir(real_uuid), self.state_dir / "checkpoints" / real_uuid)
                self.assertIsNone(check_pillar_3_explicit_role({"conversationId": real_uuid}))

            env_agyis = {
                **env_host,
                "AGYIS_APP_DATA_DIR": str(self.app_dir),
            }
            with patch.dict(os.environ, env_agyis, clear=True):
                self.assertEqual(read_conversation_lineage(real_uuid), ("parent-agyis", "agyis_builder", 1))
                self.assertEqual(resolve_cid_state_dir(real_uuid), self.brain_dir / real_uuid / ".agyis")
                self.assertEqual(
                    check_pillar_3_explicit_role({"conversationId": real_uuid}),
                    ROLE_DEEP_EXECUTION,
                )

            env_custom_ag = {
                "AGYIS_HARNESS_STATE_DIR": str(self.state_dir),
                "ANTIGRAVITY_APP_DATA_DIR": str(self.app_dir),
            }
            with patch.dict(os.environ, env_custom_ag, clear=True):
                self.assertEqual(read_conversation_lineage(real_uuid), ("parent-agyis", "agyis_builder", 1))
                self.assertEqual(resolve_cid_state_dir(real_uuid), self.brain_dir / real_uuid / ".agyis")

            tmp_art = self.root / "brain" / real_uuid
            self.assertEqual(
                _collect_search_paths({"cwd": str(Path.cwd()), "artifactDirectoryPath": str(tmp_art)}, include_cwd=False),
                [Path.cwd(), tmp_art],
            )
            self.assertEqual(
                _collect_search_paths({"artifactDirectoryPath": str(tmp_art)}, include_cwd=False),
                [tmp_art],
            )
            self.assertEqual(
                _collect_search_paths({"artifactDirectoryPath": str(tmp_art)}, include_cwd=True),
                [tmp_art, Path.cwd()],
            )

    def test_fallback_brain_lineage_ignores_planner_prose_allows_system_lines(self) -> None:
        cid_prose = "tx-prose-001"
        p1 = self.brain_dir / cid_prose / ".system_generated" / "logs"
        p1.mkdir(parents=True)
        (p1 / "transcript_full.jsonl").write_text(
            "\n".join([
                json.dumps({"step_index": 0, "type": "USER_INPUT", "content": "Inspect role: agyis_reviewer"}),
                json.dumps({"step_index": 1, "type": "PLANNER_RESPONSE", "content": "You are agyis_builder"}),
            ]) + "\n",
            encoding="utf-8",
        )
        self.assertEqual(read_conversation_lineage(cid_prose, brain_dir=self.brain_dir), (None, None, 0))

        cid_sys = "tx-sys-002"
        p2 = self.brain_dir / cid_sys / ".system_generated" / "logs"
        p2.mkdir(parents=True)
        (p2 / "transcript_full.jsonl").write_text(
            "\n".join([
                json.dumps({"step_index": 0, "type": "PLANNER_RESPONSE", "content": "You are agyis_builder"}),
                json.dumps({"step_index": 1, "source": "SYSTEM", "content": "You are agyis_investigator"}),
            ]) + "\n",
            encoding="utf-8",
        )
        self.assertEqual(read_conversation_lineage(cid_sys, brain_dir=self.brain_dir), (None, "agyis_investigator", 0))


class TestRoleNormalizationAndTurnZeroPinning(unittest.TestCase):
    """Verifies Turn-0 subagent pinning, sticky self-healing, and root plan isolation."""

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        self.app_dir = self.root / "appdata"
        self.brain_dir = self.app_dir / "brain"
        self.db_dir = self.app_dir / "conversations"
        self.ws_dir = self.root / "ws"
        self.state_dir = self.root / "state"
        for d in (self.brain_dir, self.db_dir, self.ws_dir, self.state_dir):
            d.mkdir(parents=True)

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def test_normalize_role_str_precedence_and_custom_names(self) -> None:
        cases = {
            "agyis_builder": ROLE_DEEP_EXECUTION,
            "agyis_custodian": ROLE_DEEP_EXECUTION,
            "agyis_architect": ROLE_DEEP_EXECUTION,
            "agyis_reviewer": ROLE_FORENSIC_AUDITOR,
            "agyis_auditor": ROLE_FORENSIC_AUDITOR,
            "agyis_investigator": ROLE_FORENSIC_AUDITOR,
            "agyis_planner": ROLE_FLIGHT_DIRECTOR,
            "agyis_coordinator": ROLE_FLIGHT_DIRECTOR,
            "DeepCoder-1": ROLE_DEEP_EXECUTION,
            "teamwork-3_worker": ROLE_DEEP_EXECUTION,
            "flight036-fixer-1": ROLE_DEEP_EXECUTION,
            "fix-trajectory": ROLE_DEEP_EXECUTION,
            "audit-1": ROLE_FORENSIC_AUDITOR,
            "teamwork-2_challenger": ROLE_FORENSIC_AUDITOR,
            "teamwork-1_explorer": ROLE_FORENSIC_AUDITOR,
            "researcher": ROLE_FORENSIC_AUDITOR,
            "flight": ROLE_FLIGHT_DIRECTOR,
            "self": None,
        }
        for raw, expected in cases.items():
            with self.subTest(raw=raw):
                self.assertEqual(normalize_role_str(raw), expected)

    def test_turn_zero_subagent_pinning_and_self_fallback(self) -> None:
        parent_uuid = "9bbbcf1e-cefe-4948-af78-c7224ed40592"
        agents = [
            ("11111111-aaaa-4aaa-8aaa-000000000001", "agyis_builder", ROLE_DEEP_EXECUTION, "DEEP EXECUTION"),
            ("11111111-aaaa-4aaa-8aaa-000000000002", "agyis_custodian", ROLE_DEEP_EXECUTION, "DEEP EXECUTION"),
            ("11111111-aaaa-4aaa-8aaa-000000000003", "agyis_reviewer", ROLE_FORENSIC_AUDITOR, "FORENSIC AUDITOR"),
            ("11111111-aaaa-4aaa-8aaa-000000000004", "agyis_investigator", ROLE_FORENSIC_AUDITOR, "FORENSIC AUDITOR"),
            ("11111111-aaaa-4aaa-8aaa-000000000005", "agyis_auditor", ROLE_FORENSIC_AUDITOR, "FORENSIC AUDITOR"),
            ("11111111-aaaa-4aaa-8aaa-000000000006", "agyis_planner", ROLE_FLIGHT_DIRECTOR, "FLIGHT DIRECTOR"),
            ("11111111-aaaa-4aaa-8aaa-000000000007", "DeepCoder-1", ROLE_DEEP_EXECUTION, "DEEP EXECUTION"),
            ("11111111-aaaa-4aaa-8aaa-000000000008", "teamwork-3_worker", ROLE_DEEP_EXECUTION, "DEEP EXECUTION"),
            ("11111111-aaaa-4aaa-8aaa-000000000009", "flight036-fixer-1", ROLE_DEEP_EXECUTION, "DEEP EXECUTION"),
            ("11111111-aaaa-4aaa-8aaa-000000000010", "audit-1", ROLE_FORENSIC_AUDITOR, "FORENSIC AUDITOR"),
            ("11111111-aaaa-4aaa-8aaa-000000000011", "teamwork-2_challenger", ROLE_FORENSIC_AUDITOR, "FORENSIC AUDITOR"),
            ("11111111-aaaa-4aaa-8aaa-000000000012", "self", ROLE_DEEP_EXECUTION, "DEEP EXECUTION"),
        ]
        _create_summaries_db(
            self.app_dir / "conversation_summaries.db",
            [(cid, agent, parent_uuid, 1) for cid, agent, _, _ in agents],
        )
        # Seed root workspace plan declaring flight_director; child subagents must NEVER bleed it
        art_dir = self.ws_dir / ".agents" / "artifacts"
        art_dir.mkdir(parents=True)
        (art_dir / "implementation_plan.md").write_text("**Role**: flight_director\n", encoding="utf-8")
        (art_dir / "plan.json").write_text(json.dumps({"role": "flight_director"}), encoding="utf-8")

        env = {
            "AGYIS_APP_DATA_DIR": str(self.app_dir),
            "AGYIS_HARNESS_STATE_DIR": str(self.state_dir),
        }
        with patch.dict(os.environ, env, clear=True):
            for cid, agent, expected_role, expected_header in agents:
                with self.subTest(agent=agent):
                    (self.brain_dir / cid).mkdir(parents=True, exist_ok=True)
                    res = evaluate_pre_invocation(
                        {"conversationId": cid, "initialNumSteps": 0},
                        db_dir=self.db_dir,
                        workspace_dir=self.ws_dir,
                    )
                    msgs = [s["systemMessage"]["systemMessage"] for s in res.get("injectSteps", [])]
                    self.assertTrue(msgs)
                    self.assertIn(expected_header, msgs[0])
                    sticky = load_sticky_role_state(self.brain_dir / cid / ".agyis", cid)
                    self.assertIsNotNone(sticky)
                    assert sticky is not None
                    self.assertEqual(sticky["role"], expected_role)
                    self.assertEqual(sticky["agent_name"], agent)
                    self.assertEqual(sticky["parent_conversation_id"], parent_uuid)
                    self.assertEqual(sticky["is_fallback"], agent == "self")

    def test_poisoned_sticky_state_self_heals_from_lineage_and_wal_lag(self) -> None:
        parent_uuid = "9bbbcf1e-cefe-4948-af78-c7224ed40592"
        inv_cid = "450616c1-591b-4971-a8ed-b9426a767612"
        wal_cid = "55555555-bbbb-4bbb-8bbb-000000000001"
        _create_summaries_db(
            self.app_dir / "conversation_summaries.db",
            [(inv_cid, "agyis_investigator", parent_uuid, 1)],
        )
        for cid in (inv_cid, wal_cid):
            agyis_dir = self.brain_dir / cid / ".agyis"
            agyis_dir.mkdir(parents=True, exist_ok=True)
            (agyis_dir / f"role_state_{cid}.json").write_text(
                json.dumps({"conversation_id": cid, "checkpoint": 0, "role": ROLE_FLIGHT_DIRECTOR, "pinned_at": 1.0}),
                encoding="utf-8",
            )
        # WAL-lag session has parent metadata in .metadata, no DB row yet
        (self.brain_dir / wal_cid / ".metadata").write_text(
            json.dumps({"parentConversationId": parent_uuid}),
            encoding="utf-8",
        )

        env = {"AGYIS_APP_DATA_DIR": str(self.app_dir), "AGYIS_HARNESS_STATE_DIR": str(self.state_dir)}
        with patch.dict(os.environ, env, clear=True):
            res_inv = evaluate_pre_invocation(
                {"conversationId": inv_cid, "initialNumSteps": 60},
                db_dir=self.db_dir,
                workspace_dir=self.ws_dir,
            )
            txt = res_inv["injectSteps"][0]["systemMessage"]["systemMessage"]
            self.assertIn("FORENSIC_AUDITOR (STEP 60 | CADENCE 10)", txt)
            healed = load_sticky_role_state(self.brain_dir / inv_cid / ".agyis", inv_cid)
            assert healed is not None
            self.assertEqual(healed["role"], ROLE_FORENSIC_AUDITOR)
            self.assertEqual(healed["agent_name"], "agyis_investigator")
            self.assertEqual(healed["source"], "lineage")
            self.assertFalse(healed["is_fallback"])

            # WAL-lag child must discard poisoned flight_director sticky and self-heal to deep_execution
            res_wal = evaluate_pre_invocation(
                {"conversationId": wal_cid, "initialNumSteps": 40},
                db_dir=self.db_dir,
                workspace_dir=self.ws_dir,
            )
            self.assertIn("DEEP_EXECUTION (STEP 40 | CADENCE 10)", res_wal["injectSteps"][0]["systemMessage"]["systemMessage"])
            healed_wal = load_sticky_role_state(self.brain_dir / wal_cid / ".agyis", wal_cid)
            assert healed_wal is not None
            self.assertEqual(healed_wal["role"], ROLE_DEEP_EXECUTION)
            self.assertTrue(healed_wal["is_fallback"])

    def test_step_101_subagent_prompt_extraction_and_reviewer_keywords(self) -> None:
        self.assertTrue(_is_sdk_injection_text("The following system message was injected by a PreInvocation hook:\n[AGYIS ROLE PINNING: X]"))
        self.assertTrue(_is_sdk_injection_text("[AGYIS SUBAGENT CONTEXT CONTINUITY: DEEP_EXECUTION]"))
        self.assertTrue(_is_sdk_injection_text("[AGYIS SYSTEM DIRECTIVE: COMPACTION IMMINENT]"))
        self.assertFalse(_is_sdk_injection_text("[Message] sender=123 content=Review diff"))

        cid = "subagent-101-prompt-test"
        db_path = self.db_dir / f"{cid}.db"
        conn = sqlite3.connect(db_path)
        conn.execute("CREATE TABLE steps (idx INTEGER PRIMARY KEY, step_type INTEGER, step_data TEXT, step_payload BLOB)")
        conn.execute(
            "INSERT INTO steps VALUES (0, 101, ?, ?)",
            (
                json.dumps({"source": "SYSTEM_SDK"}),
                _pb_bytes(1, b"The following system message was injected by a PreInvocation hook:\n[AGYIS ROLE PINNING: FLIGHT DIRECTOR]"),
            ),
        )
        conn.execute(
            "INSERT INTO steps VALUES (1, 101, ?, ?)",
            (
                json.dumps({"source": "SYSTEM"}),
                _pb_bytes(1, b"[Message] timestamp=2026-11-26T10:00:00Z sender=9bbbcf1e content=Perform a Hammer code review and verify fix"),
            ),
        )
        conn.execute(
            "INSERT INTO steps VALUES (2, 101, ?, ?)",
            (
                json.dumps({"source": "SYSTEM"}),
                _pb_bytes(1, b"Message from Parent Agent: Run root cause analysis (RCA) to patch regression"),
            ),
        )
        conn.commit()
        conn.close()

        metrics = read_db_trajectory_state(cid, db_dir=self.db_dir)
        self.assertIn("[Message]", metrics.turn0_prompt)
        self.assertIn("Message from Parent Agent", metrics.latest_user_prompt)
        self.assertNotIn("PreInvocation hook", metrics.turn0_prompt)
        self.assertEqual(check_pillar_1_intent({}, conversation_id=cid, db_dir=self.db_dir), ROLE_FORENSIC_AUDITOR)

    def test_role_lineage_state_dir_and_env_cid_resolution(self) -> None:
        cid_cust = "cust-lineage-uuid-001"
        _create_summaries_db(
            self.app_dir / "conversation_summaries.db",
            [(cid_cust, "agyis_custodian", "parent-9", 1)],
        )
        # Poison sticky file must be ignored in favor of conversation_summaries.db lineage
        (self.state_dir / f"role_state_{cid_cust}.json").write_text(
            json.dumps({"conversation_id": cid_cust, "checkpoint": 0, "role": ROLE_FLIGHT_DIRECTOR}),
            encoding="utf-8",
        )
        with patch.dict(
            os.environ,
            {"AGYIS_APP_DATA_DIR": str(self.app_dir), "AGYIS_HARNESS_STATE_DIR": str(self.state_dir)},
            clear=True,
        ):
            self.assertEqual(
                resolve_hook_role_and_agent({"conversationId": cid_cust}, state_dir=self.state_dir),
                (ROLE_DEEP_EXECUTION, "agyis_custodian"),
            )
            self.assertEqual(
                resolve_hook_role_and_agent({"role": "agyis_investigator"}),
                (ROLE_FORENSIC_AUDITOR, "agyis_investigator"),
            )
            self.assertEqual(resolve_cid_state_dir(cid_cust), self.state_dir / "checkpoints" / cid_cust)
            self.assertTrue(has_parent_conversation(cid_cust, {}, brain_dir=self.brain_dir))

        with patch.dict(os.environ, {"ANTIGRAVITY_CONVERSATION_ID": "env-fallback-cid"}, clear=True):
            self.assertEqual(resolve_conv_and_brain({})[0], "env-fallback-cid")


class TestWireCompatAndV2352Models(unittest.TestCase):
    """Verifies bounded pending_advisories queue, PreInvocation drain, and 2.35.2 model taxonomy."""

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        self.state_dir = self.root / "state"
        self.state_dir.mkdir(parents=True)

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def test_wire_compat_queue_bounds_drain_and_strip(self) -> None:
        cid = "wire-compat-cid-1"
        with patch.dict(os.environ, {"AGYIS_HARNESS_STATE_DIR": str(self.state_dir)}, clear=True):
            for i in range(10):
                enqueue_pending_advisory(cid, f"advisory-{i}", max_items=8)
            enqueue_pending_advisory(cid, "advisory-5", max_items=8)  # dedup moves to tail

            res1 = evaluate_pre_invocation({"conversationId": cid, "step_count": 1, "role": ROLE_DEEP_EXECUTION})
            msgs1 = [s["systemMessage"]["systemMessage"] for s in res1.get("injectSteps", [])]
            self.assertEqual(len(msgs1), 8)
            self.assertEqual(msgs1[0], "advisory-2")
            self.assertEqual(msgs1[-1], "advisory-5")

            # One-shot drain: second invocation gets none
            self.assertEqual(drain_pending_advisories(cid), [])
            res2 = evaluate_pre_invocation({"conversationId": cid, "step_count": 2, "role": ROLE_DEEP_EXECUTION})
            self.assertEqual(res2, {"injectSteps": []})

        err_buf = io.StringIO()
        with patch("sys.stderr", err_buf):
            emit_stderr_diagnostic("diagnostic trace line")
        self.assertEqual(err_buf.getvalue(), "diagnostic trace line\n")

        self.assertEqual(
            strip_wire_keys({"decision": "allow", "reason": "ok", "advisory": "drop", "warning": "drop", "direct_edits_count": 3}),
            {"decision": "allow", "reason": "ok"},
        )
        self.assertEqual(
            strip_wire_keys({"decision": "deny", "reason": "blocked", "warning": "drop"}, allowed_keys=STOP_WIRE_KEYS),
            {"decision": "deny", "reason": "blocked"},
        )
        self.assertIn("permissionOverrides", PRE_TOOL_WIRE_KEYS)

    def test_v2352_model_windows_efforts_and_extractor(self) -> None:
        self.assertEqual(infer_model_context_window("claude-opus-5-5"), 840_000)
        self.assertEqual(infer_model_context_window("Claude Opus 5.5"), 840_000)
        self.assertEqual(infer_model_context_window("claude-5-5-opus"), 840_000)
        self.assertEqual(infer_model_context_window("claude-5.5-opus"), 840_000)
        self.assertEqual(infer_model_context_window("gemini-4-carbon"), 512_000)
        self.assertEqual(infer_model_context_window("Gemini 4 Carbon"), 512_000)
        self.assertEqual(infer_model_context_window("gemini-pro-orchestrator"), 512_000)
        self.assertEqual(infer_model_context_window("gemini-pro-orchestrator-neon"), 512_000)
        self.assertEqual(infer_model_context_window("gemini-pro-coordinator"), 512_000)
        self.assertEqual(infer_model_context_window("Orchestrator (Carbon)"), 512_000)

        m_carbon = normalize_model("gemini-4-carbon (Max)")
        self.assertEqual((m_carbon.family, m_carbon.canonical_model, m_carbon.reasoning_effort, m_carbon.context_window_tokens),
                         ("gemini-4", "gemini-4-carbon", "max", 512_000))

        m_opus = normalize_model("claude-opus-5-5-max")
        self.assertEqual((m_opus.family, m_opus.canonical_model, m_opus.reasoning_effort, m_opus.context_window_tokens),
                         ("claude-5.5", "claude-opus-5-5", "max", 840_000))

        for raw, expected_can in (
            ("gemini-pro-orchestrator-neon", "gemini-pro-orchestrator-neon"),
            ("gemini-pro-orchestrator-argon", "gemini-pro-orchestrator-argon"),
            ("gemini-pro-orchestrator-g1-pro", "gemini-pro-orchestrator-g1-pro"),
            ("Orchestrator (Carbon)", "gemini-pro-orchestrator"),
            ("gemini-pro-coordinator", "gemini-pro-coordinator"),
        ):
            info = normalize_model(raw)
            self.assertEqual(info.canonical_model, expected_can)
            self.assertEqual(info.context_window_tokens, 512_000)

        # Transcript extractor recognizes gemini-4-carbon & gemini-pro-orchestrator-*
        sdir = self.root / "brain" / "sess-2352" / ".system_generated" / "logs"
        sdir.mkdir(parents=True)
        tfile = sdir / "transcript_full.jsonl"
        tfile.write_text(
            json.dumps({"step_index": 0, "type": "USER_INPUT", "content": "Using gemini-4-carbon to build"}) + "\n"
            + json.dumps({"step_index": 1, "type": "PLANNER_RESPONSE", "content": "ok"}) + "\n",
            encoding="utf-8",
        )
        extracted = extract_session(tfile)
        self.assertIsNotNone(extracted)
        assert extracted is not None
        s_row, _, _, _ = extracted
        self.assertEqual(s_row["model"], "gemini-4-carbon")
        self.assertEqual(s_row["max_context_tokens"], 512_000)

        # Benchmark SLA for Wave 1.2 lineage + pinning checks
        t0 = time.perf_counter()
        for _ in range(25):
            classify_agent_role({"conversationId": "default", "role": "agyis_builder"})
        self.assertLess(time.perf_counter() - t0, 0.25)


if __name__ == "__main__":
    unittest.main()
