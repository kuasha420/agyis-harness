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
from harness.commands import (
    cmd_agents,
    cmd_audit,
    cmd_auth,
    cmd_doctor,
    cmd_harmonize,
    cmd_hook,
    cmd_init,
    cmd_install,
    cmd_onboard,
    cmd_remote,
    cmd_skills,
    cmd_status,
    cmd_subagents,
    cmd_sync,
    cmd_test,
    cmd_uninstall,
)

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

    # doctor
    p_doc = subparsers.add_parser(
        "doctor",
        help="Audit host workstation runtimes and auto-heal",
        description="Agyis Workstation Diagnostic & Runtime Guarantee (Antigravity Immune System)",
    )
    p_doc.add_argument("--matrix", type=Path, default=None, help="Path to matrix.json")
    p_doc.add_argument("--heal", action="store_true", help="Execute safe user-space auto-healing")
    p_doc.add_argument("--json", action="store_true", help="Output audit report in JSON format")
    p_doc.add_argument(
        "--experimental-rea",
        action="store_true",
        help="Enable experimental Reverse Engineer Anything (REA) diagnostics and provider audit",
    )

    # hook
    p_hook = subparsers.add_parser("hook", help="Run a lifecycle hook handler directly")
    p_hook.add_argument(
        "hook_name",
        choices=[
            "command-safety", "safety",
            "anti-loop", "loop",
            "output-compactor", "compactor",
            "verification-fence", "fence", "stop-fence", "stop", "completion-fence",
            "anti-drift", "drift", "anti_drift",
        ],
        help="Name of the lifecycle hook to invoke",
    )

    # test
    p_test = subparsers.add_parser("test", help="Run the test suite")
    p_test.add_argument("-v", "--verbose", action="store_true", help="Verbose test runner output")
    p_test.add_argument("-s", "--start-dir", type=Path, default=None, help="Start directory for tests")

    # audit
    p_audit = subparsers.add_parser("audit", help="Run empirical telemetry laboratory pipelines")
    p_audit.add_argument(
        "stage",
        nargs="?",
        default="all",
        choices=[
            "all", "extract", "benchmark", "classify", "inventory", "dynamics",
            "traces", "interventions", "volume", "deep", "session", "live", "clusters",
        ],
        help="Audit pipeline stage to run (default: all)",
    )
    p_audit.add_argument("--db", type=str, default=None, help="Path to SQLite database")
    p_audit.add_argument("--conv-dir", type=str, default=None, help="Path to conversations directory containing .db files")
    p_audit.add_argument("--backfill", action="store_true", help="Force volume backfill from transcripts")
    p_audit.add_argument("--session-id", "-s", type=str, default=None, help="Target session ID for session audit")
    p_audit.add_argument("--save-db", action="store_true", help="Sync audited session into data/telemetry.db")
    p_audit.add_argument("--out", type=Path, default=None, help="Export session analysis JSON path")
    p_audit.add_argument("--json", action="store_true", help="Output session report in JSON format")
    p_audit.add_argument("--output-json", type=Path, default=None, help="Export analysis JSON path")
    p_audit.add_argument("--output-report", type=Path, default=None, help="Export analysis report Markdown path")
    p_audit.add_argument("--quiet", action="store_true", help="Suppress verbose stdout in pipeline stages")

    # skills
    p_skills = subparsers.add_parser("skills", help="List, inspect, and synchronize modular product skills")
    p_skills.add_argument("name", nargs="?", default=None, help="Name of specific skill to view or sync")
    p_skills.add_argument("--sync", action="store_true", help="Sync skills to .agents/skills")
    p_skills.add_argument("--group", "-g", type=str, default=None, help="Sync skills by group preset (stack, testing, runners, ops, workstation, workflow, ladder)")
    p_skills.add_argument("--stack", "-s", type=str, default=None, help="Sync skills tailored for stack preset (python, typescript, rust, go, systems, shell, auto)")
    p_skills.add_argument("--skills", type=str, default=None, help="Comma-separated skill names to sync")
    p_skills.add_argument("--override", action="store_true", help="Force overwrite existing skill files")
    p_skills.add_argument("--workspace", "-w", nargs="?", const=True, default=None, help="Sync to workspace (.agents/skills) instead of global/repo")
    p_skills.add_argument("--no-dedup", action="store_true", help="Disable deduplication when syncing skills")
    p_skills.add_argument("--prune-duplicates", action="store_true", help="Prune redundant workspace skills that shadow plugin skills")
    p_skills.add_argument("--dry-run", action="store_true", help="Simulate pruning duplicate skills without modifying disk")
    p_skills.add_argument("--config-dir", type=Path, default=None, help="Target configuration directory (default: ~/.gemini/config)")
    p_skills.add_argument("--json", action="store_true", help="Output skills in JSON format")

    # agents
    p_agents = subparsers.add_parser("agents", help="List, inspect, create, validate, or rehydrate specialist subagents")
    p_agents.add_argument("name", nargs="?", default=None, help="Name of specific agent to view, or action (create, validate, rehydrate)")
    p_agents.add_argument("target_name", nargs="?", default=None, help="Target agent name for create or file/name for validate/rehydrate")
    p_agents.add_argument("--sync", action="store_true", help="Sync agent definitions to .agents/agents")
    p_agents.add_argument("--workspace", "-w", nargs="?", const=True, default=None, help="Sync to workspace (.agents/agents) instead of global/repo")
    p_agents.add_argument("--agents", type=str, default=None, help="Comma-separated list of agent names to sync")
    p_agents.add_argument("--override", action="store_true", help="Force overwrite existing agents")
    p_agents.add_argument("--no-dedup", action="store_true", help="Disable deduplication when syncing agents")
    p_agents.add_argument("--json", action="store_true", help="Output agents in JSON format")
    p_agents.add_argument("--id", type=str, default=None, help="Conversation ID to rehydrate")
    p_agents.add_argument("--recent-hours", type=int, default=4, help="Recent hours window for subagent discovery")
    p_agents.add_argument("--brain-dir", type=Path, default=None, help="Custom brain directory path")
    p_agents.add_argument("--archetype", "-a", type=str, default=None, help="Agent archetype for creation (main, executioner, hammer, auditor, planner, coordinator)")
    p_agents.add_argument("--bundle", "-b", type=str, default=None, help="Capability bundle (read_only, verifier, builder, orchestrator, full)")
    p_agents.add_argument("--scope", type=str, choices=["project", "global"], default="project", help="Target scope (project or global)")
    p_agents.add_argument("--model", "-m", type=str, default="inherit", help="Model specification (default: inherit)")

    # subagents
    p_subagents = subparsers.add_parser(
        "subagents", help="List active subagents and context health gauge"
    )
    p_subagents.add_argument(
        "--json", action="store_true", help="Output subagents in JSON format"
    )
    p_subagents.add_argument(
        "--brain-dir", type=Path, default=None, help="Custom brain directory path"
    )

    # status / info
    subparsers.add_parser("status", help="Print harness installation and health summary")

    # remote
    p_remote = subparsers.add_parser(
        "remote", help="Remote agentic execution, script streaming & triage (ADR-027)"
    )
    p_remote_subs = p_remote.add_subparsers(dest="remote_cmd", help="Remote subcommands")

    # remote exec
    p_rexec = p_remote_subs.add_parser(
        "exec", help="Execute command on target over multiplexed SSH"
    )
    p_rexec.add_argument("target", help="Remote target (user@host or host)")
    p_rexec.add_argument("command", help="Command to execute remotely")
    p_rexec.add_argument("-p", "--port", type=int, default=None, help="SSH port")
    p_rexec.add_argument(
        "-l", "--login-shell", action="store_true", help="Wrap in login shell (bash -l -c)"
    )
    p_rexec.add_argument(
        "-t", "--timeout", type=int, default=30, help="Command timeout in seconds"
    )

    # remote script
    p_rscript = p_remote_subs.add_parser(
        "script", help="Stream or stage local script to remote target"
    )
    p_rscript.add_argument("target", help="Remote target (user@host or host)")
    p_rscript.add_argument("script", type=Path, help="Local script file to execute remotely")
    p_rscript.add_argument(
        "--stage", action="store_true", help="Stage file on remote target with trap cleanup"
    )
    p_rscript.add_argument("-p", "--port", type=int, default=None, help="SSH port")
    p_rscript.add_argument(
        "-t", "--timeout", type=int, default=60, help="Command timeout in seconds"
    )
    p_rscript.add_argument("args", nargs="*", default=[], help="Arguments to pass to script")

    # remote triage
    p_rtriage = p_remote_subs.add_parser(
        "triage", help="Run bounded diagnostic audit on remote host"
    )
    p_rtriage.add_argument("target", help="Remote target (user@host or host)")
    p_rtriage.add_argument(
        "--profile",
        choices=["all", "ports", "services", "resources", "logs"],
        default="all",
        help="Diagnostic profile filter (default: all)",
    )
    p_rtriage.add_argument(
        "--service", type=str, default=None, help="Target service name for log inspection"
    )
    p_rtriage.add_argument("-n", "--lines", type=int, default=50, help="Log line count limit")
    p_rtriage.add_argument("-p", "--port", type=int, default=None, help="SSH port")
    p_rtriage.add_argument(
        "-t", "--timeout", type=int, default=30, help="Probe timeout in seconds"
    )
    p_rtriage.add_argument("--json", action="store_true", help="Output report in JSON format")

    # remote socket
    p_rsock = p_remote_subs.add_parser(
        "socket", help="Inspect or clean up ControlMaster sockets"
    )
    p_rsock.add_argument(
        "socket_action",
        nargs="?",
        choices=["cleanup", "status"],
        default="status",
        help="Socket action to perform (default: status)",
    )

    # remote screens
    p_rscreens = p_remote_subs.add_parser(
        "screens", help="Capture and generate fleet screens carousel artifact"
    )
    p_rscreens.add_argument(
        "--brain-dir", type=Path, default=None, help="Custom brain directory path"
    )
    p_rscreens.add_argument(
        "--data", type=str, default=None, help="Path to JSON file or inline JSON with screen captures"
    )
    p_rscreens.add_argument(
        "--json", action="store_true", help="Output result in JSON format"
    )

    # auth
    p_auth = subparsers.add_parser("auth", help="Manage GitHub organization authentication for telemetry")
    auth_subs = p_auth.add_subparsers(dest="auth_cmd", help="Auth subcommands")

    p_auth_login = auth_subs.add_parser("login", help="Authenticate with GitHub Personal Access Token")
    p_auth_login.add_argument("--token", "-t", type=str, default=None, help="GitHub Personal Access Token")
    p_auth_login.add_argument("--gh", action="store_true", help="Lift token directly from GitHub CLI ('gh auth token')")
    p_auth_login.add_argument("--workspace", "-w", dest="workspace_scope", action="store_true", help="Store endpoint in workspace config (.agyis/config.json or .psl/config.json)")
    p_auth_login.add_argument("--endpoint", "-e", type=str, default=None, help="Central telemetry hub endpoint URL")
    p_auth_login.add_argument("--json", action="store_true", help="Output result in JSON format")

    p_auth_status = auth_subs.add_parser("status", help="Display current telemetry authentication status")
    p_auth_status.add_argument("--json", action="store_true", help="Output status in JSON format")

    p_auth_logout = auth_subs.add_parser("logout", help="Log out and clear stored telemetry credentials")
    p_auth_logout.add_argument("--json", action="store_true", help="Output result in JSON format")

    # sync
    p_sync = subparsers.add_parser("sync", help="Synchronize telemetry with the central hub (bi-directional default)")
    p_sync.add_argument("--push", action="store_true", help="Push local unsynced telemetry to remote hub")
    p_sync.add_argument("--pull", action="store_true", help="Pull remote telemetry deltas into local database")
    p_sync.add_argument("--remote", "-r", type=str, default=None, help="Central telemetry hub endpoint URL")
    p_sync.add_argument("--db", type=str, default=None, help="Path to SQLite telemetry database")
    p_sync.add_argument("--interactive", "-i", action="store_true", help="Interactively confirm batch push")
    p_sync.add_argument("--review", action="store_true", help="Interactively review and select candidate sessions to push")
    p_sync.add_argument("--watch", action="store_true", help="Continuously watch and sync telemetry in the background")
    p_sync.add_argument("--interval", type=float, default=5.0, help="Poll interval in seconds for watch mode (default: 5.0)")
    p_sync.add_argument("--systemd", action="store_true", help="Output systemd user service unit definition")
    p_sync.add_argument("--limit", "-l", type=int, default=None, help="Maximum number of sessions to push")
    p_sync.add_argument("--dry-run", action="store_true", help="Simulate synchronization without modifications")
    p_sync.add_argument("--session-id", "-s", type=str, default=None, help="Target session ID to ingest before syncing")
    p_sync.add_argument("--json", action="store_true", help="Output sync summary in JSON format")
    p_sync.add_argument("--all-developers", "--all", action="store_true", dest="all_developers", help="Pull telemetry across all developers and devices (bypasses anti-echo filter)")
    p_sync.add_argument("--developer", type=str, default=None, help="Filter pulled telemetry by specific developer username (or '*' for all)")
    p_sync.add_argument("--since", type=str, default=None, help="Pull telemetry deltas since a specific ISO timestamp watermark")

    ROLE_CHOICES = [
        "backend",
        "frontend",
        "fullstack",
        "cli",
        "library",
        "mobile",
        "desktop_gui",
        "media",
        "audio",
        "infra",
    ]

    # init
    p_init = subparsers.add_parser(
        "init", help="Initialize workspace with stack-tailored skills and tagged rules"
    )
    p_init.add_argument("path", nargs="?", default=None, help="Target workspace path (defaults to current directory)")
    p_init.add_argument(
        "--stack",
        "--lang",
        "-s",
        dest="stack",
        type=str,
        default=None,
        help="Language runtime preset (typescript, node, javascript, python, rust, go, systems, shell, audit, all)",
    )
    p_init.add_argument(
        "--role",
        "-r",
        type=str,
        choices=ROLE_CHOICES,
        default=None,
        help="Architectural role preset (backend, frontend, fullstack, cli, library, mobile, desktop_gui, media, audio, infra)",
    )
    p_init.add_argument(
        "--subproject",
        type=str,
        default=None,
        help="Relative path to subproject within workspace for targeted detection",
    )
    p_init.add_argument("--skills", type=str, default=None, help="Comma-separated list of skills to install")
    p_init.add_argument("--agents", type=str, nargs="?", const=True, default=None, help="Install agent definitions locally into workspace (.agents/agents)")
    p_init.add_argument("--override", action="store_true", help="Force overwrite existing files")
    p_init.add_argument("--no-dedup", action="store_true", help="Disable content-hash deduplication")
    p_init.add_argument("--dry-run", action="store_true", help="Simulate workspace initialization without modifications")
    p_init.add_argument("--yes", "-y", action="store_true", help="Non-interactive mode, apply defaults")
    p_init.add_argument("--json", action="store_true", help="Output result in JSON format")
    p_init.add_argument(
        "--experimental-rea",
        action="store_true",
        help="Initialize workspace with opt-in Reverse Engineer Anything (REA) support",
    )

    # harmonize
    p_harm = subparsers.add_parser(
        "harmonize", help="Harmonize legacy .agent/ directories and PSL-HARNESS rules into modern .agents/ structure"
    )
    p_harm.add_argument("path", nargs="?", default=None, help="Target workspace path (defaults to current directory)")
    p_harm.add_argument("--dry-run", action="store_true", help="Preview harmonization actions without modifying files")
    p_harm.add_argument("--json", action="store_true", help="Output harmonization report in JSON format")
    p_harm.add_argument("--prune-legacy", action="store_true", help="Safely remove or git-rm legacy .agent/ directory after successful migration")
    p_harm.add_argument("--clean-agent-dir", action="store_true", help="Alias for --prune-legacy")
    p_harm.add_argument("--backup", action="store_true", default=True, help="Create compressed archive of legacy .agent/ before pruning (default: true)")
    p_harm.add_argument("--no-backup", action="store_true", help="Disable archival before pruning")
    p_harm.add_argument("--backup-dir", "--archive-dir", dest="backup_dir", type=Path, default=None, help="Destination directory for backup archive (default: <workspace>/.agents/archive/)")
    p_harm.add_argument("--stack", "--lang", dest="stack", type=str, default=None, help="Provision stack skills immediately following harmonization")
    p_harm.add_argument("--role", "-r", type=str, choices=ROLE_CHOICES, default=None, help="Architectural role preset for provisioned skills")
    p_harm.add_argument("--subproject", type=str, default=None, help="Target specific subproject within monorepo")
    p_harm.add_argument("--skills", type=str, default=None, help="Comma-separated list of explicit modular skills to install")

    # onboard
    p_onboard = subparsers.add_parser(
        "onboard", help="Unified workspace onboarding with topology probing, harmonization, skills, and PR delivery"
    )
    p_onboard.add_argument("path", nargs="?", default=None, help="Target workspace path (defaults to current directory)")
    p_onboard.add_argument(
        "--lang",
        "--stack",
        "-s",
        dest="lang",
        type=str,
        default=None,
        help="Language runtime preset (typescript, node, javascript, python, rust, go, systems, shell, auto)",
    )
    p_onboard.add_argument(
        "--role",
        "-r",
        type=str,
        choices=ROLE_CHOICES,
        default=None,
        help="Architectural role preset (backend, frontend, fullstack, cli, library, mobile, desktop_gui, media, audio, infra)",
    )
    p_onboard.add_argument(
        "--subproject",
        type=str,
        default=None,
        help="Subproject path for localized monorepo onboarding",
    )
    p_onboard.add_argument(
        "--upstream-remote",
        type=str,
        default=None,
        help="Explicit upstream canonical remote name (e.g. upstream, canonical, purrfectsoft)",
    )
    p_onboard.add_argument(
        "--base-branch",
        type=str,
        default=None,
        help="Explicit base branch to target (default: auto-detected default/active branch)",
    )
    p_onboard.add_argument(
        "--prune-legacy",
        action="store_true",
        help="Prune legacy .agent/ directory after harmonization",
    )
    p_onboard.add_argument(
        "--pr",
        "--open-pr",
        "--create-pr",
        dest="pr",
        action="store_true",
        help="Open GitHub Pull Request using 'gh pr create' upon verification",
    )
    p_onboard.add_argument(
        "--dry-run",
        action="store_true",
        help="Preview all onboarding actions without filesystem or remote mutation",
    )
    p_onboard.add_argument(
        "--json",
        action="store_true",
        help="Output structured JSON summary",
    )
    p_onboard.add_argument(
        "--experimental-rea",
        action="store_true",
        help="Onboard repository with opt-in Reverse Engineer Anything (REA) support",
    )

    # install
    p_install = subparsers.add_parser(
        "install", help="Install Agyis harness globally as Google Antigravity plugin or initialize workspace"
    )
    p_install.add_argument("--global", "-g", dest="global_install", action="store_true", help="Install globally into user plugins directory (default)")
    p_install.add_argument("--bin-dir", type=Path, default=None, help="Custom binary directory for standalone CLI executable")
    p_install.add_argument("--copy", action="store_true", help="Install via copy mode")
    p_install.add_argument("--symlink", action="store_true", help="Install via symlink mode (default)")
    p_install.add_argument("--wheel", action="store_true", help="Build and install frozen release wheel via uv build")
    p_install.add_argument("--dry-run", action="store_true", help="Simulate installation without writing to disk")
    p_install.add_argument("--all-surfaces", action="store_true", help="Sync all Antigravity surfaces to canonical config")
    p_install.add_argument("--target", type=Path, default=None, help="Custom target installation directory")
    p_install.add_argument("--workspace", "-w", nargs="?", const=True, default=None, help="Initialize workspace project instead of global plugin")
    p_install.add_argument(
        "--stack",
        "--lang",
        "-s",
        dest="stack",
        type=str,
        default=None,
        help="Language runtime preset for workspace (typescript, node, javascript, python, rust, go, systems, shell, audit, all)",
    )
    p_install.add_argument(
        "--role",
        "-r",
        type=str,
        choices=ROLE_CHOICES,
        default=None,
        help="Architectural role preset for workspace (backend, frontend, fullstack, cli, library, mobile, desktop_gui, media, audio, infra)",
    )
    p_install.add_argument(
        "--subproject",
        type=str,
        default=None,
        help="Relative path to subproject within workspace for targeted detection",
    )
    p_install.add_argument("--skills", type=str, default=None, help="Comma-separated list of skills for workspace")
    p_install.add_argument("--agents", type=str, nargs="?", const=True, default=None, help="Include agent definitions in workspace (.agents/agents)")
    p_install.add_argument("--override", action="store_true", help="Force overwrite existing workspace files")
    p_install.add_argument("--no-dedup", action="store_true", help="Disable content deduplication for workspace")
    p_install.add_argument("--json", action="store_true", help="Output result in JSON format")
    p_install.add_argument(
        "--experimental-rea",
        action="store_true",
        help="Install global plugins with opt-in Reverse Engineer Anything (REA) MCP wiring",
    )

    # uninstall
    p_uninstall = subparsers.add_parser(
        "uninstall", help="Uninstall Agyis harness global plugin"
    )
    p_uninstall.add_argument("--bin-dir", type=Path, default=None, help="Custom binary directory for standalone CLI executable")
    p_uninstall.add_argument("--dry-run", action="store_true", help="Simulate uninstallation without removing files")
    p_uninstall.add_argument("--target", type=Path, default=None, help="Custom target installation directory")
    p_uninstall.add_argument("--json", action="store_true", help="Output result in JSON format")

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
    }

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
