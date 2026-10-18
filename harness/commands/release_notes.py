# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Arafat Zahan (@kuasha420)
# Corporate Stewardship & Infrastructure: Purrfect Software Limited (PSL)
# Governed by: ICARO-42/b Ordinance (Company-Supported Personal IP Framework)

"""
Release notes generation CLI command handler (Milestone M1).
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import subprocess
import sys
from typing import Any, Dict

from harness.delivery.release_notes import (
    categorize_commits,
    find_previous_tag,
    format_markdown,
    generate_release_notes,
    get_repo_remote_url,
    parse_commits,
    sync_github_release,
)


def cmd_release_notes(args: argparse.Namespace) -> int:
    """
    Generate conventional release notes from git commits and PR references.
    """
    workspace_val = getattr(args, "workspace", None)
    repo_dir = Path(workspace_val).resolve() if workspace_val else Path.cwd().resolve()

    target_ref = getattr(args, "tag", None) or "HEAD"
    base_ref = getattr(args, "base", None)
    output_path = getattr(args, "output", None)
    gh_release_tag = getattr(args, "gh_release", None)
    repo_url_override = getattr(args, "repo_url", None)
    is_json = getattr(args, "json", False)

    resolved_base_ref = (
        base_ref if base_ref is not None else find_previous_tag(repo_dir, target_ref)
    )
    resolved_repo_url = repo_url_override or get_repo_remote_url(repo_dir)

    markdown = generate_release_notes(
        repo_dir=repo_dir,
        base_tag=resolved_base_ref,
        target_ref=target_ref,
        repo_url=resolved_repo_url,
    )

    if is_json:
        rev_range = (
            f"{resolved_base_ref}..{target_ref}"
            if resolved_base_ref
            else target_ref
        )
        try:
            res = subprocess.run(
                [
                    "git",
                    "log",
                    rev_range,
                    '--format=%x1e%H%x1f%h%x1f%an%x1f%ae%x1f%aI%x1f%s%x1f%b',
                    "--no-merges",
                ],
                cwd=repo_dir,
                capture_output=True,
                text=True,
                check=False,
                timeout=15,
            )
            raw_log = res.stdout if res.returncode == 0 else ""
        except (OSError, subprocess.SubprocessError):
            raw_log = ""

        commits = parse_commits(raw_log)
        categories = categorize_commits(commits)
        payload: Dict[str, Any] = {
            "success": True,
            "target_tag": target_ref,
            "base_tag": resolved_base_ref,
            "repo_url": resolved_repo_url,
            "commits_count": len(commits),
            "categories": categories,
            "markdown": markdown,
        }
        json_str = json.dumps(payload, indent=2)
        if output_path:
            out_file = Path(output_path).resolve()
            out_file.parent.mkdir(parents=True, exist_ok=True)
            out_file.write_text(json_str, encoding="utf-8")
        else:
            print(json_str)
    else:
        if output_path:
            out_file = Path(output_path).resolve()
            out_file.parent.mkdir(parents=True, exist_ok=True)
            out_file.write_text(markdown, encoding="utf-8")
        if not output_path and not gh_release_tag:
            print(markdown)

    if gh_release_tag:
        ok, msg = sync_github_release(
            tag=gh_release_tag,
            notes_markdown=markdown,
            repo_dir=repo_dir,
        )
        if ok:
            print(f"✨ {msg}")
        else:
            print(f"❌ {msg}", file=sys.stderr)
            return 1

    return 0


__all__ = ["cmd_release_notes"]
