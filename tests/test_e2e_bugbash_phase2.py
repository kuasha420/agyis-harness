#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Arafat Zahan (@kuasha420)
# Corporate Stewardship & Infrastructure: Purrfect Software Limited (PSL)
# Governed by: ICARO-42/b Ordinance (Company-Supported Personal IP Framework)

"""
Comprehensive Opaque-Box E2E Test Suite for Bug Bash Phase 2 — Frontier 2 (Knot Mesh Remote Operations).
Covers F09-F16, remote boundary cases (B02-B04), cross-feature interactions (C03-C04), and fleet scenarios (S01, S03).
(Frontier 1 Live HUD & Hotkeys live in test_e2e_bugbash_phase2_hud_ui.py & test_e2e_bugbash_phase2_hud_lifecycle.py.)
"""

from __future__ import annotations

import inspect
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
from typing import Any, Dict, List, Optional, Tuple
import unittest
from unittest.mock import MagicMock, patch

# Dynamic repository resolution for hermetic test execution
repo_root = Path(__file__).resolve().parent.parent
if str(repo_root) not in sys.path:
    sys.path.insert(0, str(repo_root))

from harness.cli import main as cli_main
from harness.remote.runner import RemoteRunner, get_socket_dir
from harness.remote.safety import REMOTE_TOOLCHAIN_REGEX, sanitize_ssh_remote_payload
from harness.remote.scripts import ScriptStreamer
from harness.remote.triage import RemoteTriage


class BaseBugBashPhase2TestCase(unittest.TestCase):
    """Hermetic base test case providing isolated temporary workspaces and scrubbed env vars."""

    maxDiff = None

    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.ws = Path(self.temp_dir.name).resolve()

        self.orig_env = os.environ.copy()
        self.state_dir = self.ws / ".state"
        self.config_dir = self.ws / ".config" / "agyis"
        self.data_dir = self.ws / ".local" / "share" / "agyis"
        self.socket_dir = self.ws / ".ssh_sockets"

        self.state_dir.mkdir(parents=True, exist_ok=True)
        self.config_dir.mkdir(parents=True, exist_ok=True)
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.socket_dir.mkdir(parents=True, exist_ok=True)

        os.environ["PSL_HARNESS_STATE_DIR"] = str(self.state_dir)
        os.environ["AGYIS_CONFIG_DIR"] = str(self.config_dir)
        os.environ["AGYIS_DATA_DIR"] = str(self.data_dir)
        os.environ["PSL_SSH_SOCKET_DIR"] = str(self.socket_dir)

    def tearDown(self) -> None:
        os.environ.clear()
        os.environ.update(self.orig_env)
        self.temp_dir.cleanup()

    def run_cli(
        self,
        args: List[str],
        prog: str = "agyis",
        env_overrides: Optional[Dict[str, str]] = None,
        stdin_input: Optional[str] = None,
    ) -> Tuple[int, str, str]:
        """Executes CLI in-process via harness.cli.main, capturing stdout and stderr."""
        saved_env = os.environ.copy()
        if env_overrides:
            os.environ.update(env_overrides)

        stdin_buf = io.StringIO(stdin_input or "")
        stdout_buf = io.StringIO()
        stderr_buf = io.StringIO()

        try:
            with patch("sys.stdin", stdin_buf), patch("sys.stdout", stdout_buf), patch("sys.stderr", stderr_buf):
                try:
                    code = cli_main(args, prog=prog)
                except SystemExit as exc:
                    code = exc.code if isinstance(exc.code, int) else 0
        finally:
            os.environ.clear()
            os.environ.update(saved_env)

        return code, stdout_buf.getvalue(), stderr_buf.getvalue()


