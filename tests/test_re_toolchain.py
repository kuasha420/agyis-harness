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
import socket
import sqlite3
import struct
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
        self.assertTrue((dirty_dir / "cache" / "decompile").is_dir())

        gi_file = dirty_dir / ".gitignore"
        self.assertTrue(gi_file.is_file())
        self.assertIn("cache/", gi_file.read_text(encoding="utf-8"))

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
        self.assertIn('export REA_GHIDRA_DIRECT_MOUNT="1"', env_text)

        # Verify get_dirtyroom_root resolution
        found_root = get_dirtyroom_root(self.workspace)
        self.assertEqual(found_root, dirty_dir)

        # Verify get_dirtyroom_db
        db_conn = get_dirtyroom_db(dirty_dir)
        self.assertIsNotNone(db_conn)
        db_conn.close()

    def test_scaffold_dirtyroom_appends_cache_quarantine_to_root_gitignore(self):
        """Verifies root .gitignore receives .dirtyroom/cache/ quarantine entry (DEFECT-S3-002)."""
        root_gi = self.workspace / ".gitignore"
        root_gi.write_text("*.pyc\n", encoding="utf-8")

        res = scaffold_dirtyroom(self.workspace, project_name="GitIgnoreProj")
        self.assertTrue(res["success"])
        self.assertTrue(res["root_gitignore_updated"])

        gi_text = root_gi.read_text(encoding="utf-8")
        self.assertIn(".dirtyroom/ghidra/*.rep/", gi_text)
        self.assertIn(".dirtyroom/logs/", gi_text)
        self.assertIn(".dirtyroom/cache/", gi_text)

    def test_scaffold_dirtyroom_upgrades_existing_gitignore_idempotently(self):
        """Verifies re-running scaffold_dirtyroom upgrades legacy .gitignore files with cache quarantine."""
        root_gi = self.workspace / ".gitignore"
        root_gi.write_text("*.pyc\n.dirtyroom/ghidra/*.rep/\n.dirtyroom/logs/\n", encoding="utf-8")
        dirty_dir = self.workspace / ".dirtyroom"
        dirty_dir.mkdir(parents=True, exist_ok=True)
        local_gi = dirty_dir / ".gitignore"
        local_gi.write_text("ghidra/*.rep/\nlogs/*.log\n", encoding="utf-8")

        res1 = scaffold_dirtyroom(self.workspace, project_name="UpgradeProj")
        self.assertTrue(res1["success"])
        self.assertTrue(res1["root_gitignore_updated"])
        self.assertIn("cache/", local_gi.read_text(encoding="utf-8").splitlines())
        root_lines = root_gi.read_text(encoding="utf-8").splitlines()
        self.assertIn(".dirtyroom/cache/", root_lines)
        self.assertEqual(root_lines.count(".dirtyroom/logs/"), 1)

        # Second run must be strictly idempotent
        res2 = scaffold_dirtyroom(self.workspace, project_name="UpgradeProj")
        self.assertTrue(res2["success"])
        self.assertFalse(res2["root_gitignore_updated"])

        # Whole-directory .dirtyroom/ ignore must not be modified
        ws_whole = self.workspace / "whole_ignore"
        ws_whole.mkdir()
        (ws_whole / ".gitignore").write_text(".dirtyroom/\n", encoding="utf-8")
        res3 = scaffold_dirtyroom(ws_whole, project_name="WholeProj")
        self.assertTrue(res3["success"])
        self.assertFalse(res3["root_gitignore_updated"])
        self.assertEqual((ws_whole / ".gitignore").read_text(encoding="utf-8"), ".dirtyroom/\n")

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


def _make_synthetic_pcap(packets_spec: list) -> bytes:
    """Generates a valid minimal libpcap binary stream for hermetic testing."""
    hdr = struct.pack("<IHHiIII", 0xA1B2C3D4, 2, 4, 0, 0, 65535, 1)
    buf = bytearray(hdr)
    for ts_sec, ts_usec, proto_num, src_ip, dst_ip, s_port, d_port, payload in packets_spec:
        src_bytes = socket.inet_aton(src_ip)
        dst_bytes = socket.inet_aton(dst_ip)
        l4 = struct.pack(">HH", s_port, d_port) + b"\x00\x00\x00\x00"
        ip_payload = l4 + payload
        total_len = 20 + len(ip_payload)
        ip_hdr = struct.pack("!BBHHHBBH4s4s", 0x45, 0, total_len, 1234, 0, 64, proto_num, 0, src_bytes, dst_bytes)
        eth = b"\x00" * 12 + struct.pack(">H", 0x0800)
        frame = eth + ip_hdr + ip_payload
        pkt_hdr = struct.pack("<IIII", ts_sec, ts_usec, len(frame), len(frame))
        buf.extend(pkt_hdr)
        buf.extend(frame)
    return bytes(buf)


