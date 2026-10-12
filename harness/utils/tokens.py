# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Arafat Zahan (@kuasha420)
# Corporate Stewardship & Infrastructure: Purrfect Software Limited (PSL)
# Governed by: ICARO-42/b Ordinance (Company-Supported Personal IP Framework)

"""
Zero-dependency token estimation utility (ADR-014 / ADR-015).
"""

from __future__ import annotations

from pathlib import Path
from typing import Union


def estimate_tokens(content: Union[str, int, float, bytes, Path, None]) -> int:
    """
    Canonical zero-token token estimation (4 characters per token heuristic).
    Supports strings, raw character counts (int/float), bytes, and Path objects.
    """
    if content is None:
        return 0
    if isinstance(content, Path):
        try:
            return max(1, content.stat().st_size // 4)
        except OSError:
            return 0
    if isinstance(content, (int, float)):
        return max(1, int(content) // 4) if content > 0 else 0
    if isinstance(content, bytes):
        return max(1, len(content) // 4) if content else 0
    s = str(content)
    return max(1, len(s) // 4) if s else 0
