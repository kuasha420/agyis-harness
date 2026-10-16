#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Arafat Zahan (@kuasha420)
# Corporate Stewardship & Infrastructure: Purrfect Software Limited (PSL)
# Governed by: ICARO-42/b Ordinance (Company-Supported Personal IP Framework)

"""
Unit and integration tests for Agyis Workstation Doctor and CLI behavior:
- harness.runtime.doctor (run_doctor, print_cli_report, subtle backronym)
- harness.runtime.tool_checks (check_cli_binary, check_psl_collision)
- harness.commands.doctor (cmd_doctor, --json, --heal, exit codes)
- CLI invocation comparison (agyis doctor vs psl doctor)
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

from harness.cli import PSL_DEPRECATION_WARNING, deprecated_psl_main, main
from harness.commands.doctor import DEFAULT_MATRIX, cmd_doctor
from harness.runtime.doctor import (
    check_duplicate_skills,
    print_cli_report,
    run_doctor,
)
from harness.runtime.tool_checks import (
    _parse_rea_providers,
    check_cli_binary,
    check_psl_collision,
    check_rea_tooling,
    find_rea_binary,
    is_rea_mcp_configured,
    version_less_than,
)


class TestDoctorDiagnostics(unittest.TestCase):
    """Tests core doctor diagnostics and subtle backronym presentation."""

    def test_subtle_backronym_in_report(self):
        """Verifies print_cli_report includes the subtle backronym 'Antigravity Immune System'."""
        sample_audit = {
            "os_family": "linux",
            "hermetic_python_available": "/fake/uv/python3",
            "path_environment": "/usr/bin:/bin",
            "cli_binary": {
                "status": "OK",
                "agyis_status": "OK",
                "agyis_path": "/home/user/.local/bin/agyis",
                "details": "ok",
            },
            "psl_collision": {
                "status": "OK",
                "collision": False,
                "path": "/home/user/.local/bin/psl",
            },
            "duplicate_agents": {"status": "OK", "details": "none"},
            "node_script_hygiene": {"status": "OK", "details": "clean"},
            "hooks_health": {"status": "OK", "checked_hooks": ["anti-drift"], "hooks_path": "hooks.json"},
            "tiers": {},
            "summary": {"ok": 5, "warning": 0, "outdated": 0, "missing": 0, "total_tools": 5},
        }
        with patch("sys.stdout", new_callable=io.StringIO) as mock_out:
            print_cli_report(sample_audit)
            output = mock_out.getvalue()

        # Assert subtle backronym and header presence
        self.assertIn("Antigravity Immune System", output)
        self.assertIn("AGYIS WORKSTATION DOCTOR", output)
        self.assertIn("Agyis Launcher", output)
        self.assertIn("Summary: 5 OK", output)

    def test_run_doctor_audit_structure(self):
        """Verifies run_doctor returns all expected keys including cli_binary and psl_collision."""
        self.assertTrue(DEFAULT_MATRIX.exists())

        def mock_run(cmd, *args, **kwargs):
            proc = MagicMock()
            proc.returncode = 0
            proc.stderr = ""
            proc.stdout = "99.0.0"
            return proc

        with patch("subprocess.run", side_effect=mock_run):
            audit = run_doctor(DEFAULT_MATRIX)

        self.assertIn("os_family", audit)
        self.assertIn("hermetic_python_available", audit)
        self.assertIn("cli_binary", audit)
        self.assertIn("psl_collision", audit)
        self.assertIn("rea_tooling", audit)
        self.assertIn("tiers", audit)
        self.assertIn("summary", audit)
        self.assertIn("tier_1_languages", audit["tiers"])
        self.assertIn("tier_2_swe_cli", audit["tiers"])
        self.assertIn("tier_3_mesh_host", audit["tiers"])

    def test_run_doctor_missing_matrix_raises_error(self):
        """Verifies run_doctor raises FileNotFoundError for non-existent matrix path."""
        nonexistent = Path("/nonexistent/matrix_xyz_123.json")
        with self.assertRaises(FileNotFoundError):
            run_doctor(nonexistent)


class TestCliBinaryProbes(unittest.TestCase):
    """Tests check_cli_binary() probing agyis primary binary and psl collision."""

    def test_check_cli_binary_both_present_clean(self):
        """Passes with status OK when both agyis and psl resolve to valid harness scripts."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            bin_dir = Path(tmp_dir)
            agyis_bin = bin_dir / "agyis"
            psl_bin = bin_dir / "psl"
            agyis_bin.write_text("#!/usr/bin/env python3\nfrom harness.cli import main\nmain()\n")
            psl_bin.write_text("#!/usr/bin/env python3\nfrom harness.cli import deprecated_psl_main\n")

            def mock_which(cmd):
                if cmd == "agyis":
                    return str(agyis_bin)
                elif cmd == "psl":
                    return str(psl_bin)
                return None

            with patch("shutil.which", side_effect=mock_which):
                res = check_cli_binary()
                self.assertEqual(res["status"], "OK")
                self.assertEqual(res["agyis_status"], "OK")
                self.assertEqual(res["agyis_path"], str(agyis_bin))
                self.assertFalse(res["psl_collision"]["collision"])

    def test_check_cli_binary_agyis_only_clean(self):
        """Passes with status OK when agyis is present and psl is absent (deprecation lifecycle)."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            agyis_bin = Path(tmp_dir) / "agyis"
            agyis_bin.write_text("#!/usr/bin/env python3\n# agyis launcher\n")

            def mock_which(cmd):
                if cmd == "agyis":
                    return str(agyis_bin)
                return None

            with patch("shutil.which", side_effect=mock_which):
                res = check_cli_binary()
                self.assertEqual(res["status"], "OK")
                self.assertEqual(res["agyis_status"], "OK")
                self.assertIsNone(res["psl_collision"]["path"])
                self.assertFalse(res["psl_collision"]["collision"])

    def test_check_cli_binary_agyis_missing(self):
        """Yields WARNING when agyis is missing from PATH."""
        def mock_which(cmd):
            return None

        with patch("shutil.which", side_effect=mock_which):
            res = check_cli_binary()
            self.assertEqual(res["status"], "WARNING")
            self.assertEqual(res["agyis_status"], "WARNING")
            self.assertIsNone(res["agyis_path"])
            self.assertIsNotNone(res["remediation"])
            self.assertIn("harness.cli install", res["remediation"])

    def test_check_cli_binary_agyis_foreign(self):
        """Yields WARNING when agyis resolves to a foreign non-harness binary."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            foreign_bin = Path(tmp_dir) / "agyis"
            foreign_bin.write_text("#!/bin/sh\necho 'some unrelated tool'\n")

            with patch("shutil.which", return_value=str(foreign_bin)):
                res = check_cli_binary()
                self.assertEqual(res["status"], "WARNING")
                self.assertEqual(res["agyis_status"], "WARNING")
                self.assertIn("non-harness binary", res["agyis_details"])

    def test_check_cli_binary_psl_system_libpsl_collision(self):
        """Detects system libpsl collision on psl while agyis is clean."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            agyis_bin = Path(tmp_dir) / "agyis"
            agyis_bin.write_text("#!/usr/bin/env python3\nfrom harness.cli import main\n")

            def mock_which(cmd):
                if cmd == "agyis":
                    return str(agyis_bin)
                elif cmd == "psl":
                    return "/usr/bin/psl"
                return None

            with patch("shutil.which", side_effect=mock_which):
                res = check_cli_binary()
                self.assertEqual(res["status"], "WARNING")
                self.assertEqual(res["agyis_status"], "OK")
                self.assertTrue(res["psl_collision"]["collision"])
                self.assertIn("system libpsl", res["psl_collision"]["details"])


class TestDoctorCliCommand(unittest.TestCase):
    """Tests harness.commands.doctor.cmd_doctor execution and flags."""

    def test_cmd_doctor_json_mode(self):
        """Verifies cmd_doctor with --json outputs parseable JSON and exits 0."""
        args = argparse.Namespace(matrix=DEFAULT_MATRIX, json=True, heal=False)

        def mock_run(cmd, *args, **kwargs):
            proc = MagicMock()
            proc.returncode = 0
            proc.stderr = ""
            proc.stdout = "99.0.0"
            return proc

        with patch("shutil.which", side_effect=lambda x: f"/usr/bin/{x}"), \
             patch("subprocess.run", side_effect=mock_run), \
             patch("sys.stdout", new_callable=io.StringIO) as mock_out:
            code = cmd_doctor(args)
            self.assertEqual(code, 0)
            data = json.loads(mock_out.getvalue().strip())
            self.assertIn("os_family", data)
            self.assertIn("cli_binary", data)
            self.assertIn("summary", data)

    def test_cmd_doctor_human_mode(self):
        """Verifies cmd_doctor without --json outputs human-readable report."""
        args = argparse.Namespace(matrix=DEFAULT_MATRIX, json=False, heal=False)

        def mock_run(cmd, *args, **kwargs):
            proc = MagicMock()
            proc.returncode = 0
            proc.stderr = ""
            proc.stdout = "99.0.0"
            return proc

        with patch("shutil.which", side_effect=lambda x: f"/usr/bin/{x}"), \
             patch("subprocess.run", side_effect=mock_run), \
             patch("sys.stdout", new_callable=io.StringIO) as mock_out:
            code = cmd_doctor(args)
            self.assertEqual(code, 0)
            out = mock_out.getvalue()
            self.assertIn("AGYIS WORKSTATION DOCTOR", out)
            self.assertIn("Antigravity Immune System", out)

    def test_cmd_doctor_heal_flag(self):
        """Verifies cmd_doctor with --heal invokes heal_environment."""
        args = argparse.Namespace(matrix=DEFAULT_MATRIX, json=False, heal=True)

        def mock_run(cmd, *args, **kwargs):
            proc = MagicMock()
            proc.returncode = 0
            proc.stderr = ""
            proc.stdout = "99.0.0"
            return proc

        with patch("shutil.which", side_effect=lambda x: f"/usr/bin/{x}"), \
             patch("subprocess.run", side_effect=mock_run), \
             patch("harness.runtime.doctor.heal_environment", return_value=["Fixed mock permission"]) as mock_heal, \
             patch("sys.stdout", new_callable=io.StringIO) as mock_out:
            code = cmd_doctor(args)
            self.assertEqual(code, 0)
            self.assertTrue(mock_heal.called)
            out = mock_out.getvalue()
            self.assertIn("Executing Auto-Healing...", out)
            self.assertIn("Fixed mock permission", out)

    def test_cmd_doctor_exit_codes_missing_tool(self):
        """Verifies cmd_doctor exits 1 when a required tool is missing."""
        args = argparse.Namespace(matrix=DEFAULT_MATRIX, json=False, heal=False)

        mock_audit = {
            "os_family": "linux",
            "cli_binary": {"status": "OK"},
            "psl_collision": {"status": "OK"},
            "duplicate_agents": {"status": "OK"},
            "node_script_hygiene": {"status": "OK"},
            "hooks_health": {"status": "OK"},
            "tiers": {},
            "summary": {"ok": 5, "warning": 0, "outdated": 0, "missing": 1, "total_tools": 6},
        }

        with patch("harness.runtime.doctor.run_doctor", return_value=mock_audit), \
             patch("sys.stdout", new_callable=io.StringIO):
            code = cmd_doctor(args)
            self.assertEqual(code, 1)

    def test_agyis_doctor_help_subtle_backronym(self):
        """Verifies 'agyis doctor --help' outputs 'Antigravity Immune System' in its description."""
        with patch("sys.stdout", new_callable=io.StringIO) as mock_out:
            with self.assertRaises(SystemExit) as cm:
                main(["doctor", "--help"], prog="agyis")
            self.assertEqual(cm.exception.code, 0)
            output = mock_out.getvalue()
            self.assertIn("Antigravity Immune System", output)
            self.assertIn("Agyis Workstation Diagnostic & Runtime Guarantee", output)


class TestAgyisVsPslDoctorComparison(unittest.TestCase):
    """Verifies dual behavior and deprecation lifecycle between agyis doctor and psl doctor."""

    def test_agyis_doctor_clean_stderr(self):
        """Verifies 'agyis doctor' runs without emitting deprecation warning on stderr."""
        def mock_run(cmd, *args, **kwargs):
            proc = MagicMock()
            proc.returncode = 0
            proc.stderr = ""
            proc.stdout = "99.0.0"
            return proc

        with patch("shutil.which", side_effect=lambda x: f"/usr/bin/{x}"), \
             patch("subprocess.run", side_effect=mock_run), \
             patch("sys.stdout", new_callable=io.StringIO) as mock_out, \
             patch("sys.stderr", new_callable=io.StringIO) as mock_err:
            code = main(["doctor"], prog="agyis")
            self.assertEqual(code, 0)
            self.assertEqual(mock_err.getvalue(), "")
            self.assertIn("AGYIS WORKSTATION DOCTOR", mock_out.getvalue())

    def test_psl_doctor_deprecation_warning_on_stderr(self):
        """Verifies 'psl doctor' emits deprecation warning on stderr while executing normally."""
        def mock_run(cmd, *args, **kwargs):
            proc = MagicMock()
            proc.returncode = 0
            proc.stderr = ""
            proc.stdout = "99.0.0"
            return proc

        with patch("shutil.which", side_effect=lambda x: f"/usr/bin/{x}"), \
             patch("subprocess.run", side_effect=mock_run), \
             patch("sys.stdout", new_callable=io.StringIO) as mock_out, \
             patch("sys.stderr", new_callable=io.StringIO) as mock_err:
            code = deprecated_psl_main(["doctor"])
            self.assertEqual(code, 0)
            self.assertIn(PSL_DEPRECATION_WARNING.strip(), mock_err.getvalue())
            self.assertIn("AGYIS WORKSTATION DOCTOR", mock_out.getvalue())

    def test_agyis_vs_psl_doctor_identical_json_payload(self):
        """Verifies 'agyis doctor --json' and 'psl doctor --json' emit identical JSON on stdout."""
        def mock_run(cmd, *args, **kwargs):
            proc = MagicMock()
            proc.returncode = 0
            proc.stderr = ""
            proc.stdout = "99.0.0"
            return proc

        with patch("shutil.which", side_effect=lambda x: f"/usr/bin/{x}"), \
             patch("subprocess.run", side_effect=mock_run), \
             patch("sys.stdout", new_callable=io.StringIO) as agyis_out, \
             patch("sys.stderr", new_callable=io.StringIO):
            code1 = main(["doctor", "--json"], prog="agyis")
            self.assertEqual(code1, 0)
            data_agyis = json.loads(agyis_out.getvalue().strip())

        with patch("shutil.which", side_effect=lambda x: f"/usr/bin/{x}"), \
             patch("subprocess.run", side_effect=mock_run), \
             patch("sys.stdout", new_callable=io.StringIO) as psl_out, \
             patch("sys.stderr", new_callable=io.StringIO) as psl_err:
            code2 = deprecated_psl_main(["doctor", "--json"])
            self.assertEqual(code2, 0)
            # Ensure stderr had deprecation warning, but stdout was purely valid JSON
            self.assertIn("DeprecationWarning", psl_err.getvalue())
            data_psl = json.loads(psl_out.getvalue().strip())

        self.assertEqual(data_agyis["os_family"], data_psl["os_family"])
        self.assertEqual(data_agyis["summary"], data_psl["summary"])
        self.assertEqual(data_agyis["tiers"].keys(), data_psl["tiers"].keys())
        self.assertEqual(data_agyis["rea_tooling"], data_psl["rea_tooling"])


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
            if "--version" in cmd:
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
            if "--version" in cmd:
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

        with patch("subprocess.run", side_effect=mock_run), \
             patch("harness.runtime.doctor.check_rea_tooling", return_value=mock_rea):
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

        with patch("subprocess.run", side_effect=mock_run), \
             patch("harness.runtime.doctor.check_rea_tooling", return_value=mock_rea):
            audit = run_doctor(DEFAULT_MATRIX, experimental_rea=True)
            self.assertEqual(audit["rea_tooling"]["status"], "warning")
            self.assertGreaterEqual(audit["summary"]["warning"], 1)

            # Conversely, when experimental_rea=False, fast-path adds 0 warnings
            audit_fast = run_doctor(DEFAULT_MATRIX, experimental_rea=False)
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
            if "providers" in cmd:
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
            if "--version" in cmd:
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
                proc.stdout = stdout_val if "--version" in cmd else "{}"
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


class TestDuplicateSkillsHygiene(unittest.TestCase):
    """Hermetic unit tests for check_duplicate_skills and doctor integration (Issue #52)."""

    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.base_dir = Path(self.temp_dir.name)
        self.cfg_dir = self.base_dir / "config"
        self.ws_dir = self.base_dir / "workspace"
        self.cfg_dir.mkdir(parents=True)
        self.ws_dir.mkdir(parents=True)

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def test_check_duplicate_skills_pass(self) -> None:
        """PASS status when no duplicate skill definitions exist across standalone, plugins, and workspace."""
        # Standalone skill
        (self.cfg_dir / "skills" / "skill-a").mkdir(parents=True)
        (self.cfg_dir / "skills" / "skill-a" / "SKILL.md").write_text("# Skill A\n", encoding="utf-8")

        # Plugin skill
        (self.cfg_dir / "plugins" / "my-plugin" / "skills" / "skill-b").mkdir(parents=True)
        (self.cfg_dir / "plugins" / "my-plugin" / "skills" / "skill-b" / "SKILL.md").write_text("# Skill B\n", encoding="utf-8")

        # Workspace skill
        (self.ws_dir / ".agents" / "skills" / "skill-c").mkdir(parents=True)
        (self.ws_dir / ".agents" / "skills" / "skill-c" / "SKILL.md").write_text("# Skill C\n", encoding="utf-8")

        res = check_duplicate_skills(workspace_root=self.ws_dir, config_dir=self.cfg_dir)
        self.assertEqual(res["status"], "PASS")
        self.assertEqual(res["duplicates"], [])
        self.assertEqual(res["duplicate_items"], [])
        self.assertIsNone(res["remediation"])

    def test_check_duplicate_skills_workspace_plugin_collision(self) -> None:
        """WARNING status when workspace duplicates a skill supplied by a plugin (Issue #52 root cause)."""
        # Plugin skill
        (self.cfg_dir / "plugins" / "my-plugin" / "skills" / "code-review").mkdir(parents=True)
        (self.cfg_dir / "plugins" / "my-plugin" / "skills" / "code-review" / "SKILL.md").write_text("# Plugin Code Review\n", encoding="utf-8")

        # Workspace duplicate skill
        (self.ws_dir / ".agents" / "skills" / "code-review").mkdir(parents=True)
        (self.ws_dir / ".agents" / "skills" / "code-review" / "SKILL.md").write_text("# Workspace Code Review\n", encoding="utf-8")

        res = check_duplicate_skills(workspace_root=self.ws_dir, config_dir=self.cfg_dir)
        self.assertEqual(res["status"], "WARNING")
        self.assertIn("code-review", res["duplicates"])
        self.assertIsNotNone(res["remediation"])
        self.assertEqual(len(res["duplicate_items"]), 1)
        self.assertEqual(len(res["duplicate_items"][0]["sources"]), 2)

    def test_check_duplicate_skills_standalone_plugin_collision(self) -> None:
        """WARNING status when standalone skill duplicates a plugin skill."""
        (self.cfg_dir / "skills" / "subagent-ladder").mkdir(parents=True)
        (self.cfg_dir / "skills" / "subagent-ladder" / "SKILL.md").write_text("# Standalone Ladder\n", encoding="utf-8")

        (self.cfg_dir / "plugins" / "my-plugin" / "skills" / "subagent-ladder").mkdir(parents=True)
        (self.cfg_dir / "plugins" / "my-plugin" / "skills" / "subagent-ladder" / "SKILL.md").write_text("# Plugin Ladder\n", encoding="utf-8")

        res = check_duplicate_skills(workspace_root=self.ws_dir, config_dir=self.cfg_dir)
        self.assertEqual(res["status"], "WARNING")
        self.assertIn("subagent-ladder", res["duplicates"])

    def test_check_duplicate_skills_ignores_self_plugin_repo(self) -> None:
        """PASS status when workspace is the source repository for the installed plugin."""
        # Workspace has plugin.json defining 'psl-agy-harness'
        (self.ws_dir / "plugin.json").write_text(json.dumps({"name": "psl-agy-harness"}), encoding="utf-8")
        (self.ws_dir / ".agents" / "skills" / "code-review").mkdir(parents=True)
        (self.ws_dir / ".agents" / "skills" / "code-review" / "SKILL.md").write_text("# Repo Code Review\n", encoding="utf-8")

        # Installed plugin copy
        (self.cfg_dir / "plugins" / "psl-agy-harness" / "skills" / "code-review").mkdir(parents=True)
        (self.cfg_dir / "plugins" / "psl-agy-harness" / "skills" / "code-review" / "SKILL.md").write_text("# Installed Code Review\n", encoding="utf-8")

        res = check_duplicate_skills(workspace_root=self.ws_dir, config_dir=self.cfg_dir)
        self.assertEqual(res["status"], "PASS")
        self.assertEqual(len(res["duplicates"]), 0)

    def test_doctor_report_rendering_duplicate_skills_warning(self) -> None:
        """print_cli_report renders Duplicate Skills [WARN] with remediation."""
        sample_audit = {
            "os_family": "linux",
            "duplicate_skills": {
                "status": "WARNING",
                "duplicates": ["code-review"],
                "details": "Duplicate skill definitions detected across workspace, plugin, or config: code-review",
                "remediation": "Prune redundant workspace skills with 'agyis skills --prune-duplicates'",
            },
            "tiers": {},
            "summary": {"ok": 1, "warning": 1, "outdated": 0, "missing": 0},
        }
        with patch("sys.stdout", new_callable=io.StringIO) as mock_out:
            print_cli_report(sample_audit)
            output = mock_out.getvalue()
            self.assertIn("Duplicate Skills:", output)
            self.assertIn("WARN", output)
            self.assertIn("code-review", output)
            self.assertIn("--prune-duplicates", output)

    def test_doctor_report_rendering_duplicate_skills_pass(self) -> None:
        """print_cli_report renders Duplicate Skills [PASS]."""
        sample_audit = {
            "os_family": "linux",
            "duplicate_skills": {
                "status": "PASS",
                "duplicates": [],
                "details": "No duplicate skill registrations detected across workspace, plugin, or config.",
                "remediation": None,
            },
            "tiers": {},
            "summary": {"ok": 2, "warning": 0, "outdated": 0, "missing": 0},
        }
        with patch("sys.stdout", new_callable=io.StringIO) as mock_out:
            print_cli_report(sample_audit)
            output = mock_out.getvalue()
            self.assertIn("Duplicate Skills:", output)
            self.assertIn("PASS", output)


if __name__ == "__main__":
    unittest.main()