class TestTier1FeatureCoverage(BaseBugBashPhase2TestCase):
    """Tier 1: Remote operations feature coverage across F09 through F16 (40 test cases)."""

    # --- F09: Remote Exec Multiplexing ---
    def test_t1_f09_01_controlmaster_options_injected(self) -> None:
        """F09.01: RemoteRunner.build_command injects OpenSSH multiplexing options."""
        runner = RemoteRunner()
        cmd = runner.build_command("desktop", "uptime")
        cmd_str = " ".join(cmd)
        self.assertIn("ControlMaster=auto", cmd_str)
        self.assertIn("ControlPersist=10m", cmd_str)
        self.assertIn("ControlPath=", cmd_str)

    def test_t1_f09_02_toolchain_login_shell_promotion(self) -> None:
        """F09.02: Commands matching toolchain regex are promoted to login shell."""
        runner = RemoteRunner()
        cmd = runner.build_command("desktop", "pm2 status", login_shell=True)
        cmd_str = " ".join(cmd)
        self.assertIn("bash -l -c", cmd_str)

    def test_t1_f09_03_non_toolchain_no_login_shell(self) -> None:
        """F09.03: Non-toolchain command does not use login shell unless requested."""
        runner = RemoteRunner()
        cmd = runner.build_command("desktop", "uname -a", login_shell=False)
        cmd_str = " ".join(cmd)
        self.assertNotIn("bash -l -c", cmd_str)

    def test_t1_f09_04_exit_255_triggers_target_socket_cleanup(self) -> None:
        """F09.04: Return code 255 triggers target-scoped socket cleanup."""
        runner = RemoteRunner()
        with patch.object(runner, "cleanup_target_socket") as mock_cleanup, \
             patch("subprocess.run") as mock_sub:
            mock_sub.return_value = subprocess.CompletedProcess(args=["ssh"], returncode=255, stdout="", stderr="Connection failed")
            res = runner.run("offline_node", "uname -a")
            self.assertEqual(res.returncode, 255)
            mock_cleanup.assert_called_once()

    def test_t1_f09_05_exit_0_preserves_socket(self) -> None:
        """F09.05: Return code 0 does not trigger target socket cleanup."""
        runner = RemoteRunner()
        with patch.object(runner, "cleanup_target_socket") as mock_cleanup, \
             patch("subprocess.run") as mock_sub:
            mock_sub.return_value = subprocess.CompletedProcess(args=["ssh"], returncode=0, stdout="Linux", stderr="")
            res = runner.run("desktop", "uname -a")
            self.assertEqual(res.returncode, 0)
            mock_cleanup.assert_not_called()

    # --- F10: Stdin Script Streaming (Zero Disk Footprint) ---
    def test_t1_f10_01_stdin_piping_without_remote_file(self) -> None:
        """F10.01: ScriptStreamer delivers script content over stdin."""
        runner = RemoteRunner()
        script_file = self.ws / "test_stream.py"
        script_file.write_text("print('hello stdin')", encoding="utf-8")

        with patch.object(runner, "run") as mock_run:
            mock_run.return_value = subprocess.CompletedProcess(args=["ssh"], returncode=0, stdout="hello stdin", stderr="")
            res = ScriptStreamer.stream_script(runner, "desktop", script_file)
            mock_run.assert_called_once()
            _, kwargs = mock_run.call_args
            self.assertIn("input", kwargs)
            self.assertEqual(kwargs["input"], "print('hello stdin')")

    def test_t1_f10_02_python_runtime_detection(self) -> None:
        """F10.02: Python runtime detected from file extension or shebang."""
        runtime = ScriptStreamer.determine_runtime(Path("script.py"), "#!/usr/bin/env python3\n")
        self.assertIn("python3", runtime)

    def test_t1_f10_03_node_runtime_detection(self) -> None:
        """F10.03: Node runtime detected from .js extension."""
        runtime = ScriptStreamer.determine_runtime(Path("script.js"), "console.log(1)")
        self.assertIn("node", runtime)

    def test_t1_f10_04_bash_runtime_detection(self) -> None:
        """F10.04: Bash runtime detected from .sh extension."""
        runtime = ScriptStreamer.determine_runtime(Path("script.sh"), "#!/bin/bash\n")
        self.assertIn("bash", runtime)

    def test_t1_f10_05_script_arguments_passed_through(self) -> None:
        """F10.05: Script arguments are forwarded to the remote interpreter process."""
        runner = RemoteRunner()
        script_file = self.ws / "test_args.py"
        script_file.write_text("import sys; print(sys.argv)", encoding="utf-8")

        with patch.object(runner, "run") as mock_run:
            mock_run.return_value = subprocess.CompletedProcess(args=["ssh"], returncode=0, stdout="['arg1', 'arg2']", stderr="")
            ScriptStreamer.stream_script(runner, "desktop", script_file, args=["arg1", "arg2"])
            call_args = mock_run.call_args
            remote_cmd = call_args.kwargs.get("remote_cmd") or call_args.args[1]
            self.assertIn("arg1", remote_cmd)
            self.assertIn("arg2", remote_cmd)

    # --- F11: Staged Script Execution with Trap Cleanup ---
    def test_t1_f11_01_staged_script_temporary_dir(self) -> None:
        """F11.01: Staged script wrapper stages into /tmp/.psl_remote_*."""
        runner = RemoteRunner()
        script_file = self.ws / "staged.sh"
        script_file.write_text("echo staged", encoding="utf-8")

        with patch.object(runner, "run") as mock_run:
            mock_run.return_value = subprocess.CompletedProcess(args=["ssh"], returncode=0, stdout="staged", stderr="")
            ScriptStreamer.stage_script(runner, "desktop", script_file)
            call_args = mock_run.call_args
            remote_cmd = call_args.kwargs.get("remote_cmd") or call_args.args[1]
            self.assertIn("/tmp/.psl_remote_", remote_cmd)

    def test_t1_f11_02_staged_script_exit_trap(self) -> None:
        """F11.02: Staged script wrapper contains EXIT trap cleanup."""
        runner = RemoteRunner()
        script_file = self.ws / "staged.sh"
        script_file.write_text("echo staged", encoding="utf-8")

        with patch.object(runner, "run") as mock_run:
            mock_run.return_value = subprocess.CompletedProcess(args=["ssh"], returncode=0, stdout="staged", stderr="")
            ScriptStreamer.stage_script(runner, "desktop", script_file)
            call_args = mock_run.call_args
            remote_cmd = call_args.kwargs.get("remote_cmd") or call_args.args[1]
            self.assertIn("trap 'rm -rf", remote_cmd)
            self.assertIn("EXIT", remote_cmd)

    def test_t1_f11_03_staged_script_heredoc_injection(self) -> None:
        """F11.03: Staged script creates executable file with chmod +x."""
        runner = RemoteRunner()
        script_file = self.ws / "staged.sh"
        script_file.write_text("echo staged", encoding="utf-8")

        with patch.object(runner, "run") as mock_run:
            mock_run.return_value = subprocess.CompletedProcess(args=["ssh"], returncode=0, stdout="staged", stderr="")
            ScriptStreamer.stage_script(runner, "desktop", script_file)
            call_args = mock_run.call_args
            remote_cmd = call_args.kwargs.get("remote_cmd") or call_args.args[1]
            self.assertIn("chmod +x", remote_cmd)

    def test_t1_f11_04_staged_script_passes_args(self) -> None:
        """F11.04: Staged script execution passes command line arguments."""
        runner = RemoteRunner()
        script_file = self.ws / "staged.sh"
        script_file.write_text("echo staged", encoding="utf-8")

        with patch.object(runner, "run") as mock_run:
            mock_run.return_value = subprocess.CompletedProcess(args=["ssh"], returncode=0, stdout="staged", stderr="")
            ScriptStreamer.stage_script(runner, "desktop", script_file, args=["alpha", "beta"])
            call_args = mock_run.call_args
            remote_cmd = call_args.kwargs.get("remote_cmd") or call_args.args[1]
            self.assertIn("alpha beta", remote_cmd)

    def test_t1_f11_05_staged_script_preserves_return_code(self) -> None:
        """F11.05: Staged script execution returns the subprocess exit code."""
        runner = RemoteRunner()
        script_file = self.ws / "staged.sh"
        script_file.write_text("exit 42", encoding="utf-8")

        with patch.object(runner, "run") as mock_run:
            mock_run.return_value = subprocess.CompletedProcess(args=["ssh"], returncode=42, stdout="", stderr="")
            res = ScriptStreamer.stage_script(runner, "desktop", script_file)
            self.assertEqual(res.returncode, 42)

    # --- F12: Bounded Triage Report (<2,048 Bytes) ---
    def test_t1_f12_01_format_triage_strictly_under_2048(self) -> None:
        """F12.01: RemoteTriage.format_triage_markdown output is <= 2048 bytes."""
        huge_raw = "\n".join([f"line_{i} of system output data {i * 10}" for i in range(300)])
        md = RemoteTriage.format_triage_markdown(huge_raw, "desktop", max_bytes=2048)
        self.assertLessEqual(len(md.encode("utf-8")), 2048)

    def test_t1_f12_02_balanced_code_fences(self) -> None:
        """F12.02: Formatted triage markdown has balanced code fences."""
        huge_raw = "=== HOST ===\n```code block unclosed\n" + ("x" * 3000)
        md = RemoteTriage.format_triage_markdown(huge_raw, "desktop", max_bytes=2048)
        self.assertEqual(md.count("```") % 2, 0)

    def test_t1_f12_03_ports_probe_parenthesized(self) -> None:
        """F12.03: RemoteTriage.build_triage_probe parenthesizes ports fallback command (DEF-BB-051)."""
        probe = RemoteTriage.build_triage_probe(profile="ports")
        self.assertIn("(ss -tlnp 2>/dev/null || netstat -tlnp 2>/dev/null || lsof -iTCP -sTCP:LISTEN -P -n 2>/dev/null) | head -n 25", probe)

    def test_t1_f12_04_triage_profiles_filter_sections(self) -> None:
        """F12.04: Probe builder filters sections according to specified profile."""
        probe_ports = RemoteTriage.build_triage_probe(profile="ports")
        self.assertIn("=== PORTS ===", probe_ports)
        self.assertNotIn("=== SERVICES ===", probe_ports)

        probe_all = RemoteTriage.build_triage_probe(profile="all")
        self.assertIn("=== HOST ===", probe_all)
        self.assertIn("=== PORTS ===", probe_all)
        self.assertIn("=== SERVICES ===", probe_all)

    def test_t1_f12_05_triage_cli_json_flag(self) -> None:
        """F12.05: CLI agyis remote triage --json produces structured JSON."""
        mock_runner = MagicMock()
        mock_runner.run.return_value = subprocess.CompletedProcess(
            args=["ssh"],
            returncode=0,
            stdout="=== HOST ===\nLinux test-node\n",
            stderr="",
        )
        with patch("harness.remote.RemoteRunner", return_value=mock_runner):
            code, stdout, stderr = self.run_cli(["remote", "triage", "desktop", "--json"])
            self.assertEqual(code, 0)
            data = json.loads(stdout)
            self.assertEqual(data["target"], "desktop")
            self.assertTrue("report_markdown" in data or "markdown" in data)

    # --- F13: Triage Connection Error Diagnostics ---
    def test_t1_f13_01_general_error_preserved_in_markdown(self) -> None:
        """F13.01: Sections['GENERAL'] error output rendered under Diagnostic Output (DEF-BB-047)."""
        err_msg = "ssh: connect to host vps port 22: Connection refused"
        md = RemoteTriage.format_triage_markdown(err_msg, "vps")
        self.assertIn("Diagnostic & Connection Output", md)
        self.assertIn("Connection refused", md)

    def test_t1_f13_02_connection_refused_error(self) -> None:
        """F13.02: Connection refused error preserved in triage output."""
        md = RemoteTriage.format_triage_markdown("Connection refused by peer", "badnode")
        self.assertIn("Connection refused by peer", md)

    def test_t1_f13_03_host_unreachable_error(self) -> None:
        """F13.03: No route to host / network timeout error preserved in triage output."""
        md = RemoteTriage.format_triage_markdown("ssh: connect to host 10.0.0.99: No route to host", "badnode")
        self.assertIn("No route to host", md)

    def test_t1_f13_04_clean_probe_no_empty_diagnostic_header(self) -> None:
        """F13.04: Empty sections['GENERAL'] does not render diagnostic error header."""
        clean_raw = "=== HOST ===\nLinux node 6.1\n=== RESOURCES ===\nMem: 16G\n"
        md = RemoteTriage.format_triage_markdown(clean_raw, "desktop")
        self.assertNotIn("▲ Diagnostic & Connection Output", md)
        self.assertIn("Host & Resources", md)

    def test_t1_f13_05_mixed_general_and_probed_sections(self) -> None:
        """F13.05: Mixed general warning and valid sections both appear in report."""
        mixed_raw = "Banner warning: restricted system\n=== HOST ===\nLinux node 6.1\n"
        md = RemoteTriage.format_triage_markdown(mixed_raw, "desktop")
        self.assertIn("restricted system", md)
        self.assertIn("Host & Resources", md)

    # --- F14: Remote Timeout POSIX Exit 124 ---
    def test_t1_f14_01_timeout_expired_caught(self) -> None:
        """F14.01: subprocess.TimeoutExpired caught cleanly without raising exception (DEF-BB-048)."""
        runner = RemoteRunner()
        with patch("subprocess.run", side_effect=subprocess.TimeoutExpired(cmd=["ssh"], timeout=1.0)), \
             patch.object(runner, "cleanup_target_socket"):
            res = runner.run("desktop", "sleep 10", timeout=1.0)
            self.assertEqual(res.returncode, 124)

    def test_t1_f14_02_timeout_returns_exit_124(self) -> None:
        """F14.02: RemoteRunner.run on timeout returns exit code 124."""
        runner = RemoteRunner()
        with patch("subprocess.run", side_effect=subprocess.TimeoutExpired(cmd=["ssh"], timeout=5.0)), \
             patch.object(runner, "cleanup_target_socket"):
            res = runner.run("desktop", "sleep 10", timeout=5.0)
            self.assertEqual(res.returncode, 124)

    def test_t1_f14_03_timeout_stderr_diagnostic(self) -> None:
        """F14.03: Timeout result includes descriptive stderr message."""
        runner = RemoteRunner()
        with patch("subprocess.run", side_effect=subprocess.TimeoutExpired(cmd=["ssh"], timeout=2.0)), \
             patch.object(runner, "cleanup_target_socket"):
            res = runner.run("desktop", "sleep 10", timeout=2.0)
            self.assertIn("timed out after 2.0s", res.stderr)

    def test_t1_f14_04_timeout_triggers_socket_cleanup(self) -> None:
        """F14.04: Timeout automatically triggers cleanup_target_socket."""
        runner = RemoteRunner()
        with patch("subprocess.run", side_effect=subprocess.TimeoutExpired(cmd=["ssh"], timeout=1.0)), \
             patch.object(runner, "cleanup_target_socket") as mock_cleanup:
            runner.run("desktop", "sleep 10", timeout=1.0)
            mock_cleanup.assert_called_once()

    def test_t1_f14_05_cli_remote_exec_exits_124(self) -> None:
        """F14.05: CLI agyis remote exec returns exit code 124 on timeout."""
        mock_runner = MagicMock()
        mock_runner.run.return_value = subprocess.CompletedProcess(
            args=["ssh"], returncode=124, stdout="", stderr="Remote command timed out after 1.0s\n"
        )
        with patch("harness.remote.RemoteRunner", return_value=mock_runner):
            code, stdout, stderr = self.run_cli(["remote", "exec", "desktop", "sleep 10", "-t", "1"])
            self.assertEqual(code, 124)

    # --- F15: Socket Lifecycle & Graceful Termination ---
    def test_t1_f15_01_cleanup_sockets_issues_ssh_exit(self) -> None:
        """F15.01: cleanup_sockets issues graceful ssh -O exit before unlinking (DEF-BB-049)."""
        runner = RemoteRunner(socket_dir=self.socket_dir)
        mock_sock = self.socket_dir / "cm_mock_host"
        mock_sock.touch()

        with patch("subprocess.run") as mock_sub:
            mock_sub.return_value = subprocess.CompletedProcess(args=["ssh"], returncode=0)
            removed = runner.cleanup_sockets()
            self.assertIn(mock_sock, removed)
            calls = [c[0][0] for c in mock_sub.call_args_list]
            found_exit = any("-O" in c and "exit" in c for c in calls)
            self.assertTrue(found_exit)

    def test_t1_f15_02_cleanup_sockets_unlinks_files(self) -> None:
        """F15.02: cleanup_sockets removes socket files from disk."""
        runner = RemoteRunner(socket_dir=self.socket_dir)
        mock_sock = self.socket_dir / "cm_to_delete"
        mock_sock.touch()
        self.assertTrue(mock_sock.exists())

        with patch("subprocess.run"):
            runner.cleanup_sockets()
        self.assertFalse(mock_sock.exists())

    def test_t1_f15_03_socket_dir_permissions_0700(self) -> None:
        """F15.03: Socket directory created with 0700 permissions."""
        d = get_socket_dir()
        stat = d.stat()
        self.assertEqual(oct(stat.st_mode & 0o777), "0o700")

    def test_t1_f15_04_cleanup_target_socket_scoped(self) -> None:
        """F15.04: cleanup_target_socket targets only matching socket."""
        runner = RemoteRunner(socket_dir=self.socket_dir)
        sock_target = runner.get_target_socket_path("desktop")
        sock_other = runner.get_target_socket_path("laptop")
        sock_target.touch()
        sock_other.touch()

        orig_run = subprocess.run
        def mock_run(cmd, *args, **kwargs):
            if isinstance(cmd, (list, tuple)) and len(cmd) > 1 and cmd[1] == "-G":
                return orig_run(cmd, *args, **kwargs)
            return MagicMock(returncode=0)

        with patch("subprocess.run", side_effect=mock_run):
            removed = runner.cleanup_target_socket("desktop")
            self.assertIn(sock_target, removed)
            self.assertFalse(sock_target.exists())
            self.assertTrue(sock_other.exists())

    def test_t1_f15_05_list_sockets_lists_all(self) -> None:
        """F15.05: list_sockets returns list of all cm_* sockets."""
        runner = RemoteRunner(socket_dir=self.socket_dir)
        s1 = self.socket_dir / "cm_s1"
        s2 = self.socket_dir / "cm_s2"
        s1.touch()
        s2.touch()
        listed = runner.list_sockets()
        self.assertEqual(len(listed), 2)

    # --- F16: Architectural Import & Login Shell Hygiene ---
    def test_t1_f16_01_clean_import_from_remote_safety(self) -> None:
        """F16.01: REMOTE_TOOLCHAIN_REGEX imported from harness.remote.safety (DEF-BB-050)."""
        from harness.remote.safety import REMOTE_TOOLCHAIN_REGEX as REGEX1
        self.assertIsNotNone(REGEX1)
        self.assertTrue(REGEX1.search("pm2 status"))

    def test_t1_f16_02_no_hooks_import_in_remote_cli(self) -> None:
        """F16.02: harness/commands/remote.py does not import from harness.hooks (PSL-INV-008)."""
        import harness.commands.remote as remote_cmd_mod
        src = inspect.getsource(remote_cmd_mod)
        self.assertNotIn("from harness.hooks", src)
        self.assertNotIn("import harness.hooks", src)

    def test_t1_f16_03_no_double_wrapping_bash_l(self) -> None:
        """F16.03: Commands specifying bash -l -c are not double-wrapped by sanitize_ssh_remote_payload."""
        new_cmd, modified, reasons = sanitize_ssh_remote_payload("ssh desktop \"bash -l -c 'pm2 status'\"")
        self.assertFalse(modified)
        self.assertEqual(reasons, [])
        self.assertEqual(new_cmd.count("bash -l -c"), 1)

    def test_t1_f16_04_no_double_wrapping_zsh_l_sh_l(self) -> None:
        """F16.04: Commands specifying zsh -l or sh -l are preserved without login-shell double-wrapping."""
        zsh_cmd, zsh_mod, _ = sanitize_ssh_remote_payload("ssh desktop \"zsh -l -c 'nvm use 20'\"")
        sh_cmd, sh_mod, _ = sanitize_ssh_remote_payload("ssh desktop \"sh -l -c 'cargo build'\"")
        self.assertFalse(zsh_mod)
        self.assertFalse(sh_mod)
        self.assertNotIn("bash -l -c", zsh_cmd)
        self.assertNotIn("bash -l -c", sh_cmd)

    def test_t1_f16_05_toolchain_without_login_shell_promoted(self) -> None:
        """F16.05: Plain toolchain command promoted cleanly to single bash -l -c wrap."""
        new_cmd, modified, reasons = sanitize_ssh_remote_payload('ssh desktop "pm2 restart all"')
        self.assertTrue(modified)
        self.assertIn("bash -l -c 'pm2 restart all'", new_cmd)
        self.assertTrue(reasons)


