#!/usr/bin/env python3
"""
Milestone 1 Census Empirical Verification Script.
Checks all 21 PRs listed in FEEDBACK_MATRIX.md against live GitHub API.
Validates:
- PR exists
- State is OPEN
- Head branch is 'chore/agyis-harness-onboarding'
- Base branch matches FEEDBACK_MATRIX.md target branch
Also sweeps all 3 owners (purrfectsoft, kuasha420, sakibtamim) for any other open PRs on chore/agyis-harness-onboarding.
"""

import json
import subprocess
import sys
from typing import Dict, List, Any

EXPECTED_PRS = [
    {"index": 1, "owner": "purrfectsoft", "repo": "chakra-ui-icons-compat", "pr": 1, "target": "develop"},
    {"index": 2, "owner": "purrfectsoft", "repo": "bookcover-craft-api", "pr": 6, "target": "dev"},
    {"index": 3, "owner": "purrfectsoft", "repo": "bookcover-craft", "pr": 4, "target": "staging"},
    {"index": 4, "owner": "purrfectsoft", "repo": "arbiter", "pr": 1, "target": "develop"},
    {"index": 5, "owner": "purrfectsoft", "repo": "jasper-hosted", "pr": 42, "target": "main"},
    {"index": 6, "owner": "purrfectsoft", "repo": "chronicle-time-keeper", "pr": 16, "target": "develop"},
    {"index": 7, "owner": "purrfectsoft", "repo": "sunshine-physio-webapp", "pr": 52, "target": "main"},
    {"index": 8, "owner": "purrfectsoft", "repo": "purrmission", "pr": 4, "target": "master"},
    {"index": 9, "owner": "purrfectsoft", "repo": "mm-website", "pr": 411, "target": "develop"},
    {"index": 10, "owner": "purrfectsoft", "repo": "psl-website", "pr": 74, "target": "develop"},
    {"index": 11, "owner": "purrfectsoft", "repo": "psl-scaffold", "pr": 11, "target": "develop"},
    {"index": 12, "owner": "purrfectsoft", "repo": "psl-boilerplate", "pr": 1, "target": "develop"},
    {"index": 13, "owner": "purrfectsoft", "repo": "purrfectcore-client", "pr": 543, "target": "develop"},
    {"index": 14, "owner": "purrfectsoft", "repo": "purrfectcore-001", "pr": 611, "target": "develop"},
    {"index": 15, "owner": "kuasha420", "repo": "jimha", "pr": 1, "target": "main"},
    {"index": 16, "owner": "kuasha420", "repo": "knot-mesh", "pr": 80, "target": "main"},
    {"index": 17, "owner": "kuasha420", "repo": "purr", "pr": 14, "target": "main"},
    {"index": 18, "owner": "kuasha420", "repo": "react-native-template-ts-plus", "pr": 19, "target": "feat/resurrection"},
    {"index": 19, "owner": "kuasha420", "repo": "purrmission", "pr": 161, "target": "master"},
    {"index": 20, "owner": "sakibtamim", "repo": "purrfect-download-manager", "pr": 23, "target": "develop"},
    {"index": 21, "owner": "sakibtamim", "repo": "Jasper", "pr": 172, "target": "master"},
]

def run_cmd(cmd: List[str]) -> str:
    res = subprocess.run(cmd, capture_output=True, text=True)
    if res.returncode != 0:
        raise RuntimeError(f"Command {' '.join(cmd)} failed with code {res.returncode}: {res.stderr}")
    return res.stdout

