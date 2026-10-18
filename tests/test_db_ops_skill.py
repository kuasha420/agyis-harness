#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Arafat Zahan (@kuasha420)
# Corporate Stewardship & Infrastructure: Purrfect Software Limited (PSL)
# Governed by: ICARO-42/b Ordinance (Company-Supported Personal IP Framework)

"""
tests/test_db_ops_skill.py: Hermetic unit tests for Dynamic Database Port Collision
Detection in db-ops and Doctor (Issue #62).

Tests:
1. Socket probing (Tier 1: connect_ex and bind).
2. Docker container attribution (Tier 2: labels, project, working_dir, is_self).
3. Host process fallback (Tier 3: lsof and ss).
4. Candidate free port discovery (5432..5442).
5. Surgical .env re-binding with query parameters, URL encoding, comments, and quotes.
6. detect_port_collision.py CLI flags (--check, --find-free, --rebind, --json).
7. Hygiene check integration (check_database_port_conflicts).
8. Doctor diagnostic audit and CLI report rendering.

Strict sub-second (<1.0s) execution benchmark invariant (ADR-015).
"""

from __future__ import annotations

import io
import json
import os
from pathlib import Path
import shutil
import socket
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import MagicMock, call, patch

# Ensure harness and db-ops script are importable
REPO_ROOT = Path(__file__).resolve().parent.parent
SCRIPT_DIR = REPO_ROOT / "harness" / "skills" / "db-ops" / "scripts"
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

import detect_port_collision
from harness.runtime.doctor import DEFAULT_MATRIX, print_cli_report, run_doctor
from harness.runtime.hygiene_checks import check_database_port_conflicts


class TestSocketProbe(unittest.TestCase):
    """Tier 1: Non-blocking socket connect and bind probes."""

    @patch("socket.socket")
    def test_socket_probe_connected(self, mock_socket_cls):
        """Returns True when socket.connect_ex returns 0 (daemon listening)."""
        mock_sock = MagicMock()
        mock_sock.connect_ex.return_value = 0
        mock_socket_cls.return_value.__enter__.return_value = mock_sock

        in_use = detect_port_collision.is_port_in_use(5432)
        self.assertTrue(in_use)
        mock_sock.connect_ex.assert_called_with(("127.0.0.1", 5432))

    @patch("socket.socket")
    def test_socket_probe_unbound(self, mock_socket_cls):
        """Returns False when connect_ex fails and bind succeeds."""
        mock_sock = MagicMock()
        mock_sock.connect_ex.return_value = 111  # ECONNREFUSED
        mock_sock.bind.return_value = None
        mock_socket_cls.return_value.__enter__.return_value = mock_sock

        in_use = detect_port_collision.is_port_in_use(5432)
        self.assertFalse(in_use)

    @patch("socket.socket")
    def test_socket_probe_bind_fails(self, mock_socket_cls):
        """Returns True when connect_ex fails but bind raises OSError (address in use)."""
        mock_sock = MagicMock()
        mock_sock.connect_ex.return_value = 111
        mock_sock.bind.side_effect = OSError(98, "Address already in use")
        mock_socket_cls.return_value.__enter__.return_value = mock_sock

        in_use = detect_port_collision.is_port_in_use(5432)
        self.assertTrue(in_use)


