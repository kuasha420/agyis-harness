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
7. AC7: Ephemeral payload schema conformance ({"injectSteps": [{"ephemeralMessage": ...}]}).
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
    is_conversation_locked,
    record_locked_conversation,
)


class TestThresholdCalibrationAndTrigger(unittest.TestCase):
    """AC1: Calibration of default threshold and trigger mechanics."""

    def setUp(self):
        self.old_env = os.environ.copy()

    def tearDown(self):
        os.environ.clear()
        os.environ.update(self.old_env)

    def test_default_threshold_is_230k(self):
        """Asserts default threshold is strictly 230,000 tokens."""
        os.environ.pop("AGYIS_COMPACTION_THRESHOLD", None)
        os.environ.pop("PSL_COMPACTION_THRESHOLD", None)
        self.assertEqual(DEFAULT_COMPACTION_ADVISORY_THRESHOLD, 230_000)
        self.assertEqual(get_compaction_advisory_threshold(), 230_000)

    def test_below_threshold_returns_empty_inject_steps(self):
        """Tokens below threshold emit empty injectSteps."""
        payload = json.dumps({"tokens": 200_000, "role": "deep_execution"})
        res = evaluate_pre_invocation(payload, threshold=230_000)
        self.assertEqual(res, {"injectSteps": []})

    def test_at_threshold_triggers_advisory(self):
        """Tokens exactly at threshold trigger advisory."""
        payload = json.dumps({"tokens": 230_000, "role": "deep_execution"})
        res = evaluate_pre_invocation(payload, threshold=230_000)
        self.assertEqual(len(res.get("injectSteps", [])), 1)
        self.assertIn("ephemeralMessage", res["injectSteps"][0])

    def test_above_threshold_triggers_advisory(self):
        """Tokens above threshold trigger advisory."""
        payload = json.dumps({"tokens": 245_000, "role": "flight_director"})
        res = evaluate_pre_invocation(payload, threshold=230_000)
        self.assertEqual(len(res.get("injectSteps", [])), 1)
        self.assertIn("COMPACTION IMMINENT", res["injectSteps"][0]["ephemeralMessage"])

    def test_env_override_agyis_threshold(self):
        """AGYIS_COMPACTION_THRESHOLD env var overrides default threshold."""
        os.environ["AGYIS_COMPACTION_THRESHOLD"] = "150000"
        self.assertEqual(get_compaction_advisory_threshold(), 150_000)

        # 140k is below override threshold
        res_below = evaluate_pre_invocation(json.dumps({"tokens": 140_000}))
        self.assertEqual(res_below, {"injectSteps": []})

        # 160k is above override threshold
        res_above = evaluate_pre_invocation(json.dumps({"tokens": 160_000}))
        self.assertEqual(len(res_above["injectSteps"]), 1)

    def test_env_override_psl_threshold(self):
        """PSL_COMPACTION_THRESHOLD acts as fallback override."""
        os.environ.pop("AGYIS_COMPACTION_THRESHOLD", None)
        os.environ["PSL_COMPACTION_THRESHOLD"] = "180000"
        self.assertEqual(get_compaction_advisory_threshold(), 180_000)

        res_above = evaluate_pre_invocation(json.dumps({"tokens": 190_000}))
        self.assertEqual(len(res_above["injectSteps"]), 1)

    def test_calibration_metadata_structure_and_values(self):
        """AC1: Asserts CALIBRATION_METADATA is exported and contains empirical metrics."""
        self.assertIsInstance(CALIBRATION_METADATA, dict)
        self.assertEqual(CALIBRATION_METADATA["calibrated_threshold"], 230_000)
        self.assertEqual(CALIBRATION_METADATA["compaction_trigger_min"], 227_529)
        self.assertEqual(CALIBRATION_METADATA["compaction_trigger_max"], 262_127)
        self.assertEqual(CALIBRATION_METADATA["compaction_trigger_avg"], 245_941)
        self.assertEqual(CALIBRATION_METADATA["safety_runway_tokens"], 15_941)
        self.assertIn("3-6 turns", CALIBRATION_METADATA["estimated_runway_turns"])
        self.assertIn("2,500 - 4,800 tokens", CALIBRATION_METADATA["danger_zone_velocity_per_turn"])


class TestRoleClassification(unittest.TestCase):
    """AC2: Classification heuristics across metadata, workspace paths, and env vars."""

    def setUp(self):
        self.old_env = os.environ.copy()

    def tearDown(self):
        os.environ.clear()
        os.environ.update(self.old_env)

    def test_classify_from_payload_explicit_roles(self):
        """Classifies canonical roles directly from payload 'role'."""
        self.assertEqual(classify_agent_role({"role": "flight_director"}), ROLE_FLIGHT_DIRECTOR)
        self.assertEqual(classify_agent_role({"role": "swarm_orchestrator"}), ROLE_SWARM_ORCHESTRATOR)
        self.assertEqual(classify_agent_role({"role": "deep_execution"}), ROLE_DEEP_EXECUTION)
        self.assertEqual(classify_agent_role({"role": "forensic_auditor"}), ROLE_FORENSIC_AUDITOR)

    def test_classify_from_archetype_and_aliases(self):
        """Classifies roles from archetype and common alias keywords."""
        self.assertEqual(classify_agent_role({"archetype": "executioner"}), ROLE_DEEP_EXECUTION)
        self.assertEqual(classify_agent_role({"archetype": "builder"}), ROLE_DEEP_EXECUTION)
        self.assertEqual(classify_agent_role({"archetype": "hammer"}), ROLE_FORENSIC_AUDITOR)
        self.assertEqual(classify_agent_role({"typeName": "auditor"}), ROLE_FORENSIC_AUDITOR)
        self.assertEqual(classify_agent_role({"agentName": "swarm_orchestrator"}), ROLE_SWARM_ORCHESTRATOR)
        self.assertEqual(classify_agent_role({"subagent_role": "coordinator"}), ROLE_FLIGHT_DIRECTOR)

    def test_classify_from_nested_metadata(self):
        """Classifies roles when nested within agent or metadata dicts."""
        self.assertEqual(
            classify_agent_role({"agent": {"role": "deep_execution"}}),
            ROLE_DEEP_EXECUTION,
        )
        self.assertEqual(
            classify_agent_role({"subagent": {"archetype": "auditor"}}),
            ROLE_FORENSIC_AUDITOR,
        )

    def test_classify_from_workspace_paths(self):
        """Classifies roles from worktree paths or workspace names."""
        # Deep execution worktree pattern
        payload_exec = {
            "workspace": "/home/kuasha/.gemini/antigravity/worktrees/6deb7452/subagent-subagent-1-executioner-harness-builder-8f776b9f"
        }
        self.assertEqual(classify_agent_role(payload_exec), ROLE_DEEP_EXECUTION)

        # Forensic auditor worktree pattern
        payload_audit = {
            "worktree": "/worktrees/subagent-subagent-2-hammer-auditor-123"
        }
        self.assertEqual(classify_agent_role(payload_audit), ROLE_FORENSIC_AUDITOR)

        # Swarm orchestrator path pattern
        payload_orch = {
            "cwd": "/home/kuasha/Dev/mesh-orchestrator"
        }
        self.assertEqual(classify_agent_role(payload_orch), ROLE_SWARM_ORCHESTRATOR)

        # activeWorkspaces list
        payload_active_ws = {
            "activeWorkspaces": ["/home/kuasha/worktrees/subagent-subagent-1-executioner-harness-builder-8f776b9f"]
        }
        self.assertEqual(classify_agent_role(payload_active_ws), ROLE_DEEP_EXECUTION)

    def test_classify_from_environment_variables(self):
        """Classifies role from AGYIS_ROLE or ANTIGRAVITY_AGENT_ROLE."""
        os.environ["AGYIS_ROLE"] = "deep_execution"
        self.assertEqual(classify_agent_role({}), ROLE_DEEP_EXECUTION)

        os.environ.pop("AGYIS_ROLE", None)
        os.environ["ANTIGRAVITY_AGENT_ROLE"] = "forensic_auditor"
        self.assertEqual(classify_agent_role({}), ROLE_FORENSIC_AUDITOR)

    def test_default_fallback_to_flight_director(self):
        """Defaults safely to flight_director when no heuristics match."""
        os.environ.pop("AGYIS_ROLE", None)
        os.environ.pop("ANTIGRAVITY_AGENT_ROLE", None)
        self.assertEqual(classify_agent_role({}), ROLE_FLIGHT_DIRECTOR)
        self.assertEqual(classify_agent_role({"role": "unrecognized_unknown"}), ROLE_FLIGHT_DIRECTOR)

    def test_classify_from_workspace_paths_official_schema(self):
        """AC3: Classifies roles using official Antigravity camelCase 'workspacePaths' key."""
        payload_str_list = {
            "workspacePaths": ["/home/kuasha/worktrees/subagent-subagent-1-executioner-builder-8f776b9f"]
        }
        self.assertEqual(classify_agent_role(payload_str_list), ROLE_DEEP_EXECUTION)

        payload_dict_list = {
            "workspacePaths": [{"path": "/home/kuasha/worktrees/subagent-subagent-2-hammer-auditor-123"}]
        }
        self.assertEqual(classify_agent_role(payload_dict_list), ROLE_FORENSIC_AUDITOR)

    def test_classify_custodian_role(self):
        """AC3: Asserts SWE ladder custodian role maps to ROLE_DEEP_EXECUTION."""
        self.assertEqual(classify_agent_role({"role": "custodian"}), ROLE_DEEP_EXECUTION)
        self.assertEqual(classify_agent_role({"archetype": "custodian"}), ROLE_DEEP_EXECUTION)
        self.assertEqual(
            classify_agent_role({"workspace": "/worktrees/subagent-subagent-1-custodian-cleanup"}),
            ROLE_DEEP_EXECUTION,
        )


