# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Arafat Zahan (@kuasha420)
# Corporate Stewardship & Infrastructure: Purrfect Software Limited (PSL)
# Governed by: ICARO-42/b Ordinance (Company-Supported Personal IP Framework)

"""
REA Ghidra Pre-Analyzed Project Acceleration Patcher (ADR-028, PSL-RE-001).
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
import sys
import tempfile
from typing import Any, Dict, List, Optional, Tuple

from harness.runtime.tool_checks_rea import is_ghidra_12_2_installed

PATCH_SIGNATURE = "REA_GHIDRA_PROJECT_DIR"
DIRECT_MOUNT_SIGNATURE = "REA_DIRECT_MOUNT_ACTIVE"
AUTO_DISCOVERY_SIGNATURE = "AGYIS_REA_AUTODISCOVERY_V4"

_GHIDRA_POLICY_OLD = 'SUPPORTED_GHIDRA_VERSION = "12.1.4"'
_GHIDRA_POLICY_NEW = 'SUPPORTED_GHIDRA_VERSION = "12.2"'

_FS_SYNC_IMPORT_LINE = (
    'import { lstatSync as __agyisLstatSync, readFileSync as __agyisReadFileSync, '
    'readdirSync as __agyisReaddirSync, realpathSync as __agyisRealpathSync, '
    'statSync as __agyisStatSync, symlinkSync as __agyisSymlinkSync } from "node:fs";\n'
    'import { homedir as __agyisHomedir } from "node:os";\n'
    'import { join as __agyisOsJoin } from "node:path";'
)
_FASTPATH_IMPORT_LINES = (
    'import { readFile as __agyisReadFile, readdir as __agyisReaddir, stat as __agyisStat } from "node:fs/promises";\n'
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


def _atomic_write_bytes(target: Path, data: bytes) -> None:
    """Atomically writes bytes to target using a same-directory temporary file."""
    tmp_name: Optional[str] = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="wb",
            dir=target.parent,
            prefix=f".{target.name}.",
            suffix=".tmp",
            delete=False,
        ) as tmp_f:
            tmp_name = tmp_f.name
            tmp_f.write(data)
        os.replace(tmp_name, target)
    except OSError:
        if tmp_name:
            Path(tmp_name).unlink(missing_ok=True)
        raise


def _atomic_write_text(target: Path, content: str) -> None:
    """Atomically writes UTF-8 text to target."""
    _atomic_write_bytes(target, content.encode("utf-8"))


def _validate_dist_file(target: Path, dist_dir: Path) -> Optional[str]:
    """Verifies target and its .orig backup are regular non-symlink files inside dist_dir."""
    if target.is_symlink():
        return f"Refusing to patch symlink: {target}"
    orig = target.with_suffix(".js.orig")
    if orig.is_symlink():
        return f"Refusing to use symlinked backup: {orig}"
    try:
        dist_res = dist_dir.resolve()
        if not target.resolve().is_relative_to(dist_res):
            return f"Patch target escapes dist directory: {target}"
        if orig.exists() and not orig.resolve().is_relative_to(dist_res):
            return f"Backup file escapes dist directory: {orig}"
    except OSError as exc:
        return f"Failed to validate path {target}: {exc}"
    return None


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


def _load_clean_base(file_path: Path) -> Tuple[str, bool]:
    """Loads pristine upstream JS from .js.orig if present, creating backup atomically once."""
    orig = file_path.with_suffix(".js.orig")
    if orig.is_file():
        return orig.read_text(encoding="utf-8"), False

    current = file_path.read_text(encoding="utf-8")
    has_any_sig = (
        PATCH_SIGNATURE in current
        or DIRECT_MOUNT_SIGNATURE in current
        or AUTO_DISCOVERY_SIGNATURE in current
        or "AGYIS_REA_AUTODISCOVERY" in current
    )
    created_orig = False
    if not has_any_sig:
        _atomic_write_text(orig, current)
        created_orig = True
    return current, created_orig


def _inject_bundle_snippets(
    content: str,
    *,
    require_launcher: bool,
    include_fastpaths: bool,
    include_snapshot_origin: bool,
    include_requested_path: bool = False,
    require_fastpaths: bool = False,
    require_snapshot_origin: bool = False,
    require_requested_path: bool = False,
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
        elif require_fastpaths:
            return out, False, "Target fastpath function markers not found"

    if include_snapshot_origin:
        out, snap_count = _SNAPSHOT_PATH_RE.subn(
            lambda m: f"{m.group(1)}\n{SNAPSHOT_ORIGIN_SNIPPET}",
            out,
            count=1,
        )
        if snap_count:
            modified = True
        elif require_snapshot_origin:
            return out, False, "Target snapshotPath marker not found"

    if include_requested_path:
        out, req_count = _REQUESTED_PATH_RE.subn(
            lambda m: f"{m.group(1)}\n{REQUESTED_PATH_SNIPPET}",
            out,
            count=1,
        )
        if req_count:
            modified = True
        elif require_requested_path:
            return out, False, "Target requested-path realpath marker not found"

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
                        if isinstance(pkg, dict) and pkg.get("name") == "rea-agents":
                            return curr.resolve()
                    except (OSError, json.JSONDecodeError, ValueError) as exc:
                        sys.stderr.write(f"[!] Warning: Could not inspect {curr / 'package.json'}: {exc}\n")
                curr = curr.parent
        except OSError as exc:
            sys.stderr.write(f"[!] Warning: Could not resolve rea binary path '{rea_bin}': {exc}\n")

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
    target_resolver: Optional[Path] = target_resolver_cand if target_resolver_cand.is_file() else None

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
            if not cand.name.endswith(".orig"):
                mcp_resolver = cand
                break

    cli_dir = root / "dist" / "cli-runtime"
    cli_binary: Optional[Path] = None
    cli_resolver: Optional[Path] = None
    cli_kuna: Optional[Path] = None
    if cli_dir.is_dir():
        for cand in sorted(cli_dir.glob("binary-*.js")):
            if not cand.name.endswith(".orig"):
                content = _safe_read_text(cand)
                if "ghidraHeadlessArguments" in content:
                    cli_binary = cand
                    break
        for cand in sorted(cli_dir.glob("BinaryTargetResolver-*.js")):
            if not cand.name.endswith(".orig"):
                cli_resolver = cand
                break
        for cand in sorted(cli_dir.glob("KunaCommand-*.js")):
            if not cand.name.endswith(".orig") and "SUPPORTED_GHIDRA_VERSION" in _safe_read_text(cand):
                cli_kuna = cand
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
        "cli_kuna": cli_kuna,
        "policy": policy if policy.is_file() else None,
    }


def _policy_bearing_targets(targets: Dict[str, Optional[Path]]) -> List[Path]:
    """Returns all unique target files containing a SUPPORTED_GHIDRA_VERSION declaration."""
    found: List[Path] = []
    seen: set[Path] = set()
    for key in ("policy", "mcp_binary", "cli_binary", "cli_kuna"):
        p = targets.get(key)
        if p and p.is_file() and p not in seen:
            text = _safe_read_text(p)
            if "SUPPORTED_GHIDRA_VERSION" in text:
                found.append(p)
                seen.add(p)
    return found


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

    launcher_patched = bool(launcher) and PATCH_SIGNATURE in l_text
    mcp_patched = bool(mcp_binary) and PATCH_SIGNATURE in m_text
    snapshot_patched = bool(snapshot) and DIRECT_MOUNT_SIGNATURE in s_text
    cli_patched = bool(cli_binary) and PATCH_SIGNATURE in c_text and DIRECT_MOUNT_SIGNATURE in c_text

    policy_targets = _policy_bearing_targets(targets)
    policy_texts = [_safe_read_text(p) for p in policy_targets]
    policy_patched = bool(policy_targets) and all(
        _GHIDRA_POLICY_NEW in txt and _GHIDRA_POLICY_OLD not in txt for txt in policy_texts
    )
    policy_native = (
        policy_patched
        and bool(policy_file)
        and not policy_file.with_suffix(".js.orig").is_file()
        and all(
            not p.with_suffix(".js.orig").is_file()
            for p in policy_targets
            if p not in (mcp_binary, cli_binary)
        )
    )

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
        "policy_targets": [str(p) for p in policy_targets],
        "message": msg,
    }


def _rollback_patch_transaction(
    rollback_log: List[Tuple[Path, bytes, Path, bool]],
) -> List[str]:
    """Restores all files mutated in a failed apply_patch transaction."""
    errors: List[str] = []
    for target, prior_bytes, orig_path, created_orig in reversed(rollback_log):
        try:
            _atomic_write_bytes(target, prior_bytes)
        except OSError as exc:
            errors.append(f"Failed to restore {target}: {exc}")
        if created_orig:
            try:
                orig_path.unlink(missing_ok=True)
            except OSError as exc:
                errors.append(f"Failed to clean temporary backup {orig_path}: {exc}")
    return errors


def apply_patch(rea_root: Optional[Path] = None) -> Dict[str, Any]:
    """Applies or upgrades the pre-analyzed Ghidra acceleration & direct-mount patch atomically."""
    root = rea_root or find_rea_package_root()
    if not root:
        return {"success": False, "error": "REA package root not found"}

    dist_dir = root / "dist"
    if not dist_dir.is_dir() or dist_dir.is_symlink():
        return {"success": False, "error": f"Invalid REA dist directory: {dist_dir}"}

    targets = get_all_patch_targets(root)
    launcher = targets.get("launcher")
    mcp_binary = targets.get("mcp_binary")
    snapshot = targets.get("snapshot")
    target_snapshot = targets.get("target_snapshot")
    target_resolver = targets.get("target_resolver")
    mcp_resolver = targets.get("mcp_resolver")
    cli_binary = targets.get("cli_binary")
    cli_resolver = targets.get("cli_resolver")
    cli_kuna = targets.get("cli_kuna")
    policy_file = targets.get("policy")

    if not launcher or not launcher.is_file():
        return {"success": False, "error": "GhidraLauncher.js not found in REA distribution"}
    if not mcp_binary or not mcp_binary.is_file():
        return {"success": False, "error": "binary-*.js not found in REA MCP distribution"}

    ghidra_12_2 = is_ghidra_12_2_installed()
    applied_files: List[str] = []
    rollback_log: List[Tuple[Path, bytes, Path, bool]] = []

    def _fail(message: str) -> Dict[str, Any]:
        rb_errors = _rollback_patch_transaction(rollback_log)
        res: Dict[str, Any] = {"success": False, "error": message, "rolled_back": bool(rollback_log)}
        if rb_errors:
            res["rollback_errors"] = rb_errors
        return res

    def _commit_target(target: Path, new_content: str, prior_bytes: bytes, created_orig: bool) -> None:
        orig_path = target.with_suffix(".js.orig")
        rollback_log.append((target, prior_bytes, orig_path, created_orig))
        _atomic_write_text(target, new_content)
        if str(target) not in applied_files:
            applied_files.append(str(target))

    try:
    # Validate all discovered target paths upfront
        for cand in (launcher, snapshot, target_snapshot, mcp_binary, cli_binary, target_resolver, mcp_resolver, cli_resolver, cli_kuna, policy_file):
            if cand and cand.exists():
                val_err = _validate_dist_file(cand, dist_dir)
                if val_err:
                    return _fail(val_err)

        # 1. Patch or upgrade GhidraLauncher.js
        l_bytes = launcher.read_bytes()
        l_current = l_bytes.decode("utf-8")
        if PATCH_SIGNATURE not in l_current or AUTO_DISCOVERY_SIGNATURE not in l_current or _FS_SYNC_IMPORT_LINE not in l_current:
            l_base, created_orig = _load_clean_base(launcher)
            l_patched, l_mod, l_err = _inject_bundle_snippets(l_base, require_launcher=True, include_fastpaths=False, include_snapshot_origin=False)
            if l_err:
                if created_orig:
                    launcher.with_suffix(".js.orig").unlink(missing_ok=True)
                return _fail(f"{l_err} in {launcher.name}")
            if l_mod:
                _commit_target(launcher, l_patched, l_bytes, created_orig)

        # 2. Patch or upgrade GhidraProjectSnapshot.js (Zero-copy Direct Mount fastpath)
        if snapshot and snapshot.is_file():
            s_bytes = snapshot.read_bytes()
            s_current = s_bytes.decode("utf-8")
            if DIRECT_MOUNT_SIGNATURE not in s_current or AUTO_DISCOVERY_SIGNATURE not in s_current or _FASTPATH_IMPORT_LINES not in s_current:
                s_base, created_orig = _load_clean_base(snapshot)
                s_patched, s_mod, s_err = _inject_bundle_snippets(s_base, require_launcher=False, include_fastpaths=True, include_snapshot_origin=False, require_fastpaths=True)
                if s_err:
                    if created_orig:
                        snapshot.with_suffix(".js.orig").unlink(missing_ok=True)
                    return _fail(f"{s_err} in {snapshot.name}")
                if s_mod:
                    _commit_target(snapshot, s_patched, s_bytes, created_orig)

        # 3. Patch or upgrade GhidraTargetSnapshot.js (Origin path tracking for temp snapshots)
        if target_snapshot and target_snapshot.is_file():
            ts_bytes = target_snapshot.read_bytes()
            ts_current = ts_bytes.decode("utf-8")
            if AUTO_DISCOVERY_SIGNATURE not in ts_current:
                ts_base, created_orig = _load_clean_base(target_snapshot)
                ts_patched, ts_mod, ts_err = _inject_bundle_snippets(ts_base, require_launcher=False, include_fastpaths=False, include_snapshot_origin=True, require_snapshot_origin=True)
                if ts_err:
                    if created_orig:
                        target_snapshot.with_suffix(".js.orig").unlink(missing_ok=True)
                    return _fail(f"{ts_err} in {target_snapshot.name}")
                if ts_mod:
                    _commit_target(target_snapshot, ts_patched, ts_bytes, created_orig)

        # 4. Patch or upgrade dist/mcp/binary-*.js (plus inlined GhidraReleasePolicy if Ghidra 12.2)
        m_bytes = mcp_binary.read_bytes()
        m_current = m_bytes.decode("utf-8")
        has_m_fastpath_fn = bool(_FINGERPRINT_FN_RE.search(m_current) or _COPY_FN_RE.search(m_current))
        needs_m_fastpath = has_m_fastpath_fn and (
            DIRECT_MOUNT_SIGNATURE not in m_current or _FASTPATH_IMPORT_LINES not in m_current
        )
        needs_m_policy = ghidra_12_2 and _GHIDRA_POLICY_OLD in m_current
        if (
            PATCH_SIGNATURE not in m_current
            or AUTO_DISCOVERY_SIGNATURE not in m_current
            or _FS_SYNC_IMPORT_LINE not in m_current
            or needs_m_fastpath
            or needs_m_policy
        ):
            m_base, created_orig = _load_clean_base(mcp_binary)
            m_patched, m_mod, m_err = _inject_bundle_snippets(
                m_base,
                require_launcher=True,
                include_fastpaths=True,
                include_snapshot_origin=True,
            )
            if m_err:
                if created_orig:
                    mcp_binary.with_suffix(".js.orig").unlink(missing_ok=True)
                return _fail(f"{m_err} in {mcp_binary.name}")
            if ghidra_12_2 and _GHIDRA_POLICY_OLD in m_patched:
                m_patched = m_patched.replace(_GHIDRA_POLICY_OLD, _GHIDRA_POLICY_NEW)
                m_mod = True
            if m_mod:
                _commit_target(mcp_binary, m_patched, m_bytes, created_orig)

        # 5. Patch or upgrade dist/cli-runtime/binary-*.js
        if cli_binary and cli_binary.is_file():
            c_bytes = cli_binary.read_bytes()
            c_current = c_bytes.decode("utf-8")
            has_c_fastpath_fn = bool(_FINGERPRINT_FN_RE.search(c_current) or _COPY_FN_RE.search(c_current))
            needs_c_fastpath = has_c_fastpath_fn and (
                DIRECT_MOUNT_SIGNATURE not in c_current or _FASTPATH_IMPORT_LINES not in c_current
            )
            needs_c_policy = ghidra_12_2 and _GHIDRA_POLICY_OLD in c_current
            if (
                PATCH_SIGNATURE not in c_current
                or AUTO_DISCOVERY_SIGNATURE not in c_current
                or _FS_SYNC_IMPORT_LINE not in c_current
                or needs_c_fastpath
                or needs_c_policy
            ):
                c_base, created_orig = _load_clean_base(cli_binary)
                c_patched, c_mod, c_err = _inject_bundle_snippets(
                    c_base,
                    require_launcher=False,
                    include_fastpaths=True,
                    include_snapshot_origin=True,
                )
                if c_err:
                    if created_orig:
                        cli_binary.with_suffix(".js.orig").unlink(missing_ok=True)
                    return _fail(f"{c_err} in {cli_binary.name}")
                if ghidra_12_2 and _GHIDRA_POLICY_OLD in c_patched:
                    c_patched = c_patched.replace(_GHIDRA_POLICY_OLD, _GHIDRA_POLICY_NEW)
                    c_mod = True
                if c_mod:
                    _commit_target(cli_binary, c_patched, c_bytes, created_orig)

        # 5b. Patch or upgrade BinaryTargetResolver bundles (pre-realpath caller path tracking)
        warnings: List[str] = []
        for resolver_file in (target_resolver, mcp_resolver, cli_resolver):
            if resolver_file and resolver_file.is_file():
                r_bytes = resolver_file.read_bytes()
                r_current = r_bytes.decode("utf-8")
                if AUTO_DISCOVERY_SIGNATURE not in r_current:
                    r_base, created_orig = _load_clean_base(resolver_file)
                    r_patched, r_mod, r_err = _inject_bundle_snippets(
                        r_base,
                        require_launcher=False,
                        include_fastpaths=False,
                        include_snapshot_origin=False,
                        include_requested_path=True,
                        require_requested_path=True,
                    )
                    if r_err:
                        if created_orig:
                            resolver_file.with_suffix(".js.orig").unlink(missing_ok=True)
                        warnings.append(f"{r_err} in {resolver_file.name}")
                    elif r_mod:
                        _commit_target(resolver_file, r_patched, r_bytes, created_orig)

        # 6. Patch GhidraReleasePolicy.js and bundled KunaCommand-*.js if Ghidra 12.2 is installed (DEF-BB-040)
        if ghidra_12_2:
            for pol_file in (policy_file, cli_kuna):
                if pol_file and pol_file.is_file():
                    p_bytes = pol_file.read_bytes()
                    p_current = p_bytes.decode("utf-8")
                    if _GHIDRA_POLICY_OLD in p_current:
                        orig_pol = pol_file.with_suffix(".js.orig")
                        created_orig = False
                        if not orig_pol.is_file():
                            _atomic_write_bytes(orig_pol, p_bytes)
                            created_orig = True
                        p_patched = p_current.replace(_GHIDRA_POLICY_OLD, _GHIDRA_POLICY_NEW)
                        _commit_target(pol_file, p_patched, p_bytes, created_orig)

    except (OSError, UnicodeDecodeError) as exc:
        return _fail(f"I/O failure while patching REA distribution: {exc}")

    result: Dict[str, Any] = {
        "success": True,
        "applied_files": applied_files,
        "message": f"Successfully patched {len(applied_files)} files for sub-2s Ghidra acceleration & direct mount.",
    }
    if warnings:
        result["warnings"] = warnings
    return result


def revert_patch(rea_root: Optional[Path] = None) -> Dict[str, Any]:
    """Reverts REA installation to unpatched state using .orig backups with symlink & boundary guards."""
    root = rea_root or find_rea_package_root()
    if not root:
        return {"success": False, "error": "REA package root not found"}

    dist_dir = root / "dist"
    if not dist_dir.is_dir() or dist_dir.is_symlink():
        return {"success": False, "error": f"Invalid REA dist directory: {dist_dir}"}

    dist_res = dist_dir.resolve()
    reverted_files: List[str] = []
    errors: List[str] = []

    for orig in sorted(dist_dir.rglob("*.orig")):
        target = orig.with_suffix("")
        try:
            if orig.is_symlink() or target.is_symlink():
                errors.append(f"Refused symlink during revert: {orig}")
                continue
            if not orig.resolve().is_relative_to(dist_res) or not target.parent.resolve().is_relative_to(dist_res):
                errors.append(f"Refused out-of-tree path during revert: {orig}")
                continue
            orig_bytes = orig.read_bytes()
            _atomic_write_bytes(target, orig_bytes)
            orig.unlink()
            reverted_files.append(str(target))
        except OSError as exc:
            errors.append(f"Failed to revert {target}: {exc}")

    if errors:
        return {
            "success": False,
            "reverted_files": reverted_files,
            "error": "; ".join(errors),
            "errors": errors,
        }

    return {
        "success": True,
        "reverted_files": reverted_files,
        "message": f"Successfully reverted {len(reverted_files)} files from backups.",
    }
