# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Arafat Zahan (@kuasha420)
# Corporate Stewardship & Infrastructure: Purrfect Software Limited (PSL)
# Governed by: ICARO-42/b Ordinance (Company-Supported Personal IP Framework)

"""
Agyis Clean CLI: Workspace, Checkpoint, Worktree, Branch, Scratchpad & Opt-In Dist Hygiene (ADR-014 / Issue #90).

Provides automated hygiene and garbage collection across long-running sessions:
- Checkpoints: Rotates and prunes stale compaction checkpoints in .agents/artifacts/
- Worktrees: Prunes dead worktrees and cleans orphaned subagent worktree directories
- Branches: Deletes safely merged ephemeral subagent-* git branches
- Scratch: Cleans expired ephemeral scratchpad files older than TTL window (default 24h)
- Dist: Opt-in cleanup of dist/ build/distribution artifacts (--dist; preserves .git* files)
"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time
from typing import Any, Dict, List, Optional, Set

from harness.delivery.compaction_checkpoint import prune_stale_checkpoints


def clean_checkpoints(
    workspace_dir: Path,
    retention: int = 5,
    dry_run: bool = False,
) -> List[str]:
    """Prunes historical compaction checkpoints exceeding retention limit and stale ephemeral artifacts."""
    if retention < 0:
        retention = 0
    art_dir = workspace_dir / ".agents" / "artifacts"
    if not art_dir.is_dir():
        return []

    pruned_files: List[str] = []

    # 1. Prune stale non-checkpoint artifacts (plans, patches, victory reports, logs)
    stale_patterns = (
        "*.patch",
        "*plan*.md",
        "*victory*.md",
        "COMPLETION_LEDGER.md",
        "master_artifact_*.md",
        "design_compaction_*.md",
        "ladder_*.json",
        "ladder_*.log",
    )
    for pat in stale_patterns:
        try:
            for entry in art_dir.glob(pat):
                if entry.is_file() and entry.name != "compaction_checkpoint_latest.md" and not entry.name.startswith("compaction_checkpoint_"):
                    pruned_files.append(str(entry))
                    if not dry_run:
                        try:
                            entry.unlink(missing_ok=True)
                        except OSError:
                            pass
        except OSError:
            pass

    # 2. Prune compaction checkpoints (DRY delegation to prune_stale_checkpoints)
    pruned = prune_stale_checkpoints(art_dir, retention_limit=retention, dry_run=dry_run)
    for p in pruned:
        pruned_files.append(str(p))
    return pruned_files


def clean_worktrees(
    workspace_dir: Path,
    dry_run: bool = False,
) -> List[str]:
    """Prunes dead git worktrees via git worktree prune and removes orphaned subagent-* directories."""
    pruned_worktrees: List[str] = []

    def _run_git(args: List[str]) -> str:
        try:
            res = subprocess.run(
                ["git"] + args,
                cwd=str(workspace_dir),
                capture_output=True,
                text=True,
                timeout=3.0,
                check=False,
            )
            return res.stdout.strip()
        except Exception:
            return ""

    # 1. Prune registered subagent worktrees
    wt_out = _run_git(["worktree", "list", "--porcelain"])
    for line in wt_out.splitlines():
        if line.startswith("worktree "):
            p = line.split("worktree ", 1)[1].strip()
            if ".gemini/antigravity/worktrees" in p or "/subagent-" in p:
                pruned_worktrees.append(p)
                if not dry_run:
                    _run_git(["worktree", "remove", "--force", p])
                    if Path(p).is_dir():
                        shutil.rmtree(p, ignore_errors=True)

    if dry_run:
        out = _run_git(["worktree", "prune", "--dry-run", "-v"])
        if out:
            for line in out.splitlines():
                if line.strip():
                    pruned_worktrees.append(line.strip())
    else:
        out = _run_git(["worktree", "prune", "-v"])
        if out:
            for line in out.splitlines():
                if line.strip():
                    pruned_worktrees.append(line.strip())

    # Check for truly orphaned subagent directories in ~/.gemini/antigravity/worktrees
    antigravity_worktrees = Path.home() / ".gemini" / "antigravity" / "worktrees"
    if antigravity_worktrees.is_dir():
        try:
            for session_dir in antigravity_worktrees.iterdir():
                if not session_dir.is_dir():
                    continue
                for wt_dir in session_dir.glob("subagent-*"):
                    if not wt_dir.is_dir():
                        continue
                    git_link = wt_dir / ".git"
                    is_orphaned = False
                    if not git_link.exists():
                        is_orphaned = True
                    elif git_link.is_file():
                        try:
                            content = git_link.read_text(encoding="utf-8").strip()
                            if content.startswith("gitdir:"):
                                gitdir_path = Path(content.split(":", 1)[1].strip())
                                if not gitdir_path.exists():
                                    is_orphaned = True
                        except OSError:
                            pass
                    if is_orphaned:
                        pruned_worktrees.append(str(wt_dir))
                        if not dry_run:
                            shutil.rmtree(wt_dir, ignore_errors=True)
        except OSError:
            pass

    return pruned_worktrees


def clean_branches(
    workspace_dir: Path,
    dry_run: bool = False,
) -> List[str]:
    """Discovers and deletes safely merged ephemeral subagent-* git branches."""
    deleted_branches: List[str] = []

    def _run_git(args: List[str]) -> str:
        try:
            res = subprocess.run(
                ["git"] + args,
                cwd=str(workspace_dir),
                capture_output=True,
                text=True,
                timeout=3.0,
                check=False,
            )
            return res.stdout.strip()
        except Exception:
            return ""

    current_branch = _run_git(["branch", "--show-current"]).strip()
    active_branches: Set[str] = {current_branch} if current_branch else set()
    wt_list = _run_git(["worktree", "list", "--porcelain"])
    for line in wt_list.splitlines():
        if line.startswith("branch refs/heads/"):
            active_branches.add(line.replace("branch refs/heads/", "").strip())

    merged_output = _run_git(["branch", "--merged"])
    if not merged_output:
        return []

    for line in merged_output.splitlines():
        branch = line.strip().lstrip("*+ ").strip()
        if not branch:
            continue
        if branch.startswith("subagent-") and branch not in active_branches:
            deleted_branches.append(branch)
            if not dry_run:
                _run_git(["branch", "-d", branch])

    return deleted_branches


def prune_empty_scratch_dirs(
    scratch_dir: Path,
    ttl_seconds: float,
    now: float,
    orig_mtimes: Dict[Path, float],
    pruned_files: Set[Path],
    dry_run: bool = False,
) -> List[str]:
    """
    Walks scratch_dir bottom-up and prunes empty subdirectories (skipping scratch_dir
    itself and .git* entries) that either had expired files unlinked/queued or whose
    original mtime is older than ttl_seconds.
    """
    pruned_dirs: List[str] = []
    if not scratch_dir.is_dir():
        return pruned_dirs

    pruned_dirs_set: Set[Path] = set()
    dirs_with_expired: Set[Path] = set()
    for pf in pruned_files:
        cur = pf.parent
        while cur != scratch_dir and scratch_dir in cur.parents:
            dirs_with_expired.add(cur)
            cur = cur.parent

    try:
        for root, dirs, files in os.walk(scratch_dir, topdown=False):
            d = Path(root)
            if d == scratch_dir:
                continue
            try:
                rel_parts = d.relative_to(scratch_dir).parts
                if any(part.startswith(".git") for part in rel_parts):
                    continue
            except ValueError:
                continue

            has_remaining_file = any((d / f) not in pruned_files for f in files)
            has_remaining_dir = any((d / sub) not in pruned_dirs_set for sub in dirs)
            if has_remaining_file or has_remaining_dir:
                continue

            orig_mtime = orig_mtimes.get(d)
            if orig_mtime is None:
                try:
                    orig_mtime = d.stat().st_mtime
                except OSError:
                    continue

            if (d in dirs_with_expired) or ((now - orig_mtime) >= ttl_seconds):
                pruned_dirs.append(str(d))
                pruned_dirs_set.add(d)
                if not dry_run:
                    try:
                        d.rmdir()
                    except OSError:
                        pass
    except OSError:
        pass

    return pruned_dirs


def clean_scratchpads(
    workspace_dir: Path,
    scratch_hours: float = 24.0,
    dry_run: bool = False,
    pruned_dirs_out: Optional[List[str]] = None,
) -> List[str]:
    """Scans scratch directories, unlinks files older than TTL (scratch_hours), and prunes empty dirs."""
    pruned_scratch: List[str] = []
    ttl_seconds = max(0.0, scratch_hours * 3600.0)
    now = time.time()

    scratch_dirs = [
        workspace_dir / "scratch",
        workspace_dir / ".agents" / "artifacts" / "scratch",
        workspace_dir / ".agents" / "teamwork",
    ]

    for s_dir in scratch_dirs:
        if not s_dir.is_dir():
            continue
        orig_mtimes: Dict[Path, float] = {}
        local_pruned_files: Set[Path] = set()
        try:
            for root, _, files in os.walk(s_dir):
                root_path = Path(root)
                try:
                    orig_mtimes[root_path] = root_path.stat().st_mtime
                except OSError:
                    pass
                for f in files:
                    file_path = root_path / f
                    if file_path.name.startswith(".git"):
                        continue
                    try:
                        mtime = file_path.stat().st_mtime
                        if (now - mtime) >= ttl_seconds:
                            pruned_scratch.append(str(file_path))
                            local_pruned_files.add(file_path)
                            if not dry_run:
                                file_path.unlink()
                    except OSError:
                        pass
        except OSError:
            pass

        pruned_dirs = prune_empty_scratch_dirs(
            scratch_dir=s_dir,
            ttl_seconds=ttl_seconds,
            now=now,
            orig_mtimes=orig_mtimes,
            pruned_files=local_pruned_files,
            dry_run=dry_run,
        )
        if pruned_dirs_out is not None:
            pruned_dirs_out.extend(pruned_dirs)

    return pruned_scratch


def clean_dist(
    workspace_dir: Path,
    dry_run: bool = False,
) -> List[str]:
    """Removes stale build/distribution artifacts inside dist/, preserving .git* entries."""
    dist_dir = workspace_dir / "dist"
    if dist_dir.is_symlink() or not dist_dir.is_dir():
        return []

    pruned_dist: List[str] = []
    for entry in sorted(dist_dir.iterdir(), key=lambda p: p.name):
        if entry.name.startswith(".git"):
            continue
        if dry_run:
            pruned_dist.append(str(entry))
            continue
        if entry.is_dir() and not entry.is_symlink():
            shutil.rmtree(entry)
        else:
            entry.unlink()
        pruned_dist.append(str(entry))

    return pruned_dist


def cmd_clean(args: argparse.Namespace) -> int:
    """Entry point for `agyis clean` CLI."""
    t0 = time.perf_counter()

    workspace = getattr(args, "workspace", None)
    if workspace:
        ws = Path(workspace).resolve()
    else:
        ws = Path.cwd().resolve()

    do_checkpoints = getattr(args, "checkpoints", False)
    do_worktrees = getattr(args, "worktrees", False)
    do_branches = getattr(args, "branches", False)
    do_scratch = getattr(args, "scratch", False)
    do_dist = bool(getattr(args, "dist", False))
    do_all = getattr(args, "all", False)

    # Default to --all if no specific category is selected
    if not (do_checkpoints or do_worktrees or do_branches or do_scratch or do_dist or do_all):
        do_all = True

    if do_all:
        do_checkpoints = True
        do_worktrees = True
        do_branches = True
        do_scratch = True

    raw_ret = getattr(args, "retention", None)
    try:
        retention = 5 if raw_ret is None else max(0, int(raw_ret))
    except (TypeError, ValueError):
        retention = 5
    raw_hours = getattr(args, "scratch_hours", None)
    try:
        scratch_hours = 24.0 if raw_hours is None else max(0.0, float(raw_hours))
    except (TypeError, ValueError):
        scratch_hours = 24.0
    dry_run = getattr(args, "dry_run", False)
    json_output = getattr(args, "json", False)

    pruned_cps: List[str] = []
    pruned_wts: List[str] = []
    deleted_brs: List[str] = []
    pruned_scrs: List[str] = []
    pruned_scr_dirs: List[str] = []
    pruned_dist: List[str] = []
    dist_error: Optional[str] = None

    if do_checkpoints:
        pruned_cps = clean_checkpoints(ws, retention=retention, dry_run=dry_run)
    if do_worktrees:
        pruned_wts = clean_worktrees(ws, dry_run=dry_run)
    if do_branches:
        deleted_brs = clean_branches(ws, dry_run=dry_run)
    if do_scratch:
        pruned_scrs = clean_scratchpads(
            ws,
            scratch_hours=scratch_hours,
            dry_run=dry_run,
            pruned_dirs_out=pruned_scr_dirs,
        )
    if do_dist:
        try:
            pruned_dist = clean_dist(ws, dry_run=dry_run)
        except OSError as exc:
            dist_error = str(exc)

    elapsed_ms = round((time.perf_counter() - t0) * 1000.0, 2)
    total_pruned = (
        len(pruned_cps)
        + len(pruned_wts)
        + len(deleted_brs)
        + len(pruned_scrs)
        + len(pruned_scr_dirs)
        + len(pruned_dist)
    )

    if json_output:
        report: Dict[str, Any] = {
            "status": "error" if dist_error is not None else "ok",
            "dry_run": dry_run,
            "workspace": str(ws),
            "checkpoints": {"pruned": pruned_cps, "count": len(pruned_cps)},
            "worktrees": {"pruned": pruned_wts, "count": len(pruned_wts)},
            "branches": {"deleted": deleted_brs, "count": len(deleted_brs)},
            "scratch": {
                "pruned": pruned_scrs,
                "count": len(pruned_scrs),
                "pruned_dirs": pruned_scr_dirs,
                "dirs_count": len(pruned_scr_dirs),
            },
            "dist": {"pruned": pruned_dist, "count": len(pruned_dist)},
            "total_pruned": total_pruned,
            "elapsed_ms": elapsed_ms,
        }
        if dist_error is not None:
            report["error"] = dist_error
        print(json.dumps(report, indent=2))
        return 1 if dist_error is not None else 0

    if dist_error is not None:
        print(f"❌ Failed to clean dist/: {dist_error}", file=sys.stderr)
        return 1

    mode_label = "[DRY-RUN] " if dry_run else ""
    print(f"=== Agyis Hygiene & Workspace Cleanup {mode_label}===")
    print(f"Workspace: {ws}")

    if do_checkpoints:
        print(f"Checkpoints: {len(pruned_cps)} pruned (retained top {retention})")
        for cp in pruned_cps:
            print(f"  - {Path(cp).name}")

    if do_worktrees:
        print(f"Worktrees:   {len(pruned_wts)} prunable worktrees / orphaned directories")
        for wt in pruned_wts:
            print(f"  - {wt}")

    if do_branches:
        print(f"Branches:    {len(deleted_brs)} merged subagent branches deleted")
        for br in deleted_brs:
            print(f"  - {br}")

    if do_scratch:
        print(
            f"Scratchpads: {len(pruned_scrs)} files, {len(pruned_scr_dirs)} empty dirs pruned (> {scratch_hours:.0f}h old)"
        )
        for scr in pruned_scrs:
            print(f"  - {Path(scr).name}")
        for d in pruned_scr_dirs:
            print(f"  - [dir] {Path(d).name}")

    if do_dist:
        print(f"Dist:        {len(pruned_dist)} build artifacts removed")
        for d_item in pruned_dist:
            print(f"  - {Path(d_item).name}")

    print(f"✔ Completed in {elapsed_ms:.2f} ms (Total items cleaned: {total_pruned})")
    return 0