class TestDirtyroomSeeding(unittest.TestCase):
    """Verifies PCAP parsing, schema extensions, frame ingestion, and run linking."""

    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.workspace = Path(self.temp_dir.name)
        scaffold_dirtyroom(self.workspace, project_name="SeedTest")
        self.dr = self.workspace / ".dirtyroom"

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_parse_pcap_packets_python(self):
        """Verifies pure-Python libpcap frame parsing across IPv4 TCP and UDP protocols."""
        from harness.re.seeding import parse_pcap_packets_python

        specs = [
            (1700000000, 500000, 6, "192.168.1.10", "192.168.1.20", 8080, 80, b"GET / HTTP/1.1\r\n"),
            (1700000001, 250000, 17, "10.0.0.1", "10.0.0.2", 5000, 5001, b"\x01\x02\x03\x04"),
        ]
        pcap_data = _make_synthetic_pcap(specs)
        pcap_file = self.dr / "pcaps" / "synthetic.pcap"
        pcap_file.write_bytes(pcap_data)

        packets = parse_pcap_packets_python(pcap_file)
        self.assertEqual(len(packets), 2)

        # Validate packet 1 (TCP)
        p1 = packets[0]
        self.assertEqual(p1["frame_number"], 1)
        self.assertEqual(p1["proto"], "TCP")
        self.assertEqual(p1["src_ip"], "192.168.1.10")
        self.assertEqual(p1["dst_ip"], "192.168.1.20")
        self.assertEqual(p1["src_port"], 8080)
        self.assertEqual(p1["dst_port"], 80)
        self.assertIn("192.168.1.10:8080 -> 192.168.1.20:80", p1["summary"])

        # Validate packet 2 (UDP)
        p2 = packets[1]
        self.assertEqual(p2["frame_number"], 2)
        self.assertEqual(p2["proto"], "UDP")
        self.assertEqual(p2["src_ip"], "10.0.0.1")
        self.assertEqual(p2["dst_ip"], "10.0.0.2")
        self.assertEqual(p2["src_port"], 5000)
        self.assertEqual(p2["dst_port"], 5001)

    def test_seed_packets_ingests_and_links_runs(self):
        """Verifies seed_packets inserts frames into packets table and establishes binary run links."""
        from harness.re.seeding import seed_packets

        specs = [
            (1700000000, 100000, 6, "192.168.1.5", "192.168.1.1", 443, 50000, b"TLS_HELLO"),
            (1700000001, 200000, 6, "192.168.1.1", "192.168.1.5", 50000, 443, b"TLS_ACK"),
        ]
        pcap_file = self.dr / "pcaps" / "session.pcap"
        pcap_file.write_bytes(_make_synthetic_pcap(specs))

        dummy_bin = self.dr / "binaries" / "ShippingPC-ChaosGame.exe"
        dummy_bin.parent.mkdir(parents=True, exist_ok=True)
        dummy_bin.write_bytes(b"\x90" * 256)

        res = seed_packets(
            pcap_path=pcap_file,
            binary_name="ShippingPC-ChaosGame.exe",
            dirtyroom_root=self.dr,
        )
        self.assertTrue(res["success"], res.get("error"))
        self.assertEqual(res["packets_ingested"], 2)
        self.assertEqual(res["binary_name"], "ShippingPC-ChaosGame.exe")
        self.assertIsNotNone(res["binary_id"])
        self.assertIsNotNone(res["run_id"])

        # Verify DB content
        db_path = self.dr / "symbols" / "dirtyroom.db"
        conn = sqlite3.connect(db_path)
        cur = conn.cursor()

        # Check binaries table
        cur.execute("SELECT id, name, file_size FROM binaries WHERE name = ?", ("ShippingPC-ChaosGame.exe",))
        bin_row = cur.fetchone()
        self.assertIsNotNone(bin_row)
        self.assertEqual(bin_row[1], "ShippingPC-ChaosGame.exe")
        self.assertEqual(bin_row[2], 256)

        # Check runs table
        cur.execute("SELECT id, command, binary_id, exit_code FROM runs WHERE id = ?", (res["run_id"],))
        run_row = cur.fetchone()
        self.assertIsNotNone(run_row)
        self.assertIn("seed", run_row[1])
        self.assertEqual(run_row[2], res["binary_id"])
        self.assertEqual(run_row[3], 0)

        # Check packets table
        cur.execute("SELECT count(*), min(frame_number), max(frame_number), binary_id, run_id FROM packets")
        pkt_row = cur.fetchone()
        self.assertEqual(pkt_row[0], 2)
        self.assertEqual(pkt_row[1], 1)
        self.assertEqual(pkt_row[2], 2)
        self.assertEqual(pkt_row[3], res["binary_id"])
        self.assertEqual(pkt_row[4], res["run_id"])
        conn.close()

    def test_seed_packets_auto_discovery_and_limit(self):
        """Verifies auto-discovery of PCAPs in dirtyroom and enforcement of frame limit."""
        from harness.re.seeding import seed_packets

        specs = [(1700000000 + i, 0, 17, "10.0.0.1", "10.0.0.2", 1000 + i, 2000, b"DATA") for i in range(5)]
        pcap_file = self.dr / "pcaps" / "auto_session.pcap"
        pcap_file.write_bytes(_make_synthetic_pcap(specs))

        res = seed_packets(limit=3, dirtyroom_root=self.dr)
        self.assertTrue(res["success"], res.get("error"))
        self.assertEqual(res["packets_ingested"], 3)

    def test_cmd_seed_cli_dispatch(self):
        """Verifies CLI dispatch for 'agyis re seed --json'."""
        from harness.re.seeding import cmd_seed

        specs = [(1700000000, 0, 17, "1.1.1.1", "2.2.2.2", 53, 53, b"DNS")]
        pcap_file = self.dr / "pcaps" / "cli.pcap"
        pcap_file.write_bytes(_make_synthetic_pcap(specs))

        args = argparse.Namespace(pcap=str(pcap_file), binary=None, limit=None, json=True)
        out_buf = io.StringIO()
        with patch("harness.re.seeding.get_dirtyroom_root", return_value=self.dr), \
             patch("sys.stdout", out_buf):
            ret = cmd_seed(args)
            self.assertEqual(ret, 0)
            data = json.loads(out_buf.getvalue())
            self.assertTrue(data["success"])
            self.assertEqual(data["packets_ingested"], 1)

    def test_seed_packets_corrupted_or_empty_pcap(self):
        """Verifies seed_packets handles 0-byte and truncated pcap files gracefully."""
        from harness.re.seeding import parse_pcap_packets_python, seed_packets

        empty_pcap = self.dr / "pcaps" / "empty.pcap"
        empty_pcap.write_bytes(b"")
        self.assertEqual(parse_pcap_packets_python(empty_pcap), [])

        trunc_pcap = self.dr / "pcaps" / "trunc.pcap"
        trunc_pcap.write_bytes(b"\xd4\xc3\xb2")
        self.assertEqual(parse_pcap_packets_python(trunc_pcap), [])

        res = seed_packets(pcap_path=empty_pcap, dirtyroom_root=self.dr)
        self.assertFalse(res["success"])
        self.assertIn("Failed to extract frames", res.get("error", ""))

    def test_seed_packets_missing_pcap(self):
        """Verifies seed_packets returns descriptive error when no PCAP file is found."""
        from harness.re.seeding import seed_packets

        # Remove all pcaps
        for p in (self.dr / "pcaps").glob("*"):
            p.unlink()

        res = seed_packets(pcap_path=self.dr / "pcaps" / "nonexistent.pcap", dirtyroom_root=self.dr)
        self.assertFalse(res["success"])
        self.assertIn("No valid PCAP file found", res.get("error", ""))

    def test_parse_pcap_non_ipv4_frames(self):
        """Verifies handling of ARP and non-standard link frames."""
        from harness.re.seeding import parse_pcap_packets_python

        hdr = struct.pack("<IHHiIII", 0xA1B2C3D4, 2, 4, 0, 0, 65535, 1)
        buf = bytearray(hdr)
        # ARP frame: EtherType 0x0806
        arp_frame = b"\xff" * 6 + b"\x00" * 6 + struct.pack(">H", 0x0806) + b"\x00" * 28
        pkt_hdr = struct.pack("<IIII", 1700000000, 0, len(arp_frame), len(arp_frame))
        buf.extend(pkt_hdr)
        buf.extend(arp_frame)

        pcap_file = self.dr / "pcaps" / "arp.pcap"
        pcap_file.write_bytes(bytes(buf))

        pkts = parse_pcap_packets_python(pcap_file)
        self.assertEqual(len(pkts), 1)
        self.assertEqual(pkts[0]["proto"], "ARP")
        self.assertIn("ARP", pkts[0]["summary"])

    def test_parse_pcap_linux_sll_cooked_capture(self):
        """Verifies pure-Python decoding of Linux cooked capture (LinkType 113 / SLL)."""
        from harness.re.seeding import parse_pcap_packets_python

        # DLT_LINUX_SLL header
        hdr = struct.pack("<IHHiIII", 0xA1B2C3D4, 2, 4, 0, 0, 65535, 113)
        # SLL 16-byte header: packet_type(2), arphrd(2), addr_len(2), addr(8), proto(2=0x0800 IPv4)
        sll = struct.pack(">HHHQH", 0, 1, 6, 0, 0x0800)
        # IPv4 20-byte + UDP 8-byte + 4-byte payload
        ip = b"\x45\x00\x00\x20\x00\x01\x00\x00\x40\x11\x00\x00\x0a\x00\x00\x01\x0a\x00\x00\x02"
        udp = struct.pack(">HHHH", 9999, 8888, 12, 0) + b"TEST"
        pkt_data = sll + ip + udp
        rec_hdr = struct.pack("<IIII", 1700000000, 500000, len(pkt_data), len(pkt_data))

        pcap_file = self.dr / "pcaps" / "sll.pcap"
        pcap_file.write_bytes(hdr + rec_hdr + pkt_data)

        pkts = parse_pcap_packets_python(pcap_file)
        self.assertEqual(len(pkts), 1)
        self.assertEqual(pkts[0]["proto"], "UDP")
        self.assertEqual(pkts[0]["src_ip"], "10.0.0.1")
        self.assertEqual(pkts[0]["dst_ip"], "10.0.0.2")
        self.assertEqual(pkts[0]["src_port"], 9999)
        self.assertEqual(pkts[0]["dst_port"], 8888)
        self.assertIn("10.0.0.1:9999 -> 10.0.0.2:8888", pkts[0]["summary"])

    def test_parse_pcap_ipv6_frames(self):
        """Verifies pure-Python decoding of IPv6 TCP packets."""
        from harness.re.seeding import parse_pcap_packets_python

        hdr = struct.pack("<IHHiIII", 0xA1B2C3D4, 2, 4, 0, 0, 65535, 1)
        eth = b"\x00" * 12 + struct.pack(">H", 0x86DD)  # IPv6
        # IPv6 header (40 bytes): ver(6), next_hdr(6=TCP), src (2001:db8::1), dst (2001:db8::2)
        src_bytes = socket.inet_pton(socket.AF_INET6, "2001:db8::1")
        dst_bytes = socket.inet_pton(socket.AF_INET6, "2001:db8::2")
        ip6_hdr = b"\x60\x00\x00\x00\x00\x18\x06\x40" + src_bytes + dst_bytes
        tcp_hdr = struct.pack(">HHIIHHHH", 443, 54321, 1, 0, 0x5000, 0, 0, 0)
        pkt_data = eth + ip6_hdr + tcp_hdr
        rec_hdr = struct.pack("<IIII", 1700000000, 0, len(pkt_data), len(pkt_data))

        pcap_file = self.dr / "pcaps" / "ipv6.pcap"
        pcap_file.write_bytes(hdr + rec_hdr + pkt_data)

        pkts = parse_pcap_packets_python(pcap_file)
        self.assertEqual(len(pkts), 1)
        self.assertEqual(pkts[0]["proto"], "TCP")
        self.assertEqual(pkts[0]["src_ip"], "2001:db8::1")
        self.assertEqual(pkts[0]["dst_ip"], "2001:db8::2")
        self.assertEqual(pkts[0]["src_port"], 443)
        self.assertEqual(pkts[0]["dst_port"], 54321)

    def test_seed_packets_failed_extraction_marks_run_failed(self):
        """Verifies failed packet ingestion sets run exit_code to 1 with finished_at timestamp."""
        from harness.re.seeding import seed_packets

        empty_pcap = self.dr / "pcaps" / "corrupt.pcap"
        empty_pcap.write_bytes(b"")

        res = seed_packets(pcap_path=empty_pcap, dirtyroom_root=self.dr)
        self.assertFalse(res["success"])
        run_id = res.get("run_id")
        self.assertIsNotNone(run_id)

        # Inspect runs table in SQLite
        db_path = self.dr / "symbols" / "dirtyroom.db"
        conn = sqlite3.connect(db_path)
        cur = conn.cursor()
        cur.execute("SELECT exit_code, finished_at FROM runs WHERE id = ?", (run_id,))
        row = cur.fetchone()
        self.assertIsNotNone(row)
        self.assertEqual(row[0], 1)
        self.assertIsNotNone(row[1])
        conn.close()

    def test_parse_pcap_packets_tshark_timeout_and_error_handling(self):
        """Verifies parse_pcap_packets_tshark passes timeout=30.0 and handles TimeoutExpired cleanly."""
        import subprocess
        from harness.re.seeding import parse_pcap_packets_tshark

        pcap_file = self.dr / "pcaps" / "dummy.pcapng"
        pcap_file.write_bytes(b"\x0a\x0d\x0d\x0a")

        with patch("shutil.which", return_value="/usr/bin/tshark"), \
             patch("subprocess.run", side_effect=subprocess.TimeoutExpired(cmd=["tshark"], timeout=30.0)) as mock_run:
            pkts = parse_pcap_packets_tshark(pcap_file)
            self.assertEqual(pkts, [])
            self.assertEqual(mock_run.call_args.kwargs.get("timeout"), 30.0)

    def test_seed_packets_computes_streaming_binary_sha256(self):
        """Verifies seed_packets hashes binaries via streaming hashlib.file_digest."""
        import hashlib
        from harness.re.seeding import seed_packets

        specs = [(1700000000, 0, 6, "10.0.0.1", "10.0.0.2", 1234, 80, b"HI")]
        pcap_file = self.dr / "pcaps" / "hash_test.pcap"
        pcap_file.write_bytes(_make_synthetic_pcap(specs))

        payload = b"\xde\xad\xbe\xef" * 1024
        dummy_bin = self.dr / "binaries" / "HashTarget.exe"
        dummy_bin.parent.mkdir(parents=True, exist_ok=True)
        dummy_bin.write_bytes(payload)
        expected_sha = hashlib.sha256(payload).hexdigest()

        res = seed_packets(pcap_path=pcap_file, binary_name="HashTarget.exe", dirtyroom_root=self.dr)
        self.assertTrue(res["success"], res.get("error"))

        db_path = self.dr / "symbols" / "dirtyroom.db"
        conn = sqlite3.connect(db_path)
        try:
            row = conn.execute("SELECT sha256 FROM binaries WHERE name = ?", ("HashTarget.exe",)).fetchone()
            self.assertIsNotNone(row)
            self.assertEqual(row[0], expected_sha)
        finally:
            conn.close()

    def test_seed_packets_corrupted_db_invalid_limit_and_tshark_blank_lines(self):
        """Verifies clean error handling on corrupted DB, invalid limits, pcap dir skip, and tshark blank lines."""
        from harness.re.seeding import parse_pcap_packets_tshark, seed_packets

        # 1. Corrupted DB returns structured error instead of crashing
        corrupt_dr = self.workspace / "corrupt_seed_dr"
        (corrupt_dr / "symbols").mkdir(parents=True, exist_ok=True)
        (corrupt_dr / "symbols" / "dirtyroom.db").write_bytes(b"CORRUPT_HEADER_DATA")
        res_corrupt = seed_packets(dirtyroom_root=corrupt_dr)
        self.assertFalse(res_corrupt["success"])
        self.assertIn("Database error seeding packets:", res_corrupt.get("error", ""))

        # 2. Non-positive limit rejected cleanly
        self.assertFalse(seed_packets(limit=0, dirtyroom_root=self.dr)["success"])
        self.assertFalse(seed_packets(limit=-3, dirtyroom_root=self.dr)["success"])

        # 3. Auto-discovery ignores directories matching *.pcap*
        (self.dr / "pcaps" / "not_a_file.pcap.d").mkdir(parents=True, exist_ok=True)
        res_dir = seed_packets(dirtyroom_root=self.dr)
        self.assertFalse(res_dir["success"])
        self.assertIn("No valid PCAP file found", res_dir.get("error", ""))

        # 4. tshark parser skips empty/whitespace lines
        mock_proc = MagicMock()
        mock_proc.returncode = 0
        mock_proc.stdout = "1\t1700000000.5\tTCP\t1.2.3.4\t\t5.6.7.8\t\t1234\t\t80\t\t60\tSYN\n\n   \n"
        with patch("shutil.which", return_value="/usr/bin/tshark"), \
             patch("subprocess.run", return_value=mock_proc):
            pkts = parse_pcap_packets_tshark(self.dr / "pcaps" / "any.pcapng")
            self.assertEqual(len(pkts), 1)
            self.assertEqual(pkts[0]["proto"], "TCP")


