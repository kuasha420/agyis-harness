# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Arafat Zahan (@kuasha420)
# Corporate Stewardship & Infrastructure: Purrfect Software Limited (PSL)
# Governed by: ICARO-42/b Ordinance (Company-Supported Personal IP Framework)

"""
Verification suite for Phase 4: Rule Bifurcation, Packaging & Subagent Upgrades
(PSL-SPEC-2026-DRA-001).

Validates:
- GLOBAL_AGENTS.md contains universal invariants and zero harness CLI / ADR-015 benchmark mandates.
- .agents/rules/AGENTS.md isolates harness command dictionaries and ADR-015 benchmarks.
- subagent-ladder/SKILL.md has zero RecipientName occurrences and enforces Workspace: "share".
- Frozen wheel release build and install via PluginInstaller and CLI (agyis install -g).
"""

from __future__ import annotations

import argparse
import io
import json
import os
from pathlib import Path
import shutil
import tempfile
import unittest
from unittest.mock import patch

from harness.cli import main
from harness.commands.install import cmd_install
from harness.delivery import (
    DeliveryMode,
    DeliveryResult,
    PluginInstaller,
    REPO_ROOT,
)


class TestRuleBifurcation(unittest.TestCase):
    """Test suite verifying separation of universal and harness-specific rules."""

    def test_global_agents_authored_with_universal_invariants(self) -> None:
        """GLOBAL_AGENTS.md must exist and contain universal rules without harness-specific mandates."""
        root_global = REPO_ROOT / "GLOBAL_AGENTS.md"
        template_global = REPO_ROOT / "harness" / "rules" / "GLOBAL_AGENTS.md"

        self.assertTrue(root_global.exists(), f"Missing root GLOBAL_AGENTS.md at {root_global}")
        self.assertTrue(template_global.exists(), f"Missing template GLOBAL_AGENTS.md at {template_global}")

        content = root_global.read_text(encoding="utf-8")

        # Must NOT contain harness-specific commands or benchmarks
        self.assertNotIn("./agyis test", content)
        self.assertNotIn("harness.cli test", content)
        self.assertNotIn("ADR-015", content)
        self.assertNotIn("<1.0s", content)

        # Must contain universal engineering hygiene standards
        self.assertIn("Universal Automated Verification Standard", content)
        self.assertIn("Terminal Invariants & Grep Probing Exception", content)
        self.assertIn("Surgical Contiguous Edits Invariant", content)
        self.assertIn("Context Preservation, Reactive Wait & Anti-Loop Discipline", content)
        self.assertIn("The Artifact-First Planning Invariant", content)
        self.assertIn("Human-in-the-Loop & Steering Alignment", content)
        self.assertIn("Always execute the active repository's native verification command", content)

    def test_local_agents_rules_retains_harness_specifics(self) -> None:
        """Local AGENTS.md must retain harness CLI command dictionary and ADR-015 benchmarks."""
        local_rules = REPO_ROOT / ".agents" / "rules" / "AGENTS.md"
        self.assertTrue(local_rules.exists(), f"Missing local AGENTS.md at {local_rules}")

        content = local_rules.read_text(encoding="utf-8")
        self.assertIn("./agyis test", content)
        self.assertIn("python3 -m harness.cli test", content)
        self.assertIn("ADR-015", content)
        self.assertIn("<1.0 second", content)

    def test_subagent_ladder_skill_compliance(self) -> None:
        """subagent-ladder/SKILL.md must have 0 RecipientName references and specify Workspace: 'share'."""
        ladder_skill = REPO_ROOT / ".agents" / "skills" / "subagent-ladder" / "SKILL.md"
        self.assertTrue(ladder_skill.exists(), f"Missing subagent ladder skill at {ladder_skill}")

        content = ladder_skill.read_text(encoding="utf-8")

        # Zero RecipientName references
        self.assertNotIn("RecipientName", content)

        # Enforces Workspace: "share"
        self.assertIn('Workspace: "share"', content)


