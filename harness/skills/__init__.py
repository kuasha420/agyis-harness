# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Purrfect Software Limited (PSL)

"""
PSL Modular Skills Registry & Discovery Engine.

Discovers, parses, and synchronizes modular product skills between
harness/skills/ and .agents/skills/.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
import shutil
from typing import Any, Dict, List, Optional, Tuple

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
DEFAULT_SKILLS_DIR = Path(__file__).resolve().parent
DEFAULT_TARGET_DIR = REPO_ROOT / ".agents" / "skills"


from harness.utils.frontmatter import parse_frontmatter


@dataclass(frozen=True)
class SkillSpec:
    name: str
    description: str
    path: Path
    body: str = ""
    frontmatter: Dict[str, Any] = field(default_factory=dict)


def list_skills(skills_dir: Optional[Path] = None) -> List[SkillSpec]:
    """Scan and list all modular skills in the specified skills directory."""
    src = skills_dir or DEFAULT_SKILLS_DIR
    if not src.exists() or not src.is_dir():
        return []

    specs: List[SkillSpec] = []
    for item in sorted(src.iterdir()):
        skill_file = item / "SKILL.md" if item.is_dir() else None
        if not skill_file or not skill_file.exists():
            continue

        content = skill_file.read_text(encoding="utf-8", errors="replace")
        fm, body = parse_frontmatter(content)
        name = str(fm.get("name", item.name))
        desc = str(fm.get("description", ""))

        specs.append(
            SkillSpec(
                name=name,
                description=desc,
                path=skill_file,
                body=body,
                frontmatter=fm,
            )
        )

    return specs


def get_skill(name: str, skills_dir: Optional[Path] = None) -> Optional[SkillSpec]:
    """Find a skill by name or directory name."""
    norm = name.strip().lower().replace("_", "-")
    for spec in list_skills(skills_dir):
        if (
            spec.name.lower().replace("_", "-") == norm
            or spec.path.parent.name.lower().replace("_", "-") == norm
        ):
            return spec
    return None


def sync_skills(
    target_dir: Optional[Path] = None, source_dir: Optional[Path] = None
) -> List[Path]:
    """Synchronize skill definitions from harness/skills to .agents/skills."""
    src = source_dir or DEFAULT_SKILLS_DIR
    dst = target_dir or DEFAULT_TARGET_DIR
    dst.mkdir(parents=True, exist_ok=True)

    synced: List[Path] = []
    for spec in list_skills(src):
        dest_dir = dst / spec.path.parent.name
        dest_dir.mkdir(parents=True, exist_ok=True)
        dest_file = dest_dir / "SKILL.md"
        shutil.copy2(spec.path, dest_file)
        synced.append(dest_file)

    return synced
