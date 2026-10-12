# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Arafat Zahan (@kuasha420)
# Corporate Stewardship & Infrastructure: Purrfect Software Limited (PSL)
# Governed by: ICARO-42/b Ordinance (Company-Supported Personal IP Framework)

"""
Plugin installation, uninstallation, and workspace initialization CLI commands (ADR-014, ADR-030).
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

from harness.delivery import DeliveryMode, PluginInstaller


def cmd_init(args: argparse.Namespace) -> int:
    """Initializes workspace with stack-tailored skills and tagged rules."""
    from harness.delivery import install_workspace

    target_ws = Path(args.path) if getattr(args, "path", None) else Path.cwd()
    skills_list = (
        [s.strip() for s in args.skills.split(",") if s.strip()]
        if getattr(args, "skills", None)
        else None
    )

    include_agents = bool(getattr(args, "agents", False))
    agents_list = None
    if isinstance(getattr(args, "agents", None), str):
        agents_list = [a.strip() for a in args.agents.split(",") if a.strip()]
        include_agents = True

    dedup = not getattr(args, "no_dedup", False)
    override = bool(getattr(args, "override", False))
    dry_run = bool(getattr(args, "dry_run", False))

    res = install_workspace(
        workspace_dir=target_ws,
        stack=getattr(args, "stack", None),
        skills=skills_list,
        agents=agents_list,
        include_agents=include_agents,
        dedup=dedup,
        override=override,
        dry_run=dry_run,
    )

    if getattr(args, "json", False):
        print(
            json.dumps(
                {
                    "success": res.success,
                    "workspace_dir": str(res.workspace_dir),
                    "stack": res.stack,
                    "dry_run": res.dry_run,
                    "skills_installed": res.skills_installed,
                    "skills_skipped": res.skills_skipped,
                    "agents_installed": res.agents_installed,
                    "agents_skipped": res.agents_skipped,
                    "rules_updated": res.rules_updated,
                    "command_dictionary": res.command_dictionary,
                    "legacy_notice": res.legacy_notice,
                    "message": res.message,
                },
                indent=2,
            )
        )
        return 0 if res.success else 1

    if res.success:
        print(f"✔ {res.message}")
        print(f"  • Stack: {res.stack}")
        if res.skills_installed:
            label = "Planned skills" if res.dry_run else "Installed skills"
            print(f"  • {label}: {', '.join(res.skills_installed)}")
        if res.skills_skipped:
            print(f"  • Skipped skills: {', '.join(res.skills_skipped)}")
        if res.agents_installed:
            label = "Planned agents" if res.dry_run else "Installed agents"
            print(f"  • {label}: {', '.join(res.agents_installed)}")
        if res.rules_updated:
            action = "Would update" if res.dry_run else "Updated"
            print(f"  • Rules: {action} AGENTS.md with tagged AGYIS invariants block")
        else:
            print("  • Rules: AGENTS.md tagged block is up-to-date")
        if res.command_dictionary:
            print("  • Command Dictionary:")
            for verb, cmd in res.command_dictionary.items():
                print(f"    - {verb}: {cmd}")
        if res.legacy_notice:
            print(f"\n💡 Notice: {res.legacy_notice}")
        return 0
    else:
        sys.stderr.write(f"✘ Error: {res.message}\n")
        return 1


def cmd_install(args: argparse.Namespace) -> int:
    """Installs the PSL harness globally as a Google Antigravity plugin or initializes workspace."""
    if getattr(args, "workspace", None) is not None and args.workspace is not False:
        setattr(args, "path", args.workspace if args.workspace is not True else None)
        return cmd_init(args)

    mode = DeliveryMode.COPY if getattr(args, "copy", False) else DeliveryMode.SYMLINK
    bin_dir = Path(args.bin_dir) if getattr(args, "bin_dir", None) else None
    installer = PluginInstaller(bin_dir=bin_dir)
    target_dir = Path(args.target) if getattr(args, "target", None) else None
    all_surfaces = getattr(args, "all_surfaces", False)
    result = installer.install(
        mode=mode,
        dry_run=getattr(args, "dry_run", False),
        target_dir=target_dir,
        all_surfaces=all_surfaces,
    )

    if getattr(args, "json", False):
        print(
            json.dumps(
                {
                    "success": result.success,
                    "mode": result.mode,
                    "target_dir": str(result.target_dir),
                    "source_dir": str(result.source_dir),
                    "items_installed": result.items_installed,
                    "message": result.message,
                },
                indent=2,
            )
        )
        return 0 if result.success else 1

    if result.success:
        print(f"✔ {result.message}")
        return 0
    else:
        sys.stderr.write(f"✘ Error: {result.message}\n")
        return 1


def cmd_uninstall(args: argparse.Namespace) -> int:
    """Uninstalls the PSL harness global plugin."""
    bin_dir = Path(args.bin_dir) if getattr(args, "bin_dir", None) else None
    installer = PluginInstaller(bin_dir=bin_dir)
    target_dir = Path(args.target) if getattr(args, "target", None) else None
    result = installer.uninstall(
        dry_run=getattr(args, "dry_run", False), target_dir=target_dir
    )

    if getattr(args, "json", False):
        print(
            json.dumps(
                {
                    "success": result.success,
                    "mode": result.mode,
                    "target_dir": str(result.target_dir),
                    "source_dir": str(result.source_dir),
                    "items_installed": result.items_installed,
                    "message": result.message,
                },
                indent=2,
            )
        )
        return 0 if result.success else 1

    if result.success:
        print(f"✔ {result.message}")
        return 0
    else:
        sys.stderr.write(f"✘ Error: {result.message}\n")
        return 1
