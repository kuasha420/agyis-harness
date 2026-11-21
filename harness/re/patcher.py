# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Arafat Zahan (@kuasha420)
# Corporate Stewardship & Infrastructure: Purrfect Software Limited (PSL)
# Governed by: ICARO-42/b Ordinance (Company-Supported Personal IP Framework)

"""
REA Ghidra Pre-Analyzed Project Acceleration Patcher (ADR-028, PSL-INV-009).
Enables sub-2-second decompilation on large (>10MB) binaries by patching the
installed REA MCP server to reuse pre-analyzed Ghidra projects with -noanalysis -readOnly,
bypass redundant 1.3GB disk cloning (Optimization 2: Direct In-Place Mount), and
dynamically auto-discover workspace dirtyroom Ghidra projects from any global MCP session.
"""

import importlib.resources
import json
import os
from pathlib import Path
import re
import shutil
from typing import Any, Dict, List, Optional, Tuple

from harness.runtime.tool_checks_rea import is_ghidra_12_2_installed

PATCH_SIGNATURE = "REA_GHIDRA_PROJECT_DIR"
DIRECT_MOUNT_SIGNATURE = "REA_DIRECT_MOUNT_ACTIVE"
AUTO_DISCOVERY_SIGNATURE = "AGYIS_REA_AUTODISCOVERY_V4"

_FS_SYNC_IMPORT_LINE = (
    'import { lstatSync as __agyisLstatSync, readFileSync as __agyisReadFileSync, '
    'readdirSync as __agyisReaddirSync, realpathSync as __agyisRealpathSync, '
    'statSync as __agyisStatSync, symlinkSync as __agyisSymlinkSync } from "node:fs";\n'
    'import { homedir as __agyisHomedir } from "node:os";\n'
    'import { join as __agyisOsJoin } from "node:path";'
)
_FASTPATH_IMPORT_LINES = (
    'import { readdir as __agyisReaddir, stat as __agyisStat } from "node:fs/promises";\n'
    'import { dirname as __agyisDirname, join as __agyisJoin, resolve as __agyisResolve } from "node:path";'
)

_FINGERPRINT_FN_RE = re.compile(
    r"((?:(?:export\s+)?(?:const\s+)?fingerprintGhidraProject\s*=\s*async\s*\([^)]*\)\s*=>\s*\{|"
    r"async\s+function\s+fingerprintGhidraProject\s*\([^)]*\)\s*\{))"
)
_COPY_FN_RE = re.compile(
    r"((?:(?:export\s+)?(?:const\s+)?copyExistingGhidraProject\s*=\s*async\s*\([^)]*\)\s*=>\s*\{|"
    r"async\s+function\s+copyExistingGhidraProject\s*\([^)]*\)\s*\{))"
)
_SNAPSHOT_PATH_RE = re.compile(
    r"(const\s+snapshotPath\s*=\s*join\(runtimeRoot,\s*`target-\$\{expectedSha256\.slice\(0,\s*12\)\}\$\{suffix\}`\);)"
)
_REQUESTED_PATH_RE = re.compile(
    r"(const\s+canonical\s*=\s*await\s+realpath\(candidate\);)"
)


def _load_asset(name: str) -> str:
    """Loads an externalized JavaScript patch template via importlib.resources."""
    return importlib.resources.files("harness.re.assets").joinpath(name).read_text(encoding="utf-8")


LAUNCHER_SNIPPET = _load_asset("launcher_direct_mount.js")
FASTPATH_FINGERPRINT_SNIPPET = _load_asset("fastpath_fingerprint.js")
FASTPATH_COPY_SNIPPET = _load_asset("fastpath_copy.js")
SNAPSHOT_ORIGIN_SNIPPET = _load_asset("snapshot_origin.js")
REQUESTED_PATH_SNIPPET = _load_asset("requested_path.js")


def _safe_read_text(path: Optional[Path]) -> str:
    """Safely reads text from path, returning empty string on missing file or read errors."""
    if not path or not path.is_file():
        return ""
    try:
        return path.read_text(encoding="utf-8", errors="ignore")
    except (OSError, PermissionError):
        return ""


def _prepend_esm_imports(content: str, import_block: str) -> str:
    """Inserts ESM import lines cleanly after any leading shebang."""
    if content.startswith("#!"):
        nl = content.find("\n")
        if nl != -1:
            return f"{content[: nl + 1]}{import_block}\n{content[nl + 1 :]}"
    return f"{import_block}\n{content}"


