#!/usr/bin/env python3
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
    REPO_ROOT,
    CoexistenceEngine,
    DeliveryMode,
    DeliveryResult,
    PluginInstaller,
)


class TestPluginDelivery(unittest.TestCase):
    """Test suite for PluginInstaller and CoexistenceEngine."""

    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.isolated_base = Path(self.temp_dir.name)
        # Always install strictly to a subfolder inside temp
        self.target_dir = self.isolated_base / "installed_plugin"

    def tearDown(self) -> None:
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


if __name__ == "__main__":
    unittest.main()
