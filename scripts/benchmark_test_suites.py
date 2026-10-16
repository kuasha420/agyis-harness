#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Arafat Zahan (@kuasha420)
# Corporate Stewardship & Infrastructure: Purrfect Software Limited (PSL)
# Governed by: ICARO-42/b Ordinance (Company-Supported Personal IP Framework)

"""
Empirical Benchmark Verification Script for Agyis Harness Test Suites.

Measures and records:
1. tests/test_telemetry_sync.py execution time across 5 repeated runs
2. tests/test_cli.py execution time across 5 repeated runs
3. python3 -m harness.cli test (full suite) execution time and pass status
4. Asserts sub-second benchmark (<1.0s) for telemetry sync tests
5. Asserts 100% clean pass rate (0 failures, 0 errors)
"""

import json
from pathlib import Path
import statistics
import subprocess
import sys
import time
from typing import Any, Dict, List

REPO_ROOT = Path(__file__).resolve().parent.parent


def run_command(cmd: List[str]) -> Dict[str, Any]:
    t0 = time.perf_counter()
    res = subprocess.run(cmd, cwd=REPO_ROOT, capture_output=True, text=True)
    duration = time.perf_counter() - t0
    return {
        "command": " ".join(cmd),
        "returncode": res.returncode,
        "duration_seconds": round(duration, 4),
        "stdout": res.stdout,
        "stderr": res.stderr,
        "passed": (res.returncode == 0),
    }


def benchmark_suite(cmd: List[str], runs: int = 5) -> Dict[str, Any]:
    durations = []
    all_passed = True
    last_output = ""
    for r in range(runs):
        print(f"  Running {' '.join(cmd)} (run {r+1}/{runs})...")
        res = run_command(cmd)
        durations.append(res["duration_seconds"])
        if not res["passed"]:
            all_passed = False
        last_output = res["stderr"] or res["stdout"]

    return {
        "command": " ".join(cmd),
        "runs": runs,
        "durations": durations,
        "min_seconds": round(min(durations), 4),
        "max_seconds": round(max(durations), 4),
        "mean_seconds": round(statistics.mean(durations), 4),
        "median_seconds": round(statistics.median(durations), 4),
        "sub_second_guarantee": max(durations) < 1.0,
        "all_passed": all_passed,
        "last_output_summary": last_output.strip().splitlines()[-2:] if last_output else [],
    }


def main():
    print("=== Empirical Test Suite Benchmark Verification ===")
    results: Dict[str, Any] = {
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }

    # 1. Telemetry sync tests
    print("\n[1/3] Benchmarking tests/test_telemetry_sync.py...")
    sync_bench = benchmark_suite([sys.executable, "-m", "unittest", "tests/test_telemetry_sync.py"], runs=5)
    results["telemetry_sync_tests"] = sync_bench

    # 2. CLI tests
    print("\n[2/3] Benchmarking tests/test_cli.py...")
    cli_bench = benchmark_suite([sys.executable, "-m", "unittest", "tests/test_cli.py"], runs=5)
    results["cli_tests"] = cli_bench

    # 3. Full test suite
    print("\n[3/3] Benchmarking Full Test Suite (python3 -m harness.cli test)...")
    full_bench = benchmark_suite([sys.executable, "-m", "harness.cli", "test"], runs=1)
    results["full_test_suite"] = full_bench

    # Summary
    print("\nBenchmark Summary:")
    print(f"  Telemetry Sync: min={sync_bench['min_seconds']}s, max={sync_bench['max_seconds']}s, mean={sync_bench['mean_seconds']}s (<1.0s: {sync_bench['sub_second_guarantee']}, passed: {sync_bench['all_passed']})")
    print(f"  CLI Tests:      min={cli_bench['min_seconds']}s, max={cli_bench['max_seconds']}s, mean={cli_bench['mean_seconds']}s (<1.0s: {cli_bench['sub_second_guarantee']}, passed: {cli_bench['all_passed']})")
    print(f"  Full Suite:     duration={full_bench['durations'][0]}s, passed: {full_bench['all_passed']}")

    out_file = REPO_ROOT / "scripts" / "benchmark_test_suites_results.json"
    with open(out_file, "w") as f:
        json.dump(results, f, indent=2)
    print(f"Detailed results written to {out_file}")

    if not sync_bench["all_passed"] or not cli_bench["all_passed"] or not full_bench["all_passed"]:
        sys.exit(1)
    if not sync_bench["sub_second_guarantee"]:
        print("ERROR: Telemetry sync tests failed the sub-second (<1.0s) benchmark!")
        sys.exit(1)


if __name__ == "__main__":
    main()
