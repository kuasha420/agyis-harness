# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Purrfect Software Limited (PSL)

"""
Modular skills management CLI command (ADR-014).
"""

from __future__ import annotations

import argparse
import json
import sys


def cmd_skills(args: argparse.Namespace) -> int:
    """Lists, inspects, or synchronizes modular product skills."""
    from harness.skills import get_skill, list_skills, sync_skills

    if getattr(args, "sync", False):
        synced = sync_skills()
        print(f"✔ Synchronized {len(synced)} skills to .agents/skills/:")
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
