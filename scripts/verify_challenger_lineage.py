#!/usr/bin/env python3
"""
Empirical Challenger Verification Script: Git Lineage, Merge Commits, Remote Branch Deletions & Git Hygiene.
"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import subprocess
import sys
import time
from typing import Any, Dict, List

REPO_ROOT = Path(__file__).resolve().parent.parent

DEFAULT_SAMPLE_REPOS: List[Dict[str, Any]] = [
    {
        "index": 1,
        "name": "sample-ts-app",
        "path": "sample-ts-app",
        "gh_repo": "example-org/sample-ts-app",
        "pr_number": 1,
        "base_branch": "develop",
        "is_merged": True,
        "expected_merge_sha": None,
        "remote_name": "origin",
    },
    {
        "index": 2,
        "name": "sample-py-service",
        "path": "sample-py-service",
        "gh_repo": "example-org/sample-py-service",
        "pr_number": 2,
        "base_branch": "main",
        "is_merged": True,
        "expected_merge_sha": None,
        "remote_name": "origin",
    },
]


def load_repos_config(config_path: str | None) -> List[Dict[str, Any]]:
    if not config_path:
        return list(DEFAULT_SAMPLE_REPOS)
    raw = json.loads(Path(config_path).read_text(encoding="utf-8"))
    if isinstance(raw, list):
        return raw
    if isinstance(raw, dict) and isinstance(raw.get("repos"), list):
        return raw["repos"]
    raise ValueError(f"Unsupported fleet config structure in {config_path}")


def resolve_repo_path(entry: Dict[str, Any], workspace_root: Path) -> Path:
    raw_path = entry.get("path") or entry["name"]
    candidate = Path(raw_path)
    return candidate if candidate.is_absolute() else (workspace_root / candidate)


def run_cmd(cmd: List[str], cwd: Path | None = None, timeout: int = 30) -> tuple[int, str, str]:
    try:
        res = subprocess.run(
            cmd,
            cwd=cwd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=timeout,
            text=True,
        )
        return res.returncode, res.stdout.strip(), res.stderr.strip()
    except subprocess.TimeoutExpired:
        return -1, "", "TIMEOUT"
    except Exception as exc:
        return -2, "", str(exc)


def parse_args(argv: List[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Verify git merge lineage, branch deletion, and repository hygiene.")
    parser.add_argument(
        "--repos-config",
        default=os.environ.get("AGYIS_FLEET_CONFIG"),
        help="Path to JSON fleet repository configuration.",
    )
    parser.add_argument(
        "--workspace-root",
        default=os.environ.get("AGYIS_WORKSPACE_ROOT") or str(REPO_ROOT.parent),
        help="Base directory used to resolve relative repo paths.",
    )
    parser.add_argument(
        "--branch",
        default=os.environ.get("AGYIS_ONBOARD_BRANCH", "chore/agyis-harness-onboarding"),
        help="Onboarding branch name to verify deletion.",
    )
    parser.add_argument(
        "--output",
        default=str(REPO_ROOT / "scripts" / "verify_challenger_lineage_results.json"),
        help="Output JSON report path.",
    )
    return parser.parse_args(argv)


def main(argv: List[str] | None = None) -> int:
    args = parse_args(argv)
    if not args.repos_config:
        print("Notice: --repos-config not supplied; using sample placeholder repositories.", file=sys.stderr)
    repos = load_repos_config(args.repos_config)
    workspace_root = Path(args.workspace_root).resolve()

    print("=" * 80)
    print("EMPIRICAL CHALLENGER VERIFICATION HARNESS")
    print("=" * 80)

    results: Dict[str, Any] = {
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "merge_commits": [],
        "remote_branches": [],
        "repo_hygiene": [],
        "failures": [],
    }

    seen_paths: set[str] = set()
    distinct_repos: List[Dict[str, Any]] = []
    for item in repos:
        r_path = str(resolve_repo_path(item, workspace_root))
        if r_path not in seen_paths:
            seen_paths.add(r_path)
            distinct_repos.append({**item, "_resolved_path": Path(r_path)})

    print(f"\nPhase 1: Merge Commit & Lineage Verification ({len(repos)} PR items)...")
    for idx, r in enumerate(repos, 1):
        name = r["name"]
        repo_path = resolve_repo_path(r, workspace_root)
        is_merged = bool(r.get("is_merged", True))
        expected_sha = r.get("expected_merge_sha")
        print(f"\n[{idx}/{len(repos)}] Checking {name} in {repo_path}...")

        if not is_merged:
            rc, out, _ = run_cmd(["gh", "pr", "view", str(r["pr_number"]), "--repo", r["gh_repo"], "--json", "state,mergeCommit"])
            pr_info = json.loads(out) if rc == 0 else {}
            results["merge_commits"].append({
                "item": name,
                "gh_repo": r["gh_repo"],
                "pr_number": r["pr_number"],
                "is_merged": False,
                "gh_state": pr_info.get("state"),
                "status": "PASS_UNMERGED_AS_DOCUMENTED",
            })
            continue

        if not expected_sha:
            rc, out, err = run_cmd(["git", "rev-parse", "HEAD"], cwd=repo_path)
            if rc != 0:
                results["failures"].append(f"{name}: failed resolving HEAD ({err})")
                continue
            expected_sha = out

        rc, _, _ = run_cmd(["git", "rev-parse", "--verify", expected_sha], cwd=repo_path)
        if rc != 0:
            results["failures"].append(f"{name}: SHA {expected_sha} not in git history")
            continue

        rc, out, _ = run_cmd(["git", "rev-list", "--parents", "-n", "1", expected_sha], cwd=repo_path)
        parts = out.split()
        commit_sha = parts[0] if parts else ""
        parents = parts[1:] if len(parts) > 1 else []
        parent_count = len(parents)
        is_true_merge = parent_count >= 2
        if not is_true_merge:
            results["failures"].append(f"{name}: commit {expected_sha} has {parent_count} parents (<2)")

        _, graph_out, _ = run_cmd(["git", "log", "--graph", "--oneline", "-n", "5", expected_sha], cwd=repo_path)
        branch_commits: List[str] = []
        if parents:
            _, branch_commits_out, _ = run_cmd(["git", "log", f"{parents[0]}..{expected_sha}", "--oneline"], cwd=repo_path)
            branch_commits = [c for c in branch_commits_out.splitlines() if c.strip()]

        has_onboarding_commits = len(branch_commits) >= 1
        if not has_onboarding_commits:
            results["failures"].append(f"{name}: zero branch commits found in merge lineage")

        results["merge_commits"].append({
            "item": name,
            "path": str(repo_path),
            "gh_repo": r["gh_repo"],
            "pr_number": r["pr_number"],
            "expected_sha": expected_sha,
            "actual_sha": commit_sha,
            "parent_count": parent_count,
            "parents": parents,
            "is_standard_merge": is_true_merge,
            "graph_preview": graph_out,
            "branch_commits": branch_commits,
            "status": "PASS" if is_true_merge and has_onboarding_commits else "FAIL",
        })

    print(f"\nPhase 2: Remote Branch Deletion Verification ({len(repos)} PR items)...")
    for idx, r in enumerate(repos, 1):
        name = r["name"]
        gh_repo = r["gh_repo"]
        repo_path = resolve_repo_path(r, workspace_root)
        remote_name = r.get("remote_name", "origin")
        branch_name = args.branch
        print(f"\n[{idx}/{len(repos)}] Checking remote branch for {gh_repo}...")

        rc_api, _, err_api = run_cmd(["gh", "api", f"repos/{gh_repo}/branches/{branch_name}"])
        api_deleted = rc_api != 0 and ("Branch not found" in err_api or "404" in err_api or "Not Found" in err_api)

        rc_ls, out_ls, _ = run_cmd(["git", "ls-remote", remote_name, branch_name], cwd=repo_path)
        ls_remote_deleted = rc_ls == 0 and out_ls.strip() == ""

        if not r.get("is_merged", True):
            results["remote_branches"].append({
                "item": name,
                "gh_repo": gh_repo,
                "branch": branch_name,
                "api_deleted": api_deleted,
                "ls_remote_deleted": ls_remote_deleted,
                "status": "PASS_UNMERGED_AS_DOCUMENTED",
            })
            continue

        if not api_deleted or not ls_remote_deleted:
            results["failures"].append(f"{gh_repo}: remote branch {branch_name} not deleted")

        results["remote_branches"].append({
            "item": name,
            "gh_repo": gh_repo,
            "branch": branch_name,
            "api_deleted": api_deleted,
            "ls_remote_deleted": ls_remote_deleted,
            "status": "PASS" if api_deleted and ls_remote_deleted else "FAIL",
        })

    print(f"\nPhase 3: Repository Hygiene, Locks, Rebases & Detached HEAD ({len(distinct_repos)} local checkouts)...")
    for idx, r in enumerate(distinct_repos, 1):
        name = r["name"]
        repo_path = r["_resolved_path"]
        expected_base = r["base_branch"]
        print(f"\n[{idx}/{len(distinct_repos)}] Inspecting {repo_path}...")

        lock_files: List[str] = []
        git_dir = repo_path / ".git"
        if git_dir.is_dir():
            for root, _, files in os.walk(git_dir):
                for fname in files:
                    if fname.endswith(".lock"):
                        lock_files.append(str(Path(root) / fname))
        has_locks = len(lock_files) > 0
        if has_locks:
            results["failures"].append(f"{name}: lock files found {lock_files}")

        pending_states: List[str] = []
        for state_name in ("rebase-apply", "rebase-merge", "MERGE_HEAD", "CHERRY_PICK_HEAD", "REVERT_HEAD", "BISECT_LOG"):
            if (git_dir / state_name).exists():
                pending_states.append(state_name)
        has_pending = len(pending_states) > 0
        if has_pending:
            results["failures"].append(f"{name}: pending states {pending_states}")

        rc_sym, _, _ = run_cmd(["git", "symbolic-ref", "-q", "HEAD"], cwd=repo_path)
        is_detached = rc_sym != 0
        _, current_branch, _ = run_cmd(["git", "branch", "--show-current"], cwd=repo_path)
        if is_detached or not current_branch:
            results["failures"].append(f"{name}: detached HEAD state")
        elif current_branch != expected_base:
            results["failures"].append(f"{name}: branch is '{current_branch}', expected '{expected_base}'")

        _, out_b, _ = run_cmd(["git", "branch", "--list", args.branch], cwd=repo_path)
        local_branch_exists = bool(out_b.strip())
        if local_branch_exists:
            results["failures"].append(f"{name}: local branch {args.branch} exists")

        _, porcelain, _ = run_cmd(["git", "status", "--porcelain"], cwd=repo_path)
        wip_expected = bool(r.get("wip_expected", False))
        if not wip_expected and porcelain.strip():
            results["failures"].append(f"{name}: working tree dirty: {porcelain}")

        passed = (
            not has_locks
            and not has_pending
            and not is_detached
            and current_branch == expected_base
            and not local_branch_exists
            and (wip_expected or not porcelain.strip())
        )
        results["repo_hygiene"].append({
            "name": name,
            "path": str(repo_path),
            "active_branch": current_branch,
            "expected_base": expected_base,
            "is_detached": is_detached,
            "lock_files": lock_files,
            "pending_states": pending_states,
            "local_feature_branch_exists": local_branch_exists,
            "porcelain_status": porcelain,
            "status": "PASS" if passed else "FAIL",
        })

    print("\n" + "=" * 80)
    print(f"Total Failures: {len(results['failures'])}")
    for failure in results["failures"]:
        print(f" - {failure}")

    out_path = Path(args.output)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(results, indent=2) + "\n", encoding="utf-8")
    print(f"\nResults written to {out_path}")
    return 0 if not results["failures"] else 1


if __name__ == "__main__":
    sys.exit(main())
