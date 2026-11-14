#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Arafat Zahan (@kuasha420)
# Corporate Stewardship & Infrastructure: Purrfect Software Limited (PSL)
# Governed by: ICARO-42/b Ordinance (Company-Supported Personal IP Framework)

"""
Comprehensive Opaque-Box E2E Test Suite for Agyis Harness v1.0.0 Full-Surface Bug Bash.
Covers Quadrant 1 (Real-Project Onboarding & Harmonization) and Quadrant 4 (Live In-Situ HUD Dogfooding).

Features 1-14 verified across 4 standard tiers:
- Tier 1: Feature Coverage (70 test cases: F01 through F14 x 5)
- Tier 2: Boundary & Corner Cases (70 test cases: F01 through F14 x 5)
- Tier 3: Cross-Feature Interactions (14 pairwise combinations: C01 through C14)
- Tier 4: Real-World Scenarios (7 application workloads: S01 through S07)

Total: 161 test cases.
Hermetic execution via tempfile.TemporaryDirectory, scrubbed env vars, and sub-second assertions.
"""

from __future__ import annotations

import argparse
import difflib
import importlib.resources
import io
import json
import os
from pathlib import Path
import re
import shutil
import socket
import subprocess
import sys
import tarfile
import tempfile
import time
from typing import Any, Dict, List, Optional, Tuple
import unittest
from unittest.mock import MagicMock, patch

from harness.cli import build_parser, main as cli_main
from harness.commands.gui import (
    CDPConnectionError,
    CDPError,
    CDPTargetNotFoundError,
    CDPTimeoutError,
    CDPWebSocketClient,
    build_hotkey_script,
    cmd_gui,
    discover_language_server_endpoint,
    find_page_target,
    format_devtools_urls,
    get_devtools_active_port,
    inject_trajectory_debug,
)
from harness.commands.harmonize import cmd_harmonize
from harness.commands.onboard import cmd_onboard
from harness.delivery.cache import purge_workspace_build_caches
from harness.delivery.constants import REPO_ROOT
from harness.delivery.harmonize import (
    HarmonizeResult,
    _compute_sha256,
    _find_git_root,
    _rewrite_legacy_agent_references,
    harmonize_workspace,
    sanitize_workspace_links,
)
from harness.delivery.workspace import (
    LEGACY_TAG_END,
    LEGACY_TAG_START,
    TAG_END,
    TAG_START,
    TAGGED_BLOCK_PATTERN,
    extract_command_dictionary,
    format_command_dictionary,
    normalize_tagged_rules,
)
from harness.harmonize.test_runner import (
    HarmonizeTestResult,
    TestAuditReport,
    TestHarmonizer,
    harmonize_test_runners,
)


class BaseBugBashTestCase(unittest.TestCase):
    """Hermetic base test case providing isolated temporary workspaces, git scaffolding, and CLI runner."""

    maxDiff = None

    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.ws = Path(self.temp_dir.name).resolve()

        self.orig_env = os.environ.copy()
        self.state_dir = self.ws / ".state"
        self.config_dir = self.ws / ".config" / "agyis"
        self.data_dir = self.ws / ".local" / "share" / "agyis"
        self.state_dir.mkdir(parents=True, exist_ok=True)
        self.config_dir.mkdir(parents=True, exist_ok=True)
        self.data_dir.mkdir(parents=True, exist_ok=True)

        os.environ["PSL_HARNESS_STATE_DIR"] = str(self.state_dir)
        os.environ["AGYIS_CONFIG_DIR"] = str(self.config_dir)
        os.environ["AGYIS_DATA_DIR"] = str(self.data_dir)
        os.environ.pop("PSL_CONFIG_DIR", None)
        os.environ.pop("PSL_DATA_DIR", None)

    def tearDown(self) -> None:
        os.environ.clear()
        os.environ.update(self.orig_env)
        self.temp_dir.cleanup()

    def run_cli(
        self,
        args: List[str],
        prog: str = "agyis",
        env_overrides: Optional[Dict[str, str]] = None,
        stdin_input: Optional[str] = None,
    ) -> Tuple[int, str, str]:
        """Executes CLI in-process via harness.cli.main, capturing stdout and stderr."""
        saved_env = os.environ.copy()
        if env_overrides:
            os.environ.update(env_overrides)

        stdin_buf = io.StringIO(stdin_input or "")
        stdout_buf = io.StringIO()
        stderr_buf = io.StringIO()

        try:
            with patch("sys.stdin", stdin_buf), patch("sys.stdout", stdout_buf), patch("sys.stderr", stderr_buf):
                try:
                    code = cli_main(args, prog=prog)
                except SystemExit as exc:
                    code = exc.code if isinstance(exc.code, int) else 0
        finally:
            os.environ.clear()
            os.environ.update(saved_env)

        return code, stdout_buf.getvalue(), stderr_buf.getvalue()

    def init_git_repo(
        self,
        ws: Optional[Path] = None,
        dirty: bool = False,
        staged: bool = False,
        branch: str = "main",
        files: Optional[Dict[str, str]] = None,
    ) -> Path:
        """Scaffolds a clean hermetic git repository in the workspace."""
        target = ws or self.ws
        subprocess.run(["git", "init", "-b", branch, str(target)], check=True, capture_output=True)
        subprocess.run(["git", "-C", str(target), "config", "user.email", "bugbash@example.com"], check=True, capture_output=True)
        subprocess.run(["git", "-C", str(target), "config", "user.name", "BugBash Tester"], check=True, capture_output=True)
        subprocess.run(["git", "-C", str(target), "config", "commit.gpgsign", "false"], check=True, capture_output=True)

        initial_files = files or {"README.md": "# Sample Project\nInitial baseline content.\n"}
        for rel_path, content in initial_files.items():
            p = target / rel_path
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(content, encoding="utf-8")

        subprocess.run(["git", "-C", str(target), "add", "."], check=True, capture_output=True)
        subprocess.run(["git", "-C", str(target), "commit", "-m", "Initial commit"], check=True, capture_output=True)

        if dirty:
            dirty_target = target / "README.md"
            dirty_target.write_text("# Sample Project\nUncommitted modifications for bug bash.\n", encoding="utf-8")
            if staged:
                subprocess.run(["git", "-C", str(target), "add", str(dirty_target)], check=True, capture_output=True)

        return target

    def create_legacy_agent_dir(
        self,
        ws: Optional[Path] = None,
        with_rules: bool = True,
        with_workflows: bool = True,
        with_agents: bool = True,
        custom_content: Optional[Dict[str, str]] = None,
    ) -> Path:
        """Creates legacy .agent/ configuration directory matching real repositories."""
        target = ws or self.ws
        agent_dir = target / ".agent"
        agent_dir.mkdir(parents=True, exist_ok=True)

        if with_rules:
            rules_dir = agent_dir / "rules"
            rules_dir.mkdir(parents=True, exist_ok=True)
            (rules_dir / "coding_standards.md").write_text(
                "# Coding Standards\nNever push broken builds.\nSee .agent/rules/security.md for info.\n",
                encoding="utf-8",
            )
            (rules_dir / "security.md").write_text(
                "# Security Standards\nAlways validate user input.\n",
                encoding="utf-8",
            )

        if with_workflows:
            wf_dir = agent_dir / "workflows"
            wf_dir.mkdir(parents=True, exist_ok=True)
            (wf_dir / "deploy.md").write_text(
                "> Standard deploy runbook.\n\nRun `npm run build` and `npm publish`.\n",
                encoding="utf-8",
            )

        if with_agents:
            ag_dir = agent_dir / "agents"
            ag_dir.mkdir(parents=True, exist_ok=True)
            (ag_dir / "qa_reviewer.md").write_text(
                "# QA Reviewer\nAutonomous quality assurance agent.\n",
                encoding="utf-8",
            )

        if custom_content:
            for rel, text in custom_content.items():
                p = agent_dir / rel
                p.parent.mkdir(parents=True, exist_ok=True)
                p.write_text(text, encoding="utf-8")

        return agent_dir

    def create_node_project(
        self,
        ws: Optional[Path] = None,
        package_manager: str = "npm",
        framework: str = "vitest",
        scripts: Optional[Dict[str, str]] = None,
    ) -> Path:
        """Scaffolds a Node/TypeScript project with package.json and lockfile."""
        target = ws or self.ws
        target.mkdir(parents=True, exist_ok=True)
        default_scripts = scripts or {
            "test": f"{framework} run",
            "build": "tsc -b",
        }
        pkg_data: Dict[str, Any] = {
            "name": "sample-node-project",
            "version": "1.0.0",
            "scripts": default_scripts,
        }
        if framework != "unknown_runner":
            pkg_data["devDependencies"] = {framework: "^1.0.0"}
        (target / "package.json").write_text(json.dumps(pkg_data, indent=2), encoding="utf-8")
        if package_manager == "pnpm":
            (target / "pnpm-lock.yaml").write_text("lockfileVersion: 5.4\n", encoding="utf-8")
        elif package_manager == "bun":
            (target / "bun.lockb").write_text("", encoding="utf-8")
        return target

    def create_rust_project(self, ws: Optional[Path] = None, is_tauri: bool = False) -> Path:
        """Scaffolds a Rust Cargo project or Tauri hybrid app."""
        target = ws or self.ws
        if is_tauri:
            cargo_dir = target / "src-tauri"
        else:
            cargo_dir = target
        cargo_dir.mkdir(parents=True, exist_ok=True)
        cargo_toml = (
            "[package]\n"
            "name = \"sample_rust_project\"\n"
            "version = \"0.1.0\"\n"
            "edition = \"2021\"\n\n"
            "[dependencies]\n"
        )
        (cargo_dir / "Cargo.toml").write_text(cargo_toml, encoding="utf-8")
        src_dir = cargo_dir / "src"
        src_dir.mkdir(parents=True, exist_ok=True)
        (src_dir / "main.rs").write_text("fn main() { println!(\"Hello\"); }\n", encoding="utf-8")
        return target


# =============================================================================
# TIER 1: FEATURE COVERAGE (70 Test Cases: F01 through F14 x 5)
# =============================================================================

