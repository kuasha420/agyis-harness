# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Arafat Zahan (@kuasha420)
# Corporate Stewardship & Infrastructure: Purrfect Software Limited (PSL)
# Governed by: ICARO-42/b Ordinance (Company-Supported Personal IP Framework)

"""
Hermetic unit and benchmark tests for Automated Pre-Compaction Checkpoint Generator (ADR-031 / Issue #77).
"""

from __future__ import annotations

import io
import json
import os
from pathlib import Path
import tempfile
import time
import unittest
from unittest.mock import patch

from harness.delivery import (
    ArtifactLink,
    CheckpointResult,
    GitState,
    PlanState,
    PlanStatus,
    SubagentEntry,
    SubagentState,
    assemble_compaction_checkpoint,
    collect_active_artifacts,
    collect_active_subagents,
    generate_compaction_checkpoint,
    inspect_git_state,
    parse_implementation_plan,
)


class TestCompactionCheckpoint(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.ws = Path(self.temp_dir.name)

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def test_delivery_exports(self) -> None:
        """Assert all required classes, aliases, and functions are exported in harness.delivery."""
        self.assertIs(SubagentState, SubagentEntry)
        self.assertIs(PlanState, PlanStatus)
        self.assertTrue(callable(inspect_git_state))
        self.assertTrue(callable(collect_active_subagents))
        self.assertTrue(callable(collect_active_artifacts))
        self.assertTrue(callable(parse_implementation_plan))
        self.assertTrue(callable(generate_compaction_checkpoint))
        self.assertTrue(callable(assemble_compaction_checkpoint))

    def test_parse_plan_with_explicit_path(self) -> None:
        """Parse implementation plan by providing an explicit plan path."""
        custom_plan = self.ws / "docs" / "custom_plan.md"
        custom_plan.parent.mkdir(parents=True, exist_ok=True)
        custom_plan.write_text(
            "# Custom Engine Plan\n\n"
            "### Phase 1: Engine Core\n"
            "- [x] Design dataclasses\n"
            "- [x] Implement inspect_git_state\n\n"
            "### Phase 2: CLI Integration\n"
            "- [x] Add flag\n"
            "- [ ] Wire command\n\n"
            "### Phase 3: Documentation\n"
            "- [ ] Write release notes\n",
            encoding="utf-8",
        )

        status = parse_implementation_plan(self.ws, plan_path=custom_plan)
        self.assertEqual(status.plan_title, "Custom Engine Plan")
        self.assertEqual(status.total_tasks, 5)
        self.assertEqual(status.completed_tasks, 3)
        self.assertEqual(status.pending_tasks, 2)
        self.assertEqual(status.current_phase, "Phase 2: CLI Integration")
        self.assertEqual(status.next_pending_phase, "Phase 2: CLI Integration")
        self.assertEqual(status.next_pending_task, "Wire command")
        self.assertEqual(len(status.phases_summary), 3)
        self.assertEqual(status.phases_summary[0]["status"], "COMPLETED")
        self.assertEqual(status.phases_summary[1]["status"], "IN_PROGRESS")
        self.assertEqual(status.phases_summary[2]["status"], "PENDING")

    def test_parse_plan_candidate_discovery(self) -> None:
        """Verify candidate discovery picks implementation_plan_issue_77.md over implementation_plan.md."""
        art_dir = self.ws / ".agents" / "artifacts"
        art_dir.mkdir(parents=True, exist_ok=True)

        plan_77 = art_dir / "implementation_plan_issue_77.md"
        plan_77.write_text(
            "# Issue 77 Plan\n\n"
            "## Phase 1: Core\n"
            "- [ ] Implement checkpoint\n",
            encoding="utf-8",
        )

        plan_generic = art_dir / "implementation_plan.md"
        plan_generic.write_text(
            "# Generic Plan\n\n"
            "## Phase 1: Other\n"
            "- [x] Done\n",
            encoding="utf-8",
        )

        status = parse_implementation_plan(self.ws)
        self.assertEqual(status.plan_title, "Issue 77 Plan")
        self.assertEqual(status.total_tasks, 1)
        self.assertEqual(status.completed_tasks, 0)
        self.assertEqual(status.pending_tasks, 1)
        self.assertEqual(status.next_pending_task, "Implement checkpoint")

    def test_parse_plan_fallback_without_phases(self) -> None:
        """Parse plan that contains tasks without markdown phase headers."""
        art_dir = self.ws / ".agents" / "artifacts"
        art_dir.mkdir(parents=True, exist_ok=True)
        plan_file = art_dir / "plan.md"
        plan_file.write_text(
            "# Flat Task List\n\n"
            "- [x] First step done\n"
            "- [ ] Second step pending\n"
            "- [ ] Third step pending\n",
            encoding="utf-8",
        )

        status = parse_implementation_plan(self.ws)
        self.assertEqual(status.plan_title, "Flat Task List")
        self.assertEqual(status.total_tasks, 3)
        self.assertEqual(status.completed_tasks, 1)
        self.assertEqual(status.pending_tasks, 2)
        self.assertEqual(status.next_pending_task, "Second step pending")

    def test_parse_plan_nonexistent(self) -> None:
        """Nonexistent plan returns empty PlanStatus without error."""
        status = parse_implementation_plan(self.ws)
        self.assertIsNone(status.plan_path)
        self.assertEqual(status.total_tasks, 0)
        self.assertEqual(status.completed_tasks, 0)
        self.assertEqual(status.pending_tasks, 0)
        self.assertIsNone(status.next_pending_task)

    def test_collect_active_artifacts(self) -> None:
        """Collect markdown artifacts and extract headers and sizes."""
        art_dir = self.ws / ".agents" / "artifacts"
        art_dir.mkdir(parents=True, exist_ok=True)

        (art_dir / "report_1.md").write_text("# Executive Audit Report\n\nDetails...", encoding="utf-8")
        (art_dir / "spec_2.md").write_text("No header here\nJust text", encoding="utf-8")
        (art_dir / "ignored.json").write_text("{}", encoding="utf-8")

        artifacts = collect_active_artifacts(self.ws)
        self.assertEqual(len(artifacts), 2)
        by_name = {a.filename: a for a in artifacts}
        self.assertIn("report_1.md", by_name)
        self.assertEqual(by_name["report_1.md"].title, "Executive Audit Report")
        self.assertGreater(by_name["report_1.md"].size_bytes, 0)

        self.assertIn("spec_2.md", by_name)
        self.assertEqual(by_name["spec_2.md"].title, "Spec 2")

    def test_inspect_git_state_non_git_dir(self) -> None:
        """Inspect git state on empty directory without crashing."""
        git_state = inspect_git_state(self.ws)
        self.assertEqual(git_state.branch, "detached")
        self.assertEqual(git_state.commit_hash, "unknown")
        self.assertEqual(git_state.commit_short, "unknown")
        self.assertFalse(git_state.is_dirty)
        self.assertEqual(git_state.modified_files, [])
        self.assertEqual(git_state.untracked_files, [])

    def test_inspect_git_state_real_repo(self) -> None:
        """Inspect git state on the active repository root."""
        repo_root = Path(__file__).resolve().parent.parent
        git_state = inspect_git_state(repo_root)
        self.assertTrue(len(git_state.branch) > 0)
        self.assertEqual(len(git_state.commit_hash), 40)
        self.assertGreaterEqual(len(git_state.commit_short), 7)
        self.assertIsInstance(git_state.is_dirty, bool)

    def test_collect_active_subagents_with_brain_dir(self) -> None:
        """Collect active subagent statuses from mock brain session directory."""
        brain_dir = self.ws / "mock_brain"
        session_id = "test-agent-sess-42"
        sess_dir = brain_dir / session_id
        logs_dir = sess_dir / ".system_generated" / "logs"
        logs_dir.mkdir(parents=True, exist_ok=True)

        # Write transcript with role and steps
        transcript = logs_dir / "transcript.jsonl"
        lines = [
            json.dumps({"role": "user", "content": "You are agyis_builder. Build component."}),
            json.dumps({"role": "assistant", "content": "Working on it."}),
            json.dumps({"role": "user", "content": "Continue."}),
            json.dumps({"role": "assistant", "content": "Done."}),
        ]
        transcript.write_text("\n".join(lines) + "\n", encoding="utf-8")

        subagents = collect_active_subagents(self.ws, brain_dir=brain_dir)
        self.assertEqual(len(subagents), 1)
        sub = subagents[0]
        self.assertEqual(sub.conversation_id, session_id)
        self.assertEqual(sub.health_zone, "HEALTHY")
        self.assertEqual(sub.recommendation, "REUSE")
        self.assertGreaterEqual(sub.step_count, 1)

    def test_generate_compaction_checkpoint_output_and_unpacking(self) -> None:
        """Verify checkpoint generation, tuple unpacking, and 6-section structure."""
        art_dir = self.ws / ".agents" / "artifacts"
        art_dir.mkdir(parents=True, exist_ok=True)
        (art_dir / "implementation_plan.md").write_text(
            "# Test Implementation Plan\n\n"
            "### Phase 1: Delivery Core\n"
            "- [x] Dataclasses\n"
            "- [ ] Compaction checkpoint\n",
            encoding="utf-8",
        )

        t0 = time.perf_counter()
        res = generate_compaction_checkpoint(
            workspace_dir=self.ws,
            session_id="coord-session-99",
            orchestrator_role="agyis_coordinator",
            trigger_tokens=231_000,
        )
        elapsed_test_ms = (time.perf_counter() - t0) * 1000.0

        # Sub-50ms benchmark invariant
        self.assertLess(res.elapsed_ms, 50.0, f"Checkpoint latency {res.elapsed_ms:.2f}ms exceeds 50ms")

        # Tuple unpacking test: (content, out_path)
        content, out_path = res
        self.assertIsInstance(content, str)
        self.assertEqual(out_path, res.output_path)
        self.assertTrue(out_path.is_file())
        self.assertTrue(res.latest_path.is_file())

        # Assert all 6 sections are present
        self.assertIn("# 🧭 Compaction & Succession Checkpoint", content)
        self.assertIn("## 1. Executive Succession Mandate & Handoff Summary", content)
        self.assertIn("## 2. Git Working Tree & Repository State", content)
        self.assertIn("## 3. Active Implementation Plan & Milestone Progression", content)
        self.assertIn("## 4. Active Subagent Roster & Liveness Matrix", content)
        self.assertIn("## 5. Active Workspace Artifact Bridge", content)
        self.assertIn("## 6. Successor Wake-Up Checklist", content)

        # Assert specific values rendered
        self.assertIn("coord-session-99", content)
        self.assertIn("agyis_coordinator", content)
        self.assertIn("231,000", content)
        self.assertIn("Compaction checkpoint", content)
        self.assertIn("1 / 2 Tasks (50.0%)", content)

    def test_custom_output_path(self) -> None:
        """Verify passing a custom output path writes correctly."""
        custom_out = self.ws / "reports" / "my_checkpoint.md"
        res = generate_compaction_checkpoint(
            workspace_dir=self.ws,
            output_path=custom_out,
        )
        self.assertEqual(res.output_path, custom_out)
        self.assertTrue(custom_out.is_file())
        self.assertTrue((custom_out.parent / "compaction_checkpoint_latest.md").is_file())

    def test_assemble_alias_compatibility(self) -> None:
        """Verify assemble_compaction_checkpoint alias is compatible with prototype callers."""
        content, out_path = assemble_compaction_checkpoint(
            workspace_dir=self.ws,
            session_id="legacy-session",
            orchestrator_role="agyis_architect",
            trigger_tokens=220_000,
        )
        self.assertIsInstance(content, str)
        self.assertTrue(out_path.is_file())
        self.assertIn("legacy-session", content)
        self.assertIn("agyis_architect", content)

    def test_inspect_git_state_unstaged_file_parsing(self) -> None:
        """Assert unstaged modified files preserve leading character in filename."""
        import subprocess

        # Initialize temporary git repository
        subprocess.run(["git", "init"], cwd=str(self.ws), capture_output=True, check=True)
        subprocess.run(
            ["git", "config", "user.name", "Tester"],
            cwd=str(self.ws),
            capture_output=True,
            check=True,
        )
        subprocess.run(
            ["git", "config", "user.email", "tester@example.com"],
            cwd=str(self.ws),
            capture_output=True,
            check=True,
        )

        test_file = self.ws / "path_test.py"
        test_file.write_text("initial content\n", encoding="utf-8")
        subprocess.run(["git", "add", "path_test.py"], cwd=str(self.ws), capture_output=True, check=True)
        subprocess.run(
            ["git", "commit", "-m", "init"],
            cwd=str(self.ws),
            capture_output=True,
            check=True,
        )

        # Make an unstaged edit (porcelain outputs ' M path_test.py')
        test_file.write_text("unstaged change\n", encoding="utf-8")

        git_state = inspect_git_state(self.ws)
        self.assertTrue(git_state.is_dirty)
        self.assertIn("path_test.py", git_state.modified_files)
        self.assertNotIn("ath_test.py", git_state.modified_files)

    def test_subagent_full_uuid_preservation(self) -> None:
        """Verify that Section 4 rendered markdown preserves full 36-character UUIDs."""
        brain_dir = self.ws / "uuid_brain"
        full_uuid = "3a73c443-5ccd-44a7-bcce-5c604f92c0f2"
        sess_dir = brain_dir / full_uuid
        logs_dir = sess_dir / ".system_generated" / "logs"
        logs_dir.mkdir(parents=True, exist_ok=True)
        (logs_dir / "transcript.jsonl").write_text(
            json.dumps({"role": "user", "content": "You are agyis_builder. Build component."})
            + "\n",
            encoding="utf-8",
        )

        res = generate_compaction_checkpoint(
            workspace_dir=self.ws,
            brain_dir=brain_dir,
        )
        self.assertIn(full_uuid, res.content)
        self.assertIn(f"`{full_uuid}`", res.content)
        self.assertNotIn(f"`{full_uuid[:12]}` |", res.content)

    def test_empty_plan_percentage_and_task_fallback(self) -> None:
        """Verify 0.0% progress for empty plans and fallback task assignment to current phase."""
        art_dir = self.ws / ".agents" / "artifacts"
        art_dir.mkdir(parents=True, exist_ok=True)
        plan_file = art_dir / "implementation_plan.md"
        plan_file.write_text(
            "# Unstarted Plan\n\n"
            "### Phase 1: Planning\n",
            encoding="utf-8",
        )

        status = parse_implementation_plan(self.ws)
        self.assertEqual(status.total_tasks, 0)
        self.assertEqual(status.next_pending_task, "Execute Phase 1: Planning")

        res = generate_compaction_checkpoint(workspace_dir=self.ws)
        self.assertIn("0 / 0 Tasks (0.0%)", res.content)

    def test_standard_list_markers(self) -> None:
        """Verify checkbox detection across -, *, and + list markers."""
        art_dir = self.ws / ".agents" / "artifacts"
        art_dir.mkdir(parents=True, exist_ok=True)
        plan_file = art_dir / "implementation_plan.md"
        plan_file.write_text(
            "# Mixed Marker Plan\n\n"
            "### Phase 1: Star Marker\n"
            "* [x] Done with star\n"
            "* [ ] Pending with star\n\n"
            "### Phase 2: Plus Marker\n"
            "+ [x] Done with plus\n"
            "+ [ ] Pending with plus\n",
            encoding="utf-8",
        )

        status = parse_implementation_plan(self.ws)
        self.assertEqual(status.total_tasks, 4)
        self.assertEqual(status.completed_tasks, 2)
        self.assertEqual(status.pending_tasks, 2)
        self.assertEqual(status.next_pending_task, "Pending with star")


class TestCheckpointCLI(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.ws = Path(self.temp_dir.name)

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    @patch("sys.stdout", new_callable=io.StringIO)
    def test_cli_checkpoint_generate_human(self, mock_stdout: Any) -> None:
        from harness.cli import main as cli_main

        ret = cli_main(["checkpoint", "generate", "--workspace", str(self.ws)])
        self.assertEqual(ret, 0)
        out = mock_stdout.getvalue()
        self.assertIn("✔ Compaction Checkpoint Generated", out)
        self.assertIn("Artifact:", out)
        self.assertIn("Latest:", out)
        self.assertIn("Latency:", out)

    @patch("sys.stdout", new_callable=io.StringIO)
    def test_cli_checkpoint_generate_json(self, mock_stdout: Any) -> None:
        from harness.cli import main as cli_main

        ret = cli_main(["checkpoint", "generate", "--workspace", str(self.ws), "--json"])
        self.assertEqual(ret, 0)
        data = json.loads(mock_stdout.getvalue())
        self.assertEqual(data["status"], "ok")
        self.assertIn("output_path", data)
        self.assertIn("latest_path", data)
        self.assertIn("elapsed_ms", data)
        self.assertIn("content_bytes", data)
        self.assertTrue(Path(data["latest_path"]).is_file())

    @patch("sys.stdout", new_callable=io.StringIO)
    def test_cli_checkpoint_default_action_generate(self, mock_stdout: Any) -> None:
        from harness.cli import main as cli_main

        ret = cli_main(["checkpoint", "--workspace", str(self.ws), "--json"])
        self.assertEqual(ret, 0)
        data = json.loads(mock_stdout.getvalue())
        self.assertEqual(data["status"], "ok")
        self.assertTrue(Path(data["latest_path"]).is_file())

    @patch("sys.stdout", new_callable=io.StringIO)
    def test_cli_checkpoint_verify_missing(self, mock_stdout: Any) -> None:
        from harness.cli import main as cli_main

        ret = cli_main(["checkpoint", "verify", "--workspace", str(self.ws), "--json"])
        self.assertEqual(ret, 1)
        data = json.loads(mock_stdout.getvalue())
        self.assertEqual(data["status"], "missing")
        self.assertFalse(data["valid"])
        self.assertIsNone(data["checkpoint_path"])

    @patch("sys.stdout", new_callable=io.StringIO)
    def test_cli_checkpoint_verify_fresh(self, mock_stdout: Any) -> None:
        from harness.cli import main as cli_main

        generate_compaction_checkpoint(self.ws)
        ret = cli_main(
            ["checkpoint", "verify", "--workspace", str(self.ws), "--max-age-mins", "10", "--json"]
        )
        self.assertEqual(ret, 0)
        data = json.loads(mock_stdout.getvalue())
        self.assertEqual(data["status"], "ok")
        self.assertTrue(data["valid"])
        self.assertIsNotNone(data["checkpoint_path"])

    @patch("sys.stdout", new_callable=io.StringIO)
    def test_cli_checkpoint_verify_stale(self, mock_stdout: Any) -> None:
        from harness.cli import main as cli_main

        res = generate_compaction_checkpoint(self.ws)
        stale_time = time.time() - 7200.0  # 2 hours old
        os.utime(res.latest_path, (stale_time, stale_time))

        ret = cli_main(
            ["checkpoint", "verify", "--workspace", str(self.ws), "--max-age-mins", "30", "--json"]
        )
        self.assertEqual(ret, 1)
        data = json.loads(mock_stdout.getvalue())
        self.assertEqual(data["status"], "stale")
        self.assertFalse(data["valid"])

    @patch("sys.stdout", new_callable=io.StringIO)
    def test_cli_checkpoint_status_json(self, mock_stdout: Any) -> None:
        from harness.cli import main as cli_main

        generate_compaction_checkpoint(self.ws)
        ret = cli_main(["checkpoint", "status", "--workspace", str(self.ws), "--json"])
        self.assertEqual(ret, 0)
        data = json.loads(mock_stdout.getvalue())
        self.assertIn("tokens", data)
        self.assertIn("subagents", data)
        self.assertIn("git", data)
        self.assertIn("checkpoint", data)
        self.assertTrue(data["checkpoint"]["present"])

    @patch("sys.stdout", new_callable=io.StringIO)
    def test_cli_checkpoint_status_human(self, mock_stdout: Any) -> None:
        from harness.cli import main as cli_main

        ret = cli_main(["checkpoint", "status", "--workspace", str(self.ws)])
        self.assertEqual(ret, 0)
        out = mock_stdout.getvalue()
        self.assertIn("Agyis Compaction & Checkpoint Status", out)
        self.assertIn("Git Working Tree:", out)
        self.assertIn("Active Subagents:", out)

    @patch("sys.stdout", new_callable=io.StringIO)
    def test_cli_benchmark_latency(self, mock_stdout: Any) -> None:
        """Assert CLI invocation completes within sub-second benchmark (<50ms)."""
        from harness.cli import main as cli_main

        t0 = time.perf_counter()
        ret = cli_main(["checkpoint", "--workspace", str(self.ws), "--json"])
        elapsed_ms = (time.perf_counter() - t0) * 1000.0

        self.assertEqual(ret, 0)
        self.assertLess(elapsed_ms, 50.0, f"CLI latency {elapsed_ms:.2f}ms exceeds 50ms benchmark")


if __name__ == "__main__":
    unittest.main()

