# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Arafat Zahan (@kuasha420)
# Corporate Stewardship & Infrastructure: Purrfect Software Limited (PSL)
# Governed by: ICARO-42/b Ordinance (Company-Supported Personal IP Framework)

"""
Workspace Harmonization Engine (ADR-014, ADR-030).
Antigravity Immune System (Autonomous Agent Runtime).

Non-destructively harmonizes legacy Google Antigravity configurations:
- Migrates legacy .agent/agents/ to .agents/agents/
- Converts legacy .agent/workflows/*.md to .agents/skills/<name>/SKILL.md (synthesizing frontmatter)
- Migrates legacy .agent/rules/ to .agents/rules/
- Updates legacy <!-- Added by PSL-HARNESS --> tagged blocks in AGENTS.md to <!-- Added by AGYIS-HARNESS -->
- Preserves pre-existing user rules outside tagged fences 100% intact
- Supports dry-run inspection mode with zero filesystem side-effects
"""

from __future__ import annotations

from dataclasses import dataclass, field
import json
import os
from pathlib import Path
import re
import shutil
from typing import Any, Dict, List, Optional, Tuple

from harness.delivery.constants import REPO_ROOT
from harness.delivery.workspace import (
    LEGACY_TAG_END,
    LEGACY_TAG_START,
    TAG_END,
    TAG_START,
    TAGGED_BLOCK_PATTERN,
    extract_command_dictionary,
    format_command_dictionary,
)
from harness.utils.frontmatter import parse_frontmatter


def synthesize_skill_frontmatter(content: str, default_name: str) -> str:
    """
    Ensures a workflow markdown file has valid YAML frontmatter with 'name' and 'description'.
    If missing, synthesizes standard YAML frontmatter while preserving existing body content.
    """
    fm, body = parse_frontmatter(content)
    has_name = bool(fm.get("name"))
    has_desc = bool(fm.get("description"))

    if has_name and has_desc:
        return content

    name = str(fm.get("name") or default_name).strip()
    desc = str(fm.get("description") or "").strip()

    if not desc:
        for line in body.splitlines():
            s = line.strip()
            if s and not s.startswith("#") and not s.startswith("<!--"):
                clean = s.lstrip("> *-").strip()
                if clean:
                    desc = clean[:120]
                    break
        if not desc:
            desc = f"Migrated workflow: {default_name}"

    safe_desc = desc.replace('"', '\\"')
    frontmatter_block = f"---\nname: {name}\ndescription: \"{safe_desc}\"\n---\n"

    clean_body = body.lstrip()
    if clean_body:
        return f"{frontmatter_block}\n{clean_body}"
    return frontmatter_block


@dataclass
class HarmonizeResult:
    """Outcome report for workspace harmonization."""

    success: bool
    workspace_dir: Path
    dry_run: bool
    legacy_agent_dir_found: bool = False
    legacy_workflows_migrated: List[str] = field(default_factory=list)
    legacy_agents_migrated: List[str] = field(default_factory=list)
    legacy_rules_migrated: List[str] = field(default_factory=list)
    rules_action: str = ""  # "migrated_tagged_block", "inserted_tagged_block", "created_rules_file", "already_up_to_date"
    command_dictionary: Dict[str, str] = field(default_factory=dict)
    modified: bool = False
    message: str = ""

    def to_dict(self) -> Dict[str, Any]:
        """Convert harmonization result to JSON-serializable dictionary."""
        return {
            "success": self.success,
            "workspace_dir": str(self.workspace_dir),
            "dry_run": self.dry_run,
            "legacy_agent_dir_found": self.legacy_agent_dir_found,
            "legacy_workflows_migrated": self.legacy_workflows_migrated,
            "legacy_agents_migrated": self.legacy_agents_migrated,
            "legacy_rules_migrated": self.legacy_rules_migrated,
            "rules_action": self.rules_action,
            "command_dictionary": self.command_dictionary,
            "modified": self.modified,
            "message": self.message,
        }


