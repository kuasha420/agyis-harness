# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Purrfect Software Limited (PSL)

"""
Plugin installation and uninstallation CLI commands (ADR-014, ADR-030).
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

from harness.delivery import DeliveryMode, PluginInstaller


def cmd_install(args: argparse.Namespace) -> int:
    """Installs the PSL harness globally as a Google Antigravity plugin."""
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
        print(json.dumps({
            "success": result.success,
            "mode": result.mode,
            "target_dir": str(result.target_dir),
            "source_dir": str(result.source_dir),
            "items_installed": result.items_installed,
            "message": result.message,
        }, indent=2))
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
    result = installer.uninstall(dry_run=getattr(args, "dry_run", False), target_dir=target_dir)

    if getattr(args, "json", False):
        print(json.dumps({
            "success": result.success,
            "mode": result.mode,
            "target_dir": str(result.target_dir),
            "source_dir": str(result.source_dir),
            "items_installed": result.items_installed,
            "message": result.message,
        }, indent=2))
        return 0 if result.success else 1

    if result.success:
        print(f"✔ {result.message}")
        return 0
    else:
        sys.stderr.write(f"✘ Error: {result.message}\n")
        return 1
