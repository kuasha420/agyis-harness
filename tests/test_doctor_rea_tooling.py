#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Arafat Zahan (@kuasha420)
# Corporate Stewardship & Infrastructure: Purrfect Software Limited (PSL)
# Governed by: ICARO-42/b Ordinance (Company-Supported Personal IP Framework)

"""
Unit and adversarial diagnostics tests for REA tooling detection, providers, and MCP config.
Split from test_doctor.py for sub-second ADR-015 verification.
"""

import argparse
import io
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import MagicMock, patch

from harness.commands.doctor import DEFAULT_MATRIX, cmd_doctor
from harness.runtime.doctor import print_cli_report, run_doctor
from harness.runtime.tool_checks import (
    _parse_rea_providers,
    check_rea_tooling,
    find_rea_binary,
    is_rea_mcp_configured,
    version_less_than,
)


class TestReaToolingDiagnostics(unittest.TestCase):
    """Hermetic unit tests for REA tooling detection, providers audit, MCP config, and doctor integration."""

    def test_find_rea_binary_on_path(self):
        """Verifies find_rea_binary detects executable rea binary on PATH."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            fake_bin = Path(tmp_dir) / "rea"
            fake_bin.write_text("#!/bin/sh\necho 6.5.0\n")
            fake_bin.chmod(0o755)

            with patch("shutil.which", return_value=str(fake_bin)):
                found = find_rea_binary()
                self.assertIsNotNone(found)
                self.assertEqual(found, fake_bin)

    def test_find_rea_binary_pnpm_home_fallback(self):
        """Verifies find_rea_binary checks $PNPM_HOME/rea when not on PATH."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            fake_pnpm_home = Path(tmp_dir) / "pnpm"
            fake_pnpm_home.mkdir()
            fake_bin = fake_pnpm_home / "rea"
            fake_bin.write_text("#!/bin/sh\n")
            fake_bin.chmod(0o755)

            with patch("shutil.which", return_value=None), \
                 patch.dict(os.environ, {"PNPM_HOME": str(fake_pnpm_home)}):
                found = find_rea_binary()
                self.assertEqual(found, fake_bin)

    def test_find_rea_binary_pnpm_standard_dir_fallback(self):
        """Verifies find_rea_binary checks ~/.local/share/pnpm/rea when PATH and PNPM_HOME are empty."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            fake_home = Path(tmp_dir)
            pnpm_bin_dir = fake_home / ".local" / "share" / "pnpm"
            pnpm_bin_dir.mkdir(parents=True)
            fake_bin = pnpm_bin_dir / "rea"
            fake_bin.write_text("#!/bin/sh\n")
            fake_bin.chmod(0o755)

            with patch("shutil.which", return_value=None), \
                 patch.dict(os.environ, {"PNPM_HOME": ""}), \
                 patch("harness.runtime.tool_checks.Path.home", return_value=fake_home):
                found = find_rea_binary()
                self.assertEqual(found, fake_bin)

    def test_find_rea_binary_not_executable(self):
        """Verifies find_rea_binary ignores candidate file without executable permissions."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            fake_bin = Path(tmp_dir) / "rea"
            fake_bin.write_text("not executable")
            fake_bin.chmod(0o644)

            with patch("shutil.which", return_value=str(fake_bin)), \
                 patch("harness.runtime.tool_checks.Path.home", return_value=Path(tmp_dir)), \
                 patch.dict(os.environ, {"PNPM_HOME": ""}):
                found = find_rea_binary()
                self.assertIsNone(found)

    def test_find_rea_binary_missing_returns_none(self):
        """Verifies find_rea_binary returns None when rea binary is not present anywhere."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            with patch("shutil.which", return_value=None), \
                 patch.dict(os.environ, {"PNPM_HOME": ""}), \
                 patch("harness.runtime.tool_checks.Path.home", return_value=Path(tmp_dir)):
                found = find_rea_binary()
                self.assertIsNone(found)

    def test_is_rea_mcp_configured(self):
        """Verifies is_rea_mcp_configured handles missing file, active config, disabled config, and corrupt JSON."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            config_file = Path(tmp_dir) / "mcp_config.json"

            # 1. Non-existent file
            self.assertFalse(is_rea_mcp_configured(config_file))

            # 2. Configured and enabled
            config_file.write_text(json.dumps({
                "mcpServers": {
                    "rea": {"command": "rea", "args": ["mcp"]}
                }
            }))
            self.assertTrue(is_rea_mcp_configured(config_file))

            # 3. Configured but disabled
            config_file.write_text(json.dumps({
                "mcpServers": {
                    "rea": {"command": "rea", "args": ["mcp"], "disabled": True}
                }
            }))
            self.assertFalse(is_rea_mcp_configured(config_file))

            # 4. Other servers, rea missing
            config_file.write_text(json.dumps({
                "mcpServers": {
                    "context7": {"command": "npx"}
                }
            }))
            self.assertFalse(is_rea_mcp_configured(config_file))

            # 5. Corrupt JSON
            config_file.write_text("{invalid json")
            self.assertFalse(is_rea_mcp_configured(config_file))

            # 6. Non-dict JSON (list)
            config_file.write_text("[]")
            self.assertFalse(is_rea_mcp_configured(config_file))

            # 7. Non-dict JSON (null)
            config_file.write_text("null")
            self.assertFalse(is_rea_mcp_configured(config_file))

            # 8. mcpServers is non-dict
            config_file.write_text(json.dumps({"mcpServers": ["rea"]}))
            self.assertFalse(is_rea_mcp_configured(config_file))

    def test_check_rea_tooling_missing_non_fatal(self):
        """Verifies check_rea_tooling returns optional_missing with remediation when binary is absent."""
        with patch("harness.runtime.tool_checks.find_rea_binary", return_value=None), \
             patch("harness.runtime.tool_checks.is_rea_mcp_configured", return_value=False):
            res = check_rea_tooling()
            self.assertEqual(res["status"], "optional_missing")
            self.assertIsNone(res["binary"])
            self.assertIsNone(res["version"])
            self.assertEqual(res["min_version"], "6.0.0")
            self.assertEqual(res["providers"]["active"], [])
            self.assertEqual(res["providers"]["unavailable"], [])
            self.assertIsNotNone(res["remediation"])
            self.assertIn("pnpm add -g rea-agents", res["remediation"])
            self.assertIn("REA binary not found", res["details"])

    def test_check_rea_tooling_present_clean(self):
        """Verifies check_rea_tooling returns status ok when version >= 6.0.0 and MCP is configured."""
        mock_candidates_json = json.dumps({
            "analysis_provider_candidates": [
                {
                    "provider": {"id": "ghidra", "name": "Ghidra"},
                    "availability": {"status": "available", "available": True}
                },
                {
                    "provider": {"id": "ida", "name": "IDA MCP adapter"},
                    "availability": {"status": "unavailable", "available": False, "reason": "No IDA"}
                }
            ]
        })

        def mock_subprocess_run(cmd, *args, **kwargs):
            proc = MagicMock()
            proc.returncode = 0
            proc.stderr = ""
            if "-v" in cmd or (cmd and "node" in str(cmd[0])):
                proc.stdout = "v24.22.1\n"
            elif "--version" in cmd:
                proc.stdout = "rea 6.5.0\n"
            elif "providers" in cmd:
                proc.stdout = mock_candidates_json
            return proc

        with patch("harness.runtime.tool_checks.find_rea_binary", return_value=Path("/usr/local/bin/rea")), \
             patch("harness.runtime.tool_checks.is_rea_mcp_configured", return_value=True), \
             patch("subprocess.run", side_effect=mock_subprocess_run):
            res = check_rea_tooling(experimental_rea=True)
            self.assertEqual(res["status"], "ok")
            self.assertEqual(res["binary"], "/usr/local/bin/rea")
            self.assertEqual(res["version"], "6.5.0")
            self.assertTrue(res["mcp_configured"])
            self.assertIsNone(res["remediation"])
            self.assertEqual(res["providers"]["active"], ["Ghidra"])
            self.assertEqual(res["providers"]["unavailable"], ["IDA MCP adapter"])
            self.assertIn("verified", res["details"])

    def test_check_rea_tooling_outdated_version(self):
        """Verifies check_rea_tooling returns warning when REA version is < 6.0.0."""
        def mock_subprocess_run(cmd, *args, **kwargs):
            proc = MagicMock()
            proc.returncode = 0
            proc.stderr = ""
            if "--version" in cmd:
                proc.stdout = "rea 5.9.1\n"
            elif "providers" in cmd:
                proc.stdout = "{}"
            return proc

        with patch("harness.runtime.tool_checks.find_rea_binary", return_value=Path("/usr/local/bin/rea")), \
             patch("harness.runtime.tool_checks.is_rea_mcp_configured", return_value=True), \
             patch("subprocess.run", side_effect=mock_subprocess_run):
            res = check_rea_tooling(experimental_rea=True)
            self.assertEqual(res["status"], "warning")
            self.assertEqual(res["version"], "5.9.1")
            self.assertIn("outdated", res["details"])
            self.assertIsNotNone(res["remediation"])
            self.assertIn("Update REA to >= 6.0.0", res["remediation"])

    def test_check_rea_tooling_unknown_version(self):
        """Verifies check_rea_tooling returns warning when version output cannot be parsed."""
        def mock_subprocess_run(cmd, *args, **kwargs):
            proc = MagicMock()
            proc.returncode = 0
            proc.stdout = "unexpected output\n"
            proc.stderr = ""
            return proc

        with patch("harness.runtime.tool_checks.find_rea_binary", return_value=Path("/usr/local/bin/rea")), \
             patch("harness.runtime.tool_checks.is_rea_mcp_configured", return_value=True), \
             patch("subprocess.run", side_effect=mock_subprocess_run):
            res = check_rea_tooling(experimental_rea=True)
            self.assertEqual(res["status"], "warning")
            self.assertIsNone(res["version"])
            self.assertIn("could not be determined", res["details"])

    def test_check_rea_tooling_nonzero_exit_code_ignored_version(self):
        """Verifies check_rea_tooling ignores version string and leaves it None when proc.returncode != 0."""
        def mock_subprocess_run(cmd, *args, **kwargs):
            proc = MagicMock()
            proc.returncode = 1
            proc.stdout = ""
            proc.stderr = "Node error: v20.10.0 crash trace\n"
            return proc

        with patch("harness.runtime.tool_checks.find_rea_binary", return_value=Path("/usr/local/bin/rea")), \
             patch("harness.runtime.tool_checks.is_rea_mcp_configured", return_value=True), \
             patch("subprocess.run", side_effect=mock_subprocess_run):
            res = check_rea_tooling(experimental_rea=True)
            self.assertEqual(res["status"], "warning")
            self.assertIsNone(res["version"])
            self.assertIn("could not be determined", res["details"])

    def test_check_rea_tooling_mcp_not_configured(self):
        """Verifies check_rea_tooling returns warning when binary is valid but MCP is unconfigured."""
        def mock_subprocess_run(cmd, *args, **kwargs):
            proc = MagicMock()
            proc.returncode = 0
            proc.stderr = ""
            if "-v" in cmd or (cmd and "node" in str(cmd[0])):
                proc.stdout = "v24.22.1\n"
            elif "--version" in cmd:
                proc.stdout = "rea 6.5.0\n"
            elif "providers" in cmd:
                proc.stdout = "{}"
            return proc

        with patch("harness.runtime.tool_checks.find_rea_binary", return_value=Path("/usr/local/bin/rea")), \
             patch("harness.runtime.tool_checks.is_rea_mcp_configured", return_value=False), \
             patch("subprocess.run", side_effect=mock_subprocess_run):
            res = check_rea_tooling(experimental_rea=True)
            self.assertEqual(res["status"], "warning")
            self.assertFalse(res["mcp_configured"])
            self.assertIn("not registered", res["details"])
            self.assertIsNotNone(res["remediation"])
            self.assertIn("rea setup", res["remediation"])

    def test_parse_rea_providers_formats_and_resilience(self):
        """Verifies _parse_rea_providers handles multiple formats, corrupt JSON, and timeouts cleanly."""
        # 1. Dict mapping format
        dict_fmt = json.dumps({"providers": {"ghidra": True, "hopper": False}})
        res1 = _parse_rea_providers(dict_fmt)
        self.assertIn("ghidra", res1["active"])
        self.assertIn("hopper", res1["unavailable"])

        # 2. List of strings
        list_str_fmt = json.dumps(["ghidra", "rizin"])
        res2 = _parse_rea_providers(list_str_fmt)
        self.assertEqual(res2["active"], ["ghidra", "rizin"])

        # 3. Direct candidates list
        cand_list = json.dumps([{"name": "ghidra", "available": True}, {"name": "ida", "available": False}])
        res3 = _parse_rea_providers(cand_list)
        self.assertEqual(res3["active"], ["ghidra"])
        self.assertEqual(res3["unavailable"], ["ida"])

        # 4. Corrupted JSON
        res4 = _parse_rea_providers("not valid json")
        self.assertEqual(res4["active"], [])
        self.assertEqual(res4["unavailable"], [])
        self.assertEqual(res4["details"], [])

        # 5. Non-dict/list JSON (e.g. number)
        res5 = _parse_rea_providers("42")
        self.assertEqual(res5["active"], [])
        self.assertEqual(res5["unavailable"], [])

    def test_run_doctor_rea_integration_optional_missing_non_fatal(self):
        """Verifies run_doctor does not increment missing count when REA is optional_missing."""
        mock_rea = {
            "status": "optional_missing",
            "binary": None,
            "version": None,
            "min_version": "6.0.0",
            "providers": {"active": [], "unavailable": [], "details": []},
            "mcp_configured": False,
            "remediation": "pnpm add -g rea-agents",
            "details": "REA binary not found",
        }

        def mock_run(cmd, *args, **kwargs):
            proc = MagicMock()
            proc.returncode = 0
            proc.stdout = "99.0.0"
            return proc

        mock_cli = {
            "status": "OK",
            "path": "/usr/local/bin/agyis",
            "collision": False,
            "agyis_status": "OK",
            "agyis_path": "/usr/local/bin/agyis",
            "psl_details": {"status": "OK", "collision": False, "path": "/usr/local/bin/psl"},
            "psl_collision": {"status": "OK", "collision": False, "path": "/usr/local/bin/psl"},
            "details": "Agyis launcher OK",
            "remediation": None,
        }
        mock_tool = {
            "name": "mock",
            "binary": "mock",
            "status": "OK",
            "path": "/usr/bin/mock",
            "version": "99.0.0",
            "min_version": "1.0.0",
            "is_shim": False,
            "shim_details": None,
            "is_collision": False,
            "collision_details": None,
            "spec": {},
        }

        with patch("subprocess.run", side_effect=mock_run), \
             patch("harness.runtime.doctor.check_tool", return_value=mock_tool), \
             patch("harness.runtime.doctor.check_cli_binary", return_value=mock_cli), \
             patch("harness.runtime.doctor.check_rea_tooling", return_value=mock_rea), \
             patch("harness.runtime.doctor.check_telemetry_daemon", return_value={"status": "OK"}):
            audit = run_doctor(DEFAULT_MATRIX)
            self.assertEqual(audit["rea_tooling"]["status"], "optional_missing")
            self.assertEqual(audit["summary"]["missing"], 0)
            self.assertGreaterEqual(audit["summary"]["optional_missing"], 1)

    def test_run_doctor_rea_integration_warning_increments_summary(self):
        """Verifies run_doctor increments warning count when REA tooling reports warning."""
        mock_rea = {
            "status": "warning",
            "binary": "/usr/local/bin/rea",
            "version": "5.0.0",
            "min_version": "6.0.0",
            "providers": {"active": [], "unavailable": [], "details": []},
            "mcp_configured": True,
            "remediation": "Update REA",
            "details": "Outdated version",
        }

        def mock_run(cmd, *args, **kwargs):
            proc = MagicMock()
            proc.returncode = 0
            proc.stdout = "99.0.0"
            return proc

        mock_cli = {
            "status": "OK",
            "path": "/usr/local/bin/agyis",
            "collision": False,
            "agyis_status": "OK",
            "agyis_path": "/usr/local/bin/agyis",
            "psl_details": {"status": "OK", "collision": False, "path": "/usr/local/bin/psl"},
            "psl_collision": {"status": "OK", "collision": False, "path": "/usr/local/bin/psl"},
            "details": "Agyis launcher OK",
            "remediation": None,
        }
        mock_tool = {
            "name": "mock",
            "binary": "mock",
            "status": "OK",
            "path": "/usr/bin/mock",
            "version": "99.0.0",
            "min_version": "1.0.0",
            "is_shim": False,
            "shim_details": None,
            "is_collision": False,
            "collision_details": None,
            "spec": {},
        }

        with tempfile.TemporaryDirectory() as clean_ws, \
             patch("subprocess.run", side_effect=mock_run), \
             patch("harness.runtime.doctor.check_tool", return_value=mock_tool), \
             patch("harness.runtime.doctor.check_cli_binary", return_value=mock_cli), \
             patch("harness.runtime.doctor.check_rea_tooling", return_value=mock_rea), \
             patch("harness.runtime.doctor.check_telemetry_daemon", return_value={"status": "OK"}), \
             patch("harness.runtime.doctor.check_database_port_conflicts", return_value={"status": "PASS"}):
            audit = run_doctor(DEFAULT_MATRIX, workspace_root=Path(clean_ws), rea=True)
            self.assertEqual(audit["rea_tooling"]["status"], "warning")
            self.assertGreaterEqual(audit["summary"]["warning"], 1)

            # Conversely, when rea=False and experimental_rea=False in clean workspace, fast-path adds 0 warnings
            audit_fast = run_doctor(DEFAULT_MATRIX, workspace_root=Path(clean_ws), experimental_rea=False)
            self.assertEqual(audit_fast["summary"]["warning"], 0)

    def test_print_cli_report_rea_formatting_variants(self):
        """Verifies print_cli_report formats ok, optional_missing, and warning REA statuses correctly."""
        base_audit = {
            "os_family": "linux",
            "hermetic_python_available": "/fake/python",
            "path_environment": "/bin",
            "cli_binary": {"status": "OK", "path": "/bin/agyis"},
            "psl_collision": {"status": "OK", "path": "/bin/psl"},
            "duplicate_agents": {"status": "OK", "details": "none"},
            "node_script_hygiene": {"status": "OK", "details": "clean"},
            "hooks_health": {"status": "OK", "checked_hooks": [], "hooks_path": "hooks.json"},
            "tiers": {},
            "summary": {"ok": 1, "warning": 0, "outdated": 0, "missing": 0, "total_tools": 1},
        }

        # 1. OK status
        audit_ok = dict(base_audit)
        audit_ok["rea_tooling"] = {
            "status": "ok",
            "version": "6.5.0",
            "binary": "/usr/local/bin/rea",
            "providers": {"active": ["Ghidra", "Rizin"], "unavailable": []},
            "mcp_configured": True,
            "remediation": None,
            "details": "ok",
        }
        with patch("sys.stdout", new_callable=io.StringIO) as mock_out:
            print_cli_report(audit_ok)
            out = mock_out.getvalue()
            self.assertIn("REA Tooling:", out)
            self.assertIn("rea 6.5.0 (/usr/local/bin/rea)", out)
            self.assertIn("Providers: 2 active", out)
            self.assertIn("MCP: Configured", out)

        # 2. OPTIONAL_MISSING status
        audit_missing = dict(base_audit)
        audit_missing["rea_tooling"] = {
            "status": "optional_missing",
            "version": None,
            "binary": None,
            "providers": {"active": [], "unavailable": []},
            "mcp_configured": False,
            "remediation": "pnpm add -g rea-agents (or run 'rea setup')",
            "details": "not found",
        }
        with patch("sys.stdout", new_callable=io.StringIO) as mock_out:
            print_cli_report(audit_missing)
            out = mock_out.getvalue()
            self.assertIn("REA Tooling:", out)
            self.assertIn("REA not detected (optional reverse engineering toolchain)", out)
            self.assertIn("pnpm add -g rea-agents (or run 'rea setup')", out)

        # 3. WARNING status
        audit_warn = dict(base_audit)
        audit_warn["rea_tooling"] = {
            "status": "warning",
            "version": "5.9.0",
            "binary": "/bin/rea",
            "providers": {"active": [], "unavailable": []},
            "mcp_configured": False,
            "remediation": "Run 'rea setup'",
            "details": "REA MCP server is not registered",
        }
        with patch("sys.stdout", new_callable=io.StringIO) as mock_out:
            print_cli_report(audit_warn)
            out = mock_out.getvalue()
            self.assertIn("REA Tooling:", out)
            self.assertIn("REA MCP server is not registered", out)
            self.assertIn("Run 'rea setup'", out)

        # 4. OK status with providers=None
        audit_none_prov = dict(base_audit)
        audit_none_prov["rea_tooling"] = {
            "status": "ok",
            "version": "6.5.0",
            "binary": "/usr/local/bin/rea",
            "providers": None,
            "mcp_configured": True,
            "remediation": None,
            "details": "ok",
        }
        with patch("sys.stdout", new_callable=io.StringIO) as mock_out:
            print_cli_report(audit_none_prov)
            out = mock_out.getvalue()
            self.assertIn("REA Tooling:", out)
            self.assertIn("Providers: 0 active", out)


