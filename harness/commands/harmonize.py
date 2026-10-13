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
    prune_legacy = bool(getattr(args, "prune_legacy", False) or getattr(args, "clean_agent_dir", False))
    no_backup = bool(getattr(args, "no_backup", False))
    backup = bool(getattr(args, "backup", True)) and not no_backup
    backup_dir_val = getattr(args, "backup_dir", None) or getattr(args, "archive_dir", None)
    archive_dir = Path(backup_dir_val) if backup_dir_val else None
    stack = getattr(args, "stack", None)
    skills_raw = getattr(args, "skills", None)
    skills = [s.strip() for s in skills_raw.split(",") if s.strip()] if skills_raw else None

    res = harmonize_workspace(
        workspace_dir=target_ws,
        dry_run=dry_run,
        prune_legacy=prune_legacy,
        backup=backup,
        archive_dir=archive_dir,
        stack=stack,
        skills=skills,
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

    if res.pruned_legacy:
        verb = "Would prune" if res.dry_run else "Pruned"
        print(f"  • Legacy cleanup: {verb} .agent/ directory")
        if res.backup_archive:
            verb_arch = "Would archive" if res.dry_run else "Archived"
            file_count = res.backup_manifest.get("file_count", len(res.backup_manifest.get("files", []))) if res.backup_manifest else 0
            print(f"  • Backup archive: {verb_arch} to {res.backup_archive} ({file_count} files)")
        if res.untracked_debris_cleaned:
            verb_deb = "Would clean" if res.dry_run else "Cleaned"
            print(f"  • Untracked debris: {verb_deb} {len(res.untracked_debris_cleaned)} files")

    if res.skills_provisioned:
        verb_sk = "Would provision" if res.dry_run else "Provisioned"
        print(f"  • Skills: {verb_sk} ({len(res.skills_provisioned)}): {', '.join(res.skills_provisioned)}")

    if res.dry_run:
        print("  • Disk status: Zero modifications made (dry-run)")
    else:
        print("  • Disk status: Harmonization applied cleanly")

    return 0
