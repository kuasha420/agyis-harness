# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Arafat Zahan (@kuasha420)
# Corporate Stewardship & Infrastructure: Purrfect Software Limited (PSL)
# Governed by: ICARO-42/b Ordinance (Company-Supported Personal IP Framework)

"""
Unit tests for PreToolUse Token Proximity Guard Lifecycle Hook (ADR-014 / ADR-015).
Verifies:
1. Dynamic Urgency Gradient threshold calculations (<35k, 35k-45k, >=45k).
2. ANSI progress gauge rendering with bell alert (\\a) on critical.
3. Safe read-only SQLite inspection against mock databases and zero-crash fallbacks.
4. Fail-open PreToolUse contract: stdout always emits {"decision": "allow"}, exit code 0.
5. Integration with fail-safe hook runner (runner.py) and hooks.json registration.
"""

from __future__ import annotations

import io
import json
import os
from pathlib import Path
import sqlite3
import sys
import tempfile
from typing import Any, Optional
import unittest
from unittest.mock import patch

from harness.hooks import runner
from harness.hooks.token_proximity_guard import (
    AMBER_THRESHOLD,
    CHECKPOINT_STEP_TYPE,
    COMPACTION_THRESHOLD,
    RED_THRESHOLD,
    check_token_proximity,
    extract_tokens_from_protobuf_metadata,
    format_terminal_gauge,
    get_active_conversation_tokens,
    get_urgency_tier,
    is_checkpoint_step,
    main as guard_main,
    render_terminal_gauge,
    run_token_proximity_guard,
)


class TestTokenProximityThresholds(unittest.TestCase):
    """Verifies threshold constants and tier classification."""

    def test_threshold_constants(self):
        """Asserts canonical threshold values match specification."""
        self.assertEqual(COMPACTION_THRESHOLD, 50000)
        self.assertEqual(AMBER_THRESHOLD, 35000)
        self.assertEqual(RED_THRESHOLD, 45000)

    def test_get_urgency_tier(self):
        """Tests boundary transitions for Safe, Elevated, and Critical tiers."""
        self.assertEqual(get_urgency_tier(0), "SAFE")
        self.assertEqual(get_urgency_tier(15000), "SAFE")
        self.assertEqual(get_urgency_tier(34999), "SAFE")
        self.assertEqual(get_urgency_tier(35000), "ELEVATED")
        self.assertEqual(get_urgency_tier(40000), "ELEVATED")
        self.assertEqual(get_urgency_tier(44999), "ELEVATED")
        self.assertEqual(get_urgency_tier(45000), "CRITICAL")
        self.assertEqual(get_urgency_tier(50000), "CRITICAL")
        self.assertEqual(get_urgency_tier(75000), "CRITICAL")


class TestRenderTerminalGauge(unittest.TestCase):
    """Verifies ANSI output formatting, percentage, and terminal bell alerts."""

    def test_render_safe_gauge(self):
        """Safe tier outputs green styling and does not emit terminal bell."""
        gauge = render_terminal_gauge(20000)
        self.assertIn("SAFE", gauge)
        self.assertIn("20,000 / 50,000 (40.0%)", gauge)
        self.assertIn("\033[1;32m", gauge)
        self.assertNotIn("\a", gauge)

    def test_render_amber_gauge(self):
        """Elevated tier outputs amber/yellow styling and does not emit terminal bell."""
        gauge = render_terminal_gauge(38500)
        self.assertIn("ELEVATED", gauge)
        self.assertIn("38,500 / 50,000 (77.0%)", gauge)
        self.assertIn("\033[1;33m", gauge)
        self.assertNotIn("\a", gauge)

    def test_render_critical_gauge(self):
        """Critical tier outputs bold red styling and emits terminal bell (\\a)."""
        gauge = render_terminal_gauge(47500)
        self.assertIn("CRITICAL", gauge)
        self.assertIn("47,500 / 50,000 (95.0%)", gauge)
        self.assertIn("\033[1;31m", gauge)
        self.assertTrue(gauge.startswith("\a"), "Critical gauge must begin with terminal bell")

    def test_format_terminal_gauge_custom_threshold(self):
        """Supports customized threshold denominators."""
        gauge = format_terminal_gauge(10000, threshold=20000)
        self.assertIn("10,000 / 20,000 (50.0%)", gauge)


