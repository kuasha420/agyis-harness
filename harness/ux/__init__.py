# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Arafat Zahan (@kuasha420)
# Corporate Stewardship & Infrastructure: Purrfect Software Limited (PSL)
# Governed by: ICARO-42/b Ordinance (Company-Supported Personal IP Framework)

"""
Reusable Native Antigravity UX Foundation (`harness.ux`, Track A).

Exports Generative UI widget renderers (`render_crosstalk_widget`,
`render_cli_fallback`, `normalize_crosstalk_view_data`) and validated deep-link
pill formatters (`conversation_pill`, `customization_pill`, `sidecar_pill`).
"""

from __future__ import annotations

from harness.ux.pills import (
    conversation_pill,
    customization_pill,
    is_desktop_surface,
    render_pill_strip,
    sidecar_pill,
)
from harness.ux.widgets import (
    load_ux_asset,
    normalize_crosstalk_view_data,
    render_cli_fallback,
    render_crosstalk_widget,
)

__all__ = [
    "conversation_pill",
    "customization_pill",
    "is_desktop_surface",
    "load_ux_asset",
    "normalize_crosstalk_view_data",
    "render_cli_fallback",
    "render_crosstalk_widget",
    "render_pill_strip",
    "sidecar_pill",
]