def _ensure_aliased_imports(
    content: str,
    *,
    need_fs_sync: bool = False,
    need_fastpath: bool = False,
) -> str:
    """Ensures collision-free aliased Node ESM imports exist for injected snippets."""
    blocks: List[str] = []
    if need_fs_sync and _FS_SYNC_IMPORT_LINE not in content:
        blocks.append(_FS_SYNC_IMPORT_LINE)
    if need_fastpath and _FASTPATH_IMPORT_LINES not in content:
        blocks.append(_FASTPATH_IMPORT_LINES)
    if not blocks:
        return content
    return _prepend_esm_imports(content, "\n".join(blocks))


def _load_clean_base(file_path: Path) -> str:
    """Loads pristine upstream JS from .js.orig if present, creating backup once if unpatched."""
    orig = file_path.with_suffix(".js.orig")
    if orig.is_file():
        return orig.read_text(encoding="utf-8")

    current = file_path.read_text(encoding="utf-8")
    has_any_sig = (
        PATCH_SIGNATURE in current
        or DIRECT_MOUNT_SIGNATURE in current
        or AUTO_DISCOVERY_SIGNATURE in current
        or "AGYIS_REA_AUTODISCOVERY" in current
    )
    if not has_any_sig:
        orig.write_text(current, encoding="utf-8")
    return current


def _inject_bundle_snippets(
    content: str,
    *,
    require_launcher: bool,
    include_fastpaths: bool,
    include_snapshot_origin: bool,
    include_requested_path: bool = False,
) -> Tuple[str, bool, Optional[str]]:
    """Applies launcher, fastpath, snapshot-origin, and pre-realpath snippets onto pristine JS."""
    modified = False
    need_fs_sync = False
    need_fastpath = False
    out = content

    target_primary = "const bridgeDirectory = scriptPath.dirname(options.bridgeScriptPath);"
    target_alt = "bridgeDirectory = scriptPath.dirname(options.bridgeScriptPath);"

    if require_launcher or target_primary in out or target_alt in out:
        if target_primary in out:
            out = out.replace(target_primary, f"{target_primary}\n{LAUNCHER_SNIPPET}", 1)
            need_fs_sync = True
            modified = True
        elif target_alt in out:
            out = out.replace(target_alt, f"{target_alt}\n{LAUNCHER_SNIPPET}", 1)
            need_fs_sync = True
            modified = True
        elif require_launcher:
            return out, False, "Target launcher marker not found"

    if include_fastpaths:
        out, fp_count = _FINGERPRINT_FN_RE.subn(
            lambda m: f"{m.group(1)}\n{FASTPATH_FINGERPRINT_SNIPPET}",
            out,
            count=1,
        )
        out, cp_count = _COPY_FN_RE.subn(
            lambda m: f"{m.group(1)}\n{FASTPATH_COPY_SNIPPET}",
            out,
            count=1,
        )
        if fp_count or cp_count:
            need_fastpath = True
            modified = True

    if include_snapshot_origin:
        out, snap_count = _SNAPSHOT_PATH_RE.subn(
            lambda m: f"{m.group(1)}\n{SNAPSHOT_ORIGIN_SNIPPET}",
            out,
            count=1,
        )
        if snap_count:
            modified = True

    if include_requested_path:
        out, req_count = _REQUESTED_PATH_RE.subn(
            lambda m: f"{m.group(1)}\n{REQUESTED_PATH_SNIPPET}",
            out,
            count=1,
        )
        if req_count:
            modified = True

    if need_fs_sync or need_fastpath:
        out = _ensure_aliased_imports(
            out,
            need_fs_sync=need_fs_sync,
            need_fastpath=need_fastpath,
        )

    return out, modified, None


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
    target_snapshot = root / "dist" / "ghidra" / "GhidraTargetSnapshot.js"
    policy = root / "dist" / "ghidra" / "GhidraReleasePolicy.js"
    target_resolver_cand = root / "dist" / "application" / "BinaryTargetResolver.js"
    target_resolver: Optional[Path] = None
    if target_resolver_cand.is_file() and _REQUESTED_PATH_RE.search(_safe_read_text(target_resolver_cand)):
        target_resolver = target_resolver_cand

    mcp_dir = root / "dist" / "mcp"
    mcp_binary: Optional[Path] = None
    mcp_resolver: Optional[Path] = None
    if mcp_dir.is_dir():
        for cand in sorted(mcp_dir.glob("binary-*.js")):
            if not cand.name.endswith(".orig"):
                content = _safe_read_text(cand)
                if "ghidraHeadlessArguments" in content:
                    mcp_binary = cand
                    break
        for cand in sorted(mcp_dir.glob("BinaryTargetResolver-*.js")):
            if not cand.name.endswith(".orig") and _REQUESTED_PATH_RE.search(_safe_read_text(cand)):
                mcp_resolver = cand
                break

    cli_dir = root / "dist" / "cli-runtime"
    cli_binary: Optional[Path] = None
    cli_resolver: Optional[Path] = None
    if cli_dir.is_dir():
        for cand in sorted(cli_dir.glob("binary-*.js")):
            if not cand.name.endswith(".orig"):
                content = _safe_read_text(cand)
                if "ghidraHeadlessArguments" in content:
                    cli_binary = cand
                    break
        for cand in sorted(cli_dir.glob("BinaryTargetResolver-*.js")):
            if not cand.name.endswith(".orig") and _REQUESTED_PATH_RE.search(_safe_read_text(cand)):
                cli_resolver = cand
                break

    return {
        "launcher": launcher if launcher.is_file() else None,
        "snapshot": snapshot if snapshot.is_file() else None,
        "target_snapshot": target_snapshot if target_snapshot.is_file() else None,
        "target_resolver": target_resolver,
        "mcp_binary": mcp_binary,
        "mcp_resolver": mcp_resolver,
        "cli_binary": cli_binary,
        "cli_resolver": cli_resolver,
        "policy": policy if policy.is_file() else None,
    }


