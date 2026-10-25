# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Arafat Zahan (@kuasha420)
# Corporate Stewardship & Infrastructure: Purrfect Software Limited (PSL)
# Governed by: ICARO-42/b Ordinance (Company-Supported Personal IP Framework)

"""
Hermetic End-to-End Integration Test Suite: Subagent Ladder Lifecycle (Epic #51 Phase 3.3.4).

Validates the full Ladder Stage 1 (Executioner) -> Stage 2 (The Hammer) lifecycle:
1. Stage 1 Materialization:
   - Arm heartbeat cron via arm_stage_heartbeat.
   - Materialize Stage 1 role via materialize_stage_role(1, "agyis_builder", "EPIC-51-3.3").
   - Turn 0 entry injection asserts ROLE_DEEP_EXECUTION persona prompt.
2. Step 40 (Warning Horizon):
   - Heartbeat pulses step_count=40.
   - evaluate_pre_invocation evaluates step 40, asserts Tier 1 warning ephemeralMessage.
3. Step 45 (Compulsory Convergence Horizon):
   - Heartbeat pulses step_count=45.
   - evaluate_pre_invocation evaluates step 45, asserts Tier 2 interrupt ephemeralMessage.
   - anti_loop_hook evaluates tool call, asserts exploratory sweeps (list_dir, find_by_name)
     are denied, while view_file and test commands are allowed.
4. Step 50 (Hard Horizon Fence & Verification Grace):
   - Heartbeat pulses step_count=50.
   - completion_fence_hook evaluates tool call, asserts code mutation tools (write_to_file,
     replace_file_content, edit_file) are denied by hard horizon fence.
   - Local work preservation invariant asserted (disk files unmodified).
   - Verification Grace turn allows run_command test execution (./agyis test, python3 -m unittest ...).
   - Read-only tools and inter-agent communication (send_message, view_file, grep_search) allowed.
5. Stage Transition Handoff:
   - Build and validate typed stage transition payload (protocol_version 2026.1).
   - Simulate Cortex send_message handoff invocation.
6. Coordinator Handshake & Stage 2 Materialization:
   - Coordinator disarms heartbeat via disarm_stage_heartbeat(status="complete").
   - Materializes Stage 2 role via materialize_stage_role(2, "agyis_reviewer", "EPIC-51-3.3").
   - evaluate_pre_invocation evaluates Stage 2 entry, asserts persona reflects ROLE_FORENSIC_AUDITOR.
   - read_stage_heartbeat verifies status="complete".
7. Sub-Second Benchmark SLA:
   - Validates that the full lifecycle runs well under the 0.30s latency SLA (<300ms).
"""

from __future__ import annotations

import json
import os
from pathlib import Path
import tempfile
import time
import unittest

from harness.hooks.anti_loop_hook import (
    check_anti_loop,
    handle_pre_tool_use,
    ROLE_DEEP_EXECUTION as ANTI_LOOP_ROLE_DEEP_EXECUTION,
    ROLE_FORENSIC_AUDITOR as ANTI_LOOP_ROLE_FORENSIC_AUDITOR,
)
from harness.hooks.completion_fence_hook import (
    check_pre_tool_use,
    CODE_MUTATION_TOOLS,
    EXECUTIONER_HORIZON_STEPS,
    ROLE_DEEP_EXECUTION as FENCE_ROLE_DEEP_EXECUTION,
    ROLE_FORENSIC_AUDITOR as FENCE_ROLE_FORENSIC_AUDITOR,
)
from harness.hooks.pre_invocation_hook import (
    evaluate_pre_invocation,
    ROLE_DEEP_EXECUTION,
    ROLE_FORENSIC_AUDITOR,
    STEP_WARNING_THRESHOLD,
    STEP_INTERRUPT_THRESHOLD,
)
from harness.subagents import (
    arm_stage_heartbeat,
    disarm_stage_heartbeat,
    materialize_stage_role,
    pulse_stage_heartbeat,
    read_stage_heartbeat,
    read_stage_role,
    validate_heartbeat_schema,
    validate_stage_role_schema,
)


