# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Arafat Zahan (@kuasha420)
# Corporate Stewardship & Infrastructure: Purrfect Software Limited (PSL)
# Governed by: ICARO-42/b Ordinance (Company-Supported Personal IP Framework)

"""
REA Ghidra Pre-Analyzed Project Acceleration Patcher (ADR-028, PSL-INV-009).
Enables sub-2-second decompilation on large (>10MB) binaries by patching the
installed REA MCP server to reuse pre-analyzed Ghidra projects with -noanalysis -readOnly
and bypass redundant 1.3GB disk cloning (Optimization 2: Direct In-Place Mount).
"""

import json
import os
from pathlib import Path
import re
import shutil
import subprocess
from typing import Any, Dict, List, Optional, Tuple

from harness.runtime.tool_checks_rea import is_ghidra_12_2_installed

PATCH_SIGNATURE = "REA_GHIDRA_PROJECT_DIR"
DIRECT_MOUNT_SIGNATURE = "REA_DIRECT_MOUNT_ACTIVE"

LAUNCHER_SNIPPET = """    const projectDir = process.env.REA_GHIDRA_PROJECT_DIR || (process.env.AGYIS_DIRTYROOM ? scriptPath.join(process.env.AGYIS_DIRTYROOM, "ghidra") : (process.env.IMMORTAL_DIRTYROOM ? scriptPath.join(process.env.IMMORTAL_DIRTYROOM, "ghidra") : undefined));
    const projectName = process.env.REA_GHIDRA_PROJECT_NAME || (process.env.AGYIS_DIRTYROOM_PROJECT || (process.env.IMMORTAL_DIRTYROOM ? "PaladinsProject" : undefined));
    let targetBase = scriptPath.basename(options.targetPath);
    const BINARY_MAP = {
        "0c51d381dfe9": "ShippingPC-ChaosGame.exe",
        "90ce02b7b820": "MctsInterface.dll",
        "1c4ad378fb8c": "vivoxsdk_x64.dll"
    };
    if (process.env.REA_BINARY_MAP) {
        try { Object.assign(BINARY_MAP, JSON.parse(process.env.REA_BINARY_MAP)); } catch {}
    }
    if (process.env.REA_GHIDRA_PROGRAM_NAME) {
        targetBase = process.env.REA_GHIDRA_PROGRAM_NAME;
    } else if (targetBase.startsWith("target-")) {
        const prefix = targetBase.slice(7, 19);
        if (BINARY_MAP[prefix]) {
            targetBase = BINARY_MAP[prefix];
        }
    }
    if (projectDir && !options.rawBinary && !options.dosMz && !options.dosCom && options.gamecubeDol === undefined && options.psp !== true) {
        try {
            let activeProject = projectName;
            if (!activeProject) {
                const files = readdirSync(projectDir);
                const gpr = files.find(f => f.endsWith(".gpr"));
                if (gpr) activeProject = gpr.slice(0, -4);
            }
            if (activeProject) {
                const gprPath = scriptPath.join(projectDir, `${activeProject}.gpr`);
                statSync(gprPath);
                return [
                    projectDir,
                    activeProject,
                    "-process",
                    targetBase,
                    "-noanalysis",
                    "-readOnly",
                    "-log",
                    options.ghidraLogPath,
                    "-scriptlog",
                    options.scriptLogPath,
                    "-scriptPath",
                    bridgeDirectory,
                    "-postScript",
                    options.bridgeScriptPath,
                    options.descriptorPath
                ];
            }
        } catch {}
    }
"""

FASTPATH_FINGERPRINT_SNIPPET = """    if (process.env.REA_GHIDRA_DIRECT_MOUNT !== "0" && (process.env.REA_GHIDRA_PROJECT_DIR || process.env.AGYIS_DIRTYROOM || process.env.IMMORTAL_DIRTYROOM)) {
        return "0000000000000000000000000000000000000000000000000000000000000000"; // REA_DIRECT_MOUNT_ACTIVE: 64-hex SHA256 bypass
    }
"""