def main():
    print("=== Milestone 1 Empirical Verification: 21 PR Census ===")
    results = []
    all_passed = True

    for entry in EXPECTED_PRS:
        full_repo = f"{entry['owner']}/{entry['repo']}"
        pr_num = entry['pr']
        expected_target = entry['target']
        expected_head = "chore/agyis-harness-onboarding"

        cmd = [
            "gh", "pr", "view", str(pr_num),
            "--repo", full_repo,
            "--json", "number,state,baseRefName,headRefName,title,url"
        ]
        try:
            out = run_cmd(cmd)
            data = json.loads(out)
            actual_state = data.get("state")
            actual_target = data.get("baseRefName")
            actual_head = data.get("headRefName")
            actual_title = data.get("title")
            actual_url = data.get("url")

            is_open = (actual_state == "OPEN")
            head_match = (actual_head == expected_head)
            target_match = (actual_target == expected_target)

            passed = is_open and head_match and target_match
            if not passed:
                all_passed = False

            res_entry = {
                "index": entry["index"],
                "repo": full_repo,
                "pr": pr_num,
                "expected_target": expected_target,
                "actual_target": actual_target,
                "expected_head": expected_head,
                "actual_head": actual_head,
                "state": actual_state,
                "title": actual_title,
                "url": actual_url,
                "passed": passed
            }
            results.append(res_entry)
            status_symbol = "✓" if passed else "✗"
            print(f"[{status_symbol}] #{entry['index']} {full_repo}#{pr_num} state={actual_state} target={actual_target} head={actual_head}")
            if not passed:
                print(f"    FAIL: is_open={is_open}, head_match={head_match}, target_match={target_match}")
        except Exception as e:
            all_passed = False
            print(f"[✗] #{entry['index']} {full_repo}#{pr_num} ERROR: {e}")
            results.append({
                "index": entry["index"],
                "repo": full_repo,
                "pr": pr_num,
                "passed": False,
                "error": str(e)
            })

    print("\n=== Search Sweep Across 3 Owners for any other open PRs on chore/agyis-harness-onboarding ===")
    owners = ["purrfectsoft", "kuasha420", "sakibtamim"]
    discovered_prs = {}
    for owner in owners:
        search_cmd = [
            "gh", "search", "prs",
            "--head", "chore/agyis-harness-onboarding",
            "--owner", owner,
            "--state", "open",
            "--json", "repository,number,title,state,url"
        ]
        out = run_cmd(search_cmd)
        prs = json.loads(out)
        discovered_prs[owner] = prs
        print(f"Owner {owner}: found {len(prs)} open PRs")

    total_discovered = sum(len(v) for v in discovered_prs.values())
    print(f"Total discovered open PRs: {total_discovered} (Expected: 21)")

    # Check for unexpected PRs
    expected_set = {(e['owner'] + "/" + e['repo']).lower(): e['pr'] for e in EXPECTED_PRS}
    discovered_set = {}
    for owner, pr_list in discovered_prs.items():
        for p in pr_list:
            nwo = p['repository']['nameWithOwner'].lower()
            discovered_set[nwo] = p['number']

    missing_in_census = set(discovered_set.keys()) - set(expected_set.keys())
    missing_in_github = set(expected_set.keys()) - set(discovered_set.keys())

    if missing_in_census:
        print(f"WARNING: Found open PRs not in census: {missing_in_census}")
        all_passed = False
    else:
        print("✓ Zero extra open PRs found on GitHub outside census.")

    if missing_in_github:
        print(f"WARNING: Census contains PRs not found in open search: {missing_in_github}")
        all_passed = False
    else:
        print("✓ All census PRs accounted for in GitHub search.")

    verdict = "APPROVE" if all_passed else "REQUEST_CHANGES"
    print(f"\nFINAL VERDICT: {verdict}")

    output_summary = {
        "verdict": verdict,
        "all_passed": all_passed,
        "total_census_prs": len(EXPECTED_PRS),
        "total_github_open_prs": total_discovered,
        "results": results,
        "discovered_by_owner": {k: len(v) for k, v in discovered_prs.items()}
    }

    with open("/home/kuasha/Dev/psl-agy-harness/scripts/verify_m1_census_results.json", "w") as f:
        json.dump(output_summary, f, indent=2)
    print("Results dumped to /home/kuasha/Dev/psl-agy-harness/scripts/verify_m1_census_results.json")

if __name__ == "__main__":
    main()
