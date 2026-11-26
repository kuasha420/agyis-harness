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
import errno
try:
    import fcntl
except ImportError:  # pragma: no cover - non-POSIX fallback
    fcntl = None  # type: ignore[assignment]
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

from harness.utils import theme
import time
from typing import Any, Dict, List, Optional, Set, Tuple

from harness.delivery import purge_build_caches
from harness.delivery.compaction_checkpoint import prune_stale_checkpoints


def _is_cid_actively_locked(cid: str) -> bool:
    """Returns True if any Antigravity surface holds an active flock on presence/<cid>.lock."""
    if not cid or fcntl is None:
        return False
    for surface_name in ("antigravity", "antigravity-cli", "antigravity-ide"):
        lock_path = Path.home() / ".gemini" / surface_name / "presence" / f"{cid}.lock"
        if not lock_path.is_file():
            continue
        fd: Optional[int] = None
        try:
            fd = os.open(lock_path, os.O_RDONLY)
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            fcntl.flock(fd, fcntl.LOCK_UN)
        except OSError as exc:
            if exc.errno in (errno.EACCES, errno.EAGAIN, errno.EWOULDBLOCK):
                return True
        finally:
            if fd is not None:
                try:
                    os.close(fd)
                except OSError:
                    pass
    return False


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

    # 3. Also scan .agents/artifacts/checkpoints/ for v2.34.0 per-session checkpoints
    cp_dir = art_dir / "checkpoints"
    if cp_dir.is_dir():
        cp_pruned = prune_stale_checkpoints(cp_dir, retention_limit=retention, dry_run=dry_run)
        for p in cp_pruned:
            pruned_files.append(str(p))
        try:
            session_cps: List[Tuple[float, Path]] = []
            for entry in cp_dir.glob("*.md"):
                if (
                    entry.is_file()
                    and not entry.name.startswith("compaction_checkpoint_")
                    and not _is_cid_actively_locked(entry.stem)
                ):
                    session_cps.append((entry.stat().st_mtime, entry))
            session_cps.sort(key=lambda item: item[0], reverse=True)
            for _, entry in session_cps[retention:]:
                pruned_files.append(str(entry))
                if not dry_run:
                    try:
                        entry.unlink(missing_ok=True)
                    except OSError:
                        pass
        except OSError:
            pass

    return pruned_files


def _is_worktree_dirty_or_unmerged(wt_path: Path, workspace_dir: Path, wt_branch: Optional[str]) -> bool:
    """Returns True if worktree has uncommitted changes or commits not merged into HEAD."""
    try:
        st = subprocess.run(
            ["git", "-C", str(wt_path), "status", "--porcelain"],
            capture_output=True,
            text=True,
            timeout=3.0,
            check=False,
        )
        if st.returncode == 0 and st.stdout.strip():
            return True
    except Exception:
        return True

    if wt_branch:
        try:
            unmerged = subprocess.run(
                ["git", "-C", str(workspace_dir), "log", f"HEAD..{wt_branch}", "--oneline", "-n", "1"],
                capture_output=True,
                text=True,
                timeout=3.0,
                check=False,
            )
            if unmerged.returncode == 0 and unmerged.stdout.strip():
                return True
        except Exception:
            return True
    return False


