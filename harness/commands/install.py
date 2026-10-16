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
from typing import Any, Dict

from harness.delivery import DeliveryMode, PluginInstaller


from harness.commands.init import cmd_init


def cmd_install(args: argparse.Namespace) -> int:
    """Installs the Agyis harness globally as a Google Antigravity plugin or initializes workspace."""
    if getattr(args, "workspace", None) is not None and args.workspace is not False:
        setattr(args, "path", args.workspace if args.workspace is not True else None)
        return cmd_init(args)

    if getattr(args, "wheel", False):
        mode = DeliveryMode.WHEEL
    elif getattr(args, "copy", False):
        mode = DeliveryMode.COPY
    elif getattr(args, "symlink", False):
        mode = DeliveryMode.SYMLINK
    elif getattr(args, "global_install", False):
        mode = DeliveryMode.WHEEL
    else:
        mode = DeliveryMode.SYMLINK
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

    exp_rea = bool(getattr(args, "experimental_rea", False))
    rea_mcp_configured = False
    rea_mcp_errors: List[str] = []
    rea_skill_provisioned = False
    if exp_rea and result.success and not getattr(args, "dry_run", False):
        from harness.runtime.healing import provision_rea_skill
        from harness.runtime.tool_checks import configure_rea_mcp_server

        configured_paths, rea_mcp_errors = configure_rea_mcp_server()
        rea_mcp_configured = bool(configured_paths)

        global_skills = Path.home() / ".gemini" / "config" / "skills"
        prov = provision_rea_skill(global_skills, link=True, allow_download=False)
        rea_skill_provisioned = bool(prov)

    if getattr(args, "json", False):
        payload: Dict[str, Any] = {
            "success": result.success,
            "mode": result.mode,
            "target_dir": str(result.target_dir),
            "source_dir": str(result.source_dir),
            "items_installed": result.items_installed,
            "message": result.message,
            "experimental_rea": exp_rea,
            "rea_mcp_configured": rea_mcp_configured,
        }
        if rea_mcp_errors:
            payload["rea_mcp_errors"] = rea_mcp_errors
        print(json.dumps(payload, indent=2))
        return 0 if result.success else 1

    if result.success:
        print(f"✔ {result.message}")
        if exp_rea:
            if getattr(args, "dry_run", False):
                print("  • REA: Would configure global Reverse Engineer Anything MCP server (~/.gemini/config/mcp_config.json)")
            elif rea_mcp_configured:
                print("  • REA: Configured global Reverse Engineer Anything MCP server (~/.gemini/config/mcp_config.json)")
            else:
                err_detail = f" ({'; '.join(rea_mcp_errors)})" if rea_mcp_errors else ""
                print(f"  • REA: Failed to configure MCP server{err_detail}")
        return 0
    else:
        sys.stderr.write(f"✘ Error: {result.message}\n")
        return 1


def cmd_uninstall(args: argparse.Namespace) -> int:
    """Uninstalls the Agyis harness global plugin."""
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
