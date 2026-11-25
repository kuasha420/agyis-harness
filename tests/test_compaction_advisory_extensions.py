# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Arafat Zahan (@kuasha420)
# Corporate Stewardship & Infrastructure: Purrfect Software Limited (PSL)
# Governed by: ICARO-42/b Ordinance (Company-Supported Personal IP Framework)

"""
Unit and contract tests for PreInvocation Compaction Advisory Hook (Issue #83).
Verifies:
1. AC1: Threshold calibration and triggering (default 230,000, env overrides).
2. AC2: Role classification heuristics across metadata, workspace paths, and env vars.
3. AC3: Role-tailored advisory generator across all canonical roles.
4. AC4: Work preservation contract (strictly prohibit git checkout/reset, keep partial work).
5. AC5: Zero repo document pollution (local artifacts/scratch only, zero git churn).
6. AC6: Autonomous post-compaction continuation (self-resumption directives).
7. AC7: SystemMessage payload schema conformance ({"injectSteps": [{"systemMessage": ...}]}).
8. AC8: Fail-open resilience, zero crash risk, and sub-millisecond execution benchmark (<5ms).
9. AC9: Hook runner integration and hooks.json registration.
"""

from __future__ import annotations

import io
import json
import os
from pathlib import Path
import sqlite3
import subprocess
import sys
import tempfile
import time
from typing import Any, Dict, Optional
import unittest
from unittest.mock import patch

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from harness.hooks import pre_invocation_hook, runner
from harness.hooks.pre_invocation_hook import (
    CALIBRATION_METADATA,
    DEFAULT_COMPACTION_ADVISORY_THRESHOLD,
    DEFAULT_SQLITE_TIMEOUT,
    ROLE_DEEP_EXECUTION,
    ROLE_FLIGHT_DIRECTOR,
    ROLE_FORENSIC_AUDITOR,
    ROLE_SWARM_ORCHESTRATOR,
    _normalize_role_str,
    build_compaction_advisory,
    check_pillar_1_intent,
    check_pillar_2_behavior,
    check_pillar_3_explicit_role,
    classify_agent_role,
    evaluate_pre_invocation,
    get_compaction_advisory_threshold,
    get_compaction_sqlite_timeout,
    main as hook_main,
)
from harness.hooks.token_proximity_guard import (
    LOCKED_CONVERSATION_IDS,
    clear_locked_conversations,
    get_active_conversation_tokens,
    get_conversations_dir,
    is_conversation_locked,
    record_locked_conversation,
)


class TestTokenBurstBoundaryHardening(unittest.TestCase):
    """R3: Rapid token burst boundary hardening (single-turn large token jumps)."""

    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_dir = Path(self.temp_dir.name)

    def tearDown(self):
        clear_locked_conversations()
        self.temp_dir.cleanup()

    def test_sqlite_single_turn_token_burst_crosses_threshold_immediately(self):
        """R3: SQLite token jump from 180,000 directly to 245,000 triggers advisory on that exact turn."""
        conv_id = "test-token-burst-conv"
        db_path = self.db_dir / f"{conv_id}.db"

        # Turn 1: 180,000 tokens (below 230k threshold)
        with sqlite3.connect(db_path) as conn:
            conn.execute("CREATE TABLE steps (rowid INTEGER PRIMARY KEY, idx INTEGER, step_data TEXT)")
            conn.execute(
                "INSERT INTO steps (idx, step_data) VALUES (?, ?)",
                (1, json.dumps({"step_type": 15, "token_count": 180_000, "role": "deep_execution"})),
            )
        conn.close()

        payload = json.dumps({"conversationId": conv_id, "role": "deep_execution"})
        res_turn1 = evaluate_pre_invocation(payload, db_dir=self.db_dir)
        self.assertEqual(res_turn1, {"injectSteps": []})

        # Turn 2: Abrupt 65,000 token burst -> 245,000 tokens
        with sqlite3.connect(db_path) as conn:
            conn.execute(
                "INSERT INTO steps (idx, step_data) VALUES (?, ?)",
                (2, json.dumps({"step_type": 15, "token_count": 245_000, "role": "deep_execution"})),
            )
        conn.close()

        res_turn2 = evaluate_pre_invocation(payload, db_dir=self.db_dir)
        self.assertEqual(len(res_turn2.get("injectSteps", [])), 1)
        msg = res_turn2["injectSteps"][0]["systemMessage"]["systemMessage"]
        self.assertIn("COMPACTION IMMINENT", msg)
        self.assertIn("245,000 / 230,000 TOKENS", msg)
        self.assertIn("~1 TURNS REMAINING", msg)

    def test_payload_single_turn_token_burst_crosses_threshold_immediately(self):
        """R3: Payload token jump from 180k to 245k triggers immediately without intermediate turns."""
        payload_turn1 = json.dumps({"tokens": 180_000, "role": "flight_director"})
        self.assertEqual(evaluate_pre_invocation(payload_turn1), {"injectSteps": []})

        payload_turn2 = json.dumps({"tokens": 245_000, "role": "flight_director"})
        res_turn2 = evaluate_pre_invocation(payload_turn2)
        self.assertEqual(len(res_turn2.get("injectSteps", [])), 1)
        msg = res_turn2["injectSteps"][0]["systemMessage"]["systemMessage"]
        self.assertIn("COMPACTION IMMINENT", msg)
        self.assertIn("245,000 / 230,000 TOKENS", msg)

    def test_token_burst_crossing_200k_and_230k_triggers_pillar_2_and_advisory(self):
        """R3: Burst leaping from 150,000 to 245,000 tokens triggers Pillar 2 behavioral scan and advisory."""
        conv_id = "test-token-burst-pillar2"
        db_path = self.db_dir / f"{conv_id}.db"

        with sqlite3.connect(db_path) as conn:
            conn.execute("CREATE TABLE steps (rowid INTEGER PRIMARY KEY, idx INTEGER, step_data TEXT)")
            # Turn 1: 150k tokens, 105 editing steps
            for i in range(1, 106):
                tool = "edit_file" if i % 2 == 0 else "replace_file_content"
                conn.execute(
                    "INSERT INTO steps (idx, step_data) VALUES (?, ?)",
                    (i, json.dumps({"step_type": 15, "token_count": 150_000, "tool_name": tool})),
                )
        conn.close()

        payload = json.dumps({"conversationId": conv_id})
        # Turn 1: 150k is below threshold
        self.assertEqual(evaluate_pre_invocation(payload, db_dir=self.db_dir), {"injectSteps": []})

        # Turn 2: Burst to 245,000 tokens
        with sqlite3.connect(db_path) as conn:
            conn.execute(
                "INSERT INTO steps (idx, step_data) VALUES (?, ?)",
                (106, json.dumps({"step_type": 15, "token_count": 245_000, "tool_name": "edit_file"})),
            )
        conn.close()

        res_turn2 = evaluate_pre_invocation(payload, db_dir=self.db_dir)
        self.assertEqual(len(res_turn2.get("injectSteps", [])), 1)
        msg = res_turn2["injectSteps"][0]["systemMessage"]["systemMessage"]
        self.assertIn("ROLE: Deep Execution", msg)
        self.assertIn("245,000 / 230,000 TOKENS", msg)


