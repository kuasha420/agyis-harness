# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Arafat Zahan (@kuasha420)
# Corporate Stewardship & Infrastructure: Purrfect Software Limited (PSL)
# Governed by: ICARO-42/b Ordinance (Company-Supported Personal IP Framework)

"""
Agent rules deduplication and linting CLI command (Issues #70 & #71).
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

from harness.delivery.surfaces import (
    enforce_single_source_rules,
    find_workspace_root,
    lint_rule_echo,
)


def cmd_rules(args: argparse.Namespace) -> int:
    """Audits, deduplicates, and lints agent rules."""
    ws_arg = getattr(args, "workspace", None)
    if ws_arg and ws_arg is not True:
        ws_root = Path(ws_arg).resolve()
    else:
        ws_root = find_workspace_root()

    as_json = getattr(args, "json", False)

    if getattr(args, "lint", False):
        res = lint_rule_echo(ws_root)
        if as_json:
            print(json.dumps(res, indent=2))
        else:
            if res["clean"]:
                print(f"✔ Rule echo linter passed: {res['files_scanned']} files scanned, 0 echoes found in {ws_root}")
            else:
                print(f"✖ Rule echo linter failed with {len(res['echoes'])} finding(s):")
                for item in res["echoes"]:
                    print(f"  - {item['file']}: {', '.join(item['matched_echoes'])}")
        return 0 if res["clean"] else 1

    if getattr(args, "dedup", False):
        dry_run = getattr(args, "dry_run", False)
        config_dir = getattr(args, "config_dir", None)
        res = enforce_single_source_rules(
            workspace_dir=ws_root,
            config_dir=config_dir,
            dry_run=dry_run,
        )
        if as_json:
            print(json.dumps(res, indent=2))
        else:
            prefix = "Would prune" if dry_run else "Pruned"
            if res["pruned_files"]:
                print(f"✔ {prefix} duplicate universal rules in workspace ({res['tokens_saved']} tokens saved, {res['chars_removed']} chars removed):")
                for f in res["pruned_files"]:
                    print(f"  - {f}")
                if res["removed_sections"]:
                    print("  Removed sections:")
                    for s in res["removed_sections"]:
                        print(f"    * {s}")
            else:
                print(f"✔ Workspace rules already deduplicated ({ws_root})")
        return 0

    print("Specify --dedup to deduplicate rules or --lint to scan for rule repetition.")
    return 0


# Backwards-compatible alias
rules_command = cmd_rules
