#!/usr/bin/env python3
"""Build consolidated fleet execution_results.json from PR checks and local verification outputs."""

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
    parser = argparse.ArgumentParser(description="Aggregate fleet PR, sync, and verification results.")
    parser.add_argument(
        "--repos-config",
        default=os.environ.get("AGYIS_FLEET_CONFIG"),
        help="Path to JSON file containing PR targets.",
    )
    parser.add_argument(
        "--phase2-results",
        default=str(REPO_ROOT / "scripts" / "phase2_sync_results.json"),
        help="Path to phase 2 sync results JSON.",
    )
    parser.add_argument(
        "--phase4-results",
        default=str(REPO_ROOT / "scripts" / "phase4_verification_results.json"),
        help="Path to phase 4 verification results JSON.",
    )
    parser.add_argument(
        "--branch",
        default=os.environ.get("AGYIS_ONBOARD_BRANCH", "chore/agyis-harness-onboarding"),
        help="Onboarding branch expected to be deleted after merge.",
    )
    parser.add_argument(
        "--output",
        default=str(REPO_ROOT / "scripts" / "execution_results.json"),
        help="Output consolidated JSON path.",
    )
    return parser.parse_args(argv)


def main(argv: List[str] | None = None) -> int:
    args = parse_args(argv)
    if not args.repos_config:
        print("Notice: --repos-config not supplied; using sample placeholder PR targets.", file=sys.stderr)
    prs = load_prs_config(args.repos_config)
    print("Collecting live GitHub PR verification records...")
    pr_records: List[Dict[str, Any]] = []

    for idx, item in enumerate(prs, 1):
        repo = item["repo"]
        pr_num = item.get("pr") or item.get("pr_number")
        target_base = item["target_base"]

        code, stdout, stderr = run_cmd([
            "gh", "pr", "view", str(pr_num), "--repo", repo,
            "--json", "state,mergeCommit,mergedAt,mergedBy,headRefName,baseRefName,title,url",
        ])

        if code == 0:
            data = json.loads(stdout)
            state = data.get("state")
            merge_commit = (data.get("mergeCommit") or {}).get("oid")
            merged_at = data.get("mergedAt")
            merged_by = (data.get("mergedBy") or {}).get("login")

            b_code, b_out, b_err = run_cmd(["gh", "api", f"repos/{repo}/branches/{args.branch}"])
            remote_branch_deleted = b_code != 0 and (
                "404" in b_out or "Branch not found" in b_out or "404" in b_err or "Branch not found" in b_err
            )

            record = {
                "index": idx,
                "repo": repo,
                "pr_number": pr_num,
                "title": data.get("title"),
                "url": data.get("url"),
                "target_base": target_base,
                "baseRefName": data.get("baseRefName"),
                "headRefName": data.get("headRefName"),
                "state": state,
                "merge_commit_sha": merge_commit,
                "merged_at": merged_at,
                "merged_by": merged_by,
                "remote_branch_deleted": remote_branch_deleted,
                "merge_command": f"gh pr merge {pr_num} --repo {repo} --merge --delete-branch",
                "merge_result": "SUCCESS" if state == "MERGED" else "PENDING_OR_BLOCKED",
            }
        else:
            record = {
                "index": idx,
                "repo": repo,
                "pr_number": pr_num,
                "target_base": target_base,
                "error": stderr,
            }
        pr_records.append(record)

    sync_records = json.loads(Path(args.phase2_results).read_text(encoding="utf-8"))
    p4_data = json.loads(Path(args.phase4_results).read_text(encoding="utf-8"))

    wip_records = {
        rec["name"]: {
            "path": rec.get("path"),
            "base_branch": rec.get("base_branch"),
            "patch_file": ".agents/artifacts/pre_onboard_safety.patch",
            "status": "RESTORED_CLEANLY" if rec.get("wip_restored") else "CLEAN",
        }
        for rec in sync_records
        if rec.get("wip_restored")
    }

    doctor_results = p4_data.get("doctor_results", [])
    test_results = p4_data.get("test_results", [])

    final_results = {
        "summary": {
            "total_prs": len(prs),
            "merged_prs": len([p for p in pr_records if p.get("state") == "MERGED"]),
            "pending_prs": len([p for p in pr_records if p.get("state") != "MERGED"]),
            "synced_repos": len(sync_records),
            "wip_restored_repos": len(wip_records),
            "clean_repos": len([r for r in sync_records if r.get("working_tree_clean")]),
            "doctor_checks_passed": len([d for d in doctor_results if d.get("exit_code") == 0]),
            "native_test_suites_passed": len([t for t in test_results if t.get("exit_code") == 0]),
        },
        "pull_requests": pr_records,
        "local_sync": sync_records,
        "wip_restoration": wip_records,
        "doctor_verification": doctor_results,
        "native_tests_verification": test_results,
    }

    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(final_results, indent=2) + "\n", encoding="utf-8")
    print(f"Successfully generated {output_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
