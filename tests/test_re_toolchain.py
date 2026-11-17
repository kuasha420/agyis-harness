# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Arafat Zahan (@kuasha420)
# Corporate Stewardship & Infrastructure: Purrfect Software Limited (PSL)
# Governed by: ICARO-42/b Ordinance (Company-Supported Personal IP Framework)

"""
Unit tests for Agyis Cleanroom Reverse Engineering Toolsuite & REA Patcher (ADR-028, PSL-INV-009).
Verifies dirtyroom scaffolding, SQLite schemas, REA patcher lifecycle, and REA schema normalization.
"""

import argparse
import io
import json
import os
from pathlib import Path
import signal
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

    def test_cmd_decompile_query_cache_and_bypass(self):
        """Verifies decompiler query caching and --no-cache bypass flag."""
        from harness.commands.re import cmd_decompile
        import argparse
        import io

        small_bin = self.workspace / "CacheApp.exe"
        small_bin.write_bytes(b"\x90" * 100)

        dr = self.workspace / ".dirtyroom"
        (dr / "ghidra").mkdir(parents=True, exist_ok=True)
        (dr / "ghidra" / "CacheApp.gpr").write_text("<project/>", encoding="utf-8")

        mock_proc = MagicMock()
        mock_proc.returncode = 0
        mock_proc.stdout = "void target_func(void) { return; }\n"
        mock_proc.stderr = ""

        args = argparse.Namespace(
            procedure="target_func",
            binary=str(small_bin),
            no_cache=False,
            timeout=30.0,
        )

        out_buf = io.StringIO()
        with patch("shutil.which", return_value="/usr/local/bin/rea"), \
             patch("subprocess.run", return_value=mock_proc) as mock_run, \
             patch("sys.stdout", out_buf), \
             patch("harness.commands.re.get_dirtyroom_root", return_value=dr):
            code = cmd_decompile(args)
            self.assertEqual(code, 0)
            self.assertEqual(mock_run.call_count, 1)
            self.assertIn("void target_func", out_buf.getvalue())

            # Verify cache file was created on disk
            found_cache = list((dr / "cache" / "decompile").glob("CacheApp.exe_*target_func.c"))
            self.assertTrue(len(found_cache) > 0)
            cache_file = found_cache[0]
            self.assertTrue(cache_file.is_file())
            self.assertEqual(cache_file.read_text(encoding="utf-8"), mock_proc.stdout)

            # Second call: Should read from cache without calling subprocess.run
            out_buf2 = io.StringIO()
            with patch("sys.stdout", out_buf2):
                code2 = cmd_decompile(args)
                self.assertEqual(code2, 0)
                self.assertEqual(mock_run.call_count, 1)  # Still 1!
                self.assertIn("void target_func", out_buf2.getvalue())

            # Third call with no_cache=True: Should re-invoke subprocess.run and refresh cache file
            mock_proc.stdout = "void updated_target_func(void) { return; }\n"
            args_no_cache = argparse.Namespace(
                procedure="target_func",
                binary=str(small_bin),
                no_cache=True,
                timeout=30.0,
            )
            out_buf3 = io.StringIO()
            with patch("sys.stdout", out_buf3):
                code3 = cmd_decompile(args_no_cache)
                self.assertEqual(code3, 0)
                self.assertEqual(mock_run.call_count, 2)  # Re-invoked!
                self.assertIn("void updated_target_func", out_buf3.getvalue())

            # Verify on-disk cache file was refreshed with updated output
            self.assertEqual(cache_file.read_text(encoding="utf-8"), "void updated_target_func(void) { return; }\n")

    def test_inject_rea_dirtyroom_env_in_command_safety(self):
        """Verifies automated REA direct mount environment injection for raw shell commands."""
        from harness.hooks.command_safety_hook import inject_rea_dirtyroom_env

        dr = self.workspace / ".dirtyroom" / "ghidra"
        dr.mkdir(parents=True, exist_ok=True)
        (dr / "GameApp.gpr").write_text("<project/>", encoding="utf-8")

        raw_cmd = "rea decompile ShippingPC.exe --procedure 0x140001000"
        mod_cmd, changed, reasons = inject_rea_dirtyroom_env(raw_cmd, workspace_dir=self.workspace)
        self.assertTrue(changed)
        self.assertIn('REA_GHIDRA_DIRECT_MOUNT="1"', mod_cmd)
        self.assertIn('REA_GHIDRA_PROJECT_NAME=', mod_cmd)
        self.assertIn('GameApp', mod_cmd)
        self.assertIn('REA_GHIDRA_PROJECT_DIR=', mod_cmd)
        self.assertIn(str(dr), mod_cmd)
        self.assertTrue(mod_cmd.endswith(raw_cmd))

    def test_re_cache_stats_and_clear_lifecycle(self):
        """Verifies cache stats recording, hit rate calculation, and clear lifecycle."""
        from harness.re.cache import (
            clear_cache,
            cmd_cache,
            get_cache_dir,
            get_cache_stats,
            record_cache_hit,
            record_cache_miss,
        )

        dr = self.workspace / ".dirtyroom"
        cache_dir = get_cache_dir(dr, "decompile")
        cache_dir.mkdir(parents=True, exist_ok=True)

        # Create dummy cache files
        (cache_dir / "app_funcA.c").write_text("int funcA() { return 1; }\n", encoding="utf-8")
        (cache_dir / "app_funcB.c").write_text("int funcB() { return 2; }\n", encoding="utf-8")

        # Record metrics: 3 hits, 1 miss -> 75% hit rate
        record_cache_hit(dr, "decompile", key="app_funcA")
        record_cache_hit(dr, "decompile", key="app_funcA")
        record_cache_hit(dr, "decompile", key="app_funcB")
        record_cache_miss(dr, "decompile", key="app_funcC")

        stats = get_cache_stats(dr)
        self.assertEqual(stats["status"], "active")
        self.assertEqual(stats["entries"], 2)
        self.assertEqual(stats["hits"], 3)
        self.assertEqual(stats["misses"], 1)
        self.assertEqual(stats["total_queries"], 4)
        self.assertEqual(stats["hit_rate_pct"], 75.0)
        self.assertIn("decompile", stats["categories"])

        # Test CLI cmd_cache status
        args_status = argparse.Namespace(cache_action="status", json=True)
        out_buf = io.StringIO()
        with patch("sys.stdout", out_buf), patch("harness.re.cache.get_dirtyroom_root", return_value=dr):
            code = cmd_cache(args_status)
            self.assertEqual(code, 0)
            json_out = json.loads(out_buf.getvalue())
            self.assertEqual(json_out["hit_rate_pct"], 75.0)

        # Test dry-run clear
        res_dry = clear_cache(dr, category="all", dry_run=True)
        self.assertTrue(res_dry["dry_run"])
        self.assertEqual(res_dry["deleted_count"], 2)
        self.assertTrue((cache_dir / "app_funcA.c").is_file())

        # Test actual clear
        args_clear = argparse.Namespace(cache_action="clear", type="all", dry_run=False, json=True)
        out_buf2 = io.StringIO()
        with patch("sys.stdout", out_buf2), patch("harness.re.cache.get_dirtyroom_root", return_value=dr):
            code_clear = cmd_cache(args_clear)
            self.assertEqual(code_clear, 0)
            res_clear = json.loads(out_buf2.getvalue())
            self.assertEqual(res_clear["deleted_count"], 2)
            self.assertFalse((cache_dir / "app_funcA.c").exists())

        # Stats reset after all-clear
        stats_after = get_cache_stats(dr)
        self.assertEqual(stats_after["entries"], 0)
        self.assertEqual(stats_after["hits"], 0)

    def test_re_daemon_status_and_lifecycle(self):
        """Verifies REA bridge daemon status probing, start, and stop operations."""
        from harness.re.daemon import (
            cmd_daemon,
            get_daemon_status,
            get_pid_file,
            start_daemon,
            stop_daemon,
        )

        dr = self.workspace / ".dirtyroom"
        pid_file = get_pid_file(dr)

        # 1. Initially stopped
        with patch("harness.re.daemon.get_dirtyroom_root", return_value=dr):
            st = get_daemon_status(dr)
            self.assertFalse(st["running"])
            self.assertEqual(st["status"], "stopped")
            self.assertIsNone(st["pid"])

            # CLI status JSON
            args_status = argparse.Namespace(daemon_action="status", json=True)
            out_buf = io.StringIO()
            with patch("sys.stdout", out_buf):
                self.assertEqual(cmd_daemon(args_status), 0)
                out_data = json.loads(out_buf.getvalue())
                self.assertEqual(out_data["status"], "stopped")

            # 2. Test start_daemon (mocking Popen)
            mock_proc = MagicMock()
            mock_proc.pid = 99999

            def fake_popen(*p_args, **kwargs):
                pid_file.write_text("99999\n", encoding="utf-8")
                return mock_proc

            with patch("subprocess.Popen", side_effect=fake_popen), \
                 patch("shutil.which", return_value="/usr/local/bin/rea"), \
                 patch("harness.re.daemon.find_rea_binary", return_value=Path("/usr/local/bin/rea")), \
                 patch("harness.re.daemon._is_pid_alive", return_value=True), \
                 patch("harness.re.daemon.configure_rea_mcp_server"):
                res_start = start_daemon(dr, timeout=1.0)
                self.assertTrue(res_start["success"])
                self.assertEqual(res_start["pid"], 99999)

                # Check status now reports running
                st_running = get_daemon_status(dr)
                self.assertTrue(st_running["running"])
                self.assertEqual(st_running["pid"], 99999)

                # Start again -> already running
                res_again = start_daemon(dr)
                self.assertTrue(res_again["already_running"])

            # 3. Test stop_daemon
            with patch("harness.re.daemon._is_pid_alive", side_effect=[True, False]), \
                 patch("os.kill") as mock_kill:
                res_stop = stop_daemon(dr, timeout=1.0)
                self.assertTrue(res_stop["success"])
                self.assertTrue(res_stop["stopped"])
                mock_kill.assert_called_with(99999, signal.SIGTERM)
                self.assertFalse(pid_file.exists())

    def test_patcher_supports_async_function_syntax(self):
        """Verifies patcher handles standard async function syntax variants across rea releases."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            mock_root = Path(tmp_dir)
            ghidra_dir = mock_root / "dist" / "ghidra"
            ghidra_dir.mkdir(parents=True)
            mcp_dir = mock_root / "dist" / "mcp"
            mcp_dir.mkdir(parents=True)

            launcher = ghidra_dir / "GhidraLauncher.js"
            launcher.write_text(
                'import { statSync } from "node:fs";\n'
                'const bridgeDirectory = scriptPath.dirname(options.bridgeScriptPath);\n'
                'let targetBase = options.target;\n',
                encoding="utf-8",
            )

            # Alternate ES syntax: async function instead of arrow function
            snapshot = ghidra_dir / "GhidraProjectSnapshot.js"
            snapshot.write_text(
                'async function fingerprintGhidraProject(root, name, resources, signal) {\n'
                '    return "original-fingerprint";\n'
                '}\n'
                'async function copyExistingGhidraProject(sourcePath, dest, options = {}) {\n'
                '    return originalCopy();\n'
                '}\n',
                encoding="utf-8",
            )

            mcp_bin = mcp_dir / "binary-12345.js"
            mcp_bin.write_text(
                'import { statSync } from "node:fs";\n'
                'const bridgeDirectory = scriptPath.dirname(options.bridgeScriptPath);\n'
                'const ghidraHeadlessArguments = [];\n'
                'async function fingerprintGhidraProject(root, name, resources, signal) {\n'
                '    return "mcp-fingerprint";\n'
                '}\n'
                'async function copyExistingGhidraProject(sourcePath, dest, options = {}) {\n'
                '    return mcpCopy();\n'
                '}\n',
                encoding="utf-8",
            )

            res = apply_patch(mock_root)
            self.assertTrue(res["success"], res.get("error"))

            # Verify direct mount fastpath was injected
            snap_txt = snapshot.read_text(encoding="utf-8")
            self.assertIn("REA_DIRECT_MOUNT_ACTIVE", snap_txt)
            self.assertIn("0000000000000000000000000000000000000000000000000000000000000000", snap_txt)

            status = check_patch(mock_root)
            self.assertTrue(status["direct_mount_active"])
            self.assertEqual(status["status"], "applied")


if __name__ == "__main__":
    unittest.main()

