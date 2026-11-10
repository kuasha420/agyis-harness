# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Arafat Zahan (@kuasha420)
# Corporate Stewardship & Infrastructure: Purrfect Software Limited (PSL)
# Governed by: ICARO-42/b Ordinance (Company-Supported Personal IP Framework)

"""
Hermetic Unit and Benchmark Tests for Delegate Subagent Liveness Engine (Issue #78, ADR-025, Epic #74).
Verifies ACTIVE, STALE, PARKED, and DEAD state classifications, CLI integration, and sub-second SLA (<0.05s).
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import io
import json
import os
from pathlib import Path
import tempfile
import time
import unittest
from unittest.mock import patch

from harness.cli import build_parser
from harness.commands.subagents import cmd_subagents, format_liveness_table
from harness.commands.cockpit import _audit_flight_director_invariants
from harness.subagents.liveness import (
    SubagentLivenessStatus,
    probe_subagent_liveness,
)


class TestSubagentLivenessEngine(unittest.TestCase):
    """Hermetic unit tests for probe_subagent_liveness engine."""

    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.root = Path(self.temp_dir.name)
        self.workspace = self.root / "workspace"
        self.workspace.mkdir(parents=True, exist_ok=True)
        self.brain = self.root / "brain"
        self.brain.mkdir(parents=True, exist_ok=True)

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def _create_session(
        self,
        session_id: str,
        role: str,
        age_seconds: float,
        system_generated: bool = True,
    ) -> Path:
        sess_dir = self.brain / session_id
        if system_generated:
            log_dir = sess_dir / ".system_generated" / "logs"
            log_dir.mkdir(parents=True, exist_ok=True)
            t_path = log_dir / "transcript.jsonl"
        else:
            sess_dir.mkdir(parents=True, exist_ok=True)
            t_path = sess_dir / "transcript.jsonl"

        line1 = json.dumps({
            "conversation_id": session_id,
            "role": role,
            "content": f"You are {role} in ladder protocol.",
        })
        t_path.write_text(line1 + "\n", encoding="utf-8")

        # Set modification time
        target_mtime = time.time() - age_seconds
        os.utime(t_path, (target_mtime, target_mtime))
        os.utime(sess_dir, (target_mtime, target_mtime))
        return t_path

    def _create_teamwork_progress(
        self,
        agent_name: str,
        iso_timestamp: str,
        status: str = "IN_PROGRESS",
    ) -> Path:
        agent_dir = self.workspace / ".agents" / "teamwork" / agent_name
        agent_dir.mkdir(parents=True, exist_ok=True)
        prog_path = agent_dir / "progress.md"
        content = (
            f"# Progress for {agent_name}\n\n"
            f"- Status: {status}\n"
            f"- Last visited: {iso_timestamp}\n"
        )
        prog_path.write_text(content, encoding="utf-8")
        return prog_path

    def test_empty_directories(self) -> None:
        """Probe against empty brain and teamwork yields empty list."""
        statuses = probe_subagent_liveness(
            workspace_dir=self.workspace,
            brain_dir=self.brain,
        )
        self.assertEqual(statuses, [])

    def test_state_classifications_active_stale_dead(self) -> None:
        """Tests ACTIVE (<=300s), STALE (301-1800s), and DEAD (>1800s) default classifications."""
        self._create_session("sess-active-01", "agyis_builder", age_seconds=50)
        self._create_session("sess-stale-02", "agyis_reviewer", age_seconds=450)
        self._create_session("sess-dead-03", "agyis_investigator", age_seconds=2500)

        statuses = probe_subagent_liveness(
            workspace_dir=self.workspace,
            brain_dir=self.brain,
            stale_threshold=300,
            dead_threshold=1800,
        )

        status_by_id = {s.conversation_id: s for s in statuses}
        self.assertIn("sess-active-01", status_by_id)
        self.assertIn("sess-stale-02", status_by_id)
        self.assertIn("sess-dead-03", status_by_id)

        self.assertEqual(status_by_id["sess-active-01"].liveness_state, "ACTIVE")
        self.assertEqual(status_by_id["sess-active-01"].role, "agyis_builder")
        self.assertFalse(status_by_id["sess-active-01"].is_parked)

        self.assertEqual(status_by_id["sess-stale-02"].liveness_state, "STALE")
        self.assertEqual(status_by_id["sess-stale-02"].role, "agyis_reviewer")
        self.assertFalse(status_by_id["sess-stale-02"].is_parked)

        self.assertEqual(status_by_id["sess-dead-03"].liveness_state, "DEAD")
        self.assertEqual(status_by_id["sess-dead-03"].role, "agyis_investigator")
        self.assertFalse(status_by_id["sess-dead-03"].is_parked)

    def test_custom_thresholds(self) -> None:
        """Tests custom --stale-threshold and --dead-threshold overrides."""
        self._create_session("sess-custom-01", "agyis_builder", age_seconds=70)

        # Default 300s -> ACTIVE
        statuses_default = probe_subagent_liveness(
            workspace_dir=self.workspace,
            brain_dir=self.brain,
            stale_threshold=300,
            dead_threshold=1800,
        )
        self.assertEqual(statuses_default[0].liveness_state, "ACTIVE")

        # Custom stale_threshold=60s -> STALE
        statuses_custom = probe_subagent_liveness(
            workspace_dir=self.workspace,
            brain_dir=self.brain,
            stale_threshold=60,
            dead_threshold=600,
        )
        self.assertEqual(statuses_custom[0].liveness_state, "STALE")

        # Custom dead_threshold=65s -> DEAD
        statuses_dead = probe_subagent_liveness(
            workspace_dir=self.workspace,
            brain_dir=self.brain,
            stale_threshold=30,
            dead_threshold=65,
        )
        self.assertEqual(statuses_dead[0].liveness_state, "DEAD")

    def test_teamwork_progress_heartbeat(self) -> None:
        """Tests parsing Last visited ISO timestamp in teamwork progress.md."""
        now = time.time()
        active_iso = datetime.fromtimestamp(now - 40, tz=timezone.utc).isoformat().replace("+00:00", "Z")
        self._create_teamwork_progress("worker_alpha", active_iso)

        statuses = probe_subagent_liveness(
            workspace_dir=self.workspace,
            brain_dir=self.brain,
        )
        self.assertEqual(len(statuses), 1)
        st = statuses[0]
        self.assertEqual(st.conversation_id, "worker_alpha")
        self.assertEqual(st.liveness_state, "ACTIVE")
        self.assertIsNotNone(st.progress_file)
        self.assertTrue(st.progress_file.endswith("progress.md"))

    def test_parked_state_detection(self) -> None:
        """Tests PARKED detection via pause_gate.json, PARKED_STATE.md, and progress status."""
        # 1. Subagent with explicit PARKED status in progress.md
        now = time.time()
        active_iso = datetime.fromtimestamp(now - 10, tz=timezone.utc).isoformat().replace("+00:00", "Z")
        self._create_teamwork_progress("worker_parked", active_iso, status="PARKED")

        statuses = probe_subagent_liveness(
            workspace_dir=self.workspace,
            brain_dir=self.brain,
        )
        self.assertEqual(statuses[0].liveness_state, "PARKED")
        self.assertTrue(statuses[0].is_parked)

        # 2. Global pause gate in .agents/artifacts/pause_gate.json
        gate_dir = self.workspace / ".agents" / "artifacts"
        gate_dir.mkdir(parents=True, exist_ok=True)
        (gate_dir / "pause_gate.json").write_text(json.dumps({"status": "paused"}), encoding="utf-8")

        self._create_session("sess-running", "agyis_builder", age_seconds=10)
        statuses_paused = probe_subagent_liveness(
            workspace_dir=self.workspace,
            brain_dir=self.brain,
        )
        for s in statuses_paused:
            self.assertEqual(s.liveness_state, "PARKED")
            self.assertTrue(s.is_parked)


class TestSubagentLivenessCLI(unittest.TestCase):
    """Hermetic unit tests for CLI integration of 'agyis subagents --liveness'."""

    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.root = Path(self.temp_dir.name)
        self.workspace = self.root / "workspace"
        self.workspace.mkdir(parents=True, exist_ok=True)
        self.brain = self.root / "brain"
        self.brain.mkdir(parents=True, exist_ok=True)

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def test_cli_argument_parsing(self) -> None:
        """Verifies CLI argument parser recognizes --liveness, thresholds, and workspace."""
        parser = build_parser()
        args = parser.parse_args([
            "subagents",
            "--liveness",
            "--stale-threshold",
            "120",
            "--dead-threshold",
            "600",
            "-w",
            str(self.workspace),
            "--json",
        ])
        self.assertTrue(args.liveness)
        self.assertEqual(args.stale_threshold, 120)
        self.assertEqual(args.dead_threshold, 600)
        self.assertEqual(args.workspace, self.workspace)
        self.assertTrue(args.json)

    def test_cmd_subagents_liveness_json(self) -> None:
        """Verifies 'agyis subagents --liveness --json' outputs structured JSON schema."""
        sess_dir = self.brain / "sess-json-01" / ".system_generated" / "logs"
        sess_dir.mkdir(parents=True, exist_ok=True)
        t_path = sess_dir / "transcript.jsonl"
        t_path.write_text(
            json.dumps({"conversation_id": "sess-json-01", "role": "agyis_builder"}) + "\n",
            encoding="utf-8",
        )

        args = argparse.Namespace(
            subcommand="subagents",
            liveness=True,
            json=True,
            workspace=self.workspace,
            brain_dir=self.brain,
            stale_threshold=300,
            dead_threshold=1800,
        )

        out = io.StringIO()
        with patch("sys.stdout", out):
            code = cmd_subagents(args)

        self.assertEqual(code, 0)
        data = json.loads(out.getvalue())
        self.assertIsInstance(data, list)
        self.assertEqual(len(data), 1)

        item = data[0]
        expected_keys = {
            "conversation_id",
            "role",
            "last_heartbeat_iso",
            "heartbeat_age_seconds",
            "liveness_state",
            "progress_file",
            "is_parked",
        }
        self.assertTrue(expected_keys.issubset(set(item.keys())))
        self.assertEqual(item["conversation_id"], "sess-json-01")
        self.assertEqual(item["role"], "agyis_builder")
        self.assertEqual(item["liveness_state"], "ACTIVE")

    def test_format_liveness_table_and_badges(self) -> None:
        """Verifies ASCII table formatting and emoji status badges."""
        statuses = [
            SubagentLivenessStatus(
                conversation_id="conv-111122223333",
                role="agyis_builder",
                last_heartbeat_iso="2026-10-27T01:00:00Z",
                heartbeat_age_seconds=25.0,
                liveness_state="ACTIVE",
                progress_file=None,
                is_parked=False,
            ),
            SubagentLivenessStatus(
                conversation_id="conv-444455556666",
                role="agyis_reviewer",
                last_heartbeat_iso="2026-10-27T00:50:00Z",
                heartbeat_age_seconds=650.0,
                liveness_state="STALE",
                progress_file="/path/to/progress.md",
                is_parked=False,
            ),
            SubagentLivenessStatus(
                conversation_id="conv-777788889999",
                role="agyis_custodian",
                last_heartbeat_iso="2026-10-27T00:00:00Z",
                heartbeat_age_seconds=3700.0,
                liveness_state="DEAD",
                progress_file=None,
                is_parked=False,
            ),
            SubagentLivenessStatus(
                conversation_id="conv-000011112222",
                role="agyis_coordinator",
                last_heartbeat_iso="2026-10-27T00:55:00Z",
                heartbeat_age_seconds=300.0,
                liveness_state="PARKED",
                progress_file=None,
                is_parked=True,
            ),
        ]

        table = format_liveness_table(statuses)
        self.assertIn("Conversation ID", table)
        self.assertIn("Heartbeat Age", table)
        self.assertIn("Liveness State", table)
        self.assertIn("Progress Source", table)

        # Check badges
        self.assertIn("🟢 ACTIVE", table)
        self.assertIn("🟡 STALE", table)
        self.assertIn("🔴 DEAD", table)
        self.assertIn("⏸️ PARKED", table)

        # Check formatted age
        self.assertIn("25s ago", table)
        self.assertIn("10m 50s ago", table)
        self.assertIn("1h 1m ago", table)


class TestLivenessCockpitDirector(unittest.TestCase):
    """Verifies Cockpit Flight Director Invariant 5 detects DEAD subagents."""

    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.root = Path(self.temp_dir.name)
        self.workspace = self.root / "workspace"
        self.workspace.mkdir(parents=True, exist_ok=True)
        self.brain = self.root / "brain"
        self.brain.mkdir(parents=True, exist_ok=True)
        # Create checkpoint file so Invariant 4 passes
        cp_dir = self.workspace / ".agents" / "artifacts"
        cp_dir.mkdir(parents=True, exist_ok=True)
        (cp_dir / "compaction_checkpoint_latest.md").write_text("# Checkpoint", encoding="utf-8")
        self.env_patch = patch.dict(os.environ, {"ANTIGRAVITY_BRAIN_DIR": str(self.brain)})
        self.env_patch.start()

    def tearDown(self) -> None:
        self.env_patch.stop()
        self.temp_dir.cleanup()

    def test_invariant_5_fails_on_dead_subagent(self) -> None:
        """When a delegate subagent is DEAD, cockpit invariant audit fails unless allow_dirty is True."""
        dead_prog = self.workspace / ".agents" / "teamwork" / "dead_worker" / "progress.md"
        dead_prog.parent.mkdir(parents=True, exist_ok=True)
        dead_prog.write_text("- Last visited: 2026-01-01T00:00:00Z\n", encoding="utf-8")

        overall_pass, results = _audit_flight_director_invariants(self.workspace, allow_dirty=False)
        inv5 = next(r for r in results if r["invariant"] == "Subagent Cognitive Health")

        self.assertFalse(inv5["passed"])
        self.assertIn("dead", inv5["details"])
        self.assertTrue(any("DEAD: dead_worker" in v for v in inv5["violations"]))

        # When allow_dirty=True, passed is True
        overall_dirty, results_dirty = _audit_flight_director_invariants(self.workspace, allow_dirty=True)
        inv5_dirty = next(r for r in results_dirty if r["invariant"] == "Subagent Cognitive Health")
        self.assertTrue(inv5_dirty["passed"])


class TestSubagentLivenessBenchmark(unittest.TestCase):
    """Verifies sub-second SLA (<0.05s) across 25 subagent records."""

    def test_benchmark_sla(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            ws = root / "workspace"
            ws.mkdir()
            brain = root / "brain"
            brain.mkdir()

            now = time.time()
            for i in range(25):
                s_dir = brain / f"session-{i:03d}" / ".system_generated" / "logs"
                s_dir.mkdir(parents=True)
                t_file = s_dir / "transcript.jsonl"
                t_file.write_text(
                    json.dumps({"conversation_id": f"session-{i:03d}", "role": f"worker_{i}"}) + "\n"
                )
                mtime = now - (i * 100)
                os.utime(t_file, (mtime, mtime))

            t0 = time.perf_counter()
            statuses = probe_subagent_liveness(workspace_dir=ws, brain_dir=brain)
            elapsed = time.perf_counter() - t0

            self.assertEqual(len(statuses), 25)
            self.assertLess(
                elapsed,
                0.05,
                f"Liveness probing exceeded 0.05s SLA: {elapsed:.4f}s >= 0.05s",
            )


class TestSubagentLivenessScopingAndTTL(unittest.TestCase):
    """Hermetic unit tests for active conversation scoping, --all flag, and 24h pause TTL (Issue #95)."""

    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.root = Path(self.temp_dir.name)
        self.workspace = self.root / "workspace"
        self.workspace.mkdir(parents=True, exist_ok=True)
        self.brain = self.root / "brain"
        self.brain.mkdir(parents=True, exist_ok=True)

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def test_active_conversation_scoping(self) -> None:
        """Only child subagents of the active conversation are shown when show_all=False."""
        parent_id = "parent-sess-001"
        child1_id = "child-builder-001"
        child2_id = "child-reviewer-002"
        unrelated_id = "unrelated-investigator-003"

        # Create parent session that invoked child1 and child2
        parent_dir = self.brain / parent_id / ".system_generated" / "logs"
        parent_dir.mkdir(parents=True, exist_ok=True)
        parent_t = parent_dir / "transcript.jsonl"
        parent_t.write_text(
            json.dumps({"conversation_id": parent_id, "role": "agyis_coordinator"}) + "\n"
            + json.dumps({
                "type": "MODEL",
                "tool_calls": [
                    {"name": "invoke_subagent", "args": {"TypeName": "agyis_builder", "conversationId": child1_id}},
                    {"name": "invoke_subagent", "args": {"TypeName": "agyis_reviewer", "conversationId": child2_id}},
                ],
            }) + "\n",
            encoding="utf-8",
        )

        # Create child 1 session
        c1_dir = self.brain / child1_id / ".system_generated" / "logs"
        c1_dir.mkdir(parents=True, exist_ok=True)
        (c1_dir / "transcript.jsonl").write_text(
            json.dumps({"conversation_id": child1_id, "role": "agyis_builder", "parent": parent_id}) + "\n",
            encoding="utf-8",
        )

        # Create child 2 session
        c2_dir = self.brain / child2_id / ".system_generated" / "logs"
        c2_dir.mkdir(parents=True, exist_ok=True)
        (c2_dir / "transcript.jsonl").write_text(
            json.dumps({"conversation_id": child2_id, "role": "agyis_reviewer", "parent": parent_id}) + "\n",
            encoding="utf-8",
        )

        # Create unrelated session
        un_dir = self.brain / unrelated_id / ".system_generated" / "logs"
        un_dir.mkdir(parents=True, exist_ok=True)
        (un_dir / "transcript.jsonl").write_text(
            json.dumps({"conversation_id": unrelated_id, "role": "agyis_investigator"}) + "\n",
            encoding="utf-8",
        )

        # Create teamwork for child1 and unrelated worker
        now = time.time()
        iso_str = datetime.fromtimestamp(now - 30, tz=timezone.utc).isoformat().replace("+00:00", "Z")
        tw_c1 = self.workspace / ".agents" / "teamwork" / child1_id
        tw_c1.mkdir(parents=True, exist_ok=True)
        (tw_c1 / "progress.md").write_text(f"- Last visited: {iso_str}\n", encoding="utf-8")

        tw_un = self.workspace / ".agents" / "teamwork" / "unrelated_worker"
        tw_un.mkdir(parents=True, exist_ok=True)
        (tw_un / "progress.md").write_text(f"- Last visited: {iso_str}\n", encoding="utf-8")

        # Probe with active conversation scoping (show_all=False)
        statuses = probe_subagent_liveness(
            workspace_dir=self.workspace,
            brain_dir=self.brain,
            conv_id=parent_id,
            show_all=False,
        )

        status_ids = {s.conversation_id for s in statuses}
        self.assertIn(child1_id, status_ids)
        self.assertIn(child2_id, status_ids)
        self.assertNotIn(unrelated_id, status_ids)
        self.assertNotIn("unrelated_worker", status_ids)
        self.assertNotIn(parent_id, status_ids)
        self.assertEqual(len(statuses), 2)

    def test_show_all_flag_displays_cross_session(self) -> None:
        """When show_all=True, subagents from all sessions and teamwork are displayed."""
        parent_id = "parent-sess-001"
        child1_id = "child-builder-001"
        unrelated_id = "unrelated-investigator-003"

        p_dir = self.brain / parent_id / ".system_generated" / "logs"
        p_dir.mkdir(parents=True, exist_ok=True)
        (p_dir / "transcript.jsonl").write_text(
            json.dumps({"conversation_id": parent_id, "role": "agyis_coordinator"}) + "\n"
            + json.dumps({"tool_calls": [{"name": "invoke_subagent", "args": {"conversationId": child1_id}}]}) + "\n",
            encoding="utf-8",
        )

        c1_dir = self.brain / child1_id / ".system_generated" / "logs"
        c1_dir.mkdir(parents=True, exist_ok=True)
        (c1_dir / "transcript.jsonl").write_text(
            json.dumps({"conversation_id": child1_id, "role": "agyis_builder"}) + "\n",
            encoding="utf-8",
        )

        un_dir = self.brain / unrelated_id / ".system_generated" / "logs"
        un_dir.mkdir(parents=True, exist_ok=True)
        (un_dir / "transcript.jsonl").write_text(
            json.dumps({"conversation_id": unrelated_id, "role": "agyis_investigator"}) + "\n",
            encoding="utf-8",
        )

        statuses_all = probe_subagent_liveness(
            workspace_dir=self.workspace,
            brain_dir=self.brain,
            conv_id=parent_id,
            show_all=True,
        )

        status_ids_all = {s.conversation_id for s in statuses_all}
        self.assertIn(child1_id, status_ids_all)
        self.assertIn(unrelated_id, status_ids_all)

    def test_parked_state_ttl_expiration(self) -> None:
        """PARKED_STATE.md older than 24 hours (86400s) is ignored, preventing global pause trap."""
        artifacts_dir = self.workspace / ".agents" / "artifacts"
        artifacts_dir.mkdir(parents=True, exist_ok=True)
        parked_file = artifacts_dir / "PARKED_STATE.md"
        parked_file.write_text("# Parked State\n\nstatus: paused\n", encoding="utf-8")

        # Set mtime to 25 hours ago (expired)
        expired_mtime = time.time() - 90000
        os.utime(parked_file, (expired_mtime, expired_mtime))

        sess_dir = self.brain / "sess-active-fresh" / ".system_generated" / "logs"
        sess_dir.mkdir(parents=True, exist_ok=True)
        (sess_dir / "transcript.jsonl").write_text(
            json.dumps({"conversation_id": "sess-active-fresh", "role": "agyis_builder"}) + "\n",
            encoding="utf-8",
        )

        statuses = probe_subagent_liveness(
            workspace_dir=self.workspace,
            brain_dir=self.brain,
            show_all=True,
        )
        self.assertEqual(len(statuses), 1)
        self.assertEqual(statuses[0].liveness_state, "ACTIVE")
        self.assertFalse(statuses[0].is_parked)

        # Now touch mtime to 1 hour ago (valid pause gate)
        valid_mtime = time.time() - 3600
        os.utime(parked_file, (valid_mtime, valid_mtime))

        statuses_paused = probe_subagent_liveness(
            workspace_dir=self.workspace,
            brain_dir=self.brain,
            show_all=True,
        )
        self.assertEqual(len(statuses_paused), 1)
        self.assertEqual(statuses_paused[0].liveness_state, "PARKED")
        self.assertTrue(statuses_paused[0].is_parked)

    def test_cli_all_and_session_args(self) -> None:
        """Verifies CLI accepts --all and --session arguments and filters output accordingly."""
        parser = build_parser()
        args = parser.parse_args(["subagents", "--liveness", "--all", "--session", "conv-test-123"])
        self.assertTrue(args.all)
        self.assertEqual(args.session, "conv-test-123")


class TestSubagentCompletedState(unittest.TestCase):
    """Hermetic unit tests for COMPLETED state classification and Cockpit Invariant 5 scoping."""

    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.root = Path(self.temp_dir.name)
        self.workspace = self.root / "workspace"
        self.workspace.mkdir(parents=True, exist_ok=True)
        self.brain = self.root / "brain"
        self.brain.mkdir(parents=True, exist_ok=True)

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def _write_transcript(self, session_id: str, entries: list[dict], age_seconds: float) -> Path:
        log_dir = self.brain / session_id / ".system_generated" / "logs"
        log_dir.mkdir(parents=True, exist_ok=True)
        t_path = log_dir / "transcript.jsonl"
        t_path.write_text("\n".join(json.dumps(e) for e in entries) + "\n", encoding="utf-8")
        mtime = time.time() - age_seconds
        os.utime(t_path, (mtime, mtime))
        os.utime(self.brain / session_id, (mtime, mtime))
        return t_path

    def test_completed_transcript_tail_vs_crashed_and_midflight_tails(self) -> None:
        """Finished PLANNER_RESPONSE+DONE without tool_calls -> COMPLETED; crashed/midflight -> STALE/DEAD."""
        # 1. Clean completion (even with old mtime > 1800s and empty tool_calls list)
        self._write_transcript(
            "sess-done-01",
            [
                {"conversation_id": "sess-done-01", "role": "agyis_builder"},
                {"type": "PLANNER_RESPONSE", "status": "DONE", "tool_calls": []},
            ],
            age_seconds=3600,
        )
        # 2. Mid-flight PLANNER_RESPONSE with pending tool_calls -> DEAD
        self._write_transcript(
            "sess-pending-tc-02",
            [
                {"conversation_id": "sess-pending-tc-02", "role": "agyis_builder"},
                {"type": "PLANNER_RESPONSE", "status": "DONE", "tool_calls": [{"name": "run_command"}]},
            ],
            age_seconds=3600,
        )
        # 3. Mid-flight PLANNER_RESPONSE with camelCase toolCalls -> STALE
        self._write_transcript(
            "sess-pending-camel-03",
            [
                {"conversation_id": "sess-pending-camel-03", "role": "agyis_reviewer"},
                {"type": "PLANNER_RESPONSE", "status": "DONE", "toolCalls": [{"name": "view_file"}]},
            ],
            age_seconds=600,
        )
        # 4. Crashed GENERIC ERROR -> DEAD
        self._write_transcript(
            "sess-gen-err-04",
            [
                {"conversation_id": "sess-gen-err-04", "role": "agyis_investigator"},
                {"type": "GENERIC", "status": "ERROR"},
            ],
            age_seconds=3600,
        )
        # 5. Mid-loop GENERIC DONE -> STALE
        self._write_transcript(
            "sess-gen-done-05",
            [
                {"conversation_id": "sess-gen-done-05", "role": "agyis_custodian"},
                {"type": "GENERIC", "status": "DONE"},
            ],
            age_seconds=600,
        )
        # 6. SYSTEM_MESSAGE tail -> DEAD
        self._write_transcript(
            "sess-sys-msg-06",
            [
                {"conversation_id": "sess-sys-msg-06", "role": "agyis_auditor"},
                {"type": "SYSTEM_MESSAGE", "status": "DONE"},
            ],
            age_seconds=3600,
        )

        statuses = probe_subagent_liveness(workspace_dir=self.workspace, brain_dir=self.brain)
        by_id = {s.conversation_id: s for s in statuses}

        self.assertEqual(by_id["sess-done-01"].liveness_state, "COMPLETED")
        self.assertFalse(by_id["sess-done-01"].is_parked)
        self.assertEqual(by_id["sess-pending-tc-02"].liveness_state, "DEAD")
        self.assertEqual(by_id["sess-pending-camel-03"].liveness_state, "STALE")
        self.assertEqual(by_id["sess-gen-err-04"].liveness_state, "DEAD")
        self.assertEqual(by_id["sess-gen-done-05"].liveness_state, "STALE")
        self.assertEqual(by_id["sess-sys-msg-06"].liveness_state, "DEAD")

    def test_progress_md_complete_marker_and_precedence_and_badge(self) -> None:
        """progress.md Status: Complete -> COMPLETED; explicit PARKED > COMPLETED > global pause."""
        tw = self.workspace / ".agents" / "teamwork"
        (tw / "worker_done").mkdir(parents=True)
        (tw / "worker_done" / "progress.md").write_text(
            "- Status: Complete\n- Last visited: 2026-01-01T00:00:00Z\n",
            encoding="utf-8",
        )
        (tw / "worker_explicit_parked").mkdir(parents=True)
        (tw / "worker_explicit_parked" / "progress.md").write_text(
            "- Status: Complete\nPARKED by operator\n- Last visited: 2026-01-01T00:00:00Z\n",
            encoding="utf-8",
        )
        (tw / "worker_in_progress").mkdir(parents=True)
        (tw / "worker_in_progress" / "progress.md").write_text(
            "- Status: IN_PROGRESS\n- Last visited: 2026-01-01T00:00:00Z\n",
            encoding="utf-8",
        )

        # Global pause gate should NOT override COMPLETED unless explicitly parked
        art = self.workspace / ".agents" / "artifacts"
        art.mkdir(parents=True, exist_ok=True)
        (art / "pause_gate.json").write_text(json.dumps({"status": "paused"}), encoding="utf-8")

        statuses = probe_subagent_liveness(workspace_dir=self.workspace, brain_dir=self.brain)
        by_id = {s.conversation_id: s for s in statuses}

        self.assertEqual(by_id["worker_done"].liveness_state, "COMPLETED")
        self.assertFalse(by_id["worker_done"].is_parked)
        self.assertEqual(by_id["worker_explicit_parked"].liveness_state, "PARKED")
        self.assertTrue(by_id["worker_explicit_parked"].is_parked)
        self.assertEqual(by_id["worker_in_progress"].liveness_state, "PARKED")

        table = format_liveness_table([by_id["worker_done"]])
        self.assertIn("✅ COMPLETED", table)

    def test_cockpit_invariants_ignore_completed_and_active_conv_sessions(self) -> None:
        """Cockpit Invariant 5 passes with COMPLETED >80-step brain sessions and fails on DEAD workers."""
        cp_dir = self.workspace / ".agents" / "artifacts"
        cp_dir.mkdir(parents=True, exist_ok=True)
        (cp_dir / "compaction_checkpoint_latest.md").write_text("# Checkpoint", encoding="utf-8")

        # Create active orchestrator session with >80 lines (RED_ALERT if not excluded)
        active_id = "active-coord-999"
        completed_id = "hist-completed-888"
        active_lines = (
            [{"conversation_id": active_id, "role": "agyis_coordinator"}]
            + [
                {
                    "type": "MODEL",
                    "tool_calls": [
                        {"name": "invoke_subagent", "args": {"TypeName": "agyis_builder", "conversationId": completed_id}}
                    ],
                }
            ]
            + [{"type": "GENERIC", "content": f"turn {i}"} for i in range(90)]
        )
        self._write_transcript(active_id, active_lines, age_seconds=10)

        # Create historical COMPLETED session <4h with >80 lines (RED_ALERT if not excluded)
        comp_lines = [{"conversation_id": completed_id, "role": "agyis_builder"}] + [
            {"type": "GENERIC", "content": f"step {i}"} for i in range(85)
        ] + [{"type": "PLANNER_RESPONSE", "status": "DONE"}]
        self._write_transcript(completed_id, comp_lines, age_seconds=300)

        with patch.dict(
            os.environ,
            {
                "ANTIGRAVITY_BRAIN_DIR": str(self.brain),
                "ANTIGRAVITY_CONVERSATION_ID": active_id,
            },
        ):
            _, results = _audit_flight_director_invariants(self.workspace, allow_dirty=False)
            inv5 = next(r for r in results if r["invariant"] == "Subagent Cognitive Health")
            self.assertTrue(inv5["passed"], f"Unexpected Invariant 5 failure: {inv5}")
            self.assertIn("0 active subagents", inv5["details"])

            # Adding a DEAD teamwork worker linked to active session still fails Invariant 5
            dead_prog = self.workspace / ".agents" / "teamwork" / "dead_worker" / "progress.md"
            dead_prog.parent.mkdir(parents=True, exist_ok=True)
            dead_prog.write_text(
                f"Parent: {active_id}\n- Last visited: 2026-01-01T00:00:00Z\n",
                encoding="utf-8",
            )
            _, results_dead = _audit_flight_director_invariants(self.workspace, allow_dirty=False)
            inv5_dead = next(r for r in results_dead if r["invariant"] == "Subagent Cognitive Health")
            self.assertFalse(inv5_dead["passed"])
            self.assertTrue(any("DEAD: dead_worker" in v for v in inv5_dead["violations"]))

    def test_empty_and_malformed_trailing_transcripts_not_completed(self) -> None:
        """0-byte empty transcripts and malformed trailing JSON lines must not classify as COMPLETED."""
        # 1. 0-byte empty transcripts (aged >1800s -> DEAD; aged 600s -> STALE)
        for sid, age in (
            ("sess-empty-dead", 3600),
            ("sess-empty-stale", 600),
        ):
            log_dir = self.brain / sid / ".system_generated" / "logs"
            log_dir.mkdir(parents=True, exist_ok=True)
            t_path = log_dir / "transcript.jsonl"
            t_path.write_text("", encoding="utf-8")
            mtime = time.time() - age
            os.utime(t_path, (mtime, mtime))
            os.utime(self.brain / sid, (mtime, mtime))

        # 2. Malformed trailing JSON line transcripts (aged >1800s -> DEAD; aged 600s -> STALE)
        for sid, age, tail in (
            ("sess-malformed-dead", 3600, "{truncated json"),
            ("sess-malformed-stale", 600, '{"type": "PLANNER_RESPONSE", "status":'),
        ):
            log_dir = self.brain / sid / ".system_generated" / "logs"
            log_dir.mkdir(parents=True, exist_ok=True)
            t_path = log_dir / "transcript.jsonl"
            t_path.write_text(
                json.dumps({"conversation_id": sid, "role": "agyis_builder"}) + "\n" + tail + "\n",
                encoding="utf-8",
            )
            mtime = time.time() - age
            os.utime(t_path, (mtime, mtime))
            os.utime(self.brain / sid, (mtime, mtime))

        statuses = probe_subagent_liveness(workspace_dir=self.workspace, brain_dir=self.brain)
        by_id = {s.conversation_id: s for s in statuses}

        self.assertEqual(by_id["sess-empty-dead"].liveness_state, "DEAD")
        self.assertEqual(by_id["sess-empty-stale"].liveness_state, "STALE")
        self.assertEqual(by_id["sess-malformed-dead"].liveness_state, "DEAD")
        self.assertEqual(by_id["sess-malformed-stale"].liveness_state, "STALE")

    def test_cockpit_invariants_exclude_stale_active_conv_from_dead_subagents(self) -> None:
        """_audit_flight_director_invariants excludes active_conv even when >1800s old without PLANNER_RESPONSE+DONE."""
        cp_dir = self.workspace / ".agents" / "artifacts"
        cp_dir.mkdir(parents=True, exist_ok=True)
        (cp_dir / "compaction_checkpoint_latest.md").write_text("# Checkpoint", encoding="utf-8")

        active_id = "active-coord-stale-777"
        self._write_transcript(
            active_id,
            [
                {"conversation_id": active_id, "role": "agyis_coordinator"},
                {"type": "GENERIC", "content": "long running parent without DONE tail"},
            ],
            age_seconds=3600,
        )

        # Confirm probe_subagent_liveness solo fallback classifies aged active_id as DEAD
        solo_probe = probe_subagent_liveness(
            workspace_dir=self.workspace,
            brain_dir=self.brain,
            conv_id=active_id,
        )
        self.assertEqual(len(solo_probe), 1)
        self.assertEqual(solo_probe[0].conversation_id, active_id)
        self.assertEqual(solo_probe[0].liveness_state, "DEAD")

        with patch.dict(
            os.environ,
            {
                "ANTIGRAVITY_BRAIN_DIR": str(self.brain),
                "ANTIGRAVITY_CONVERSATION_ID": active_id,
            },
        ):
            _, results = _audit_flight_director_invariants(self.workspace, allow_dirty=False)
            inv5 = next(r for r in results if r["invariant"] == "Subagent Cognitive Health")
            self.assertTrue(inv5["passed"], f"active_conv should be excluded from dead_subagents: {inv5}")
            self.assertEqual(inv5["violations"], [])

            # Adding an actual DEAD child/worker still fails Invariant 5 while excluding active_conv
            dead_prog = self.workspace / ".agents" / "teamwork" / "dead_worker" / "progress.md"
            dead_prog.parent.mkdir(parents=True, exist_ok=True)
            dead_prog.write_text(
                f"Parent: {active_id}\n- Last visited: 2026-01-01T00:00:00Z\n",
                encoding="utf-8",
            )
            _, results_dead = _audit_flight_director_invariants(self.workspace, allow_dirty=False)
            inv5_dead = next(r for r in results_dead if r["invariant"] == "Subagent Cognitive Health")
            self.assertFalse(inv5_dead["passed"])
            self.assertTrue(any("DEAD: dead_worker" in v for v in inv5_dead["violations"]))
            self.assertFalse(any(active_id[:8] in v for v in inv5_dead["violations"]))



if __name__ == "__main__":
    unittest.main()

