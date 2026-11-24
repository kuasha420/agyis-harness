#!/usr/bin/env python3
"""Independent Reviewer PR Check: Verify onboarding PRs and branch cleanup on GitHub."""

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
        if isinstance(raw.get("prs"), list):
            return raw["prs"]
        if isinstance(raw.get("repos"), list):
            return raw["repos"]
    raise ValueError(f"Unsupported fleet config structure in {config_path}")


def run_cmd(cmd: List[str]) -> tuple[int, str, str]:
    res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    return res.returncode, res.stdout.strip(), res.stderr.strip()


def parse_args(argv: List[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Audit merged onboarding PRs and branch deletion via GitHub API.")
    parser.add_argument(
        "--repos-config",
        default=os.environ.get("AGYIS_FLEET_CONFIG"),
        help="Path to JSON file containing PR entries [{repo, pr, target_base}, ...].",
    )
    parser.add_argument(
        "--permission-check-repos",
        default="",
        help="Comma-separated owner/repo targets to audit repository permissions for.",
    )
    parser.add_argument(
        "--output",
        default=str(REPO_ROOT / "scripts" / "independent_reviewer_results.json"),
        help="Output JSON report path.",
    )
    return parser.parse_args(argv)


def main(argv: List[str] | None = None) -> int:
    args = parse_args(argv)
    if not args.repos_config:
        print("Notice: --repos-config not supplied; using sample placeholder PR targets.", file=sys.stderr)
    prs = load_prs_config(args.repos_config)
    results: List[Dict[str, Any]] = []
    print(f"Starting independent verification of {len(prs)} Pull Requests...")

    for idx, item in enumerate(prs, 1):
        repo = item["repo"]
        pr_num = item.get("pr") or item.get("pr_number")
        target_base = item["target_base"]
        print(f"[{idx}/{len(prs)}] Auditing {repo} PR #{pr_num}...")

        code, stdout, stderr = run_cmd(["gh", "api", f"repos/{repo}/pulls/{pr_num}"])
        if code != 0:
            print(f"  ERROR fetching PR #{pr_num}: {stderr}", file=sys.stderr)
            results.append({"index": idx, "repo": repo, "pr_number": pr_num, "error": stderr})
            continue

        pr_data = json.loads(stdout)
        state = pr_data.get("state")
        merged = pr_data.get("merged", False)
        merge_commit_sha = pr_data.get("merge_commit_sha")
        merged_at = pr_data.get("merged_at")
        merged_by = (pr_data.get("merged_by") or {}).get("login")
        base_ref = (pr_data.get("base") or {}).get("ref")
        head_ref = (pr_data.get("head") or {}).get("ref")
        head_repo = ((pr_data.get("head") or {}).get("repo") or {}).get("full_name")
        is_cross_repo = head_repo != repo

        parents: List[str] = []
        is_merge_commit = False
        commit_message = ""
        if merged and merge_commit_sha:
            c_code, c_stdout, _ = run_cmd(["gh", "api", f"repos/{repo}/commits/{merge_commit_sha}"])
            if c_code == 0:
                c_data = json.loads(c_stdout)
                parents = [p.get("sha") for p in c_data.get("parents", []) if p.get("sha")]
                is_merge_commit = len(parents) >= 2
                commit_message = c_data.get("commit", {}).get("message", "").split("\n")[0]

        t_code, t_stdout, t_stderr = run_cmd(["gh", "api", f"repos/{repo}/branches/{head_ref}"])
        target_branch_deleted = t_code != 0 and (
            "404" in t_stdout or "Branch not found" in t_stdout or "404" in t_stderr or "Branch not found" in t_stderr
        )

        if is_cross_repo and head_repo:
            h_code, h_stdout, h_stderr = run_cmd(["gh", "api", f"repos/{head_repo}/branches/{head_ref}"])
            head_repo_branch_deleted = h_code != 0 and (
                "404" in h_stdout or "Branch not found" in h_stdout or "404" in h_stderr or "Branch not found" in h_stderr
            )
        else:
            head_repo_branch_deleted = target_branch_deleted

        rec = {
            "index": idx,
            "repo": repo,
            "pr_number": pr_num,
            "target_base": target_base,
            "base_ref": base_ref,
            "head_ref": head_ref,
            "head_repo": head_repo,
            "is_cross_repo": is_cross_repo,
            "state": state,
            "merged": merged,
            "merge_commit_sha": merge_commit_sha,
            "merged_at": merged_at,
            "merged_by": merged_by,
            "parents": parents,
            "num_parents": len(parents),
            "is_merge_commit": is_merge_commit,
            "commit_message": commit_message,
            "target_branch_deleted": target_branch_deleted,
            "head_repo_branch_deleted": head_repo_branch_deleted,
        }
        results.append(rec)
        print(f"  State: {state}, Merged: {merged}, Parents: {len(parents)}, BranchDeleted: {target_branch_deleted}")

    perm_results: Dict[str, Any] = {}
    perm_repos = [r.strip() for r in args.permission_check_repos.split(",") if r.strip()]
    if perm_repos:
        print("\nAuditing repository collaborator permissions...")
        for r in perm_repos:
            p_code, p_out, p_err = run_cmd(["gh", "api", f"repos/{r}"])
            if p_code == 0:
                p_data = json.loads(p_out)
                perm_results[r] = p_data.get("permissions")
                print(f"  {r} permissions: {perm_results[r]}")
            else:
                perm_results[r] = {"error": p_err}

    out_file = Path(args.output)
    out_file.parent.mkdir(parents=True, exist_ok=True)
    full_output = {
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "pull_requests": results,
        "permissions": perm_results,
    }
    out_file.write_text(json.dumps(full_output, indent=2) + "\n", encoding="utf-8")
    print(f"\nVerification complete! Saved results to {out_file}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
