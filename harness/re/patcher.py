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

import json
import os
from pathlib import Path
import shutil
import sys
from typing import Any, Dict, List, Optional, Tuple

from harness.re.patcher_utils import (
    AUTO_DISCOVERY_SIGNATURE,
    COPY_FN_RE as _COPY_FN_RE,
    DIRECT_MOUNT_SIGNATURE,
    FASTPATH_COPY_SNIPPET,
    FASTPATH_FINGERPRINT_SNIPPET,
    FASTPATH_IMPORT_LINES as _FASTPATH_IMPORT_LINES,
    FINGERPRINT_FN_RE as _FINGERPRINT_FN_RE,
    FS_SYNC_IMPORT_LINE as _FS_SYNC_IMPORT_LINE,
    GHIDRA_POLICY_RE,
    LAUNCHER_SNIPPET,
    PATCH_SIGNATURE,
    REQUESTED_PATH_SNIPPET,
    SNAPSHOT_ORIGIN_SNIPPET,
    atomic_write_bytes,
    atomic_write_text,
    inject_bundle_snippets,
    load_clean_base,
    needs_ghidra_policy_update,
    rewrite_ghidra_policy,
    rollback_patch_transaction,
    safe_read_text,
    validate_dist_file,
)
from harness.runtime.tool_checks_common import parse_version
from harness.runtime.tool_checks_rea import (
    detect_installed_ghidra_version,
    is_ghidra_12_2_installed,
)


def _resolve_target_ghidra_version() -> Optional[str]:
    """Dynamically resolve the active installed Ghidra 12.x release string."""
    detected = detect_installed_ghidra_version()
    if detected and parse_version(detected)[0] == 12:
        if detected == "12.2" and not is_ghidra_12_2_installed():
            return None
        return detected
    if is_ghidra_12_2_installed():
        return "12.2"
    return None


