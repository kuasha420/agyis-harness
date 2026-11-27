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
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

import argparse
from harness.cli import main
from harness.commands.init import cmd_init
from harness.delivery import (
    DISTRIBUTABLE_ITEMS,
    GIT_EXCLUDE_PATTERNS,
    REPO_ROOT,
    SYNC_SURFACE_ITEMS,
    CoexistenceEngine,
    DeliveryMode,
    DeliveryResult,
    PluginInstaller,
    configure_git_exclude,
    enforce_single_source_skills,
    find_workspace_root,
    install_workspace,
    sync_surfaces,
    adapt_spdx_license,
    detect_repository_license,
    extract_command_descriptions,
)


class TestDeliverySurfacesAndLaunchers(unittest.TestCase):
    """Test suite for global CLI launchers, multi-surface sync, single-source enforcement, and config.json."""

    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.isolated_base = Path(self.temp_dir.name)
        # Always install strictly to a subfolder inside temp
        self.target_dir = self.isolated_base / "installed_plugin"
        self.bin_dir = self.isolated_base / "bin"
        self.aux_bin_1 = self.isolated_base / "gemini" / "antigravity" / "bin"
        self.aux_bin_2 = self.isolated_base / "gemini" / "antigravity-cli" / "bin"
        self.config_dir = self.isolated_base / "gemini" / "config"
        self.surfaces = [
            self.isolated_base / "gemini" / "antigravity",
            self.isolated_base / "gemini" / "antigravity-cli",
            self.isolated_base / "gemini" / "antigravity-ide",
        ]
        self.orig_bin_dir = os.environ.get("PSL_BIN_DIR")
        os.environ["PSL_BIN_DIR"] = str(self.bin_dir)
        self.orig_aux_bin_dirs = os.environ.get("PSL_AUX_BIN_DIRS")
        os.environ["PSL_AUX_BIN_DIRS"] = f"{self.aux_bin_1}:{self.aux_bin_2}"
        self.orig_agyis_config_dir = os.environ.get("AGYIS_CONFIG_DIR")
        os.environ["AGYIS_CONFIG_DIR"] = str(self.config_dir)
        self.orig_psl_config_dir = os.environ.get("PSL_CONFIG_DIR")
        os.environ["PSL_CONFIG_DIR"] = str(self.config_dir)
        self.orig_agyis_surfaces = os.environ.get("AGYIS_SURFACES")
        os.environ["AGYIS_SURFACES"] = os.pathsep.join(str(s) for s in self.surfaces)

    def tearDown(self) -> None:
        for key, orig in (
            ("PSL_BIN_DIR", self.orig_bin_dir),
            ("PSL_AUX_BIN_DIRS", self.orig_aux_bin_dirs),
            ("AGYIS_CONFIG_DIR", self.orig_agyis_config_dir),
            ("PSL_CONFIG_DIR", self.orig_psl_config_dir),
            ("AGYIS_SURFACES", self.orig_agyis_surfaces),
        ):
            if orig is not None:
                os.environ[key] = orig
            else:
                os.environ.pop(key, None)

        self.temp_dir.cleanup()

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

    def test_install_cleans_legacy_psl_agy_harness_dir(self) -> None:
        """Installing agyis-harness cleans up legacy psl-agy-harness directory to prevent duplicate hooks."""
        plugins_dir = self.isolated_base / "plugins"
        legacy_dir = plugins_dir / "psl-agy-harness"
        legacy_dir.mkdir(parents=True, exist_ok=True)
        (legacy_dir / "plugin.json").write_text('{"name": "psl-agy-harness"}', encoding="utf-8")

        new_target = plugins_dir / "agyis-harness"
        installer = PluginInstaller(
            source_dir=REPO_ROOT,
            default_target_dir=new_target,
            bin_dir=self.bin_dir,
        )

        res = installer.install(mode=DeliveryMode.SYMLINK)
        self.assertTrue(res.success)
        self.assertTrue(new_target.exists())
        self.assertFalse(legacy_dir.exists())
        self.assertIn(str(legacy_dir), res.duplicates_removed)

        # Test uninstall also handles legacy dir if it reappears
        legacy_dir.mkdir(parents=True, exist_ok=True)
        (legacy_dir / "plugin.json").write_text('{"name": "psl-agy-harness"}', encoding="utf-8")
        res_un = installer.uninstall()
        self.assertTrue(res_un.success)
        self.assertFalse(legacy_dir.exists())

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
        dup_agent = fake_agents / "agyis_builder.md"
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
        self.assertTrue((self.target_dir / "agents" / "agyis_builder.md").exists())

    def test_single_source_skill_delivery(self) -> None:
        """Plugin installation purges duplicate standalone skills in ~/.gemini/config/skills/ (Issue #52)."""
        fake_cfg = self.isolated_base / "cfg_single_source_skills"
        fake_skills = fake_cfg / "skills"
        fake_skills.mkdir(parents=True)

        # Standalone skill duplicate that exists in harness/skills
        dup_skill = fake_skills / "code-review"
        dup_skill.mkdir(parents=True)
        (dup_skill / "SKILL.md").write_text("# Duplicate Standalone Skill\n", encoding="utf-8")

        # Independent custom skill
        user_skill = fake_skills / "custom-user-skill"
        user_skill.mkdir(parents=True)
        (user_skill / "SKILL.md").write_text("# User Custom Skill\n", encoding="utf-8")

        installer = PluginInstaller(
            source_dir=REPO_ROOT,
            default_target_dir=self.target_dir,
            config_dir=fake_cfg,
        )

        res = installer.install(mode=DeliveryMode.COPY)
        self.assertTrue(res.success)
        # Standalone duplicate removed
        self.assertIn(str(dup_skill), res.duplicates_removed)
        self.assertFalse(dup_skill.exists())
        # Custom user skill preserved
        self.assertTrue(user_skill.exists())
        # Plugin single source exists
        self.assertTrue((self.target_dir / "skills" / "code-review").exists())

    def test_enforce_single_source_skills_workspace_and_dry_run(self) -> None:
        """enforce_single_source_skills prunes workspace duplicate skills and respects dry_run (Issue #52)."""
        fake_cfg = self.isolated_base / "cfg_skills_ws"
        fake_ws = self.isolated_base / "fake_workspace"
        ws_skills = fake_ws / ".agents" / "skills"
        ws_skills.mkdir(parents=True)

        # Create plugin skill under fake_cfg/plugins/psl-agy-harness/skills/
        plugin_skills_dir = fake_cfg / "plugins" / "psl-agy-harness" / "skills"
        plugin_skill = plugin_skills_dir / "psl-stack-python"
        plugin_skill.mkdir(parents=True)
        (plugin_skill / "SKILL.md").write_text("# Plugin Python Skill\n", encoding="utf-8")

        # Create shadowing workspace duplicate
        ws_dup = ws_skills / "psl-stack-python"
        ws_dup.mkdir(parents=True)
        (ws_dup / "SKILL.md").write_text("# Redundant Workspace Python Skill\n", encoding="utf-8")

        # Create unique custom workspace skill
        ws_custom = ws_skills / "custom-project-skill"
        ws_custom.mkdir(parents=True)
        (ws_custom / "SKILL.md").write_text("# Custom Project Skill\n", encoding="utf-8")

        # Test dry-run
        dry_removed = enforce_single_source_skills(
            config_dir=fake_cfg,
            workspace_dir=fake_ws,
            dry_run=True,
            plugin_skills_dir=plugin_skills_dir,
        )
        self.assertIn(str(ws_dup), dry_removed)
        self.assertTrue(ws_dup.exists(), "Dry run must not delete files")

        # Test live enforcement
        live_removed = enforce_single_source_skills(
            config_dir=fake_cfg,
            workspace_dir=fake_ws,
            dry_run=False,
            plugin_skills_dir=plugin_skills_dir,
        )
        self.assertIn(str(ws_dup), live_removed)
        self.assertFalse(ws_dup.exists(), "Live enforcement must prune workspace duplicate")
        self.assertTrue(ws_custom.exists(), "Custom project skill must remain intact")

    def test_copy_delivery_rules_bifurcation(self) -> None:
        """COPY installation delivers GLOBAL_AGENTS.md into rules/AGENTS.md without ADR-015 commands (Issue #53)."""
        installer = PluginInstaller(
            source_dir=REPO_ROOT,
            default_target_dir=self.target_dir,
            config_dir=self.isolated_base / "cfg_rules",
        )

        res = installer.install(mode=DeliveryMode.COPY)
        self.assertTrue(res.success)
        self.assertTrue((self.target_dir / "rules" / "AGENTS.md").exists())
        content = (self.target_dir / "rules" / "AGENTS.md").read_text(encoding="utf-8")

        # Must NOT contain repo-internal ADR-015 mandates
        self.assertNotIn("./agyis test", content)
        self.assertNotIn("harness.cli test", content)
        self.assertNotIn("<1.0 second", content)
        # Must contain universal engineering guidelines (Codex v2)
        self.assertIn("Empirical Verification & Clean-Room Testing", content)
        self.assertIn("Tool Determinism, Failure Transparency & Minimal Diffs", content)

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

    def test_install_uninstall_never_mutates_live_home_config_or_surfaces(self) -> None:
        """Installing/uninstalling to custom target_dir never touches live ~/.gemini/config/config.json or surfaces."""
        fake_home = self.isolated_base / "fake_home"
        live_cfg_dir = fake_home / ".gemini" / "config"
        live_cfg_dir.mkdir(parents=True)
        live_cfg_file = live_cfg_dir / "config.json"
        original_payload = json.dumps(
            {
                "plugins": {
                    "agyis-harness": {"enabled": True, "installedFrom": "live"},
                }
            },
            indent=2,
        ) + "\n"
        live_cfg_file.write_text(original_payload, encoding="utf-8")

        live_surface = fake_home / ".gemini" / "antigravity"
        live_surface.mkdir(parents=True)
        (live_cfg_dir / "skills").mkdir(parents=True)
        (live_surface / "skills").symlink_to(live_cfg_dir / "skills")

        custom_target_1 = self.isolated_base / "custom_1" / "agyis-harness"
        custom_target_2 = self.isolated_base / "custom_2" / "agyis-harness"
        env_clear = {
            "AGYIS_CONFIG_DIR": "",
            "PSL_CONFIG_DIR": "",
            "AGYIS_SURFACES": "",
            "AGYIS_PLUGINS_DIR": "",
            "PSL_PLUGINS_DIR": "",
        }
        with patch.dict(os.environ, env_clear, clear=False):
            for k in env_clear:
                os.environ.pop(k, None)
            with patch.object(Path, "home", return_value=fake_home):
                installer_1 = PluginInstaller(
                    source_dir=REPO_ROOT,
                    default_target_dir=custom_target_1,
                    bin_dir=self.bin_dir,
                    aux_bin_dirs=[self.aux_bin_1],
                )
                self.assertNotEqual(installer_1.config_dir, live_cfg_dir.resolve())
                self.assertNotIn(live_surface.resolve(), installer_1.surfaces)
                installer_1.install(mode=DeliveryMode.COPY, all_surfaces=True)
                installer_1.uninstall(clean_surfaces=True)

                installer_2 = PluginInstaller(
                    source_dir=REPO_ROOT,
                    bin_dir=self.bin_dir,
                    aux_bin_dirs=[self.aux_bin_1],
                )
                installer_2.install(mode=DeliveryMode.COPY, target_dir=custom_target_2, all_surfaces=True)
                installer_2.uninstall(target_dir=custom_target_2, clean_surfaces=True)

        self.assertEqual(live_cfg_file.read_text(encoding="utf-8"), original_payload)
        self.assertTrue((live_surface / "skills").is_symlink())

    def test_config_json_atomic_permissions_siblings_and_env_overrides(self) -> None:
        """_enable_in_config and uninstall preserve sibling keys, enforce 0o600, and honor env overrides."""
        import stat

        env_cfg = self.isolated_base / "env_cfg"
        env_surf_1 = self.isolated_base / "env_surf_1"
        env_surf_2 = self.isolated_base / "env_surf_2"
        env_plugin = env_cfg / "plugins" / "agyis-harness"
        env_cfg.mkdir(parents=True, exist_ok=True)
        cfg_file = env_cfg / "config.json"
        cfg_file.write_text(
            json.dumps(
                {
                    "theme": "dark",
                    "plugins": {
                        "agyis-harness": {"enabled": False, "installedFrom": "marketplace"},
                        "other-plugin": {"enabled": True},
                    },
                },
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )

        with patch.dict(
            os.environ,
            {
                "AGYIS_CONFIG_DIR": str(env_cfg),
                "AGYIS_SURFACES": os.pathsep.join([str(env_surf_1), str(env_surf_2)]),
            },
            clear=False,
        ):
            installer = PluginInstaller(
                source_dir=REPO_ROOT,
                default_target_dir=env_plugin,
                bin_dir=self.bin_dir,
                aux_bin_dirs=[self.aux_bin_1],
            )
            self.assertEqual(installer.config_dir, env_cfg.resolve())
            self.assertEqual(installer.surfaces, [env_surf_1.resolve(), env_surf_2.resolve()])

            res = installer.install(mode=DeliveryMode.COPY, all_surfaces=True)
            self.assertTrue(res.success)
            self.assertEqual(stat.S_IMODE(cfg_file.stat().st_mode), 0o600)
            after_install = json.loads(cfg_file.read_text(encoding="utf-8"))
            self.assertEqual(after_install["theme"], "dark")
            self.assertEqual(
                after_install["plugins"]["agyis-harness"],
                {"enabled": True, "installedFrom": "marketplace"},
            )
            self.assertEqual(after_install["plugins"]["other-plugin"], {"enabled": True})

            un_res = installer.uninstall(clean_surfaces=True)
            self.assertTrue(un_res.success)
            self.assertEqual(stat.S_IMODE(cfg_file.stat().st_mode), 0o600)
            after_uninstall = json.loads(cfg_file.read_text(encoding="utf-8"))
            self.assertEqual(after_uninstall["theme"], "dark")
            self.assertNotIn("agyis-harness", after_uninstall["plugins"])
            self.assertEqual(after_uninstall["plugins"]["other-plugin"], {"enabled": True})

    def test_cli_extension_cannot_shadow_builtin_subcommand(self) -> None:
        """DRIFT-P1-10: Workspace .agents/commands/doctor.py cannot shadow built-in agyis doctor."""
        with patch("harness.cli.discover_workspace_commands", return_value={"doctor": Path("/tmp/evil_doctor.py")}), \
             patch("harness.cli.execute_extension_command") as mock_ext, \
             patch("harness.cli.cmd_doctor", return_value=0) as mock_doc:
            rc = main(["doctor", "--json"])
        self.assertEqual(rc, 0)
        mock_ext.assert_not_called()
        mock_doc.assert_called_once()

    def test_launcher_prefers_cwd_checkout_and_cwd_venv_over_installed_paths(self) -> None:
        """Generated bin launcher puts CWD checkout at sys.path[0] and prefers CWD .venv python (Issue #120)."""
        from harness.delivery.bin_launcher import _build_launcher_content

        def _make_repo(root: Path, origin_tag: str) -> None:
            root.mkdir(parents=True, exist_ok=True)
            (root / "pyproject.toml").write_text('[project]\nname = "agyis-harness"\n', encoding="utf-8")
            (root / "tests").mkdir(parents=True, exist_ok=True)
            (root / "harness").mkdir(parents=True, exist_ok=True)
            (root / "harness" / "__init__.py").write_text("", encoding="utf-8")
            (root / "harness" / "cli.py").write_text(
                "import json, os, sys\n"
                "def main():\n"
                f"    print(json.dumps({{'origin': {origin_tag!r}, 'sys_path_0': sys.path[0], 'venv_flag': os.environ.get('CWD_VENV_RAN', '')}}))\n"
                "    return 0\n",
                encoding="utf-8",
            )

        fake_home = self.isolated_base / "home"
        plugin_dir = fake_home / ".gemini" / "config" / "plugins" / "agyis-harness"
        target_dir = self.isolated_base / "target_dir"
        source_dir = self.isolated_base / "installed_source"
        cwd_repo = self.isolated_base / "cwd_checkout"
        unrelated_dir = self.isolated_base / "unrelated_dir"
        unrelated_dir.mkdir(parents=True)

        _make_repo(plugin_dir, "plugin_dir")
        _make_repo(target_dir, "target_dir")
        _make_repo(source_dir, "source_dir")
        _make_repo(cwd_repo, "cwd_repo")

        # Install executable .venv/bin/python shims in both source_dir and cwd_repo
        for repo_root, env_key in ((source_dir, "SRC_VENV_RAN"), (cwd_repo, "CWD_VENV_RAN")):
            venv_py = repo_root / ".venv" / "bin" / "python"
            venv_py.parent.mkdir(parents=True, exist_ok=True)
            venv_py.write_text(
                f"#!/bin/sh\nexport {env_key}=1\nexec {sys.executable!r} \"$@\"\n",
                encoding="utf-8",
            )
            venv_py.chmod(0o755)

        launcher_src = self.bin_dir / "agyis_source_mode"
        self.bin_dir.mkdir(parents=True, exist_ok=True)
        launcher_src.write_text(
            _build_launcher_content(
                str(target_dir.resolve()),
                str(source_dir.resolve()),
                entrypoint_func="main",
                python_executable=None,
            ),
            encoding="utf-8",
        )
        launcher_src.chmod(0o755)

        clean_env = {k: v for k, v in os.environ.items() if k not in ("PYTHONPATH", "_AGYIS_LAUNCHER_REEXEC")}
        clean_env["HOME"] = str(fake_home)

        # 1. From CWD checkout root: CWD checkout wins sys.path[0] & CWD .venv/bin/python runs
        run_cwd = subprocess.run(
            [sys.executable, str(launcher_src)],
            cwd=str(cwd_repo),
            env=clean_env,
            capture_output=True,
            text=True,
            check=True,
        )
        cwd_payload = json.loads(run_cwd.stdout.strip())
        self.assertEqual(cwd_payload["origin"], "cwd_repo")
        self.assertEqual(cwd_payload["sys_path_0"], str(cwd_repo.resolve()))
        self.assertEqual(cwd_payload["venv_flag"], "1")

        # 2. From CWD checkout subdirectory (tests/): still detects ancestor CWD checkout
        run_sub = subprocess.run(
            [sys.executable, str(launcher_src)],
            cwd=str(cwd_repo / "tests"),
            env=clean_env,
            capture_output=True,
            text=True,
            check=True,
        )
        sub_payload = json.loads(run_sub.stdout.strip())
        self.assertEqual(sub_payload["origin"], "cwd_repo")
        self.assertEqual(sub_payload["sys_path_0"], str(cwd_repo.resolve()))

        # 3. From unrelated directory: falls back to source_dir
        run_other = subprocess.run(
            [sys.executable, str(launcher_src)],
            cwd=str(unrelated_dir),
            env=clean_env,
            capture_output=True,
            text=True,
            check=True,
        )
        other_payload = json.loads(run_other.stdout.strip())
        self.assertEqual(other_payload["origin"], "source_dir")

        # 4. Packaged launcher with explicit python_executable still gives CWD checkout sys.path[0]
        launcher_pkg = self.bin_dir / "agyis_pkg_mode"
        launcher_pkg.write_text(
            _build_launcher_content(
                str(target_dir.resolve()),
                str(source_dir.resolve()),
                entrypoint_func="main",
                python_executable=sys.executable,
            ),
            encoding="utf-8",
        )
        launcher_pkg.chmod(0o755)
        run_pkg = subprocess.run(
            [str(launcher_pkg)],
            cwd=str(cwd_repo),
            env=clean_env,
            capture_output=True,
            text=True,
            check=True,
        )
        pkg_payload = json.loads(run_pkg.stdout.strip())
        self.assertEqual(pkg_payload["origin"], "cwd_repo")
        self.assertEqual(pkg_payload["sys_path_0"], str(cwd_repo.resolve()))


if __name__ == "__main__":
    unittest.main()
