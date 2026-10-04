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
import json
import os
from pathlib import Path
import re
import shutil
import time
from typing import Any, Dict, List, Optional, Tuple

from harness.skills import parse_frontmatter

REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_AGENTS_DIR = Path(__file__).resolve().parent / "agents"
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
        elif norm in ("custodian", "git_custodian", "commit_gate", "subagent_x_custodian"):
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


def inspect_workspace_context(repo_root: Optional[Path] = None) -> Dict[str, Any]:
    """
    Scans root project files (package.json, pyproject.toml, Cargo.toml, AGENTS.md, matrix.json, roadmap.md)
    to extract project name, languages, test runners, commands, and active rules.
    """
    root = repo_root or REPO_ROOT
    project_name = root.name
    languages: List[str] = []
    test_runners: List[str] = []
    commands: List[str] = []
    rules: List[str] = []
    detected_files: List[str] = []

    # 1. pyproject.toml
    pyproject = root / "pyproject.toml"
    if pyproject.is_file():
        detected_files.append("pyproject.toml")
        if "Python" not in languages:
            languages.append("Python")
        try:
            content = pyproject.read_text(encoding="utf-8", errors="replace")
            m_name = re.search(r'name\s*=\s*["\']([^"\']+)["\']', content)
            if m_name and m_name.group(1):
                project_name = m_name.group(1).strip()
            if "pytest" in content and "pytest" not in test_runners:
                test_runners.append("pytest")
            for script_m in re.finditer(r'([a-zA-Z0-9_-]+)\s*=\s*["\']([^"\']+)["\']', content):
                sc_name = script_m.group(1)
                if sc_name not in ("name", "version", "description", "readme", "requires-python", "license", "authors"):
                    if sc_name not in commands:
                        commands.append(sc_name)
        except OSError:
            pass

    # 2. package.json
    pkg_json = root / "package.json"
    if pkg_json.is_file():
        detected_files.append("package.json")
        try:
            data = json.loads(pkg_json.read_text(encoding="utf-8", errors="replace"))
            if isinstance(data, dict):
                if data.get("name") and (project_name == root.name or not project_name):
                    project_name = str(data["name"])
                deps = {**data.get("dependencies", {}), **data.get("devDependencies", {})}
                if "typescript" in deps or (root / "tsconfig.json").is_file():
                    if "TypeScript" not in languages:
                        languages.append("TypeScript")
                else:
                    if "JavaScript" not in languages:
                        languages.append("JavaScript")
                scripts = data.get("scripts", {})
                if isinstance(scripts, dict):
                    if "test" in scripts:
                        t_cmd = str(scripts["test"])
                        if t_cmd not in test_runners:
                            test_runners.append(t_cmd)
                    for k in scripts:
                        if k not in commands:
                            commands.append(k)
        except (json.JSONDecodeError, OSError):
            pass

    # 3. Cargo.toml
    cargo = root / "Cargo.toml"
    if cargo.is_file():
        detected_files.append("Cargo.toml")
        if "Rust" not in languages:
            languages.append("Rust")
        try:
            content = cargo.read_text(encoding="utf-8", errors="replace")
            m_name = re.search(r'name\s*=\s*["\']([^"\']+)["\']', content)
            if m_name and (project_name == root.name or not project_name):
                project_name = m_name.group(1).strip()
            if "cargo test" not in test_runners:
                test_runners.append("cargo test")
            if "cargo" not in commands:
                commands.append("cargo")
        except OSError:
            pass

    # 4. AGENTS.md
    agents_md = root / "AGENTS.md"
    if agents_md.is_file():
        detected_files.append("AGENTS.md")
        try:
            content = agents_md.read_text(encoding="utf-8", errors="replace")
            for line in content.splitlines():
                s = line.strip()
                if (s.startswith("- ") or re.match(r"^\d+\.\s+", s)) and len(s) > 5:
                    clean_rule = re.sub(r"^[-*\d.]+\s+", "", s).strip()
                    if clean_rule and clean_rule not in rules:
                        rules.append(clean_rule)
        except OSError:
            pass

    # 5. matrix.json
    matrix = root / "matrix.json"
    if matrix.is_file():
        detected_files.append("matrix.json")
        try:
            m_data = json.loads(matrix.read_text(encoding="utf-8", errors="replace"))
            if isinstance(m_data, dict):
                for k, v in m_data.items():
                    if isinstance(v, (str, list, dict)):
                        rule_summary = f"{k}: {v}" if isinstance(v, str) else k
                        if rule_summary not in rules:
                            rules.append(rule_summary)
        except (json.JSONDecodeError, OSError):
            pass

    # 6. roadmap.md
    roadmap = root / "roadmap.md"
    if roadmap.is_file():
        detected_files.append("roadmap.md")
        try:
            content = roadmap.read_text(encoding="utf-8", errors="replace")
            for line in content.splitlines():
                s = line.strip()
                if s.startswith("## ") or s.startswith("### "):
                    heading = s.lstrip("#").strip()
                    if heading and heading not in rules:
                        rules.append(f"Roadmap: {heading}")
        except OSError:
            pass

    return {
        "project_name": project_name,
        "languages": languages,
        "test_runners": test_runners,
        "commands": commands,
        "rules": rules,
        "detected_files": detected_files,
    }


