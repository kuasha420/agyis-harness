#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Arafat Zahan (@kuasha420)
# Corporate Stewardship & Infrastructure: Purrfect Software Limited (PSL)
# Governed by: ICARO-42/b Ordinance (Company-Supported Personal IP Framework)

"""
Real Node.js E2E verification of REA direct-mount auto-discovery and bundle patching.
Split from test_re_toolchain.py for sub-second ADR-015 verification.
"""

from __future__ import annotations

import argparse
import io
import json
import os
from pathlib import Path
import shutil
import sqlite3
import subprocess
import tempfile
import unittest
from unittest.mock import MagicMock, patch

from harness.re.patcher import (
    AUTO_DISCOVERY_SIGNATURE,
    DIRECT_MOUNT_SIGNATURE,
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


def _isolate_registry(test_case: unittest.TestCase) -> Path:
    """Redirects AGYIS_DIRTYROOM_REGISTRY into an isolated temp dir for test hermeticity."""
    reg_td = tempfile.TemporaryDirectory()
    reg_path = Path(reg_td.name) / "agyis_dirtyrooms.json"
    orig_val = os.environ.get("AGYIS_DIRTYROOM_REGISTRY")
    os.environ["AGYIS_DIRTYROOM_REGISTRY"] = str(reg_path)

    def _restore() -> None:
        if orig_val is None:
            os.environ.pop("AGYIS_DIRTYROOM_REGISTRY", None)
        else:
            os.environ["AGYIS_DIRTYROOM_REGISTRY"] = orig_val
        reg_td.cleanup()

    test_case.addCleanup(_restore)
    return reg_path


class TestGlobalReaDirectMountNodeE2E(unittest.TestCase):
    """End-to-end Node.js verification of multi-workspace direct-mount JS patching and bundles."""

    def setUp(self):
        self.registry_path = _isolate_registry(self)
        self.temp_dir = tempfile.TemporaryDirectory()
        self.root = Path(self.temp_dir.name)

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_node_e2e_direct_mount_autodiscovery_without_static_env_vars(self):
        """Real Node.js E2E test proving global direct-mount works with ONLY REA_GHIDRA_DIRECT_MOUNT=1."""
        node_bin = shutil.which("node")
        if not node_bin:
            self.skipTest("node binary not available in PATH")

        # 1. Build a realistic ESM rea-agents layout matching rea-agents@6.9.0
        mock_rea = self.root / "rea-agents"
        ghidra_dir = mock_rea / "dist" / "ghidra"
        mcp_dir = mock_rea / "dist" / "mcp"
        ghidra_dir.mkdir(parents=True)
        mcp_dir.mkdir(parents=True)
        (mock_rea / "package.json").write_text('{"name":"rea-agents","type":"module"}\n', encoding="utf-8")

        (ghidra_dir / "GhidraLauncher.js").write_text(
            'import { constants as fsConstants } from "node:fs";\n'
            'import { copyFile, mkdir } from "node:fs/promises";\n'
            'import { posix, win32 } from "node:path";\n'
            'export const ghidraHeadlessArguments = (options) => {\n'
            '    const scriptPath = (options.platform ?? process.platform) === "win32" ? win32 : posix;\n'
            '    const bridgeDirectory = scriptPath.dirname(options.bridgeScriptPath);\n'
            '    return [options.projectRoot, "rea-project", "-import", options.targetPath];\n'
            '};\n',
            encoding="utf-8",
        )
        (ghidra_dir / "GhidraProjectSnapshot.js").write_text(
            'import { cp, lstat, mkdir, readdir, realpath } from "node:fs/promises";\n'
            'import { basename, dirname, isAbsolute, join, relative, resolve, sep } from "node:path";\n'
            'export const fingerprintGhidraProject = async (root, name, resources, signal) => {\n'
            '    return "non-bypassed-real-fingerprint";\n'
            '};\n'
            'export const copyExistingGhidraProject = async (sourcePath, destinationRoot, options = {}) => {\n'
            '    await mkdir(join(destinationRoot, "COPIED_MARKER"), { recursive: true });\n'
            '};\n',
            encoding="utf-8",
        )
        (ghidra_dir / "GhidraTargetSnapshot.js").write_text(
            'import { extname, join } from "node:path";\n'
            'const safeExtension = (p) => extname(p) || ".bin";\n'
            'export const createGhidraTargetSnapshot = async (sourcePath, runtimeRoot, expectedSha256, options = {}) => {\n'
            '    const suffix = safeExtension(sourcePath);\n'
            '    const snapshotPath = join(runtimeRoot, `target-${expectedSha256.slice(0, 12)}${suffix}`);\n'
            '    return { path: snapshotPath, sha256: expectedSha256 };\n'
            '};\n',
            encoding="utf-8",
        )
        (mcp_dir / "binary-e2e.js").write_text(
            'import { statSync } from "node:fs";\n'
            'import { mkdir, readdir } from "node:fs/promises";\n'
            'import { dirname, extname, join, posix, resolve, win32 } from "node:path";\n'
            'export const fingerprintGhidraProject = async (root, name, resources, signal) => {\n'
            '    return "non-bypassed-mcp-fingerprint";\n'
            '};\n'
            'export const copyExistingGhidraProject = async (sourcePath, destinationRoot, options = {}) => {\n'
            '    await mkdir(join(destinationRoot, "COPIED_MCP"), { recursive: true });\n'
            '};\n'
            'const safeExtension = (p) => extname(p) || ".bin";\n'
            'export const createGhidraTargetSnapshot = async (sourcePath, runtimeRoot, expectedSha256, options = {}) => {\n'
            '    const suffix = safeExtension(sourcePath);\n'
            '    const snapshotPath = join(runtimeRoot, `target-${expectedSha256.slice(0, 12)}${suffix}`);\n'
            '    return { path: snapshotPath, sha256: expectedSha256 };\n'
            '};\n'
            'export const ghidraHeadlessArguments = (options) => {\n'
            '    const scriptPath = (options.platform ?? process.platform) === "win32" ? win32 : posix;\n'
            '    const bridgeDirectory = scriptPath.dirname(options.bridgeScriptPath);\n'
            '    return [options.projectRoot, "rea-project", "-import", options.targetPath];\n'
            '};\n',
            encoding="utf-8",
        )

        patch_res = apply_patch(mock_rea)
        self.assertTrue(patch_res["success"], patch_res.get("error"))
        status = check_patch(mock_rea)
        self.assertEqual(status["status"], "applied")
        self.assertTrue(status["direct_mount_active"])
        self.assertTrue(status["auto_discovery_active"])

        # 2. Build temp RE workspace with .dirtyroom/binaries/test.exe and dirtyroom/ghidra/MyProj.gpr
        re_ws = self.root / "game_workspace"
        (re_ws / ".dirtyroom" / "binaries").mkdir(parents=True)
        (re_ws / ".dirtyroom" / "ghidra" / "MyProj.rep").mkdir(parents=True)
        (re_ws / ".dirtyroom" / "ghidra" / "MyProj.gpr").write_text("gpr", encoding="utf-8")
        target_exe = re_ws / ".dirtyroom" / "binaries" / "test.exe"
        target_exe.write_bytes(b"MZTEST")
        (re_ws / "dirtyroom").symlink_to(".dirtyroom", target_is_directory=True)

        # Unrelated cwd and non-RE target
        unrelated_cwd = self.root / "unrelated_cwd"
        unrelated_cwd.mkdir()
        plain_exe = unrelated_cwd / "plain.exe"
        plain_exe.write_bytes(b"MZPLAIN")
        dest_root = self.root / "clone_dest"
        dest_root.mkdir()
        dest_optout = self.root / "clone_dest_optout"
        dest_optout.mkdir()
        tmp_runtime = self.root / "rea_runtime"
        tmp_runtime.mkdir()

        # 3. Execute real Node.js harness script testing all code paths
        driver = self.root / "e2e_driver.mjs"
        driver.write_text(
            'import assert from "node:assert/strict";\n'
            'import { readdirSync } from "node:fs";\n'
            'import { ghidraHeadlessArguments } from "./rea-agents/dist/ghidra/GhidraLauncher.js";\n'
            'import { fingerprintGhidraProject, copyExistingGhidraProject } from "./rea-agents/dist/ghidra/GhidraProjectSnapshot.js";\n'
            'import { createGhidraTargetSnapshot } from "./rea-agents/dist/ghidra/GhidraTargetSnapshot.js";\n'
            'import * as mcpBundle from "./rea-agents/dist/mcp/binary-e2e.js";\n'
            'const ws = process.env.TEST_WS;\n'
            'const targetExe = process.env.TEST_TARGET;\n'
            'const plainExe = process.env.TEST_PLAIN;\n'
            'const destRoot = process.env.TEST_DEST;\n'
            'const destOptout = process.env.TEST_DEST_OPTOUT;\n'
            'const tmpRuntime = process.env.TEST_RUNTIME;\n'
            'const expectedDir = `${ws}/dirtyroom/ghidra`;\n'
            'const baseOpts = {\n'
            '    platform: "linux",\n'
            '    projectRoot: "/tmp/ephemeral/project",\n'
            '    bridgeScriptPath: "/opt/rea/bridge/Bridge.java",\n'
            '    descriptorPath: "/tmp/ephemeral/session.json",\n'
            '    ghidraLogPath: "/tmp/ephemeral/ghidra.log",\n'
            '    scriptLogPath: "/tmp/ephemeral/script.log",\n'
            '};\n'
            '// Case 1: Auto-discovery from targetPath with ONLY REA_GHIDRA_DIRECT_MOUNT=1\n'
            'const argsDirect = ghidraHeadlessArguments({ ...baseOpts, targetPath: targetExe });\n'
            'assert.equal(argsDirect[0], expectedDir);\n'
            'assert.ok(!argsDirect[0].includes("/.dirtyroom/"));\n'
            'assert.equal(argsDirect[1], "MyProj");\n'
            'assert.equal(argsDirect[2], "-process");\n'
            'assert.equal(argsDirect[3], "test.exe");\n'
            'assert.equal(argsDirect[4], "-noanalysis");\n'
            'assert.equal(argsDirect[5], "-readOnly");\n'
            '// Case 2: Real rea mcp snapshot indirection (temp target-<sha>.exe -> original workspace binary)\n'
            'const sha = "a".repeat(64);\n'
            'const snap = await createGhidraTargetSnapshot(targetExe, tmpRuntime, sha);\n'
            'const argsSnap = ghidraHeadlessArguments({ ...baseOpts, targetPath: snap.path });\n'
            'assert.equal(argsSnap[0], expectedDir);\n'
            'assert.equal(argsSnap[1], "MyProj");\n'
            'assert.equal(argsSnap[2], "-process");\n'
            'assert.equal(argsSnap[3], "test.exe");\n'
            'assert.equal(argsSnap[4], "-noanalysis");\n'
            'assert.equal(argsSnap[5], "-readOnly");\n'
            '// Case 3: MCP bundle snapshot + launcher + fastpaths with ONLY REA_GHIDRA_DIRECT_MOUNT=1\n'
            'const mcpSnap = await mcpBundle.createGhidraTargetSnapshot(targetExe, tmpRuntime, "b".repeat(64));\n'
            'const mcpArgs = mcpBundle.ghidraHeadlessArguments({ ...baseOpts, targetPath: mcpSnap.path });\n'
            'assert.equal(mcpArgs[0], expectedDir);\n'
            'assert.equal(mcpArgs[3], "test.exe");\n'
            '// Case 4: Fingerprint and copy fastpaths short-circuit via auto-discovery without cloning\n'
            'const fp = await fingerprintGhidraProject(expectedDir, "MyProj");\n'
            'assert.equal(fp, "0".repeat(64));\n'
            'const fpDot = await mcpBundle.fingerprintGhidraProject(`${ws}/.dirtyroom/ghidra`, "MyProj");\n'
            'assert.equal(fpDot, "0".repeat(64));\n'
            'await copyExistingGhidraProject(expectedDir, destRoot, { projectName: "MyProj" });\n'
            'await mcpBundle.copyExistingGhidraProject(`${ws}/.dirtyroom/ghidra`, destRoot, { projectName: "MyProj" });\n'
            'assert.deepEqual(readdirSync(destRoot), []);\n'
            '// Case 5: Non-RE workspace binary falls back cleanly to -import\n'
            'const plainArgs = ghidraHeadlessArguments({ ...baseOpts, targetPath: plainExe });\n'
            'assert.equal(plainArgs[2], "-import");\n'
            '// Case 6: Explicit dot-path env var REA_GHIDRA_PROJECT_DIR normalized to non-dot sibling\n'
            'process.env.REA_GHIDRA_PROJECT_DIR = `${ws}/.dirtyroom/ghidra`;\n'
            'const dotNormArgs = ghidraHeadlessArguments({ ...baseOpts, targetPath: plainExe });\n'
            'assert.equal(dotNormArgs[0], expectedDir);\n'
            'assert.ok(!dotNormArgs[0].includes("/.dirtyroom/"));\n'
            'delete process.env.REA_GHIDRA_PROJECT_DIR;\n'
            '// Case 7: Explicit opt-out REA_GHIDRA_DIRECT_MOUNT=0 disables direct mount and fastpaths\n'
            'process.env.REA_GHIDRA_DIRECT_MOUNT = "0";\n'
            'const optOutArgs = ghidraHeadlessArguments({ ...baseOpts, targetPath: targetExe });\n'
            'assert.equal(optOutArgs[2], "-import");\n'
            'const optOutFp = await fingerprintGhidraProject(expectedDir, "MyProj");\n'
            'assert.equal(optOutFp, "non-bypassed-real-fingerprint");\n'
            'await copyExistingGhidraProject(expectedDir, destOptout, { projectName: "MyProj" });\n'
            'assert.deepEqual(readdirSync(destOptout), ["COPIED_MARKER"]);\n'
            'console.log("NODE_E2E_OK");\n',
            encoding="utf-8",
        )

        # Construct strictly clean env with ONLY REA_GHIDRA_DIRECT_MOUNT=1 (no project dir / dirtyroom env)
        clean_env = {
            "PATH": os.environ.get("PATH", ""),
            "HOME": os.environ.get("HOME", str(self.root)),
            "REA_GHIDRA_DIRECT_MOUNT": "1",
            "AGYIS_DIRTYROOM_REGISTRY": str(self.registry_path),
            "TEST_WS": str(re_ws),
            "TEST_TARGET": str(target_exe),
            "TEST_PLAIN": str(plain_exe),
            "TEST_DEST": str(dest_root),
            "TEST_DEST_OPTOUT": str(dest_optout),
            "TEST_RUNTIME": str(tmp_runtime),
        }

        proc = subprocess.run(
            [node_bin, str(driver)],
            cwd=str(unrelated_cwd),
            env=clean_env,
            capture_output=True,
            text=True,
            timeout=10,
        )
        self.assertEqual(proc.returncode, 0, f"Node E2E failed:\nSTDOUT:\n{proc.stdout}\nSTDERR:\n{proc.stderr}")
        self.assertIn("NODE_E2E_OK", proc.stdout)

    def test_node_e2e_adversarial_edge_cases_and_real_rea_bundles(self):
        """Real Node.js E2E test covering auto-symlink, multi-GPR selection, overrides, and real rea-agents bundles."""
        node_bin = shutil.which("node")
        if not node_bin:
            self.skipTest("node binary not available in PATH")

        # 1. Minimal mock ESM modules (note: GhidraProjectSnapshot has ZERO imports to test aliased import injection)
        mock_rea = self.root / "rea-adv"
        ghidra_dir = mock_rea / "dist" / "ghidra"
        mcp_dir = mock_rea / "dist" / "mcp"
        ghidra_dir.mkdir(parents=True)
        mcp_dir.mkdir(parents=True)
        (mock_rea / "package.json").write_text('{"name":"rea-agents","type":"module"}\n', encoding="utf-8")

        (ghidra_dir / "GhidraLauncher.js").write_text(
            'import { posix, win32 } from "node:path";\n'
            'export const ghidraHeadlessArguments = (options) => {\n'
            '    const scriptPath = (options.platform ?? process.platform) === "win32" ? win32 : posix;\n'
            '    const bridgeDirectory = scriptPath.dirname(options.bridgeScriptPath);\n'
            '    if (options.existingProject) return [options.projectRoot, options.existingProject.projectName, "-process", options.existingProject.programName];\n'
            '    return [options.projectRoot, "rea-project", "-import", options.packedProgramPath ?? options.targetPath];\n'
            '};\n',
            encoding="utf-8",
        )
        (ghidra_dir / "GhidraProjectSnapshot.js").write_text(
            'export async function fingerprintGhidraProject(root, name, resources, signal) {\n'
            '    return "non-bypassed-fp";\n'
            '}\n'
            'export async function copyExistingGhidraProject(sourcePath, destinationRoot, options = {}) {\n'
            '    return "non-bypassed-copy";\n'
            '}\n',
            encoding="utf-8",
        )
        (mcp_dir / "binary-adv.js").write_text(
            'import { posix, win32 } from "node:path";\n'
            'export const ghidraHeadlessArguments = (options) => {\n'
            '    const scriptPath = (options.platform ?? process.platform) === "win32" ? win32 : posix;\n'
            '    const bridgeDirectory = scriptPath.dirname(options.bridgeScriptPath);\n'
            '    return [options.projectRoot, "rea-project", "-import", options.targetPath];\n'
            '};\n',
            encoding="utf-8",
        )
        self.assertTrue(apply_patch(mock_rea)["success"])

        # 2. Workspace without pre-existing dirtyroom symlink (DEF-BB-038 auto-symlink)
        ws_nosym = self.root / "ws_nosym"
        (ws_nosym / ".dirtyroom" / "ghidra" / "NoSym.rep").mkdir(parents=True)
        (ws_nosym / ".dirtyroom" / "ghidra" / "NoSym.gpr").write_text("gpr", encoding="utf-8")
        (ws_nosym / ".dirtyroom" / "binaries").mkdir(parents=True)
        t_nosym = ws_nosym / ".dirtyroom" / "binaries" / "app.exe"
        t_nosym.write_bytes(b"MZ")

        # 3. Multi-GPR workspace with populated .rep/idata/*.prp metadata
        ws_multi = self.root / "ws_multi"
        for proj, prog in [("Alpha", "alpha.exe"), ("Beta", "beta.dll")]:
            idata = ws_multi / ".dirtyroom" / "ghidra" / f"{proj}.rep" / "idata" / "00"
            idata.mkdir(parents=True)
            (ws_multi / ".dirtyroom" / "ghidra" / f"{proj}.gpr").write_text("gpr", encoding="utf-8")
            (idata / "00000001.prp").write_text(
                f'<?xml version="1.0"?><FILE_INFO><BASIC_INFO>'
                f'<STATE NAME="CONTENT_TYPE" TYPE="string" VALUE="Program" />'
                f'<STATE NAME="NAME" TYPE="string" VALUE="{prog}" />'
                f'</BASIC_INFO></FILE_INFO>\n',
                encoding="utf-8",
            )
        (ws_multi / ".dirtyroom" / "binaries").mkdir(parents=True)
        t_beta = ws_multi / ".dirtyroom" / "binaries" / "beta.dll"
        t_beta.write_bytes(b"MZ")
        t_unimported = ws_multi / ".dirtyroom" / "binaries" / "unimported.so"
        t_unimported.write_bytes(b"\x7fELF")
        (ws_multi / "dirtyroom").symlink_to(".dirtyroom", target_is_directory=True)

        # 4. Custom standalone Ghidra project dir (not named dirtyroom/ghidra)
        custom_proj = self.root / "custom_proj"
        (custom_proj / "Custom.rep").mkdir(parents=True)
        (custom_proj / "Custom.gpr").write_text("gpr", encoding="utf-8")

        driver = self.root / "adv_driver.mjs"
        driver.write_text(
            'import assert from "node:assert/strict";\n'
            'import { lstatSync } from "node:fs";\n'
            'import { ghidraHeadlessArguments } from "./rea-adv/dist/ghidra/GhidraLauncher.js";\n'
            'import { fingerprintGhidraProject, copyExistingGhidraProject } from "./rea-adv/dist/ghidra/GhidraProjectSnapshot.js";\n'
            'const base = {\n'
            '    platform: "linux",\n'
            '    projectRoot: "/tmp/p",\n'
            '    bridgeScriptPath: "/opt/rea/bridge.java",\n'
            '    descriptorPath: "/tmp/session.json",\n'
            '    ghidraLogPath: "/tmp/g.log",\n'
            '    scriptLogPath: "/tmp/s.log",\n'
            '};\n'
            '// 1. Auto-symlink DEF-BB-038 when dirtyroom symlink was initially missing\n'
            'const aNoSym = ghidraHeadlessArguments({ ...base, targetPath: process.env.T_NOSYM });\n'
            'assert.equal(aNoSym[0], `${process.env.WS_NOSYM}/dirtyroom/ghidra`);\n'
            'assert.ok(!aNoSym[0].includes("/.dirtyroom/"));\n'
            'assert.ok(lstatSync(`${process.env.WS_NOSYM}/dirtyroom`).isSymbolicLink());\n'
            'assert.equal(aNoSym[1], "NoSym");\n'
            'assert.equal(aNoSym[2], "-process");\n'
            'assert.equal(aNoSym[3], "app.exe");\n'
            '// 2. Multi-GPR picks Beta for beta.dll, and falls back to -import for unimported.so\n'
            'const aBeta = ghidraHeadlessArguments({ ...base, targetPath: process.env.T_BETA });\n'
            'assert.equal(aBeta[1], "Beta");\n'
            'assert.equal(aBeta[2], "-process");\n'
            'assert.equal(aBeta[3], "beta.dll");\n'
            'const aUnimp = ghidraHeadlessArguments({ ...base, targetPath: process.env.T_UNIMP });\n'
            'assert.equal(aUnimp[2], "-import");\n'
            '// 3. Respects packedProgramPath, languageOverride, and options.existingProject\n'
            'const aPacked = ghidraHeadlessArguments({ ...base, targetPath: process.env.T_BETA, packedProgramPath: "/tmp/r.gzf" });\n'
            'assert.equal(aPacked[2], "-import");\n'
            'assert.equal(aPacked[3], "/tmp/r.gzf");\n'
            'const aLang = ghidraHeadlessArguments({ ...base, targetPath: process.env.T_BETA, languageOverride: { languageId: "x86:LE:64:default" } });\n'
            'assert.equal(aLang[2], "-import");\n'
            'const aExisting = ghidraHeadlessArguments({\n'
            '    ...base,\n'
            '    targetPath: "/tmp/target-111122223333.exe",\n'
            '    existingProject: { projectPath: `${process.env.WS_MULTI}/.dirtyroom/ghidra`, projectName: "Beta", programName: "CustomProg.exe" },\n'
            '});\n'
            'assert.equal(aExisting[0], `${process.env.WS_MULTI}/dirtyroom/ghidra`);\n'
            'assert.equal(aExisting[1], "Beta");\n'
            'assert.equal(aExisting[2], "-process");\n'
            'assert.equal(aExisting[3], "CustomProg.exe");\n'
            '// 4. Fastpaths bypass custom project dir AND do NOT falsely bypass nonexistent dirs even when cwd is an RE workspace\n'
            'const fpCustom = await fingerprintGhidraProject(process.env.CUSTOM_PROJ, "Custom");\n'
            'assert.equal(fpCustom, "0".repeat(64));\n'
            'const cpCustom = await copyExistingGhidraProject(process.env.CUSTOM_PROJ, "/tmp/unused", { projectName: "Custom" });\n'
            'assert.equal(cpCustom, undefined);\n'
            'const fpMissing = await fingerprintGhidraProject("/tmp/definitely-missing-ghidra-proj-xyz", "Missing");\n'
            'assert.equal(fpMissing, "non-bypassed-fp");\n'
            'const cpMissing = await copyExistingGhidraProject("/tmp/definitely-missing-ghidra-proj-xyz", "/tmp/unused", { projectName: "Missing" });\n'
            'assert.equal(cpMissing, "non-bypassed-copy");\n'
            'console.log("ADV_E2E_OK");\n',
            encoding="utf-8",
        )
        clean_env = {
            "PATH": os.environ.get("PATH", ""),
            "HOME": os.environ.get("HOME", str(self.root)),
            "REA_GHIDRA_DIRECT_MOUNT": "1",
            "AGYIS_DIRTYROOM_REGISTRY": str(self.registry_path),
            "WS_NOSYM": str(ws_nosym),
            "T_NOSYM": str(t_nosym),
            "WS_MULTI": str(ws_multi),
            "T_BETA": str(t_beta),
            "T_UNIMP": str(t_unimported),
            "CUSTOM_PROJ": str(custom_proj),
        }
        proc = subprocess.run(
            [node_bin, str(driver)],
            cwd=str(ws_multi),
            env=clean_env,
            capture_output=True,
            text=True,
            timeout=10,
        )
        self.assertEqual(proc.returncode, 0, f"Adversarial Node E2E failed:\nSTDOUT:\n{proc.stdout}\nSTDERR:\n{proc.stderr}")
        self.assertIn("ADV_E2E_OK", proc.stdout)

        # 5. If real rea-agents is installed on the host, test patching a temp copy of its real files + node --check
        from harness.re.patcher import find_rea_package_root, get_all_patch_targets

        real_root = find_rea_package_root()
        if real_root is not None:
            real_copy = self.root / "real_rea_copy"
            targets = get_all_patch_targets(real_root)
            for key, src_path in targets.items():
                if src_path is None or not src_path.is_file():
                    continue
                orig_path = src_path.with_suffix(".js.orig")
                source_file = orig_path if orig_path.is_file() else src_path
                rel = src_path.relative_to(real_root)
                dst = real_copy / rel
                dst.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(source_file, dst)
            (real_copy / "package.json").write_text('{"name":"rea-agents","type":"module"}\n', encoding="utf-8")

            res = apply_patch(real_copy)
            self.assertTrue(res["success"], res.get("error"))
            st = check_patch(real_copy)
            self.assertEqual(st["status"], "applied")
            self.assertTrue(st["auto_discovery_active"])
            self.assertTrue(st["direct_mount_active"])
            for patched_file in res["applied_files"]:
                chk = subprocess.run(
                    [node_bin, "--check", patched_file],
                    capture_output=True,
                    text=True,
                    timeout=10,
                )
                self.assertEqual(chk.returncode, 0, f"node --check failed on {patched_file}:\n{chk.stderr}")
            self.assertTrue(revert_patch(real_copy)["success"])
            self.assertEqual(check_patch(real_copy)["status"], "unapplied")

    def test_node_e2e_v4_symlinked_binaries_and_registry_autodiscovery(self):
        """Real Node.js E2E reproducing the exact Antigravity IDE symlink + CWD=/tmp failure and V4 fix."""
        node_bin = shutil.which("node")
        if not node_bin:
            self.skipTest("node binary not available in PATH")

        from harness.re.registry import register_dirtyroom

        # 1. Build mock rea-agents@6.9.0 ESM layout including BinaryTargetResolver (V3 -> V4 upgrade too)
        mock_rea = self.root / "rea-v4-e2e"
        ghidra_dir = mock_rea / "dist" / "ghidra"
        app_dir = mock_rea / "dist" / "application"
        mcp_dir = mock_rea / "dist" / "mcp"
        ghidra_dir.mkdir(parents=True)
        app_dir.mkdir(parents=True)
        mcp_dir.mkdir(parents=True)
        (mock_rea / "package.json").write_text('{"name":"rea-agents","type":"module"}\n', encoding="utf-8")

        orig_launcher = (
            'import { posix, win32 } from "node:path";\n'
            'export const ghidraHeadlessArguments = (options) => {\n'
            '    const scriptPath = (options.platform ?? process.platform) === "win32" ? win32 : posix;\n'
            '    const bridgeDirectory = scriptPath.dirname(options.bridgeScriptPath);\n'
            '    return [options.projectRoot, "rea-project", "-import", options.targetPath];\n'
            '};\n'
        )
        orig_target_snap = (
            'import { extname, join } from "node:path";\n'
            'const safeExtension = (p) => extname(p) || ".bin";\n'
            'export const createGhidraTargetSnapshot = async (sourcePath, runtimeRoot, expectedSha256) => {\n'
            '    const suffix = safeExtension(sourcePath);\n'
            '    const snapshotPath = join(runtimeRoot, `target-${expectedSha256.slice(0, 12)}${suffix}`);\n'
            '    return { path: snapshotPath, sha256: expectedSha256 };\n'
            '};\n'
        )
        orig_resolver = (
            'import { realpath } from "node:fs/promises";\n'
            'export const resolveBinaryTarget = async (candidate) => {\n'
            '    const canonical = await realpath(candidate);\n'
            '    const sourcePath = process.platform === "win32" ? candidate : canonical;\n'
            '    return { sourcePath, canonical };\n'
            '};\n'
        )

        # Simulate V3-patched state with .orig backups to verify V3 -> V4 clean upgrade
        (ghidra_dir / "GhidraLauncher.js.orig").write_text(orig_launcher, encoding="utf-8")
        (ghidra_dir / "GhidraLauncher.js").write_text(
            orig_launcher.replace("const bridgeDirectory =", "// AGYIS_REA_AUTODISCOVERY_V3 REA_GHIDRA_PROJECT_DIR\nconst bridgeDirectory ="),
            encoding="utf-8",
        )
        (ghidra_dir / "GhidraTargetSnapshot.js").write_text(orig_target_snap, encoding="utf-8")
        (app_dir / "BinaryTargetResolver.js").write_text(orig_resolver, encoding="utf-8")
        (mcp_dir / "binary-v4e2e.js.orig").write_text(orig_launcher, encoding="utf-8")
        (mcp_dir / "binary-v4e2e.js").write_text(
            orig_launcher.replace("const bridgeDirectory =", "// AGYIS_REA_AUTODISCOVERY_V3 REA_GHIDRA_PROJECT_DIR REA_DIRECT_MOUNT_ACTIVE\nconst bridgeDirectory ="),
            encoding="utf-8",
        )
        (mcp_dir / "BinaryTargetResolver-v4e2e.js").write_text(orig_resolver, encoding="utf-8")

        v3_status = check_patch(mock_rea)
        self.assertEqual(v3_status["status"], "partial")
        self.assertFalse(v3_status["auto_discovery_active"])

        upgrade_res = apply_patch(mock_rea)
        self.assertTrue(upgrade_res["success"], upgrade_res.get("error"))
        v4_status = check_patch(mock_rea)
        self.assertEqual(v4_status["status"], "applied")
        self.assertTrue(v4_status["auto_discovery_active"])
        self.assertEqual(AUTO_DISCOVERY_SIGNATURE, "AGYIS_REA_AUTODISCOVERY_V4")

        # 2. Exact Antigravity IDE scenario: external steam_dir + symlinked .dirtyroom/binaries
        steam_dir = self.root / "steam_dir"
        steam_dir.mkdir()
        game_exe = steam_dir / "Game.exe"
        game_exe.write_bytes(b"MZGAME_BINARY_BYTES")
        direct_ext_exe = steam_dir / "DirectExt.exe"
        direct_ext_exe.write_bytes(b"MZDIRECT_EXT_BYTES")
        sym_only_exe = steam_dir / "SymOnly.exe"
        sym_only_exe.write_bytes(b"MZSYMONLY_BYTES")

        sha12 = "a1b2c3d4e5f6"
        ws_game = self.root / "ws_game"
        scaffold_dirtyroom(ws_game, project_name="GameProj")
        dr_game = ws_game / ".dirtyroom"
        (dr_game / "binaries").symlink_to(steam_dir, target_is_directory=True)
        (dr_game / "ghidra" / "GameProj.rep").mkdir(parents=True)
        (dr_game / "ghidra" / "GameProj.gpr").write_text("gpr", encoding="utf-8")
        conn = sqlite3.connect(dr_game / "symbols" / "dirtyroom.db")
        conn.execute(
            "INSERT INTO binaries (name, sha256, file_size, created_at) VALUES (?, ?, ?, ?)",
            ("Game.exe", sha12 + "0" * 52, 1024, "2026-11-18T00:00:00Z"),
        )
        conn.commit()
        conn.close()

        reg_file = self.root / "v4_e2e_registry.json"
        reg_res = register_dirtyroom(dr_game, registry_path=reg_file)
        self.assertTrue(reg_res["registered"])
        self.assertEqual(reg_res["binaries"].get(sha12), "Game.exe")

        # Second registered workspace: .dirtyroom symlinked to external non-dot mount, .prp-only match (no DB sha)
        ext_dr_storage = self.root / "ext_storage" / "prp_dirtyroom"
        prp_idata = ext_dr_storage / "ghidra" / "PrpOnlyProj.rep" / "idata" / "00"
        prp_idata.mkdir(parents=True)
        (ext_dr_storage / "ghidra" / "PrpOnlyProj.gpr").write_text("gpr", encoding="utf-8")
        (prp_idata / "00000001.prp").write_text(
            '<?xml version="1.0"?><FILE_INFO><BASIC_INFO>'
            '<STATE NAME="CONTENT_TYPE" TYPE="string" VALUE="Program" />'
            '<STATE NAME="NAME" TYPE="string" VALUE="DirectExt.exe" />'
            '</BASIC_INFO></FILE_INFO>\n',
            encoding="utf-8",
        )
        ws_prp = self.root / "ws_prp_ext"
        ws_prp.mkdir()
        (ws_prp / ".dirtyroom").symlink_to(ext_dr_storage, target_is_directory=True)
        reg_prp = register_dirtyroom(ws_prp / ".dirtyroom", registry_path=reg_file)
        self.assertTrue(reg_prp["registered"])
        self.assertEqual(reg_prp["ghidra_dir"], str((ext_dr_storage / "ghidra").resolve()))

        # Third workspace: UNREGISTERED in registry, tests pre-realpath BinaryTargetResolver symlink capture
        ws_unreg = self.root / "ws_unreg_sym"
        (ws_unreg / ".dirtyroom" / "ghidra" / "UnregProj.rep").mkdir(parents=True)
        (ws_unreg / ".dirtyroom" / "ghidra" / "UnregProj.gpr").write_text("gpr", encoding="utf-8")
        (ws_unreg / ".dirtyroom" / "binaries").symlink_to(steam_dir, target_is_directory=True)
        (ws_unreg / "dirtyroom").symlink_to(".dirtyroom", target_is_directory=True)

        runtime_tmp = self.root / "rea_v4_runtime"
        runtime_tmp.mkdir()

        driver = self.root / "v4_e2e_driver.mjs"
        driver.write_text(
            'import assert from "node:assert/strict";\n'
            'import { ghidraHeadlessArguments } from "./rea-v4-e2e/dist/ghidra/GhidraLauncher.js";\n'
            'import { createGhidraTargetSnapshot } from "./rea-v4-e2e/dist/ghidra/GhidraTargetSnapshot.js";\n'
            'import { resolveBinaryTarget } from "./rea-v4-e2e/dist/application/BinaryTargetResolver.js";\n'
            'const baseOpts = {\n'
            '    platform: "linux",\n'
            '    projectRoot: "/tmp/ephemeral/project",\n'
            '    bridgeScriptPath: "/opt/rea/bridge/Bridge.java",\n'
            '    descriptorPath: "/tmp/ephemeral/session.json",\n'
            '    ghidraLogPath: "/tmp/ephemeral/ghidra.log",\n'
            '    scriptLogPath: "/tmp/ephemeral/script.log",\n'
            '};\n'
            '// Case A: Exact IDE failure — CWD=/tmp, target-<sha12>.bin, ONLY REA_GHIDRA_DIRECT_MOUNT=1 + registry\n'
            'const argsSha = ghidraHeadlessArguments({\n'
            '    ...baseOpts,\n'
            '    targetPath: `/tmp/rea-ghidra-xyz/target-${process.env.TEST_SHA12}.bin`,\n'
            '});\n'
            'assert.equal(argsSha[0], process.env.EXPECTED_GAME_DIR);\n'
            'assert.ok(!argsSha[0].includes("/.dirtyroom/"));\n'
            'assert.equal(argsSha[1], "GameProj");\n'
            'assert.equal(argsSha[2], "-process");\n'
            'assert.equal(argsSha[3], "Game.exe");\n'
            'assert.equal(argsSha[4], "-noanalysis");\n'
            'assert.equal(argsSha[5], "-readOnly");\n'
            '// Case B: Unregistered binary does NOT hijack GameProj — falls back cleanly to -import\n'
            'const argsUnregSha = ghidraHeadlessArguments({\n'
            '    ...baseOpts,\n'
            '    targetPath: "/tmp/rea-ghidra-xyz/target-deadbeef1234.bin",\n'
            '});\n'
            'assert.equal(argsUnregSha[2], "-import");\n'
            'const argsUnregBin = ghidraHeadlessArguments({\n'
            '    ...baseOpts,\n'
            '    targetPath: "/bin/ls",\n'
            '});\n'
            'assert.equal(argsUnregBin[2], "-import");\n'
            '// Case C: Direct external binary path matched strictly via .rep/idata/*.prp in registry\n'
            'const argsPrp = ghidraHeadlessArguments({\n'
            '    ...baseOpts,\n'
            '    targetPath: process.env.DIRECT_EXT_EXE,\n'
            '});\n'
            'assert.equal(argsPrp[0], process.env.EXPECTED_PRP_DIR);\n'
            'assert.equal(argsPrp[1], "PrpOnlyProj");\n'
            'assert.equal(argsPrp[2], "-process");\n'
            'assert.equal(argsPrp[3], "DirectExt.exe");\n'
            'assert.equal(argsPrp[4], "-noanalysis");\n'
            'assert.equal(argsPrp[5], "-readOnly");\n'
            '// Case D: Pre-realpath capture in BinaryTargetResolver recovers symlinked dirtyroom without registry\n'
            'const resolved = await resolveBinaryTarget(process.env.UNREG_SYM_TARGET);\n'
            'assert.ok(!resolved.sourcePath.includes(".dirtyroom"));\n'
            'const snap = await createGhidraTargetSnapshot(resolved.sourcePath, process.env.RUNTIME_TMP, "f".repeat(64));\n'
            'const argsPreRealpath = ghidraHeadlessArguments({ ...baseOpts, targetPath: snap.path });\n'
            'assert.equal(argsPreRealpath[0], process.env.EXPECTED_UNREG_DIR);\n'
            'assert.equal(argsPreRealpath[1], "UnregProj");\n'
            'assert.equal(argsPreRealpath[2], "-process");\n'
            'assert.equal(argsPreRealpath[3], "SymOnly.exe");\n'
            'assert.equal(argsPreRealpath[4], "-noanalysis");\n'
            'assert.equal(argsPreRealpath[5], "-readOnly");\n'
            '// Case E: __agyisToNonDotDir uses realpathSync when .dirtyroom symlinks to non-dot mount (no sibling symlink)\n'
            'process.env.REA_GHIDRA_PROJECT_DIR = process.env.PRP_DOT_GHIDRA;\n'
            'const argsRealNonDot = ghidraHeadlessArguments({ ...baseOpts, targetPath: process.env.DIRECT_EXT_EXE });\n'
            'assert.equal(argsRealNonDot[0], process.env.EXPECTED_PRP_DIR);\n'
            'assert.ok(!argsRealNonDot[0].includes("/.dirtyroom/"));\n'
            'assert.equal(argsRealNonDot[1], "PrpOnlyProj");\n'
            'delete process.env.REA_GHIDRA_PROJECT_DIR;\n'
            '// Case F: Corrupted registry JSON fails closed to -import without throwing\n'
            'process.env.AGYIS_DIRTYROOM_REGISTRY = process.env.CORRUPT_REG;\n'
            'const argsCorrupt = ghidraHeadlessArguments({\n'
            '    ...baseOpts,\n'
            '    targetPath: `/tmp/rea-ghidra-xyz/target-${process.env.TEST_SHA12}.bin`,\n'
            '});\n'
            'assert.equal(argsCorrupt[2], "-import");\n'
            'console.log("V4_NODE_E2E_OK");\n',
            encoding="utf-8",
        )

        corrupt_reg = self.root / "corrupt_registry.json"
        corrupt_reg.write_text("{not valid json!!!", encoding="utf-8")

        # Strictly minimal env: ONLY REA_GHIDRA_DIRECT_MOUNT=1 + AGYIS_DIRTYROOM_REGISTRY (CWD=/tmp!)
        clean_env = {
            "PATH": os.environ.get("PATH", ""),
            "HOME": str(self.root),
            "REA_GHIDRA_DIRECT_MOUNT": "1",
            "AGYIS_DIRTYROOM_REGISTRY": str(reg_file),
            "TEST_SHA12": sha12,
            "EXPECTED_GAME_DIR": str(ws_game / "dirtyroom" / "ghidra"),
            "DIRECT_EXT_EXE": str(direct_ext_exe),
            "EXPECTED_PRP_DIR": str((ext_dr_storage / "ghidra").resolve()),
            "PRP_DOT_GHIDRA": str(ws_prp / ".dirtyroom" / "ghidra"),
            "UNREG_SYM_TARGET": str(ws_unreg / ".dirtyroom" / "binaries" / "SymOnly.exe"),
            "EXPECTED_UNREG_DIR": str(ws_unreg / "dirtyroom" / "ghidra"),
            "RUNTIME_TMP": str(runtime_tmp),
            "CORRUPT_REG": str(corrupt_reg),
        }
        proc = subprocess.run(
            [node_bin, str(driver)],
            cwd="/tmp",
            env=clean_env,
            capture_output=True,
            text=True,
            timeout=10,
        )
        self.assertEqual(proc.returncode, 0, f"V4 Node E2E failed:\nSTDOUT:\n{proc.stdout}\nSTDERR:\n{proc.stderr}")
        self.assertIn("V4_NODE_E2E_OK", proc.stdout)

        # Verify revert_patch cleanly restores all files including BinaryTargetResolver
        self.assertTrue(revert_patch(mock_rea)["success"])
        self.assertEqual(check_patch(mock_rea)["status"], "unapplied")
        self.assertEqual((app_dir / "BinaryTargetResolver.js").read_text(encoding="utf-8"), orig_resolver)

    def test_node_launcher_nan_safe_sort_and_hidden_ancestor_guards(self):
        """Real Node.js test verifying NaN-safe last_seen sorting and hidden-ancestor non-dot guards in launcher_direct_mount.js."""
        node_bin = shutil.which("node")
        if not node_bin:
            self.skipTest("node binary not available in PATH")

        mock_rea = self.root / "rea-hardening"
        (mock_rea / "dist" / "ghidra").mkdir(parents=True)
        (mock_rea / "dist" / "mcp").mkdir(parents=True)
        (mock_rea / "dist" / "application").mkdir(parents=True)
        (mock_rea / "package.json").write_text('{"name":"rea-agents","type":"module"}\n', encoding="utf-8")
        launcher_stub = (
            'import { posix, win32 } from "node:path";\n'
            'export const ghidraHeadlessArguments = (options) => {\n'
            '    const scriptPath = (options.platform ?? process.platform) === "win32" ? win32 : posix;\n'
            '    const bridgeDirectory = scriptPath.dirname(options.bridgeScriptPath);\n'
            '    return [options.projectRoot, "rea-project", "-import", options.targetPath];\n'
            '};\n'
        )
        (mock_rea / "dist" / "ghidra" / "GhidraLauncher.js").write_text(launcher_stub, encoding="utf-8")
        (mock_rea / "dist" / "mcp" / "binary-hardening.js").write_text(launcher_stub, encoding="utf-8")
        (mock_rea / "dist" / "ghidra" / "GhidraTargetSnapshot.js").write_text(
            'import { extname, join } from "node:path";\n'
            'export const createGhidraTargetSnapshot = async (sourcePath, runtimeRoot, expectedSha256) => {\n'
            '    const suffix = extname(sourcePath) || ".bin";\n'
            '    const snapshotPath = join(runtimeRoot, `target-${expectedSha256.slice(0, 12)}${suffix}`);\n'
            '    return { path: snapshotPath, sha256: expectedSha256 };\n'
            '};\n',
            encoding="utf-8",
        )
        (mock_rea / "dist" / "application" / "BinaryTargetResolver.js").write_text(
            'import { realpath } from "node:fs/promises";\n'
            'export const resolveBinaryTarget = async (candidate) => ({ sourcePath: await realpath(candidate) });\n',
            encoding="utf-8",
        )
        self.assertTrue(apply_patch(mock_rea)["success"])

        # 1. NaN-safe last_seen sorting: invalid string entry listed FIRST must lose to valid numeric last_seen entry
        ws_invalid = self.root / "ws_nan_invalid"
        idata_inv = ws_invalid / "dirtyroom" / "ghidra" / "InvalidTsProj.rep" / "idata" / "00"
        idata_inv.mkdir(parents=True)
        (ws_invalid / "dirtyroom" / "ghidra" / "InvalidTsProj.gpr").write_text("gpr", encoding="utf-8")
        (idata_inv / "00000001.prp").write_text(
            '<FILE_INFO><BASIC_INFO><STATE NAME="CONTENT_TYPE" TYPE="string" VALUE="Program" />'
            '<STATE NAME="NAME" TYPE="string" VALUE="SharedApp.exe" /></BASIC_INFO></FILE_INFO>\n',
            encoding="utf-8",
        )

        ws_valid = self.root / "ws_nan_valid"
        idata_val = ws_valid / "dirtyroom" / "ghidra" / "ValidTsProj.rep" / "idata" / "00"
        idata_val.mkdir(parents=True)
        (ws_valid / "dirtyroom" / "ghidra" / "ValidTsProj.gpr").write_text("gpr", encoding="utf-8")
        (idata_val / "00000001.prp").write_text(
            '<FILE_INFO><BASIC_INFO><STATE NAME="CONTENT_TYPE" TYPE="string" VALUE="Program" />'
            '<STATE NAME="NAME" TYPE="string" VALUE="SharedApp.exe" /></BASIC_INFO></FILE_INFO>\n',
            encoding="utf-8",
        )

        nan_reg = self.root / "nan_sort_registry.json"
        nan_reg.write_text(
            json.dumps({
                "version": 1,
                "dirtyrooms": {
                    str(ws_invalid / "dirtyroom" / "ghidra"): {
                        "ghidra_dir": str(ws_invalid / "dirtyroom" / "ghidra"),
                        "last_seen": "invalid",
                        "projects": ["InvalidTsProj"],
                        "binaries": {},
                    },
                    str(ws_valid / "dirtyroom" / "ghidra"): {
                        "ghidra_dir": str(ws_valid / "dirtyroom" / "ghidra"),
                        "last_seen": 500,
                        "projects": ["ValidTsProj"],
                        "binaries": {},
                    },
                },
            }),
            encoding="utf-8",
        )

        # 2. Hidden-ancestor .dirtyroom: must NOT create sibling symlink and must NOT leak dot path
        hidden_dot_ws = self.root / ".hidden_js" / "ws_dot"
        (hidden_dot_ws / ".dirtyroom" / "ghidra").mkdir(parents=True)
        (hidden_dot_ws / ".dirtyroom" / "ghidra" / "HiddenDotProj.gpr").write_text("gpr", encoding="utf-8")
        (hidden_dot_ws / ".dirtyroom" / "binaries").mkdir(parents=True)
        hidden_dot_bin = hidden_dot_ws / ".dirtyroom" / "binaries" / "DotApp.exe"
        hidden_dot_bin.write_bytes(b"MZ")

        # 3. Hidden-ancestor preferred dirtyroom/ghidra: must NOT leak leading-dot ancestor path to Ghidra
        hidden_pref_ws = self.root / ".hidden_js" / "ws_pref"
        (hidden_pref_ws / "dirtyroom" / "ghidra").mkdir(parents=True)
        (hidden_pref_ws / "dirtyroom" / "ghidra" / "HiddenPrefProj.gpr").write_text("gpr", encoding="utf-8")
        (hidden_pref_ws / "dirtyroom" / "binaries").mkdir(parents=True)
        hidden_pref_bin = hidden_pref_ws / "dirtyroom" / "binaries" / "PrefApp.exe"
        hidden_pref_bin.write_bytes(b"MZ")

        driver = self.root / "hardening_driver.mjs"
        driver.write_text(
            'import assert from "node:assert/strict";\n'
            'import { ghidraHeadlessArguments } from "./rea-hardening/dist/ghidra/GhidraLauncher.js";\n'
            'const base = {\n'
            '    platform: "linux", projectRoot: "/tmp/p", bridgeScriptPath: "/b/B.java",\n'
            '    descriptorPath: "/d", ghidraLogPath: "/g", scriptLogPath: "/s",\n'
            '};\n'
            '// Case 1: NaN-safe last_seen sort picks ValidTsProj (last_seen=500) over InvalidTsProj (last_seen="invalid")\n'
            'const argsSort = ghidraHeadlessArguments({ ...base, targetPath: "/tmp/other/SharedApp.exe" });\n'
            'assert.equal(argsSort[0], process.env.EXPECTED_VALID_DIR);\n'
            'assert.equal(argsSort[1], "ValidTsProj");\n'
            'assert.equal(argsSort[2], "-process");\n'
            'assert.equal(argsSort[3], "SharedApp.exe");\n'
            '// Case 2: Hidden-ancestor .dirtyroom via explicit env & auto-discovery falls back cleanly to -import\n'
            'process.env.REA_GHIDRA_PROJECT_DIR = process.env.HIDDEN_DOT_GHIDRA;\n'
            'const argsHiddenEnv = ghidraHeadlessArguments({ ...base, targetPath: process.env.HIDDEN_DOT_BIN });\n'
            'assert.equal(argsHiddenEnv[2], "-import");\n'
            'delete process.env.REA_GHIDRA_PROJECT_DIR;\n'
            'const argsHiddenAuto = ghidraHeadlessArguments({ ...base, targetPath: process.env.HIDDEN_DOT_BIN });\n'
            'assert.equal(argsHiddenAuto[2], "-import");\n'
            '// Case 3: Hidden-ancestor preferred dirtyroom/ghidra does not leak dot-ancestor path into Ghidra\n'
            'const argsHiddenPref = ghidraHeadlessArguments({ ...base, targetPath: process.env.HIDDEN_PREF_BIN });\n'
            'assert.equal(argsHiddenPref[2], "-import");\n'
            'console.log("JS_HARDENING_OK");\n',
            encoding="utf-8",
        )
        env = {
            "PATH": os.environ.get("PATH", ""),
            "HOME": str(self.root),
            "REA_GHIDRA_DIRECT_MOUNT": "1",
            "AGYIS_DIRTYROOM_REGISTRY": str(nan_reg),
            "EXPECTED_VALID_DIR": str(ws_valid / "dirtyroom" / "ghidra"),
            "HIDDEN_DOT_GHIDRA": str(hidden_dot_ws / ".dirtyroom" / "ghidra"),
            "HIDDEN_DOT_BIN": str(hidden_dot_bin),
            "HIDDEN_PREF_BIN": str(hidden_pref_bin),
        }
        proc = subprocess.run(
            [node_bin, str(driver)],
            cwd="/tmp",
            env=env,
            capture_output=True,
            text=True,
            timeout=10,
        )
        self.assertEqual(proc.returncode, 0, f"JS hardening test failed:\nSTDOUT:\n{proc.stdout}\nSTDERR:\n{proc.stderr}")
        self.assertIn("JS_HARDENING_OK", proc.stdout)
        self.assertFalse((hidden_dot_ws / "dirtyroom").exists())
        self.assertFalse((hidden_dot_ws / "dirtyroom").is_symlink())


if __name__ == "__main__":
    unittest.main()