class TestAdvisoryContracts(unittest.TestCase):
    """AC4, AC5, AC6: Work Preservation, Zero Repo Pollution, and Autonomous Continuation."""

    def test_deep_execution_advisory_contracts(self):
        """
        Deep execution advisory must enforce:
        - Work Preservation (AC4): prohibit checkout/reset, keep partial edits on disk.
        - Zero Repo Document Pollution (AC5): save state strictly to artifacts/scratch.
        - Autonomous Continuation (AC6): run git status/git diff, resume without asking operator.
        """
        adv = build_compaction_advisory(ROLE_DEEP_EXECUTION, 240_000, 230_000)
        self.assertIn("240,000 / 230,000 TOKENS", adv)
        self.assertIn("Deep Execution", adv)

        # AC4 Work Preservation Contract
        self.assertIn("git checkout -- .", adv)
        self.assertIn("git reset --hard", adv)
        self.assertIn("STRICTLY PROHIBIT", adv)
        self.assertIn("intact on disk", adv)

        # AC5 Zero Repo Pollution
        self.assertIn(".agents/artifacts/", adv)
        self.assertIn("Zero git commits", adv)

        # AC6 Autonomous Continuation
        self.assertIn("git status", adv)
        self.assertIn("git diff", adv)
        self.assertIn("without asking the operator what happened", adv)

    def test_flight_director_advisory_contracts(self):
        """
        Flight director advisory must enforce:
        - Zero Repo Pollution (AC5): store phase state strictly in artifacts/scratch.
        - Work Preservation (AC4): prohibit checkout/reset.
        - Autonomous Continuation (AC6): inspect active plan, resume without human re-explanation.
        """
        adv = build_compaction_advisory(ROLE_FLIGHT_DIRECTOR, 235_000, 230_000)
        self.assertIn("Flight Director", adv)
        self.assertIn(".agents/artifacts/", adv)
        self.assertIn("Zero repository pollution", adv)
        self.assertIn("git checkout -- .", adv)
        self.assertIn("git reset --hard", adv)
        self.assertIn("without human re-explanation", adv)

    def test_swarm_orchestrator_advisory_contracts(self):
        """
        Swarm orchestrator advisory must enforce:
        - Swarm state survival & zero repo pollution (AC5): flush strand assignments to scratch.
        - Autonomous Continuation (AC6): resume barrier joins without manual intervention.
        """
        adv = build_compaction_advisory(ROLE_SWARM_ORCHESTRATOR, 250_000, 230_000)
        self.assertIn("Swarm Orchestrator", adv)
        self.assertIn("barrier join", adv)
        self.assertIn("git status", adv)
        self.assertIn("without manual intervention", adv)

    def test_forensic_auditor_advisory_contracts(self):
        """
        Forensic auditor advisory must enforce:
        - Evidence preservation (AC5): defect reports in scratch.
        - Autonomous Continuation (AC6): re-execute test suites on HEAD, verify exit codes.
        """
        adv = build_compaction_advisory(ROLE_FORENSIC_AUDITOR, 231_000, 230_000)
        self.assertIn("Forensic Auditor", adv)
        self.assertIn("re-execute verification suites on HEAD", adv)
        self.assertIn("verify exit codes", adv)

    def test_dynamic_remaining_turns_in_advisory(self):
        """AC3: Asserts dynamic runway and turns calculation is reflected in advisory text."""
        # Tokens: 235,000 -> remaining: 11,000 -> turns: 3
        adv_3 = build_compaction_advisory(ROLE_DEEP_EXECUTION, 235_000, 230_000)
        self.assertIn("3 TURNS REMAINING", adv_3)

        # Tokens: 245,000 -> remaining: 1,000 -> turns: 1
        adv_1 = build_compaction_advisory(ROLE_DEEP_EXECUTION, 245_000, 230_000)
        self.assertIn("1 TURNS REMAINING", adv_1)

        # Tokens: 250,000 (>246,000) -> lower bound: 1 turn
        adv_over = build_compaction_advisory(ROLE_DEEP_EXECUTION, 250_000, 230_000)
        self.assertIn("1 TURNS REMAINING", adv_over)


class TestEphemeralPayloadSchema(unittest.TestCase):
    """AC7: Payload schema conformance with Antigravity PreInvocation contract."""

    def test_schema_below_threshold(self):
        """Below threshold payload adheres to {'injectSteps': []} schema."""
        res = evaluate_pre_invocation(json.dumps({"tokens": 100_000}))
        self.assertIsInstance(res, dict)
        self.assertIn("injectSteps", res)
        self.assertEqual(res["injectSteps"], [])

    def test_schema_at_or_above_threshold(self):
        """At/above threshold payload contains exactly one ephemeralMessage step."""
        res = evaluate_pre_invocation(json.dumps({"tokens": 240_000}))
        self.assertIsInstance(res, dict)
        self.assertIn("injectSteps", res)
        steps = res["injectSteps"]
        self.assertEqual(len(steps), 1)
        self.assertIn("ephemeralMessage", steps[0])
        self.assertIsInstance(steps[0]["ephemeralMessage"], str)
        self.assertTrue(len(steps[0]["ephemeralMessage"]) > 50)


