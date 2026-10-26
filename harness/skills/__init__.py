# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Arafat Zahan (@kuasha420)
# Corporate Stewardship & Infrastructure: Purrfect Software Limited (PSL)
# Governed by: ICARO-42/b Ordinance (Company-Supported Personal IP Framework)

"""
PSL Modular Skills Registry & Discovery Engine.

Discovers, parses, and synchronizes modular product skills between
harness/skills/ and .agents/skills/.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
import shutil
from typing import Any, Dict, List, Optional, Set, Tuple, Union

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


LANGUAGE_RUNTIME_PRESETS: Dict[str, List[str]] = {
    "typescript": [
        "psl-stack-typescript",
        "psl-test-node",
    ],
    "node": [
        "psl-stack-typescript",
        "psl-test-node",
    ],
    "javascript": [
        "psl-stack-typescript",
        "psl-test-node",
    ],
    "python": [
        "psl-stack-python",
        "psl-test-python",
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
    ],
    "systems": [
        "psl-stack-systems",
        "psl-stack-shell",
    ],
    "shell": [
        "psl-stack-shell",
    ],
}

ARCHITECTURAL_ROLE_PRESETS: Dict[str, List[str]] = {
    "backend": [
        "psl-stack-backend",
        "db-ops",
    ],
    "frontend": [
        "modern-web-guidance",
    ],
    "fullstack": [
        "modern-web-guidance",
        "psl-stack-backend",
        "db-ops",
    ],
    "mobile": [
        "android-cli",
    ],
    "desktop_gui": [
        "display-ops",
    ],
    "cli": [],
    "library": [],
    "media": [
        "media-ops",
    ],
    "audio": [
        "audio-ops",
    ],
    "infra": [
        "mesh-ops",
        "remote-ops",
        "sec-forensics",
        "storage-ops",
    ],
}

# Backward compatibility mapping for STACK_PRESETS
STACK_PRESETS: Dict[str, List[str]] = {
    **LANGUAGE_RUNTIME_PRESETS,
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
        "psl-test-harmonize",
    ],
    "runners": [
        "psl-test-python",
        "psl-test-node",
        "psl-test-cargo",
        "psl-test-go",
        "psl-test-harmonize",
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
    "resilience": [
        "powerloss-resume",
        "db-ops",
        "storage-ops",
    ],
    "continuity": [
        "graceful-parking",
        "milestone-handoff",
        "git-worktree-ops",
    ],
}


def detect_workspace_stack(
    workspace_root: Optional[Path] = None,
    subproject: Optional[Union[Path, str]] = None,
) -> Optional[str]:
    """Detect workspace language stack from project files, with subproject and shell support."""
    from harness.delivery.surfaces import find_workspace_root

    root = Path(workspace_root) if workspace_root else find_workspace_root()
    if subproject:
        root = (root / subproject).resolve()

    if not root.is_dir():
        return None

    # Multi-factor TS vs JS separation
    has_tsconfig = (root / "tsconfig.json").is_file()
    has_jsconfig = (root / "jsconfig.json").is_file()
    has_package_json = (root / "package.json").is_file()

    if has_tsconfig:
        return "typescript"

    if has_jsconfig:
        return "javascript"

    if has_package_json:
        # Inspect package.json dependencies and source files to differentiate TS vs JS
        is_ts = False
        try:
            import json

            pkg_data = json.loads((root / "package.json").read_text(encoding="utf-8"))
            deps = {
                **pkg_data.get("dependencies", {}),
                **pkg_data.get("devDependencies", {}),
            }
            if "typescript" in deps:
                is_ts = True
        except Exception:
            pass

        if not is_ts:
            try:
                # Check for any .ts or .tsx files in root or root/src
                ts_files = any(
                    p.is_file() and p.suffix in (".ts", ".tsx") for p in root.iterdir()
                )
                src_dir = root / "src"
                if not ts_files and src_dir.is_dir():
                    ts_files = any(
                        p.is_file() and p.suffix in (".ts", ".tsx")
                        for p in src_dir.iterdir()
                    )
                if ts_files:
                    is_ts = True
            except OSError:
                pass

        if is_ts:
            return "typescript"

        # Check if there are JS files (.js, .jsx, .mjs, .cjs)
        try:
            js_files = any(
                p.is_file() and p.suffix in (".js", ".jsx", ".mjs", ".cjs")
                for p in root.iterdir()
            )
            src_dir = root / "src"
            if not js_files and src_dir.is_dir():
                js_files = any(
                    p.is_file() and p.suffix in (".js", ".jsx", ".mjs", ".cjs")
                    for p in src_dir.iterdir()
                )
            if js_files:
                return "javascript"
        except OSError:
            pass

        # Default fallback for package.json without explicit indicators
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
    if (
        (root / "Makefile").is_file()
        or (root / "CMakeLists.txt").is_file()
        or (root / "meson.build").is_file()
        or (root / "flake.nix").is_file()
        or (root / "PKGBUILD").is_file()
    ):
        return "systems"

    # Shell script detection: *.sh files in root or scripts/ or bin/
    try:
        if any(p.is_file() and p.name.endswith(".sh") for p in root.iterdir()):
            return "shell"
        for sub in ("bin", "scripts"):
            sub_p = root / sub
            if sub_p.is_dir() and any(
                p.is_file() and p.name.endswith(".sh") for p in sub_p.iterdir()
            ):
                return "shell"
    except OSError:
        pass

    return None


def detect_workspace_role(
    workspace_root: Optional[Path] = None,
    subproject: Optional[Union[Path, str]] = None,
) -> Optional[str]:
    """
    Detects architectural role from manifests and dependencies.
    Returns: 'backend', 'frontend', 'fullstack', 'mobile', 'desktop_gui', or None.
    """
    from harness.delivery.surfaces import find_workspace_root

    root = Path(workspace_root) if workspace_root else find_workspace_root()
    if subproject:
        root = (root / subproject).resolve()

    if not root.is_dir():
        return None

    has_frontend = False
    has_backend = False

    # 1. Inspect package.json
    pkg_json = root / "package.json"
    if pkg_json.is_file():
        try:
            import json

            data = json.loads(pkg_json.read_text(encoding="utf-8"))
            deps = {
                **data.get("dependencies", {}),
                **data.get("devDependencies", {}),
            }
            deps_lower = {k.lower(): v for k, v in deps.items()}

            # Mobile check
            if (
                "react-native" in deps_lower
                or "expo" in deps_lower
                or (root / "android").is_dir()
                or (root / "ios").is_dir()
            ):
                return "mobile"

            # Desktop GUI check
            if "electron" in deps_lower or "@tauri-apps/api" in deps_lower:
                return "desktop_gui"

            # Fullstack frameworks
            if any(
                f in deps_lower
                for f in (
                    "next",
                    "remix",
                    "@remix-run/node",
                    "nuxt",
                    "@sveltejs/kit",
                    "astro",
                )
            ):
                has_frontend = True
                has_backend = True

            # Frontend libraries
            if any(
                f in deps_lower
                for f in (
                    "react",
                    "vue",
                    "svelte",
                    "vite",
                    "tailwindcss",
                    "@angular/core",
                    "solid-js",
                    "preact",
                )
            ):
                has_frontend = True

            # Backend libraries
            if any(
                b in deps_lower
                for b in (
                    "express",
                    "fastify",
                    "@nestjs/core",
                    "koa",
                    "@prisma/client",
                    "prisma",
                    "typeorm",
                    "sequelize",
                    "mongoose",
                    "pg",
                    "mysql2",
                    "knex",
                    "sqlite3",
                )
            ):
                has_backend = True
        except Exception:
            pass

    # 2. Inspect Python manifests
    pyproj = root / "pyproject.toml"
    reqs = root / "requirements.txt"
    setup_py = root / "setup.py"
    py_text = ""
    for pf in (pyproj, reqs, setup_py):
        if pf.is_file():
            try:
                py_text += (
                    pf.read_text(encoding="utf-8", errors="replace").lower() + "\n"
                )
            except Exception:
                pass

    if py_text:
        # Desktop GUI
        if any(
            gui in py_text
            for gui in ("pyqt5", "pyqt6", "pyside2", "pyside6", "kivy", "wxpython")
        ):
            return "desktop_gui"
        # Backend / Database
        if any(
            be in py_text
            for be in (
                "fastapi",
                "django",
                "flask",
                "sqlalchemy",
                "alembic",
                "tortoise-orm",
                "psycopg",
                "databases",
                "sqlmodel",
                "peewee",
            )
        ):
            has_backend = True

    # 3. Inspect Go manifests
    go_mod = root / "go.mod"
    if go_mod.is_file():
        try:
            go_text = go_mod.read_text(encoding="utf-8", errors="replace").lower()
            if any(
                be in go_text
                for be in (
                    "gorm.io",
                    "github.com/gin-gonic/gin",
                    "github.com/jackc/pgx",
                    "github.com/jmoiron/sqlx",
                    "github.com/labstack/echo",
                    "github.com/go-chi/chi",
                    "github.com/lib/pq",
                )
            ):
                has_backend = True
        except Exception:
            pass

    # 4. Inspect Rust manifests
    cargo = root / "Cargo.toml"
    if cargo.is_file():
        try:
            cargo_text = cargo.read_text(encoding="utf-8", errors="replace").lower()
            if any(gui in cargo_text for gui in ("tauri", "egui", "iced", "slint")):
                return "desktop_gui"
            if any(
                be in cargo_text
                for be in ("actix-web", "axum", "rocket", "diesel", "sqlx", "sea-orm")
            ):
                has_backend = True
        except Exception:
            pass

    # 5. Infrastructure indicators
    for compose_name in ("docker-compose.yml", "compose.yaml", "docker-compose.yaml"):
        dc_file = root / compose_name
        if dc_file.is_file():
            try:
                dc_text = dc_file.read_text(
                    encoding="utf-8", errors="replace"
                ).lower()
                if any(
                    db in dc_text
                    for db in ("postgres", "mysql", "mariadb", "mongo", "redis")
                ):
                    has_backend = True
            except Exception:
                pass
            break

    if has_frontend and has_backend:
        return "fullstack"
    if has_backend:
        return "backend"
    if has_frontend:
        return "frontend"
    return None


def is_monorepo(workspace_root: Path) -> bool:
    """Evaluates whether workspace root exhibits monorepo orchestrator characteristics."""
    root = Path(workspace_root)
    if (
        (root / "pnpm-workspace.yaml").is_file()
        or (root / "turbo.json").is_file()
        or (root / "lerna.json").is_file()
        or (root / "nx.json").is_file()
    ):
        return True

    pkg_json = root / "package.json"
    if pkg_json.is_file():
        try:
            import json

            data = json.loads(pkg_json.read_text(encoding="utf-8"))
            if "workspaces" in data:
                return True
        except Exception:
            pass

    for parent in ("apps", "services", "packages", "modules"):
        p = root / parent
        if p.is_dir():
            try:
                if any(c.is_dir() and not c.name.startswith(".") for c in p.iterdir()):
                    return True
            except OSError:
                pass
    return False


def detect_monorepo_stack(workspace_root: Path) -> Tuple[Set[str], Set[str]]:
    """
    Sweeps child directories at bounded depth 2 across standard monorepo directories:
    apps/, services/, packages/, modules/.

    Returns (detected_languages, detected_roles).
    Preserves sub-second execution benchmark by strictly avoiding recursive walks.
    """
    root = Path(workspace_root)
    detected_languages: Set[str] = set()
    detected_roles: Set[str] = set()

    # Root manifest check
    root_lang = detect_workspace_stack(root)
    if root_lang:
        detected_languages.add(root_lang)
    root_role = detect_workspace_role(root)
    if root_role:
        detected_roles.add(root_role)

    for parent_name in ("apps", "services", "packages", "modules"):
        parent_dir = root / parent_name
        if not parent_dir.is_dir():
            continue

        try:
            for child in parent_dir.iterdir():
                if not child.is_dir() or child.name.startswith("."):
                    continue

                lang = detect_workspace_stack(child)
                if lang:
                    detected_languages.add(lang)

                role = detect_workspace_role(child)
                if role:
                    detected_roles.add(role)
        except OSError:
            continue

    return detected_languages, detected_roles


def resolve_skills_to_sync(
    skill_names: Optional[List[str]] = None,
    group: Optional[str] = None,
    stack: Optional[str] = None,
    role: Optional[str] = None,
    workspace_root: Optional[Path] = None,
    subproject: Optional[Union[Path, str]] = None,
) -> Optional[List[str]]:
    """Resolve list of skill names to sync based on explicit names, group, stack, or role."""
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
            target_ws = Path(workspace_root) if workspace_root else None
            if target_ws and subproject:
                target_ws = (target_ws / subproject).resolve()

            if target_ws and is_monorepo(target_ws) and not subproject:
                mono_langs, mono_roles = detect_monorepo_stack(target_ws)
                for l in mono_langs:
                    if l in LANGUAGE_RUNTIME_PRESETS:
                        resolved.extend(LANGUAGE_RUNTIME_PRESETS[l])
                if role is None:
                    for r in mono_roles:
                        if r in ARCHITECTURAL_ROLE_PRESETS:
                            resolved.extend(ARCHITECTURAL_ROLE_PRESETS[r])
            else:
                detected = detect_workspace_stack(target_ws)
                if detected and detected in LANGUAGE_RUNTIME_PRESETS:
                    resolved.extend(LANGUAGE_RUNTIME_PRESETS[detected])
                if role is None and target_ws:
                    detected_r = detect_workspace_role(target_ws)
                    if detected_r and detected_r in ARCHITECTURAL_ROLE_PRESETS:
                        resolved.extend(ARCHITECTURAL_ROLE_PRESETS[detected_r])
        elif stk_norm in STACK_PRESETS:
            resolved.extend(STACK_PRESETS[stk_norm])
        else:
            raise ValueError(
                f"Unknown stack preset '{stack}'. Choose from: {', '.join(sorted(STACK_PRESETS.keys()))}, auto"
            )

    if role:
        role_norm = role.strip().lower()
        if role_norm in ARCHITECTURAL_ROLE_PRESETS:
            resolved.extend(ARCHITECTURAL_ROLE_PRESETS[role_norm])
        else:
            raise ValueError(
                f"Unknown architectural role '{role}'. Choose from: {', '.join(sorted(ARCHITECTURAL_ROLE_PRESETS.keys()))}"
            )

    if not skill_names and not group and not stack and not role:
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
    role: Optional[str] = None,
    subproject: Optional[Union[Path, str]] = None,
    dedup: bool = True,
    override: bool = False,
) -> List[Path]:
    """Synchronize skill definitions from harness/skills to .agents/skills."""
    src = source_dir or DEFAULT_SKILLS_DIR
    dst = target_dir or DEFAULT_TARGET_DIR
    dst.mkdir(parents=True, exist_ok=True)

    ws_root = (
        dst.parent.parent
        if dst.parent.name == ".agents"
        else (
            dst.parent
            if (
                (dst.parent / "pyproject.toml").is_file()
                or (dst.parent / "package.json").is_file()
                or (dst.parent / "Cargo.toml").is_file()
                or (dst.parent / "go.mod").is_file()
                or (dst.parent / "Makefile").is_file()
                or (dst.parent / "CMakeLists.txt").is_file()
                or (dst.parent / "meson.build").is_file()
                or (dst.parent / "flake.nix").is_file()
                or (dst.parent / "PKGBUILD").is_file()
            )
            else None
        )
    )
    filter_names = resolve_skills_to_sync(
        skill_names=skill_names,
        group=group,
        stack=stack,
        role=role,
        workspace_root=ws_root,
        subproject=subproject,
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
            elif child.is_dir() and not child.name.startswith("."):
                shutil.copytree(child, dest_dir / child.name, dirs_exist_ok=True)

        synced.append(dest_file)

    return synced


__all__ = [
    "ARCHITECTURAL_ROLE_PRESETS",
    "DEFAULT_SKILLS_DIR",
    "DEFAULT_TARGET_DIR",
    "GROUP_PRESETS",
    "LANGUAGE_RUNTIME_PRESETS",
    "STACK_PRESETS",
    "SkillSpec",
    "detect_monorepo_stack",
    "detect_workspace_role",
    "detect_workspace_stack",
    "get_skill",
    "is_monorepo",
    "list_skills",
    "parse_frontmatter",
    "resolve_skills_to_sync",
    "sync_skills",
]
