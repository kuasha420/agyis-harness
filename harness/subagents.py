"""
PSL Specialist Subagents Registry & Scaffold.

Defines programmatic schemas and registry loader for specialized subagents:
- Executioner (Builder): write-enabled implementer
- Hammer (Reviewer): read-only auditor
- Auditor (QA Verifier): test-execution auditor with zero edit permissions
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
import shutil
from typing import Any, Dict, List, Optional

from harness.skills import parse_frontmatter

REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_AGENTS_DIR = Path(__file__).resolve().parent / "agents"
DEFAULT_TARGET_DIR = REPO_ROOT / ".agents" / "agents"


class AgentArchetype(str, Enum):
    """Specialist subagent archetypes in the Subagent Ladder protocol."""

    EXECUTIONER = "executioner"
    HAMMER = "hammer"
    AUDITOR = "auditor"

    @classmethod
    def from_string(cls, val: str) -> AgentArchetype:
        """Parse string to archetype enum safely."""
        norm = val.strip().lower().replace("-", "_")
        for member in cls:
            if member.value == norm or member.name.lower() == norm:
                return member
        # Fallback aliases
        if norm in ("builder", "worker", "implementer"):
            return cls.EXECUTIONER
        elif norm in ("reviewer", "inspector"):
            return cls.HAMMER
        elif norm in ("qa", "verifier", "qa_verifier"):
            return cls.AUDITOR
        raise ValueError(f"Unknown AgentArchetype: {val}")


@dataclass(frozen=True)
class ToolPermissions:
    """Tool group permissions for specialist subagents."""

    read: bool = True
    write: bool = False
    execute: bool = False
    subagent: bool = False
    mcp: bool = False

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

    raw_tools = fm.get("allowed_tools", [])
    allowed_tools = [str(t) for t in raw_tools] if isinstance(raw_tools, list) else []

    return AgentSpec(
        name=name,
        archetype=archetype,
        description=desc,
        role=role,
        system_prompt=prompt.strip(),
        permissions=permissions,
        allowed_tools=allowed_tools,
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
    target_dir: Optional[Path] = None, source_dir: Optional[Path] = None
) -> List[Path]:
    """Synchronize agent definitions from harness/agents to .agents/agents."""
    src = source_dir or DEFAULT_AGENTS_DIR
    dst = target_dir or DEFAULT_TARGET_DIR
    dst.mkdir(parents=True, exist_ok=True)

    synced: List[Path] = []
    for spec in list_agent_specs(src):
        if spec.source_file and spec.source_file.exists():
            dest_file = dst / spec.source_file.name
            shutil.copy2(spec.source_file, dest_file)
            synced.append(dest_file)

    return synced