def scaffold_agent_markdown(
    name: str,
    archetype: AgentArchetype | str,
    description: Optional[str] = None,
    role: Optional[str] = None,
    bundle: Optional[str] = None,
    tools: Optional[List[str]] = None,
    model: str = "inherit",
    subagent: bool = True,
    main_agent: bool = True,
    inherit_customizations: bool = True,
    permissions: Optional[ToolPermissions | Dict[str, Any]] = None,
    skills: Optional[List[str]] = None,
    workspace_context: Optional[Dict[str, Any]] = None,
    custom_instructions: Optional[str] = None,
) -> str:
    """
    Generates complete Markdown file with valid YAML frontmatter and structured
    system prompt with hybrid workspace grounding.
    """
    if isinstance(archetype, str):
        arch = AgentArchetype.from_string(archetype)
    else:
        arch = archetype

    # Determine bundle and tools
    resolved_bundle = bundle
    if resolved_bundle is None and tools is None:
        if arch == AgentArchetype.MAIN:
            resolved_bundle = "full"
        elif arch == AgentArchetype.EXECUTIONER:
            resolved_bundle = "builder"
        elif arch == AgentArchetype.AUDITOR:
            resolved_bundle = "verifier"
        elif arch == AgentArchetype.CUSTODIAN:
            resolved_bundle = "verifier"
        elif arch == AgentArchetype.COORDINATOR:
            resolved_bundle = "orchestrator"
        elif arch == AgentArchetype.PLANNER:
            tools = [
                "view_file",
                "list_dir",
                "grep_search",
                "find_by_name",
                "read_url_content",
                "search_web",
                "manage_task",
                "write_to_file",
                "ask_question",
                "invoke_subagent",
                "send_message",
                "manage_subagents",
            ]
        else:
            resolved_bundle = "read_only"

    if tools is None:
        tools = list(CAPABILITY_BUNDLES.get(resolved_bundle or "read_only", CAPABILITY_BUNDLES["read_only"]))

    # Derive role if not provided
    if not role:
        if arch == AgentArchetype.MAIN:
            role = "PSL Lead Architect & Master Implementer"
        elif arch == AgentArchetype.EXECUTIONER:
            role = "Executioner (Worker / Implementer)"
        elif arch == AgentArchetype.HAMMER:
            role = "Hammer (Ruthless Reviewer / Auditor)"
        elif arch == AgentArchetype.AUDITOR:
            role = "QA Verifier (Hermetic Benchmark Auditor)"
        elif arch == AgentArchetype.CUSTODIAN:
            role = "Custodian (Macro Reviewer, Deduplication & Git Commit Gate)"
        elif arch == AgentArchetype.PLANNER:
            role = "Software Architect & Solution Planner"
        elif arch == AgentArchetype.COORDINATOR:
            role = "Swarm Coordinator & Multi-Agent Lead"
        else:
            role = f"{arch.value.capitalize()} Specialist"

    # Derive description if not provided
    if not description:
        if arch == AgentArchetype.MAIN:
            description = (
                "PSL lead architect, systems engineer, and master implementer "
                "with full tool capabilities, complete customization inheritance, "
                "and verified operational discipline."
            )
        elif arch == AgentArchetype.EXECUTIONER:
            description = "Surgical single-phase task execution following an approved implementation plan."
        elif arch == AgentArchetype.HAMMER:
            description = "Delta-focused code review against the 5 Ground Rules and stack invariants."
        elif arch == AgentArchetype.AUDITOR:
            description = "Hermetic verification, doctor audit, and sub-second test suite benchmarking."
        elif arch == AgentArchetype.CUSTODIAN:
            description = (
                "Macro architectural review, DRY code deduplication audit, "
                "workspace hygiene, and atomic git commit gate."
            )
        elif arch == AgentArchetype.PLANNER:
            description = "Architectural research, dependency analysis, and artifact-first implementation plan synthesis."
        elif arch == AgentArchetype.COORDINATOR:
            description = "Multi-agent swarm orchestration, milestone decomposition, and project ledger governance."
        else:
            description = f"Specialized {arch.value} agent for codebase tasks."

    # Derive permissions
    if permissions is None:
        if arch == AgentArchetype.MAIN:
            perms = ToolPermissions(
                read=True,
                write=True,
                execute=True,
                subagent=True,
                mcp=True,
                enable_write_tools=True,
            )
        else:
            can_w = any(t in tools for t in ("write_to_file", "replace_file_content", "edit_file"))
            can_e = any(t in tools for t in ("run_command",))
            can_s = any(t in tools for t in ("invoke_subagent", "manage_subagents", "define_subagent")) or arch == AgentArchetype.COORDINATOR
            can_m = arch in (AgentArchetype.PLANNER, AgentArchetype.MAIN) or bool(skills)
            enable_w = arch in (AgentArchetype.EXECUTIONER, AgentArchetype.AUDITOR, AgentArchetype.CUSTODIAN) or can_w
            perms = ToolPermissions(
                read=True,
                write=can_w,
                execute=can_e,
                subagent=can_s,
                mcp=can_m,
                enable_write_tools=enable_w,
            )
    elif isinstance(permissions, dict):
        perms = ToolPermissions.from_dict(permissions)
    else:
        perms = permissions

    # Build frontmatter
    fm_lines = [
        "---",
        f"name: {name}",
        f"archetype: {arch.value}",
        f"description: {description}",
        f"role: {role}",
        f"subagent: {'true' if subagent else 'false'}",
        f"mainAgent: {'true' if main_agent else 'false'}",
        f"inheritCustomizations: {'true' if inherit_customizations else 'false'}",
        f"model: {model}",
        "permissions:",
        f"  read: {'true' if perms.read else 'false'}",
        f"  write: {'true' if perms.write else 'false'}",
        f"  execute: {'true' if perms.execute else 'false'}",
        f"  subagents: {'true' if perms.subagent else 'false'}",
        f"  mcp: {'true' if perms.mcp else 'false'}",
    ]
    if perms.enable_write_tools:
        fm_lines.append("  enable_write_tools: true")

    if skills:
        fm_lines.append("skills:")
        for s in skills:
            fm_lines.append(f"  - {s}")

    fm_lines.append("tools:")
    for t in tools:
        fm_lines.append(f"  - {t}")

    fm_lines.append("allowed_tools:")
    for t in tools:
        fm_lines.append(f"  - {t}")

    fm_lines.append("---")
    frontmatter_str = "\n".join(fm_lines)

    # Build system prompt body with hybrid grounding
    body_lines = [
        f"# {role}",
        "",
        f"You are `{name}`, the dedicated {role} in the PSL Subagent Ladder protocol.",
        "",
    ]

    # Hybrid workspace grounding
    ws = workspace_context
    if ws:
        body_lines.append("## Workspace Context")
        if ws.get("project_name"):
            body_lines.append(f"- **Project**: {ws['project_name']}")
        if ws.get("languages"):
            body_lines.append(f"- **Languages**: {', '.join(ws['languages'])}")
        if ws.get("test_runners"):
            body_lines.append(f"- **Test Runner**: {', '.join(ws['test_runners'])}")
        if ws.get("commands"):
            body_lines.append(f"- **Key Commands**: {', '.join(ws['commands'][:6])}")
        if ws.get("rules"):
            body_lines.append("- **Project Rules**:")
            for r in ws["rules"][:5]:
                body_lines.append(f"  • {r}")
        body_lines.append("")

    # Operational Invariants
    body_lines.append("## Operational Invariants")
    if arch == AgentArchetype.MAIN:
        body_lines.append("1. **Lead Architecture & Governance**:")
        body_lines.append("   - Act as lead architect, systems engineer, and master implementer with end-to-end accountability.")
        body_lines.append("   - Enforce system invariants, clean-room testing, and bounded execution scopes across all tasks.")
    elif arch == AgentArchetype.EXECUTIONER:
        body_lines.append("1. **Plan Adherence**: Read the approved implementation plan before making edits. Implement ONLY tasks specified in the plan. Zero speculative expansions.")
    elif arch == AgentArchetype.HAMMER:
        body_lines.append("1. **Delta Focus**: Inspect ONLY modified files and contiguous diff lines (`git diff -U3`). Do not re-read entire repositories.")
    elif arch == AgentArchetype.AUDITOR:
        body_lines.append("1. **Hermetic Verification**: Execute test suites, doctor audits, and runtime linters to establish deterministic ground truth.")
    elif arch == AgentArchetype.CUSTODIAN:
        body_lines.extend([
            "1. **Macro Review & Deduplication Mandate**:",
            "   - **DRY & Code Deduplication Audit**: Before approving any commit gate, actively search the repository (`grep_search`, `find_by_name`) to ensure newly introduced helpers, utilities, constants, and test mocks do NOT duplicate existing logic elsewhere in the codebase. If duplicate logic is found, reject the commit gate with a DRY defect report instructing Executioner to reuse existing modules.",
            "   - **Macro Architectural Review**: Evaluate repository-wide architectural integrity beyond Hammer's micro-diff: verify cross-module boundary compliance (e.g. ADR-014 Product vs. Project bifurcation: `harness/` must never import `pipeline/`), detect orphan files, dead code, leftover temporary scripts, and uncommitted working-tree residue.",
            "   - **Git Commit Gate**: Verify clean porcelain tree status (`git status --porcelain`), stage strictly intended deliverables (never blind `git add .` or `git add -A`), and seal an atomic conventional commit on HEAD so Stage 5 Auditor audits an immutable revision.",
        ])
    elif arch == AgentArchetype.PLANNER:
        body_lines.append("1. **Artifact-First Planning (ADR-012)**: Synthesize codebase research and architecture analysis into interactive `implementation_plan.md` artifacts. You can write to exempt artifact paths for synthesis, but cannot mutate product code directly.")
    elif arch == AgentArchetype.COORDINATOR:
        body_lines.append("1. **Swarm Orchestration**: Decompose milestones into single-phase tasks, delegate to specialist subagents, and govern the project ledger.")

    body_lines.extend([
        "2. **The 5 Ground Rules**:",
        "   - **Rule 1 (Zero Error Swallowing)**: Never hide or swallow errors. Zero bare `except:`, no unhandled pipe errors.",
        "   - **Rule 2 (No Product Homework in Tests)**: Never redefine product logic or duplicate production calculations in test asserts.",
        "   - **Rule 3 (Complete Deliveries)**: Deliver complete packages (code + types + tests + docs). No partial drafts.",
        "   - **Rule 4 (Zero Verification Homework)**: Self-verify all changes using the project test suite.",
        "   - **Rule 5 (Stop & Inquire)**: Stop and ask if an unforeseen blocker, architectural conflict, or ambiguity arises.",
    ])

    if arch == AgentArchetype.MAIN:
        body_lines.extend([
            "3. **Explicit Command Dictionary (The Victory Pattern)**:",
            "   - `python3 -m harness.cli test`: Run complete hermetic test suite (sub-second benchmark invariant).",
            "   - `python3 -m harness.cli doctor`: Audit host workstation runtimes and auto-heal environment.",
            "   - `python3 -m harness.cli status`: Display harness health, active hooks, and telemetry gauge.",
            "   - `./psl sync`: Audit and synchronize active session into telemetry.db.",
            "4. **Architectural Decisions & Standards**:",
            "   - **ADR-012 (Artifact-First Planning)**: Never propose multi-component changes in raw chat. Crystallize into interactive `implementation_plan.md` artifacts before execution.",
            "   - **ADR-013 (Terminal Invariants & Pattern Probing)**: Always use `set -euo pipefail`. Pattern probes (`grep`, `diff`) without conditionals must append `|| [ $? -eq 1 ]`. Pre-flight test tools with `command -v`.",
            "   - **ADR-014 (Product vs. Project Bifurcation)**: Distributable plugin and CLI toolchain live in `harness/`; pipeline scripts, test suites, and telemetry data live in `pipeline/`, `tests/`, and `data/`.",
            "   - **ADR-015 (Clean-Room Testing)**: All verification must be hermetic and execute strictly in <1.0s benchmark runtime.",
            "5. **Subagent Delegation Ladder Protocol**:",
            "   - Decompose multi-phase tasks and delegate using native `@<subagent>` syntax (e.g., `@harness_builder`, `@harness_reviewer`, `@harness_auditor`, `@planner`, `@coordinator`).",
            "   - Follow the Ladder lifecycle: Plan -> Implement (Builder) -> Review (Reviewer) -> Audit (Auditor).",
            "6. **Toolgroup Capabilities**:",
            f"   - Full capability bundle enabled: {', '.join(tools)}.",
            "7. **Stack Invariants**:",
            "   - Python: Hermetic CPython 3.12, no bare except, clean tempfile state.",
            "   - Shell: `set -euo pipefail`, ADR-013 pattern probing exit exception (`|| [ $? -eq 1 ]`).",
            "8. **Zero-Exploration Invariant**:",
            "   - Prohibit blind `list_dir` / `find_by_name` sweeps across the repository. Open target files directly from instructions, or communicate back and halt immediately.",
        ])
    else:
        # Toolgroup restrictions
        body_lines.append("3. **Toolgroup Restrictions**:")
        body_lines.append(f"   - Allowed tools: {', '.join(tools)}.")
        if not perms.write:
            body_lines.append("   - File modifications (`write_to_file`, `replace_file_content`, `edit_file`) are strictly disabled.")
        if not perms.execute:
            body_lines.append("   - Command executions (`run_command`) are strictly disabled.")
        if not perms.subagent:
            body_lines.append("   - Nested subagent spawning is strictly disabled.")

        body_lines.append("4. **Stack Invariants**:")
        body_lines.append("   - Python: Hermetic CPython 3.12, no bare except, clean tempfile state.")
        body_lines.append("   - Shell: `set -euo pipefail`, ADR-013 pattern probing exit exception (`|| [ $? -eq 1 ]`).")

        # Zero-Exploration / Targeted Macro Sweeps Invariant
        if arch == AgentArchetype.CUSTODIAN:
            body_lines.append("5. **Targeted Macro & Deduplication Sweep Invariant**:")
            body_lines.append("   - Blind wandering without a query or hypothesis remains strictly prohibited.")
            body_lines.append("   - Targeted repository sweeps (`grep_search`, `find_by_name`, `list_dir`) for symbol discovery, code deduplication audits, and macro consistency are explicitly mandated and prescribed.")
        else:
            body_lines.append("5. **Zero-Exploration Invariant**:")
            body_lines.append("   - Prohibit blind `list_dir` / `find_by_name` sweeps across the repository. Open target files directly from instructions, or communicate back and halt immediately.")

    if custom_instructions and custom_instructions.strip():
        body_lines.append("")
        body_lines.append("## Custom Directives")
        body_lines.append(custom_instructions.strip())

    body_lines.append("")
    return frontmatter_str + "\n\n" + "\n".join(body_lines)