FASTPATH_COPY_SNIPPET = """    if (process.env.REA_GHIDRA_DIRECT_MOUNT !== "0" && (process.env.REA_GHIDRA_PROJECT_DIR || process.env.AGYIS_DIRTYROOM || process.env.IMMORTAL_DIRTYROOM)) {
        return; // REA_DIRECT_MOUNT_ACTIVE: Bypass 1.3GB disk copy
    }
"""


def find_rea_package_root() -> Optional[Path]:
    """Discovers the installed rea-agents npm/pnpm package directory."""
    # 1. Explicit env override
    env_path = os.environ.get("REA_PACKAGE_PATH")
    if env_path:
        p = Path(env_path).resolve()
        if p.is_dir() and (p / "dist").is_dir():
            return p

    # 2. Check rea CLI executable path
    rea_bin = shutil.which("rea")
    if rea_bin:
        try:
            real_bin = Path(rea_bin).resolve()
            curr = real_bin.parent
            while curr != curr.parent:
                if (curr / "node_modules" / "rea-agents" / "dist").is_dir():
                    return (curr / "node_modules" / "rea-agents").resolve()
                if (curr / "dist" / "ghidra").is_dir() and (curr / "package.json").is_file():
                    try:
                        pkg = json.loads((curr / "package.json").read_text(encoding="utf-8"))
                        if pkg.get("name") == "rea-agents":
                            return curr.resolve()
                    except Exception:
                        pass
                curr = curr.parent
        except Exception:
            pass

    # 3. Known global pnpm locations
    home = Path.home()
    pnpm_global = home / ".local" / "share" / "pnpm" / "global"
    if pnpm_global.is_dir():
        for cand in pnpm_global.glob("**/node_modules/rea-agents"):
            if (cand / "dist" / "ghidra").is_dir():
                return cand.resolve()

    # 4. Standard npm/yarn global paths
    for base in [
        Path("/usr/local/lib/node_modules/rea-agents"),
        Path("/usr/lib/node_modules/rea-agents"),
        home / ".npm-global" / "lib" / "node_modules" / "rea-agents",
    ]:
        if (base / "dist" / "ghidra").is_dir():
            return base.resolve()

    return None


def get_patch_targets(rea_root: Optional[Path] = None) -> Tuple[Optional[Path], Optional[Path]]:
    """Returns (launcher_path, mcp_binary_path) within rea-agents package for backward compatibility."""
    targets = get_all_patch_targets(rea_root)
    return targets.get("launcher"), targets.get("mcp_binary")


def get_all_patch_targets(rea_root: Optional[Path] = None) -> Dict[str, Optional[Path]]:
    """Returns all patch target paths within rea-agents package."""
    root = rea_root or find_rea_package_root()
    if not root:
        return {}

    launcher = root / "dist" / "ghidra" / "GhidraLauncher.js"
    snapshot = root / "dist" / "ghidra" / "GhidraProjectSnapshot.js"
    policy = root / "dist" / "ghidra" / "GhidraReleasePolicy.js"

    mcp_dir = root / "dist" / "mcp"
    mcp_binary: Optional[Path] = None
    if mcp_dir.is_dir():
        for cand in mcp_dir.glob("binary-*.js"):
            if not cand.name.endswith(".orig"):
                try:
                    content = cand.read_text(encoding="utf-8", errors="ignore")
                    if "ghidraHeadlessArguments" in content:
                        mcp_binary = cand
                        break
                except Exception:
                    pass

    cli_dir = root / "dist" / "cli-runtime"
    cli_binary: Optional[Path] = None
    if cli_dir.is_dir():
        for cand in cli_dir.glob("binary-*.js"):
            if not cand.name.endswith(".orig"):
                try:
                    content = cand.read_text(encoding="utf-8", errors="ignore")
                    if "ghidraHeadlessArguments" in content:
                        cli_binary = cand
                        break
                except Exception:
                    pass

    return {
        "launcher": launcher if launcher.is_file() else None,
        "snapshot": snapshot if snapshot.is_file() else None,
        "mcp_binary": mcp_binary,
        "cli_binary": cli_binary,
        "policy": policy if policy.is_file() else None,
    }


