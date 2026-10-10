# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Purrfect Software Limited (PSL)

"""
Constants and data models for PSL harness delivery (ADR-014, ADR-030).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
import os
from pathlib import Path
from typing import Any, Dict, List

REPO_ROOT = Path(__file__).resolve().parent.parent.parent

DEFAULT_PLUGIN_DIR = (
    Path(os.environ["PSL_PLUGINS_DIR"])
    if "PSL_PLUGINS_DIR" in os.environ
    else Path.home() / ".gemini" / "config" / "plugins" / "psl-agy-harness"
)

DEFAULT_SURFACE_NAMES: tuple[str, ...] = (
    "antigravity",
    "antigravity-cli",
    "antigravity-ide",
)

SYNC_SURFACE_ITEMS: tuple[str, ...] = (
    "agents",
    "skills",
    "plugins",
    "rules",
    "hooks.json",
    "AGENTS.md",
)

GIT_EXCLUDE_PATTERNS: tuple[str, ...] = (
    ".agents/",
    ".psl/",
    ".cache/",
    "scratch/",
)

DISTRIBUTABLE_ITEMS: frozenset[str] = frozenset({
    "plugin.json",
    "harness",
    "matrix.json",
    "hooks.json",
    "skills",
    "agents",
    "rules",
})

EXCLUDED_PACKAGING_NAMES: frozenset[str] = frozenset({
    "pipeline",
    "data",
    "tests",
    "docs",
    "scratch",
    ".git",
    "artifacts",
    "__pycache__",
})


class DeliveryMode(str, Enum):
    """Plugin installation modes."""

    SYMLINK = "symlink"
    COPY = "copy"


@dataclass
class DeliveryResult:
    """Outcome report for plugin installation or uninstallation."""

    success: bool
    mode: str
    target_dir: Path
    source_dir: Path
    items_installed: List[str] = field(default_factory=list)
    duplicates_removed: List[str] = field(default_factory=list)
    surfaces_synced: List[Dict[str, Any]] = field(default_factory=list)
    message: str = ""
