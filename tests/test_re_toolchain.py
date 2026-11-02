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
from unittest.mock import patch

from harness.hooks.command_safety_hook import normalize_rea_mcp_tool_call
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

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_check_patch_detects_unpatched_state(self):
        res = check_patch(self.mock_rea)
        self.assertEqual(res["status"], "unapplied")
        self.assertFalse(res["launcher_patched"])
        self.assertFalse(res["mcp_patched"])

    def test_apply_and_revert_patch_roundtrip(self):
        # 1. Apply patch
        apply_res = apply_patch(self.mock_rea)
        self.assertTrue(apply_res["success"])

        # Check patched files
        check_res = check_patch(self.mock_rea)
        self.assertEqual(check_res["status"], "applied")
        self.assertTrue(check_res["launcher_patched"])
        self.assertTrue(check_res["mcp_patched"])

        l_content = self.launcher.read_text(encoding="utf-8")
        self.assertIn(PATCH_SIGNATURE, l_content)
        self.assertIn("-noanalysis", l_content)
        self.assertIn("-readOnly", l_content)

        # Verify .orig backups exist
        self.assertTrue(self.launcher.with_suffix(".js.orig").is_file())
        self.assertTrue(self.mcp_binary.with_suffix(".js.orig").is_file())

        # 2. Revert patch
        rev_res = revert_patch(self.mock_rea)
        self.assertTrue(rev_res["success"])

        check_after = check_patch(self.mock_rea)
        self.assertEqual(check_after["status"], "unapplied")
        self.assertFalse(self.launcher.with_suffix(".js.orig").exists())
        self.assertNotIn(PATCH_SIGNATURE, self.launcher.read_text(encoding="utf-8"))


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


if __name__ == "__main__":
    unittest.main()
