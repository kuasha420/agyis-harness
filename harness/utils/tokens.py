# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Arafat Zahan (@kuasha420)
# Corporate Stewardship & Infrastructure: Purrfect Software Limited (PSL)
# Governed by: ICARO-42/b Ordinance (Company-Supported Personal IP Framework)

"""
Zero-dependency token estimation utility (ADR-014 / ADR-015).
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional, Union


def estimate_tokens(
    content: Union[str, int, float, bytes, Path, None],
    chars_per_token: Optional[float] = None,
) -> int:
    """
    Canonical zero-token token estimation (default 4 chars/token; optional 3.5 HUD ratio).
    Supports strings, raw character counts (int/float), bytes, and Path objects.
    """
    if content is None:
        return 0
    if isinstance(content, Path):
        try:
            char_len = int(content.stat().st_size)
        except OSError:
            return 0
    elif isinstance(content, (int, float)):
        char_len = int(content)
    elif isinstance(content, bytes):
        char_len = len(content)
    else:
        char_len = len(str(content))

    if char_len <= 0:
        return 0
    if chars_per_token is not None and chars_per_token > 0:
        return round(char_len / chars_per_token)
    return max(1, char_len // 4)
