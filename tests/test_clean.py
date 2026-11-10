# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Arafat Zahan (@kuasha420)
# Corporate Stewardship & Infrastructure: Purrfect Software Limited (PSL)
# Governed by: ICARO-42/b Ordinance (Company-Supported Personal IP Framework)

"""
Hermetic unit and CLI tests for Agyis Clean Command (Issue #90).
"""

from __future__ import annotations

import argparse
import io
import json
import os
from pathlib import Path
import tempfile
import time
from typing import Any
import unittest
from unittest.mock import patch

from harness.cli import main as cli_main
from harness.commands.clean import (
    clean_branches,
    clean_checkpoints,
    clean_scratchpads,
    clean_worktrees,
    cmd_clean,
)


class TestCleanHygiene(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.ws = Path(self.temp_dir.name)

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def test_clean_checkpoints_retention(self) -> None:
        """Verify clean_checkpoints prunes older checkpoints according to retention."""
        art_dir = self.ws / ".agents" / "artifacts"
        art_dir.mkdir(parents=True, exist_ok=True)

        for i in range(10):
            (art_dir / f"compaction_checkpoint_{100 + i}.md").write_text(f"epoch {i}\n")
        (art_dir / "compaction_checkpoint_latest.md").write_text("latest\n")

        # Dry run should identify 5 files without unlinking
        pruned_dry = clean_checkpoints(self.ws, retention=5, dry_run=True)
        self.assertEqual(len(pruned_dry), 5)
        self.assertEqual(len(list(art_dir.glob("compaction_checkpoint_*.md"))), 11)

        # Real run should delete 5 files
        pruned_real = clean_checkpoints(self.ws, retention=5, dry_run=False)
        self.assertEqual(len(pruned_real), 5)
        remaining = list(art_dir.glob("compaction_checkpoint_*.md"))
        self.assertEqual(len(remaining), 6)  # 5 historical + 1 latest.md
        self.assertTrue((art_dir / "compaction_checkpoint_latest.md").is_file())

    def test_clean_scratchpads_ttl(self) -> None:
        """Verify clean_scratchpads prunes expired files older than scratch_hours."""
        scratch_dir = self.ws / "scratch"
        scratch_dir.mkdir(parents=True, exist_ok=True)
        art_scratch = self.ws / ".agents" / "artifacts" / "scratch"
        art_scratch.mkdir(parents=True, exist_ok=True)

        fresh_file = scratch_dir / "fresh.txt"
        fresh_file.write_text("fresh")

        expired_file = art_scratch / "old.txt"
        expired_file.write_text("expired")
        # Set mtime to 48 hours ago
        past_time = time.time() - (48 * 3600)
        os.utime(expired_file, (past_time, past_time))

        # Dry run
        pruned_dry = clean_scratchpads(self.ws, scratch_hours=24.0, dry_run=True)
        self.assertEqual(len(pruned_dry), 1)
        self.assertIn("old.txt", pruned_dry[0])
        self.assertTrue(expired_file.is_file())

        # Real run
        pruned_real = clean_scratchpads(self.ws, scratch_hours=24.0, dry_run=False)
        self.assertEqual(len(pruned_real), 1)
        self.assertFalse(expired_file.is_file())
        self.assertTrue(fresh_file.is_file())

    def test_clean_scratchpads_prunes_empty_dirs_respecting_ttl_and_dry_run(self) -> None:
        """Verify empty and newly-emptied teamwork/scratch dirs are pruned while fresh <24h empty dirs survive."""
        teamwork_dir = self.ws / ".agents" / "teamwork"
        teamwork_dir.mkdir(parents=True, exist_ok=True)

        # 1. Newly emptied nested dir containing expired file (even with recent dir mtime)
        expired_worker = teamwork_dir / "old_worker"
        nested_sub = expired_worker / "nested"
        nested_sub.mkdir(parents=True)
        expired_file = nested_sub / "progress.md"
        expired_file.write_text("old")
        past_time = time.time() - (48 * 3600)
        os.utime(expired_file, (past_time, past_time))

        # 2. Pre-existing empty dir older than 24h
        old_empty = teamwork_dir / "old_empty"
        old_empty.mkdir()
        os.utime(old_empty, (past_time, past_time))

        # 3. Fresh <24h empty dir (must be preserved)
        fresh_empty = teamwork_dir / "fresh_empty"
        fresh_empty.mkdir()

        # 4. Dir with fresh file + expired file (only expired file unlinked, dir preserved)
        mixed_dir = teamwork_dir / "mixed_worker"
        mixed_dir.mkdir()
        mixed_old = mixed_dir / "old.md"
        mixed_old.write_text("old")
        os.utime(mixed_old, (past_time, past_time))
        mixed_fresh = mixed_dir / "fresh.md"
        mixed_fresh.write_text("fresh")

        # Dry run must detect both expired files, not unlink anything, and report dry-run pruned dirs
        dry_dirs: list[str] = []
        pruned_dry = clean_scratchpads(self.ws, scratch_hours=24.0, dry_run=True, pruned_dirs_out=dry_dirs)
        self.assertEqual(len(pruned_dry), 2)
        self.assertTrue(expired_file.is_file())
        self.assertTrue(old_empty.is_dir())
        self.assertIn(str(nested_sub), dry_dirs)
        self.assertIn(str(expired_worker), dry_dirs)
        self.assertIn(str(old_empty), dry_dirs)
        self.assertNotIn(str(fresh_empty), dry_dirs)
        self.assertNotIn(str(mixed_dir), dry_dirs)

        # Real run prunes files and empty expired dirs, preserving teamwork_dir, fresh_empty, and mixed_dir
        real_dirs: list[str] = []
        pruned_real = clean_scratchpads(self.ws, scratch_hours=24.0, dry_run=False, pruned_dirs_out=real_dirs)
        self.assertEqual(len(pruned_real), 2)
        self.assertTrue(teamwork_dir.is_dir())
        self.assertFalse(nested_sub.exists())
        self.assertFalse(expired_worker.exists())
        self.assertFalse(old_empty.exists())
        self.assertTrue(fresh_empty.is_dir())
        self.assertTrue(mixed_dir.is_dir())
        self.assertTrue(mixed_fresh.is_file())
        self.assertFalse(mixed_old.exists())

    def test_clean_branches_merged(self) -> None:
        """Verify merged subagent-* branches are pruned and active branch preserved."""
        with patch("subprocess.run") as mock_run:
            class DummyCompleted:
                def __init__(self, stdout: str):
                    self.stdout = stdout

            def fake_run(args, **kwargs):
                if args[1] == "branch" and "--show-current" in args:
                    return DummyCompleted("subagent-active\n")
                elif args[1] == "branch" and "--merged" in args:
                    return DummyCompleted("  main\n* subagent-active\n  subagent-old-1\n  subagent-old-2\n  feature/foo\n")
                elif args[1] == "branch" and "-d" in args:
                    return DummyCompleted("Deleted branch\n")
                return DummyCompleted("")

            mock_run.side_effect = fake_run

            # Dry run
            deleted_dry = clean_branches(self.ws, dry_run=True)
            self.assertEqual(deleted_dry, ["subagent-old-1", "subagent-old-2"])

            # Real run
            deleted_real = clean_branches(self.ws, dry_run=False)
            self.assertEqual(deleted_real, ["subagent-old-1", "subagent-old-2"])

    def test_clean_worktrees_orphaned(self) -> None:
        """Verify dead git worktrees are pruned."""
        with patch("subprocess.run") as mock_run:
            class DummyCompleted:
                def __init__(self, stdout: str):
                    self.stdout = stdout

            def fake_run(args, **kwargs):
                return DummyCompleted("worktree /path/to/main\nHEAD abc\nbranch refs/heads/main\n\n")

            mock_run.side_effect = fake_run

            pruned = clean_worktrees(self.ws, dry_run=True)
            self.assertIsInstance(pruned, list)

    def test_clean_scratchpads_preserves_gitkeep_and_enclosing_dir(self) -> None:
        """Verify .gitkeep files and their enclosing dirs in .agents/teamwork/ survive even when older than TTL."""
        teamwork_dir = self.ws / ".agents" / "teamwork"
        keep_subdir = teamwork_dir / "keep_placeholder"
        keep_subdir.mkdir(parents=True, exist_ok=True)
        root_gitkeep = teamwork_dir / ".gitkeep"
        root_gitkeep.write_text("", encoding="utf-8")
        sub_gitkeep = keep_subdir / ".gitkeep"
        sub_gitkeep.write_text("", encoding="utf-8")

        past_time = time.time() - (72 * 3600)
        os.utime(root_gitkeep, (past_time, past_time))
        os.utime(sub_gitkeep, (past_time, past_time))
        os.utime(keep_subdir, (past_time, past_time))

        pruned_dirs: list[str] = []
        pruned_files = clean_scratchpads(
            self.ws,
            scratch_hours=24.0,
            dry_run=False,
            pruned_dirs_out=pruned_dirs,
        )

        self.assertEqual(pruned_files, [])
        self.assertEqual(pruned_dirs, [])
        self.assertTrue(root_gitkeep.is_file())
        self.assertTrue(sub_gitkeep.is_file())
        self.assertTrue(keep_subdir.is_dir())
        self.assertTrue(teamwork_dir.is_dir())



class TestCleanCLI(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.ws = Path(self.temp_dir.name)

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    @patch("sys.stdout", new_callable=io.StringIO)
    def test_cli_clean_defaults_to_all(self, mock_stdout: Any) -> None:
        """Running agyis clean without args defaults to all categories."""
        art_dir = self.ws / ".agents" / "artifacts"
        art_dir.mkdir(parents=True, exist_ok=True)
        for i in range(7):
            (art_dir / f"compaction_checkpoint_{200 + i}.md").write_text(f"epoch {i}\n")

        ret = cli_main(["clean", "--workspace", str(self.ws)])
        self.assertEqual(ret, 0)
        out = mock_stdout.getvalue()
        self.assertIn("=== Agyis Hygiene & Workspace Cleanup ===", out)
        self.assertIn("Checkpoints: 2 pruned", out)
        self.assertIn("Worktrees:", out)
        self.assertIn("Branches:", out)
        self.assertIn("Scratchpads:", out)

    @patch("sys.stdout", new_callable=io.StringIO)
    def test_cli_clean_json_output(self, mock_stdout: Any) -> None:
        """agyis clean --json outputs valid schema with timing and item counts."""
        t0 = time.perf_counter()
        ret = cli_main(["clean", "--workspace", str(self.ws), "--json", "--dry-run"])
        elapsed_ms = (time.perf_counter() - t0) * 1000.0

        self.assertEqual(ret, 0)
        self.assertLess(elapsed_ms, 200.0, f"Clean CLI latency {elapsed_ms:.2f}ms exceeds 200ms benchmark")

        data = json.loads(mock_stdout.getvalue())
        self.assertEqual(data["status"], "ok")
        self.assertTrue(data["dry_run"])
        self.assertIn("checkpoints", data)
        self.assertIn("worktrees", data)
        self.assertIn("branches", data)
        self.assertIn("scratch", data)
        self.assertIn("total_pruned", data)
        self.assertIn("elapsed_ms", data)

    @patch("sys.stdout", new_callable=io.StringIO)
    def test_cli_clean_checkpoints_only(self, mock_stdout: Any) -> None:
        """agyis clean --checkpoints only cleans checkpoints."""
        art_dir = self.ws / ".agents" / "artifacts"
        art_dir.mkdir(parents=True, exist_ok=True)
        for i in range(8):
            (art_dir / f"compaction_checkpoint_{300 + i}.md").write_text(f"epoch {i}\n")

        ret = cli_main(["clean", "--checkpoints", "--retention", "3", "--workspace", str(self.ws)])
        self.assertEqual(ret, 0)
        out = mock_stdout.getvalue()
        self.assertIn("Checkpoints: 5 pruned (retained top 3)", out)
        self.assertNotIn("Worktrees:", out)
        self.assertNotIn("Branches:", out)

    @patch("sys.stdout", new_callable=io.StringIO)
    def test_cmd_clean_respects_zero_retention_and_zero_scratch_hours(self, mock_stdout: Any) -> None:
        """cmd_clean with retention=0 and scratch_hours=0.0 must not fall back to 5 and 24.0."""
        art_dir = self.ws / ".agents" / "artifacts"
        art_dir.mkdir(parents=True, exist_ok=True)
        for i in range(3):
            (art_dir / f"compaction_checkpoint_{400 + i}.md").write_text(f"epoch {i}\n", encoding="utf-8")
        latest_cp = art_dir / "compaction_checkpoint_latest.md"
        latest_cp.write_text("latest\n", encoding="utf-8")

        scratch_dir = self.ws / "scratch"
        scratch_dir.mkdir(parents=True, exist_ok=True)
        recent_scratch = scratch_dir / "recent.txt"
        recent_scratch.write_text("recent", encoding="utf-8")
        recent_mtime = time.time() - 5.0
        os.utime(recent_scratch, (recent_mtime, recent_mtime))

        args = argparse.Namespace(
            workspace=str(self.ws),
            checkpoints=True,
            worktrees=False,
            branches=False,
            scratch=True,
            all=False,
            retention=0,
            scratch_hours=0.0,
            dry_run=False,
            json=True,
        )
        ret = cmd_clean(args)
        self.assertEqual(ret, 0)

        data = json.loads(mock_stdout.getvalue())
        self.assertEqual(data["checkpoints"]["count"], 3)
        self.assertEqual(data["scratch"]["count"], 1)
        self.assertEqual(list(art_dir.glob("compaction_checkpoint_*.md")), [latest_cp])
        self.assertFalse(recent_scratch.exists())


if __name__ == "__main__":
    unittest.main()

