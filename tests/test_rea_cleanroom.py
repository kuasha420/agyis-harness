# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Arafat Zahan (@kuasha420)
# Corporate Stewardship & Infrastructure: Purrfect Software Limited (PSL)
# Governed by: ICARO-42/b Ordinance (Company-Supported Personal IP Framework)

"""
Hermetic Unit Tests for Native REA Integration, Automated Runtime Healing & Typed Obligation Schemas (Issue #96).
"""

from __future__ import annotations

import argparse
import io
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import MagicMock, patch

from harness.cleanroom.obligation import (
    EvidenceBundle,
    ObligationManifest,
    ReviewedObligation,
    scaffold_obligation_ledger,
    validate_obligation_ledger,
)
from harness.commands.verify import cmd_verify
from harness.hooks.command_safety_hook import (
    check_command_safety,
    inject_rea_setup_flags,
    sanitize_command,
)
from harness.hooks.completion_fence_hook import is_manifest_verified
from harness.runtime.healing import heal_rea_tooling
from harness.runtime.tool_checks import (
    check_node_toolchain,
    check_rea_tooling,
    configure_rea_mcp_server,
    find_jdk21_path,
    is_rea_node_compatible,
)


class TestREANodeSemverCompatibility(unittest.TestCase):
    """Tests is_rea_node_compatible semver check across version ladders."""

    def test_node_version_26_ladder(self):
        self.assertFalse(is_rea_node_compatible("26.12.0"))
        self.assertTrue(is_rea_node_compatible("26.12.1"))
        self.assertTrue(is_rea_node_compatible("v26.12.1"))
        self.assertTrue(is_rea_node_compatible("26.13.0"))
        self.assertTrue(is_rea_node_compatible("v27.0.0"))

    def test_node_version_24_ladder(self):
        self.assertFalse(is_rea_node_compatible("24.22.0"))
        self.assertTrue(is_rea_node_compatible("24.22.1"))
        self.assertTrue(is_rea_node_compatible("v24.22.1"))
        self.assertTrue(is_rea_node_compatible("24.23.0"))

    def test_node_version_22_ladder(self):
        self.assertFalse(is_rea_node_compatible("22.23.3"))
        self.assertTrue(is_rea_node_compatible("22.23.4"))
        self.assertTrue(is_rea_node_compatible("v22.23.4"))
        self.assertTrue(is_rea_node_compatible("22.24.0"))

    def test_incompatible_major_versions(self):
        self.assertFalse(is_rea_node_compatible("20.0.0"))
        self.assertFalse(is_rea_node_compatible("v20.18.1"))
        self.assertFalse(is_rea_node_compatible("21.0.0"))
        self.assertFalse(is_rea_node_compatible("23.0.0"))
        self.assertFalse(is_rea_node_compatible("25.0.0"))

    def test_invalid_versions(self):
        self.assertFalse(is_rea_node_compatible(""))
        self.assertFalse(is_rea_node_compatible("invalid"))
        self.assertFalse(is_rea_node_compatible(None))  # type: ignore


class TestNodeToolchainCheck(unittest.TestCase):
    """Tests check_node_toolchain audit logic."""

    def test_node_toolchain_missing(self):
        with patch("shutil.which", return_value=None):
            res = check_node_toolchain()
            self.assertEqual(res["status"], "MISSING")
            self.assertFalse(res["rea_compatible"])
            self.assertIn("pnpm env use --global 24", res["remediation"])

    def test_node_toolchain_incompatible(self):
        mock_proc = MagicMock()
        mock_proc.returncode = 0
        mock_proc.stdout = "v26.12.0\n"
        with patch("shutil.which", return_value="/usr/bin/node"), patch(
            "subprocess.run", return_value=mock_proc
        ):
            res = check_node_toolchain()
            self.assertEqual(res["status"], "WARNING")
            self.assertFalse(res["rea_compatible"])
            self.assertEqual(res["version"], "26.12.0")
            self.assertIn("pnpm env use --global 24", res["remediation"])

    def test_node_toolchain_compatible(self):
        mock_proc = MagicMock()
        mock_proc.returncode = 0
        mock_proc.stdout = "v24.22.1\n"
        with patch("shutil.which", return_value="/usr/bin/node"), patch(
            "subprocess.run", return_value=mock_proc
        ):
            res = check_node_toolchain()
            self.assertEqual(res["status"], "OK")
            self.assertTrue(res["rea_compatible"])
            self.assertEqual(res["version"], "24.22.1")
            self.assertIsNone(res["remediation"])


