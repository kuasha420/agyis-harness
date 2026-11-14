# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Arafat Zahan (@kuasha420)
# Corporate Stewardship & Infrastructure: Purrfect Software Limited (PSL)
# Governed by: ICARO-42/b Ordinance (Company-Supported Personal IP Framework)

"""
Unit tests for Agyis Cleanroom Reverse Engineering Toolsuite & REA Patcher (ADR-028, PSL-INV-009).
Verifies dirtyroom scaffolding, SQLite schemas, REA patcher lifecycle, and REA schema normalization.
"""

import json
import os
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import MagicMock, patch

from harness.hooks.command_safety_hook import (
    normalize_mcp_tool_call,
    normalize_rea_mcp_tool_call,
)
from harness.re.patcher import (
    LAUNCHER_SNIPPET,
    PATCH_SIGNATURE,
    apply_patch,
    check_patch,
    revert_patch,
)
from harness.re.scaffold import (
    get_dirtyroom_db,
    get_dirtyroom_root,
    init_dirtyroom_db,
    scaffold_dirtyroom,
)


class TestDirtyroomScaffolding(unittest.TestCase):
    """Verifies hermetic dirtyroom directory and SQLite schema generation."""

    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.workspace = Path(self.temp_dir.name)

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_scaffold_dirtyroom_creates_layout_and_db(self):
        res = scaffold_dirtyroom(self.workspace, project_name="TestProj")
        self.assertTrue(res["success"])
        self.assertTrue(res["db_created"])

        dirty_dir = self.workspace / ".dirtyroom"
        self.assertTrue(dirty_dir.is_dir())
        self.assertTrue((dirty_dir / "ghidra").is_dir())
        self.assertTrue((dirty_dir / "symbols").is_dir())
        self.assertTrue((dirty_dir / "logs").is_dir())
        self.assertTrue((dirty_dir / "pcaps").is_dir())

        db_path = dirty_dir / "symbols" / "dirtyroom.db"
        self.assertTrue(db_path.is_file())

        # Verify tables and indexes
        conn = sqlite3.connect(db_path)
        cur = conn.cursor()
        cur.execute("SELECT name FROM sqlite_master WHERE type='table'")
        tables = {row[0] for row in cur.fetchall()}
        self.assertIn("binaries", tables)
        self.assertIn("functions", tables)
        self.assertIn("strings", tables)
        self.assertIn("rtti_classes", tables)
        self.assertIn("packets", tables)
        self.assertIn("runs", tables)

        cur.execute("SELECT name FROM sqlite_master WHERE type='index'")
        indexes = {row[0] for row in cur.fetchall()}
        self.assertIn("idx_functions_name", indexes)
        self.assertIn("idx_strings_value", indexes)
        conn.close()

        # Verify non-dot symlink exists (DEF-BB-038)
        symlink_alias = self.workspace / "dirtyroom"
        self.assertTrue(symlink_alias.is_symlink() or symlink_alias.is_dir())
        self.assertEqual(symlink_alias.resolve(), dirty_dir.resolve())

        # Verify env file
        env_file = dirty_dir / "dirtyroom.env"
        self.assertTrue(env_file.is_file())
        env_text = env_file.read_text(encoding="utf-8")
        self.assertIn('REA_GHIDRA_PROJECT_NAME="TestProj"', env_text)
        self.assertIn("export AGYIS_DIRTYROOM=", env_text)

        # Verify get_dirtyroom_root resolution
        found_root = get_dirtyroom_root(self.workspace)
        self.assertEqual(found_root, dirty_dir)

        # Verify get_dirtyroom_db
        db_conn = get_dirtyroom_db(dirty_dir)
        self.assertIsNotNone(db_conn)
        db_conn.close()

    def test_preanalyze_binary_resolves_nondot_ghidra_dir(self):
        """Verifies preanalyze_binary uses non-dot symlink to satisfy Ghidra path invariants (DEF-BB-038)."""
        from harness.re.preanalyze import preanalyze_binary
        from unittest.mock import MagicMock

        bin_path = self.workspace / "test.bin"
        bin_path.write_bytes(b"\x90" * 64)
        scaffold_dirtyroom(self.workspace)

        mock_proc = MagicMock()
        mock_proc.returncode = 0

        with patch("harness.re.preanalyze.find_ghidra_headless", return_value=Path("/opt/ghidra/support/analyzeHeadless")), \
             patch("subprocess.run", return_value=mock_proc) as mock_run:
            res = preanalyze_binary(bin_path)
            self.assertTrue(res["success"])
            call_cmd = mock_run.call_args[0][0]
            project_dir_arg = call_cmd[1]
            parts = Path(project_dir_arg).parts
            self.assertFalse(any(p.startswith(".") for p in parts), f"Path components must not start with '.': {parts}")