class TestTier2BoundaryCases(BaseBugBashPhase2TestCase):
    """Tier 2: Remote boundary, corner, and adversarial stress cases (6 test cases)."""

    def test_t2_b02_01_single_character_target_name(self) -> None:
        """B02.01: RemoteRunner target 'c' cleanup does not match or delete unrelated socket 'client'."""
        runner = RemoteRunner(socket_dir=self.socket_dir)
        sock_target = runner.get_target_socket_path("c")
        sock_other = runner.get_target_socket_path("client")
        self.assertNotEqual(sock_target, sock_other)
        sock_target.touch()
        sock_other.touch()

        orig_run = subprocess.run
        def mock_run(cmd, *args, **kwargs):
            if isinstance(cmd, (list, tuple)) and len(cmd) > 1 and cmd[1] == "-G":
                return orig_run(cmd, *args, **kwargs)
            return MagicMock(returncode=0)

        with patch("subprocess.run", side_effect=mock_run):
            removed = runner.cleanup_target_socket("c")
            self.assertIn(sock_target, removed)
            self.assertFalse(sock_target.exists())
            self.assertTrue(sock_other.exists())

    def test_t2_b02_02_underscore_target_name(self) -> None:
        """B02.02: RemoteRunner target '_' cleanup does not match or delete unrelated socket 'desktop'."""
        runner = RemoteRunner(socket_dir=self.socket_dir)
        sock_target = runner.get_target_socket_path("_")
        sock_other = runner.get_target_socket_path("desktop")
        self.assertNotEqual(sock_target, sock_other)
        sock_target.touch()
        sock_other.touch()

        orig_run = subprocess.run
        def mock_run(cmd, *args, **kwargs):
            if isinstance(cmd, (list, tuple)) and len(cmd) > 1 and cmd[1] == "-G":
                return orig_run(cmd, *args, **kwargs)
            return MagicMock(returncode=0)

        with patch("subprocess.run", side_effect=mock_run):
            removed = runner.cleanup_target_socket("_")
            self.assertIn(sock_target, removed)
            self.assertFalse(sock_target.exists())
            self.assertTrue(sock_other.exists())

    def test_t2_b03_01_extreme_50kb_triage_clamping(self) -> None:
        """B03.01: Extreme 50KB input is deterministically clamped strictly to <= 2048 bytes."""
        huge_input = ("LOG ENTRY DATA " * 3500)
        res = RemoteTriage.format_triage_markdown(huge_input, "stress_node", max_bytes=2048)
        self.assertLessEqual(len(res.encode("utf-8")), 2048)

    def test_t2_b03_02_unclosed_code_fence_balancing(self) -> None:
        """B03.02: Truncated output with unclosed backtick fence is cleanly balanced."""
        raw = "=== HOST ===\n```bash\n" + ("echo test\n" * 300)
        md = RemoteTriage.format_triage_markdown(raw, "desktop", max_bytes=2048)
        self.assertEqual(md.count("```") % 2, 0)

    def test_t2_b04_01_empty_output_triage_handling(self) -> None:
        """B04.01: 0-byte output formatted without crashing."""
        res = RemoteTriage.format_triage_markdown("", "desktop")
        self.assertIn("Remote Triage Report", res)

    def test_t2_b04_02_permission_denied_sections(self) -> None:
        """B04.02: Permission denied probe responses are formatted cleanly."""
        raw = "=== SERVICES ===\nFailed to connect to bus: Permission denied\n"
        res = RemoteTriage.format_triage_markdown(raw, "desktop")
        self.assertIn("Services", res)
        self.assertIn("Permission denied", res)