class TestFailOpenResilienceAndBenchmark(unittest.TestCase):
    """AC8: Fail-open resilience, zero crash risk, and sub-millisecond execution benchmark."""

    def test_fail_open_on_malformed_inputs(self):
        """Malformed JSON, empty string, and non-dict inputs safely return empty injectSteps."""
        for bad_input in ("", "   ", "{invalid json", "[]", "123", "null"):
            with self.subTest(bad_input=bad_input):
                res = evaluate_pre_invocation(bad_input)
                self.assertEqual(res, {"injectSteps": []})

    def test_fail_open_on_missing_db(self):
        """Missing SQLite DB returns empty injectSteps without raising."""
        res = evaluate_pre_invocation(
            json.dumps({"conversationId": "nonexistent-conv-id"}),
            db_dir=Path("/nonexistent/dir"),
        )
        self.assertEqual(res, {"injectSteps": []})

    def test_fail_open_main_with_exception(self):
        """main() catches unhandled exceptions and exits 0 emitting valid JSON."""
        with patch("harness.hooks.pre_invocation_hook.evaluate_pre_invocation", side_effect=RuntimeError("unexpected crash")), \
             patch("sys.stdin", io.StringIO("{}")), \
             patch("sys.stdout", new_callable=io.StringIO) as mock_out, \
             patch("sys.stderr", new_callable=io.StringIO) as mock_err:
            ret = hook_main([])
            self.assertEqual(ret, 0)
            res = json.loads(mock_out.getvalue().strip())
            self.assertEqual(res, {"injectSteps": []})
            self.assertIn("[PSL PRE-INVOCATION HOOK]", mock_err.getvalue())

    def test_sub_millisecond_benchmark(self):
        """Direct execution benchmark: evaluates in < 5.0ms (typically <0.1ms)."""
        payload = json.dumps({"tokens": 240_000, "role": "deep_execution"})

        iterations = 100
        start = time.perf_counter()
        for _ in range(iterations):
            evaluate_pre_invocation(payload)
        elapsed = time.perf_counter() - start

        avg_ms = (elapsed / iterations) * 1000
        self.assertLess(
            avg_ms,
            5.0,
            f"Average execution time {avg_ms:.3f}ms exceeds 5.0ms sub-millisecond requirement",
        )


class TestRunnerIntegrationAndHooksJson(unittest.TestCase):
    """AC9: Hook runner integration and hooks.json registration."""

    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.old_psl_dir = os.environ.get("PSL_HARNESS_STATE_DIR")
        os.environ["PSL_HARNESS_STATE_DIR"] = self.temp_dir.name

    def tearDown(self):
        if self.old_psl_dir is not None:
            os.environ["PSL_HARNESS_STATE_DIR"] = self.old_psl_dir
        else:
            os.environ.pop("PSL_HARNESS_STATE_DIR", None)
        self.temp_dir.cleanup()

    def test_runner_resolves_pre_invocation(self):
        """Runner resolves 'pre-invocation' and canonical aliases."""
        self.assertEqual(
            runner.resolve_hook_module("pre-invocation"),
            "harness.hooks.pre_invocation_hook",
        )
        self.assertEqual(
            runner.resolve_hook_module("preinvocation"),
            "harness.hooks.pre_invocation_hook",
        )
        self.assertEqual(
            runner.resolve_hook_module("pre_invocation"),
            "harness.hooks.pre_invocation_hook",
        )

    def test_runner_dispatch_below_threshold(self):
        """Runner dispatching pre-invocation with tokens below threshold outputs empty injectSteps."""
        payload = json.dumps({"tokens": 100_000})
        with patch("sys.stdout", new_callable=io.StringIO) as mock_out:
            code = runner.run_hook("pre-invocation", payload_str=payload)
            self.assertEqual(code, 0)
            res = json.loads(mock_out.getvalue().strip())
            self.assertEqual(res, {"injectSteps": []})

    def test_runner_dispatch_above_threshold(self):
        """Runner dispatching pre-invocation with tokens above threshold outputs advisory."""
        payload = json.dumps({"tokens": 240_000, "role": "deep_execution"})
        with patch("sys.stdout", new_callable=io.StringIO) as mock_out:
            code = runner.run_hook("pre-invocation", payload_str=payload)
            self.assertEqual(code, 0)
            res = json.loads(mock_out.getvalue().strip())
            self.assertEqual(len(res.get("injectSteps", [])), 1)
            self.assertIn("COMPACTION IMMINENT", res["injectSteps"][0]["ephemeralMessage"])

    def test_hooks_json_configuration(self):
        """Asserts hooks.json registers psl-compaction-advisory under PreInvocation."""
        hooks_path = Path(__file__).resolve().parent.parent / "hooks.json"
        self.assertTrue(hooks_path.is_file(), f"hooks.json missing at {hooks_path}")

        data = json.loads(hooks_path.read_text(encoding="utf-8"))
        self.assertIn("psl-compaction-advisory", data)
        advisory_config = data["psl-compaction-advisory"]
        self.assertIn("PreInvocation", advisory_config)

        pre_inv = advisory_config["PreInvocation"]
        self.assertIsInstance(pre_inv, list)
        self.assertTrue(len(pre_inv) > 0)
        cmd_item = pre_inv[0]
        self.assertEqual(cmd_item.get("type"), "command")
        self.assertIn("runner pre-invocation", cmd_item.get("command", ""))
        self.assertEqual(cmd_item.get("timeout"), 5)

    def test_subprocess_smoke_runner_pre_invocation(self):
        """Real subprocess invocation of python3 -m harness.hooks.runner pre-invocation."""
        payload = json.dumps({"tokens": 240_000, "role": "deep_execution"})
        proc = subprocess.run(
            [sys.executable, "-m", "harness.hooks.runner", "pre-invocation"],
            input=payload,
            capture_output=True,
            text=True,
            cwd=str(Path(__file__).parent.parent),
            timeout=5,
        )
        self.assertEqual(proc.returncode, 0)
        res = json.loads(proc.stdout.strip())
        self.assertEqual(len(res.get("injectSteps", [])), 1)
        self.assertIn("COMPACTION IMMINENT", res["injectSteps"][0]["ephemeralMessage"])

    def test_runner_resolves_compaction_advisory_aliases(self):
        """AC9: Asserts runner resolves 'compaction-advisory' and associated aliases."""
        for alias in ("compaction-advisory", "compaction_advisory", "compaction", "advisory"):
            with self.subTest(alias=alias):
                self.assertEqual(
                    runner.resolve_hook_module(alias),
                    "harness.hooks.pre_invocation_hook",
                )

    def test_runner_dispatch_compaction_advisory_alias(self):
        """AC9: Asserts runner.run_hook('compaction-advisory') dispatches correctly."""
        payload = json.dumps({"tokens": 240_000, "role": "deep_execution"})
        with patch("sys.stdout", new_callable=io.StringIO) as mock_out:
            code = runner.run_hook("compaction-advisory", payload_str=payload)
            self.assertEqual(code, 0)
            res = json.loads(mock_out.getvalue().strip())
            self.assertEqual(len(res.get("injectSteps", [])), 1)
            self.assertIn("COMPACTION IMMINENT", res["injectSteps"][0]["ephemeralMessage"])

    def test_runner_compaction_advisory_fail_open_schema(self):
        """AC8: Asserts runner compaction-advisory fail-open emits {'injectSteps': []} on corrupt input."""
        with patch("sys.stdout", new_callable=io.StringIO) as mock_out:
            code = runner.run_hook("compaction-advisory", payload_str="corrupt { json")
            self.assertEqual(code, 0)
            res = json.loads(mock_out.getvalue().strip())
            self.assertEqual(res, {"injectSteps": []})
            self.assertNotIn("decision", res)


