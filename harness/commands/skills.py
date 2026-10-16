# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Arafat Zahan (@kuasha420)
# Corporate Stewardship & Infrastructure: Purrfect Software Limited (PSL)
# Governed by: ICARO-42/b Ordinance (Company-Supported Personal IP Framework)

"""
Modular skills management CLI command (ADR-014).
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from typing import List


def cmd_skills(args: argparse.Namespace) -> int:
    """Lists, inspects, or synchronizes modular product skills."""
    from harness.delivery.surfaces import enforce_single_source_skills, find_workspace_root
    from harness.skills import get_skill, list_skills, sync_skills

    if getattr(args, "prune_duplicates", False):
        ws_arg = getattr(args, "workspace", None)
        if ws_arg and ws_arg is not True:
            ws_root = Path(ws_arg).resolve()
        else:
            ws_root = find_workspace_root()

        config_dir = getattr(args, "config_dir", None)
        if config_dir is None:
            config_dir = Path.home() / ".gemini" / "config"
        else:
            config_dir = Path(config_dir).resolve()

        dry_run = getattr(args, "dry_run", False)

        removed = enforce_single_source_skills(
            config_dir=config_dir,
            workspace_dir=ws_root,
            dry_run=dry_run,
        )

        ws_removed = [p for p in removed if str(ws_root) in p]
        cfg_removed = [p for p in removed if str(ws_root) not in p]

        if getattr(args, "json", False):
            print(json.dumps({
                "workspace": str(ws_root),
                "dry_run": dry_run,
                "pruned_workspace": ws_removed,
                "pruned_config": cfg_removed,
                "total_pruned": len(removed),
            }, indent=2))
            return 0

        prefix = "Would prune" if dry_run else "Pruned"
        if removed:
            print(f"✔ {prefix} {len(removed)} duplicate skill(s):")
            for p in removed:
                print(f"  • {Path(p).name} ({p})")
        else:
            print(f"No duplicate skills found across workspace ({ws_root}) and config ({config_dir}).")
        return 0

    if getattr(args, "sync", False):
        target_dir = getattr(args, "target_dir", None)
        ws_arg = getattr(args, "workspace", None)
        if target_dir:
            dest = Path(target_dir)
        elif ws_arg and ws_arg is not True:
            dest = Path(ws_arg) / ".agents" / "skills"
        else:
            dest = find_workspace_root() / ".agents" / "skills"

        names: List[str] = []
        name_arg = getattr(args, "name", None)
        if name_arg:
            names.append(name_arg)
        skills_arg = getattr(args, "skills", None)
        if skills_arg:
            names.extend([s.strip() for s in skills_arg.split(",") if s.strip()])

        group_arg = getattr(args, "group", None)
        stack_arg = getattr(args, "stack", None)
        override_arg = getattr(args, "override", False)
        dedup_arg = not getattr(args, "no_dedup", False)

        try:
            synced = sync_skills(
                target_dir=dest,
                skill_names=names or None,
                group=group_arg,
                stack=stack_arg,
                dedup=dedup_arg,
                override=override_arg,
            )
        except ValueError as exc:
            sys.stderr.write(f"Error: {exc}\n")
            return 1

        label = "all"
        if names:
            label = f"skills={','.join(names)}"
        elif group_arg:
            label = f"group={group_arg}"
        elif stack_arg:
            label = f"stack={stack_arg}"

        print(f"✔ Synchronized {len(synced)} skill(s) ({label}) to {dest}:")
        for p in synced:
            print(f"  • {p.parent.name} -> {p}")
        return 0

    if getattr(args, "name", None):
        spec = get_skill(args.name)
        if not spec:
            sys.stderr.write(f"Error: Skill '{args.name}' not found.\n")
            return 1
        if getattr(args, "json", False):
            print(
                json.dumps(
                    {
                        "name": spec.name,
                        "description": spec.description,
                        "path": str(spec.path),
                        "frontmatter": spec.frontmatter,
                    },
                    indent=2,
                )
            )
            return 0
        print(f"Skill: {spec.name}")
        print(f"Path:  {spec.path}")
        print(f"Description:\n  {spec.description}\n")
        print("=" * 60)
        print(spec.body.strip())
        return 0

    skills = list_skills()
    if getattr(args, "json", False):
        print(
            json.dumps(
                [
                    {
                        "name": s.name,
                        "description": s.description,
                        "path": str(s.path),
                    }
                    for s in skills
                ],
                indent=2,
            )
        )
        return 0

    print(f"Agyis Modular Skills ({len(skills)} available):")
    print("-" * 60)
    for s in skills:
        print(f"  • {s.name:<24} {s.description}")
    print()
    return 0