class TestDockerAttribution(unittest.TestCase):
    """Tier 2: Docker container ownership attribution."""

    @patch("subprocess.run")
    def test_docker_attribution_foreign_collision(self, mock_run):
        """Foreign container with different working_dir classified as is_self=False."""
        docker_json = json.dumps({
            "ID": "abc123456789",
            "Names": "foreign_postgres_1",
            "Image": "postgres:16-alpine",
            "Status": "Up 2 hours",
            "Ports": "0.0.0.0:5432->5432/tcp",
            "Labels": "com.docker.compose.project=jasper-hosted,com.docker.compose.project.working_dir=/home/kuasha/Dev/jasper-hosted,com.docker.compose.service=postgres",
        })
        mock_run.return_value = MagicMock(returncode=0, stdout=docker_json)

        owner = detect_port_collision.probe_docker_port_owner(
            5432,
            workspace_root="/home/kuasha/Dev/my-service",
        )
        self.assertIsNotNone(owner)
        self.assertEqual(owner["id"], "abc123456789")
        self.assertEqual(owner["name"], "foreign_postgres_1")
        self.assertEqual(owner["project"], "jasper-hosted")
        self.assertEqual(owner["working_dir"], "/home/kuasha/Dev/jasper-hosted")
        self.assertFalse(owner["is_self"])

    @patch("subprocess.run")
    def test_docker_attribution_self_owned_by_working_dir(self, mock_run):
        """Container matching workspace_root working_dir classified as is_self=True."""
        docker_json = json.dumps({
            "ID": "self12345678",
            "Names": "local_postgres_1",
            "Image": "postgres:16-alpine",
            "Status": "Up 10 minutes",
            "Ports": "0.0.0.0:5432->5432/tcp",
            "Labels": "com.docker.compose.project=my-service,com.docker.compose.project.working_dir=/home/kuasha/Dev/my-service,com.docker.compose.service=db",
        })
        mock_run.return_value = MagicMock(returncode=0, stdout=docker_json)

        owner = detect_port_collision.probe_docker_port_owner(
            5432,
            workspace_root="/home/kuasha/Dev/my-service",
        )
        self.assertIsNotNone(owner)
        self.assertTrue(owner["is_self"])

    @patch("subprocess.run")
    def test_docker_attribution_self_owned_by_project_name(self, mock_run):
        """Container matching workspace folder name in compose project label is is_self=True."""
        docker_json = json.dumps({
            "ID": "self99999999",
            "Names": "db_container",
            "Image": "postgres:15",
            "Status": "Up 1 hour",
            "Ports": "0.0.0.0:5432->5432/tcp",
            "Labels": "com.docker.compose.project=billing-api,com.docker.compose.service=postgres",
        })
        mock_run.return_value = MagicMock(returncode=0, stdout=docker_json)

        owner = detect_port_collision.probe_docker_port_owner(
            5432,
            workspace_root="/home/kuasha/Dev/billing-api",
        )
        self.assertIsNotNone(owner)
        self.assertTrue(owner["is_self"])

    @patch("subprocess.run")
    def test_docker_attribution_docker_cli_missing(self, mock_run):
        """Returns None gracefully when docker CLI is not found."""
        mock_run.side_effect = FileNotFoundError("docker not found")

        owner = detect_port_collision.probe_docker_port_owner(5432)
        self.assertIsNone(owner)

    @patch("subprocess.run")
    def test_docker_attribution_no_containers(self, mock_run):
        """Returns None when docker ps returns empty output (no published port)."""
        mock_run.return_value = MagicMock(returncode=0, stdout="")

        owner = detect_port_collision.probe_docker_port_owner(5432)
        self.assertIsNone(owner)


class TestHostProcessAttribution(unittest.TestCase):
    """Tier 3: Fallback inspection via lsof and ss."""

    @patch("subprocess.run")
    def test_lsof_process_attribution(self, mock_run):
        """Extracts process name and PID from lsof stdout."""
        lsof_out = (
            "COMMAND   PID     USER   FD   TYPE DEVICE SIZE/OFF NODE NAME\n"
            "postgres 4321 postgres    3u  IPv4  12345      0t0  TCP *:5432 (LISTEN)\n"
        )
        mock_run.return_value = MagicMock(returncode=0, stdout=lsof_out)

        owner = detect_port_collision.probe_host_process_owner(5432)
        self.assertIsNotNone(owner)
        self.assertEqual(owner["type"], "host_process")
        self.assertEqual(owner["name"], "postgres")
        self.assertEqual(owner["pid"], 4321)
        self.assertEqual(owner["user"], "postgres")

    @patch("subprocess.run")
    def test_ss_process_attribution(self, mock_run):
        """Extracts process name and PID from ss stdout when lsof fails."""
        def fake_run(cmd, *args, **kwargs):
            if cmd[0] == "lsof":
                return MagicMock(returncode=1, stdout="")
            if cmd[0] == "ss":
                ss_out = 'tcp LISTEN 0 128 0.0.0.0:5432 0.0.0.0:* users:(("postgres",pid=9876,fd=3))\n'
                return MagicMock(returncode=0, stdout=ss_out)
            return MagicMock(returncode=1, stdout="")

        mock_run.side_effect = fake_run

        owner = detect_port_collision.probe_host_process_owner(5432)
        self.assertIsNotNone(owner)
        self.assertEqual(owner["type"], "host_process")
        self.assertEqual(owner["name"], "postgres")
        self.assertEqual(owner["pid"], 9876)

    @patch("subprocess.run")
    def test_unknown_process_fallback(self, mock_run):
        """Returns unknown process info when both lsof and ss fail."""
        mock_run.return_value = MagicMock(returncode=1, stdout="")

        owner = detect_port_collision.probe_host_process_owner(5432)
        self.assertIsNotNone(owner)
        self.assertEqual(owner["name"], "unknown")
        self.assertIsNone(owner["pid"])


