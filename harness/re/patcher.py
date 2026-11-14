# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Arafat Zahan (@kuasha420)
# Corporate Stewardship & Infrastructure: Purrfect Software Limited (PSL)
# Governed by: ICARO-42/b Ordinance (Company-Supported Personal IP Framework)

"""
REA Ghidra Pre-Analyzed Project Acceleration Patcher (ADR-028, PSL-INV-009).
Enables sub-2-second decompilation on large (>10MB) binaries by patching the
installed REA MCP server to reuse pre-analyzed Ghidra projects with -noanalysis -readOnly.
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
    if (targetBase.startsWith("target-")) {
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
            # Follow directory hierarchy upwards to find rea-agents package root
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
    """Returns (launcher_path, mcp_binary_path) within rea-agents package."""
    root = rea_root or find_rea_package_root()
    if not root:
        return None, None

    launcher = root / "dist" / "ghidra" / "GhidraLauncher.js"
    if not launcher.is_file():
        launcher = None

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

    return launcher, mcp_binary


def check_patch(rea_root: Optional[Path] = None) -> Dict[str, Any]:
    """Inspects whether the Ghidra acceleration patch is currently applied."""
    root = rea_root or find_rea_package_root()
    if not root:
        return {
            "status": "not_installed",
            "rea_root": None,
            "launcher_patched": False,
            "mcp_patched": False,
            "launcher_path": None,
            "mcp_path": None,
            "message": "REA (rea-agents) package could not be found.",
        }

    launcher, mcp_binary = get_patch_targets(root)

    launcher_patched = False
    mcp_patched = False
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

    policy_file = root / "dist" / "ghidra" / "GhidraReleasePolicy.js"
    if policy_file.is_file():
        try:
            p_content = policy_file.read_text(encoding="utf-8", errors="ignore")
            policy_patched = 'SUPPORTED_GHIDRA_VERSION = "12.2"' in p_content
        except Exception:
            pass

    if launcher_patched and mcp_patched:
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
        "policy_patched": policy_patched,
        "launcher_path": str(launcher) if launcher else None,
        "mcp_path": str(mcp_binary) if mcp_binary else None,
        "policy_path": str(policy_file) if policy_file.is_file() else None,
        "message": msg,
    }


def apply_patch(rea_root: Optional[Path] = None) -> Dict[str, Any]:
    """Applies the pre-analyzed Ghidra acceleration patch to the REA installation."""
    root = rea_root or find_rea_package_root()
    if not root:
        return {"success": False, "error": "REA package root not found"}

    launcher, mcp_binary = get_patch_targets(root)
    if not launcher or not launcher.is_file():
        return {"success": False, "error": "GhidraLauncher.js not found in REA distribution"}
    if not mcp_binary or not mcp_binary.is_file():
        return {"success": False, "error": "binary-*.js not found in REA MCP distribution"}

    applied_files: List[str] = []

    # 1. Patch GhidraLauncher.js
    l_content = launcher.read_text(encoding="utf-8")
    if PATCH_SIGNATURE not in l_content:
        orig = launcher.with_suffix(".js.orig")
        if not orig.is_file():
            orig.write_text(l_content, encoding="utf-8")

        # Ensure statSync and readdirSync are imported
        if 'import { statSync' not in l_content and 'import { readdirSync' not in l_content:
            l_content = re.sub(
                r'(import \{[^\}]*?\}\s*from\s*"node:fs/promises";)',
                r'import { readdirSync, statSync } from "node:fs";\n\1',
                l_content,
                count=1,
            )
        elif 'readdirSync' not in l_content:
            l_content = l_content.replace('import { statSync', 'import { readdirSync, statSync')

        # Insert snippet after bridgeDirectory definition
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

    # 2. Patch dist/mcp/binary-*.js
    m_content = mcp_binary.read_text(encoding="utf-8")
    if PATCH_SIGNATURE not in m_content:
        orig = mcp_binary.with_suffix(".js.orig")
        if not orig.is_file():
            orig.write_text(m_content, encoding="utf-8")

        # Ensure readdirSync is imported if needed
        if 'readdirSync' not in m_content:
            m_content = re.sub(
                r'(import \{[^\}]*statSync[^\}]*\}\s*from\s*"node:fs";)',
                lambda m: m.group(0).replace('statSync', 'readdirSync, statSync'),
                m_content,
                count=1,
            )

        # In Vite bundle: ghidraHeadlessArguments = (options) => { ... }
        # bridgeDirectory = scriptPath.dirname(options.bridgeScriptPath);
        target_mcp = "const bridgeDirectory = scriptPath.dirname(options.bridgeScriptPath);"
        alt_target = "bridgeDirectory = scriptPath.dirname(options.bridgeScriptPath);"

        if target_mcp in m_content:
            m_content = m_content.replace(
                target_mcp,
                f"{target_mcp}\n{LAUNCHER_SNIPPET}",
                1,
            )
            mcp_binary.write_text(m_content, encoding="utf-8")
            applied_files.append(str(mcp_binary))
        elif alt_target in m_content:
            m_content = m_content.replace(
                alt_target,
                f"{alt_target}\n{LAUNCHER_SNIPPET}",
                1,
            )
            mcp_binary.write_text(m_content, encoding="utf-8")
            applied_files.append(str(mcp_binary))
        else:
            return {"success": False, "error": f"Target marker not found in {mcp_binary.name}"}

    # 3. Patch GhidraReleasePolicy.js if Ghidra 12.2 is installed (DEF-BB-040)
    policy_file = root / "dist" / "ghidra" / "GhidraReleasePolicy.js"
    if policy_file.is_file() and is_ghidra_12_2_installed():
        p_content = policy_file.read_text(encoding="utf-8")
        if 'SUPPORTED_GHIDRA_VERSION = "12.1.4"' in p_content:
            p_orig = policy_file.with_suffix(".js.orig")
            if not p_orig.is_file():
                p_orig.write_text(p_content, encoding="utf-8")
            p_content = p_content.replace(
                'SUPPORTED_GHIDRA_VERSION = "12.1.4"',
                'SUPPORTED_GHIDRA_VERSION = "12.2"',
            )
            policy_file.write_text(p_content, encoding="utf-8")
            applied_files.append(str(policy_file))

    return {
        "success": True,
        "applied_files": applied_files,
        "message": f"Successfully patched {len(applied_files)} files for sub-2s Ghidra acceleration.",
    }


def revert_patch(rea_root: Optional[Path] = None) -> Dict[str, Any]:
    """Reverts REA installation to unpatched state using .orig backups."""
    root = rea_root or find_rea_package_root()
    if not root:
        return {"success": False, "error": "REA package root not found"}

    launcher, mcp_binary = get_patch_targets(root)
    reverted_files: List[str] = []

    if launcher:
        orig = launcher.with_suffix(".js.orig")
        if orig.is_file():
            shutil.copy2(orig, launcher)
            orig.unlink()
            reverted_files.append(str(launcher))

    if mcp_binary:
        orig = mcp_binary.with_suffix(".js.orig")
        if orig.is_file():
            shutil.copy2(orig, mcp_binary)
            orig.unlink()
            reverted_files.append(str(mcp_binary))

    policy_file = root / "dist" / "ghidra" / "GhidraReleasePolicy.js"
    if policy_file.is_file():
        p_orig = policy_file.with_suffix(".js.orig")
        if p_orig.is_file():
            shutil.copy2(p_orig, policy_file)
            p_orig.unlink()
            reverted_files.append(str(policy_file))

    return {
        "success": True,
        "reverted_files": reverted_files,
        "message": f"Successfully reverted {len(reverted_files)} files from backups.",
    }
