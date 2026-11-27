#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Arafat Zahan (@kuasha420)
# Corporate Stewardship & Infrastructure: Purrfect Software Limited (PSL)
# Governed by: ICARO-42/b Ordinance (Company-Supported Personal IP Framework)

"""
Hermetic Wave 1.1 tests for stable --rea promotion, unified doctor --re,
standalone agyis-doctor --heal --json, cmd_decompile daemon routing, and dynamic Ghidra 12.x patching.
"""

from __future__ import annotations

import argparse
import io
import json
import os
from pathlib import Path
import socket
import subprocess
import tempfile
import threading
import unittest
from unittest.mock import MagicMock, patch

from harness.cli import main as cli_main
from harness.commands.re import cmd_decompile
from harness.re.daemon import get_socket_file
from harness.re.patcher import apply_patch, check_patch
from harness.runtime import doctor as runtime_doctor
from harness.runtime.healing import heal_rea_tooling


class TestReaPromotionAndUnifiedDoctor(unittest.TestCase):
    """Tests --rea promotion, deprecated --experimental-rea stderr warning, and doctor --re unification."""

    def setUp(self) -> None:
        self.td = tempfile.TemporaryDirectory()
        self.ws = Path(self.td.name).resolve()

    def tearDown(self) -> None:
        self.td.cleanup()

    def _run_doc(self, **kwargs):
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
        mock_cli = {
            "status": "OK",
            "path": "/usr/bin/agyis",
            "collision": False,
            "agyis_status": "OK",
            "agyis_path": "/usr/bin/agyis",
            "psl_details": {"status": "OK", "collision": False, "path": "/usr/bin/psl"},
            "psl_collision": {"status": "OK", "collision": False, "path": "/usr/bin/psl"},
            "details": "ok",
            "remediation": None,
        }
        with patch("harness.runtime.doctor.check_tool", return_value=mock_tool), \
             patch("harness.runtime.doctor.check_cli_binary", return_value=mock_cli), \
             patch("harness.runtime.doctor.check_telemetry_daemon", return_value={"status": "OK"}), \
             patch("harness.runtime.doctor.check_database_port_conflicts", return_value={"status": "PASS"}), \
             patch("harness.runtime.doctor.check_hooks_health", return_value={"status": "OK", "checked_hooks": []}):
            return runtime_doctor.run_doctor(runtime_doctor.DEFAULT_MATRIX, workspace_root=self.ws, **kwargs)

    def test_deprecated_experimental_rea_warns_stderr_without_polluting_json(self) -> None:
        mock_rea = {"status": "ok", "fast_path": False, "binary": "/usr/bin/rea", "version": "6.9.0", "mcp_configured": True, "providers": {"active": [], "unavailable": [], "details": []}}
        with patch("harness.runtime.doctor.check_rea_tooling", return_value=mock_rea), \
             patch("harness.runtime.doctor.check_tool", return_value={"name": "m", "binary": "m", "status": "OK", "path": "/bin/m", "version": "99.0.0", "min_version": "1.0.0", "is_shim": False, "is_collision": False, "spec": {}}), \
             patch("harness.runtime.doctor.check_cli_binary", return_value={"status": "OK", "collision": False, "psl_details": {"status": "OK", "collision": False}}), \
             patch("harness.runtime.doctor.check_telemetry_daemon", return_value={"status": "OK"}), \
             patch("harness.runtime.doctor.check_database_port_conflicts", return_value={"status": "PASS"}), \
             patch("harness.runtime.doctor.check_hooks_health", return_value={"status": "OK", "checked_hooks": []}), \
             patch("sys.stdout", new_callable=io.StringIO) as out_buf, \
             patch("sys.stderr", new_callable=io.StringIO) as err_buf:
            code = cli_main(["doctor", "-w", str(self.ws), "--experimental-rea", "--json"], prog="agyis")
            self.assertEqual(code, 0)
            self.assertIn("DeprecationWarning", err_buf.getvalue())
            data = json.loads(out_buf.getvalue())
            self.assertTrue(data["rea"])
            self.assertTrue(data["experimental_rea"])

    def test_doctor_re_and_workspace_configs_activate_rea(self) -> None:
        mock_rea = {"status": "ok", "fast_path": False, "binary": "/usr/bin/rea", "version": "6.9.0", "mcp_configured": True, "providers": {"active": [], "unavailable": [], "details": []}}
        mock_ft = {"profile": "static-cleanroom", "tools": [], "missing_packages": [], "summary": {"pass": 1, "warn": 0, "info": 0}}
        with patch("harness.runtime.doctor.check_rea_tooling", return_value=mock_rea) as mock_chk, \
             patch("harness.runtime.doctor.audit_forensic_toolchain", return_value=mock_ft):
            res_re = self._run_doc(re_toolchain=True)
            self.assertTrue(res_re["re_toolchain"])
            self.assertTrue(res_re["rea"])
            self.assertTrue(res_re["experimental_rea"])
            self.assertTrue(mock_chk.call_args.kwargs.get("rea"))

            # Legacy .psl/config.json {"experimental_rea": true}
            psl_cfg = self.ws / ".psl" / "config.json"
            psl_cfg.parent.mkdir(parents=True, exist_ok=True)
            psl_cfg.write_text(json.dumps({"experimental_rea": True}), encoding="utf-8")
            res_cfg = self._run_doc()
            self.assertTrue(res_cfg["rea"])
            self.assertFalse(res_cfg["re_toolchain"])

    def test_standalone_agyis_doctor_flags_and_heal_before_json(self) -> None:
        mock_audit = {
            "os_family": "linux",
            "cli_binary": {"status": "OK"},
            "tiers": {},
            "summary": {"ok": 5, "warning": 0, "outdated": 0, "missing": 0, "optional_missing": 0},
            "rea": True,
            "re_toolchain": True,
        }
        with patch("harness.runtime.doctor.run_doctor", return_value=mock_audit) as mock_run, \
             patch("harness.runtime.doctor.heal_environment", return_value=["healed-item"]) as mock_heal, \
             patch("sys.argv", ["agyis-doctor", "-w", str(self.ws), "--rea", "--re", "--heal", "--json"]), \
             patch("sys.stdout", new_callable=io.StringIO) as out_buf, \
             patch("sys.stderr", new_callable=io.StringIO) as err_buf:
            code = runtime_doctor.main()
            self.assertEqual(code, 0)
            self.assertEqual(err_buf.getvalue(), "")
            self.assertEqual(mock_run.call_count, 2)
            mock_heal.assert_called_once()
            self.assertTrue(mock_run.call_args.kwargs["rea"])
            self.assertTrue(mock_run.call_args.kwargs["re_toolchain"])
            self.assertEqual(mock_run.call_args.kwargs["workspace_root"], self.ws)
            data = json.loads(out_buf.getvalue())
            self.assertEqual(data["heal_actions"], ["healed-item"])

    def test_heal_json_prints_progress_to_stderr_keeping_stdout_valid_json(self) -> None:
        fake_audit = {
            "os_family": "linux",
            "rea_tooling": {"status": "optional_missing", "binary": None},
            "tiers": {},
            "summary": {"ok": 5, "warning": 0, "outdated": 0, "missing": 0, "optional_missing": 0},
        }
        with patch("harness.runtime.doctor.run_doctor", return_value=fake_audit), \
             patch("harness.runtime.tool_checks.check_node_toolchain", return_value={"rea_compatible": False}), \
             patch("harness.runtime.tool_checks.configure_rea_mcp_server", return_value=([], [])), \
             patch("harness.runtime.tool_checks.find_jdk21_path", return_value=None), \
             patch("harness.runtime.healing.provision_rea_skill", return_value=None), \
             patch("shutil.which", side_effect=lambda name: "/usr/bin/pnpm" if name == "pnpm" else None), \
             patch("subprocess.run", return_value=MagicMock(returncode=0, stdout="", stderr="")), \
             patch("sys.stdout", new_callable=io.StringIO) as out_buf, \
             patch("sys.stderr", new_callable=io.StringIO) as err_buf:
            code = cli_main(["doctor", "-w", str(self.ws), "--rea", "--heal", "--json"], prog="agyis")
        self.assertEqual(code, 0)
        data = json.loads(out_buf.getvalue())
        self.assertIn("heal_actions", data)
        self.assertIn("[*]", err_buf.getvalue())
        self.assertNotIn("[*]", out_buf.getvalue())

        # Also exercise heal_rea_tooling directly with stdout/stderr capture
        with patch("harness.runtime.tool_checks.check_node_toolchain", return_value={"rea_compatible": True}), \
             patch("harness.runtime.tool_checks.configure_rea_mcp_server", return_value=([], [])), \
             patch("harness.runtime.tool_checks.find_jdk21_path", return_value=None), \
             patch("harness.runtime.healing.provision_rea_skill", return_value=None), \
             patch("shutil.which", side_effect=lambda name: "/usr/bin/npm" if name == "npm" else None), \
             patch("subprocess.run", return_value=MagicMock(returncode=0, stdout="", stderr="")), \
             patch("sys.stdout", new_callable=io.StringIO) as out2, \
             patch("sys.stderr", new_callable=io.StringIO) as err2:
            heal_rea_tooling(fake_audit)
        self.assertEqual(out2.getvalue(), "")
        self.assertIn("Installing/updating rea-agents", err2.getvalue())