class TestFreePortDiscovery(unittest.TestCase):
    """Candidate free port discovery across 5432..5442."""

    @patch("detect_port_collision.is_port_in_use")
    def test_find_free_port_first_port_available(self, mock_in_use):
        """Returns 5432 immediately when 5432 is unbound."""
        mock_in_use.return_value = False

        free_p = detect_port_collision.find_free_port(5432, 5442)
        self.assertEqual(free_p, 5432)
        mock_in_use.assert_called_once_with(5432, host="127.0.0.1")

    @patch("detect_port_collision.is_port_in_use")
    def test_find_free_port_scans_until_free(self, mock_in_use):
        """Scans ports 5432..5436 and returns 5437."""
        # Ports 5432..5436 in use, 5437 is free
        mock_in_use.side_effect = lambda p, **kwargs: p < 5437

        free_p = detect_port_collision.find_free_port(5432, 5442)
        self.assertEqual(free_p, 5437)

    @patch("detect_port_collision.is_port_in_use")
    def test_find_free_port_all_exhausted(self, mock_in_use):
        """Returns None when all ports 5432..5442 are occupied."""
        mock_in_use.return_value = True

        free_p = detect_port_collision.find_free_port(5432, 5442)
        self.assertIsNone(free_p)


class TestCollisionLadder(unittest.TestCase):
    """Full 3-tier collision ladder resolution."""

    @patch("detect_port_collision.is_port_in_use", return_value=False)
    def test_collision_ladder_unbound(self, _):
        """Unbound port returns status UNBOUND, collision False."""
        res = detect_port_collision.check_port_collision(5432)
        self.assertEqual(res["status"], "UNBOUND")
        self.assertFalse(res["collision"])
        self.assertIsNone(res["owner"])
        self.assertEqual(res["free_port"], 5432)

    @patch("detect_port_collision.probe_docker_port_owner")
    @patch("detect_port_collision.is_port_in_use", return_value=True)
    def test_collision_ladder_self_owned(self, _, mock_docker):
        """Self-owned docker container returns status SELF_OWNED, collision False."""
        mock_docker.return_value = {
            "type": "docker",
            "name": "my_db",
            "is_self": True,
        }

        res = detect_port_collision.check_port_collision(5432, workspace_root="/app")
        self.assertEqual(res["status"], "SELF_OWNED")
        self.assertFalse(res["collision"])
        self.assertEqual(res["owner"]["name"], "my_db")

    @patch("detect_port_collision.find_free_port", return_value=5437)
    @patch("detect_port_collision.probe_docker_port_owner")
    @patch("detect_port_collision.is_port_in_use", return_value=True)
    def test_collision_ladder_foreign_docker(self, _, mock_docker, __):
        """Foreign docker container returns status FOREIGN_COLLISION, collision True."""
        mock_docker.return_value = {
            "type": "docker",
            "id": "foreign123",
            "name": "foreign_postgres",
            "project": "foreign-project",
            "is_self": False,
        }

        res = detect_port_collision.check_port_collision(5432, workspace_root="/app")
        self.assertEqual(res["status"], "FOREIGN_COLLISION")
        self.assertTrue(res["collision"])
        self.assertEqual(res["free_port"], 5437)
        self.assertIn("foreign-project", res["details"])
        self.assertIn("docker stop", res["remediation"])

    @patch("detect_port_collision.find_free_port", return_value=5438)
    @patch("detect_port_collision.probe_host_process_owner")
    @patch("detect_port_collision.probe_docker_port_owner", return_value=None)
    @patch("detect_port_collision.is_port_in_use", return_value=True)
    def test_collision_ladder_host_process(self, _, __, mock_proc, ___):
        """Host process returns status FOREIGN_COLLISION with process attribution."""
        mock_proc.return_value = {
            "type": "host_process",
            "name": "postgres",
            "pid": 5555,
        }

        res = detect_port_collision.check_port_collision(5432)
        self.assertEqual(res["status"], "FOREIGN_COLLISION")
        self.assertTrue(res["collision"])
        self.assertEqual(res["free_port"], 5438)
        self.assertIn("PID: 5555", res["details"])


