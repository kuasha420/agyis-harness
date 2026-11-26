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
    check_telemetry_daemon,
    print_cli_report,
    run_doctor,
    run_doctor_checks,
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


def _fast_doctor_probes():
    """Isolate whole-repo/host sub-probes in CLI structure and parity unit tests."""
    return patch.multiple(
        "harness.runtime.doctor",
        check_architectural_fitness=MagicMock(return_value={"status": "OK", "score": 100.0}),
        check_database_port_conflicts=MagicMock(return_value={"status": "PASS"}),
        check_duplicate_agents=MagicMock(return_value={"status": "OK"}),
        check_duplicate_skills=MagicMock(return_value={"status": "OK"}),
        check_hooks_health=MagicMock(return_value={"status": "OK"}),
        check_node_script_hygiene=MagicMock(return_value={"status": "OK"}),
        check_rea_tooling=MagicMock(return_value={"status": "optional_missing", "fast_path": True}),
        check_telemetry_daemon=MagicMock(return_value={"status": "OK", "message": "ok"}),
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

        with patch("subprocess.run", side_effect=mock_run), _fast_doctor_probes():
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

    def setUp(self):
        self._fast_patch = _fast_doctor_probes()
        self._fast_patch.start()

    def tearDown(self):
        self._fast_patch.stop()

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

    def setUp(self):
        self._fast_patch = _fast_doctor_probes()
        self._fast_patch.start()

    def tearDown(self):
        self._fast_patch.stop()

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


class TestTelemetryDaemonDoctor(unittest.TestCase):
    """Verifies check_telemetry_daemon across active, inactive, failed, and non-systemd states (Issue #55)."""

    def setUp(self):
        self._tmp_dir = tempfile.TemporaryDirectory()
        root = Path(self._tmp_dir.name)
        self.state_dir = root / "state"
        self.state_dir.mkdir(parents=True, exist_ok=True)
        self.app_dir = root / "antigravity"
        (self.app_dir / "brain").mkdir(parents=True, exist_ok=True)
        self._env_patch = patch.dict(
            os.environ,
            {
                "AGYIS_HARNESS_STATE_DIR": str(self.state_dir),
                "PSL_HARNESS_STATE_DIR": str(self.state_dir),
                "ANTIGRAVITY_APP_DATA_DIR": str(self.app_dir),
                "ANTIGRAVITY_BRAIN_DIR": str(self.app_dir / "brain"),
                "AGYIS_TELEMETRY_DB": str(root / "telemetry.db"),
            },
            clear=False,
        )
        self._env_patch.start()

    def tearDown(self):
        self._env_patch.stop()
        self._tmp_dir.cleanup()

    def test_check_telemetry_daemon_no_systemctl(self):
        """Returns None when systemctl binary is not available in PATH."""
        with patch("shutil.which", return_value=None):
            result = check_telemetry_daemon()
            self.assertIsNone(result)

    def test_check_telemetry_daemon_active(self):
        """Returns OK when agyis-sync.service is active with clean isolated sync status."""
        proc = MagicMock(stdout="active\n", stderr="", returncode=0)
        with patch("shutil.which", return_value="/usr/bin/systemctl"), \
             patch("subprocess.run", return_value=proc), \
             patch("harness.telemetry.sync.daemon.read_sync_status", return_value={}), \
             patch("harness.telemetry.sync.daemon.compute_telemetry_lag", return_value={}):
            result = check_telemetry_daemon()
            self.assertIsNotNone(result)
            self.assertEqual(result["status"], "OK")
            self.assertEqual(result["state"], "active")
            self.assertEqual(result["message"], "Telemetry Sync Service (agyis-sync.service is active)")

    def test_check_telemetry_daemon_inactive(self):
        """Returns WARNING with remediation guidance when agyis-sync.service is inactive."""
        proc = MagicMock(stdout="inactive\n", stderr="", returncode=3)
        with patch("shutil.which", return_value="/usr/bin/systemctl"), \
             patch("subprocess.run", return_value=proc), \
             patch("harness.telemetry.sync.daemon.read_sync_status", return_value={}), \
             patch("harness.telemetry.sync.daemon.compute_telemetry_lag", return_value={}):
            result = check_telemetry_daemon()
            self.assertIsNotNone(result)
            self.assertEqual(result["status"], "WARNING")
            self.assertEqual(result["state"], "inactive")
            self.assertEqual(
                result["remediation"],
                "agyis-sync.service is inactive. Run 'agyis sync --service install' / 'start' to enable background sync.",
            )

    def test_check_telemetry_daemon_failed(self):
        """Returns WARNING with status inspection guidance when agyis-sync.service is failed."""
        proc = MagicMock(stdout="failed\n", stderr="", returncode=3)
        with patch("shutil.which", return_value="/usr/bin/systemctl"), \
             patch("subprocess.run", return_value=proc), \
             patch("harness.telemetry.sync.daemon.read_sync_status", return_value={}), \
             patch("harness.telemetry.sync.daemon.compute_telemetry_lag", return_value={}):
            result = check_telemetry_daemon()
            self.assertIsNotNone(result)
            self.assertEqual(result["status"], "WARNING")
            self.assertEqual(result["state"], "failed")
            self.assertEqual(
                result["remediation"],
                "agyis-sync.service in failed state. Run 'agyis sync --service status' for logs.",
            )

    def test_check_telemetry_daemon_unknown(self):
        """Returns WARNING when state is unknown or command times out."""
        proc = MagicMock(stdout="unknown\n", stderr="", returncode=4)
        with patch("shutil.which", return_value="/usr/bin/systemctl"), \
             patch("subprocess.run", return_value=proc), \
             patch("harness.telemetry.sync.daemon.read_sync_status", return_value={}), \
             patch("harness.telemetry.sync.daemon.compute_telemetry_lag", return_value={}):
            result = check_telemetry_daemon()
            self.assertIsNotNone(result)
            self.assertEqual(result["status"], "WARNING")
            self.assertEqual(result["state"], "unknown")
            self.assertIn("Run 'agyis sync --service install' / 'start'", result["remediation"])

    def test_check_telemetry_daemon_timeout_exception(self):
        """Handles subprocess TimeoutExpired safely returning WARNING."""
        with patch("shutil.which", return_value="/usr/bin/systemctl"), \
             patch("subprocess.run", side_effect=subprocess.TimeoutExpired(cmd="systemctl", timeout=0.5)), \
             patch("harness.telemetry.sync.daemon.read_sync_status", return_value={}), \
             patch("harness.telemetry.sync.daemon.compute_telemetry_lag", return_value={}):
            result = check_telemetry_daemon()
            self.assertIsNotNone(result)
            self.assertEqual(result["status"], "WARNING")

    def test_run_doctor_checks_includes_telemetry_daemon(self):
        """Verifies run_doctor_checks registers telemetry_daemon in output."""
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
        fast_ver = subprocess.CompletedProcess(args=["tool"], returncode=0, stdout="v24.22.1\n", stderr="")
        with _fast_doctor_probes(), \
             patch("harness.runtime.doctor.check_cli_binary", return_value=mock_cli), \
             patch("harness.runtime.tool_checks_common.subprocess.run", return_value=fast_ver), \
             patch("harness.runtime.doctor.check_telemetry_daemon", return_value={"status": "OK", "message": "Telemetry Sync Service (agyis-sync.service is active)"}):
            audit = run_doctor_checks()
            self.assertIn("telemetry_daemon", audit)
            self.assertEqual(audit["telemetry_daemon"]["status"], "OK")

        with _fast_doctor_probes(), \
             patch("harness.runtime.doctor.check_tool", return_value={"name": "mock", "binary": "mock", "status": "OK", "path": "/bin/mock", "version": "99.0.0", "min_version": "1.0.0", "is_shim": False, "shim_details": None, "is_collision": False, "collision_details": None, "spec": {}}), \
             patch("harness.runtime.doctor.check_cli_binary", return_value=mock_cli), \
             patch("harness.runtime.doctor.check_telemetry_daemon", return_value={"status": "WARNING", "message": "agyis-sync.service is inactive."}):
            warn_audit = run_doctor(DEFAULT_MATRIX, experimental_rea=False)
            self.assertGreaterEqual(warn_audit["summary"]["warning"], 1)

    def test_print_cli_report_renders_telemetry_daemon(self):
        """Verifies print_cli_report renders active and warning telemetry daemon status."""
        active_audit = {
            "os_family": "linux",
            "telemetry_daemon": {
                "status": "OK",
                "message": "Telemetry Sync Service (agyis-sync.service is active)",
            },
            "tiers": {},
            "summary": {"ok": 1, "warning": 0, "outdated": 0, "missing": 0},
        }
        with patch("sys.stdout", new_callable=io.StringIO) as mock_out:
            print_cli_report(active_audit)
            self.assertIn("Telemetry Daemon:", mock_out.getvalue())
            self.assertIn("Telemetry Sync Service (agyis-sync.service is active)", mock_out.getvalue())

        warn_audit = {
            "os_family": "linux",
            "telemetry_daemon": {
                "status": "WARNING",
                "message": "agyis-sync.service is inactive.",
                "remediation": "Run 'agyis sync --service install'",
                "sync_health": {"status": "error", "last_harvest_at": "2026-11-10T10:00:00Z"},
                "telemetry_lag": {"unsynced_local": 3, "stale_local": 1},
            },
            "tiers": {},
            "summary": {"ok": 0, "warning": 1, "outdated": 0, "missing": 0},
        }
        with patch("sys.stdout", new_callable=io.StringIO) as mock_out:
            print_cli_report(warn_audit)
            out_txt = mock_out.getvalue()
            self.assertIn("Telemetry Daemon:", out_txt)
            self.assertIn("Run 'agyis sync --service install'", out_txt)
            self.assertIn("Sync Health:", out_txt)
            self.assertIn("lag=3 unsynced / 1 stale", out_txt)

    def test_check_telemetry_daemon_active_with_failing_sync_status(self):
        """Active systemd service must report WARNING when daemon sync health records failures."""
        with tempfile.TemporaryDirectory() as td:
            state_dir = Path(td)
            (state_dir / "telemetry_sync_status.json").write_text(
                json.dumps({
                    "status": "error",
                    "consecutive_failures": 4,
                    "last_error": "disk I/O error",
                    "last_harvest_at": "2026-11-08T00:00:00Z",
                }),
                encoding="utf-8",
            )
            proc = MagicMock(stdout="active\n", stderr="", returncode=0)
            with patch.dict(os.environ, {"AGYIS_HARNESS_STATE_DIR": td, "PSL_HARNESS_STATE_DIR": td}), \
                 patch("shutil.which", return_value="/usr/bin/systemctl"), \
                 patch("subprocess.run", return_value=proc), \
                 patch("harness.telemetry.sync.daemon.compute_telemetry_lag", return_value={}):
                result = check_telemetry_daemon()
            self.assertEqual(result["status"], "WARNING")
            self.assertEqual(result["state"], "active_failing")
            self.assertIn("disk I/O error", result["remediation"])
            self.assertEqual(result["sync_health"]["consecutive_failures"], 4)

    def test_check_telemetry_daemon_active_failing_timeout_regression(self):
        """DEF-GATE2-001: Hermetic regression verifying active_failing on consecutive_failures=2 timeout error."""
        failing_payload = {
            "consecutive_failures": 2,
            "status": "error",
            "last_error": "timeout",
        }
        proc = MagicMock(stdout="active\n", stderr="", returncode=0)
        # 1. File-backed via isolated temp state_dir
        (self.state_dir / "telemetry_sync_status.json").write_text(json.dumps(failing_payload), encoding="utf-8")
        with patch("shutil.which", return_value="/usr/bin/systemctl"), \
             patch("subprocess.run", return_value=proc), \
             patch("harness.telemetry.sync.daemon.compute_telemetry_lag", return_value={}):
            res_disk = check_telemetry_daemon()
        self.assertEqual(res_disk["status"], "WARNING")
        self.assertEqual(res_disk["state"], "active_failing")
        self.assertIn("2 consecutive failure(s): timeout", res_disk["remediation"])
        self.assertIn("agyis sync --service status", res_disk["message"])

        # 2. Explicitly mocked read_sync_status
        with patch("shutil.which", return_value="/usr/bin/systemctl"), \
             patch("subprocess.run", return_value=proc), \
             patch("harness.telemetry.sync.daemon.read_sync_status", return_value=failing_payload), \
             patch("harness.telemetry.sync.daemon.compute_telemetry_lag", return_value={}):
            res_mock = check_telemetry_daemon()
        self.assertEqual(res_mock["status"], "WARNING")
        self.assertEqual(res_mock["state"], "active_failing")
        self.assertIn("2 consecutive failure(s): timeout", res_mock["remediation"])
        self.assertIn("agyis sync --service status", res_mock["message"])

    def test_doctor_summary_accounting_and_legacy_cli_hooks_check(self):
        """DRIFT-P2-04: run_doctor keeps ok <= total_tools, reports antigravity_surfaces, and flags legacy cli hooks.json."""
        from harness.runtime.doctor import run_doctor
        from harness.runtime.hygiene_checks import check_hooks_health

        matrix_path = Path(__file__).resolve().parent.parent / "harness" / "runtime" / "matrix.json"
        fast_ver = subprocess.CompletedProcess(args=["tool"], returncode=0, stdout="v24.22.1\n", stderr="")
        with _fast_doctor_probes(), \
             patch("harness.runtime.tool_checks_common.subprocess.run", return_value=fast_ver):
            audit = run_doctor(matrix_path, workspace_root=Path(__file__).resolve().parent.parent)
        self.assertLessEqual(audit["summary"]["ok"], audit["summary"]["total_tools"])
        self.assertIn("antigravity_surfaces", audit)
        self.assertIn("cli_bin", audit["antigravity_surfaces"])

        with tempfile.TemporaryDirectory() as td:
            fake_home = Path(td)
            cli_hooks = fake_home / ".gemini" / "antigravity-cli" / "hooks.json"
            cli_hooks.parent.mkdir(parents=True)
            cli_hooks.write_text("{}", encoding="utf-8")
            with patch.object(Path, "home", return_value=fake_home):
                res = check_hooks_health()
            self.assertEqual(res["status"], "WARNING")
            self.assertIn("Legacy non-symlinked", res["failures"][0])


if __name__ == "__main__":
    unittest.main()
