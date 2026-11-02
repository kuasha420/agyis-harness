# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Arafat Zahan (@kuasha420)
# Corporate Stewardship & Infrastructure: Purrfect Software Limited (PSL)
# Governed by: ICARO-42/b Ordinance (Company-Supported Personal IP Framework)

"""
Extensible Workspace CLI Command Architecture (ADR-034).
Discovers, catalogs, and dispatches project-specific bespoke CLI commands from
.agents/commands/ (*.py, *.sh, executables) and .agents/commands.json.
Allows downstream projects (e.g. Project Immortal) to emerge bespoke features cleanly
without bloating product core, while providing a seamless upstreaming runway.
"""

from dataclasses import asdict, dataclass
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
from typing import Any, Dict, List, Optional


@dataclass
class ExtensionCommand:
    """Represents a discovered workspace CLI extension command."""
    name: str
    entrypoint: Path
    command_type: str  # "python", "shell", "binary"
    description: str
    workspace_root: Path
    origin: str  # "file" or "manifest"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "entrypoint": str(self.entrypoint),
            "command_type": self.command_type,
            "description": self.description,
            "workspace_root": str(self.workspace_root),
            "origin": self.origin,
        }


def get_workspace_root(start_path: Optional[Path] = None) -> Path:
    """Discovers project root containing .agents or .git."""
    curr = (start_path or Path.cwd()).resolve()
    for parent in [curr] + list(curr.parents):
        if (parent / ".agents").is_dir() or (parent / ".git").is_dir():
            return parent
    return curr


def discover_workspace_commands(
    workspace_root: Optional[Path] = None,
) -> Dict[str, ExtensionCommand]:
    """
    Discovers bespoke CLI extension commands in the workspace.
    Scans:
    1. .agents/commands.json or .agents/commands/manifest.json
    2. .agents/commands/ directory (*.py, *.sh, executable files)
    """
    ws = workspace_root or get_workspace_root()
    commands: Dict[str, ExtensionCommand] = {}

    # 1. Inspect manifest files
    manifest_paths = [
        ws / ".agents" / "commands.json",
        ws / ".agents" / "commands" / "manifest.json",
    ]
    for mf in manifest_paths:
        if mf.is_file():
            try:
                data = json.loads(mf.read_text(encoding="utf-8"))
                if isinstance(data, dict):
                    for name, spec in data.items():
                        if not isinstance(spec, dict):
                            continue
                        ep_str = spec.get("entrypoint") or spec.get("path")
                        if not ep_str:
                            continue
                        ep_path = Path(ep_str)
                        if not ep_path.is_absolute():
                            ep_path = ws / ep_path
                        if ep_path.exists():
                            cmd_type = spec.get("type") or spec.get("runtime")
                            if not cmd_type:
                                if ep_path.suffix == ".py":
                                    cmd_type = "python"
                                elif ep_path.suffix in (".sh", ".bash"):
                                    cmd_type = "shell"
                                else:
                                    cmd_type = "binary"
                            commands[name] = ExtensionCommand(
                                name=name,
                                entrypoint=ep_path,
                                command_type=cmd_type,
                                description=spec.get("description", "Workspace extension command"),
                                workspace_root=ws,
                                origin="manifest",
                            )
            except Exception:
                pass

    # 2. Inspect .agents/commands/ directory
    cmd_dir = ws / ".agents" / "commands"
    if cmd_dir.is_dir():
        for item in cmd_dir.iterdir():
            if item.name.startswith(".") or item.name == "manifest.json":
                continue
            name = item.stem if item.suffix in (".py", ".sh", ".bash") else item.name
            if name in commands:
                continue  # Manifest takes precedence
            if item.is_file():
                if item.suffix == ".py":
                    cmd_type = "python"
                elif item.suffix in (".sh", ".bash"):
                    cmd_type = "shell"
                elif os.access(item, os.X_OK):
                    cmd_type = "binary"
                else:
                    continue

                # Extract first-line docstring/comment as description if available
                desc = f"Workspace {cmd_type} command ({item.name})"
                try:
                    head_lines = item.read_text(encoding="utf-8", errors="ignore").splitlines()[:5]
                    for hl in head_lines:
                        clean_hl = hl.strip()
                        if clean_hl.startswith("#") and not clean_hl.startswith("#!"):
                            c = clean_hl.lstrip("#").strip()
                            if c and not c.startswith("SPDX") and not c.startswith("Copyright"):
                                desc = c
                                break
                        elif clean_hl.startswith('"""') or clean_hl.startswith("'''"):
                            desc = clean_hl.strip("'\"").strip()
                            break
                except Exception:
                    pass

                commands[name] = ExtensionCommand(
                    name=name,
                    entrypoint=item,
                    command_type=cmd_type,
                    description=desc,
                    workspace_root=ws,
                    origin="file",
                )

    return commands


def execute_extension_command(
    cmd: ExtensionCommand,
    args: List[str],
) -> int:
    """Executes a discovered workspace extension command cleanly."""
    env = os.environ.copy()
    env["AGYIS_WORKSPACE"] = str(cmd.workspace_root)
    env["AGYIS_EXTENSION_COMMAND"] = cmd.name

    if cmd.command_type == "python":
        exec_args = [sys.executable, str(cmd.entrypoint)] + args
    elif cmd.command_type == "shell":
        exec_args = ["bash", str(cmd.entrypoint)] + args
    else:
        exec_args = [str(cmd.entrypoint)] + args

    try:
        proc = subprocess.run(exec_args, env=env, check=False)
        return proc.returncode
    except Exception as e:
        print(f"[!] Error executing extension command '{cmd.name}': {e}", file=sys.stderr)
        return 1
