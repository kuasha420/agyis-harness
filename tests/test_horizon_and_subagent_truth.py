# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Arafat Zahan (@kuasha420)
# Corporate Stewardship & Infrastructure: Purrfect Software Limited (PSL)
# Governed by: ICARO-42/b Ordinance (Company-Supported Personal IP Framework)

"""
Hermetic test suite for Track 2:
- Model-window-scaled soft checkpoint step horizon (256k->80, 512k->160, 1M->320)
- Anti-spam CID-scoped cooldowns in PreInvocation and TokenProximityGuard
- Pending advisory coalescing in wire_compat.enqueue_pending_advisory
- Native Antigravity subagent dispatch detection & /tmp host isolation in fence_gates
- Concrete truth_errors surfacing & native delegate liveness in stop gates
"""

from __future__ import annotations

import contextlib
import io
import json
import os
from pathlib import Path
import sqlite3
import tempfile
import time
import unittest
from unittest.mock import patch

from harness.hooks.anti_loop_hook import check_anti_loop
from harness.hooks.fence_gates import (
    _has_dispatched_subagents,
    check_pre_tool_use,
    evaluate_stop,
)
from harness.hooks.pre_invocation_hook import evaluate_pre_invocation
from harness.hooks.token_proximity_guard import (
    format_terminal_gauge,
    run_token_proximity_guard,
)
from harness.hooks.wire_compat import (
    drain_pending_advisories,
    enqueue_pending_advisory,
)
from harness.subagents.routing import build_stage_transition_payload
from harness.subagents.truth import validate_transition_payload_truth
from harness.subagents.verdict import generate_audit_verdict
from harness.trajectory import (
    ROLE_DEEP_EXECUTION,
    SOFT_CHECKPOINT_STEP_ADVISORY,
    classify_context_health,
    extract_payload_context_window,
    get_scaled_step_horizon,
)


def _extract_inject_messages(res: dict) -> list[str]:
    out: list[str] = []
    for item in res.get("injectSteps", []):
        sm = item.get("systemMessage")
        if isinstance(sm, dict):
            out.append(str(sm.get("systemMessage", "")))
        elif isinstance(sm, str):
            out.append(sm)
    return out


