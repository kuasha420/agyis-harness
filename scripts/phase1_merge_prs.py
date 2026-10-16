#!/usr/bin/env python3
"""Phase 1: Programmatic Fleet PR Merge via Merge Commits (--merge) & Delete Remote Branches (--delete-branch)."""

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
    print(f"Starting Phase 1: Merging {len(PRS)} Pull Requests...")
    
    for idx, item in enumerate(PRS, 1):
        repo = item["repo"]
        pr_num = item["pr"]
        target_base = item["target_base"]
        print(f"[{idx}/{len(PRS)}] Processing {repo} PR #{pr_num} (target base: {target_base})...")
        
        # Check current PR state
        code, stdout, stderr = run_cmd([
            "gh", "pr", "view", str(pr_num), "--repo", repo,
            "--json", "state,mergeCommit,mergedAt,mergedBy,headRefName,baseRefName"
        ])
        
        if code != 0:
            print(f"  ERROR viewing PR: {stderr}")
            sys.exit(1)
            
        pr_info = json.loads(stdout)
        merge_cmd_stdout = ""
        merge_cmd_stderr = ""
        merge_cmd_code = 0
        
        if pr_info.get("state") != "MERGED":
            print(f"  State is {pr_info.get('state')}. Executing gh pr merge --merge --delete-branch...")
            merge_cmd = [
                "gh", "pr", "merge", str(pr_num),
                "--repo", repo,
                "--merge",
                "--delete-branch"
            ]
            merge_cmd_code, merge_cmd_stdout, merge_cmd_stderr = run_cmd(merge_cmd)
            if merge_cmd_code != 0:
                print(f"  ERROR merging PR: {merge_cmd_stderr}")
                sys.exit(1)
            print(f"  Merge command succeeded: {merge_cmd_stdout}")
            # Give GitHub a moment to settle
            time.sleep(1)
            
            # Query updated state
            code, stdout, stderr = run_cmd([
                "gh", "pr", "view", str(pr_num), "--repo", repo,
                "--json", "state,mergeCommit,mergedAt,mergedBy,headRefName,baseRefName"
            ])
            pr_info = json.loads(stdout)
        else:
            print(f"  Already MERGED. Merge commit: {pr_info.get('mergeCommit', {}).get('oid')}")
            merge_cmd_stdout = "Already merged previously"

        assert pr_info.get("state") == "MERGED", f"PR {repo}#{pr_num} state is {pr_info.get('state')}, expected MERGED"
        merge_commit_sha = pr_info.get("mergeCommit", {}).get("oid", "")
        assert merge_commit_sha, f"PR {repo}#{pr_num} has empty mergeCommit"
        
        # Verify remote branch deleted
        b_code, b_out, b_err = run_cmd([
            "gh", "api", f"repos/{repo}/branches/chore/agyis-harness-onboarding"
        ])
        remote_branch_deleted = (b_code != 0 and "404" in b_out or "Branch not found" in b_out or "404" in b_err or "Branch not found" in b_err)
        print(f"  Verified MERGED commit: {merge_commit_sha}")
        print(f"  Remote branch chore/agyis-harness-onboarding deleted: {remote_branch_deleted}")
        
        record = {
            "index": idx,
            "repo": repo,
            "pr_number": pr_num,
            "target_base": target_base,
            "baseRefName": pr_info.get("baseRefName"),
            "headRefName": pr_info.get("headRefName"),
            "state": pr_info.get("state"),
            "mergedAt": pr_info.get("mergedAt"),
            "mergedBy": pr_info.get("mergedBy", {}).get("login"),
            "mergeCommitSha": merge_commit_sha,
            "merge_command": f"gh pr merge {pr_num} --repo {repo} --merge --delete-branch",
            "merge_exit_code": merge_cmd_code,
            "merge_stdout": merge_cmd_stdout,
            "remote_branch_deleted": remote_branch_deleted
        }
        results.append(record)

    output_path = "/home/kuasha/Dev/psl-agy-harness/scripts/phase1_merge_results.json"
    with open(output_path, "w") as f:
        json.dump(results, f, indent=2)
    print(f"\nPhase 1 successfully completed! All 21 PRs merged and verified. Results saved to {output_path}")

if __name__ == "__main__":
    main()
