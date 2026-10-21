# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Arafat Zahan (@kuasha420)
# Corporate Stewardship & Infrastructure: Purrfect Software Limited (PSL)
# Governed by: ICARO-42/b Ordinance (Company-Supported Personal IP Framework)

"""
Workspace and Dynamic Repository Awareness (DRA) utilities (PSL-SPEC-2026-DRA-001).

Provides runtime detection of:
1. Whether a directory is the PSL/Agyis Harness development repository (`is_harness_workspace`).
2. Native project test runner commands across external client codebases (`detect_project_test_runner`).
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Optional, Union


def is_harness_workspace(cwd: Union[Path, str, None] = None) -> bool:
    """
    Returns True strictly if cwd is the psl-agy-harness / agyis-harness repository,
    detected by repository markers:
      - harness/cli.py
      - pipeline/harvest_conversations.py
      - harness/hooks/hooks.json (or harness/manifest.json)
    """
    if cwd is None:
        root = Path.cwd()
    else:
        root = Path(cwd)

    try:
        if not root.is_dir():
            return False
        has_cli = (root / "harness" / "cli.py").exists()
        has_harvest = (root / "pipeline" / "harvest_conversations.py").exists()
        has_hooks_json = (root / "harness" / "hooks" / "hooks.json").exists()
        has_manifest_json = (root / "harness" / "manifest.json").exists()
        return has_cli and has_harvest and (has_hooks_json or has_manifest_json)
    except OSError:
        return False


from harness.discovery import detect_project_test_runner

__all__ = [
    "is_harness_workspace",
    "detect_project_test_runner",
]