class TestScaledStepHorizonAndCooldown(unittest.TestCase):
    """Tests scaled checkpoint step horizon, advisory coalescing, and cooldown state."""

    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.ws = self.root / "ws"
        self.ws.mkdir(parents=True, exist_ok=True)
        self.state_dir = self.root / "state"
        self.state_dir.mkdir(parents=True, exist_ok=True)
        self.env_patch = patch.dict(
            os.environ,
            {"AGYIS_HARNESS_STATE_DIR": str(self.state_dir)},
            clear=False,
        )
        self.env_patch.start()
        for k in ("AGYIS_ROLE", "PSL_AGENT_ROLE"):
            os.environ.pop(k, None)

    def tearDown(self) -> None:
        self.env_patch.stop()
        self.tmp.cleanup()

    def test_get_scaled_step_horizon_and_context_health_bounds(self) -> None:
        self.assertEqual(SOFT_CHECKPOINT_STEP_ADVISORY, 80)
        self.assertEqual(get_scaled_step_horizon(None), 80)
        self.assertEqual(get_scaled_step_horizon(0), 80)
        self.assertEqual(get_scaled_step_horizon(-500), 80)
        self.assertEqual(get_scaled_step_horizon(256_000), 80)
        self.assertEqual(get_scaled_step_horizon(512_000), 160)
        self.assertEqual(get_scaled_step_horizon(1_000_000), 320)
        self.assertEqual(get_scaled_step_horizon(1_048_576), 320)
        self.assertEqual(get_scaled_step_horizon(2_000_000), 320)
        self.assertEqual(get_scaled_step_horizon(128_000), 40)
        self.assertEqual(get_scaled_step_horizon(64_000), 40)
        self.assertEqual(get_scaled_step_horizon(160_000), 50)

        self.assertEqual(classify_context_health(10_000, 90, 512_000), ("HEALTHY", "REUSE"))
        self.assertEqual(classify_context_health(10_000, 160, 512_000), ("AMBER", "COMPACT_SOON"))
        self.assertEqual(classify_context_health(10_000, 200, 1_000_000), ("HEALTHY", "REUSE"))
        self.assertEqual(classify_context_health(10_000, 320, 1_000_000), ("AMBER", "COMPACT_SOON"))

        # Booleans must never be coerced to maxContextTokens=1
        self.assertIsNone(extract_payload_context_window({"maxContextTokens": True}))
        self.assertEqual(
            extract_payload_context_window({"maxContextTokens": True, "model": "gemini-4-neon"}),
            512_000,
        )
        self.assertEqual(
            extract_payload_context_window({"maxContextTokens": False, "model": "gemini-4-neon"}),
            512_000,
        )

    def test_pre_invocation_scaled_horizon_cooldown_and_reset(self) -> None:
        cid = "cid-scaled-512k"
        # At 512k (horizon=160, cadence=40), step 90 must NOT emit horizon advisory
        res_90 = evaluate_pre_invocation(
            {"conversationId": cid, "maxContextTokens": 512_000, "step_count": 90, "role": ROLE_DEEP_EXECUTION},
            workspace_dir=self.ws,
        )
        msgs_90 = _extract_inject_messages(res_90)
        self.assertFalse(any("CHECKPOINT HORIZON ADVISORY" in m for m in msgs_90))
        self.assertTrue(any("ROLE RE-ANCHOR" in m for m in msgs_90))

        # Step 91 is completely silent
        res_91 = evaluate_pre_invocation(
            {"conversationId": cid, "maxContextTokens": 512_000, "step_count": 91, "role": ROLE_DEEP_EXECUTION},
            workspace_dir=self.ws,
        )
        self.assertEqual(res_91, {"injectSteps": []})

        # Step 160 fires scaled 160/160 horizon advisory
        res_160 = evaluate_pre_invocation(
            {"conversationId": cid, "maxContextTokens": 512_000, "step_count": 160, "role": ROLE_DEEP_EXECUTION},
            workspace_dir=self.ws,
        )
        msgs_160 = _extract_inject_messages(res_160)
        self.assertTrue(any("Checkpoint step 160/160" in m for m in msgs_160))

        # Step 170 is inside 40-step cooldown -> horizon suppressed, regular reanchor still emitted
        res_170 = evaluate_pre_invocation(
            {"conversationId": cid, "maxContextTokens": 512_000, "step_count": 170, "role": ROLE_DEEP_EXECUTION},
            workspace_dir=self.ws,
        )
        msgs_170 = _extract_inject_messages(res_170)
        self.assertFalse(any("CHECKPOINT HORIZON ADVISORY" in m for m in msgs_170))
        self.assertTrue(any("ROLE RE-ANCHOR" in m for m in msgs_170))

        # Step 199 (delta 39 < 40) stays silent
        res_199 = evaluate_pre_invocation(
            {"conversationId": cid, "maxContextTokens": 512_000, "step_count": 199, "role": ROLE_DEEP_EXECUTION},
            workspace_dir=self.ws,
        )
        self.assertEqual(res_199, {"injectSteps": []})

        # Step 200 (delta 40 >= 40) fires again
        res_200 = evaluate_pre_invocation(
            {"conversationId": cid, "maxContextTokens": 512_000, "step_count": 200, "role": ROLE_DEEP_EXECUTION},
            workspace_dir=self.ws,
        )
        msgs_200 = _extract_inject_messages(res_200)
        self.assertTrue(any("Checkpoint step 200/160" in m for m in msgs_200))

        # New checkpoint_index resets cooldown immediately (step 162 fires even though < 200)
        res_cp1 = evaluate_pre_invocation(
            {
                "conversationId": cid,
                "maxContextTokens": 512_000,
                "checkpoint_index": 1,
                "step_count": 162,
                "role": ROLE_DEEP_EXECUTION,
            },
            workspace_dir=self.ws,
        )
        msgs_cp1 = _extract_inject_messages(res_cp1)
        self.assertTrue(any("Checkpoint step 162/160" in m for m in msgs_cp1))

    def test_pre_invocation_default_cid_skips_persistent_suppression(self) -> None:
        payload = {"step_count": 80, "role": ROLE_DEEP_EXECUTION}
        msgs_1 = _extract_inject_messages(evaluate_pre_invocation(payload, workspace_dir=self.ws))
        msgs_2 = _extract_inject_messages(evaluate_pre_invocation(payload, workspace_dir=self.ws))
        self.assertTrue(any("Checkpoint step 80/80" in m for m in msgs_1))
        self.assertTrue(any("Checkpoint step 80/80" in m for m in msgs_2))

    def test_wire_compat_coalesces_checkpoint_horizon_advisories(self) -> None:
        cid = "cid-coalesce"
        enqueue_pending_advisory(cid, "Unrelated reminder A", state_dir=self.state_dir)
        enqueue_pending_advisory(
            cid,
            "[AGYIS CHECKPOINT HORIZON ADVISORY: Checkpoint step 160/160]",
            state_dir=self.state_dir,
        )
        enqueue_pending_advisory(
            cid,
            "[CHECKPOINT HORIZON: 160/160 STEPS] First sweep notice",
            state_dir=self.state_dir,
        )
        enqueue_pending_advisory(
            cid,
            "[CHECKPOINT HORIZON: 161/160 STEPS] Second edit notice",
            state_dir=self.state_dir,
        )
        enqueue_pending_advisory(
            cid,
            "[CHECKPOINT HORIZON: 162/160 STEPS] Latest notice",
            state_dir=self.state_dir,
        )

        drained = drain_pending_advisories(cid, state_dir=self.state_dir)
        horizon_entries = [m for m in drained if "[CHECKPOINT HORIZON:" in m]
        self.assertEqual(len(horizon_entries), 1)
        self.assertIn("162/160 STEPS", horizon_entries[0])
        self.assertIn("Unrelated reminder A", drained)
        self.assertIn("[AGYIS CHECKPOINT HORIZON ADVISORY: Checkpoint step 160/160]", drained)

    def test_anti_loop_and_fence_gates_scale_horizon_and_coalesce(self) -> None:
        cid = "cid-hooks-512k"
        payload_90 = {"conversationId": cid, "maxContextTokens": 512_000, "step_count": 90, "role": ROLE_DEEP_EXECUTION}
        err_90 = io.StringIO()
        with contextlib.redirect_stderr(err_90):
            check_anti_loop("list_dir", {"DirectoryPath": str(self.ws)}, conv_id=cid, state_dir=self.state_dir, payload=payload_90)
            check_pre_tool_use("edit_file", {"TargetFile": "app.py"}, conv_id=cid, state_dir=self.state_dir, payload=payload_90)
        self.assertEqual(err_90.getvalue(), "")
        self.assertEqual(drain_pending_advisories(cid, state_dir=self.state_dir), [])

        payload_160 = {"conversationId": cid, "maxContextTokens": 512_000, "step_count": 160, "role": ROLE_DEEP_EXECUTION}
        err_160 = io.StringIO()
        with contextlib.redirect_stderr(err_160):
            check_anti_loop("list_dir", {"DirectoryPath": str(self.ws)}, conv_id=cid, state_dir=self.state_dir, payload=payload_160)
            check_pre_tool_use("edit_file", {"TargetFile": "app.py"}, conv_id=cid, state_dir=self.state_dir, payload=payload_160)
        self.assertIn("[CHECKPOINT HORIZON: 160/160 STEPS]", err_160.getvalue())
        queued = drain_pending_advisories(cid, state_dir=self.state_dir)
        self.assertEqual(len([m for m in queued if "[CHECKPOINT HORIZON:" in m]), 1)

    def test_token_proximity_guard_scaled_labels_and_stderr_cooldown(self) -> None:
        g_512_below = format_terminal_gauge(tokens=10_000, threshold=512_000, step_count=90, role=ROLE_DEEP_EXECUTION)
        self.assertNotIn("[CHECKPOINT HORIZON:", g_512_below)
        g_512_hit = format_terminal_gauge(tokens=10_000, threshold=512_000, step_count=160, role=ROLE_DEEP_EXECUTION)
        self.assertIn("[CHECKPOINT HORIZON: 160/160 STEPS]", g_512_hit)
        g_1m_hit = format_terminal_gauge(tokens=10_000, threshold=1_000_000, step_count=320, role=ROLE_DEEP_EXECUTION)
        self.assertIn("[CHECKPOINT HORIZON: 320/320 STEPS]", g_1m_hit)

        cid = "cid-gauge-cooldown"
        err1 = io.StringIO()
        run_token_proximity_guard(
            {"conversationId": cid, "maxContextTokens": 512_000, "step_count": 160, "role": ROLE_DEEP_EXECUTION},
            stderr=err1,
            state_dir=self.state_dir,
        )
        self.assertIn("[CHECKPOINT HORIZON: 160/160 STEPS]", err1.getvalue())

        # Consecutive call within 40-step cooldown is suppressed
        err2 = io.StringIO()
        run_token_proximity_guard(
            {"conversationId": cid, "maxContextTokens": 512_000, "step_count": 165, "role": ROLE_DEEP_EXECUTION},
            stderr=err2,
            state_dir=self.state_dir,
        )
        self.assertEqual(err2.getvalue(), "")

        # Delta >= 40 emits again
        err3 = io.StringIO()
        run_token_proximity_guard(
            {"conversationId": cid, "maxContextTokens": 512_000, "step_count": 200, "role": ROLE_DEEP_EXECUTION},
            stderr=err3,
            state_dir=self.state_dir,
        )
        self.assertIn("[CHECKPOINT HORIZON: 200/160 STEPS]", err3.getvalue())

        # New checkpoint_index resets cooldown
        err4 = io.StringIO()
        run_token_proximity_guard(
            {
                "conversationId": cid,
                "maxContextTokens": 512_000,
                "checkpoint_index": 1,
                "step_count": 161,
                "role": ROLE_DEEP_EXECUTION,
            },
            stderr=err4,
            state_dir=self.state_dir,
        )
        self.assertIn("[CHECKPOINT HORIZON: 161/160 STEPS]", err4.getvalue())


