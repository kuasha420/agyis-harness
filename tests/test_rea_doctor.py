#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Arafat Zahan (@kuasha420)
# Corporate Stewardship & Infrastructure: Purrfect Software Limited (PSL)
# Governed by: ICARO-42/b Ordinance (Company-Supported Personal IP Framework)

"""
Hermetic test suite for REA opt-in diagnostics, dynamic JVM ladder,
disassembler contracts, auto-healing, and CLI provisioning (ADR-015 / ADR-028).
"""

from __future__ import annotations

import argparse
import io
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import time
import unittest
from unittest.mock import MagicMock, call, patch

from harness.cli import build_parser, main
from harness.commands.doctor import cmd_doctor
from harness.commands.init import cmd_init
from harness.commands.install import cmd_install
from harness.runtime.doctor import DEFAULT_MATRIX, print_cli_report, run_doctor
from harness.runtime.healing import heal_environment, heal_rea_tooling
from harness.runtime.tool_checks import (
    _parse_rea_providers,
    check_rea_tooling,
    find_rea_binary,
    is_rea_mcp_configured,
)


class TestReaDoctorFastPath(unittest.TestCase):
    """Verifies that standard `agyis doctor` runs zero-delay fast path with 0 warnings."""

    def test_doctor_fast_path_when_rea_missing(self):
        """Verifies fast path executes in <0.05s, skips subprocesses, and adds 0 warnings."""
        with patch("harness.runtime.tool_checks.find_rea_binary", return_value=None), \
             patch("subprocess.run") as mock_run:
            t0 = time.perf_counter()
            audit = run_doctor(DEFAULT_MATRIX, experimental_rea=False)
            elapsed = time.perf_counter() - t0

            # Sub-second benchmark invariant: fast path must execute well under 0.05s
            self.assertLess(elapsed, 0.05)
            self.assertEqual(audit["summary"]["warning"], 0)
            self.assertEqual(audit["summary"]["missing"], 0)
            rea_info = audit["rea_tooling"]
            self.assertTrue(rea_info.get("fast_path"))
            self.assertEqual(rea_info["status"], "optional_missing")
            self.assertIsNone(rea_info["binary"])

            # Asserts that subprocess.run was NEVER invoked for REA version or providers
            for c in mock_run.call_args_list:
                args, _ = c
                cmd_str = " ".join(str(a) for a in args[0]) if isinstance(args[0], (list, tuple)) else str(args[0])
                self.assertNotIn("rea --version", cmd_str)
                self.assertNotIn("rea providers", cmd_str)

    def test_doctor_fast_path_when_rea_present(self):
        """Verifies fast path detects binary presence without running heavy provider scans."""
        with patch("harness.runtime.tool_checks.find_rea_binary", return_value=Path("/usr/local/bin/rea")), \
             patch("subprocess.run") as mock_run:
            t0 = time.perf_counter()
            audit = run_doctor(DEFAULT_MATRIX, experimental_rea=False)
            elapsed = time.perf_counter() - t0

            self.assertLess(elapsed, 0.05)
            self.assertEqual(audit["summary"]["warning"], 0)
            rea_info = audit["rea_tooling"]
            self.assertTrue(rea_info.get("fast_path"))
            self.assertEqual(rea_info["status"], "ok")
            self.assertEqual(rea_info["binary"], "/usr/local/bin/rea")
            self.assertIsNone(rea_info["version"])

            for c in mock_run.call_args_list:
                args, _ = c
                cmd_str = " ".join(str(a) for a in args[0]) if isinstance(args[0], (list, tuple)) else str(args[0])
                self.assertNotIn("rea providers", cmd_str)


