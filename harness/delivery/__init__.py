# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Purrfect Software Limited (PSL)

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
    GLOBAL_CORE_SKILLS,
    STACK_SKILL_PRESETS,
    TAG_END,
    TAG_START,
    WorkspaceInstallResult,
    install_workspace,
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
    "GLOBAL_CORE_SKILLS",
    "STACK_SKILL_PRESETS",
    "TAG_END",
    "TAG_START",
    "WorkspaceInstallResult",
    "install_workspace",
]
