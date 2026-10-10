# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Purrfect Software Limited (PSL)

"""
Test suite runner CLI command (ADR-014, ADR-015).
"""

from __future__ import annotations

import argparse
from pathlib import Path
import sys
import unittest

from harness.hooks import completion_fence_hook

REPO_ROOT = Path(__file__).resolve().parent.parent.parent


def cmd_test(args: argparse.Namespace) -> int:
    """Runs the test suite."""
    start_dir = getattr(args, "start_dir", None)
    test_dir = Path(start_dir) if start_dir else (REPO_ROOT / "tests")
    if not test_dir.exists():
        sys.stderr.write(f"Error: test directory not found at {test_dir}\n")
        return 1

    loader = unittest.TestLoader()
    suite = loader.discover(start_dir=str(test_dir), pattern="test_*.py")
    verbosity = 2 if getattr(args, "verbose", False) else 1
    runner = unittest.TextTestRunner(verbosity=verbosity)
    result = runner.run(suite)

    success = result.wasSuccessful()
    completion_fence_hook.record_verification(success=success)
    state_dir = completion_fence_hook.get_state_dir()
    if state_dir.exists():
        for sf in state_dir.glob("verification_state_*.json"):
            cid = sf.stem.replace("verification_state_", "")
            completion_fence_hook.record_verification(success=success, conv_id=cid)
    return 0 if success else 1