class TestReBridgeAndDynamicPatcher(unittest.TestCase):
    """Tests cmd_decompile Unix-socket routing -> CLI fallback and dynamic Ghidra 12.x patching."""

    def setUp(self) -> None:
        self.td = tempfile.TemporaryDirectory()
        self.ws = Path(self.td.name).resolve()
        self.dr = self.ws / ".dirtyroom"
        self.dr.mkdir(parents=True, exist_ok=True)
        self.target_bin = self.ws / "sample.bin"
        self.target_bin.write_bytes(b"\x7fELF" + b"\x00" * 64)

    def tearDown(self) -> None:
        self.td.cleanup()

    def test_cmd_decompile_routes_via_socket_then_caches(self) -> None:
        sock_path = get_socket_file(self.dr)
        methods_seen = []

        srv = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        srv.bind(str(sock_path))
        srv.listen(4)
        srv.settimeout(2.0)

        def _serve() -> None:
            for _ in range(2):
                conn, _ = srv.accept()
                with conn, conn.makefile("r", encoding="utf-8") as reader:
                    req = json.loads(reader.readline())
                    tool_name = req["params"]["name"]
                    methods_seen.append(tool_name)
                    text = "opened" if tool_name == "open_binary" else "int main(void) { return 42; }"
                    resp = {"jsonrpc": "2.0", "id": req["id"], "result": {"content": [{"type": "text", "text": text}]}}
                    conn.sendall((json.dumps(resp) + "\n").encode("utf-8"))

        thread = threading.Thread(target=_serve, daemon=True)
        thread.start()

        try:
            args = argparse.Namespace(procedure="main", binary=str(self.target_bin), no_cache=True, timeout=5.0)
            out_buf = io.StringIO()
            with patch("harness.commands.re.get_dirtyroom_db", return_value=None), \
                 patch("harness.commands.re.get_dirtyroom_root", return_value=self.dr), \
                 patch("shutil.which", return_value=None), \
                 patch("subprocess.run") as mock_sub, \
                 patch("sys.stdout", out_buf):
                code = cmd_decompile(args)
            thread.join(timeout=2.0)
            self.assertEqual(code, 0)
            self.assertEqual(methods_seen, ["open_binary", "procedure_pseudo_code"])
            self.assertIn("return 42", out_buf.getvalue())
            mock_sub.assert_not_called()
            cached = list((self.dr / "cache" / "decompile").glob("*.c"))
            self.assertEqual(len(cached), 1)
            self.assertIn("return 42", cached[0].read_text(encoding="utf-8"))
        finally:
            srv.close()

    def test_cmd_decompile_falls_back_to_cli_when_socket_absent(self) -> None:
        args = argparse.Namespace(procedure="main", binary=str(self.target_bin), no_cache=True, timeout=5.0)
        out_buf = io.StringIO()
        with patch("harness.commands.re.get_dirtyroom_db", return_value=None), \
             patch("harness.commands.re.get_dirtyroom_root", return_value=self.dr), \
             patch("shutil.which", return_value="/usr/local/bin/rea"), \
             patch("subprocess.run", return_value=MagicMock(returncode=0, stdout="void fallback() {}", stderr="")) as mock_run, \
             patch("sys.stdout", out_buf):
            code = cmd_decompile(args)
        self.assertEqual(code, 0)
        self.assertIn("fallback", out_buf.getvalue())
        mock_run.assert_called_once()

    def test_cmd_decompile_daemon_error_warns_stderr_and_falls_back(self) -> None:
        sock_path = get_socket_file(self.dr)
        srv = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        srv.bind(str(sock_path))
        srv.listen(2)
        srv.settimeout(2.0)

        def _serve_err() -> None:
            conn, _ = srv.accept()
            with conn, conn.makefile("r", encoding="utf-8") as reader:
                req = json.loads(reader.readline())
                resp = {"jsonrpc": "2.0", "id": req["id"], "error": {"code": -32001, "message": "project locked"}}
                conn.sendall((json.dumps(resp) + "\n").encode("utf-8"))

        thread = threading.Thread(target=_serve_err, daemon=True)
        thread.start()
        try:
            args = argparse.Namespace(procedure="main", binary=str(self.target_bin), no_cache=True, timeout=5.0)
            out_buf = io.StringIO()
            err_buf = io.StringIO()
            with patch("harness.commands.re.get_dirtyroom_db", return_value=None), \
                 patch("harness.commands.re.get_dirtyroom_root", return_value=self.dr), \
                 patch("shutil.which", return_value="/usr/local/bin/rea"), \
                 patch("subprocess.run", return_value=MagicMock(returncode=0, stdout="void recovered() {}", stderr="")), \
                 patch("sys.stdout", out_buf), \
                 patch("sys.stderr", err_buf):
                code = cmd_decompile(args)
            thread.join(timeout=2.0)
            self.assertEqual(code, 0)
            self.assertIn("recovered", out_buf.getvalue())
            self.assertIn("falling back to CLI", err_buf.getvalue())
        finally:
            srv.close()

    def test_patcher_matches_dynamic_ghidra_12x_release(self) -> None:
        rea_root = self.ws / "rea-agents"
        gh_dir = rea_root / "dist" / "ghidra"
        mcp_dir = rea_root / "dist" / "mcp"
        cli_dir = rea_root / "dist" / "cli-runtime"
        for d in (gh_dir, mcp_dir, cli_dir):
            d.mkdir(parents=True, exist_ok=True)
        (gh_dir / "GhidraLauncher.js").write_text("const bridgeDirectory = scriptPath.dirname(options.bridgeScriptPath);\nconst ghidraHeadlessArguments = [];\n", encoding="utf-8")
        (gh_dir / "GhidraReleasePolicy.js").write_text('export const SUPPORTED_GHIDRA_VERSION = "12.1.4";\n', encoding="utf-8")
        (mcp_dir / "binary-abc.js").write_text('const bridgeDirectory = scriptPath.dirname(options.bridgeScriptPath);\nconst ghidraHeadlessArguments = [];\nexport const SUPPORTED_GHIDRA_VERSION = \'12.0\';\n', encoding="utf-8")
        (cli_dir / "KunaCommand-xyz.js").write_text('export const SUPPORTED_GHIDRA_VERSION = "12.2";\n', encoding="utf-8")

        with patch("harness.re.patcher.detect_installed_ghidra_version", return_value="12.3.1"), \
             patch("harness.re.patcher.is_ghidra_12_2_installed", return_value=True):
            res = apply_patch(rea_root)
            self.assertTrue(res["success"])
            chk = check_patch(rea_root)
            self.assertEqual(chk["status"], "applied")
            self.assertTrue(chk["policy_patched"])
            self.assertEqual(chk["target_ghidra_version"], "12.3.1")
            self.assertIn('SUPPORTED_GHIDRA_VERSION = "12.3.1"', (gh_dir / "GhidraReleasePolicy.js").read_text(encoding="utf-8"))
            self.assertIn("SUPPORTED_GHIDRA_VERSION = '12.3.1'", (mcp_dir / "binary-abc.js").read_text(encoding="utf-8"))
            self.assertIn('SUPPORTED_GHIDRA_VERSION = "12.3.1"', (cli_dir / "KunaCommand-xyz.js").read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
