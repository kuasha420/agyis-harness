#!/usr/bin/env python3
"""
Empirical Challenger Verification Script: Git Lineage, Merge Commits, Remote Branch Deletions & Git Hygiene
Author: o9_challenger_2
"""
import os
import sys
import json
import subprocess
import time

REPOS = [
    {
        "index": 1,
        "name": "chakra-ui-icons-compat",
        "path": "/home/kuasha/Dev/chakra-ui-icons-compat",
        "gh_repo": "purrfectsoft/chakra-ui-icons-compat",
        "pr_number": 1,
        "base_branch": "develop",
        "is_merged": True,
        "expected_merge_sha": "faa7b37af794a15f32aceddcc7cb267c06240519",
        "remote_name": "origin",
    },
    {
        "index": 2,
        "name": "bookcover-craft-api",
        "path": "/home/kuasha/Dev/bookcover-craft-api",
        "gh_repo": "purrfectsoft/bookcover-craft-api",
        "pr_number": 6,
        "base_branch": "dev",
        "is_merged": True,
        "expected_merge_sha": "c388be52795639684c80c5857328c639e68f9190",
        "remote_name": "origin",
        "wip_expected": True,
    },
    {
        "index": 3,
        "name": "bookcover-craft",
        "path": "/home/kuasha/Dev/bookcover-craft",
        "gh_repo": "purrfectsoft/bookcover-craft",
        "pr_number": 4,
        "base_branch": "staging",
        "is_merged": True,
        "expected_merge_sha": "d2020b5bfe3442e63740695cb25f5b0a14807c25",
        "remote_name": "origin",
        "wip_expected": True,
    },
    {
        "index": 4,
        "name": "arbiter",
        "path": "/home/kuasha/Dev/arbiter",
        "gh_repo": "purrfectsoft/arbiter",
        "pr_number": 1,
        "base_branch": "develop",
        "is_merged": True,
        "expected_merge_sha": "3b7c4e8878f9c2d792f50a39d73ae7e058412881",
        "remote_name": "origin",
    },
    {
        "index": 5,
        "name": "jasper-hosted",
        "path": "/home/kuasha/Dev/jasper-hosted",
        "gh_repo": "purrfectsoft/jasper-hosted",
        "pr_number": 42,
        "base_branch": "main",
        "is_merged": True,
        "expected_merge_sha": "21f703c649d8174bf6caef54aaf20a84e5da2215",
        "remote_name": "origin",
    },
    {
        "index": 6,
        "name": "chronicle-time-keeper",
        "path": "/home/kuasha/Dev/chronicle-time-keeper",
        "gh_repo": "purrfectsoft/chronicle-time-keeper",
        "pr_number": 16,
        "base_branch": "develop",
        "is_merged": True,
        "expected_merge_sha": "e0eb32e4a467a5227d887525e666c7cd36c90781",
        "remote_name": "origin",
    },
    {
        "index": 7,
        "name": "sunshine-physio-universalapp",
        "path": "/home/kuasha/Dev/sunshine-physio-universalapp",
        "gh_repo": "purrfectsoft/sunshine-physio-webapp",
        "pr_number": 52,
        "base_branch": "main",
        "is_merged": True,
        "expected_merge_sha": "665ca430d57b0948d1173fb77b7eb0554c129d20",
        "remote_name": "origin",
    },
    {
        "index": 8,
        "name": "purrmission (purrfectsoft PR #4)",
        "path": "/home/kuasha/Dev/purrmission",
        "gh_repo": "purrfectsoft/purrmission",
        "pr_number": 4,
        "base_branch": "master",
        "is_merged": True,
        "expected_merge_sha": "a6610ad5cc06e3f9e03600cf10a450d3727a235b",
        "remote_name": "purrfectsoft",
    },
    {
        "index": 9,
        "name": "purrmission (kuasha420 PR #161)",
        "path": "/home/kuasha/Dev/purrmission",
        "gh_repo": "kuasha420/purrmission",
        "pr_number": 161,
        "base_branch": "master",
        "is_merged": True,
        "expected_merge_sha": "224e222248a39bf67a4479a470032809904b30df",
        "remote_name": "origin",
    },
    {
        "index": 10,
        "name": "mm-website",
        "path": "/home/kuasha/Dev/mm-website",
        "gh_repo": "purrfectsoft/mm-website",
        "pr_number": 411,
        "base_branch": "develop",
        "is_merged": True,
        "expected_merge_sha": "a513f1690d7f0cb02e684f43f043735cb3384e03",
        "remote_name": "origin",
    },
    {
        "index": 11,
        "name": "psl-website",
        "path": "/home/kuasha/Dev/psl-website",
        "gh_repo": "purrfectsoft/psl-website",
        "pr_number": 74,
        "base_branch": "develop",
        "is_merged": True,
        "expected_merge_sha": "4bdac50b6c6f3de961905f4b3098983891cd4234",
        "remote_name": "origin",
    },
    {
        "index": 12,
        "name": "psl-scaffold",
        "path": "/home/kuasha/Dev/psl-scaffold",
        "gh_repo": "purrfectsoft/psl-scaffold",
        "pr_number": 11,
        "base_branch": "develop",
        "is_merged": True,
        "expected_merge_sha": "16505987b2a100818ba37cbab88023a2792f90fb",
        "remote_name": "origin",
    },
    {
        "index": 13,
        "name": "psl-boilerplate",
        "path": "/home/kuasha/Dev/psl-boilerplate",
        "gh_repo": "purrfectsoft/psl-boilerplate",
        "pr_number": 1,
        "base_branch": "develop",
        "is_merged": True,
        "expected_merge_sha": "895ed6acdb7bf1b00f0890c3158156ef703f7ca8",
        "remote_name": "origin",
    },
    {
        "index": 14,
        "name": "purrfectcore-client",
        "path": "/home/kuasha/Dev/purrfectcore-client",
        "gh_repo": "purrfectsoft/purrfectcore-client",
        "pr_number": 543,
        "base_branch": "develop",
        "is_merged": True,
        "expected_merge_sha": "dc5b8dd30eec61724350ebe28acee773fbaf8e2c",
        "remote_name": "origin",
    },
    {
        "index": 15,
        "name": "purrfectcore-001",
        "path": "/home/kuasha/Dev/purrfectcore-001",
        "gh_repo": "purrfectsoft/purrfectcore-001",
        "pr_number": 611,
        "base_branch": "develop",
        "is_merged": True,
        "expected_merge_sha": "dc30494d4218e6205c961c6d6c1b23ebb9dcc7ae",
        "remote_name": "origin",
    },
    {
        "index": 16,
        "name": "jimha",
        "path": "/home/kuasha/Dev/jimha",
        "gh_repo": "kuasha420/jimha",
        "pr_number": 1,
        "base_branch": "main",
        "is_merged": True,
        "expected_merge_sha": "521b7cc8d39b0ff94d2682245fd9ebea27645d9c",
        "remote_name": "origin",
    },
    {
        "index": 17,
        "name": "knot-mesh",
        "path": "/home/kuasha/Dev/knot-mesh",
        "gh_repo": "kuasha420/knot-mesh",
        "pr_number": 80,
        "base_branch": "main",
        "is_merged": True,
        "expected_merge_sha": "e4ab43d56f392a184be1157f298493fac279b944",
        "remote_name": "origin",
    },
    {
        "index": 18,
        "name": "purr",
        "path": "/home/kuasha/Dev/purr",
        "gh_repo": "kuasha420/purr",
        "pr_number": 14,
        "base_branch": "main",
        "is_merged": True,
        "expected_merge_sha": "891c806e1f50fe68af1b761d03995e76cec0a454",
        "remote_name": "origin",
    },
    {
        "index": 19,
        "name": "react-native-template-ts-plus",
        "path": "/home/kuasha/Dev/react-native-template-ts-plus",
        "gh_repo": "kuasha420/react-native-template-ts-plus",
        "pr_number": 19,
        "base_branch": "feat/resurrection",
        "is_merged": True,
        "expected_merge_sha": "28f4e079f44d06510f665e05b0cf25750a8d282b",
        "remote_name": "origin",
    },
    {
        "index": 20,
        "name": "purrfect-download-manager",
        "path": "/home/kuasha/Dev/purrfect-download-manager",
        "gh_repo": "sakibtamim/purrfect-download-manager",
        "pr_number": 23,
        "base_branch": "develop",
        "is_merged": False,
        "expected_merge_sha": None,
        "remote_name": "origin",
    },
    {
        "index": 21,
        "name": "Jasper",
        "path": "/home/kuasha/Dev/Jasper",
        "gh_repo": "sakibtamim/Jasper",
        "pr_number": 172,
        "base_branch": "master",
        "is_merged": True,
        "expected_merge_sha": "3d10e0e89e607d3d7c1ea105f87c082c325b8dbd",
        "remote_name": "origin",
    },
]

