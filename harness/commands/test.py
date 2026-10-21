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
