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


class TestOnboardCliAndTopology(unittest.TestCase):
    """Hermetic tests for onboard JSON/PR/DB port warning and git topology probes."""

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

    def test_onboard_json_output(self):
        """Verifies structured JSON output for automated pipelines."""
        target = self.ws / "json-project"
        self._init_git_repo(target)

        with patch("sys.stdout", new_callable=io.StringIO) as mock_out:
            code = cmd_onboard(target, lang="shell", role="infra", json_output=True, config_dir=self.isolated_cfg)
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
             patch("subprocess.run", side_effect=mock_subprocess_run), \
             patch("sys.stdout", new_callable=io.StringIO):
            mock_pr.return_value = (True, "https://github.com/org/repo/pull/42")

            code = cmd_onboard(target, open_pr=True, config_dir=self.isolated_cfg)
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

    def test_onboard_database_port_conflict_warning_backend_role(self):
        """Verifies database port conflict detection is invoked and reported for backend/fullstack roles."""
        target = self.ws / "db-warning-repo"
        self._init_git_repo(target)

        mock_db_warning = {
            "status": "WARNING",
            "collision": True,
            "port": 5432,
            "owner": {"type": "docker", "name": "foreign_pg"},
            "free_port": 5433,
            "details": "Foreign container collision on port 5432",
            "remediation": "Rebind port to 5433",
        }

        # Backend role with mocked warning in JSON output
        target_json = self.ws / "db-warning-json"
        self._init_git_repo(target_json)
        with patch(
            "harness.runtime.hygiene_checks.check_database_port_conflicts",
            return_value=mock_db_warning,
        ) as mock_chk, patch("sys.stdout", new_callable=io.StringIO) as mock_out:
            code = cmd_onboard(
                target_json,
                role="backend",
                json_output=True,
                config_dir=self.isolated_cfg,
            )
            self.assertEqual(code, 0)
            self.assertTrue(mock_chk.called)
            data = json.loads(mock_out.getvalue().strip())
            self.assertEqual(data["database_port_check"]["status"], "WARNING")
            self.assertEqual(data["database_port_check"]["port"], 5432)

        # Backend role with mocked warning in console output
        target_console = self.ws / "db-warning-console"
        self._init_git_repo(target_console)
        with patch(
            "harness.runtime.hygiene_checks.check_database_port_conflicts",
            return_value=mock_db_warning,
        ), patch("sys.stdout", new_callable=io.StringIO) as mock_out:
            code = cmd_onboard(
                target_console,
                role="backend",
                json_output=False,
                config_dir=self.isolated_cfg,
            )
            self.assertEqual(code, 0)
            self.assertIn("Warning: Database port conflict detected on port 5432: Foreign container collision on port 5432", mock_out.getvalue())

        # Non-backend role (e.g. frontend) should NOT trigger check
        target_frontend = self.ws / "db-warning-frontend"
        self._init_git_repo(target_frontend)
        with patch(
            "harness.runtime.hygiene_checks.check_database_port_conflicts",
            return_value=mock_db_warning,
        ) as mock_chk_frontend, patch("sys.stdout", new_callable=io.StringIO) as mock_out:
            code = cmd_onboard(
                target_frontend,
                role="frontend",
                json_output=True,
                config_dir=self.isolated_cfg,
            )
            self.assertEqual(code, 0)
            self.assertFalse(mock_chk_frontend.called)
            data = json.loads(mock_out.getvalue().strip())
            self.assertIsNone(data["database_port_check"])

    def test_onboard_dry_run_skips_git_topology_mutations(self) -> None:
        """DRIFT-P1-10: GitTopologyProbe.probe(..., dry_run=True) never runs gh repo fork or git remote add."""
        from harness.delivery.git_topology import GitTopologyProbe

        repo = self.ws / "dry-run-fork-repo"
        self._init_git_repo(repo)
        import subprocess
        subprocess.run(["git", "remote", "add", "origin", "https://github.com/org/repo.git"], cwd=repo, check=True)

        real_run = subprocess.run
        calls = []

        def _fake_run(cmd, *args, **kwargs):
            calls.append(cmd)
            if cmd[:2] == ["gh", "api"]:
                return subprocess.CompletedProcess(cmd, 0, stdout="testuser\n", stderr="")
            if cmd[:3] == ["gh", "repo", "view"] and "org/repo" in cmd:
                return subprocess.CompletedProcess(
                    cmd,
                    0,
                    stdout=json.dumps({"viewerPermission": "READ", "defaultBranchRef": {"name": "main"}}),
                    stderr="",
                )
            if cmd[:3] == ["gh", "repo", "view"]:
                return subprocess.CompletedProcess(cmd, 1, stdout="", stderr="")
            return real_run(cmd, *args, **kwargs)

        with patch("shutil.which", return_value="/usr/bin/gh"), \
             patch("harness.delivery.git_topology.subprocess.run", side_effect=_fake_run):
            topo = GitTopologyProbe.probe(repo, dry_run=True)

        self.assertTrue(topo.requires_fork)
        self.assertEqual(topo.push_target_remote, "fork")
        self.assertFalse(any(c[:3] == ["gh", "repo", "fork"] for c in calls))
        self.assertFalse(any(c[:3] == ["git", "remote", "add"] for c in calls))


if __name__ == "__main__":
    unittest.main()
