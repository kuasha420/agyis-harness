# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Arafat Zahan (@kuasha420)
# Corporate Stewardship & Infrastructure: Purrfect Software Limited (PSL)
# Governed by: ICARO-42/b Ordinance (Company-Supported Personal IP Framework)

"""
Canonical state directory helper for Agyis Harness (ADR-014 / ADR-015).
"""

from __future__ import annotations

import os
from pathlib import Path


def get_state_dir(default_name: str = "agyis_harness_state") -> Path:
    """
    Returns the harness state directory respecting AGYIS_HARNESS_STATE_DIR and PSL_HARNESS_STATE_DIR.
    Ensures directory exists.
    """
    env_dir = os.environ.get("AGYIS_HARNESS_STATE_DIR") or os.environ.get("PSL_HARNESS_STATE_DIR")
    if env_dir and env_dir.strip():
        path = Path(env_dir.strip())
    else:
        path = Path(f"/tmp/{default_name}")
    path.mkdir(parents=True, exist_ok=True)
    return path
