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
import os
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
    if exp_rea and result.success and not getattr(args, "dry_run", False):
        from harness.runtime.tool_checks import find_jdk21_path

        jdk21_path = find_jdk21_path()
        ghidra_dir = os.environ.get("GHIDRA_INSTALL_DIR")
        if not ghidra_dir:
            for cand in [Path("/opt/ghidra"), Path("/usr/local/opt/ghidra"), Path.home() / "ghidra"]:
                if cand.is_dir():
                    ghidra_dir = str(cand)
                    break

        config_paths = [
            Path.home() / ".gemini" / "config" / "mcp_config.json",
            Path.home() / ".gemini" / "antigravity" / "mcp_config.json",
        ]
        for cfg_p in config_paths:
            try:
                data: Dict[str, Any] = {}
                if cfg_p.is_file():
                    try:
                        data = json.loads(cfg_p.read_text(encoding="utf-8"))
                    except (json.JSONDecodeError, OSError):
                        data = {}
                if not isinstance(data, dict):
                    data = {}
                if "mcpServers" not in data or not isinstance(data["mcpServers"], dict):
                    data["mcpServers"] = {}

                data["mcpServers"]["rea"] = {
                    "command": "rea",
                    "args": ["mcp"],
                    "env": {
                        "GHIDRA_INSTALL_DIR": ghidra_dir or "/opt/ghidra",
                        "JAVA_HOME": str(jdk21_path) if jdk21_path else "",
                        "REA_MCP_INPUT_SCHEMA_PROFILE": "full",
                        "REA_MCP_OUTPUT_SCHEMA_PROFILE": "off",
                    },
                }
                cfg_p.parent.mkdir(parents=True, exist_ok=True)
                cfg_p.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
                rea_mcp_configured = True
            except OSError:
                pass

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
                    "experimental_rea": exp_rea,
                    "rea_mcp_configured": rea_mcp_configured,
                },
                indent=2,
            )
        )
        return 0 if result.success else 1

    if result.success:
        print(f"✔ {result.message}")
        if exp_rea:
            label = "Would configure" if getattr(args, "dry_run", False) else "Configured"
            print(f"  • REA: {label} global Reverse Engineer Anything MCP server (~/.gemini/config/mcp_config.json)")
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