class TestReaDoctorDeepAudit(unittest.TestCase):
    """Verifies comprehensive deep diagnostics when --experimental-rea is active."""

    def test_doctor_deep_audit_clean_pass(self):
        """Verifies deep audit parses CLI version, MCP registration, and provider json."""
        mock_candidates = json.dumps({
            "analysis_provider_candidates": [
                {"name": "Ghidra", "available": True},
                {"name": "IDA MCP adapter", "available": False, "reason": "No IDA licence"},
            ]
        })

        def mock_subproc(cmd, *args, **kwargs):
            proc = MagicMock()
            proc.returncode = 0
            proc.stderr = ""
            if "--version" in cmd:
                proc.stdout = "rea 6.5.0\n"
            elif "providers" in cmd:
                proc.stdout = mock_candidates
            else:
                proc.stdout = "ok"
            return proc

        with patch("harness.runtime.tool_checks.find_rea_binary", return_value=Path("/usr/local/bin/rea")), \
             patch("harness.runtime.tool_checks.is_rea_mcp_configured", return_value=True), \
             patch("subprocess.run", side_effect=mock_subproc):
            audit = run_doctor(DEFAULT_MATRIX, experimental_rea=True)
            rea_info = audit["rea_tooling"]
            self.assertFalse(rea_info.get("fast_path"))
            self.assertEqual(rea_info["status"], "ok")
            self.assertEqual(rea_info["version"], "6.5.0")
            self.assertTrue(rea_info["mcp_configured"])
            self.assertEqual(rea_info["providers"]["active"], ["Ghidra"])
            self.assertEqual(rea_info["providers"]["unavailable"], ["IDA MCP adapter"])

    def test_doctor_deep_audit_outdated_rea_warns(self):
        """Verifies deep audit adds warning when REA CLI version is < 6.0.0."""
        def mock_subproc(cmd, *args, **kwargs):
            proc = MagicMock()
            proc.returncode = 0
            proc.stderr = ""
            if "--version" in cmd:
                proc.stdout = "rea 5.8.0\n"
            elif "providers" in cmd:
                proc.stdout = "{}"
            return proc

        with patch("harness.runtime.tool_checks.find_rea_binary", return_value=Path("/usr/local/bin/rea")), \
             patch("harness.runtime.tool_checks.is_rea_mcp_configured", return_value=True), \
             patch("subprocess.run", side_effect=mock_subproc):
            audit = run_doctor(DEFAULT_MATRIX, experimental_rea=True)
            self.assertEqual(audit["rea_tooling"]["status"], "warning")
            self.assertGreaterEqual(audit["summary"]["warning"], 1)
            self.assertIn("outdated", audit["rea_tooling"]["details"])

    def test_doctor_deep_audit_missing_rea_warns(self):
        """Verifies deep audit adds warning when REA binary is absent and opt-in was requested."""
        with patch("harness.runtime.tool_checks.find_rea_binary", return_value=None), \
             patch("harness.runtime.tool_checks.is_rea_mcp_configured", return_value=False), \
             patch("subprocess.run", return_value=MagicMock(returncode=0, stdout="1.0.0\n", stderr="")):
            audit = run_doctor(DEFAULT_MATRIX, experimental_rea=True)
            self.assertEqual(audit["rea_tooling"]["status"], "warning")
            self.assertGreaterEqual(audit["summary"]["warning"], 1)

    def test_doctor_deep_audit_unregistered_mcp_warns(self):
        """Verifies deep audit adds warning when REA is installed but MCP server is unconfigured."""
        def mock_subproc(cmd, *args, **kwargs):
            proc = MagicMock()
            proc.returncode = 0
            proc.stderr = ""
            if "--version" in cmd:
                proc.stdout = "rea 6.5.0\n"
            elif "providers" in cmd:
                proc.stdout = "{}"
            return proc

        with patch("harness.runtime.tool_checks.find_rea_binary", return_value=Path("/usr/local/bin/rea")), \
             patch("harness.runtime.tool_checks.is_rea_mcp_configured", return_value=False), \
             patch("subprocess.run", side_effect=mock_subproc):
            audit = run_doctor(DEFAULT_MATRIX, experimental_rea=True)
            self.assertEqual(audit["rea_tooling"]["status"], "warning")
            self.assertFalse(audit["rea_tooling"]["mcp_configured"])
            self.assertGreaterEqual(audit["summary"]["warning"], 1)


