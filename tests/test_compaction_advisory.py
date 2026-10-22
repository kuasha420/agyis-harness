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
    ROLE_DEEP_EXECUTION,
    ROLE_FLIGHT_DIRECTOR,
    ROLE_FORENSIC_AUDITOR,
    ROLE_SWARM_ORCHESTRATOR,
    build_compaction_advisory,
    classify_agent_role,
    evaluate_pre_invocation,
    get_compaction_advisory_threshold,
    main as hook_main,
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

        payload = json.dumps({"conversationId": conv_id, "role": "deep_execution"})
        res = evaluate_pre_invocation(payload, db_dir=self.db_dir)
        self.assertEqual(res, {"injectSteps": []})


if __name__ == "__main__":
    unittest.main()
