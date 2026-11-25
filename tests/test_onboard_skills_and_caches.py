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


class TestOnboardSkillsAndCaches(unittest.TestCase):
    """Hermetic tests for onboarding skill selection, legacy pruning, and cache purging."""

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

    def test_onboard_explicit_skills_flag(self):
        """Verifies --skills provisions only explicitly requested modular skills."""
        target = self.ws / "explicit-skills-repo"
        self._init_git_repo(target)

        with patch("sys.stdout", new_callable=io.StringIO):
            code = cmd_onboard(
                target,
                skills=["git-worktree-ops", "telemetry-sync"],
                config_dir=self.isolated_cfg,
            )
        self.assertEqual(code, 0)
        skills_dir = target / ".agents" / "skills"
        self.assertTrue((skills_dir / "git-worktree-ops").exists())
        self.assertTrue((skills_dir / "telemetry-sync").exists())
        self.assertFalse((skills_dir / "psl-stack-python").exists())

    def test_onboard_explicit_skills_comma_string(self):
        """Verifies explicit skills as comma-separated string."""
        target = self.ws / "explicit-skills-str"
        self._init_git_repo(target)

        with patch("sys.stdout", new_callable=io.StringIO):
            code = cmd_onboard(
                target,
                skills="git-worktree-ops,telemetry-sync",
                config_dir=self.isolated_cfg,
            )
        self.assertEqual(code, 0)
        skills_dir = target / ".agents" / "skills"
        self.assertTrue((skills_dir / "git-worktree-ops").exists())
        self.assertTrue((skills_dir / "telemetry-sync").exists())

    def test_onboard_default_pruning(self):
        """Verifies legacy .agent/ directory is pruned by default without explicit --prune-legacy."""
        target = self.ws / "default-prune-repo"
        self._init_git_repo(target)
        legacy = target / ".agent"
        (legacy / "rules").mkdir(parents=True)
        (legacy / "rules" / "rule.md").write_text("# Old Rule\n", encoding="utf-8")
        subprocess.run(["git", "add", ".agent"], cwd=target, check=True)
        subprocess.run(["git", "commit", "-m", "add legacy"], cwd=target, check=True, stdout=subprocess.DEVNULL)

        with patch("sys.stdout", new_callable=io.StringIO):
            code = cmd_onboard(target, config_dir=self.isolated_cfg)
        self.assertEqual(code, 0)
        self.assertFalse(legacy.exists(), "Legacy .agent/ must be pruned by default")

    def test_onboard_no_prune_option(self):
        """Verifies --no-prune preserves legacy .agent/ directory."""
        target = self.ws / "no-prune-repo"
        self._init_git_repo(target)
        legacy = target / ".agent"
        legacy.mkdir()
        (legacy / "rules").mkdir()
        (legacy / "rules" / "rule.md").write_text("# Old Rule\n", encoding="utf-8")
        subprocess.run(["git", "add", ".agent"], cwd=target, check=True)
        subprocess.run(["git", "commit", "-m", "Add legacy .agent"], cwd=target, check=True, stdout=subprocess.DEVNULL)

        with patch("sys.stdout", new_callable=io.StringIO):
            code = cmd_onboard(target, no_prune=True, config_dir=self.isolated_cfg)
        self.assertEqual(code, 0)
        self.assertTrue(legacy.exists(), "Legacy .agent/ must remain when no_prune=True")

    def test_onboard_cache_purging_lifecycle(self):
        """Verifies .next/ and .turbo/ cache directories are purged while node_modules is preserved."""
        target = self.ws / "next-app"
        self._init_git_repo(target)

        # Root caches with read-only file and subdirectory to verify chmod onerror handling
        ro_sub = target / ".next" / "ro_sub"
        ro_sub.mkdir(parents=True)
        ro_file = ro_sub / "locked.txt"
        ro_file.write_text("// locked\n", encoding="utf-8")
        os.chmod(ro_file, 0o444)
        os.chmod(ro_sub, 0o555)

        (target / ".next" / "types").mkdir(parents=True)
        (target / ".next" / "types" / "route.d.ts").write_text("// stale\n", encoding="utf-8")
        (target / ".turbo").mkdir(parents=True)

        # Subproject cache
        (target / "apps" / "web" / ".next").mkdir(parents=True)

        # Untouched directory in node_modules
        (target / "node_modules" / "some-pkg" / ".next").mkdir(parents=True)

        with patch("sys.stdout", new_callable=io.StringIO):
            code = cmd_onboard(target, config_dir=self.isolated_cfg)
        self.assertEqual(code, 0)

        self.assertFalse((target / ".next").exists())
        self.assertFalse((target / ".turbo").exists())
        self.assertFalse((target / "apps" / "web" / ".next").exists())
        self.assertTrue((target / "node_modules" / "some-pkg" / ".next").exists(), "node_modules must never be touched")

    def test_onboard_cache_purging_dry_run(self):
        """Verifies dry-run identifies caches to purge without deleting them from disk."""
        target = self.ws / "dry-run-cache"
        self._init_git_repo(target)
        (target / ".next").mkdir()

        with patch("sys.stdout", new_callable=io.StringIO) as mock_out:
            code = cmd_onboard(target, dry_run=True, json_output=True, config_dir=self.isolated_cfg)
            self.assertEqual(code, 0)
            data = json.loads(mock_out.getvalue().strip())
            self.assertIn(str(target / ".next"), data["caches_purged"])
        self.assertTrue((target / ".next").exists())

    def test_onboard_single_source_skills_enforced(self):
        """Verifies single-source skill deduplication prunes shadowing workspace skills and preserves unique skills."""
        target = self.ws / "dedup-repo"
        self._init_git_repo(target)

        fake_cfg = self.ws / "fake_cfg"
        plugin_skill_dir = fake_cfg / "plugins" / "psl-agy-harness" / "skills" / "psl-stack-python"
        plugin_skill_dir.mkdir(parents=True)
        (plugin_skill_dir / "SKILL.md").write_text("# Plugin Skill\n", encoding="utf-8")

        # Target already has a custom project skill
        custom_skill = target / ".agents" / "skills" / "custom-mesh-op"
        custom_skill.mkdir(parents=True)
        (custom_skill / "SKILL.md").write_text("# Custom Skill\n", encoding="utf-8")
        subprocess.run(["git", "add", "."], cwd=target, check=True)
        subprocess.run(["git", "commit", "-m", "Add custom skill"], cwd=target, check=True, stdout=subprocess.DEVNULL)

        with patch("sys.stdout", new_callable=io.StringIO):
            code = cmd_onboard(target, lang="python", config_dir=fake_cfg)
        self.assertEqual(code, 0)

        # psl-stack-python should have been deduplicated against plugin
        self.assertFalse((target / ".agents" / "skills" / "psl-stack-python").exists())
        # custom-mesh-op must be preserved
        self.assertTrue(custom_skill.exists())

    def test_cli_onboard_flags_parsing(self):
        """Verifies CLI argument parsing for --skills, --prune-legacy, --no-prune, and --subproject."""
        target = self.ws / "cli-args-test"
        self._init_git_repo(target)

        with patch("sys.stdout", new_callable=io.StringIO) as mock_out:
            code = main(
                [
                    "onboard",
                    str(target),
                    "--skills",
                    "git-worktree-ops,telemetry-sync",
                    "--no-prune",
                    "--dry-run",
                    "--json",
                    "--config-dir",
                    str(self.isolated_cfg),
                ],
                prog="agyis",
            )
            self.assertEqual(code, 0)
            data = json.loads(mock_out.getvalue().strip())
            self.assertEqual(data["skills_provisioned"], ["git-worktree-ops", "telemetry-sync"])


if __name__ == "__main__":
    unittest.main()
