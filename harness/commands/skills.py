# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Purrfect Software Limited (PSL)

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
    from harness.delivery.surfaces import find_workspace_root
    from harness.skills import get_skill, list_skills, sync_skills

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

    print(f"PSL Modular Skills ({len(skills)} available):")
    print("-" * 60)
    for s in skills:
        print(f"  • {s.name:<24} {s.description}")
    print()
    return 0