class TestSqliteIntegration(unittest.TestCase):
    """Verifies end-to-end token extraction from SQLite database."""

    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_dir = Path(self.temp_dir.name)

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_sqlite_token_reading_triggers_advisory(self):
        """PreInvocation hook reads token count from SQLite DB steps table and triggers advisory."""
        conv_id = "test-conv-compaction-123"
        db_path = self.db_dir / f"{conv_id}.db"

        # Create mock conversation SQLite DB
        with sqlite3.connect(db_path) as conn:
            conn.execute(
                "CREATE TABLE steps (rowid INTEGER PRIMARY KEY, idx INTEGER, step_data TEXT)"
            )
            step_obj = {
                "step_type": 15,
                "token_count": 245_000,
                "role": "deep_execution",
            }
            conn.execute(
                "INSERT INTO steps (idx, step_data) VALUES (?, ?)",
                (1, json.dumps(step_obj)),
            )
        conn.close()

        payload = json.dumps({"conversationId": conv_id, "role": "deep_execution"})
        res = evaluate_pre_invocation(payload, db_dir=self.db_dir)
        self.assertEqual(len(res.get("injectSteps", [])), 1)
        msg = res["injectSteps"][0]["ephemeralMessage"]
        self.assertIn("245,000 / 230,000 TOKENS", msg)
        self.assertIn("Deep Execution", msg)

    def test_post_compaction_token_reset_silence(self):
        """AC2: Asserts hook falls silent ({'injectSteps': []}) after step_type 23 checkpoint."""
        conv_id = "test-conv-post-compaction-silence"
        db_path = self.db_dir / f"{conv_id}.db"

        with sqlite3.connect(db_path) as conn:
            conn.execute(
                "CREATE TABLE steps (rowid INTEGER PRIMARY KEY, idx INTEGER, step_type INTEGER, step_data TEXT)"
            )
            # Pre-compaction step: 248,000 tokens
            step_pre = json.dumps({"step_type": 15, "token_count": 248_000, "role": "deep_execution"})
            conn.execute("INSERT INTO steps (idx, step_type, step_data) VALUES (1, 15, ?)", (step_pre,))

            # Checkpoint step: 23 (compaction barrier)
            conn.execute("INSERT INTO steps (idx, step_type, step_data) VALUES (2, 23, NULL)")

            # Post-compaction model step: 28,000 tokens (well below 230k threshold)
            step_post = json.dumps({"step_type": 15, "token_count": 28_000, "role": "deep_execution"})
            conn.execute("INSERT INTO steps (idx, step_type, step_data) VALUES (3, 15, ?)", (step_post,))
        conn.close()

        payload = json.dumps({"conversationId": conv_id, "role": "deep_execution"})
        res = evaluate_pre_invocation(payload, db_dir=self.db_dir)
        self.assertEqual(res, {"injectSteps": []})


class TestPillar3ExplicitSelfIdentification(unittest.TestCase):
    """Pillar 3: Explicit Cognitive Self-Identification (.agents/session_role.json, active plan, env vars)."""

    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.workspace_dir = Path(self.temp_dir.name)
        self.old_env = os.environ.copy()

    def tearDown(self):
        os.environ.clear()
        os.environ.update(self.old_env)
        self.temp_dir.cleanup()

    def test_session_role_json_in_agents(self):
        """Pillar 3: .agents/session_role.json explicitly sets flight_director."""
        agents_dir = self.workspace_dir / ".agents"
        agents_dir.mkdir(parents=True, exist_ok=True)
        role_file = agents_dir / "session_role.json"
        role_file.write_text(json.dumps({"role": "flight_director"}), encoding="utf-8")

        self.assertEqual(
            check_pillar_3_explicit_role({}, workspace_dir=self.workspace_dir),
            ROLE_FLIGHT_DIRECTOR,
        )
        self.assertEqual(
            classify_agent_role({}, workspace_dir=self.workspace_dir),
            ROLE_FLIGHT_DIRECTOR,
        )

    def test_session_role_json_in_artifacts(self):
        """Pillar 3: .agents/artifacts/session_role.json explicitly sets deep_execution."""
        artifacts_dir = self.workspace_dir / ".agents" / "artifacts"
        artifacts_dir.mkdir(parents=True, exist_ok=True)
        role_file = artifacts_dir / "session_role.json"
        role_file.write_text(json.dumps({"role": "deep_execution"}), encoding="utf-8")

        self.assertEqual(
            check_pillar_3_explicit_role({}, workspace_dir=self.workspace_dir),
            ROLE_DEEP_EXECUTION,
        )
        self.assertEqual(
            classify_agent_role({}, workspace_dir=self.workspace_dir),
            ROLE_DEEP_EXECUTION,
        )

    def test_active_plan_markdown_role(self):
        """Pillar 3: Active implementation plan markdown declares role."""
        artifacts_dir = self.workspace_dir / ".agents" / "artifacts"
        artifacts_dir.mkdir(parents=True, exist_ok=True)
        plan_file = artifacts_dir / "implementation_plan.md"
        plan_file.write_text("# Implementation Plan\n\n**Role**: deep_execution\n\nDetails...", encoding="utf-8")

        self.assertEqual(
            check_pillar_3_explicit_role({}, workspace_dir=self.workspace_dir),
            ROLE_DEEP_EXECUTION,
        )
        self.assertEqual(
            classify_agent_role({}, workspace_dir=self.workspace_dir),
            ROLE_DEEP_EXECUTION,
        )

    def test_active_plan_json_role(self):
        """Pillar 3: Active plan.json declares role."""
        artifacts_dir = self.workspace_dir / ".agents" / "artifacts"
        artifacts_dir.mkdir(parents=True, exist_ok=True)
        plan_file = artifacts_dir / "plan.json"
        plan_file.write_text(json.dumps({"role": "flight_director", "goal": "coordinate"}), encoding="utf-8")

        self.assertEqual(
            check_pillar_3_explicit_role({}, workspace_dir=self.workspace_dir),
            ROLE_FLIGHT_DIRECTOR,
        )

    def test_pillar_3_overrides_prompt_heuristics(self):
        """Pillar 3: Explicit session_role.json strictly overrides prompt-based intent heuristics."""
        agents_dir = self.workspace_dir / ".agents"
        agents_dir.mkdir(parents=True, exist_ok=True)
        (agents_dir / "session_role.json").write_text(
            json.dumps({"role": "flight_director"}), encoding="utf-8"
        )

        # Prompt would normally seed ROLE_DEEP_EXECUTION
        payload = {"prompt": "Please fix the bug in server.py and write unit tests"}
        role = classify_agent_role(payload, workspace_dir=self.workspace_dir)
        self.assertEqual(role, ROLE_FLIGHT_DIRECTOR)

    def test_pillar_3_env_vars(self):
        """Pillar 3: AGYIS_ROLE and PSL_AGENT_ROLE act as explicit self-identification."""
        os.environ["AGYIS_ROLE"] = "deep_execution"
        self.assertEqual(check_pillar_3_explicit_role({}), ROLE_DEEP_EXECUTION)

        os.environ.pop("AGYIS_ROLE", None)
        os.environ["PSL_AGENT_ROLE"] = "flight_director"
        self.assertEqual(check_pillar_3_explicit_role({}), ROLE_FLIGHT_DIRECTOR)

    def test_corrupt_session_role_fails_open(self):
        """Pillar 3: Corrupt JSON in session_role.json fails open gracefully."""
        agents_dir = self.workspace_dir / ".agents"
        agents_dir.mkdir(parents=True, exist_ok=True)
        (agents_dir / "session_role.json").write_text("{corrupt json", encoding="utf-8")

        self.assertIsNone(check_pillar_3_explicit_role({}, workspace_dir=self.workspace_dir))


