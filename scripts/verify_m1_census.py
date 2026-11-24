#!/usr/bin/env python3
"""
Milestone 1 Census Empirical Verification Script.
Checks onboarding PRs from a fleet configuration against the live GitHub API.
Validates PR existence, OPEN state, expected head branch, and base branch alignment,
and optionally sweeps configured GitHub owners for unaccounted open onboarding PRs.
"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import subprocess
import sys
from typing import Any, Dict, List

REPO_ROOT = Path(__file__).resolve().parent.parent

DEFAULT_SAMPLE_PRS: List[Dict[str, Any]] = [
    {"index": 1, "owner": "example-org", "repo": "sample-ts-app", "pr": 1, "target": "develop"},
    {"index": 2, "owner": "example-org", "repo": "sample-py-service", "pr": 2, "target": "main"},
    {"index": 3, "owner": "example-org", "repo": "sample-rust-cli", "pr": 3, "target": "main"},
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


def run_cmd(cmd: List[str]) -> str:
    res = subprocess.run(cmd, capture_output=True, text=True)
    if res.returncode != 0:
        raise RuntimeError(f"Command {' '.join(cmd)} failed with code {res.returncode}: {res.stderr}")
    return res.stdout


def parse_args(argv: List[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Verify fleet onboarding PR census against GitHub.")
    parser.add_argument(
        "--repos-config",
        default=os.environ.get("AGYIS_FLEET_CONFIG"),
        help="Path to JSON file containing PR entries [{index, owner, repo, pr, target}, ...].",
    )
    parser.add_argument(
        "--owners",
        default=os.environ.get("AGYIS_FLEET_OWNERS", ""),
        help="Comma-separated GitHub owners/orgs to sweep for open onboarding PRs.",
    )
    parser.add_argument(
        "--head-branch",
        default=os.environ.get("AGYIS_ONBOARD_BRANCH", "chore/agyis-harness-onboarding"),
        help="Expected head branch name.",
    )
    parser.add_argument(
        "--output",
        default=str(REPO_ROOT / "scripts" / "verify_m1_census_results.json"),
        help="Output JSON report path.",
    )
    return parser.parse_args(argv)


def main(argv: List[str] | None = None) -> int:
    args = parse_args(argv)
    if not args.repos_config:
        print("Notice: --repos-config not supplied; using sample placeholder PR targets.", file=sys.stderr)
    expected_prs = load_prs_config(args.repos_config)
    owners = [o.strip() for o in args.owners.split(",") if o.strip()] or sorted(
        {str(e.get("owner") or e.get("repo", "").split("/")[0]) for e in expected_prs if e.get("owner") or "/" in str(e.get("repo", ""))}
    )

    print(f"=== Milestone 1 Empirical Verification: {len(expected_prs)} PR Census ===")
    results: List[Dict[str, Any]] = []
    all_passed = True

    for idx, entry in enumerate(expected_prs, 1):
        entry_idx = entry.get("index", idx)
        if "owner" in entry:
            full_repo = f"{entry['owner']}/{entry['repo']}"
        else:
            full_repo = str(entry["repo"])
        pr_num = entry.get("pr") or entry.get("pr_number")
        expected_target = entry.get("target") or entry.get("target_base")
        expected_head = args.head_branch

        cmd = [
            "gh", "pr", "view", str(pr_num),
            "--repo", full_repo,
            "--json", "number,state,baseRefName,headRefName,title,url",
        ]
        try:
            out = run_cmd(cmd)
            data = json.loads(out)
            actual_state = data.get("state")
            actual_target = data.get("baseRefName")
            actual_head = data.get("headRefName")
            actual_title = data.get("title")
            actual_url = data.get("url")

            is_open = actual_state == "OPEN"
            head_match = actual_head == expected_head
            target_match = actual_target == expected_target

            passed = is_open and head_match and target_match
            if not passed:
                all_passed = False

            results.append({
                "index": entry_idx,
                "repo": full_repo,
                "pr": pr_num,
                "expected_target": expected_target,
                "actual_target": actual_target,
                "expected_head": expected_head,
                "actual_head": actual_head,
                "state": actual_state,
                "title": actual_title,
                "url": actual_url,
                "passed": passed,
            })
            status_symbol = "PASS" if passed else "FAIL"
            print(f"[{status_symbol}] #{entry_idx} {full_repo}#{pr_num} state={actual_state} target={actual_target} head={actual_head}")
        except Exception as exc:
            all_passed = False
            print(f"[FAIL] #{entry_idx} {full_repo}#{pr_num} ERROR: {exc}", file=sys.stderr)
            results.append({
                "index": entry_idx,
                "repo": full_repo,
                "pr": pr_num,
                "passed": False,
                "error": str(exc),
            })

    print(f"\n=== Search Sweep Across {len(owners)} Owners for '{args.head_branch}' ===")
    discovered_prs: Dict[str, List[Dict[str, Any]]] = {}
    for owner in owners:
        search_cmd = [
            "gh", "search", "prs",
            "--head", args.head_branch,
            "--owner", owner,
            "--state", "open",
            "--json", "repository,number,title,state,url",
        ]
        try:
            out = run_cmd(search_cmd)
            prs = json.loads(out)
        except Exception as exc:
            all_passed = False
            print(f"Owner {owner}: search ERROR: {exc}", file=sys.stderr)
            prs = []
        discovered_prs[owner] = prs
        print(f"Owner {owner}: found {len(prs)} open PRs")

    total_discovered = sum(len(v) for v in discovered_prs.values())
    expected_set = {
        (f"{e['owner']}/{e['repo']}" if "owner" in e else str(e["repo"])).lower(): (e.get("pr") or e.get("pr_number"))
        for e in expected_prs
    }
    discovered_set: Dict[str, int] = {}
    for pr_list in discovered_prs.values():
        for p in pr_list:
            nwo = p["repository"]["nameWithOwner"].lower()
            discovered_set[nwo] = p["number"]

    missing_in_census = set(discovered_set.keys()) - set(expected_set.keys())
    missing_in_github = set(expected_set.keys()) - set(discovered_set.keys())
    if missing_in_census or missing_in_github:
        all_passed = False
        if missing_in_census:
            print(f"WARNING: Found open PRs not in census: {sorted(missing_in_census)}")
        if missing_in_github:
            print(f"WARNING: Census contains PRs not found in open search: {sorted(missing_in_github)}")

    verdict = "APPROVE" if all_passed else "REQUEST_CHANGES"
    print(f"\nFINAL VERDICT: {verdict}")

    output_summary = {
        "verdict": verdict,
        "all_passed": all_passed,
        "total_census_prs": len(expected_prs),
        "total_github_open_prs": total_discovered,
        "results": results,
        "discovered_by_owner": {k: len(v) for k, v in discovered_prs.items()},
    }

    out_path = Path(args.output)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(output_summary, indent=2) + "\n", encoding="utf-8")
    print(f"Results dumped to {out_path}")
    return 0 if all_passed else 1


if __name__ == "__main__":
    sys.exit(main())
