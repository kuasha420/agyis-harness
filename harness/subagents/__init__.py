# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Arafat Zahan (@kuasha420)
# Corporate Stewardship & Infrastructure: Purrfect Software Limited (PSL)
# Governed by: ICARO-42/b Ordinance (Company-Supported Personal IP Framework)

"""
Specialist subagent management and Ladder protocol coordination (ADR-014, ADR-025).
"""

from __future__ import annotations

from harness.subagents.spec import (
    DEFAULT_AGENTS_DIR,
    DEFAULT_TARGET_DIR,
    REPO_ROOT,
    ANTIGRAVITY_PLATFORM_TOOLS,
    CAPABILITY_BUNDLES,
    AgentArchetype,
    AgentSpec,
    ToolPermissions,
    get_agent_spec,
    list_agent_specs,
    load_agent_spec,
    sync_agent_definitions,
)
from harness.subagents.scaffold import (
    inspect_workspace_context,
    scaffold_agent_markdown,
)
from harness.subagents.validator import validate_agent_spec
from harness.subagents.context import (
    SubagentContextStatus,
    classify_context_health,
    estimate_subagent_context,
    extract_role_from_text,
    list_active_subagent_statuses,
)
from harness.subagents.rehydrate import (
    StepSummary,
    rehydrate_subagent_session,
)

__all__ = [
    "DEFAULT_AGENTS_DIR",
    "DEFAULT_TARGET_DIR",
    "REPO_ROOT",
    "ANTIGRAVITY_PLATFORM_TOOLS",
    "CAPABILITY_BUNDLES",
    "AgentArchetype",
    "AgentSpec",
    "ToolPermissions",
    "get_agent_spec",
    "list_agent_specs",
    "load_agent_spec",
    "sync_agent_definitions",
    "inspect_workspace_context",
    "scaffold_agent_markdown",
    "validate_agent_spec",
    "SubagentContextStatus",
    "classify_context_health",
    "estimate_subagent_context",
    "extract_role_from_text",
    "list_active_subagent_statuses",
    "StepSummary",
    "rehydrate_subagent_session",
]