class TestDirtyroomPriming(unittest.TestCase):
    """Verifies decompiler query cache pre-warming and priority function selection."""

    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.workspace = Path(self.temp_dir.name)
        scaffold_dirtyroom(self.workspace, project_name="PrimeTest")
        self.dr = self.workspace / ".dirtyroom"

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_get_priority_functions_sorting(self):
        """Verifies priority functions prioritize exported status and subroutine size."""
        from harness.re.priming import get_priority_functions

        db_path = self.dr / "symbols" / "dirtyroom.db"
        conn = sqlite3.connect(db_path)
        cur = conn.cursor()
        cur.execute("INSERT INTO binaries (name, sha256, file_size, created_at) VALUES ('app.exe', 'abc', 1000, 'now')")
        bin_id = cur.lastrowid

        cur.execute("INSERT INTO functions (binary_id, name, address, size, is_exported, created_at) VALUES (?, 'sub_small', '0x1000', 50, 0, 'now')", (bin_id,))
        cur.execute("INSERT INTO functions (binary_id, name, address, size, is_exported, created_at) VALUES (?, 'sub_large', '0x2000', 500, 0, 'now')", (bin_id,))
        cur.execute("INSERT INTO functions (binary_id, name, address, size, is_exported, created_at) VALUES (?, 'exp_mid', '0x3000', 100, 1, 'now')", (bin_id,))
        conn.commit()

        funcs = get_priority_functions(conn, binary_id=bin_id, limit=2)
        # Exported function comes first, then largest unexported function
        self.assertEqual(funcs, ["exp_mid", "sub_large"])
        conn.close()

    def test_prime_cache_with_symbols_file_dry_run(self):
        """Verifies symbols file parsing and dry-run preview mode."""
        from harness.re.priming import prime_cache

        sym_file = self.workspace / "priority_syms.txt"
        sym_file.write_text("FuncAlpha\nFuncBeta\n# comment line\nFuncGamma\n", encoding="utf-8")

        res = prime_cache(symbols_file=sym_file, dry_run=True, dirtyroom_root=self.dr)
        self.assertTrue(res["success"], res.get("error"))
        self.assertEqual(res["candidates"], 3)
        self.assertEqual(res["already_cached"], 0)
        self.assertTrue(res["dry_run"])
        results = res["results"]
        self.assertEqual(len(results), 3)
        self.assertTrue(all(r["status"] == "would_prime" for r in results))

    def test_prime_cache_execution_and_caching(self):
        """Verifies decompiler caching mechanics, skipping existing cache entries."""
        from harness.re.priming import compute_cache_key, prime_cache

        cache_dir = self.dr / "cache" / "decompile"
        cache_dir.mkdir(parents=True, exist_ok=True)

        # Pre-cache FuncOne
        key_one = compute_cache_key(None, "target", "FuncOne")
        (cache_dir / f"{key_one}.c").write_text("void FuncOne() { return; }\n", encoding="utf-8")

        sym_file = self.workspace / "syms.txt"
        sym_file.write_text("FuncOne\nFuncTwo\n", encoding="utf-8")

        mock_proc = MagicMock()
        mock_proc.returncode = 0
        mock_proc.stdout = "void FuncTwo() { int x = 42; }\n"
        mock_proc.stderr = ""

        with patch("shutil.which", return_value="/usr/local/bin/rea"), \
             patch("subprocess.run", return_value=mock_proc):
            res = prime_cache(symbols_file=sym_file, dry_run=False, dirtyroom_root=self.dr)
            self.assertTrue(res["success"], res.get("error"))
            self.assertEqual(res["candidates"], 2)
            self.assertEqual(res["already_cached"], 1)
            self.assertEqual(res["primed"], 1)
            self.assertEqual(res["failed"], 0)

            # Assert FuncTwo cache file exists
            key_two = compute_cache_key(None, "target", "FuncTwo")
            cached_two = cache_dir / f"{key_two}.c"
            self.assertTrue(cached_two.is_file())
            self.assertIn("int x = 42", cached_two.read_text(encoding="utf-8"))

    def test_cmd_prime_cli_dispatch(self):
        """Verifies CLI dispatch for 'agyis re prime --dry-run --json'."""
        from harness.re.priming import cmd_prime

        sym_file = self.workspace / "cli_syms.txt"
        sym_file.write_text("TargetProc\n", encoding="utf-8")

        args = argparse.Namespace(top=20, file=str(sym_file), binary=None, timeout=30.0, dry_run=True, json=True)
        out_buf = io.StringIO()
        with patch("harness.re.priming.get_dirtyroom_root", return_value=self.dr), \
             patch("sys.stdout", out_buf):
            ret = cmd_prime(args)
            self.assertEqual(ret, 0)
            data = json.loads(out_buf.getvalue())
            self.assertTrue(data["success"])
            self.assertEqual(data["candidates"], 1)

    def test_prime_cache_missing_symbols_file(self):
        """Verifies prime_cache returns error when specified symbols file does not exist."""
        from harness.re.priming import prime_cache

        res = prime_cache(symbols_file=self.workspace / "missing.txt", dirtyroom_root=self.dr)
        self.assertFalse(res["success"])
        self.assertIn("Symbols file not found", res.get("error", ""))

    def test_prime_cache_no_candidates_returns_informative_status(self):
        """Verifies prime_cache returns clean error when 0 priority functions exist in DB."""
        from harness.re.priming import prime_cache

        res = prime_cache(top=10, dirtyroom_root=self.dr)
        self.assertFalse(res["success"])
        self.assertEqual(res["candidates"], 0)
        self.assertIn("No priority functions found", res.get("error", ""))

    def test_prime_cache_unknown_binary_returns_error(self):
        """Verifies prime_cache returns clean error if explicitly specified binary does not exist in DB."""
        from harness.re.priming import prime_cache

        db_path = self.dr / "symbols" / "dirtyroom.db"
        conn = sqlite3.connect(db_path)
        cur = conn.cursor()
        cur.execute("INSERT INTO binaries (name, sha256, file_size, created_at) VALUES ('other_app.exe', 'abc', 1000, 'now')")
        cur.execute("INSERT INTO functions (binary_id, name, address, size, is_exported, created_at) VALUES (1, 'fnOther', '0x1000', 50, 1, 'now')")
        conn.commit()
        conn.close()

        res = prime_cache(binary_name="missing_app.exe", dirtyroom_root=self.dr)
        self.assertFalse(res["success"])
        self.assertEqual(res["candidates"], 0)
        self.assertIn("not found in dirtyroom database", res.get("error", ""))

    def test_prime_cache_default_binary_resolution(self):
        """Verifies prime_cache resolves primary executable binary when binary_name is omitted."""
        from harness.re.priming import prime_cache

        db_path = self.dr / "symbols" / "dirtyroom.db"
        conn = sqlite3.connect(db_path)
        cur = conn.cursor()
        cur.execute("INSERT INTO binaries (name, sha256, file_size, created_at) VALUES ('libhelper.dll', '111', 1000, 'now')")
        cur.execute("INSERT INTO binaries (name, sha256, file_size, created_at) VALUES ('MainApp.exe', '222', 2000, 'now')")
        cur.execute("INSERT INTO functions (binary_id, name, address, size, is_exported, created_at) VALUES (2, 'fnMain', '0x1000', 50, 1, 'now')")
        conn.commit()
        conn.close()

        res = prime_cache(dry_run=True, dirtyroom_root=self.dr)
        self.assertTrue(res["success"])
        self.assertEqual(res["binary"], "MainApp.exe")
        self.assertEqual(res["candidates"], 1)

    def test_prime_cache_does_not_pollute_cache_stats(self):
        """Verifies prime_cache does not artificially record query cache hits or misses."""
        from harness.re.cache import get_cache_stats
        from harness.re.priming import prime_cache

        sym_file = self.workspace / "stats_syms.txt"
        sym_file.write_text("FuncX\n", encoding="utf-8")

        mock_proc = MagicMock()
        mock_proc.returncode = 0
        mock_proc.stdout = "void FuncX() {}\n"
        mock_proc.stderr = ""

        with patch("shutil.which", return_value="/usr/local/bin/rea"), \
             patch("subprocess.run", return_value=mock_proc):
            res = prime_cache(symbols_file=sym_file, dry_run=False, dirtyroom_root=self.dr)
            self.assertTrue(res["success"])

        stats = get_cache_stats(self.dr)
        self.assertEqual(stats["hits"], 0)
        self.assertEqual(stats["misses"], 0)

    def test_get_priority_functions_propagates_sqlite_error_and_prime_cache_reports_it(self):
        """Verifies sqlite3.Error is not swallowed in get_priority_functions or prime_cache (DEFECT-S3-001)."""
        from harness.re.priming import get_priority_functions, prime_cache

        db_path = self.dr / "symbols" / "dirtyroom.db"
        conn = sqlite3.connect(db_path)
        try:
            conn.execute("DROP TABLE functions")
            conn.commit()
            with self.assertRaises(sqlite3.Error):
                get_priority_functions(conn)
        finally:
            conn.close()

        res = prime_cache(top=5, dirtyroom_root=self.dr)
        self.assertFalse(res["success"])
        self.assertIn("Database error resolving binary/functions:", res.get("error", ""))

    def test_compute_cache_key_centralized_in_cache_module(self):
        """Verifies compute_cache_key lives in harness.re.cache and is shared by priming (DEFECT-S3-006)."""
        from harness.re.cache import compute_cache_key as cache_compute_key
        from harness.re.priming import compute_cache_key as priming_compute_key

        self.assertIs(cache_compute_key, priming_compute_key)
        self.assertEqual(cache_compute_key(None, "app.exe", "ns::func/1"), "app.exe_00000000_ns__func_1")
        self.assertEqual(cache_compute_key(None, "", "main"), "target_00000000_main")

    def test_prime_cache_failures_validation_dedup_and_decompile_hit_roundtrip(self):
        """Verifies prime_cache rejects invalid args/failures, deduplicates symbols, and feeds cmd_decompile cache."""
        from harness.commands.re import cmd_decompile
        from harness.re.cache import get_cache_stats
        from harness.re.priming import cmd_prime, get_priority_functions, prime_cache

        # 1. Negative/zero top & timeout validation
        conn = sqlite3.connect(self.dr / "symbols" / "dirtyroom.db")
        try:
            conn.execute("INSERT INTO binaries (name, sha256, file_size, created_at) VALUES ('v.exe', '0', 10, 'now')")
            conn.execute("INSERT INTO functions (binary_id, name, address, size, is_exported, created_at) VALUES (1, 'f1', '0x1', 10, 1, 'now')")
            conn.commit()
            self.assertEqual(get_priority_functions(conn, limit=-1), [])
            self.assertEqual(get_priority_functions(conn, limit=0), [])
        finally:
            conn.close()

        self.assertFalse(prime_cache(top=-5, dirtyroom_root=self.dr)["success"])
        self.assertFalse(prime_cache(top=0, dirtyroom_root=self.dr)["success"])
        self.assertFalse(prime_cache(top=5, timeout=0, dirtyroom_root=self.dr)["success"])

        # cmd_prime with explicit --top 0 must fail (not silently default to 20)
        args_zero = argparse.Namespace(top=0, file=None, binary=None, timeout=30.0, dry_run=True, json=True)
        out_zero = io.StringIO()
        with patch("harness.re.priming.get_dirtyroom_root", return_value=self.dr), \
             patch("sys.stdout", out_zero):
            self.assertEqual(cmd_prime(args_zero), 1)
            self.assertFalse(json.loads(out_zero.getvalue())["success"])

        # 2. Missing rea CLI with uncached targets must fail & deduplicate duplicate symbols
        sym_file = self.workspace / "dup_syms.txt"
        sym_file.write_text("SharedFunc\nSharedFunc\n", encoding="utf-8")
        with patch("shutil.which", return_value=None):
            res_missing_rea = prime_cache(symbols_file=sym_file, dry_run=False, dirtyroom_root=self.dr)
            self.assertFalse(res_missing_rea["success"])
            self.assertEqual(res_missing_rea["candidates"], 1)
            self.assertEqual(res_missing_rea["failed"], 1)
            self.assertIn("rea CLI not found", res_missing_rea.get("error", ""))

        # 3. End-to-end roundtrip: prime_cache writes cache entry -> cmd_decompile hits cache (<5ms, 0 subprocess)
        bin_file = self.dr / "binaries" / "RoundTrip.exe"
        bin_file.parent.mkdir(parents=True, exist_ok=True)
        bin_file.write_bytes(b"\x90" * 128)
        conn = sqlite3.connect(self.dr / "symbols" / "dirtyroom.db")
        try:
            conn.execute("INSERT INTO binaries (name, sha256, file_size, created_at) VALUES ('RoundTrip.exe', '1', 128, 'now')")
            conn.commit()
        finally:
            conn.close()

        mock_proc = MagicMock()
        mock_proc.returncode = 0
        mock_proc.stdout = "int SharedFunc(void) { return 7; }\n"
        mock_proc.stderr = ""
        with patch("shutil.which", return_value="/usr/local/bin/rea"), \
             patch("subprocess.run", return_value=mock_proc):
            res_prime = prime_cache(symbols_file=sym_file, binary_name="RoundTrip.exe", dry_run=False, dirtyroom_root=self.dr)
            self.assertTrue(res_prime["success"], res_prime.get("error"))
            self.assertEqual(res_prime["primed"], 1)

        out_dec = io.StringIO()
        dec_args = argparse.Namespace(procedure="SharedFunc", binary="RoundTrip.exe", no_cache=False, timeout=30.0)
        with patch("shutil.which", return_value="/usr/local/bin/rea"), \
             patch("subprocess.run", side_effect=AssertionError("Should hit primed cache")) as mock_dec_run, \
             patch("sys.stdout", out_dec), \
             patch("harness.commands.re.get_dirtyroom_root", return_value=self.dr), \
             patch("harness.re.scaffold.get_dirtyroom_root", return_value=self.dr):
            code = cmd_decompile(dec_args)
            self.assertEqual(code, 0)
            self.assertIn("return 7;", out_dec.getvalue())
            mock_dec_run.assert_not_called()

        stats = get_cache_stats(self.dr)
        self.assertEqual(stats["hits"], 1)
        self.assertEqual(stats["misses"], 0)


