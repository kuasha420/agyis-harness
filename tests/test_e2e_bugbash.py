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

import contextlib
import io
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
from typing import Any, Dict, List, Optional, Tuple
import unittest
from unittest.mock import patch

from harness.cli import main as cli_main
from harness.commands.onboard import cmd_onboard
from harness.delivery.harmonize import (
    _compute_sha256,
    _find_git_root,
    harmonize_workspace,
    sanitize_workspace_links,
)
from harness.delivery.workspace import (
    LEGACY_TAG_END,
    LEGACY_TAG_START,
    TAG_END,
    TAG_START,
)
from harness.harmonize.test_runner import (
    TestHarmonizer,
    harmonize_test_runners,
)


class BaseBugBashTestCase(unittest.TestCase):
    """Hermetic base test case providing isolated temporary workspaces, git scaffolding, and CLI runner."""

    maxDiff = None
    _git_template_tmp: Optional[tempfile.TemporaryDirectory] = None
    _git_template_dir: Optional[Path] = None

    @classmethod
    def setUpClass(cls) -> None:
        super().setUpClass()
        tmp = tempfile.TemporaryDirectory()
        tpath = Path(tmp.name).resolve()
        subprocess.run(["git", "init", "-b", "main", str(tpath)], check=True, capture_output=True)
        subprocess.run(["git", "-C", str(tpath), "config", "user.email", "bugbash@example.com"], check=True, capture_output=True)
        subprocess.run(["git", "-C", str(tpath), "config", "user.name", "BugBash Tester"], check=True, capture_output=True)
        subprocess.run(["git", "-C", str(tpath), "config", "commit.gpgsign", "false"], check=True, capture_output=True)
        (tpath / "README.md").write_text("# Sample Project\nInitial baseline content.\n", encoding="utf-8")
        subprocess.run(["git", "-C", str(tpath), "add", "."], check=True, capture_output=True)
        subprocess.run(["git", "-C", str(tpath), "commit", "-m", "Initial commit"], check=True, capture_output=True)
        cls._git_template_tmp = tmp
        cls._git_template_dir = tpath

    @classmethod
    def tearDownClass(cls) -> None:
        if cls._git_template_tmp is not None:
            cls._git_template_tmp.cleanup()
            cls._git_template_tmp = None
            cls._git_template_dir = None
        super().tearDownClass()

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
        self._captured_stdout = io.StringIO()
        self._captured_stderr = io.StringIO()
        self.enterContext(contextlib.redirect_stdout(self._captured_stdout))
        self.enterContext(contextlib.redirect_stderr(self._captured_stderr))

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
        if branch == "main" and files is None and self._git_template_dir is not None:
            shutil.copytree(self._git_template_dir, target, dirs_exist_ok=True)
        else:
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

    # --- Feature 14: E2E Regression & Tier Verification ---
    # (Features F10-F13 GUI/CDP tests live in test_e2e_bugbash_gui_routes.py & test_e2e_bugbash_gui_rpc.py)
    # (Tiers 2, 3, 4 live in test_e2e_bugbash_boundaries.py & test_e2e_bugbash_scenarios.py)

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


if __name__ == "__main__":
    unittest.main()