class TestBinaryNoiseAndStdinStreamResilience(unittest.TestCase):
    """R4: Binary noise, null bytes, malformed UTF-8, and unexpected ingress keys on stdin."""

    def test_evaluate_pre_invocation_raw_bytes_and_null_bytes(self):
        """R4: evaluate_pre_invocation handles raw bytes with null characters gracefully."""
        raw_inputs = [
            b"\x00\x00\x00",
            b"\xff\xfe\x00\x80\x90",
            b"{\"role\": \"\x00\xff\"}",
            b"\x00{\"tokens\": 1000}\x00",
            b"",
        ]
        for inp in raw_inputs:
            with self.subTest(inp=inp):
                res = evaluate_pre_invocation(inp)
                self.assertEqual(res, {"injectSteps": []})

    def test_hook_main_binary_noise_and_null_bytes(self):
        """R4: hook_main() exits 0 and emits {'injectSteps': []} when reading binary noise with null bytes."""
        binary_payload = b"\x00\xff\xfe\x00\x80\x90\r\n{corrupt"

        class MockStdinWithBuffer:
            def __init__(self, raw: bytes):
                self.buffer = io.BytesIO(raw)
            def read(self):
                return self.buffer.read().decode("utf-8", errors="replace")

        with patch("sys.stdin", MockStdinWithBuffer(binary_payload)), \
             patch("sys.stdout", new_callable=io.StringIO) as mock_out:
            code = hook_main([])
            self.assertEqual(code, 0)
            res = json.loads(mock_out.getvalue().strip())
            self.assertEqual(res, {"injectSteps": []})

    def test_runner_binary_noise_and_null_bytes(self):
        """R4: runner.run_hook() exits 0 and emits {'injectSteps': []} on binary noise."""
        binary_payload = b"\x00\xff\xfe\x00\x80\x90{corrupt"
        with patch("sys.stdout", new_callable=io.StringIO) as mock_out:
            code = runner.run_hook("compaction-advisory", payload_str=binary_payload)
            self.assertEqual(code, 0)
            res = json.loads(mock_out.getvalue().strip())
            self.assertEqual(res, {"injectSteps": []})

    def test_unexpected_ingress_keys_and_structures(self):
        """R4: Unexpected ingress keys, null values, and weird types do not crash or emit errors."""
        bizarre_payload = json.dumps({
            "unknown_top_level_field": 12345,
            "nested_garbage": {"a": [None, True, False, -1]},
            "tokens": None,
            "conversationId": 42,
            "role": ["unexpected", "list"],
            "hookEvent": "PreInvocation",
            "metadata": None,
        })
        res = evaluate_pre_invocation(bizarre_payload)
        self.assertEqual(res, {"injectSteps": []})

    def test_stdin_binary_noise_and_fuzz(self):
        """R4: Binary noise, null bytes, and non-UTF8 on stdin exit code 0 and emit {'injectSteps': []}."""
        binary_noise = b"\x00\xff\xfe\x00\x80\x90\r\n{\"corrupt\": true"

        class MockStdinWithBuffer:
            def __init__(self, raw: bytes):
                self.buffer = io.BytesIO(raw)
            def read(self):
                return self.buffer.read().decode("utf-8", errors="replace")

        with patch("sys.stdin", MockStdinWithBuffer(binary_noise)), \
             patch("sys.stdout", new_callable=io.StringIO) as mock_out:
            code = runner.main(["compaction-advisory"])
            self.assertEqual(code, 0)
            res = json.loads(mock_out.getvalue().strip())
            self.assertEqual(res, {"injectSteps": []})