class TestReaPatcherLifecycle(unittest.TestCase):
    """Verifies check_patch, apply_patch, and revert_patch against mock REA package."""

    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.mock_rea = Path(self.temp_dir.name) / "rea-agents"
        self.ghidra_dir = self.mock_rea / "dist" / "ghidra"
        self.mcp_dir = self.mock_rea / "dist" / "mcp"
        self.ghidra_dir.mkdir(parents=True, exist_ok=True)
        self.mcp_dir.mkdir(parents=True, exist_ok=True)

        # Create unpatched GhidraLauncher.js
        self.launcher = self.ghidra_dir / "GhidraLauncher.js"
        self.launcher.write_text(
            'import { mkdir } from "node:fs/promises";\n'
            'const ghidraHeadlessArguments = (options) => {\n'
            '    const scriptPath = win32;\n'
            '    const bridgeDirectory = scriptPath.dirname(options.bridgeScriptPath);\n'
            '    const override = options.languageOverride;\n'
            '};\n',
            encoding="utf-8",
        )

        # Create unpatched dist/mcp/binary-DR8ElrdQ.js
        self.mcp_binary = self.mcp_dir / "binary-test1234.js"
        self.mcp_binary.write_text(
            'import { statSync } from "node:fs";\n'
            'ghidraHeadlessArguments = (options) => {\n'
            '    const scriptPath = win32;\n'
            '    const bridgeDirectory = scriptPath.dirname(options.bridgeScriptPath);\n'
            '    return [];\n'
            '};\n',
            encoding="utf-8",
        )

        # Create unpatched GhidraReleasePolicy.js (DEF-BB-040)
        self.policy = self.ghidra_dir / "GhidraReleasePolicy.js"
        self.policy.write_text(
            'export const SUPPORTED_GHIDRA_VERSION = "12.1.4";\n'
            'export const SUPPORTED_GHIDRA_JAVA_MAJOR = 21;\n',
            encoding="utf-8",
        )

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_check_patch_detects_unpatched_state(self):
        res = check_patch(self.mock_rea)
        self.assertEqual(res["status"], "unapplied")
        self.assertFalse(res["launcher_patched"])
        self.assertFalse(res["mcp_patched"])

    def test_apply_and_revert_patch_roundtrip(self):
        with patch("harness.re.patcher.is_ghidra_12_2_installed", return_value=True):
            # 1. Apply patch
            apply_res = apply_patch(self.mock_rea)
            self.assertTrue(apply_res["success"])

            # Check patched files
            check_res = check_patch(self.mock_rea)
            self.assertEqual(check_res["status"], "applied")
            self.assertTrue(check_res["launcher_patched"])
            self.assertTrue(check_res["mcp_patched"])
            self.assertTrue(check_res["policy_patched"])

            l_content = self.launcher.read_text(encoding="utf-8")
            self.assertIn(PATCH_SIGNATURE, l_content)
            self.assertIn("-noanalysis", l_content)
            self.assertIn("-readOnly", l_content)

            p_content = self.policy.read_text(encoding="utf-8")
            self.assertIn('SUPPORTED_GHIDRA_VERSION = "12.2"', p_content)

            # Verify .orig backups exist
            self.assertTrue(self.launcher.with_suffix(".js.orig").is_file())
            self.assertTrue(self.mcp_binary.with_suffix(".js.orig").is_file())
            self.assertTrue(self.policy.with_suffix(".js.orig").is_file())

            # 2. Revert patch
            rev_res = revert_patch(self.mock_rea)
            self.assertTrue(rev_res["success"])

            check_after = check_patch(self.mock_rea)
            self.assertEqual(check_after["status"], "unapplied")
            self.assertFalse(self.launcher.with_suffix(".js.orig").exists())
            self.assertFalse(self.policy.with_suffix(".js.orig").exists())
            self.assertNotIn(PATCH_SIGNATURE, self.launcher.read_text(encoding="utf-8"))
            self.assertIn('SUPPORTED_GHIDRA_VERSION = "12.1.4"', self.policy.read_text(encoding="utf-8"))


