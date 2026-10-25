# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Arafat Zahan (@kuasha420)
# Corporate Stewardship & Infrastructure: Purrfect Software Limited (PSL)
# Governed by: ICARO-42/b Ordinance (Company-Supported Personal IP Framework)

"""
Hermetic unit tests for Subagent Ladder Heartbeat crons and telemetry (Issue #84).

Validates:
- Heartbeat schema validation (strict key sets, valid stages, valid statuses, ISO-8601 timestamps).
- Atomic arming, pulsing, disarming, and clearing of ladder_heartbeat.json.
- Staleness detection (>300s timeout, non-terminal transition to status='stale').
- Subagents CLI table formatting and JSON ladder stage attribution.
- Status CLI command rendering of the Active Subagent Ladder Stage panel.
- Sub-second benchmark SLA (<0.20s).
"""

from __future__ import annotations

import argparse
from datetime import datetime, timedelta, timezone
import io
import json
from pathlib import Path
import tempfile
import time
import unittest
from unittest.mock import patch

from harness.commands.status import cmd_status
from harness.commands.subagents import cmd_subagents, format_subagents_table
from harness.subagents import (
    LADDER_HEARTBEAT_PATH,
    SubagentContextStatus,
    VALID_STAGES,
    VALID_STATUSES,
    arm_stage_heartbeat,
    clear_stage_heartbeat,
    disarm_stage_heartbeat,
    pulse_stage_heartbeat,
    read_stage_heartbeat,
    validate_heartbeat_schema,
)