class TestSQLiteInspectionHermetic(unittest.TestCase):
    """Verifies safe read-only queries against hermetic mock databases."""

    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_dir = Path(self.temp_dir.name)

    def tearDown(self):
        self.temp_dir.cleanup()

    def _create_mock_db(self, conv_id: str, steps_data: list) -> Path:
        db_path = self.db_dir / f"{conv_id}.db"
        conn = sqlite3.connect(db_path)
        cur = conn.cursor()
        cur.execute("CREATE TABLE steps (step_index INTEGER PRIMARY KEY, step_data TEXT)")
        for idx, sdata in enumerate(steps_data):
            cur.execute("INSERT INTO steps VALUES (?, ?)", (idx + 1, json.dumps(sdata)))
        conn.commit()
        conn.close()
        return db_path

    def test_missing_database_returns_zero(self):
        """Non-existent database file returns 0 without raising exceptions."""
        tokens = get_active_conversation_tokens("nonexistent-conv", db_dir=self.db_dir)
        self.assertEqual(tokens, 0)

    def test_empty_or_default_conv_id_returns_zero(self):
        """Empty or 'default' conversation IDs return 0."""
        self.assertEqual(get_active_conversation_tokens("", db_dir=self.db_dir), 0)
        self.assertEqual(get_active_conversation_tokens("default", db_dir=self.db_dir), 0)

    def test_corrupt_database_returns_zero(self):
        """Unreadable or corrupted database returns 0 fail-open."""
        corrupt_path = self.db_dir / "corrupt-conv.db"
        corrupt_path.write_bytes(b"NOT A SQLITE FILE")
        tokens = get_active_conversation_tokens("corrupt-conv", db_dir=self.db_dir)
        self.assertEqual(tokens, 0)

    def test_read_tokens_from_generator_metadata(self):
        """Extracts token count from generator_metadata.metadata.value.message_prompts[0].num_tokens."""
        conv_id = "test-session-amber"
        mock_steps = [
            {
                "generator_metadata": {
                    "metadata": {
                        "value": {
                            "message_prompts": [{"num_tokens": 38200}]
                        }
                    }
                }
            }
        ]
        self._create_mock_db(conv_id, mock_steps)
        tokens = get_active_conversation_tokens(conv_id, db_dir=self.db_dir)
        self.assertEqual(tokens, 38200)

    def test_read_tokens_from_camel_case_num_tokens(self):
        """Extracts token count from message_prompts[0].numTokens."""
        conv_id = "test-session-critical"
        mock_steps = [
            {
                "generator_metadata": {
                    "metadata": {
                        "value": {
                            "message_prompts": [{"numTokens": 46500}]
                        }
                    }
                }
            }
        ]
        self._create_mock_db(conv_id, mock_steps)
        tokens = get_active_conversation_tokens(conv_id, db_dir=self.db_dir)
        self.assertEqual(tokens, 46500)

    def test_read_tokens_latest_step_precedence(self):
        """Ensures the latest step's token count is retrieved."""
        conv_id = "test-session-multiple"
        mock_steps = [
            {"generator_metadata": {"metadata": {"value": {"message_prompts": [{"num_tokens": 15000}]}}}},
            {"generator_metadata": {"metadata": {"value": {"message_prompts": [{"num_tokens": 28000}]}}}},
            {"generator_metadata": {"metadata": {"value": {"message_prompts": [{"num_tokens": 42000}]}}}},
        ]
        self._create_mock_db(conv_id, mock_steps)
        tokens = get_active_conversation_tokens(conv_id, db_dir=self.db_dir)
        self.assertEqual(tokens, 42000)

    def test_read_tokens_from_dedicated_column(self):
        """Extracts token count from dedicated token_count column in steps."""
        conv_id = "test-session-col"
        db_path = self.db_dir / f"{conv_id}.db"
        conn = sqlite3.connect(db_path)
        cur = conn.cursor()
        cur.execute("CREATE TABLE steps (step_index INTEGER PRIMARY KEY, token_count INTEGER)")
        cur.execute("INSERT INTO steps VALUES (1, 36000)")
        conn.commit()
        conn.close()

        tokens = get_active_conversation_tokens(conv_id, db_dir=self.db_dir)
        self.assertEqual(tokens, 36000)

    def test_read_tokens_from_gen_metadata_table(self):
        """Extracts token count from gen_metadata table fallback."""
        conv_id = "test-session-gen-meta"
        db_path = self.db_dir / f"{conv_id}.db"
        conn = sqlite3.connect(db_path)
        cur = conn.cursor()
        cur.execute("CREATE TABLE gen_metadata (idx INTEGER PRIMARY KEY, data TEXT)")
        cur.execute("INSERT INTO gen_metadata VALUES (1, ?)", (json.dumps({"num_tokens": 37500}),))
        conn.commit()
        conn.close()

        tokens = get_active_conversation_tokens(conv_id, db_dir=self.db_dir)
        self.assertEqual(tokens, 37500)

    def test_read_tokens_from_json_metadata_column(self):
        """Extracts token count from steps.metadata JSON string."""
        conv_id = "test-session-meta-json"
        db_path = self.db_dir / f"{conv_id}.db"
        conn = sqlite3.connect(db_path)
        cur = conn.cursor()
        cur.execute("CREATE TABLE steps (idx INTEGER PRIMARY KEY, metadata TEXT)")
        cur.execute("INSERT INTO steps VALUES (1, ?)", (json.dumps({"tokens": 48000}),))
        conn.commit()
        conn.close()

        tokens = get_active_conversation_tokens(conv_id, db_dir=self.db_dir)
        self.assertEqual(tokens, 48000)

    def test_env_dir_resolution(self):
        """Asserts ANTIGRAVITY_CONVERSATIONS_DIR environment variable is respected."""
        conv_id = "env-resolved-session"
        self._create_mock_db(conv_id, [{"token_count": 39500}])
        with patch.dict(os.environ, {"ANTIGRAVITY_CONVERSATIONS_DIR": str(self.db_dir)}):
            tokens = get_active_conversation_tokens(conv_id)
            self.assertEqual(tokens, 39500)


