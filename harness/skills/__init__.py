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


STACK_PRESETS: Dict[str, List[str]] = {
    "python": [
        "psl-stack-python",
        "psl-test-python",
        "psl-stack-backend",
    ],
    "typescript": [
        "psl-stack-typescript",
        "psl-test-node",
        "psl-stack-backend",
    ],
    "javascript": [
        "psl-stack-typescript",
        "psl-test-node",
        "psl-stack-backend",
    ],
    "rust": [
        "psl-test-cargo",
        "psl-stack-systems",
        "psl-stack-shell",
    ],
    "cargo": [
        "psl-test-cargo",
        "psl-stack-systems",
        "psl-stack-shell",
    ],
    "go": [
        "psl-test-go",
        "psl-stack-backend",
    ],
    "systems": [
        "psl-stack-systems",
        "psl-stack-shell",
    ],
    "shell": [
        "psl-stack-shell",
    ],
    "backend": [
        "psl-stack-backend",
        "db-ops",
    ],
}

GROUP_PRESETS: Dict[str, List[str]] = {
    "stack": [
        "psl-stack-python",
        "psl-stack-typescript",
        "psl-stack-shell",
        "psl-stack-systems",
        "psl-stack-backend",
    ],
    "testing": [
        "psl-test-python",
        "psl-test-node",
        "psl-test-cargo",
        "psl-test-go",
    ],
    "runners": [
        "psl-test-python",
        "psl-test-node",
        "psl-test-cargo",
        "psl-test-go",
    ],
    "ops": [
        "storage-ops",
        "audio-ops",
        "display-ops",
        "sec-forensics",
        "media-ops",
        "db-ops",
        "mesh-ops",
        "git-worktree-ops",
        "remote-ops",
    ],
    "workstation": [
        "storage-ops",
        "audio-ops",
        "display-ops",
        "sec-forensics",
        "media-ops",
        "db-ops",
        "mesh-ops",
        "git-worktree-ops",
    ],
    "workflow": [
        "agent-builder",
        "subagent-ladder",
        "milestone-handoff",
        "code-review",
        "psl-audit-toolkit",
    ],
    "ladder": [
        "agent-builder",
        "subagent-ladder",
        "milestone-handoff",
        "code-review",
    ],
}


def detect_workspace_stack(workspace_root: Optional[Path] = None) -> Optional[str]:
    """Detect workspace language stack from project files."""
    from harness.delivery.surfaces import find_workspace_root

    root = Path(workspace_root) if workspace_root else find_workspace_root()
    if (root / "tsconfig.json").is_file() or (root / "package.json").is_file():
        return "typescript"
    if (
        (root / "pyproject.toml").is_file()
        or (root / "requirements.txt").is_file()
        or (root / "setup.py").is_file()
    ):
        return "python"
    if (root / "Cargo.toml").is_file():
        return "rust"
    if (root / "go.mod").is_file():
        return "go"
    return None


def resolve_skills_to_sync(
    skill_names: Optional[List[str]] = None,
    group: Optional[str] = None,
    stack: Optional[str] = None,
    workspace_root: Optional[Path] = None,
) -> Optional[List[str]]:
    """Resolve list of skill names to sync based on explicit names, group, or stack."""
    resolved: List[str] = []

    if skill_names:
        resolved.extend(skill_names)

    if group:
        grp_norm = group.strip().lower()
        if grp_norm in GROUP_PRESETS:
            resolved.extend(GROUP_PRESETS[grp_norm])
        else:
            raise ValueError(
                f"Unknown skill group '{group}'. Choose from: {', '.join(sorted(GROUP_PRESETS.keys()))}"
            )

    if stack:
        stk_norm = stack.strip().lower()
        if stk_norm == "auto":
            detected = detect_workspace_stack(workspace_root)
            if detected and detected in STACK_PRESETS:
                resolved.extend(STACK_PRESETS[detected])
        elif stk_norm in STACK_PRESETS:
            resolved.extend(STACK_PRESETS[stk_norm])
        else:
            raise ValueError(
                f"Unknown stack preset '{stack}'. Choose from: {', '.join(sorted(STACK_PRESETS.keys()))}, auto"
            )

    if not skill_names and not group and not stack:
        return None

    seen: set[str] = set()
    result: List[str] = []
    for s in resolved:
        norm = s.strip().lower().replace("_", "-")
        if norm not in seen:
            seen.add(norm)
            result.append(s)
    return result


def sync_skills(
    target_dir: Optional[Path] = None,
    source_dir: Optional[Path] = None,
    skill_names: Optional[List[str]] = None,
    group: Optional[str] = None,
    stack: Optional[str] = None,
    dedup: bool = True,
    override: bool = False,
) -> List[Path]:
    """Synchronize skill definitions from harness/skills to .agents/skills."""
    src = source_dir or DEFAULT_SKILLS_DIR
    dst = target_dir or DEFAULT_TARGET_DIR
    dst.mkdir(parents=True, exist_ok=True)

    filter_names = resolve_skills_to_sync(
        skill_names=skill_names,
        group=group,
        stack=stack,
        workspace_root=dst.parent.parent if dst.parent.name == ".agents" else None,
    )
    norm_filter = (
        {s.strip().lower().replace("_", "-") for s in filter_names}
        if filter_names is not None
        else None
    )

    synced: List[Path] = []
    for spec in list_skills(src):
        name_norm = spec.name.lower().replace("_", "-")
        dir_norm = spec.path.parent.name.lower().replace("_", "-")
        if (
            norm_filter is not None
            and name_norm not in norm_filter
            and dir_norm not in norm_filter
        ):
            continue

        dest_dir = dst / spec.path.parent.name
        dest_file = dest_dir / "SKILL.md"

        if dest_file.exists() and not override:
            is_identical = dest_file.read_bytes() == spec.path.read_bytes()
            if dedup and is_identical:
                synced.append(dest_file)
                continue

        dest_dir.mkdir(parents=True, exist_ok=True)
        shutil.copy2(spec.path, dest_file)
        for child in spec.path.parent.iterdir():
            if child.is_file() and child.name != "SKILL.md":
                shutil.copy2(child, dest_dir / child.name)

        synced.append(dest_file)

    return synced