def check_patch(rea_root: Optional[Path] = None) -> Dict[str, Any]:
    """Inspects whether the Ghidra acceleration patch is currently applied."""
    root = rea_root or find_rea_package_root()
    if not root:
        return {
            "status": "not_installed",
            "rea_root": None,
            "launcher_patched": False,
            "mcp_patched": False,
            "snapshot_patched": False,
            "cli_patched": False,
            "direct_mount_active": False,
            "launcher_path": None,
            "mcp_path": None,
            "message": "REA (rea-agents) package could not be found.",
        }

    targets = get_all_patch_targets(root)
    launcher = targets.get("launcher")
    mcp_binary = targets.get("mcp_binary")
    snapshot = targets.get("snapshot")
    cli_binary = targets.get("cli_binary")
    policy_file = targets.get("policy")

    launcher_patched = False
    mcp_patched = False
    snapshot_patched = False
    cli_patched = False
    policy_patched = False

    if launcher and launcher.is_file():
        try:
            content = launcher.read_text(encoding="utf-8", errors="ignore")
            launcher_patched = PATCH_SIGNATURE in content
        except Exception:
            pass

    if mcp_binary and mcp_binary.is_file():
        try:
            content = mcp_binary.read_text(encoding="utf-8", errors="ignore")
            mcp_patched = PATCH_SIGNATURE in content
        except Exception:
            pass

    if snapshot and snapshot.is_file():
        try:
            content = snapshot.read_text(encoding="utf-8", errors="ignore")
            snapshot_patched = DIRECT_MOUNT_SIGNATURE in content
        except Exception:
            pass

    if cli_binary and cli_binary.is_file():
        try:
            content = cli_binary.read_text(encoding="utf-8", errors="ignore")
            cli_patched = PATCH_SIGNATURE in content and DIRECT_MOUNT_SIGNATURE in content
        except Exception:
            pass

    if policy_file and policy_file.is_file():
        try:
            p_content = policy_file.read_text(encoding="utf-8", errors="ignore")
            policy_patched = 'SUPPORTED_GHIDRA_VERSION = "12.2"' in p_content
        except Exception:
            pass

    direct_mount_active = (
        (not snapshot or snapshot_patched)
        and (not cli_binary or cli_patched)
        and (not mcp_binary or (DIRECT_MOUNT_SIGNATURE in (mcp_binary.read_text(encoding="utf-8", errors="ignore") if mcp_binary.is_file() else "")))
    )

    if launcher_patched and mcp_patched and direct_mount_active:
        status = "applied"
        msg = "REA pre-analyzed Ghidra project acceleration patch & zero-copy direct mount active."
    elif launcher_patched and mcp_patched:
        status = "applied"
        msg = "REA pre-analyzed Ghidra project acceleration patch is active."
    elif launcher_patched or mcp_patched:
        status = "partial"
        msg = "REA patch is partially applied (inconsistent launcher/mcp bundle)."
    else:
        status = "unapplied"
        msg = "REA patch is not applied (ad-hoc temporary analysis pass will occur)."

    return {
        "status": status,
        "rea_root": str(root),
        "launcher_patched": launcher_patched,
        "mcp_patched": mcp_patched,
        "snapshot_patched": snapshot_patched,
        "cli_patched": cli_patched,
        "direct_mount_active": direct_mount_active,
        "policy_patched": policy_patched,
        "launcher_path": str(launcher) if launcher else None,
        "mcp_path": str(mcp_binary) if mcp_binary else None,
        "cli_path": str(cli_binary) if cli_binary else None,
        "policy_path": str(policy_file) if policy_file else None,
        "message": msg,
    }


