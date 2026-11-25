#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Arafat Zahan (@kuasha420)
# Corporate Stewardship & Infrastructure: Purrfect Software Limited (PSL)
# Governed by: ICARO-42/b Ordinance (Company-Supported Personal IP Framework)

"""
Global REA mcp_config.json direct-mount wiring and dirtyroom registry tests.
Split from test_re_toolchain.py for sub-second ADR-015 verification.
"""

from __future__ import annotations

import argparse
import io
import json
import os
from pathlib import Path
import shutil
import socket
import sqlite3
import struct
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


class TestGlobalReaDirectMountAndRegistry(unittest.TestCase):
    """Verification of global mcp_config.json wiring and dirtyroom registry management."""

    def setUp(self):
        self.registry_path = _isolate_registry(self)
        self.temp_dir = tempfile.TemporaryDirectory()
        self.root = Path(self.temp_dir.name)

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_configure_rea_mcp_server_emits_direct_mount_and_preserves_user_env_from_non_re_dir(self):
        """Verifies Bugs A & B: REA_GHIDRA_DIRECT_MOUNT=1 emitted globally and user env preserved."""
        from harness.runtime.tool_checks_rea import configure_rea_mcp_server

        cfg_file = self.root / "mcp_config.json"
        fake_jdk = self.root / "jdk-21"
        fake_jdk.mkdir(parents=True)
        (fake_jdk / "release").write_text('JAVA_VERSION="21.0.4"\n', encoding="utf-8")

        # 1. Fresh install from a non-RE dir still emits REA_GHIDRA_DIRECT_MOUNT="1"
        with patch("harness.re.scaffold.get_dirtyroom_root", return_value=None):
            configured, errors = configure_rea_mcp_server(
                config_paths=[cfg_file],
                jdk21_path=fake_jdk,
                ghidra_dir="/opt/ghidra",
            )
        self.assertEqual(errors, [])
        self.assertEqual(configured, [cfg_file])
        fresh_env = json.loads(cfg_file.read_text(encoding="utf-8"))["mcpServers"]["rea"]["env"]
        self.assertEqual(fresh_env["REA_GHIDRA_DIRECT_MOUNT"], "1")
        self.assertEqual(fresh_env["GHIDRA_INSTALL_DIR"], "/opt/ghidra")

        # 2. Reinstall from a non-RE dir preserves pre-existing user-pinned dirtyroom env vars
        pinned = {
            "mcpServers": {
                "rea": {
                    "command": "rea",
                    "args": ["mcp"],
                    "env": {
                        "REA_GHIDRA_PROJECT_DIR": "/pinned/ws/dirtyroom/ghidra",
                        "REA_GHIDRA_PROJECT_NAME": "PinnedProj",
                        "REA_GHIDRA_PROJECT_PATH": "/pinned/ws/dirtyroom/ghidra/PinnedProj.gpr",
                        "REA_GHIDRA_PROGRAM_NAME": "CustomTarget.exe",
                        "AGYIS_DIRTYROOM": "/pinned/ws/.dirtyroom",
                        "IMMORTAL_DIRTYROOM": "/legacy/immortal",
                        "REA_BINARY_MAP": '{"deadbeef1234":"CustomTarget.exe"}',
                    },
                }
            }
        }
        cfg_file.write_text(json.dumps(pinned, indent=2), encoding="utf-8")

        with patch("harness.re.scaffold.get_dirtyroom_root", return_value=None):
            configured, errors = configure_rea_mcp_server(
                config_paths=[cfg_file],
                jdk21_path=fake_jdk,
                ghidra_dir="/opt/ghidra",
            )
        self.assertEqual(errors, [])
        merged_env = json.loads(cfg_file.read_text(encoding="utf-8"))["mcpServers"]["rea"]["env"]
        self.assertEqual(merged_env["REA_GHIDRA_DIRECT_MOUNT"], "1")
        self.assertEqual(merged_env["REA_GHIDRA_PROJECT_DIR"], "/pinned/ws/dirtyroom/ghidra")
        self.assertEqual(merged_env["REA_GHIDRA_PROJECT_NAME"], "PinnedProj")
        self.assertEqual(merged_env["REA_GHIDRA_PROJECT_PATH"], "/pinned/ws/dirtyroom/ghidra/PinnedProj.gpr")
        self.assertEqual(merged_env["REA_GHIDRA_PROGRAM_NAME"], "CustomTarget.exe")
        self.assertEqual(merged_env["AGYIS_DIRTYROOM"], "/pinned/ws/.dirtyroom")
        self.assertEqual(merged_env["IMMORTAL_DIRTYROOM"], "/legacy/immortal")
        self.assertEqual(merged_env["REA_BINARY_MAP"], '{"deadbeef1234":"CustomTarget.exe"}')

        # 3. Explicit user opt-out REA_GHIDRA_DIRECT_MOUNT="0" is respected
        opt_out = json.loads(cfg_file.read_text(encoding="utf-8"))
        opt_out["mcpServers"]["rea"]["env"]["REA_GHIDRA_DIRECT_MOUNT"] = "0"
        cfg_file.write_text(json.dumps(opt_out, indent=2), encoding="utf-8")

        with patch("harness.re.scaffold.get_dirtyroom_root", return_value=None):
            configure_rea_mcp_server(
                config_paths=[cfg_file],
                jdk21_path=fake_jdk,
                ghidra_dir="/opt/ghidra",
            )
        opt_out_env = json.loads(cfg_file.read_text(encoding="utf-8"))["mcpServers"]["rea"]["env"]
        self.assertEqual(opt_out_env["REA_GHIDRA_DIRECT_MOUNT"], "0")

    def test_configure_rea_mcp_server_resolves_nondot_dirtyroom_ghidra_path(self):
        """Verifies Bug C (DEF-BB-038): prefers non-dot dirtyroom/ghidra symlink over .dirtyroom/ghidra."""
        from harness.runtime.tool_checks_rea import configure_rea_mcp_server

        ws = self.root / "re_ws"
        dr = ws / ".dirtyroom"
        (dr / "ghidra").mkdir(parents=True)
        (dr / "ghidra" / "MyProj.gpr").write_text("gpr", encoding="utf-8")
        (ws / "dirtyroom").symlink_to(".dirtyroom", target_is_directory=True)

        cfg_file = self.root / "mcp_re.json"
        fake_jdk = self.root / "jdk-21"
        fake_jdk.mkdir(parents=True)
        (fake_jdk / "release").write_text('JAVA_VERSION="21.0.4"\n', encoding="utf-8")

        with patch("harness.re.scaffold.get_dirtyroom_root", return_value=dr):
            configured, errors = configure_rea_mcp_server(
                config_paths=[cfg_file],
                jdk21_path=fake_jdk,
                ghidra_dir="/opt/ghidra",
            )
        self.assertEqual(errors, [])
        self.assertEqual(configured, [cfg_file])
        env = json.loads(cfg_file.read_text(encoding="utf-8"))["mcpServers"]["rea"]["env"]
        expected_dir = str(ws / "dirtyroom" / "ghidra")
        self.assertEqual(env["REA_GHIDRA_PROJECT_DIR"], expected_dir)
        self.assertEqual(env["REA_GHIDRA_PROJECT_PATH"], str(ws / "dirtyroom" / "ghidra" / "MyProj.gpr"))
        self.assertEqual(env["REA_GHIDRA_PROJECT_NAME"], "MyProj")
        self.assertEqual(env["REA_GHIDRA_DIRECT_MOUNT"], "1")
        self.assertNotIn("/.dirtyroom/", env["REA_GHIDRA_PROJECT_DIR"])
        self.assertNotIn("/.dirtyroom/", env["REA_GHIDRA_PROJECT_PATH"])

        # Also verify auto-creation of non-dot symlink if missing
        ws2 = self.root / "re_ws_nosym"
        dr2 = ws2 / ".dirtyroom"
        (dr2 / "ghidra").mkdir(parents=True)
        (dr2 / "ghidra" / "AutoSym.gpr").write_text("gpr", encoding="utf-8")
        cfg_file2 = self.root / "mcp_re2.json"

        with patch("harness.re.scaffold.get_dirtyroom_root", return_value=dr2):
            configure_rea_mcp_server(
                config_paths=[cfg_file2],
                jdk21_path=fake_jdk,
                ghidra_dir="/opt/ghidra",
            )
        self.assertTrue((ws2 / "dirtyroom").is_symlink())
        env2 = json.loads(cfg_file2.read_text(encoding="utf-8"))["mcpServers"]["rea"]["env"]
        self.assertEqual(env2["REA_GHIDRA_PROJECT_DIR"], str(ws2 / "dirtyroom" / "ghidra"))

        # Verify NO stray symlink is created when .dirtyroom/ghidra/ has zero .gpr files
        ws3 = self.root / "re_ws_empty_ghidra"
        dr3 = ws3 / ".dirtyroom"
        (dr3 / "ghidra").mkdir(parents=True)
        cfg_file3 = self.root / "mcp_re3.json"
        with patch("harness.re.scaffold.get_dirtyroom_root", return_value=dr3):
            configure_rea_mcp_server(
                config_paths=[cfg_file3],
                jdk21_path=fake_jdk,
                ghidra_dir="/opt/ghidra",
            )
        self.assertFalse((ws3 / "dirtyroom").exists())
        self.assertFalse((ws3 / "dirtyroom").is_symlink())
        env3 = json.loads(cfg_file3.read_text(encoding="utf-8"))["mcpServers"]["rea"]["env"]
        self.assertEqual(env3["REA_GHIDRA_DIRECT_MOUNT"], "1")
        self.assertNotIn("REA_GHIDRA_PROJECT_DIR", env3)

        # Verify unrelated regular 'dirtyroom/ghidra' dir does NOT cause mismatched dir/dot-path
        ws4 = self.root / "re_ws_separate_dir"
        dr4 = ws4 / ".dirtyroom"
        (dr4 / "ghidra").mkdir(parents=True)
        (dr4 / "ghidra" / "RealProj.gpr").write_text("gpr", encoding="utf-8")
        (ws4 / "dirtyroom" / "ghidra").mkdir(parents=True)  # unrelated regular dir, NOT symlink
        cfg_file4 = self.root / "mcp_re4.json"
        with patch("harness.re.scaffold.get_dirtyroom_root", return_value=dr4):
            configure_rea_mcp_server(
                config_paths=[cfg_file4],
                jdk21_path=fake_jdk,
                ghidra_dir="/opt/ghidra",
            )
        env4 = json.loads(cfg_file4.read_text(encoding="utf-8"))["mcpServers"]["rea"]["env"]
        self.assertEqual(env4["REA_GHIDRA_DIRECT_MOUNT"], "1")
        self.assertNotIn("REA_GHIDRA_PROJECT_DIR", env4)
        self.assertNotIn("REA_GHIDRA_PROJECT_PATH", env4)

    def test_patcher_upgrades_older_v1_patch_using_orig_and_reverts_cleanly(self):
        """Verifies apply_patch safely upgrades V1-patched installations via .orig backups."""
        mock_rea = self.root / "rea-v1-upgrade"
        ghidra_dir = mock_rea / "dist" / "ghidra"
        mcp_dir = mock_rea / "dist" / "mcp"
        cli_dir = mock_rea / "dist" / "cli-runtime"
        ghidra_dir.mkdir(parents=True)
        mcp_dir.mkdir(parents=True)
        cli_dir.mkdir(parents=True)

        orig_launcher = (
            'import { constants as fsConstants } from "node:fs";\n'
            'import { copyFile, mkdir } from "node:fs/promises";\n'
            'import { posix, win32 } from "node:path";\n'
            'export const ghidraHeadlessArguments = (options) => {\n'
            '    const scriptPath = (options.platform ?? process.platform) === "win32" ? win32 : posix;\n'
            '    const bridgeDirectory = scriptPath.dirname(options.bridgeScriptPath);\n'
            '    return [options.projectRoot, "rea-project", "-import", options.targetPath];\n'
            '};\n'
        )
        orig_snapshot = (
            'import { cp, lstat, mkdir, readdir, realpath } from "node:fs/promises";\n'
            'import { basename, dirname, isAbsolute, join, relative, resolve, sep } from "node:path";\n'
            'export const fingerprintGhidraProject = async (root, name, resources, signal) => {\n'
            '    return "slow-sha256";\n'
            '};\n'
            'export const copyExistingGhidraProject = async (sourcePath, destinationRoot, options = {}) => {\n'
            '    throw new Error("should-not-copy");\n'
            '};\n'
        )
        orig_target_snap = (
            'import { extname, join } from "node:path";\n'
            'const safeExtension = (p) => extname(p) || ".bin";\n'
            'export const createGhidraTargetSnapshot = async (sourcePath, runtimeRoot, expectedSha256, options = {}) => {\n'
            '    const suffix = safeExtension(sourcePath);\n'
            '    const snapshotPath = join(runtimeRoot, `target-${expectedSha256.slice(0, 12)}${suffix}`);\n'
            '    return { path: snapshotPath, sha256: expectedSha256 };\n'
            '};\n'
        )
        orig_bundle = (
            'import { statSync } from "node:fs";\n'
            'import { readdir } from "node:fs/promises";\n'
            'import { dirname, extname, join, posix, resolve, win32 } from "node:path";\n'
            'export const fingerprintGhidraProject = async (root, name, resources, signal) => {\n'
            '    return "slow-bundle-sha";\n'
            '};\n'
            'export const copyExistingGhidraProject = async (sourcePath, destinationRoot, options = {}) => {\n'
            '    throw new Error("should-not-copy-bundle");\n'
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
            '};\n'
        )

        # Simulate an older V1-patched installation with .orig backups present
        launcher = ghidra_dir / "GhidraLauncher.js"
        snapshot = ghidra_dir / "GhidraProjectSnapshot.js"
        target_snap = ghidra_dir / "GhidraTargetSnapshot.js"
        mcp_bin = mcp_dir / "binary-v1test.js"
        cli_bin = cli_dir / "binary-v1cli.js"

        launcher.with_suffix(".js.orig").write_text(orig_launcher, encoding="utf-8")
        snapshot.with_suffix(".js.orig").write_text(orig_snapshot, encoding="utf-8")
        mcp_bin.with_suffix(".js.orig").write_text(orig_bundle, encoding="utf-8")
        cli_bin.with_suffix(".js.orig").write_text(orig_bundle, encoding="utf-8")

        launcher.write_text(orig_launcher.replace("const bridgeDirectory =", "// V1 REA_GHIDRA_PROJECT_DIR\nconst bridgeDirectory ="), encoding="utf-8")
        snapshot.write_text(orig_snapshot.replace('"slow-sha256"', '"0000" // REA_DIRECT_MOUNT_ACTIVE'), encoding="utf-8")
        target_snap.write_text(orig_target_snap, encoding="utf-8")
        mcp_bin.write_text(orig_bundle.replace("const bridgeDirectory =", "// V1 REA_GHIDRA_PROJECT_DIR REA_DIRECT_MOUNT_ACTIVE\nconst bridgeDirectory ="), encoding="utf-8")
        cli_bin.write_text(orig_bundle.replace("const bridgeDirectory =", "// V1 REA_GHIDRA_PROJECT_DIR REA_DIRECT_MOUNT_ACTIVE\nconst bridgeDirectory ="), encoding="utf-8")

        # 1. check_patch detects outdated V1 state as partial with auto_discovery_active=False
        before = check_patch(mock_rea)
        self.assertEqual(before["status"], "partial")
        self.assertTrue(before["launcher_patched"])
        self.assertTrue(before["mcp_patched"])
        self.assertFalse(before["auto_discovery_active"])

        # 2. apply_patch upgrades cleanly from .orig backups without overwriting .orig
        upgrade_res = apply_patch(mock_rea)
        self.assertTrue(upgrade_res["success"], upgrade_res.get("error"))
        self.assertEqual(len(upgrade_res["applied_files"]), 5)

        after = check_patch(mock_rea)
        self.assertEqual(after["status"], "applied")
        self.assertTrue(after["direct_mount_active"])
        self.assertTrue(after["auto_discovery_active"])
        self.assertNotIn("// V1 ", launcher.read_text(encoding="utf-8"))
        self.assertIn(AUTO_DISCOVERY_SIGNATURE, launcher.read_text(encoding="utf-8"))
        self.assertIn(AUTO_DISCOVERY_SIGNATURE, snapshot.read_text(encoding="utf-8"))
        self.assertIn(AUTO_DISCOVERY_SIGNATURE, target_snap.read_text(encoding="utf-8"))
        self.assertEqual(launcher.with_suffix(".js.orig").read_text(encoding="utf-8"), orig_launcher)

        # 3. Re-running apply_patch is idempotent
        second_res = apply_patch(mock_rea)
        self.assertTrue(second_res["success"])
        self.assertEqual(second_res["applied_files"], [])

        # 4. revert_patch restores pristine originals cleanly
        rev = revert_patch(mock_rea)
        self.assertTrue(rev["success"])
        self.assertEqual(launcher.read_text(encoding="utf-8"), orig_launcher)
        self.assertEqual(snapshot.read_text(encoding="utf-8"), orig_snapshot)
        self.assertEqual(target_snap.read_text(encoding="utf-8"), orig_target_snap)
        self.assertEqual(mcp_bin.read_text(encoding="utf-8"), orig_bundle)
        self.assertEqual(check_patch(mock_rea)["status"], "unapplied")

    def test_dirtyroom_registry_registration_nondot_cap_and_pruning(self):
        """Verifies register_dirtyroom non-dot resolution, binaries map, 64-entry LRU cap, pruning, and CLI wiring."""
        from harness.commands.re import cmd_decompile, cmd_status
        from harness.re.preanalyze import preanalyze_binary
        from harness.re.registry import (
            MAX_REGISTRY_ENTRIES,
            load_dirtyroom_registry,
            register_dirtyroom,
        )
        from harness.re.seeding import seed_packets

        reg_file = self.root / "isolated_dirtyrooms.json"

        # 1. Standard .dirtyroom with DB binaries + .gpr + placeholder zero hash ignored
        ws1 = self.root / "ws_std"
        scaffold_dirtyroom(ws1, project_name="StdProj")
        dr1 = ws1 / ".dirtyroom"
        (dr1 / "ghidra" / "StdProj.gpr").write_text("gpr", encoding="utf-8")
        conn = sqlite3.connect(dr1 / "symbols" / "dirtyroom.db")
        conn.execute(
            "INSERT INTO binaries (name, sha256, file_size, created_at) VALUES (?, ?, ?, ?)",
            ("Alpha.exe", "ABCDEF012345" + "9" * 52, 4096, "2026-11-18T00:00:00Z"),
        )
        conn.execute(
            "INSERT INTO binaries (name, sha256, file_size, created_at) VALUES (?, ?, ?, ?)",
            ("Placeholder.exe", "0" * 64, 0, "2026-11-18T00:00:00Z"),
        )
        conn.commit()
        conn.close()

        res1 = register_dirtyroom(dr1, registry_path=reg_file)
        self.assertTrue(res1["registered"])
        self.assertEqual(res1["ghidra_dir"], str(ws1 / "dirtyroom" / "ghidra"))
        self.assertNotIn("/.dirtyroom/", res1["ghidra_dir"])
        self.assertEqual(res1["projects"], ["StdProj"])
        self.assertEqual(res1["binaries"], {"abcdef012345": "Alpha.exe"})

        # 2. Symlinked .dirtyroom pointing to external non-dot directory (NO sibling 'dirtyroom' symlink)
        ext_mount = self.root / "fast_storage" / "re_project_mount"
        (ext_mount / "ghidra").mkdir(parents=True)
        (ext_mount / "ghidra" / "ExtProj.gpr").write_text("gpr", encoding="utf-8")
        ws_ext = self.root / "ws_symlink_dr"
        ws_ext.mkdir()
        (ws_ext / ".dirtyroom").symlink_to(ext_mount, target_is_directory=True)

        res_ext = register_dirtyroom(ws_ext / ".dirtyroom", registry_path=reg_file)
        self.assertTrue(res_ext["registered"])
        self.assertEqual(res_ext["ghidra_dir"], str((ext_mount / "ghidra").resolve()))
        self.assertFalse((ws_ext / "dirtyroom").exists())

        # Deduplication: re-registering via resolved external path keeps single entry for same physical dir
        res_ext_dup = register_dirtyroom(ext_mount, registry_path=reg_file)
        self.assertTrue(res_ext_dup["registered"])
        self.assertEqual(res_ext_dup["entry_count"], 2)

        # 3. Stale pruning: deleting ws_std's ghidra dir removes it on next upsert
        #    Also verify NO stray sibling symlink is created for an empty .dirtyroom/ghidra without .gpr files
        ws_empty = self.root / "ws_empty_no_gpr"
        (ws_empty / ".dirtyroom" / "ghidra").mkdir(parents=True)
        res_empty = register_dirtyroom(ws_empty / ".dirtyroom", registry_path=reg_file)
        self.assertFalse(res_empty["registered"])
        self.assertFalse((ws_empty / "dirtyroom").exists())
        self.assertFalse((ws_empty / "dirtyroom").is_symlink())

        shutil.rmtree(dr1 / "ghidra")
        ws_keep = self.root / "ws_keep"
        (ws_keep / ".dirtyroom" / "ghidra").mkdir(parents=True)
        (ws_keep / ".dirtyroom" / "ghidra" / "KeepProj.gpr").write_text("gpr", encoding="utf-8")
        res_keep = register_dirtyroom(ws_keep / ".dirtyroom", registry_path=reg_file)
        self.assertTrue(res_keep["registered"])
        self.assertTrue((ws_keep / "dirtyroom").is_symlink())
        loaded_after_prune = load_dirtyroom_registry(reg_file)["dirtyrooms"]
        self.assertNotIn(str(ws1 / "dirtyroom" / "ghidra"), loaded_after_prune)
        self.assertEqual(len(loaded_after_prune), 2)

        # 4. Bounded 64-entry LRU eviction cap
        cap_reg = self.root / "cap_registry.json"
        for idx in range(MAX_REGISTRY_ENTRIES + 6):
            w = self.root / f"cap_ws_{idx:03d}"
            (w / "dirtyroom" / "ghidra").mkdir(parents=True)
            register_dirtyroom(w / "dirtyroom", registry_path=cap_reg)
        cap_entries = load_dirtyroom_registry(cap_reg)["dirtyrooms"]
        self.assertEqual(len(cap_entries), MAX_REGISTRY_ENTRIES)
        self.assertNotIn(str(self.root / "cap_ws_000" / "dirtyroom" / "ghidra"), cap_entries)
        self.assertIn(str(self.root / f"cap_ws_{MAX_REGISTRY_ENTRIES + 5:03d}" / "dirtyroom" / "ghidra"), cap_entries)

        # 5. Automatic wiring into preanalyze_binary, cmd_status, cmd_decompile, seed_packets
        #    (scaffold_dirtyroom on a .gpr-less workspace skips registry + symlink creation cleanly)
        wire_ws = self.root / "wire_ws"
        scaffold_dirtyroom(wire_ws, project_name="WireProj")
        self.assertFalse((wire_ws / "dirtyroom").exists())
        self.assertEqual(load_dirtyroom_registry(self.registry_path)["dirtyrooms"], {})
        wire_key = str(wire_ws / "dirtyroom" / "ghidra")

        wire_bin = wire_ws / ".dirtyroom" / "binaries" / "WireApp.exe"
        wire_bin.parent.mkdir(parents=True, exist_ok=True)
        wire_bin.write_bytes(b"MZWIRE_PAYLOAD_12345")
        import hashlib
        wire_sha12 = hashlib.sha256(wire_bin.read_bytes()).hexdigest()[:12]
        (wire_ws / ".dirtyroom" / "ghidra" / "WireProj.gpr").write_text("gpr", encoding="utf-8")

        with patch("harness.re.preanalyze.find_ghidra_headless", return_value=None):
            preanalyze_binary(wire_bin, dirtyroom_dir=wire_ws / ".dirtyroom", project_name="WireProj")
        reg_entry = load_dirtyroom_registry(self.registry_path)["dirtyrooms"][wire_key]
        self.assertEqual(reg_entry["binaries"].get(wire_sha12), "WireApp.exe")
        self.assertEqual(reg_entry["projects"], ["WireProj"])

        # cmd_status & cmd_decompile & seed_packets all refresh registry cleanly
        self.registry_path.unlink()
        out_buf = io.StringIO()
        with patch("harness.commands.re.get_dirtyroom_root", return_value=wire_ws / ".dirtyroom"), \
             patch("harness.commands.re.check_patch", return_value={"status": "applied", "message": "ok"}), \
             patch("harness.commands.re.find_ghidra_headless", return_value=None), \
             patch("sys.stdout", out_buf):
            self.assertEqual(cmd_status(argparse.Namespace(json=True)), 0)
        self.assertIn(wire_key, load_dirtyroom_registry(self.registry_path)["dirtyrooms"])

        self.registry_path.unlink()
        mock_proc = MagicMock(returncode=0, stdout="int main() { return 0; }\n", stderr="")
        with patch("shutil.which", return_value="/usr/local/bin/rea"), \
             patch("subprocess.run", return_value=mock_proc), \
             patch("harness.commands.re.get_dirtyroom_root", return_value=wire_ws / ".dirtyroom"), \
             patch("sys.stdout", io.StringIO()):
            self.assertEqual(
                cmd_decompile(argparse.Namespace(procedure="main", binary=str(wire_bin), no_cache=True, timeout=10.0)),
                0,
            )
        self.assertIn(wire_key, load_dirtyroom_registry(self.registry_path)["dirtyrooms"])

        self.registry_path.unlink()
        pcap_path = wire_ws / ".dirtyroom" / "pcaps" / "wire.pcap"
        pcap_path.write_bytes(_make_synthetic_pcap([(1700000000, 1, 6, "10.0.0.1", "10.0.0.2", 1234, 80, b"hi")]))
        seed_res = seed_packets(pcap_path=pcap_path, binary_name="WireApp.exe", dirtyroom_root=wire_ws / ".dirtyroom")
        self.assertTrue(seed_res["success"])
        self.assertIn(wire_key, load_dirtyroom_registry(self.registry_path)["dirtyrooms"])

    def test_v4_registry_and_launcher_edge_case_regressions(self):
        """Regression tests for relative paths, URI-special chars, null last_seen, SHA-conflict rejection, seed continuation, state-dir parity, and canonical PRP casing."""
        node_bin = shutil.which("node")
        if not node_bin:
            self.skipTest("node binary not available in PATH")

        from harness.re.registry import load_dirtyroom_registry, register_dirtyroom

        # 1. Relative dirtyroom_root resolves to absolute paths in registry (never relative 'dirtyroom/ghidra')
        ws_rel = self.root / "ws_relative"
        (ws_rel / ".dirtyroom" / "ghidra").mkdir(parents=True)
        (ws_rel / ".dirtyroom" / "ghidra" / "RelProj.gpr").write_text("gpr", encoding="utf-8")
        (ws_rel / "dirtyroom").symlink_to(".dirtyroom", target_is_directory=True)
        reg_rel = self.root / "reg_rel.json"
        orig_cwd = os.getcwd()
        try:
            os.chdir(ws_rel)
            res_rel = register_dirtyroom(Path(".dirtyroom"), registry_path=reg_rel)
        finally:
            os.chdir(orig_cwd)
        self.assertTrue(res_rel["registered"])
        self.assertTrue(Path(res_rel["ghidra_dir"]).is_absolute())
        self.assertEqual(res_rel["ghidra_dir"], str(ws_rel / "dirtyroom" / "ghidra"))
        stored_rel = load_dirtyroom_registry(reg_rel)["dirtyrooms"][res_rel["ghidra_dir"]]
        self.assertTrue(Path(stored_rel["dirtyroom_root"]).is_absolute())
        self.assertEqual(stored_rel["workspace"], str(ws_rel))

        # 2. Corrupted/null last_seen in >64-entry registry does not crash register_dirtyroom
        reg_bad = self.root / "reg_bad_ts.json"
        bad_map = {}
        for idx in range(64):
            gdir = self.root / f"ts_ws_{idx}" / "dirtyroom" / "ghidra"
            gdir.mkdir(parents=True)
            bad_map[str(gdir)] = {
                "ghidra_dir": str(gdir),
                "last_seen": None if idx == 0 else ("invalid" if idx == 1 else float(idx)),
            }
        reg_bad.write_text(json.dumps({"version": 1, "dirtyrooms": bad_map}), encoding="utf-8")
        ws_extra = self.root / "ts_ws_extra" / "dirtyroom"
        (ws_extra / "ghidra").mkdir(parents=True)
        res_bad = register_dirtyroom(ws_extra, registry_path=reg_bad)
        self.assertTrue(res_bad["registered"])
        self.assertEqual(res_bad["entry_count"], 64)

        # 3. Paths containing URI-special characters ('#', '?') still read SQLite binaries cleanly
        ws_uri = self.root / "proj#1?v=2"
        (ws_uri / ".dirtyroom" / "ghidra").mkdir(parents=True)
        (ws_uri / ".dirtyroom" / "symbols").mkdir(parents=True)
        (ws_uri / ".dirtyroom" / "ghidra" / "UriProj.gpr").write_text("gpr", encoding="utf-8")
        (ws_uri / "dirtyroom").symlink_to(".dirtyroom", target_is_directory=True)
        conn_uri = sqlite3.connect(ws_uri / ".dirtyroom" / "symbols" / "dirtyroom.db")
        conn_uri.execute("CREATE TABLE binaries (name TEXT, sha256 TEXT)")
        conn_uri.execute("INSERT INTO binaries VALUES (?, ?)", ("UriApp.exe", "123456abcdef" + "0" * 52))
        conn_uri.commit()
        conn_uri.close()
        res_uri = register_dirtyroom(ws_uri / ".dirtyroom", registry_path=self.root / "reg_uri.json")
        self.assertEqual(res_uri["binaries"], {"123456abcdef": "UriApp.exe"})

        # 4. Node E2E for SHA-conflict rejection, multi-seed fallback, PSL_HARNESS_STATE_DIR parity, and PRP casing
        mock_rea = self.root / "rea-reg"
        (mock_rea / "dist" / "ghidra").mkdir(parents=True)
        (mock_rea / "dist" / "mcp").mkdir(parents=True)
        (mock_rea / "dist" / "application").mkdir(parents=True)
        (mock_rea / "package.json").write_text('{"name":"rea-agents","type":"module"}\n', encoding="utf-8")
        (mock_rea / "dist" / "ghidra" / "GhidraLauncher.js").write_text(
            'import { posix, win32 } from "node:path";\n'
            'export const ghidraHeadlessArguments = (options) => {\n'
            '    const scriptPath = (options.platform ?? process.platform) === "win32" ? win32 : posix;\n'
            '    const bridgeDirectory = scriptPath.dirname(options.bridgeScriptPath);\n'
            '    return [options.projectRoot, "rea-project", "-import", options.targetPath];\n'
            '};\n',
            encoding="utf-8",
        )
        (mock_rea / "dist" / "ghidra" / "GhidraTargetSnapshot.js").write_text(
            'import { extname, join } from "node:path";\n'
            'export const createGhidraTargetSnapshot = async (sourcePath, runtimeRoot, expectedSha256) => {\n'
            '    const suffix = extname(sourcePath) || ".bin";\n'
            '    const snapshotPath = join(runtimeRoot, `target-${expectedSha256.slice(0, 12)}${suffix}`);\n'
            '    return { path: snapshotPath, sha256: expectedSha256 };\n'
            '};\n',
            encoding="utf-8",
        )
        (mock_rea / "dist" / "mcp" / "binary-reg.js").write_text(
            'import { posix, win32 } from "node:path";\n'
            'export const ghidraHeadlessArguments = (options) => {\n'
            '    const scriptPath = (options.platform ?? process.platform) === "win32" ? win32 : posix;\n'
            '    const bridgeDirectory = scriptPath.dirname(options.bridgeScriptPath);\n'
            '    return [options.projectRoot, "rea-project", "-import", options.targetPath];\n'
            '};\n',
            encoding="utf-8",
        )
        (mock_rea / "dist" / "application" / "BinaryTargetResolver.js").write_text(
            'import { realpath } from "node:fs/promises";\n'
            'export const resolveBinaryTarget = async (candidate) => {\n'
            '    const canonical = await realpath(candidate);\n'
            '    return { sourcePath: canonical };\n'
            '};\n',
            encoding="utf-8",
        )
        self.assertTrue(apply_patch(mock_rea)["success"])

        # Workspace A: Game.exe (SHA aaaaaaaaaaaa) in ProjA.gpr
        ws_a = self.root / "ws_a"
        idata_a = ws_a / ".dirtyroom" / "ghidra" / "ProjA.rep" / "idata" / "00"
        idata_a.mkdir(parents=True)
        (ws_a / ".dirtyroom" / "ghidra" / "ProjA.gpr").write_text("gpr", encoding="utf-8")
        (idata_a / "00000001.prp").write_text(
            '<FILE_INFO><BASIC_INFO><STATE NAME="CONTENT_TYPE" TYPE="string" VALUE="Program" />'
            '<STATE NAME="NAME" TYPE="string" VALUE="Game.exe" /></BASIC_INFO></FILE_INFO>\n',
            encoding="utf-8",
        )
        (ws_a / ".dirtyroom" / "symbols").mkdir(parents=True)
        conn_a = sqlite3.connect(ws_a / ".dirtyroom" / "symbols" / "dirtyroom.db")
        conn_a.execute("CREATE TABLE binaries (name TEXT, sha256 TEXT)")
        conn_a.execute("INSERT INTO binaries VALUES (?, ?)", ("Game.exe", "a" * 64))
        conn_a.commit()
        conn_a.close()
        (ws_a / "dirtyroom").symlink_to(".dirtyroom", target_is_directory=True)

        # Workspace B: AppB.exe in ProjB.gpr (unregistered), symlinked from ws_a/.dirtyroom/binaries/AppB.exe
        ws_b = self.root / "ws_b"
        idata_b = ws_b / ".dirtyroom" / "ghidra" / "ProjB.rep" / "idata" / "00"
        idata_b.mkdir(parents=True)
        (ws_b / ".dirtyroom" / "ghidra" / "ProjB.gpr").write_text("gpr", encoding="utf-8")
        (idata_b / "00000001.prp").write_text(
            '<FILE_INFO><BASIC_INFO><STATE NAME="CONTENT_TYPE" TYPE="string" VALUE="Program" />'
            '<STATE NAME="NAME" TYPE="string" VALUE="AppB.exe" /></BASIC_INFO></FILE_INFO>\n',
            encoding="utf-8",
        )
        (ws_b / ".dirtyroom" / "binaries").mkdir(parents=True)
        app_b_real = ws_b / ".dirtyroom" / "binaries" / "AppB.exe"
        app_b_real.write_bytes(b"MZB")
        (ws_b / "dirtyroom").symlink_to(".dirtyroom", target_is_directory=True)
        (ws_a / ".dirtyroom" / "binaries").mkdir(parents=True)
        app_b_link = ws_a / ".dirtyroom" / "binaries" / "AppB.exe"
        app_b_link.symlink_to(app_b_real)

        # Unrelated v2 Game.exe outside any dirtyroom (SHA cccccccccccc != aaaaaaaaaaaa)
        ext_v2 = self.root / "ext_v2"
        ext_v2.mkdir()
        game_v2 = ext_v2 / "Game.exe"
        game_v2.write_bytes(b"MZv2")

        # Register ws_a into PSL_HARNESS_STATE_DIR/agyis_dirtyrooms.json
        state_dir = self.root / "state_dir_e2e"
        state_dir.mkdir()
        register_dirtyroom(ws_a / ".dirtyroom", registry_path=state_dir / "agyis_dirtyrooms.json")

        driver = self.root / "reg_e2e_driver.mjs"
        driver.write_text(
            'import assert from "node:assert/strict";\n'
            'import { ghidraHeadlessArguments } from "./rea-reg/dist/ghidra/GhidraLauncher.js";\n'
            'import { createGhidraTargetSnapshot } from "./rea-reg/dist/ghidra/GhidraTargetSnapshot.js";\n'
            'import { resolveBinaryTarget } from "./rea-reg/dist/application/BinaryTargetResolver.js";\n'
            'const base = {\n'
            '    platform: "linux", projectRoot: "/tmp/p", bridgeScriptPath: "/b/B.java",\n'
            '    descriptorPath: "/d", ghidraLogPath: "/g", scriptLogPath: "/s",\n'
            '};\n'
            '// 4a. PSL_HARNESS_STATE_DIR parity resolves SHA aaaaaaaaaaaa without AGYIS_DIRTYROOM_REGISTRY\n'
            'const argsState = ghidraHeadlessArguments({ ...base, targetPath: "/tmp/target-aaaaaaaaaaaa.exe" });\n'
            'assert.equal(argsState[0], process.env.EXPECTED_WSA_DIR);\n'
            'assert.equal(argsState[1], "ProjA");\n'
            'assert.equal(argsState[2], "-process");\n'
            'assert.equal(argsState[3], "Game.exe");\n'
            '// 4b. Different SHA (cccccccccccc) with same filename Game.exe MUST NOT hijack ProjA\n'
            'const snapV2 = await createGhidraTargetSnapshot(process.env.GAME_V2, "/tmp", "c".repeat(64));\n'
            'const argsConflict = ghidraHeadlessArguments({ ...base, targetPath: snapV2.path });\n'
            'assert.equal(argsConflict[2], "-import");\n'
            '// 4c. Symlink inside ws_a pointing to ws_b continues past non-matching ws_a to match ProjB\n'
            'const resB = await resolveBinaryTarget(process.env.APPB_LINK);\n'
            'const snapB = await createGhidraTargetSnapshot(resB.sourcePath, "/tmp", "d".repeat(64));\n'
            'const argsSeed = ghidraHeadlessArguments({ ...base, targetPath: snapB.path });\n'
            'assert.equal(argsSeed[0], process.env.EXPECTED_WSB_DIR);\n'
            'assert.equal(argsSeed[1], "ProjB");\n'
            'assert.equal(argsSeed[2], "-process");\n'
            'assert.equal(argsSeed[3], "AppB.exe");\n'
            '// 4d. Case-insensitive .prp match passes canonical PRP program casing ("Game.exe") to -process\n'
            'const argsCase = ghidraHeadlessArguments({ ...base, targetPath: `${process.env.WSA}/.dirtyroom/binaries/game.exe` });\n'
            'assert.equal(argsCase[1], "ProjA");\n'
            'assert.equal(argsCase[2], "-process");\n'
            'assert.equal(argsCase[3], "Game.exe");\n'
            'console.log("V4_REGRESSIONS_OK");\n',
            encoding="utf-8",
        )
        env = {
            "PATH": os.environ.get("PATH", ""),
            "HOME": str(self.root),
            "REA_GHIDRA_DIRECT_MOUNT": "1",
            "PSL_HARNESS_STATE_DIR": str(state_dir),
            "EXPECTED_WSA_DIR": str(ws_a / "dirtyroom" / "ghidra"),
            "EXPECTED_WSB_DIR": str(ws_b / "dirtyroom" / "ghidra"),
            "WSA": str(ws_a),
            "GAME_V2": str(game_v2),
            "APPB_LINK": str(app_b_link),
        }
        proc = subprocess.run(
            [node_bin, str(driver)],
            cwd="/tmp",
            env=env,
            capture_output=True,
            text=True,
            timeout=10,
        )
        self.assertEqual(proc.returncode, 0, f"V4 regression E2E failed:\nSTDOUT:\n{proc.stdout}\nSTDERR:\n{proc.stderr}")
        self.assertIn("V4_REGRESSIONS_OK", proc.stdout)

    def test_try_register_dirtyroom_diagnostics_and_json_stdout_purity(self):
        """Verifies try_register_dirtyroom surfaces OSError warnings via stderr + result dicts while keeping JSON stdout clean."""
        from harness.commands.re import cmd_decompile, cmd_status
        from harness.re.preanalyze import preanalyze_binary
        from harness.re.registry import try_register_dirtyroom
        from harness.re.seeding import seed_packets

        # Regular file used as parent directory triggers deterministic NotADirectoryError (OSError) even as root
        blocker_file = self.root / "reg_parent_blocker"
        blocker_file.write_text("not-a-directory", encoding="utf-8")
        unwritable_reg = blocker_file / "agyis_dirtyrooms.json"

        ws = self.root / "ws_warn"
        err_buf = io.StringIO()
        with patch.dict(os.environ, {"AGYIS_DIRTYROOM_REGISTRY": str(unwritable_reg)}), \
             patch("sys.stderr", err_buf):
            scaf_res = scaffold_dirtyroom(ws, project_name="WarnProj")
        self.assertTrue(scaf_res["success"])
        # .gpr-less init does not register or create root symlink, so no registry write warning yet
        self.assertNotIn("registry_warning", scaf_res)

        dr = ws / ".dirtyroom"
        (dr / "ghidra" / "WarnProj.gpr").write_text("gpr", encoding="utf-8")

        # Re-scaffolding once a .gpr exists surfaces registry OSError via stderr + result dict
        err_buf_gpr = io.StringIO()
        with patch.dict(os.environ, {"AGYIS_DIRTYROOM_REGISTRY": str(unwritable_reg)}), \
             patch("sys.stderr", err_buf_gpr):
            scaf_res_gpr = scaffold_dirtyroom(ws, project_name="WarnProj")
        self.assertTrue(scaf_res_gpr["success"])
        self.assertIn("registry_warning", scaf_res_gpr)
        self.assertIn("Failed to update global dirtyroom registry", scaf_res_gpr["registry_warning"])
        self.assertIn("[!] Warning: Failed to update global dirtyroom registry", err_buf_gpr.getvalue())

        # Direct helper with emit_stderr=False returns warning without touching stderr
        silent_err = io.StringIO()
        with patch("sys.stderr", silent_err):
            reg_res, reg_warn = try_register_dirtyroom(dr, registry_path=unwritable_reg, emit_stderr=False)
        self.assertIsNone(reg_res)
        self.assertIsNotNone(reg_warn)
        self.assertEqual(silent_err.getvalue(), "")

        # cmd_status --json: stdout must remain strictly valid JSON carrying registry_warning; warning goes to stderr
        out_buf = io.StringIO()
        err_buf = io.StringIO()
        with patch.dict(os.environ, {"AGYIS_DIRTYROOM_REGISTRY": str(unwritable_reg)}), \
             patch("harness.commands.re.get_dirtyroom_root", return_value=dr), \
             patch("harness.commands.re.check_patch", return_value={"status": "applied", "message": "ok"}), \
             patch("harness.commands.re.find_ghidra_headless", return_value=None), \
             patch("sys.stdout", out_buf), \
             patch("sys.stderr", err_buf):
            self.assertEqual(cmd_status(argparse.Namespace(json=True)), 0)
        parsed_status = json.loads(out_buf.getvalue())
        self.assertIn("registry_warning", parsed_status)
        self.assertIn("[!] Warning: Failed to update global dirtyroom registry", err_buf.getvalue())

        # preanalyze_binary (no headless path + headless success path)
        bin_path = dr / "binaries" / "WarnApp.exe"
        bin_path.parent.mkdir(parents=True, exist_ok=True)
        bin_path.write_bytes(b"MZWARN_PAYLOAD")

        err_buf = io.StringIO()
        with patch.dict(os.environ, {"AGYIS_DIRTYROOM_REGISTRY": str(unwritable_reg)}), \
             patch("harness.re.preanalyze.find_ghidra_headless", return_value=None), \
             patch("sys.stderr", err_buf):
            pre_no_hl = preanalyze_binary(bin_path, dirtyroom_dir=dr, project_name="WarnProj")
        self.assertFalse(pre_no_hl["success"])
        self.assertIn("registry_warning", pre_no_hl)
        self.assertIn("[!] Warning: Failed to update global dirtyroom registry", err_buf.getvalue())

        err_buf = io.StringIO()
        mock_hl_proc = MagicMock(returncode=0)
        with patch.dict(os.environ, {"AGYIS_DIRTYROOM_REGISTRY": str(unwritable_reg)}), \
             patch("harness.re.preanalyze.find_ghidra_headless", return_value=Path("/opt/ghidra/analyzeHeadless")), \
             patch("harness.re.preanalyze.subprocess.run", return_value=mock_hl_proc), \
             patch("sys.stderr", err_buf):
            pre_ok = preanalyze_binary(bin_path, dirtyroom_dir=dr, project_name="WarnProj")
        self.assertTrue(pre_ok["success"])
        self.assertIn("registry_warning", pre_ok)
        self.assertIn("[!] Warning: Failed to update global dirtyroom registry", err_buf.getvalue())

        # seed_packets surfaces registry_warning and writes to stderr
        pcap_path = dr / "pcaps" / "warn.pcap"
        pcap_path.write_bytes(_make_synthetic_pcap([(1700000000, 1, 6, "10.0.0.1", "10.0.0.2", 1234, 80, b"hi")]))
        err_buf = io.StringIO()
        with patch.dict(os.environ, {"AGYIS_DIRTYROOM_REGISTRY": str(unwritable_reg)}), \
             patch("sys.stderr", err_buf):
            seed_res = seed_packets(pcap_path=pcap_path, binary_name="WarnApp.exe", dirtyroom_root=dr)
        self.assertTrue(seed_res["success"])
        self.assertIn("registry_warning", seed_res)
        self.assertIn("[!] Warning: Failed to update global dirtyroom registry", err_buf.getvalue())

        # cmd_decompile emits warning to stderr without blocking decompilation
        out_buf = io.StringIO()
        err_buf = io.StringIO()
        mock_dec = MagicMock(returncode=0, stdout="int main() { return 0; }\n", stderr="")
        with patch.dict(os.environ, {"AGYIS_DIRTYROOM_REGISTRY": str(unwritable_reg)}), \
             patch("shutil.which", return_value="/usr/local/bin/rea"), \
             patch("subprocess.run", return_value=mock_dec), \
             patch("harness.commands.re.get_dirtyroom_root", return_value=dr), \
             patch("sys.stdout", out_buf), \
             patch("sys.stderr", err_buf):
            code = cmd_decompile(argparse.Namespace(procedure="main", binary=str(bin_path), no_cache=True, timeout=10.0))
        self.assertEqual(code, 0)
        self.assertIn("int main()", out_buf.getvalue())
        self.assertIn("[!] Warning: Failed to update global dirtyroom registry", err_buf.getvalue())

    def test_read_registered_binaries_streams_and_caps_at_max(self):
        """Verifies _read_registered_binaries streams via cursor iteration without fetchall() and caps at MAX_BINARIES_PER_DIRTYROOM."""
        from harness.re.registry import MAX_BINARIES_PER_DIRTYROOM, _read_registered_binaries

        dr = self.root / "ws_stream" / ".dirtyroom"
        (dr / "symbols").mkdir(parents=True)
        db_path = dr / "symbols" / "dirtyroom.db"
        total_rows = MAX_BINARIES_PER_DIRTYROOM + 40
        conn = sqlite3.connect(db_path)
        conn.execute("CREATE TABLE binaries (name TEXT, sha256 TEXT)")
        conn.executemany(
            "INSERT INTO binaries VALUES (?, ?)",
            [(f"bin_{idx:04d}.exe", f"{idx + 1:012x}" + "a" * 52) for idx in range(total_rows)],
        )
        conn.commit()
        conn.close()

        rows_yielded = 0
        real_connect = sqlite3.connect

        class _StreamingCursorProxy:
            def __init__(self, inner):
                self._inner = inner

            def fetchall(self):
                raise AssertionError("_read_registered_binaries must stream rows instead of calling fetchall()")

            def __iter__(self):
                nonlocal rows_yielded
                for row in self._inner:
                    rows_yielded += 1
                    yield row

            def close(self):
                self._inner.close()

        class _StreamingConnProxy:
            def __init__(self, inner):
                self._inner = inner

            def execute(self, sql, *args, **kwargs):
                return _StreamingCursorProxy(self._inner.execute(sql, *args, **kwargs))

            def close(self):
                self._inner.close()

        with patch("harness.re.registry.sqlite3.connect", side_effect=lambda *a, **kw: _StreamingConnProxy(real_connect(*a, **kw))):
            binaries = _read_registered_binaries(dr)

        self.assertEqual(len(binaries), MAX_BINARIES_PER_DIRTYROOM)
        self.assertEqual(rows_yielded, MAX_BINARIES_PER_DIRTYROOM + 1)

    def test_resolve_nondot_ghidra_dir_hidden_ancestor_guard(self):
        """Verifies resolve_nondot_ghidra_dir returns None and avoids creating a useless symlink under a dot-prefixed ancestor."""
        from harness.re.registry import resolve_nondot_ghidra_dir

        hidden_ws = self.root / ".hidden" / "ws"
        hidden_dr = hidden_ws / ".dirtyroom"
        (hidden_dr / "ghidra").mkdir(parents=True)
        (hidden_dr / "ghidra" / "HiddenProj.gpr").write_text("gpr", encoding="utf-8")

        self.assertIsNone(resolve_nondot_ghidra_dir(hidden_dr))
        self.assertFalse((hidden_ws / "dirtyroom").exists())
        self.assertFalse((hidden_ws / "dirtyroom").is_symlink())


if __name__ == "__main__":
    unittest.main()