class TestEnvRebind(unittest.TestCase):
    """Regex-safe .env file re-binding."""

    def test_rebind_preserves_query_params_passwords_and_comments(self):
        """Rebinds POSTGRES_PORT and DATABASE_URL preserving query params, %40, and comments."""
        with tempfile.TemporaryDirectory() as td:
            env_file = Path(td) / ".env"
            original_content = (
                "# Environment Variables for Dev Stack\n"
                "NODE_ENV=development\n"
                'POSTGRES_PORT="5432" # active postgres port\n'
                'DATABASE_URL="postgresql://user:p%40ssword@localhost:5432/mydb?schema=public&sslmode=disable" # primary db connection\n'
                "DIRECT_URL='postgresql://user:p%40ssword@localhost:5432/mydb' # unpooled connection\n"
                "OTHER_PORT=8080\n"
            )
            env_file.write_text(original_content, encoding="utf-8")

            ok, msg = detect_port_collision.rebind_env_file(env_file, 5437)
            self.assertTrue(ok)
            self.assertIn("port variable(s)", msg)

            updated_content = env_file.read_text(encoding="utf-8")
            self.assertIn('POSTGRES_PORT="5437" # active postgres port', updated_content)
            self.assertIn(
                'DATABASE_URL="postgresql://user:p%40ssword@localhost:5437/mydb?schema=public&sslmode=disable" # primary db connection',
                updated_content,
            )
            self.assertIn(
                "DIRECT_URL='postgresql://user:p%40ssword@localhost:5437/mydb' # unpooled connection",
                updated_content,
            )
            self.assertIn("OTHER_PORT=8080", updated_content)

    def test_rebind_unquoted_database_url_without_port(self):
        """Rebinds unquoted DATABASE_URL that previously lacked explicit port."""
        with tempfile.TemporaryDirectory() as td:
            env_file = Path(td) / ".env"
            env_file.write_text("DATABASE_URL=postgres://postgres:secret@127.0.0.1/production\n", encoding="utf-8")

            ok, _ = detect_port_collision.rebind_env_file(env_file, 5440)
            self.assertTrue(ok)
            updated = env_file.read_text(encoding="utf-8")
            self.assertEqual(updated.strip(), "DATABASE_URL=postgres://postgres:secret@127.0.0.1:5440/production")

    def test_rebind_missing_file_returns_false(self):
        """Returns False with error message when target file does not exist."""
        ok, msg = detect_port_collision.rebind_env_file("/nonexistent/.env", 5433)
        self.assertFalse(ok)
        self.assertIn("does not exist", msg)

    def test_rebind_no_matching_variables(self):
        """Returns False when .env has no database port or url keys."""
        with tempfile.TemporaryDirectory() as td:
            env_file = Path(td) / ".env"
            env_file.write_text("FOO=bar\nBAZ=qux\n", encoding="utf-8")

            ok, msg = detect_port_collision.rebind_env_file(env_file, 5433)
            self.assertFalse(ok)
            self.assertIn("No matching", msg)


