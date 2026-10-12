# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Arafat Zahan (@kuasha420)
# Corporate Stewardship & Infrastructure: Purrfect Software Limited (PSL)
# Governed by: ICARO-42/b Ordinance (Company-Supported Personal IP Framework)

"""
Workspace Harmonization CLI Command (ADR-014, ADR-030).
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

from harness.delivery.harmonize import harmonize_workspace


def cmd_harmonize(args: argparse.Namespace) -> int:
    """Harmonizes legacy .agent/ configuration and tagged rules into modern .agents/ structure."""
    target_ws = Path(args.path) if getattr(args, "path", None) else Path.cwd()
    dry_run = bool(getattr(args, "dry_run", False))

    res = harmonize_workspace(
        workspace_dir=target_ws,
        dry_run=dry_run,
    )

    if getattr(args, "json", False):
        print(json.dumps(res.to_dict(), indent=2))
        return 0 if res.success else 1

    if not res.success:
        sys.stderr.write(f"✘ Error: {res.message}\n")
        return 1

    prefix = "✔ [DRY-RUN] " if res.dry_run else "✔ "
    print(f"{prefix}{res.message}")
    print(f"  • Workspace: {res.workspace_dir}")
    print(f"  • Legacy .agent/ found: {'yes' if res.legacy_agent_dir_found else 'no'}")

    if res.legacy_agents_migrated:
        verb = "Would migrate" if res.dry_run else "Migrated"
        print(f"  • {verb} agents ({len(res.legacy_agents_migrated)}): {', '.join(res.legacy_agents_migrated)}")
    if res.legacy_workflows_migrated:
        verb = "Would convert" if res.dry_run else "Converted"
        print(f"  • {verb} workflows to skills ({len(res.legacy_workflows_migrated)}): {', '.join(res.legacy_workflows_migrated)}")
    if res.legacy_rules_migrated:
        verb = "Would migrate" if res.dry_run else "Migrated"
        print(f"  • {verb} rules ({len(res.legacy_rules_migrated)}): {', '.join(res.legacy_rules_migrated)}")

    rules_desc = {
        "migrated_tagged_block": "Upgraded legacy PSL-HARNESS block to AGYIS-HARNESS",
        "inserted_tagged_block": "Injected AGYIS-HARNESS block (preserved existing user rules)",
        "created_rules_file": "Created AGENTS.md with AGYIS-HARNESS block",
        "already_up_to_date": "AGENTS.md tagged block is already up-to-date",
    }.get(res.rules_action, res.rules_action)
    print(f"  • Rules: {rules_desc}")

    if res.dry_run:
        print("  • Disk status: Zero modifications made (dry-run)")
    else:
        print("  • Disk status: Harmonization applied cleanly")

    return 0