def check_patch(rea_root: Optional[Path] = None) -> Dict[str, Any]:
    """Inspects whether the Ghidra acceleration & auto-discovery patch is currently applied."""
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
            "auto_discovery_active": False,
            "launcher_path": None,
            "mcp_path": None,
            "message": "REA (rea-agents) package could not be found.",
        }

    targets = get_all_patch_targets(root)
    launcher = targets.get("launcher")
    mcp_binary = targets.get("mcp_binary")
    snapshot = targets.get("snapshot")
    target_snapshot = targets.get("target_snapshot")
    target_resolver = targets.get("target_resolver")
    mcp_resolver = targets.get("mcp_resolver")
    cli_binary = targets.get("cli_binary")
    cli_resolver = targets.get("cli_resolver")
    policy_file = targets.get("policy")

    l_text = _safe_read_text(launcher)
    m_text = _safe_read_text(mcp_binary)
    s_text = _safe_read_text(snapshot)
    ts_text = _safe_read_text(target_snapshot)
    tr_text = _safe_read_text(target_resolver)
    mr_text = _safe_read_text(mcp_resolver)
    c_text = _safe_read_text(cli_binary)
    cr_text = _safe_read_text(cli_resolver)
    p_text = _safe_read_text(policy_file)

    launcher_patched = bool(launcher) and PATCH_SIGNATURE in l_text
    mcp_patched = bool(mcp_binary) and PATCH_SIGNATURE in m_text
    snapshot_patched = bool(snapshot) and DIRECT_MOUNT_SIGNATURE in s_text
    cli_patched = bool(cli_binary) and PATCH_SIGNATURE in c_text and DIRECT_MOUNT_SIGNATURE in c_text
    policy_native = bool(policy_file) and 'SUPPORTED_GHIDRA_VERSION = "12.2"' in p_text and not policy_file.with_suffix(".js.orig").is_file()
    policy_patched = bool(policy_file) and 'SUPPORTED_GHIDRA_VERSION = "12.2"' in p_text

    direct_mount_active = (
        (not snapshot or snapshot_patched)
        and (not cli_binary or cli_patched)
        and (not mcp_binary or (DIRECT_MOUNT_SIGNATURE in m_text))
    )
    auto_discovery_active = (
        bool(launcher)
        and AUTO_DISCOVERY_SIGNATURE in l_text
        and _FS_SYNC_IMPORT_LINE in l_text
        and bool(mcp_binary)
        and AUTO_DISCOVERY_SIGNATURE in m_text
        and _FS_SYNC_IMPORT_LINE in m_text
        and (not snapshot or (AUTO_DISCOVERY_SIGNATURE in s_text and _FASTPATH_IMPORT_LINES in s_text))
        and (not cli_binary or (AUTO_DISCOVERY_SIGNATURE in c_text and _FS_SYNC_IMPORT_LINE in c_text))
        and (not target_snapshot or AUTO_DISCOVERY_SIGNATURE in ts_text)
        and (not target_resolver or AUTO_DISCOVERY_SIGNATURE in tr_text)
        and (not mcp_resolver or AUTO_DISCOVERY_SIGNATURE in mr_text)
        and (not cli_resolver or AUTO_DISCOVERY_SIGNATURE in cr_text)
    )

    if launcher_patched and mcp_patched and auto_discovery_active and direct_mount_active:
        status = "applied"
        msg = "REA pre-analyzed Ghidra acceleration, direct mount & multi-workspace auto-discovery active."
    elif launcher_patched and mcp_patched and auto_discovery_active:
        status = "applied"
        msg = "REA pre-analyzed Ghidra acceleration & multi-workspace auto-discovery active."
    elif launcher_patched or mcp_patched or snapshot_patched or cli_patched:
        status = "partial"
        if launcher_patched and mcp_patched and not auto_discovery_active:
            msg = "REA patch is outdated (missing latest multi-workspace auto-discovery); re-run 'agyis re patch-rea --apply'."
        else:
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
        "auto_discovery_active": auto_discovery_active,
        "policy_patched": policy_patched,
        "policy_native": policy_native,
        "launcher_path": str(launcher) if launcher else None,
        "mcp_path": str(mcp_binary) if mcp_binary else None,
        "cli_path": str(cli_binary) if cli_binary else None,
        "policy_path": str(policy_file) if policy_file else None,
        "message": msg,
    }