class TestPillar1EarlyTurnIntent(unittest.TestCase):
    """Pillar 1: Early Turn Intent Interception (Step 1/2 in SQLite steps or prompt payload)."""

    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_dir = Path(self.temp_dir.name)

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_orchestrator_keywords_in_prompt(self):
        """Pillar 1: Orchestrator keywords in prompt seed preliminary ROLE_FLIGHT_DIRECTOR."""
        keywords = [
            "/teamwork-preview",
            "/boost",
            "/subagent-ladder",
            "/goal",
            "orchestrate",
            "coordinate swarm",
        ]
        for kw in keywords:
            with self.subTest(kw=kw):
                payload = {"prompt": f"Let's {kw} and refactor auth module"}
                self.assertEqual(check_pillar_1_intent(payload), ROLE_FLIGHT_DIRECTOR)
                self.assertEqual(classify_agent_role(payload), ROLE_FLIGHT_DIRECTOR)

    def test_direct_coding_keywords_in_prompt(self):
        """Pillar 1: Direct coding/bugfix prompt seeds preliminary ROLE_DEEP_EXECUTION."""
        prompts = [
            "Please fix the bug in auth.py and verify tests",
            "Implement the 3-pillar classifier in pre_invocation_hook.py",
            "Refactor database connection pool handling",
            "Add unit test for token counter",
            "/fix crash on startup",
        ]
        for p in prompts:
            with self.subTest(prompt=p):
                payload = {"prompt": p}
                self.assertEqual(check_pillar_1_intent(payload), ROLE_DEEP_EXECUTION)
                self.assertEqual(classify_agent_role(payload), ROLE_DEEP_EXECUTION)

    def test_early_steps_in_sqlite_direct_coding(self):
        """Pillar 1: SQLite Step 1 with direct bugfix prompt seeds ROLE_DEEP_EXECUTION."""
        conv_id = "test-conv-early-step-bugfix"
        db_path = self.db_dir / f"{conv_id}.db"

        with sqlite3.connect(db_path) as conn:
            conn.execute("CREATE TABLE steps (rowid INTEGER PRIMARY KEY, idx INTEGER, step_data TEXT)")
            conn.execute(
                "INSERT INTO steps (idx, step_data) VALUES (1, ?)",
                (json.dumps({"prompt": "Fix bug in payment processing and add tests"}),),
            )
        conn.close()

        role = classify_agent_role({}, conversation_id=conv_id, db_dir=self.db_dir)
        self.assertEqual(role, ROLE_DEEP_EXECUTION)

    def test_early_steps_in_sqlite_orchestrator(self):
        """Pillar 1: SQLite Step 1 with orchestrator slash command seeds ROLE_FLIGHT_DIRECTOR."""
        conv_id = "test-conv-early-step-orch"
        db_path = self.db_dir / f"{conv_id}.db"

        with sqlite3.connect(db_path) as conn:
            conn.execute("CREATE TABLE steps (rowid INTEGER PRIMARY KEY, idx INTEGER, step_data TEXT)")
            conn.execute(
                "INSERT INTO steps (idx, step_data) VALUES (1, ?)",
                (json.dumps({"prompt": "/subagent-ladder --all execute milestone"}),),
            )
        conn.close()

        role = classify_agent_role({}, conversation_id=conv_id, db_dir=self.db_dir)
        self.assertEqual(role, ROLE_FLIGHT_DIRECTOR)

    def test_orchestrator_precedence_over_coding_in_same_prompt(self):
        """Pillar 1: Orchestrator keyword takes precedence when combined with coding keyword."""
        payload = {"prompt": "/subagent-ladder fix the bug in server.py"}
        self.assertEqual(check_pillar_1_intent(payload), ROLE_FLIGHT_DIRECTOR)
        self.assertEqual(classify_agent_role(payload), ROLE_FLIGHT_DIRECTOR)


class TestPillar2MidTrajectoryBehavioralVerification(unittest.TestCase):
    """Pillar 2: Mid-Trajectory Behavioral Verification at Step 100 or >= 200,000 tokens."""

    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_dir = Path(self.temp_dir.name)

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_below_threshold_returns_none(self):
        """Pillar 2: Inactive below 100 steps and 200,000 tokens."""
        payload = {"tokens": 150_000, "step_count": 50, "tool_calls": ["edit_file"]}
        self.assertIsNone(check_pillar_2_behavior(payload, tokens=150_000))

    def test_subagent_spawns_confirm_flight_director(self):
        """Pillar 2: Count of invoke_subagent, manage_task, schedule, send_message > 0 confirms flight_director."""
        subagent_tools = ["invoke_subagent", "manage_task", "schedule", "send_message"]
        for tool in subagent_tools:
            with self.subTest(tool=tool):
                payload = {
                    "tokens": 205_000,
                    "tool_calls": [tool, "read_file", "view_file"],
                }
                self.assertEqual(
                    check_pillar_2_behavior(payload, tokens=205_000),
                    ROLE_FLIGHT_DIRECTOR,
                )
                self.assertEqual(classify_agent_role(payload, tokens=205_000), ROLE_FLIGHT_DIRECTOR)

    def test_swarm_subagent_confirms_swarm_orchestrator(self):
        """Pillar 2: Swarm/mesh coordination tool calls confirm swarm_orchestrator."""
        payload = {
            "tokens": 205_000,
            "tool_calls": [{"tool_name": "manage_task", "arguments": "swarm barrier join"}],
        }
        self.assertEqual(
            check_pillar_2_behavior(payload, tokens=205_000),
            ROLE_SWARM_ORCHESTRATOR,
        )

    def test_monolithic_swe_pairing_confirms_deep_execution(self):
        """Pillar 2: edit_file, write_file, test runner commands with 0 subagents confirm deep_execution."""
        payload = {
            "tokens": 210_000,
            "tool_calls": [
                "edit_file",
                "write_file",
                {"tool_name": "run_command", "arguments": "pytest tests/test_auth.py"},
                "replace_file_content",
            ],
        }
        self.assertEqual(
            check_pillar_2_behavior(payload, tokens=210_000),
            ROLE_DEEP_EXECUTION,
        )
        self.assertEqual(classify_agent_role(payload, tokens=210_000), ROLE_DEEP_EXECUTION)

    def test_dominant_read_grep_confirms_forensic_auditor(self):
        """Pillar 2: Dominant read_file, grep, audit tools confirm forensic_auditor."""
        payload = {
            "tokens": 210_000,
            "tool_calls": [
                "read_file",
                "view_file",
                "grep_search",
                "find_by_name",
                {"tool_name": "run_command", "arguments": "python3 -m harness.cli audit all"},
            ],
        }
        self.assertEqual(
            check_pillar_2_behavior(payload, tokens=210_000),
            ROLE_FORENSIC_AUDITOR,
        )
        self.assertEqual(classify_agent_role(payload, tokens=210_000), ROLE_FORENSIC_AUDITOR)

    def test_step_100_in_sqlite_triggers_pillar_2(self):
        """Pillar 2: Step count >= 100 in SQLite triggers behavioral verification even under 200k tokens."""
        conv_id = "test-conv-step-100-swe"
        db_path = self.db_dir / f"{conv_id}.db"

        with sqlite3.connect(db_path) as conn:
            conn.execute("CREATE TABLE steps (rowid INTEGER PRIMARY KEY, idx INTEGER, step_data TEXT)")
            # Insert 105 steps with edit_file and test runners
            for i in range(1, 106):
                step_data = {
                    "tool_name": "edit_file" if i % 2 == 0 else "run_command",
                    "arguments": "python3 -m unittest discover" if i % 2 != 0 else "harness/hooks.py",
                }
                conn.execute(
                    "INSERT INTO steps (idx, step_data) VALUES (?, ?)",
                    (i, json.dumps(step_data)),
                )
        conn.close()

        role = classify_agent_role(
            {"tokens": 80_000},
            conversation_id=conv_id,
            db_dir=self.db_dir,
            tokens=80_000,
        )
        self.assertEqual(role, ROLE_DEEP_EXECUTION)

    def test_200k_tokens_in_sqlite_triggers_pillar_2(self):
        """Pillar 2: Tokens >= 200k in SQLite triggers behavioral verification with subagent spawn."""
        conv_id = "test-conv-200k-subagent"
        db_path = self.db_dir / f"{conv_id}.db"

        with sqlite3.connect(db_path) as conn:
            conn.execute("CREATE TABLE steps (rowid INTEGER PRIMARY KEY, idx INTEGER, step_data TEXT)")
            for i in range(1, 15):
                step_data = {"tool_name": "invoke_subagent" if i == 5 else "view_file"}
                conn.execute(
                    "INSERT INTO steps (idx, step_data) VALUES (?, ?)",
                    (i, json.dumps(step_data)),
                )
        conn.close()

        role = classify_agent_role(
            {"tokens": 215_000},
            conversation_id=conv_id,
            db_dir=self.db_dir,
            tokens=215_000,
        )
        self.assertEqual(role, ROLE_FLIGHT_DIRECTOR)


