#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Arafat Zahan (@kuasha420)
# Corporate Stewardship & Infrastructure: Purrfect Software Limited (PSL)
# Governed by: ICARO-42/b Ordinance (Company-Supported Personal IP Framework)

"""
Hermetic unit and integration tests for PSL Harness Delivery & Plugin Installer (ADR-030).

Validates:
- DeliveryMode.SYMLINK and DeliveryMode.COPY installations
- File packaging filters (ADR-014 Product vs. Project Bifurcation)
- Path safety guards against deleting REPO_ROOT
- Dry-run modes and idempotent re-installations
- Safe uninstallation without collateral damage
- CoexistenceEngine 3-layer resource precedence (Layer 3 > Layer 2 > Layer 1)
- Zero Git Pollution verification
- CLI subcommands `psl install` and `psl uninstall`
"""

from __future__ import annotations

import io
import json
import os
from pathlib import Path
import shutil
import tempfile
import unittest
from unittest.mock import patch

from harness.cli import main
from harness.delivery import (
    GIT_EXCLUDE_PATTERNS,
    REPO_ROOT,
    SYNC_SURFACE_ITEMS,
    CoexistenceEngine,
    DeliveryMode,
    DeliveryResult,
    PluginInstaller,
    configure_git_exclude,
    find_workspace_root,
    install_workspace,
    sync_surfaces,
)


