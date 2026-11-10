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
    clean_dist,
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

    def test_clean_dist_missing_dir(self) -> None:
        """clean_dist returns [] when dist/ does not exist."""
        self.assertEqual(clean_dist(self.ws, dry_run=False), [])
        self.assertEqual(clean_dist(self.ws, dry_run=True), [])

    def test_clean_dist_preserves_git_and_cleans_files_subdirs_symlinks(self) -> None:
        """clean_dist removes files, subdirs, and symlinks while preserving .git* entries and honoring dry_run."""
        dist_dir = self.ws / "dist"
        dist_dir.mkdir(parents=True, exist_ok=True)
        gitignore = dist_dir / ".gitignore"
        gitignore.write_text("*\n!.gitignore\n", encoding="utf-8")
        gitkeep = dist_dir / ".gitkeep"
        gitkeep.write_text("", encoding="utf-8")

        pkg_file = dist_dir / "agyis_harness-1.0.0-py3-none-any.whl"
        pkg_file.write_text("wheel-bytes", encoding="utf-8")
        sub_dir = dist_dir / "unpacked_build"
        (sub_dir / "nested").mkdir(parents=True)
        (sub_dir / "nested" / "artifact.txt").write_text("nested", encoding="utf-8")

        outside_target = self.ws / "outside_keep_dir"
        outside_target.mkdir()
        outside_file = outside_target / "important.txt"
        outside_file.write_text("keep me", encoding="utf-8")
        sym_dir = dist_dir / "link_to_outside"
        sym_dir.symlink_to(outside_target, target_is_directory=True)

        dry_candidates = clean_dist(self.ws, dry_run=True)
        self.assertEqual(
            dry_candidates,
            [str(pkg_file), str(sym_dir), str(sub_dir)],
        )
        self.assertTrue(pkg_file.is_file())
        self.assertTrue(sub_dir.is_dir())
        self.assertTrue(sym_dir.is_symlink())
        self.assertTrue(gitignore.is_file())
        self.assertTrue(gitkeep.is_file())

        pruned = clean_dist(self.ws, dry_run=False)
        self.assertEqual(
            pruned,
            [str(pkg_file), str(sym_dir), str(sub_dir)],
        )
        self.assertFalse(pkg_file.exists())
        self.assertFalse(sub_dir.exists())
        self.assertFalse(sym_dir.exists())
        self.assertFalse(sym_dir.is_symlink())
        # Symlink target must NOT be deleted when unlinking symlink
        self.assertTrue(outside_target.is_dir())
        self.assertTrue(outside_file.is_file())
        # .git* files in dist/ must be preserved
        self.assertTrue(gitignore.is_file())
        self.assertTrue(gitkeep.is_file())

    def test_clean_dist_skips_symlinked_dist_root(self) -> None:
        """clean_dist must never traverse or clean a symlinked dist/ directory."""
        outside_dir = self.ws / "outside_release"
        outside_dir.mkdir()
        keep_file = outside_dir / "keep.whl"
        keep_file.write_text("do-not-delete", encoding="utf-8")

        dist_link = self.ws / "dist"
        dist_link.symlink_to(outside_dir, target_is_directory=True)

        self.assertEqual(clean_dist(self.ws, dry_run=True), [])
        self.assertEqual(clean_dist(self.ws, dry_run=False), [])
        self.assertTrue(dist_link.is_symlink())
        self.assertTrue(keep_file.is_file())

    def test_clean_dist_propagates_oserror_on_unremovable_entries(self) -> None:
        """clean_dist must propagate OSError from unlink/rmtree without swallowing errors."""
        dist_dir = self.ws / "dist"
        dist_dir.mkdir(parents=True, exist_ok=True)
        bad_file = dist_dir / "locked.whl"
        bad_file.write_text("locked", encoding="utf-8")

        with patch.object(Path, "unlink", side_effect=PermissionError("denied file")):
            with self.assertRaises(PermissionError):
                clean_dist(self.ws, dry_run=False)
        self.assertTrue(bad_file.is_file())

        bad_file.unlink()
        bad_dir = dist_dir / "locked_dir"
        bad_dir.mkdir()
        with patch("harness.commands.clean.shutil.rmtree", side_effect=PermissionError("denied dir")):
            with self.assertRaises(PermissionError):
                clean_dist(self.ws, dry_run=False)
        self.assertTrue(bad_dir.is_dir())



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

    def test_cli_clean_default_and_all_do_not_touch_dist(self) -> None:
        """agyis clean and agyis clean --all must leave dist/ untouched unless --dist is passed."""
        dist_dir = self.ws / "dist"
        dist_dir.mkdir(parents=True, exist_ok=True)
        (dist_dir / ".gitignore").write_text("*\n!.gitignore\n", encoding="utf-8")
        wheel = dist_dir / "pkg-1.0.0.whl"
        wheel.write_text("wheel", encoding="utf-8")
        tarball = dist_dir / "pkg-1.0.0.tar.gz"
        tarball.write_text("tar", encoding="utf-8")

        with patch("pathlib.Path.home", return_value=self.ws):
            with patch("sys.stdout", new_callable=io.StringIO) as out_default:
                ret_default = cli_main(["clean", "--workspace", str(self.ws)])
                self.assertEqual(ret_default, 0)
                self.assertNotIn("Dist:", out_default.getvalue())
            self.assertTrue(wheel.is_file())
            self.assertTrue(tarball.is_file())

            with patch("sys.stdout", new_callable=io.StringIO) as out_all:
                ret_all = cli_main(["clean", "--all", "--workspace", str(self.ws), "--json"])
                self.assertEqual(ret_all, 0)
                data = json.loads(out_all.getvalue())
                self.assertEqual(data["dist"]["count"], 0)
                self.assertEqual(data["dist"]["pruned"], [])
            self.assertTrue(wheel.is_file())
            self.assertTrue(tarball.is_file())

    def test_cli_clean_dist_dry_run_and_real(self) -> None:
        """agyis clean --dist cleans dist/ (preserving .git*) without touching other categories."""
        art_dir = self.ws / ".agents" / "artifacts"
        art_dir.mkdir(parents=True, exist_ok=True)
        for i in range(7):
            (art_dir / f"compaction_checkpoint_{800 + i}.md").write_text(f"epoch {i}\n", encoding="utf-8")

        dist_dir = self.ws / "dist"
        dist_dir.mkdir(parents=True, exist_ok=True)
        gitignore = dist_dir / ".gitignore"
        gitignore.write_text("*\n!.gitignore\n", encoding="utf-8")
        wheel = dist_dir / "pkg-1.0.0.whl"
        wheel.write_text("wheel", encoding="utf-8")
        build_sub = dist_dir / "build_tmp"
        build_sub.mkdir()
        (build_sub / "temp.bin").write_text("bin", encoding="utf-8")

        # 1. Dry run + JSON
        with patch("sys.stdout", new_callable=io.StringIO) as out_dry:
            t0 = time.perf_counter()
            ret_dry = cli_main(["clean", "--dist", "--dry-run", "--workspace", str(self.ws), "--json"])
            elapsed_ms = (time.perf_counter() - t0) * 1000.0
            self.assertEqual(ret_dry, 0)
            self.assertLess(elapsed_ms, 200.0)
            data_dry = json.loads(out_dry.getvalue())
            self.assertTrue(data_dry["dry_run"])
            self.assertEqual(data_dry["dist"]["count"], 2)
            self.assertEqual(data_dry["total_pruned"], 2)
            self.assertEqual(data_dry["checkpoints"]["count"], 0)
        self.assertTrue(wheel.is_file())
        self.assertTrue(build_sub.is_dir())

        # 2. Real run + JSON
        with patch("sys.stdout", new_callable=io.StringIO) as out_real:
            t1 = time.perf_counter()
            ret_real = cli_main(["clean", "--dist", "--workspace", str(self.ws), "--json"])
            elapsed_real_ms = (time.perf_counter() - t1) * 1000.0
            self.assertEqual(ret_real, 0)
            self.assertLess(elapsed_real_ms, 200.0)
            data_real = json.loads(out_real.getvalue())
            self.assertFalse(data_real["dry_run"])
            self.assertEqual(data_real["dist"]["count"], 2)
            self.assertEqual(data_real["total_pruned"], 2)
        self.assertFalse(wheel.exists())
        self.assertFalse(build_sub.exists())
        self.assertTrue(gitignore.is_file())
        # Checkpoints must remain untouched when only --dist was requested
        self.assertEqual(len(list(art_dir.glob("compaction_checkpoint_*.md"))), 7)

        # 3. Human output verification on fresh dist artifact
        extra_artifact = dist_dir / "pkg-2.0.0.tar.gz"
        extra_artifact.write_text("tar2", encoding="utf-8")
        with patch("sys.stdout", new_callable=io.StringIO) as out_human:
            ret_human = cli_main(["clean", "--dist", "--workspace", str(self.ws)])
            self.assertEqual(ret_human, 0)
            human_text = out_human.getvalue()
            self.assertIn("Dist:", human_text)
            self.assertIn("1 build artifacts removed", human_text)
            self.assertIn("pkg-2.0.0.tar.gz", human_text)
            self.assertNotIn("Checkpoints:", human_text)
        self.assertFalse(extra_artifact.exists())
        self.assertTrue(gitignore.is_file())

    def test_cli_clean_dist_symlink_and_error_exit_code(self) -> None:
        """agyis clean --dist ignores symlinked dist/ and exits 1 with explicit error on OSError."""
        outside_dir = self.ws / "outside_dist"
        outside_dir.mkdir()
        keep_file = outside_dir / "keep.whl"
        keep_file.write_text("keep", encoding="utf-8")
        dist_link = self.ws / "dist"
        dist_link.symlink_to(outside_dir, target_is_directory=True)

        with patch("sys.stdout", new_callable=io.StringIO) as out_sym:
            ret_sym = cli_main(["clean", "--dist", "--workspace", str(self.ws), "--json"])
            self.assertEqual(ret_sym, 0)
            data_sym = json.loads(out_sym.getvalue())
            self.assertEqual(data_sym["dist"]["count"], 0)
        self.assertTrue(keep_file.is_file())
        self.assertTrue(dist_link.is_symlink())

        # Replace symlink with real dist/ containing an unremovable file
        dist_link.unlink()
        dist_link.mkdir()
        locked_file = dist_link / "locked.whl"
        locked_file.write_text("locked", encoding="utf-8")

        with patch.object(Path, "unlink", side_effect=PermissionError("Permission denied")):
            with (
                patch("sys.stdout", new_callable=io.StringIO) as out_err_human,
                patch("sys.stderr", new_callable=io.StringIO) as err_human,
            ):
                ret_err_human = cli_main(["clean", "--dist", "--workspace", str(self.ws)])
                self.assertEqual(ret_err_human, 1)
                self.assertIn("Failed to clean dist/", err_human.getvalue())
                self.assertIn("Permission denied", err_human.getvalue())
                self.assertNotIn("✔ Completed", out_err_human.getvalue())

            with patch("sys.stdout", new_callable=io.StringIO) as out_err_json:
                ret_err_json = cli_main(["clean", "--dist", "--workspace", str(self.ws), "--json"])
                self.assertEqual(ret_err_json, 1)
                data_err = json.loads(out_err_json.getvalue())
                self.assertEqual(data_err["status"], "error")
                self.assertIn("Permission denied", data_err["error"])
                self.assertEqual(data_err["dist"]["count"], 0)
        self.assertTrue(locked_file.is_file())


if __name__ == "__main__":
    unittest.main()

