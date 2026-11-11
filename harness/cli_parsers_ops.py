# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Arafat Zahan (@kuasha420)
# Corporate Stewardship & Infrastructure: Purrfect Software Limited (PSL)
# Governed by: ICARO-42/b Ordinance (Company-Supported Personal IP Framework)

"""Operational CLI subparser registrations for Agyis harness."""

from __future__ import annotations

import argparse
from pathlib import Path


def register_ops_parsers(subparsers: argparse._SubParsersAction) -> None:
    """Register GUI, release, checkpoint, cockpit, clean, RE, and extension subparsers."""
    # gui
    p_gui = subparsers.add_parser(
        "gui",
        help="Control and introspect Google Antigravity GUI via Chrome DevTools Protocol (CDP)",
        description="Google Antigravity Desktop GUI Telemetry & DevTools Controller (ADR-014)",
    )
    p_gui.add_argument(
        "--devtools",
        action="store_true",
        help="Inspect active Antigravity DevTools port and display CDP connection URLs",
    )
    p_gui.add_argument(
        "--trajectory-debug",
        action="store_true",
        help="Inject developer flags and trigger Trajectory Debug View (?trajectoryDebugOpen=true)",
    )
    p_gui.add_argument(
        "--toggle",
        action="store_true",
        help="Toggle Trajectory Debug View open/closed state",
    )
    p_gui.add_argument(
        "--no-popup", "--no-open", "--setup-only",
        action="store_true",
        dest="no_popup",
        help="Inject developer flags and hotkeys without opening the Trajectory Debug View modal popup",
    )
    p_gui.add_argument(
        "--wait",
        type=float,
        default=None,
        metavar="SECONDS",
        help="Wait/poll timeout in seconds for active Antigravity webview to become ready",
    )
    p_gui.add_argument(
        "--port-file",
        type=Path,
        default=None,
        help="Path to DevToolsActivePort file (default: ~/.config/Antigravity/DevToolsActivePort)",
    )
    p_gui.add_argument(
        "--timeout",
        type=float,
        default=5.0,
        help="Connection timeout in seconds (default: 5.0)",
    )
    p_gui.add_argument(
        "--hud",
        action="store_true",
        help="Inject or update real-time token burn velocity HUD badge in Google Antigravity GUI",
    )
    p_gui.add_argument(
        "--hud-remove",
        action="store_true",
        help="Remove real-time token burn velocity HUD badge from Google Antigravity GUI",
    )
    p_gui.add_argument(
        "--server",
        action="store_true",
        help="Start background Trajectory HTTP API server and keep alive",
    )
    p_gui.add_argument(
        "--server-port",
        type=int,
        default=40624,
        help="Port for Trajectory HTTP API server (default: 40624)",
    )
    p_gui.add_argument(
        "--service",
        choices=["install", "status", "start", "stop", "uninstall"],
        default=None,
        help="Manage automatic GUI HUD unlock systemd user service (install, status, start, stop, uninstall)",
    )
    p_gui.add_argument(
        "--json",
        action="store_true",
        help="Output result in JSON format",
    )
    p_gui.add_argument(
        "-v", "--verbose",
        action="store_true",
        help="Print verbose retry diagnostics to stderr",
    )

    # release-notes
    p_relnotes = subparsers.add_parser(
        "release-notes",
        help="Generate conventional release notes from git commits and PR references",
        description="Conventional Release Notes Generator & GitHub Release Synchronizer (Milestone M1)",
    )
    p_relnotes.add_argument(
        "--tag",
        type=str,
        default=None,
        help="Target release tag or ref (default: HEAD or latest tag)",
    )
    p_relnotes.add_argument(
        "--base",
        type=str,
        default=None,
        help="Base release tag or ref to compare against (default: auto-detected predecessor tag)",
    )
    p_relnotes.add_argument(
        "--rev",
        type=str,
        default=None,
        help="Target git revision to inspect (defaults to --tag if valid ref, else HEAD)",
    )
    p_relnotes.add_argument(
        "--output", "-o",
        type=str,
        default=None,
        help="Output markdown file path",
    )
    p_relnotes.add_argument(
        "--gh-release",
        type=str,
        default=None,
        help="Create or edit GitHub release using gh CLI",
    )
    p_relnotes.add_argument(
        "--title",
        type=str,
        default=None,
        help="GitHub release title override when syncing via --gh-release",
    )
    rel_pre_group = p_relnotes.add_mutually_exclusive_group()
    rel_pre_group.add_argument(
        "--prerelease",
        dest="prerelease",
        action="store_true",
        default=argparse.SUPPRESS,
        help="Mark GitHub release as prerelease when syncing via --gh-release",
    )
    rel_pre_group.add_argument(
        "--no-prerelease",
        dest="prerelease",
        action="store_false",
        default=argparse.SUPPRESS,
        help="Mark GitHub release as stable (non-prerelease) when syncing via --gh-release",
    )
    p_relnotes.set_defaults(prerelease=None)
    p_relnotes.add_argument(
        "--workspace", "-w",
        type=Path,
        default=None,
        help="Path to git repository workspace (default: current directory)",
    )
    p_relnotes.add_argument(
        "--repo-url",
        type=str,
        default=None,
        help="GitHub repository URL override for changelog compare links",
    )
    p_relnotes.add_argument(
        "--json",
        action="store_true",
        help="Output release notes and structured categories in JSON format",
    )

    # changelog (alias: changelogs)
    p_changelog = subparsers.add_parser(
        "changelog",
        aliases=["changelogs"],
        help="Generate, update, or backfill Keep-a-Changelog entries in CHANGELOG.md",
        description="Native Keep-a-Changelog Generator & Idempotent CHANGELOG.md Manager",
    )
    p_changelog.add_argument(
        "--tag",
        "--version",
        dest="tag",
        type=str,
        default=None,
        help="Target release tag or version (default: Unreleased)",
    )
    p_changelog.add_argument(
        "--base",
        type=str,
        default=None,
        help="Base release tag or ref to compare against (default: latest/predecessor tag)",
    )
    p_changelog.add_argument(
        "--rev",
        type=str,
        default=None,
        help="Target git revision to inspect (defaults to --tag if valid ref, else HEAD)",
    )
    p_changelog.add_argument(
        "--date",
        type=str,
        default=None,
        help="Release date override in YYYY-MM-DD format (default: git tag date or today UTC)",
    )
    p_changelog.add_argument(
        "--file", "-f",
        type=Path,
        default=Path("CHANGELOG.md"),
        help="Target changelog file path (default: CHANGELOG.md)",
    )
    p_changelog.add_argument(
        "--write",
        action="store_true",
        help="Write/upsert the generated changelog into --file",
    )
    p_changelog.add_argument(
        "--backfill",
        action="store_true",
        help="Backfill missing SemVer release tags plus [Unreleased] into --file",
    )
    p_changelog.add_argument(
        "--style",
        choices=["canonical", "keepachangelog"],
        default="canonical",
        help="Section heading style (default: canonical)",
    )
    p_changelog.add_argument(
        "--workspace", "-w",
        type=Path,
        default=None,
        help="Path to git repository workspace (default: current directory)",
    )
    p_changelog.add_argument(
        "--repo-url",
        type=str,
        default=None,
        help="GitHub repository URL override for compare reference links",
    )
    p_changelog.add_argument(
        "--json",
        action="store_true",
        help="Output structured changelog result in JSON format",
    )

    # checkpoint
    p_checkpoint = subparsers.add_parser(
        "checkpoint",
        help="Pre-compaction state capture, verification, and checkpoint status (ADR-031)",
        description="Compaction Checkpoint Engine & Pre-Compaction Handoff Automation",
    )
    p_checkpoint.add_argument(
        "--plan",
        type=Path,
        default=None,
        help="Path to implementation plan markdown file",
    )
    p_checkpoint.add_argument(
        "--out",
        type=Path,
        default=None,
        help="Custom output markdown file path",
    )
    p_checkpoint.add_argument(
        "--workspace", "-w",
        type=Path,
        default=None,
        help="Path to workspace directory (default: current directory)",
    )
    p_checkpoint.add_argument(
        "--role",
        type=str,
        default=None,
        help="Orchestrator role identifier (default: from env or agyis_coordinator)",
    )
    p_checkpoint.add_argument(
        "--trigger-tokens",
        type=int,
        default=None,
        help="Context tokens trigger threshold (default: auto-scaled from active context window or 230,000)",
    )
    p_checkpoint.add_argument(
        "--max-age-mins",
        type=float,
        default=60.0,
        help="Maximum allowable checkpoint age in minutes for verify (default: 60)",
    )
    p_checkpoint.add_argument(
        "--json",
        action="store_true",
        help="Output result in JSON format",
    )
    p_checkpoint.add_argument(
        "--brain-dir",
        type=Path,
        default=None,
        help="Path to conversation brain directory (default: from env or ~/.gemini/antigravity/brain/<conv_id>)",
    )

    cp_subparsers = p_checkpoint.add_subparsers(
        dest="checkpoint_action",
        help="Checkpoint action (default: generate)",
    )

    # checkpoint generate
    p_cp_gen = cp_subparsers.add_parser(
        "generate",
        aliases=["create"],
        help="Generate compaction checkpoint artifact",
        description="Capture runtime ground truth into compaction checkpoint artifact",
    )
    p_cp_gen.add_argument(
        "--plan",
        type=Path,
        default=argparse.SUPPRESS,
        help="Path to implementation plan markdown file",
    )
    p_cp_gen.add_argument(
        "--out",
        type=Path,
        default=argparse.SUPPRESS,
        help="Custom output markdown file path",
    )
    p_cp_gen.add_argument(
        "--workspace", "-w",
        type=Path,
        default=argparse.SUPPRESS,
        help="Path to workspace directory (default: current directory)",
    )
    p_cp_gen.add_argument(
        "--role",
        type=str,
        default=argparse.SUPPRESS,
        help="Orchestrator role identifier",
    )
    p_cp_gen.add_argument(
        "--trigger-tokens",
        type=int,
        default=argparse.SUPPRESS,
        help="Context tokens trigger threshold (default: auto-scaled from active context window or 230,000)",
    )
    p_cp_gen.add_argument(
        "--brain-dir",
        type=Path,
        default=argparse.SUPPRESS,
        help="Path to conversation brain directory (default: from env or ~/.gemini/antigravity/brain/<conv_id>)",
    )
    p_cp_gen.add_argument(
        "--json",
        action="store_true",
        default=argparse.SUPPRESS,
        help="Output result in JSON format",
    )

    # checkpoint verify
    p_cp_ver = cp_subparsers.add_parser(
        "verify",
        help="Verify latest checkpoint presence and freshness",
        description="Assert compaction_checkpoint_latest.md exists and is within max-age",
    )
    p_cp_ver.add_argument(
        "--max-age-mins",
        type=float,
        default=argparse.SUPPRESS,
        help="Maximum allowable checkpoint age in minutes (default: 60)",
    )
    p_cp_ver.add_argument(
        "--workspace", "-w",
        type=Path,
        default=argparse.SUPPRESS,
        help="Path to workspace directory (default: current directory)",
    )
    p_cp_ver.add_argument(
        "--json",
        action="store_true",
        default=argparse.SUPPRESS,
        help="Output result in JSON format",
    )

    # checkpoint status
    p_cp_stat = cp_subparsers.add_parser(
        "status",
        help="Display token, subagent, git, and checkpoint status",
        description="Display runtime status overview of compaction checkpoint parameters",
    )
    p_cp_stat.add_argument(
        "--workspace", "-w",
        type=Path,
        default=argparse.SUPPRESS,
        help="Path to workspace directory (default: current directory)",
    )
    p_cp_stat.add_argument(
        "--trigger-tokens",
        type=int,
        default=argparse.SUPPRESS,
        help="Context tokens trigger threshold (default: auto-scaled from active context window or 230,000)",
    )
    p_cp_stat.add_argument(
        "--json",
        action="store_true",
        default=argparse.SUPPRESS,
        help="Output result in JSON format",
    )

    # checkpoint prune
    p_cp_prune = cp_subparsers.add_parser(
        "prune",
        help="Prune stale historical compaction checkpoints",
        description="Retain top N historical checkpoints while preserving compaction_checkpoint_latest.md",
    )
    p_cp_prune.add_argument(
        "--retention",
        "--keep",
        dest="retention",
        type=int,
        default=None,
        help="Number of historical checkpoints to retain (default: AGYIS_CHECKPOINT_RETENTION or 5)",
    )
    p_cp_prune.add_argument(
        "--dry-run",
        action="store_true",
        help="Preview candidate stale checkpoints without deleting files",
    )
    p_cp_prune.add_argument(
        "--workspace", "-w",
        type=Path,
        default=argparse.SUPPRESS,
        help="Path to workspace directory (default: current directory)",
    )
    p_cp_prune.add_argument(
        "--json",
        action="store_true",
        default=argparse.SUPPRESS,
        help="Output result in JSON format",
    )

    # cockpit
    p_cockpit = subparsers.add_parser(
        "cockpit",
        help="Flight deck pairing, workflow routing, and invariant audit (Issue #92)",
        description="Agyis Cockpit Flight Director Suite",
    )
    p_cockpit.add_argument(
        "--workspace", "-w",
        type=Path,
        default=None,
        help="Path to workspace directory (default: current directory)",
    )
    p_cockpit.add_argument(
        "--json",
        action="store_true",
        help="Output result in JSON format",
    )
    cockpit_subparsers = p_cockpit.add_subparsers(
        dest="cockpit_action",
        title="actions",
        description="Flight director commands",
    )

    # cockpit status
    p_cp_stat_cmd = cockpit_subparsers.add_parser(
        "status",
        help="Display flight deck status, attention horizon, git, and subagents",
        description="Display runtime status overview of flight deck parameters",
    )
    p_cp_stat_cmd.add_argument(
        "--workspace", "-w",
        type=Path,
        default=None,
        help="Path to workspace directory (default: current directory)",
    )
    p_cp_stat_cmd.add_argument(
        "--json",
        action="store_true",
        help="Output result in JSON format",
    )

    # cockpit route
    p_cp_route = cockpit_subparsers.add_parser(
        "route",
        help="Display dispatch briefing & payload template for a canonical workflow",
        description="Display dispatch briefing and psl_stage_transition_payload.json template",
    )
    p_cp_route.add_argument(
        "workflow",
        type=str,
        help="Workflow route letter (A-L) or alias (e.g. rca, feature, builder, overhaul, victory)",
    )
    p_cp_route.add_argument(
        "--task-id",
        type=str,
        default="TASK-001",
        help="Task or phase identifier (default: TASK-001)",
    )
    p_cp_route.add_argument(
        "--workspace", "-w",
        type=Path,
        default=None,
        help="Path to workspace directory (default: current directory)",
    )
    p_cp_route.add_argument(
        "--json",
        action="store_true",
        help="Output dispatch briefing in JSON format",
    )

    # cockpit verify
    p_cp_verify = cockpit_subparsers.add_parser(
        "verify",
        help="Audit active session against the 5 flight director invariants",
        description="Audit flight deck invariants (clean product code, clean scratchpads, no orphaned worktrees)",
    )
    p_cp_verify.add_argument(
        "--allow-dirty",
        action="store_true",
        help="Permit in-flight uncommitted product code modifications",
    )
    p_cp_verify.add_argument(
        "--workspace", "-w",
        type=Path,
        default=None,
        help="Path to workspace directory (default: current directory)",
    )
    p_cp_verify.add_argument(
        "--json",
        action="store_true",
        help="Output audit result in JSON format",
    )

    # router / ladder aliases
    for alias_name in ("router", "ladder"):
        p_alias = subparsers.add_parser(
            alias_name,
            help="Dynamic subagent router (alias for 'cockpit route')",
            description="Dynamic subagent router & execution pipeline",
        )
        p_alias.add_argument(
            "workflow",
            type=str,
            nargs="?",
            default="status",
            help="Workflow route letter (A-L) or alias (e.g. rca, feature, builder, overhaul, victory)",
        )
        p_alias.add_argument(
            "--task-id",
            type=str,
            default="TASK-001",
            help="Task or phase identifier (default: TASK-001)",
        )
        p_alias.add_argument(
            "--workspace", "-w",
            type=Path,
            default=None,
            help="Path to workspace directory (default: current directory)",
        )
        p_alias.add_argument(
            "--json",
            action="store_true",
            help="Output in JSON format",
        )

    # clean
    p_clean = subparsers.add_parser(
        "clean",
        help="Clean workspace debris, stale checkpoints, worktrees, and scratchpads",
        description="Agyis Workspace & File Management Hygiene (Issue #90)",
    )
    p_clean.add_argument(
        "--checkpoints",
        action="store_true",
        help="Prune historical compaction checkpoints in .agents/artifacts/",
    )
    p_clean.add_argument(
        "--worktrees",
        action="store_true",
        help="Prune dead git worktrees and orphaned subagent directories",
    )
    p_clean.add_argument(
        "--branches",
        action="store_true",
        help="Delete merged ephemeral subagent-* git branches",
    )
    p_clean.add_argument(
        "--scratch",
        action="store_true",
        help="Clean expired ephemeral files in scratch/ directories",
    )
    p_clean.add_argument(
        "--dist",
        action="store_true",
        help="Remove build/distribution artifacts in dist/ (opt-in; preserves .git*)",
    )
    p_clean.add_argument(
        "--all",
        action="store_true",
        help="Execute all standard cleanup actions (checkpoints, worktrees, branches, scratch; excludes dist/ unless --dist is passed)",
    )
    p_clean.add_argument(
        "--retention",
        type=int,
        default=5,
        help="Number of historical checkpoints to retain (default: 5)",
    )
    p_clean.add_argument(
        "--scratch-hours",
        type=float,
        default=24.0,
        help="Age threshold in hours for scratchpad expiration (default: 24.0)",
    )
    p_clean.add_argument(
        "--dry-run",
        action="store_true",
        help="Preview files and branches to be removed without modifying disk",
    )
    p_clean.add_argument(
        "--workspace",
        "-w",
        type=Path,
        default=None,
        help="Path to workspace root (default: current working directory)",
    )
    p_clean.add_argument(
        "--json",
        action="store_true",
        help="Output structured cleanup report in JSON format",
    )

    # re
    p_re = subparsers.add_parser(
        "re",
        help="Cleanroom reverse engineering & dirty-room toolsuite (ADR-028, PSL-INV-009)",
        description="Unified RE pipeline, sub-2s Ghidra project acceleration, and dirtyroom governance",
    )
    p_re.add_argument("re_args", nargs=argparse.REMAINDER, help="Arguments passed to 'agyis re'")

    # ext
    p_ext = subparsers.add_parser(
        "ext",
        help="Workspace CLI command extensions (ADR-034)",
        description="Run, list, or scaffold project-specific CLI extension commands",
    )
    p_ext.add_argument("ext_args", nargs=argparse.REMAINDER, help="Arguments passed to 'agyis ext'")