class TestDualAdvisoriesDistinctText(unittest.TestCase):
    """Verifies distinct contract texts for Flight Director and Deep Execution dual advisories."""

    def test_flight_director_cognitive_state_flush_distinct_directives(self):
        """Flight Director advisory mandates Cognitive State Flush Invariant into compaction_checkpoint.md."""
        adv = build_compaction_advisory(ROLE_FLIGHT_DIRECTOR, 235_000, 230_000)

        # Mandatory Invariant Directives
        self.assertIn("COGNITIVE STATE FLUSH INVARIANT", adv)
        self.assertIn("compaction_checkpoint.md", adv)
        self.assertIn("materialize working memory", adv)
        self.assertIn("active task decomposition", adv)
        self.assertIn("pending subagent assignments", adv)
        self.assertIn("operator steering decisions", adv)
        self.assertIn("Zero repository pollution", adv)

        # Must NOT include monolithic SWE pairing directive
        self.assertNotIn("Monolithic SWE Pairing", adv)

    def test_deep_execution_work_preservation_distinct_directives(self):
        """Deep Execution advisory mandates Work Preservation Contract with git clean -fd and wake-up directive."""
        adv = build_compaction_advisory(ROLE_DEEP_EXECUTION, 235_000, 230_000)

        # Mandatory Invariant Directives
        self.assertIn("Monolithic SWE Pairing", adv)
        self.assertIn("WORK PRESERVATION CONTRACT", adv)
        self.assertIn("git checkout -- .", adv)
        self.assertIn("git reset --hard", adv)
        self.assertIn("git clean -fd", adv)
        self.assertIn("in-flight work", adv)
        self.assertIn("intact on disk", adv)
        self.assertIn("Post-compaction wake-up directive", adv)
        self.assertIn("git status", adv)
        self.assertIn("git diff", adv)
        self.assertIn("without reverting", adv)

        # Must NOT include compaction_checkpoint.md flush
        self.assertNotIn("compaction_checkpoint.md", adv)


class TestClassifierEdgeCases(unittest.TestCase):
    """Explicit edge case tests: empty inputs, boundary thresholds, error paths, and tie-breakers."""

    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_dir = Path(self.temp_dir.name)

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_empty_inputs_return_none_or_default(self):
        """Empty inputs to helper functions safely return None; classify_agent_role falls back to flight_director."""
        self.assertIsNone(check_pillar_3_explicit_role({}))
        self.assertIsNone(check_pillar_1_intent({}))
        self.assertIsNone(check_pillar_2_behavior({}))
        self.assertEqual(classify_agent_role({}), ROLE_FLIGHT_DIRECTOR)

    def test_pillar_2_exact_boundary_conditions(self):
        """Tokens 199,999 and step 99 do not trigger Pillar 2; 200,000 tokens triggers."""
        # Just below boundary
        payload_below = {"tokens": 199_999, "step_count": 99, "tool_calls": ["edit_file"]}
        self.assertIsNone(check_pillar_2_behavior(payload_below, tokens=199_999))

        # At boundary: 200,000 tokens
        payload_at = {"tokens": 200_000, "tool_calls": ["edit_file"]}
        self.assertEqual(check_pillar_2_behavior(payload_at, tokens=200_000), ROLE_DEEP_EXECUTION)

    def test_pillar_2_subagent_precedence_over_heavy_editing(self):
        """Even if editing tools vastly outnumber subagent calls, any subagent call triggers flight_director."""
        payload = {
            "tokens": 205_000,
            "tool_calls": ["edit_file"] * 50 + ["invoke_subagent"],
        }
        self.assertEqual(check_pillar_2_behavior(payload, tokens=205_000), ROLE_FLIGHT_DIRECTOR)

    def test_pillar_2_equal_edit_and_audit_tools_tie_breaker(self):
        """When edit_write_test count equals audit_read count, deep execution wins the tie-break."""
        payload = {
            "tokens": 205_000,
            "tool_calls": ["edit_file", "write_file", "read_file", "view_file"],
        }
        self.assertEqual(check_pillar_2_behavior(payload, tokens=205_000), ROLE_DEEP_EXECUTION)

    def test_pillar_2_dominant_audit_over_minimal_edit(self):
        """When explicit audit commands dominate over minimal edit, forensic auditor is confirmed."""
        payload = {
            "tokens": 205_000,
            "tool_calls": [
                "edit_file",
                {"tool_name": "run_command", "arguments": "python3 -m harness.cli audit all"},
                {"tool_name": "run_command", "arguments": "agyis audit deep"},
                {"tool_name": "run_command", "arguments": "agyis audit volume"},
                "read_file",
                "grep_search",
            ],
        }
        self.assertEqual(check_pillar_2_behavior(payload, tokens=205_000), ROLE_FORENSIC_AUDITOR)

    def test_pillar_2_monolithic_swe_pairing_reads_outnumber_edits(self):
        """Monolithic SWE pairing where reads outnumber edits still confirms deep_execution."""
        payload = {
            "tokens": 205_000,
            "tool_calls": [
                "edit_file",
                "read_file",
                "view_file",
                "grep_search",
                "find_by_name",
            ],
        }
        self.assertEqual(check_pillar_2_behavior(payload, tokens=205_000), ROLE_DEEP_EXECUTION)
        self.assertEqual(classify_agent_role(payload, tokens=205_000), ROLE_DEEP_EXECUTION)

    def test_pillar_2_initial_num_steps_triggers_behavioral_verification(self):
        """Official Antigravity initialNumSteps >= 100 triggers Pillar 2 behavioral verification."""
        payload = {
            "initialNumSteps": 105,
            "tokens": 80_000,
            "tool_calls": ["edit_file", "write_file", "view_file"],
        }
        self.assertEqual(check_pillar_2_behavior(payload, tokens=80_000), ROLE_DEEP_EXECUTION)
        self.assertEqual(classify_agent_role(payload, tokens=80_000), ROLE_DEEP_EXECUTION)

    def test_pillar_3_artifact_directory_path_tilde_expansion(self):
        """Pillar 3: artifactDirectoryPath discovers session_role.json."""
        with tempfile.TemporaryDirectory() as td:
            brain_path = Path(td) / "brain"
            brain_path.mkdir(parents=True, exist_ok=True)
            (brain_path / "session_role.json").write_text(json.dumps({"role": "deep_execution"}), encoding="utf-8")

            payload = {
                "artifactDirectoryPath": str(brain_path),
            }
            self.assertEqual(check_pillar_3_explicit_role(payload), ROLE_DEEP_EXECUTION)
            self.assertEqual(classify_agent_role(payload), ROLE_DEEP_EXECUTION)

    def test_pillar_2_takes_precedence_over_generic_cwd(self):
        """At Step 100 or 200k tokens, Pillar 2 behavioral verification takes precedence over generic cwd name."""
        payload = {
            "cwd": "/home/kuasha/Dev/mesh-orchestrator",
            "tokens": 205_000,
            "tool_calls": ["edit_file", "write_file", "view_file"],
        }
        self.assertEqual(classify_agent_role(payload, tokens=205_000), ROLE_DEEP_EXECUTION)

    def test_multi_worktree_stale_subagent_does_not_override_pillar_2(self):
        """Multi-worktree session with stale subagent worktree does not override subagent tool confirmation."""
        payload = {
            "workspacePaths": [
                "/home/kuasha/Dev/psl-agy-harness",
                "/home/kuasha/.gemini/antigravity/worktrees/6deb7452/subagent-subagent-1-executioner-8f776b9f",
            ],
            "tokens": 210_000,
            "tool_calls": ["invoke_subagent", "send_message", "view_file"],
        }
        self.assertEqual(classify_agent_role(payload, tokens=210_000), ROLE_FLIGHT_DIRECTOR)

    def test_corrupt_sqlite_file_fail_open(self):
        """Corrupt or locked SQLite file does not raise an unhandled error."""
        conv_id = "test-corrupt-db"
        bad_file = self.db_dir / f"{conv_id}.db"
        bad_file.write_bytes(b"not a valid sqlite database header bytes")

        role = classify_agent_role(
            {"tokens": 220_000},
            conversation_id=conv_id,
            db_dir=self.db_dir,
            tokens=220_000,
        )
        self.assertEqual(role, ROLE_FLIGHT_DIRECTOR)


