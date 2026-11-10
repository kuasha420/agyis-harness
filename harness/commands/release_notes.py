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
import sys
from typing import Any, Dict

from harness.delivery.release_notes import (
    collect_release_notes,
    sync_github_release,
)


def cmd_release_notes(args: argparse.Namespace) -> int:
    """
    Generate conventional release notes from git commits and PR references.
    """
    workspace_val = getattr(args, "workspace", None)
    repo_dir = Path(workspace_val).resolve() if workspace_val else Path.cwd().resolve()

    target_ref = getattr(args, "tag", None) or "HEAD"
    target_rev = getattr(args, "rev", None)
    base_ref = getattr(args, "base", None)
    output_path = getattr(args, "output", None)
    gh_release_tag = getattr(args, "gh_release", None)
    repo_url_override = getattr(args, "repo_url", None)
    is_json = getattr(args, "json", False)
    title = getattr(args, "title", None)
    prerelease = getattr(args, "prerelease", None)

    try:
        result = collect_release_notes(
            repo_dir=repo_dir,
            base_tag=base_ref,
            target_ref=target_ref,
            repo_url=repo_url_override,
            target_rev=target_rev,
        )
    except (ValueError, RuntimeError) as exc:
        print(f"❌ {exc}", file=sys.stderr)
        return 1

    if is_json:
        payload: Dict[str, Any] = {
            "success": True,
            "target_tag": result.target_tag,
            "base_tag": result.base_tag,
            "repo_url": result.repo_url,
            "compare_url": result.compare_url,
            "commits_count": result.commits_count,
            "categories": result.categories,
            "markdown": result.markdown,
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
            out_file.write_text(result.markdown, encoding="utf-8")
        if not output_path and not gh_release_tag:
            print(result.markdown)

    if gh_release_tag:
        ok, msg = sync_github_release(
            tag=gh_release_tag,
            notes_markdown=result.markdown,
            repo_dir=repo_dir,
            prerelease=prerelease,
            title=title,
        )
        if ok:
            print(f"✨ {msg}")
        else:
            print(f"❌ {msg}", file=sys.stderr)
            return 1

    return 0


__all__ = ["cmd_release_notes"]