class TestCheckTokenProximityLogic(unittest.TestCase):
    """Verifies warning emission behavior and decisions."""

    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_dir = Path(self.temp_dir.name)

    def tearDown(self):
        self.temp_dir.cleanup()

    def _create_db_with_tokens(self, conv_id: str, tokens: int):
        db_path = self.db_dir / f"{conv_id}.db"
        conn = sqlite3.connect(db_path)
        cur = conn.cursor()
        cur.execute("CREATE TABLE steps (step_index INTEGER PRIMARY KEY, step_data TEXT)")
        payload = {"generator_metadata": {"metadata": {"value": {"message_prompts": [{"num_tokens": tokens}]}}}}
        cur.execute("INSERT INTO steps VALUES (1, ?)", (json.dumps(payload),))
        conn.commit()
        conn.close()

    def test_safe_zone_no_stderr(self):
        """Safe zone (<35k) does not emit warning to stderr."""
        conv_id = "safe-conv"
        self._create_db_with_tokens(conv_id, 25000)

        with patch("sys.stderr", new_callable=io.StringIO) as mock_err:
            res = check_token_proximity(conv_id, db_dir=self.db_dir)
            self.assertEqual(res["decision"], "allow")
            self.assertEqual(res["tier"], "SAFE")
            self.assertFalse(res["warned"])
            self.assertEqual(mock_err.getvalue(), "")

    def test_amber_zone_emits_stderr(self):
        """Amber zone (35k–45k) emits warning gauge to stderr without bell."""
        conv_id = "amber-conv"
        self._create_db_with_tokens(conv_id, 39000)

        with patch("sys.stderr", new_callable=io.StringIO) as mock_err:
            res = check_token_proximity(conv_id, db_dir=self.db_dir)
            self.assertEqual(res["decision"], "allow")
            self.assertEqual(res["tier"], "ELEVATED")
            self.assertTrue(res["warned"])
            err_out = mock_err.getvalue()
            self.assertIn("ELEVATED", err_out)
            self.assertNotIn("\a", err_out)

    def test_critical_zone_emits_bell_and_red_pulse(self):
        """Critical zone (>=45k) emits warning gauge with terminal bell (\\a)."""
        conv_id = "critical-conv"
        self._create_db_with_tokens(conv_id, 47000)

        with patch("sys.stderr", new_callable=io.StringIO) as mock_err:
            res = check_token_proximity(conv_id, db_dir=self.db_dir)
            self.assertEqual(res["decision"], "allow")
            self.assertEqual(res["tier"], "CRITICAL")
            self.assertTrue(res["warned"])
            err_out = mock_err.getvalue()
            self.assertIn("CRITICAL", err_out)
            self.assertIn("\a", err_out)

    def test_run_token_proximity_guard_functional(self):
        """Tests run_token_proximity_guard directly with custom stderr."""
        conv_id = "amber-direct"
        self._create_db_with_tokens(conv_id, 41000)
        custom_err = io.StringIO()

        with patch.dict(os.environ, {"ANTIGRAVITY_CONVERSATIONS_DIR": str(self.db_dir)}):
            payload = {"conversationId": conv_id}
            res = run_token_proximity_guard(payload, stderr=custom_err)
            self.assertEqual(res["decision"], "allow")
            self.assertIn("ELEVATED", custom_err.getvalue())


