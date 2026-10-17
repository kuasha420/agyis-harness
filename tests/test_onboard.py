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


class TestOnboardCommand(unittest.TestCase):
    """Hermetic unit and integration tests for cmd_onboard."""

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
        subprocess.run(["git", "add", "README.md"], cwd=repo_path, check=True)
        subprocess.run(["git", "commit", "-m", "Initial commit"], cwd=repo_path, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    def test_onboard_harness_host_notice(self):
        """Verifies onboarding against Agyis harness repo itself emits an exemption notice."""
        with patch("sys.stdout", new_callable=io.StringIO) as mock_out:
            code = cmd_onboard(REPO_ROOT)
            self.assertEqual(code, 0)
            self.assertIn("Notice: Workspace is the Agyis harness host repository", mock_out.getvalue())

        with patch("sys.stdout", new_callable=io.StringIO) as mock_out:
            code = cmd_onboard(REPO_ROOT, json_output=True)
            self.assertEqual(code, 0)
            data = json.loads(mock_out.getvalue().strip())
            self.assertTrue(data["success"])
            self.assertTrue(data["is_harness_host"])
            self.assertIn("Notice: Workspace is the Agyis harness host repository", data["message"])

    def test_onboard_auxiliary_clone_notice(self):
        """Verifies onboarding against an auxiliary clone emits an exemption notice."""
        aux_ws = self.ws / "repo-2"
        self._init_git_repo(aux_ws)

        with patch("sys.stdout", new_callable=io.StringIO) as mock_out:
            code = cmd_onboard(aux_ws)
            self.assertEqual(code, 0)
            self.assertIn("Notice: Workspace is an auxiliary clone", mock_out.getvalue())

        with patch("sys.stdout", new_callable=io.StringIO) as mock_out:
            code = cmd_onboard(aux_ws, json_output=True)
            self.assertEqual(code, 0)
            data = json.loads(mock_out.getvalue().strip())
            self.assertTrue(data["success"])
            self.assertTrue(data["is_auxiliary_clone"])

    def test_onboard_dry_run_zero_mutation(self):
        """Verifies dry-run previews onboarding actions without creating .agents/ or modifying disk."""
        target = self.ws / "sample-project"
        self._init_git_repo(target)
        legacy = target / ".agent"
        legacy.mkdir()
        (legacy / "rules").mkdir()
        (legacy / "rules" / "rule.md").write_text("Legacy rule\n", encoding="utf-8")

        with patch("sys.stdout", new_callable=io.StringIO) as mock_out:
            code = cmd_onboard(target, dry_run=True, lang="python", role="cli")
            self.assertEqual(code, 0)
            self.assertIn("[DRY-RUN]", mock_out.getvalue())

        # Assert zero modification on disk
        self.assertFalse((target / ".agents").exists())
        self.assertTrue(legacy.exists())

    def test_onboard_live_lifecycle_and_pruning(self):
        """Verifies end-to-end live onboarding: harmonization, pruning, archive, skills, rules."""
        target = self.ws / "purr-client"
        self._init_git_repo(target)

        # Legacy structure
        legacy = target / ".agent"
        (legacy / "workflows").mkdir(parents=True)
        (legacy / "workflows" / "deploy.md").write_text("# Deploy Workflow\n", encoding="utf-8")
        (legacy / "rules").mkdir(parents=True)
        (legacy / "rules" / "custom.md").write_text("# Custom Rule\n", encoding="utf-8")

        # Track legacy files in git
        subprocess.run(["git", "add", ".agent"], cwd=target, check=True)
        subprocess.run(["git", "commit", "-m", "Add legacy .agent"], cwd=target, check=True, stdout=subprocess.DEVNULL)

        # Run live onboarding with pruning and test-isolated config
        code = cmd_onboard(
            target,
            lang="python",
            role="backend",
            prune_legacy=True,
            config_dir=self.isolated_cfg,
        )
        self.assertEqual(code, 0)

        # Assertions
        self.assertFalse(legacy.exists())
        self.assertTrue((target / ".agents" / "skills" / "deploy" / "SKILL.md").exists())
        self.assertTrue((target / ".agents" / "rules" / "custom.md").exists())
        self.assertTrue((target / "AGENTS.md").exists())
        self.assertIn("<!-- Added by AGYIS-HARNESS -->", (target / "AGENTS.md").read_text(encoding="utf-8"))

        # Verify archive created
        archive_dir = target / ".agents" / "archive"
        self.assertTrue(archive_dir.is_dir())
        tarballs = list(archive_dir.glob("legacy-agent-backup-*.tar.gz"))
        self.assertEqual(len(tarballs), 1)

        # Verify skills provisioned
        skills_dir = target / ".agents" / "skills"
        self.assertTrue((skills_dir / "psl-stack-python").exists())
        self.assertTrue((skills_dir / "psl-test-python").exists())
        self.assertTrue((skills_dir / "psl-stack-backend").exists())
        self.assertTrue((skills_dir / "db-ops").exists())

        # Verify zero git pollution
        pollution = verify_zero_git_pollution(target)
        self.assertEqual(pollution, [])

    def test_onboard_subproject_monorepo(self):
        """Verifies localized onboarding of a subproject inside a monorepo."""
        target = self.ws / "monorepo"
        self._init_git_repo(target)
        sub = target / "services" / "billing"
        sub.mkdir(parents=True)
        (sub / "package.json").write_text('{"name": "billing"}\n', encoding="utf-8")

        code = cmd_onboard(
            target,
            subproject="services/billing",
            lang="typescript",
            role="frontend",
            config_dir=self.isolated_cfg,
        )
        self.assertEqual(code, 0)

        # Skills should be installed in subproject directory
        sub_skills = sub / ".agents" / "skills"
        self.assertTrue((sub_skills / "psl-stack-typescript").exists())
        self.assertTrue((sub_skills / "psl-test-node").exists())
        self.assertFalse((sub_skills / "psl-stack-backend").exists())

    def test_onboard_json_output(self):
        """Verifies structured JSON output for automated pipelines."""
        target = self.ws / "json-project"
        self._init_git_repo(target)

        with patch("sys.stdout", new_callable=io.StringIO) as mock_out:
            code = cmd_onboard(target, lang="shell", role="infra", json_output=True)
            self.assertEqual(code, 0)
            data = json.loads(mock_out.getvalue().strip())
            self.assertTrue(data["success"])
            self.assertEqual(data["stack"], "shell")
            self.assertEqual(data["role"], "infra")
            self.assertIn("topology", data)
            self.assertIn("skills_provisioned", data)
            self.assertIn("psl-stack-shell", data["skills_provisioned"])
            self.assertIn("storage-ops", data["skills_provisioned"])

    def test_onboard_pr_open_mock(self):
        """Verifies open_pr calls create_pull_request with appropriate arguments."""
        target = self.ws / "pr-project"
        self._init_git_repo(target, branch="feat/onboard")

        real_run = subprocess.run

        def mock_subprocess_run(cmd, *args, **kwargs):
            if cmd and cmd[0] == "git" and len(cmd) > 1 and cmd[1] == "push":
                return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")
            return real_run(cmd, *args, **kwargs)

        with patch("harness.commands.onboard.create_pull_request") as mock_pr, \
             patch("subprocess.run", side_effect=mock_subprocess_run):
            mock_pr.return_value = (True, "https://github.com/org/repo/pull/42")

            code = cmd_onboard(target, open_pr=True)
            self.assertEqual(code, 0)
            self.assertTrue(mock_pr.called)

    def test_cli_onboard_and_psl_alias(self):
        """Verifies `agyis onboard` and deprecated `psl onboard` CLI execution."""
        target = self.ws / "cli-project"
        self._init_git_repo(target)

        # 1. agyis onboard
        with patch("sys.stdout", new_callable=io.StringIO) as mock_out, \
             patch("sys.stderr", new_callable=io.StringIO) as mock_err:
            code1 = main(["onboard", str(target), "--dry-run", "--json"], prog="agyis")
            self.assertEqual(code1, 0)
            self.assertEqual(mock_err.getvalue(), "")
            res1 = json.loads(mock_out.getvalue().strip())
            self.assertTrue(res1["dry_run"])

        # 2. psl onboard (with deprecation warning)
        with patch("sys.stdout", new_callable=io.StringIO) as mock_out, \
             patch("sys.stderr", new_callable=io.StringIO) as mock_err:
            code2 = deprecated_psl_main(["onboard", str(target), "--dry-run", "--json"])
            self.assertEqual(code2, 0)
            self.assertIn(PSL_DEPRECATION_WARNING.strip(), mock_err.getvalue())
            res2 = json.loads(mock_out.getvalue().strip())
            self.assertTrue(res2["dry_run"])

    def test_onboard_explicit_skills_flag(self):
        """Verifies --skills provisions only explicitly requested modular skills."""
        target = self.ws / "explicit-skills-repo"
        self._init_git_repo(target)

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
