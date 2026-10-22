# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Arafat Zahan (@kuasha420)
# Corporate Stewardship & Infrastructure: Purrfect Software Limited (PSL)
# Governed by: ICARO-42/b Ordinance (Company-Supported Personal IP Framework)

"""
Test suite runner CLI command (ADR-014, ADR-015, RFC-051 Phase 2).
"""

from __future__ import annotations

import argparse
import os
from pathlib import Path
import subprocess
import sys
import unittest

from harness.discovery import (
    detect_project_test_runner,
    inject_non_interactive_guards,
    resolve_affected_tests,
)
from harness.hooks import completion_fence_hook

REPO_ROOT = Path(__file__).resolve().parent.parent.parent


def _record_verification_all(success: bool, tier: str = "full") -> None:
    try:
        completion_fence_hook.record_verification(success=success, tier=tier)
    except TypeError:
        completion_fence_hook.record_verification(success=success)
    state_dir = completion_fence_hook.get_state_dir()
    if state_dir.exists():
        for sf in state_dir.glob("verification_state_*.json"):
            cid = sf.stem.replace("verification_state_", "")
            try:
                completion_fence_hook.record_verification(success=success, tier=tier, conv_id=cid)
            except TypeError:
                completion_fence_hook.record_verification(success=success, conv_id=cid)


def cmd_test(args: argparse.Namespace) -> int:
    """Runs the test suite with diff-awareness and tier-gated verification."""
    cwd = Path.cwd().resolve()

    # 1. Harmonization pre-step if requested
    if getattr(args, "harmonize", False):
        from harness.harmonize.test_runner import harmonize_test_runners
        dry_run = getattr(args, "dry_run", False)
        res = harmonize_test_runners(workspace_dir=cwd, dry_run=dry_run, apply=not dry_run)
        if not res.success:
            sys.stderr.write(f"Harmonization error: {res.message}\n")
            return 1
        if dry_run:
            print(f"✔ [DRY-RUN] {res.message}")
            return 0

    # 1.5. Micro-mutation testing if requested
    if getattr(args, "mutation", False):
        from harness.mutation.micro_probe import run_micro_mutation, MutationConfig
        config = MutationConfig(
            verbose=getattr(args, "verbose", False),
            repo_root=cwd,
        )
        result = run_micro_mutation(config=config)
        if result.error_message:
            if getattr(args, "json", False):
                import json
                print(json.dumps({
                    "error": result.error_message,
                    "passed": False,
                    "total_mutants": result.total_mutants,
                    "killed": result.killed_mutants,
                    "survived": len(result.survived_mutants),
                    "exit_code": result.exit_code,
                }, indent=2))
            else:
                sys.stderr.write(f"✖ {result.error_message}\n")
            _record_verification_all(success=False, tier="mutation")
            return result.exit_code or 1

        if getattr(args, "json", False):
            import json
            score = 100.0 if result.total_mutants == 0 else (result.killed_mutants / result.total_mutants) * 100.0
            passed = len(result.survived_mutants) == 0
            payload = {
                "total_mutants": result.total_mutants,
                "killed": result.killed_mutants,
                "killed_mutants": result.killed_mutants,
                "survived": len(result.survived_mutants),
                "survived_mutants": [sm.to_dict() if hasattr(sm, "to_dict") else str(sm) for sm in result.survived_mutants],
                "score": score,
                "passed": passed,
            }
            print(json.dumps(payload, indent=2))
            _record_verification_all(success=passed, tier="mutation")
            return 0 if passed else 1

        if result.total_mutants == 0:
            print("✔ 0 mutants generated (clean working tree or only arid lines modified).")
            _record_verification_all(success=True, tier="mutation")
            return 0

        print(f"\nMicro-mutation testing complete: {result.killed_mutants}/{result.total_mutants} killed.")
        if result.survived_mutants:
            for sm in result.survived_mutants:
                print(sm.to_actionable_report())
            _record_verification_all(success=False, tier="mutation")
            return 1
        print("✔ All mutants killed! Test suite verified.")
        _record_verification_all(success=True, tier="mutation")
        return 0

    is_diff = getattr(args, "diff", False)
    is_affected = getattr(args, "affected", False)
    branch = getattr(args, "branch", None)
    pkg = getattr(args, "pkg", None)
    is_full = getattr(args, "full", False)

    # 2. Diff-aware affected test resolution (if any diff flag provided and not --full)
    if (is_diff or is_affected or branch or pkg) and not is_full:
        mode = "affected" if is_affected else "diff"
        resolved = resolve_affected_tests(
            repo_root=cwd,
            mode=mode,
            branch=branch,
            pkg=pkg,
        )

        tier_to_record = "affected" if is_affected else ("pkg" if pkg else "diff")

        if resolved.is_empty:
            print(f"✔ 0 affected tests detected for {mode} scope on clean working tree.")
            _record_verification_all(success=True, tier=tier_to_record)
            return 0

        if getattr(args, "dry_run", False):
            print(f"✔ [DRY-RUN] Would execute: {resolved.runner_cmd} (Tier {resolved.tier}: {resolved.tier_name})")
            return 0

        # Inject non-interactive guards
        clean_cmd, guarded_env = inject_non_interactive_guards(resolved.runner_cmd)

        run_res = subprocess.run(clean_cmd, shell=True, env=guarded_env, cwd=str(cwd))
        success = (run_res.returncode == 0)
        _record_verification_all(success=success, tier=tier_to_record)
        return run_res.returncode

    # 3. Macro / Full Test Execution
    start_dir = getattr(args, "start_dir", None)
    test_dir = Path(start_dir) if start_dir else (REPO_ROOT / "tests")

    # In external workspace without start_dir and with detected runner:
    if not start_dir and cwd != REPO_ROOT and not (cwd / "tests").is_dir():
        external_runner = detect_project_test_runner(cwd)
        if external_runner:
            if getattr(args, "dry_run", False):
                print(f"✔ [DRY-RUN] Would execute full project runner: {external_runner}")
                return 0
            clean_cmd, guarded_env = inject_non_interactive_guards(external_runner)
            run_res = subprocess.run(clean_cmd, shell=True, env=guarded_env, cwd=str(cwd))
            success = (run_res.returncode == 0)
            _record_verification_all(success=success, tier="full")
            return run_res.returncode

    # Standard python unittest discovery
    if not test_dir.exists():
        sys.stderr.write(f"Error: test directory not found at {test_dir}\n")
        return 1

    loader = unittest.TestLoader()
    suite = loader.discover(start_dir=str(test_dir), pattern="test_*.py")
    verbosity = 2 if getattr(args, "verbose", False) else 1
    runner = unittest.TextTestRunner(verbosity=verbosity)
    result = runner.run(suite)

    success = result.wasSuccessful()
    _record_verification_all(success=success, tier="full")
    return 0 if success else 1