class TestHookMainExecution(unittest.TestCase):
    """Verifies stdin/stdout protojson protocol contracts in main()."""

    def test_main_empty_stdin_allows(self):
        """Empty stdin emits {'decision': 'allow'}."""
        with patch("sys.stdin", io.StringIO("")), patch("sys.stdout", new_callable=io.StringIO) as mock_out:
            guard_main()
            data = json.loads(mock_out.getvalue().strip())
            self.assertEqual(data.get("decision"), "allow")

    def test_main_malformed_json_allows(self):
        """Malformed JSON on stdin emits {'decision': 'allow'} fail-open."""
        with patch("sys.stdin", io.StringIO("{bad json")), patch("sys.stdout", new_callable=io.StringIO) as mock_out:
            guard_main()
            data = json.loads(mock_out.getvalue().strip())
            self.assertEqual(data.get("decision"), "allow")

    def test_main_pre_tool_use_execution(self):
        """Valid PreToolUse payload emits allow decision."""
        payload = {
            "conversationId": "nonexistent-session",
            "toolCall": {"name": "run_command", "args": {"CommandLine": "ls"}}
        }
        with patch("sys.stdin", io.StringIO(json.dumps(payload))), patch("sys.stdout", new_callable=io.StringIO) as mock_out:
            guard_main()
            data = json.loads(mock_out.getvalue().strip())
            self.assertEqual(data.get("decision"), "allow")

    def test_main_action_get_tokens(self):
        """Tests testing action 'get_tokens'."""
        payload = {"action": "get_tokens", "conversationId": "nonexistent"}
        with patch("sys.stdin", io.StringIO(json.dumps(payload))), patch("sys.stdout", new_callable=io.StringIO) as mock_out:
            guard_main()
            data = json.loads(mock_out.getvalue().strip())
            self.assertEqual(data.get("status"), "ok")
            self.assertEqual(data.get("tokens"), 0)
            self.assertEqual(data.get("tier"), "SAFE")

    def test_main_action_render_gauge(self):
        """Tests testing action 'render_gauge'."""
        payload = {"action": "render_gauge", "tokens": 46000}
        with patch("sys.stdin", io.StringIO(json.dumps(payload))), patch("sys.stdout", new_callable=io.StringIO) as mock_out:
            guard_main()
            data = json.loads(mock_out.getvalue().strip())
            self.assertEqual(data.get("status"), "ok")
            self.assertIn("CRITICAL", data.get("gauge"))


class TestHookRunnerIntegration(unittest.TestCase):
    """Verifies runner.py module resolution and hooks.json registration."""

    def test_runner_resolves_token_proximity(self):
        """Asserts runner resolves 'token-proximity' and aliases."""
        self.assertEqual(runner.resolve_hook_module("token-proximity"), "harness.hooks.token_proximity_guard")
        self.assertEqual(runner.resolve_hook_module("token"), "harness.hooks.token_proximity_guard")
        self.assertEqual(runner.resolve_hook_module("token_proximity_guard"), "harness.hooks.token_proximity_guard")
        self.assertEqual(runner.resolve_hook_module("token-proximity-guard"), "harness.hooks.token_proximity_guard")

    def test_hooks_json_registration(self):
        """Asserts psl-token-proximity-guard is configured in hooks.json under PreToolUse."""
        hooks_path = Path(__file__).resolve().parent.parent / "harness" / "hooks" / "hooks.json"
        with open(hooks_path, "r", encoding="utf-8") as f:
            cfg = json.load(f)

        guard = cfg.get("psl-token-proximity-guard")
        self.assertIsNotNone(guard, "psl-token-proximity-guard missing from hooks.json")
        pre_tool = guard.get("PreToolUse", [])
        self.assertTrue(len(pre_tool) > 0)
        cmd = pre_tool[0]["hooks"][0]["command"]
        self.assertIn("token-proximity", cmd)


def _encode_varint(val: int) -> bytes:
    """Encodes an integer into standard protobuf varint bytes."""
    res = bytearray()
    while val > 0x7F:
        res.append((val & 0x7F) | 0x80)
        val >>= 7
    res.append(val & 0x7F)
    return bytes(res)


def _encode_field(field_num: int, wire_type: int, val: Any) -> bytes:
    """Encodes a single protobuf tag, wire type, and payload."""
    tag = (field_num << 3) | wire_type
    res = bytearray(_encode_varint(tag))
    if wire_type == 0:
        res.extend(_encode_varint(int(val)))
    elif wire_type == 1:
        res.extend(val if isinstance(val, bytes) else b"\x00" * 8)
    elif wire_type == 2:
        if isinstance(val, str):
            val = val.encode("utf-8")
        res.extend(_encode_varint(len(val)))
        res.extend(val)
    elif wire_type == 5:
        res.extend(val if isinstance(val, bytes) else b"\x00" * 4)
    return bytes(res)


