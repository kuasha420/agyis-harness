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
import importlib
from pathlib import Path
import sys
from typing import Any, Dict, List, Optional, Tuple

import harness
from harness.cli_parsers_core import register_core_parsers
from harness.cli_parsers_ops import register_ops_parsers

_LAZY_EXPORTS: Dict[str, Tuple[str, str]] = {
    "cmd_doctor": ("harness.commands.doctor", "cmd_doctor"),
    "cmd_hook": ("harness.commands.hook", "cmd_hook"),
    "cmd_test": ("harness.commands.test", "cmd_test"),
    "cmd_audit": ("harness.commands.audit", "cmd_audit"),
    "cmd_auth": ("harness.commands.auth", "cmd_auth"),
    "cmd_sync": ("harness.commands.sync", "cmd_sync"),
    "cmd_rules": ("harness.commands.rules", "cmd_rules"),
    "cmd_skills": ("harness.commands.skills", "cmd_skills"),
    "cmd_agents": ("harness.commands.agents", "cmd_agents"),
    "cmd_subagents": ("harness.commands.subagents", "cmd_subagents"),
    "cmd_remote": ("harness.commands.remote", "cmd_remote"),
    "cmd_status": ("harness.commands.status", "cmd_status"),
    "cmd_init": ("harness.commands.install", "cmd_init"),
    "cmd_harmonize": ("harness.commands.harmonize", "cmd_harmonize"),
    "cmd_onboard": ("harness.commands.onboard", "cmd_onboard"),
    "cmd_install": ("harness.commands.install", "cmd_install"),
    "cmd_uninstall": ("harness.commands.install", "cmd_uninstall"),
    "cmd_verify": ("harness.commands.verify", "cmd_verify"),
    "cmd_gui": ("harness.commands.gui", "cmd_gui"),
    "cmd_release": ("harness.commands.release", "cmd_release"),
    "cmd_release_notes": ("harness.commands.release_notes", "cmd_release_notes"),
    "cmd_changelog": ("harness.commands.changelog", "cmd_changelog"),
    "cmd_checkpoint": ("harness.commands.checkpoint", "cmd_checkpoint"),
    "cmd_cockpit": ("harness.commands.cockpit", "cmd_cockpit"),
    "cmd_clean": ("harness.commands.clean", "cmd_clean"),
    "cmd_project": ("harness.commands.project", "cmd_project"),
    "cmd_re": ("harness.commands.re", "main"),
    "cmd_ext": ("harness.commands.ext", "main"),
    "discover_workspace_commands": ("harness.runtime.extensions", "discover_workspace_commands"),
    "execute_extension_command": ("harness.runtime.extensions", "execute_extension_command"),
}

_SUBCOMMAND_ATTRS: Dict[str, str] = {
    "doctor": "cmd_doctor",
    "hook": "cmd_hook",
    "test": "cmd_test",
    "audit": "cmd_audit",
    "auth": "cmd_auth",
    "sync": "cmd_sync",
    "rules": "cmd_rules",
    "skills": "cmd_skills",
    "agents": "cmd_agents",
    "subagents": "cmd_subagents",
    "remote": "cmd_remote",
    "status": "cmd_status",
    "init": "cmd_init",
    "harmonize": "cmd_harmonize",
    "onboard": "cmd_onboard",
    "install": "cmd_install",
    "uninstall": "cmd_uninstall",
    "verify": "cmd_verify",
    "gui": "cmd_gui",
    "release": "cmd_release",
    "release-notes": "cmd_release_notes",
    "changelog": "cmd_changelog",
    "changelogs": "cmd_changelog",
    "checkpoint": "cmd_checkpoint",
    "cockpit": "cmd_cockpit",
    "router": "cmd_cockpit",
    "ladder": "cmd_cockpit",
    "clean": "cmd_clean",
    "project": "cmd_project",
}


def __getattr__(name: str) -> Any:
    spec = _LAZY_EXPORTS.get(name)
    if spec is None:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    mod_name, attr_name = spec
    value = getattr(importlib.import_module(mod_name), attr_name)
    globals()[name] = value
    return value


def __dir__() -> List[str]:
    return sorted(set(globals()) | set(_LAZY_EXPORTS))


def _resolve_export(name: str) -> Any:
    val = globals().get(name)
    if val is not None:
        return val
    return __getattr__(name)

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
        desc = "Agyis Harness (Legacy 'psl' CLI Alias — Deprecated: Use 'agyis')"
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

    reserved_subcommands = set(_SUBCOMMAND_ATTRS.keys()) | {"re", "ext"}

    raw_argv = sys.argv[1:] if argv is None else list(argv)
    if raw_argv and not raw_argv[0].startswith("-"):
        first_tok = raw_argv[0]
        if first_tok == "re":
            return _resolve_export("cmd_re")(raw_argv[1:])
        if first_tok == "ext":
            return _resolve_export("cmd_ext")(raw_argv[1:])
        # Check if first token matches a workspace extension command (never shadow built-ins)
        if first_tok not in reserved_subcommands:
            exts = _resolve_export("discover_workspace_commands")()
            if first_tok in exts:
                return _resolve_export("execute_extension_command")(exts[first_tok], raw_argv[1:])

    parser = build_parser(prog=prog)
    args = parser.parse_args(argv)

    if not args.subcommand:
        parser.print_help()
        return 0

    if args.subcommand == "re":
        return _resolve_export("cmd_re")(getattr(args, "re_args", []))

    if args.subcommand == "ext":
        return _resolve_export("cmd_ext")(getattr(args, "ext_args", []))

    handler_attr = _SUBCOMMAND_ATTRS.get(args.subcommand)
    if handler_attr:
        return _resolve_export(handler_attr)(args)

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
