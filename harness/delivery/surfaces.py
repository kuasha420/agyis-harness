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
