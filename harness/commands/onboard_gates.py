# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Arafat Zahan (@kuasha420)
# Corporate Stewardship & Infrastructure: Purrfect Software Limited (PSL)
# Governed by: ICARO-42/b Ordinance (Company-Supported Personal IP Framework)

"""
Onboarding REA provisioning, native verification gate, and atomic git commit helpers (ADR-031).
"""

from __future__ import annotations

import json
import os
from pathlib import Path
import re
import shlex
import subprocess
import sys
from typing import Any, Dict, List, Optional, Tuple

_MANIFEST_FILENAMES: Tuple[str, ...] = (
    "package.json",
    "Cargo.toml",
    "src-tauri/Cargo.toml",
    "native/Cargo.toml",
    "pyproject.toml",
    "Makefile",
    "makefile",
)


def resolve_workspace_rea_enabled(
    ws: Path,
    subproject_path: Path,
    rea: bool = False,
    experimental_rea: bool = False,
) -> bool:
    """Resolve REA activation from CLI flags or existing .agyis/.psl config.json."""
    if rea or experimental_rea:
        return True

    candidates: List[Path] = []
    for base in (subproject_path, ws):
        for rel in (".agyis/config.json", ".psl/config.json"):
            cand = base / rel
            if cand not in candidates:
                candidates.append(cand)

    for cfg_path in candidates:
        if not cfg_path.is_file():
            continue
        try:
            data = json.loads(cfg_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError, ValueError):
            continue
        if isinstance(data, dict) and (data.get("rea") or data.get("experimental_rea")):
            return True
    return False


def run_onboard_test_manifest_sync(
    subproject_path: Path,
    dry_run: bool = False,
) -> Optional[Dict[str, Any]]:
    """Generate or preview `.agyis/test_manifest.json` without mutating project manifests."""
    has_known_manifest = any((subproject_path / rel).is_file() for rel in _MANIFEST_FILENAMES)
    if not has_known_manifest:
        return None

    from harness.harmonize.test_runner import harmonize_test_runners

    res = harmonize_test_runners(
        subproject_path,
        dry_run=dry_run,
        apply=not dry_run,
        backup=False,
        mutate_package_json=False,
        write_manifest=not dry_run,
    )
    manifest_path = res.manifest_path or (subproject_path / ".agyis" / "test_manifest.json")

    return {
        "generated": (not dry_run) and manifest_path.is_file(),
        "planned": bool(dry_run),
        "path": str(manifest_path),
        "manifest_type": res.audit.manifest_type,
        "framework": res.audit.test_framework,
        "package_manager": res.audit.package_manager,
        "tiers": res.manifest_data.get("tiers") if isinstance(res.manifest_data, dict) else None,
        "scripts": res.manifest_data.get("scripts") if isinstance(res.manifest_data, dict) else None,
    }


def _guard_npx_no_download(
    cmd_tokens: Optional[List[str]],
    clean_cmd: str,
    cmd_env: Optional[Dict[str, str]],
    use_shell: bool,
) -> Tuple[Optional[List[str]], str, Optional[Dict[str, str]]]:
    """Ensure `npx` invocations inside onboard --verify never trigger network downloads."""
    env_out = dict(cmd_env) if cmd_env is not None else None
    if cmd_tokens and Path(cmd_tokens[0]).name == "npx":
        filtered = [tok for tok in cmd_tokens if tok not in ("-y", "--yes")]
        if "--no-install" not in filtered:
            filtered = [filtered[0], "--no-install", *filtered[1:]]
        if env_out is None:
            env_out = os.environ.copy()
        env_out["NPM_CONFIG_YES"] = "false"
        return filtered, " ".join(shlex.quote(t) for t in filtered), env_out

    if use_shell and re.search(r"\bnpx\b", clean_cmd):
        guarded = re.sub(
            r"\bnpx\b(?!\s+--no-install\b)",
            "npx --no-install",
            clean_cmd,
        )
        if env_out is None:
            env_out = os.environ.copy()
        env_out["NPM_CONFIG_YES"] = "false"
        return cmd_tokens, guarded, env_out

    return cmd_tokens, clean_cmd, env_out


def run_onboard_verification(subproject_path: Path, dry_run: bool) -> Dict[str, Any]:
    """Run native workspace test verification when configured, or fail cleanly on unconfigured test surfaces."""
    from harness.discovery import detect_project_test_runner, inject_non_interactive_guards
    from harness.discovery_manifest import (
        has_non_python_test_surface,
        has_python_unittest_files,
        resolve_manifest_full_command,
    )

    runner = resolve_manifest_full_command(subproject_path) or detect_project_test_runner(subproject_path)
    cmd_tokens: Optional[List[str]] = None
    cmd_env: Optional[Dict[str, str]] = None
    clean_cmd = ""
    use_shell = False

    if runner:
        clean_cmd, cmd_env = inject_non_interactive_guards(runner, cwd=subproject_path)
        if any(tok in clean_cmd for tok in ("&&", "||", ";", "*")):
            use_shell = True
        else:
            cmd_tokens = shlex.split(clean_cmd)
        cmd_tokens, clean_cmd, cmd_env = _guard_npx_no_download(cmd_tokens, clean_cmd, cmd_env, use_shell)
    elif has_python_unittest_files(subproject_path / "tests"):
        runner = "python3 -m unittest discover -s tests"
        clean_cmd, cmd_env = inject_non_interactive_guards(runner, cwd=subproject_path)
        cmd_tokens = [sys.executable, "-m", "unittest", "discover", "-s", "tests"]

    if not runner and not cmd_tokens:
        if has_non_python_test_surface(subproject_path):
            return {
                "ran": False,
                "passed": False,
                "skipped": False,
                "status": "no_executable_runner",
                "command": None,
                "exit_code": 1,
                "reason": "no_executable_runner",
                "error": "Non-Python manifest or test files found, but no executable test runner command resolved.",
            }
        return {"ran": False, "passed": True, "skipped": True, "command": None, "reason": "no_runner_detected"}
    if dry_run:
        return {"ran": False, "passed": True, "skipped": True, "command": runner, "reason": "dry-run"}

    try:
        proc = subprocess.run(
            clean_cmd if use_shell else cmd_tokens,
            shell=use_shell,
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
