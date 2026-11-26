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
    do_lint = bool(getattr(args, "lint", False))
    do_dedup = bool(getattr(args, "dedup", False))

    if not do_lint and not do_dedup:
        print("Specify --dedup to deduplicate rules or --lint to scan for rule repetition.")
        return 0

    dedup_res = None
    if do_dedup:
        dry_run = getattr(args, "dry_run", False)
        config_dir = getattr(args, "config_dir", None)
        dedup_res = enforce_single_source_rules(
            workspace_dir=ws_root,
            config_dir=config_dir,
            dry_run=dry_run,
        )
        if not as_json:
            prefix = "Would prune" if dry_run else "Pruned"
            if dedup_res["pruned_files"]:
                print(
                    f"✔ {prefix} duplicate universal rules in workspace "
                    f"({dedup_res['tokens_saved']} tokens saved, {dedup_res['chars_removed']} chars removed):"
                )
                for f in dedup_res["pruned_files"]:
                    print(f"  - {f}")
                if dedup_res["removed_sections"]:
                    print("  Removed sections:")
                    for s in dedup_res["removed_sections"]:
                        print(f"    * {s}")
            else:
                print(f"✔ Workspace rules already deduplicated ({ws_root})")

    lint_res = None
    if do_lint:
        lint_res = lint_rule_echo(ws_root)
        if not as_json:
            if lint_res["clean"]:
                print(f"✔ Rule echo linter passed: {lint_res['files_scanned']} files scanned, 0 echoes found in {ws_root}")
            else:
                print(f"✖ Rule echo linter failed with {len(lint_res['echoes'])} finding(s):")
                for item in lint_res["echoes"]:
                    print(f"  - {item['file']}: {', '.join(item['matched_echoes'])}")

    if as_json:
        if do_lint and do_dedup:
            print(json.dumps({"lint": lint_res, "dedup": dedup_res, "clean": bool(lint_res and lint_res["clean"])}, indent=2))
        elif do_lint:
            print(json.dumps(lint_res, indent=2))
        else:
            print(json.dumps(dedup_res, indent=2))

    if lint_res is not None:
        return 0 if lint_res["clean"] else 1
    return 0


# Backwards-compatible alias
rules_command = cmd_rules
