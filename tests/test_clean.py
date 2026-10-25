# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Arafat Zahan (@kuasha420)
# Corporate Stewardship & Infrastructure: Purrfect Software Limited (PSL)
# Governed by: ICARO-42/b Ordinance (Company-Supported Personal IP Framework)

"""
Hermetic unit and CLI tests for Agyis Clean Command (Issue #90).
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


if __name__ == "__main__":
    unittest.main()