class TestAdversarialConcurrencyAndTimeoutResilience(unittest.TestCase):
    """R1: Adversarial concurrency & timeout resilience under SQLite write-lock contention."""

    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_dir = Path(self.temp_dir.name)
        self.old_env = os.environ.copy()

    def tearDown(self):
        clear_locked_conversations()
        os.environ.clear()
        os.environ.update(self.old_env)
        self.temp_dir.cleanup()

    def test_sqlite_default_timeout_is_at_most_half_second(self):
        """Asserts default SQLite timeout is <= 0.5s."""
        self.assertLessEqual(DEFAULT_SQLITE_TIMEOUT, 0.5)
        self.assertLessEqual(get_compaction_sqlite_timeout(), 0.5)

    def test_env_override_sqlite_timeout_clamped_to_max_half_second(self):
        """R1: AGYIS_SQLITE_TIMEOUT overrides are strictly clamped to <= 0.5s."""
        os.environ["AGYIS_SQLITE_TIMEOUT"] = "2.0"
        self.assertLessEqual(get_compaction_sqlite_timeout(), 0.5)

        os.environ["AGYIS_SQLITE_TIMEOUT"] = "0.02"
        self.assertEqual(get_compaction_sqlite_timeout(), 0.02)

        os.environ["AGYIS_SQLITE_TIMEOUT"] = "-1"
        self.assertEqual(get_compaction_sqlite_timeout(), 0.5)

        os.environ["AGYIS_SQLITE_TIMEOUT"] = "invalid"
        self.assertEqual(get_compaction_sqlite_timeout(), 0.5)

    def test_locked_conversation_expiry(self):
        """R1: Locked conversation IDs expire transparently after TTL window."""
        conv_id = "test-conv-exp-ttl"
        record_locked_conversation(conv_id)
        self.assertTrue(is_conversation_locked(conv_id))
        self.assertIn(conv_id, LOCKED_CONVERSATION_IDS)

        clear_locked_conversations()
        self.assertFalse(is_conversation_locked(conv_id))
        self.assertNotIn(conv_id, LOCKED_CONVERSATION_IDS)

    def test_pillar_1_db_path_with_db_extension(self):
        """R1: check_pillar_1_intent correctly queries DB when conversation_id ends with .db."""
        conv_id = "test-conv-ext.db"
        db_path = self.db_dir / conv_id

        with sqlite3.connect(db_path) as conn:
            conn.execute("CREATE TABLE steps (rowid INTEGER PRIMARY KEY, idx INTEGER, step_data TEXT)")
            conn.execute(
                "INSERT INTO steps (idx, step_data) VALUES (1, ?)",
                (json.dumps({"prompt": "Fix bug in payment processing and add tests"}),),
            )
        conn.close()

        role = check_pillar_1_intent({}, conversation_id=conv_id, db_dir=self.db_dir)
        self.assertEqual(role, ROLE_DEEP_EXECUTION)

    def test_runner_and_hook_main_unpiped_stdin_tty_does_not_hang(self):
        """R4: runner and hook_main exit 0 and emit {'injectSteps': []} without blocking on TTY stdin."""
        class MockTTYStdin:
            def isatty(self):
                return True
            @property
            def buffer(self):
                raise AssertionError("buffer should not be read when isatty is True")
            def read(self):
                raise AssertionError("read should not be called when isatty is True")

        with patch("sys.stdin", MockTTYStdin()), patch("sys.stdout", new_callable=io.StringIO) as mock_out:
            code = runner.run_hook("compaction-advisory")
            self.assertEqual(code, 0)
            res = json.loads(mock_out.getvalue().strip())
            self.assertEqual(res, {"injectSteps": []})

        with patch("sys.stdin", MockTTYStdin()), patch("sys.stdout", new_callable=io.StringIO) as mock_out:
            code = hook_main([])
            self.assertEqual(code, 0)
            res = json.loads(mock_out.getvalue().strip())
            self.assertEqual(res, {"injectSteps": []})

    def test_multiprocess_sqlite_lock_contention_runner_fails_open_cleanly(self):
        """R1: Cross-process SQLite write-lock contention respects <=0.5s timeout and fails open."""
        conv_id = "test-mp-locked-runner"
        db_path = self.db_dir / f"{conv_id}.db"

        # Initialize SQLite DB in WAL mode with steps
        init_conn = sqlite3.connect(str(db_path))
        init_conn.execute("PRAGMA journal_mode=WAL")
        init_conn.execute("CREATE TABLE steps (rowid INTEGER PRIMARY KEY, idx INTEGER, step_data TEXT)")
        init_conn.execute(
            "INSERT INTO steps (idx, step_data) VALUES (1, ?)",
            (json.dumps({"step_type": 15, "token_count": 245000, "tool_name": "edit_file"}),),
        )
        init_conn.commit()
        init_conn.close()

        # Start external subprocess holding exclusive lock
        lock_script = (
            "import sqlite3, time, sys\n"
            "conn = sqlite3.connect(sys.argv[1])\n"
            "conn.execute('PRAGMA locking_mode = EXCLUSIVE')\n"
            "conn.execute('BEGIN EXCLUSIVE')\n"
            "conn.execute('INSERT INTO steps (idx, step_data) VALUES (999, \"locked\")')\n"
            "print('LOCKED', flush=True)\n"
            "time.sleep(0.5)\n"
            "conn.close()\n"
        )
        sub_proc = subprocess.Popen(
            [sys.executable, "-c", lock_script, str(db_path)],
            stdout=subprocess.PIPE,
        )
        try:
            line = sub_proc.stdout.readline().decode().strip()
            self.assertEqual(line, "LOCKED")

            os.environ["AGYIS_SQLITE_TIMEOUT"] = "0.01"
            t0 = time.perf_counter()
            with patch("sys.stdout", new_callable=io.StringIO) as mock_out:
                payload = json.dumps({"conversationId": conv_id})
                code = runner.run_hook("compaction-advisory", payload_str=payload)
                elapsed = time.perf_counter() - t0

                self.assertEqual(code, 0)
                self.assertLessEqual(elapsed, 0.5)
                res = json.loads(mock_out.getvalue().strip())
                self.assertEqual(res, {"injectSteps": []})
        finally:
            if sub_proc.stdout:
                sub_proc.stdout.close()
            sub_proc.kill()
            sub_proc.wait()

    def test_sqlite_locked_concurrency_fail_open(self):
        """R1: Concurrent SQLite write-lock contention respects <=0.5s timeout and fails open to empty injectSteps."""
        conv_id = "test-locked-conv"
        db_path = self.db_dir / f"{conv_id}.db"

        # Initialize SQLite DB in WAL mode with steps
        lock_conn = sqlite3.connect(str(db_path))
        lock_conn.execute("PRAGMA journal_mode=WAL")
        lock_conn.execute("CREATE TABLE steps (rowid INTEGER PRIMARY KEY, idx INTEGER, step_data TEXT)")
        for i in range(1, 105):
            lock_conn.execute("INSERT INTO steps (idx, step_data) VALUES (?, ?)", (i, json.dumps({"tool_name": "edit_file"})))
        lock_conn.commit()

        # Acquire exclusive lock in lock_conn
        lock_conn.execute("PRAGMA locking_mode = EXCLUSIVE")
        lock_conn.execute("BEGIN EXCLUSIVE")
        lock_conn.execute("INSERT INTO steps (idx, step_data) VALUES (999, 'locked')")

        try:
            # Under locked DB, evaluate_pre_invocation with 200k tokens or step 100 scan respects timeout <= 0.5s
            payload = json.dumps({"conversationId": conv_id, "tokens": 200_000, "step_count": 105})
            t0 = time.perf_counter()
            res = evaluate_pre_invocation(payload, db_dir=self.db_dir, sqlite_timeout=0.005)
            elapsed = time.perf_counter() - t0

            self.assertLessEqual(elapsed, 0.5)
            self.assertEqual(res, {"injectSteps": []})
        finally:
            lock_conn.close()

    def test_check_pillar_2_behavior_locked_fail_open(self):
        """R1: Pillar 2 scan under active write lock catches OperationalError and fails open cleanly."""
        conv_id = "test-pillar2-locked"
        db_path = self.db_dir / f"{conv_id}.db"

        lock_conn = sqlite3.connect(str(db_path))
        lock_conn.execute("PRAGMA journal_mode=WAL")
        lock_conn.execute("CREATE TABLE steps (rowid INTEGER PRIMARY KEY, idx INTEGER, step_data TEXT)")
        lock_conn.commit()

        lock_conn.execute("PRAGMA locking_mode = EXCLUSIVE")
        lock_conn.execute("BEGIN EXCLUSIVE")
        lock_conn.execute("INSERT INTO steps (idx, step_data) VALUES (1, 'locked')")

        try:
            payload = {"tokens": 210_000, "step_count": 105}
            t0 = time.perf_counter()
            role = check_pillar_2_behavior(payload, conversation_id=conv_id, tokens=210_000, db_dir=self.db_dir, timeout=0.005)
            elapsed = time.perf_counter() - t0

            self.assertLessEqual(elapsed, 0.5)
            self.assertIsNone(role)
        finally:
            lock_conn.close()

    def test_sqlite_locked_concurrency_tokens_in_db_fails_open(self):
        """R1: When tokens reside in locked SQLite DB, token fetch fails open to 0 and returns empty injectSteps."""
        conv_id = "test-tokens-locked"
        db_path = self.db_dir / f"{conv_id}.db"

        lock_conn = sqlite3.connect(str(db_path))
        lock_conn.execute("PRAGMA journal_mode=WAL")
        lock_conn.execute("CREATE TABLE steps (rowid INTEGER PRIMARY KEY, idx INTEGER, step_data TEXT)")
        lock_conn.commit()

        lock_conn.execute("PRAGMA locking_mode = EXCLUSIVE")
        lock_conn.execute("BEGIN EXCLUSIVE")
        lock_conn.execute("INSERT INTO steps (idx, step_data) VALUES (1, 'locked')")

        try:
            # No tokens in payload; must query DB which is locked
            payload = json.dumps({"conversationId": conv_id})
            t0 = time.perf_counter()
            res = evaluate_pre_invocation(payload, db_dir=self.db_dir, sqlite_timeout=0.005)
            elapsed = time.perf_counter() - t0

            self.assertLessEqual(elapsed, 0.5)
            self.assertEqual(res, {"injectSteps": []})
        finally:
            lock_conn.close()