def clean_worktrees(
    workspace_dir: Path,
    dry_run: bool = False,
    force: bool = False,
) -> List[str]:
    """Prunes dead git worktrees and orphaned directories without deleting active/dirty worktrees."""
    pruned_worktrees: List[str] = []

    def _run_git(args: List[str]) -> subprocess.CompletedProcess[str] | None:
        try:
            return subprocess.run(
                ["git"] + args,
                cwd=str(workspace_dir),
                capture_output=True,
                text=True,
                timeout=3.0,
                check=False,
            )
        except Exception:
            return None

    # 1. Prune registered ephemeral worktrees only when safe (or --force)
    wt_res = _run_git(["worktree", "list", "--porcelain"])
    wt_out = wt_res.stdout.strip() if wt_res else ""
    blocks: List[Dict[str, str]] = []
    cur_block: Dict[str, str] = {}
    for line in wt_out.splitlines():
        if not line.strip():
            if cur_block:
                blocks.append(cur_block)
                cur_block = {}
            continue
        if " " in line:
            k, v = line.split(" ", 1)
            cur_block[k] = v.strip()
        else:
            cur_block[line.strip()] = ""
    if cur_block:
        blocks.append(cur_block)

    ephemeral_markers = (
        ".gemini/antigravity/worktrees",
        ".gemini/antigravity-cli/worktrees",
        ".gemini/antigravity-ide/worktrees",
        ".system_generated/worktrees",
        "/subagent-",
    )
    resolved_ws = workspace_dir.resolve()
    for blk in blocks:
        p = blk.get("worktree", "")
        if not p:
            continue
        wt_path = Path(p)
        if wt_path.resolve() == resolved_ws:
            continue
        if not any(marker in p for marker in ephemeral_markers):
            continue
        wt_branch = blk.get("branch", "").replace("refs/heads/", "").strip() or None
        cid_candidates = [wt_path.name, wt_path.parent.name]
        if not force:
            if any(_is_cid_actively_locked(cid) for cid in cid_candidates):
                continue
            if wt_path.is_dir() and _is_worktree_dirty_or_unmerged(wt_path, workspace_dir, wt_branch):
                continue
        pruned_worktrees.append(p)
        if not dry_run:
            rm_args = ["worktree", "remove"]
            if force:
                rm_args.append("--force")
            rm_args.append(p)
            _run_git(rm_args)
            if wt_path.is_dir() and force:
                shutil.rmtree(wt_path, ignore_errors=True)

    prune_args = ["worktree", "prune", "--dry-run", "-v"] if dry_run else ["worktree", "prune", "-v"]
    prune_res = _run_git(prune_args)
    out = prune_res.stdout.strip() if prune_res else ""
    if out:
        for line in out.splitlines():
            if line.strip():
                pruned_worktrees.append(line.strip())

    # 2. Check for truly orphaned directories in Antigravity worktrees & .system_generated/worktrees
    candidate_roots = [
        Path.home() / ".gemini" / "antigravity" / "worktrees",
        Path.home() / ".gemini" / "antigravity-cli" / "worktrees",
        Path.home() / ".gemini" / "antigravity-ide" / "worktrees",
        Path.home() / ".gemini" / "antigravity" / ".system_generated" / "worktrees",
        workspace_dir / ".system_generated" / "worktrees",
    ]
    for wt_root in candidate_roots:
        if not wt_root.is_dir():
            continue
        try:
            for entry in wt_root.iterdir():
                if not entry.is_dir():
                    continue
                candidates: List[Path] = []
                if (entry / ".git").exists() or entry.name.startswith(("subagent-", "worktree-", "swarm-")):
                    candidates.append(entry)
                for sub_wt in entry.glob("subagent-*"):
                    if sub_wt.is_dir():
                        candidates.append(sub_wt)
                for wt_dir in candidates:
                    if not force and (
                        _is_cid_actively_locked(wt_dir.name)
                        or _is_cid_actively_locked(entry.name)
                    ):
                        continue
                    git_link = wt_dir / ".git"
                    is_orphaned = False
                    if not git_link.exists():
                        is_orphaned = True
                    elif git_link.is_file():
                        try:
                            content = git_link.read_text(encoding="utf-8").strip()
                            if content.startswith("gitdir:"):
                                raw_gitdir = content.split(":", 1)[1].strip()
                                raw_path = Path(raw_gitdir)
                                gitdir_path = (
                                    raw_path.resolve()
                                    if raw_path.is_absolute()
                                    else (wt_dir / raw_path).resolve()
                                )
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
        if branch.startswith(("subagent-", "worktree-", "swarm-")) and branch not in active_branches:
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
    do_caches = bool(getattr(args, "caches", False))
    do_all = getattr(args, "all", False)

    # Default to --all if no specific category is selected
    if not (do_checkpoints or do_worktrees or do_branches or do_scratch or do_dist or do_caches or do_all):
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
    force = bool(getattr(args, "force", False))
    json_output = getattr(args, "json", False)

    pruned_cps: List[str] = []
    pruned_wts: List[str] = []
    deleted_brs: List[str] = []
    pruned_scrs: List[str] = []
    pruned_scr_dirs: List[str] = []
    pruned_dist: List[str] = []
    pruned_caches: List[str] = []
    dist_error: Optional[str] = None

    if do_checkpoints:
        pruned_cps = clean_checkpoints(ws, retention=retention, dry_run=dry_run)
    if do_worktrees:
        pruned_wts = clean_worktrees(ws, dry_run=dry_run, force=force)
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
    if do_caches:
        pruned_caches = purge_build_caches(ws, dry_run=dry_run)

    elapsed_ms = round((time.perf_counter() - t0) * 1000.0, 2)
    total_pruned = (
        len(pruned_cps)
        + len(pruned_wts)
        + len(deleted_brs)
        + len(pruned_scrs)
        + len(pruned_scr_dirs)
        + len(pruned_dist)
        + len(pruned_caches)
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
            "caches": {"pruned": pruned_caches, "count": len(pruned_caches)},
            "total_pruned": total_pruned,
            "elapsed_ms": elapsed_ms,
        }
        if dist_error is not None:
            report["error"] = dist_error
        print(json.dumps(report, indent=2))
        return 1 if dist_error is not None else 0

    if dist_error is not None:
        print(theme.badge("FAIL", f"Failed to clean dist/: {dist_error}", stream=sys.stderr), file=sys.stderr)
        return 1

    mode_label = " [DRY-RUN]" if dry_run else ""
    print(theme.banner(f"Agyis Hygiene & Workspace Cleanup{mode_label}"))
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

    if do_caches:
        print(f"Caches:      {len(pruned_caches)} build cache directories purged")
        for c_item in pruned_caches:
            print(f"  - {Path(c_item).name}")

    print(theme.badge("PASS", f"Completed in {elapsed_ms:.2f} ms (Total items cleaned: {total_pruned})"))
    return 0
