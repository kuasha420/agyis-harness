#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Arafat Zahan (@kuasha420)
# Corporate Stewardship & Infrastructure: Purrfect Software Limited (PSL)
# Governed by: ICARO-42/b Ordinance (Company-Supported Personal IP Framework)

"""
Agyis Harness for Google Antigravity™ (Unified Developer CLI).
Antigravity Immune System (Autonomous Agent Runtime).

Primary console entrypoint for the Agyis Harness runtime:
- agyis doctor: Workstation runtime diagnostic & auto-healing
- agyis hook <name>: Deterministic lifecycle hook execution
- agyis test: Test suite discovery & verification
- agyis audit [stage]: Empirical telemetry lab runner
- agyis status: System & customization health overview
- agyis remote: Remote execution, streaming & triage
- agyis subagents: Active subagents & context health gauge
"""

from __future__ import annotations

import argparse
from pathlib import Path
import sys
from typing import List, Optional

import harness
from harness.cli_parsers_core import register_core_parsers
from harness.cli_parsers_ops import register_ops_parsers
from harness.commands import (
    cmd_agents,
    cmd_audit,
    cmd_auth,
    cmd_doctor,
    cmd_gui,
    cmd_harmonize,
    cmd_hook,
    cmd_init,
    cmd_install,
    cmd_onboard,
    cmd_remote,
    cmd_rules,
    cmd_skills,
    cmd_status,
    cmd_subagents,
    cmd_sync,
    cmd_test,
    cmd_uninstall,
    cmd_verify,
    cmd_release_notes,
    cmd_changelog,
    cmd_checkpoint,
    cmd_cockpit,
    cmd_clean,
)
from harness.commands.re import main as cmd_re
from harness.commands.ext import main as cmd_ext
from harness.runtime.extensions import discover_workspace_commands, execute_extension_command

REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_MATRIX = Path(__file__).resolve().parent / "runtime" / "matrix.json"
DEFAULT_DB = REPO_ROOT / "data" / "telemetry.db"
_TEST_WORKSPACE_ROOT: Optional[Path] = None

PSL_DEPRECATION_WARNING = (
    "DeprecationWarning: 'psl' is deprecated and will be removed in 3 months. Use 'agyis' instead.\n"
)


def emit_psl_deprecation_warning() -> None:
    """Emits the active deprecation warning for legacy 'psl' invocations to sys.stderr."""
    sys.stderr.write(PSL_DEPRECATION_WARNING)
    sys.stderr.flush()


def build_parser(prog: str = "agyis") -> argparse.ArgumentParser:
    """Build the top-level argument parser for the Agyis harness CLI."""
    if prog == "psl":
        desc = "PSL Harness for Google Antigravity™ — Unified Developer CLI (Deprecated: Use 'agyis')"
    else:
        desc = "Agyis Harness for Google Antigravity™ — Unified Developer CLI (Antigravity Immune System)"

    parser = argparse.ArgumentParser(
        prog=prog,
        description=desc,
    )
    parser.add_argument(
        "-v", "--version", action="version", version=f"agyis-harness {harness.__version__}"
    )

    subparsers = parser.add_subparsers(dest="subcommand", help="Available subcommands")
    register_core_parsers(subparsers)
    register_ops_parsers(subparsers)
    return parser


def deprecated_psl_main(argv: Optional[List[str]] = None) -> int:
    """Deprecated CLI entrypoint for legacy 'psl' invocations."""
    emit_psl_deprecation_warning()
    return main(argv=argv, prog="psl", _warned=True)


def main(
    argv: Optional[List[str]] = None,
    prog: Optional[str] = None,
    _warned: bool = False,
) -> int:
    """Main CLI dispatch entrypoint for Agyis harness."""
    if prog is None:
        if argv is None and sys.argv and sys.argv[0]:
            try:
                invoked_stem = Path(sys.argv[0]).stem.lower()
                prog = "psl" if invoked_stem == "psl" else "agyis"
            except Exception:
                prog = "agyis"
        else:
            prog = "agyis"

    if prog == "psl" and not _warned:
        emit_psl_deprecation_warning()

    raw_argv = sys.argv[1:] if argv is None else list(argv)
    if raw_argv and not raw_argv[0].startswith("-"):
        first_tok = raw_argv[0]
        # Check if first token matches a workspace extension command before argparse
        exts = discover_workspace_commands()
        if first_tok in exts:
            return execute_extension_command(exts[first_tok], raw_argv[1:])

    parser = build_parser(prog=prog)
    args = parser.parse_args(argv)

    if not args.subcommand:
        parser.print_help()
        return 0

    commands = {
        "doctor": cmd_doctor,
        "hook": cmd_hook,
        "test": cmd_test,
        "audit": cmd_audit,
        "auth": cmd_auth,
        "sync": cmd_sync,
        "rules": cmd_rules,
        "skills": cmd_skills,
        "agents": cmd_agents,
        "subagents": cmd_subagents,
        "remote": cmd_remote,
        "status": cmd_status,
        "init": cmd_init,
        "harmonize": cmd_harmonize,
        "onboard": cmd_onboard,
        "install": cmd_install,
        "uninstall": cmd_uninstall,
        "verify": cmd_verify,
        "gui": cmd_gui,
        "release-notes": cmd_release_notes,
        "changelog": cmd_changelog,
        "changelogs": cmd_changelog,
        "checkpoint": cmd_checkpoint,
        "cockpit": cmd_cockpit,
        "router": cmd_cockpit,
        "ladder": cmd_cockpit,
        "clean": cmd_clean,
    }

    if args.subcommand == "re":
        return cmd_re(getattr(args, "re_args", []))

    if args.subcommand == "ext":
        return cmd_ext(getattr(args, "ext_args", []))

    handler = commands.get(args.subcommand)
    if handler:
        return handler(args)

    return 0


__all__ = [
    "DEFAULT_DB",
    "DEFAULT_MATRIX",
    "PSL_DEPRECATION_WARNING",
    "REPO_ROOT",
    "build_parser",
    "deprecated_psl_main",
    "emit_psl_deprecation_warning",
    "main",
]


if __name__ == "__main__":
    sys.exit(main())