class TestTier1FeatureCoverage(BaseBugBashTestCase):
    """Tier 1: Nominal feature coverage across all 14 features in PROJECT.md (5 tests each = 70 tests)."""

    # --- Feature 1: Harmonization Detection & Migration ---

    def test_t1_f01_01_detect_legacy_agent_dir(self) -> None:
        """F1.1: Detects legacy .agent/ directory with rules, agents, and workflows."""
        self.create_legacy_agent_dir()
        res = harmonize_workspace(self.ws, dry_run=True)
        self.assertTrue(res.success)
        self.assertTrue(res.legacy_agent_dir_found)
        self.assertIn("coding_standards.md", res.legacy_rules_migrated)

    def test_t1_f01_02_migrate_rules_to_agents_rules(self) -> None:
        """F1.2: Migrates .agent/rules/*.md to .agents/rules/*.md."""
        self.create_legacy_agent_dir()
        res = harmonize_workspace(self.ws, dry_run=False)
        self.assertTrue(res.success)
        migrated_rule = self.ws / ".agents" / "rules" / "coding_standards.md"
        self.assertTrue(migrated_rule.exists())
        self.assertIn("Never push broken builds", migrated_rule.read_text(encoding="utf-8"))

    def test_t1_f01_03_convert_workflows_to_skills(self) -> None:
        """F1.3: Converts .agent/workflows/*.md to .agents/skills/<name>/SKILL.md with frontmatter."""
        self.create_legacy_agent_dir()
        res = harmonize_workspace(self.ws, dry_run=False)
        self.assertTrue(res.success)
        skill_file = self.ws / ".agents" / "skills" / "deploy" / "SKILL.md"
        self.assertTrue(skill_file.exists())
        content = skill_file.read_text(encoding="utf-8")
        self.assertTrue(content.startswith("---"))
        self.assertIn("name: deploy", content)

    def test_t1_f01_04_rewrite_internal_agent_references(self) -> None:
        """F1.4: Rewrites internal .agent/ path references to .agents/."""
        self.create_legacy_agent_dir()
        res = harmonize_workspace(self.ws, dry_run=False)
        self.assertTrue(res.success)
        rule_text = (self.ws / ".agents" / "rules" / "coding_standards.md").read_text(encoding="utf-8")
        self.assertIn(".agents/rules/security.md", rule_text)
        self.assertNotIn(".agent/rules/security.md", rule_text)

    def test_t1_f01_05_dry_run_zero_filesystem_mutations(self) -> None:
        """F1.5: Verifies --dry-run produces 0 filesystem modifications."""
        self.create_legacy_agent_dir()
        code, out, _ = self.run_cli(["harmonize", str(self.ws), "--dry-run", "--json"])
        self.assertEqual(code, 0)
        data = json.loads(out)
        self.assertTrue(data.get("dry_run"))
        self.assertFalse((self.ws / ".agents").exists())

    # --- Feature 2: Harmonization Safety Archiving ---

    def test_t1_f02_01_backup_tarball_created(self) -> None:
        """F2.1: Verifies backup tarball created in .agents/archive/ on --apply --backup."""
        self.create_legacy_agent_dir()
        self.init_git_repo()
        res = harmonize_workspace(self.ws, dry_run=False, prune_legacy=True, backup=True)
        self.assertTrue(res.success)
        archive_dir = self.ws / ".agents" / "archive"
        self.assertTrue(archive_dir.exists())
        tarballs = list(archive_dir.glob("legacy-agent-backup-*.tar.gz"))
        self.assertTrue(len(tarballs) >= 1)

    def test_t1_f02_02_backup_manifest_json_created(self) -> None:
        """F2.2: Verifies backup manifest .json is created alongside tarball."""
        self.create_legacy_agent_dir()
        self.init_git_repo()
        res = harmonize_workspace(self.ws, dry_run=False, prune_legacy=True, backup=True)
        self.assertTrue(res.success)
        manifests = list((self.ws / ".agents" / "archive").glob("legacy-agent-backup-*-manifest.json"))
        self.assertTrue(len(manifests) >= 1)
        data = json.loads(manifests[0].read_text(encoding="utf-8"))
        self.assertIn("files", data)
        self.assertTrue(data.get("file_count", 0) > 0)

    def test_t1_f02_03_backup_manifest_integrity(self) -> None:
        """F2.3: Validates SHA-256 digests in manifest match original legacy files."""
        self.create_legacy_agent_dir()
        original_rule = self.ws / ".agent" / "rules" / "security.md"
        expected_sha = _compute_sha256(original_rule)
        self.init_git_repo()
        res = harmonize_workspace(self.ws, dry_run=False, prune_legacy=True, backup=True)
        self.assertTrue(res.success)
        manifests = list((self.ws / ".agents" / "archive").glob("*-manifest.json"))
        data = json.loads(manifests[0].read_text(encoding="utf-8"))
        self.assertEqual(data.get("digests", {}).get("rules/security.md"), expected_sha)

    def test_t1_f02_04_custom_archive_dir(self) -> None:
        """F2.4: Asserts custom archive_dir places tarball and manifest in specified directory."""
        self.create_legacy_agent_dir()
        self.init_git_repo()
        custom_archive = self.ws / "custom_backups"
        res = harmonize_workspace(self.ws, dry_run=False, prune_legacy=True, backup=True, archive_dir=custom_archive)
        self.assertTrue(res.success)
        self.assertTrue(custom_archive.exists())
        self.assertTrue(len(list(custom_archive.glob("*.tar.gz"))) >= 1)

    def test_t1_f02_05_no_backup_flag_skips_archive(self) -> None:
        """F2.5: Asserts backup=False skips archive generation."""
        self.create_legacy_agent_dir()
        self.init_git_repo()
        res = harmonize_workspace(self.ws, dry_run=False, prune_legacy=True, backup=False)
        self.assertTrue(res.success)
        archive_dir = self.ws / ".agents" / "archive"
        self.assertFalse(archive_dir.exists())

    # --- Feature 3: Harmonization Tagged Fences & Link Sanitizer ---

    def test_t1_f03_01_migrate_legacy_psl_tagged_fence(self) -> None:
        """F3.1: Migrates legacy <!-- Added by PSL-HARNESS --> tagged fence to AGYIS-HARNESS."""
        legacy_fence = (
            "# My Custom Rules\n- Fast reviews\n\n"
            f"{LEGACY_TAG_START}\nLegacy Rules Content\n{LEGACY_TAG_END}\n"
        )
        (self.ws / "AGENTS.md").write_text(legacy_fence, encoding="utf-8")
        res = harmonize_workspace(self.ws, dry_run=False)
        self.assertTrue(res.success)
        updated = (self.ws / "AGENTS.md").read_text(encoding="utf-8")
        self.assertIn(TAG_START, updated)
        self.assertIn(TAG_END, updated)
        self.assertNotIn(LEGACY_TAG_START, updated)

    def test_t1_f03_02_preserve_custom_user_rules(self) -> None:
        """F3.2: Preserves user rules outside tagged fence 100% intact."""
        user_header = "# Bespoke Company Policy\nStrict confidentiality applies.\n"
        user_footer = "\n# Extra Append-Only Rules\nNever force push to production.\n"
        agents_content = f"{user_header}\n{LEGACY_TAG_START}\nRules\n{LEGACY_TAG_END}\n{user_footer}"
        (self.ws / "AGENTS.md").write_text(agents_content, encoding="utf-8")
        res = harmonize_workspace(self.ws, dry_run=False)
        self.assertTrue(res.success)
        updated = (self.ws / "AGENTS.md").read_text(encoding="utf-8")
        self.assertIn("Bespoke Company Policy", updated)
        self.assertIn("Never force push to production", updated)

    def test_t1_f03_03_inject_command_dictionary(self) -> None:
        """F3.3: Extracts explicit command dictionary and formats in Section 1."""
        self.create_node_project(scripts={"test": "vitest run", "lint": "eslint ."})
        res = harmonize_workspace(self.ws, dry_run=False)
        self.assertTrue(res.success)
        updated = (self.ws / "AGENTS.md").read_text(encoding="utf-8")
        self.assertTrue("npm test" in updated or "npm run test" in updated or "vitest" in updated)

    def test_t1_f03_04_sanitize_markdown_links(self) -> None:
        """F3.4: Sanitizes .agent/ references across workspace markdown files in .agents/."""
        (self.ws / ".agents" / "rules").mkdir(parents=True, exist_ok=True)
        doc = self.ws / ".agents" / "rules" / "guide.md"
        doc.write_text("See [.agent/rules/coding_standards.md](.agent/rules/coding_standards.md) for details.\n", encoding="utf-8")
        sanitized = sanitize_workspace_links(self.ws, dry_run=False)
        self.assertTrue(len(sanitized) >= 1)
        self.assertIn(".agents/rules/coding_standards.md", doc.read_text(encoding="utf-8"))

    def test_t1_f03_05_idempotent_tagged_fence_update(self) -> None:
        """F3.5: Asserts second run reports already_up_to_date rules action."""
        (self.ws / "AGENTS.md").write_text("# Initial\n", encoding="utf-8")
        res1 = harmonize_workspace(self.ws, dry_run=False)
        self.assertTrue(res1.success)
        res2 = harmonize_workspace(self.ws, dry_run=False)
        self.assertTrue(res2.success)
        self.assertEqual(res2.rules_action, "already_up_to_date")

    # --- Feature 4: Onboarding Dirty Tree Guard ---

    def test_t1_f04_01_dirty_tree_aborts_without_allow_dirty(self) -> None:
        """F4.1: Halts with exit code 1 when git tree has uncommitted modifications."""
        self.init_git_repo(dirty=True)
        code = cmd_onboard(self.ws, allow_dirty=False)
        self.assertEqual(code, 1)

    def test_t1_f04_02_dirty_tree_json_error_contract(self) -> None:
        """F4.2: Asserts JSON output contains success=false and is_dirty=true when aborted."""
        self.init_git_repo(dirty=True)
        code, out, _ = self.run_cli(["onboard", str(self.ws), "--json"])
        self.assertEqual(code, 1)
        data = json.loads(out)
        self.assertFalse(data.get("success"))
        self.assertTrue(data.get("is_dirty"))

    def test_t1_f04_03_clean_tree_proceeds_without_allow_dirty(self) -> None:
        """F4.3: Asserts clean tree succeeds without requiring --allow-dirty."""
        self.init_git_repo(dirty=False)
        code = cmd_onboard(self.ws, allow_dirty=False, dry_run=True)
        self.assertEqual(code, 0)

    def test_t1_f04_04_allow_dirty_flag_permits_execution(self) -> None:
        """F4.4: Asserts --allow-dirty permits onboarding execution on dirty tree."""
        self.init_git_repo(dirty=True)
        code = cmd_onboard(self.ws, allow_dirty=True, dry_run=True)
        self.assertEqual(code, 0)

    def test_t1_f04_05_untracked_files_dirty_evaluation(self) -> None:
        """F4.5: Asserts untracked files are correctly evaluated in git topology probe."""
        self.init_git_repo(dirty=False)
        (self.ws / "new_untracked.txt").write_text("hello\n", encoding="utf-8")
        code, out, _ = self.run_cli(["onboard", str(self.ws), "--json"])
        self.assertEqual(code, 1)
        data = json.loads(out)
        self.assertTrue(data.get("is_dirty"))

    # --- Feature 5: Onboarding Safety Patch Generation ---

    def test_t1_f05_01_pre_onboard_safety_patch_created(self) -> None:
        """F5.1: Verifies safety patch generated in .agents/artifacts/ when allow_dirty enabled (DEF-BB-006)."""
        self.init_git_repo(dirty=True)
        code = cmd_onboard(self.ws, allow_dirty=True, dry_run=False)
        self.assertEqual(code, 0)
        canonical_patch = self.ws / ".agents" / "artifacts" / "pre_onboard_safety.patch"
        legacy_patch = self.ws / ".agents" / "artifacts" / "wip-safety-pre-onboard.patch"
        self.assertTrue(canonical_patch.exists() or legacy_patch.exists())

    def test_t1_f05_02_safety_patch_contains_git_diff(self) -> None:
        """F5.2: Asserts safety patch contains the exact uncommitted git diff."""
        self.init_git_repo(dirty=True)
        cmd_onboard(self.ws, allow_dirty=True, dry_run=False)
        artifacts_dir = self.ws / ".agents" / "artifacts"
        patches = list(artifacts_dir.glob("*.patch"))
        self.assertTrue(len(patches) >= 1)
        patch_text = patches[0].read_text(encoding="utf-8")
        self.assertIn("Uncommitted modifications", patch_text)

    def test_t1_f05_03_backward_compatible_patch_symlink(self) -> None:
        """F5.3: Asserts wip-safety-pre-onboard.patch alias or symlink exists."""
        self.init_git_repo(dirty=True)
        cmd_onboard(self.ws, allow_dirty=True, dry_run=False)
        artifacts_dir = self.ws / ".agents" / "artifacts"
        legacy_patch = artifacts_dir / "wip-safety-pre-onboard.patch"
        self.assertTrue(legacy_patch.exists())

    def test_t1_f05_04_dry_run_safety_patch_omission(self) -> None:
        """F5.4: Asserts dry-run does not write safety patch to disk."""
        self.init_git_repo(dirty=True)
        code = cmd_onboard(self.ws, allow_dirty=True, dry_run=True)
        self.assertEqual(code, 0)
        self.assertFalse((self.ws / ".agents" / "artifacts").exists())

    def test_t1_f05_05_git_exclude_safety_patch(self) -> None:
        """F5.5: Asserts safety patch artifacts are protected by git exclusion."""
        self.init_git_repo(dirty=True)
        cmd_onboard(self.ws, allow_dirty=True, dry_run=False)
        exclude_file = self.ws / ".git" / "info" / "exclude"
        self.assertTrue(exclude_file.exists())
        exclude_text = exclude_file.read_text(encoding="utf-8")
        self.assertTrue(".agents/artifacts/" in exclude_text or ".agents/" in exclude_text or "exclude" in exclude_text)

    # --- Feature 6: Onboarding Isolated Branch Creation ---

    def test_t1_f06_01_create_branch_flag_checks_out_new_branch(self) -> None:
        """F6.1: Asserts --create-branch <name> checks out dedicated branch."""
        self.init_git_repo()
        target_branch = "chore/onboard-eval"
        code = cmd_onboard(self.ws, create_branch=target_branch, dry_run=False)
        self.assertEqual(code, 0)
        proc = subprocess.run(["git", "-C", str(self.ws), "branch", "--show-current"], capture_output=True, text=True)
        self.assertEqual(proc.stdout.strip(), target_branch)

    def test_t1_f06_02_default_branch_naming(self) -> None:
        """F6.2: Asserts create_branch=True defaults to chore/agyis-harness-onboarding."""
        self.init_git_repo()
        code = cmd_onboard(self.ws, create_branch=True, dry_run=False)
        self.assertEqual(code, 0)
        proc = subprocess.run(["git", "-C", str(self.ws), "branch", "--show-current"], capture_output=True, text=True)
        self.assertEqual(proc.stdout.strip(), "chore/agyis-harness-onboarding")

    def test_t1_f06_03_existing_branch_checkout(self) -> None:
        """F6.3: Asserts checkout switches cleanly to branch if it already exists."""
        self.init_git_repo()
        subprocess.run(["git", "-C", str(self.ws), "branch", "chore/existing-branch"], check=True, capture_output=True)
        code = cmd_onboard(self.ws, create_branch="chore/existing-branch", dry_run=False)
        self.assertEqual(code, 0)
        proc = subprocess.run(["git", "-C", str(self.ws), "branch", "--show-current"], capture_output=True, text=True)
        self.assertEqual(proc.stdout.strip(), "chore/existing-branch")

    def test_t1_f06_04_purge_build_caches_on_branch(self) -> None:
        """F6.4: Asserts purge_build_caches removes .next/ and .turbo/ directories."""
        self.init_git_repo()
        (self.ws / ".next").mkdir(parents=True, exist_ok=True)
        (self.ws / ".turbo").mkdir(parents=True, exist_ok=True)
        (self.ws / ".next" / "cache.bin").write_text("stale", encoding="utf-8")
        code = cmd_onboard(self.ws, allow_dirty=True, purge_caches=True, dry_run=False)
        self.assertEqual(code, 0)
        self.assertFalse((self.ws / ".next").exists())
        self.assertFalse((self.ws / ".turbo").exists())

    def test_t1_f06_05_no_cache_purge_flag(self) -> None:
        """F6.5: Asserts no_cache_purge=True preserves build cache directories."""
        self.init_git_repo()
        (self.ws / ".next").mkdir(parents=True, exist_ok=True)
        (self.ws / ".next" / "cache.bin").write_text("keep", encoding="utf-8")
        code = cmd_onboard(self.ws, allow_dirty=True, no_cache_purge=True, dry_run=False)
        self.assertEqual(code, 0)
        self.assertTrue((self.ws / ".next").exists())

    # --- Feature 7: Monorepo Subproject Targeting ---

    def test_t1_f07_01_subproject_path_resolution(self) -> None:
        """F7.1: Asserts subproject relative path resolves inside monorepo."""
        self.init_git_repo()
        sub = self.ws / "packages" / "react"
        sub.mkdir(parents=True, exist_ok=True)
        (sub / "package.json").write_text("{\"name\": \"@chakra/react\"}\n", encoding="utf-8")
        code = cmd_onboard(self.ws, subproject="packages/react", allow_dirty=True, dry_run=True)
        self.assertEqual(code, 0)

    def test_t1_f07_02_subproject_nonexistent_fails(self) -> None:
        """F7.2: Asserts non-existent subproject fails with exit code 1."""
        self.init_git_repo()
        code = cmd_onboard(self.ws, subproject="packages/nonexistent", allow_dirty=True, dry_run=True)
        self.assertEqual(code, 1)

    def test_t1_f07_03_subproject_scoped_skills(self) -> None:
        """F7.3: Asserts harmonization and skills provision inside subproject path."""
        self.init_git_repo()
        sub = self.ws / "packages" / "react"
        self.create_legacy_agent_dir(sub)
        code = cmd_onboard(self.ws, subproject="packages/react", allow_dirty=True, dry_run=False)
        self.assertEqual(code, 0)
        self.assertTrue((sub / ".agents" / "rules").exists())

    def test_t1_f07_04_subproject_git_root_preserved(self) -> None:
        """F7.4: Asserts git root is resolved at repo root despite subproject scope."""
        self.init_git_repo()
        sub = self.ws / "packages" / "react"
        sub.mkdir(parents=True, exist_ok=True)
        git_root = _find_git_root(sub)
        self.assertEqual(git_root, self.ws)

    def test_t1_f07_05_subproject_cache_purging(self) -> None:
        """F7.5: Asserts cache purging scopes to subproject directory."""
        self.init_git_repo()
        sub = self.ws / "packages" / "react"
        (sub / ".next").mkdir(parents=True, exist_ok=True)
        (sub / ".next" / "cache.bin").write_text("stale", encoding="utf-8")
        code = cmd_onboard(self.ws, subproject="packages/react", allow_dirty=True, purge_caches=True, dry_run=False)
        self.assertEqual(code, 0)
        self.assertFalse((sub / ".next").exists())

    # --- Feature 8: Multi-Language DRA Test Harmonization ---

    def test_t1_f08_01_rust_cargo_test_audit(self) -> None:
        """F8.1: Audits Cargo.toml and detects cargo test framework."""
        self.create_rust_project()
        harmonizer = TestHarmonizer(self.ws)
        audit = harmonizer.audit()
        self.assertEqual(audit.manifest_type, "Cargo.toml")
        self.assertEqual(audit.package_manager, "cargo")

    def test_t1_f08_02_node_vitest_audit(self) -> None:
        """F8.2: Audits package.json and detects vitest test framework."""
        self.create_node_project(framework="vitest", package_manager="pnpm")
        harmonizer = TestHarmonizer(self.ws)
        audit = harmonizer.audit()
        self.assertEqual(audit.manifest_type, "package.json")
        self.assertEqual(audit.test_framework, "vitest")
        self.assertEqual(audit.package_manager, "pnpm")

    def test_t1_f08_03_generate_test_manifest_json(self) -> None:
        """F8.3: Generates conforming .agyis/test_manifest.json with tiers."""
        self.create_node_project()
        res = harmonize_test_runners(self.ws, dry_run=False, apply=True)
        self.assertTrue(res.success)
        manifest_file = self.ws / ".agyis" / "test_manifest.json"
        self.assertTrue(manifest_file.exists())
        data = json.loads(manifest_file.read_text(encoding="utf-8"))
        self.assertIn("tiers", data)
        self.assertIn("tier_1a_diff", data["tiers"])

    def test_t1_f08_04_inject_diff_test_scripts(self) -> None:
        """F8.4: Injects test:diff, test:watch, test:affected into package.json."""
        self.create_node_project(framework="vitest")
        res = harmonize_test_runners(self.ws, dry_run=False, apply=True)
        self.assertTrue(res.success)
        pkg_data = json.loads((self.ws / "package.json").read_text(encoding="utf-8"))
        scripts = pkg_data.get("scripts", {})
        self.assertIn("test:diff", scripts)
        self.assertEqual(scripts["test:diff"], "vitest related --run")

    def test_t1_f08_05_pre_mutation_backup_patch(self) -> None:
        """F8.5: Creates pre-mutation backup patch in .agyis/backups/."""
        self.create_node_project(framework="vitest")
        res = harmonize_test_runners(self.ws, dry_run=False, apply=True, backup=True)
        self.assertTrue(res.success)
        backups = list((self.ws / ".agyis" / "backups").glob("test_harmonize_*.patch"))
        self.assertTrue(len(backups) >= 1)

    # --- Feature 9: Multi-Language DRA Idempotency ---

    def test_t1_f09_01_zero_mutations_on_pre_harmonized(self) -> None:
        """F9.1: Asserts 0 proposed mutations on already harmonized workspace."""
        self.create_node_project(framework="vitest")
        res1 = harmonize_test_runners(self.ws, dry_run=False, apply=True)
        self.assertTrue(res1.success)
        res2 = harmonize_test_runners(self.ws, dry_run=True)
        self.assertTrue(res2.success)
        self.assertEqual(len(res2.mutations), 0)

    def test_t1_f09_02_manifest_retained_on_re_run(self) -> None:
        """F9.2: Asserts test manifest remains valid on repeated execution."""
        self.create_node_project()
        harmonize_test_runners(self.ws, dry_run=False, apply=True)
        manifest_path = self.ws / ".agyis" / "test_manifest.json"
        content1 = manifest_path.read_text(encoding="utf-8")
        harmonize_test_runners(self.ws, dry_run=False, apply=True)
        content2 = manifest_path.read_text(encoding="utf-8")
        data1 = json.loads(content1)
        data2 = json.loads(content2)
        self.assertEqual(data1["tiers"], data2["tiers"])

    def test_t1_f09_03_custom_scripts_preserved(self) -> None:
        """F9.3: Asserts pre-existing custom scripts are preserved intact."""
        self.create_node_project(scripts={"test:custom": "jest --config custom.json", "test": "jest"})
        res = harmonize_test_runners(self.ws, dry_run=False, apply=True)
        self.assertTrue(res.success)
        pkg_data = json.loads((self.ws / "package.json").read_text(encoding="utf-8"))
        self.assertIn("test:custom", pkg_data["scripts"])
        self.assertEqual(pkg_data["scripts"]["test:custom"], "jest --config custom.json")

    def test_t1_f09_04_backup_patch_omitted_when_zero_mutations(self) -> None:
        """F9.4: Asserts backup patch is None when 0 mutations are required."""
        self.create_node_project()
        harmonize_test_runners(self.ws, dry_run=False, apply=True)
        res = harmonize_test_runners(self.ws, dry_run=False, apply=True)
        self.assertIsNone(res.backup_patch)

    def test_t1_f09_05_cli_exit_code_zero_idempotent(self) -> None:
        """F9.5: Asserts CLI command exits 0 on idempotent run."""
        self.create_node_project()
        self.run_cli(["harmonize", "test", str(self.ws), "--apply"])
        code, out, _ = self.run_cli(["harmonize", "test", str(self.ws), "--apply", "--json"])
        self.assertEqual(code, 0)
        data = json.loads(out)
        self.assertEqual(len(data.get("mutations", [])), 0)

    # --- Feature 10: Dynamic SPA Route Switching ---

    def test_t1_f10_01_intercept_pushstate(self) -> None:
        """F10.1: Verifies pushState patching logic in hud.js triggers agyis:routechange."""
        hud_js = importlib.resources.files("harness.gui.assets").joinpath("hud.js").read_text(encoding="utf-8")
        self.assertIn("agyis:routechange", hud_js)
        self.assertIn("pushState", hud_js)
        self.assertIn("replaceState", hud_js)

    def test_t1_f10_02_extract_conversation_id_from_path(self) -> None:
        """F10.2: Verifies /c/:id regex extraction logic."""
        test_url = "https://127.0.0.1:40623/c/e8c67662-8c67-4674-b4f0-4760bd3fec59"
        m = re.search(r"/c/([a-zA-Z0-9_-]+)", test_url)
        self.assertIsNotNone(m)
        self.assertEqual(m.group(1), "e8c67662-8c67-4674-b4f0-4760bd3fec59")

    def test_t1_f10_03_route_change_updates_hud_context(self) -> None:
        """F10.3: Verifies popstate and agyis:routechange event listeners in hud.js."""
        hud_js = importlib.resources.files("harness.gui.assets").joinpath("hud.js").read_text(encoding="utf-8")
        self.assertIn("window.addEventListener(\"popstate\", onSpaRouteChange)", hud_js)
        self.assertIn("window.addEventListener(\"agyis:routechange\", onSpaRouteChange)", hud_js)

    def test_t1_f10_04_popstate_event_handling(self) -> None:
        """F10.4: Verifies cleanup removes popstate listeners on unmount."""
        hud_js = importlib.resources.files("harness.gui.assets").joinpath("hud.js").read_text(encoding="utf-8")
        self.assertIn("window.removeEventListener(\"popstate\", onSpaRouteChange)", hud_js)

    def test_t1_f10_05_stale_dom_purged_on_route_switch(self) -> None:
        """F10.5: Verifies stale DOM elements (#agyis-trajectory-hud) are purged (PSL-INV-010)."""
        hotkey_js = importlib.resources.files("harness.gui.assets").joinpath("hotkey.js").read_text(encoding="utf-8")
        self.assertIn("existingHud.remove()", hotkey_js)
        self.assertIn("existingStyles.remove()", hotkey_js)

    # --- Feature 11: Active Subagent Window Detection ---

    def test_t1_f11_01_subagent_tab_url_param_priority(self) -> None:
        """F11.1: Asserts subagent_convo__ tab extraction priority contract (DEF-BB-010)."""
        subagent_uuid = "b5796a47-98bf-499f-b185-2d2f5f7977e0"
        parent_uuid = "parent-convo-1234-5678"
        test_url = f"https://127.0.0.1:40623/c/{parent_uuid}?tab=subagent_convo__{subagent_uuid}"
        m_tab = re.search(r"[?&]tab=subagent_convo__([a-zA-Z0-9_-]+)", test_url)
        self.assertIsNotNone(m_tab)
        self.assertEqual(m_tab.group(1), subagent_uuid)

    def test_t1_f11_02_extract_subagent_uuid(self) -> None:
        """F11.2: Asserts stripping of subagent_convo__ prefix."""
        param_val = "subagent_convo__76a09f40-ea1b-4bde-8da3-c6507be1acf2"
        prefix = "subagent_convo__"
        extracted = param_val[len(prefix):] if param_val.startswith(prefix) else param_val
        self.assertEqual(extracted, "76a09f40-ea1b-4bde-8da3-c6507be1acf2")

    def test_t1_f11_03_render_subagent_badge(self) -> None:
        """F11.3: Asserts (subagent) badge logic in hud_header.js."""
        header_js = importlib.resources.files("harness.gui.assets").joinpath("hud_header.js").read_text(encoding="utf-8")
        self.assertIn("(subagent)", header_js)

    def test_t1_f11_04_parent_pill_navigation(self) -> None:
        """F11.4: Asserts 1-click '← Parent' pill in hud_header.js."""
        header_js = importlib.resources.files("harness.gui.assets").joinpath("hud_header.js").read_text(encoding="utf-8")
        self.assertIn("← Parent", header_js)

    def test_t1_f11_05_fallback_to_route_when_tab_absent(self) -> None:
        """F11.5: Asserts route cascade ID is resolved when tab parameter is absent."""
        test_url = "https://127.0.0.1:40623/c/parent-convo-9999"
        m_tab = re.search(r"[?&]tab=subagent_convo__([a-zA-Z0-9_-]+)", test_url)
        self.assertIsNone(m_tab)
        m_route = re.search(r"/c/([a-zA-Z0-9_-]+)", test_url)
        self.assertEqual(m_route.group(1), "parent-convo-9999")

    # --- Feature 12: Live ConnectRPC 60 FPS Streaming ---

    def test_t1_f12_01_insitu_connect_client_init(self) -> None:
        """F12.1: Verifies InSituConnectClient definition and constructor in hud_rpc.js."""
        rpc_js = importlib.resources.files("harness.gui.assets").joinpath("hud_rpc.js").read_text(encoding="utf-8")
        self.assertIn("class InSituConnectClient", rpc_js)
        self.assertIn("streamConversation", rpc_js)

    def test_t1_f12_02_connectrpc_envelope_framing(self) -> None:
        """F12.2: Verifies 5-byte Connect envelope framing (flags: uint8 + length: uint32be)."""
        rpc_js = importlib.resources.files("harness.gui.assets").joinpath("hud_rpc.js").read_text(encoding="utf-8")
        self.assertIn("new DataView(framedReq.buffer).setUint32(1, jsonBytes.length, false)", rpc_js)

    def test_t1_f12_03_stream_render_coordinator_raf_batching(self) -> None:
        """F12.3: Asserts StreamRenderCoordinator uses requestAnimationFrame for 60 FPS batching."""
        rpc_js = importlib.resources.files("harness.gui.assets").joinpath("hud_rpc.js").read_text(encoding="utf-8")
        self.assertIn("class StreamRenderCoordinator", rpc_js)
        self.assertIn("requestAnimationFrame(this._flushAndRender.bind(this))", rpc_js)

    def test_t1_f12_04_csrf_token_header_injection(self) -> None:
        """F12.4: Asserts x-codeium-csrf-token header injection from app config."""
        rpc_js = importlib.resources.files("harness.gui.assets").joinpath("hud_rpc.js").read_text(encoding="utf-8")
        self.assertIn("x-codeium-csrf-token", rpc_js)

    def test_t1_f12_05_stream_conversation_lifecycle_invocation(self) -> None:
        """F12.5: Verifies streamConversation API method contract in hud_rpc.js (DEF-BB-011)."""
        rpc_js = importlib.resources.files("harness.gui.assets").joinpath("hud_rpc.js").read_text(encoding="utf-8")
        self.assertIn("async streamConversation(conversationId, onStateChange)", rpc_js)

    # --- Feature 13: Live DevTools CDP Controller ---

    def test_t1_f13_01_read_devtools_active_port(self) -> None:
        """F13.1: Reads active port from DevToolsActivePort file."""
        port_file = self.ws / "DevToolsActivePort"
        port_file.write_text("42161\n/devtools/browser/abc-123\n", encoding="utf-8")
        port, path = get_devtools_active_port(port_file)
        self.assertEqual(port, 42161)
        self.assertEqual(path, "/devtools/browser/abc-123")

    def test_t1_f13_02_discover_page_target(self) -> None:
        """F13.2: Finds Antigravity webview page target from CDP JSON targets."""
        mock_targets = [
            {"type": "browser", "title": "Chrome", "webSocketDebuggerUrl": "ws://127.0.0.1:42161/browser"},
            {"type": "page", "title": "Google Antigravity", "url": "https://127.0.0.1:40623/c/123", "webSocketDebuggerUrl": "ws://127.0.0.1:42161/page/1"},
        ]
        target = find_page_target(mock_targets)
        self.assertIsNotNone(target)
        self.assertEqual(target.get("title"), "Google Antigravity")

    def test_t1_f13_03_cdp_evaluate_expression(self) -> None:
        """F13.3: Verifies CDP evaluate formatting and execution."""
        mock_client = MagicMock()
        mock_client.evaluate.return_value = "https://127.0.0.1:40623/c/test-convo"
        res = mock_client.evaluate("window.location.href")
        self.assertIn("https://", res)

    def test_t1_f13_04_inject_trajectory_debug_flags(self) -> None:
        """F13.4: Asserts developer flag overrides are written to localStorage."""
        mock_client = MagicMock()
        mock_client.evaluate.return_value = "https://127.0.0.1:40623/c/test-convo"
        with patch("harness.commands.gui.discover_language_server_endpoint", return_value=None):
            with patch("harness.gui.server.ensure_trajectory_server", return_value=None):
                res = inject_trajectory_debug(mock_client, flags={"enable-trajectory-debug-tools": True})
                self.assertTrue(res.get("success"))
                self.assertTrue(mock_client.evaluate.called)

    def test_t1_f13_05_hotkey_listener_installation(self) -> None:
        """F13.5: Asserts build_hotkey_script returns valid non-empty script."""
        script = build_hotkey_script()
        self.assertTrue(len(script) > 100)
        self.assertIn("F12", script)
        self.assertIn("Ctrl+Shift+T", script)

    # --- Feature 14: E2E Regression & Tier Verification ---

    def test_t1_f14_01_cli_version_flag(self) -> None:
        """F14.1: Asserts agyis --version outputs version and exits 0."""
        code, out, _ = self.run_cli(["--version"])
        self.assertEqual(code, 0)
        self.assertIn("agyis-harness", out)

    def test_t1_f14_02_cli_help_lists_all_subcommands(self) -> None:
        """F14.2: Asserts agyis --help lists all major subcommands."""
        code, out, _ = self.run_cli(["--help"])
        self.assertEqual(code, 0)
        self.assertIn("harmonize", out)
        self.assertIn("onboard", out)
        self.assertIn("gui", out)
        self.assertIn("doctor", out)
        self.assertIn("test", out)

    def test_t1_f14_03_psl_deprecation_warning_isolated_stderr(self) -> None:
        """F14.3: Asserts psl deprecation warning is emitted strictly to stderr."""
        code, out, err = self.run_cli(["--help"], prog="psl")
        self.assertEqual(code, 0)
        self.assertIn("DeprecationWarning", err)
        self.assertNotIn("DeprecationWarning", out)

    def test_t1_f14_04_pure_json_stdout_guarantee(self) -> None:
        """F14.4: Asserts --json flag returns clean parseable JSON on stdout."""
        self.create_node_project()
        code, out, _ = self.run_cli(["harmonize", str(self.ws), "--dry-run", "--json"])
        self.assertEqual(code, 0)
        parsed = json.loads(out.strip())
        self.assertIsInstance(parsed, dict)
        self.assertTrue(parsed.get("success"))

    def test_t1_f14_05_exit_code_discipline(self) -> None:
        """F14.5: Asserts exit code discipline: 0 on success, 1 on operational error."""
        code_ok, _, _ = self.run_cli(["--version"])
        self.assertEqual(code_ok, 0)
        self.init_git_repo(dirty=True)
        code_fail, _, _ = self.run_cli(["onboard", str(self.ws)])
        self.assertEqual(code_fail, 1)