class TestReaMcpSchemaNormalizerHook(unittest.TestCase):
    """Verifies PreToolUse REA schema normalizer and PSL-INV-009 gate in command_safety_hook."""

    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.workspace = Path(self.temp_dir.name)

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_normalize_pascal_case_arguments(self):
        tool_args = {
            "ServerName": "rea",
            "ToolName": "procedure_assembly",
            "Arguments": {
                "Address": "0x140001000",
                "Length": 64,
            },
        }
        dec, mod_args, reason = normalize_rea_mcp_tool_call("call_mcp_tool", tool_args)
        self.assertEqual(dec, "allow")
        self.assertIsNotNone(mod_args)
        self.assertEqual(mod_args["Arguments"]["procedure"], "0x140001000")
        self.assertEqual(mod_args["Arguments"]["length"], 64)
        self.assertNotIn("Address", mod_args["Arguments"])
        self.assertIn("normalized argument 'Address'", reason)

    def test_normalize_alias_arguments(self):
        tool_args = {
            "ServerName": "rea",
            "ToolName": "search_strings",
            "Arguments": {
                "file_path": "/path/to/binary",
                "query": "password",
            },
        }
        dec, mod_args, reason = normalize_rea_mcp_tool_call("call_mcp_tool", tool_args)
        self.assertEqual(dec, "allow")
        self.assertIsNotNone(mod_args)
        self.assertEqual(mod_args["Arguments"]["path"], "/path/to/binary")
        self.assertEqual(mod_args["Arguments"]["pattern"], "password")

    def test_psl_inv_009_large_binary_denial_without_cache(self):
        # Create a mock 15MB binary without Ghidra project
        large_bin = self.workspace / "LargeTarget.exe"
        with open(large_bin, "wb") as f:
            f.seek(15 * 1024 * 1024 - 1)
            f.write(b"\0")

        tool_args = {
            "ServerName": "rea",
            "ToolName": "open_binary",
            "Arguments": {
                "path": str(large_bin),
            },
        }
        dec, mod_args, reason = normalize_rea_mcp_tool_call("call_mcp_tool", tool_args)
        self.assertEqual(dec, "deny")
        self.assertIn("PSL-INV-009 VIOLATION", reason)
        self.assertIn("15.0 MB (>10 MB)", reason)

    def test_psl_inv_009_large_binary_allowed_with_cache(self):
        # Create mock 15MB binary with .dirtyroom/ghidra/Project.gpr
        dr = self.workspace / ".dirtyroom" / "ghidra"
        dr.mkdir(parents=True, exist_ok=True)
        (dr / "TargetProject.gpr").write_text("<project/>", encoding="utf-8")

        large_bin = self.workspace / "LargeTarget.exe"
        with open(large_bin, "wb") as f:
            f.seek(15 * 1024 * 1024 - 1)
            f.write(b"\0")

        tool_args = {
            "ServerName": "rea",
            "ToolName": "open_binary",
            "Arguments": {
                "path": str(large_bin),
            },
        }
        dec, mod_args, reason = normalize_rea_mcp_tool_call("call_mcp_tool", tool_args)
        self.assertEqual(dec, "allow")

    def test_psl_inv_009_external_large_binary_fallback_to_workspace_cache(self):
        """Verifies external binary outside workspace falls back to workspace dirtyroom cache (DEF-BB-023)."""
        dr = self.workspace / ".dirtyroom" / "ghidra"
        dr.mkdir(parents=True, exist_ok=True)
        (dr / "TargetProject.gpr").write_text("<project/>", encoding="utf-8")

        with tempfile.TemporaryDirectory() as external_dir:
            external_bin = Path(external_dir) / "ExternalTarget.bin"
            with open(external_bin, "wb") as f:
                f.seek(15 * 1024 * 1024 - 1)
                f.write(b"\0")

            tool_args = {
                "ServerName": "rea",
                "ToolName": "open_binary",
                "Arguments": {
                    "path": str(external_bin),
                },
            }
            with patch("os.getcwd", return_value=str(self.workspace)):
                dec, mod_args, reason = normalize_rea_mcp_tool_call("call_mcp_tool", tool_args)
                self.assertEqual(dec, "allow")

    def test_normalize_procedure_pseudo_code_aliases(self):
        """Verifies Address, addr, target, procedure_name, and proc map to procedure."""
        aliases = ["Address", "address", "addr", "procedure_name", "target", "proc"]
        for alias in aliases:
            tool_args = {
                "ServerName": "rea",
                "ToolName": "procedure_pseudo_code",
                "Arguments": {
                    alias: "0x140001000",
                },
            }
            dec, mod_args, reason = normalize_mcp_tool_call("call_mcp_tool", tool_args)
            self.assertEqual(dec, "allow")
            self.assertIsNotNone(mod_args)
            self.assertEqual(mod_args["Arguments"]["procedure"], "0x140001000")
            if alias != "procedure":
                self.assertNotIn(alias, mod_args["Arguments"])

    def test_normalize_read_bytes_aliases(self):
        """Verifies read_bytes normalizes Address/addr -> address and Length/size/count -> length."""
        tool_args = {
            "ServerName": "rea",
            "ToolName": "read_bytes",
            "Arguments": {
                "Address": "0x401000",
                "Length": 128,
            },
        }
        dec, mod_args, reason = normalize_mcp_tool_call("call_mcp_tool", tool_args)
        self.assertEqual(dec, "allow")
        self.assertEqual(mod_args["Arguments"]["address"], "0x401000")
        self.assertEqual(mod_args["Arguments"]["length"], 128)

        # Test size / count synonyms
        for size_alias in ["size", "count", "bytes", "len"]:
            tool_args = {
                "ServerName": "rea",
                "ToolName": "read_bytes",
                "Arguments": {
                    "addr": "0x401000",
                    size_alias: 32,
                },
            }
            dec, mod_args, reason = normalize_mcp_tool_call("call_mcp_tool", tool_args)
            self.assertEqual(dec, "allow")
            self.assertEqual(mod_args["Arguments"]["address"], "0x401000")
            self.assertEqual(mod_args["Arguments"]["length"], 32)
            self.assertNotIn(size_alias, mod_args["Arguments"])

    def test_normalize_context7_aliases_and_casing(self):
        """Verifies Context7 query-docs normalizes library_id variants and preserves query."""
        for lib_key in ["library_id", "LibraryId", "libraryID", "lib_id"]:
            tool_args = {
                "ServerName": "context7",
                "ToolName": "query-docs",
                "Arguments": {
                    lib_key: "/mongodb/docs",
                    "query": "authentication with jwt",
                },
            }
            dec, mod_args, reason = normalize_mcp_tool_call("call_mcp_tool", tool_args)
            self.assertEqual(dec, "allow")
            self.assertIsNotNone(mod_args)
            self.assertEqual(mod_args["Arguments"]["libraryId"], "/mongodb/docs")
            self.assertEqual(mod_args["Arguments"]["query"], "authentication with jwt")
            self.assertNotIn(lib_key, mod_args["Arguments"])

    def test_zero_degradation_valid_payloads(self):
        """Verifies that already-valid payloads are not mutated or degraded."""
        # 1. Perfectly valid payload: no overwrite produced
        tool_args = {
            "ServerName": "rea",
            "ToolName": "procedure_pseudo_code",
            "Arguments": {
                "procedure": "0x140001000",
                "document": "app.exe",
            },
        }
        dec, mod_args, reason = normalize_mcp_tool_call("call_mcp_tool", tool_args)
        self.assertEqual(dec, "allow")
        self.assertIsNone(mod_args)
        self.assertIsNone(reason)

        # 2. Both canonical key and alias provided: canonical takes precedence, alias dropped
        conflict_args = {
            "ServerName": "rea",
            "ToolName": "procedure_pseudo_code",
            "Arguments": {
                "procedure": "0x140001000",
                "Address": "0x999999999",
            },
        }
        dec, mod_args, reason = normalize_mcp_tool_call("call_mcp_tool", conflict_args)
        self.assertEqual(dec, "allow")
        self.assertIsNotNone(mod_args)
        self.assertEqual(mod_args["Arguments"]["procedure"], "0x140001000")
        self.assertNotIn("Address", mod_args["Arguments"])
        self.assertIn("removed redundant alias 'Address'", reason)

    def test_generic_mcp_server_schema_normalization(self):
        """Verifies schema-driven case-insensitive and snake-to-camel normalization for generic MCP server."""
        # Hermetically create a schema under temp_dir
        schema_dir = self.workspace / "schemas" / "custom_mcp"
        schema_dir.mkdir(parents=True, exist_ok=True)
        (schema_dir / "custom_tool.json").write_text(json.dumps({
            "name": "custom_tool",
            "parameters": {
                "type": "object",
                "properties": {
                    "apiKey": {"type": "string"},
                    "maxResults": {"type": "integer"},
                    "filterQuery": {"type": "string"},
                },
                "required": ["apiKey"]
            }
        }), encoding="utf-8")

        with patch.dict(os.environ, {"AGYIS_MCP_SCHEMAS_DIR": str(self.workspace / "schemas")}):
            tool_args = {
                "ServerName": "custom_mcp",
                "ToolName": "custom_tool",
                "Arguments": {
                    "api_key": "secret123",
                    "MaxResults": 50,
                    "filter_query": "status:active",
                },
            }
            dec, mod_args, reason = normalize_mcp_tool_call("call_mcp_tool", tool_args)
            self.assertEqual(dec, "allow")
            self.assertIsNotNone(mod_args)
            self.assertEqual(mod_args["Arguments"]["apiKey"], "secret123")
            self.assertEqual(mod_args["Arguments"]["maxResults"], 50)
            self.assertEqual(mod_args["Arguments"]["filterQuery"], "status:active")
            self.assertNotIn("api_key", mod_args["Arguments"])
            self.assertNotIn("MaxResults", mod_args["Arguments"])
            self.assertNotIn("filter_query", mod_args["Arguments"])