def validate_agent_spec(file_path: Path) -> List[str]:
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


@dataclass(frozen=True)
class SubagentContextStatus:
    """Zero-token context status and health gauge for a subagent."""

    conversation_id: str
    role: str
    step_count: int
    token_count: int
    health_zone: str  # "HEALTHY" | "AMBER" | "RED_ALERT"
    recommendation: str  # "REUSE" | "COMPACT_RECREATE" | "RETIRE"
    latency_ms: float


def classify_context_health(token_count: int, step_count: int) -> Tuple[str, str]:
    """Classify context health into (health_zone, recommendation) based on ADR-025 thresholds."""
    if token_count > 80_000 or step_count > 80:
        return "RED_ALERT", "RETIRE"
    elif token_count >= 40_000 or step_count >= 40:
        return "AMBER", "COMPACT_RECREATE"
    else:
        return "HEALTHY", "REUSE"


def extract_role_from_text(text: str) -> Optional[str]:
    """Extract subagent role from prompt text or content."""
    if not text or not isinstance(text, str):
        return None
    if "continuing work" in text or "resuming work" in text:
        return None
    m_stage = re.search(r"You are\s+(?:the\s+)?(Stage\s+\d+\s+[A-Za-z0-9_]+)", text)
    if m_stage:
        return m_stage.group(1).strip()
    m = re.search(
        r"You are\s+(?:a\s+|an\s+|the\s+)?([A-Za-z0-9_]+(?:-[A-Za-z0-9_]+)*)", text
    )
    if m:
        cand = m.group(1).strip()
        if cand.lower() not in ("a", "an", "the", "now", "here"):
            return cand
    return None