class TestAdversarialReaDoctorProbing(unittest.TestCase):
    """Adversarial stress testing and edge-case probing for REA diagnostics and doctor integration."""

    def test_rea_subprocess_timeout_expired_graceful(self):
        """Verifies check_rea_tooling handles subprocess.TimeoutExpired without hanging or crashing."""
        def mock_timeout_version(cmd, *args, **kwargs):
            if "--version" in cmd:
                raise subprocess.TimeoutExpired(cmd=cmd, timeout=3.0)
            proc = MagicMock()
            proc.returncode = 0
            proc.stdout = "{}"
            proc.stderr = ""
            return proc

        with patch("harness.runtime.tool_checks.find_rea_binary", return_value=Path("/usr/bin/rea")), \
             patch("harness.runtime.tool_checks.is_rea_mcp_configured", return_value=True), \
             patch("subprocess.run", side_effect=mock_timeout_version):
            res = check_rea_tooling(timeout=0.1, experimental_rea=True)
            self.assertEqual(res["status"], "warning")
            self.assertIsNone(res["version"])
            self.assertIn("could not be determined", res["details"])

        def mock_timeout_providers(cmd, *args, **kwargs):
            if "-v" in cmd or (cmd and "node" in str(cmd[0])):
                proc = MagicMock()
                proc.returncode = 0
                proc.stdout = "v24.22.1\n"
                proc.stderr = ""
                return proc
            if "providers" in cmd:
                raise subprocess.TimeoutExpired(cmd=cmd, timeout=3.0)
            proc = MagicMock()
            proc.returncode = 0
            proc.stdout = "rea 6.1.0\n"
            proc.stderr = ""
            return proc

        with patch("harness.runtime.tool_checks.find_rea_binary", return_value=Path("/usr/bin/rea")), \
             patch("harness.runtime.tool_checks.is_rea_mcp_configured", return_value=True), \
             patch("subprocess.run", side_effect=mock_timeout_providers):
            res = check_rea_tooling(timeout=0.1, experimental_rea=True)
            self.assertEqual(res["status"], "ok")
            self.assertEqual(res["version"], "6.1.0")
            self.assertEqual(res["providers"]["active"], [])
            self.assertEqual(res["providers"]["unavailable"], [])

    def test_rea_providers_nonzero_exit_and_stderr_dumps(self):
        """Verifies check_rea_tooling discards non-zero exit code and large stderr dumps gracefully."""
        huge_stderr = "FATAL: Segmentation fault (core dumped)\n" + ("stack frame\n" * 500)
        def mock_crash_providers(cmd, *args, **kwargs):
            proc = MagicMock()
            if "-v" in cmd or (cmd and "node" in str(cmd[0])):
                proc.returncode = 0
                proc.stdout = "v24.22.1\n"
                proc.stderr = ""
            elif "providers" in cmd:
                proc.returncode = 139
                proc.stdout = ""
                proc.stderr = huge_stderr
            else:
                proc.returncode = 0
                proc.stdout = "rea 6.2.0\n"
                proc.stderr = ""
            return proc

        with patch("harness.runtime.tool_checks.find_rea_binary", return_value=Path("/usr/bin/rea")), \
             patch("harness.runtime.tool_checks.is_rea_mcp_configured", return_value=True), \
             patch("subprocess.run", side_effect=mock_crash_providers):
            res = check_rea_tooling(experimental_rea=True)
            self.assertEqual(res["status"], "ok")
            self.assertEqual(res["version"], "6.2.0")
            self.assertEqual(res["providers"]["active"], [])
            self.assertEqual(res["providers"]["unavailable"], [])

    def test_rea_subprocess_malformed_unicode_and_binary_garbage(self):
        """Verifies check_rea_tooling gracefully handles malformed Unicode and binary garbage."""
        def mock_binary_garbage(cmd, *args, **kwargs):
            proc = MagicMock()
            proc.returncode = 0
            if "-v" in cmd or (cmd and "node" in str(cmd[0])):
                proc.stdout = "v24.22.1\n"
                proc.stderr = ""
            elif "--version" in cmd:
                proc.stdout = "rea \ufffd\ufffd 6.3.0 \x00\x01\xfe\xff"
                proc.stderr = ""
            elif "providers" in cmd:
                proc.stdout = "\x00\x01\xfe\xff {invalid binary json"
                proc.stderr = ""
            return proc

        with patch("harness.runtime.tool_checks.find_rea_binary", return_value=Path("/usr/bin/rea")), \
             patch("harness.runtime.tool_checks.is_rea_mcp_configured", return_value=True), \
             patch("subprocess.run", side_effect=mock_binary_garbage):
            res = check_rea_tooling(experimental_rea=True)
            self.assertEqual(res["status"], "ok")
            self.assertEqual(res["version"], "6.3.0")
            self.assertEqual(res["providers"]["active"], [])

        def mock_unicode_decode_err(cmd, *args, **kwargs):
            raise UnicodeDecodeError("utf-8", b"\xff\xfe", 0, 1, "invalid start byte")

        with patch("harness.runtime.tool_checks.find_rea_binary", return_value=Path("/usr/bin/rea")), \
             patch("harness.runtime.tool_checks.is_rea_mcp_configured", return_value=True), \
             patch("subprocess.run", side_effect=mock_unicode_decode_err):
            res = check_rea_tooling(experimental_rea=True)
            self.assertEqual(res["status"], "warning")
            self.assertIsNone(res["version"])

    def test_weird_version_formats(self):
        """Verifies check_rea_tooling and version_less_than handle weird version formats properly."""
        test_cases = [
            ("rea 6.0.0-beta.1", "6.0.0", "ok"),
            ("rea v6.0.0", "6.0.0", "ok"),
            ("rea 6.0", "6.0", "ok"),
            ("rea 7.0.0rc2", "7.0.0", "ok"),
            ("rea 6.10.12", "6.10.12", "ok"),
            ("rea 5.99.9", "5.99.9", "warning"),
            ("rea 5.9.1-alpha", "5.9.1", "warning"),
        ]

        for stdout_val, expected_ver, expected_status in test_cases:
            def mock_ver(cmd, *args, **kwargs):
                proc = MagicMock()
                proc.returncode = 0
                proc.stderr = ""
                if "-v" in cmd or (cmd and "node" in str(cmd[0])):
                    proc.stdout = "v24.22.1\n"
                elif "--version" in cmd:
                    proc.stdout = stdout_val
                else:
                    proc.stdout = "{}"
                return proc

            with patch("harness.runtime.tool_checks.find_rea_binary", return_value=Path("/usr/bin/rea")), \
                 patch("harness.runtime.tool_checks.is_rea_mcp_configured", return_value=True), \
                 patch("subprocess.run", side_effect=mock_ver):
                res = check_rea_tooling(experimental_rea=True)
                self.assertEqual(res["status"], expected_status, f"Failed for {stdout_val}")
                self.assertEqual(res["version"], expected_ver, f"Wrong extracted version for {stdout_val}")

        self.assertFalse(version_less_than((6, 0), (6, 0, 0)))
        self.assertFalse(version_less_than((6, 0, 0), (6, 0)))
        self.assertFalse(version_less_than((6, 10, 12), (6, 0, 0)))
        self.assertTrue(version_less_than((5, 99, 9), (6, 0, 0)))
        self.assertTrue(version_less_than((5,), (6, 0, 0)))

    def test_mcp_config_edge_cases(self):
        """Verifies is_rea_mcp_configured handles all configuration anomalies and disabled variations."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir)

            empty_file = tmp_path / "empty.json"
            empty_file.write_text("")
            self.assertFalse(is_rea_mcp_configured(empty_file))

            dummy_dir = tmp_path / "dir_config"
            dummy_dir.mkdir()
            self.assertFalse(is_rea_mcp_configured(dummy_dir))

            with patch("builtins.open", side_effect=PermissionError("Permission denied")):
                self.assertFalse(is_rea_mcp_configured(empty_file))

            cfg_invalid = tmp_path / "invalid_rea.json"
            cfg_invalid.write_text(json.dumps({"mcpServers": {"rea": "invalid_string"}}))
            self.assertFalse(is_rea_mcp_configured(cfg_invalid))

            cfg_none = tmp_path / "none_rea.json"
            cfg_none.write_text(json.dumps({"mcpServers": {"rea": None}}))
            self.assertFalse(is_rea_mcp_configured(cfg_none))

            cfg_list = tmp_path / "list_rea.json"
            cfg_list.write_text(json.dumps({"mcpServers": {"rea": [1, 2, 3]}}))
            self.assertFalse(is_rea_mcp_configured(cfg_list))

            cfg_test = tmp_path / "test_disabled.json"

            for dis_val in [False, "false", "False", "0", 0, None]:
                payload = {"mcpServers": {"rea": {"command": "rea"}}}
                if dis_val is not None:
                    payload["mcpServers"]["rea"]["disabled"] = dis_val
                cfg_test.write_text(json.dumps(payload))
                self.assertTrue(is_rea_mcp_configured(cfg_test), f"Expected enabled for disabled={dis_val}")

            for dis_val in [True, "true", "True", "1", 1, "yes"]:
                payload = {"mcpServers": {"rea": {"command": "rea", "disabled": dis_val}}}
                cfg_test.write_text(json.dumps(payload))
                self.assertFalse(is_rea_mcp_configured(cfg_test), f"Expected disabled for disabled={dis_val}")

    def test_broken_symlinks_and_non_executable_candidates(self):
        """Verifies find_rea_binary ignores broken symlinks, directories, and non-executable candidates."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir)

            broken_target = tmp_path / "nonexistent_target"
            broken_symlink = tmp_path / "broken_rea"
            try:
                broken_symlink.symlink_to(broken_target)
            except OSError:
                pass

            if broken_symlink.is_symlink():
                with patch("shutil.which", return_value=str(broken_symlink)), \
                     patch.dict(os.environ, {"PNPM_HOME": ""}), \
                     patch("harness.runtime.tool_checks.Path.home", return_value=tmp_path):
                    self.assertIsNone(find_rea_binary())

            pnpm_bin_dir = tmp_path / ".local" / "share" / "pnpm"
            pnpm_bin_dir.mkdir(parents=True)
            non_exec_cand = pnpm_bin_dir / "rea"
            non_exec_cand.write_text("#!/bin/sh\necho rea\n")
            non_exec_cand.chmod(0o644)

            with patch("shutil.which", return_value=None), \
                 patch.dict(os.environ, {"PNPM_HOME": ""}), \
                 patch("harness.runtime.tool_checks.Path.home", return_value=tmp_path):
                self.assertIsNone(find_rea_binary())

            non_exec_cand.unlink()
            cand_dir = pnpm_bin_dir / "rea"
            cand_dir.mkdir()

            with patch("shutil.which", return_value=None), \
                 patch.dict(os.environ, {"PNPM_HOME": ""}), \
                 patch("harness.runtime.tool_checks.Path.home", return_value=tmp_path):
                self.assertIsNone(find_rea_binary())

            with patch("shutil.which", return_value=None), \
                 patch.dict(os.environ, {"PNPM_HOME": ""}), \
                 patch("pathlib.Path.is_file", side_effect=PermissionError("Stat denied")):
                self.assertIsNone(find_rea_binary())

    def test_doctor_exit_code_strictly_zero_across_all_rea_states(self):
        """Verifies cmd_doctor returns exit code 0 across ALL REA states when tier tools are OK."""
        args = argparse.Namespace(matrix=DEFAULT_MATRIX, json=False, heal=False)

        rea_states = [
            {
                "status": "optional_missing",
                "binary": None,
                "version": None,
                "min_version": "6.0.0",
                "providers": {"active": [], "unavailable": [], "details": []},
                "mcp_configured": False,
                "remediation": "pnpm add -g rea-agents",
                "details": "not found",
            },
            {
                "status": "warning",
                "binary": "/usr/local/bin/rea",
                "version": "5.8.0",
                "min_version": "6.0.0",
                "providers": {"active": [], "unavailable": [], "details": []},
                "mcp_configured": True,
                "remediation": "Update REA",
                "details": "Outdated REA version",
            },
            {
                "status": "warning",
                "binary": "/usr/local/bin/rea",
                "version": "6.5.0",
                "min_version": "6.0.0",
                "providers": {"active": [], "unavailable": [], "details": []},
                "mcp_configured": False,
                "remediation": "Run rea setup",
                "details": "MCP not configured",
            },
            {
                "status": "warning",
                "binary": "/usr/local/bin/rea",
                "version": None,
                "min_version": "6.0.0",
                "providers": {"active": [], "unavailable": [], "details": []},
                "mcp_configured": True,
                "remediation": "Check binary",
                "details": "Timeout determining version",
            },
            {
                "status": "ok",
                "binary": "/usr/local/bin/rea",
                "version": "6.5.0",
                "min_version": "6.0.0",
                "providers": {"active": ["Ghidra"], "unavailable": [], "details": []},
                "mcp_configured": True,
                "remediation": None,
                "details": "Verified",
            },
        ]

        def mock_tool_ok(cmd, *args, **kwargs):
            proc = MagicMock()
            proc.returncode = 0
            proc.stdout = "99.0.0"
            proc.stderr = ""
            return proc

        for rea_state in rea_states:
            with patch("shutil.which", side_effect=lambda x: f"/usr/bin/{x}"), \
                 patch("subprocess.run", side_effect=mock_tool_ok), \
                 patch("harness.runtime.doctor.check_rea_tooling", return_value=rea_state), \
                 patch("sys.stdout", new_callable=io.StringIO):
                code = cmd_doctor(args)
                self.assertEqual(code, 0, f"Doctor should exit 0 for REA state {rea_state['status']}")


if __name__ == "__main__":
    unittest.main()