class TestDirtyroomHygiene(unittest.TestCase):
    """Verifies lock file detection, log pruning, database vacuum, and routine hygiene."""

    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.workspace = Path(self.temp_dir.name)
        scaffold_dirtyroom(self.workspace, project_name="HygieneTest")
        self.dr = self.workspace / ".dirtyroom"

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_clean_locks_detects_and_removes_stale_locks(self):
        """Verifies detection and unlinking of orphan Ghidra .lock files."""
        from harness.re.hygiene import clean_locks

        ghidra_dir = self.dr / "ghidra"
        sub_rep = ghidra_dir / "TestProj.rep"
        sub_rep.mkdir(parents=True, exist_ok=True)

        l1 = ghidra_dir / "TestProj.gpr.lock"
        l2 = sub_rep / "project.lock~"
        l3 = sub_rep / ".lockfile"
        for l in (l1, l2, l3):
            l.write_text("ghidra-lock-content", encoding="utf-8")

        # 1. Dry run
        dry_res = clean_locks(self.dr, dry_run=True)
        self.assertEqual(dry_res["count"], 3)
        self.assertTrue(l1.is_file())
        self.assertTrue(l2.is_file())
        self.assertTrue(l3.is_file())

        # 2. Live execution (with no ghidra process active)
        with patch("harness.re.hygiene._is_ghidra_running", return_value=False):
            res = clean_locks(self.dr, dry_run=False)
            self.assertEqual(res["count"], 3)
            self.assertFalse(l1.exists())
            self.assertFalse(l2.exists())
            self.assertFalse(l3.exists())

    def test_clean_locks_process_safety_guard(self):
        """Verifies active Ghidra processes prevent accidental lock deletion without force."""
        from harness.re.hygiene import clean_locks

        lock_p = self.dr / "ghidra" / "active.lock"
        lock_p.write_text("active-lock", encoding="utf-8")

        with patch("harness.re.hygiene._is_ghidra_running", return_value=True):
            # Guard prevents deletion
            safe_res = clean_locks(self.dr, dry_run=False, force=False)
            self.assertEqual(safe_res["count"], 0)
            self.assertTrue(safe_res["ghidra_running"])
            self.assertTrue(lock_p.is_file())

            # Force override deletes anyway
            force_res = clean_locks(self.dr, dry_run=False, force=True)
            self.assertEqual(force_res["count"], 1)
            self.assertFalse(lock_p.exists())

    def test_clean_logs_pruning_preserves_active_daemon(self):
        """Verifies log pruning deletes old logs while preserving active supervisor daemon log."""
        from harness.re.hygiene import clean_logs

        logs_dir = self.dr / "logs"
        logs_dir.mkdir(parents=True, exist_ok=True)

        old_log = logs_dir / "old_headless.log"
        old_tmp = logs_dir / "scratch.tmp"
        daemon_log = logs_dir / "rea_daemon.log"
        daemon_pid = logs_dir / "rea_daemon.pid"

        old_log.write_text("old-log-text", encoding="utf-8")
        old_tmp.write_text("temp-text", encoding="utf-8")
        daemon_log.write_text("daemon-log-active", encoding="utf-8")
        daemon_pid.write_text("12345\n", encoding="utf-8")

        with patch("harness.re.hygiene._read_pid", return_value=12345), \
             patch("harness.re.hygiene._is_pid_alive", return_value=True):
            res = clean_logs(self.dr, dry_run=False)
            self.assertEqual(res["count"], 2)
            self.assertFalse(old_log.exists())
            self.assertFalse(old_tmp.exists())
            self.assertTrue(daemon_log.is_file())
            self.assertTrue(daemon_pid.is_file())

    def test_vacuum_database_optimizes_db(self):
        """Verifies vacuum_database executes VACUUM, REINDEX, and ANALYZE without corruption."""
        from harness.re.hygiene import vacuum_database

        db_path = self.dr / "symbols" / "dirtyroom.db"
        conn = sqlite3.connect(db_path)
        cur = conn.cursor()
        for i in range(100):
            cur.execute("INSERT INTO strings (binary_id, value) VALUES (1, ?)", (f"string_{i}" * 50,))
        conn.commit()
        # Delete to create free pages
        cur.execute("DELETE FROM strings WHERE id > 50")
        conn.commit()
        conn.close()

        res = vacuum_database(self.dr, dry_run=False)
        self.assertTrue(res["success"], res.get("error"))
        self.assertGreater(res["size_before"], 0)
        self.assertGreater(res["size_after"], 0)

    def test_clean_dirtyroom_orchestration_and_cmd_clean(self):
        """Verifies clean_dirtyroom and cmd_clean CLI dispatch."""
        from harness.re.hygiene import clean_dirtyroom, cmd_clean

        res = clean_dirtyroom(dry_run=True, dirtyroom_root=self.dr)
        self.assertTrue(res["success"])
        self.assertTrue(res["dry_run"])
        self.assertIn("locks", res)
        self.assertIn("logs", res)
        self.assertIn("vacuum", res)

        args = argparse.Namespace(locks=False, logs=False, vacuum=False, force=False, dry_run=True, json=True)
        out_buf = io.StringIO()
        with patch("harness.re.hygiene.get_dirtyroom_root", return_value=self.dr), \
             patch("sys.stdout", out_buf):
            ret = cmd_clean(args)
            self.assertEqual(ret, 0)
            data = json.loads(out_buf.getvalue())
            self.assertTrue(data["success"])

    def test_clean_dirtyroom_no_dirtyroom(self):
        """Verifies clean_dirtyroom returns error when no dirtyroom root is resolved."""
        from harness.re.hygiene import clean_dirtyroom

        with patch("harness.re.hygiene.get_dirtyroom_root", return_value=None):
            res = clean_dirtyroom(dirtyroom_root=None)
            self.assertFalse(res["success"])
            self.assertIn("No active dirtyroom found", res.get("error", ""))

    def test_vacuum_database_missing_db(self):
        """Verifies vacuum_database returns descriptive error if symbols DB is missing."""
        from harness.re.hygiene import vacuum_database

        empty_dir = self.workspace / "empty_dir"
        empty_dir.mkdir(parents=True, exist_ok=True)
        res = vacuum_database(empty_dir)
        self.assertFalse(res["success"])
        self.assertIn("No symbols database found", res.get("error", ""))

    def test_vacuum_database_autocommit_isolation_level(self):
        """Verifies vacuum_database succeeds in autocommit mode without transaction errors."""
        from harness.re.hygiene import vacuum_database

        db_path = self.dr / "symbols" / "dirtyroom.db"
        conn = sqlite3.connect(db_path)
        conn.execute("PRAGMA journal_mode=WAL;")
        cur = conn.cursor()
        for i in range(50):
            cur.execute("INSERT INTO strings (binary_id, value) VALUES (1, ?)", (f"wal_str_{i}",))
        conn.commit()
        conn.close()

        res = vacuum_database(self.dr, dry_run=False)
        self.assertTrue(res["success"], res.get("error"))

    def test_clean_locks_and_logs_safe_stat(self):
        """Verifies clean_locks and clean_logs handle deleted/inaccessible files safely."""
        from harness.re.hygiene import _safe_stat_size, clean_locks, clean_logs

        # Safe stat returns 0 on missing/inaccessible path
        self.assertEqual(_safe_stat_size(Path("/nonexistent/file/path.lock")), 0)

        ghidra_dir = self.dr / "ghidra"
        lock_f = ghidra_dir / "temp.lock"
        lock_f.write_text("lock", encoding="utf-8")

        logs_dir = self.dr / "logs"
        log_f = logs_dir / "trace.log"
        log_f.write_text("log", encoding="utf-8")

        with patch("harness.re.hygiene._safe_stat_size", return_value=0):
            lock_res = clean_locks(self.dr, dry_run=True, force=True)
            self.assertEqual(lock_res["bytes"], 0)

            log_res = clean_logs(self.dr, dry_run=True)
            self.assertEqual(log_res["bytes"], 0)

    def test_clean_dirtyroom_explicit_vacuum_missing_db_fails(self):
        """Verifies clean_dirtyroom(vacuum=True) surfaces failure when DB is missing (DEFECT-S3-003)."""
        from harness.re.hygiene import clean_dirtyroom, cmd_clean

        empty_dir = self.workspace / "empty_dirtyroom"
        empty_dir.mkdir(parents=True, exist_ok=True)

        res = clean_dirtyroom(vacuum=True, dirtyroom_root=empty_dir)
        self.assertFalse(res["success"])
        self.assertIn("No symbols database found", res.get("error", ""))

        args = argparse.Namespace(locks=False, logs=False, vacuum=True, force=False, dry_run=False, json=True)
        out_buf = io.StringIO()
        with patch("harness.re.hygiene.get_dirtyroom_root", return_value=empty_dir), \
             patch("sys.stdout", out_buf):
            code = cmd_clean(args)
            self.assertEqual(code, 1)
            payload = json.loads(out_buf.getvalue())
            self.assertFalse(payload["success"])

    def test_clean_dirtyroom_default_all_missing_db_succeeds_but_sqlite_failure_fails(self):
        """Verifies default do_all tolerates missing DB but surfaces real SQLite failures (DEFECT-S3-003)."""
        from harness.re.hygiene import clean_dirtyroom

        # Missing DB during default do_all should not fail the whole cleanup pass
        empty_dir = self.workspace / "empty_all_dir"
        empty_dir.mkdir(parents=True, exist_ok=True)
        res_empty = clean_dirtyroom(dirtyroom_root=empty_dir)
        self.assertTrue(res_empty["success"])
        self.assertFalse(res_empty["vacuum"]["success"])

        # Real SQLite failure on corrupted DB during default do_all MUST fail
        corrupt_dir = self.workspace / "corrupt_db_dir"
        (corrupt_dir / "symbols").mkdir(parents=True, exist_ok=True)
        (corrupt_dir / "symbols" / "dirtyroom.db").write_bytes(b"NOT_A_SQLITE_DATABASE_HEADER_AT_ALL")
        res_corrupt = clean_dirtyroom(dirtyroom_root=corrupt_dir)
        self.assertFalse(res_corrupt["success"])
        self.assertIn("VACUUM execution failed", res_corrupt.get("error", ""))

    def test_clean_dirtyroom_surfaces_unlink_errors_and_multi_db_vacuum_failure(self):
        """Verifies failed lock/log unlinks are not misreported as deleted and multi-DB partial VACUUM fails cleanly."""
        from harness.re.hygiene import clean_dirtyroom, clean_locks

        # 1. PermissionError during lock unlink must not report file as deleted and must fail clean_dirtyroom
        lock_f = self.dr / "ghidra" / "locked.lock"
        lock_f.write_text("locked", encoding="utf-8")
        with patch("harness.re.hygiene._is_ghidra_running", return_value=False), \
             patch.object(Path, "unlink", side_effect=PermissionError("denied")):
            lock_res = clean_locks(self.dr, dry_run=False, force=True)
            self.assertEqual(lock_res["count"], 0)
            self.assertEqual(lock_res["bytes"], 0)
            self.assertEqual(lock_res["failed_count"], 1)

            dirty_res = clean_dirtyroom(locks=True, force=True, dirtyroom_root=self.dr)
            self.assertFalse(dirty_res["success"])
            self.assertIn("Failed to remove 1 lock file(s)", dirty_res.get("error", ""))
        self.assertTrue(lock_f.exists())
        lock_f.unlink()

        # 2. Multi-DB: first DB valid, second DB corrupted -> vacuum & clean_dirtyroom must fail
        second_db = self.dr / "symbols" / "paladins_symbols.sqlite"
        second_db.write_bytes(b"CORRUPT_SECOND_DB_BYTES")
        res_multi = clean_dirtyroom(vacuum=True, dirtyroom_root=self.dr)
        self.assertFalse(res_multi["success"])
        self.assertIn("paladins_symbols.sqlite", res_multi.get("error", ""))


if __name__ == "__main__":
    unittest.main()