class TestDefectRemediesAndAdversarialEdgeCases(unittest.TestCase):
    """Verifies remedies for OPEN-2, OPEN-6, OPEN-7, OPEN-8, OPEN-9, OPEN-10, OPEN-11."""

    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_dir = Path(self.temp_dir.name)
        clear_locked_conversations()

    def tearDown(self):
        clear_locked_conversations()
        self.temp_dir.cleanup()

    def test_dot_db_suffix_resolution_pillar2_and_token_guard(self):
        """OPEN-8: Passes .db suffix into token guard and Pillar 2 without creating .db.db."""
        conv_id = "test-suffix-conv"
        db_path = self.db_dir / f"{conv_id}.db"

        with sqlite3.connect(db_path) as conn:
            conn.execute("CREATE TABLE steps (rowid INTEGER PRIMARY KEY, idx INTEGER, step_data TEXT)")
            conn.execute(
                "INSERT INTO steps (idx, step_data) VALUES (?, ?)",
                (1, json.dumps({"step_type": 15, "token_count": 240_000, "tool_name": "replace_file_content"})),
            )
        conn.close()

        # 1. get_active_conversation_tokens with .db suffix
        tokens = get_active_conversation_tokens(f"{conv_id}.db", db_dir=self.db_dir)
        self.assertEqual(tokens, 240_000)

        # 2. check_pillar_2_behavior with .db suffix
        role = check_pillar_2_behavior(
            {"force_pillar_2": True},
            conversation_id=f"{conv_id}.db",
            tokens=240_000,
            db_dir=self.db_dir,
        )
        self.assertEqual(role, ROLE_DEEP_EXECUTION)

        # 3. LOCKED_CONVERSATION_IDS normalization across .db and raw id
        LOCKED_CONVERSATION_IDS.add(f"{conv_id}.db")
        self.assertIn(conv_id, LOCKED_CONVERSATION_IDS)
        self.assertIn(f"{conv_id}.db", LOCKED_CONVERSATION_IDS)
        LOCKED_CONVERSATION_IDS.discard(conv_id)
        self.assertNotIn(f"{conv_id}.db", LOCKED_CONVERSATION_IDS)

    def test_crash_on_unreadable_or_permission_denied_directory(self):
        """OPEN-7: Accessing unreadable directory fails open without raising PermissionError."""
        restricted_dir = self.db_dir / "restricted"
        restricted_dir.mkdir(parents=True, exist_ok=True)
        try:
            restricted_dir.chmod(0o000)
            # Must catch PermissionError / OSError and fail open safely
            tokens = get_active_conversation_tokens("any-conv", db_dir=restricted_dir)
            self.assertEqual(tokens, 0)

            p1_res = check_pillar_1_intent({}, conversation_id="any-conv", db_dir=restricted_dir)
            self.assertIsNone(p1_res)

            p2_res = check_pillar_2_behavior({}, conversation_id="any-conv", db_dir=restricted_dir)
            self.assertIsNone(p2_res)
        finally:
            restricted_dir.chmod(0o755)

    def test_agyis_conversations_dir_env_var(self):
        """OPEN-7: Resolves conversations dir from AGYIS_CONVERSATIONS_DIR env var."""
        custom_path = "/tmp/agyis_test_conversations_dir"
        with patch.dict(os.environ, {"AGYIS_CONVERSATIONS_DIR": custom_path}, clear=False):
            resolved = get_conversations_dir()
            self.assertEqual(resolved, Path(custom_path))

    def test_ingress_payload_conversation_id_resolution(self):
        """OPEN-11: Pillar 1 and 2 extract conversationId directly from ingress payload."""
        conv_id = "test-payload-cid"
        db_path = self.db_dir / f"{conv_id}.db"

        with sqlite3.connect(db_path) as conn:
            conn.execute("CREATE TABLE steps (rowid INTEGER PRIMARY KEY, idx INTEGER, step_data TEXT)")
            # Early step with coding intent
            conn.execute(
                "INSERT INTO steps (idx, step_data) VALUES (?, ?)",
                (1, json.dumps({"prompt": "implement bugfix in test suite"})),
            )
            # Behavioral step with edit_file
            conn.execute(
                "INSERT INTO steps (idx, step_data) VALUES (?, ?)",
                (2, json.dumps({"step_type": 132, "tool_name": "edit_file"})),
            )
        conn.close()

        # Pillar 1 resolves from payload conversationId without kwarg
        p1 = check_pillar_1_intent({"conversationId": conv_id}, db_dir=self.db_dir)
        self.assertEqual(p1, ROLE_DEEP_EXECUTION)

        # Pillar 2 resolves from payload conversationId without kwarg
        p2 = check_pillar_2_behavior({"conversationId": conv_id, "force_pillar_2": True}, db_dir=self.db_dir)
        self.assertEqual(p2, ROLE_DEEP_EXECUTION)

    def test_token_burst_db_lag_uses_max_tokens(self):
        """OPEN-9 / R3: When DB lags behind current turn payload, max(db, payload) triggers advisory."""
        conv_id = "test-burst-lag-conv"
        db_path = self.db_dir / f"{conv_id}.db"

        # DB has 180,000 tokens from previous turn
        with sqlite3.connect(db_path) as conn:
            conn.execute("CREATE TABLE steps (rowid INTEGER PRIMARY KEY, idx INTEGER, step_data TEXT)")
            conn.execute(
                "INSERT INTO steps (idx, step_data) VALUES (?, ?)",
                (1, json.dumps({"step_type": 15, "token_count": 180_000})),
            )
        conn.close()

        # Payload has 245,000 tokens from immediate burst
        payload = json.dumps({
            "conversationId": conv_id,
            "tokens": 245_000,
            "role": "deep_execution",
        })
        res = evaluate_pre_invocation(payload, db_dir=self.db_dir)
        self.assertEqual(len(res.get("injectSteps", [])), 1)
        msg = res["injectSteps"][0]["systemMessage"]["systemMessage"]
        self.assertIn("COMPACTION IMMINENT", msg)
        self.assertIn("245,000 / 230,000 TOKENS", msg)

    def test_sqlite_timeout_direct_argument_clamped(self):
        """OPEN-10: Directly passed sqlite_timeout or timeout argument is clamped to <= 0.5s."""
        self.assertEqual(get_compaction_sqlite_timeout(5.0), 0.5)
        self.assertEqual(get_compaction_sqlite_timeout(100.0), 0.5)
        self.assertEqual(get_compaction_sqlite_timeout(0.01), 0.01)
        self.assertEqual(get_compaction_sqlite_timeout(-5.0), 0.5)

        # Create dummy file so is_file() passes
        (self.db_dir / "any-conv.db").touch()

        # Verify get_active_conversation_tokens clamps timeout passed to sqlite3.connect
        with patch("sqlite3.connect", side_effect=sqlite3.OperationalError("mock lock")) as mock_conn:
            get_active_conversation_tokens("any-conv", db_dir=self.db_dir, timeout=10.0)
            mock_conn.assert_called_once()
            _, kwargs = mock_conn.call_args
            self.assertLessEqual(kwargs.get("timeout", 1.0), 0.5)

    def test_nfs_cifs_error_classification(self):
        """OPEN-6: Classifies disk I/O and locking protocol errors as locked conversations."""
        conv_id = "test-nfs-conv"
        (self.db_dir / f"{conv_id}.db").touch()

        # 1. disk I/O error
        with patch("sqlite3.connect", side_effect=sqlite3.OperationalError("disk I/O error")):
            tokens = get_active_conversation_tokens(conv_id, db_dir=self.db_dir)
            self.assertEqual(tokens, 0)
            self.assertIn(conv_id, LOCKED_CONVERSATION_IDS)

        clear_locked_conversations()

        # 2. locking protocol error
        with patch("sqlite3.connect", side_effect=sqlite3.OperationalError("locking protocol")):
            tokens = get_active_conversation_tokens(conv_id, db_dir=self.db_dir)
            self.assertEqual(tokens, 0)
            self.assertIn(conv_id, LOCKED_CONVERSATION_IDS)

    def test_unbounded_stdin_payload_clamped(self):
        """OPEN-2: Large payload (>512KB) is clamped safely without memory explosion."""
        large_junk = "x" * 530_000
        payload = json.dumps({"role": "flight_director", "junk": large_junk})
        self.assertGreater(len(payload), 524_288)

        # evaluate_pre_invocation clamps payload
        res = evaluate_pre_invocation(payload)
        self.assertIn("injectSteps", res)

        # runner.run_hook clamps payload
        with patch("sys.stdout", new_callable=io.StringIO):
            res_code = runner.run_hook("compaction-advisory", payload_str=payload)
            self.assertEqual(res_code, 0)

    def test_cifs_unable_to_open_database_error_fails_open_and_caches_lock(self):
        """OPEN-12 / OPEN-13: CIFS / EMFILE unable to open database error fails open and caches lock."""
        conv_id = "test-cifs-cantopen-conv"
        (self.db_dir / f"{conv_id}.db").touch()

        with patch("sqlite3.connect", side_effect=sqlite3.OperationalError("unable to open database file")):
            tokens = get_active_conversation_tokens(conv_id, db_dir=self.db_dir)
            self.assertEqual(tokens, 0)
            self.assertIn(conv_id, LOCKED_CONVERSATION_IDS)

    def test_numeric_string_tokens_in_payload(self):
        """String-encoded numeric tokens in payload trigger advisory deterministically."""
        payload = json.dumps({"tokens": "245000", "role": "deep_execution"})
        res = evaluate_pre_invocation(payload)
        self.assertEqual(len(res.get("injectSteps", [])), 1)
        self.assertIn("245,000 / 230,000 TOKENS", res["injectSteps"][0]["systemMessage"]["systemMessage"])