class TestSubagentLadderIntegration(unittest.TestCase):
    """End-to-End integration test suite for Subagent Ladder Stage 1 -> Stage 2 transitions."""

    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.workspace_dir = Path(self.temp_dir.name)
        self.orig_role = os.environ.get("AGYIS_ROLE")
        self.orig_agent_role = os.environ.get("PSL_AGENT_ROLE")
        self.orig_cadence = os.environ.get("AGYIS_ROLE_PINNING_CADENCE")
        os.environ.pop("AGYIS_ROLE", None)
        os.environ.pop("PSL_AGENT_ROLE", None)
        os.environ.pop("AGYIS_ROLE_PINNING_CADENCE", None)

    def tearDown(self) -> None:
        if self.orig_role is not None:
            os.environ["AGYIS_ROLE"] = self.orig_role
        else:
            os.environ.pop("AGYIS_ROLE", None)

        if self.orig_agent_role is not None:
            os.environ["PSL_AGENT_ROLE"] = self.orig_agent_role
        else:
            os.environ.pop("PSL_AGENT_ROLE", None)

        if self.orig_cadence is not None:
            os.environ["AGYIS_ROLE_PINNING_CADENCE"] = self.orig_cadence
        else:
            os.environ.pop("AGYIS_ROLE_PINNING_CADENCE", None)

        self.temp_dir.cleanup()

    def test_complete_stage_1_to_stage_2_lifecycle(self) -> None:
        """Simulate a complete Ladder Stage 1 (Executioner) -> Stage 2 (The Hammer) lifecycle."""
        task_id = "EPIC-51-3.3"

        # ---------------------------------------------------------------------
        # 1. Stage 1 Setup: Arm Heartbeat & Materialize Stage 1 Role
        # ---------------------------------------------------------------------
        hb_path = arm_stage_heartbeat(
            task_id=task_id,
            stage="executioner",
            agent_id="agyis_builder",
            role_title="Stage 1: Executioner (agyis_builder)",
            workspace_dir=self.workspace_dir,
        )
        self.assertTrue(hb_path.is_file())

        role_path = materialize_stage_role(
            stage=1,
            agent_name="agyis_builder",
            task_id=task_id,
            workspace_dir=self.workspace_dir,
        )
        self.assertTrue(role_path.is_file())

        # Verify initial heartbeat & stage role state
        initial_hb = read_stage_heartbeat(workspace_dir=self.workspace_dir)
        self.assertIsNotNone(initial_hb)
        self.assertTrue(validate_heartbeat_schema(initial_hb))
        self.assertEqual(initial_hb["status"], "dispatched")
        self.assertEqual(initial_hb["stage"], "executioner")
        self.assertEqual(initial_hb["active_agent_id"], "agyis_builder")
        self.assertEqual(initial_hb["step_count"], 0)

        initial_role = read_stage_role(self.workspace_dir)
        self.assertIsNotNone(initial_role)
        self.assertTrue(validate_stage_role_schema(initial_role))
        self.assertEqual(initial_role["role"], "deep_execution")
        self.assertEqual(initial_role["stage"], 1)
        self.assertEqual(initial_role["stage_name"], "EXECUTION")
        self.assertEqual(initial_role["specialist_agent"], "agyis_builder")

        # Turn 0 Pre-Invocation injection asserts ROLE_DEEP_EXECUTION persona
        res_0 = evaluate_pre_invocation({"step_count": 0}, workspace_dir=self.workspace_dir)
        inject_steps_0 = res_0.get("injectSteps", [])
        self.assertEqual(len(inject_steps_0), 1)
        self.assertIn("systemMessage", inject_steps_0[0])
        sys_msg_0 = inject_steps_0[0]["systemMessage"]
        self.assertIn("[AGYIS ROLE PINNING: DEEP EXECUTION / EXECUTIONER]", sys_msg_0)
        self.assertIn("SURGICAL CONTIGUOUS EDITS INVARIANT", sys_msg_0)

        # ---------------------------------------------------------------------
        # 2. Step 40: Warning Ephemeral Message Injection
        # ---------------------------------------------------------------------
        pulse_ok_40 = pulse_stage_heartbeat(
            step_count=STEP_WARNING_THRESHOLD,
            last_action="editing test files",
            status="in_progress",
            workspace_dir=self.workspace_dir,
        )
        self.assertTrue(pulse_ok_40)

        res_40 = evaluate_pre_invocation(
            {"step_count": STEP_WARNING_THRESHOLD}, workspace_dir=self.workspace_dir
        )
        inject_steps_40 = res_40.get("injectSteps", [])
        self.assertEqual(len(inject_steps_40), 1)
        self.assertIn("ephemeralMessage", inject_steps_40[0])
        msg_40 = inject_steps_40[0]["ephemeralMessage"]
        self.assertIn(
            "[AGYIS HORIZON WARNING: THRASHING DETECTED / REMEDY MODE ACTIVE - 10 STEPS REMAINING]",
            msg_40,
        )
        self.assertIn("10 steps remaining in your convergence budget", msg_40)

        # ---------------------------------------------------------------------
        # 3. Step 45: Compulsory Convergence Horizon & Exploratory Sweep Denials
        # ---------------------------------------------------------------------
        pulse_ok_45 = pulse_stage_heartbeat(
            step_count=STEP_INTERRUPT_THRESHOLD,
            last_action="verifying local edits",
            status="in_progress",
            workspace_dir=self.workspace_dir,
        )
        self.assertTrue(pulse_ok_45)

        # Assert Tier 2 interrupt ephemeralMessage
        res_45 = evaluate_pre_invocation(
            {"step_count": STEP_INTERRUPT_THRESHOLD}, workspace_dir=self.workspace_dir
        )
        inject_steps_45 = res_45.get("injectSteps", [])
        self.assertEqual(len(inject_steps_45), 1)
        self.assertIn("ephemeralMessage", inject_steps_45[0])
        msg_45 = inject_steps_45[0]["ephemeralMessage"]
        self.assertIn("[AGYIS HORIZON INTERRUPT: 5 STEPS REMAINING]", msg_45)
        self.assertIn("Compulsory convergence active. You have 5 steps remaining.", msg_45)

        # Assert exploratory sweeps (list_dir, find_by_name) denied in anti_loop_hook
        conv_id = "test-ladder-stage1-lifecycle"
        deny_list_dir = check_anti_loop(
            "list_dir",
            {"DirectoryPath": str(self.workspace_dir)},
            conv_id=conv_id,
            state_dir=self.workspace_dir,
            step_count=STEP_INTERRUPT_THRESHOLD,
            role=ANTI_LOOP_ROLE_DEEP_EXECUTION,
        )
        self.assertEqual(deny_list_dir.get("decision"), "deny")
        self.assertIn("Compulsory convergence active", deny_list_dir.get("reason", ""))

        deny_find_by_name = check_anti_loop(
            "find_by_name",
            {"Pattern": "*.py", "SearchDirectory": str(self.workspace_dir)},
            conv_id=conv_id,
            state_dir=self.workspace_dir,
            step_count=STEP_INTERRUPT_THRESHOLD,
            role=ANTI_LOOP_ROLE_DEEP_EXECUTION,
        )
        self.assertEqual(deny_find_by_name.get("decision"), "deny")
        self.assertIn("Compulsory convergence active", deny_find_by_name.get("reason", ""))

        # Assert handle_pre_tool_use with payload dictionary also blocks sweeps
        payload_sweep = {
            "conversationId": conv_id,
            "toolCall": {"name": "list_dir", "args": {"DirectoryPath": str(self.workspace_dir)}},
            "step_count": STEP_INTERRUPT_THRESHOLD,
            "role": ANTI_LOOP_ROLE_DEEP_EXECUTION,
        }
        self.assertEqual(
            handle_pre_tool_use(payload_sweep, state_dir=self.workspace_dir).get("decision"),
            "deny",
        )

        # Assert view_file and test execution remain allowed at step 45
        allow_view = check_anti_loop(
            "view_file",
            {"AbsolutePath": str(self.workspace_dir / "test.py")},
            conv_id=conv_id,
            state_dir=self.workspace_dir,
            step_count=STEP_INTERRUPT_THRESHOLD,
            role=ANTI_LOOP_ROLE_DEEP_EXECUTION,
        )
        self.assertEqual(allow_view.get("decision"), "allow")

        allow_cmd = check_anti_loop(
            "run_command",
            {"CommandLine": "./agyis test"},
            conv_id=conv_id,
            state_dir=self.workspace_dir,
            step_count=STEP_INTERRUPT_THRESHOLD,
            role=ANTI_LOOP_ROLE_DEEP_EXECUTION,
        )
        self.assertEqual(allow_cmd.get("decision"), "allow")

        # ---------------------------------------------------------------------
        # 4. Step 50: Hard Horizon Fence & Verification Grace Turn
        # ---------------------------------------------------------------------
        pulse_ok_50 = pulse_stage_heartbeat(
            step_count=EXECUTIONER_HORIZON_STEPS,
            last_action="running verification grace tests",
            status="in_progress",
            workspace_dir=self.workspace_dir,
        )
        self.assertTrue(pulse_ok_50)

        # Work preservation: sample file on disk
        target_src = self.workspace_dir / "target_module.py"
        target_src.write_text("# clean production code\n", encoding="utf-8")

        # Code mutation tools denied by hard horizon fence
        for tool in sorted(CODE_MUTATION_TOOLS):
            with self.subTest(fence_tool=tool):
                res_fence = check_pre_tool_use(
                    tool,
                    {"TargetFile": str(target_src), "CodeContent": "# unapproved mutation"},
                    conv_id=conv_id,
                    state_dir=self.workspace_dir,
                    step_count=EXECUTIONER_HORIZON_STEPS,
                    role=FENCE_ROLE_DEEP_EXECUTION,
                )
                self.assertEqual(res_fence.get("decision"), "deny")
                self.assertIn("HARD HORIZON FENCE TRIGGERED", res_fence.get("reason", ""))
                self.assertIn(
                    "20-Step Remedy Budget Exhausted / 50 Steps Reached",
                    res_fence.get("reason", ""),
                )

        # Assert Work Preservation Invariant: File content remains unaltered
        self.assertEqual(target_src.read_text(encoding="utf-8"), "# clean production code\n")

        # Assert Verification Grace allows test commands via run_command
        test_commands = [
            "./agyis test",
            "python3 -m unittest discover -s tests -v",
            "pytest tests/",
            "python3 -m harness.cli test",
            "python3 -m unittest tests/test_ladder_integration.py -v",
        ]
        for cmd in test_commands:
            with self.subTest(grace_cmd=cmd):
                res_grace = check_pre_tool_use(
                    "run_command",
                    {"CommandLine": cmd},
                    conv_id=conv_id,
                    state_dir=self.workspace_dir,
                    step_count=EXECUTIONER_HORIZON_STEPS,
                    role=FENCE_ROLE_DEEP_EXECUTION,
                )
                self.assertEqual(res_grace.get("decision"), "allow")

        # Assert Read-Only and messaging tools allowed at step 50
        for read_tool in ("view_file", "grep_search", "send_message"):
            with self.subTest(read_tool=read_tool):
                res_read = check_pre_tool_use(
                    read_tool,
                    {"Recipient": "agyis_coordinator", "Message": "handoff"},
                    conv_id=conv_id,
                    state_dir=self.workspace_dir,
                    step_count=EXECUTIONER_HORIZON_STEPS,
                    role=FENCE_ROLE_DEEP_EXECUTION,
                )
                self.assertEqual(res_read.get("decision"), "allow")

        # ---------------------------------------------------------------------
        # 5. Simulate Stage Transition Handoff Payload
        # ---------------------------------------------------------------------
        handoff_payload = {
            "protocol_version": "2026.1",
            "task_id": task_id,
            "phase": "Phase 3.3",
            "stage": "EXECUTION",
            "status": "COMPLETE",
            "sender_role": "agyis_builder",
            "next_recommended_stage": "CODE_REVIEW",
            "git_commit_hash": "d0f0cf4",
            "diff_summary": {
                "modified_files": [
                    "harness/hooks/anti_loop_hook.py",
                    "harness/hooks/completion_fence_hook.py",
                    "tests/test_ladder_integration.py",
                ],
                "added_lines": 350,
                "deleted_lines": 20,
                "contiguous_chunks_count": 3,
            },
            "verification": {
                "command": "./agyis test",
                "exit_code": 0,
                "total_tests": 1572,
                "passed_tests": 1572,
                "failed_tests": 0,
                "benchmark_latency_s": 0.42,
            },
            "artifacts": {
                "plan_path": "docs/specs/epic-51-phase-3-3-plan.md",
                "reproduction_script": None,
                "report_path": None,
            },
        }

        # Validate handoff payload structure
        self.assertEqual(handoff_payload["protocol_version"], "2026.1")
        self.assertEqual(handoff_payload["task_id"], task_id)
        self.assertEqual(handoff_payload["stage"], "EXECUTION")
        self.assertEqual(handoff_payload["status"], "COMPLETE")
        self.assertEqual(handoff_payload["sender_role"], "agyis_builder")
        self.assertEqual(handoff_payload["next_recommended_stage"], "CODE_REVIEW")
        self.assertEqual(handoff_payload["verification"]["exit_code"], 0)

        handoff_message = (
            f"### Stage 1 (Executioner) Complete\n\n```json\n"
            f"{json.dumps(handoff_payload, indent=2)}\n```"
        )
        res_send = check_pre_tool_use(
            "send_message",
            {"Recipient": "agyis_coordinator", "Message": handoff_message},
            conv_id=conv_id,
            state_dir=self.workspace_dir,
            step_count=EXECUTIONER_HORIZON_STEPS,
            role=FENCE_ROLE_DEEP_EXECUTION,
        )
        self.assertEqual(res_send.get("decision"), "allow")

        # ---------------------------------------------------------------------
        # 6. Coordinator Handshake: Disarm Heartbeat & Materialize Stage 2
        # ---------------------------------------------------------------------
        disarm_ok = disarm_stage_heartbeat(status="complete", workspace_dir=self.workspace_dir)
        self.assertTrue(disarm_ok)

        # Verify heartbeat reflects complete status
        disarmed_hb = read_stage_heartbeat(workspace_dir=self.workspace_dir)
        self.assertIsNotNone(disarmed_hb)
        self.assertTrue(validate_heartbeat_schema(disarmed_hb))
        self.assertEqual(disarmed_hb["status"], "complete")
        self.assertIn("Disarmed stage with status: complete", disarmed_hb["last_action"])

        # Materialize Stage 2 (The Hammer / agyis_reviewer)
        role_path_s2 = materialize_stage_role(
            stage=2,
            agent_name="agyis_reviewer",
            task_id=task_id,
            workspace_dir=self.workspace_dir,
        )
        self.assertTrue(role_path_s2.is_file())

        stage2_role = read_stage_role(self.workspace_dir)
        self.assertIsNotNone(stage2_role)
        self.assertTrue(validate_stage_role_schema(stage2_role))
        self.assertEqual(stage2_role["role"], "forensic_auditor")
        self.assertEqual(stage2_role["stage"], 2)
        self.assertEqual(stage2_role["stage_name"], "CODE_REVIEW")
        self.assertEqual(stage2_role["specialist_agent"], "agyis_reviewer")

        # Evaluate Pre-Invocation for Stage 2 entry: asserts ROLE_FORENSIC_AUDITOR persona
        res_stage2 = evaluate_pre_invocation({}, workspace_dir=self.workspace_dir)
        inject_steps_s2 = res_stage2.get("injectSteps", [])
        self.assertEqual(len(inject_steps_s2), 1)
        self.assertIn("systemMessage", inject_steps_s2[0])
        sys_msg_s2 = inject_steps_s2[0]["systemMessage"]
        self.assertIn("[AGYIS ROLE PINNING: FORENSIC AUDITOR / THE HAMMER]", sys_msg_s2)
        self.assertIn("ANTI-FIXING & ZERO ERROR SWALLOWING", sys_msg_s2)
        self.assertIn("DUAL-AUDITOR GATE & CLEAN REVISION INVARIANT", sys_msg_s2)

    def test_stage_2_hammer_exemption_from_step_horizon(self) -> None:
        """Stage 2 (forensic_auditor) is exempt from the executioner's step horizon fence."""
        materialize_stage_role(2, "agyis_reviewer", "EPIC-51-3.3", workspace_dir=self.workspace_dir)

        # Anti-loop check at step 45: forensic_auditor allowed to list_dir
        res_sweep = check_anti_loop(
            "list_dir",
            {"DirectoryPath": str(self.workspace_dir)},
            conv_id="test-hammer-exemption",
            state_dir=self.workspace_dir,
            step_count=STEP_INTERRUPT_THRESHOLD,
            role=ANTI_LOOP_ROLE_FORENSIC_AUDITOR,
        )
        self.assertEqual(res_sweep.get("decision"), "allow")

        # Completion fence check at step 50: forensic_auditor is strictly exempt from
        # the hard horizon fence that blocks CODE_MUTATION_TOOLS for executioners.
        for tool in sorted(CODE_MUTATION_TOOLS):
            with self.subTest(exempt_tool=tool):
                res_tool = check_pre_tool_use(
                    tool,
                    {
                        "TargetFile": str(self.workspace_dir / "review_notes.md"),
                        "CodeContent": "# review verdict",
                    },
                    conv_id="test-hammer-exemption",
                    state_dir=self.workspace_dir,
                    step_count=EXECUTIONER_HORIZON_STEPS,
                    role=FENCE_ROLE_FORENSIC_AUDITOR,
                )
                self.assertEqual(res_tool.get("decision"), "allow")

    def test_sub_second_benchmark_execution_sla(self) -> None:
        """Full Ladder lifecycle simulation executes strictly within the 0.30s SLA (<300ms)."""
        t0 = time.perf_counter()

        for _ in range(5):
            # 1. Arm and materialize Stage 1
            arm_stage_heartbeat("EPIC-51-BENCH", "executioner", "agyis_builder", "role", self.workspace_dir)
            materialize_stage_role(1, "agyis_builder", "EPIC-51-BENCH", self.workspace_dir)
            evaluate_pre_invocation({"step_count": 0}, workspace_dir=self.workspace_dir)

            # 2. Step 40 warning
            pulse_stage_heartbeat(40, "action", "in_progress", self.workspace_dir)
            evaluate_pre_invocation({"step_count": 40}, workspace_dir=self.workspace_dir)

            bench_target = self.workspace_dir / "bench_target.py"

            # 3. Step 45 interrupt and anti-loop sweep deny
            pulse_stage_heartbeat(45, "action", "in_progress", self.workspace_dir)
            evaluate_pre_invocation({"step_count": 45}, workspace_dir=self.workspace_dir)
            check_anti_loop(
                "list_dir",
                {"DirectoryPath": str(self.workspace_dir)},
                conv_id="bench-integ",
                state_dir=self.workspace_dir,
                step_count=45,
                role=ANTI_LOOP_ROLE_DEEP_EXECUTION,
            )

            # 4. Step 50 hard horizon fence deny
            pulse_stage_heartbeat(50, "action", "in_progress", self.workspace_dir)
            check_pre_tool_use(
                "write_to_file",
                {"TargetFile": str(bench_target)},
                conv_id="bench-integ",
                state_dir=self.workspace_dir,
                step_count=50,
                role=FENCE_ROLE_DEEP_EXECUTION,
            )

            # 5. Disarm and materialize Stage 2
            disarm_stage_heartbeat(status="complete", workspace_dir=self.workspace_dir)
            materialize_stage_role(2, "agyis_reviewer", "EPIC-51-BENCH", self.workspace_dir)
            evaluate_pre_invocation({}, workspace_dir=self.workspace_dir)

        elapsed = time.perf_counter() - t0
        self.assertLess(
            elapsed,
            0.30,
            f"5 full lifecycle iterations took {elapsed:.4f}s (SLA: <0.30s)",
        )


if __name__ == "__main__":
    unittest.main()