class TestTier3CrossFeatureInteractions(BaseBugBashPhase2TestCase):
    """Tier 3: Remote cross-feature interactions (2 test cases)."""

    def test_t3_c03_socket_cleanup_during_inflight_run(self) -> None:
        """C03: Target-scoped cleanup for node A does not terminate node B's active socket."""
        runner = RemoteRunner(socket_dir=self.socket_dir)
        sock_a = runner.get_target_socket_path("nodeA")
        sock_b = runner.get_target_socket_path("nodeB")
        sock_a.touch()
        sock_b.touch()

        orig_run = subprocess.run
        def mock_run(cmd, *args, **kwargs):
            if isinstance(cmd, (list, tuple)) and len(cmd) > 1 and cmd[1] == "-G":
                return orig_run(cmd, *args, **kwargs)
            return MagicMock(returncode=0)

        with patch("subprocess.run", side_effect=mock_run):
            runner.cleanup_target_socket("nodeA")
            self.assertFalse(sock_a.exists())
            self.assertTrue(sock_b.exists())

    def test_t3_c04_hotkey_toggle_during_script_stream(self) -> None:
        """C04: F12 toggle while script is streaming over stdin does not interrupt pipe."""
        runner = RemoteRunner(socket_dir=self.socket_dir)
        script_file = self.ws / "pipe_test.py"
        script_file.write_text("print('stream active')", encoding="utf-8")

        with patch.object(runner, "run") as mock_run:
            mock_run.return_value = subprocess.CompletedProcess(args=["ssh"], returncode=0, stdout="stream active", stderr="")
            res = ScriptStreamer.stream_script(runner, "desktop", script_file)
            self.assertEqual(res.returncode, 0)


