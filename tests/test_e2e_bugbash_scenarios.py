#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Arafat Zahan (@kuasha420)
# Corporate Stewardship & Infrastructure: Purrfect Software Limited (PSL)
# Governed by: ICARO-42/b Ordinance (Company-Supported Personal IP Framework)

"""
Bug Bash Tier 3 Cross-Feature Interactions & Tier 4 Real-World Onboarding Scenarios.
Split from test_e2e_bugbash.py for sub-second ADR-015 verification.
"""

from __future__ import annotations

import subprocess
import unittest

from harness.commands.onboard import cmd_onboard
from harness.delivery.cache import purge_workspace_build_caches
from harness.delivery.harmonize import harmonize_workspace
from harness.delivery.workspace import LEGACY_TAG_END, LEGACY_TAG_START, TAG_START
from harness.harmonize.test_runner import TestHarmonizer, harmonize_test_runners
from tests.test_e2e_bugbash import BaseBugBashTestCase


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
        purge_workspace_build_caches(sub1, dry_run=False)
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


class TestTier4RealWorldScenarios(BaseBugBashTestCase):
    """Tier 4: Realistic end-to-end application workloads modeling project onboarding."""

    def test_t4_s01_python_bot_harmonization(self) -> None:
        """S01: Harmonization of Python bot legacy configuration."""
        self.init_git_repo()
        self.create_legacy_agent_dir(
            custom_content={
                "rules/bot_rules.md": "# Bot Rules\nHandle user tickets respectfully.\nSee .agent/rules/security.md.\n",
                "workflows/deploy_bot.md": "> Bot deployment.\n\npython3 main.py\n",
            }
        )
        (self.ws / "requirements.txt").write_text("discord.py>=2.0.0\n", encoding="utf-8")
        (self.ws / "AGENTS.md").write_text(f"{LEGACY_TAG_START}\nRules\n{LEGACY_TAG_END}\n", encoding="utf-8")

        res = harmonize_workspace(self.ws, dry_run=False, prune_legacy=True, backup=True)
        self.assertTrue(res.success)
        self.assertTrue((self.ws / ".agents" / "rules" / "bot_rules.md").exists())
        self.assertTrue((self.ws / ".agents" / "skills" / "deploy_bot" / "SKILL.md").exists())
        self.assertTrue((self.ws / ".agents" / "archive").exists())

    def test_t4_s02_tauri_desktop_harmonization(self) -> None:
        """S02: Harmonization and desktop GUI skill provisioning for hybrid Tauri workspace."""
        self.init_git_repo()
        self.create_rust_project(is_tauri=True)
        self.create_node_project(framework="vitest")
        self.create_legacy_agent_dir()

        code = cmd_onboard(self.ws, role="desktop_gui", allow_dirty=True, dry_run=False)
        self.assertEqual(code, 0)
        self.assertTrue((self.ws / ".agents" / "rules").exists())

    def test_t4_s03_mobile_app_dirty_onboarding(self) -> None:
        """S03: Dirty-tree onboarding of React Native worktree with safety patch."""
        self.init_git_repo(dirty=True)
        (self.ws / "App.tsx").write_text("import React from 'react';\nexport default () => null;\n", encoding="utf-8")

        code_fail = cmd_onboard(self.ws, allow_dirty=False)
        self.assertEqual(code_fail, 1)

        code_ok = cmd_onboard(self.ws, allow_dirty=True, create_branch="chore/onboard-eval", dry_run=False)
        self.assertEqual(code_ok, 0)
        self.assertTrue((self.ws / ".agents" / "artifacts").exists())

    def test_t4_s04_monorepo_subproject_onboarding(self) -> None:
        """S04: Monorepo subproject onboarding targeting packages/react."""
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

    def test_t4_s05_rust_cargo_test_harmonization(self) -> None:
        """S05: Rust workspace Cargo test harmonization and manifest generation."""
        self.init_git_repo()
        self.create_rust_project()

        harmonizer = TestHarmonizer(self.ws)
        audit = harmonizer.audit()
        self.assertEqual(audit.manifest_type, "Cargo.toml")
        manifest_data = harmonizer.build_test_manifest(audit)
        self.assertIn("tier_1a_diff", manifest_data["tiers"])
        self.assertEqual(manifest_data["tiers"]["tier_1a_diff"]["command"], "cargo test")

    def test_t4_s06_node_vitest_test_harmonization(self) -> None:
        """S06: Node/TS Vitest project test runner harmonization and backup patch generation."""
        self.init_git_repo()
        self.create_node_project(framework="vitest", package_manager="pnpm")

        res = harmonize_test_runners(self.ws, dry_run=False, apply=True, backup=True)
        self.assertTrue(res.success)
        self.assertTrue((self.ws / ".agyis" / "test_manifest.json").exists())
        self.assertTrue((self.ws / ".agyis" / "backups").exists())


if __name__ == "__main__":
    unittest.main()
