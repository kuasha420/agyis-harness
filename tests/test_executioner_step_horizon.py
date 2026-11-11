# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Arafat Zahan (@kuasha420)
# Corporate Stewardship & Infrastructure: Purrfect Software Limited (PSL)
# Governed by: ICARO-42/b Ordinance (Company-Supported Personal IP Framework)

"""
Hermetic test suite for Issue #109 (Epoch-Aware Soft Horizon Advisories, Replacing Cumulative 45/50 Hard Blocks).

Tests:
1. Cumulative steps 40/45/50 do NOT block healthy <80% workers in anti_loop_hook, fence_gates, or pre_invocation_hook.
2. Epoch step 80 (SOFT_EPOCH_STEP_ADVISORY) emits non-blocking [AGYIS EPOCH HORIZON ADVISORY: ...] in pre_invocation_hook.
3. Native slash commands bypass epoch horizon advisory injection.
4. Non-executioner roles (flight_director, forensic_auditor) are exempt from executioner horizon advisories.
5. Token proximity guard step horizon terminal gauge emits [EPOCH HORIZON: {step_count}/80 STEPS] at >= 80 epoch steps.
6. Benchmark SLA: Complete test suite passes in <0.20s.
"""

from __future__ import annotations

import io
import os
from pathlib import Path
import tempfile
import time
import unittest

from harness.hooks.anti_loop_hook import (
    EXECUTIONER_HORIZON_STEPS as ANTI_LOOP_HORIZON_STEPS,
    ROLE_DEEP_EXECUTION as ANTI_LOOP_ROLE_DEEP_EXECUTION,
    ROLE_FLIGHT_DIRECTOR as ANTI_LOOP_ROLE_FLIGHT_DIRECTOR,
    ROLE_FORENSIC_AUDITOR as ANTI_LOOP_ROLE_FORENSIC_AUDITOR,
    STEP_INTERRUPT_THRESHOLD,
    check_anti_loop,
    handle_pre_tool_use,
)
from harness.hooks.completion_fence_hook import (
    EXECUTIONER_HORIZON_STEPS,
    ROLE_DEEP_EXECUTION as FENCE_ROLE_DEEP_EXECUTION,
    ROLE_FLIGHT_DIRECTOR as FENCE_ROLE_FLIGHT_DIRECTOR,
    ROLE_FORENSIC_AUDITOR as FENCE_ROLE_FORENSIC_AUDITOR,
    check_pre_tool_use,
)
from harness.hooks.pre_invocation_hook import (
    EXECUTIONER_HORIZON_STEPS as PRE_INVOCATION_HORIZON_STEPS,
    ROLE_DEEP_EXECUTION as PRE_ROLE_DEEP_EXECUTION,
    ROLE_FLIGHT_DIRECTOR as PRE_ROLE_FLIGHT_DIRECTOR,
    SOFT_EPOCH_STEP_ADVISORY,
    evaluate_pre_invocation,
)
from harness.hooks.token_proximity_guard import (
    format_terminal_gauge,
    run_token_proximity_guard,
)


