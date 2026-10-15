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
from typing import Callable, List, Optional


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
    if rules_src and rules_src.is_dir():
        rules_dst = target / "rules"
        if rules_dst.exists():
            shutil.rmtree(rules_dst)
        shutil.copytree(
            rules_src,
            rules_dst,
            ignore=shutil.ignore_patterns("__pycache__", "*.pyc"),
        )
        installed_items.append("rules")

    return installed_items
