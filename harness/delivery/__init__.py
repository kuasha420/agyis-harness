# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Arafat Zahan (@kuasha420)
# Corporate Stewardship & Infrastructure: Purrfect Software Limited (PSL)
# Governed by: ICARO-42/b Ordinance (Company-Supported Personal IP Framework)

"""
Agyis Harness Delivery & Global Plugin Installer (ADR-030).
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
    GitTopology,
    GitTopologyProbe,
    RemoteInfo,
    configure_git_exclude,
    create_pull_request,
    verify_zero_git_pollution,
)
from harness.delivery.surfaces import (
    enforce_single_source_skills,
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
    adapt_spdx_license,
    detect_repository_license,
    detect_test_command,
    extract_command_descriptions,
    extract_command_dictionary,
    format_command_dictionary,
    install_workspace,
)
from harness.delivery.cache import (
    DEFAULT_CACHE_TARGETS,
    purge_workspace_build_caches,
)
from harness.delivery.harmonize import (
    HarmonizeResult,
    harmonize_workspace,
    sanitize_workspace_links,
)

purge_build_caches = purge_workspace_build_caches

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
    "GitTopology",
    "GitTopologyProbe",
    "RemoteInfo",
    "configure_git_exclude",
    "create_pull_request",
    "verify_zero_git_pollution",
    "sync_surfaces",
    "find_workspace_root",
    "enforce_single_source_skills",
    "LEGACY_TAG_END",
    "LEGACY_TAG_START",
    "STACK_SKILL_PRESETS",
    "TAG_END",
    "TAG_START",
    "TAGGED_BLOCK_PATTERN",
    "WorkspaceInstallResult",
    "adapt_spdx_license",
    "detect_repository_license",
    "detect_test_command",
    "extract_command_descriptions",
    "extract_command_dictionary",
    "format_command_dictionary",
    "install_workspace",
    "DEFAULT_CACHE_TARGETS",
    "purge_workspace_build_caches",
    "purge_build_caches",
    "HarmonizeResult",
    "harmonize_workspace",
    "sanitize_workspace_links",
]