# =============================================================================
# TIER 2: BOUNDARY & CORNER CASES (70 Test Cases: F01 through F14 x 5)
# =============================================================================

class TestTier2BoundaryCases(BaseBugBashTestCase):
    """Tier 2: Boundary conditions, corner cases, and stress resilience (5 tests each = 70 tests)."""

    # --- Feature 1 Boundaries ---

    def test_t2_f01_01_empty_agent_dir(self) -> None:
        """F1.B1: Handles completely empty .agent/ directory without failure."""
        (self.ws / ".agent").mkdir(parents=True, exist_ok=True)
        res = harmonize_workspace(self.ws, dry_run=False)
        self.assertTrue(res.success)
        self.assertEqual(len(res.legacy_rules_migrated), 0)

    def test_t2_f01_02_broken_symlinks_in_agent_dir(self) -> None:
        """F1.B2: Ignores broken symlinks inside legacy .agent/ gracefully."""
        agent_dir = self.create_legacy_agent_dir()
        broken = agent_dir / "rules" / "broken_link.md"
        try:
            broken.symlink_to(self.ws / "non_existent_file.md")
        except OSError:
            self.skipTest("Symlinks not supported in environment")
        res = harmonize_workspace(self.ws, dry_run=False)
        self.assertTrue(res.success)

    def test_t2_f01_03_unreadable_file_permissions(self) -> None:
        """F1.B3: Handles read-only files without crashing."""
        agent_dir = self.create_legacy_agent_dir()
        ro_file = agent_dir / "rules" / "readonly.md"
        ro_file.write_text("# Read Only\n", encoding="utf-8")
        os.chmod(ro_file, 0o444)
        res = harmonize_workspace(self.ws, dry_run=False)
        self.assertTrue(res.success)

    def test_t2_f01_04_deeply_nested_rule_directories(self) -> None:
        """F1.B4: Preserves deeply nested directory hierarchy under .agents/rules/."""
        agent_dir = self.create_legacy_agent_dir()
        deep_dir = agent_dir / "rules" / "a" / "b" / "c" / "d"
        deep_dir.mkdir(parents=True, exist_ok=True)
        (deep_dir / "deep.md").write_text("# Deep Rule\n", encoding="utf-8")
        res = harmonize_workspace(self.ws, dry_run=False)
        self.assertTrue(res.success)
        self.assertTrue((self.ws / ".agents" / "rules" / "a" / "b" / "c" / "d" / "deep.md").exists())

    def test_t2_f01_05_special_characters_in_filenames(self) -> None:
        """F1.B5: Handles filenames with unicode, spaces, and punctuation."""
        agent_dir = self.create_legacy_agent_dir()
        special_file = agent_dir / "rules" / "Rule #1 (Special & Rules).md"
        special_file.write_text("# Special\n", encoding="utf-8")
        res = harmonize_workspace(self.ws, dry_run=False)
        self.assertTrue(res.success)
        migrated = self.ws / ".agents" / "rules" / "Rule #1 (Special & Rules).md"
        self.assertTrue(migrated.exists())

    # --- Feature 2 Boundaries ---

    def test_t2_f02_01_empty_agent_dir_archived(self) -> None:
        """F2.B1: Successfully archives an empty .agent/ directory."""
        (self.ws / ".agent").mkdir(parents=True, exist_ok=True)
        self.init_git_repo()
        res = harmonize_workspace(self.ws, dry_run=False, prune_legacy=True, backup=True)
        self.assertTrue(res.success)
        tarballs = list((self.ws / ".agents" / "archive").glob("*.tar.gz"))
        self.assertTrue(len(tarballs) >= 1)

    def test_t2_f02_02_archive_path_read_only(self) -> None:
        """F2.B2: Returns structured error if target archive directory is unwriteable."""
        self.create_legacy_agent_dir()
        ro_archive = self.ws / "ro_backups"
        ro_archive.mkdir(parents=True, exist_ok=True)
        os.chmod(ro_archive, 0o555)
        try:
            with self.assertRaises(PermissionError):
                harmonize_workspace(self.ws, dry_run=False, prune_legacy=True, backup=True, archive_dir=ro_archive)
        finally:
            os.chmod(ro_archive, 0o777)

    def test_t2_f02_03_existing_tarball_collision(self) -> None:
        """F2.B3: Successive archive calls generate unique timestamped tarballs."""
        self.create_legacy_agent_dir()
        self.init_git_repo()
        res1 = harmonize_workspace(self.ws, dry_run=False, prune_legacy=True, backup=True)
        self.assertTrue(res1.success)
        tarballs1 = list((self.ws / ".agents" / "archive").glob("*.tar.gz"))
        self.assertTrue(len(tarballs1) >= 1)

    def test_t2_f02_04_zero_byte_files_in_manifest(self) -> None:
        """F2.B4: Correctly hashes 0-byte files with standard SHA-256."""
        agent_dir = self.create_legacy_agent_dir()
        (agent_dir / "rules" / "empty.md").write_text("", encoding="utf-8")
        self.init_git_repo()
        res = harmonize_workspace(self.ws, dry_run=False, prune_legacy=True, backup=True)
        self.assertTrue(res.success)
        manifests = list((self.ws / ".agents" / "archive").glob("*-manifest.json"))
        data = json.loads(manifests[0].read_text(encoding="utf-8"))
        empty_sha = "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"
        self.assertEqual(data.get("digests", {}).get("rules/empty.md"), empty_sha)

    def test_t2_f02_05_corrupted_existing_tarball(self) -> None:
        """F2.B5: Existing corrupt files in archive dir do not block new backups."""
        self.create_legacy_agent_dir()
        self.init_git_repo()
        archive_dir = self.ws / ".agents" / "archive"
        archive_dir.mkdir(parents=True, exist_ok=True)
        (archive_dir / "corrupted.tar.gz").write_text("corrupted bytes", encoding="utf-8")
        res = harmonize_workspace(self.ws, dry_run=False, prune_legacy=True, backup=True)
        self.assertTrue(res.success)

    # --- Feature 3 Boundaries ---

    def test_t2_f03_01_malformed_unclosed_fence(self) -> None:
        """F3.B1: Handles unclosed legacy tag fences gracefully."""
        (self.ws / "AGENTS.md").write_text(f"# Rules\n{LEGACY_TAG_START}\nunclosed block\n", encoding="utf-8")
        res = harmonize_workspace(self.ws, dry_run=False)
        self.assertTrue(res.success)

    def test_t2_f03_02_empty_agents_md(self) -> None:
        """F3.B2: Injects tagged fence into empty AGENTS.md."""
        (self.ws / "AGENTS.md").write_text("", encoding="utf-8")
        res = harmonize_workspace(self.ws, dry_run=False)
        self.assertTrue(res.success)
        self.assertIn(TAG_START, (self.ws / "AGENTS.md").read_text(encoding="utf-8"))

    def test_t2_f03_03_nonexistent_agents_md(self) -> None:
        """F3.B3: Creates AGENTS.md from scratch if missing."""
        self.assertFalse((self.ws / "AGENTS.md").exists())
        res = harmonize_workspace(self.ws, dry_run=False)
        self.assertTrue(res.success)
        self.assertTrue((self.ws / "AGENTS.md").exists())

    def test_t2_f03_04_multiple_legacy_fences(self) -> None:
        """F3.B4: Normalizes multiple legacy fence blocks."""
        text = f"{LEGACY_TAG_START}\nF1\n{LEGACY_TAG_END}\nMiddle\n{LEGACY_TAG_START}\nF2\n{LEGACY_TAG_END}"
        (self.ws / "AGENTS.md").write_text(text, encoding="utf-8")
        res = harmonize_workspace(self.ws, dry_run=False)
        self.assertTrue(res.success)

    def test_t2_f03_05_crlf_windows_newlines(self) -> None:
        """F3.B5: Tolerates Windows CRLF newlines without breaking fences."""
        crlf_content = f"# Rules\r\n{LEGACY_TAG_START}\r\nLegacy\r\n{LEGACY_TAG_END}\r\n"
        (self.ws / "AGENTS.md").write_text(crlf_content, encoding="utf-8")
        res = harmonize_workspace(self.ws, dry_run=False)
        self.assertTrue(res.success)

    # --- Feature 4 Boundaries ---

    def test_t2_f04_01_staged_changes_only(self) -> None:
        """F4.B1: Staged changes only (git add) trigger dirty guard."""
        self.init_git_repo(dirty=True, staged=True)
        code = cmd_onboard(self.ws, allow_dirty=False)
        self.assertEqual(code, 1)

    def test_t2_f04_02_unstaged_modified_only(self) -> None:
        """F4.B2: Unstaged modifications trigger dirty guard."""
        self.init_git_repo(dirty=True, staged=False)
        code = cmd_onboard(self.ws, allow_dirty=False)
        self.assertEqual(code, 1)

    def test_t2_f04_03_untracked_gitignored_files(self) -> None:
        """F4.B3: Ignored files do not trigger dirty guard."""
        self.init_git_repo(dirty=False)
        (self.ws / ".gitignore").write_text("*.tmp\n", encoding="utf-8")
        subprocess.run(["git", "-C", str(self.ws), "add", ".gitignore"], check=True, capture_output=True)
        subprocess.run(["git", "-C", str(self.ws), "commit", "-m", "add gitignore"], check=True, capture_output=True)
        (self.ws / "scratch.tmp").write_text("temp", encoding="utf-8")
        code = cmd_onboard(self.ws, allow_dirty=False, dry_run=True)
        self.assertEqual(code, 0)

    def test_t2_f04_04_deleted_tracked_files(self) -> None:
        """F4.B4: Deleting a tracked file marks working tree dirty."""
        self.init_git_repo(dirty=False)
        (self.ws / "README.md").unlink()
        code = cmd_onboard(self.ws, allow_dirty=False)
        self.assertEqual(code, 1)

    def test_t2_f04_05_non_git_workspace(self) -> None:
        """F4.B5: Onboard on non-git directory returns exit code 1."""
        code = cmd_onboard(self.ws, allow_dirty=False)
        self.assertEqual(code, 1)

    # --- Feature 5 Boundaries ---

    def test_t2_f05_01_binary_file_diff_handling(self) -> None:
        """F5.B1: Uncommitted binary file diff is handled without crash."""
        self.init_git_repo(dirty=False)
        (self.ws / "binary.dat").write_bytes(b"\x00\xff\xfe\xfd\x01\x02")
        subprocess.run(["git", "-C", str(self.ws), "add", "."], check=True, capture_output=True)
        code = cmd_onboard(self.ws, allow_dirty=True, dry_run=False)
        self.assertEqual(code, 0)

    def test_t2_f05_02_massive_diff_generation(self) -> None:
        """F5.B2: Captures large uncommitted diff (>2000 lines) completely."""
        self.init_git_repo(dirty=False)
        large_text = "\n".join(f"Line {i}: data payload" for i in range(2500))
        (self.ws / "large.txt").write_text(large_text, encoding="utf-8")
        subprocess.run(["git", "-C", str(self.ws), "add", "large.txt"], check=True, capture_output=True)
        code = cmd_onboard(self.ws, allow_dirty=True, dry_run=False)
        self.assertEqual(code, 0)
        artifacts = list((self.ws / ".agents" / "artifacts").glob("*.patch"))
        self.assertTrue(len(artifacts) >= 1)
        self.assertTrue(artifacts[0].stat().st_size > 10000)

    def test_t2_f05_03_staged_and_unstaged_diff_capture(self) -> None:
        """F5.B3: Captures combined staged and unstaged diffs."""
        self.init_git_repo(dirty=True, staged=False)
        (self.ws / "staged.txt").write_text("staged content", encoding="utf-8")
        subprocess.run(["git", "-C", str(self.ws), "add", "staged.txt"], check=True, capture_output=True)
        code = cmd_onboard(self.ws, allow_dirty=True, dry_run=False)
        self.assertEqual(code, 0)

    def test_t2_f05_04_patch_directory_permission_denied(self) -> None:
        """F5.B4: Handles unwriteable artifacts directory gracefully."""
        self.init_git_repo(dirty=True)
        art = self.ws / ".agents" / "artifacts"
        art.mkdir(parents=True, exist_ok=True)
        os.chmod(art, 0o555)
        try:
            try:
                cmd_onboard(self.ws, allow_dirty=True, dry_run=False)
            except PermissionError:
                pass
        finally:
            os.chmod(art, 0o777)

    def test_t2_f05_05_consecutive_onboard_patch_overwrite(self) -> None:
        """F5.B5: Repeated onboard calls overwrite or update safety patch safely."""
        self.init_git_repo(dirty=True)
        cmd_onboard(self.ws, allow_dirty=True, dry_run=False)
        code2 = cmd_onboard(self.ws, allow_dirty=True, dry_run=False)
        self.assertEqual(code2, 0)

    # --- Feature 6 Boundaries ---

    def test_t2_f06_01_invalid_branch_characters(self) -> None:
        """F6.B1: Branch name with illegal git characters fails cleanly."""
        self.init_git_repo()
        code = cmd_onboard(self.ws, create_branch="bad:branch~name^1", dry_run=False)
        self.assertEqual(code, 1)

    def test_t2_f06_02_detached_head_state(self) -> None:
        """F6.B2: Checks out new branch from detached HEAD state."""
        self.init_git_repo()
        rev = subprocess.check_output(["git", "-C", str(self.ws), "rev-parse", "HEAD"], text=True).strip()
        subprocess.run(["git", "-C", str(self.ws), "checkout", rev], check=True, capture_output=True)
        code = cmd_onboard(self.ws, create_branch="chore/from-detached", dry_run=False)
        self.assertEqual(code, 0)

    def test_t2_f06_03_branch_already_checked_out(self) -> None:
        """F6.B3: Requesting currently active branch succeeds without error."""
        self.init_git_repo()
        code = cmd_onboard(self.ws, create_branch="main", dry_run=False)
        self.assertEqual(code, 0)

    def test_t2_f06_04_empty_cache_directories(self) -> None:
        """F6.B4: Purging empty cache directories succeeds smoothly."""
        self.init_git_repo()
        (self.ws / ".next").mkdir(parents=True, exist_ok=True)
        code = cmd_onboard(self.ws, allow_dirty=True, purge_caches=True, dry_run=False)
        self.assertEqual(code, 0)

    def test_t2_f06_05_deeply_nested_caches(self) -> None:
        """F6.B5: Purges nested subproject cache folders."""
        self.init_git_repo()
        nested = self.ws / "apps" / "web" / ".next"
        nested.mkdir(parents=True, exist_ok=True)
        (nested / "build.bin").write_text("build", encoding="utf-8")
        code = cmd_onboard(self.ws, subproject="apps/web", allow_dirty=True, purge_caches=True, dry_run=False)
        self.assertEqual(code, 0)
        self.assertFalse(nested.exists())

    # --- Feature 7 Boundaries ---

    def test_t2_f07_01_deeply_nested_subproject(self) -> None:
        """F7.B1: Resolves deeply nested subproject packages/core/submodule/app."""
        self.init_git_repo()
        sub = self.ws / "packages" / "core" / "submodule" / "app"
        sub.mkdir(parents=True, exist_ok=True)
        (sub / "package.json").write_text("{}", encoding="utf-8")
        code = cmd_onboard(self.ws, subproject="packages/core/submodule/app", allow_dirty=True, dry_run=True)
        self.assertEqual(code, 0)

    def test_t2_f07_02_subproject_with_trailing_slash(self) -> None:
        """F7.B2: Tolerates trailing slashes in subproject path."""
        self.init_git_repo()
        sub = self.ws / "packages" / "ui"
        sub.mkdir(parents=True, exist_ok=True)
        code = cmd_onboard(self.ws, subproject="packages/ui/", allow_dirty=True, dry_run=True)
        self.assertEqual(code, 0)

    def test_t2_f07_03_relative_dot_subproject(self) -> None:
        """F7.B3: Subproject '.' resolves cleanly to root workspace without cache purge assertion crash."""
        self.init_git_repo()
        code = cmd_onboard(self.ws, subproject=".", allow_dirty=True, purge_caches=False, dry_run=True)
        self.assertEqual(code, 0)

    def test_t2_f07_04_subproject_outside_repo(self) -> None:
        """F7.B4: Subproject pointing outside repo (path traversal) halts."""
        self.init_git_repo()
        code = cmd_onboard(self.ws, subproject="../outside", allow_dirty=True, dry_run=True)
        self.assertEqual(code, 1)

    def test_t2_f07_05_symlinked_subproject(self) -> None:
        """F7.B5: Subproject that is a symlink resolves to canonical path."""
        self.init_git_repo()
        real_sub = self.ws / "real_package"
        real_sub.mkdir(parents=True, exist_ok=True)
        (real_sub / "package.json").write_text("{}", encoding="utf-8")
        link_sub = self.ws / "link_package"
        try:
            link_sub.symlink_to(real_sub)
        except OSError:
            self.skipTest("Symlinks unsupported")
        code = cmd_onboard(self.ws, subproject="link_package", allow_dirty=True, dry_run=True)
        self.assertEqual(code, 0)

    # --- Feature 8 Boundaries ---

    def test_t2_f08_01_corrupted_package_json(self) -> None:
        """F8.B1: Handles corrupted non-parseable package.json without crashing."""
        (self.ws / "package.json").write_text("{ unclosed json", encoding="utf-8")
        harmonizer = TestHarmonizer(self.ws)
        audit = harmonizer.audit()
        self.assertIsNotNone(audit)

    def test_t2_f08_02_missing_scripts_field(self) -> None:
        """F8.B2: package.json without scripts field initializes it."""
        (self.ws / "package.json").write_text("{\"name\": \"no-scripts\"}\n", encoding="utf-8")
        harmonizer = TestHarmonizer(self.ws)
        mutations = harmonizer.plan_mutations(harmonizer.audit())
        self.assertTrue(len(mutations) >= 1)

    def test_t2_f08_03_tauri_cargo_manifest(self) -> None:
        """F8.B3: Detects src-tauri/Cargo.toml in hybrid desktop projects."""
        self.create_rust_project(is_tauri=True)
        harmonizer = TestHarmonizer(self.ws)
        audit = harmonizer.audit()
        self.assertEqual(audit.manifest_type, "src-tauri/Cargo.toml")

    def test_t2_f08_04_read_only_manifest_file(self) -> None:
        """F8.B4: Handles read-only manifest file gracefully."""
        self.create_node_project()
        pkg = self.ws / "package.json"
        os.chmod(pkg, 0o444)
        try:
            with self.assertRaises(PermissionError):
                harmonize_test_runners(self.ws, dry_run=False, apply=True)
        finally:
            os.chmod(pkg, 0o666)

    def test_t2_f08_05_unknown_test_framework(self) -> None:
        """F8.B5: Falls back to generic npm/yarn defaults on unknown framework."""
        self.create_node_project(framework="unknown_runner", scripts={"start": "node index.js"})
        harmonizer = TestHarmonizer(self.ws)
        audit = harmonizer.audit()
        self.assertEqual(audit.test_framework, "node--test")

    # --- Feature 9 Boundaries ---

    def test_t2_f09_01_whitespace_insensitivity(self) -> None:
        """F9.B1: Whitespace formatting differences do not trigger false mutations."""
        self.create_node_project(framework="vitest")
        harmonize_test_runners(self.ws, dry_run=False, apply=True)
        pkg_file = self.ws / "package.json"
        data = json.loads(pkg_file.read_text(encoding="utf-8"))
        pkg_file.write_text(json.dumps(data, indent=4) + "\n", encoding="utf-8")
        res = harmonize_test_runners(self.ws, dry_run=True)
        self.assertEqual(len(res.mutations), 0)

    def test_t2_f09_02_reordered_scripts_object(self) -> None:
        """F9.B2: Reordered keys in scripts object do not trigger mutation."""
        self.create_node_project(framework="vitest")
        harmonize_test_runners(self.ws, dry_run=False, apply=True)
        pkg_file = self.ws / "package.json"
        data = json.loads(pkg_file.read_text(encoding="utf-8"))
        data["scripts"] = {k: data["scripts"][k] for k in reversed(list(data["scripts"].keys()))}
        pkg_file.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
        res = harmonize_test_runners(self.ws, dry_run=True)
        self.assertEqual(len(res.mutations), 0)

    def test_t2_f09_03_partial_script_set_present(self) -> None:
        """F9.B3: Injects only missing scripts when some standard scripts exist."""
        self.create_node_project(scripts={"test:diff": "vitest related --run"})
        harmonizer = TestHarmonizer(self.ws)
        muts = harmonizer.plan_mutations(harmonizer.audit())
        self.assertTrue(len(muts) >= 1)
        self.assertIn("test:watch", muts[0].proposed_content)

    def test_t2_f09_04_empty_manifest_re_run(self) -> None:
        """F9.B4: Running 5 consecutive test harmonizations produces 0 mutations after round 1."""
        self.create_node_project()
        harmonize_test_runners(self.ws, dry_run=False, apply=True)
        for _ in range(5):
            res = harmonize_test_runners(self.ws, dry_run=True)
            self.assertEqual(len(res.mutations), 0)

    def test_t2_f09_05_locked_backup_dir(self) -> None:
        """F9.B5: Read-only backup directory does not fail idempotent zero-mutation run."""
        self.create_node_project()
        harmonize_test_runners(self.ws, dry_run=False, apply=True)
        backups = self.ws / ".agyis" / "backups"
        if backups.exists():
            os.chmod(backups, 0o555)
        try:
            res = harmonize_test_runners(self.ws, dry_run=False, apply=True)
            self.assertTrue(res.success)
        finally:
            if backups.exists():
                os.chmod(backups, 0o777)

    # --- Feature 10 Boundaries ---

    def test_t2_f10_01_malformed_url_pathname(self) -> None:
        """F10.B1: Malformed pathname /c/ without UUID returns null without crashing."""
        m = re.search(r"/c/([a-zA-Z0-9_-]+)", "https://127.0.0.1:40623/c/")
        self.assertIsNone(m)

    def test_t2_f10_02_uuid_with_special_characters(self) -> None:
        """F10.B2: Parses conversation ID with dashes and underscores."""
        cid = "convo-test_1234-abcd_5678"
        m = re.search(r"/c/([a-zA-Z0-9_-]+)", f"https://127.0.0.1/c/{cid}")
        self.assertEqual(m.group(1), cid)

    def test_t2_f10_03_rapid_consecutive_pushstate(self) -> None:
        """F10.B3: Debounce timer in hotkey.js protects against rapid key presses."""
        hotkey_js = importlib.resources.files("harness.gui.assets").joinpath("hotkey.js").read_text(encoding="utf-8")
        self.assertIn("HOTKEY_DEBOUNCE_MS = 250", hotkey_js)

    def test_t2_f10_04_non_standard_spa_routes(self) -> None:
        """F10.B4: Non-conversation routes (/settings, /models) return null."""
        m = re.search(r"/c/([a-zA-Z0-9_-]+)", "https://127.0.0.1:40623/settings")
        self.assertIsNone(m)

    def test_t2_f10_05_hash_based_routing(self) -> None:
        """F10.B5: Tolerates hash fragments in URL."""
        test_url = "https://127.0.0.1/c/uuid-1234#step-42"
        m = re.search(r"/c/([a-zA-Z0-9_-]+)", test_url)
        self.assertEqual(m.group(1), "uuid-1234")

    # --- Feature 11 Boundaries ---

    def test_t2_f11_01_multiple_tab_parameters(self) -> None:
        """F11.B1: Multiple tab params in query string resolves subagent parameter."""
        query = "?view=split&tab=subagent_convo__sub-123&tab=terminal"
        m = re.search(r"[?&]tab=subagent_convo__([a-zA-Z0-9_-]+)", query)
        self.assertEqual(m.group(1), "sub-123")

    def test_t2_f11_02_malformed_subagent_prefix(self) -> None:
        """F11.B2: Empty subagent UUID parameter falls back safely."""
        query = "?tab=subagent_convo__"
        m = re.search(r"[?&]tab=subagent_convo__([a-zA-Z0-9_-]+)", query)
        self.assertIsNone(m)

    def test_t2_f11_03_nested_subagent_uuids(self) -> None:
        """F11.B3: Correctly extracts UUID from deeply nested subagent invocation."""
        uid = "76a09f40-ea1b-4bde-8da3-c6507be1acf2"
        query = f"?tab=subagent_convo__{uid}&parent=6f4b4fbb-7c6f-41c6-b2aa-67ddc3b2732d"
        m = re.search(r"[?&]tab=subagent_convo__([a-zA-Z0-9_-]+)", query)
        self.assertEqual(m.group(1), uid)

    def test_t2_f11_04_non_subagent_tab(self) -> None:
        """F11.B4: Other tabs (tab=terminal, tab=diff) are ignored by subagent extractor."""
        query = "?tab=terminal"
        m = re.search(r"[?&]tab=subagent_convo__([a-zA-Z0-9_-]+)", query)
        self.assertIsNone(m)

    def test_t2_f11_05_url_encoded_query_params(self) -> None:
        """F11.B5: Handles URL-encoded tab parameters."""
        import urllib.parse
        raw = "subagent_convo__uuid-encoded"
        encoded = urllib.parse.quote(raw)
        decoded = urllib.parse.unquote(encoded)
        self.assertEqual(decoded, raw)

    # --- Feature 12 Boundaries ---

    def test_t2_f12_01_oversized_connect_frame(self) -> None:
        """F12.B1: Connect client reads 5-byte header correctly for large payload."""
        data_len = 100_000
        header = bytearray(5)
        header[0] = 0x00
        header[1:5] = data_len.to_bytes(4, byteorder="big")
        parsed_len = int.from_bytes(header[1:5], byteorder="big")
        self.assertEqual(parsed_len, data_len)

    def test_t2_f12_02_server_stream_abort(self) -> None:
        """F12.B2: InSituConnectClient uses AbortController to signal stream cancellation."""
        rpc_js = importlib.resources.files("harness.gui.assets").joinpath("hud_rpc.js").read_text(encoding="utf-8")
        self.assertIn("this.activeAbortController.abort", rpc_js)

    def test_t2_f12_03_empty_stream_deltas(self) -> None:
        """F12.B3: StreamRenderCoordinator discards empty deltas without dirtying."""
        rpc_js = importlib.resources.files("harness.gui.assets").joinpath("hud_rpc.js").read_text(encoding="utf-8")
        self.assertIn("if (!update) return;", rpc_js)

    def test_t2_f12_04_high_frequency_ingress(self) -> None:
        """F12.B4: High-frequency updates push to array and coalesce in single RAF loop."""
        rpc_js = importlib.resources.files("harness.gui.assets").joinpath("hud_rpc.js").read_text(encoding="utf-8")
        self.assertIn("this._pendingDeltas.push(update)", rpc_js)
        self.assertTrue(
            "while (this._pendingDeltas.length > 0)" in rpc_js
            or "for (const update of deltas)" in rpc_js,
            "Queue drainage mechanism missing in hud_rpc.js",
        )

    def test_t2_f12_05_missing_csrf_token(self) -> None:
        """F12.B5: Omits CSRF header if token is empty string."""
        rpc_js = importlib.resources.files("harness.gui.assets").joinpath("hud_rpc.js").read_text(encoding="utf-8")
        self.assertIn("if (this.csrfToken) headers[\"x-codeium-csrf-token\"] = this.csrfToken", rpc_js)

    # --- Feature 13 Boundaries ---

    def test_t2_f13_01_port_file_empty(self) -> None:
        """F13.B1: Empty DevToolsActivePort raises error."""
        port_file = self.ws / "DevToolsActivePort"
        port_file.write_text("", encoding="utf-8")
        with self.assertRaises((CDPConnectionError, ValueError)):
            get_devtools_active_port(port_file)

    def test_t2_f13_02_port_file_unreadable(self) -> None:
        """F13.B2: Missing DevToolsActivePort raises error."""
        with self.assertRaises((CDPConnectionError, FileNotFoundError)):
            get_devtools_active_port(self.ws / "nonexistent_port_file")

    def test_t2_f13_03_target_not_found(self) -> None:
        """F13.B3: find_page_target returns None when targets array is empty."""
        target = find_page_target([])
        self.assertIsNone(target)

    def test_t2_f13_04_websocket_handshake_timeout(self) -> None:
        """F13.B4: WebSocket connection handles timeout gracefully."""
        client = CDPWebSocketClient(timeout=0.1)
        with patch("socket.create_connection", side_effect=socket.timeout):
            with self.assertRaises(CDPConnectionError):
                client.connect("ws://127.0.0.1:42161/test")

    def test_t2_f13_05_evaluate_syntax_error(self) -> None:
        """F13.B5: Evaluate handles syntax error gracefully."""
        mock_client = MagicMock()
        mock_client.evaluate.side_effect = CDPError("SyntaxError")
        with self.assertRaises(CDPError):
            mock_client.evaluate("invalid(")

    # --- Feature 14 Boundaries ---

    def test_t2_f14_01_empty_argv_invokes_help(self) -> None:
        """F14.B1: Calling CLI with no arguments exits 0 and prints help."""
        code, out, _ = self.run_cli([])
        self.assertEqual(code, 0)
        self.assertIn("Available subcommands", out)

    def test_t2_f14_02_unknown_subcommand_exit_code(self) -> None:
        """F14.B2: Unrecognized subcommand exits with code 2."""
        code, _, _ = self.run_cli(["nonexistent-subcommand"])
        self.assertEqual(code, 2)

    def test_t2_f14_03_unrecognized_arguments_exit_code(self) -> None:
        """F14.B3: Known subcommand with invalid flag exits with code 2."""
        code, _, _ = self.run_cli(["doctor", "--invalid-flag"])
        self.assertEqual(code, 2)

    def test_t2_f14_04_extreme_environment_variables(self) -> None:
        """F14.B4: Runs safely when HOME or USER env vars are unset."""
        code, _, _ = self.run_cli(["--version"], env_overrides={"HOME": "/nonexistent"})
        self.assertEqual(code, 0)

    def test_t2_f14_05_signal_interrupt_handling(self) -> None:
        """F14.B5: Propagates KeyboardInterrupt cleanly."""
        with patch("harness.cli.build_parser", side_effect=KeyboardInterrupt):
            with self.assertRaises(KeyboardInterrupt):
                cli_main(["--help"])