def build_usage_metadata_protobuf(
    prompt_tokens: Optional[int] = None,
    cached_tokens: Optional[int] = None,
    candidates_tokens: Optional[int] = None,
    total_tokens: Optional[int] = None,
    subfield_order: Optional[list[str]] = None,
    prefix_bytes: bytes = b"",
) -> bytes:
    """
    Constructs a complete protobuf metadata payload containing field 9 (UsageMetadata)
    with controllable subfields and byte ordering.
    """
    chunk = bytearray()
    order = subfield_order or ["candidates", "prompt", "total", "cached"]
    for item in order:
        if item == "candidates" and candidates_tokens is not None:
            chunk.extend(_encode_field(1, 0, candidates_tokens))
        elif item == "prompt" and prompt_tokens is not None:
            chunk.extend(_encode_field(2, 0, prompt_tokens))
        elif item == "total" and total_tokens is not None:
            chunk.extend(_encode_field(3, 0, total_tokens))
        elif item == "cached" and cached_tokens is not None:
            chunk.extend(_encode_field(5, 0, cached_tokens))

    field_9 = _encode_field(9, 2, bytes(chunk))
    return prefix_bytes + field_9


class TestSQLiteOrderingInversion(unittest.TestCase):
    """Verifies that step ordering is strictly chronological and never sorts by BLOB bytes (Defect 1)."""

    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_dir = Path(self.temp_dir.name)

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_blob_ordering_lexicographical_inversion_resistance_idx(self):
        """
        Step 1 has high byte prefix (0xFF) with low tokens (10k).
        Step 2 has low byte prefix (0x01) with high tokens (46k).
        ORDER BY 1 DESC would select Step 1 (10k).
        ORDER BY idx DESC correctly selects Step 2 (46k).
        """
        conv_id = "test-blob-inversion-idx"
        db_path = self.db_dir / f"{conv_id}.db"
        conn = sqlite3.connect(db_path)
        cur = conn.cursor()
        cur.execute("CREATE TABLE steps (idx INTEGER PRIMARY KEY, metadata BLOB)")

        # Step 1: BLOB has field 1 with 0xFF 0xFF (lexicographically greater than 0x00 0x00)
        blob_step_1 = build_usage_metadata_protobuf(prompt_tokens=10000, prefix_bytes=_encode_field(1, 2, b"\xff\xff"))
        # Step 2: BLOB has field 1 with 0x00 0x00 (lexicographically smaller)
        blob_step_2 = build_usage_metadata_protobuf(prompt_tokens=46000, prefix_bytes=_encode_field(1, 2, b"\x00\x00"))

        cur.execute("INSERT INTO steps (idx, metadata) VALUES (1, ?)", (blob_step_1,))
        cur.execute("INSERT INTO steps (idx, metadata) VALUES (2, ?)", (blob_step_2,))
        conn.commit()
        conn.close()

        tokens = get_active_conversation_tokens(conv_id, db_dir=self.db_dir)
        self.assertEqual(tokens, 46000, "Must retrieve latest chronological step (idx=2), not 0xFF-prefixed step 1")

    def test_blob_ordering_fallback_step_index(self):
        """Tests chronological ordering when primary key is named 'step_index'."""
        conv_id = "test-blob-inversion-step-index"
        db_path = self.db_dir / f"{conv_id}.db"
        conn = sqlite3.connect(db_path)
        cur = conn.cursor()
        cur.execute("CREATE TABLE steps (step_index INTEGER PRIMARY KEY, metadata BLOB)")

        blob_1 = build_usage_metadata_protobuf(prompt_tokens=12000, prefix_bytes=_encode_field(1, 2, b"\xfe\x00"))
        blob_2 = build_usage_metadata_protobuf(prompt_tokens=38000, prefix_bytes=_encode_field(1, 2, b"\x02\x00"))
        cur.execute("INSERT INTO steps (step_index, metadata) VALUES (1, ?)", (blob_1,))
        cur.execute("INSERT INTO steps (step_index, metadata) VALUES (2, ?)", (blob_2,))
        conn.commit()
        conn.close()

        tokens = get_active_conversation_tokens(conv_id, db_dir=self.db_dir)
        self.assertEqual(tokens, 38000)

    def test_blob_ordering_fallback_rowid(self):
        """Tests fallback to rowid DESC when neither idx nor step_index column is declared."""
        conv_id = "test-blob-inversion-rowid"
        db_path = self.db_dir / f"{conv_id}.db"
        conn = sqlite3.connect(db_path)
        cur = conn.cursor()
        cur.execute("CREATE TABLE steps (metadata BLOB)")

        blob_1 = build_usage_metadata_protobuf(prompt_tokens=15000, prefix_bytes=_encode_field(1, 2, b"\xfe\x00"))
        blob_2 = build_usage_metadata_protobuf(prompt_tokens=47000, prefix_bytes=_encode_field(1, 2, b"\x02\x00"))
        cur.execute("INSERT INTO steps (metadata) VALUES (?)", (blob_1,))
        cur.execute("INSERT INTO steps (metadata) VALUES (?)", (blob_2,))
        conn.commit()
        conn.close()

        tokens = get_active_conversation_tokens(conv_id, db_dir=self.db_dir)
        self.assertEqual(tokens, 47000)

    def test_step_data_json_ordering_by_idx(self):
        """Verifies step_data JSON column orders by idx rather than string key sorting."""
        conv_id = "test-json-inversion"
        db_path = self.db_dir / f"{conv_id}.db"
        conn = sqlite3.connect(db_path)
        cur = conn.cursor()
        cur.execute("CREATE TABLE steps (idx INTEGER PRIMARY KEY, step_data TEXT)")

        # Step 1 starts with 'z_' (alphabetically after 'a_')
        s1 = json.dumps({"z_prop": 1, "tokens": 15000})
        s2 = json.dumps({"a_prop": 1, "tokens": 41000})
        cur.execute("INSERT INTO steps (idx, step_data) VALUES (1, ?)", (s1,))
        cur.execute("INSERT INTO steps (idx, step_data) VALUES (2, ?)", (s2,))
        conn.commit()
        conn.close()

        tokens = get_active_conversation_tokens(conv_id, db_dir=self.db_dir)
        self.assertEqual(tokens, 41000)

    def test_gen_metadata_ordering_by_idx_and_rowid(self):
        """Verifies gen_metadata table orders by idx DESC or rowid DESC."""
        conv_id = "test-gen-meta-ordering"
        db_path = self.db_dir / f"{conv_id}.db"
        conn = sqlite3.connect(db_path)
        cur = conn.cursor()
        cur.execute("CREATE TABLE gen_metadata (idx INTEGER PRIMARY KEY, data BLOB)")

        blob_1 = build_usage_metadata_protobuf(prompt_tokens=11000, prefix_bytes=_encode_field(1, 2, b"\xff\xff"))
        blob_2 = build_usage_metadata_protobuf(prompt_tokens=39000, prefix_bytes=_encode_field(1, 2, b"\x01\x00"))
        cur.execute("INSERT INTO gen_metadata (idx, data) VALUES (1, ?)", (blob_1,))
        cur.execute("INSERT INTO gen_metadata (idx, data) VALUES (2, ?)", (blob_2,))
        conn.commit()
        conn.close()

        tokens = get_active_conversation_tokens(conv_id, db_dir=self.db_dir)
        self.assertEqual(tokens, 39000)


