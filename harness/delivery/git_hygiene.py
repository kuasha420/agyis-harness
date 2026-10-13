# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Arafat Zahan (@kuasha420)
# Corporate Stewardship & Infrastructure: Purrfect Software Limited (PSL)
# Governed by: ICARO-42/b Ordinance (Company-Supported Personal IP Framework)

"""
Git hygiene and exclusion configuration (ADR-030).
"""

from __future__ import annotations

import os
from pathlib import Path
import re
import subprocess
from typing import List

from harness.delivery.constants import GIT_EXCLUDE_PATTERNS
from harness.delivery.git_topology import (
    GitTopology,
    GitTopologyProbe,
    RemoteInfo,
    create_pull_request,
)


def configure_git_exclude(workspace_root: Path) -> Path:
    """
    Ensures .agents/artifacts/, .agents/teamwork/, .agents/archive/, *.patch, .agyis/, .psl/, .cache/, and scratch/ are excluded from git.

    Correctly recognizes worktrees where .git is a file containing:
        gitdir: <common_gitdir>/worktrees/<name>
    resolves the common gitdir, and appends required ignore patterns to .git/info/exclude.
    """
    ws = Path(workspace_root).resolve()
    git_entry = ws / ".git"
    if not git_entry.exists():
        raise FileNotFoundError(f"No .git entry found at workspace root {ws}")

    if git_entry.is_file():
        # Git worktree pointer file
        content = git_entry.read_text(encoding="utf-8").strip()
        m = re.match(r"^gitdir:\s*(.+)$", content, re.MULTILINE)
        if not m:
            raise ValueError(f"Malformed .git worktree pointer at {git_entry}: {content}")
        raw_gitdir = m.group(1).strip()
        gitdir_path = Path(raw_gitdir)
        if not gitdir_path.is_absolute():
            gitdir_path = (ws / gitdir_path).resolve()
        else:
            gitdir_path = gitdir_path.resolve()

        commondir_file = gitdir_path / "commondir"
        if commondir_file.is_file():
            cd_content = commondir_file.read_text(encoding="utf-8").strip()
            cd_path = Path(cd_content)
            if not cd_path.is_absolute():
                common_gitdir = (gitdir_path / cd_path).resolve()
            else:
                common_gitdir = cd_path.resolve()
        elif "worktrees" in gitdir_path.parts:
            common_gitdir = gitdir_path.parent.parent
        else:
            common_gitdir = gitdir_path
    elif git_entry.is_dir():
        common_gitdir = git_entry
    else:
        raise ValueError(f"Unsupported .git entry at {git_entry}")

    exclude_file = common_gitdir / "info" / "exclude"
    exclude_file.parent.mkdir(parents=True, exist_ok=True)

    existing_lines: List[str] = []
    if exclude_file.exists():
        existing_lines = [
            line.strip()
            for line in exclude_file.read_text(encoding="utf-8", errors="replace").splitlines()
        ]

    lines_to_add = [pat for pat in GIT_EXCLUDE_PATTERNS if pat not in existing_lines]
    if lines_to_add:
        with open(exclude_file, "a", encoding="utf-8") as f:
            if existing_lines and existing_lines[-1] != "":
                f.write("\n")
            f.write("# Agyis Harness Ignored Directories & Patterns\n")
            for pat in lines_to_add:
                f.write(f"{pat}\n")

    return exclude_file


def verify_zero_git_pollution(workspace_root: Path) -> List[str]:
    """
    Audits workspace repository status to ensure zero runtime or telemetry pollution.

    Checks for untracked database files, temporary test state files, or unignored
    scratch files that would violate clean-tree invariants.
    """
    ws = Path(workspace_root).resolve()
    if not ws.exists():
        return []

    polluting_patterns = [
        "telemetry.db*",
        "verification_state_*.json",
        "*.pyc",
        "__pycache__",
        ".coverage*",
        ".pytest_cache",
        "*.patch",
        "*.tar.gz",
    ]

    polluting_files: List[str] = []

    # 1. Use git status --porcelain if git repo exists
    git_dir = ws / ".git"
    if git_dir.exists():
        try:
            proc = subprocess.run(
                ["git", "status", "--porcelain"],
                cwd=ws,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                timeout=5,
                check=False,
            )
            if proc.returncode == 0:
                for line in proc.stdout.splitlines():
                    entry = line.strip()
                    if entry.startswith("??"):
                        rel_path = entry[2:].strip().strip('"')
                        base_name = Path(rel_path).name
                        if (
                            "telemetry.db" in base_name
                            or "verification_state_" in base_name
                            or base_name.endswith(".pyc")
                            or base_name in ("__pycache__", ".coverage", ".pytest_cache")
                            or base_name.endswith(".patch")
                            or "legacy-agent-backup-" in base_name
                        ):
                            polluting_files.append(rel_path)
                return sorted(polluting_files)
        except (OSError, subprocess.SubprocessError):
            pass

    # 2. Filesystem probe fallback
    for pattern in polluting_patterns:
        for match in ws.rglob(pattern):
            # Filter out intentional fixtures if inside tests/fixtures
            try:
                rel = match.relative_to(ws)
                if not str(rel).startswith("tests/"):
                    polluting_files.append(str(rel))
            except ValueError:
                pass

    return sorted(list(set(polluting_files)))


__all__ = [
    "GitTopology",
    "GitTopologyProbe",
    "RemoteInfo",
    "configure_git_exclude",
    "create_pull_request",
    "verify_zero_git_pollution",
]