def harmonize_workspace(
    workspace_dir: Path,
    dry_run: bool = False,
    source_dir: Optional[Path] = None,
) -> HarmonizeResult:
    """
    Non-destructively harmonizes a workspace from legacy .agent/ configuration
    and PSL-HARNESS tagged rules into modern .agents/ structure and AGYIS-HARNESS rules.
    """
    ws = Path(workspace_dir).resolve()
    if not ws.exists():
        return HarmonizeResult(
            success=False,
            workspace_dir=ws,
            dry_run=dry_run,
            message=f"Target workspace directory '{ws}' does not exist",
        )

    src = Path(source_dir).resolve() if source_dir else REPO_ROOT.resolve()

    legacy_agent_dir = ws / ".agent"
    legacy_agent_dir_found = legacy_agent_dir.is_dir()

    target_agents_dir = ws / ".agents"
    target_agents_subagents = target_agents_dir / "agents"
    target_skills_dir = target_agents_dir / "skills"
    target_rules_dir = target_agents_dir / "rules"

    legacy_agents_migrated: List[str] = []
    legacy_workflows_migrated: List[str] = []
    legacy_rules_migrated: List[str] = []
    any_modified = False

    # 1. Migrate .agent/agents/ -> .agents/agents/
    src_agents_dir = legacy_agent_dir / "agents"
    if src_agents_dir.is_dir():
        for item in sorted(src_agents_dir.glob("*.md")):
            if item.is_file() and not item.is_symlink():
                dst_file = target_agents_subagents / item.name
                needs_copy = True
                if dst_file.is_file():
                    try:
                        if dst_file.read_bytes() == item.read_bytes():
                            needs_copy = False
                    except OSError:
                        pass
                if needs_copy:
                    legacy_agents_migrated.append(item.name)
                    any_modified = True
                    if not dry_run:
                        target_agents_subagents.mkdir(parents=True, exist_ok=True)
                        shutil.copy2(item, dst_file)

    # 2. Migrate legacy workflows -> .agents/skills/<name>/SKILL.md
    workflow_dirs = []
    if (legacy_agent_dir / "workflows").is_dir():
        workflow_dirs.append(legacy_agent_dir / "workflows")
    if (ws / "workflows").is_dir() and (ws / "workflows") != (target_agents_dir / "workflows"):
        workflow_dirs.append(ws / "workflows")

    for wf_dir in workflow_dirs:
        for item in sorted(wf_dir.glob("*.md")):
            if item.is_file() and not item.is_symlink():
                skill_name = item.stem
                dst_skill_dir = target_skills_dir / skill_name
                dst_skill_file = dst_skill_dir / "SKILL.md"

                content = item.read_text(encoding="utf-8", errors="replace")
                synthesized = synthesize_skill_frontmatter(content, default_name=skill_name)

                needs_write = True
                if dst_skill_file.is_file():
                    try:
                        if dst_skill_file.read_text(encoding="utf-8", errors="replace") == synthesized:
                            needs_write = False
                    except OSError:
                        pass

                if needs_write:
                    legacy_workflows_migrated.append(skill_name)
                    any_modified = True
                    if not dry_run:
                        dst_skill_dir.mkdir(parents=True, exist_ok=True)
                        dst_skill_file.write_text(synthesized, encoding="utf-8")

    # 3. Migrate .agent/rules/ -> .agents/rules/
    src_rules_dir = legacy_agent_dir / "rules"
    if src_rules_dir.is_dir():
        for item in sorted(src_rules_dir.rglob("*")):
            if item.is_file() and not item.is_symlink():
                rel_path = item.relative_to(src_rules_dir)
                dst_file = target_rules_dir / rel_path
                needs_copy = True
                if dst_file.is_file():
                    try:
                        if dst_file.read_bytes() == item.read_bytes():
                            needs_copy = False
                    except OSError:
                        pass
                if needs_copy:
                    legacy_rules_migrated.append(str(rel_path))
                    any_modified = True
                    if not dry_run:
                        dst_file.parent.mkdir(parents=True, exist_ok=True)
                        shutil.copy2(item, dst_file)

    # 4. Extract command dictionary
    cmd_dict = extract_command_dictionary(ws)

    # 5. Harmonize AGENTS.md tagged block
    rules_path = ws / "AGENTS.md"
    universal_rules_file = src / "harness" / "rules" / "universal_agents.md"
    if not universal_rules_file.is_file():
        for cand in [src / "rules" / "universal_agents.md", src / "rules" / "AGENTS.md"]:
            if cand.is_file():
                universal_rules_file = cand
                break

    if universal_rules_file.is_file():
        universal_text = universal_rules_file.read_text(encoding="utf-8").strip()
    else:
        universal_text = "# Universal Empirical Agent Rules: Agyis Harness Guidelines"

    formatted_cmds = format_command_dictionary(cmd_dict)
    if formatted_cmds:
        if "```bash\n" in universal_text:
            universal_text = universal_text.replace("```bash\n", f"```bash\n{formatted_cmds}\n\n", 1)
        else:
            universal_text = f"```bash\n{formatted_cmds}\n```\n\n{universal_text}"

    tagged_block = f"{TAG_START}\n{universal_text}\n{TAG_END}"
    rules_action = "already_up_to_date"

    if rules_path.is_file():
        existing_rules = rules_path.read_text(encoding="utf-8")
        if TAGGED_BLOCK_PATTERN.search(existing_rules):
            new_rules = TAGGED_BLOCK_PATTERN.sub(tagged_block, existing_rules)
            if new_rules != existing_rules:
                rules_action = "migrated_tagged_block"
                any_modified = True
                if not dry_run:
                    rules_path.write_text(new_rules, encoding="utf-8")
            else:
                rules_action = "already_up_to_date"
        else:
            existing_clean = existing_rules.rstrip()
            if existing_clean:
                new_rules = f"{existing_clean}\n\n{tagged_block}\n"
            else:
                new_rules = f"{tagged_block}\n"
            rules_action = "inserted_tagged_block"
            any_modified = True
            if not dry_run:
                rules_path.write_text(new_rules, encoding="utf-8")
    else:
        new_rules = f"{tagged_block}\n"
        rules_action = "created_rules_file"
        any_modified = True
        if not dry_run:
            rules_path.write_text(new_rules, encoding="utf-8")

    action_summary = []
    if legacy_agents_migrated:
        action_summary.append(f"{len(legacy_agents_migrated)} agents")
    if legacy_workflows_migrated:
        action_summary.append(f"{len(legacy_workflows_migrated)} workflows")
    if legacy_rules_migrated:
        action_summary.append(f"{len(legacy_rules_migrated)} rules")
    if rules_action in ("migrated_tagged_block", "inserted_tagged_block", "created_rules_file"):
        action_summary.append(f"rules: {rules_action}")

    prefix = "[dry-run] " if dry_run else ""
    if any_modified:
        msg = f"{prefix}Harmonized workspace ({', '.join(action_summary) if action_summary else 'updated'})"
    else:
        msg = f"{prefix}Workspace already harmonized (no changes needed)"

    return HarmonizeResult(
        success=True,
        workspace_dir=ws,
        dry_run=dry_run,
        legacy_agent_dir_found=legacy_agent_dir_found,
        legacy_workflows_migrated=legacy_workflows_migrated,
        legacy_agents_migrated=legacy_agents_migrated,
        legacy_rules_migrated=legacy_rules_migrated,
        rules_action=rules_action,
        command_dictionary=cmd_dict,
        modified=any_modified,
        message=msg,
    )