class TestVertexContextCacheProtobuf(unittest.TestCase):
    """Verifies protobuf UsageMetadata extraction and context cache summation (Defect 2)."""

    def test_extract_tokens_prompt_only_no_cache(self):
        """Standard prompt tokens without context caching."""
        payload = build_usage_metadata_protobuf(prompt_tokens=25000)
        self.assertEqual(extract_tokens_from_protobuf_metadata(payload), 25000)

    def test_extract_tokens_cache_only_no_prompt(self):
        """Context caching hits without uncached delta."""
        payload = build_usage_metadata_protobuf(cached_tokens=42000)
        self.assertEqual(extract_tokens_from_protobuf_metadata(payload), 42000)

    def test_extract_tokens_summation_live_step_91_reproduction(self):
        """
        Exact PM live scenario:
        promptTokenCount (subfield 2) = 2,879
        cachedContentTokenCount (subfield 5) = 94,046
        Expected Total = 96,925
        """
        payload = build_usage_metadata_protobuf(prompt_tokens=2879, cached_tokens=94046)
        self.assertEqual(extract_tokens_from_protobuf_metadata(payload), 96925)

    def test_extract_tokens_subfield_reverse_order(self):
        """Asserts order invariance when subfield 5 precedes subfield 2."""
        payload = build_usage_metadata_protobuf(
            prompt_tokens=10000,
            cached_tokens=50000,
            subfield_order=["cached", "prompt"],
        )
        self.assertEqual(extract_tokens_from_protobuf_metadata(payload), 60000)

    def test_extract_tokens_ignores_candidates_and_total_tokens(self):
        """Ensures subfield 1 (candidates) and subfield 3 (total) do not corrupt input token sum."""
        payload = build_usage_metadata_protobuf(
            candidates_tokens=1500,
            prompt_tokens=3000,
            total_tokens=99999,
            cached_tokens=45000,
        )
        # Should sum prompt (3000) + cached (45000) = 48000
        self.assertEqual(extract_tokens_from_protobuf_metadata(payload), 48000)

    def test_extract_tokens_corrupted_or_truncated_safe(self):
        """Asserts zero-crash fail-open behavior on corrupted or invalid payloads."""
        self.assertEqual(extract_tokens_from_protobuf_metadata(b""), 0)
        self.assertEqual(extract_tokens_from_protobuf_metadata(None), 0)
        self.assertEqual(extract_tokens_from_protobuf_metadata("not_bytes"), 0)
        self.assertEqual(extract_tokens_from_protobuf_metadata(b"\x4a\x05\x10\xff"), 0)

    def test_end_to_end_context_cache_triggers_critical_urgency(self):
        """End-to-end integration test asserting CRITICAL urgency tier when cache hits exceed 45k."""
        with tempfile.TemporaryDirectory() as td:
            db_dir = Path(td)
            conv_id = "test-session-cache-critical"
            db_path = db_dir / f"{conv_id}.db"
            conn = sqlite3.connect(db_path)
            cur = conn.cursor()
            cur.execute("CREATE TABLE steps (idx INTEGER PRIMARY KEY, metadata BLOB)")

            # 2,879 uncached + 94,046 cached = 96,925 total tokens
            pb = build_usage_metadata_protobuf(prompt_tokens=2879, cached_tokens=94046)
            cur.execute("INSERT INTO steps (idx, metadata) VALUES (1, ?)", (pb,))
            conn.commit()
            conn.close()

            res = check_token_proximity(conv_id, db_dir=db_dir, emit_stderr=False)
            self.assertEqual(res["decision"], "allow")
            self.assertEqual(res["tokens"], 96925)
            self.assertEqual(res["tier"], "CRITICAL")
            self.assertTrue(res["warned"])