class TestFrozenWheelPackaging(unittest.TestCase):
    """Test suite verifying frozen wheel release build and installation."""

    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.target_dir = Path(self.temp_dir.name) / "installed_plugin"
        self.bin_dir = Path(self.temp_dir.name) / "bin"
        self.bin_dir.mkdir(parents=True, exist_ok=True)

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def test_cli_install_global_defaults_to_wheel(self) -> None:
        """agyis install -g (global_install=True) defaults to DeliveryMode.WHEEL."""
        args = argparse.Namespace(
            global_install=True,
            copy=False,
            symlink=False,
            wheel=False,
            target=str(self.target_dir),
            bin_dir=str(self.bin_dir),
            dry_run=True,
            json=True,
            workspace=None,
            all_surfaces=False,
        )
        with patch("sys.stdout", new_callable=io.StringIO) as mock_out:
            code = cmd_install(args)
            self.assertEqual(code, 0)
            data = json.loads(mock_out.getvalue().strip())
            self.assertTrue(data["success"])
            self.assertEqual(data["mode"], "wheel")

    def test_cli_install_wheel_flag_selects_wheel_mode(self) -> None:
        """agyis install --wheel selects DeliveryMode.WHEEL."""
        args = argparse.Namespace(
            global_install=False,
            copy=False,
            symlink=False,
            wheel=True,
            target=str(self.target_dir),
            bin_dir=str(self.bin_dir),
            dry_run=True,
            json=True,
            workspace=None,
            all_surfaces=False,
        )
        with patch("sys.stdout", new_callable=io.StringIO) as mock_out:
            code = cmd_install(args)
            self.assertEqual(code, 0)
            data = json.loads(mock_out.getvalue().strip())
            self.assertTrue(data["success"])
            self.assertEqual(data["mode"], "wheel")

    def test_cli_symlink_overrides_global(self) -> None:
        """Explicit --symlink flag overrides global default to preserve symlink mode."""
        args = argparse.Namespace(
            global_install=True,
            copy=False,
            symlink=True,
            wheel=False,
            target=str(self.target_dir),
            bin_dir=str(self.bin_dir),
            dry_run=True,
            json=True,
            workspace=None,
            all_surfaces=False,
        )
        with patch("sys.stdout", new_callable=io.StringIO) as mock_out:
            code = cmd_install(args)
            self.assertEqual(code, 0)
            data = json.loads(mock_out.getvalue().strip())
            self.assertTrue(data["success"])
            self.assertEqual(data["mode"], "symlink")

    def test_installer_wheel_installation_and_symlink_severing(self) -> None:
        """PluginInstaller installs frozen wheel release, severs symlink hazard, and prunes local AGENTS.md."""
        installer = PluginInstaller(
            source_dir=REPO_ROOT,
            default_target_dir=self.target_dir,
            bin_dir=self.bin_dir,
        )

        # 1. Create a simulated live development symlink hazard
        dummy_source = Path(self.temp_dir.name) / "dummy_repo"
        dummy_source.mkdir()
        self.target_dir.symlink_to(dummy_source)
        self.assertTrue(self.target_dir.is_symlink())

        # 2. Install with DeliveryMode.WHEEL (mocking _build_frozen_wheel for fast hermetic test)
        import zipfile
        fake_wheel = Path(self.temp_dir.name) / "agyis_harness-1.0.0-py3-none-any.whl"
        with zipfile.ZipFile(fake_wheel, "w") as zf:
            zf.writestr("harness/__init__.py", "__version__ = '1.0.0'\n")
            zf.writestr("agyis_harness-1.0.0.dist-info/METADATA", "Name: agyis-harness\n")

        with patch.object(installer, "_build_frozen_wheel", return_value=fake_wheel):
            result = installer.install(mode=DeliveryMode.WHEEL)

        self.assertTrue(result.success)
        self.assertEqual(result.mode, "wheel")

        # Symlink must be completely severed: target must be a real directory
        self.assertFalse(self.target_dir.is_symlink())
        self.assertTrue(self.target_dir.is_dir())

        # Expected packaged contents
        self.assertTrue((self.target_dir / "harness" / "__init__.py").exists())
        self.assertTrue((self.target_dir / "dist" / fake_wheel.name).exists())
        self.assertTrue((self.target_dir / "plugin.json").exists())
        self.assertTrue((self.target_dir / "matrix.json").exists())
        self.assertTrue((self.target_dir / "hooks.json").exists())
        self.assertTrue((self.target_dir / "skills").is_dir())

        # Rules isolation in global installation: GLOBAL_AGENTS.md installed into rules/AGENTS.md, repo-internal commands pruned
        self.assertTrue((self.target_dir / "rules" / "GLOBAL_AGENTS.md").exists())
        self.assertTrue((self.target_dir / "rules" / "AGENTS.md").exists())
        installed_rules = (self.target_dir / "rules" / "AGENTS.md").read_text(encoding="utf-8")
        self.assertNotIn("./agyis test", installed_rules)
        self.assertNotIn("harness.cli test", installed_rules)
        self.assertIn("Universal Automated Verification Standard", installed_rules)
        self.assertEqual(installed_rules, (self.target_dir / "rules" / "GLOBAL_AGENTS.md").read_text(encoding="utf-8"))

        # Install info detection
        info = installer.get_install_info(self.target_dir)
        self.assertTrue(info["installed"])
        self.assertEqual(info["mode"], "wheel")

        # Uninstallation cleans up completely
        uninst = installer.uninstall(target_dir=self.target_dir)
        self.assertTrue(uninst.success)
        self.assertEqual(uninst.mode, "wheel")
        self.assertFalse(self.target_dir.exists())


if __name__ == "__main__":
    unittest.main()
