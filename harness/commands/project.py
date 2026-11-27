# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Arafat Zahan (@kuasha420)
# Corporate Stewardship & Infrastructure: Purrfect Software Limited (PSL)
# Governed by: ICARO-42/b Ordinance (Company-Supported Personal IP Framework)

"""
Antigravity Project Registry CLI Command (`agyis project {list,ensure}`).
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from typing import Any, Dict, List

from harness.delivery.projects import (
    ensure_project_registered,
    list_registered_projects,
    resolve_projects_config_dir,
)
from harness.utils import theme


def _format_list_output(projects: List[Dict[str, Any]], config_dir: Path) -> str:
    """Format registered Antigravity projects as a themed terminal report."""
    lines: List[str] = [
        theme.banner(
            "Antigravity Project Registry",
            subtitle=f"Config Dir: {config_dir / 'projects'}",
            badge_label=f"{len(projects)} FOUND",
            status="PASS" if projects else "INFO",
        )
    ]
    if not projects:
        lines.append("  " + theme.badge("INFO", "No registered Antigravity projects found."))
        lines.append(theme.rule("━"))
        return "\n".join(lines)

    rows: List[List[str]] = []
    for proj in projects:
        kind = "git" if proj.get("is_git_folder") else "folder"
        branch = proj.get("default_branch") or "-"
        uris = proj.get("folder_uris") or []
        uri_display = ", ".join(uris) if uris else "-"
        proj_id = str(proj.get("id") or "")
        short_id = proj_id[:8] if len(proj_id) > 8 else proj_id
        rows.append([
            proj.get("name") or "(unnamed)",
            short_id,
            kind,
            branch,
            uri_display,
        ])

    lines.append(theme.format_table(["Name", "ID", "Type", "Branch", "Folder URI(s)"], rows))
    lines.append(theme.rule("━"))
    return "\n".join(lines)


def _handle_list(args: argparse.Namespace, *, is_json: bool) -> int:
    config_dir = getattr(args, "config_dir", None)
    resolved_cfg = resolve_projects_config_dir(config_dir)
    projects = list_registered_projects(config_dir=resolved_cfg)

    if is_json:
        print(
            json.dumps(
                {
                    "success": True,
                    "config_dir": str(resolved_cfg),
                    "projects_dir": str(resolved_cfg / "projects"),
                    "count": len(projects),
                    "projects": projects,
                },
                indent=2,
            )
        )
        return 0

    print(_format_list_output(projects, resolved_cfg))
    return 0


def _handle_ensure(args: argparse.Namespace, *, is_json: bool) -> int:
    raw_path = getattr(args, "path", None) or Path.cwd()
    config_dir = getattr(args, "config_dir", None)
    name = getattr(args, "name", None)
    branch = getattr(args, "branch", None)
    dry_run = bool(getattr(args, "dry_run", False))

    result = ensure_project_registered(
        workspace_path=raw_path,
        config_dir=config_dir,
        name=name,
        default_branch=branch,
        dry_run=dry_run,
    )

    if is_json:
        print(json.dumps(result, indent=2))
        return 0 if result.get("success") else 1

    if not result.get("success"):
        err_msg = str(result.get("error") or "Failed to register project")
        sys.stderr.write(theme.badge("FAIL", f"Error: {err_msg}", stream=sys.stderr) + "\n")
        return 1

    action = result.get("action")
    if action == "already_registered":
        badge_msg = f"Project already registered: {result['name']} ({result['project_id']})"
    elif action == "would_create":
        badge_msg = f"[DRY-RUN] Would register project: {result['name']} ({result['project_id']})"
    else:
        badge_msg = f"Registered project: {result['name']} ({result['project_id']})"

    print(theme.badge("PASS", badge_msg))
    print(f"  • Folder URI:     {result.get('folder_uri')}")
    print(f"  • Default Branch: {result.get('default_branch') or '-'}")
    print(f"  • Project File:   {result.get('project_file')}")
    return 0


def cmd_project(args: argparse.Namespace) -> int:
    """Handle `agyis project {list,ensure}` subcommands."""
    action = getattr(args, "project_action", None) or "list"
    is_json = bool(getattr(args, "json", False))

    if action == "list":
        return _handle_list(args, is_json=is_json)
    if action == "ensure":
        return _handle_ensure(args, is_json=is_json)

    if is_json:
        print(json.dumps({"success": False, "error": f"Unknown project action: {action}"}, indent=2))
    else:
        sys.stderr.write(theme.badge("FAIL", f"Unknown project action: {action}", stream=sys.stderr) + "\n")
    return 1


__all__ = ["cmd_project"]
