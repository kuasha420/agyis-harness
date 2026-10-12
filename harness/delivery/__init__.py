# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Arafat Zahan (@kuasha420)
# Corporate Stewardship & Infrastructure: Purrfect Software Limited (PSL)
# Governed by: ICARO-42/b Ordinance (Company-Supported Personal IP Framework)

"""
PSL Harness Delivery & Global Plugin Installer (ADR-030).
"""

from __future__ import annotations

from harness.delivery.constants import (
    DEFAULT_PLUGIN_DIR,
    DEFAULT_SURFACE_NAMES,
    DISTRIBUTABLE_ITEMS,
    EXCLUDED_PACKAGING_NAMES,
    GIT_EXCLUDE_PATTERNS,
    REPO_ROOT,
    SYNC_SURFACE_ITEMS,
    DeliveryMode,
    DeliveryResult,
)
from harness.delivery.git_hygiene import (
    configure_git_exclude,
    verify_zero_git_pollution,
)
from harness.delivery.surfaces import (
    find_workspace_root,
    sync_surfaces,
)
from harness.delivery.installer import PluginInstaller
from harness.delivery.coexistence import CoexistenceEngine
from harness.delivery.workspace import (
    LEGACY_TAG_END,
    LEGACY_TAG_START,
    STACK_SKILL_PRESETS,
    TAG_END,
    TAG_START,
    TAGGED_BLOCK_PATTERN,
    WorkspaceInstallResult,
    extract_command_dictionary,
    format_command_dictionary,
    install_workspace,
)
from harness.delivery.harmonize import (
    HarmonizeResult,
    harmonize_workspace,
)

__all__ = [
    "DEFAULT_PLUGIN_DIR",
    "DEFAULT_SURFACE_NAMES",
    "DISTRIBUTABLE_ITEMS",
    "EXCLUDED_PACKAGING_NAMES",
    "GIT_EXCLUDE_PATTERNS",
    "REPO_ROOT",
    "SYNC_SURFACE_ITEMS",
    "DeliveryMode",
    "DeliveryResult",
    "PluginInstaller",
    "CoexistenceEngine",
    "configure_git_exclude",
    "verify_zero_git_pollution",
    "sync_surfaces",
    "find_workspace_root",
    "LEGACY_TAG_END",
    "LEGACY_TAG_START",
    "STACK_SKILL_PRESETS",
    "TAG_END",
    "TAG_START",
    "TAGGED_BLOCK_PATTERN",
    "WorkspaceInstallResult",
    "extract_command_dictionary",
    "format_command_dictionary",
    "install_workspace",
    "HarmonizeResult",
    "harmonize_workspace",
]
