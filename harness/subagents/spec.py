# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Purrfect Software Limited (PSL)

"""
Specialist subagent data models, archetypes, and spec loader (ADR-014).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
import json
import os
from pathlib import Path
import shutil
from typing import Any, Dict, List, Optional

from harness.utils.frontmatter import parse_frontmatter

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
DEFAULT_AGENTS_DIR = Path(__file__).resolve().parent.parent / "agents"
DEFAULT_TARGET_DIR = REPO_ROOT / ".agents" / "agents"


class AgentArchetype(str, Enum):
    """Specialist subagent archetypes in the Subagent Ladder protocol."""

    EXECUTIONER = "executioner"
    HAMMER = "hammer"
    AUDITOR = "auditor"
    PLANNER = "planner"
    COORDINATOR = "coordinator"
    MAIN = "main"
    CUSTODIAN = "custodian"

    @classmethod
    def from_string(cls, val: str) -> AgentArchetype:
        """Parse string to archetype enum safely."""
        norm = val.strip().lower().replace("-", "_")
        for member in cls:
            if member.value == norm or member.name.lower() == norm:
                return member
        # Fallback aliases
        if norm in ("main", "psl_main", "lead", "general", "default"):
            return cls.MAIN
        elif norm in ("builder", "worker", "implementer", "executioner"):
            return cls.EXECUTIONER
        elif norm in ("reviewer", "inspector", "hammer"):
            return cls.HAMMER
        elif norm in ("qa", "verifier", "qa_verifier", "auditor"):
            return cls.AUDITOR
        elif norm in ("planner", "architect", "designer", "researcher"):
            return cls.PLANNER
        elif norm in ("coordinator", "orchestrator", "swarm_lead"):
            return cls.COORDINATOR
        elif norm in ("custodian", "harness_custodian", "git_custodian", "commit_gate", "subagent_x_custodian"):
            return cls.CUSTODIAN
        raise ValueError(f"Unknown AgentArchetype: {val}")


ANTIGRAVITY_PLATFORM_TOOLS: frozenset[str] = frozenset({
    "view_file",
    "list_dir",
    "grep_search",
    "find_by_name",
    "write_to_file",
    "replace_file_content",
    "run_command",
    "manage_task",
    "invoke_subagent",
    "send_message",
    "manage_subagents",
    "define_subagent",
    "schedule",
    "generate_image",
    "read_url_content",
    "search_web",
    "ask_question",
})

CAPABILITY_BUNDLES: Dict[str, List[str]] = {
    "read_only": [
        "view_file",
        "list_dir",
        "grep_search",
        "find_by_name",
        "read_url_content",
        "search_web",
    ],
    "verifier": [
        "view_file",
        "list_dir",
        "grep_search",
        "find_by_name",
        "read_url_content",
        "search_web",
        "run_command",
        "manage_task",
    ],
    "adversarial_verifier": [
        "view_file",
        "list_dir",
        "grep_search",
        "find_by_name",
        "read_url_content",
        "search_web",
        "run_command",
        "manage_task",
        "write_to_file",
        "replace_file_content",
    ],
    "builder": [
        "view_file",
        "list_dir",
        "grep_search",
        "find_by_name",
        "read_url_content",
        "search_web",
        "run_command",
        "manage_task",
        "write_to_file",
        "replace_file_content",
    ],
    "orchestrator": [
        "view_file",
        "list_dir",
        "grep_search",
        "find_by_name",
        "read_url_content",
        "search_web",
        "invoke_subagent",
        "send_message",
        "manage_subagents",
        "manage_task",
        "ask_question",
    ],
    "full": [
        "view_file",
        "list_dir",
        "grep_search",
        "find_by_name",
        "write_to_file",
        "replace_file_content",
        "run_command",
        "manage_task",
        "invoke_subagent",
        "send_message",
        "manage_subagents",
        "define_subagent",
        "schedule",
        "generate_image",
        "read_url_content",
        "search_web",
        "ask_question",
    ],
}


@dataclass(frozen=True)
class ToolPermissions:
    """Tool group permissions for specialist subagents."""

    read: bool = True
    write: bool = False
    execute: bool = False
    subagent: bool = False
    mcp: bool = False
    enable_write_tools: bool = False

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> ToolPermissions:
        """Construct permissions from frontmatter dictionary."""
        subagent = bool(data.get("subagent", data.get("subagents", False)))
        return cls(
            read=bool(data.get("read", True)),
            write=bool(data.get("write", False)),
            execute=bool(data.get("execute", False)),
            subagent=subagent,
            mcp=bool(data.get("mcp", False)),
            enable_write_tools=bool(data.get("enable_write_tools", False)),
        )


@dataclass(frozen=True)
class AgentSpec:
    """Specification and system prompt contract for a specialist subagent."""

    name: str
    archetype: AgentArchetype
    description: str
    role: str
    system_prompt: str
    permissions: ToolPermissions
    allowed_tools: List[str] = field(default_factory=list)
    tools: List[str] = field(default_factory=list)
    subagent: bool = True
    main_agent: bool = True
    inherit_customizations: bool = True
    model: str = "inherit"
    source_file: Optional[Path] = None

    @property
    def can_write(self) -> bool:
        """Whether the agent has file modification permissions."""
        return self.permissions.write

    @property
    def can_execute(self) -> bool:
        """Whether the agent has command execution permissions."""
        return self.permissions.execute

    @property
    def can_subagent(self) -> bool:
        """Whether the agent can spawn nested subagents."""
        return self.permissions.subagent

    @property
    def can_mcp(self) -> bool:
        """Whether the agent has MCP server access."""
        return self.permissions.mcp


def load_agent_spec(file_path: Path) -> AgentSpec:
    """Parse a single agent markdown definition file into an AgentSpec."""
    content = file_path.read_text(encoding="utf-8", errors="replace")
    fm, prompt = parse_frontmatter(content)

    name = str(fm.get("name", file_path.stem))
    raw_arch = str(fm.get("archetype", "executioner"))
    archetype = AgentArchetype.from_string(raw_arch)
    desc = str(fm.get("description", ""))
    role = str(fm.get("role", archetype.value.capitalize()))

    raw_perms = fm.get("permissions", {})
    if isinstance(raw_perms, dict):
        permissions = ToolPermissions.from_dict(raw_perms)
    else:
        permissions = ToolPermissions()

    raw_tools = fm.get("tools")
    raw_allowed = fm.get("allowed_tools")
    tools_list: List[str] = []
    if isinstance(raw_tools, list):
        tools_list = [str(t) for t in raw_tools]
    elif isinstance(raw_tools, str):
        tools_list = [t.strip().strip("'\"") for t in raw_tools.strip("[]").split(",") if t.strip()]

    allowed_list: List[str] = []
    if isinstance(raw_allowed, list):
        allowed_list = [str(t) for t in raw_allowed]
    elif isinstance(raw_allowed, str):
        allowed_list = [t.strip().strip("'\"") for t in raw_allowed.strip("[]").split(",") if t.strip()]

    if not tools_list and allowed_list:
        tools_list = list(allowed_list)
    if not allowed_list and tools_list:
        allowed_list = list(tools_list)

    subagent = bool(fm.get("subagent", True))
    main_agent = bool(fm.get("mainAgent", fm.get("main_agent", True)))
    raw_inherit = fm.get("inheritCustomizations", fm.get("inherit_customizations", True))
    if isinstance(raw_inherit, str):
        inherit_customizations = raw_inherit.strip().lower() not in ("false", "0", "no")
    elif raw_inherit is None:
        inherit_customizations = True
    else:
        inherit_customizations = bool(raw_inherit)
    model = str(fm.get("model", "inherit"))

    return AgentSpec(
        name=name,
        archetype=archetype,
        description=desc,
        role=role,
        system_prompt=prompt.strip(),
        permissions=permissions,
        allowed_tools=allowed_list,
        tools=tools_list,
        subagent=subagent,
        main_agent=main_agent,
        inherit_customizations=inherit_customizations,
        model=model,
        source_file=file_path,
    )


def list_agent_specs(agents_dir: Optional[Path] = None) -> List[AgentSpec]:
    """Scan and list all specialist agent specifications in directory."""
    src = agents_dir or DEFAULT_AGENTS_DIR
    if not src.exists() or not src.is_dir():
        return []

    specs: List[AgentSpec] = []
    for item in sorted(src.glob("*.md")):
        if item.is_file():
            specs.append(load_agent_spec(item))

    return specs


def get_agent_spec(
    name: str, agents_dir: Optional[Path] = None
) -> Optional[AgentSpec]:
    """Retrieve an agent specification by name, stem, or archetype alias."""
    norm = name.strip().lower().replace("-", "_")
    target_arch: Optional[AgentArchetype] = None
    try:
        target_arch = AgentArchetype.from_string(norm)
    except ValueError:
        target_arch = None

    for spec in list_agent_specs(agents_dir):
        if (
            spec.name.lower().replace("-", "_") == norm
            or (spec.source_file and spec.source_file.stem.lower().replace("-", "_") == norm)
            or spec.archetype.value == norm
            or (target_arch is not None and spec.archetype == target_arch)
            or norm in spec.name.lower()
        ):
            return spec
    return None


def sync_agent_definitions(
    target_dir: Optional[Path] = None,
    source_dir: Optional[Path] = None,
    agent_names: Optional[List[str]] = None,
    dedup: bool = True,
    override: bool = False,
) -> List[Path]:
    """Synchronize agent definitions from harness/agents to .agents/agents."""
    from harness.delivery import find_workspace_root

    src = source_dir or DEFAULT_AGENTS_DIR
    if target_dir is not None:
        dst = Path(target_dir)
    else:
        ws_root = find_workspace_root()
        if ws_root.resolve() == REPO_ROOT.resolve():
            dst = DEFAULT_TARGET_DIR
        else:
            dst = ws_root / ".agents" / "agents"
    dst.mkdir(parents=True, exist_ok=True)

    synced: List[Path] = []
    norm_filter = (
        {a.strip().lower().replace("_", "-") for a in agent_names}
        if agent_names is not None
        else None
    )

    for spec in list_agent_specs(src):
        if not (spec.source_file and spec.source_file.exists()):
            continue

        name_norm = spec.name.lower().replace("_", "-")
        stem_norm = spec.source_file.stem.lower().replace("_", "-")
        arch_norm = spec.archetype.value.lower().replace("_", "-")
        if (
            norm_filter is not None
            and name_norm not in norm_filter
            and stem_norm not in norm_filter
            and arch_norm not in norm_filter
        ):
            continue

        dest_file = dst / spec.source_file.name

        if dest_file.exists() and not override:
            is_identical = dest_file.read_bytes() == spec.source_file.read_bytes()
            if dedup and is_identical:
                continue
            continue

        shutil.copy2(spec.source_file, dest_file)
        synced.append(dest_file)

    return synced