class TestReaNativeProvidersParsing(unittest.TestCase):
    """Verifies parsing of native `rea providers --json` output (ADR-032)."""

    def test_parse_analysis_provider_candidates(self):
        """Verifies structured candidate list with availability dicts and reasons."""
        raw_json = json.dumps({
            "analysis_provider_candidates": [
                {
                    "provider": {"name": "Ghidra", "id": "ghidra"},
                    "availability": {"available": True, "reason": None},
                },
                {
                    "provider": {"name": "IDA Pro", "id": "ida"},
                    "availability": {"available": False, "reason": "No IDA license located"},
                },
                {
                    "provider": {"name": "Rizin", "id": "rizin"},
                    "availability": {"available": True},
                },
            ]
        })
        parsed = _parse_rea_providers(raw_json)
        self.assertEqual(parsed["active"], ["Ghidra", "Rizin"])
        self.assertEqual(parsed["unavailable"], ["IDA Pro"])
        self.assertEqual(len(parsed["details"]), 3)
        self.assertEqual(parsed["details"][1]["reason"], "No IDA license located")

    def test_parse_flat_candidates_list(self):
        """Verifies candidate dicts without nested provider or availability objects."""
        raw_json = json.dumps({
            "providers": [
                {"name": "Hopper", "available": True},
                {"name": "JADX", "available": False, "reason": "jadx not found on PATH"},
            ]
        })
        parsed = _parse_rea_providers(raw_json)
        self.assertEqual(parsed["active"], ["Hopper"])
        self.assertEqual(parsed["unavailable"], ["JADX"])
        self.assertEqual(parsed["details"][0]["available"], True)
        self.assertEqual(parsed["details"][1]["reason"], "jadx not found on PATH")

    def test_parse_candidates_dict_mapping(self):
        """Verifies dictionary mapping candidate names to availability structures."""
        raw_json = json.dumps({
            "ghidra": True,
            "ida": {"available": False, "reason": "No headless binary"},
            "rizin": {"status": "available"},
        })
        parsed = _parse_rea_providers(raw_json)
        self.assertIn("ghidra", parsed["active"])
        self.assertIn("rizin", parsed["active"])
        self.assertIn("ida", parsed["unavailable"])
        ida_detail = next(d for d in parsed["details"] if d["name"] == "ida")
        self.assertEqual(ida_detail["reason"], "No headless binary")

    def test_parse_string_list_candidates(self):
        """Verifies simple list of provider name strings."""
        raw_json = json.dumps(["ghidra", "hopper", "cutter"])
        parsed = _parse_rea_providers(raw_json)
        self.assertEqual(parsed["active"], ["ghidra", "hopper", "cutter"])
        self.assertEqual(parsed["unavailable"], [])

    def test_parse_corrupted_json_graceful_degradation(self):
        """Verifies corrupted or invalid JSON returns empty collections without failing."""
        for invalid in ["", "{not valid json}", "12345", "null", "true"]:
            parsed = _parse_rea_providers(invalid)
            self.assertEqual(parsed["active"], [])
            self.assertEqual(parsed["unavailable"], [])
            self.assertEqual(parsed["details"], [])


