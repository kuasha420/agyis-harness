#!/usr/bin/env python3
"""Phase 1: Programmatic Fleet PR Merge via Merge Commits (--merge) & Remote Branch Cleanup."""

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

DEFAULT_SAMPLE_PRS: List[Dict[str, Any]] = [
    {"repo": "example-org/sample-ts-app", "pr": 1, "target_base": "develop"},
    {"repo": "example-org/sample-py-service", "pr": 2, "target_base": "main"},
    {"repo": "example-org/sample-rust-cli", "pr": 3, "target_base": "main"},
]


def load_prs_config(config_path: str | None) -> List[Dict[str, Any]]:
    if not config_path:
        return list(DEFAULT_SAMPLE_PRS)
    raw = json.loads(Path(config_path).read_text(encoding="utf-8"))
    if isinstance(raw, list):
        return raw
    if isinstance(raw, dict):
        if "prs" in raw and isinstance(raw["prs"], list):
            return raw["prs"]
        if "repos" in raw and isinstance(raw["repos"], list):
            return raw["repos"]
    raise ValueError(f"Unsupported fleet config structure in {config_path}")


def run_cmd(cmd: List[str]) -> tuple[int, str, str]:
    res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    return res.returncode, res.stdout.strip(), res.stderr.strip()


def parse_args(argv: List[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Merge fleet onboarding pull requests via gh CLI.")
    parser.add_argument(
        "--repos-config",
        default=os.environ.get("AGYIS_FLEET_CONFIG"),
        help="Path to JSON file containing PR entries [{repo, pr, target_base}, ...].",
    )
    parser.add_argument(
        "--branch",
        default=os.environ.get("AGYIS_ONBOARD_BRANCH", "chore/agyis-harness-onboarding"),
        help="Onboarding branch name expected to be deleted after merge.",
    )
    parser.add_argument(
        "--output",
        default=str(REPO_ROOT / "scripts" / "phase1_merge_results.json"),
        help="Output JSON report path.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Inspect PR status without executing merges.",
    )
    return parser.parse_args(argv)


def main(argv: List[str] | None = None) -> int:
    args = parse_args(argv)
    if not args.repos_config:
        print("Notice: --repos-config not supplied; using sample placeholder PR targets.", file=sys.stderr)
    prs = load_prs_config(args.repos_config)
    results: List[Dict[str, Any]] = []
    print(f"Starting Phase 1: Processing {len(prs)} Pull Requests...")

    for idx, item in enumerate(prs, 1):
        repo = item["repo"]
        pr_num = item.get("pr") or item.get("pr_number")
        target_base = item["target_base"]
        print(f"[{idx}/{len(prs)}] Processing {repo} PR #{pr_num} (target base: {target_base})...")

        code, stdout, stderr = run_cmd([
            "gh", "pr", "view", str(pr_num), "--repo", repo,
            "--json", "state,mergeCommit,mergedAt,mergedBy,headRefName,baseRefName",
        ])

        if code != 0:
            print(f"  ERROR viewing PR: {stderr}", file=sys.stderr)
            return 1

        pr_info = json.loads(stdout)
        merge_cmd_stdout = ""
        merge_cmd_code = 0

        if pr_info.get("state") != "MERGED":
            if args.dry_run:
                print(f"  [DRY-RUN] State is {pr_info.get('state')}; would run gh pr merge {pr_num} --repo {repo} --merge --delete-branch")
                merge_cmd_stdout = "dry-run"
            else:
                print(f"  State is {pr_info.get('state')}. Executing gh pr merge --merge --delete-branch...")
                merge_cmd = [
                    "gh", "pr", "merge", str(pr_num),
                    "--repo", repo,
                    "--merge",
                    "--delete-branch",
                ]
                merge_cmd_code, merge_cmd_stdout, merge_cmd_stderr = run_cmd(merge_cmd)
                if merge_cmd_code != 0:
                    print(f"  ERROR merging PR: {merge_cmd_stderr}", file=sys.stderr)
                    return 1
                print(f"  Merge command succeeded: {merge_cmd_stdout}")
                time.sleep(1)

                code, stdout, stderr = run_cmd([
                    "gh", "pr", "view", str(pr_num), "--repo", repo,
                    "--json", "state,mergeCommit,mergedAt,mergedBy,headRefName,baseRefName",
                ])
                if code != 0:
                    print(f"  ERROR refreshing PR state: {stderr}", file=sys.stderr)
                    return 1
                pr_info = json.loads(stdout)
        else:
            print(f"  Already MERGED. Merge commit: {pr_info.get('mergeCommit', {}).get('oid')}")
            merge_cmd_stdout = "Already merged previously"

        if not args.dry_run and pr_info.get("state") != "MERGED":
            print(f"  ERROR: PR {repo}#{pr_num} state is {pr_info.get('state')}, expected MERGED", file=sys.stderr)
            return 1

        merge_commit_sha = (pr_info.get("mergeCommit") or {}).get("oid", "")
        if not args.dry_run and not merge_commit_sha:
            print(f"  ERROR: PR {repo}#{pr_num} has empty mergeCommit", file=sys.stderr)
            return 1

        b_code, b_out, b_err = run_cmd([
            "gh", "api", f"repos/{repo}/branches/{args.branch}",
        ])
        remote_branch_deleted = (
            b_code != 0 and ("404" in b_out or "Branch not found" in b_out or "404" in b_err or "Branch not found" in b_err)
        )
        print(f"  Verified commit: {merge_commit_sha or 'pending'} | Remote branch '{args.branch}' deleted: {remote_branch_deleted}")

        results.append({
            "index": idx,
            "repo": repo,
            "pr_number": pr_num,
            "target_base": target_base,
            "baseRefName": pr_info.get("baseRefName"),
            "headRefName": pr_info.get("headRefName"),
            "state": pr_info.get("state"),
            "mergedAt": pr_info.get("mergedAt"),
            "mergedBy": (pr_info.get("mergedBy") or {}).get("login"),
            "mergeCommitSha": merge_commit_sha,
            "merge_command": f"gh pr merge {pr_num} --repo {repo} --merge --delete-branch",
            "merge_exit_code": merge_cmd_code,
            "merge_stdout": merge_cmd_stdout,
            "remote_branch_deleted": remote_branch_deleted,
        })

    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(results, indent=2) + "\n", encoding="utf-8")
    print(f"\nPhase 1 completed. Results saved to {output_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