def apply_patch(rea_root: Optional[Path] = None) -> Dict[str, Any]:
    """Applies the pre-analyzed Ghidra acceleration patch and zero-copy direct mount to the REA installation."""
    root = rea_root or find_rea_package_root()
    if not root:
        return {"success": False, "error": "REA package root not found"}

    targets = get_all_patch_targets(root)
    launcher = targets.get("launcher")
    mcp_binary = targets.get("mcp_binary")
    snapshot = targets.get("snapshot")
    cli_binary = targets.get("cli_binary")
    policy_file = targets.get("policy")

    if not launcher or not launcher.is_file():
        return {"success": False, "error": "GhidraLauncher.js not found in REA distribution"}
    if not mcp_binary or not mcp_binary.is_file():
        return {"success": False, "error": "binary-*.js not found in REA MCP distribution"}

    applied_files: List[str] = []

    # Helper to backup to .orig once
    def ensure_backup(file_path: Path, content: str) -> None:
        orig = file_path.with_suffix(".js.orig")
        if not orig.is_file():
            orig.write_text(content, encoding="utf-8")

    # 1. Patch GhidraLauncher.js
    l_content = launcher.read_text(encoding="utf-8")
    if PATCH_SIGNATURE not in l_content:
        ensure_backup(launcher, l_content)

        if 'import { statSync' not in l_content and 'import { readdirSync' not in l_content:
            l_content = re.sub(
                r'(import \{[^\}]*?\}\s*from\s*"node:fs/promises";)',
                r'import { readdirSync, statSync } from "node:fs";\n\1',
                l_content,
                count=1,
            )
        elif 'readdirSync' not in l_content:
            l_content = l_content.replace('import { statSync', 'import { readdirSync, statSync')

        target_marker = "const bridgeDirectory = scriptPath.dirname(options.bridgeScriptPath);"
        if target_marker in l_content:
            l_content = l_content.replace(
                target_marker,
                f"{target_marker}\n{LAUNCHER_SNIPPET}",
                1,
            )
            launcher.write_text(l_content, encoding="utf-8")
            applied_files.append(str(launcher))
        else:
            return {"success": False, "error": f"Target marker not found in {launcher.name}"}

    # 2. Patch GhidraProjectSnapshot.js (Zero-copy Direct Mount fastpath)
    if snapshot and snapshot.is_file():
        s_content = snapshot.read_text(encoding="utf-8")
        if DIRECT_MOUNT_SIGNATURE not in s_content:
            ensure_backup(snapshot, s_content)

            s_content = re.sub(
                r"(fingerprintGhidraProject\s*=\s*async\s*\([^)]*\)\s*=>\s*\{)",
                r"\1\n" + FASTPATH_FINGERPRINT_SNIPPET,
                s_content,
                count=1,
            )
            s_content = re.sub(
                r"(copyExistingGhidraProject\s*=\s*async\s*\([^)]*\)\s*=>\s*\{)",
                r"\1\n" + FASTPATH_COPY_SNIPPET,
                s_content,
                count=1,
            )
            snapshot.write_text(s_content, encoding="utf-8")
            applied_files.append(str(snapshot))

    # 3. Patch dist/mcp/binary-*.js
    m_content = mcp_binary.read_text(encoding="utf-8")
    m_modified = False
    if PATCH_SIGNATURE not in m_content or DIRECT_MOUNT_SIGNATURE not in m_content:
        ensure_backup(mcp_binary, m_content)

        if 'readdirSync' not in m_content:
            m_content = re.sub(
                r'(import \{[^\}]*statSync[^\}]*\}\s*from\s*"node:fs";)',
                lambda m: m.group(0).replace('statSync', 'readdirSync, statSync'),
                m_content,
                count=1,
            )
            m_modified = True

        target_mcp = "const bridgeDirectory = scriptPath.dirname(options.bridgeScriptPath);"
        alt_target = "bridgeDirectory = scriptPath.dirname(options.bridgeScriptPath);"

        if PATCH_SIGNATURE not in m_content:
            if target_mcp in m_content:
                m_content = m_content.replace(target_mcp, f"{target_mcp}\n{LAUNCHER_SNIPPET}", 1)
                m_modified = True
            elif alt_target in m_content:
                m_content = m_content.replace(alt_target, f"{alt_target}\n{LAUNCHER_SNIPPET}", 1)
                m_modified = True
            else:
                return {"success": False, "error": f"Target marker not found in {mcp_binary.name}"}

        if DIRECT_MOUNT_SIGNATURE not in m_content:
            m_content = re.sub(
                r"(fingerprintGhidraProject\s*=\s*async\s*\([^)]*\)\s*=>\s*\{)",
                r"\1\n" + FASTPATH_FINGERPRINT_SNIPPET,
                m_content,
                count=1,
            )
            m_content = re.sub(
                r"(copyExistingGhidraProject\s*=\s*async\s*\([^)]*\)\s*=>\s*\{)",
                r"\1\n" + FASTPATH_COPY_SNIPPET,
                m_content,
                count=1,
            )
            m_modified = True

        if m_modified:
            mcp_binary.write_text(m_content, encoding="utf-8")
            applied_files.append(str(mcp_binary))

    # 4. Patch dist/cli-runtime/binary-*.js (CLI runtime acceleration)
    if cli_binary and cli_binary.is_file():
        c_content = cli_binary.read_text(encoding="utf-8")
        c_modified = False
        if PATCH_SIGNATURE not in c_content or DIRECT_MOUNT_SIGNATURE not in c_content:
            ensure_backup(cli_binary, c_content)

            if 'readdirSync' not in c_content:
                c_content = re.sub(
                    r'(import \{[^\}]*statSync[^\}]*\}\s*from\s*"node:fs";)',
                    lambda m: m.group(0).replace('statSync', 'readdirSync, statSync'),
                    c_content,
                    count=1,
                )
                c_modified = True

            target_cli = "const bridgeDirectory = scriptPath.dirname(options.bridgeScriptPath);"
            alt_target = "bridgeDirectory = scriptPath.dirname(options.bridgeScriptPath);"

            if PATCH_SIGNATURE not in c_content:
                if target_cli in c_content:
                    c_content = c_content.replace(target_cli, f"{target_cli}\n{LAUNCHER_SNIPPET}", 1)
                    c_modified = True
                elif alt_target in c_content:
                    c_content = c_content.replace(alt_target, f"{alt_target}\n{LAUNCHER_SNIPPET}", 1)
                    c_modified = True

            if DIRECT_MOUNT_SIGNATURE not in c_content:
                c_content = re.sub(
                    r"(fingerprintGhidraProject\s*=\s*async\s*\([^)]*\)\s*=>\s*\{)",
                    r"\1\n" + FASTPATH_FINGERPRINT_SNIPPET,
                    c_content,
                    count=1,
                )
                c_content = re.sub(
                    r"(copyExistingGhidraProject\s*=\s*async\s*\([^)]*\)\s*=>\s*\{)",
                    r"\1\n" + FASTPATH_COPY_SNIPPET,
                    c_content,
                    count=1,
                )
                c_modified = True

            if c_modified:
                cli_binary.write_text(c_content, encoding="utf-8")
                applied_files.append(str(cli_binary))

    # 5. Patch GhidraReleasePolicy.js if Ghidra 12.2 is installed (DEF-BB-040)
    if policy_file and policy_file.is_file() and is_ghidra_12_2_installed():
        p_content = policy_file.read_text(encoding="utf-8")
        if 'SUPPORTED_GHIDRA_VERSION = "12.1.4"' in p_content:
            ensure_backup(policy_file, p_content)
            p_content = p_content.replace(
                'SUPPORTED_GHIDRA_VERSION = "12.1.4"',
                'SUPPORTED_GHIDRA_VERSION = "12.2"',
            )
            policy_file.write_text(p_content, encoding="utf-8")
            applied_files.append(str(policy_file))

    return {
        "success": True,
        "applied_files": applied_files,
        "message": f"Successfully patched {len(applied_files)} files for sub-2s Ghidra acceleration & direct mount.",
    }


def revert_patch(rea_root: Optional[Path] = None) -> Dict[str, Any]:
    """Reverts REA installation to unpatched state using .orig backups."""
    root = rea_root or find_rea_package_root()
    if not root:
        return {"success": False, "error": "REA package root not found"}

    reverted_files: List[str] = []

    # Find all .orig backups anywhere under root/dist
    dist_dir = root / "dist"
    if dist_dir.is_dir():
        for orig in dist_dir.rglob("*.orig"):
            target = orig.with_suffix("")
            shutil.copy2(orig, target)
            orig.unlink()
            reverted_files.append(str(target))

    return {
        "success": True,
        "reverted_files": reverted_files,
        "message": f"Successfully reverted {len(reverted_files)} files from backups.",
    }
