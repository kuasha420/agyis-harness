# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Arafat Zahan (@kuasha420)
# Corporate Stewardship & Infrastructure: Purrfect Software Limited (PSL)
# Governed by: ICARO-42/b Ordinance (Company-Supported Personal IP Framework)

"""
Multi-surface synchronization and workspace path resolution (ADR-030).
"""

from __future__ import annotations

import os
from pathlib import Path
import re
import shutil
from typing import Any, Dict, List, Optional, Set

from harness.delivery.constants import (
    DEFAULT_SURFACE_NAMES,
    SYNC_SURFACE_ITEMS,
)


def find_workspace_root(start_dir: Optional[Path] = None) -> Path:
    """
    Finds the root of the workspace repository.

    Traverses parent directories from start_dir (or current working directory)
    until a directory containing .git (as a directory or worktree pointer file) is found.
    """
    curr = Path(start_dir).resolve() if start_dir is not None else Path.cwd().resolve()
    for candidate in [curr] + list(curr.parents):
        git_target = candidate / ".git"
        if git_target.exists():
            return candidate
    return curr


def enforce_single_source_agents_impl(
    plugin_agents_dir: Optional[Path],
    config_dir: Path,
    target: Path,
    source_dir: Path,
    dry_run: bool = False,
) -> List[str]:
    """
    Enforces single-source agent delivery (Issue #30).
    Removes standalone duplicate agent markdown files from candidate
    global config/agents directories so the plugin bundle is the single source.
    """
    if not plugin_agents_dir or not plugin_agents_dir.is_dir():
        return []

    plugin_agent_names = {
        f.name for f in plugin_agents_dir.glob("*.md")
    }
    if not plugin_agent_names:
        return []

    candidate_dirs = [config_dir / "agents"]
    if target.parent.name == "plugins":
        candidate_dirs.append(target.parent.parent / "agents")

    removed: List[str] = []
    seen_dirs: Set[Path] = set()

    for cand_dir in candidate_dirs:
        resolved_cand = cand_dir.resolve()
        if resolved_cand in seen_dirs:
            continue
        seen_dirs.add(resolved_cand)

        if not cand_dir.exists() or not cand_dir.is_dir():
            continue

        # Safety guard: never touch inside source_dir
        try:
            if resolved_cand.is_relative_to(source_dir.resolve()):
                continue
        except (ValueError, OSError):
            pass

        for fname in plugin_agent_names:
            dup_file = cand_dir / fname
            if dup_file.is_file() or dup_file.is_symlink():
                if not dry_run:
                    try:
                        dup_file.unlink()
                    except OSError:
                        continue
                removed.append(str(dup_file))

    return removed


