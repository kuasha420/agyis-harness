# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Purrfect Software Limited (PSL)

"""
Specialist subagent definition validation (ADR-014).
"""

from __future__ import annotations

from pathlib import Path
from typing import List

from harness.utils.frontmatter import parse_frontmatter
from harness.subagents.spec import (
    ANTIGRAVITY_PLATFORM_TOOLS,
    AgentArchetype,
    ToolPermissions,
)


def validate_agent_spec(file_path: Path | str) -> List[str]:
    """
    Validates agent definition file:
    - Parses YAML frontmatter
    - Asserts tool names exist in ANTIGRAVITY_PLATFORM_TOOLS to prevent platform hanging bug
    - Flags contradictions (e.g. write tools listed when write: false)
    - Verifies prompt invariants (Zero-Exploration Invariant)
    """
    errors: List[str] = []
    p = Path(file_path)
    if not p.is_file():
        return [f"File not found: {p}"]

    try:
        content = p.read_text(encoding="utf-8", errors="replace")
    except OSError as exc:
        return [f"Cannot read file {p}: {exc}"]

    if not content.startswith("---"):
        return ["Missing YAML frontmatter (must start with '---')"]

    try:
        fm, prompt = parse_frontmatter(content)
    except Exception as exc:
        return [f"Failed to parse frontmatter: {exc}"]

    if not fm:
        return ["Empty or invalid YAML frontmatter"]

    # Validate name
    name = str(fm.get("name", "")).strip()
    if not name:
        errors.append("Missing required field 'name'")

    # Validate archetype
    raw_arch = fm.get("archetype")
    if not raw_arch:
        errors.append("Missing required field 'archetype'")
    else:
        try:
            AgentArchetype.from_string(str(raw_arch))
        except ValueError:
            valid_archs = [a.value for a in AgentArchetype]
            errors.append(f"Invalid archetype '{raw_arch}'. Expected one of: {valid_archs}")

    # Validate inheritCustomizations
    for key in ("inheritCustomizations", "inherit_customizations"):
        if key in fm:
            val = fm[key]
            if not isinstance(val, bool) and not (
                isinstance(val, str) and val.strip().lower() in ("true", "false")
            ):
                errors.append(f"Field '{key}' must be a boolean (true or false)")

    # Validate permissions
    raw_perms = fm.get("permissions", {})
    if isinstance(raw_perms, dict):
        perms = ToolPermissions.from_dict(raw_perms)
    else:
        perms = ToolPermissions()

    # Tools extraction
    raw_tools = fm.get("tools")
    raw_allowed = fm.get("allowed_tools")
    declared_tools: List[str] = []
    if isinstance(raw_tools, list):
        declared_tools.extend([str(t) for t in raw_tools])
    if isinstance(raw_allowed, list):
        for t in raw_allowed:
            st = str(t)
            if st not in declared_tools:
                declared_tools.append(st)

    if not declared_tools:
        errors.append("Agent must declare at least one tool in 'tools' or 'allowed_tools'")

    for tool in declared_tools:
        if tool in ("call_mcp_tool", "list_resources", "read_resource"):
            errors.append(
                f"Invalid tool '{tool}': MCP tools (call_mcp_tool, list_resources, read_resource) cannot be listed "
                "in 'tools' or 'allowed_tools'. Enable MCP via 'permissions: {mcp: true}' and 'inheritCustomizations: true' "
                "instead. Listing MCP tools statically causes Antigravity executor resolution to crash."
            )
        elif tool not in ANTIGRAVITY_PLATFORM_TOOLS:
            errors.append(
                f"Unknown tool '{tool}' not recognized in ANTIGRAVITY_PLATFORM_TOOLS. "
                "Non-existent tools cause Antigravity subagent sessions to hang indefinitely."
            )

    # Contradiction checks
    if not perms.write:
        write_tools = [t for t in declared_tools if t in ("write_to_file", "replace_file_content", "edit_file")]
        if write_tools:
            errors.append(
                f"Contradiction: agent has 'write: false' in permissions, but declares file mutation tools: {write_tools}"
            )

    if not perms.execute:
        exec_tools = [t for t in declared_tools if t in ("run_command",)]
        if exec_tools:
            errors.append(
                f"Contradiction: agent has 'execute: false' in permissions, but declares execution tools: {exec_tools}"
            )

    if not perms.subagent:
        sub_tools = [t for t in declared_tools if t in ("invoke_subagent", "manage_subagents", "define_subagent")]
        if sub_tools:
            errors.append(
                f"Contradiction: agent has 'subagent: false' in permissions, but declares subagent tools: {sub_tools}"
            )

    # Prompt validation
    if not prompt or not prompt.strip():
        errors.append("System prompt body cannot be empty")
    else:
        has_sweep_invariant = (
            "Zero-Exploration Invariant" in prompt
            or "Targeted Macro & Deduplication Sweep Invariant" in prompt
        )
        if not has_sweep_invariant:
            errors.append(
                "System prompt must declare 'Zero-Exploration Invariant' or 'Targeted Macro & Deduplication Sweep Invariant'"
            )
        if "list_dir" not in prompt or "find_by_name" not in prompt:
            errors.append("System prompt exploration invariant must explicitly reference 'list_dir' and 'find_by_name'")

    return errors