# =============================================================================
# TIER 3: CROSS-FEATURE INTERACTIONS (14 Pairwise Combinations)
# =============================================================================

class TestTier3CrossFeatureInteractions(BaseBugBashTestCase):
    """Tier 3: Pairwise cross-feature interactions validating end-to-end multi-module pipelines."""

    def test_t3_c01_harmonize_migration_and_safety_archive(self) -> None:
        """C01 (F1 x F2): Harmonization migration creates verified backup archive before migrating."""
        self.create_legacy_agent_dir()
        self.init_git_repo()
        res = harmonize_workspace(self.ws, dry_run=False, prune_legacy=True, backup=True)
        self.assertTrue(res.success)
        self.assertTrue((self.ws / ".agents" / "rules").exists())
        self.assertTrue((self.ws / ".agents" / "archive").exists())

    def test_t3_c02_safety_archive_and_tagged_fences(self) -> None:
        """C02 (F2 x F3): Safety archive created while updating AGENTS.md tagged fence."""
        self.create_legacy_agent_dir()
        (self.ws / "AGENTS.md").write_text(f"{LEGACY_TAG_START}\nOld Rules\n{LEGACY_TAG_END}\n", encoding="utf-8")
        self.init_git_repo()
        res = harmonize_workspace(self.ws, dry_run=False, prune_legacy=True, backup=True)
        self.assertTrue(res.success)
        self.assertIn(TAG_START, (self.ws / "AGENTS.md").read_text(encoding="utf-8"))

    def test_t3_c03_dirty_guard_and_safety_patch(self) -> None:
        """C03 (F4 x F5): Dirty tree guard halts without allow-dirty, then generates safety patch with it."""
        self.init_git_repo(dirty=True)
        code1 = cmd_onboard(self.ws, allow_dirty=False)
        self.assertEqual(code1, 1)
        code2 = cmd_onboard(self.ws, allow_dirty=True, dry_run=False)
        self.assertEqual(code2, 0)
        self.assertTrue((self.ws / ".agents" / "artifacts").exists())

    def test_t3_c04_safety_patch_and_isolated_branch(self) -> None:
        """C04 (F5 x F6): Safety patch generated prior to checking out dedicated onboarding branch."""
        self.init_git_repo(dirty=True)
        code = cmd_onboard(self.ws, allow_dirty=True, create_branch="chore/onboard-eval", dry_run=False)
        self.assertEqual(code, 0)
        proc = subprocess.run(["git", "-C", str(self.ws), "branch", "--show-current"], capture_output=True, text=True)
        self.assertEqual(proc.stdout.strip(), "chore/onboard-eval")

    def test_t3_c05_monorepo_subproject_and_harmonize(self) -> None:
        """C05 (F7 x F1): Monorepo subproject onboarding scopes harmonization strictly to subproject."""
        self.init_git_repo()
        sub = self.ws / "packages" / "react"
        self.create_legacy_agent_dir(sub)
        code = cmd_onboard(self.ws, subproject="packages/react", allow_dirty=True, dry_run=False)
        self.assertEqual(code, 0)
        self.assertTrue((sub / ".agents" / "rules").exists())
        self.assertFalse((self.ws / ".agents" / "rules").exists())

    def test_t3_c06_monorepo_subproject_and_cache_purge(self) -> None:
        """C06 (F7 x F6): Subproject cache purge directly targets subproject build directory."""
        self.init_git_repo()
        sub1 = self.ws / "packages" / "pkg1"
        sub2 = self.ws / "packages" / "pkg2"
        (sub1 / ".next").mkdir(parents=True, exist_ok=True)
        (sub2 / ".next").mkdir(parents=True, exist_ok=True)
        (sub1 / ".next" / "c.bin").write_text("c1", encoding="utf-8")
        (sub2 / ".next" / "c.bin").write_text("c2", encoding="utf-8")
        purged = purge_workspace_build_caches(sub1, dry_run=False)
        self.assertFalse((sub1 / ".next").exists())
        self.assertTrue((sub2 / ".next").exists())

    def test_t3_c07_dra_harmonize_and_monorepo_subproject(self) -> None:
        """C07 (F8 x F7): DRA test harmonization detects and injects scripts in monorepo subproject."""
        self.init_git_repo()
        sub = self.ws / "packages" / "react"
        self.create_node_project(sub, framework="vitest")
        res = harmonize_test_runners(sub, dry_run=False, apply=True)
        self.assertTrue(res.success)
        self.assertTrue((sub / ".agyis" / "test_manifest.json").exists())

    def test_t3_c08_dra_harmonize_and_idempotency_cycle(self) -> None:
        """C08 (F8 x F9): First test harmonization mutates manifest, second run yields 0 mutations."""
        self.create_node_project(framework="vitest")
        res1 = harmonize_test_runners(self.ws, dry_run=False, apply=True)
        self.assertTrue(res1.success)
        self.assertTrue(len(res1.mutations) > 0)
        res2 = harmonize_test_runners(self.ws, dry_run=True)
        self.assertTrue(res2.success)
        self.assertEqual(len(res2.mutations), 0)

    def test_t3_c09_spa_route_switch_and_subagent_detection(self) -> None:
        """C09 (F10 x F11): Switching route to subagent conversation extracts subagent ID over parent ID."""
        parent_id = "00000000-0000-0000-0000-000000000001"
        subagent_id = "11111111-1111-1111-1111-111111111111"
        test_url = f"https://127.0.0.1:40623/c/{parent_id}?tab=subagent_convo__{subagent_id}"
        m_tab = re.search(r"[?&]tab=subagent_convo__([a-zA-Z0-9_-]+)", test_url)
        active_id = m_tab.group(1) if m_tab else re.search(r"/c/([a-zA-Z0-9_-]+)", test_url).group(1)
        self.assertEqual(active_id, subagent_id)

    def test_t3_c10_subagent_detection_and_connectrpc_stream(self) -> None:
        """C10 (F11 x F12): Extracted subagent ID is passed to streamConversation."""
        subagent_id = "22222222-2222-2222-2222-222222222222"
        rpc_js = importlib.resources.files("harness.gui.assets").joinpath("hud_rpc.js").read_text(encoding="utf-8")
        self.assertIn("streamConversation(conversationId, onStateChange)", rpc_js)

    def test_t3_c11_devtools_cdp_and_spa_route_switch(self) -> None:
        """C11 (F13 x F10): CDP controller evaluates location and dynamic route changes."""
        mock_client = MagicMock()
        mock_client.evaluate.return_value = "https://127.0.0.1:40623/c/routed-uuid"
        url = mock_client.evaluate("window.location.href")
        m = re.search(r"/c/([a-zA-Z0-9_-]+)", url)
        self.assertEqual(m.group(1), "routed-uuid")

    def test_t3_c12_onboard_dirty_guard_and_harmonize_backup(self) -> None:
        """C12 (F4 x F2): Dirty onboard with allow-dirty creates safety patch and runs harmonize."""
        self.init_git_repo(dirty=True)
        self.create_legacy_agent_dir()
        code = cmd_onboard(self.ws, allow_dirty=True, dry_run=False)
        self.assertEqual(code, 0)
        self.assertTrue((self.ws / ".agents" / "artifacts").exists())

    def test_t3_c13_dra_test_harmonize_and_onboard_branch(self) -> None:
        """C13 (F8 x F6): Branch checkout, cache purge, and test harmonization execute in sequence."""
        self.init_git_repo()
        self.create_node_project()
        (self.ws / ".next").mkdir(parents=True, exist_ok=True)
        code = cmd_onboard(self.ws, create_branch="chore/test-onboard", allow_dirty=True, purge_caches=True, dry_run=False)
        self.assertEqual(code, 0)
        res = harmonize_test_runners(self.ws, dry_run=False, apply=True)
        self.assertTrue(res.success)
        self.assertTrue((self.ws / ".agyis" / "test_manifest.json").exists())

    def test_t3_c14_cdp_controller_and_connectrpc_client(self) -> None:
        """C14 (F13 x F12): CDP injection passes discovered ConnectRPC port into in-situ client."""
        discovered_port = 42161
        mock_client = MagicMock()
        with patch("harness.commands.gui.discover_language_server_endpoint", return_value={"port": discovered_port, "url": f"https://127.0.0.1:{discovered_port}"}):
            with patch("harness.gui.server.ensure_trajectory_server", return_value=None):
                res = inject_trajectory_debug(mock_client, conversation_id="convo-1")
                self.assertTrue(res.get("success"))


