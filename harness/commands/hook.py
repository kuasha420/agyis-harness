# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Purrfect Software Limited (PSL)

"""
Lifecycle hook runner CLI command (ADR-014).
"""

from __future__ import annotations

import argparse

from harness.hooks import runner


def cmd_hook(args: argparse.Namespace) -> int:
    """Dispatches lifecycle hook execution from stdin to stdout via fail-safe runner."""
    return runner.run_hook(args.hook_name)
