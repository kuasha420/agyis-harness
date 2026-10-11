# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Purrfect Software Limited (PSL)

"""
Workspace instantiation, tagged rules management, and stack-tailored skill deployment (ADR-030).
"""

from __future__ import annotations

from dataclasses import dataclass, field
import os
from pathlib import Path
import re
import shutil
from typing import Any, Dict, List, Optional

from harness.delivery.constants import REPO_ROOT
from harness.delivery.surfaces import find_workspace_root
from harness.skills import (
    STACK_PRESETS,
    detect_workspace_stack,
)

TAG_START = "<!-- Added by PSL-HARNESS -->"
TAG_END = "<!-- End PSL-HARNESS -->"

STACK_SKILL_PRESETS: Dict[str, List[str]] = {
    **STACK_PRESETS,
    "audit": ["psl-audit-toolkit"],
    "all": [
        "psl-stack-typescript",
        "psl-stack-python",
        "psl-stack-systems",
        "psl-stack-shell",
        "psl-stack-backend",
        "psl-audit-toolkit",
    ],
}


@dataclass
class WorkspaceInstallResult:
    """Outcome report for workspace initialization."""

    success: bool
    workspace_dir: Path
    stack: str
    skills_installed: List[str] = field(default_factory=list)
    skills_skipped: List[str] = field(default_factory=list)
    agents_installed: List[str] = field(default_factory=list)
    agents_skipped: List[str] = field(default_factory=list)
    rules_updated: bool = False
    legacy_notice: Optional[str] = None
    message: str = ""