class TestNativeSubagentStopGateTruth(unittest.TestCase):
    """Tests native Antigravity dispatch detection, /tmp host isolation, and stop-gate truth surfacing."""

    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.ws = self.root / "ws"
        self.ws.mkdir(parents=True, exist_ok=True)
        self.state_dir = self.root / "state"
        self.state_dir.mkdir(parents=True, exist_ok=True)
        self.app_dir = self.root / "app"
        self.brain_dir = self.app_dir / "brain"
        self.brain_dir.mkdir(parents=True, exist_ok=True)

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def _write_valid_transition_payload(self) -> None:
        plan_file = self.ws / "plan.md"
        plan_file.write_text("# Plan\n", encoding="utf-8")
        payload = build_stage_transition_payload(
            task_id="TRACK-2",
            phase="Phase 2",
            stage="BUILD",
            status="PASS",
            plan_path=str(plan_file),
            exit_code=0,
            total_tests=12,
            passed_tests=12,
            failed_tests=0,
        )
        (self.ws / "psl_stage_transition_payload.json").write_text(
            json.dumps(payload), encoding="utf-8"
        )

    def test_tmp_solo_workspace_isolated_from_host_gemini_dir(self) -> None:
        # Even when host ANTIGRAVITY_APP_DATA_DIR points to ~/.gemini/antigravity, /tmp solo workspace must not leak
        fake_host_app = Path.home() / ".gemini" / "antigravity"
        with patch.dict(
            os.environ,
            {"ANTIGRAVITY_APP_DATA_DIR": str(fake_host_app)},
            clear=False,
        ):
            os.environ.pop("ANTIGRAVITY_BRAIN_DIR", None)
            os.environ.pop("GEMINI_BRAIN_DIR", None)
            self.assertFalse(_has_dispatched_subagents(self.ws, None))
            self.assertFalse(_has_dispatched_subagents(self.ws, None, conv_id="solo-tmp-cid"))
            self.assertFalse(_has_dispatched_subagents(self.ws, {"conversationId": "default"}))
            res = evaluate_stop(
                conv_id="solo-tmp-cid",
                state_dir=self.state_dir,
                cwd=self.ws,
                payload={"role": "agyis_coordinator"},
            )
            self.assertEqual(res.get("decision"), "allow")

    def test_detects_native_swarm_plan_json(self) -> None:
        cid = "parent-swarm-01"
        plan_file = self.brain_dir / cid / ".system_generated" / "swarm" / "plan.json"
        plan_file.parent.mkdir(parents=True, exist_ok=True)
        plan_file.write_text(json.dumps({"workers": []}), encoding="utf-8")
        self.assertFalse(_has_dispatched_subagents(self.ws, None, conv_id=cid, brain_dir=self.brain_dir))

        plan_file.write_text(
            json.dumps({"workers": [{"id": "worker-1", "name": "agyis_builder"}]}),
            encoding="utf-8",
        )
        self.assertTrue(_has_dispatched_subagents(self.ws, None, conv_id=cid, brain_dir=self.brain_dir))

    def test_detects_native_transcript_dispatches(self) -> None:
        for idx, tc in enumerate((
            {"name": "invoke_subagent", "args": {"agent": "agyis_builder", "prompt": "build"}},
            {"name": "run_workflow", "args": {"workflow": "build"}},
            {"name": "swarm", "args": {"action": "add", "name": "worker"}},
            {"name": "manage_subagents", "args": {"action": "spawn", "agent": "agyis_reviewer"}},
        )):
            cid = f"parent-tx-{idx}"
            t_path = self.brain_dir / cid / ".system_generated" / "logs" / "transcript.jsonl"
            t_path.parent.mkdir(parents=True, exist_ok=True)
            t_path.write_text(
                json.dumps({"step_index": 0, "type": "PLANNER_RESPONSE", "tool_calls": [tc]}) + "\n",
                encoding="utf-8",
            )
            with self.subTest(tool=tc["name"]):
                self.assertTrue(_has_dispatched_subagents(self.ws, None, conv_id=cid, brain_dir=self.brain_dir))

    def test_detects_native_conversation_summaries_db_children(self) -> None:
        cid = "parent-db-01"
        db_path = self.app_dir / "conversation_summaries.db"
        conn = sqlite3.connect(db_path)
        try:
            conn.execute(
                "CREATE TABLE conversation_summaries "
                "(conversation_id TEXT PRIMARY KEY, parent_conversation_id TEXT, agent_name TEXT)"
            )
            conn.execute(
                "INSERT INTO conversation_summaries VALUES (?, ?, ?)",
                ("child-db-01", cid, "agyis_builder"),
            )
            conn.commit()
        finally:
            conn.close()

        with patch.dict(os.environ, {"ANTIGRAVITY_APP_DATA_DIR": str(self.app_dir)}, clear=False):
            self.assertTrue(_has_dispatched_subagents(self.ws, None, conv_id=cid))
            self.assertFalse(_has_dispatched_subagents(self.ws, None, conv_id="unrelated-cid"))

    def test_orchestrator_stop_surfaces_concrete_dead_native_delegate_error(self) -> None:
        parent_cid = "parent-live-check-01"
        child_cid = "child-dead-worker-01"

        # Parent transcript spawned child_cid via invoke_subagent
        parent_tx = self.brain_dir / parent_cid / ".system_generated" / "logs" / "transcript.jsonl"
        parent_tx.parent.mkdir(parents=True, exist_ok=True)
        parent_tx.write_text(
            json.dumps({
                "step_index": 0,
                "type": "PLANNER_RESPONSE",
                "tool_calls": [{"name": "invoke_subagent", "args": {"agent": "agyis_builder"}}],
            }) + "\n",
            encoding="utf-8",
        )

        # Native child transcript with NO .agents/teamwork/ dir, aged > 1800s -> DEAD
        child_tx = self.brain_dir / child_cid / ".system_generated" / "logs" / "transcript.jsonl"
        child_tx.parent.mkdir(parents=True, exist_ok=True)
        child_tx.write_text(
            json.dumps({
                "step_index": 0,
                "conversation_id": child_cid,
                "parent_conversation_id": parent_cid,
                "role": "agyis_builder",
                "content": "Executing Track 2 implementation",
            }) + "\n",
            encoding="utf-8",
        )
        old_ts = time.time() - 3600
        os.utime(child_tx, (old_ts, old_ts))

        # Write a valid transition payload so the ONLY failure is the DEAD native delegate
        self._write_valid_transition_payload()

        valid, errors = validate_transition_payload_truth(
            self.ws,
            brain_dir=self.brain_dir,
            conv_id=parent_cid,
        )
        self.assertFalse(valid)
        self.assertTrue(any("DEAD state" in e and "agyis_builder" in e for e in errors))

        res = evaluate_stop(
            conv_id=parent_cid,
            state_dir=self.state_dir,
            cwd=self.ws,
            brain_dir=self.brain_dir,
            payload={"role": "agyis_coordinator"},
        )
        self.assertEqual(res.get("decision"), "continue")
        reason = res.get("reason", "")
        self.assertIn("Persona Truth Violation", reason)
        self.assertIn("DEAD state", reason)
        self.assertIn("agyis_builder", reason)

        # Once native child finishes cleanly and auditor verdict exists, orchestrator stop is allowed
        child_tx.write_text(
            json.dumps({
                "step_index": 0,
                "conversation_id": child_cid,
                "parent_conversation_id": parent_cid,
                "role": "agyis_builder",
                "content": "Executing Track 2 implementation",
            }) + "\n" + json.dumps({
                "step_index": 1,
                "type": "PLANNER_RESPONSE",
                "status": "DONE",
                "tool_calls": [{"name": "finish", "args": {}}],
            }) + "\n",
            encoding="utf-8",
        )
        generate_audit_verdict(
            workspace_dir=self.ws,
            task_id="TRACK-2",
            verdict="VICTORY CONFIRMED",
            test_suite_result={
                "exit_code": 0,
                "total_tests": 12,
                "passed_tests": 12,
                "failed_tests": 0,
                "benchmark_latency_s": 0.1,
            },
            aff_result={"status": "PASS", "score": 100.0},
        )

        res_ok = evaluate_stop(
            conv_id=parent_cid,
            state_dir=self.state_dir,
            cwd=self.ws,
            brain_dir=self.brain_dir,
            payload={"role": "agyis_coordinator"},
        )
        self.assertEqual(res_ok.get("decision"), "allow")


if __name__ == "__main__":
    unittest.main()