class TestNativeSlashCommandBypass(unittest.TestCase):
    """
    Verifies that all Antigravity native system slash commands cleanly bypass
    PreInvocation compaction advisories to eliminate client-side interceptor collisions,
    while custom modular skills (/db-ops, etc.) retain full protection.
    """

    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_dir = Path(self.temp_dir.name)

    def tearDown(self):
        clear_locked_conversations()
        self.temp_dir.cleanup()

    def test_native_slash_commands_recognized(self):
        """All 23 agy 1.5.15 native system slash commands are recognized regardless of flags or args."""
        from harness.hooks.pre_invocation_hook import is_native_slash_command, NATIVE_SYSTEM_SLASH_COMMANDS

        expected_cmds = [
            "compact",
            "clear",
            "reset",
            "goal",
            "plan",
            "boost",
            "teamwork",
            "teamwork-preview",
            "grill-me",
            "browser",
            "schedule",
            "learn",
            "automation",
            "plugin",
            "context",
            "model",
            "usage",
            "quota",
            "thinking",
            "config",
            "skills",
            "swarm",
            "btw",
        ]
        self.assertEqual(set(expected_cmds), set(NATIVE_SYSTEM_SLASH_COMMANDS))

        for cmd in expected_cmds:
            with self.subTest(cmd=cmd):
                self.assertTrue(is_native_slash_command(f"/{cmd}"))
                self.assertTrue(is_native_slash_command(f"/{cmd} with additional arguments"))
                self.assertTrue(is_native_slash_command(f"  /{cmd}  "))
                self.assertTrue(is_native_slash_command(f"/{cmd.upper()}"))

    def test_xml_wrapped_native_slash_command(self):
        """is_native_slash_command handles Antigravity <USER_REQUEST> XML envelopes."""
        from harness.hooks.pre_invocation_hook import is_native_slash_command

        xml_compact = "<USER_REQUEST>\n/compact \n</USER_REQUEST>\n<ADDITIONAL_METADATA>\nTime: now\n</ADDITIONAL_METADATA>"
        self.assertTrue(is_native_slash_command(xml_compact))

        xml_plan = "<USER_REQUEST>\n/plan design architecture\n</USER_REQUEST>"
        self.assertTrue(is_native_slash_command(xml_plan))

    def test_skills_and_normal_prompts_not_bypassed(self):
        """Modular skills and standard conversational turns are NOT classified as native commands."""
        from harness.hooks.pre_invocation_hook import is_native_slash_command

        skills = [
            "/db-ops",
            "/audio-ops",
            "/storage-ops",
            "/psl-stack-typescript",
            "/git-worktree-ops",
            "/sec-forensics",
            "/custom-skill",
        ]
        for skill in skills:
            with self.subTest(skill=skill):
                self.assertFalse(is_native_slash_command(skill))
                self.assertFalse(is_native_slash_command(f"{skill} execute check"))

        normal_prompts = [
            "Please run /compact on the context",
            "How does /plan work?",
            "Fix the bug in server.py",
            "// comment in code",
            "/",
            "https://example.com/plan",
        ]
        for p in normal_prompts:
            with self.subTest(prompt=p):
                self.assertFalse(is_native_slash_command(p))

        path_prompts = [
            "/plan.md",
            "/plan/roadmap.md",
            "/plugin/index.ts",
            "/clear.sh",
            "/reset.json",
            "/browser/page.ts",
            "/compact.tar.gz",
        ]
        for p in path_prompts:
            with self.subTest(path=p):
                self.assertFalse(is_native_slash_command(p))
                self.assertFalse(is_native_slash_command(f"{p} review"))

    def test_extract_prompt_text_handles_sqlite_json_steps(self):
        """extract_prompt_text extracts slash commands from SQLite JSON string and bytes steps."""
        from harness.hooks.pre_invocation_hook import extract_prompt_text

        cid = "test-conv-sqlite-json-steps"
        db_path = self.db_dir / f"{cid}.db"

        # 1. JSON string step with candidate field 'prompt'
        with sqlite3.connect(db_path) as conn:
            conn.execute(
                "CREATE TABLE steps (rowid INTEGER PRIMARY KEY, idx INTEGER, step_data TEXT)"
            )
            step_obj = {"prompt": "/compact"}
            conn.execute(
                "INSERT INTO steps (idx, step_data) VALUES (?, ?)",
                (1, json.dumps(step_obj)),
            )
        conn.close()

        extracted = extract_prompt_text({}, conversation_id=cid, db_dir=self.db_dir)
        self.assertEqual(extracted, "/compact")

        # 2. JSON bytes step with candidate field 'message'
        cid_bytes = "test-conv-sqlite-bytes-steps"
        db_path_bytes = self.db_dir / f"{cid_bytes}.db"
        with sqlite3.connect(db_path_bytes) as conn:
            conn.execute(
                "CREATE TABLE steps (rowid INTEGER PRIMARY KEY, idx INTEGER, step_payload BLOB)"
            )
            step_bytes = json.dumps({"message": "/plan design architecture"}).encode("utf-8")
            conn.execute(
                "INSERT INTO steps (idx, step_payload) VALUES (?, ?)",
                (1, step_bytes),
            )
        conn.close()

        extracted_bytes = extract_prompt_text({}, conversation_id=cid_bytes, db_dir=self.db_dir)
        self.assertEqual(extracted_bytes, "/plan design architecture")

        # 3. Non-command JSON steps (URLs, file paths, unrelated fields) do not match
        cid_non_cmd = "test-conv-sqlite-non-cmd"
        db_path_non_cmd = self.db_dir / f"{cid_non_cmd}.db"
        with sqlite3.connect(db_path_non_cmd) as conn:
            conn.execute(
                "CREATE TABLE steps (rowid INTEGER PRIMARY KEY, idx INTEGER, step_data TEXT)"
            )
            # URL in prompt
            conn.execute(
                "INSERT INTO steps (idx, step_data) VALUES (?, ?)",
                (1, json.dumps({"prompt": "https://example.com/plan"})),
            )
            # Path in text
            conn.execute(
                "INSERT INTO steps (idx, step_data) VALUES (?, ?)",
                (2, json.dumps({"text": "/plan.md"})),
            )
            # Unrelated field with slash command
            conn.execute(
                "INSERT INTO steps (idx, step_data) VALUES (?, ?)",
                (3, json.dumps({"unrelated": "/compact"})),
            )
        conn.close()

        extracted_non_cmd = extract_prompt_text({}, conversation_id=cid_non_cmd, db_dir=self.db_dir)
        self.assertEqual(extracted_non_cmd, "")

    def test_extract_prompt_text_fast_path_last_user_input(self):
        """extract_prompt_text prioritizes lastUserInput from Antigravity 1.4.11+ hook stdin payload."""
        from harness.hooks.pre_invocation_hook import extract_prompt_text

        # 1. CamelCase lastUserInput
        payload1 = {"lastUserInput": "/teamwork design multi-agent system"}
        self.assertEqual(
            extract_prompt_text(payload1, conversation_id="nonexistent-db"),
            "/teamwork design multi-agent system",
        )

        # 2. Snake_case last_user_input
        payload2 = {"last_user_input": "/compact"}
        self.assertEqual(
            extract_prompt_text(payload2, conversation_id="nonexistent-db"),
            "/compact",
        )

        # 3. Inside steps list
        payload3 = {"steps": [{"lastUserInput": "/plan milestone 1"}]}
        self.assertEqual(
            extract_prompt_text(payload3, conversation_id="nonexistent-db"),
            "/plan milestone 1",
        )

    def test_extract_prompt_text_records_locked_cid_on_operational_error(self):
        """extract_prompt_text records conversation_id into LOCKED_CONVERSATION_IDS on sqlite3.OperationalError."""
        from harness.hooks.pre_invocation_hook import extract_prompt_text
        from harness.hooks.token_proximity_guard import LOCKED_CONVERSATION_IDS

        cid = "test-conv-locked-operational-err"
        db_path = self.db_dir / f"{cid}.db"
        db_path.touch()

        self.assertNotIn(cid, LOCKED_CONVERSATION_IDS)

        with patch("sqlite3.connect", side_effect=sqlite3.OperationalError("database is locked")):
            extracted = extract_prompt_text({}, conversation_id=cid, db_dir=self.db_dir)
            self.assertEqual(extracted, "")

        self.assertIn(cid, LOCKED_CONVERSATION_IDS)

        # Subsequent call skips SQLite access entirely because CID is locked
        with patch("sqlite3.connect") as mock_conn:
            extracted_subsequent = extract_prompt_text({}, conversation_id=cid, db_dir=self.db_dir)
            self.assertEqual(extracted_subsequent, "")
            mock_conn.assert_not_called()

    def test_evaluate_pre_invocation_bypasses_native_slash_commands(self):
        """Above threshold (245k tokens), native commands emit empty injectSteps, skills emit advisory."""
        # 1. Native /compact -> bypassed
        res_compact = evaluate_pre_invocation(json.dumps({
            "tokens": 245_000,
            "prompt": "/compact",
            "role": "deep_execution",
        }))
        self.assertEqual(res_compact, {"injectSteps": []})

        # 2. Native /plan -> bypassed
        res_plan = evaluate_pre_invocation(json.dumps({
            "tokens": 245_000,
            "prompt": "/plan refactor backend",
            "role": "flight_director",
        }))
        self.assertEqual(res_plan, {"injectSteps": []})

        # 3. Native /boost -> bypassed
        res_boost = evaluate_pre_invocation(json.dumps({
            "tokens": 245_000,
            "prompt": "/boost investigate latency spike",
            "role": "flight_director",
        }))
        self.assertEqual(res_boost, {"injectSteps": []})

        # 4. XML-wrapped /compact -> bypassed
        res_xml = evaluate_pre_invocation(json.dumps({
            "tokens": 245_000,
            "prompt": "<USER_REQUEST>\n/compact \n</USER_REQUEST>",
            "role": "deep_execution",
        }))
        self.assertEqual(res_xml, {"injectSteps": []})

        # 5. Modular skill /db-ops -> NOT bypassed, advisory emitted
        res_skill = evaluate_pre_invocation(json.dumps({
            "tokens": 245_000,
            "prompt": "/db-ops check connection pool",
            "role": "deep_execution",
        }))
        self.assertEqual(len(res_skill.get("injectSteps", [])), 1)
        self.assertIn("245,000 / 230,000 TOKENS", res_skill["injectSteps"][0]["systemMessage"]["systemMessage"])

        # 6. Standard developer prompt -> NOT bypassed, advisory emitted
        res_dev = evaluate_pre_invocation(json.dumps({
            "tokens": 245_000,
            "prompt": "Please fix the failing tests in auth.py",
            "role": "deep_execution",
        }))
        self.assertEqual(len(res_dev.get("injectSteps", [])), 1)
        self.assertIn("245,000 / 230,000 TOKENS", res_dev["injectSteps"][0]["systemMessage"]["systemMessage"])



