# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Arafat Zahan (@kuasha420)
# Corporate Stewardship & Infrastructure: Purrfect Software Limited (PSL)
# Governed by: ICARO-42/b Ordinance (Company-Supported Personal IP Framework)

"""
Unit tests for background telemetry sync systemd user service management (Issue #57 / R4).
Ensures hermetic execution, mocked subprocesses, and <1.0s benchmark (ADR-015).
"""

from __future__ import annotations

import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import MagicMock, call, patch

from harness.cli import main
from harness.telemetry.sync import systemd


class TestSyncServiceGenerator(unittest.TestCase):
    """Verifies unit definition generator and dynamic executable resolution."""

    def test_generate_systemd_service_default(self):
        with patch("shutil.which", return_value=None):
            unit = systemd.generate_systemd_service(interval_sec=10.0)
            self.assertIn("[Unit]", unit)
            self.assertIn("[Service]", unit)
            self.assertIn("[Install]", unit)
            self.assertIn("Description=Agyis Telemetry Background Sync Service", unit)
            self.assertIn("Restart=on-failure", unit)
            self.assertIn("RestartSec=10s", unit)
            self.assertIn("Environment=PYTHONUNBUFFERED=1", unit)
            self.assertIn("WantedBy=default.target", unit)
            self.assertIn(f"{sys.executable} -m harness.cli sync --watch --interval 10.0", unit)

    def test_generate_systemd_service_with_agyis_binary(self):
        with patch("shutil.which", return_value="/home/kuasha/.local/bin/agyis"):
            unit = systemd.generate_systemd_service(interval_sec=5.0)
            self.assertIn("ExecStart=/home/kuasha/.local/bin/agyis sync --watch --interval 5.0", unit)

    def test_generate_systemd_service_python_bin_override(self):
        unit = systemd.generate_systemd_service(
            python_bin="/usr/custom/python3",
            interval_sec=15.0,
            working_dir="/opt/custom",
        )
        self.assertIn("ExecStart=/usr/custom/python3 -m harness.cli sync --watch --interval 15.0", unit)
        self.assertIn("WorkingDirectory=/opt/custom", unit)


