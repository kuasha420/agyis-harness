# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Arafat Zahan (@kuasha420)
# Corporate Stewardship & Infrastructure: Purrfect Software Limited (PSL)
# Governed by: ICARO-42/b Ordinance (Company-Supported Personal IP Framework)

"""
Constants and data models for Agyis harness delivery (ADR-014, ADR-030).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
import os
from pathlib import Path
from typing import Any, Dict, List

REPO_ROOT = Path(__file__).resolve().parent.parent.parent


def _resolve_default_plugin_dir() -> Path:
    env_dir = os.environ.get("AGYIS_PLUGINS_DIR") or os.environ.get("PSL_PLUGINS_DIR")
    if env_dir and env_dir.strip():
        return Path(env_dir.strip())
    target = Path.home() / ".gemini" / "config" / "plugins" / "agyis-harness"
    legacy = Path.home() / ".gemini" / "config" / "plugins" / "psl-agy-harness"
    if not target.exists() and legacy.exists():
        return legacy
    return target


DEFAULT_PLUGIN_DIR = _resolve_default_plugin_dir()

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
    ".agents/artifacts/",
    ".agents/teamwork/",
    ".agents/archive/",
    "*.patch",
    ".agyis/",
    ".psl/",
    ".cache/",
    "scratch/",
    "*.env",
    "*.env.*",
    "*.token",
    "*.key",
    "*.pem",
    "ORIGINAL_REQUEST.md",
    "COMPLETION_LEDGER.md",
    "PARKED_STATE.md",
    "pause_gate.json",
    "psl_stage_transition_payload.json",
    "*stage_transition*.json",
    "audit_verdict.json",
    "*verdict*.json",
    "implementation_plan*.md",
    "victory_audit_report*.md",
    "rca_report*.md",
    "heisenbug_rca*.md",
    "research_synthesis*.md",
    "ladder_heartbeat.json",
    "ladder_telemetry.log",
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
    WHEEL = "wheel"


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
