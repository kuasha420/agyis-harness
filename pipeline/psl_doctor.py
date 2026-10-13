#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Arafat Zahan (@kuasha420)
# Corporate Stewardship & Infrastructure: Purrfect Software Limited (PSL)
# Governed by: ICARO-42/b Ordinance (Company-Supported Personal IP Framework)

"""
Backward-compatibility wrapper for pipeline.psl_doctor.

The canonical workstation doctor engine now resides in harness.runtime.doctor (ADR-014).
This shim maintains full backward compatibility for existing scripts, tests, and entrypoints.
"""

from __future__ import annotations

import sys
from harness.runtime import doctor as _doctor
from harness.runtime.doctor import (
    DEFAULT_MATRIX,
    REPO_ROOT,
    check_duplicate_agents,
    check_hooks_health,
    check_node_script_hygiene,
    check_psl_collision,
    check_tool,
    detect_os_family,
    find_hermetic_uv_python,
    heal_environment,
    main,
    parse_version,
    print_cli_report,
    run_doctor,
)

# Re-export all public attributes
for _name in dir(_doctor):
    if not _name.startswith("__"):
        globals()[_name] = getattr(_doctor, _name)

if __name__ == "__main__":
    sys.exit(main())