def estimate_subagent_context(transcript_path: Path | str) -> SubagentContextStatus:
    """
    Estimate subagent context window consumption and health gauge with zero LLM tokens.

    Uses exact JSON streaming (<1ms) for transcripts <=2MB.
    Falls back to fast size-stat heuristic (<0.05ms) for titan files >2MB.

    Thresholds:
    - <40k tokens & <40 steps: HEALTHY / REUSE
    - 40k-80k tokens or 40-80 steps: AMBER / COMPACT_RECREATE
    - >80k tokens or >80 steps: RED_ALERT / RETIRE
    """
    t0 = time.perf_counter()
    p = Path(transcript_path)

    if not p.is_file():
        latency_ms = round((time.perf_counter() - t0) * 1000.0, 3)
        return SubagentContextStatus(
            conversation_id="unknown",
            role="unknown",
            step_count=0,
            token_count=0,
            health_zone="HEALTHY",
            recommendation="REUSE",
            latency_ms=latency_ms,
        )

    try:
        file_size = p.stat().st_size
    except OSError:
        latency_ms = round((time.perf_counter() - t0) * 1000.0, 3)
        return SubagentContextStatus(
            conversation_id="unknown",
            role="unknown",
            step_count=0,
            token_count=0,
            health_zone="HEALTHY",
            recommendation="REUSE",
            latency_ms=latency_ms,
        )

    # Derive candidate conversation_id from path
    candidate_id = "unknown"
    parts = p.parts
    if ".system_generated" in parts:
        idx = parts.index(".system_generated")
        if idx > 0:
            candidate_id = parts[idx - 1]
    elif p.parent.name and p.stem in ("transcript", "transcript_full"):
        candidate_id = p.parent.name
    elif p.stem not in ("transcript", "transcript_full"):
        candidate_id = p.stem

    detected_role = ""
    detected_id = ""

    # Size-heuristic fallback for runaway / titan files (>2MB)
    if file_size > 2 * 1024 * 1024:
        try:
            with open(p, "r", encoding="utf-8", errors="replace") as f:
                sample = f.read(8192)
                line1 = sample.split("\n", 1)[0]
                try:
                    obj1 = json.loads(line1)
                    if isinstance(obj1, dict):
                        detected_id = (
                            obj1.get("conversation_id")
                            or obj1.get("conversationId")
                            or ""
                        )
                        raw_role = obj1.get("role") or obj1.get("Role") or ""
                        if str(raw_role).strip().lower() in ("user", "assistant", "system", "tool", "model"):
                            raw_role = ""
                        detected_role = (
                            raw_role
                            or extract_role_from_text(str(obj1.get("content") or ""))
                            or ""
                        )
                except (json.JSONDecodeError, ValueError, KeyError, TypeError):
                    pass

                if not detected_id:
                    m_id = re.search(r'"conversation(?:_i|I)d":\s*"([^"]+)"', sample)
                    if m_id:
                        detected_id = m_id.group(1).strip()
                if not detected_role:
                    detected_role = extract_role_from_text(sample) or ""
        except OSError:
            pass

        token_count = max(1, file_size // 4)
        step_count = max(1, file_size // 1400)
        final_id = detected_id or candidate_id
        final_role = detected_role or "subagent"
        health_zone, rec = classify_context_health(token_count, step_count)
        latency_ms = round((time.perf_counter() - t0) * 1000.0, 3)
        return SubagentContextStatus(
            conversation_id=final_id,
            role=final_role,
            step_count=step_count,
            token_count=token_count,
            health_zone=health_zone,
            recommendation=rec,
            latency_ms=latency_ms,
        )

    # Exact JSON streaming for <= 2MB
    step_count = 0
    total_chars = 0
    explicit_tokens = 0

    try:
        with open(p, "r", encoding="utf-8", errors="replace") as f:
            for line in f:
                line_str = line.strip()
                if not line_str:
                    continue
                step_count += 1
                try:
                    obj = json.loads(line_str)
                    if isinstance(obj, dict):
                        if not detected_id:
                            detected_id = (
                                obj.get("conversation_id")
                                or obj.get("conversationId")
                                or ""
                            )
                        if not detected_role:
                            raw_role = obj.get("role") or obj.get("Role") or ""
                            if str(raw_role).strip().lower() in ("user", "assistant", "system", "tool", "model"):
                                raw_role = ""
                            detected_role = (
                                raw_role
                                or extract_role_from_text(str(obj.get("content") or ""))
                                or ""
                            )

                        if "token_count" in obj or "tokens" in obj:
                            val = obj.get("token_count") or obj.get("tokens") or 0
                            if isinstance(val, (int, float)):
                                explicit_tokens += int(val)

                        content = obj.get("content") or ""
                        thinking = obj.get("thinking") or ""
                        chars = len(content) + len(thinking)
                        if chars == 0:
                            chars = len(line_str)
                        total_chars += chars
                except (json.JSONDecodeError, ValueError):
                    total_chars += len(line_str)
    except OSError:
        pass

    if explicit_tokens > 0:
        token_count = explicit_tokens
    else:
        token_count = max(1, total_chars // 4) if total_chars else 0

    final_id = detected_id or candidate_id
    final_role = detected_role or "subagent"
    health_zone, rec = classify_context_health(token_count, step_count)
    latency_ms = round((time.perf_counter() - t0) * 1000.0, 3)

    return SubagentContextStatus(
        conversation_id=final_id,
        role=final_role,
        step_count=step_count,
        token_count=token_count,
        health_zone=health_zone,
        recommendation=rec,
        latency_ms=latency_ms,
    )


def list_active_subagent_statuses(
    brain_dir: Optional[Path] = None,
) -> List[SubagentContextStatus]:
    """
    Discover active subagents in brain directory and report their context health statuses.
    """
    b_dir = brain_dir or Path(
        os.environ.get(
            "ANTIGRAVITY_BRAIN_DIR",
            os.environ.get(
                "GEMINI_BRAIN_DIR", Path.home() / ".gemini" / "antigravity" / "brain"
            ),
        )
    )
    if not b_dir.exists() or not b_dir.is_dir():
        return []

    subagent_statuses: List[SubagentContextStatus] = []
    seen_ids: set[str] = set()

    # When brain_dir is provided (e.g. test fixtures), check all session directories
    if brain_dir is not None:
        for item in sorted(b_dir.iterdir()):
            if not item.is_dir() or item.name.startswith("."):
                continue
            t_path = item / ".system_generated" / "logs" / "transcript.jsonl"
            if not t_path.is_file():
                t_path = item / "transcript.jsonl"
            if not t_path.is_file():
                continue

            status = estimate_subagent_context(t_path)
            if status.conversation_id not in seen_ids:
                seen_ids.add(status.conversation_id)
                subagent_statuses.append(status)
        return subagent_statuses

    # In production/default brain_dir, scan recent sessions active in the last 4 hours
    try:
        entries = [
            e
            for e in os.scandir(b_dir)
            if e.is_dir() and not e.name.startswith(".")
        ]
        entries.sort(key=lambda e: e.stat().st_mtime, reverse=True)
    except OSError:
        return []

    now = time.time()
    for entry in entries:
        try:
            # Sorted by mtime descending: stop scanning once older than 4 hours
            if now - entry.stat().st_mtime > 14400:
                break

            s_path = Path(entry.path)
            t_path = s_path / ".system_generated" / "logs" / "transcript.jsonl"
            if not t_path.is_file():
                t_path = s_path / "transcript.jsonl"
            if not t_path.is_file():
                continue

            with open(t_path, "r", encoding="utf-8", errors="replace") as f:
                line0 = f.readline()
                if (
                    "You are " in line0
                    or "<subagent_reminder>" in line0
                    or '"role"' in line0
                    or '"Role"' in line0
                ):
                    status = estimate_subagent_context(t_path)
                    if status.conversation_id not in seen_ids:
                        seen_ids.add(status.conversation_id)
                        subagent_statuses.append(status)
        except OSError:
            pass

    return subagent_statuses
