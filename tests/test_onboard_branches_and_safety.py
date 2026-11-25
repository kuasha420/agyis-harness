# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Arafat Zahan (@kuasha420)
# Corporate Stewardship & Infrastructure: Purrfect Software Limited (PSL)
# Governed by: ICARO-42/b Ordinance (Company-Supported Personal IP Framework)

"""
Hermetic test suite for `agyis onboard` CLI and lifecycle command (ADR-031).
Verifies end-to-end repository onboarding, topology probing, legacy pruning, and PR triggers.
"""

from __future__ import annotations

import io
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import MagicMock, patch

from harness.cli import PSL_DEPRECATION_WARNING, deprecated_psl_main, main
from harness.commands.onboard import cmd_onboard
from harness.delivery import REPO_ROOT, verify_zero_git_pollution


class TestOnboardBranchesAndSafety(unittest.TestCase):
    """Hermetic tests for dirty-tree safety patches and branch creation."""

    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.ws = Path(self.temp_dir.name).resolve()
        self.isolated_cfg = self.ws / "isolated_cfg"
        stub_plugin = self.isolated_cfg / "plugins" / "isolated_stub" / "skills" / "isolated_skill"
        stub_plugin.mkdir(parents=True)
        (stub_plugin / "SKILL.md").write_text("# Isolated Skill\n", encoding="utf-8")

    def tearDown(self):
        self.temp_dir.cleanup()

    def _init_git_repo(self, repo_path: Path, branch: str = "main") -> None:
        """Initializes a clean local git repository."""
        repo_path.mkdir(parents=True, exist_ok=True)
        subprocess.run(["git", "init", "-b", branch], cwd=repo_path, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        subprocess.run(["git", "config", "user.name", "TestUser"], cwd=repo_path, check=True)
        subprocess.run(["git", "config", "user.email", "test@example.com"], cwd=repo_path, check=True)
        dummy = repo_path / "README.md"
        dummy.write_text("# Test Repo\n", encoding="utf-8")
        (repo_path / ".gitignore").write_text(".next\n.turbo\nnode_modules\n", encoding="utf-8")
        subprocess.run(["git", "add", "README.md", ".gitignore"], cwd=repo_path, check=True)
        subprocess.run(["git", "commit", "-m", "Initial commit"], cwd=repo_path, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    def test_onboard_dirty_working_tree_aborts_without_allow_dirty(self):
        """Verifies onboarding aborts with exit code 1 if working tree has uncommitted modifications without --allow-dirty."""
        target = self.ws / "dirty-repo-abort"
        self._init_git_repo(target)
        (target / "dirty.txt").write_text("uncommitted content\n", encoding="utf-8")

        # Test stderr output and exit code 1
        with patch("sys.stderr", new_callable=io.StringIO) as mock_err, \
             patch("sys.stdout", new_callable=io.StringIO):
            code = cmd_onboard(target, allow_dirty=False)
            self.assertEqual(code, 1)
            self.assertIn("Working tree has uncommitted changes", mock_err.getvalue())

        # Test JSON output and exit code 1
        with patch("sys.stdout", new_callable=io.StringIO) as mock_out:
            code = cmd_onboard(target, allow_dirty=False, json_output=True)
            self.assertEqual(code, 1)
            data = json.loads(mock_out.getvalue().strip())
            self.assertFalse(data["success"])
            self.assertTrue(data["is_dirty"])
            self.assertIn("Working tree has uncommitted changes", data["error"])

    def test_onboard_dirty_working_tree_proceeds_with_allow_dirty_and_exports_patch(self):
        """Verifies --allow-dirty records pre-onboard diff to .agents/artifacts/pre_onboard_safety.patch."""
        target = self.ws / "dirty-repo-allow"
        self._init_git_repo(target)
        # Modify tracked file
        (target / "README.md").write_text("# Test Repo modified\n", encoding="utf-8")

        with patch("sys.stdout", new_callable=io.StringIO) as mock_out:
            code = cmd_onboard(target, allow_dirty=True, json_output=True, config_dir=self.isolated_cfg)
            self.assertEqual(code, 0)
            data = json.loads(mock_out.getvalue().strip())
            self.assertTrue(data["success"])
            patch_expected = str(target / ".agents" / "artifacts" / "pre_onboard_safety.patch")
            self.assertEqual(data["safety_patch"], patch_expected)

        patch_file = target / ".agents" / "artifacts" / "pre_onboard_safety.patch"
        compat_patch_file = target / ".agents" / "artifacts" / "wip-safety-pre-onboard.patch"
        self.assertTrue(patch_file.is_file())
        self.assertTrue(compat_patch_file.exists())
        patch_text = patch_file.read_text(encoding="utf-8")
        self.assertIn("+# Test Repo modified", patch_text)

    def test_onboard_dirty_working_tree_dry_run_with_allow_dirty(self):
        """Verifies dry-run reports safety patch path without writing patch to disk."""
        target = self.ws / "dirty-repo-dry-run"
        self._init_git_repo(target)
        (target / "README.md").write_text("# Modified in dry run\n", encoding="utf-8")

        with patch("sys.stdout", new_callable=io.StringIO) as mock_out:
            code = cmd_onboard(target, allow_dirty=True, dry_run=True, json_output=True, config_dir=self.isolated_cfg)
            self.assertEqual(code, 0)
            data = json.loads(mock_out.getvalue().strip())
            self.assertTrue(data["dry_run"])
            patch_expected = str(target / ".agents" / "artifacts" / "pre_onboard_safety.patch")
            self.assertEqual(data["safety_patch"], patch_expected)

        # In dry run, patch file should not be created
        patch_file = target / ".agents" / "artifacts" / "pre_onboard_safety.patch"
        compat_patch_file = target / ".agents" / "artifacts" / "wip-safety-pre-onboard.patch"
        self.assertFalse(patch_file.exists())
        self.assertFalse(compat_patch_file.exists())

    def test_onboard_create_branch_default_and_custom(self):
        """Verifies --create-branch switches to default chore/agyis-harness-onboarding or custom branch."""
        # Case A: Default branch name
        target_default = self.ws / "branch-repo-default"
        self._init_git_repo(target_default)
        with patch("sys.stdout", new_callable=io.StringIO):
            code = cmd_onboard(target_default, create_branch=True, config_dir=self.isolated_cfg)
        self.assertEqual(code, 0)
        curr_branch = (
            subprocess.check_output(["git", "branch", "--show-current"], cwd=target_default)
            .decode("utf-8")
            .strip()
        )
        self.assertEqual(curr_branch, "chore/agyis-harness-onboarding")

        # Case B: Custom branch name
        target_custom = self.ws / "branch-repo-custom"
        self._init_git_repo(target_custom)
        with patch("sys.stdout", new_callable=io.StringIO):
            code2 = cmd_onboard(target_custom, create_branch="feat/custom-onboard", config_dir=self.isolated_cfg)
        self.assertEqual(code2, 0)
        curr_branch2 = (
            subprocess.check_output(["git", "branch", "--show-current"], cwd=target_custom)
            .decode("utf-8")
            .strip()
        )
        self.assertEqual(curr_branch2, "feat/custom-onboard")

    def test_onboard_create_branch_already_exists(self):
        """Verifies checking out an already-existing branch succeeds cleanly."""
        target = self.ws / "branch-repo-exists"
        self._init_git_repo(target)
        # Create the branch beforehand
        subprocess.run(["git", "branch", "chore/agyis-harness-onboarding"], cwd=target, check=True)
        # Ensure we are currently on main
        curr_before = (
            subprocess.check_output(["git", "branch", "--show-current"], cwd=target)
            .decode("utf-8")
            .strip()
        )
        self.assertEqual(curr_before, "main")

        with patch("sys.stdout", new_callable=io.StringIO):
            code = cmd_onboard(target, create_branch=True, config_dir=self.isolated_cfg)
        self.assertEqual(code, 0)
        curr_after = (
            subprocess.check_output(["git", "branch", "--show-current"], cwd=target)
            .decode("utf-8")
            .strip()
        )
        self.assertEqual(curr_after, "chore/agyis-harness-onboarding")

    def test_cli_onboard_allow_dirty_and_create_branch_flags(self):
        """Verifies CLI argument parsing for --allow-dirty, --create-branch, --purge-caches, and --no-cache-purge."""
        target = self.ws / "cli-flags-repo"
        self._init_git_repo(target)
        (target / "README.md").write_text("# Dirty file\n", encoding="utf-8")

        # 1. Without --allow-dirty, CLI must exit with code 1
        with patch("sys.stdout", new_callable=io.StringIO) as mock_out, \
             patch("sys.stderr", new_callable=io.StringIO) as mock_err:
            code_fail = main(["onboard", str(target), "--json"], prog="agyis")
            self.assertEqual(code_fail, 1)
            data_fail = json.loads(mock_out.getvalue().strip())
            self.assertFalse(data_fail["success"])
            self.assertTrue(data_fail["is_dirty"])

        # 2. With --allow-dirty, --create-branch (flag only = default branch), and --no-cache-purge
        with patch("sys.stdout", new_callable=io.StringIO) as mock_out:
            code_ok = main(
                [
                    "onboard",
                    str(target),
                    "--allow-dirty",
                    "--create-branch",
                    "--no-cache-purge",
                    "--dry-run",
                    "--json",
                    "--config-dir",
                    str(self.isolated_cfg),
                ],
                prog="agyis",
            )
            self.assertEqual(code_ok, 0)
            data = json.loads(mock_out.getvalue().strip())
            self.assertEqual(data["created_branch"], "chore/agyis-harness-onboarding")
            self.assertIn("pre_onboard_safety.patch", data["safety_patch"])
            self.assertEqual(data["purged_caches"], [])
            self.assertEqual(data["caches_purged"], [])

        # 3. With explicit branch name
        with patch("sys.stdout", new_callable=io.StringIO) as mock_out:
            code_custom = main(
                [
                    "onboard",
                    str(target),
                    "--allow-dirty",
                    "--create-branch",
                    "feat/custom-branch",
                    "--dry-run",
                    "--json",
                    "--config-dir",
                    str(self.isolated_cfg),
                ],
                prog="agyis",
            )
            self.assertEqual(code_custom, 0)
            data_custom = json.loads(mock_out.getvalue().strip())
            self.assertEqual(data_custom["created_branch"], "feat/custom-branch")


if __name__ == "__main__":
    unittest.main()
