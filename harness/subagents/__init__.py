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
from harness.subagents.liveness import (
    SubagentLivenessStatus,
    probe_subagent_liveness,
)
from harness.subagents.rehydrate import (
    StepSummary,
    rehydrate_subagent_session,
)
from harness.subagents.stage_role import (
    STAGE_NAME_MAP,
    STAGE_ROLE_MAP,
    clear_stage_role,
    materialize_stage_role,
    read_stage_role,
    validate_stage_role_schema,
)
from harness.subagents.heartbeat import (
    LADDER_HEARTBEAT_PATH,
    VALID_STAGES,
    VALID_STATUSES,
    arm_stage_heartbeat,
    clear_stage_heartbeat,
    disarm_stage_heartbeat,
    pulse_stage_heartbeat,
    read_stage_heartbeat,
    validate_heartbeat_schema,
)
from harness.subagents.succession import (
    build_custody_transfer_payload,
    build_succession_prompt,
    resolve_self_alias,
    scaffold_successor_generation,
)
from harness.subagents.routing import (
    CANONICAL_ROUTES,
    WorkflowMode,
    WorkflowRoute,
    build_stage_transition_payload,
    format_route_briefing,
    get_route,
    list_routes,
    validate_stage_transition_payload,
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
    "SubagentLivenessStatus",
    "probe_subagent_liveness",
    "StepSummary",
    "rehydrate_subagent_session",
    "STAGE_NAME_MAP",
    "STAGE_ROLE_MAP",
    "clear_stage_role",
    "materialize_stage_role",
    "read_stage_role",
    "validate_stage_role_schema",
    "LADDER_HEARTBEAT_PATH",
    "VALID_STAGES",
    "VALID_STATUSES",
    "arm_stage_heartbeat",
    "clear_stage_heartbeat",
    "disarm_stage_heartbeat",
    "pulse_stage_heartbeat",
    "read_stage_heartbeat",
    "validate_heartbeat_schema",
    "resolve_self_alias",
    "build_succession_prompt",
    "build_custody_transfer_payload",
    "scaffold_successor_generation",
    "CANONICAL_ROUTES",
    "WorkflowMode",
    "WorkflowRoute",
    "build_stage_transition_payload",
    "format_route_briefing",
    "get_route",
    "list_routes",
    "validate_stage_transition_payload",
]

