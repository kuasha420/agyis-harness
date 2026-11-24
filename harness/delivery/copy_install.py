# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Arafat Zahan (@kuasha420)
# Corporate Stewardship & Infrastructure: Purrfect Software Limited (PSL)
# Governed by: ICARO-42/b Ordinance (Company-Supported Personal IP Framework)

"""
Packaging and copy installation engine for Agyis harness (ADR-014, ADR-030).
"""

from __future__ import annotations

from pathlib import Path
import shutil
import subprocess
import sys
from typing import Callable, List, Optional


def build_frozen_wheel(source_dir: Path, output_dir: Path) -> Path:
    """Builds a binary wheel distribution using uv build (with pip fallback)."""
    if not (source_dir / "pyproject.toml").is_file():
        raise RuntimeError(
            f"Cannot build frozen wheel: pyproject.toml not found in {source_dir}. "
            "Use --copy mode when installing from a packaged wheel."
        )
    if shutil.which("uv"):
        cmd = ["uv", "build", "--wheel", "--out-dir", str(output_dir)]
    else:
        cmd = [
            sys.executable,
            "-m",
            "pip",
            "wheel",
            "--no-deps",
            "-w",
            str(output_dir),
            str(source_dir),
        ]

    res = subprocess.run(
        cmd,
        cwd=str(source_dir),
        capture_output=True,
        text=True,
    )
    if res.returncode != 0:
        raise RuntimeError(
            f"Release wheel build failed (exit code {res.returncode}): {res.stderr or res.stdout}"
        )
    wheels = list(output_dir.glob("*.whl"))
    if not wheels:
        raise RuntimeError(f"No wheel artifact found in build output directory {output_dir}")
    return wheels[0]


def copy_distributable_tree(
    source_dir: Path,
    target: Path,
    find_distributable_item: Callable[[str], Optional[Path]],
    skip_harness_package: bool = False,
) -> List[str]:
    """Copies distributable plugin assets from source to target directory."""
    installed_items: List[str] = []

    # 1. plugin.json
    plugin_src = find_distributable_item("plugin.json")
    if plugin_src and plugin_src.is_file():
        shutil.copy2(plugin_src, target / "plugin.json")
        installed_items.append("plugin.json")

    # 1b. assets/
    assets_src = find_distributable_item("assets")
    if assets_src and assets_src.is_dir():
        assets_dst = target / "assets"
        if assets_dst.is_symlink():
            assets_dst.unlink()
        elif assets_dst.exists():
            shutil.rmtree(assets_dst)
        shutil.copytree(
            assets_src,
            assets_dst,
            ignore=shutil.ignore_patterns("__pycache__", "*.pyc"),
        )
        installed_items.append("assets")

    # 2. harness/ package directory
    if not skip_harness_package:
        harness_src = source_dir / "harness"
        if harness_src.is_dir():
            harness_dst = target / "harness"
            if harness_dst.exists():
                shutil.rmtree(harness_dst)
            shutil.copytree(
                harness_src,
                harness_dst,
                ignore=shutil.ignore_patterns(
                    "__pycache__", "*.pyc", "*.pyo", "*.db*", "telemetry.db"
                ),
            )
            installed_items.append("harness")

    # 3. matrix.json
    matrix_src = find_distributable_item("matrix.json")
    if matrix_src and matrix_src.is_file():
        shutil.copy2(matrix_src, target / "matrix.json")
        installed_items.append("matrix.json")

    # 4. hooks.json
    hooks_src = find_distributable_item("hooks.json")
    if hooks_src and hooks_src.is_file():
        shutil.copy2(hooks_src, target / "hooks.json")
        installed_items.append("hooks.json")

    # 5. skills/
    skills_src = find_distributable_item("skills")
    if skills_src and skills_src.is_dir():
        skills_dst = target / "skills"
        if skills_dst.exists():
            shutil.rmtree(skills_dst)
        shutil.copytree(
            skills_src,
            skills_dst,
            ignore=shutil.ignore_patterns("__pycache__", "*.pyc"),
        )
        installed_items.append("skills")

    # 6. agents/
    agents_src = find_distributable_item("agents")
    if agents_src and agents_src.is_dir():
        agents_dst = target / "agents"
        if agents_dst.exists():
            shutil.rmtree(agents_dst)
        shutil.copytree(
            agents_src,
            agents_dst,
            ignore=shutil.ignore_patterns("__pycache__", "*.pyc"),
        )
        installed_items.append("agents")

    # 7. rules/
    rules_src = find_distributable_item("rules")
    global_candidates = [
        source_dir / "GLOBAL_AGENTS.md",
        source_dir / "harness" / "GLOBAL_AGENTS.md",
    ]
    if rules_src and rules_src.is_dir():
        global_candidates.append(rules_src / "GLOBAL_AGENTS.md")
    global_candidates.append(source_dir / "harness" / "rules" / "GLOBAL_AGENTS.md")
    global_rules_src = next((p for p in global_candidates if p.exists()), None)

    if (rules_src and rules_src.is_dir()) or global_rules_src is not None:
        rules_dst = target / "rules"
        if rules_dst.exists():
            shutil.rmtree(rules_dst)
        rules_dst.mkdir(parents=True, exist_ok=True)

        # Copy auxiliary markdown rules excluding repo-internal AGENTS.md
        if rules_src and rules_src.is_dir():
            for f in rules_src.glob("*.md"):
                if f.name not in ("AGENTS.md", "GLOBAL_AGENTS.md"):
                    shutil.copy2(f, rules_dst / f.name)

        # Scoped rule isolation: install GLOBAL_AGENTS.md into rules/AGENTS.md (Issue #53)
        if global_rules_src is not None:
            shutil.copy2(global_rules_src, rules_dst / "AGENTS.md")

        installed_items.append("rules")

    return installed_items
