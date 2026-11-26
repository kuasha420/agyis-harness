# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Arafat Zahan (@kuasha420)
# Corporate Stewardship & Infrastructure: Purrfect Software Limited (PSL)
# Governed by: ICARO-42/b Ordinance (Company-Supported Personal IP Framework)

"""
Shared filesystem, ESM injection, Ghidra policy rewrite, and rollback helpers for REA patching.
"""

from __future__ import annotations

import importlib.resources
import os
from pathlib import Path
import re
import tempfile
from typing import List, Optional, Tuple

PATCH_SIGNATURE = "REA_GHIDRA_PROJECT_DIR"
DIRECT_MOUNT_SIGNATURE = "REA_DIRECT_MOUNT_ACTIVE"
AUTO_DISCOVERY_SIGNATURE = "AGYIS_REA_AUTODISCOVERY_V4"

FS_SYNC_IMPORT_LINE = (
    'import { lstatSync as __agyisLstatSync, readFileSync as __agyisReadFileSync, '
    'readdirSync as __agyisReaddirSync, realpathSync as __agyisRealpathSync, '
    'statSync as __agyisStatSync, symlinkSync as __agyisSymlinkSync } from "node:fs";\n'
    'import { homedir as __agyisHomedir } from "node:os";\n'
    'import { join as __agyisOsJoin } from "node:path";'
)
FASTPATH_IMPORT_LINES = (
    'import { readFile as __agyisReadFile, readdir as __agyisReaddir, stat as __agyisStat } from "node:fs/promises";\n'
    'import { dirname as __agyisDirname, join as __agyisJoin, resolve as __agyisResolve } from "node:path";'
)

FINGERPRINT_FN_RE = re.compile(
    r"((?:(?:export\s+)?(?:const\s+)?fingerprintGhidraProject\s*=\s*async\s*\([^)]*\)\s*=>\s*\{|"
    r"async\s+function\s+fingerprintGhidraProject\s*\([^)]*\)\s*\{))"
)
COPY_FN_RE = re.compile(
    r"((?:(?:export\s+)?(?:const\s+)?copyExistingGhidraProject\s*=\s*async\s*\([^)]*\)\s*=>\s*\{|"
    r"async\s+function\s+copyExistingGhidraProject\s*\([^)]*\)\s*\{))"
)
_SNAPSHOT_PATH_RE = re.compile(
    r"(const\s+snapshotPath\s*=\s*join\(runtimeRoot,\s*`target-\$\{expectedSha256\.slice\(0,\s*12\)\}\$\{suffix\}`\);)"
)
_REQUESTED_PATH_RE = re.compile(
    r"(const\s+canonical\s*=\s*await\s+realpath\(candidate\);)"
)
GHIDRA_POLICY_RE = re.compile(r"""(SUPPORTED_GHIDRA_VERSION\s*=\s*)(["'])([^"']+)(\2)""")


def _load_asset(name: str) -> str:
    """Loads an externalized JavaScript patch template via importlib.resources."""
    return importlib.resources.files("harness.re.assets").joinpath(name).read_text(encoding="utf-8")


LAUNCHER_SNIPPET = _load_asset("launcher_direct_mount.js")
FASTPATH_FINGERPRINT_SNIPPET = _load_asset("fastpath_fingerprint.js")
FASTPATH_COPY_SNIPPET = _load_asset("fastpath_copy.js")
SNAPSHOT_ORIGIN_SNIPPET = _load_asset("snapshot_origin.js")
REQUESTED_PATH_SNIPPET = _load_asset("requested_path.js")


def safe_read_text(path: Optional[Path]) -> str:
    """Safely reads UTF-8 text from path, returning empty string on missing or unreadable file."""
    if not path or not path.is_file():
        return ""
    try:
        return path.read_text(encoding="utf-8", errors="ignore")
    except (OSError, PermissionError):
        return ""


def atomic_write_bytes(target: Path, data: bytes) -> None:
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


def atomic_write_text(target: Path, content: str) -> None:
    """Atomically writes UTF-8 text to target."""
    atomic_write_bytes(target, content.encode("utf-8"))


def validate_dist_file(target: Path, dist_dir: Path) -> Optional[str]:
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


def ensure_aliased_imports(
    content: str,
    *,
    need_fs_sync: bool = False,
    need_fastpath: bool = False,
) -> str:
    """Ensures collision-free aliased Node ESM imports exist for injected snippets."""
    blocks: List[str] = []
    if need_fs_sync and FS_SYNC_IMPORT_LINE not in content:
        blocks.append(FS_SYNC_IMPORT_LINE)
    if need_fastpath and FASTPATH_IMPORT_LINES not in content:
        blocks.append(FASTPATH_IMPORT_LINES)
    if not blocks:
        return content
    return _prepend_esm_imports(content, "\n".join(blocks))


def load_clean_base(file_path: Path) -> Tuple[str, bool]:
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
        atomic_write_text(orig, current)
        created_orig = True
    return current, created_orig


def inject_bundle_snippets(
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
        out, fp_count = FINGERPRINT_FN_RE.subn(
            lambda m: f"{m.group(1)}\n{FASTPATH_FINGERPRINT_SNIPPET}",
            out,
            count=1,
        )
        out, cp_count = COPY_FN_RE.subn(
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
        out = ensure_aliased_imports(
            out,
            need_fs_sync=need_fs_sync,
            need_fastpath=need_fastpath,
        )

    return out, modified, None


def needs_ghidra_policy_update(text: str, target_version: Optional[str]) -> bool:
    """Return True when text contains SUPPORTED_GHIDRA_VERSION mismatched from target_version."""
    if not target_version:
        return False
    return any(m.group(3) != target_version for m in GHIDRA_POLICY_RE.finditer(text))


def rewrite_ghidra_policy(text: str, target_version: Optional[str]) -> Tuple[str, bool]:
    """Update SUPPORTED_GHIDRA_VERSION string literals to match active installed Ghidra version."""
    if not target_version:
        return text, False
    changed = False

    def _sub(match: re.Match[str]) -> str:
        nonlocal changed
        if match.group(3) != target_version:
            changed = True
        return f"{match.group(1)}{match.group(2)}{target_version}{match.group(4)}"

    updated = GHIDRA_POLICY_RE.sub(_sub, text)
    return updated, changed


def rollback_patch_transaction(
    rollback_log: List[Tuple[Path, bytes, Path, bool]],
) -> List[str]:
    """Restores all files mutated in a failed apply_patch transaction."""
    errors: List[str] = []
    for target, prior_bytes, orig_path, created_orig in reversed(rollback_log):
        try:
            atomic_write_bytes(target, prior_bytes)
        except OSError as exc:
            errors.append(f"Failed to restore {target}: {exc}")
        if created_orig:
            try:
                orig_path.unlink(missing_ok=True)
            except OSError as exc:
                errors.append(f"Failed to clean temporary backup {orig_path}: {exc}")
    return errors
