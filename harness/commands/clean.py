# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Arafat Zahan (@kuasha420)
# Corporate Stewardship & Infrastructure: Purrfect Software Limited (PSL)
# Governed by: ICARO-42/b Ordinance (Company-Supported Personal IP Framework)

"""
Agyis Clean CLI: Workspace, Checkpoint, Worktree, Branch & Scratchpad Hygiene (ADR-014 / Issue #90).

Provides automated hygiene and garbage collection across long-running sessions:
- Checkpoints: Rotates and prunes stale compaction checkpoints in .agents/artifacts/
- Worktrees: Prunes dead worktrees and cleans orphaned subagent worktree directories
- Branches: Deletes safely merged ephemeral subagent-* git branches
- Scratch: Cleans expired ephemeral scratchpad files older than TTL window (default 24h)
"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import time
from typing import Any, Dict, List, Optional, Set

from harness.delivery.compaction_checkpoint import prune_stale_checkpoints


def clean_checkpoints(
    workspace_dir: Path,
    retention: int = 5,
    dry_run: bool = False,
) -> List[str]:
    """Prunes historical compaction checkpoints exceeding retention limit."""
    art_dir = workspace_dir / ".agents" / "artifacts"
    if not art_dir.is_dir():
        return []

    if dry_run:
        checkpoint_pattern = re.compile(r"^compaction_checkpoint_(\d+)\.md$")
        sortable: List[tuple[float, Path]] = []
        try:
            for entry in art_dir.glob("compaction_checkpoint_*.md"):
                if not entry.is_file() or entry.name == "compaction_checkpoint_latest.md":
                    continue
                m = checkpoint_pattern.match(entry.name)
                sort_key = float(m.group(1)) if m else entry.stat().st_mtime
                sortable.append((sort_key, entry))
        except OSError:
            return []

        sortable.sort(key=lambda x: x[0], reverse=True)
        to_prune = sortable[retention:]
        return [str(p) for _, p in to_prune]

    pruned = prune_stale_checkpoints(art_dir, retention_limit=retention)
    return [str(p) for p in pruned]


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


def clean_scratchpads(
    workspace_dir: Path,
    scratch_hours: float = 24.0,
    dry_run: bool = False,
) -> List[str]:
    """Scans scratch directories and unlinks files older than TTL (scratch_hours)."""
    pruned_scratch: List[str] = []
    ttl_seconds = max(0.0, scratch_hours * 3600.0)
    now = time.time()

    scratch_dirs = [
        workspace_dir / "scratch",
        workspace_dir / ".agents" / "artifacts" / "scratch",
    ]

    for s_dir in scratch_dirs:
        if not s_dir.is_dir():
            continue
        try:
            for root, _, files in os.walk(s_dir):
                for f in files:
                    file_path = Path(root) / f
                    if file_path.name.startswith(".git"):
                        continue
                    try:
                        mtime = file_path.stat().st_mtime
                        if (now - mtime) >= ttl_seconds:
                            pruned_scratch.append(str(file_path))
                            if not dry_run:
                                file_path.unlink()
                    except OSError:
                        pass
        except OSError:
            pass

    return pruned_scratch


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
    do_all = getattr(args, "all", False)

    # Default to --all if no specific category is selected
    if not (do_checkpoints or do_worktrees or do_branches or do_scratch or do_all):
        do_all = True

    if do_all:
        do_checkpoints = True
        do_worktrees = True
        do_branches = True
        do_scratch = True

    retention = getattr(args, "retention", 5) or 5
    scratch_hours = getattr(args, "scratch_hours", 24.0) or 24.0
    dry_run = getattr(args, "dry_run", False)
    json_output = getattr(args, "json", False)

    pruned_cps: List[str] = []
    pruned_wts: List[str] = []
    deleted_brs: List[str] = []
    pruned_scrs: List[str] = []

    if do_checkpoints:
        pruned_cps = clean_checkpoints(ws, retention=retention, dry_run=dry_run)
    if do_worktrees:
        pruned_wts = clean_worktrees(ws, dry_run=dry_run)
    if do_branches:
        deleted_brs = clean_branches(ws, dry_run=dry_run)
    if do_scratch:
        pruned_scrs = clean_scratchpads(ws, scratch_hours=scratch_hours, dry_run=dry_run)

    elapsed_ms = round((time.perf_counter() - t0) * 1000.0, 2)
    total_pruned = len(pruned_cps) + len(pruned_wts) + len(deleted_brs) + len(pruned_scrs)

    if json_output:
        report: Dict[str, Any] = {
            "status": "ok",
            "dry_run": dry_run,
            "workspace": str(ws),
            "checkpoints": {"pruned": pruned_cps, "count": len(pruned_cps)},
            "worktrees": {"pruned": pruned_wts, "count": len(pruned_wts)},
            "branches": {"deleted": deleted_brs, "count": len(deleted_brs)},
            "scratch": {"pruned": pruned_scrs, "count": len(pruned_scrs)},
            "total_pruned": total_pruned,
            "elapsed_ms": elapsed_ms,
        }
        print(json.dumps(report, indent=2))
        return 0

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
        print(f"Scratchpads: {len(pruned_scrs)} files pruned (> {scratch_hours:.0f}h old)")
        for scr in pruned_scrs:
            print(f"  - {Path(scr).name}")

    print(f"✔ Completed in {elapsed_ms:.2f} ms (Total items cleaned: {total_pruned})")
    return 0
