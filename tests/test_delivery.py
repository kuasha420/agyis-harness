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


class TestPluginDelivery(unittest.TestCase):
    """Test suite for core PluginInstaller and CoexistenceEngine."""

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

    def test_symlink_installation_and_validation(self) -> None:
        """Symlink installation creates valid link to source and passes is_installed."""
        installer = PluginInstaller(
            source_dir=REPO_ROOT,
            default_target_dir=self.target_dir,
            config_dir=self.config_dir,
            surfaces=self.surfaces,
        )

        result = installer.install(mode=DeliveryMode.SYMLINK)
        self.assertTrue(result.success)
        self.assertEqual(result.mode, "symlink")
        self.assertTrue(self.target_dir.is_symlink())
        self.assertEqual(self.target_dir.resolve(), REPO_ROOT.resolve())
        for item in ("plugin.json", "assets", "harness", "matrix.json", "hooks.json", "skills", "agents", "rules"):
            self.assertIn(item, result.items_installed)
        self.assertTrue((self.target_dir / "assets" / "logo.svg").is_file())
        self.assertTrue((self.target_dir / "harness" / "gui" / "assets" / "hud.js").is_file())
        self.assertTrue((self.target_dir / "skills" / "cockpit-director" / "SKILL.md").is_file())
        self.assertTrue((self.target_dir / "agents" / "agyis_builder.md").is_file())

        # Validation
        self.assertTrue(installer.is_installed(self.target_dir))
        info = installer.get_install_info(self.target_dir)
        self.assertTrue(info["installed"])
        self.assertEqual(info["mode"], "symlink")
        self.assertIn("plugin.json", info["items"])

    def test_copy_installation_and_file_integrity(self) -> None:
        """Copy installation packages distributable files and passes integrity checks."""
        installer = PluginInstaller(
            source_dir=REPO_ROOT,
            default_target_dir=self.target_dir,
            config_dir=self.config_dir,
            surfaces=self.surfaces,
        )

        result = installer.install(mode=DeliveryMode.COPY)
        self.assertTrue(result.success)
        self.assertEqual(result.mode, "copy")
        self.assertFalse(self.target_dir.is_symlink())
        self.assertTrue(self.target_dir.is_dir())
        self.assertIn("assets", DISTRIBUTABLE_ITEMS)
        self.assertIn("assets", result.items_installed)

        # Distributables present
        self.assertTrue((self.target_dir / "plugin.json").is_file())
        self.assertTrue((self.target_dir / "assets" / "logo.svg").is_file())
        self.assertTrue((self.target_dir / "harness").is_dir())
        self.assertTrue((self.target_dir / "harness" / "gui" / "assets" / "hud.js").is_file())
        self.assertTrue((self.target_dir / "matrix.json").is_file())
        self.assertTrue((self.target_dir / "hooks.json").is_file())
        self.assertTrue((self.target_dir / "skills" / "cockpit-director" / "SKILL.md").is_file())
        self.assertTrue((self.target_dir / "agents" / "agyis_builder.md").is_file())
        self.assertTrue((self.target_dir / "rules" / "AGENTS.md").is_file())

        import tomllib
        from harness import __version__

        pyproject_version = tomllib.loads((REPO_ROOT / "pyproject.toml").read_text(encoding="utf-8"))["project"]["version"]
        plugin_version = json.loads((REPO_ROOT / "plugin.json").read_text(encoding="utf-8"))["version"]

        self.assertTrue(installer.is_installed(self.target_dir))
        info = installer.get_install_info(self.target_dir)
        self.assertTrue(info["installed"])
        self.assertEqual(info["mode"], "copy")
        self.assertEqual(info["version"], __version__)
        self.assertRegex(__version__, r"^\d+\.\d+\.\d+(?:-rc\d+)?$")
        self.assertEqual(__version__, pyproject_version)
        self.assertEqual(__version__, plugin_version)

    def test_wheel_extracted_source_fallback_and_full_assets(self) -> None:
        """PluginInstaller resolves assets/plugin.json from harness/ fallback and delivers full assets in wheel mode."""
        import zipfile

        # 1. Wheel-extracted site-packages layout (only harness/ exists at source_dir root)
        wheel_site = self.isolated_base / "wheel_site"
        for rel in (
            "harness/__init__.py",
            "harness/plugin.json",
            "harness/assets/logo.svg",
            "harness/gui/assets/hud.js",
            "harness/hooks/hooks.json",
            "harness/runtime/matrix.json",
            "harness/agents/agyis_builder.md",
            "harness/skills/cockpit-director/SKILL.md",
            "harness/rules/GLOBAL_AGENTS.md",
        ):
            dst = wheel_site / rel
            dst.parent.mkdir(parents=True, exist_ok=True)
            if rel == "harness/plugin.json":
                dst.write_text((REPO_ROOT / "plugin.json").read_text(encoding="utf-8"), encoding="utf-8")
            elif rel == "harness/assets/logo.svg":
                dst.write_text((REPO_ROOT / "assets" / "logo.svg").read_text(encoding="utf-8"), encoding="utf-8")
            else:
                dst.write_text((REPO_ROOT / rel).read_text(encoding="utf-8"), encoding="utf-8")

        copy_target = self.isolated_base / "copy_from_wheel_site"
        fallback_installer = PluginInstaller(
            source_dir=wheel_site,
            default_target_dir=copy_target,
            bin_dir=self.bin_dir,
        )
        res_copy = fallback_installer.install(mode=DeliveryMode.COPY)
        self.assertTrue(res_copy.success)
        self.assertIn("assets", res_copy.items_installed)
        self.assertIn("plugin.json", res_copy.items_installed)
        self.assertTrue((copy_target / "assets" / "logo.svg").is_file())
        self.assertTrue((copy_target / "plugin.json").is_file())
        self.assertTrue((copy_target / "harness" / "gui" / "assets" / "hud.js").is_file())
        self.assertTrue((copy_target / "hooks.json").is_file())
        self.assertTrue((copy_target / "matrix.json").is_file())
        self.assertTrue((copy_target / "agents" / "agyis_builder.md").is_file())
        self.assertTrue((copy_target / "skills" / "cockpit-director" / "SKILL.md").is_file())
        self.assertTrue((copy_target / "rules" / "AGENTS.md").is_file())
        self.assertIn(
            "Empirical Verification & Clean-Room Testing",
            (copy_target / "rules" / "AGENTS.md").read_text(encoding="utf-8"),
        )

        # 2. DeliveryMode.WHEEL from REPO_ROOT delivers full assets (mocked wheel zip for sub-second isolation)
        fake_wheel = self.isolated_base / "agyis_harness-1.0.0rc9-py3-none-any.whl"
        with zipfile.ZipFile(fake_wheel, "w") as zf:
            zf.writestr("harness/__init__.py", (REPO_ROOT / "harness" / "__init__.py").read_text(encoding="utf-8"))
            zf.writestr(
                "harness/gui/assets/hud.js",
                (REPO_ROOT / "harness" / "gui" / "assets" / "hud.js").read_text(encoding="utf-8"),
            )
            zf.writestr("harness/plugin.json", (REPO_ROOT / "plugin.json").read_text(encoding="utf-8"))
            zf.writestr("harness/assets/logo.svg", (REPO_ROOT / "assets" / "logo.svg").read_text(encoding="utf-8"))
            zf.writestr("agyis_harness-1.0.0rc9.dist-info/METADATA", "Name: agyis-harness\n")

        wheel_target = self.isolated_base / "wheel_target"
        wheel_installer = PluginInstaller(
            source_dir=REPO_ROOT,
            default_target_dir=wheel_target,
            bin_dir=self.bin_dir,
        )
        with patch.object(wheel_installer, "_build_frozen_wheel", return_value=fake_wheel):
            res_wheel = wheel_installer.install(mode=DeliveryMode.WHEEL)
        self.assertTrue(res_wheel.success)
        self.assertIn("assets", res_wheel.items_installed)
        self.assertTrue((wheel_target / "assets" / "logo.svg").is_file())
        self.assertTrue((wheel_target / "plugin.json").is_file())
        self.assertTrue((wheel_target / "harness" / "gui" / "assets" / "hud.js").is_file())
        self.assertTrue((wheel_target / "harness" / "plugin.json").is_file())
        self.assertTrue((wheel_target / "harness" / "assets" / "logo.svg").is_file())
        self.assertTrue((wheel_target / "hooks.json").is_file())
        self.assertTrue((wheel_target / "matrix.json").is_file())
        self.assertTrue((wheel_target / "agents" / "agyis_builder.md").is_file())
        self.assertTrue((wheel_target / "skills" / "cockpit-director" / "SKILL.md").is_file())
        self.assertTrue((wheel_target / "rules" / "AGENTS.md").is_file())
        self.assertFalse((wheel_target / "rules" / "GLOBAL_AGENTS.md").exists())

    def test_dry_run_mode(self) -> None:
        """Dry-run mode does not mutate disk for install or uninstall."""
        installer = PluginInstaller(
            source_dir=REPO_ROOT,
            default_target_dir=self.target_dir,
            config_dir=self.config_dir,
            surfaces=self.surfaces,
        )

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
        installer = PluginInstaller(
            source_dir=REPO_ROOT,
            default_target_dir=self.target_dir,
            config_dir=self.config_dir,
            surfaces=self.surfaces,
        )

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
        installer = PluginInstaller(
            source_dir=REPO_ROOT,
            default_target_dir=self.target_dir,
            config_dir=self.config_dir,
            surfaces=self.surfaces,
        )

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

        installer = PluginInstaller(
            source_dir=REPO_ROOT,
            default_target_dir=self.target_dir,
            config_dir=self.config_dir,
            surfaces=self.surfaces,
        )
        with self.assertRaises(ValueError):
            installer.install(target_dir=REPO_ROOT)

        with self.assertRaises(ValueError):
            installer.uninstall(target_dir=REPO_ROOT)

    def test_product_vs_project_exclusions(self) -> None:
        """Project files (pipeline/, tests/, data/, docs/) are strictly excluded from package."""
        installer = PluginInstaller(
            source_dir=REPO_ROOT,
            default_target_dir=self.target_dir,
            config_dir=self.config_dir,
            surfaces=self.surfaces,
        )
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

    def test_copy_over_wheel_prunes_stale_wheel_and_deleted_entries(self) -> None:
        """DeliveryMode.COPY over a prior WHEEL install prunes dist/, *.dist-info/, and deleted entries (Issue #119)."""
        import zipfile

        fake_src = self.isolated_base / "fake_src_repo"
        (fake_src / "harness").mkdir(parents=True)
        (fake_src / "harness" / "__init__.py").write_text('__version__ = "1.0.0"\n', encoding="utf-8")
        (fake_src / "assets").mkdir()
        (fake_src / "assets" / "logo.svg").write_text("<svg/>\n", encoding="utf-8")
        (fake_src / "skills" / "demo-skill").mkdir(parents=True)
        (fake_src / "skills" / "demo-skill" / "SKILL.md").write_text("# Demo\n", encoding="utf-8")
        (fake_src / "agents").mkdir()
        (fake_src / "agents" / "demo_agent.md").write_text("# Agent\n", encoding="utf-8")
        (fake_src / "rules").mkdir()
        (fake_src / "rules" / "GLOBAL_AGENTS.md").write_text("# Global Rules\n", encoding="utf-8")
        (fake_src / "plugin.json").write_text('{"name": "agyis-harness", "version": "1.0.0"}\n', encoding="utf-8")
        (fake_src / "matrix.json").write_text('{"matrix": true}\n', encoding="utf-8")
        (fake_src / "hooks.json").write_text('{"hooks": {}}\n', encoding="utf-8")

        fake_wheel = self.isolated_base / "agyis_harness-1.0.0-py3-none-any.whl"
        with zipfile.ZipFile(fake_wheel, "w") as zf:
            zf.writestr("harness/__init__.py", '__version__ = "1.0.0"\n')
            zf.writestr("agyis_harness-1.0.0.dist-info/METADATA", "Name: agyis-harness\n")

        installer = PluginInstaller(
            source_dir=fake_src,
            default_target_dir=self.target_dir,
            bin_dir=self.bin_dir,
            config_dir=self.config_dir,
            surfaces=self.surfaces,
        )
        with patch.object(installer, "_build_frozen_wheel", return_value=fake_wheel):
            wheel_res = installer.install(mode=DeliveryMode.WHEEL)
        self.assertTrue(wheel_res.success)
        self.assertTrue((self.target_dir / "dist" / fake_wheel.name).is_file())
        self.assertTrue((self.target_dir / "agyis_harness-1.0.0.dist-info" / "METADATA").is_file())
        self.assertEqual(installer.get_install_info(self.target_dir)["mode"], "wheel")

        # Simulate obsolete entries and a file deleted from source_dir in a newer release
        (self.target_dir / "obsolete_dir").mkdir()
        (self.target_dir / "obsolete_dir" / "legacy.txt").write_text("stale", encoding="utf-8")
        (self.target_dir / "deleted_top.txt").write_text("stale", encoding="utf-8")
        (fake_src / "matrix.json").unlink()

        copy_res = installer.install(mode=DeliveryMode.COPY)
        self.assertTrue(copy_res.success)
        self.assertEqual(copy_res.mode, "copy")
        self.assertFalse((self.target_dir / "dist").exists())
        self.assertEqual(list(self.target_dir.glob("*.dist-info")), [])
        self.assertFalse((self.target_dir / "obsolete_dir").exists())
        self.assertFalse((self.target_dir / "deleted_top.txt").exists())
        self.assertFalse((self.target_dir / "matrix.json").exists())
        self.assertTrue((self.target_dir / "harness" / "__init__.py").is_file())
        self.assertTrue((self.target_dir / "plugin.json").is_file())
        self.assertTrue((self.target_dir / "rules" / "AGENTS.md").is_file())
        self.assertEqual(installer.get_install_info(self.target_dir)["mode"], "copy")

    def test_copy_unlinks_destination_symlinks_without_mutating_targets(self) -> None:
        """DeliveryMode.COPY unlinks symlinks at harness/skills/agents/rules/stale entries safely (Issue #119)."""
        canary_dir = self.isolated_base / "canary_target"
        canary_dir.mkdir(parents=True)
        (canary_dir / "keep.txt").write_text("do not delete", encoding="utf-8")

        self.target_dir.mkdir(parents=True)
        for name in ("harness", "skills", "agents", "rules"):
            (self.target_dir / name).symlink_to(canary_dir)
        (self.target_dir / "dangling_stale").symlink_to(self.isolated_base / "missing_target")

        installer = PluginInstaller(
            source_dir=REPO_ROOT,
            default_target_dir=self.target_dir,
            bin_dir=self.bin_dir,
            config_dir=self.config_dir,
            surfaces=self.surfaces,
        )
        res = installer.install(mode=DeliveryMode.COPY)
        self.assertTrue(res.success)
        for name in ("harness", "skills", "agents", "rules"):
            dst = self.target_dir / name
            self.assertFalse(dst.is_symlink(), f"{name} symlink should be unlinked")
            self.assertTrue(dst.is_dir())
        self.assertFalse((self.target_dir / "dangling_stale").is_symlink())
        self.assertEqual((canary_dir / "keep.txt").read_text(encoding="utf-8"), "do not delete")


if __name__ == "__main__":
    unittest.main()