class TestScriptCLI(unittest.TestCase):
    """CLI invocations of detect_port_collision.py."""

    @patch("detect_port_collision.check_port_collision")
    def test_cli_check_unbound_json(self, mock_check):
        """--check --json outputs valid JSON and exits 0 when UNBOUND."""
        mock_check.return_value = {
            "status": "UNBOUND",
            "collision": False,
            "port": 5432,
            "owner": None,
            "free_port": 5432,
            "details": "Port 5432 is unbound.",
        }

        buf = io.StringIO()
        with patch("sys.stdout", buf):
            code = detect_port_collision.main(["--check", "--port", "5432", "--json"])

        self.assertEqual(code, 0)
        data = json.loads(buf.getvalue())
        self.assertEqual(data["status"], "UNBOUND")
        self.assertEqual(data["port"], 5432)

    @patch("detect_port_collision.check_port_collision")
    def test_cli_check_foreign_collision_json(self, mock_check):
        """--check --json outputs valid JSON and exits 1 when FOREIGN_COLLISION."""
        mock_check.return_value = {
            "status": "FOREIGN_COLLISION",
            "collision": True,
            "port": 5432,
            "owner": {"type": "docker", "name": "foreign_db"},
            "free_port": 5437,
            "details": "Port collision.",
            "remediation": "Rebind port.",
        }

        buf = io.StringIO()
        with patch("sys.stdout", buf):
            code = detect_port_collision.main(["--check", "--port", "5432", "--json"])

        self.assertEqual(code, 1)
        data = json.loads(buf.getvalue())
        self.assertEqual(data["status"], "FOREIGN_COLLISION")
        self.assertEqual(data["free_port"], 5437)

    @patch("detect_port_collision.find_free_port", return_value=5437)
    def test_cli_find_free_json(self, _):
        """--find-free --json outputs candidate free port and exits 0."""
        buf = io.StringIO()
        with patch("sys.stdout", buf):
            code = detect_port_collision.main(["--find-free", "--port", "5432", "--json"])

        self.assertEqual(code, 0)
        data = json.loads(buf.getvalue())
        self.assertEqual(data["free_port"], 5437)

    def test_cli_rebind_env_success(self):
        """--find-free --rebind --env <path> --json rebinds env and exits 0."""
        with tempfile.TemporaryDirectory() as td:
            env_file = Path(td) / ".env"
            env_file.write_text("POSTGRES_PORT=5432\nDATABASE_URL=postgres://u:p@localhost:5432/db\n", encoding="utf-8")

            with patch("detect_port_collision.find_free_port", return_value=5437):
                buf = io.StringIO()
                with patch("sys.stdout", buf):
                    code = detect_port_collision.main([
                        "--find-free",
                        "--rebind",
                        "--env", str(env_file),
                        "--port", "5432",
                        "--json",
                    ])

            self.assertEqual(code, 0)
            data = json.loads(buf.getvalue())
            self.assertEqual(data["action_taken"], "rebind")
            self.assertEqual(data["free_port"], 5437)
            self.assertIn("5437", env_file.read_text(encoding="utf-8"))

    def test_cli_rebind_without_env_flag_fails(self):
        """--rebind without --env outputs error and exits 1."""
        buf = io.StringIO()
        with patch("sys.stdout", buf):
            code = detect_port_collision.main(["--rebind", "--json"])

        self.assertEqual(code, 1)
        data = json.loads(buf.getvalue())
        self.assertEqual(data["status"], "ERROR")

    @patch("detect_port_collision.check_port_collision")
    def test_cli_human_readable_output(self, mock_check):
        """Emits structured human-readable text without --json."""
        mock_check.return_value = {
            "status": "UNBOUND",
            "collision": False,
            "port": 5432,
            "owner": None,
            "free_port": 5432,
            "details": "Port 5432 is free.",
        }

        buf = io.StringIO()
        with patch("sys.stdout", buf):
            code = detect_port_collision.main(["--check", "--port", "5432"])

        self.assertEqual(code, 0)
        out = buf.getvalue()
        self.assertIn("Database Port (5432) Status: UNBOUND", out)
        self.assertIn("Details: Port 5432 is free.", out)