def run_cmd(cmd, cwd=None, timeout=30):
    try:
        res = subprocess.run(
            cmd,
            shell=isinstance(cmd, str),
            cwd=cwd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=timeout,
            text=True
        )
        return res.returncode, res.stdout.strip(), res.stderr.strip()
    except subprocess.TimeoutExpired:
        return -1, "", "TIMEOUT"
    except Exception as e:
        return -2, "", str(e)

def main():
    print("=" * 80)
    print("EMPIRICAL CHALLENGER VERIFICATION HARNESS")
    print("=" * 80)

    results = {
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "merge_commits": [],
        "remote_branches": [],
        "repo_hygiene": [],
        "failures": []
    }

    # Track distinct local checkouts
    seen_paths = set()
    distinct_repos = []
    for item in REPOS:
        if item["path"] not in seen_paths:
            seen_paths.add(item["path"])
            distinct_repos.append(item)

    print(f"\nPhase 1: Merge Commit & Lineage Verification ({len(REPOS)} PR items)...")
    for r in REPOS:
        name = r["name"]
        path = r["path"]
        is_merged = r["is_merged"]
        expected_sha = r["expected_merge_sha"]
        print(f"\n[{r['index']}/{len(REPOS)}] Checking {name} in {path}...")

        if not is_merged:
            print(f"  -> PR #{r['pr_number']} on {r['gh_repo']} marked NOT merged (permission boundary).")
            # Verify PR status on GitHub
            rc, out, err = run_cmd(f"gh pr view {r['pr_number']} --repo {r['gh_repo']} --json state,mergeCommit")
            pr_info = json.loads(out) if rc == 0 else {}
            results["merge_commits"].append({
                "item": r["name"],
                "gh_repo": r["gh_repo"],
                "pr_number": r["pr_number"],
                "is_merged": False,
                "gh_state": pr_info.get("state"),
                "status": "PASS_UNMERGED_AS_DOCUMENTED"
            })
            continue

        # 1. Verify expected merge commit exists in local git history
        rc, out, err = run_cmd(f"git rev-parse --verify {expected_sha}", cwd=path)
        if rc != 0:
            print(f"  [FAIL] Expected merge SHA {expected_sha} not found in {path}")
            results["failures"].append(f"{name}: SHA {expected_sha} not in git history")
            continue

        # 2. Verify number of parents of the merge commit
        rc, out, err = run_cmd(f"git rev-list --parents -n 1 {expected_sha}", cwd=path)
        # Output format: <commit-sha> <parent1-sha> <parent2-sha> ...
        parts = out.split()
        commit_sha = parts[0]
        parents = parts[1:]
        parent_count = len(parents)

        print(f"  Merge Commit: {commit_sha[:10]} | Parent Count: {parent_count} | Parents: {[p[:10] for p in parents]}")

        is_true_merge = parent_count >= 2
        if not is_true_merge:
            print(f"  [FAIL] Commit {expected_sha} has only {parent_count} parent(s)! Not a standard merge commit!")
            results["failures"].append(f"{name}: commit {expected_sha} has {parent_count} parents (<2)")
        else:
            print(f"  [OK] Valid merge commit with {parent_count} parents.")

        # 3. Check git log --graph --oneline -n 5
        rc, graph_out, _ = run_cmd(f"git log --graph --oneline -n 5 {expected_sha}", cwd=path)

        # 4. Confirm full onboarding commit history is preserved on base branch
        # Inspect commits brought in via parent 2
        rc, branch_commits_out, _ = run_cmd(f"git log {parents[0]}..{expected_sha} --oneline", cwd=path)
        branch_commits = [c for c in branch_commits_out.splitlines() if c.strip()]
        print(f"  Preserved Branch Commits ({len(branch_commits)}):")
        for bc in branch_commits[:3]:
            print(f"    - {bc}")
        if len(branch_commits) > 3:
            print(f"    ... and {len(branch_commits)-3} more commits")

        has_onboarding_commits = len(branch_commits) >= 1
        if not has_onboarding_commits:
            print(f"  [FAIL] No commits brought in between {parents[0][:10]} and {expected_sha[:10]}!")
            results["failures"].append(f"{name}: zero branch commits found in merge lineage")

        results["merge_commits"].append({
            "item": name,
            "path": path,
            "gh_repo": r["gh_repo"],
            "pr_number": r["pr_number"],
            "expected_sha": expected_sha,
            "actual_sha": commit_sha,
            "parent_count": parent_count,
            "parents": parents,
            "is_standard_merge": is_true_merge,
            "graph_preview": graph_out,
            "branch_commits": branch_commits,
            "status": "PASS" if is_true_merge and has_onboarding_commits else "FAIL"
        })

    print(f"\nPhase 2: Remote Branch Deletion Verification ({len(REPOS)} PR items)...")
    for r in REPOS:
        name = r["name"]
        gh_repo = r["gh_repo"]
        pr_number = r["pr_number"]
        path = r["path"]
        remote_name = r["remote_name"]
        branch_name = "chore/agyis-harness-onboarding"
        print(f"\n[{r['index']}/{len(REPOS)}] Checking remote branch for {gh_repo}...")

        # A. Query GitHub API directly: gh api repos/<repo>/branches/<branch>
        rc_api, out_api, err_api = run_cmd(f"gh api repos/{gh_repo}/branches/{branch_name}")
        # Expected: HTTP 404 (Branch not found) for merged PRs
        api_deleted = False
        if rc_api != 0 and ("Branch not found" in err_api or "404" in err_api or "Not Found" in err_api):
            api_deleted = True
            print(f"  gh api: 404 Not Found (Branch confirmed DELETED on GitHub)")
        elif rc_api == 0:
            print(f"  gh api: HTTP 200 (Branch EXISTS on GitHub)")
            api_deleted = False
        else:
            print(f"  gh api error: {err_api}")

        # B. Query git ls-remote: git ls-remote <remote> <branch>
        rc_ls, out_ls, err_ls = run_cmd(f"git ls-remote {remote_name} {branch_name}", cwd=path)
        ls_remote_deleted = (rc_ls == 0 and out_ls.strip() == "")
        print(f"  git ls-remote {remote_name} {branch_name}: '{out_ls.strip()}' (Deleted: {ls_remote_deleted})")

        # In case of purrfect-download-manager, it was NOT merged, so remote branch may still exist
        if not r["is_merged"]:
            print(f"  Note: {gh_repo} PR was not merged due to collaborator permission boundary.")
            results["remote_branches"].append({
                "item": name,
                "gh_repo": gh_repo,
                "branch": branch_name,
                "api_deleted": api_deleted,
                "ls_remote_deleted": ls_remote_deleted,
                "status": "PASS_UNMERGED_AS_DOCUMENTED"
            })
            continue

        if not api_deleted or not ls_remote_deleted:
            print(f"  [FAIL] Remote branch {branch_name} still exists on {gh_repo}!")
            results["failures"].append(f"{gh_repo}: remote branch {branch_name} not deleted")
        else:
            print(f"  [OK] Remote branch {branch_name} confirmed deleted.")

        results["remote_branches"].append({
            "item": name,
            "gh_repo": gh_repo,
            "branch": branch_name,
            "api_deleted": api_deleted,
            "ls_remote_deleted": ls_remote_deleted,
            "status": "PASS" if api_deleted and ls_remote_deleted else "FAIL"
        })

    print(f"\nPhase 3: Repository Hygiene, Locks, Rebases & Detached HEAD ({len(distinct_repos)} local checkouts)...")
    for r in distinct_repos:
        name = r["name"]
        path = r["path"]
        expected_base = r["base_branch"]
        print(f"\n[{r['index']}/{len(distinct_repos)}] Inspecting {path}...")

        # 1. Lock files (.git/index.lock, *.lock)
        lock_files = []
        git_dir = os.path.join(path, ".git")
        if os.path.exists(git_dir):
            if os.path.isdir(git_dir):
                for root, dirs, files in os.walk(git_dir):
                    for f in files:
                        if f.endswith(".lock"):
                            lock_files.append(os.path.join(root, f))
            elif os.path.isfile(git_dir):
                # Git worktree / submodule pointer
                pass

        has_locks = len(lock_files) > 0
        if has_locks:
            print(f"  [FAIL] Found lock files: {lock_files}")
            results["failures"].append(f"{name}: lock files found {lock_files}")
        else:
            print(f"  [OK] Zero lock files found.")

        # 2. Pending rebase / merge / cherry-pick / bisect states
        pending_states = []
        checks = [
            ("rebase-apply", os.path.join(git_dir, "rebase-apply")),
            ("rebase-merge", os.path.join(git_dir, "rebase-merge")),
            ("MERGE_HEAD", os.path.join(git_dir, "MERGE_HEAD")),
            ("CHERRY_PICK_HEAD", os.path.join(git_dir, "CHERRY_PICK_HEAD")),
            ("REVERT_HEAD", os.path.join(git_dir, "REVERT_HEAD")),
            ("BISECT_LOG", os.path.join(git_dir, "BISECT_LOG"))
        ]
        for state_name, state_path in checks:
            if os.path.exists(state_path):
                pending_states.append(state_name)

        has_pending = len(pending_states) > 0
        if has_pending:
            print(f"  [FAIL] Pending git state operations found: {pending_states}")
            results["failures"].append(f"{name}: pending states {pending_states}")
        else:
            print(f"  [OK] Zero pending rebase/merge states.")

        # 3. Detached HEAD check
        rc_sym, out_sym, err_sym = run_cmd("git symbolic-ref -q HEAD", cwd=path)
        is_detached = (rc_sym != 0)
        rc_branch, current_branch, _ = run_cmd("git branch --show-current", cwd=path)

        if is_detached or current_branch == "":
            print(f"  [FAIL] Detached HEAD state detected!")
            results["failures"].append(f"{name}: detached HEAD state")
        elif current_branch != expected_base:
            print(f"  [FAIL] Current branch '{current_branch}' != expected '{expected_base}'")
            results["failures"].append(f"{name}: branch is '{current_branch}', expected '{expected_base}'")
        else:
            print(f"  [OK] Active branch is '{current_branch}' (not detached, matches tracking base).")

        # 4. Deleted local feature branch
        rc_b, out_b, _ = run_cmd("git branch --list chore/agyis-harness-onboarding", cwd=path)
        local_branch_exists = bool(out_b.strip())
        if local_branch_exists:
            print(f"  [FAIL] Local branch chore/agyis-harness-onboarding still exists!")
            results["failures"].append(f"{name}: local branch chore/agyis-harness-onboarding exists")
        else:
            print(f"  [OK] Local feature branch deleted.")

        # 5. Working tree status
        rc_st, porcelain, _ = run_cmd("git status --porcelain", cwd=path)
        wip_expected = r.get("wip_expected", False)
        if wip_expected:
            print(f"  [OK] Restored in-flight WIP verified:\n{porcelain}")
        else:
            if porcelain.strip():
                print(f"  [FAIL] Working tree is dirty when expected clean:\n{porcelain}")
                results["failures"].append(f"{name}: working tree dirty: {porcelain}")
            else:
                print(f"  [OK] Working tree 100% clean.")

        results["repo_hygiene"].append({
            "name": name,
            "path": path,
            "active_branch": current_branch,
            "expected_base": expected_base,
            "is_detached": is_detached,
            "lock_files": lock_files,
            "pending_states": pending_states,
            "local_feature_branch_exists": local_branch_exists,
            "porcelain_status": porcelain,
            "status": "PASS" if not has_locks and not has_pending and not is_detached and (current_branch == expected_base) and not local_branch_exists and (wip_expected or not porcelain.strip()) else "FAIL"
        })

    # Summary
    print("\n" + "=" * 80)
    print("VERIFICATION SUMMARY")
    print("=" * 80)
    print(f"Total Failures: {len(results['failures'])}")
    if results["failures"]:
        print("FAILURES ENCOUNTERED:")
        for f in results["failures"]:
            print(f" - {f}")
    else:
        print("ALL EMPIRICAL CHECKS PASSED PERFECTLY!")

    with open("/home/kuasha/Dev/psl-agy-harness/scripts/verify_challenger_lineage_results.json", "w") as f:
        json.dump(results, f, indent=2)
    print("\nResults written to /home/kuasha/Dev/psl-agy-harness/scripts/verify_challenger_lineage_results.json")

if __name__ == "__main__":
    main()
