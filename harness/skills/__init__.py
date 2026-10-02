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


def parse_frontmatter(content: str) -> Tuple[Dict[str, Any], str]:
    """Parse YAML frontmatter and markdown body from skill/rule files."""
    if not content.startswith("---"):
        return {}, content

    parts = content.split("---", 2)
    if len(parts) < 3:
        return {}, content

    raw_fm = parts[1]
    body = parts[2].lstrip()
    result: Dict[str, Any] = {}
    lines = raw_fm.strip().splitlines()
    i = 0

    while i < len(lines):
        line = lines[i]
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            i += 1
            continue

        if ":" in line and not line.startswith(" ") and not line.startswith("\t"):
            key, val = line.split(":", 1)
            key = key.strip()
            val = val.strip()

            if val in (">-", ">", "|", "|-"):
                buf: List[str] = []
                i += 1
                while i < len(lines) and (
                    lines[i].startswith("  ")
                    or lines[i].startswith("\t")
                    or not lines[i].strip()
                ):
                    if lines[i].strip():
                        buf.append(lines[i].strip())
                    i += 1
                joiner = " " if val in (">-", ">") else "\n"
                result[key] = joiner.join(buf)
                continue
            elif val == "":
                i += 1
                child_list: List[str] = []
                child_dict: Dict[str, Any] = {}
                is_list = False
                is_dict = False
                while i < len(lines) and (
                    lines[i].startswith("  ")
                    or lines[i].startswith("\t")
                    or not lines[i].strip()
                ):
                    cline = lines[i].strip()
                    if not cline:
                        i += 1
                        continue
                    if cline.startswith("- "):
                        is_list = True
                        child_list.append(cline[2:].strip())
                    elif ":" in cline:
                        is_dict = True
                        ck, cv = cline.split(":", 1)
                        ck = ck.strip()
                        cv = cv.strip()
                        if cv.lower() == "true":
                            child_dict[ck] = True
                        elif cv.lower() == "false":
                            child_dict[ck] = False
                        else:
                            child_dict[ck] = cv
                    i += 1
                if is_list:
                    result[key] = child_list
                elif is_dict:
                    result[key] = child_dict
                else:
                    result[key] = ""
                continue
            else:
                if val.lower() == "true":
                    result[key] = True
                elif val.lower() == "false":
                    result[key] = False
                elif (
                    val.startswith(('"', "'"))
                    and val.endswith(('"', "'"))
                    and len(val) >= 2
                ):
                    result[key] = val[1:-1]
                elif val.startswith("[") and val.endswith("]"):
                    inner = val[1:-1].strip()
                    if not inner:
                        result[key] = []
                    else:
                        result[key] = [
                            item.strip().strip("'\"")
                            for item in inner.split(",")
                            if item.strip()
                        ]
                elif val.startswith("{") and val.endswith("}"):
                    inner = val[1:-1].strip()
                    c_dict: Dict[str, Any] = {}
                    if inner:
                        for pair in inner.split(","):
                            if ":" in pair:
                                pk, pv = pair.split(":", 1)
                                pk = pk.strip().strip("'\"")
                                pv = pv.strip().strip("'\"")
                                if pv.lower() == "true":
                                    c_dict[pk] = True
                                elif pv.lower() == "false":
                                    c_dict[pk] = False
                                elif pv.isdigit():
                                    c_dict[pk] = int(pv)
                                else:
                                    c_dict[pk] = pv
                    result[key] = c_dict
                else:
                    result[key] = val
        i += 1

    return result, body


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