def install_workspace(
    workspace_dir: Path,
    stack: Optional[str] = None,
    skills: Optional[List[str]] = None,
    agents: Optional[List[str]] = None,
    include_agents: bool = False,
    dedup: bool = True,
    override: bool = False,
    source_dir: Optional[Path] = None,
) -> WorkspaceInstallResult:
    """
    Initializes a workspace with stack-tailored skills, tagged rules, and optional subagents.

    - Preserves existing rules in <ws>/AGENTS.md with tagged PSL delimiters.
    - Installs stack skills to <ws>/.agents/skills/.
    - Installs subagents to <ws>/.agents/agents/ if requested.
    - Enforces byte-comparison deduplication and non-destructive overwrite guards.
    - Emits actionable notice if legacy .agent/ configuration is detected.
    """
    ws = Path(workspace_dir).resolve()
    if not ws.exists():
        ws.mkdir(parents=True, exist_ok=True)

    src = Path(source_dir).resolve() if source_dir else REPO_ROOT.resolve()

    # Legacy setup check
    legacy_notice: Optional[str] = None
    if (ws / ".agent").exists() and (ws / ".agent").is_dir():
        legacy_notice = (
            "Legacy '.agent/' directory detected. Run the /psl-harmonize skill "
            "to migrate legacy agents, workflows, and rules to modern '.agents/' structure."
        )
    elif (ws / "workflows").exists() or (ws / ".agent" / "workflows").exists():
        legacy_notice = (
            "Legacy workflow files detected. Run the /psl-harmonize skill "
            "to migrate legacy workflows to modular skills."
        )

    # Stack detection
    if stack:
        detected_stack = stack.strip().lower()
    else:
        detected_stack = detect_workspace_stack(ws) or "generic"

    # Skills installation
    src_skills = (src / "harness" / "skills") if (src / "harness" / "skills").is_dir() else (src / "skills")
    if skills is not None:
        selected_skills = list(skills)
    else:
        selected_skills = list(STACK_SKILL_PRESETS.get(detected_stack, []))

    target_skills_dir = ws / ".agents" / "skills"
    skills_installed: List[str] = []
    skills_skipped: List[str] = []

    if selected_skills and src_skills.is_dir():
        target_skills_dir.mkdir(parents=True, exist_ok=True)
        for sk_name in selected_skills:
            sk_dir = src_skills / sk_name
            if not (sk_dir.exists() and sk_dir.is_dir()):
                for cand in src_skills.iterdir():
                    if cand.is_dir() and cand.name.lower().replace("_", "-") == sk_name.lower().replace("_", "-"):
                        sk_dir = cand
                        break
            if not (sk_dir.exists() and sk_dir.is_dir()):
                continue

            dst_sk_dir = target_skills_dir / sk_dir.name
            dst_skill_file = dst_sk_dir / "SKILL.md"
            src_skill_file = sk_dir / "SKILL.md"

            if dst_skill_file.exists() and not override:
                is_identical = (
                    src_skill_file.exists()
                    and dst_skill_file.read_bytes() == src_skill_file.read_bytes()
                )
                if dedup and is_identical:
                    skills_skipped.append(sk_dir.name)
                    continue
                skills_skipped.append(sk_dir.name)
                continue

            dst_sk_dir.mkdir(parents=True, exist_ok=True)
            for item in sk_dir.rglob("*"):
                if item.is_file():
                    rel = item.relative_to(sk_dir)
                    out_f = dst_sk_dir / rel
                    out_f.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(item, out_f)
            skills_installed.append(sk_dir.name)

    # Agents installation
    src_agents = (src / "harness" / "agents") if (src / "harness" / "agents").is_dir() else (src / "agents")
    agents_installed: List[str] = []
    agents_skipped: List[str] = []
    if agents is not None:
        selected_agents = list(agents)
    elif include_agents:
        selected_agents = [p.stem for p in sorted(src_agents.glob("*.md"))]
    else:
        selected_agents = []

    if selected_agents and src_agents.is_dir():
        target_agents_dir = ws / ".agents" / "agents"
        target_agents_dir.mkdir(parents=True, exist_ok=True)
        for ag_name in selected_agents:
            ag_src = src_agents / f"{ag_name}.md"
            if not ag_src.is_file():
                for cand in src_agents.glob("*.md"):
                    if cand.stem.lower().replace("_", "-") == ag_name.lower().replace("_", "-"):
                        ag_src = cand
                        break
            if not ag_src.is_file():
                continue

            dst_ag_file = target_agents_dir / ag_src.name
            if dst_ag_file.exists() and not override:
                is_identical = dst_ag_file.read_bytes() == ag_src.read_bytes()
                if dedup and is_identical:
                    agents_skipped.append(ag_src.stem)
                    continue
                agents_skipped.append(ag_src.stem)
                continue

            shutil.copy2(ag_src, dst_ag_file)
            agents_installed.append(ag_src.stem)

    # Tagged rules management in <ws>/AGENTS.md
    rules_updated = False
    rules_path = ws / "AGENTS.md"
    universal_rules_file = src / "harness" / "rules" / "universal_agents.md"
    if not universal_rules_file.is_file():
        for cand in [src / "rules" / "universal_agents.md", src / "rules" / "AGENTS.md"]:
            if cand.is_file():
                universal_rules_file = cand
                break
    if universal_rules_file.is_file():
        universal_text = universal_rules_file.read_text(encoding="utf-8").strip()
        tagged_block = f"{TAG_START}\n{universal_text}\n{TAG_END}"

        if rules_path.exists():
            existing_rules = rules_path.read_text(encoding="utf-8")
            pattern = re.compile(rf"{re.escape(TAG_START)}[\s\S]*?{re.escape(TAG_END)}")
            if pattern.search(existing_rules):
                new_rules = pattern.sub(tagged_block, existing_rules)
            else:
                existing_clean = existing_rules.rstrip()
                if existing_clean:
                    new_rules = f"{existing_clean}\n\n{tagged_block}\n"
                else:
                    new_rules = f"{tagged_block}\n"
            if new_rules != existing_rules:
                rules_path.write_text(new_rules, encoding="utf-8")
                rules_updated = True
        else:
            rules_path.write_text(f"{tagged_block}\n", encoding="utf-8")
            rules_updated = True

    return WorkspaceInstallResult(
        success=True,
        workspace_dir=ws,
        stack=detected_stack,
        skills_installed=skills_installed,
        skills_skipped=skills_skipped,
        agents_installed=agents_installed,
        agents_skipped=agents_skipped,
        rules_updated=rules_updated,
        legacy_notice=legacy_notice,
        message=f"Workspace initialized successfully for stack '{detected_stack}'",
    )