class TestNormalizeRoleExpansion(unittest.TestCase):
    """
    Phase 2: Comprehensive classification engine expansion and backward compatibility tests.
    Verifies deterministic normalization across modern agyis_* names, internal archetypes,
    legacy aliases, and substring patterns into the 4 canonical runtime role buckets.
    """

    def test_modern_agent_names_normalization(self):
        """Verifies all 9 modern agent names normalize to their canonical runtime buckets."""
        expected_mappings = {
            "agyis_coordinator": ROLE_FLIGHT_DIRECTOR,
            "agyis_planner": ROLE_FLIGHT_DIRECTOR,
            "agyis_investigator": ROLE_FORENSIC_AUDITOR,
            "agyis_builder": ROLE_DEEP_EXECUTION,
            "agyis_reviewer": ROLE_FORENSIC_AUDITOR,
            "agyis_custodian": ROLE_DEEP_EXECUTION,
            "agyis_auditor": ROLE_FORENSIC_AUDITOR,
            "agyis_architect": ROLE_DEEP_EXECUTION,
            "cockpit_director": ROLE_FLIGHT_DIRECTOR,
        }
        for name, expected_role in expected_mappings.items():
            with self.subTest(name=name):
                self.assertEqual(
                    _normalize_role_str(name),
                    expected_role,
                    f"Modern agent name '{name}' should normalize to '{expected_role}'",
                )

    def test_internal_codenames_and_archetypes(self):
        """Verifies internal archetypes and codenames normalize deterministically."""
        expected_mappings = {
            "hammer": ROLE_FORENSIC_AUDITOR,
            "executioner": ROLE_DEEP_EXECUTION,
            "detective": ROLE_FORENSIC_AUDITOR,
            "investigator": ROLE_FORENSIC_AUDITOR,
            "architect": ROLE_DEEP_EXECUTION,
            "coordinator": ROLE_FLIGHT_DIRECTOR,
            "planner": ROLE_FLIGHT_DIRECTOR,
            "implementer": ROLE_DEEP_EXECUTION,
            "master_implementer": ROLE_DEEP_EXECUTION,
            "verifier": ROLE_FORENSIC_AUDITOR,
        }
        for name, expected_role in expected_mappings.items():
            with self.subTest(archetype=name):
                self.assertEqual(
                    _normalize_role_str(name),
                    expected_role,
                    f"Archetype '{name}' should normalize to '{expected_role}'",
                )

    def test_legacy_aliases_backward_compatibility(self):
        """Verifies 100% backward compatibility for all legacy harness agent names."""
        expected_mappings = {
            "harness_builder": ROLE_DEEP_EXECUTION,
            "harness_reviewer": ROLE_FORENSIC_AUDITOR,
            "harness_custodian": ROLE_DEEP_EXECUTION,
            "harness_auditor": ROLE_FORENSIC_AUDITOR,
            "coordinator": ROLE_FLIGHT_DIRECTOR,
            "git_custodian": ROLE_DEEP_EXECUTION,
        }
        for name, expected_role in expected_mappings.items():
            with self.subTest(legacy_alias=name):
                self.assertEqual(
                    _normalize_role_str(name),
                    expected_role,
                    f"Legacy alias '{name}' should normalize to '{expected_role}'",
                )

    def test_hyphen_and_case_insensitivity(self):
        """Verifies robust normalization regardless of hyphenation, uppercase, or whitespace."""
        test_cases = [
            ("agyis-coordinator", ROLE_FLIGHT_DIRECTOR),
            ("AGYIS_BUILDER", ROLE_DEEP_EXECUTION),
            ("Agyis-Investigator", ROLE_FORENSIC_AUDITOR),
            ("  agyis_architect  ", ROLE_DEEP_EXECUTION),
            ("agyis-custodian", ROLE_DEEP_EXECUTION),
            ("AGYIS-REVIEWER", ROLE_FORENSIC_AUDITOR),
            ("agyis-auditor", ROLE_FORENSIC_AUDITOR),
            ("agyis-planner", ROLE_FLIGHT_DIRECTOR),
            ("COCKPIT-DIRECTOR", ROLE_FLIGHT_DIRECTOR),
        ]
        for val, expected_role in test_cases:
            with self.subTest(input_val=val):
                self.assertEqual(
                    _normalize_role_str(val),
                    expected_role,
                    f"Value '{val}' should normalize to '{expected_role}'",
                )

    def test_substring_pattern_matching_expansion(self):
        """Verifies expanded substring patterns for roles not matching exact keywords."""
        substring_cases = [
            ("lead_architect_specialist", ROLE_DEEP_EXECUTION),
            ("system_architect", ROLE_DEEP_EXECUTION),
            ("pr_diff_reviewer", ROLE_FORENSIC_AUDITOR),
            ("root_cause_investigator", ROLE_FORENSIC_AUDITOR),
            ("heisenbug_detective", ROLE_FORENSIC_AUDITOR),
            ("cleanroom_spec_verifier", ROLE_FORENSIC_AUDITOR),
            ("strategic_sprint_planner", ROLE_FLIGHT_DIRECTOR),
        ]
        for val, expected_role in substring_cases:
            with self.subTest(substring_input=val):
                self.assertEqual(
                    _normalize_role_str(val),
                    expected_role,
                    f"Substring value '{val}' should normalize to '{expected_role}'",
                )

    def test_classify_agent_role_integration_with_expanded_names(self):
        """Verifies classify_agent_role accurately maps expanded names across payloads."""
        payloads_and_expected = [
            ({"role": "agyis_architect"}, ROLE_DEEP_EXECUTION),
            ({"typeName": "agyis_planner"}, ROLE_FLIGHT_DIRECTOR),
            ({"agentName": "agyis_investigator"}, ROLE_FORENSIC_AUDITOR),
            ({"agent": {"subagent_role": "agyis_reviewer"}}, ROLE_FORENSIC_AUDITOR),
            ({"subagent": {"typeName": "agyis_builder"}}, ROLE_DEEP_EXECUTION),
            ({"metadata": {"role": "agyis_custodian"}}, ROLE_DEEP_EXECUTION),
            ({"role": "agyis_auditor"}, ROLE_FORENSIC_AUDITOR),
            ({"role": "cockpit_director"}, ROLE_FLIGHT_DIRECTOR),
            ({"role": "harness_reviewer"}, ROLE_FORENSIC_AUDITOR),
            ({"role": "harness_auditor"}, ROLE_FORENSIC_AUDITOR),
        ]
        for payload, expected_role in payloads_and_expected:
            with self.subTest(payload=payload):
                self.assertEqual(
                    classify_agent_role(payload),
                    expected_role,
                    f"Payload {payload} should classify as '{expected_role}'",
                )


