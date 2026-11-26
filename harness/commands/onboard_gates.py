# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Arafat Zahan (@kuasha420)
# Corporate Stewardship & Infrastructure: Purrfect Software Limited (PSL)
# Governed by: ICARO-42/b Ordinance (Company-Supported Personal IP Framework)

"""
Onboarding REA provisioning, native verification gate, and atomic git commit helpers (ADR-031).
"""

from __future__ import annotations

from pathlib import Path
import shlex
import subprocess
import sys
from typing import Any, Dict, List, Optional, Tuple


def run_onboard_verification(subproject_path: Path, dry_run: bool) -> Dict[str, Any]:
    """Run native workspace test verification when configured, or skip cleanly if absent."""
    from harness.discovery import detect_project_test_runner, inject_non_interactive_guards

    runner = detect_project_test_runner(subproject_path)
    cmd_tokens: Optional[List[str]] = None
    cmd_env: Optional[Dict[str, str]] = None
    if runner:
        clean_cmd, cmd_env = inject_non_interactive_guards(runner)
        cmd_tokens = shlex.split(clean_cmd)
    elif (subproject_path / "tests").is_dir() and list((subproject_path / "tests").glob("test_*.py")):
        runner = "python3 -m unittest discover -s tests"
        _, cmd_env = inject_non_interactive_guards(runner)
        cmd_tokens = [sys.executable, "-m", "unittest", "discover", "-s", "tests"]

    if not cmd_tokens:
        return {"ran": False, "passed": True, "skipped": True, "command": None, "reason": "no_runner_detected"}
    if dry_run:
        return {"ran": False, "passed": True, "skipped": True, "command": runner, "reason": "dry-run"}

    try:
        proc = subprocess.run(
            cmd_tokens,
            cwd=subproject_path,
            env=cmd_env,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            timeout=120,
            check=False,
        )
    except (subprocess.SubprocessError, OSError) as exc:
        return {"ran": True, "passed": False, "skipped": False, "command": runner, "exit_code": 1, "error": str(exc)}

    out_tail = (proc.stderr or proc.stdout or "").strip()[-500:]
    return {
        "ran": True,
        "passed": proc.returncode == 0,
        "skipped": False,
        "command": runner,
        "exit_code": proc.returncode,
        "error": out_tail if proc.returncode != 0 else None,
    }


def commit_onboarded_files(
    ws: Path,
    subproject: Optional[str],
    include_legacy_agent: bool,
) -> Tuple[bool, Optional[str], Optional[str]]:
    """Stage unignored onboarded artifacts explicitly and commit atomically."""
    base = Path(subproject) if subproject else Path(".")
    rels = [
        "AGENTS.md",
        ".agents/rules",
        ".agents/skills",
        ".agents/agents",
        ".agents/ledger",
    ]
    if include_legacy_agent:
        rels.append(".agent")
    candidates = [(base / r).as_posix() if base != Path(".") else r for r in rels]

    stage_paths: List[str] = []
    for cand in candidates:
        ign = subprocess.run(
            ["git", "check-ignore", "-q", cand],
            cwd=ws,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=10,
            check=False,
        )
        if ign.returncode == 0:
            continue
        if (ws / cand).exists():
            stage_paths.append(cand)
            continue
        ls_proc = subprocess.run(
            ["git", "ls-files", "--error-unmatch", cand],
            cwd=ws,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=10,
            check=False,
        )
        if ls_proc.returncode == 0:
            stage_paths.append(cand)

    if not stage_paths:
        return False, None, None

    add_proc = subprocess.run(
        ["git", "add", "-A", "--", *stage_paths],
        cwd=ws,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        timeout=15,
        check=False,
    )
    if add_proc.returncode != 0:
        return False, None, (add_proc.stderr or add_proc.stdout or "git add failed").strip()

    diff_cached = subprocess.run(
        ["git", "diff", "--cached", "--quiet"],
        cwd=ws,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        timeout=10,
        check=False,
    )
    if diff_cached.returncode == 0:
        return False, None, None

    commit_proc = subprocess.run(
        ["git", "commit", "-m", "chore: onboard workspace to Agyis Harness"],
        cwd=ws,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        timeout=15,
        check=False,
    )
    if commit_proc.returncode != 0:
        return False, None, (commit_proc.stderr or commit_proc.stdout or "git commit failed").strip()

    sha_proc = subprocess.run(
        ["git", "rev-parse", "--short", "HEAD"],
        cwd=ws,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        timeout=10,
        check=False,
    )
    sha = sha_proc.stdout.strip() if sha_proc.returncode == 0 else None
    return True, sha, None
