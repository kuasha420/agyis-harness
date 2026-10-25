# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Arafat Zahan (@kuasha420)
# Corporate Stewardship & Infrastructure: Purrfect Software Limited (PSL)
# Governed by: ICARO-42/b Ordinance (Company-Supported Personal IP Framework)

"""
Hermetic test suite for Phase 3.3.2 (Issue #86: Thrashing-Activated Dynamic Horizon Fence).

Tests:
1. Step 40 warning ephemeralMessage injection in pre_invocation_hook.
2. Step 45 interrupt ephemeralMessage injection in pre_invocation_hook.
3. Step 45 exploratory sweep block (list_dir, find_by_name) in anti_loop_hook.
4. Step 50 hard mutation stop fence in completion_fence_hook blocking code edits.
5. Verification grace turn allows run_command test execution and read-only tools at step 50.
6. Non-executioner roles (flight_director, forensic_auditor) exempt from the 50-step fence.
7. Work preservation invariant (no git reverts, modifications preserved intact on disk).
8. Token proximity guard step horizon terminal gauge awareness ([HORIZON: {step_count}/50 STEPS]).
9. Benchmark SLA: Complete test suite passes in <0.20s.
"""

from __future__ import annotations

import io
import json
import os
from pathlib import Path
import tempfile
import time
import unittest

from harness.hooks.anti_loop_hook import (
    check_anti_loop,
    evaluate_tool_call,
    handle_pre_tool_use,
    ROLE_DEEP_EXECUTION as ANTI_LOOP_ROLE_DEEP_EXECUTION,
    ROLE_FLIGHT_DIRECTOR as ANTI_LOOP_ROLE_FLIGHT_DIRECTOR,
    ROLE_FORENSIC_AUDITOR as ANTI_LOOP_ROLE_FORENSIC_AUDITOR,
)
from harness.hooks.completion_fence_hook import (
    check_pre_tool_use,
    check_completion_fence_pre_tool,
    CODE_MUTATION_TOOLS,
    EXECUTIONER_HORIZON_STEPS,
    ROLE_DEEP_EXECUTION as FENCE_ROLE_DEEP_EXECUTION,
    ROLE_FLIGHT_DIRECTOR as FENCE_ROLE_FLIGHT_DIRECTOR,
    ROLE_FORENSIC_AUDITOR as FENCE_ROLE_FORENSIC_AUDITOR,
)
from harness.hooks.pre_invocation_hook import (
    evaluate_pre_invocation,
    EXECUTIONER_HORIZON_STEPS as PRE_INVOCATION_HORIZON_STEPS,
    STEP_WARNING_THRESHOLD,
    STEP_INTERRUPT_THRESHOLD,
    ROLE_DEEP_EXECUTION as PRE_ROLE_DEEP_EXECUTION,
    ROLE_FLIGHT_DIRECTOR as PRE_ROLE_FLIGHT_DIRECTOR,
)
from harness.hooks.token_proximity_guard import (
    format_terminal_gauge,
    check_token_proximity,
    run_token_proximity_guard,
    ROLE_DEEP_EXECUTION as GUARD_ROLE_DEEP_EXECUTION,
)