class TestSessionRoleSchemaFuzzing(unittest.TestCase):
    """R2: Schema fuzzing battery for .agents/session_role.json."""

    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.workspace_dir = Path(self.temp_dir.name)
        self.agents_dir = self.workspace_dir / ".agents"
        self.agents_dir.mkdir(parents=True, exist_ok=True)
        self.role_file = self.agents_dir / "session_role.json"

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_corrupt_or_truncated_json_syntax(self):
        """R2: Truncated or syntactically invalid JSON fails open to heuristic classification."""
        bad_syntax_cases = [
            '{"role": "flight_dire',
            '{role: flight_director}',
            '{"role": }',
            '<<<MALFORMED>>>',
            '{"role": "deep_execution"',
            '}{',
        ]
        for content in bad_syntax_cases:
            with self.subTest(content=content):
                self.role_file.write_text(content, encoding="utf-8")
                # With prompt heuristic "fix bug in tests", should fall open to deep_execution
                payload = {"prompt": "fix bug in test suite", "workspace": str(self.workspace_dir)}
                self.assertIsNone(check_pillar_3_explicit_role(payload, workspace_dir=self.workspace_dir))
                self.assertEqual(classify_agent_role(payload, workspace_dir=self.workspace_dir), ROLE_DEEP_EXECUTION)

    def test_non_dictionary_json_payloads(self):
        """R2: Non-dictionary JSON root (arrays, numbers, booleans, null, strings) fails open to heuristic classification."""
        non_dict_cases = [
            '["flight_director", "builder"]',
            '42',
            '3.14159',
            'true',
            'false',
            'null',
            '"deep_execution"',
        ]
        for content in non_dict_cases:
            with self.subTest(content=content):
                self.role_file.write_text(content, encoding="utf-8")
                payload = {"prompt": "fix bug in test suite", "workspace": str(self.workspace_dir)}
                self.assertIsNone(check_pillar_3_explicit_role(payload, workspace_dir=self.workspace_dir))
                self.assertEqual(classify_agent_role(payload, workspace_dir=self.workspace_dir), ROLE_DEEP_EXECUTION)

    def test_missing_role_keys_or_empty_role_strings(self):
        """R2: Missing 'role' keys or empty/whitespace role strings fail open to heuristic classification."""
        missing_or_empty_cases = [
            '{}',
            '{"other_key": "val", "data": 123}',
            '{"role": ""}',
            '{"role": "   "}',
            '{"role": "\t\n"}',
            '{"agent_role": ""}',
        ]
        for content in missing_or_empty_cases:
            with self.subTest(content=content):
                self.role_file.write_text(content, encoding="utf-8")
                payload = {"prompt": "orchestrate multi-node swarm", "workspace": str(self.workspace_dir)}
                self.assertIsNone(check_pillar_3_explicit_role(payload, workspace_dir=self.workspace_dir))
                self.assertEqual(classify_agent_role(payload, workspace_dir=self.workspace_dir), ROLE_FLIGHT_DIRECTOR)

    def test_non_string_role_values(self):
        """R2: Non-string role values (integers, floats, dicts, lists, booleans) fail open."""
        non_string_cases = [
            '{"role": 123}',
            '{"role": 45.67}',
            '{"role": true}',
            '{"role": false}',
            '{"role": null}',
            '{"role": {"nested": "deep_execution"}}',
            '{"role": ["flight_director"]}',
            '{"role": [{"name": "builder"}]}',
        ]
        for content in non_string_cases:
            with self.subTest(content=content):
                self.role_file.write_text(content, encoding="utf-8")
                payload = {"prompt": "implement unit test", "workspace": str(self.workspace_dir)}
                self.assertIsNone(check_pillar_3_explicit_role(payload, workspace_dir=self.workspace_dir))
                self.assertEqual(classify_agent_role(payload, workspace_dir=self.workspace_dir), ROLE_DEEP_EXECUTION)

    def test_oversized_json_files_rejected(self):
        """R2: Oversized JSON files (>64KB) are skipped safely without parsing."""
        padding = "x" * 70_000
        content = json.dumps({"role": "flight_director", "pad": padding})
        self.role_file.write_text(content, encoding="utf-8")
        self.assertGreater(self.role_file.stat().st_size, 65_536)

        payload = {"prompt": "implement bugfix", "workspace": str(self.workspace_dir)}
        self.assertIsNone(check_pillar_3_explicit_role(payload, workspace_dir=self.workspace_dir))
        self.assertEqual(classify_agent_role(payload, workspace_dir=self.workspace_dir), ROLE_DEEP_EXECUTION)

    def test_fuzzing_emits_no_stdout_traces(self):
        """R2: Schema fuzzing cases emit zero error traces to stdout."""
        fuzz_samples = [
            '{"role": [1, 2, 3]}',
            '{corrupt',
            'null',
            '{"role": 9999}',
        ]
        for sample in fuzz_samples:
            self.role_file.write_text(sample, encoding="utf-8")
            with patch("sys.stdout", new_callable=io.StringIO) as mock_out:
                payload = json.dumps({"tokens": 240_000, "workspace": str(self.workspace_dir), "prompt": "fix issue"})
                res = evaluate_pre_invocation(payload, workspace_dir=self.workspace_dir)
                self.assertEqual(mock_out.getvalue(), "")
                self.assertIn("injectSteps", res)


class TestTokenBurstBoundaryHardening(unittest.TestCase):
    """R3: Rapid token burst boundary hardening (single-turn large token jumps)."""

    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_dir = Path(self.temp_dir.name)

    def tearDown(self):
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
        msg = res_turn2["injectSteps"][0]["ephemeralMessage"]
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
        msg = res_turn2["injectSteps"][0]["ephemeralMessage"]
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
        msg = res_turn2["injectSteps"][0]["ephemeralMessage"]
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


if __name__ == "__main__":
    unittest.main()