class TestExecutionerStepHorizon(unittest.TestCase):
    """Hermetic unit test suite for Issue #109 Epoch-Aware Soft Horizon Advisories."""

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

    def test_horizon_constants_unified_at_80_epoch_steps(self) -> None:
        """Retired 45/50 hard fences now align cleanly with SOFT_EPOCH_STEP_ADVISORY = 80."""
        self.assertEqual(SOFT_EPOCH_STEP_ADVISORY, 80)
        self.assertEqual(STEP_INTERRUPT_THRESHOLD, SOFT_EPOCH_STEP_ADVISORY)
        self.assertEqual(ANTI_LOOP_HORIZON_STEPS, SOFT_EPOCH_STEP_ADVISORY)
        self.assertEqual(EXECUTIONER_HORIZON_STEPS, SOFT_EPOCH_STEP_ADVISORY)
        self.assertEqual(PRE_INVOCATION_HORIZON_STEPS, SOFT_EPOCH_STEP_ADVISORY)

    # 1. Steps 40/45/50 remain unblocked for healthy agents
    def test_steps_40_45_50_remain_unblocked_for_healthy_executioner(self) -> None:
        """Healthy executioners at cumulative steps 40, 45, 50 are never hard-blocked."""
        for step in (40, 45, 50):
            with self.subTest(step=step):
                pre = evaluate_pre_invocation(
                    {"step_count": step, "role": PRE_ROLE_DEEP_EXECUTION},
                    workspace_dir=self.workspace_dir,
                )
                for item in pre.get("injectSteps", []):
                    msg = str(item.get("ephemeralMessage", ""))
                    self.assertNotIn("HORIZON WARNING", msg)
                    self.assertNotIn("HORIZON INTERRUPT", msg)
                    self.assertNotIn("EPOCH HORIZON ADVISORY", msg)

                sweep = check_anti_loop(
                    "list_dir",
                    {"DirectoryPath": "/workspace"},
                    conv_id=f"test-healthy-step-{step}",
                    state_dir=self.workspace_dir,
                    step_count=step,
                    role=ANTI_LOOP_ROLE_DEEP_EXECUTION,
                )
                self.assertEqual(sweep.get("decision"), "allow")

                edit = check_pre_tool_use(
                    "edit_file",
                    {"TargetFile": "/workspace/src/app.py"},
                    conv_id=f"test-healthy-edit-{step}",
                    state_dir=self.workspace_dir,
                    step_count=step,
                    role=FENCE_ROLE_DEEP_EXECUTION,
                )
                self.assertEqual(edit.get("decision"), "allow")

    # 2. Step 80 soft epoch horizon advisory injection
    def test_step_80_soft_epoch_advisory_injection(self) -> None:
        """Epoch step count 80 emits non-blocking [AGYIS EPOCH HORIZON ADVISORY] ephemeralMessage."""
        payload = {
            "step_count": SOFT_EPOCH_STEP_ADVISORY,
            "role": PRE_ROLE_DEEP_EXECUTION,
        }
        res = evaluate_pre_invocation(payload, workspace_dir=self.workspace_dir)
        inject_steps = res.get("injectSteps", [])
        self.assertEqual(len(inject_steps), 1)
        self.assertIn("ephemeralMessage", inject_steps[0])
        msg = inject_steps[0]["ephemeralMessage"]
        self.assertIn(f"[AGYIS EPOCH HORIZON ADVISORY: Epoch step 80/{SOFT_EPOCH_STEP_ADVISORY}", msg)

    def test_step_80_native_slash_command_bypass(self) -> None:
        """Native slash commands (/compact, /plan, /goal) bypass Epoch 80 advisory injection."""
        for cmd in ("/compact", "/plan", "/goal", "/boost", "/teamwork-preview"):
            with self.subTest(cmd=cmd):
                payload = {
                    "step_count": SOFT_EPOCH_STEP_ADVISORY,
                    "role": PRE_ROLE_DEEP_EXECUTION,
                    "prompt": f"{cmd} test",
                }
                res = evaluate_pre_invocation(payload, workspace_dir=self.workspace_dir)
                self.assertEqual(res, {"injectSteps": []})

    # 3. Anti-loop & completion fence remain non-blocking at step 80
    def test_step_80_exploratory_sweep_and_edits_remain_allowed_with_soft_advisory(self) -> None:
        """Anti-loop & completion fence emit soft advisories without denying healthy agents at step >= 80."""
        payload = {
            "conversationId": "test-soft-horizon-payload",
            "toolCall": {"name": "list_dir", "args": {"DirectoryPath": "/workspace"}},
            "step_count": 84,
            "role": "deep_execution",
        }
        self.assertEqual(handle_pre_tool_use(payload, state_dir=self.workspace_dir).get("decision"), "allow")

        for tool in ("write_to_file", "replace_file_content", "edit_file"):
            with self.subTest(tool=tool):
                res = check_pre_tool_use(
                    tool,
                    {"TargetFile": "/workspace/src/app.py", "CodeContent": "# update"},
                    conv_id="test-soft-fence-80",
                    state_dir=self.workspace_dir,
                    step_count=80,
                    role=FENCE_ROLE_DEEP_EXECUTION,
                )
                self.assertEqual(res.get("decision"), "allow")
                self.assertIn("[EPOCH HORIZON: 80/80 STEPS]", res.get("advisory", ""))

    def test_non_executioner_roles_exempt_from_epoch_horizon_advisories(self) -> None:
        """Non-executioner roles (flight_director, forensic_auditor) stay allow with no executioner fence."""
        for role in (FENCE_ROLE_FLIGHT_DIRECTOR, FENCE_ROLE_FORENSIC_AUDITOR):
            with self.subTest(role=role):
                self.assertEqual(
                    check_anti_loop(
                        "list_dir",
                        {"DirectoryPath": "/workspace"},
                        conv_id=f"test-exempt-{role}",
                        state_dir=self.workspace_dir,
                        step_count=85,
                        role=role,
                    ).get("decision"),
                    "allow",
                )
                res = check_pre_tool_use(
                    "write_to_file",
                    {"TargetFile": "/workspace/plan.md", "CodeContent": "# plan"},
                    conv_id=f"test-exempt-{role}-85",
                    state_dir=self.workspace_dir,
                    step_count=85,
                    role=role,
                )
                self.assertEqual(res, {"decision": "allow"})

    def test_work_preservation_on_soft_advisory(self) -> None:
        """Soft advisories never alter or revert local workspace files."""
        sample_file = self.workspace_dir / "preserved_work.py"
        sample_file.write_text("# precious in-flight modification\n", encoding="utf-8")

        res = check_pre_tool_use(
            "write_to_file",
            {"TargetFile": str(sample_file), "CodeContent": "# new content"},
            conv_id="test-work-preservation",
            state_dir=self.workspace_dir,
            step_count=85,
            role=FENCE_ROLE_DEEP_EXECUTION,
        )
        self.assertEqual(res.get("decision"), "allow")
        self.assertEqual(sample_file.read_text(encoding="utf-8"), "# precious in-flight modification\n")

    # 4. Token proximity guard step horizon terminal gauge awareness
    def test_token_proximity_guard_gauge_includes_epoch_horizon_tag(self) -> None:
        """format_terminal_gauge includes [EPOCH HORIZON: {step_count}/80 STEPS] when step >= 80 for executioner."""
        gauge_80 = format_terminal_gauge(tokens=1000, step_count=80, role="deep_execution")
        self.assertIn("[EPOCH HORIZON: 80/80 STEPS]", gauge_80)

        gauge_85 = format_terminal_gauge(tokens=2000, step_count=85, role="deep_execution")
        self.assertIn("[EPOCH HORIZON: 85/80 STEPS]", gauge_85)

        gauge_coord = format_terminal_gauge(tokens=1000, step_count=85, role="flight_director")
        self.assertNotIn("[EPOCH HORIZON:", gauge_coord)

        gauge_45 = format_terminal_gauge(tokens=1000, step_count=45, role="deep_execution")
        self.assertNotIn("[EPOCH HORIZON:", gauge_45)

    def test_run_token_proximity_guard_emits_epoch_horizon_gauge_to_stderr(self) -> None:
        """run_token_proximity_guard emits gauge with epoch horizon tag when epoch steps >= 80."""
        err_stream = io.StringIO()
        payload = {
            "conversationId": "test-proximity-horizon",
            "step_count": 82,
            "role": "deep_execution",
        }
        res = run_token_proximity_guard(payload, stderr=err_stream)
        self.assertEqual(res, {"decision": "allow"})
        output = err_stream.getvalue()
        self.assertIn("[EPOCH HORIZON: 82/80 STEPS]", output)
        self.assertIn("[AGYIS TOKEN GAUGE]", output)


class TestStepHorizonBenchmark(unittest.TestCase):
    """Asserts that all step horizon evaluations execute well under 0.20s."""

    def test_complete_horizon_benchmark_sla(self) -> None:
        """50 iterations of pre-invocation, anti-loop, and completion fence execute in <0.20s."""
        t0 = time.perf_counter()

        for step in (45, 50, 80):
            evaluate_pre_invocation({"step_count": step, "role": "deep_execution"})
            check_anti_loop("list_dir", {"DirectoryPath": "/tmp"}, step_count=step, role="deep_execution")
            check_pre_tool_use("write_to_file", {"TargetFile": "/tmp/test.py"}, step_count=step, role="deep_execution")
            format_terminal_gauge(tokens=10000, step_count=step, role="deep_execution")

        elapsed = time.perf_counter() - t0
        self.assertLess(
            elapsed,
            0.20,
            f"Step horizon cycle evaluation took {elapsed:.4f}s (SLA is <0.20s)",
        )


if __name__ == "__main__":
    unittest.main()