class TestPluginDelivery(unittest.TestCase):
    """Test suite for PluginInstaller and CoexistenceEngine."""

    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.isolated_base = Path(self.temp_dir.name)
        # Always install strictly to a subfolder inside temp
        self.target_dir = self.isolated_base / "installed_plugin"
        self.bin_dir = self.isolated_base / "bin"
        self.aux_bin_1 = self.isolated_base / "gemini" / "antigravity" / "bin"
        self.aux_bin_2 = self.isolated_base / "gemini" / "antigravity-cli" / "bin"
        self.orig_bin_dir = os.environ.get("PSL_BIN_DIR")
        os.environ["PSL_BIN_DIR"] = str(self.bin_dir)
        self.orig_aux_bin_dirs = os.environ.get("PSL_AUX_BIN_DIRS")
        os.environ["PSL_AUX_BIN_DIRS"] = f"{self.aux_bin_1}:{self.aux_bin_2}"

    def tearDown(self) -> None:
        if self.orig_bin_dir is not None:
            os.environ["PSL_BIN_DIR"] = self.orig_bin_dir
        else:
            os.environ.pop("PSL_BIN_DIR", None)

        if self.orig_aux_bin_dirs is not None:
            os.environ["PSL_AUX_BIN_DIRS"] = self.orig_aux_bin_dirs
        else:
            os.environ.pop("PSL_AUX_BIN_DIRS", None)

        self.temp_dir.cleanup()

    def test_symlink_installation_and_validation(self) -> None:
        """Symlink installation creates valid link to source and passes is_installed."""
        installer = PluginInstaller(source_dir=REPO_ROOT, default_target_dir=self.target_dir)

        result = installer.install(mode=DeliveryMode.SYMLINK)
        self.assertTrue(result.success)
        self.assertEqual(result.mode, "symlink")
        self.assertTrue(self.target_dir.is_symlink())
        self.assertEqual(self.target_dir.resolve(), REPO_ROOT.resolve())

        # Validation
        self.assertTrue(installer.is_installed(self.target_dir))
        info = installer.get_install_info(self.target_dir)
        self.assertTrue(info["installed"])
        self.assertEqual(info["mode"], "symlink")
        self.assertIn("plugin.json", info["items"])

    def test_copy_installation_and_file_integrity(self) -> None:
        """Copy installation packages distributable files and passes integrity checks."""
        installer = PluginInstaller(source_dir=REPO_ROOT, default_target_dir=self.target_dir)

        result = installer.install(mode=DeliveryMode.COPY)
        self.assertTrue(result.success)
        self.assertEqual(result.mode, "copy")
        self.assertFalse(self.target_dir.is_symlink())
        self.assertTrue(self.target_dir.is_dir())

        # Distributables present
        self.assertTrue((self.target_dir / "plugin.json").is_file())
        self.assertTrue((self.target_dir / "harness").is_dir())
        self.assertTrue((self.target_dir / "matrix.json").is_file())
        self.assertTrue((self.target_dir / "hooks.json").is_file())
        self.assertTrue((self.target_dir / "skills").is_dir())
        self.assertTrue((self.target_dir / "agents").is_dir())
        self.assertTrue((self.target_dir / "rules").is_dir())

        self.assertTrue(installer.is_installed(self.target_dir))
        info = installer.get_install_info(self.target_dir)
        self.assertTrue(info["installed"])
        self.assertEqual(info["mode"], "copy")
        self.assertEqual(info["version"], "0.1.0")

    def test_dry_run_mode(self) -> None:
        """Dry-run mode does not mutate disk for install or uninstall."""
        installer = PluginInstaller(source_dir=REPO_ROOT, default_target_dir=self.target_dir)

        # 1. Install dry-run
        res_inst = installer.install(mode=DeliveryMode.COPY, dry_run=True)
        self.assertTrue(res_inst.success)
        self.assertFalse(self.target_dir.exists())
        self.assertFalse(installer.is_installed(self.target_dir))

        # 2. Actual install
        installer.install(mode=DeliveryMode.COPY, dry_run=False)
        self.assertTrue(self.target_dir.exists())

        # 3. Uninstall dry-run
        res_un = installer.uninstall(dry_run=True)
        self.assertTrue(res_un.success)
        self.assertTrue(self.target_dir.exists())

    def test_idempotent_reinstallation(self) -> None:
        """Repeated install calls overwrite cleanly and succeed idempotently."""
        installer = PluginInstaller(source_dir=REPO_ROOT, default_target_dir=self.target_dir)

        # Symlink then symlink
        r1 = installer.install(mode=DeliveryMode.SYMLINK)
        self.assertTrue(r1.success)
        r2 = installer.install(mode=DeliveryMode.SYMLINK)
        self.assertTrue(r2.success)
        self.assertTrue(self.target_dir.is_symlink())

        # Copy over symlink
        r3 = installer.install(mode=DeliveryMode.COPY)
        self.assertTrue(r3.success)
        self.assertFalse(self.target_dir.is_symlink())
        self.assertTrue(self.target_dir.is_dir())

        # Copy over copy
        r4 = installer.install(mode=DeliveryMode.COPY)
        self.assertTrue(r4.success)
        self.assertTrue(installer.is_installed(self.target_dir))

    def test_uninstall_symlink_and_copy(self) -> None:
        """Uninstall cleans destination without collateral damage to source repo."""
        installer = PluginInstaller(source_dir=REPO_ROOT, default_target_dir=self.target_dir)

        # 1. Symlink uninstall
        installer.install(mode=DeliveryMode.SYMLINK)
        self.assertTrue(self.target_dir.is_symlink())
        res_un_sym = installer.uninstall()
        self.assertTrue(res_un_sym.success)
        self.assertFalse(self.target_dir.exists())
        self.assertTrue(REPO_ROOT.exists(), "Source REPO_ROOT must never be touched")

        # 2. Copy uninstall
        installer.install(mode=DeliveryMode.COPY)
        self.assertTrue(self.target_dir.is_dir())
        res_un_copy = installer.uninstall()
        self.assertTrue(res_un_copy.success)
        self.assertFalse(self.target_dir.exists())
        self.assertTrue(REPO_ROOT.exists(), "Source REPO_ROOT must never be touched")

    def test_path_safety_guard_rejects_repo_root_or_parent(self) -> None:
        """Targeting REPO_ROOT or an ancestor raises ValueError to prevent deletion."""
        # 1. Target equals source root
        with self.assertRaises(ValueError):
            PluginInstaller(source_dir=REPO_ROOT, default_target_dir=REPO_ROOT)

        # 2. Target contains source root (parent directory)
        with self.assertRaises(ValueError):
            PluginInstaller(source_dir=REPO_ROOT, default_target_dir=REPO_ROOT.parent)

        installer = PluginInstaller(source_dir=REPO_ROOT, default_target_dir=self.target_dir)
        with self.assertRaises(ValueError):
            installer.install(target_dir=REPO_ROOT)

        with self.assertRaises(ValueError):
            installer.uninstall(target_dir=REPO_ROOT)

    def test_product_vs_project_exclusions(self) -> None:
        """Project files (pipeline/, tests/, data/, docs/) are strictly excluded from package."""
        installer = PluginInstaller(source_dir=REPO_ROOT, default_target_dir=self.target_dir)
        installer.install(mode=DeliveryMode.COPY)

        # Excluded directories must NOT exist in copied package
        for excluded in ("pipeline", "tests", "data", "docs", "scratch", ".git"):
            self.assertFalse(
                (self.target_dir / excluded).exists(),
                f"Project artifact '{excluded}' should NOT be packaged into plugin",
            )

        # Pycache files must be pruned
        pyc_matches = list((self.target_dir / "harness").rglob("*.pyc"))
        self.assertEqual(len(pyc_matches), 0, "No .pyc files should be copied into package")

    def test_coexistence_precedence_hierarchy(self) -> None:
        """Resource resolution adheres strictly to Layer 3 (Workspace) > Layer 2 (User) > Layer 1 (Plugin)."""
        ws_dir = self.isolated_base / "workspace"
        user_dir = self.isolated_base / "user"
        plugin_dir = self.isolated_base / "plugin"

        ws_dir.mkdir(parents=True)
        user_dir.mkdir(parents=True)
        plugin_dir.mkdir(parents=True)

        engine = CoexistenceEngine(
            workspace_root=ws_dir,
            user_dir=user_dir,
            plugin_dir=plugin_dir,
        )

        # 1. Only in Layer 1 (Plugin)
        p_agent = plugin_dir / "harness" / "agents" / "specialist.md"
        p_agent.parent.mkdir(parents=True, exist_ok=True)
        p_agent.write_text("layer 1", encoding="utf-8")

        res1 = engine.resolve_resource("agent", "specialist")
        self.assertTrue(res1["found"])
        self.assertEqual(res1["layer"], 1)
        self.assertEqual(res1["layer_name"], "plugin")
        self.assertEqual(res1["path"], p_agent)

        # 2. Override in Layer 2 (User)
        u_agent = user_dir / "agents" / "specialist.md"
        u_agent.parent.mkdir(parents=True, exist_ok=True)
        u_agent.write_text("layer 2", encoding="utf-8")

        res2 = engine.resolve_resource("agent", "specialist")
        self.assertTrue(res2["found"])
        self.assertEqual(res2["layer"], 2)
        self.assertEqual(res2["layer_name"], "user")
        self.assertEqual(res2["path"], u_agent)

        # 3. Override in Layer 3 (Workspace)
        w_agent = ws_dir / ".agents" / "agents" / "specialist.md"
        w_agent.parent.mkdir(parents=True, exist_ok=True)
        w_agent.write_text("layer 3", encoding="utf-8")

        res3 = engine.resolve_resource("agent", "specialist")
        self.assertTrue(res3["found"])
        self.assertEqual(res3["layer"], 3)
        self.assertEqual(res3["layer_name"], "workspace")
        self.assertEqual(res3["path"], w_agent)

        # 4. Non-existent resource
        res4 = engine.resolve_resource("agent", "non_existent")
        self.assertFalse(res4["found"])
        self.assertIsNone(res4["layer"])

    def test_zero_git_pollution_verification(self) -> None:
        """verify_zero_git_pollution catches runtime debris and passes clean workspaces."""
        ws_dir = self.isolated_base / "pollute_test"
        ws_dir.mkdir()

        engine = CoexistenceEngine(workspace_root=ws_dir)

        # Clean workspace
        self.assertEqual(engine.verify_zero_git_pollution(ws_dir), [])

        # Polluted workspace with forbidden debris
        (ws_dir / "telemetry.db").touch()
        (ws_dir / "verification_state_test.json").touch()
        (ws_dir / "debris.pyc").touch()

        pollution = engine.verify_zero_git_pollution(ws_dir)
        self.assertIn("telemetry.db", pollution)
        self.assertIn("verification_state_test.json", pollution)
        self.assertIn("debris.pyc", pollution)

    def test_cli_install_and_uninstall_commands(self) -> None:
        """CLI `psl install` and `psl uninstall` work cleanly with JSON and flags."""
        # 1. CLI dry-run install
        with patch("sys.stdout", new_callable=io.StringIO) as mock_out:
            code = main(["install", "--target", str(self.target_dir), "--dry-run", "--json"])
            self.assertEqual(code, 0)
            data = json.loads(mock_out.getvalue().strip())
            self.assertTrue(data["success"])
            self.assertEqual(data["mode"], "symlink")
            self.assertFalse(self.target_dir.exists())

        # 1b. CLI --global flag works cleanly
        with patch("sys.stdout", new_callable=io.StringIO) as mock_out:
            code = main(["install", "--global", "--target", str(self.target_dir), "--dry-run", "--json"])
            self.assertEqual(code, 0)
            data = json.loads(mock_out.getvalue().strip())
            self.assertTrue(data["success"])

        # 2. CLI copy install
        with patch("sys.stdout", new_callable=io.StringIO) as mock_out:
            code = main(["install", "--target", str(self.target_dir), "--copy", "--json"])
            self.assertEqual(code, 0)
            data = json.loads(mock_out.getvalue().strip())
            self.assertTrue(data["success"])
            self.assertEqual(data["mode"], "copy")
            self.assertTrue(self.target_dir.is_dir())

        # 3. CLI uninstall
        with patch("sys.stdout", new_callable=io.StringIO) as mock_out:
            code = main(["uninstall", "--target", str(self.target_dir), "--json"])
            self.assertEqual(code, 0)
            data = json.loads(mock_out.getvalue().strip())
            self.assertTrue(data["success"])
            self.assertFalse(self.target_dir.exists())

    def test_install_creates_global_bin(self) -> None:
        """Plugin installation creates executable agyis and psl launchers in bin_dir, removed on uninstall."""
        import stat
        installer = PluginInstaller(
            source_dir=REPO_ROOT,
            default_target_dir=self.target_dir,
            bin_dir=self.bin_dir,
        )

        res = installer.install(mode=DeliveryMode.SYMLINK)
        self.assertTrue(res.success)
        agyis_bin = self.bin_dir / "agyis"
        psl_bin = self.bin_dir / "psl"
        self.assertTrue(agyis_bin.is_file())
        self.assertTrue(psl_bin.is_file())
        file_mode_agyis = stat.S_IMODE(agyis_bin.stat().st_mode)
        file_mode_psl = stat.S_IMODE(psl_bin.stat().st_mode)
        self.assertEqual(file_mode_agyis & 0o755, 0o755)
        self.assertEqual(file_mode_psl & 0o755, 0o755)

        agyis_content = agyis_bin.read_text(encoding="utf-8")
        self.assertIn("from harness.cli import main", agyis_content)
        self.assertIn("sys.exit(main())", agyis_content)

        psl_content = psl_bin.read_text(encoding="utf-8")
        self.assertIn("from harness.cli import main, deprecated_psl_main", psl_content)
        self.assertIn("sys.exit(deprecated_psl_main())", psl_content)

        # Uninstall removes both launchers
        res_un = installer.uninstall()
        self.assertTrue(res_un.success)
        self.assertFalse(agyis_bin.exists())
        self.assertFalse(psl_bin.exists())

    def test_install_cli_global_flag(self) -> None:
        """CLI `psl install --global` installs into bin_dir."""
        with patch("sys.stdout", new_callable=io.StringIO) as mock_out:
            code = main([
                "install",
                "--target", str(self.target_dir),
                "--bin-dir", str(self.bin_dir),
                "--global",
                "--json",
            ])
            self.assertEqual(code, 0)
            data = json.loads(mock_out.getvalue().strip())
            self.assertTrue(data["success"])
            agyis_bin = self.bin_dir / "agyis"
            psl_bin = self.bin_dir / "psl"
            self.assertTrue(agyis_bin.is_file())
            self.assertTrue(psl_bin.is_file())

        with patch("sys.stdout", new_callable=io.StringIO) as mock_out:
            code = main([
                "uninstall",
                "--target", str(self.target_dir),
                "--bin-dir", str(self.bin_dir),
                "--json",
            ])
            self.assertEqual(code, 0)
            self.assertFalse(agyis_bin.exists())
            self.assertFalse(psl_bin.exists())

    def test_install_and_uninstall_auxiliary_launchers(self) -> None:
        """Verifies _install_bin deploys auxiliary launchers in test environment and uninstall cleans them up."""
        import stat
        installer = PluginInstaller(
            source_dir=REPO_ROOT,
            default_target_dir=self.target_dir,
            bin_dir=self.bin_dir,
            aux_bin_dirs=[self.aux_bin_1, self.aux_bin_2],
        )

        res = installer.install(mode=DeliveryMode.SYMLINK)
        self.assertTrue(res.success)

        primary_agyis = self.bin_dir / "agyis"
        primary_psl = self.bin_dir / "psl"
        self.assertTrue(primary_agyis.is_file())
        self.assertTrue(primary_psl.is_file())

        aux_agyis_1 = self.aux_bin_1 / "agyis"
        aux_psl_1 = self.aux_bin_1 / "psl"
        aux_agyis_2 = self.aux_bin_2 / "agyis"
        aux_psl_2 = self.aux_bin_2 / "psl"
        self.assertTrue(aux_agyis_1.is_file())
        self.assertTrue(aux_psl_1.is_file())
        self.assertTrue(aux_agyis_2.is_file())
        self.assertTrue(aux_psl_2.is_file())

        self.assertEqual(stat.S_IMODE(aux_agyis_1.stat().st_mode) & 0o755, 0o755)
        self.assertEqual(stat.S_IMODE(aux_psl_1.stat().st_mode) & 0o755, 0o755)
        self.assertEqual(stat.S_IMODE(aux_agyis_2.stat().st_mode) & 0o755, 0o755)
        self.assertEqual(stat.S_IMODE(aux_psl_2.stat().st_mode) & 0o755, 0o755)

        content = aux_psl_1.read_text(encoding="utf-8")
        self.assertIn("from harness.cli import main", content)
        self.assertIn("sys.exit(deprecated_psl_main())", content)

        res_un = installer.uninstall()
        self.assertTrue(res_un.success)
        self.assertFalse(primary_agyis.exists())
        self.assertFalse(primary_psl.exists())
        self.assertFalse(aux_agyis_1.exists())
        self.assertFalse(aux_psl_1.exists())
        self.assertFalse(aux_agyis_2.exists())
        self.assertFalse(aux_psl_2.exists())

    def test_sync_surfaces_clean_and_idempotent(self) -> None:
        """sync_surfaces idempotently links surface items to canonical config."""
        fake_cfg = self.isolated_base / "fake_config"
        surf_1 = self.isolated_base / "surface_1"
        surf_2 = self.isolated_base / "surface_2"

        # Pre-populate surface_1 / agents with a custom file to test migration
        (surf_1 / "agents").mkdir(parents=True)
        (surf_1 / "agents" / "migrated.md").write_text("# Migrated\n", encoding="utf-8")

        # First pass
        results = sync_surfaces(surfaces=[surf_1, surf_2], config_dir=fake_cfg)
        self.assertTrue(len(results) > 0)

        # File was migrated to canonical config
        self.assertTrue((fake_cfg / "agents" / "migrated.md").is_file())

        for surface in (surf_1, surf_2):
            for item in SYNC_SURFACE_ITEMS:
                item_link = surface / item
                self.assertTrue(item_link.is_symlink())
                self.assertEqual(item_link.resolve(), (fake_cfg / item).resolve())

        # Second pass (idempotent)
        second_results = sync_surfaces(surfaces=[surf_1, surf_2], config_dir=fake_cfg)
        for r in second_results:
            self.assertEqual(r["status"], "already_linked")

    def test_find_workspace_root_standard_and_worktree(self) -> None:
        """find_workspace_root discovers root for standard git and worktree pointer files."""
        # 1. Standard git directory
        repo_dir = self.isolated_base / "std_repo"
        (repo_dir / ".git").mkdir(parents=True)
        sub_dir = repo_dir / "pkg" / "src"
        sub_dir.mkdir(parents=True)

        found = find_workspace_root(sub_dir)
        self.assertEqual(found, repo_dir)

        # 2. Worktree pointer file
        main_repo = self.isolated_base / "main_repo"
        (main_repo / ".git" / "worktrees" / "wt1").mkdir(parents=True)

        wt_dir = self.isolated_base / "wt_worktree"
        wt_dir.mkdir(parents=True)
        (wt_dir / ".git").write_text(f"gitdir: {main_repo}/.git/worktrees/wt1\n", encoding="utf-8")
        wt_sub = wt_dir / "nested" / "module"
        wt_sub.mkdir(parents=True)

        found_wt = find_workspace_root(wt_sub)
        self.assertEqual(found_wt, wt_dir)

    def test_configure_git_exclude_standard_and_worktree(self) -> None:
        """configure_git_exclude appends required patterns to .git/info/exclude idempotently."""
        # 1. Standard repo
        std_repo = self.isolated_base / "exclude_std"
        (std_repo / ".git").mkdir(parents=True)

        exclude_file = configure_git_exclude(std_repo)
        self.assertTrue(exclude_file.is_file())
        content = exclude_file.read_text(encoding="utf-8")
        for pat in GIT_EXCLUDE_PATTERNS:
            self.assertIn(pat, content)

        # Calling again does not duplicate patterns
        configure_git_exclude(std_repo)
        lines = [line.strip() for line in exclude_file.read_text(encoding="utf-8").splitlines() if line.strip()]
        for pat in GIT_EXCLUDE_PATTERNS:
            self.assertEqual(lines.count(pat), 1)

        # 2. Worktree layout
        main_git = self.isolated_base / "wt_exclude_main" / ".git"
        (main_git / "worktrees" / "wt_branch").mkdir(parents=True)
        wt_root = self.isolated_base / "wt_exclude_child"
        wt_root.mkdir(parents=True)
        (wt_root / ".git").write_text(f"gitdir: {main_git}/worktrees/wt_branch\n", encoding="utf-8")

        wt_exclude_file = configure_git_exclude(wt_root)
        self.assertEqual(wt_exclude_file, main_git / "info" / "exclude")
        wt_content = wt_exclude_file.read_text(encoding="utf-8")
        for pat in GIT_EXCLUDE_PATTERNS:
            self.assertIn(pat, wt_content)

    def test_single_source_agent_delivery(self) -> None:
        """Plugin installation purges duplicate standalone agents in ~/.gemini/config/agents/."""
        fake_cfg = self.isolated_base / "cfg_single_source"
        fake_agents = fake_cfg / "agents"
        fake_agents.mkdir(parents=True)

        # Standalone agent duplicate
        dup_agent = fake_agents / "harness_builder.md"
        dup_agent.write_text("# Duplicate Standalone Agent\n", encoding="utf-8")

        # Independent custom agent
        user_agent = fake_agents / "custom-operator.md"
        user_agent.write_text("# User Custom Agent\n", encoding="utf-8")

        installer = PluginInstaller(
            source_dir=REPO_ROOT,
            default_target_dir=self.target_dir,
            config_dir=fake_cfg,
        )

        res = installer.install(mode=DeliveryMode.COPY)
        self.assertTrue(res.success)
        # Duplicate removed
        self.assertIn(str(dup_agent), res.duplicates_removed)
        self.assertFalse(dup_agent.exists())
        # Non-colliding user agent remains intact
        self.assertTrue(user_agent.exists())
        # Single source exists inside plugin directory
        self.assertTrue((self.target_dir / "agents" / "harness_builder.md").exists())

    def test_uninstall_clean_surfaces(self) -> None:
        """Uninstall with clean_surfaces=True unlinks surface symlinks without touching config."""
        fake_cfg = self.isolated_base / "uninstall_cfg"
        surf = self.isolated_base / "uninstall_surf"

        installer = PluginInstaller(
            source_dir=REPO_ROOT,
            default_target_dir=self.target_dir,
            config_dir=fake_cfg,
            surfaces=[surf],
        )

        installer.install(mode=DeliveryMode.SYMLINK, all_surfaces=True)
        self.assertTrue((surf / "agents").is_symlink())

        installer.uninstall(clean_surfaces=True)
        self.assertFalse((surf / "agents").exists())
        self.assertFalse((surf / "agents").is_symlink())
        # Canonical config remains intact
        self.assertTrue((fake_cfg / "agents").is_dir())

    def test_tagged_rules_insertion_and_idempotence(self) -> None:
        """Workspace AGENTS.md preserves domain rules and manages tagged block idempotently."""
        ws_dir = self.isolated_base / "workspace_jasper"
        ws_dir.mkdir(parents=True)
        rules_file = ws_dir / "AGENTS.md"

        # Pre-existing project rules
        initial_rules = (
            "# Jasper Project Rules\n\n"
            "- Wait 10 minutes before merging PRs to allow CI fences to settle.\n"
            "- Always target staging branch.\n"
        )
        rules_file.write_text(initial_rules, encoding="utf-8")

        # 1. Initial install_workspace
        res1 = install_workspace(ws_dir, source_dir=REPO_ROOT)
        self.assertTrue(res1.success)
        self.assertTrue(res1.rules_updated)

        updated_content = rules_file.read_text(encoding="utf-8")
        self.assertIn("- Wait 10 minutes before merging PRs", updated_content)
        self.assertIn("- Always target staging branch.", updated_content)
        self.assertIn("<!-- Added by AGYIS-HARNESS -->", updated_content)
        self.assertIn("<!-- End AGYIS-HARNESS -->", updated_content)
        self.assertNotIn("<!-- Added by PSL-HARNESS -->", updated_content)
        self.assertNotIn("<!-- End PSL-HARNESS -->", updated_content)

        # 2. Idempotent re-run
        res2 = install_workspace(ws_dir, source_dir=REPO_ROOT)
        self.assertTrue(res2.success)
        self.assertFalse(res2.rules_updated)

        re_read_content = rules_file.read_text(encoding="utf-8")
        self.assertEqual(re_read_content, updated_content)
        self.assertEqual(re_read_content.count("<!-- Added by AGYIS-HARNESS -->"), 1)
        self.assertEqual(re_read_content.count("<!-- End AGYIS-HARNESS -->"), 1)
        self.assertEqual(re_read_content.count("<!-- Added by PSL-HARNESS -->"), 0)
        self.assertEqual(re_read_content.count("<!-- End PSL-HARNESS -->"), 0)

    def test_workspace_stack_instantiation_and_dedup(self) -> None:
        """Workspace install auto-detects stack, installs stack skills, and respects dedup."""
        ws_dir = self.isolated_base / "workspace_ts"
        ws_dir.mkdir(parents=True)
        (ws_dir / "package.json").write_text(
            json.dumps({"name": "test-ts-app", "devDependencies": {"typescript": "^5.0.0"}}),
            encoding="utf-8",
        )

        # 1. Initial workspace install
        res1 = install_workspace(ws_dir, source_dir=REPO_ROOT)
        self.assertTrue(res1.success)
        self.assertEqual(res1.stack, "typescript")
        self.assertIn("psl-stack-typescript", res1.skills_installed)
        self.assertTrue((ws_dir / ".agents" / "skills" / "psl-stack-typescript" / "SKILL.md").is_file())

        # By default zero agent definitions in workspace (Layer 1 global inheritance)
        self.assertFalse((ws_dir / ".agents" / "agents").exists())

        # 2. Second run with dedup=True skips identical files
        res2 = install_workspace(ws_dir, source_dir=REPO_ROOT, dedup=True)
        self.assertTrue(res2.success)
        self.assertIn("psl-stack-typescript", res2.skills_skipped)
        self.assertEqual(res2.skills_installed, [])

        # 3. Third run with override=True reinstalls
        res3 = install_workspace(ws_dir, source_dir=REPO_ROOT, override=True)
        self.assertTrue(res3.success)
        self.assertIn("psl-stack-typescript", res3.skills_installed)

        # 4. Opt-in local agents
        res4 = install_workspace(ws_dir, source_dir=REPO_ROOT, include_agents=True)
        self.assertTrue(res4.success)
        self.assertTrue((ws_dir / ".agents" / "agents" / "harness_builder.md").is_file())

    def test_workspace_rust_and_go_stack_instantiation(self) -> None:
        """Rust (Cargo.toml) and Go (go.mod) workspaces install respective stack and test runner skills."""
        # Rust workspace
        ws_rust = self.isolated_base / "workspace_rust"
        ws_rust.mkdir(parents=True)
        (ws_rust / "Cargo.toml").write_text("[package]\nname = 'rust-crate'\n", encoding="utf-8")

        res_rust = install_workspace(ws_rust, source_dir=REPO_ROOT)
        self.assertTrue(res_rust.success)
        self.assertEqual(res_rust.stack, "rust")
        self.assertIn("psl-test-cargo", res_rust.skills_installed)
        self.assertIn("psl-stack-systems", res_rust.skills_installed)
        self.assertIn("psl-stack-shell", res_rust.skills_installed)
        self.assertTrue((ws_rust / ".agents" / "skills" / "psl-test-cargo" / "SKILL.md").is_file())

        # Go workspace
        ws_go = self.isolated_base / "workspace_go"
        ws_go.mkdir(parents=True)
        (ws_go / "go.mod").write_text("module example.com/gomod\n\ngo 1.22\n", encoding="utf-8")

        res_go = install_workspace(ws_go, source_dir=REPO_ROOT)
        self.assertTrue(res_go.success)
        self.assertEqual(res_go.stack, "go")
        self.assertIn("psl-test-go", res_go.skills_installed)
        self.assertIn("psl-stack-backend", res_go.skills_installed)
        self.assertTrue((ws_go / ".agents" / "skills" / "psl-test-go" / "SKILL.md").is_file())

    def test_legacy_setup_detection_notice(self) -> None:
        """Legacy .agent/ directory triggers actionable notice recommending /psl-harmonize."""
        ws_dir = self.isolated_base / "legacy_ws"
        (ws_dir / ".agent").mkdir(parents=True)

        res = install_workspace(ws_dir, source_dir=REPO_ROOT)
        self.assertTrue(res.success)
        self.assertIsNotNone(res.legacy_notice)
        self.assertIn(".agent", res.legacy_notice)
        self.assertIn("/psl-harmonize", res.legacy_notice)

    def test_find_workspace_root(self) -> None:
        """find_workspace_root walks up directory tree to find marker files."""
        ws_dir = self.isolated_base / "project_root"
        nested_dir = ws_dir / "src" / "deep" / "nested"
        nested_dir.mkdir(parents=True)
        (ws_dir / ".git").mkdir()

        # From nested directory, finds root
        root = find_workspace_root(nested_dir)
        self.assertEqual(root, ws_dir)

        # From root itself
        self.assertEqual(find_workspace_root(ws_dir), ws_dir)

    def test_cli_init_subcommand(self) -> None:
        """CLI `psl init` initializes a workspace project."""
        ws_dir = self.isolated_base / "cli_ws"
        ws_dir.mkdir(parents=True)
        (ws_dir / "pyproject.toml").write_text("[project]\nname = 'sample-py'\n", encoding="utf-8")

        with patch("sys.stdout", new_callable=io.StringIO) as mock_out:
            code = main(["init", str(ws_dir), "--yes", "--json"])
            self.assertEqual(code, 0)
            data = json.loads(mock_out.getvalue().strip())
            self.assertTrue(data["success"])
            self.assertEqual(data["stack"], "python")
            self.assertIn("psl-stack-python", data["skills_installed"])
            self.assertTrue((ws_dir / "AGENTS.md").is_file())

    def test_install_workspace_with_standalone_plugin_layout(self) -> None:
        """install_workspace resolves skills, agents, and rules when source is a distributed plugin layout."""
        fake_plugin = self.isolated_base / "dist_plugin"
        (fake_plugin / "skills" / "psl-harmonize").mkdir(parents=True)
        (fake_plugin / "skills" / "psl-harmonize" / "SKILL.md").write_text("# Harmonize", encoding="utf-8")
        (fake_plugin / "agents").mkdir(parents=True)
        (fake_plugin / "agents" / "hammer.md").write_text("# Hammer", encoding="utf-8")
        (fake_plugin / "rules").mkdir(parents=True)
        (fake_plugin / "rules" / "AGENTS.md").write_text("Universal Rules", encoding="utf-8")

        ws_dir = self.isolated_base / "dist_ws"
        ws_dir.mkdir(parents=True)

        res = install_workspace(
            ws_dir,
            skills=["psl-harmonize"],
            include_agents=True,
            source_dir=fake_plugin,
        )
        self.assertTrue(res.success)
        self.assertIn("psl-harmonize", res.skills_installed)
        self.assertTrue((ws_dir / ".agents" / "skills" / "psl-harmonize" / "SKILL.md").is_file())
        self.assertIn("hammer", res.agents_installed)
        self.assertTrue((ws_dir / ".agents" / "agents" / "hammer.md").is_file())
        self.assertTrue((ws_dir / "AGENTS.md").is_file())
        self.assertIn("Universal Rules", (ws_dir / "AGENTS.md").read_text(encoding="utf-8"))

    def test_tagged_rules_migration_from_legacy_psl_harness(self) -> None:
        """Workspace AGENTS.md converts legacy PSL-HARNESS blocks to AGYIS-HARNESS in place."""
        ws_dir = self.isolated_base / "workspace_legacy_migration"
        ws_dir.mkdir(parents=True)
        rules_file = ws_dir / "AGENTS.md"

        legacy_rules = (
            "# Existing Domain Rules\n\n"
            "- Wait 10 minutes before merging PRs to allow CI fences to settle.\n"
            "- Always target staging branch.\n\n"
            "<!-- Added by PSL-HARNESS -->\n"
            "# Universal Empirical Agent Rules: PSL Harness Guidelines\n"
            "- Pre-flight tool availability\n"
            "<!-- End PSL-HARNESS -->\n\n"
            "# Custom Footer Rules\n"
            "- Enforce clean code hygiene.\n"
        )
        rules_file.write_text(legacy_rules, encoding="utf-8")

        # 1. Initial install_workspace converts legacy block in-place
        res1 = install_workspace(ws_dir, source_dir=REPO_ROOT)
        self.assertTrue(res1.success)
        self.assertTrue(res1.rules_updated)

        updated_content = rules_file.read_text(encoding="utf-8")
        # Domain rules before and after the block are preserved
        self.assertIn("# Existing Domain Rules", updated_content)
        self.assertIn("- Wait 10 minutes before merging PRs", updated_content)
        self.assertIn("- Always target staging branch.", updated_content)
        self.assertIn("# Custom Footer Rules", updated_content)
        self.assertIn("- Enforce clean code hygiene.", updated_content)

        # Legacy tags are replaced by modern AGYIS-HARNESS tags
        self.assertNotIn("<!-- Added by PSL-HARNESS -->", updated_content)
        self.assertNotIn("<!-- End PSL-HARNESS -->", updated_content)
        self.assertIn("<!-- Added by AGYIS-HARNESS -->", updated_content)
        self.assertIn("<!-- End AGYIS-HARNESS -->", updated_content)
        self.assertEqual(updated_content.count("<!-- Added by AGYIS-HARNESS -->"), 1)
        self.assertEqual(updated_content.count("<!-- End AGYIS-HARNESS -->"), 1)

        # 2. Idempotent re-run
        res2 = install_workspace(ws_dir, source_dir=REPO_ROOT)
        self.assertTrue(res2.success)
        self.assertFalse(res2.rules_updated)

        re_read_content = rules_file.read_text(encoding="utf-8")
        self.assertEqual(re_read_content, updated_content)
        self.assertEqual(re_read_content.count("<!-- Added by AGYIS-HARNESS -->"), 1)
        self.assertEqual(re_read_content.count("<!-- End AGYIS-HARNESS -->"), 1)
        self.assertEqual(re_read_content.count("<!-- Added by PSL-HARNESS -->"), 0)
        self.assertEqual(re_read_content.count("<!-- End PSL-HARNESS -->"), 0)

    def test_tagged_rules_constants_and_pattern_exports(self) -> None:
        """TAG_START, TAG_END, LEGACY_TAG_START, LEGACY_TAG_END, and TAGGED_BLOCK_PATTERN are exported."""
        from harness.delivery import (
            LEGACY_TAG_END,
            LEGACY_TAG_START,
            TAG_END,
            TAG_START,
            TAGGED_BLOCK_PATTERN,
        )

        self.assertEqual(TAG_START, "<!-- Added by AGYIS-HARNESS -->")
        self.assertEqual(TAG_END, "<!-- End AGYIS-HARNESS -->")
        self.assertEqual(LEGACY_TAG_START, "<!-- Added by PSL-HARNESS -->")
        self.assertEqual(LEGACY_TAG_END, "<!-- End PSL-HARNESS -->")

        # Pattern matches modern and legacy fences
        self.assertTrue(bool(TAGGED_BLOCK_PATTERN.search(f"{TAG_START}\nRules\n{TAG_END}")))
        self.assertTrue(bool(TAGGED_BLOCK_PATTERN.search(f"{LEGACY_TAG_START}\nRules\n{LEGACY_TAG_END}")))
        self.assertTrue(bool(TAGGED_BLOCK_PATTERN.search(f"{LEGACY_TAG_START}\nRules\n{TAG_END}")))
        self.assertFalse(bool(TAGGED_BLOCK_PATTERN.search("# Plain rules without demarcations")))

    def test_extract_command_dictionary_node(self) -> None:
        """Extracts command dictionary from package.json with pnpm, yarn, bun, and npm."""
        from harness.delivery import extract_command_dictionary

        ws = self.isolated_base / "node_cmd_ws"
        ws.mkdir(parents=True)
        (ws / "package.json").write_text(
            json.dumps({"scripts": {"test": "vitest", "build": "tsc", "lint": "eslint ."}}),
            encoding="utf-8",
        )
        (ws / "pnpm-lock.yaml").write_text("", encoding="utf-8")

        cmds = extract_command_dictionary(ws)
        self.assertEqual(cmds.get("test"), "pnpm test")
        self.assertEqual(cmds.get("build"), "pnpm build")
        self.assertEqual(cmds.get("lint"), "pnpm lint")

    def test_extract_command_dictionary_python(self) -> None:
        """Extracts command dictionary from pyproject.toml with pytest and ruff."""
        from harness.delivery import extract_command_dictionary

        ws = self.isolated_base / "py_cmd_ws"
        ws.mkdir(parents=True)
        (ws / "pyproject.toml").write_text(
            '[tool.pytest.ini_options]\naddopts = "-q"\n[tool.ruff]\nline-length = 88\n',
            encoding="utf-8",
        )

        cmds = extract_command_dictionary(ws)
        self.assertEqual(cmds.get("test"), "pytest")
        self.assertEqual(cmds.get("lint"), "ruff check .")
        self.assertEqual(cmds.get("format"), "ruff format .")

    def test_extract_command_dictionary_makefile(self) -> None:
        """Extracts command dictionary from Makefile."""
        from harness.delivery import extract_command_dictionary

        ws = self.isolated_base / "make_cmd_ws"
        ws.mkdir(parents=True)
        (ws / "Makefile").write_text(
            "all:\n\tgcc main.c\n\ntest:\n\t./test.sh\n\nclean:\n\trm -rf *.o\n",
            encoding="utf-8",
        )

        cmds = extract_command_dictionary(ws)
        self.assertEqual(cmds.get("all"), "make all")
        self.assertEqual(cmds.get("test"), "make test")
        self.assertEqual(cmds.get("clean"), "make clean")

    def test_extract_command_dictionary_rust_and_go(self) -> None:
        """Extracts command dictionary from Cargo.toml and go.mod."""
        from harness.delivery import extract_command_dictionary

        ws_rust = self.isolated_base / "rust_cmd_ws"
        ws_rust.mkdir(parents=True)
        (ws_rust / "Cargo.toml").write_text('[package]\nname = "foo"\n', encoding="utf-8")
        rust_cmds = extract_command_dictionary(ws_rust)
        self.assertEqual(rust_cmds.get("test"), "cargo test")
        self.assertEqual(rust_cmds.get("build"), "cargo build")
        self.assertEqual(rust_cmds.get("lint"), "cargo clippy")

        ws_go = self.isolated_base / "go_cmd_ws"
        ws_go.mkdir(parents=True)
        (ws_go / "go.mod").write_text("module example.com/foo\n", encoding="utf-8")
        go_cmds = extract_command_dictionary(ws_go)
        self.assertEqual(go_cmds.get("test"), "go test ./...")
        self.assertEqual(go_cmds.get("build"), "go build ./...")

    def test_install_workspace_dry_run_zero_mutations(self) -> None:
        """install_workspace with dry_run=True performs zero filesystem modifications."""
        ws = self.isolated_base / "dry_run_ws"
        ws.mkdir(parents=True)
        (ws / "package.json").write_text(
            json.dumps({"scripts": {"test": "jest"}}),
            encoding="utf-8",
        )

        res = install_workspace(ws, dry_run=True, source_dir=REPO_ROOT)
        self.assertTrue(res.success)
        self.assertTrue(res.dry_run)
        self.assertEqual(res.stack, "typescript")
        self.assertIn("psl-stack-typescript", res.skills_installed)
        self.assertEqual(res.command_dictionary.get("test"), "npm test")

        # Zero disk mutations
        self.assertFalse((ws / ".agents").exists())
        self.assertFalse((ws / "AGENTS.md").exists())

    def test_install_workspace_injects_command_dictionary(self) -> None:
        """install_workspace embeds extracted command dictionary into AGENTS.md."""
        ws = self.isolated_base / "inject_cmd_ws"
        ws.mkdir(parents=True)
        (ws / "package.json").write_text(
            json.dumps({"scripts": {"test": "jest", "build": "tsc"}}),
            encoding="utf-8",
        )

        res = install_workspace(ws, dry_run=False, source_dir=REPO_ROOT)
        self.assertTrue(res.success)
        self.assertFalse(res.dry_run)
        self.assertTrue((ws / "AGENTS.md").is_file())

        content = (ws / "AGENTS.md").read_text(encoding="utf-8")
        self.assertIn("# 🧪 Project Verification & Native Toolchain", content)
        self.assertIn("npm test", content)
        self.assertIn("<!-- Added by AGYIS-HARNESS -->", content)


if __name__ == "__main__":
    unittest.main()