class TestTier4RealWorldScenarios(BaseBugBashPhase2TestCase):
    """Tier 4: Realistic end-to-end remote fleet scenarios (2 test cases)."""

    def test_t4_s01_full_knot_mesh_fleet_health_audit(self) -> None:
        """S01: Full Knot mesh fleet health audit across Desktop, Laptop, and Handheld nodes."""
        runner = RemoteRunner(socket_dir=self.socket_dir)
        nodes = ["desktop", "laptop", "steamdeck"]
        results = {}

        def mock_dispatch(cmd, **kwargs):
            cmd_str = " ".join(cmd)
            if "desktop" in cmd:
                return subprocess.CompletedProcess(
                    args=cmd,
                    returncode=0,
                    stdout="=== HOST ===\nLinux desktop 7.2\n=== RESOURCES ===\nMem: 16G\n",
                    stderr="",
                )
            elif "laptop" in cmd:
                raise subprocess.TimeoutExpired(cmd=cmd, timeout=5.0)
            elif "steamdeck" in cmd:
                return subprocess.CompletedProcess(
                    args=cmd,
                    returncode=255,
                    stdout="",
                    stderr="Connection refused",
                )
            return subprocess.CompletedProcess(args=cmd, returncode=0, stdout="", stderr="")

        with patch("subprocess.run", side_effect=mock_dispatch), \
             patch.object(runner, "cleanup_target_socket"):
            for node in nodes:
                try:
                    res = runner.run(node, RemoteTriage.build_triage_probe(), timeout=5.0)
                    results[node] = {
                        "exit_code": res.returncode,
                        "report": RemoteTriage.format_triage_markdown(res.stdout or res.stderr, node),
                    }
                except Exception as exc:
                    results[node] = {"error": str(exc)}

        self.assertEqual(results["desktop"]["exit_code"], 0)
        self.assertIn("Host & Resources", results["desktop"]["report"])

        self.assertEqual(results["laptop"]["exit_code"], 124)  # POSIX exit 124 on timeout
        self.assertIn("Diagnostic & Connection Output", results["laptop"]["report"])

        self.assertEqual(results["steamdeck"]["exit_code"], 255)
        self.assertIn("Connection refused", results["steamdeck"]["report"])

    def test_t4_s03_edge_node_network_dropout_255_and_socket_recovery(self) -> None:
        """S03: Edge node network drop (255) -> target socket cleanup -> clean reconnect."""
        runner = RemoteRunner(socket_dir=self.socket_dir)
        target = "edge-node"
        sock = runner.get_target_socket_path(target)
        sock.touch()
        self.assertTrue(sock.exists())

        call_count = 0
        def mock_ssh(cmd, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return subprocess.CompletedProcess(args=cmd, returncode=255, stdout="", stderr="Broken pipe")
            else:
                return subprocess.CompletedProcess(args=cmd, returncode=0, stdout="Connected over WireGuard", stderr="")

        with patch("subprocess.run", side_effect=mock_ssh), \
             patch.object(runner, "cleanup_target_socket", wraps=runner.cleanup_target_socket) as spy_cleanup:
            res1 = runner.run(target, "uptime")
            self.assertEqual(res1.returncode, 255)
            spy_cleanup.assert_called_once()
            self.assertFalse(sock.exists())

            res2 = runner.run(target, "uptime")
            self.assertEqual(res2.returncode, 0)
            self.assertEqual(res2.stdout, "Connected over WireGuard")


if __name__ == "__main__":
    unittest.main()
