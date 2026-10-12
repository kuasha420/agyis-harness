#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Arafat Zahan (@kuasha420)
# Corporate Stewardship & Infrastructure: Purrfect Software Limited (PSL)
# Governed by: ICARO-42/b Ordinance (Company-Supported Personal IP Framework)

"""
Hermetic unit and integration tests for harness/remote subsystem (ADR-027).
Covers RemoteRunner, ScriptStreamer, and RemoteTriage.
"""

import io
import json
import os
from pathlib import Path
import stat
import subprocess
import tempfile
import unittest
from unittest.mock import MagicMock, patch

from harness.remote import (
    RemoteRunner,
    RemoteScriptStreamer,
    RemoteTriage,
    RemoteTriageEngine,
    ScriptStreamer,
    SSHRunner,
    get_socket_dir,
)


class TestRemoteRunner(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.orig_state_dir = os.environ.get("PSL_HARNESS_STATE_DIR")
        os.environ["PSL_HARNESS_STATE_DIR"] = self.temp_dir.name

    def tearDown(self):
        if self.orig_state_dir is not None:
            os.environ["PSL_HARNESS_STATE_DIR"] = self.orig_state_dir
        else:
            os.environ.pop("PSL_HARNESS_STATE_DIR", None)
        self.temp_dir.cleanup()

    def test_socket_dir_resolution_and_permissions(self):
        """Verifies socket directory uses PSL_HARNESS_STATE_DIR with 0700 permissions."""
        sock_dir = get_socket_dir()
        self.assertTrue(sock_dir.exists())
        self.assertTrue(sock_dir.is_dir())
        mode = stat.S_IMODE(sock_dir.stat().st_mode)
        self.assertEqual(mode, 0o700)
        self.assertTrue(str(sock_dir).startswith(self.temp_dir.name))

    def test_socket_dir_resolution_prefers_agyis_over_psl(self):
        """Verifies get_socket_dir prefers AGYIS_HARNESS_STATE_DIR over PSL_HARNESS_STATE_DIR."""
        with tempfile.TemporaryDirectory() as td_agyis, tempfile.TemporaryDirectory() as td_psl:
            with patch.dict(os.environ, {
                "AGYIS_HARNESS_STATE_DIR": td_agyis,
                "PSL_HARNESS_STATE_DIR": td_psl,
            }):
                sock_dir = get_socket_dir()
                self.assertTrue(str(sock_dir).startswith(td_agyis))

            with patch.dict(os.environ, {
                "PSL_HARNESS_STATE_DIR": td_psl,
            }, clear=False):
                os.environ.pop("AGYIS_HARNESS_STATE_DIR", None)
                sock_dir = get_socket_dir()
                self.assertTrue(str(sock_dir).startswith(td_psl))

    def test_multiplex_options_structure(self):
        """Verifies OpenSSH multiplexing options include ControlMaster and cm_%C."""
        runner = RemoteRunner()
        opts = runner.get_multiplex_options()
        self.assertIn("ControlMaster=auto", " ".join(opts))
        self.assertIn("ControlPath=", " ".join(opts))
        self.assertIn("cm_%C", " ".join(opts))
        self.assertIn("ControlPersist=10m", " ".join(opts))
        self.assertIn("BatchMode=yes", " ".join(opts))
        self.assertIn("ConnectTimeout=10", " ".join(opts))
        self.assertIn("ServerAliveInterval=15", " ".join(opts))

    def test_build_command_basic_and_login_shell(self):
        """Verifies argument construction with ports and login shell wrapping."""
        runner = RemoteRunner()
        cmd = runner.build_command("user@staging.host", "uptime", port=2222)
        self.assertEqual(cmd[0], "ssh")
        self.assertIn("-p", cmd)
        self.assertIn("2222", cmd)
        self.assertEqual(cmd[-2], "user@staging.host")
        self.assertEqual(cmd[-1], "uptime")

        # Test login shell wrapping
        cmd_login = runner.build_command(
            "user@staging.host", "pm2 restart app", login_shell=True
        )
        self.assertIn("bash -l -c 'pm2 restart app'", cmd_login[-1])

    @patch("subprocess.run")
    def test_run_hermetic_subprocess_dispatch(self, mock_subproc):
        """Verifies runner.run invokes subprocess.run with constructed args and stdin."""
        mock_subproc.return_value = subprocess.CompletedProcess(
            args=["ssh"], returncode=0, stdout="pong\n", stderr=""
        )
        runner = RemoteRunner()
        res = runner.run("knot-desktop", "echo ping", timeout=15)
        self.assertEqual(res.returncode, 0)
        self.assertEqual(res.stdout, "pong\n")
        mock_subproc.assert_called_once()
        call_kwargs = mock_subproc.call_args[1]
        self.assertEqual(call_kwargs["timeout"], 15)

    def test_socket_listing_and_cleanup(self):
        """Verifies list_sockets and cleanup_sockets correctly manage socket files."""
        runner = RemoteRunner()
        sock1 = runner.socket_dir / "cm_abc123"
        sock2 = runner.socket_dir / "cm_def456"
        other = runner.socket_dir / "unrelated.txt"
        sock1.write_text("socket1")
        sock2.write_text("socket2")
        other.write_text("other")

        sockets = runner.list_sockets()
        self.assertEqual(len(sockets), 2)
        socket_names = [s["name"] for s in sockets]
        self.assertIn("cm_abc123", socket_names)
        self.assertIn("cm_def456", socket_names)

        removed = runner.cleanup_sockets()
        self.assertEqual(len(removed), 2)
        self.assertFalse(sock1.exists())
        self.assertFalse(sock2.exists())
        self.assertTrue(other.exists())

    def test_ssh_runner_socket_recovery_on_255(self):
        """
        Mock SSH exit code 255 and assert automatic stale ControlMaster socket
        unlinking and recovery per ADR-027.
        """
        self.assertIs(SSHRunner, RemoteRunner)
        runner = SSHRunner()
        sock = runner.socket_dir / "cm_stale_255_sock"
        sock.touch()
        self.assertTrue(sock.exists())

        mock_proc = subprocess.CompletedProcess(
            args=["ssh"],
            returncode=255,
            stdout="",
            stderr="ssh: connect to host vps port 22: Connection timed out",
        )
        with patch("subprocess.run", return_value=mock_proc):
            proc = runner.run("vps", "echo test")
            self.assertEqual(proc.returncode, 255)
            # ControlMaster socket must be automatically purged
            self.assertFalse(sock.exists())


class TestScriptStreamer(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.orig_state_dir = os.environ.get("PSL_HARNESS_STATE_DIR")
        os.environ["PSL_HARNESS_STATE_DIR"] = self.temp_dir.name

    def tearDown(self):
        if self.orig_state_dir is not None:
            os.environ["PSL_HARNESS_STATE_DIR"] = self.orig_state_dir
        else:
            os.environ.pop("PSL_HARNESS_STATE_DIR", None)
        self.temp_dir.cleanup()

    def test_determine_runtime_by_shebang_and_extension(self):
        """Verifies runtime detection from shebang line or file extensions."""
        p_py = Path(self.temp_dir.name) / "task.py"
        p_js = Path(self.temp_dir.name) / "task.js"
        p_sh = Path(self.temp_dir.name) / "task.sh"
        p_custom = Path(self.temp_dir.name) / "custom_task"

        self.assertEqual(ScriptStreamer.determine_runtime(p_py), ["python3", "-s", "-"])
        self.assertEqual(ScriptStreamer.determine_runtime(p_js), ["node", "-"])
        self.assertEqual(ScriptStreamer.determine_runtime(p_sh), ["bash", "-l", "-s"])

        # By shebang
        content_py = "#!/usr/bin/env python3\nprint('hi')"
        self.assertEqual(
            ScriptStreamer.determine_runtime(p_custom, content_py),
            ["python3", "-s", "-"],
        )
        content_node = "#!/usr/bin/env node\nconsole.log(1);"
        self.assertEqual(
            ScriptStreamer.determine_runtime(p_custom, content_node),
            ["node", "-"],
        )

    @patch("subprocess.run")
    def test_stream_script_stdin_invocation(self, mock_subproc):
        """Verifies stream_script delivers script content via stdin without creating remote files."""
        mock_subproc.return_value = subprocess.CompletedProcess(
            args=["ssh"], returncode=0, stdout="success", stderr=""
        )
        script_file = Path(self.temp_dir.name) / "probe.py"
        script_content = "import sys\nprint('args:', sys.argv[1:])\n"
        script_file.write_text(script_content)

        runner = RemoteRunner()
        res = ScriptStreamer.stream_script(
            runner, "knot-laptop", script_file, args=["--dry-run", "test"]
        )
        self.assertEqual(res.returncode, 0)
        mock_subproc.assert_called_once()
        call_args, call_kwargs = mock_subproc.call_args
        ssh_cmd = call_args[0]
        self.assertIn("python3 -s - --dry-run test", ssh_cmd[-1])
        self.assertEqual(call_kwargs["input"], script_content)

    @patch("subprocess.run")
    def test_stage_script_trap_cleanup_wrapper(self, mock_subproc):
        """Verifies stage_script wraps file creation in an automatic EXIT trap cleanup handler."""
        mock_subproc.return_value = subprocess.CompletedProcess(
            args=["ssh"], returncode=0, stdout="staged_ok", stderr=""
        )
        # 1. Shebangless script -> interpreter prepended
        script_file = Path(self.temp_dir.name) / "deploy.sh"
        script_file.write_text("echo deploying\n")

        runner = RemoteRunner()
        res = ScriptStreamer.stage_script(
            runner, "knot-laptop", script_file, args=["prod"]
        )
        self.assertEqual(res.returncode, 0)
        mock_subproc.assert_called_once()
        call_args, _ = mock_subproc.call_args
        ssh_cmd = call_args[0]
        cmd_str = ssh_cmd[-1]
        self.assertIn("mkdir -p /tmp/.psl_remote_", cmd_str)
        self.assertIn("trap", cmd_str)
        self.assertIn("rm -rf /tmp/.psl_remote_", cmd_str)
        self.assertIn("EOF_PSL_STAGE_", cmd_str)
        self.assertIn("bash -l /tmp/.psl_remote_", cmd_str)
        self.assertIn("deploy.sh prod", cmd_str)

        # 2. Script with shebang -> direct execution without extra interpreter
        mock_subproc.reset_mock()
        script_with_shebang = Path(self.temp_dir.name) / "run_bin.sh"
        script_with_shebang.write_text("#!/usr/bin/env bash\necho running\n")
        res2 = ScriptStreamer.stage_script(
            runner, "knot-laptop", script_with_shebang, args=["arg1"]
        )
        self.assertEqual(res2.returncode, 0)
        mock_subproc.assert_called_once()
        call_args2, _ = mock_subproc.call_args
        cmd_str2 = call_args2[0][-1]
        self.assertIn("chmod +x /tmp/.psl_remote_", cmd_str2)
        self.assertIn("&& /tmp/.psl_remote_", cmd_str2)

    def test_remote_scripts_missing_file_and_shebangs(self):
        """
        Asserts RemoteScriptStreamer.stream_script raises FileNotFoundError
        on non-existent scripts, and verifies shebang parsing for Node and Bash.
        """
        runner = RemoteRunner()
        missing_script = Path(self.temp_dir.name) / "does_not_exist.py"
        with self.assertRaises(FileNotFoundError):
            RemoteScriptStreamer.stream_script(runner, "staging", missing_script)

        with self.assertRaises(FileNotFoundError):
            RemoteScriptStreamer.stage_script(runner, "staging", missing_script)

        # Verify shebang detection
        node_shebang = "#!/usr/bin/env node\nconsole.log(process.version);"
        bash_shebang = "#!/bin/sh\necho 'shell test'"
        py_shebang = "#!/usr/bin/python3\nimport sys"

        temp_node = Path(self.temp_dir.name) / "script_node"
        temp_node.write_text(node_shebang, encoding="utf-8")
        temp_bash = Path(self.temp_dir.name) / "script_bash"
        temp_bash.write_text(bash_shebang, encoding="utf-8")

        self.assertEqual(RemoteScriptStreamer.determine_runtime(temp_node), ["node", "-"])
        self.assertEqual(RemoteScriptStreamer.determine_runtime(temp_bash), ["bash", "-l", "-s"])
        self.assertEqual(RemoteScriptStreamer.determine_runtime(Path("x"), node_shebang), ["node", "-"])
        self.assertEqual(RemoteScriptStreamer.determine_runtime(Path("y"), bash_shebang), ["bash", "-l", "-s"])
        self.assertEqual(RemoteScriptStreamer.determine_runtime(Path("z"), py_shebang), ["python3", "-s", "-"])


class TestRemoteTriage(unittest.TestCase):
    def test_build_triage_probe_profiles(self):
        """Verifies probe shell command formulation across different profiles."""
        cmd_all = RemoteTriage.build_triage_probe(profile="all")
        self.assertIn("=== HOST ===", cmd_all)
        self.assertIn("=== RESOURCES ===", cmd_all)
        self.assertIn("=== PORTS ===", cmd_all)
        self.assertIn("=== SERVICES ===", cmd_all)

        cmd_ports = RemoteTriage.build_triage_probe(profile="ports")
        self.assertIn("=== PORTS ===", cmd_ports)
        self.assertNotIn("=== RESOURCES ===", cmd_ports)

        cmd_logs = RemoteTriage.build_triage_probe(service="nginx", lines=30)
        self.assertIn("=== LOGS ===", cmd_logs)
        self.assertIn("nginx", cmd_logs)

    def test_format_triage_markdown_structure(self):
        """Verifies format_triage_markdown correctly structures sections and PM2 json."""
        raw_output = (
            "=== HOST ===\n"
            "staging-box\n"
            " 14:00:00 up 10 days, 1 user, load average: 0.15, 0.20, 0.25\n"
            "=== RESOURCES ===\n"
            "Mem: 16000 8000 8000 0 1000 7000\n"
            "/dev/sda1 50G 25G 25G 50% /\n"
            "=== PORTS ===\n"
            "LISTEN 0 128 0.0.0.0:80 0.0.0.0:*\n"
            "LISTEN 0 128 0.0.0.0:443 0.0.0.0:*\n"
            "=== SERVICES ===\n"
            '[{"name": "api-server", "pm2_env": {"status": "online", "restart_time": 2}}]\n'
            "=== LOGS ===\n"
            "2026-10-04 Error handled gracefully\n"
        )
        md = RemoteTriage.format_triage_markdown(raw_output, target="staging-box")
        self.assertIn("Remote Triage Report: `staging-box`", md)
        self.assertIn("Host & Resources", md)
        self.assertIn("Listening Sockets", md)
        self.assertIn("0.0.0.0:80", md)
        self.assertIn("Services Status", md)
        self.assertIn("`api-server`: `online`", md)
        self.assertIn("Diagnostic Logs", md)
        self.assertLess(len(md.encode("utf-8")), 2048)

    def test_format_triage_markdown_strictly_bounded_under_2kb(self):
        """Verifies deterministic output truncation strictly under specified max_bytes."""
        giant_output = (
            "=== PORTS ===\n"
            + "\n".join(f"LISTEN 0 128 127.0.0.1:{p} 0.0.0.0:* users:(('srv',pid={p},fd=3))" for p in range(1000, 1050))
            + "\n=== SERVICES ===\n"
            + "\n".join(f"active running service unit {s}.service" for s in range(50))
            + "\n=== LOGS ===\n"
            + "\n".join(f"Giant error log entry number {i:04d} with detailed stack traces" for i in range(50))
        )
        md = RemoteTriage.format_triage_markdown(giant_output, target="cloud-vps", max_bytes=1024)
        byte_len = len(md.encode("utf-8"))
        self.assertLessEqual(byte_len, 1024)
        self.assertIn("bounded to <2KB", md)

    def test_remote_triage_degraded_states(self):
        """
        Asserts RemoteTriageEngine generates clean, valid markdown triage reports
        when ports, Docker containers, and systemd journal logs are completely empty or unavailable.
        """
        self.assertIs(RemoteTriageEngine, RemoteTriage)
        degraded_raw = (
            "=== HOST ===\n"
            "offline-edge-node\n"
            " 00:00:00 up 0 days, 0 users, load average: 0.00, 0.00, 0.00\n"
            "=== RESOURCES ===\n"
            "=== PORTS ===\n"
            "State Recv-Q Send-Q Local Address:Port Peer Address:Port\n"
            "=== SERVICES ===\n"
            "=== LOGS ===\n"
        )
        md = RemoteTriageEngine.format_triage_markdown(degraded_raw, target="offline-edge-node")
        self.assertIn("Remote Triage Report: `offline-edge-node`", md)
        self.assertIn("_No listening ports discovered or permission denied._", md)
        self.assertIn("_No failed units or active containers detected._", md)
        self.assertIn("_No log entries captured._", md)
        self.assertLess(len(md.encode("utf-8")), 2048)

        # Test orchestration with run_triage on degraded target
        mock_runner = MagicMock()
        mock_runner.run.return_value = subprocess.CompletedProcess(
            args=["ssh"],
            returncode=0,
            stdout=degraded_raw,
            stderr="",
        )
        res = RemoteTriageEngine.run_triage(mock_runner, target="offline-edge-node")
        self.assertEqual(res["target"], "offline-edge-node")
        self.assertEqual(res["exit_code"], 0)
        self.assertIn("_No listening ports discovered or permission denied._", res["report_markdown"])


if __name__ == "__main__":
    unittest.main()