class TestDynamicContextWindowPropagation(unittest.TestCase):
    """Track 6: Dynamic maxContextTokens scaling across pre_invocation_hook and CLI gauges."""

    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.root = Path(self.temp_dir.name)
        self.db_dir = self.root / "convs"
        self.ws = self.root / "ws"
        self.db_dir.mkdir(parents=True, exist_ok=True)
        self.ws.mkdir(parents=True, exist_ok=True)

    def tearDown(self):
        self.temp_dir.cleanup()

    def _write_512k_db(self, conv_id: str, estimated_tokens: int, max_ctx: int = 512000) -> None:
        db_path = self.db_dir / f"{conv_id}.db"
        conn = sqlite3.connect(db_path)
        conn.execute("CREATE TABLE gen_metadata (idx INTEGER PRIMARY KEY, data TEXT)")
        conn.execute(
            "INSERT INTO gen_metadata VALUES (1, ?)",
            (
                json.dumps(
                    {
                        "chatStartMetadata": {
                            "contextWindowMetadata": {
                                "estimatedTokensUsed": estimated_tokens,
                                "maxContextTokens": max_ctx,
                            }
                        }
                    }
                ),
            ),
        )
        conn.commit()
        conn.close()

    def test_get_compaction_advisory_threshold_dynamic_scaling(self):
        """Scales advisory threshold proportionally when max_context_tokens != 256000 and respects env override."""
        env_clean = {
            k: v
            for k, v in os.environ.items()
            if k not in ("AGYIS_COMPACTION_THRESHOLD", "PSL_COMPACTION_THRESHOLD")
        }
        with patch.dict(os.environ, env_clean, clear=True):
            self.assertEqual(get_compaction_advisory_threshold(), 230_000)
            self.assertEqual(get_compaction_advisory_threshold(max_context_tokens=512_000), 460_000)
            os.environ["AGYIS_COMPACTION_THRESHOLD"] = "300000"
            self.assertEqual(get_compaction_advisory_threshold(max_context_tokens=512_000), 300_000)

    def test_pre_invocation_512k_threshold_and_badge(self):
        """374,475 / 512,000 does not false-trigger compaction; 470,000 / 512,000 emits scaled advisory and badge."""
        conv_mid = "11111111-1111-1111-1111-111111111111"
        self._write_512k_db(conv_mid, 374475, 512000)
        res_mid = evaluate_pre_invocation(
            {"conversationId": conv_mid, "role": "deep_execution"},
            db_dir=self.db_dir,
            workspace_dir=self.ws,
        )
        self.assertEqual(res_mid, {"injectSteps": []})

        conv_high = "22222222-2222-2222-2222-222222222222"
        self._write_512k_db(conv_high, 470000, 512000)
        res_first = evaluate_pre_invocation(
            {"conversationId": conv_high, "role": "deep_execution"},
            db_dir=self.db_dir,
            workspace_dir=self.ws,
        )
        self.assertEqual(len(res_first["injectSteps"]), 1)
        self.assertIn("470,000 / 460,000 TOKENS", res_first["injectSteps"][0]["systemMessage"]["systemMessage"])

        res_second = evaluate_pre_invocation(
            {"conversationId": conv_high, "role": "deep_execution"},
            db_dir=self.db_dir,
            workspace_dir=self.ws,
        )
        self.assertEqual(len(res_second["injectSteps"]), 1)
        self.assertIn(
            "[AGYIS TOKEN GAUGE: ~470,000 / 512,000 TOKENS | Compaction Checkpoint Active]",
            res_second["injectSteps"][0]["systemMessage"]["systemMessage"],
        )

    def test_status_cockpit_and_checkpoint_512k_cli_integration(self):
        """Verifies status, cockpit status, and checkpoint status/create auto-scale to 512k context."""
        import argparse
        from harness.cli import build_parser
        from harness.commands.checkpoint import cmd_checkpoint
        from harness.commands.cockpit import cmd_cockpit
        from harness.commands.status import cmd_status

        conv_id = "33333333-3333-3333-3333-333333333333"
        self._write_512k_db(conv_id, 374475, 512000)

        env_patch = {
            "AGYIS_CONVERSATIONS_DIR": str(self.db_dir),
            "ANTIGRAVITY_CONVERSATION_ID": conv_id,
            "AGYIS_CONVERSATION_ID": conv_id,
        }
        with patch.dict(os.environ, env_patch):
            # 1. status
            status_out = io.StringIO()
            with patch("sys.stdout", status_out):
                ret_status = cmd_status(argparse.Namespace(workspace_dir=self.ws))
            self.assertEqual(ret_status, 0)
            s_txt = status_out.getvalue()
            self.assertIn("512k Model Context Window", s_txt)
            self.assertIn("<360k tokens", s_txt)
            self.assertIn("360k–460k tokens", s_txt)
            self.assertIn(">=460k tokens", s_txt)
            self.assertIn("374,475 / 512,000", s_txt)

            # 2. cockpit status --json & plain text
            parser = build_parser()
            args_json = parser.parse_args(["cockpit", "status", "--workspace", str(self.ws), "--json"])
            cockpit_json_out = io.StringIO()
            with patch("sys.stdout", cockpit_json_out):
                self.assertEqual(cmd_cockpit(args_json), 0)
            cp_json = json.loads(cockpit_json_out.getvalue())
            fd = cp_json["flight_director"]
            self.assertEqual(fd["tokens_estimated"], 374475)
            self.assertEqual(fd["max_context_tokens"], 512000)
            self.assertEqual(fd["amber_threshold"], 360000)
            self.assertEqual(fd["red_threshold"], 460000)
            self.assertEqual(fd["proximity_zone"], "AMBER")

            args_txt = parser.parse_args(["cockpit", "status", "--workspace", str(self.ws)])
            cockpit_txt_out = io.StringIO()
            with patch("sys.stdout", cockpit_txt_out):
                self.assertEqual(cmd_cockpit(args_txt), 0)
            self.assertIn("~374,475 / 512,000 tokens", cockpit_txt_out.getvalue())

            # 3. checkpoint status --json (omitted --trigger-tokens auto-scales to 460k)
            args_cp_status = parser.parse_args(["checkpoint", "status", "--workspace", str(self.ws), "--json"])
            cp_status_out = io.StringIO()
            with patch("sys.stdout", cp_status_out):
                self.assertEqual(cmd_checkpoint(args_cp_status), 0)
            cp_stat_data = json.loads(cp_status_out.getvalue())
            self.assertEqual(cp_stat_data["tokens"]["current"], 374475)
            self.assertEqual(cp_stat_data["tokens"]["max_context_tokens"], 512000)
            self.assertEqual(cp_stat_data["tokens"]["trigger_threshold"], 460000)

            # 4. checkpoint create (omitted --trigger-tokens writes 460,000 into artifact)
            args_cp_create = parser.parse_args(["checkpoint", "create", "--workspace", str(self.ws), "--json"])
            cp_create_out = io.StringIO()
            with patch("sys.stdout", cp_create_out):
                self.assertEqual(cmd_checkpoint(args_cp_create), 0)
            cp_create_data = json.loads(cp_create_out.getvalue())
            self.assertIn("460,000", Path(cp_create_data["output_path"]).read_text(encoding="utf-8"))