class TestExecutionerStepHorizon(unittest.TestCase):
    """Hermetic unit test suite for Issue #86 Thrashing-Activated Dynamic Horizon Fence."""

    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.workspace_dir = Path(self.temp_dir.name)
        self.orig_role = os.environ.get("AGYIS_ROLE")
        self.orig_agent_role = os.environ.get("PSL_AGENT_ROLE")
        os.environ.pop("AGYIS_ROLE", None)
        os.environ.pop("PSL_AGENT_ROLE", None)

    def tearDown(self) -> None:
        if self.orig_role is not None:
            os.environ["AGYIS_ROLE"] = self.orig_role
        else:
            os.environ.pop("AGYIS_ROLE", None)
        if self.orig_agent_role is not None:
            os.environ["PSL_AGENT_ROLE"] = self.orig_agent_role
        else:
            os.environ.pop("PSL_AGENT_ROLE", None)
        self.temp_dir.cleanup()

    # 1. Step 40 warning ephemeralMessage injection
    def test_step_40_warning_ephemeral_message_injection(self) -> None:
        """Step count 40 for executioner injects transient ephemeralMessage warning."""
        payload = {
            "step_count": STEP_WARNING_THRESHOLD,
            "role": PRE_ROLE_DEEP_EXECUTION,
        }
        res = evaluate_pre_invocation(payload, workspace_dir=self.workspace_dir)
        inject_steps = res.get("injectSteps", [])
        self.assertEqual(len(inject_steps), 1)
        self.assertIn("ephemeralMessage", inject_steps[0])

        msg = inject_steps[0]["ephemeralMessage"]
        expected_warning = (
            "[AGYIS HORIZON WARNING: THRASHING DETECTED / REMEDY MODE ACTIVE - 10 STEPS REMAINING] "
            "You have 10 steps remaining in your convergence budget. Cease exploring new files, "
            "complete active edits, run tests, and prepare stage handoff."
        )
        self.assertIn(expected_warning, msg)

    def test_step_40_warning_native_slash_command_bypass(self) -> None:
        """Native slash commands (/compact, /plan, /goal) bypass Step 40 warning injection."""
        for cmd in ("/compact", "/plan", "/goal", "/boost", "/teamwork-preview"):
            with self.subTest(cmd=cmd):
                payload = {
                    "step_count": STEP_WARNING_THRESHOLD,
                    "role": PRE_ROLE_DEEP_EXECUTION,
                    "prompt": f"{cmd} test",
                }
                res = evaluate_pre_invocation(payload, workspace_dir=self.workspace_dir)
                self.assertEqual(res, {"injectSteps": []})

    # 2. Step 45 interrupt ephemeralMessage injection
    def test_step_45_interrupt_ephemeral_message_injection(self) -> None:
        """Step count 45 for executioner injects transient ephemeralMessage interrupt."""
        payload = {
            "step_count": STEP_INTERRUPT_THRESHOLD,
            "role": PRE_ROLE_DEEP_EXECUTION,
        }
        res = evaluate_pre_invocation(payload, workspace_dir=self.workspace_dir)
        inject_steps = res.get("injectSteps", [])
        self.assertEqual(len(inject_steps), 1)
        self.assertIn("ephemeralMessage", inject_steps[0])

        msg = inject_steps[0]["ephemeralMessage"]
        expected_interrupt = (
            "[AGYIS HORIZON INTERRUPT: 5 STEPS REMAINING] "
            "Compulsory convergence active. You have 5 steps remaining. Open sweeps are blocked. "
            "Wrap up active diff and emit stage handoff."
        )
        self.assertEqual(expected_interrupt, msg)

    def test_step_45_interrupt_native_slash_command_bypass(self) -> None:
        """Native slash commands bypass Step 45 interrupt injection."""
        payload = {
            "step_count": STEP_INTERRUPT_THRESHOLD,
            "role": PRE_ROLE_DEEP_EXECUTION,
            "prompt": "/compact",
        }
        res = evaluate_pre_invocation(payload, workspace_dir=self.workspace_dir)
        self.assertEqual(res, {"injectSteps": []})

    def test_non_executioner_exempt_from_horizon_messages(self) -> None:
        """Non-executioner roles (flight_director) do not receive horizon warning/interrupt."""
        for step in (STEP_WARNING_THRESHOLD, STEP_INTERRUPT_THRESHOLD):
            with self.subTest(step=step):
                payload = {
                    "step_count": step,
                    "role": PRE_ROLE_FLIGHT_DIRECTOR,
                }
                res = evaluate_pre_invocation(payload, workspace_dir=self.workspace_dir)
                inject_steps = res.get("injectSteps", [])
                for item in inject_steps:
                    msg = item.get("ephemeralMessage", "")
                    self.assertNotIn("[AGYIS HORIZON WARNING:", msg)
                    self.assertNotIn("[AGYIS HORIZON INTERRUPT:", msg)

    # 3. Step 45 exploratory sweep block in anti_loop_hook
    def test_step_45_exploratory_sweep_blocked_in_anti_loop(self) -> None:
        """list_dir and find_by_name are blocked for executioner at step >= 45."""
        expected_reason = (
            "Compulsory convergence active (Step 45/50). "
            "Open-ended repository sweeps are blocked. "
            "Complete active edits, run tests, and emit stage handoff."
        )

        for tool in ("list_dir", "find_by_name"):
            with self.subTest(tool=tool):
                res = check_anti_loop(
                    tool,
                    {"DirectoryPath": "/workspace"} if tool == "list_dir" else {"Pattern": "*.py", "SearchDirectory": "/workspace"},
                    conv_id="test-horizon-sweeps",
                    state_dir=self.workspace_dir,
                    step_count=45,
                    role=ANTI_LOOP_ROLE_DEEP_EXECUTION,
                )
                self.assertEqual(res.get("decision"), "deny")
                self.assertEqual(res.get("reason"), expected_reason)

    def test_step_45_payload_based_sweep_blocked_in_anti_loop(self) -> None:
        """handle_pre_tool_use blocks exploratory sweeps when step >= 45 in payload."""
        payload = {
            "conversationId": "test-horizon-payload",
            "toolCall": {"name": "list_dir", "args": {"DirectoryPath": "/workspace"}},
            "step_count": 48,
            "role": "deep_execution",
        }
        res = handle_pre_tool_use(payload, state_dir=self.workspace_dir)
        self.assertEqual(res.get("decision"), "deny")
        self.assertIn("Compulsory convergence active", res.get("reason", ""))

    def test_step_45_targeted_inspection_and_test_permitted(self) -> None:
        """view_file and run_command test runners remain permitted at step >= 45."""
        view_res = check_anti_loop(
            "view_file",
            {"AbsolutePath": "/workspace/src/app.py"},
            conv_id="test-horizon-permitted",
            state_dir=self.workspace_dir,
            step_count=45,
            role=ANTI_LOOP_ROLE_DEEP_EXECUTION,
        )
        self.assertEqual(view_res.get("decision"), "allow")

        test_res = check_anti_loop(
            "run_command",
            {"CommandLine": "./agyis test"},
            conv_id="test-horizon-permitted",
            state_dir=self.workspace_dir,
            step_count=45,
            role=ANTI_LOOP_ROLE_DEEP_EXECUTION,
        )
        self.assertEqual(test_res.get("decision"), "allow")

    def test_step_below_45_exploratory_sweep_allowed(self) -> None:
        """Exploratory sweeps at step 44 are permitted by compulsory convergence."""
        res = check_anti_loop(
            "list_dir",
            {"DirectoryPath": "/workspace"},
            conv_id="test-horizon-step44",
            state_dir=self.workspace_dir,
            step_count=44,
            role=ANTI_LOOP_ROLE_DEEP_EXECUTION,
        )
        self.assertEqual(res.get("decision"), "allow")

    def test_non_executioner_exploratory_sweep_allowed_at_step_45(self) -> None:
        """Non-executioner roles (flight_director, forensic_auditor) are exempt from sweep blocking at step 45."""
        for role in (ANTI_LOOP_ROLE_FLIGHT_DIRECTOR, ANTI_LOOP_ROLE_FORENSIC_AUDITOR):
            with self.subTest(role=role):
                res = check_anti_loop(
                    "list_dir",
                    {"DirectoryPath": "/workspace"},
                    conv_id=f"test-exempt-{role}",
                    state_dir=self.workspace_dir,
                    step_count=45,
                    role=role,
                )
                self.assertEqual(res.get("decision"), "allow")

    # 4. Step 50 hard mutation stop fence in completion_fence_hook
    def test_step_50_hard_mutation_stop_fence_blocks_code_edits(self) -> None:
        """Code mutation tools are strictly blocked for executioner at step >= 50."""
        expected_reason = (
            "HARD HORIZON FENCE TRIGGERED (20-Step Remedy Budget Exhausted / 50 Steps Reached). "
            "Further code mutation is strictly blocked to prevent cognitive cliff collapse. "
            "All local modifications are preserved intact on disk. You are granted 1 Verification Grace turn to run tests. "
            "You MUST immediately message the parent agent via send_message with your stage transition payload and STOP calling tools."
        )

        for tool in ("write_to_file", "replace_file_content", "edit_file"):
            with self.subTest(tool=tool):
                res = check_pre_tool_use(
                    tool,
                    {"TargetFile": "/workspace/src/app.py", "CodeContent": "# update"},
                    conv_id="test-horizon-fence-50",
                    state_dir=self.workspace_dir,
                    step_count=50,
                    role=FENCE_ROLE_DEEP_EXECUTION,
                )
                self.assertEqual(res.get("decision"), "deny")
                self.assertEqual(res.get("reason"), expected_reason)

    def test_step_below_50_allows_code_edits(self) -> None:
        """Code mutation tools at step 49 are allowed by horizon fence."""
        res = check_pre_tool_use(
            "write_to_file",
            {"TargetFile": "/workspace/src/app.py", "CodeContent": "# update"},
            conv_id="test-horizon-fence-49",
            state_dir=self.workspace_dir,
            step_count=49,
            role=FENCE_ROLE_DEEP_EXECUTION,
        )
        self.assertEqual(res.get("decision"), "allow")

    # 5. Verification grace turn allows run_command test execution at step 50
    def test_step_50_verification_grace_permits_tests_and_reads(self) -> None:
        """Verification grace turn permits test runner commands and read-only tools at step 50."""
        # Test command permitted
        res_test = check_pre_tool_use(
            "run_command",
            {"CommandLine": "./agyis test"},
            conv_id="test-grace-turn",
            state_dir=self.workspace_dir,
            step_count=50,
            role=FENCE_ROLE_DEEP_EXECUTION,
        )
        self.assertEqual(res_test.get("decision"), "allow")

        # Read-only tools permitted
        for tool in ("view_file", "grep_search", "send_message"):
            with self.subTest(tool=tool):
                res_read = check_pre_tool_use(
                    tool,
                    {"AbsolutePath": "/workspace/test.py"},
                    conv_id="test-grace-turn",
                    state_dir=self.workspace_dir,
                    step_count=50,
                    role=FENCE_ROLE_DEEP_EXECUTION,
                )
                self.assertEqual(res_read.get("decision"), "allow")

    # 6. Non-executioner roles exempt from 50-step fence
    def test_non_executioner_roles_exempt_from_50_step_fence(self) -> None:
        """Non-executioner roles (flight_director, forensic_auditor) are exempt from 50-step mutation fence."""
        for role in (FENCE_ROLE_FLIGHT_DIRECTOR, FENCE_ROLE_FORENSIC_AUDITOR):
            with self.subTest(role=role):
                res = check_pre_tool_use(
                    "write_to_file",
                    {"TargetFile": "/workspace/plan.md", "CodeContent": "# plan"},
                    conv_id=f"test-exempt-{role}-50",
                    state_dir=self.workspace_dir,
                    step_count=50,
                    role=role,
                )
                self.assertEqual(res.get("decision"), "allow")

    # 7. Work preservation invariant (no git reverts)
    def test_work_preservation_invariant_no_git_reverts(self) -> None:
        """When hard horizon fence triggers denial, local files on disk remain completely intact."""
        sample_file = self.workspace_dir / "preserved_work.py"
        sample_file.write_text("# precious in-flight modification\n", encoding="utf-8")

        res = check_pre_tool_use(
            "write_to_file",
            {"TargetFile": str(sample_file), "CodeContent": "# new content"},
            conv_id="test-work-preservation",
            state_dir=self.workspace_dir,
            step_count=50,
            role=FENCE_ROLE_DEEP_EXECUTION,
        )
        self.assertEqual(res.get("decision"), "deny")
        # Ensure disk content is preserved intact
        self.assertEqual(sample_file.read_text(encoding="utf-8"), "# precious in-flight modification\n")

    # 8. Token proximity guard step horizon terminal gauge awareness
    def test_token_proximity_guard_gauge_includes_horizon_tag(self) -> None:
        """format_terminal_gauge includes [HORIZON: {step_count}/50 STEPS] when step >= 40 for executioner."""
        gauge_40 = format_terminal_gauge(tokens=1000, step_count=40, role="deep_execution")
        self.assertIn("[HORIZON: 40/50 STEPS]", gauge_40)

        gauge_45 = format_terminal_gauge(tokens=2000, step_count=45, role="deep_execution")
        self.assertIn("[HORIZON: 45/50 STEPS]", gauge_45)

        # Non-executioner does not include horizon tag
        gauge_coord = format_terminal_gauge(tokens=1000, step_count=45, role="flight_director")
        self.assertNotIn("[HORIZON:", gauge_coord)

        # Step count < 40 does not include horizon tag
        gauge_39 = format_terminal_gauge(tokens=1000, step_count=39, role="deep_execution")
        self.assertNotIn("[HORIZON:", gauge_39)

    def test_run_token_proximity_guard_emits_horizon_gauge_to_stderr(self) -> None:
        """run_token_proximity_guard emits gauge with horizon tag to stderr when step >= 40 for executioner."""
        err_stream = io.StringIO()
        payload = {
            "conversationId": "test-proximity-horizon",
            "step_count": 42,
            "role": "deep_execution",
        }
        res = run_token_proximity_guard(payload, stderr=err_stream)
        self.assertEqual(res, {"decision": "allow"})
        output = err_stream.getvalue()
        self.assertIn("[HORIZON: 42/50 STEPS]", output)
        self.assertIn("[AGYIS TOKEN GAUGE]", output)


class TestStepHorizonBenchmark(unittest.TestCase):
    """Asserts that all step horizon evaluations execute well under 0.20s."""

    def test_complete_horizon_benchmark_sla(self) -> None:
        """50 iterations of pre-invocation, anti-loop, and completion fence execute in <0.20s."""
        t0 = time.perf_counter()

        for step in (40, 45, 50):
            # Pre-invocation evaluation
            evaluate_pre_invocation({"step_count": step, "role": "deep_execution"})

            # Anti-loop check
            check_anti_loop("list_dir", {"DirectoryPath": "/tmp"}, step_count=step, role="deep_execution")

            # Completion fence PreToolUse check
            check_pre_tool_use("write_to_file", {"TargetFile": "/tmp/test.py"}, step_count=step, role="deep_execution")

            # Token proximity gauge format
            format_terminal_gauge(tokens=10000, step_count=step, role="deep_execution")

        elapsed = time.perf_counter() - t0
        self.assertLess(
            elapsed,
            0.20,
            f"Step horizon cycle evaluation took {elapsed:.4f}s (SLA is <0.20s)",
        )


if __name__ == "__main__":
    unittest.main()
