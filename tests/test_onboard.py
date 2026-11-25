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
    """Hermetic unit tests for cmd_onboard core lifecycle."""

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

    def test_onboard_harness_host_notice(self):
        """Verifies onboarding against Agyis harness repo itself emits an exemption notice."""
        with patch.dict(os.environ, {"AGYIS_OFFLINE": "1"}):
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
        subprocess.run(["git", "add", ".agent"], cwd=target, check=True)
        subprocess.run(["git", "commit", "-m", "Add legacy .agent"], cwd=target, check=True, stdout=subprocess.DEVNULL)

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
        with patch("sys.stdout", new_callable=io.StringIO):
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
        subprocess.run(["git", "add", "."], cwd=target, check=True)
        subprocess.run(["git", "commit", "-m", "Add services/billing"], cwd=target, check=True, stdout=subprocess.DEVNULL)

        with patch("sys.stdout", new_callable=io.StringIO):
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

    def test_onboard_polyglot_comma_separated_lang(self):
        """Verifies onboarding with comma-separated --lang provisions skills for all stacks."""
        target = self.ws / "polyglot-tauri"
        self._init_git_repo(target)
        (target / "package.json").write_text('{"name": "polyglot-app"}\n', encoding="utf-8")
        (target / "src-tauri").mkdir()
        (target / "src-tauri" / "Cargo.toml").write_text('[package]\nname = "src-tauri"\n', encoding="utf-8")
        subprocess.run(["git", "add", "."], cwd=target, check=True)
        subprocess.run(["git", "commit", "-m", "Initial polyglot layout"], cwd=target, check=True, stdout=subprocess.DEVNULL)

        with patch("sys.stdout", new_callable=io.StringIO):
            code = cmd_onboard(
                target,
                lang="typescript,rust",
                role="desktop_gui",
                config_dir=self.isolated_cfg,
            )
        self.assertEqual(code, 0)

        skills_dir = target / ".agents" / "skills"
        self.assertTrue((skills_dir / "psl-stack-typescript").exists())
        self.assertTrue((skills_dir / "psl-test-cargo").exists())
        self.assertTrue((skills_dir / "display-ops").exists())


if __name__ == "__main__":
    unittest.main()