class TestReaAutoHealing(unittest.TestCase):
    """Verifies safe zero-sudo user-space auto-healing with --heal and --experimental-rea."""

    def test_heal_rea_tooling_wires_mcp_config(self):
        """Verifies heal_rea_tooling installs package and writes definitive mcp_config.json."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_home = Path(tmp_dir)
            cfg_p = tmp_home / ".gemini" / "config" / "mcp_config.json"

            def mock_subproc(cmd, *args, **kwargs):
                proc = MagicMock()
                proc.returncode = 0
                proc.stderr = ""
                proc.stdout = "Installed"
                return proc

            with patch("pathlib.Path.home", return_value=tmp_home), \
                 patch("shutil.which", side_effect=lambda x: "/usr/bin/pnpm" if x == "pnpm" else None), \
                 patch.dict(os.environ, {"JAVA_HOME": "/usr/lib/jvm/java-21", "GHIDRA_INSTALL_DIR": "/opt/ghidra"}), \
                 patch("sys.stdout", new_callable=io.StringIO), \
                 patch("subprocess.run", side_effect=mock_subproc):
                audit = {
                    "os_family": "linux",
                    "tiers": {},
                    "rea_tooling": {"status": "warning", "binary": None},
                    "experimental_rea": True,
                }
                actions = heal_environment(audit, DEFAULT_MATRIX, experimental_rea=True)
                self.assertTrue(any("rea-agents" in act for act in actions))
                self.assertTrue(cfg_p.is_file())

                data = json.loads(cfg_p.read_text(encoding="utf-8"))
                rea_server = data["mcpServers"]["rea"]
                self.assertEqual(rea_server["command"], "rea")
                self.assertEqual(rea_server["args"], ["mcp"])
                self.assertEqual(rea_server["env"]["GHIDRA_INSTALL_DIR"], "/opt/ghidra")
                self.assertEqual(rea_server["env"]["JAVA_HOME"], "/usr/lib/jvm/java-21")
                self.assertEqual(rea_server["env"]["REA_MCP_INPUT_SCHEMA_PROFILE"], "full")
                self.assertEqual(rea_server["env"]["REA_MCP_OUTPUT_SCHEMA_PROFILE"], "off")


class TestReaCliFlagsAndProvisioning(unittest.TestCase):
    """Verifies CLI flag integration and workspace/global provisioning."""

    def test_cli_parser_experimental_rea_flags(self):
        """Verifies --experimental-rea flag is registered across doctor, init, onboard, install."""
        parser = build_parser()

        # 1. doctor
        args_doc = parser.parse_args(["doctor", "--experimental-rea"])
        self.assertTrue(args_doc.experimental_rea)
        args_doc_def = parser.parse_args(["doctor"])
        self.assertFalse(args_doc_def.experimental_rea)

        # 2. init
        args_init = parser.parse_args(["init", "--experimental-rea"])
        self.assertTrue(args_init.experimental_rea)
        args_init_def = parser.parse_args(["init"])
        self.assertFalse(args_init_def.experimental_rea)

        # 3. onboard
        args_onb = parser.parse_args(["onboard", "--experimental-rea"])
        self.assertTrue(args_onb.experimental_rea)
        args_onb_def = parser.parse_args(["onboard"])
        self.assertFalse(args_onb_def.experimental_rea)

        # 4. install
        args_inst = parser.parse_args(["install", "--experimental-rea"])
        self.assertTrue(args_inst.experimental_rea)
        args_inst_def = parser.parse_args(["install"])
        self.assertFalse(args_inst_def.experimental_rea)

    def test_cmd_init_scaffolds_ledger_and_records_config(self):
        """Verifies `agyis init --experimental-rea` scaffolds .agents/ledger/ and sets config."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            ws_dir = Path(tmp_dir) / "test_repo"
            ws_dir.mkdir()

            args = argparse.Namespace(
                path=str(ws_dir),
                stack=None,
                role=None,
                subproject=None,
                skills=None,
                agents=None,
                override=False,
                no_dedup=False,
                dry_run=False,
                json=True,
                experimental_rea=True,
            )

            with patch("sys.stdout", new_callable=io.StringIO), \
                 patch("harness.runtime.healing.provision_rea_skill") as mock_prov:
                code = cmd_init(args)
            self.assertEqual(code, 0)
            mock_prov.assert_called_once()

            # Assert .agyis/config.json exists with experimental_rea: true
            cfg_p = ws_dir / ".agyis" / "config.json"
            self.assertTrue(cfg_p.is_file())
            cfg_data = json.loads(cfg_p.read_text(encoding="utf-8"))
            self.assertTrue(cfg_data.get("experimental_rea"))

            # Assert .agents/ledger/ directory exists
            ledger_dir = ws_dir / ".agents" / "ledger"
            self.assertTrue(ledger_dir.is_dir())

    def test_cmd_install_configures_global_rea_mcp(self):
        """Verifies `agyis install --experimental-rea` configures global MCP server in config."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_home = Path(tmp_dir)
            cfg_p = tmp_home / ".gemini" / "config" / "mcp_config.json"

            args = argparse.Namespace(
                workspace=None,
                wheel=False,
                copy=False,
                symlink=False,
                global_install=True,
                bin_dir=None,
                target=tmp_home / ".gemini" / "plugins" / "agyis-harness",
                all_surfaces=False,
                dry_run=False,
                json=True,
                experimental_rea=True,
            )

            with patch("pathlib.Path.home", return_value=tmp_home), \
                 patch("sys.stdout", new_callable=io.StringIO), \
                 patch("harness.runtime.healing.provision_rea_skill") as mock_prov, \
                 patch("harness.delivery.PluginInstaller.install", return_value=MagicMock(success=True, mode="wheel", target_dir=tmp_home, source_dir=tmp_home, items_installed=[], message="Installed")):
                code = cmd_install(args)
            self.assertEqual(code, 0)
            mock_prov.assert_called_once()
            self.assertTrue(cfg_p.is_file())
            data = json.loads(cfg_p.read_text(encoding="utf-8"))
            self.assertIn("rea", data.get("mcpServers", {}))
            self.assertEqual(data["mcpServers"]["rea"]["env"]["REA_MCP_INPUT_SCHEMA_PROFILE"], "full")
            self.assertEqual(data["mcpServers"]["rea"]["env"]["REA_MCP_OUTPUT_SCHEMA_PROFILE"], "off")


if __name__ == "__main__":
    unittest.main()