def find_rea_package_root() -> Optional[Path]:
    """Discovers the installed rea-agents npm/pnpm package directory."""
    env_path = os.environ.get("REA_PACKAGE_PATH")
    if env_path:
        p = Path(env_path).resolve()
        if p.is_dir() and (p / "dist").is_dir():
            return p

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

    home = Path.home()
    pnpm_global = home / ".local" / "share" / "pnpm" / "global"
    if pnpm_global.is_dir():
        for cand in pnpm_global.glob("**/node_modules/rea-agents"):
            if (cand / "dist" / "ghidra").is_dir():
                return cand.resolve()

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
            if not cand.name.endswith(".orig") and "ghidraHeadlessArguments" in safe_read_text(cand):
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
            if not cand.name.endswith(".orig") and "ghidraHeadlessArguments" in safe_read_text(cand):
                cli_binary = cand
                break
        for cand in sorted(cli_dir.glob("BinaryTargetResolver-*.js")):
            if not cand.name.endswith(".orig"):
                cli_resolver = cand
                break
        for cand in sorted(cli_dir.glob("KunaCommand-*.js")):
            if not cand.name.endswith(".orig") and "SUPPORTED_GHIDRA_VERSION" in safe_read_text(cand):
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
            if "SUPPORTED_GHIDRA_VERSION" in safe_read_text(p):
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

    l_text = safe_read_text(launcher)
    m_text = safe_read_text(mcp_binary)
    s_text = safe_read_text(snapshot)
    ts_text = safe_read_text(target_snapshot)
    tr_text = safe_read_text(target_resolver)
    mr_text = safe_read_text(mcp_resolver)
    c_text = safe_read_text(cli_binary)
    cr_text = safe_read_text(cli_resolver)

    launcher_patched = bool(launcher) and PATCH_SIGNATURE in l_text
    mcp_patched = bool(mcp_binary) and PATCH_SIGNATURE in m_text
    snapshot_patched = bool(snapshot) and DIRECT_MOUNT_SIGNATURE in s_text
    cli_patched = bool(cli_binary) and PATCH_SIGNATURE in c_text and DIRECT_MOUNT_SIGNATURE in c_text

    target_ghidra_version = _resolve_target_ghidra_version()
    policy_targets = _policy_bearing_targets(targets)
    policy_texts = [safe_read_text(p) for p in policy_targets]
    if target_ghidra_version:
        policy_patched = bool(policy_targets) and all(
            not needs_ghidra_policy_update(txt, target_ghidra_version) for txt in policy_texts
        )
    else:
        policy_patched = bool(policy_targets) and all(
            not GHIDRA_POLICY_RE.search(txt) or (
                (m := GHIDRA_POLICY_RE.search(txt)) is not None and m.group(3) != "12.1.4"
            )
            for txt in policy_texts
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
        "target_ghidra_version": target_ghidra_version,
        "launcher_path": str(launcher) if launcher else None,
        "mcp_path": str(mcp_binary) if mcp_binary else None,
        "cli_path": str(cli_binary) if cli_binary else None,
        "policy_path": str(policy_file) if policy_file else None,
        "policy_targets": [str(p) for p in policy_targets],
        "message": msg,
    }


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

    target_ghidra_version = _resolve_target_ghidra_version()
    applied_files: List[str] = []
    rollback_log: List[Tuple[Path, bytes, Path, bool]] = []

    def _fail(message: str) -> Dict[str, Any]:
        rb_errors = rollback_patch_transaction(rollback_log)
        res: Dict[str, Any] = {"success": False, "error": message, "rolled_back": bool(rollback_log)}
        if rb_errors:
            res["rollback_errors"] = rb_errors
        return res

    def _commit_target(target: Path, new_content: str, prior_bytes: bytes, created_orig: bool) -> None:
        orig_path = target.with_suffix(".js.orig")
        rollback_log.append((target, prior_bytes, orig_path, created_orig))
        atomic_write_text(target, new_content)
        if str(target) not in applied_files:
            applied_files.append(str(target))

    def _patch_bundle(
        target: Path,
        *,
        needs_upgrade: bool,
        require_launcher: bool,
        include_fastpaths: bool,
        include_snapshot_origin: bool,
        include_requested_path: bool = False,
        require_fastpaths: bool = False,
        require_snapshot_origin: bool = False,
        require_requested_path: bool = False,
        apply_policy: bool = False,
        warn_only: bool = False,
    ) -> Optional[str]:
        if not needs_upgrade:
            return None
        prior_bytes = target.read_bytes()
        base_txt, created_orig = load_clean_base(target)
        patched_txt, modified, err = inject_bundle_snippets(
            base_txt,
            require_launcher=require_launcher,
            include_fastpaths=include_fastpaths,
            include_snapshot_origin=include_snapshot_origin,
            include_requested_path=include_requested_path,
            require_fastpaths=require_fastpaths,
            require_snapshot_origin=require_snapshot_origin,
            require_requested_path=require_requested_path,
        )
        if err:
            if created_orig:
                target.with_suffix(".js.orig").unlink(missing_ok=True)
            if warn_only:
                return f"{err} in {target.name}"
            raise RuntimeError(f"{err} in {target.name}")
        if apply_policy and target_ghidra_version:
            patched_txt, pol_changed = rewrite_ghidra_policy(patched_txt, target_ghidra_version)
            modified = modified or pol_changed
        if modified:
            _commit_target(target, patched_txt, prior_bytes, created_orig)
        return None

    try:
        for cand in (launcher, snapshot, target_snapshot, mcp_binary, cli_binary, target_resolver, mcp_resolver, cli_resolver, cli_kuna, policy_file):
            if cand and cand.exists():
                val_err = validate_dist_file(cand, dist_dir)
                if val_err:
                    return _fail(val_err)

        l_cur = launcher.read_text(encoding="utf-8")
        _patch_bundle(
            launcher,
            needs_upgrade=(PATCH_SIGNATURE not in l_cur or AUTO_DISCOVERY_SIGNATURE not in l_cur or _FS_SYNC_IMPORT_LINE not in l_cur),
            require_launcher=True,
            include_fastpaths=False,
            include_snapshot_origin=False,
        )

        if snapshot and snapshot.is_file():
            s_cur = snapshot.read_text(encoding="utf-8")
            _patch_bundle(
                snapshot,
                needs_upgrade=(DIRECT_MOUNT_SIGNATURE not in s_cur or AUTO_DISCOVERY_SIGNATURE not in s_cur or _FASTPATH_IMPORT_LINES not in s_cur),
                require_launcher=False,
                include_fastpaths=True,
                include_snapshot_origin=False,
                require_fastpaths=True,
            )

        if target_snapshot and target_snapshot.is_file():
            ts_cur = target_snapshot.read_text(encoding="utf-8")
            _patch_bundle(
                target_snapshot,
                needs_upgrade=(AUTO_DISCOVERY_SIGNATURE not in ts_cur),
                require_launcher=False,
                include_fastpaths=False,
                include_snapshot_origin=True,
                require_snapshot_origin=True,
            )

        for bundle, req_launcher in ((mcp_binary, True), (cli_binary, False)):
            if not bundle or not bundle.is_file():
                continue
            cur = bundle.read_text(encoding="utf-8")
            has_fp = bool(_FINGERPRINT_FN_RE.search(cur) or _COPY_FN_RE.search(cur))
            needs_fp = has_fp and (DIRECT_MOUNT_SIGNATURE not in cur or _FASTPATH_IMPORT_LINES not in cur)
            needs_pol = needs_ghidra_policy_update(cur, target_ghidra_version)
            _patch_bundle(
                bundle,
                needs_upgrade=(PATCH_SIGNATURE not in cur or AUTO_DISCOVERY_SIGNATURE not in cur or _FS_SYNC_IMPORT_LINE not in cur or needs_fp or needs_pol),
                require_launcher=req_launcher,
                include_fastpaths=True,
                include_snapshot_origin=True,
                apply_policy=True,
            )

        warnings: List[str] = []
        for resolver_file in (target_resolver, mcp_resolver, cli_resolver):
            if resolver_file and resolver_file.is_file():
                r_cur = resolver_file.read_text(encoding="utf-8")
                w = _patch_bundle(
                    resolver_file,
                    needs_upgrade=(AUTO_DISCOVERY_SIGNATURE not in r_cur),
                    require_launcher=False,
                    include_fastpaths=False,
                    include_snapshot_origin=False,
                    include_requested_path=True,
                    require_requested_path=True,
                    warn_only=True,
                )
                if w:
                    warnings.append(w)

        if target_ghidra_version:
            for pol_file in (policy_file, cli_kuna):
                if pol_file and pol_file.is_file():
                    p_bytes = pol_file.read_bytes()
                    p_current = p_bytes.decode("utf-8")
                    if needs_ghidra_policy_update(p_current, target_ghidra_version):
                        orig_pol = pol_file.with_suffix(".js.orig")
                        created_orig = False
                        if not orig_pol.is_file():
                            atomic_write_bytes(orig_pol, p_bytes)
                            created_orig = True
                        p_patched, _ = rewrite_ghidra_policy(p_current, target_ghidra_version)
                        _commit_target(pol_file, p_patched, p_bytes, created_orig)

    except RuntimeError as exc:
        return _fail(str(exc))
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
            atomic_write_bytes(target, orig_bytes)
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
