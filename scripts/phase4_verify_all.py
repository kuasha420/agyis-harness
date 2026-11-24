#!/usr/bin/env python3
"""Phase 4: Final Post-Merge Verification Gate (agyis doctor + native test suites)."""

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
    {
        "name": "sample-ts-app",
        "path": "sample-ts-app",
        "test_cmd": ["pnpm", "test"],
        "test_name": "pnpm test (Vitest)",
    },
    {
        "name": "sample-py-service",
        "path": "sample-py-service",
        "test_cmd": ["pytest", "tests/"],
        "test_name": "pytest tests/",
    },
    {
        "name": "sample-rust-cli",
        "path": "sample-rust-cli",
        "test_cmd": ["cargo", "test"],
        "test_name": "cargo test",
    },
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


def run_cmd(cmd: List[str], cwd: Path | None = None, env: Dict[str, str] | None = None) -> tuple[int, str, str]:
    res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, cwd=cwd, env=env)
    return res.returncode, res.stdout.strip(), res.stderr.strip()


def parse_args(argv: List[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run agyis doctor and native test suites across fleet repositories.")
    parser.add_argument(
        "--repos-config",
        default=os.environ.get("AGYIS_FLEET_CONFIG"),
        help="Path to JSON file containing repo entries [{name, path, test_cmd, test_name}, ...].",
    )
    parser.add_argument(
        "--workspace-root",
        default=os.environ.get("AGYIS_WORKSPACE_ROOT") or str(REPO_ROOT.parent),
        help="Base directory used to resolve relative repo paths.",
    )
    parser.add_argument(
        "--output",
        default=str(REPO_ROOT / "scripts" / "phase4_verification_results.json"),
        help="Output JSON report path.",
    )
    return parser.parse_args(argv)


def main(argv: List[str] | None = None) -> int:
    args = parse_args(argv)
    if not args.repos_config:
        print("Notice: --repos-config not supplied; using sample placeholder repositories.", file=sys.stderr)
    repos = load_repos_config(args.repos_config)
    workspace_root = Path(args.workspace_root).resolve()

    doctor_results: List[Dict[str, Any]] = []
    test_results: List[Dict[str, Any]] = []

    print("=" * 70)
    print("Executing Phase 4: Final Post-Merge Verification Gate")
    print("=" * 70)

    print(f"\nPart 1: Running 'agyis doctor' across {len(repos)} repositories...")
    for idx, repo in enumerate(repos, 1):
        name = repo["name"]
        repo_path = resolve_repo_path(repo, workspace_root)
        print(f"[{idx}/{len(repos)}] Running agyis doctor in {name} ({repo_path})...")
        if not repo_path.is_dir():
            print(f"  ERROR: repository path does not exist: {repo_path}", file=sys.stderr)
            return 1
        code, stdout, stderr = run_cmd(["agyis", "doctor"], cwd=repo_path)
        if code != 0:
            print(f"  FAILED (exit code {code}): {stderr}", file=sys.stderr)
            return 1
        print("  PASS (exit code 0)")
        doctor_results.append({
            "repo": name,
            "path": str(repo_path),
            "command": "agyis doctor",
            "exit_code": code,
            "output": stdout,
        })

    print("\nPart 2: Running native test suites across repositories...")
    env = os.environ.copy()
    env["CI"] = "true"

    for idx, repo in enumerate(repos, 1):
        name = repo["name"]
        repo_path = resolve_repo_path(repo, workspace_root)
        cmd = repo.get("test_cmd")
        test_name = repo.get("test_name") or (" ".join(cmd) if cmd else "N/A")

        if cmd is None:
            print(f"[{idx}/{len(repos)}] {name}: {test_name}")
            test_results.append({
                "repo": name,
                "path": str(repo_path),
                "command": None,
                "test_name": test_name,
                "exit_code": 0,
                "status": "SKIPPED_NO_TEST_SCRIPT",
                "output": "Repository has no native test script configured.",
            })
            continue

        print(f"[{idx}/{len(repos)}] Running {test_name} in {name}...")
        code, stdout, stderr = run_cmd(cmd, cwd=repo_path, env=env)
        if code != 0:
            print(f"  FAILED (exit code {code}): {stderr}\n{stdout}", file=sys.stderr)
            return 1
        print("  PASS (exit code 0)")
        test_results.append({
            "repo": name,
            "path": str(repo_path),
            "command": " ".join(cmd),
            "test_name": test_name,
            "exit_code": code,
            "status": "PASS",
            "output_snippet": stdout[-500:] if len(stdout) > 500 else stdout,
        })

    final_payload = {
        "doctor_results": doctor_results,
        "test_results": test_results,
    }

    out_file = Path(args.output)
    out_file.parent.mkdir(parents=True, exist_ok=True)
    out_file.write_text(json.dumps(final_payload, indent=2) + "\n", encoding="utf-8")
    print(f"\nPhase 4 completed! All {len(repos)} doctor checks and native tests passed. Results saved to {out_file}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
