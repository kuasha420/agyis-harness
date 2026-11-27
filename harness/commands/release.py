# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Arafat Zahan (@kuasha420)
# Corporate Stewardship & Infrastructure: Purrfect Software Limited (PSL)
# Governed by: ICARO-42/b Ordinance (Company-Supported Personal IP Framework)

"""
Unified Single-Command Release CLI Handler (`agyis release bump|check`).
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from typing import Any, Dict

from harness.delivery.release_bump import (
    apply_release_bump,
    check_release_parity,
    format_release_bump_report,
    format_release_check_report,
)
from harness.utils import theme


def _emit_error(message: str, *, is_json: bool) -> int:
    """Emit structured JSON or themed stderr error and return exit code 1."""
    if is_json:
        print(json.dumps({"success": False, "error": message}, indent=2))
    else:
        print(theme.badge("FAIL", message, stream=sys.stderr), file=sys.stderr)
    return 1


def cmd_release(args: argparse.Namespace) -> int:
    """Execute `agyis release bump` or `agyis release check`."""
    action = getattr(args, "release_action", None)
    is_json = bool(getattr(args, "json", False))
    workspace_val = getattr(args, "workspace", None)
    repo_dir = Path(workspace_val).resolve() if workspace_val else Path.cwd().resolve()

    if action == "bump":
        version = getattr(args, "version", "")
        apply_flag = bool(getattr(args, "apply", False))
        skip_og = bool(getattr(args, "skip_og", False))
        skip_lock = bool(getattr(args, "skip_lock", False))
        skip_changelog = bool(getattr(args, "skip_changelog", False))
        release_date = getattr(args, "date", None)
        repo_url = getattr(args, "repo_url", None)

        try:
            result = apply_release_bump(
                repo_dir,
                version,
                apply=apply_flag,
                release_date=release_date,
                repo_url=repo_url,
                skip_og=skip_og,
                skip_lock=skip_lock,
                skip_changelog=skip_changelog,
            )
        except (ValueError, RuntimeError, OSError) as exc:
            return _emit_error(str(exc), is_json=is_json)

        if is_json:
            payload: Dict[str, Any] = {"success": True, **result.to_dict()}
            print(json.dumps(payload, indent=2))
        else:
            print(format_release_bump_report(result))
        return 0

    if action == "check":
        version_opt = getattr(args, "version", None)
        include_site = bool(getattr(args, "include_site", False))
        try:
            report = check_release_parity(
                repo_dir,
                version=version_opt,
                include_site=include_site,
            )
        except (ValueError, RuntimeError, OSError) as exc:
            return _emit_error(str(exc), is_json=is_json)

        if is_json:
            print(json.dumps(report, indent=2))
        else:
            print(format_release_check_report(report))
        return 0 if report.get("status") == "PASS" else 1

    return _emit_error("Missing release subcommand. Expected: 'agyis release bump <version>' or 'agyis release check'.", is_json=is_json)


__all__ = ["cmd_release"]