def apply_patch(rea_root: Optional[Path] = None) -> Dict[str, Any]:
    """Applies or upgrades the pre-analyzed Ghidra acceleration & direct-mount patch."""
    root = rea_root or find_rea_package_root()
    if not root:
        return {"success": False, "error": "REA package root not found"}

    targets = get_all_patch_targets(root)
    launcher = targets.get("launcher")
    mcp_binary = targets.get("mcp_binary")
    snapshot = targets.get("snapshot")
    target_snapshot = targets.get("target_snapshot")
    target_resolver = targets.get("target_resolver")
    mcp_resolver = targets.get("mcp_resolver")
    cli_binary = targets.get("cli_binary")
    cli_resolver = targets.get("cli_resolver")
    policy_file = targets.get("policy")

    if not launcher or not launcher.is_file():
        return {"success": False, "error": "GhidraLauncher.js not found in REA distribution"}
    if not mcp_binary or not mcp_binary.is_file():
        return {"success": False, "error": "binary-*.js not found in REA MCP distribution"}

    applied_files: List[str] = []

    # 1. Patch or upgrade GhidraLauncher.js
    l_current = launcher.read_text(encoding="utf-8")
    if (
        PATCH_SIGNATURE not in l_current
        or AUTO_DISCOVERY_SIGNATURE not in l_current
        or _FS_SYNC_IMPORT_LINE not in l_current
    ):
        l_base = _load_clean_base(launcher)
        l_patched, l_mod, l_err = _inject_bundle_snippets(
            l_base,
            require_launcher=True,
            include_fastpaths=False,
            include_snapshot_origin=False,
        )
        if l_err:
            return {"success": False, "error": f"{l_err} in {launcher.name}"}
        if l_mod:
            launcher.write_text(l_patched, encoding="utf-8")
            applied_files.append(str(launcher))

    # 2. Patch or upgrade GhidraProjectSnapshot.js (Zero-copy Direct Mount fastpath)
    if snapshot and snapshot.is_file():
        s_current = snapshot.read_text(encoding="utf-8")
        if (
            DIRECT_MOUNT_SIGNATURE not in s_current
            or AUTO_DISCOVERY_SIGNATURE not in s_current
            or _FASTPATH_IMPORT_LINES not in s_current
        ):
            s_base = _load_clean_base(snapshot)
            s_patched, s_mod, _ = _inject_bundle_snippets(
                s_base,
                require_launcher=False,
                include_fastpaths=True,
                include_snapshot_origin=False,
            )
            if s_mod:
                snapshot.write_text(s_patched, encoding="utf-8")
                applied_files.append(str(snapshot))

    # 3. Patch or upgrade GhidraTargetSnapshot.js (Origin path tracking for temp snapshots)
    if target_snapshot and target_snapshot.is_file():
        ts_current = target_snapshot.read_text(encoding="utf-8")
        if AUTO_DISCOVERY_SIGNATURE not in ts_current:
            ts_base = _load_clean_base(target_snapshot)
            ts_patched, ts_mod, _ = _inject_bundle_snippets(
                ts_base,
                require_launcher=False,
                include_fastpaths=False,
                include_snapshot_origin=True,
            )
            if ts_mod:
                target_snapshot.write_text(ts_patched, encoding="utf-8")
                applied_files.append(str(target_snapshot))

    # 4. Patch or upgrade dist/mcp/binary-*.js
    m_current = mcp_binary.read_text(encoding="utf-8")
    has_m_fastpath_fn = bool(_FINGERPRINT_FN_RE.search(m_current) or _COPY_FN_RE.search(m_current))
    needs_m_fastpath = has_m_fastpath_fn and (
        DIRECT_MOUNT_SIGNATURE not in m_current or _FASTPATH_IMPORT_LINES not in m_current
    )
    if (
        PATCH_SIGNATURE not in m_current
        or AUTO_DISCOVERY_SIGNATURE not in m_current
        or _FS_SYNC_IMPORT_LINE not in m_current
        or needs_m_fastpath
    ):
        m_base = _load_clean_base(mcp_binary)
        m_patched, m_mod, m_err = _inject_bundle_snippets(
            m_base,
            require_launcher=True,
            include_fastpaths=True,
            include_snapshot_origin=True,
        )
        if m_err:
            return {"success": False, "error": f"{m_err} in {mcp_binary.name}"}
        if m_mod:
            mcp_binary.write_text(m_patched, encoding="utf-8")
            applied_files.append(str(mcp_binary))

    # 5. Patch or upgrade dist/cli-runtime/binary-*.js
    if cli_binary and cli_binary.is_file():
        c_current = cli_binary.read_text(encoding="utf-8")
        has_c_fastpath_fn = bool(_FINGERPRINT_FN_RE.search(c_current) or _COPY_FN_RE.search(c_current))
        needs_c_fastpath = has_c_fastpath_fn and (
            DIRECT_MOUNT_SIGNATURE not in c_current or _FASTPATH_IMPORT_LINES not in c_current
        )
        if (
            PATCH_SIGNATURE not in c_current
            or AUTO_DISCOVERY_SIGNATURE not in c_current
            or _FS_SYNC_IMPORT_LINE not in c_current
            or needs_c_fastpath
        ):
            c_base = _load_clean_base(cli_binary)
            c_patched, c_mod, _ = _inject_bundle_snippets(
                c_base,
                require_launcher=False,
                include_fastpaths=True,
                include_snapshot_origin=True,
            )
            if c_mod:
                cli_binary.write_text(c_patched, encoding="utf-8")
                applied_files.append(str(cli_binary))

    # 5b. Patch or upgrade BinaryTargetResolver bundles (pre-realpath caller path tracking)
    for resolver_file in (target_resolver, mcp_resolver, cli_resolver):
        if resolver_file and resolver_file.is_file():
            r_current = resolver_file.read_text(encoding="utf-8")
            if AUTO_DISCOVERY_SIGNATURE not in r_current:
                r_base = _load_clean_base(resolver_file)
                r_patched, r_mod, _ = _inject_bundle_snippets(
                    r_base,
                    require_launcher=False,
                    include_fastpaths=False,
                    include_snapshot_origin=False,
                    include_requested_path=True,
                )
                if r_mod:
                    resolver_file.write_text(r_patched, encoding="utf-8")
                    applied_files.append(str(resolver_file))

    # 6. Patch GhidraReleasePolicy.js if Ghidra 12.2 is installed (DEF-BB-040)
    if policy_file and policy_file.is_file() and is_ghidra_12_2_installed():
        p_current = policy_file.read_text(encoding="utf-8")
        if 'SUPPORTED_GHIDRA_VERSION = "12.1.4"' in p_current:
            orig_policy = policy_file.with_suffix(".js.orig")
            if not orig_policy.is_file():
                orig_policy.write_text(p_current, encoding="utf-8")
            p_patched = p_current.replace(
                'SUPPORTED_GHIDRA_VERSION = "12.1.4"',
                'SUPPORTED_GHIDRA_VERSION = "12.2"',
            )
            policy_file.write_text(p_patched, encoding="utf-8")
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
