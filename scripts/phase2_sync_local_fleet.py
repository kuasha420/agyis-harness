#!/usr/bin/env python3
"""Phase 2 & 3: Local Fleet Synchronization & Working Tree Verification."""

import json
import os
import subprocess
import sys

REPOS = [
    {"name": "chakra-ui-icons-compat", "path": "/home/kuasha/Dev/chakra-ui-icons-compat", "base": "develop", "expected_merge_sha": "faa7b37af794a15f32aceddcc7cb267c06240519", "wip": False},
    {"name": "bookcover-craft-api", "path": "/home/kuasha/Dev/bookcover-craft-api", "base": "dev", "expected_merge_sha": "c388be52795639684c80c5857328c639e68f9190", "wip": True},
    {"name": "bookcover-craft", "path": "/home/kuasha/Dev/bookcover-craft", "base": "staging", "expected_merge_sha": "d2020b5bfe3442e63740695cb25f5b0a14807c25", "wip": True},
    {"name": "arbiter", "path": "/home/kuasha/Dev/arbiter", "base": "develop", "expected_merge_sha": "3b7c4e8878f9c2d792f50a39d73ae7e058412881", "wip": False},
    {"name": "jasper-hosted", "path": "/home/kuasha/Dev/jasper-hosted", "base": "main", "expected_merge_sha": "21f703c649d8174bf6caef54aaf20a84e5da2215", "wip": False},
    {"name": "chronicle-time-keeper", "path": "/home/kuasha/Dev/chronicle-time-keeper", "base": "develop", "expected_merge_sha": "e0eb32e4a467a5227d887525e666c7cd36c90781", "wip": False},
    {"name": "sunshine-physio-universalapp", "path": "/home/kuasha/Dev/sunshine-physio-universalapp", "base": "main", "expected_merge_sha": "665ca430d57b0948d1173fb77b7eb0554c129d20", "wip": False},
    {"name": "purrmission", "path": "/home/kuasha/Dev/purrmission", "base": "master", "expected_merge_sha": "224e222248a39bf67a4479a470032809904b30df", "wip": False},
    {"name": "mm-website", "path": "/home/kuasha/Dev/mm-website", "base": "develop", "expected_merge_sha": "a513f1690d7f0cb02e684f43f043735cb3384e03", "wip": False},
    {"name": "psl-website", "path": "/home/kuasha/Dev/psl-website", "base": "develop", "expected_merge_sha": "4bdac50b6c6f3de961905f4b3098983891cd4234", "wip": False},
    {"name": "psl-scaffold", "path": "/home/kuasha/Dev/psl-scaffold", "base": "develop", "expected_merge_sha": "16505987b2a100818ba37cbab88023a2792f90fb", "wip": False},
    {"name": "psl-boilerplate", "path": "/home/kuasha/Dev/psl-boilerplate", "base": "develop", "expected_merge_sha": "895ed6acdb7bf1b00f0890c3158156ef703f7ca8", "wip": False},
    {"name": "purrfectcore-client", "path": "/home/kuasha/Dev/purrfectcore-client", "base": "develop", "expected_merge_sha": "dc5b8dd30eec61724350ebe28acee773fbaf8e2c", "wip": False},
    {"name": "purrfectcore-001", "path": "/home/kuasha/Dev/purrfectcore-001", "base": "develop", "expected_merge_sha": "dc30494d4218e6205c961c6d6c1b23ebb9dcc7ae", "wip": False},
    {"name": "jimha", "path": "/home/kuasha/Dev/jimha", "base": "main", "expected_merge_sha": "521b7cc8d39b0ff94d2682245fd9ebea27645d9c", "wip": False},
    {"name": "knot-mesh", "path": "/home/kuasha/Dev/knot-mesh", "base": "main", "expected_merge_sha": "e4ab43d56f392a184be1157f298493fac279b944", "wip": False},
    {"name": "purr", "path": "/home/kuasha/Dev/purr", "base": "main", "expected_merge_sha": "891c806e1f50fe68af1b761d03995e76cec0a454", "wip": False},
    {"name": "react-native-template-ts-plus", "path": "/home/kuasha/Dev/react-native-template-ts-plus", "base": "feat/resurrection", "expected_merge_sha": "28f4e079f44d06510f665e05b0cf25750a8d282b", "wip": False},
    {"name": "purrfect-download-manager", "path": "/home/kuasha/Dev/purrfect-download-manager", "base": "develop", "expected_merge_sha": None, "wip": False},
    {"name": "Jasper", "path": "/home/kuasha/Dev/Jasper", "base": "master", "expected_merge_sha": "3d10e0e89e607d3d7c1ea105f87c082c325b8dbd", "wip": False},
]