class TestCmdDecompilePSLINV009(unittest.TestCase):
    """Verifies PSL-INV-009 §1 pre-analyzed cache enforcement in cmd_decompile (DEF-BB-039)."""

    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.workspace = Path(self.temp_dir.name)

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_cmd_decompile_rejects_large_binary_without_gpr(self):
        from harness.commands.re import cmd_decompile
        import argparse
        import io

        large_bin = self.workspace / "LargeApp.exe"
        with open(large_bin, "wb") as f:
            f.seek(12 * 1024 * 1024 - 1)
            f.write(b"\0")

        args = argparse.Namespace(
            procedure="main",
            binary=str(large_bin),
        )
        err_buf = io.StringIO()
        with patch("shutil.which", return_value="/usr/local/bin/rea"), \
             patch("sys.stderr", err_buf), \
             patch("os.getcwd", return_value=str(self.workspace)):
            code = cmd_decompile(args)
            self.assertEqual(code, 1)
            err_msg = err_buf.getvalue()
            self.assertIn("PSL-INV-009 §1 Violation", err_msg)
            self.assertIn("exceeds 10MB (12.0MB)", err_msg)
            self.assertIn("Run 'agyis re preanalyze", err_msg)

    def test_cmd_decompile_allows_large_binary_with_gpr(self):
        from harness.commands.re import cmd_decompile
        import argparse
        import subprocess

        large_bin = self.workspace / "LargeApp.exe"
        with open(large_bin, "wb") as f:
            f.seek(12 * 1024 * 1024 - 1)
            f.write(b"\0")

        ghidra_dir = self.workspace / ".dirtyroom" / "ghidra"
        ghidra_dir.mkdir(parents=True, exist_ok=True)
        (ghidra_dir / "LargeApp.gpr").write_text("<project/>", encoding="utf-8")

        args = argparse.Namespace(
            procedure="main",
            binary=str(large_bin),
        )
        mock_proc = MagicMock()
        mock_proc.returncode = 0

        with patch("shutil.which", return_value="/usr/local/bin/rea"), \
             patch("subprocess.run", return_value=mock_proc) as mock_run, \
             patch("harness.commands.re.get_dirtyroom_root", return_value=self.workspace / ".dirtyroom"):
            code = cmd_decompile(args)
            self.assertEqual(code, 0)
            mock_run.assert_called_once()

    def test_cmd_decompile_timeout_expired_prints_sla_violation(self):
        """Verifies PSL-INV-009 §2 benchmark violation on decompilation timeout (DEF-REVIEW-002)."""
        from harness.commands.re import cmd_decompile
        import argparse
        import io
        import subprocess

        small_bin = self.workspace / "SmallApp.exe"
        small_bin.write_bytes(b"\x90" * 100)

        args = argparse.Namespace(
            procedure="main",
            binary=str(small_bin),
        )
        err_buf = io.StringIO()
        with patch("shutil.which", return_value="/usr/local/bin/rea"), \
             patch("subprocess.run", side_effect=subprocess.TimeoutExpired(cmd=["rea"], timeout=15.0)), \
             patch("sys.stderr", err_buf):
            code = cmd_decompile(args)
            self.assertEqual(code, 1)
            self.assertIn("PSL-INV-009 §2 Benchmark Violation", err_buf.getvalue())
            self.assertIn("exceeded 15s SLA", err_buf.getvalue())

    def test_preanalyze_alias_dispatches_correctly(self):
        """Verifies 'preanalyze' alias is recognized in re subcommand (DEF-REVIEW-001)."""
        from harness.commands.re import main as re_main
        with patch("harness.commands.re.cmd_preanalyze", return_value=0) as mock_cmd:
            code = re_main(["preanalyze", "/tmp/nonexistent.bin"])
            self.assertEqual(code, 0)
            mock_cmd.assert_called_once()


if __name__ == "__main__":
    unittest.main()