class TestJDK21DiscoveryAndMCPConfig(unittest.TestCase):
    """Tests find_jdk21_path and configure_rea_mcp_server zero-empty-string guarantee."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.tmp_path = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def test_find_jdk21_path_from_env_valid(self):
        fake_jdk = self.tmp_path / "jdk-21"
        fake_jdk.mkdir(parents=True)
        (fake_jdk / "release").write_text('JAVA_VERSION="21.0.3"\n', encoding="utf-8")

        with patch.dict(os.environ, {"JAVA_HOME": str(fake_jdk)}):
            found = find_jdk21_path()
            self.assertIsNotNone(found)
            self.assertEqual(found, fake_jdk.resolve())

    def test_find_jdk21_path_from_env_rejects_older(self):
        fake_jdk17 = self.tmp_path / "jdk-17"
        fake_jdk17.mkdir(parents=True)
        (fake_jdk17 / "release").write_text('JAVA_VERSION="17.0.2"\n', encoding="utf-8")

        with patch.dict(os.environ, {"JAVA_HOME": str(fake_jdk17)}):
            found = find_jdk21_path()
            # Must not return the JDK 17 path
            self.assertNotEqual(found, fake_jdk17.resolve())

    def test_configure_rea_mcp_server_omits_java_home_when_not_found(self):
        cfg_file = self.tmp_path / "mcp_config.json"
        with patch("harness.runtime.tool_checks.find_jdk21_path", return_value=None):
            configured, errors = configure_rea_mcp_server(
                config_paths=[cfg_file],
                jdk21_path=None,
                ghidra_dir="/opt/ghidra",
            )
            self.assertEqual(len(errors), 0)
            self.assertEqual(len(configured), 1)
            data = json.loads(cfg_file.read_text(encoding="utf-8"))
            rea_env = data["mcpServers"]["rea"]["env"]
            # CRITICAL: JAVA_HOME must be completely omitted, NEVER ""
            self.assertNotIn("JAVA_HOME", rea_env)
            self.assertEqual(rea_env["GHIDRA_INSTALL_DIR"], "/opt/ghidra")

    def test_configure_rea_mcp_server_writes_java_home_when_present(self):
        cfg_file = self.tmp_path / "mcp_config.json"
        fake_jdk = self.tmp_path / "jdk-21"
        fake_jdk.mkdir(parents=True)
        (fake_jdk / "release").write_text('JAVA_VERSION="21.0.1"\n', encoding="utf-8")

        configured, errors = configure_rea_mcp_server(
            config_paths=[cfg_file],
            jdk21_path=fake_jdk,
            ghidra_dir="/opt/ghidra",
        )
        self.assertEqual(len(errors), 0)
        data = json.loads(cfg_file.read_text(encoding="utf-8"))
        rea_env = data["mcpServers"]["rea"]["env"]
        self.assertEqual(rea_env["JAVA_HOME"], str(fake_jdk))


@patch("harness.hooks.command_safety_hook.get_user_path_shims", return_value=[])
class TestCommandSafetyREASetup(unittest.TestCase):
    """Tests transparent --yes injection for rea setup in command_safety_hook."""

    def test_direct_inject_rea_setup_flags(self, mock_shims):
        mod, changed, reasons = inject_rea_setup_flags("rea setup")
        self.assertTrue(changed)
        self.assertEqual(mod, "rea setup --yes")
        self.assertEqual(reasons, ["enforced non-interactive rea setup --yes"])

    def test_rea_setup_lacking_yes_flag(self, mock_shims):
        cmd = "rea setup"
        decision, mod, reason = sanitize_command(cmd)
        self.assertEqual(decision, "allow")
        self.assertIsNotNone(mod)
        self.assertEqual(mod, "rea setup --yes")
        self.assertIn("enforced non-interactive rea setup --yes", reason)

    def test_rea_setup_with_args_lacking_yes(self, mock_shims):
        cmd = "/usr/local/bin/rea setup --dir /opt"
        decision, mod, reason = sanitize_command(cmd)
        self.assertEqual(decision, "allow")
        self.assertIsNotNone(mod)
        self.assertEqual(mod, "/usr/local/bin/rea setup --yes --dir /opt")

    def test_rea_setup_already_has_yes(self, mock_shims):
        for cmd in ("rea setup --yes", "rea setup -y", "/usr/bin/rea setup --yes"):
            decision, mod, reason = sanitize_command(cmd)
            self.assertEqual(decision, "allow")
            self.assertIsNone(mod)
            self.assertIsNone(reason)

    def test_check_command_safety_alias(self, mock_shims):
        decision, mod, reason = check_command_safety("rea setup")
        self.assertEqual(decision, "allow")
        self.assertEqual(mod, "rea setup --yes")


class TestCleanroomObligationSchema(unittest.TestCase):
    """Tests typed obligation ledger scaffolding and REA 6.8.0 schema validation."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.tmp_path = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def test_scaffold_and_validate_clean(self):
        ledger_path = self.tmp_path / ".agents" / "ledger" / "obligation_ledger.json"
        out = scaffold_obligation_ledger(ledger_path)
        self.assertTrue(out.is_file())

        valid, errors = validate_obligation_ledger(out)
        self.assertTrue(valid, f"Scaffolded ledger must be valid: {errors}")
        self.assertEqual(errors, [])

    def test_validate_missing_evidence_bundle(self):
        ledger_path = self.tmp_path / "bad_ledger.json"
        ledger_path.write_text(json.dumps({"reviewed_obligations": []}), encoding="utf-8")
        valid, errors = validate_obligation_ledger(ledger_path)
        self.assertFalse(valid)
        self.assertTrue(any("evidence_bundle" in e for e in errors))

    def test_validate_unresolved_contradictions(self):
        ledger_path = self.tmp_path / "contradiction_ledger.json"
        scaffold_obligation_ledger(ledger_path)
        data = json.loads(ledger_path.read_text(encoding="utf-8"))
        data["manifest"]["contradictions"] = [{"id": "CON-1", "issue": "Symbol collision"}]
        ledger_path.write_text(json.dumps(data), encoding="utf-8")

        valid, errors = validate_obligation_ledger(ledger_path)
        self.assertFalse(valid)
        self.assertTrue(any("contradictions" in e for e in errors))


