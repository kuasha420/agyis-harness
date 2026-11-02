# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Arafat Zahan (@kuasha420)
# Corporate Stewardship & Infrastructure: Purrfect Software Limited (PSL)
# Governed by: ICARO-42/b Ordinance (Company-Supported Personal IP Framework)

"""
Workspace CLI Extensions Command (ADR-034).
Lists, runs, and scaffolds project-specific CLI extension commands.
"""

import argparse
import json
import os
from pathlib import Path
import sys
from typing import List, Optional

from harness.runtime.extensions import (
    discover_workspace_commands,
    execute_extension_command,
    get_workspace_root,
)


def cmd_list(args: argparse.Namespace) -> int:
    """Lists all discovered workspace extension commands."""
    ws = Path(args.workspace).resolve() if getattr(args, "workspace", None) else get_workspace_root()
    commands = discover_workspace_commands(ws)

    if getattr(args, "json", False):
        print(json.dumps([c.to_dict() for c in commands.values()], indent=2))
        return 0

    print(f"=== Discovered Workspace CLI Commands ({len(commands)}) ===")
    print(f"Workspace: {ws}\n")
    if not commands:
        print("  No extension commands found.")
        print("  Add scripts to .agents/commands/ or define .agents/commands.json")
        print("  Run: agyis ext init <name> to scaffold a new command.")
        return 0

    print(f"{'Command':<16} {'Type':<8} {'Origin':<10} {'Description'}")
    print("-" * 75)
    for name, cmd in sorted(commands.items()):
        print(f"{name:<16} {cmd.command_type:<8} {cmd.origin:<10} {cmd.description}")

    return 0


def cmd_run(args: argparse.Namespace) -> int:
    """Runs a workspace extension command by name."""
    ws = Path(args.workspace).resolve() if getattr(args, "workspace", None) else get_workspace_root()
    commands = discover_workspace_commands(ws)

    if args.name not in commands:
        print(f"[!] Extension command '{args.name}' not found in workspace.", file=sys.stderr)
        print("Run 'agyis ext list' to view available commands.", file=sys.stderr)
        return 1

    cmd = commands[args.name]
    extra_args = getattr(args, "args", [])
    return execute_extension_command(cmd, extra_args)


def cmd_init(args: argparse.Namespace) -> int:
    """Scaffolds a new workspace extension command in .agents/commands/."""
    ws = Path(args.workspace).resolve() if getattr(args, "workspace", None) else get_workspace_root()
    cmd_dir = ws / ".agents" / "commands"
    cmd_dir.mkdir(parents=True, exist_ok=True)

    name = args.name
    cmd_type = getattr(args, "type", "py")

    if cmd_type == "py":
        target_file = cmd_dir / f"{name}.py"
        content = f"""#!/usr/bin/env python3
# Workspace CLI command: {name}
import sys

def main():
    print("Executing workspace command '{name}' with args:", sys.argv[1:])
    return 0

if __name__ == "__main__":
    sys.exit(main())
"""
    else:
        target_file = cmd_dir / f"{name}.sh"
        content = f"""#!/usr/bin/env bash
# Workspace CLI command: {name}
set -euo pipefail

echo "Executing workspace shell command '{name}' with args: $@"
"""

    if target_file.exists():
        print(f"[!] File already exists: {target_file}", file=sys.stderr)
        return 1

    target_file.write_text(content, encoding="utf-8")
    target_file.chmod(0o755)

    print(f"[+] Scaffolded new extension command at {target_file}")
    print(f"    Invoke with: ./agyis {name} or ./agyis ext run {name}")
    return 0


def main(argv: Optional[List[str]] = None) -> int:
    """CLI dispatcher for 'agyis ext'."""
    parser = argparse.ArgumentParser(
        prog="agyis ext",
        description="Agyis Workspace CLI Extension Architecture (ADR-034)",
    )
    sub = parser.add_subparsers(dest="ext_cmd", help="Extension subcommand")

    # list
    p_list = sub.add_parser("list", help="List discovered workspace extension commands")
    p_list.add_argument("--workspace", "-w", type=Path, help="Workspace root")
    p_list.add_argument("--json", action="store_true", help="Output JSON")

    # run
    p_run = sub.add_parser("run", help="Run a workspace extension command")
    p_run.add_argument("name", help="Extension command name")
    p_run.add_argument("args", nargs=argparse.REMAINDER, help="Arguments passed to extension")
    p_run.add_argument("--workspace", "-w", type=Path, help="Workspace root")

    # init
    p_init = sub.add_parser("init", help="Scaffold a new extension command")
    p_init.add_argument("name", help="Extension command name")
    p_init.add_argument("--type", choices=["py", "sh"], default="py", help="Command script type")
    p_init.add_argument("--workspace", "-w", type=Path, help="Workspace root")

    args = parser.parse_args(argv)
    if not args.ext_cmd or args.ext_cmd == "list":
        return cmd_list(args)
    if args.ext_cmd == "run":
        return cmd_run(args)
    if args.ext_cmd == "init":
        return cmd_init(args)

    parser.print_help()
    return 1


if __name__ == "__main__":
    sys.exit(main())
