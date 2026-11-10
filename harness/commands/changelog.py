# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Arafat Zahan (@kuasha420)
# Corporate Stewardship & Infrastructure: Purrfect Software Limited (PSL)
# Governed by: ICARO-42/b Ordinance (Company-Supported Personal IP Framework)

"""
Native Keep-a-Changelog CLI command handler (`agyis changelog` / `changelogs`).
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from typing import Any, Dict

from harness.delivery.changelog import backfill_changelog, generate_changelog


def cmd_changelog(args: argparse.Namespace) -> int:
    """
    Generate, preview, or update Keep-a-Changelog entries in CHANGELOG.md.
    """
    workspace_val = getattr(args, "workspace", None)
    repo_dir = Path(workspace_val).resolve() if workspace_val else Path.cwd().resolve()

    target_tag = getattr(args, "tag", None)
    base_ref = getattr(args, "base", None)
    target_rev = getattr(args, "rev", None)
    release_date = getattr(args, "date", None)
    file_arg = getattr(args, "file", None)
    write_flag = bool(getattr(args, "write", False))
    backfill_flag = bool(getattr(args, "backfill", False))
    is_json = bool(getattr(args, "json", False))
    repo_url_override = getattr(args, "repo_url", None)
    style = getattr(args, "style", "canonical") or "canonical"

    try:
        if backfill_flag:
            result = backfill_changelog(
                repo_dir=repo_dir,
                changelog_path=file_arg,
                repo_url=repo_url_override,
                style=style,
                include_unreleased=True,
                target_rev=target_rev,
                base_tag=base_ref,
                write=write_flag,
            )
        else:
            result = generate_changelog(
                repo_dir=repo_dir,
                tag=target_tag,
                base_tag=base_ref,
                target_rev=target_rev,
                release_date=release_date,
                repo_url=repo_url_override,
                style=style,
                changelog_path=file_arg,
                write=write_flag,
            )
    except (ValueError, RuntimeError) as exc:
        print(f"❌ {exc}", file=sys.stderr)
        return 1

    if is_json:
        payload: Dict[str, Any] = {
            "success": True,
            **result.to_dict(),
        }
        print(json.dumps(payload, indent=2))
    elif write_flag:
        versions_summary = ", ".join(result.updated_versions) or result.version
        print(f"✨ Updated {result.file_path} ({versions_summary})")
    elif backfill_flag:
        print(result.document_markdown, end="")
    else:
        print(result.section_markdown)

    return 0


__all__ = ["cmd_changelog"]