def enforce_single_source_skills(
    config_dir: Path | str,
    workspace_dir: Optional[Path | str] = None,
    dry_run: bool = False,
    plugin_skills_dir: Optional[Path | str] = None,
    target: Optional[Path] = None,
    source_dir: Optional[Path] = None,
) -> List[str]:
    """
    Enforces single-source skill delivery (Issue #52).
    Removes standalone duplicate skill directories in ~/.gemini/config/skills/
    if already supplied by the plugin bundle. Also prunes redundant workspace
    duplicate skills from <workspace>/.agents/skills/ when workspace_dir is provided.
    """
    cfg = Path(config_dir).resolve()
    removed: List[str] = []

    plugin_skill_names: Set[str] = set()
    if plugin_skills_dir:
        p_dir = Path(plugin_skills_dir).resolve()
        if p_dir.is_dir():
            for item in p_dir.iterdir():
                if item.is_dir() and not item.name.startswith("."):
                    if (item / "SKILL.md").is_file() or any(item.glob("*.md")):
                        plugin_skill_names.add(item.name)

    if not plugin_skill_names:
        plugins_root = cfg / "plugins"
        if plugins_root.is_dir():
            for plugin_dir in plugins_root.iterdir():
                if plugin_dir.is_dir() and not plugin_dir.name.startswith("."):
                    skills_sub = plugin_dir / "skills"
                    if skills_sub.is_dir():
                        for item in skills_sub.iterdir():
                            if item.is_dir() and not item.name.startswith("."):
                                if (item / "SKILL.md").is_file() or any(item.glob("*.md")):
                                    plugin_skill_names.add(item.name)

    if not plugin_skill_names:
        repo_skills = Path(__file__).resolve().parent.parent / "skills"
        if repo_skills.is_dir():
            for item in repo_skills.iterdir():
                if item.is_dir() and not item.name.startswith("."):
                    if (item / "SKILL.md").is_file() or any(item.glob("*.md")):
                        plugin_skill_names.add(item.name)

    if not plugin_skill_names:
        return []

    candidate_dirs = [cfg / "skills"]
    if target is not None and target.parent.name == "plugins":
        candidate_dirs.append(target.parent.parent / "skills")

    seen_dirs: Set[Path] = set()
    for cand_dir in candidate_dirs:
        resolved_cand = cand_dir.resolve()
        if resolved_cand in seen_dirs:
            continue
        seen_dirs.add(resolved_cand)

        if not cand_dir.exists() or not cand_dir.is_dir():
            continue

        if source_dir is not None:
            try:
                if resolved_cand.is_relative_to(Path(source_dir).resolve()):
                    continue
            except (ValueError, OSError):
                pass

        for sname in plugin_skill_names:
            dup_dir = cand_dir / sname
            if dup_dir.exists():
                if not dry_run:
                    try:
                        if dup_dir.is_symlink():
                            dup_dir.unlink()
                        elif dup_dir.is_dir():
                            shutil.rmtree(dup_dir)
                    except OSError:
                        continue
                removed.append(str(dup_dir))

    if workspace_dir is not None:
        ws_root = Path(workspace_dir).resolve()
        from harness.utils.workspace import is_harness_workspace
        if not is_harness_workspace(ws_root):
            ws_skills = ws_root / ".agents" / "skills"
            if ws_skills.is_dir():
                for sname in plugin_skill_names:
                    dup_ws_dir = ws_skills / sname
                    if dup_ws_dir.exists():
                        if not dry_run:
                            try:
                                if dup_ws_dir.is_symlink():
                                    dup_ws_dir.unlink()
                                elif dup_ws_dir.is_dir():
                                    shutil.rmtree(dup_ws_dir)
                            except OSError:
                                continue
                        removed.append(str(dup_ws_dir))

    return removed


def sync_surfaces_impl(
    surfaces: List[Path],
    config_dir: Path,
    dry_run: bool = False,
) -> List[Dict[str, Any]]:
    """
    Synchronizes all Antigravity surfaces (~/.gemini/antigravity,
    ~/.gemini/antigravity-cli, ~/.gemini/antigravity-ide) to link
    agents, skills, plugins, rules, hooks.json, AGENTS.md to canonical config.
    """
    cfg_root = Path(config_dir).resolve()
    if not dry_run:
        cfg_root.mkdir(parents=True, exist_ok=True)

    # Ensure canonical config directories exist
    for dname in ("agents", "skills", "plugins", "rules"):
        if not dry_run:
            (cfg_root / dname).mkdir(parents=True, exist_ok=True)

    # Ensure canonical hooks.json and AGENTS.md exist if not present
    canonical_hooks = cfg_root / "hooks.json"
    if not canonical_hooks.exists() and not dry_run:
        canonical_hooks.write_text("{\n  \"hooks\": []\n}\n", encoding="utf-8")

    canonical_agents_md = cfg_root / "AGENTS.md"
    if not canonical_agents_md.exists() and not dry_run:
        canonical_agents_md.write_text("# Global Agent Rules\n", encoding="utf-8")

    results: List[Dict[str, Any]] = []

    for surface in surfaces:
        surface_resolved = Path(surface).resolve()
        if not dry_run:
            surface_resolved.mkdir(parents=True, exist_ok=True)

        for item in SYNC_SURFACE_ITEMS:
            canonical_item = cfg_root / item
            surface_link = surface_resolved / item

            # Avoid self-referencing if surface IS the config root
            if surface_resolved == cfg_root:
                continue

            if surface_link.is_symlink():
                try:
                    if surface_link.resolve() == canonical_item.resolve():
                        results.append({
                            "surface": str(surface_resolved),
                            "item": item,
                            "status": "already_linked",
                            "target": str(canonical_item),
                        })
                        continue
                except OSError:
                    pass
                if not dry_run:
                    surface_link.unlink()
            elif surface_link.exists():
                if surface_link.is_dir():
                    # Migrate files from surface dir to canonical before linking
                    if not dry_run:
                        for child in surface_link.iterdir():
                            dest = canonical_item / child.name
                            if not dest.exists():
                                shutil.move(str(child), str(dest))
                        shutil.rmtree(surface_link)
                else:
                    if not dry_run:
                        surface_link.unlink()

            if not dry_run:
                surface_link.symlink_to(canonical_item)

            results.append({
                "surface": str(surface_resolved),
                "item": item,
                "status": "linked",
                "target": str(canonical_item),
            })

    return results


