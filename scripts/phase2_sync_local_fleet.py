#!/usr/bin/env python3
"""Phase 2 & 3: Local Fleet Synchronization & Working Tree Verification."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import subprocess
import sys
from typing import Any, Dict, List

REPO_ROOT = Path(__file__).resolve().parent.parent

DEFAULT_SAMPLE_REPOS: List[Dict[str, Any]] = [
    {"name": "sample-ts-app", "path": "sample-ts-app", "base": "develop", "expected_merge_sha": None, "wip": False},
    {"name": "sample-py-service", "path": "sample-py-service", "base": "main", "expected_merge_sha": None, "wip": False},
    {"name": "sample-rust-cli", "path": "sample-rust-cli", "base": "main", "expected_merge_sha": None, "wip": False},
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


def run_cmd(cmd: List[str], cwd: Path | None = None) -> tuple[int, str, str]:
    res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, cwd=cwd)
    return res.returncode, res.stdout.strip(), res.stderr.strip()


def parse_args(argv: List[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Synchronize local fleet repositories to their base branches.")
    parser.add_argument(
        "--repos-config",
        default=os.environ.get("AGYIS_FLEET_CONFIG"),
        help="Path to JSON file containing repo entries [{name, path, base, expected_merge_sha, wip}, ...].",
    )
    parser.add_argument(
        "--workspace-root",
        default=os.environ.get("AGYIS_WORKSPACE_ROOT") or str(REPO_ROOT.parent),
        help="Base directory used to resolve relative repo paths.",
    )
    parser.add_argument(
        "--branch",
        default=os.environ.get("AGYIS_ONBOARD_BRANCH", "chore/agyis-harness-onboarding"),
        help="Local onboarding branch name to prune after merge.",
    )
    parser.add_argument(
        "--output",
        default=str(REPO_ROOT / "scripts" / "phase2_sync_results.json"),
        help="Output JSON report path.",
    )
    parser.add_argument("--dry-run", action="store_true", help="Inspect branch/status without mutating local git state.")
    return parser.parse_args(argv)


def main(argv: List[str] | None = None) -> int:
    args = parse_args(argv)
    if not args.repos_config:
        print("Notice: --repos-config not supplied; using sample placeholder repositories.", file=sys.stderr)
    repos = load_repos_config(args.repos_config)
    workspace_root = Path(args.workspace_root).resolve()
    results: List[Dict[str, Any]] = []
    print(f"Executing Phase 2: Local Fleet Synchronization across {len(repos)} repositories (root: {workspace_root})...")

    for idx, repo in enumerate(repos, 1):
        name = repo["name"]
        repo_path = resolve_repo_path(repo, workspace_root)
        base = repo["base"]
        expected_sha = repo.get("expected_merge_sha")
        has_wip = bool(repo.get("wip", False))

        print(f"[{idx}/{len(repos)}] Syncing {name} ({repo_path}) to base '{base}'...")
        if not repo_path.is_dir():
            print(f"  ERROR: repository path does not exist: {repo_path}", file=sys.stderr)
            return 1

        if not args.dry_run:
            c_code, _, c_err = run_cmd(["git", "-C", str(repo_path), "checkout", base])
            if c_code != 0:
                print(f"  ERROR checking out {base}: {c_err}", file=sys.stderr)
                return 1

            p_code, p_out, p_err = run_cmd(["git", "-C", str(repo_path), "pull", "--ff-only", "origin", base])
            if p_code != 0:
                print(f"  ERROR pulling {base}: {p_err}", file=sys.stderr)
                return 1
        else:
            p_out = "dry-run"

        _, current_head, _ = run_cmd(["git", "-C", str(repo_path), "rev-parse", "HEAD"])
        print(f"  Current HEAD: {current_head}")
        if expected_sha and current_head != expected_sha:
            print(f"  ERROR: {name} HEAD {current_head} != expected {expected_sha}", file=sys.stderr)
            return 1

        if not args.dry_run:
            b_code, _, _ = run_cmd(["git", "-C", str(repo_path), "branch", "-D", args.branch])
            branch_deleted = b_code == 0
        else:
            branch_deleted = False

        _, active_branch, _ = run_cmd(["git", "-C", str(repo_path), "branch", "--show-current"])
        if not args.dry_run and active_branch != base:
            print(f"  ERROR: {name} active branch is {active_branch}, expected {base}", file=sys.stderr)
            return 1

        _, status_out, _ = run_cmd(["git", "-C", str(repo_path), "status", "--porcelain"])
        if has_wip:
            if not status_out:
                print(f"  ERROR: {name} expected WIP files in working tree, but status is empty", file=sys.stderr)
                return 1
            tree_clean = False
        else:
            if status_out:
                print(f"  ERROR: {name} expected clean working tree, got:\n{status_out}", file=sys.stderr)
                return 1
            tree_clean = True

        results.append({
            "index": idx,
            "name": name,
            "path": str(repo_path),
            "base_branch": base,
            "active_branch": active_branch,
            "current_head": current_head,
            "expected_merge_sha": expected_sha,
            "head_matches_merge": (current_head == expected_sha) if expected_sha else None,
            "pull_output": p_out,
            "local_feature_branch_deleted": branch_deleted,
            "working_tree_clean": tree_clean,
            "porcelain_status": status_out,
            "wip_restored": has_wip,
        })

    out_file = Path(args.output)
    out_file.parent.mkdir(parents=True, exist_ok=True)
    out_file.write_text(json.dumps(results, indent=2) + "\n", encoding="utf-8")
    print(f"\nPhase 2 & 3 completed! Results written to {out_file}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
