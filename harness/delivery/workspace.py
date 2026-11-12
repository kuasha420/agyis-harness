# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Arafat Zahan (@kuasha420)
# Corporate Stewardship & Infrastructure: Purrfect Software Limited (PSL)
# Governed by: ICARO-42/b Ordinance (Company-Supported Personal IP Framework)

"""
Workspace instantiation, tagged rules management, and stack-tailored skill deployment (ADR-030).
"""

from __future__ import annotations

from dataclasses import dataclass, field
import os
from pathlib import Path
import re
import shutil
import stat
from typing import Any, Dict, List, Optional, Sequence, Union

from harness.delivery.cache import purge_workspace_build_caches
from harness.delivery.constants import REPO_ROOT
from harness.delivery.surfaces import find_workspace_root
from harness.skills import (
    ARCHITECTURAL_ROLE_PRESETS,
    LANGUAGE_RUNTIME_PRESETS,
    STACK_PRESETS,
    detect_workspace_stack,
    resolve_skills_to_sync,
)

TAG_START = "<!-- Added by AGYIS-HARNESS -->"
TAG_END = "<!-- End AGYIS-HARNESS -->"
LEGACY_TAG_START = "<!-- Added by PSL-HARNESS -->"
LEGACY_TAG_END = "<!-- End PSL-HARNESS -->"

TAGGED_BLOCK_PATTERN = re.compile(
    r"<!-- Added by (?:AGYIS-HARNESS|PSL-HARNESS) -->[\s\S]*?<!-- End (?:AGYIS-HARNESS|PSL-HARNESS) -->"
)

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


def _dedup_skills(skills: Sequence[str]) -> List[str]:
    """Deduplicates skill identifiers in insertion order using normalized names."""
    seen: set[str] = set()
    result: List[str] = []
    for s in skills:
        norm = s.strip().lower().replace("_", "-")
        if norm and norm not in seen:
            seen.add(norm)
            result.append(s)
    return result


def resolve_skills_for_workspace(
    workspace_dir: Path | str,
    stack: Optional[str] = None,
    role: Optional[str] = None,
    subproject: Optional[Union[Path, str]] = None,
    skills: Optional[Sequence[str]] = None,
) -> List[str]:
    """Resolves workspace skills via decoupled Language Runtime, Architectural Role, and Subproject presets.

    Preserves backward compatibility for legacy stack presets (``"audit"``, ``"all"``,
    ``"generic"``, or unknown stack names) while delegating standard language/role/subproject
    resolution to ``harness.skills.resolve_skills_to_sync``.
    """
    if skills is not None:
        return _dedup_skills(skills)

    root_ws = Path(workspace_dir).resolve()
    stk_norm = stack.strip().lower() if stack else None
    role_norm = role.strip().lower() if role else None

    if role_norm and role_norm not in ARCHITECTURAL_ROLE_PRESETS:
        raise ValueError(
            f"Unknown architectural role '{role}'. Choose from: {', '.join(sorted(ARCHITECTURAL_ROLE_PRESETS.keys()))}"
        )

    if stk_norm in ("audit", "all", "generic"):
        resolved: List[str] = []
        if stk_norm == "audit":
            resolved.append("psl-audit-toolkit")
        elif stk_norm == "all":
            resolved.extend([
                "psl-stack-typescript",
                "psl-stack-python",
                "psl-stack-systems",
                "psl-stack-shell",
                "psl-stack-backend",
                "psl-audit-toolkit",
            ])
        if role_norm:
            resolved.extend(ARCHITECTURAL_ROLE_PRESETS[role_norm])
        return _dedup_skills(resolved)

    if stk_norm and stk_norm != "auto" and stk_norm not in STACK_PRESETS:
        tokens = [t.strip() for t in stk_norm.split(",") if t.strip()]
        if not all(t in STACK_PRESETS or t in LANGUAGE_RUNTIME_PRESETS for t in tokens):
            resolved = list(ARCHITECTURAL_ROLE_PRESETS[role_norm]) if role_norm else []
            return _dedup_skills(resolved)

    resolved_skills = resolve_skills_to_sync(
        stack=stk_norm or "auto",
        role=role_norm,
        workspace_root=root_ws,
        subproject=subproject,
    )
    return list(resolved_skills or [])


