# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Arafat Zahan (@kuasha420)
# Corporate Stewardship & Infrastructure: Purrfect Software Limited (PSL)
# Governed by: ICARO-42/b Ordinance (Company-Supported Personal IP Framework)

"""
Standalone automated build cache invalidation module (ADR-031, Issue #63).

Provides bounded recursive discovery and removal of stale build caches
(.next, .turbo, node_modules/.cache) across workspace roots and monorepo subprojects.
Enforces strict workspace path containment and symlink safety without following external targets.
"""

from __future__ import annotations

import os
from pathlib import Path
import shutil
import stat
import sys
from typing import List, Optional, Sequence, Set, Union

DEFAULT_CACHE_TARGETS: tuple[str, ...] = (".next", ".turbo", "node_modules/.cache")

_IGNORED_DIR_NAMES: set[str] = {
    ".git",
    ".venv",
    "venv",
    ".agents",
    ".agent",
    "dist",
    "build",
    "scratch",
}


def _handle_remove_readonly(func, path, exc_info):
    """
    Error callback for shutil.rmtree to unblock removal of read-only files and directories.
    """
    try:
        parent = os.path.dirname(path)
        if parent and os.path.exists(parent):
            os.chmod(parent, stat.S_IRWXU | stat.S_IRWXG | stat.S_IRWXO)
        if os.path.exists(path):
            os.chmod(path, stat.S_IRWXU | stat.S_IRWXG | stat.S_IRWXO)
        func(path)
    except Exception:
        pass


def _onexc_readonly(func, path, exc):
    """
    Python 3.12+ onexc adapter for _handle_remove_readonly.
    """
    _handle_remove_readonly(func, path, (type(exc), exc, exc.__traceback__))


def _assert_contained(cand: Path, ws_resolved: Path) -> None:
    """
    Assert that the candidate path is strictly contained within the workspace root.
    For symlinks, assert that the symlink file itself is within the workspace.
    For non-symlinks, assert that the resolved target is within the workspace.
    """
    if cand.is_symlink():
        loc = (cand.parent.resolve() / cand.name)
        if not loc.is_relative_to(ws_resolved) or loc == ws_resolved:
            raise AssertionError(
                f"Path containment violation: symlink '{cand}' at '{loc}' escapes workspace '{ws_resolved}'"
            )
    else:
        try:
            resolved = cand.resolve()
        except OSError:
            resolved = cand.absolute()
        if not resolved.is_relative_to(ws_resolved) or resolved == ws_resolved:
            raise AssertionError(
                f"Path containment violation: target '{cand}' resolved to '{resolved}' escapes workspace '{ws_resolved}'"
            )


def purge_workspace_build_caches(
    workspace_dir: Union[Path, str],
    target_dirs: Optional[Sequence[str]] = None,
    dry_run: bool = False,
    max_depth: int = 3,
    subproject: Optional[Union[Path, str]] = None,
) -> List[str]:
    """
    Purge stale build cache directories and files across workspace root and subprojects.

    Args:
        workspace_dir: Path to workspace root directory.
        target_dirs: Sequence of cache directory/file patterns relative to subprojects.
                     Defaults to ('.next', '.turbo', 'node_modules/.cache').
        dry_run: If True, identifies and returns targets without mutating disk.
        max_depth: Maximum directory traversal depth relative to workspace root (default 3).
        subproject: Optional subproject path (relative or absolute) to explicitly check.

    Returns:
        Sorted list of purged (or identified) cache path strings.

    Raises:
        AssertionError: If any target or candidate escapes workspace containment.
    """
    ws = Path(workspace_dir).expanduser()
    if not ws.exists() or not ws.is_dir():
        return []

    ws_resolved = ws.resolve()

    raw_targets = target_dirs if target_dirs is not None else DEFAULT_CACHE_TARGETS
    for raw_t in raw_targets:
        if raw_t in ("", "."):
            raise AssertionError(
                f"Path containment violation: target directory '{raw_t}' must be relative to workspace root and not root itself"
            )

    targets: List[str] = [Path(t).as_posix() for t in raw_targets]

    # Initial containment assertion on targets
    for t in targets:
        t_path = Path(t)
        if t_path.is_absolute() or t in ("", "."):
            raise AssertionError(
                f"Path containment violation: target directory '{t}' must be relative to workspace root and not root itself"
            )
        _assert_contained(ws / t_path, ws_resolved)

    target_first_parts: set[str] = {
        Path(t).parts[0] for t in targets if Path(t).parts
    }
    prune_names: set[str] = _IGNORED_DIR_NAMES | target_first_parts | {"node_modules"}

    found_targets: Set[Path] = set()

    # 1. Direct checks on workspace root
    for t in targets:
        cand = ws / t
        if cand.is_symlink() or cand.exists():
            _assert_contained(cand, ws_resolved)
            found_targets.add(cand)

    # 2. Check explicit subproject if provided
    if subproject:
        sub_path = Path(subproject)
        if not sub_path.is_absolute():
            sub_path = ws / subproject
        _assert_contained(sub_path, ws_resolved)
        if sub_path.is_dir():
            for t in targets:
                cand = sub_path / t
                if cand.is_symlink() or cand.exists():
                    _assert_contained(cand, ws_resolved)
                    found_targets.add(cand)

    # 3. Bounded monorepo traversal (depth <= max_depth)
    for root_dir, dirs, files in os.walk(ws):
        root = Path(root_dir)
        try:
            rel_depth = len(root.relative_to(ws).parts)
        except ValueError:
            dirs[:] = []
            continue

        if rel_depth >= max_depth:
            dirs[:] = []

        # Check candidates at current root
        for t in targets:
            cand = root / t
            if cand.is_symlink() or cand.exists():
                _assert_contained(cand, ws_resolved)
                found_targets.add(cand)

        # Check files at current root matching target names
        for f in files:
            if f in targets:
                cand = root / f
                _assert_contained(cand, ws_resolved)
                found_targets.add(cand)

        # Prune dirs in-place to avoid descending into ignored or target subtrees
        dirs[:] = [d for d in dirs if d not in prune_names]

    purged: List[str] = []
    for target in sorted(found_targets, key=lambda p: str(p)):
        if dry_run:
            purged.append(str(target))
        else:
            try:
                if target.is_symlink():
                    try:
                        target.unlink()
                    except PermissionError:
                        parent = target.parent
                        if parent.exists():
                            os.chmod(parent, stat.S_IRWXU | stat.S_IRWXG | stat.S_IRWXO)
                        target.unlink()
                elif target.is_dir():
                    try:
                        os.chmod(target, stat.S_IRWXU | stat.S_IRWXG | stat.S_IRWXO)
                    except OSError:
                        pass
                    if sys.version_info >= (3, 12):
                        shutil.rmtree(target, onexc=_onexc_readonly)
                    else:
                        shutil.rmtree(target, onerror=_handle_remove_readonly)
                elif target.is_file():
                    try:
                        target.unlink()
                    except PermissionError:
                        parent = target.parent
                        if parent.exists():
                            os.chmod(parent, stat.S_IRWXU | stat.S_IRWXG | stat.S_IRWXO)
                        os.chmod(target, stat.S_IRWXU | stat.S_IRWXG | stat.S_IRWXO)
                        target.unlink()
            except OSError:
                pass

            if not target.exists() and not target.is_symlink():
                purged.append(str(target))

    return sorted(purged)