def sync_surfaces(
    surfaces: Optional[List[Path]] = None,
    config_dir: Optional[Path] = None,
    dry_run: bool = False,
) -> List[Dict[str, Any]]:
    """Standalone helper for multi-surface synchronization across Antigravity paths."""
    from harness.delivery.installer import PluginInstaller

    installer = PluginInstaller(config_dir=config_dir, surfaces=surfaces)
    return installer.sync_surfaces(surfaces=surfaces, config_dir=config_dir, dry_run=dry_run)


# --- Single-Source Rule Deduplication Engine (Issues #70 & #71) ---

UNIVERSAL_SECTION_KEYWORDS = [
    "terminal invariants",
    "surgical contiguous edits",
    "context preservation",
    "artifact-first planning",
    "human-in-the-loop",
    "cleanroom reverse engineering",
    "cockpit flight direction",
]

VERBATIM_RULE_ECHO_SNIPPETS = [
    "Universal Automated Verification Standard",
    "Terminal Invariants & Grep Probing Exception",
    "Surgical Contiguous Edits Invariant (99.9% Tool Success)",
    "Audit revealed single contiguous block replacements achieve 99.9% tool success",
    "Context Preservation, Reactive Wait & Anti-Loop Discipline",
    "Trajectories <50 steps / <50k tokens maintain 0.8 errors/session",
    "The Artifact-First Planning Invariant (ADR-012) & Dynamic Aperture",
    "Human-in-the-Loop & Steering Alignment",
    "Universal Cleanroom Reverse Engineering & Reconstruction Invariants",
    "Cockpit Flight Direction & Dual-Auditor Gate",
]