from harness.delivery.workspace_probe import (  # noqa: F401
    STANDARD_VERB_DESCRIPTIONS,
    _has_python_files,
    adapt_spdx_license,
    detect_repository_license,
    detect_test_command,
    extract_command_descriptions,
    extract_command_dictionary,
    format_command_dictionary,
    normalize_tagged_rules,
)



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
    command_dictionary: Dict[str, str] = field(default_factory=dict)
    dry_run: bool = False
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
    dry_run: bool = False,
) -> WorkspaceInstallResult:
    """
    Initializes a workspace with stack-tailored skills, tagged rules, and optional subagents.

    - Preserves existing rules in <ws>/AGENTS.md with tagged AGYIS delimiters (upgrading legacy PSL delimiters).
    - Installs stack skills to <ws>/.agents/skills/.
    - Installs subagents to <ws>/.agents/agents/ if requested.
    - Enforces byte-comparison deduplication and non-destructive overwrite guards.
    - Emits actionable notice if legacy .agent/ configuration is detected.
    - Supports dry-run preview mode with zero filesystem modifications.
    """
    ws = Path(workspace_dir).resolve()
    if not ws.exists() and not dry_run:
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

    # Command dictionary extraction
    cmd_dict = extract_command_dictionary(ws)

    # Detect repository license
    repo_license = detect_repository_license(ws)

    # Skills installation
    src_skills = (src / "harness" / "skills") if (src / "harness" / "skills").is_dir() else (src / "skills")
    if skills is not None:
        selected_skills = list(skills)
    else:
        selected_skills = resolve_skills_for_workspace(
            workspace_dir=ws,
            stack=stack,
        )

    target_skills_dir = ws / ".agents" / "skills"
    skills_installed: List[str] = []
    skills_skipped: List[str] = []

    if selected_skills and src_skills.is_dir():
        if not dry_run:
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
            is_symlink = dst_sk_dir.is_symlink()
            real_dst_dir = dst_sk_dir.resolve() if is_symlink else dst_sk_dir

            dst_skill_file = real_dst_dir / "SKILL.md"
            src_skill_file = sk_dir / "SKILL.md"

            if dst_skill_file.exists() and not override:
                src_bytes = src_skill_file.read_bytes() if src_skill_file.exists() else b""
                if repo_license and src_skill_file.exists():
                    src_bytes = adapt_spdx_license(
                        src_skill_file.read_text(encoding="utf-8", errors="replace"), repo_license
                    ).encode("utf-8")
                is_identical = (
                    dst_skill_file.exists()
                    and dst_skill_file.read_bytes() == src_bytes
                )
                if dedup and is_identical:
                    skills_skipped.append(sk_dir.name)
                    continue
                skills_skipped.append(sk_dir.name)
                continue

            if not dry_run:
                real_dst_dir.mkdir(parents=True, exist_ok=True)
                for item in sk_dir.rglob("*"):
                    if item.is_file():
                        rel = item.relative_to(sk_dir)
                        out_f = real_dst_dir / rel
                        out_f.parent.mkdir(parents=True, exist_ok=True)
                        if repo_license and item.suffix.lower() in (".md", ".txt", ".json", ".yaml", ".yml"):
                            file_text = item.read_text(encoding="utf-8", errors="replace")
                            adapted = adapt_spdx_license(file_text, repo_license)
                            out_f.write_text(adapted, encoding="utf-8")
                        else:
                            shutil.copy2(item, out_f)
            skills_installed.append(sk_dir.name)

    # Adapt SPDX licenses of any existing installed skills if repository license is detected
    if repo_license and not dry_run and target_skills_dir.exists():
        for sk_md in target_skills_dir.rglob("*.md"):
            if sk_md.is_file():
                try:
                    txt = sk_md.read_text(encoding="utf-8", errors="replace")
                    adp = adapt_spdx_license(txt, repo_license)
                    if adp != txt:
                        sk_md.write_text(adp, encoding="utf-8")
                except OSError:
                    pass

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
        if not dry_run:
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

            if not dry_run:
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
        if repo_license:
            universal_text = adapt_spdx_license(universal_text, repo_license)
        formatted_cmds = format_command_dictionary(cmd_dict, workspace_dir=ws)
        if formatted_cmds:
            if "```bash\n" in universal_text:
                universal_text = universal_text.replace("```bash\n", f"```bash\n{formatted_cmds}\n\n", 1)
            else:
                universal_text = f"```bash\n{formatted_cmds}\n```\n\n{universal_text}"

        tagged_block = f"{TAG_START}\n{universal_text}\n{TAG_END}"

        if rules_path.exists():
            existing_rules = rules_path.read_text(encoding="utf-8")
            if repo_license:
                existing_rules = adapt_spdx_license(existing_rules, repo_license)
            pattern = TAGGED_BLOCK_PATTERN
            if pattern.search(existing_rules):
                new_rules = pattern.sub(tagged_block, existing_rules)
            else:
                existing_clean = existing_rules.rstrip()
                if existing_clean:
                    new_rules = f"{existing_clean}\n\n{tagged_block}\n"
                else:
                    new_rules = f"{tagged_block}\n"
            if new_rules != existing_rules and normalize_tagged_rules(new_rules) != normalize_tagged_rules(existing_rules):
                if not dry_run:
                    rules_path.write_text(new_rules, encoding="utf-8")
                rules_updated = True
        else:
            if not dry_run:
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
        command_dictionary=cmd_dict,
        dry_run=dry_run,
        message=(
            f"[DRY-RUN] Workspace initialization preview for stack '{detected_stack}'"
            if dry_run
            else f"Workspace initialized successfully for stack '{detected_stack}'"
        ),
    )


def purge_build_caches(
    workspace_dir: Path | str,
    subproject: Optional[Path | str] = None,
    dry_run: bool = False,
    target_dirs: Optional[Sequence[str]] = None,
    max_depth: int = 3,
) -> List[str]:
    """
    Purges stale build cache directories (.next/, .turbo/, node_modules/.cache) before verification gates (ADR-031).
    Delegates to harness.delivery.cache.purge_workspace_build_caches.
    """
    return purge_workspace_build_caches(
        workspace_dir=workspace_dir,
        target_dirs=target_dirs,
        dry_run=dry_run,
        max_depth=max_depth,
        subproject=subproject,
    )