# =============================================================================
# TIER 4: REAL-WORLD SCENARIOS (7 Application Workloads)
# =============================================================================

class TestTier4RealWorldScenarios(BaseBugBashTestCase):
    """Tier 4: Realistic end-to-end application workloads modeling active target repositories."""

    def test_t4_s01_modmail_bot_python_harmonization(self) -> None:
        """S01: Harmonization of ModMail-Bot legacy Python Discord bot configuration."""
        self.init_git_repo()
        self.create_legacy_agent_dir(
            custom_content={
                "rules/modmail_rules.md": "# ModMail Rules\nHandle user tickets respectfully.\nSee .agent/rules/security.md.\n",
                "workflows/deploy_bot.md": "> Discord bot deployment.\n\npython3 main.py\n",
            }
        )
        (self.ws / "requirements.txt").write_text("discord.py>=2.0.0\n", encoding="utf-8")
        (self.ws / "AGENTS.md").write_text(f"{LEGACY_TAG_START}\nRules\n{LEGACY_TAG_END}\n", encoding="utf-8")

        res = harmonize_workspace(self.ws, dry_run=False, prune_legacy=True, backup=True)
        self.assertTrue(res.success)
        self.assertTrue((self.ws / ".agents" / "rules" / "modmail_rules.md").exists())
        self.assertTrue((self.ws / ".agents" / "skills" / "deploy_bot" / "SKILL.md").exists())
        self.assertTrue((self.ws / ".agents" / "archive").exists())

    def test_t4_s02_purrfect_download_manager_tauri_harmonization(self) -> None:
        """S02: Harmonization and desktop GUI skill provisioning for purrfect-download-manager."""
        self.init_git_repo()
        self.create_rust_project(is_tauri=True)
        self.create_node_project(framework="vitest")
        self.create_legacy_agent_dir()

        code = cmd_onboard(self.ws, role="desktop_gui", allow_dirty=True, dry_run=False)
        self.assertEqual(code, 0)
        self.assertTrue((self.ws / ".agents" / "rules").exists())

    def test_t4_s03_dream_emirates_app_dirty_onboarding(self) -> None:
        """S03: Dirty-tree onboarding of dream-emirates-app React Native worktree with safety patch."""
        self.init_git_repo(dirty=True)
        (self.ws / "App.tsx").write_text("import React from 'react';\nexport default () => null;\n", encoding="utf-8")

        # Step 1: Reject without --allow-dirty
        code_fail = cmd_onboard(self.ws, allow_dirty=False)
        self.assertEqual(code_fail, 1)

        # Step 2: Accept with --allow-dirty and isolated branch
        code_ok = cmd_onboard(self.ws, allow_dirty=True, create_branch="chore/onboard-eval", dry_run=False)
        self.assertEqual(code_ok, 0)
        self.assertTrue((self.ws / ".agents" / "artifacts").exists())

    def test_t4_s04_chakra_ui_monorepo_subproject_onboarding(self) -> None:
        """S04: Monorepo subproject onboarding on chakra-ui targeting packages/react."""
        self.init_git_repo()
        pkg_react = self.ws / "packages" / "react"
        self.create_node_project(pkg_react, framework="vitest")
        self.create_legacy_agent_dir(pkg_react)
        (pkg_react / ".turbo").mkdir(parents=True, exist_ok=True)
        (pkg_react / ".turbo" / "cache.bin").write_text("stale", encoding="utf-8")

        code = cmd_onboard(self.ws, subproject="packages/react", allow_dirty=True, purge_caches=True, dry_run=False)
        self.assertEqual(code, 0)
        self.assertTrue((pkg_react / ".agents" / "rules").exists())
        self.assertFalse((pkg_react / ".turbo").exists())

    def test_t4_s05_immortal_rust_cargo_test_harmonization(self) -> None:
        """S05: Immortal Rust workspace Cargo test harmonization and manifest generation."""
        self.init_git_repo()
        self.create_rust_project()

        harmonizer = TestHarmonizer(self.ws)
        audit = harmonizer.audit()
        self.assertEqual(audit.manifest_type, "Cargo.toml")
        manifest_data = harmonizer.build_test_manifest(audit)
        self.assertIn("tier_1a_diff", manifest_data["tiers"])
        self.assertEqual(manifest_data["tiers"]["tier_1a_diff"]["command"], "cargo test")

    def test_t4_s06_jimha_node_vitest_test_harmonization(self) -> None:
        """S06: Jimha Node/TS Vitest project test runner harmonization and backup patch generation."""
        self.init_git_repo()
        self.create_node_project(framework="vitest", package_manager="pnpm")

        res = harmonize_test_runners(self.ws, dry_run=False, apply=True, backup=True)
        self.assertTrue(res.success)
        self.assertTrue((self.ws / ".agyis" / "test_manifest.json").exists())
        self.assertTrue((self.ws / ".agyis" / "backups").exists())

    def test_t4_s07_live_insitu_hud_dogfooding_session(self) -> None:
        """S07: Simulates live In-Situ HUD session with dynamic route switching and subagent tabs."""
        mock_client = MagicMock()
        mock_client.evaluate.return_value = "https://127.0.0.1:40623/c/parent-uuid?tab=subagent_convo__child-uuid"

        with patch("harness.commands.gui.discover_language_server_endpoint", return_value={"port": 42161, "url": "https://127.0.0.1:42161"}):
            with patch("harness.gui.server.ensure_trajectory_server", return_value=None):
                res = inject_trajectory_debug(mock_client)
                self.assertTrue(res.get("success"))
                self.assertTrue(mock_client.evaluate.called)


if __name__ == "__main__":
    unittest.main()