class TestCheckpointStepTypeRecognition(unittest.TestCase):
    """Verifies that compaction checkpoints (step_type = 23) boundary scans correctly (Defect 3)."""

    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_dir = Path(self.temp_dir.name)

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_checkpoint_step_type_constant_and_helper(self):
        """Asserts CHECKPOINT_STEP_TYPE == 23 and is_checkpoint_step correctly classifies enums."""
        self.assertEqual(CHECKPOINT_STEP_TYPE, 23)
        self.assertTrue(is_checkpoint_step(23))
        self.assertTrue(is_checkpoint_step("23"))
        self.assertFalse(is_checkpoint_step(4))
        self.assertFalse(is_checkpoint_step("4"))
        self.assertFalse(is_checkpoint_step(15))
        self.assertFalse(is_checkpoint_step(None))
        self.assertFalse(is_checkpoint_step("invalid"))

    def test_checkpoint_step_type_23_stops_backward_scan(self):
        """
        Step 1 (idx=1, step_type=15): 48,000 tokens (Pre-compaction)
        Step 2 (idx=2, step_type=23): Compaction Checkpoint (no tokens)
        Step 3 (idx=3, step_type=14): User Turn post-compaction (no tokens)
        Querying at Step 3 must stop scanning at Step 2 and NOT report Step 1's 48k tokens.
        """
        conv_id = "test-checkpoint-boundary"
        db_path = self.db_dir / f"{conv_id}.db"
        conn = sqlite3.connect(db_path)
        cur = conn.cursor()
        cur.execute("CREATE TABLE steps (idx INTEGER PRIMARY KEY, step_type INTEGER, metadata BLOB)")

        pb_step_1 = build_usage_metadata_protobuf(prompt_tokens=48000)
        cur.execute("INSERT INTO steps (idx, step_type, metadata) VALUES (1, 15, ?)", (pb_step_1,))
        cur.execute("INSERT INTO steps (idx, step_type, metadata) VALUES (2, 23, NULL)")
        cur.execute("INSERT INTO steps (idx, step_type, metadata) VALUES (3, 14, NULL)")
        conn.commit()
        conn.close()

        tokens = get_active_conversation_tokens(conv_id, db_dir=self.db_dir)
        self.assertEqual(tokens, 0, "Scan must not bleed past step_type 23 compaction checkpoint into pre-compaction history")

    def test_checkpoint_step_type_23_with_post_compaction_model_step(self):
        """
        Step 1 (idx=1, step_type=15): 49,000 tokens (Pre-compaction)
        Step 2 (idx=2, step_type=23): Compaction Checkpoint
        Step 3 (idx=3, step_type=15): 14,000 tokens (Post-compaction model step)
        Querying must return 14,000 tokens (SAFE tier).
        """
        conv_id = "test-checkpoint-post-model"
        db_path = self.db_dir / f"{conv_id}.db"
        conn = sqlite3.connect(db_path)
        cur = conn.cursor()
        cur.execute("CREATE TABLE steps (idx INTEGER PRIMARY KEY, step_type INTEGER, metadata BLOB)")

        pb_1 = build_usage_metadata_protobuf(prompt_tokens=49000)
        pb_3 = build_usage_metadata_protobuf(prompt_tokens=14000)
        cur.execute("INSERT INTO steps (idx, step_type, metadata) VALUES (1, 15, ?)", (pb_1,))
        cur.execute("INSERT INTO steps (idx, step_type, metadata) VALUES (2, 23, NULL)")
        cur.execute("INSERT INTO steps (idx, step_type, metadata) VALUES (3, 15, ?)", (pb_3,))
        conn.commit()
        conn.close()

        tokens = get_active_conversation_tokens(conv_id, db_dir=self.db_dir)
        self.assertEqual(tokens, 14000)

    def test_step_type_4_is_not_treated_as_checkpoint(self):
        """
        Step 1 (idx=1, step_type=15): 38,000 tokens
        Step 2 (idx=2, step_type=4): Non-checkpoint step in Antigravity (no tokens)
        Step 3 (idx=3, step_type=14): User turn (no tokens)
        Since step_type = 4 is NOT a checkpoint, scan continues and returns 38,000 tokens.
        """
        conv_id = "test-step-type-4-non-checkpoint"
        db_path = self.db_dir / f"{conv_id}.db"
        conn = sqlite3.connect(db_path)
        cur = conn.cursor()
        cur.execute("CREATE TABLE steps (idx INTEGER PRIMARY KEY, step_type INTEGER, metadata BLOB)")

        pb_1 = build_usage_metadata_protobuf(prompt_tokens=38000)
        cur.execute("INSERT INTO steps (idx, step_type, metadata) VALUES (1, 15, ?)", (pb_1,))
        cur.execute("INSERT INTO steps (idx, step_type, metadata) VALUES (2, 4, NULL)")
        cur.execute("INSERT INTO steps (idx, step_type, metadata) VALUES (3, 14, NULL)")
        conn.commit()
        conn.close()

        tokens = get_active_conversation_tokens(conv_id, db_dir=self.db_dir)
        self.assertEqual(tokens, 38000, "step_type = 4 must not halt backward scan")

    def test_missing_step_type_column_schema_resilience(self):
        """Verifies backward compatibility when steps table lacks step_type column."""
        conv_id = "test-no-step-type"
        db_path = self.db_dir / f"{conv_id}.db"
        conn = sqlite3.connect(db_path)
        cur = conn.cursor()
        cur.execute("CREATE TABLE steps (idx INTEGER PRIMARY KEY, metadata BLOB)")

        pb = build_usage_metadata_protobuf(prompt_tokens=36000)
        cur.execute("INSERT INTO steps (idx, metadata) VALUES (1, ?)", (pb,))
        conn.commit()
        conn.close()

        tokens = get_active_conversation_tokens(conv_id, db_dir=self.db_dir)
        self.assertEqual(tokens, 36000)

    def test_checkpoint_in_step_data_json(self):
        """Verifies checkpoint barrier in step_data JSON format."""
        conv_id = "test-checkpoint-json"
        db_path = self.db_dir / f"{conv_id}.db"
        conn = sqlite3.connect(db_path)
        cur = conn.cursor()
        cur.execute("CREATE TABLE steps (idx INTEGER PRIMARY KEY, step_data TEXT)")

        s1 = json.dumps({"step_type": 15, "tokens": 45000})
        s2 = json.dumps({"step_type": 23, "summary": "compacted"})
        cur.execute("INSERT INTO steps (idx, step_data) VALUES (1, ?)", (s1,))
        cur.execute("INSERT INTO steps (idx, step_data) VALUES (2, ?)", (s2,))
        conn.commit()
        conn.close()

        tokens = get_active_conversation_tokens(conv_id, db_dir=self.db_dir)
        self.assertEqual(tokens, 0, "JSON step_type 23 must act as compaction barrier")

    def test_checkpoint_in_dedicated_token_column(self):
        """Verifies checkpoint barrier when steps table has dedicated token column."""
        conv_id = "test-checkpoint-col"
        db_path = self.db_dir / f"{conv_id}.db"
        conn = sqlite3.connect(db_path)
        cur = conn.cursor()
        cur.execute("CREATE TABLE steps (idx INTEGER PRIMARY KEY, token_count INTEGER, step_type INTEGER)")

        cur.execute("INSERT INTO steps VALUES (1, 48000, 15)")
        cur.execute("INSERT INTO steps VALUES (2, NULL, 23)")
        conn.commit()
        conn.close()

        tokens = get_active_conversation_tokens(conv_id, db_dir=self.db_dir)
        self.assertEqual(tokens, 0, "Dedicated token column query must respect checkpoint barrier")


if __name__ == "__main__":
    unittest.main()