def run_cmd(cmd, cwd=None):
    res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, cwd=cwd)
    return res.returncode, res.stdout.strip(), res.stderr.strip()

def main():
    results = []
    print("Executing Phase 2: Local Fleet Synchronization across 20 repositories...")
    
    for idx, repo in enumerate(REPOS, 1):
        name = repo["name"]
        path = repo["path"]
        base = repo["base"]
        expected_sha = repo["expected_merge_sha"]
        has_wip = repo["wip"]
        
        print(f"[{idx}/20] Syncing {name} ({path}) to base '{base}'...")
        
        # 1. Checkout base branch
        c_code, c_out, c_err = run_cmd(["git", "-C", path, "checkout", base])
        if c_code != 0:
            print(f"  ERROR checking out {base}: {c_err}")
            sys.exit(1)
            
        # 2. Fast-forward pull from origin
        p_code, p_out, p_err = run_cmd(["git", "-C", path, "pull", "--ff-only", "origin", base])
        if p_code != 0:
            print(f"  ERROR pulling {base}: {p_err}")
            sys.exit(1)
            
        # 3. Verify local HEAD
        h_code, current_head, h_err = run_cmd(["git", "-C", path, "rev-parse", "HEAD"])
        print(f"  Current HEAD: {current_head}")
        if expected_sha:
            assert current_head == expected_sha, f"{name}: HEAD {current_head} != expected {expected_sha}"
            print(f"  ✓ HEAD matches merge commit {expected_sha}")
        else:
            print(f"  ℹ HEAD is {current_head} (upstream merge pending on third-party repo)")
            
        # 4. Prune/delete local feature branch if present
        b_code, b_out, b_err = run_cmd(["git", "-C", path, "branch", "-D", "chore/agyis-harness-onboarding"])
        branch_deleted = (b_code == 0)
        
        # 5. Check active branch
        a_code, active_branch, a_err = run_cmd(["git", "-C", path, "branch", "--show-current"])
        assert active_branch == base, f"{name}: active branch is {active_branch}, expected {base}"
        
        # 6. Check porcelain status
        s_code, status_out, s_err = run_cmd(["git", "-C", path, "status", "--porcelain"])
        if has_wip:
            assert len(status_out) > 0, f"{name}: expected WIP files in working tree, but status is empty!"
            print(f"  ✓ Restored WIP files verified in status:\n{status_out}")
            tree_clean = False
        else:
            assert status_out == "", f"{name}: expected clean working tree, but got:\n{status_out}"
            print("  ✓ Working tree verified 100% CLEAN")
            tree_clean = True
            
        results.append({
            "index": idx,
            "name": name,
            "path": path,
            "base_branch": base,
            "active_branch": active_branch,
            "current_head": current_head,
            "expected_merge_sha": expected_sha,
            "head_matches_merge": (current_head == expected_sha) if expected_sha else None,
            "pull_output": p_out,
            "local_feature_branch_deleted": branch_deleted,
            "working_tree_clean": tree_clean,
            "porcelain_status": status_out,
            "wip_restored": has_wip
        })
        
    out_file = "/home/kuasha/Dev/psl-agy-harness/scripts/phase2_sync_results.json"
    with open(out_file, "w") as f:
        json.dump(results, f, indent=2)
    print(f"\nPhase 2 & 3 completed successfully! Results written to {out_file}")

if __name__ == "__main__":
    main()