class TestCompletionFenceAndVerifyCLI(unittest.TestCase):
    """Tests completion_fence_hook and cmd_verify with typed REA obligation ledger."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.ws = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def test_is_manifest_verified_with_typed_ledger(self):
        ledger_path = self.ws / ".agents" / "ledger" / "obligation_ledger.json"
        scaffold_obligation_ledger(ledger_path)

        # Scaffolded ledger has disposition="satisfied" -> verified
        self.assertTrue(is_manifest_verified(self.ws))

        # Change disposition to rejected -> not verified
        data = json.loads(ledger_path.read_text(encoding="utf-8"))
        data["reviewed_obligations"][0]["disposition"] = "rejected"
        ledger_path.write_text(json.dumps(data), encoding="utf-8")
        self.assertFalse(is_manifest_verified(self.ws))

    def test_cmd_verify_scaffold_flag(self):
        args = argparse.Namespace(
            workspace=self.ws,
            spec=False,
            json=True,
            scaffold=True,
        )
        buf = io.StringIO()
        with patch("sys.stdout", buf):
            code = cmd_verify(args)
        self.assertEqual(code, 0)
        data = json.loads(buf.getvalue())
        self.assertEqual(data["status"], "scaffolded")
        self.assertTrue((self.ws / ".agents" / "ledger" / "obligation_ledger.json").is_file())

    def test_cmd_verify_delegates_to_rea_build_and_evaluate(self):
        ledger_path = self.ws / ".agents" / "ledger" / "obligation_ledger.json"
        scaffold_obligation_ledger(ledger_path)

        args = argparse.Namespace(
            workspace=self.ws,
            spec=False,
            json=False,
            scaffold=False,
        )
        mock_proc_build = subprocess.CompletedProcess(
            args=["rea", "build-reconstruction-obligation-ledger"],
            returncode=0,
            stdout="Built obligation ledger: 1 obligation",
            stderr="",
        )
        mock_proc_eval = subprocess.CompletedProcess(
            args=["rea", "evaluate-reconstruction-coverage"],
            returncode=0,
            stdout="Coverage: 100% (1/1 satisfied)",
            stderr="",
        )

        def mock_subp(cmd, *a, **kw):
            if "build-reconstruction-obligation-ledger" in cmd:
                return mock_proc_build
            if "evaluate-reconstruction-coverage" in cmd:
                return mock_proc_eval
            return MagicMock()

        buf = io.StringIO()
        with patch("shutil.which", return_value="/usr/local/bin/rea"), patch(
            "subprocess.run", side_effect=mock_subp
        ) as mock_run, patch("sys.stdout", buf):
            code = cmd_verify(args)
            self.assertEqual(code, 0)
            self.assertEqual(mock_run.call_count, 2)
            self.assertIn("Cleanroom reconstruction verified via REA", buf.getvalue())


class TestAutoHealingREANode(unittest.TestCase):
    """Tests heal_rea_tooling auto-healing Node.js 24 LTS via pnpm."""

    def test_heal_rea_tooling_switches_node24_when_incompatible(self):
        mock_audit = {
            "rea_tooling": {"binary": "/usr/local/bin/rea", "status": "ok"},
        }
        mock_node_check = {
            "status": "WARNING",
            "rea_compatible": False,
            "version": "26.12.0",
        }
        mock_pnpm_proc = MagicMock()
        mock_pnpm_proc.returncode = 0

        with patch("harness.runtime.tool_checks.check_node_toolchain", return_value=mock_node_check), \
             patch("shutil.which", return_value="/usr/bin/pnpm"), \
             patch("subprocess.run", return_value=mock_pnpm_proc) as mock_subp, \
             patch("harness.runtime.tool_checks.find_jdk21_path", return_value=None), \
             patch("harness.runtime.tool_checks.configure_rea_mcp_server", return_value=([], [])):
            actions = heal_rea_tooling(mock_audit)
            self.assertTrue(any("switched to Node 24 LTS" in a for a in actions))
            mock_subp.assert_any_call(["/usr/bin/pnpm", "env", "use", "--global", "24"], capture_output=True, text=True)


if __name__ == "__main__":
    unittest.main()
