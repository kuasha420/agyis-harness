# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Purrfect Software Limited (PSL)

"""
Constants and configuration helpers for telemetry sync (ADR-030).
"""

from __future__ import annotations

import os
from typing import Optional

DEFAULT_BATCH_SESSION_LIMIT = 10
DEFAULT_BATCH_STEP_LIMIT = 2500


def _get_retry_backoff(custom: Optional[float] = None) -> float:
    if custom is not None:
        return custom
    env_val = os.environ.get("PSL_RETRY_BACKOFF")
    if env_val is not None:
        try:
            return float(env_val)
        except ValueError:
            pass
    return 1.0