class TestHygieneCheck(unittest.TestCase):
    """Hygiene check function: check_database_port_conflicts."""

    @patch("detect_port_collision.check_port_collision")
    def test_hygiene_check_pass(self, mock_check):
        """Maps UNBOUND to hygiene status PASS."""
        mock_check.return_value = {
            "status": "UNBOUND",
            "collision": False,
            "port": 5432,
            "owner": None,
            "free_port": 5432,
            "details": "Port 5432 is free.",
            "remediation": None,
        }

        res = check_database_port_conflicts(port=5432)
        self.assertEqual(res["status"], "PASS")
        self.assertFalse(res["collision"])
        self.assertEqual(res["port"], 5432)
        self.assertIsNone(res["remediation"])

    @patch("detect_port_collision.check_port_collision")
    def test_hygiene_check_ok_self_owned(self, mock_check):
        """Maps SELF_OWNED to hygiene status OK."""
        mock_check.return_value = {
            "status": "SELF_OWNED",
            "collision": False,
            "port": 5432,
            "owner": {"type": "docker", "name": "my_db"},
            "free_port": None,
            "details": "Port 5432 is self owned.",
            "remediation": None,
        }

        res = check_database_port_conflicts(port=5432)
        self.assertEqual(res["status"], "OK")
        self.assertFalse(res["collision"])

    @patch("detect_port_collision.check_port_collision")
    def test_hygiene_check_warning_foreign_collision(self, mock_check):
        """Maps FOREIGN_COLLISION to hygiene status WARNING with remediation."""
        mock_check.return_value = {
            "status": "FOREIGN_COLLISION",
            "collision": True,
            "port": 5432,
            "owner": {"type": "docker", "name": "foreign_db"},
            "free_port": 5437,
            "details": "Port collision with foreign_db.",
            "remediation": "docker stop foreign_db",
        }

        res = check_database_port_conflicts(port=5432)
        self.assertEqual(res["status"], "WARNING")
        self.assertTrue(res["collision"])
        self.assertEqual(res["free_port"], 5437)
        self.assertEqual(res["remediation"], "docker stop foreign_db")


class TestDoctorIntegration(unittest.TestCase):
    """Doctor diagnostic audit and report rendering integration."""

    @patch("harness.runtime.doctor.check_database_port_conflicts")
    def test_doctor_audit_includes_database_port_conflicts(self, mock_db_check):
        """run_doctor includes database_port_conflicts and adds warning when status==WARNING."""
        mock_db_check.return_value = {
            "status": "WARNING",
            "collision": True,
            "port": 5432,
            "details": "Port 5432 collision.",
            "remediation": "Rebind port.",
        }

        with patch("harness.runtime.doctor.check_rea_tooling", return_value={"status": "ok"}):
            audit = run_doctor(DEFAULT_MATRIX, experimental_rea=False)

        self.assertIn("database_port_conflicts", audit)
        self.assertEqual(audit["database_port_conflicts"]["status"], "WARNING")
        self.assertGreaterEqual(audit["summary"]["warning"], 1)

    def test_print_cli_report_renders_database_port_pass_and_warn(self):
        """print_cli_report renders Database Port (5432) [PASS] and [WARN]."""
        pass_audit = {
            "os_family": "linux",
            "summary": {"total_tools": 0, "ok": 0, "warning": 0, "outdated": 0, "missing": 0, "optional_missing": 0},
            "tiers": {},
            "database_port_conflicts": {
                "status": "PASS",
                "port": 5432,
                "details": "Port 5432 is free (no database collision).",
            },
        }

        buf = io.StringIO()
        with patch("sys.stdout", buf):
            print_cli_report(pass_audit)
        out = buf.getvalue()
        self.assertIn("Database Port (5432):", out)
        self.assertIn("PASS", out)

        warn_audit = {
            "os_family": "linux",
            "summary": {"total_tools": 0, "ok": 0, "warning": 0, "outdated": 0, "missing": 0, "optional_missing": 0},
            "tiers": {},
            "database_port_conflicts": {
                "status": "WARNING",
                "port": 5432,
                "details": "Port 5432 collision: occupied by foreign container.",
                "remediation": "Run detect_port_collision.py --find-free --rebind --env .env",
            },
        }

        buf2 = io.StringIO()
        with patch("sys.stdout", buf2):
            print_cli_report(warn_audit)
        out2 = buf2.getvalue()
        self.assertIn("Database Port (5432):", out2)
        self.assertIn("WARN", out2)
        self.assertIn("Run detect_port_collision.py", out2)


if __name__ == "__main__":
    unittest.main()
