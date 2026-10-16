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
    print_cli_report,
    run_doctor,
)
from harness.runtime.tool_checks import (
    check_cli_binary,
    check_psl_collision,
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


if __name__ == "__main__":
    unittest.main()
