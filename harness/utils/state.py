# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Purrfect Software Limited (PSL)

"""
Canonical state directory helper for PSL Harness (ADR-014 / ADR-015).
"""

from __future__ import annotations

import os
from pathlib import Path


def get_state_dir(default_name: str = "psl_agy_harness_state") -> Path:
    """
    Returns the harness state directory respecting PSL_HARNESS_STATE_DIR.
    Ensures directory exists.
    """
    env_dir = os.environ.get("PSL_HARNESS_STATE_DIR")
    if env_dir:
        path = Path(env_dir)
    else:
        path = Path(f"/tmp/{default_name}")
    path.mkdir(parents=True, exist_ok=True)
    return path