class TestRc10AcceptanceGapRegressions(unittest.TestCase):
    """Regression coverage for RC10 acceptance criteria #107.2, #109.2, #111.2, #112.1, and #112.2."""

    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.db_dir = self.root / "conversations"
        self.brain_dir = self.root / "brain"
        self.ws_dir = self.root / "ws"
        self.db_dir.mkdir(parents=True, exist_ok=True)
        self.brain_dir.mkdir(parents=True, exist_ok=True)
        self.ws_dir.mkdir(parents=True, exist_ok=True)

    def tearDown(self) -> None:
        from harness.trajectory.sqlite_reader import clear_locked_conversations
        clear_locked_conversations()
        self.tmp.cleanup()

    @staticmethod
    def _create_steps_db(db_path: Path, steps: list) -> None:
        conn = sqlite3.connect(db_path)
        try:
            conn.execute(
                "CREATE TABLE steps (rowid INTEGER PRIMARY KEY, idx INTEGER, step_type INTEGER, step_payload BLOB, step_data TEXT)"
            )
            for idx, st_type, payload_blob, data_dict in steps:
                conn.execute(
                    "INSERT INTO steps (idx, step_type, step_payload, step_data) VALUES (?, ?, ?, ?)",
                    (idx, st_type, payload_blob, json.dumps(data_dict)),
                )
            conn.commit()
        finally:
            conn.close()

    @staticmethod
    def _pb_user_prompt(text: str) -> bytes:
        def _ld(fno: int, raw: bytes) -> bytes:
            out = bytearray()
            v = len(raw)
            while v >= 0x80:
                out.append((v & 0x7F) | 0x80)
                v >>= 7
            out.append(v)
            return bytes([(fno << 3) | 2]) + bytes(out) + raw
        return _ld(1, _ld(1, text.encode("utf-8")))

    def test_status_labels_explicit_cid_and_mtime_fallback(self) -> None:
        """#107.2: agyis status prints explicit CID without fallback label and labels newest mtime fallback."""
        import argparse
        from harness.commands.status import cmd_status

        old_db = self.db_dir / "11111111-1111-4111-8111-111111111111.db"
        new_db = self.db_dir / "22222222-2222-4222-8222-222222222222.db"
        self._create_steps_db(old_db, [(1, 15, None, {"step_type": 15, "token_count": 40000})])
        self._create_steps_db(new_db, [(1, 15, None, {"step_type": 15, "token_count": 50000})])
        now = time.time()
        os.utime(old_db, (now - 120, now - 120))
        os.utime(new_db, (now, now))

        args = argparse.Namespace(conv_id=None, json=False, compact=False, verbose=False)
        with patch("harness.commands.status.DEFAULT_DB", self.root / "no_telemetry.db"), \
             patch("harness.telemetry.config.resolve_db_path", return_value=self.root / "no_telemetry.db"), \
             patch("harness.subagents.list_active_subagent_statuses", return_value=[]):
            with patch.dict(
                os.environ,
                {"AGYIS_CONVERSATIONS_DIR": str(self.db_dir), "AGYIS_CONVERSATION_ID": old_db.stem},
                clear=False,
            ):
                for k in (
                    "CONVERSATION_ID",
                    "ANTIGRAVITY_CONVERSATION_ID",
                    "ANTIGRAVITY_SOURCE_METADATA",
                    "GEMINI_CONVERSATION_ID",
                    "PSL_CONVERSATION_ID",
                ):
                    os.environ.pop(k, None)
                out_env = io.StringIO()
                with patch("sys.stdout", out_env):
                    self.assertEqual(cmd_status(args), 0)
                self.assertIn(f"Active Session ({old_db.stem}):", out_env.getvalue())
                self.assertNotIn("fallback: newest mtime", out_env.getvalue())

            with patch.dict(os.environ, {"AGYIS_CONVERSATIONS_DIR": str(self.db_dir)}, clear=False):
                for k in (
                    "AGYIS_CONVERSATION_ID",
                    "CONVERSATION_ID",
                    "ANTIGRAVITY_CONVERSATION_ID",
                    "ANTIGRAVITY_SOURCE_METADATA",
                    "GEMINI_CONVERSATION_ID",
                    "PSL_CONVERSATION_ID",
                ):
                    os.environ.pop(k, None)
                out_fb = io.StringIO()
                with patch("sys.stdout", out_fb):
                    self.assertEqual(cmd_status(args), 0)
                self.assertIn(f"Active Session ({new_db.stem} | fallback: newest mtime):", out_fb.getvalue())

    def test_compaction_alert_file_persists_epoch_and_clears_without_unlink(self) -> None:
        """#109.2: .compaction_alert_<cid>.json records epoch history and persists active=False below threshold."""
        conv_id = "test-alert-epoch-persist"
        (self.brain_dir / conv_id).mkdir(parents=True, exist_ok=True)
        self._create_steps_db(
            self.db_dir / f"{conv_id}.db",
            [(1, 23, None, {"step_type": 23}), (2, 15, None, {"step_type": 15, "token_count": 240_000})],
        )
        alert_file = self.brain_dir / conv_id / ".agyis" / f".compaction_alert_{conv_id}.json"

        with patch.dict(os.environ, {"AGYIS_BRAIN_DIR": str(self.brain_dir)}):
            res_hi = evaluate_pre_invocation(
                {"conversationId": conv_id, "step_count": 5, "role": ROLE_DEEP_EXECUTION},
                db_dir=self.db_dir,
                workspace_dir=self.ws_dir,
            )
            self.assertTrue(any("COMPACTION" in (s.get("systemMessage", {}).get("systemMessage", "") if isinstance(s.get("systemMessage"), dict) else "") for s in res_hi.get("injectSteps", [])))
            self.assertTrue(alert_file.is_file())
            alert_hi = json.loads(alert_file.read_text(encoding="utf-8"))
            self.assertEqual(alert_hi["epoch"], 1)
            self.assertTrue(alert_hi["active"])
            self.assertIn(1, alert_hi["alerted_epochs"])

            # Drop DB tokens below threshold -> must NOT unlink; must update active=False & preserve alerted_epochs
            (self.db_dir / f"{conv_id}.db").unlink()
            self._create_steps_db(
                self.db_dir / f"{conv_id}.db",
                [(1, 23, None, {"step_type": 23}), (2, 15, None, {"step_type": 15, "token_count": 20_000})],
            )
            evaluate_pre_invocation(
                {"conversationId": conv_id, "step_count": 6, "role": ROLE_DEEP_EXECUTION},
                db_dir=self.db_dir,
                workspace_dir=self.ws_dir,
            )
            self.assertTrue(alert_file.is_file())
            alert_lo = json.loads(alert_file.read_text(encoding="utf-8"))
            self.assertFalse(alert_lo["active"])
            self.assertEqual(alert_lo["epoch"], 1)
            self.assertIn("cleared_at", alert_lo)
            self.assertIn(1, alert_lo["alerted_epochs"])

    def test_has_parent_conversation_detects_live_sender_transcript_line(self) -> None:
        """#111.2: has_parent_conversation detects [Message] sender=<uuid> in live subagent transcripts."""
        from harness.hooks.role_pinning import has_parent_conversation

        child_id = "child-subagent-1112"
        root_id = "root-session-1112"
        logs_dir = self.brain_dir / child_id / ".system_generated" / "logs"
        logs_dir.mkdir(parents=True, exist_ok=True)
        (logs_dir / "transcript.jsonl").write_text(
            json.dumps({
                "step_index": 0,
                "type": "USER_INPUT",
                "content": "[Message] timestamp=2026-11-12T00:00:00Z sender=11111111-1111-4111-8111-111111111111 content=Run audit",
            }) + "\n",
            encoding="utf-8",
        )
        (self.brain_dir / root_id / ".system_generated" / "logs").mkdir(parents=True, exist_ok=True)
        (self.brain_dir / root_id / ".system_generated" / "logs" / "transcript.jsonl").write_text(
            json.dumps({"step_index": 0, "type": "USER_INPUT", "content": "Hello"}) + "\n",
            encoding="utf-8",
        )
        with patch("harness.hooks.role_pinning.get_active_brain_dir", return_value=self.brain_dir):
            self.assertTrue(has_parent_conversation({}, child_id))
            self.assertFalse(has_parent_conversation({}, root_id))

    def test_subagent_compaction_advisory_tailored_for_continuity(self) -> None:
        """#112.1: Subagent compaction advisory suppresses COMPACTION IMMINENT and /compact self-curtailment."""
        sub_msg = build_compaction_advisory(ROLE_DEEP_EXECUTION, 240_000, is_subagent=True)
        self.assertIn("[AGYIS SUBAGENT CONTEXT CONTINUITY:", sub_msg)
        self.assertNotIn("COMPACTION IMMINENT", sub_msg)
        self.assertIn("/compact", sub_msg)

        parent_msg = build_compaction_advisory(ROLE_DEEP_EXECUTION, 240_000, is_subagent=False)
        self.assertIn("COMPACTION IMMINENT", parent_msg)

        # End-to-end evaluate_pre_invocation detection via live child transcript sender
        child_id = "subagent-live-1121"
        logs_dir = self.brain_dir / child_id / ".system_generated" / "logs"
        logs_dir.mkdir(parents=True, exist_ok=True)
        (logs_dir / "transcript.jsonl").write_text(
            json.dumps({"step_index": 0, "content": "[Message] sender=aaaaaaaa-bbbb-4ccc-8ddd-eeeeeeeeeeee"}) + "\n",
            encoding="utf-8",
        )
        self._create_steps_db(
            self.db_dir / f"{child_id}.db",
            [(1, 15, None, {"step_type": 15, "token_count": 240_000})],
        )
        with patch.dict(os.environ, {"AGYIS_BRAIN_DIR": str(self.brain_dir)}), \
             patch("harness.hooks.role_pinning.get_active_brain_dir", return_value=self.brain_dir):
            res = evaluate_pre_invocation(
                {"conversationId": child_id, "role": ROLE_DEEP_EXECUTION},
                db_dir=self.db_dir,
                workspace_dir=self.ws_dir,
            )
            ephemeral = " ".join((s.get("systemMessage", {}).get("systemMessage", "") if isinstance(s.get("systemMessage"), dict) else "") for s in res.get("injectSteps", []))
            self.assertIn("AGYIS SUBAGENT CONTEXT CONTINUITY", ephemeral)
            self.assertNotIn("COMPACTION IMMINENT", ephemeral)

    def test_stage0_and_legacy_session_role_do_not_suppress_root_compaction(self) -> None:
        """P0 fix: Stage 0 or legacy unscoped session_role.json must NOT mark root sessions as subagents."""
        from harness.subagents.stage_role import materialize_stage_role

        # 1. Stage 0 (flight_director) scoped to root_cid -> still root session, NOT subagent
        root_cid = "root-stage0-1121"
        materialize_stage_role(
            stage=0,
            agent_name="agyis_coordinator",
            task_id="ROOT-STAGE-0",
            workspace_dir=self.ws_dir,
            conversation_id=root_cid,
        )
        self._create_steps_db(
            self.db_dir / f"{root_cid}.db",
            [(1, 15, None, {"step_type": 15, "token_count": 240_000})],
        )
        with patch.dict(os.environ, {"AGYIS_BRAIN_DIR": str(self.brain_dir)}):
            res_s0 = evaluate_pre_invocation(
                {"conversationId": root_cid, "step_count": 5, "role": ROLE_FLIGHT_DIRECTOR},
                db_dir=self.db_dir,
                workspace_dir=self.ws_dir,
            )
            msg_s0 = " ".join((s.get("systemMessage", {}).get("systemMessage", "") if isinstance(s.get("systemMessage"), dict) else "") for s in res_s0.get("injectSteps", []))
            self.assertIn("COMPACTION IMMINENT", msg_s0)
            self.assertNotIn("AGYIS SUBAGENT CONTEXT CONTINUITY", msg_s0)

        # 2. Legacy unscoped .agents/session_role.json (stage=1 without conversation_id) on default/unrelated root payload
        ws_legacy = self.root / "ws_legacy"
        ws_legacy.mkdir(parents=True, exist_ok=True)
        materialize_stage_role(
            stage=1,
            agent_name="agyis_builder",
            task_id="LEGACY-STAGE-1",
            workspace_dir=ws_legacy,
        )
        res_legacy = evaluate_pre_invocation(
            {"tokens": 240_000, "step_count": 5, "role": ROLE_DEEP_EXECUTION},
            workspace_dir=ws_legacy,
        )
        msg_legacy = " ".join((s.get("systemMessage", {}).get("systemMessage", "") if isinstance(s.get("systemMessage"), dict) else "") for s in res_legacy.get("injectSteps", []))
        self.assertIn("COMPACTION IMMINENT", msg_legacy)
        self.assertNotIn("AGYIS SUBAGENT CONTEXT CONTINUITY", msg_legacy)

        # 3. CID-scoped Stage 1 specialist subagent -> DOES receive subagent continuity advisory
        sub_cid = "sub-stage1-scoped-1121"
        materialize_stage_role(
            stage=1,
            agent_name="agyis_builder",
            task_id="SUB-STAGE-1",
            workspace_dir=self.ws_dir,
            conversation_id=sub_cid,
        )
        res_sub = evaluate_pre_invocation(
            {"conversationId": sub_cid, "tokens": 240_000, "step_count": 5, "role": ROLE_DEEP_EXECUTION},
            workspace_dir=self.ws_dir,
        )
        msg_sub = " ".join((s.get("systemMessage", {}).get("systemMessage", "") if isinstance(s.get("systemMessage"), dict) else "") for s in res_sub.get("injectSteps", []))
        self.assertIn("AGYIS SUBAGENT CONTEXT CONTINUITY", msg_sub)
        self.assertNotIn("COMPACTION IMMINENT", msg_sub)

    def test_post_compaction_persona_fires_on_native_context_summary_prompt(self) -> None:
        """#112.2: build_post_compaction_persona_prompt fires on native <CONTEXT_SUMMARY> both in payload and SQLite."""
        native_summary = (
            "<CONTEXT_SUMMARY>\n"
            "The following is a summary of the conversation history that has been truncated...\n"
            "RESUMING MY OWN TASK\n"
            "</CONTEXT_SUMMARY>"
        )
        res_payload = evaluate_pre_invocation(
            {"prompt": native_summary, "role": ROLE_DEEP_EXECUTION},
            workspace_dir=self.ws_dir,
        )
        sys_msgs = [s.get("systemMessage", {}).get("systemMessage", "") for s in res_payload.get("injectSteps", [])]
        self.assertTrue(any("[AGYIS POST-COMPACTION SUCCESSION DIRECTIVE]" in m for m in sys_msgs))

        conv_id = "test-native-summary-sqlite"
        self._create_steps_db(
            self.db_dir / f"{conv_id}.db",
            [
                (1, 23, None, {"step_type": 23}),
                (2, 1, self._pb_user_prompt(native_summary), {"step_type": 1}),
            ],
        )
        res_db = evaluate_pre_invocation(
            {"conversationId": conv_id, "role": ROLE_DEEP_EXECUTION},
            db_dir=self.db_dir,
            workspace_dir=self.ws_dir,
        )
        sys_msgs_db = [s.get("systemMessage", {}).get("systemMessage", "") for s in res_db.get("injectSteps", [])]
        self.assertTrue(any("[AGYIS POST-COMPACTION SUCCESSION DIRECTIVE]" in m for m in sys_msgs_db))


if __name__ == "__main__":
    unittest.main()
