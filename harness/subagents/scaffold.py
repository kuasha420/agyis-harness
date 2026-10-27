# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Arafat Zahan (@kuasha420)
# Corporate Stewardship & Infrastructure: Purrfect Software Limited (PSL)
# Governed by: ICARO-42/b Ordinance (Company-Supported Personal IP Framework)

"""
Specialist subagent workspace context inspection and markdown scaffolding (ADR-014).
"""

from __future__ import annotations

import json
import os
from pathlib import Path
import re
from typing import Any, Dict, List, Optional

from harness.subagents.spec import (
    CAPABILITY_BUNDLES,
    REPO_ROOT,
    AgentArchetype,
    ToolPermissions,
)


def inspect_workspace_context(repo_root: Optional[Path] = None) -> Dict[str, Any]:
    """
    Scans root project files (package.json, pyproject.toml, Cargo.toml, AGENTS.md, matrix.json, roadmap.md)
    to extract project name, languages, test runners, commands, and active rules.
    """
    if repo_root is not None:
        root = Path(repo_root)
    else:
        from harness.delivery.surfaces import find_workspace_root
        root = find_workspace_root()
    project_name = root.name
    languages: List[str] = []
    test_runners: List[str] = []
    commands: List[str] = []
    rules: List[str] = []
    detected_files: List[str] = []
    is_esm: bool = False
    module_format: str = "commonjs"

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
                if data.get("type") == "module":
                    is_esm = True
                    module_format = "module"
                elif data.get("type"):
                    module_format = str(data.get("type"))
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
        "is_esm": is_esm,
        "module_format": module_format,
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
        elif arch == AgentArchetype.INVESTIGATOR:
            resolved_bundle = "investigator"
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
            role = "Agyis Lead Architect & Master Implementer"
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
        elif arch == AgentArchetype.INVESTIGATOR:
            role = "Agyis Root Cause Analyst & Forensic Investigator"
        else:
            role = f"{arch.value.capitalize()} Specialist"

    # Derive description if not provided
    if not description:
        if arch == AgentArchetype.MAIN:
            description = (
                "Agyis lead architect, systems engineer, master implementer, "
                "and cross-repo harmonizer with full tool capabilities, complete "
                "customization inheritance, and verified operational discipline."
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
        elif arch == AgentArchetype.INVESTIGATOR:
            description = (
                "Hypothesis testing, minimal reproduction scripts in scratch, "
                "and root cause analysis. Strictly read-only on product code."
            )
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
            can_m = arch in (AgentArchetype.PLANNER, AgentArchetype.MAIN, AgentArchetype.INVESTIGATOR) or bool(skills)
            enable_w = can_w
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
    ]
    if perms.allowed_mcp_servers:
        fm_lines.append("  mcp:")
        for s in perms.allowed_mcp_servers:
            fm_lines.append(f"    - {s}")
    else:
        fm_lines.append(f"  mcp: {'true' if perms.can_mcp else 'false'}")
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
        f"You are `{name}`, the dedicated {role} in the Agyis Subagent Ladder protocol.",
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
    elif arch == AgentArchetype.INVESTIGATOR:
        body_lines.append(
            "1. **Hypothesis-Driven Root Cause Analysis (RCA)**: Formulate explicit, falsifiable hypotheses. "
            "Author minimal standalone reproduction scripts in scratch (scratch/reproduce_issue.py) confirming "
            "deterministic red failure before proposing fixes. Strictly read-only on product code: forbidden from "
            "editing product source code or modifying existing test suites. Writes only to scratch and Tier 1 "
            "rca_report.md with concrete fix specifications for agyis_builder."
        )

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
            "   - `agyis test`: Run complete hermetic test suite (sub-second benchmark invariant).",
            "   - `agyis doctor`: Audit host workstation runtimes and auto-heal environment.",
            "   - `agyis status`: Display harness health, active hooks, and telemetry gauge.",
            "   - `agyis sync`: Audit and synchronize active session into telemetry.db.",
            "4. **Architectural Decisions & Standards**:",
            "   - **ADR-012 (Artifact-First Planning)**: Never propose multi-component changes in raw chat. Crystallize into interactive `implementation_plan.md` artifacts before execution.",
            "   - **ADR-013 (Terminal Invariants & Pattern Probing)**: Always use `set -euo pipefail`. Pattern probes (`grep`, `diff`) without conditionals must append `|| [ $? -eq 1 ]`. Pre-flight test tools with `command -v`.",
            "   - **ADR-014 (Product vs. Project Bifurcation)**: Distributable plugin and CLI toolchain live in `harness/`; pipeline scripts, test suites, and telemetry data live in `pipeline/`, `tests/`, and `data/`.",
            "   - **ADR-015 (Clean-Room Testing)**: All verification must be hermetic and execute strictly in <1.0s benchmark runtime.",
            "5. **Subagent Delegation Ladder Protocol**:",
            "   - Decompose multi-phase tasks and delegate using native `@<subagent>` syntax (e.g., `@agyis_architect`, `@harness_builder`, `@harness_reviewer`, `@harness_auditor`, `@planner`, `@coordinator`, `@harness_custodian`).",
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

        if arch == AgentArchetype.INVESTIGATOR:
            body_lines.append("6. **Tool-Native Reverse Engineering Invariant (PSL-INV-004 §3)**:")
            body_lines.append("   - When reverse engineering compiled binaries (PE, ELF, Mach-O), you must use native REA tooling (`rea analyze`, `rea decompile`, `rea search`). Custom python binary parsers are prohibited.")

    if custom_instructions and custom_instructions.strip():
        body_lines.append("")
        body_lines.append("## Custom Directives")
        body_lines.append(custom_instructions.strip())

    body_lines.append("")
    return frontmatter_str + "\n\n" + "\n".join(body_lines)
