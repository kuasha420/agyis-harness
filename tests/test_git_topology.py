# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Arafat Zahan (@kuasha420)
# Corporate Stewardship & Infrastructure: Purrfect Software Limited (PSL)
# Governed by: ICARO-42/b Ordinance (Company-Supported Personal IP Framework)

"""
Hermetic test suite for GitTopologyProbe and pull request delivery helpers (ADR-031).
Verifies inverted cloned-fork, collaborator permissions, auxiliary clones, and offline fallbacks.
"""

from __future__ import annotations

import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import MagicMock, patch

from harness.delivery.git_topology import (
    GitTopology,
    GitTopologyProbe,
    RemoteInfo,
    _parse_remote_url,
    create_pull_request,
)


class TestGitTopologyProbe(unittest.TestCase):
    """Hermetic unit tests for Git remote topology analysis."""

    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.ws = Path(self.temp_dir.name).resolve()

    def tearDown(self):
        self.temp_dir.cleanup()

    def _init_git_repo(self, repo_path: Path, branch: str = "main") -> None:
        """Helper to create a local hermetic git repository without network."""
        repo_path.mkdir(parents=True, exist_ok=True)
        subprocess.run(["git", "init", "-b", branch], cwd=repo_path, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        subprocess.run(["git", "config", "user.name", "TestUser"], cwd=repo_path, check=True)
        subprocess.run(["git", "config", "user.email", "test@example.com"], cwd=repo_path, check=True)
        dummy = repo_path / "README.md"
        dummy.write_text("# Test Repo\n", encoding="utf-8")
        subprocess.run(["git", "add", "README.md"], cwd=repo_path, check=True)
        subprocess.run(["git", "commit", "-m", "Initial commit"], cwd=repo_path, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    def test_remote_url_parsing(self):
        """Verifies regex extraction of owner, repo, and GitHub flag across URL formats."""
        # SSH SCP format
        owner, repo, is_gh = _parse_remote_url("git@github.com:purrfectsoft/purrmission.git")
        self.assertEqual(owner, "purrfectsoft")
        self.assertEqual(repo, "purrmission")
        self.assertTrue(is_gh)

        # HTTPS GitHub format with .git
        owner, repo, is_gh = _parse_remote_url("https://github.com/kuasha420/psl-agy-harness.git")
        self.assertEqual(owner, "kuasha420")
        self.assertEqual(repo, "psl-agy-harness")
        self.assertTrue(is_gh)

        # HTTPS GitHub format without .git
        owner, repo, is_gh = _parse_remote_url("https://github.com/sakibtamim/purrfect-download-manager")
        self.assertEqual(owner, "sakibtamim")
        self.assertEqual(repo, "purrfect-download-manager")
        self.assertTrue(is_gh)

        # SSH URI format
        owner, repo, is_gh = _parse_remote_url("ssh://git@github.com/org/custom-repo.git")
        self.assertEqual(owner, "org")
        self.assertEqual(repo, "custom-repo")
        self.assertTrue(is_gh)

        # GitLab format
        owner, repo, is_gh = _parse_remote_url("git@gitlab.com:custom-org/my-service.git")
        self.assertEqual(owner, "custom-org")
        self.assertEqual(repo, "my-service")
        self.assertFalse(is_gh)

        # Local path
        owner, repo, is_gh = _parse_remote_url("/tmp/local-git-repo.git")
        self.assertIsNone(owner)
        self.assertIsNone(repo)
        self.assertFalse(is_gh)

    def test_non_git_repo_raises_error(self):
        """Verifies probing a non-git directory raises ValueError."""
        non_git = self.ws / "empty"
        non_git.mkdir()
        with self.assertRaises(ValueError):
            GitTopologyProbe.probe(non_git)

    def test_standard_direct_push_maintainer(self):
        """Verifies standard repository where authenticated user has WRITE or ADMIN rights."""
        self._init_git_repo(self.ws, branch="main")
        subprocess.run(
            ["git", "remote", "add", "origin", "https://github.com/purrfectsoft/purrmission.git"],
            cwd=self.ws,
            check=True,
        )

        def mock_subprocess_run(cmd, *args, **kwargs):
            cmd_str = " ".join(str(c) for c in cmd)
            if "gh api user --jq .login" in cmd_str:
                return subprocess.CompletedProcess(cmd, 0, stdout="purrfectsoft\n", stderr="")
            if "gh repo view purrfectsoft/purrmission --json viewerPermission,defaultBranchRef" in cmd_str:
                payload = json.dumps({"viewerPermission": "ADMIN", "defaultBranchRef": {"name": "main"}})
                return subprocess.CompletedProcess(cmd, 0, stdout=payload, stderr="")
            return real_subprocess_run(cmd, *args, **kwargs)

        real_subprocess_run = subprocess.run
        with patch("subprocess.run", side_effect=mock_subprocess_run):
            topology = GitTopologyProbe.probe(self.ws)

        self.assertEqual(topology.authenticated_user, "purrfectsoft")
        self.assertEqual(topology.push_target_remote, "origin")
        self.assertEqual(topology.pr_target_repo, "purrfectsoft/purrmission")
        self.assertEqual(topology.pr_head_branch, "main")
        self.assertEqual(topology.pr_base_branch, "main")
        self.assertFalse(topology.requires_fork)
        self.assertEqual(topology.viewer_permission, "ADMIN")

    def test_inverted_cloned_fork_topology(self):
        """Verifies inverted fork where origin is personal fork and upstream is canonical."""
        self._init_git_repo(self.ws, branch="feat/custom-sync")
        subprocess.run(
            ["git", "remote", "add", "origin", "https://github.com/kuasha420/purrmission.git"],
            cwd=self.ws,
            check=True,
        )
        subprocess.run(
            ["git", "remote", "add", "upstream", "https://github.com/purrfectsoft/purrmission.git"],
            cwd=self.ws,
            check=True,
        )

        def mock_subprocess_run(cmd, *args, **kwargs):
            cmd_str = " ".join(str(c) for c in cmd)
            if "gh api user --jq .login" in cmd_str:
                return subprocess.CompletedProcess(cmd, 0, stdout="kuasha420\n", stderr="")
            if "gh repo view purrfectsoft/purrmission --json viewerPermission,defaultBranchRef" in cmd_str:
                payload = json.dumps({"viewerPermission": "READ", "defaultBranchRef": {"name": "master"}})
                return subprocess.CompletedProcess(cmd, 0, stdout=payload, stderr="")
            return real_subprocess_run(cmd, *args, **kwargs)

        real_subprocess_run = subprocess.run
        with patch("subprocess.run", side_effect=mock_subprocess_run):
            topology = GitTopologyProbe.probe(self.ws)

        self.assertEqual(topology.authenticated_user, "kuasha420")
        self.assertEqual(topology.push_target_remote, "origin")
        self.assertEqual(topology.canonical_upstream_remote, "upstream")
        self.assertEqual(topology.pr_target_repo, "purrfectsoft/purrmission")
        self.assertEqual(topology.pr_head_branch, "kuasha420:feat/custom-sync")
        self.assertEqual(topology.pr_base_branch, "master")
        self.assertFalse(topology.requires_fork)

    def test_read_only_fork_required_workflow(self):
        """Verifies READ permission triggers fork requirement and headless remote setup."""
        self._init_git_repo(self.ws, branch="chore/onboard")
        subprocess.run(
            ["git", "remote", "add", "origin", "https://github.com/sakibtamim/purrfect-download-manager.git"],
            cwd=self.ws,
            check=True,
        )

        def mock_subprocess_run(cmd, *args, **kwargs):
            cmd_str = " ".join(str(c) for c in cmd)
            if "gh api user --jq .login" in cmd_str:
                return subprocess.CompletedProcess(cmd, 0, stdout="kuasha420\n", stderr="")
            if "gh repo view sakibtamim/purrfect-download-manager --json viewerPermission,defaultBranchRef" in cmd_str:
                payload = json.dumps({"viewerPermission": "READ", "defaultBranchRef": {"name": "develop"}})
                return subprocess.CompletedProcess(cmd, 0, stdout=payload, stderr="")
            if "gh repo view kuasha420/purrfect-download-manager --json nameWithOwner" in cmd_str:
                # Initially not found
                return subprocess.CompletedProcess(cmd, 1, stdout="", stderr="not found")
            if "gh repo fork sakibtamim/purrfect-download-manager --clone=false --remote=true --remote-name=fork" in cmd_str:
                return subprocess.CompletedProcess(cmd, 0, stdout="fork created\n", stderr="")
            return real_subprocess_run(cmd, *args, **kwargs)

        real_subprocess_run = subprocess.run
        with patch("subprocess.run", side_effect=mock_subprocess_run):
            topology = GitTopologyProbe.probe(self.ws)

        self.assertTrue(topology.requires_fork)
        self.assertEqual(topology.push_target_remote, "fork")
        self.assertEqual(topology.pr_target_repo, "sakibtamim/purrfect-download-manager")
        self.assertEqual(topology.pr_head_branch, "kuasha420:chore/onboard")
        self.assertEqual(topology.pr_base_branch, "develop")
        self.assertEqual(topology.viewer_permission, "READ")
        self.assertIn("fork", topology.remotes)
        self.assertEqual(topology.remotes["fork"].owner, "kuasha420")

    def test_offline_or_gh_missing_fallback(self):
        """Verifies graceful non-crashing fallback when gh CLI is unavailable or unauthenticated."""
        self._init_git_repo(self.ws, branch="main")
        subprocess.run(
            ["git", "remote", "add", "origin", "git@gitlab.com:private/repo.git"],
            cwd=self.ws,
            check=True,
        )

        def mock_subprocess_run(cmd, *args, **kwargs):
            cmd_str = " ".join(str(c) for c in cmd)
            if "gh api user" in cmd_str:
                raise FileNotFoundError("gh command not found")
            return real_subprocess_run(cmd, *args, **kwargs)

        real_subprocess_run = subprocess.run
        with patch("subprocess.run", side_effect=mock_subprocess_run):
            topology = GitTopologyProbe.probe(self.ws)

        self.assertIsNone(topology.authenticated_user)
        self.assertEqual(topology.push_target_remote, "origin")
        self.assertEqual(topology.pr_head_branch, "main")
        self.assertFalse(topology.requires_fork)
        self.assertIsNone(topology.viewer_permission)

    def test_worktree_detection(self):
        """Verifies git worktree pointer file is correctly detected as is_worktree=True."""
        worktree_dir = self.ws / "worktree-branch"
        worktree_dir.mkdir()
        git_ptr = worktree_dir / ".git"
        git_ptr.write_text("gitdir: /home/test/.git/worktrees/worktree-branch\n", encoding="utf-8")

        def mock_subprocess_run(cmd, *args, **kwargs):
            cmd_str = " ".join(str(c) for c in cmd)
            if "rev-parse --is-inside-work-tree" in cmd_str:
                return subprocess.CompletedProcess(cmd, 0, stdout="true\n", stderr="")
            if "branch --show-current" in cmd_str:
                return subprocess.CompletedProcess(cmd, 0, stdout="feature-1\n", stderr="")
            if "remote -v" in cmd_str:
                return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")
            if "status --porcelain" in cmd_str:
                return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")
            if "gh api user" in cmd_str:
                return subprocess.CompletedProcess(cmd, 1, stdout="", stderr="")
            return real_subprocess_run(cmd, *args, **kwargs)

        real_subprocess_run = subprocess.run
        with patch("subprocess.run", side_effect=mock_subprocess_run):
            topology = GitTopologyProbe.probe(worktree_dir)

        self.assertTrue(topology.is_worktree)
        self.assertEqual(topology.current_branch, "feature-1")

    def test_auxiliary_clone_detection(self):
        """Verifies sister clone directories (-2, -worktrees) are detected."""
        aux_dir = self.ws / "mm-website-2"
        self._init_git_repo(aux_dir, branch="main")

        def mock_subprocess_run(cmd, *args, **kwargs):
            cmd_str = " ".join(str(c) for c in cmd)
            if "gh api user" in cmd_str:
                return subprocess.CompletedProcess(cmd, 1, stdout="", stderr="")
            return real_subprocess_run(cmd, *args, **kwargs)

        real_subprocess_run = subprocess.run
        with patch("subprocess.run", side_effect=mock_subprocess_run):
            topology = GitTopologyProbe.probe(aux_dir)

        self.assertTrue(topology.is_auxiliary_clone)

    def test_host_repo_self_detection(self):
        """Verifies agyis-harness host self-detection avoids self-onboarding."""
        host_dir = self.ws / "agyis-harness"
        self._init_git_repo(host_dir, branch="main")
        (host_dir / "harness").mkdir()
        (host_dir / "harness" / "__init__.py").write_text("", encoding="utf-8")
        (host_dir / "matrix.json").write_text("{}", encoding="utf-8")
        (host_dir / "plugin.json").write_text(json.dumps({"name": "agyis-harness"}), encoding="utf-8")

        def mock_subprocess_run(cmd, *args, **kwargs):
            cmd_str = " ".join(str(c) for c in cmd)
            if "gh api user" in cmd_str:
                return subprocess.CompletedProcess(cmd, 1, stdout="", stderr="")
            return real_subprocess_run(cmd, *args, **kwargs)

        real_subprocess_run = subprocess.run
        with patch("subprocess.run", side_effect=mock_subprocess_run):
            topology = GitTopologyProbe.probe(host_dir)

        self.assertTrue(topology.is_harness_host)

    def test_dirtiness_tracking(self):
        """Verifies untracked and modified files populate dirtiness arrays."""
        self._init_git_repo(self.ws, branch="main")
        untracked = self.ws / "untracked_file.txt"
        untracked.write_text("untracked", encoding="utf-8")
        modified = self.ws / "README.md"
        modified.write_text("modified", encoding="utf-8")

        def mock_subprocess_run(cmd, *args, **kwargs):
            cmd_str = " ".join(str(c) for c in cmd)
            if "gh api user" in cmd_str:
                return subprocess.CompletedProcess(cmd, 1, stdout="", stderr="")
            return real_subprocess_run(cmd, *args, **kwargs)

        real_subprocess_run = subprocess.run
        with patch("subprocess.run", side_effect=mock_subprocess_run):
            topology = GitTopologyProbe.probe(self.ws)

        self.assertTrue(topology.is_dirty)
        self.assertIn("untracked_file.txt", topology.untracked_files)
        self.assertIn("README.md", topology.modified_files)

    def test_create_pull_request_host_and_auxiliary_guards(self):
        """Verifies host repo and auxiliary clones are exempted from duplicate PR generation."""
        # 1. Host repo
        topo_host = GitTopology(
            workspace=self.ws,
            remotes={},
            current_branch="main",
            active_base_branch="main",
            is_dirty=False,
            untracked_files=[],
            modified_files=[],
            is_worktree=False,
            is_auxiliary_clone=False,
            is_harness_host=True,
        )
        ok, msg = create_pull_request(topo_host, "Title", "Body")
        self.assertFalse(ok)
        self.assertIn("Notice: Workspace is the Agyis harness host repository", msg)

        # 2. Auxiliary clone
        topo_aux = GitTopology(
            workspace=self.ws,
            remotes={},
            current_branch="main",
            active_base_branch="main",
            is_dirty=False,
            untracked_files=[],
            modified_files=[],
            is_worktree=False,
            is_auxiliary_clone=True,
            is_harness_host=False,
        )
        ok, msg = create_pull_request(topo_aux, "Title", "Body")
        self.assertFalse(ok)
        self.assertIn("Notice: Workspace is an auxiliary clone", msg)

    def test_create_pull_request_execution(self):
        """Verifies gh pr create is invoked with correct cross-repo arguments."""
        topo = GitTopology(
            workspace=self.ws,
            remotes={},
            current_branch="chore/onboard",
            active_base_branch="develop",
            is_dirty=False,
            untracked_files=[],
            modified_files=[],
            is_worktree=False,
            is_auxiliary_clone=False,
            is_harness_host=False,
            authenticated_user="kuasha420",
            push_target_remote="fork",
            pr_target_repo="sakibtamim/purrfect-download-manager",
            pr_base_branch="develop",
            pr_head_branch="kuasha420:chore/onboard",
            requires_fork=True,
        )

        with patch("subprocess.run") as mock_run:
            mock_run.return_value = subprocess.CompletedProcess(
                ["gh", "pr", "create"],
                0,
                stdout="https://github.com/sakibtamim/purrfect-download-manager/pull/23\n",
                stderr="",
            )
            ok, pr_url = create_pull_request(topo, "Title", "Body")

        self.assertTrue(ok)
        self.assertEqual(pr_url, "https://github.com/sakibtamim/purrfect-download-manager/pull/23")
        call_cmd = mock_run.call_args[0][0]
        self.assertIn("--repo", call_cmd)
        self.assertIn("sakibtamim/purrfect-download-manager", call_cmd)
        self.assertIn("--head", call_cmd)
        self.assertIn("kuasha420:chore/onboard", call_cmd)
        self.assertIn("--base", call_cmd)
        self.assertIn("develop", call_cmd)


if __name__ == "__main__":
    unittest.main()