def enforce_single_source_rules(
    workspace_dir: Path | str,
    config_dir: Optional[Path | str] = None,
    dry_run: bool = False,
    universal_rules_file: Optional[Path | str] = None,
) -> Dict[str, Any]:
    """
    Enforces single-source rule delivery across global plugin and workspace (Issue #70).
    Detects and strips duplicate universal rule blocks from <workspace>/.agents/rules/AGENTS.md
    and <workspace>/rules/AGENTS.md to eliminate token bloat and rule numbering collisions.

    Returns a dict with:
        workspace: str path
        pruned_files: List[str] of modified file paths
        removed_sections: List[str] of stripped rule section titles
        tokens_saved: int approximate token count saved
        chars_removed: int characters removed
        dry_run: bool
    """
    ws_root = Path(workspace_dir).resolve()
    agents_rules = ws_root / ".agents" / "rules" / "AGENTS.md"
    root_rules = ws_root / "rules" / "AGENTS.md"

    pruned_files: List[str] = []
    removed_sections: List[str] = []
    chars_removed = 0

    inheritance_notice = "<!-- Inherits Universal Invariants from Global Plugin: PSL-INV-001 through PSL-INV-008 -->\n\n"
    pruned_content: str = ""

    if agents_rules.exists() and not agents_rules.is_symlink():
        original_content = agents_rules.read_text(encoding="utf-8")
        sections = re.split(r"(?m)(?=^## )", original_content)
        kept_sections: List[str] = []
        file_removed_sections: List[str] = []

        preamble = sections[0]
        if "<!-- Inherits Universal Invariants from Global Plugin: PSL-INV-001 through PSL-INV-008 -->" not in preamble:
            match = re.search(r"((?:<!--.*?-->\n*)+)", preamble, re.DOTALL)
            if match and match.start() == 0:
                preamble = match.group(0) + inheritance_notice + preamble[match.end():]
            else:
                preamble = inheritance_notice + preamble
        kept_sections.append(preamble)

        for sec in sections[1:]:
            first_line = sec.split("\n", 1)[0].strip()
            is_universal = any(kw in first_line.lower() for kw in UNIVERSAL_SECTION_KEYWORDS)
            if is_universal:
                file_removed_sections.append(first_line)
            else:
                kept_sections.append(sec)

        pruned_content = "".join(kept_sections)
        if not pruned_content.endswith("\n"):
            pruned_content += "\n"

        if file_removed_sections or pruned_content != original_content:
            diff_chars = len(original_content) - len(pruned_content)
            if diff_chars > 0:
                chars_removed += diff_chars
            removed_sections.extend(file_removed_sections)
            pruned_files.append(str(agents_rules))
            if not dry_run:
                agents_rules.parent.mkdir(parents=True, exist_ok=True)
                agents_rules.write_text(pruned_content, encoding="utf-8")
    elif agents_rules.exists() and agents_rules.is_symlink():
        try:
            pruned_content = agents_rules.resolve().read_text(encoding="utf-8")
        except OSError:
            pruned_content = ""

    from harness.utils.workspace import is_harness_workspace

    if is_harness_workspace(ws_root):
        harness_rules = ws_root / "harness" / "rules" / "AGENTS.md"
        if harness_rules.is_symlink():
            if not dry_run:
                harness_rules.unlink()
        if pruned_content and (not harness_rules.exists() or (harness_rules.is_file() and harness_rules.read_text(encoding="utf-8") != pruned_content)):
            pruned_files.append(str(harness_rules))
            if not dry_run:
                harness_rules.parent.mkdir(parents=True, exist_ok=True)
                harness_rules.write_text(pruned_content, encoding="utf-8")

    else:
        # Handle root_rules symlink pointing to ../.agents/rules/AGENTS.md in consumer repositories
        target_link = Path("../.agents/rules/AGENTS.md")
        symlink_needed = False

        if root_rules.is_symlink():
            try:
                link_dst = os.readlink(root_rules)
                if link_dst != str(target_link):
                    symlink_needed = True
            except (OSError, ValueError):
                symlink_needed = True
        elif root_rules.exists() or agents_rules.exists():
            symlink_needed = True

        if symlink_needed:
            pruned_files.append(str(root_rules))
            if not dry_run:
                root_rules.parent.mkdir(parents=True, exist_ok=True)
                if root_rules.is_symlink() or root_rules.is_file():
                    root_rules.unlink()
                elif root_rules.is_dir():
                    shutil.rmtree(root_rules)
                root_rules.symlink_to(target_link)


    tokens_saved = chars_removed // 4
    return {
        "workspace": str(ws_root),
        "pruned_files": sorted(list(set(pruned_files))),
        "removed_sections": sorted(list(set(removed_sections))),
        "tokens_saved": tokens_saved,
        "chars_removed": chars_removed,
        "dry_run": dry_run,
    }


def lint_rule_echo(workspace_dir: Path | str) -> Dict[str, Any]:
    """
    Scans workspace skills and agent personas for verbatim universal rule block repetition.
    Returns findings summary.
    """
    ws_root = Path(workspace_dir).resolve()
    findings: List[Dict[str, Any]] = []
    scanned_files: List[str] = []

    scan_dirs = [
        ws_root / ".agents" / "skills",
        ws_root / ".agents" / "agents",
        ws_root / "harness" / "skills",
        ws_root / "harness" / "agents",
    ]

    for sdir in scan_dirs:
        if not sdir.is_dir():
            continue
        for md_file in sdir.glob("**/*.md"):
            if md_file.is_file() and not md_file.is_symlink():
                scanned_files.append(str(md_file))
                try:
                    text = md_file.read_text(encoding="utf-8")
                except OSError:
                    continue
                matches = [snippet for snippet in VERBATIM_RULE_ECHO_SNIPPETS if snippet in text]
                if matches:
                    findings.append({
                        "file": str(md_file),
                        "matched_echoes": matches,
                    })

    return {
        "workspace": str(ws_root),
        "clean": len(findings) == 0,
        "files_scanned": len(scanned_files),
        "echoes": findings,
    }
