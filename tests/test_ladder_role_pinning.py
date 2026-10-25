# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Arafat Zahan (@kuasha420)
# Corporate Stewardship & Infrastructure: Purrfect Software Limited (PSL)
# Governed by: ICARO-42/b Ordinance (Company-Supported Personal IP Framework)

"""
Hermetic Unit Tests: Subagent Ladder Role-Pinning Invariants & Stage Materialization (Issue #85).

Verifies:
- STAGE_ROLE_MAP and STAGE_NAME_MAP constants.
- Materialization, schema validation, reading, and clearing of .agents/session_role.json.
- Pillar 3 explicit cognitive role resolution via check_pillar_3_explicit_role.
- Turn 0 dual-anchor systemMessage injection (stage entry and post-compaction).
- Intra-epoch periodic ephemeralMessage re-anchor advisories (turns 10, 20, 30).
- Native system slash commands bypassing role injection.
- Hermetic execution under 0.20s benchmark latency SLA.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
import tempfile
import time
import unittest

from harness.hooks.pre_invocation_hook import (
    DEFAULT_ROLE_PINNING_CADENCE,
    ROLE_DEEP_EXECUTION,
    ROLE_FLIGHT_DIRECTOR,
    ROLE_FORENSIC_AUDITOR,
    ROLE_SWARM_ORCHESTRATOR,
    build_role_persona_prompt,
    build_role_reanchor_advisory,
    check_pillar_3_explicit_role,
    evaluate_pre_invocation,
    get_role_pinning_cadence,
)
from harness.subagents.stage_role import (
    STAGE_NAME_MAP,
    STAGE_ROLE_MAP,
    clear_stage_role,
    materialize_stage_role,
    read_stage_role,
    validate_stage_role_schema,
)


class TestStageRoleMapping(unittest.TestCase):
    """Verifies STAGE_ROLE_MAP and STAGE_NAME_MAP structural taxonomy."""

    def test_stage_role_map_entries(self) -> None:
        """STAGE_ROLE_MAP maps stages 0-4 to mainline roles."""
        expected_roles = {
            0: "flight_director",
            1: "deep_execution",
            2: "forensic_auditor",
            3: "deep_execution",
            4: "forensic_auditor",
        }
        self.assertEqual(STAGE_ROLE_MAP, expected_roles)

    def test_stage_name_map_entries(self) -> None:
        """STAGE_NAME_MAP maps stages 0-4 to uppercase canonical stage identifiers."""
        expected_names = {
            0: "COORDINATION",
            1: "EXECUTION",
            2: "CODE_REVIEW",
            3: "GIT_CUSTODY",
            4: "QA_AUDIT",
        }
        self.assertEqual(STAGE_NAME_MAP, expected_names)

    def test_stage_keys_match(self) -> None:
        """STAGE_ROLE_MAP and STAGE_NAME_MAP must declare identical stage keys."""
        self.assertEqual(set(STAGE_ROLE_MAP.keys()), set(STAGE_NAME_MAP.keys()))
        self.assertEqual(set(STAGE_ROLE_MAP.keys()), {0, 1, 2, 3, 4})


class TestStageRoleMaterializationAndSchema(unittest.TestCase):
    """Verifies atomic writing, reading, clearing, and schema validation of session_role.json."""

    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.workspace_dir = Path(self.temp_dir.name)

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def test_materialize_and_read_all_stages(self) -> None:
        """Every ladder stage (0-4) materializes and reads back a valid schema payload."""
        specialists = {
            0: "agyis_coordinator",
            1: "agyis_builder",
            2: "agyis_reviewer",
            3: "agyis_custodian",
            4: "agyis_auditor",
        }

        for stage, agent_name in specialists.items():
            with self.subTest(stage=stage, agent=agent_name):
                task_id = f"TASK-{stage}-001"
                role_path = materialize_stage_role(
                    stage=stage,
                    agent_name=agent_name,
                    task_id=task_id,
                    workspace_dir=self.workspace_dir,
                )

                self.assertTrue(role_path.is_file())
                self.assertEqual(
                    role_path, self.workspace_dir / ".agents" / "session_role.json"
                )

                data = read_stage_role(self.workspace_dir)
                self.assertIsNotNone(data)
                self.assertIsInstance(data, dict)
                self.assertEqual(data["role"], STAGE_ROLE_MAP[stage])
                self.assertEqual(data["specialist_agent"], agent_name)
                self.assertEqual(data["stage"], stage)
                self.assertEqual(data["stage_name"], STAGE_NAME_MAP[stage])
                self.assertEqual(data["task_id"], task_id)
                self.assertIn("updated_at", data)
                self.assertIn("$schema", data)

    def test_clear_stage_role(self) -> None:
        """clear_stage_role safely unlinks session_role.json."""
        materialize_stage_role(1, "agyis_builder", "T-01", workspace_dir=self.workspace_dir)
        self.assertTrue((self.workspace_dir / ".agents" / "session_role.json").is_file())

        cleared = clear_stage_role(self.workspace_dir)
        self.assertTrue(cleared)
        self.assertFalse((self.workspace_dir / ".agents" / "session_role.json").exists())

        # Second clear call returns False safely
        self.assertFalse(clear_stage_role(self.workspace_dir))

    def test_schema_validation_failures(self) -> None:
        """validate_stage_role_schema rejects malformed payloads."""
        self.assertFalse(validate_stage_role_schema(None))
        self.assertFalse(validate_stage_role_schema("not-a-dict"))
        self.assertFalse(validate_stage_role_schema({}))

        # Missing required key
        incomplete = {
            "role": "deep_execution",
            "specialist_agent": "agyis_builder",
            "stage": 1,
            "stage_name": "EXECUTION",
            # missing task_id
        }
        self.assertFalse(validate_stage_role_schema(incomplete))

        # Invalid stage number
        invalid_stage = {
            "role": "deep_execution",
            "specialist_agent": "agyis_builder",
            "stage": 99,
            "stage_name": "EXECUTION",
            "task_id": "T-1",
        }
        self.assertFalse(validate_stage_role_schema(invalid_stage))

        # Role mismatch for stage
        role_mismatch = {
            "role": "flight_director",  # should be deep_execution for stage 1
            "specialist_agent": "agyis_builder",
            "stage": 1,
            "stage_name": "EXECUTION",
            "task_id": "T-1",
        }
        self.assertFalse(validate_stage_role_schema(role_mismatch))

        # Stage name mismatch
        name_mismatch = {
            "role": "deep_execution",
            "specialist_agent": "agyis_builder",
            "stage": 1,
            "stage_name": "COORDINATION",
            "task_id": "T-1",
        }
        self.assertFalse(validate_stage_role_schema(name_mismatch))

    def test_materialize_argument_validation(self) -> None:
        """materialize_stage_role raises ValueError on invalid inputs."""
        with self.assertRaises(ValueError):
            materialize_stage_role(99, "agyis_builder", "T-1", workspace_dir=self.workspace_dir)
        with self.assertRaises(ValueError):
            materialize_stage_role(1, "", "T-1", workspace_dir=self.workspace_dir)
        with self.assertRaises(ValueError):
            materialize_stage_role(1, "agyis_builder", "", workspace_dir=self.workspace_dir)

    def test_read_corrupted_json(self) -> None:
        """read_stage_role gracefully returns None on corrupted JSON."""
        role_file = self.workspace_dir / ".agents" / "session_role.json"
        role_file.parent.mkdir(parents=True, exist_ok=True)
        role_file.write_text("{broken json", encoding="utf-8")
        self.assertIsNone(read_stage_role(self.workspace_dir))


class TestPillar3ExplicitRoleResolution(unittest.TestCase):
    """Verifies check_pillar_3_explicit_role resolves materialized session_role.json."""

    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.workspace_dir = Path(self.temp_dir.name)

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def test_pillar_3_resolves_all_stages(self) -> None:
        """check_pillar_3_explicit_role returns the mapped role for each materialized stage."""
        for stage, expected_role in STAGE_ROLE_MAP.items():
            with self.subTest(stage=stage, expected_role=expected_role):
                materialize_stage_role(
                    stage=stage,
                    agent_name=f"agent_{stage}",
                    task_id=f"T-{stage}",
                    workspace_dir=self.workspace_dir,
                )
                resolved = check_pillar_3_explicit_role(
                    {}, workspace_dir=self.workspace_dir
                )
                self.assertEqual(resolved, expected_role)

    def test_pillar_3_returns_none_when_cleared(self) -> None:
        """check_pillar_3_explicit_role returns None after stage role is cleared."""
        materialize_stage_role(1, "agyis_builder", "T-01", workspace_dir=self.workspace_dir)
        self.assertEqual(
            check_pillar_3_explicit_role({}, workspace_dir=self.workspace_dir),
            ROLE_DEEP_EXECUTION,
        )
        clear_stage_role(self.workspace_dir)
        self.assertIsNone(
            check_pillar_3_explicit_role({}, workspace_dir=self.workspace_dir)
        )


class TestRolePinningDualAnchorAndReAnchor(unittest.TestCase):
    """Verifies Turn 0 systemMessage dual-anchor and periodic ephemeralMessage re-anchors."""

    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.workspace_dir = Path(self.temp_dir.name)
        os.environ.pop("AGYIS_ROLE_PINNING_CADENCE", None)

    def tearDown(self) -> None:
        self.temp_dir.cleanup()
        os.environ.pop("AGYIS_ROLE_PINNING_CADENCE", None)

    def test_turn_zero_stage_entry_injection(self) -> None:
        """Turn 0 stage entry via explicit payload step_count=0 injects role persona systemMessage."""
        payload = {"step_count": 0, "role": "deep_execution"}
        res = evaluate_pre_invocation(payload, workspace_dir=self.workspace_dir)

        inject_steps = res.get("injectSteps", [])
        self.assertEqual(len(inject_steps), 1)
        self.assertIn("systemMessage", inject_steps[0])

        system_msg = inject_steps[0]["systemMessage"]
        self.assertIn("[AGYIS ROLE PINNING: DEEP EXECUTION / EXECUTIONER]", system_msg)
        self.assertIn("WORK PRESERVATION CONTRACT", system_msg)
        self.assertIn("SURGICAL CONTIGUOUS EDITS INVARIANT", system_msg)
        self.assertIn("ZERO SCOPE CREEP", system_msg)

    def test_turn_zero_materialized_stage_role(self) -> None:
        """Materialized stage role in workspace triggers Turn 0 stage entry systemMessage."""
        materialize_stage_role(
            stage=1,
            agent_name="agyis_builder",
            task_id="PHASE-3-3-1",
            workspace_dir=self.workspace_dir,
        )

        # Empty payload without step_count resolves Turn 0 via materialized stage_role
        res = evaluate_pre_invocation({}, workspace_dir=self.workspace_dir)
        inject_steps = res.get("injectSteps", [])
        self.assertEqual(len(inject_steps), 1)
        self.assertIn("systemMessage", inject_steps[0])
        self.assertIn("DEEP EXECUTION", inject_steps[0]["systemMessage"])

    def test_turn_zero_coordinator_stage(self) -> None:
        """Stage 0 (flight_director) injects coordinator-specific invariants."""
        payload = {"step_count": 0, "role": "flight_director"}
        res = evaluate_pre_invocation(payload, workspace_dir=self.workspace_dir)

        inject_steps = res.get("injectSteps", [])
        self.assertEqual(len(inject_steps), 1)
        system_msg = inject_steps[0]["systemMessage"]
        self.assertIn("[AGYIS ROLE PINNING: FLIGHT DIRECTOR / COORDINATOR]", system_msg)
        self.assertIn("ANTI-CHATBOT SEDUCTION & COGNITIVE STATE FLUSH", system_msg)
        self.assertIn("ZERO COORDINATOR REMEDIATION", system_msg)

    def test_turn_zero_auditor_stage(self) -> None:
        """Stage 2/4 (forensic_auditor) injects auditor-specific invariants."""
        payload = {"step_count": 0, "role": "forensic_auditor"}
        res = evaluate_pre_invocation(payload, workspace_dir=self.workspace_dir)

        inject_steps = res.get("injectSteps", [])
        self.assertEqual(len(inject_steps), 1)
        system_msg = inject_steps[0]["systemMessage"]
        self.assertIn("[AGYIS ROLE PINNING: FORENSIC AUDITOR / THE HAMMER]", system_msg)
        self.assertIn("ANTI-FIXING & ZERO ERROR SWALLOWING", system_msg)
        self.assertIn("DUAL-AUDITOR GATE & CLEAN REVISION INVARIANT", system_msg)

    def test_post_compaction_reanchor_dual_anchor(self) -> None:
        """Turn 0 post-compaction ('# Resuming from a compaction...') injects systemMessage."""
        prompts = [
            "# Resuming from a compaction...\nPrevious context summarized.",
            "# Resuming from a compaction\nContinuing work.",
            "Some header\n\n# Resuming from a compaction...\nRest of prompt",
        ]
        for prompt in prompts:
            with self.subTest(prompt=prompt[:35]):
                payload = {
                    "step_count": 5,  # Mid-trajectory turn, but post-compaction
                    "prompt": prompt,
                    "role": "deep_execution",
                }
                res = evaluate_pre_invocation(payload, workspace_dir=self.workspace_dir)
                inject_steps = res.get("injectSteps", [])
                self.assertEqual(len(inject_steps), 1)
                self.assertIn("systemMessage", inject_steps[0])
                self.assertIn("DEEP EXECUTION", inject_steps[0]["systemMessage"])

    def test_intra_epoch_periodic_reanchors(self) -> None:
        """Turns 10, 20, 30 inject intra-epoch ephemeralMessage re-anchor advisories."""
        for step in (10, 20, 30, 40):
            with self.subTest(step=step):
                payload = {"step_count": step, "role": "deep_execution"}
                res = evaluate_pre_invocation(payload, workspace_dir=self.workspace_dir)

                inject_steps = res.get("injectSteps", [])
                self.assertEqual(len(inject_steps), 1)
                self.assertIn("ephemeralMessage", inject_steps[0])

                msg = inject_steps[0]["ephemeralMessage"]
                self.assertIn(f"[AGYIS ROLE RE-ANCHOR: DEEP_EXECUTION (STEP {step} | CADENCE 10)]", msg)
                self.assertIn("PERIODIC COGNITIVE ATTENTION AUDIT", msg)
                self.assertIn("Work Preservation", msg)

    def test_off_cadence_turns_emit_no_reanchor(self) -> None:
        """Non-cadence turns (1, 5, 9, 11, 23) do not trigger ephemeralMessage re-anchors."""
        for step in (1, 2, 5, 9, 11, 15, 23):
            with self.subTest(step=step):
                payload = {"step_count": step, "role": "deep_execution"}
                res = evaluate_pre_invocation(payload, workspace_dir=self.workspace_dir)
                self.assertEqual(res, {"injectSteps": []})

    def test_cadence_override_via_env_var(self) -> None:
        """AGYIS_ROLE_PINNING_CADENCE environment variable modifies re-anchor cadence."""
        os.environ["AGYIS_ROLE_PINNING_CADENCE"] = "15"
        self.assertEqual(get_role_pinning_cadence(), 15)

        # Step 10 is no longer a re-anchor turn under cadence 15
        res_10 = evaluate_pre_invocation(
            {"step_count": 10, "role": "deep_execution"},
            workspace_dir=self.workspace_dir,
        )
        self.assertEqual(res_10, {"injectSteps": []})

        # Step 15 triggers the re-anchor
        res_15 = evaluate_pre_invocation(
            {"step_count": 15, "role": "deep_execution"},
            workspace_dir=self.workspace_dir,
        )
        self.assertEqual(len(res_15.get("injectSteps", [])), 1)
        self.assertIn("CADENCE 15", res_15["injectSteps"][0]["ephemeralMessage"])


class TestNativeSlashCommandsBypass(unittest.TestCase):
    """Verifies native system slash commands bypass role injection."""

    def test_turn_zero_native_slash_commands_bypassed(self) -> None:
        """Turn 0 role pinning is bypassed when prompt starts with a native system slash command."""
        native_commands = [
            "/compact",
            "/plan refactor backend",
            "/boost optimize query",
            "/teamwork-preview",
            "/clear",
            "/reset",
            "/goal ship release",
            "<USER_REQUEST>\n/compact\n</USER_REQUEST>",
        ]

        for cmd in native_commands:
            with self.subTest(command=cmd):
                payload = {
                    "step_count": 0,
                    "prompt": cmd,
                    "role": "deep_execution",
                }
                res = evaluate_pre_invocation(payload)
                self.assertEqual(
                    res,
                    {"injectSteps": []},
                    f"Command '{cmd}' should have bypassed role injection at Turn 0",
                )

    def test_turn_ten_native_slash_commands_bypassed(self) -> None:
        """Turn 10 periodic re-anchor is bypassed for native slash commands."""
        payload = {
            "step_count": 10,
            "prompt": "/plan add new endpoint",
            "role": "deep_execution",
        }
        res = evaluate_pre_invocation(payload)
        self.assertEqual(res, {"injectSteps": []})

    def test_post_compaction_native_slash_commands_bypassed(self) -> None:
        """Post-compaction prompt with native slash command is bypassed."""
        payload = {
            "prompt": "/compact",
            "role": "flight_director",
        }
        res = evaluate_pre_invocation(payload)
        self.assertEqual(res, {"injectSteps": []})

    def test_modular_skills_are_not_bypassed(self) -> None:
        """Modular skills (/db-ops, /audio-ops) are NOT bypassed and receive role injection."""
        # Turn 0 with modular skill prompt receives systemMessage
        payload_0 = {
            "step_count": 0,
            "prompt": "/db-ops check connection pool",
            "role": "deep_execution",
        }
        res_0 = evaluate_pre_invocation(payload_0)
        self.assertEqual(len(res_0.get("injectSteps", [])), 1)
        self.assertIn("systemMessage", res_0["injectSteps"][0])

        # Turn 10 with modular skill prompt receives ephemeralMessage
        payload_10 = {
            "step_count": 10,
            "prompt": "/audio-ops status",
            "role": "deep_execution",
        }
        res_10 = evaluate_pre_invocation(payload_10)
        self.assertEqual(len(res_10.get("injectSteps", [])), 1)
        self.assertIn("ephemeralMessage", res_10["injectSteps"][0])


class TestSubSecondExecutionBenchmark(unittest.TestCase):
    """Asserts that role-pinning and stage-role evaluation meet the sub-second latency SLA (<0.20s)."""

    def test_role_pinning_sub_second_benchmark(self) -> None:
        """50 iterations of evaluate_pre_invocation must complete well under 0.20s."""
        t0 = time.perf_counter()
        for i in range(50):
            payload = {"step_count": i % 15, "role": "deep_execution"}
            res = evaluate_pre_invocation(payload)
            self.assertIsInstance(res, dict)
        elapsed = time.perf_counter() - t0

        self.assertLess(
            elapsed,
            0.20,
            f"50 evaluate_pre_invocation iterations took {elapsed:.4f}s (SLA: <0.20s)",
        )


if __name__ == "__main__":
    unittest.main()