class TestSyncServiceLifecycle(unittest.TestCase):
    """Verifies systemctl lifecycle management operations."""

    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.unit_path = Path(self.temp_dir.name) / "systemd" / "user" / "agyis-sync.service"

    def tearDown(self):
        self.temp_dir.cleanup()

    @patch("shutil.which")
    @patch("subprocess.run")
    def test_install_service_success(self, mock_run, mock_which):
        mock_which.side_effect = lambda cmd: "/usr/bin/" + cmd if cmd in ("systemctl", "agyis") else None
        mock_run.return_value = subprocess.CompletedProcess(args=[], returncode=0, stdout="", stderr="")

        rc = systemd.install_service(interval=10.0, unit_path=self.unit_path)
        self.assertEqual(rc, 0)
        self.assertTrue(self.unit_path.exists())
        content = self.unit_path.read_text(encoding="utf-8")
        self.assertIn("[Unit]", content)
        self.assertIn("[Service]", content)
        self.assertIn("--interval 10.0", content)

        # Verify systemctl calls
        mock_run.assert_any_call(
            ["systemctl", "--user", "daemon-reload"],
            capture_output=True,
            text=True,
            timeout=15.0,
        )
        mock_run.assert_any_call(
            ["systemctl", "--user", "enable", "agyis-sync.service"],
            capture_output=True,
            text=True,
            timeout=15.0,
        )

    @patch("shutil.which", return_value=None)
    def test_install_service_missing_systemctl(self, mock_which):
        with patch("sys.stderr", new_callable=io.StringIO) as mock_err:
            rc = systemd.install_service(unit_path=self.unit_path)
            self.assertEqual(rc, 1)
            self.assertIn("systemctl command not found", mock_err.getvalue())

    @patch("shutil.which", return_value="/usr/bin/systemctl")
    def test_status_service_not_installed(self, mock_which):
        with patch("sys.stderr", new_callable=io.StringIO) as mock_err:
            rc = systemd.service_status(unit_path=self.unit_path)
            self.assertEqual(rc, 1)
            self.assertIn("is not installed", mock_err.getvalue())

    @patch("shutil.which", return_value="/usr/bin/systemctl")
    @patch("subprocess.run")
    def test_status_service_active(self, mock_run, mock_which):
        # Create dummy unit
        self.unit_path.parent.mkdir(parents=True, exist_ok=True)
        self.unit_path.write_text("[Unit]\n", encoding="utf-8")

        mock_run.return_value = subprocess.CompletedProcess(
            args=[],
            returncode=0,
            stdout="● agyis-sync.service - Agyis Telemetry Background Sync Service\n   Active: active (running)",
            stderr="",
        )

        with patch("sys.stdout", new_callable=io.StringIO) as mock_out:
            rc = systemd.service_status(unit_path=self.unit_path)
            self.assertEqual(rc, 0)
            self.assertIn("Active: active (running)", mock_out.getvalue())

    @patch("shutil.which", return_value="/usr/bin/systemctl")
    @patch("subprocess.run")
    def test_status_service_inactive_returns_zero(self, mock_run, mock_which):
        # In systemd, code 3 means loaded but inactive/stopped
        self.unit_path.parent.mkdir(parents=True, exist_ok=True)
        self.unit_path.write_text("[Unit]\n", encoding="utf-8")

        mock_run.return_value = subprocess.CompletedProcess(
            args=[],
            returncode=3,
            stdout="● agyis-sync.service - Agyis Telemetry Background Sync Service\n   Active: inactive (dead)",
            stderr="",
        )

        with patch("sys.stdout", new_callable=io.StringIO) as mock_out:
            rc = systemd.service_status(unit_path=self.unit_path)
            self.assertEqual(rc, 0)
            self.assertIn("Active: inactive (dead)", mock_out.getvalue())

    @patch("shutil.which", return_value="/usr/bin/systemctl")
    @patch("subprocess.run")
    def test_status_service_json(self, mock_run, mock_which):
        self.unit_path.parent.mkdir(parents=True, exist_ok=True)
        self.unit_path.write_text("[Unit]\n", encoding="utf-8")

        mock_run.return_value = subprocess.CompletedProcess(
            args=[],
            returncode=0,
            stdout="Active: active (running)",
            stderr="",
        )

        with patch("sys.stdout", new_callable=io.StringIO) as mock_out:
            rc = systemd.service_status(unit_path=self.unit_path, json_output=True)
            self.assertEqual(rc, 0)
            data = json.loads(mock_out.getvalue())
            self.assertEqual(data["service"], "agyis-sync.service")
            self.assertTrue(data["installed"])
            self.assertTrue(data["active"])

    @patch("shutil.which", return_value="/usr/bin/systemctl")
    @patch("subprocess.run")
    def test_start_service_success(self, mock_run, mock_which):
        self.unit_path.parent.mkdir(parents=True, exist_ok=True)
        self.unit_path.write_text("[Unit]\n", encoding="utf-8")

        mock_run.return_value = subprocess.CompletedProcess(args=[], returncode=0, stdout="", stderr="")

        with patch("sys.stdout", new_callable=io.StringIO) as mock_out:
            rc = systemd.start_service(unit_path=self.unit_path)
            self.assertEqual(rc, 0)
            self.assertIn("Started agyis-sync.service", mock_out.getvalue())
            mock_run.assert_called_with(
                ["systemctl", "--user", "start", "agyis-sync.service"],
                capture_output=True,
                text=True,
                timeout=15.0,
            )

    @patch("shutil.which", return_value="/usr/bin/systemctl")
    def test_start_service_not_installed(self, mock_which):
        with patch("sys.stderr", new_callable=io.StringIO) as mock_err:
            rc = systemd.start_service(unit_path=self.unit_path)
            self.assertEqual(rc, 1)
            self.assertIn("is not installed", mock_err.getvalue())

    @patch("shutil.which", return_value="/usr/bin/systemctl")
    @patch("subprocess.run")
    def test_stop_service_success(self, mock_run, mock_which):
        mock_run.return_value = subprocess.CompletedProcess(args=[], returncode=0, stdout="", stderr="")

        with patch("sys.stdout", new_callable=io.StringIO) as mock_out:
            rc = systemd.stop_service(unit_path=self.unit_path)
            self.assertEqual(rc, 0)
            self.assertIn("Stopped agyis-sync.service", mock_out.getvalue())
            mock_run.assert_called_with(
                ["systemctl", "--user", "stop", "agyis-sync.service"],
                capture_output=True,
                text=True,
                timeout=15.0,
            )

    @patch("shutil.which", return_value="/usr/bin/systemctl")
    @patch("subprocess.run")
    def test_uninstall_service_success(self, mock_run, mock_which):
        self.unit_path.parent.mkdir(parents=True, exist_ok=True)
        self.unit_path.write_text("[Unit]\n", encoding="utf-8")

        mock_run.return_value = subprocess.CompletedProcess(args=[], returncode=0, stdout="", stderr="")

        with patch("sys.stdout", new_callable=io.StringIO) as mock_out:
            rc = systemd.uninstall_service(unit_path=self.unit_path)
            self.assertEqual(rc, 0)
            self.assertFalse(self.unit_path.exists())
            self.assertIn("Successfully uninstalled agyis-sync.service", mock_out.getvalue())

            mock_run.assert_any_call(
                ["systemctl", "--user", "stop", "agyis-sync.service"],
                capture_output=True,
                text=True,
                timeout=15.0,
            )
            mock_run.assert_any_call(
                ["systemctl", "--user", "disable", "agyis-sync.service"],
                capture_output=True,
                text=True,
                timeout=15.0,
            )
            mock_run.assert_any_call(
                ["systemctl", "--user", "daemon-reload"],
                capture_output=True,
                text=True,
                timeout=15.0,
            )

    @patch("shutil.which", return_value="/usr/bin/systemctl")
    @patch("subprocess.run")
    def test_uninstall_service_idempotent_when_already_missing(self, mock_run, mock_which):
        mock_run.return_value = subprocess.CompletedProcess(args=[], returncode=0, stdout="", stderr="")
        rc = systemd.uninstall_service(unit_path=self.unit_path)
        self.assertEqual(rc, 0)

    @patch("shutil.which", return_value="/usr/bin/systemctl")
    @patch("subprocess.run")
    def test_dbus_not_connected_error(self, mock_run, mock_which):
        self.unit_path.parent.mkdir(parents=True, exist_ok=True)
        self.unit_path.write_text("[Unit]\n", encoding="utf-8")

        mock_run.return_value = subprocess.CompletedProcess(
            args=[],
            returncode=1,
            stdout="",
            stderr="Failed to connect to bus: No such file or directory",
        )

        with patch("sys.stderr", new_callable=io.StringIO) as mock_err:
            rc = systemd.start_service(unit_path=self.unit_path)
            self.assertEqual(rc, 1)
            self.assertIn("Unable to communicate with systemd user session bus", mock_err.getvalue())
            self.assertIn("XDG_RUNTIME_DIR", mock_err.getvalue())

    @patch("shutil.which", return_value="/usr/bin/systemctl")
    @patch("subprocess.run", side_effect=subprocess.TimeoutExpired(cmd=["systemctl"], timeout=15.0))
    def test_subprocess_timeout(self, mock_run, mock_which):
        self.unit_path.parent.mkdir(parents=True, exist_ok=True)
        self.unit_path.write_text("[Unit]\n", encoding="utf-8")

        with patch("sys.stderr", new_callable=io.StringIO) as mock_err:
            rc = systemd.start_service(unit_path=self.unit_path)
            self.assertEqual(rc, 1)
            self.assertIn("timed out", mock_err.getvalue())


class TestSyncServiceCliIntegration(unittest.TestCase):
    """Verifies CLI flag parsing and dispatch through agyis sync --service."""

    @patch("harness.telemetry.sync.systemd.manage_service")
    def test_cli_sync_service_dispatch(self, mock_manage):
        mock_manage.return_value = 0
        code = main(["sync", "--service", "status"])
        self.assertEqual(code, 0)
        mock_manage.assert_called_with(
            action="status",
            interval=5.0,
            json_output=False,
        )

    @patch("harness.telemetry.sync.systemd.manage_service")
    def test_cli_sync_service_install_with_interval(self, mock_manage):
        mock_manage.return_value = 0
        code = main(["sync", "--service", "install", "--interval", "15.0", "--json"])
        self.assertEqual(code, 0)
        mock_manage.assert_called_with(
            action="install",
            interval=15.0,
            json_output=True,
        )

    def test_cli_sync_service_invalid_choice(self):
        with patch("sys.stderr", new_callable=io.StringIO):
            with self.assertRaises(SystemExit) as cm:
                main(["sync", "--service", "invalid-action"])
            self.assertEqual(cm.exception.code, 2)


if __name__ == "__main__":
    unittest.main()
