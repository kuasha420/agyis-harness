#!/usr/bin/env python3
"""Independent Reviewer PR Check: Verify 21 PRs on GitHub."""

import json
import subprocess
import sys
import time

PRS = [
    {"repo": "purrfectsoft/chakra-ui-icons-compat", "pr": 1, "target_base": "develop"},
    {"repo": "purrfectsoft/bookcover-craft-api", "pr": 6, "target_base": "dev"},
    {"repo": "purrfectsoft/bookcover-craft", "pr": 4, "target_base": "staging"},
    {"repo": "purrfectsoft/arbiter", "pr": 1, "target_base": "develop"},
    {"repo": "purrfectsoft/jasper-hosted", "pr": 42, "target_base": "main"},
    {"repo": "purrfectsoft/chronicle-time-keeper", "pr": 16, "target_base": "develop"},
    {"repo": "purrfectsoft/sunshine-physio-webapp", "pr": 52, "target_base": "main"},
    {"repo": "purrfectsoft/purrmission", "pr": 4, "target_base": "master"},
    {"repo": "purrfectsoft/mm-website", "pr": 411, "target_base": "develop"},
    {"repo": "purrfectsoft/psl-website", "pr": 74, "target_base": "develop"},
    {"repo": "purrfectsoft/psl-scaffold", "pr": 11, "target_base": "develop"},
    {"repo": "purrfectsoft/psl-boilerplate", "pr": 1, "target_base": "develop"},
    {"repo": "purrfectsoft/purrfectcore-client", "pr": 543, "target_base": "develop"},
    {"repo": "purrfectsoft/purrfectcore-001", "pr": 611, "target_base": "develop"},
    {"repo": "kuasha420/jimha", "pr": 1, "target_base": "main"},
    {"repo": "kuasha420/knot-mesh", "pr": 80, "target_base": "main"},
    {"repo": "kuasha420/purr", "pr": 14, "target_base": "main"},
    {"repo": "kuasha420/react-native-template-ts-plus", "pr": 19, "target_base": "feat/resurrection"},
    {"repo": "kuasha420/purrmission", "pr": 161, "target_base": "master"},
    {"repo": "sakibtamim/purrfect-download-manager", "pr": 23, "target_base": "develop"},
    {"repo": "sakibtamim/Jasper", "pr": 172, "target_base": "master"},
]

def run_cmd(cmd):
    res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    return res.returncode, res.stdout.strip(), res.stderr.strip()

def main():
    results = []
    print(f"Starting independent verification of {len(PRS)} Pull Requests...")

    for idx, item in enumerate(PRS, 1):
        repo = item["repo"]
        pr_num = item["pr"]
        target_base = item["target_base"]
        print(f"[{idx}/{len(PRS)}] Auditing {repo} PR #{pr_num}...")

        # 1. Inspect PR via gh api
        code, stdout, stderr = run_cmd([
            "gh", "api", f"repos/{repo}/pulls/{pr_num}"
        ])
        if code != 0:
            print(f"  ERROR fetching PR #{pr_num}: {stderr}")
            results.append({
                "index": idx,
                "repo": repo,
                "pr_number": pr_num,
                "error": stderr
            })
            continue

        pr_data = json.loads(stdout)
        state = pr_data.get("state")
        merged = pr_data.get("merged", False)
        merge_commit_sha = pr_data.get("merge_commit_sha")
        merged_at = pr_data.get("merged_at")
        merged_by = pr_data.get("merged_by", {}).get("login") if pr_data.get("merged_by") else None
        base_ref = pr_data.get("base", {}).get("ref")
        head_ref = pr_data.get("head", {}).get("ref")
        head_repo = pr_data.get("head", {}).get("repo", {}).get("full_name")
        is_cross_repo = (head_repo != repo)

        # 2. Inspect merge commit lineage if merged
        parents = []
        is_merge_commit = False
        commit_message = ""
        if merged and merge_commit_sha:
            c_code, c_stdout, c_stderr = run_cmd([
                "gh", "api", f"repos/{repo}/commits/{merge_commit_sha}"
            ])
            if c_code == 0:
                c_data = json.loads(c_stdout)
                parents = [p.get("sha") for p in c_data.get("parents", [])]
                is_merge_commit = len(parents) >= 2
                commit_message = c_data.get("commit", {}).get("message", "").split("\n")[0]

        # 3. Inspect branch deletion on target repo
        t_code, t_stdout, t_stderr = run_cmd([
            "gh", "api", f"repos/{repo}/branches/{head_ref}"
        ])
        target_branch_deleted = (t_code != 0 and ("404" in t_stdout or "Branch not found" in t_stdout or "404" in t_stderr or "Branch not found" in t_stderr))

        # 4. Inspect branch deletion on head repo (if cross-repo fork)
        head_repo_branch_deleted = None
        if is_cross_repo and head_repo:
            h_code, h_stdout, h_stderr = run_cmd([
                "gh", "api", f"repos/{head_repo}/branches/{head_ref}"
            ])
            head_repo_branch_deleted = (h_code != 0 and ("404" in h_stdout or "Branch not found" in h_stdout or "404" in h_stderr or "Branch not found" in h_stderr))
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
        print(f"  State: {state}, Merged: {merged}, Parents: {len(parents)}, BranchDeleted(Target): {target_branch_deleted}, BranchDeleted(Head): {head_repo_branch_deleted}")

    # Inspect permissions on sakibtamim repos
    print("\nAuditing permissions on sakibtamim repositories...")
    perm_results = {}
    for r in ["sakibtamim/purrfect-download-manager", "sakibtamim/Jasper"]:
        p_code, p_out, p_err = run_cmd(["gh", "api", f"repos/{r}"])
        if p_code == 0:
            p_data = json.loads(p_out)
            perm_results[r] = p_data.get("permissions")
            print(f"  {r} permissions: {p_data.get('permissions')}")

    out_file = "/home/kuasha/Dev/psl-agy-harness/scripts/independent_reviewer_results.json"
    full_output = {
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "pull_requests": results,
        "permissions": perm_results
    }
    with open(out_file, "w") as f:
        json.dump(full_output, f, indent=2)
    print(f"\nVerification complete! Saved results to {out_file}")

if __name__ == "__main__":
    main()