class TestLadderHeartbeat(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.tmp = Path(self.temp_dir.name)

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def test_schema_validation_valid(self) -> None:
        """Valid heartbeat dictionary passes schema validation."""
        valid_payload = {
            "event": "ladder_heartbeat",
            "protocol_version": "2026.1",
            "task_id": "ISSUE-84",
            "stage": "executioner",
            "active_agent_id": "agyis_builder",
            "subagent_role": "Stage 1: Executioner (agyis_builder)",
            "step_count": 12,
            "elapsed_s": 45.2,
            "status": "in_progress",
            "last_action": "python3 -m unittest ...",
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
        self.assertTrue(validate_heartbeat_schema(valid_payload))

    def test_schema_validation_invalid_cases(self) -> None:
        """Invalid types, missing keys, invalid stages, or bad timestamps fail validation."""
        base = {
            "event": "ladder_heartbeat",
            "protocol_version": "2026.1",
            "task_id": "ISSUE-84",
            "stage": "executioner",
            "active_agent_id": "agyis_builder",
            "subagent_role": "executioner",
            "step_count": 0,
            "elapsed_s": 0.0,
            "status": "dispatched",
            "last_action": "init",
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

        # Non-dict
        self.assertFalse(validate_heartbeat_schema("not a dict"))
        self.assertFalse(validate_heartbeat_schema(None))

        # Missing required key
        incomplete = dict(base)
        del incomplete["stage"]
        self.assertFalse(validate_heartbeat_schema(incomplete))

        # Invalid stage
        bad_stage = dict(base, stage="unknown_stage")
        self.assertFalse(validate_heartbeat_schema(bad_stage))

        # Invalid status
        bad_status = dict(base, status="invalid_status")
        self.assertFalse(validate_heartbeat_schema(bad_status))

        # Invalid step_count
        bad_steps = dict(base, step_count=-1)
        self.assertFalse(validate_heartbeat_schema(bad_steps))
        bad_steps_bool = dict(base, step_count=True)
        self.assertFalse(validate_heartbeat_schema(bad_steps_bool))

        # Invalid elapsed_s
        bad_elapsed = dict(base, elapsed_s=-5.0)
        self.assertFalse(validate_heartbeat_schema(bad_elapsed))
        bad_elapsed_bool = dict(base, elapsed_s=False)
        self.assertFalse(validate_heartbeat_schema(bad_elapsed_bool))

        # Invalid timestamp
        bad_ts = dict(base, timestamp="not-a-timestamp")
        self.assertFalse(validate_heartbeat_schema(bad_ts))

    def test_arm_stage_heartbeat_lifecycle(self) -> None:
        """arm_stage_heartbeat atomically materializes ladder_heartbeat.json."""
        target_path = arm_stage_heartbeat(
            task_id="ISSUE-84",
            stage="executioner",
            agent_id="agyis_builder",
            role_title="Stage 1: Executioner (agyis_builder)",
            workspace_dir=self.tmp,
        )
        self.assertTrue(target_path.is_file())
        self.assertEqual(target_path, self.tmp / LADDER_HEARTBEAT_PATH)

        data = read_stage_heartbeat(workspace_dir=self.tmp)
        self.assertIsNotNone(data)
        self.assertEqual(data["task_id"], "ISSUE-84")
        self.assertEqual(data["stage"], "executioner")
        self.assertEqual(data["active_agent_id"], "agyis_builder")
        self.assertEqual(data["subagent_role"], "Stage 1: Executioner (agyis_builder)")
        self.assertEqual(data["step_count"], 0)
        self.assertEqual(data["elapsed_s"], 0.0)
        self.assertEqual(data["status"], "dispatched")
        self.assertFalse(data["is_stale"])

        # Error cases
        with self.assertRaises(ValueError):
            arm_stage_heartbeat("ISSUE-84", "invalid_stage", "agent", "role", self.tmp)
        with self.assertRaises(ValueError):
            arm_stage_heartbeat("", "executioner", "agent", "role", self.tmp)
        with self.assertRaises(ValueError):
            arm_stage_heartbeat("ISSUE-84", "executioner", "", "role", self.tmp)
        with self.assertRaises(ValueError):
            arm_stage_heartbeat("ISSUE-84", "executioner", "agent", "", self.tmp)

    def test_pulse_stage_heartbeat(self) -> None:
        """pulse_stage_heartbeat updates step count, action, and calculates elapsed time."""
        arm_stage_heartbeat(
            task_id="ISSUE-84",
            stage="executioner",
            agent_id="agyis_builder",
            role_title="Stage 1: Executioner",
            workspace_dir=self.tmp,
        )

        success = pulse_stage_heartbeat(
            step_count=10,
            last_action="python3 -m unittest tests/test_ladder_heartbeat.py",
            status="in_progress",
            workspace_dir=self.tmp,
        )
        self.assertTrue(success)

        data = read_stage_heartbeat(workspace_dir=self.tmp)
        self.assertIsNotNone(data)
        self.assertEqual(data["step_count"], 10)
        self.assertEqual(data["last_action"], "python3 -m unittest tests/test_ladder_heartbeat.py")
        self.assertEqual(data["status"], "in_progress")
        self.assertGreaterEqual(data["elapsed_s"], 0.0)

        # Pulse on non-existent workspace returns False
        empty_tmp = tempfile.TemporaryDirectory()
        try:
            self.assertFalse(pulse_stage_heartbeat(1, "act", workspace_dir=empty_tmp.name))
        finally:
            empty_tmp.cleanup()

        # Step count as boolean is rejected defensively
        self.assertFalse(pulse_stage_heartbeat(step_count=True, last_action="bool test", workspace_dir=self.tmp))
        self.assertFalse(pulse_stage_heartbeat(step_count=False, last_action="bool test", workspace_dir=self.tmp))

    def test_disarm_stage_heartbeat(self) -> None:
        """disarm_stage_heartbeat marks terminal status and finalizes telemetry."""
        arm_stage_heartbeat(
            task_id="ISSUE-84",
            stage="auditor",
            agent_id="agyis_auditor",
            role_title="Stage 4: Victory Auditor",
            workspace_dir=self.tmp,
        )
        pulse_stage_heartbeat(step_count=5, last_action="audit passed", workspace_dir=self.tmp)

        success = disarm_stage_heartbeat(status="complete", workspace_dir=self.tmp)
        self.assertTrue(success)

        data = read_stage_heartbeat(workspace_dir=self.tmp)
        self.assertIsNotNone(data)
        self.assertEqual(data["status"], "complete")
        self.assertIn("Disarmed stage with status: complete", data["last_action"])

    def test_read_staleness_detection(self) -> None:
        """read_stage_heartbeat marks is_stale=True and status='stale' when elapsed time > 300s."""
        target_path = arm_stage_heartbeat(
            task_id="ISSUE-84",
            stage="hammer",
            agent_id="agyis_reviewer",
            role_title="Stage 2: The Hammer",
            workspace_dir=self.tmp,
        )

        # Simulate heartbeat 400 seconds in the past
        old_time = datetime.now(timezone.utc) - timedelta(seconds=400)
        raw = json.loads(target_path.read_text(encoding="utf-8"))
        raw["timestamp"] = old_time.isoformat()
        target_path.write_text(json.dumps(raw), encoding="utf-8")

        data = read_stage_heartbeat(workspace_dir=self.tmp, stale_timeout_s=300.0)
        self.assertIsNotNone(data)
        self.assertTrue(data["is_stale"])
        self.assertEqual(data["status"], "stale")
        self.assertGreaterEqual(data["heartbeat_age_s"], 399.0)

        # Terminal status (complete) does not get overridden to 'stale'
        raw["status"] = "complete"
        target_path.write_text(json.dumps(raw), encoding="utf-8")
        data_complete = read_stage_heartbeat(workspace_dir=self.tmp, stale_timeout_s=300.0)
        self.assertIsNotNone(data_complete)
        self.assertTrue(data_complete["is_stale"])
        self.assertEqual(data_complete["status"], "complete")

    def test_clear_stage_heartbeat(self) -> None:
        """clear_stage_heartbeat safely removes heartbeat file."""
        arm_stage_heartbeat("ISSUE-84", "custodian", "agyis_custodian", "role", self.tmp)
        self.assertTrue((self.tmp / LADDER_HEARTBEAT_PATH).is_file())

        self.assertTrue(clear_stage_heartbeat(self.tmp))
        self.assertFalse((self.tmp / LADDER_HEARTBEAT_PATH).exists())
        self.assertFalse(clear_stage_heartbeat(self.tmp))

    def test_format_subagents_table_with_heartbeat(self) -> None:
        """format_subagents_table annotates subagent role with active ladder stage badge."""
        mock_status = SubagentContextStatus(
            conversation_id="conv-builder-1234",
            role="agyis_builder",
            step_count=18,
            token_count=14500,
            health_zone="HEALTHY",
            recommendation="REUSE",
            latency_ms=1.1,
        )

        heartbeat = {
            "event": "ladder_heartbeat",
            "protocol_version": "2026.1",
            "task_id": "ISSUE-84",
            "stage": "executioner",
            "active_agent_id": "conv-builder-1234",
            "subagent_role": "Stage 1: Executioner",
            "step_count": 18,
            "elapsed_s": 80.0,
            "status": "in_progress",
            "last_action": "running local tests",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "is_stale": False,
        }

        table_str = format_subagents_table([mock_status], heartbeat=heartbeat)
        self.assertIn("Executioner", table_str)
        self.assertIn("conv-builder", table_str)
        self.assertIn("HEALTHY", table_str)

    def test_cmd_subagents_json_and_text_ladder_attribution(self) -> None:
        """cmd_subagents annotates text output and appends ladder_stage to JSON."""
        mock_status = SubagentContextStatus(
            conversation_id="conv-test-99",
            role="agyis_builder",
            step_count=5,
            token_count=3200,
            health_zone="HEALTHY",
            recommendation="REUSE",
            latency_ms=0.8,
        )

        heartbeat = {
            "event": "ladder_heartbeat",
            "protocol_version": "2026.1",
            "task_id": "ISSUE-84",
            "stage": "executioner",
            "active_agent_id": "conv-test-99",
            "subagent_role": "Stage 1: Executioner",
            "step_count": 5,
            "elapsed_s": 25.0,
            "status": "in_progress",
            "last_action": "editing code",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "is_stale": False,
        }

        with patch("harness.subagents.list_active_subagent_statuses", return_value=[mock_status]), \
             patch("harness.subagents.heartbeat.read_stage_heartbeat", return_value=heartbeat):

            # Text mode
            with patch("sys.stdout", new_callable=io.StringIO) as out_text:
                args = argparse.Namespace(json=False, brain_dir=None)
                ret = cmd_subagents(args)
                self.assertEqual(ret, 0)
                text = out_text.getvalue()
                self.assertIn("Active Ladder Stage: Executioner [IN_PROGRESS]", text)
                self.assertIn("Executioner", text)

            # JSON mode
            with patch("sys.stdout", new_callable=io.StringIO) as out_json:
                args_json = argparse.Namespace(json=True, brain_dir=None)
                ret = cmd_subagents(args_json)
                self.assertEqual(ret, 0)
                data = json.loads(out_json.getvalue().strip())
                self.assertEqual(len(data), 1)
                self.assertEqual(data[0]["ladder_stage"], "executioner")

    def test_cmd_subagents_with_workspace_dir_passthrough(self) -> None:
        """cmd_subagents with workspace_dir reads heartbeat from specified directory."""
        arm_stage_heartbeat(
            task_id="ISSUE-84",
            stage="custodian",
            agent_id="conv-cust-1",
            role_title="Stage 3: Workspace Custodian",
            workspace_dir=self.tmp,
        )
        pulse_stage_heartbeat(
            step_count=7,
            last_action="auditing staging",
            status="in_progress",
            workspace_dir=self.tmp,
        )

        mock_status = SubagentContextStatus(
            conversation_id="conv-cust-1",
            role="agyis_custodian",
            step_count=7,
            token_count=4500,
            health_zone="HEALTHY",
            recommendation="REUSE",
            latency_ms=0.9,
        )

        with patch("harness.subagents.list_active_subagent_statuses", return_value=[mock_status]):
            # Verify workspace_dir is used to read heartbeat
            with patch("sys.stdout", new_callable=io.StringIO) as out_text:
                args = argparse.Namespace(json=False, brain_dir=None, workspace_dir=self.tmp)
                ret = cmd_subagents(args)
                self.assertEqual(ret, 0)
                text = out_text.getvalue()
                self.assertIn("Active Ladder Stage: Custodian [IN_PROGRESS]", text)
                self.assertIn("Custodian", text)

            with patch("sys.stdout", new_callable=io.StringIO) as out_json:
                args_json = argparse.Namespace(json=True, brain_dir=None, workspace_dir=self.tmp)
                ret = cmd_subagents(args_json)
                self.assertEqual(ret, 0)
                data = json.loads(out_json.getvalue().strip())
                self.assertEqual(len(data), 1)
                self.assertEqual(data[0]["ladder_stage"], "custodian")

    def test_cmd_status_renders_active_ladder_stage_panel(self) -> None:
        """cmd_status renders dedicated Active Subagent Ladder Stage panel when heartbeat is active."""
        arm_stage_heartbeat(
            task_id="ISSUE-84",
            stage="executioner",
            agent_id="agyis_builder",
            role_title="Stage 1: Executioner (agyis_builder)",
            workspace_dir=self.tmp,
        )
        pulse_stage_heartbeat(
            step_count=32,
            last_action="python3 -m unittest ...",
            status="in_progress",
            workspace_dir=self.tmp,
        )

        # Force elapsed_s to 142.5 for exact format test
        target_path = self.tmp / LADDER_HEARTBEAT_PATH
        raw = json.loads(target_path.read_text(encoding="utf-8"))
        raw["elapsed_s"] = 142.5
        target_path.write_text(json.dumps(raw), encoding="utf-8")

        args = argparse.Namespace(workspace_dir=self.tmp)
        with patch("sys.stdout", new_callable=io.StringIO) as mock_out:
            ret = cmd_status(args)
            self.assertEqual(ret, 0)
            output = mock_out.getvalue()

            self.assertIn("Active Subagent Ladder Stage:", output)
            self.assertIn("Stage:         Stage 1: Executioner (agyis_builder)", output)
            self.assertIn("Task ID:       ISSUE-84", output)
            self.assertIn("Step Count:    32 steps", output)
            self.assertIn("Elapsed Time:  142.5s (2m 22s)", output)
            self.assertIn("Last Action:   python3 -m unittest ...", output)
            self.assertIn("Status:        🟢 IN_PROGRESS (Heartbeat", output)

    def test_benchmark_sla(self) -> None:
        """Entire test suite runs well under the 0.20s SLA (<200ms)."""
        start = time.perf_counter()
        arm_stage_heartbeat("SLA-01", "executioner", "builder", "role", self.tmp)
        pulse_stage_heartbeat(10, "action", "in_progress", self.tmp)
        read_stage_heartbeat(self.tmp)
        disarm_stage_heartbeat("complete", self.tmp)
        clear_stage_heartbeat(self.tmp)
        duration = time.perf_counter() - start
        self.assertLess(duration, 0.05, f"Heartbeat operations took {duration:.4f}s, expected <0.05s")


if __name__ == "__main__":
    unittest.main()
