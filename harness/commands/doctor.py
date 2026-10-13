# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Arafat Zahan (@kuasha420)
# Corporate Stewardship & Infrastructure: Purrfect Software Limited (PSL)
# Governed by: ICARO-42/b Ordinance (Company-Supported Personal IP Framework)

"""
Workstation runtime diagnostic & auto-healing CLI command (ADR-014).
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

from harness.runtime import doctor as psl_doctor

DEFAULT_MATRIX = Path(__file__).resolve().parent.parent / "runtime" / "matrix.json"


def cmd_doctor(args: argparse.Namespace) -> int:
    """Executes the workstation runtime audit and optional auto-healing."""
    matrix_path = Path(args.matrix) if getattr(args, "matrix", None) else DEFAULT_MATRIX
    if not matrix_path.exists():
        pkg_matrix = Path(__file__).resolve().parent.parent / "runtime" / "matrix.json"
        if pkg_matrix.exists():
            matrix_path = pkg_matrix
        else:
            sys.stderr.write(f"Error: matrix.json not found at {matrix_path}\n")
            return 1

    audit = psl_doctor.run_doctor(matrix_path)

    if getattr(args, "json", False):
        print(json.dumps(audit, indent=2))
        return 0

    psl_doctor.print_cli_report(audit)

    if getattr(args, "heal", False):
        print("\n🔧 Executing Auto-Healing...")
        actions = psl_doctor.heal_environment(audit, matrix_path)
        for act in actions:
            print(f"  ✔ {act}")
        print()

    if audit["summary"]["missing"] > 0 or audit["summary"]["outdated"] > 0:
        return 1
    return 0
