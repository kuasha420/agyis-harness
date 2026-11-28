# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Arafat Zahan (@kuasha420)
# Corporate Stewardship & Infrastructure: Purrfect Software Limited (PSL)
# Governed by: ICARO-42/b Ordinance (Company-Supported Personal IP Framework)

"""CLI subparser registration for `agyis crosstalk`."""

from __future__ import annotations

import argparse
from pathlib import Path

from harness.delivery.crosstalk import MAX_CROSSTALK_HOPS


def _add_common_query_flags(subparser: argparse.ArgumentParser) -> None:
    """Attach shared discovery/output flags to list and search subparsers."""
    subparser.add_argument(
        "--project", "-p",
        type=str,
        default=None,
        help="Filter by project UUID, workspace path, or repo slug",
    )
    subparser.add_argument(
        "--surface",
        choices=["desktop", "cli", "ide", "all"],
        default="all",
        help="Target Antigravity surface filter (default: all)",
    )
    subparser.add_argument(
        "--include-archived",
        action="store_true",
        help="Include archived conversations in results",
    )
    subparser.add_argument(
        "--include-children",
        action="store_true",
        help="Include child subagent conversations in results",
    )
    subparser.add_argument(
        "--limit",
        type=int,
        default=20,
        help="Maximum number of conversations to return (default: 20)",
    )
    subparser.add_argument(
        "--config-dir",
        type=Path,
        default=argparse.SUPPRESS,
        help="Optional configuration directory override",
    )
    subparser.add_argument(
        "--json",
        action="store_true",
        default=argparse.SUPPRESS,
        help="Output result in JSON format",
    )


def _add_handoff_subparser(xt_subparsers: argparse._SubParsersAction) -> None:
    """Register `agyis crosstalk handoff` with D6 safety & dry-run/send flags."""
    p_handoff = xt_subparsers.add_parser(
        "handoff",
        help="Create a sanitized cross-thread or cross-project conversation handoff",
        description="Sanitized baton handoff across projects or horizontal session succession (preflight dry-run by default unless --send is passed)",
    )
    p_handoff.add_argument("--to", type=str, default=None, help="Target project UUID, path, or slug")
    p_handoff.add_argument(
        "--new",
        action="store_true",
        help="Start a new horizontal successor conversation (defaults --to to active workspace)",
    )
    p_handoff.add_argument("--project", "-p", type=str, default=None, help="Target project alias for --to")
    p_handoff.add_argument("--title", type=str, default=None, help="Title for the target conversation")
    p_handoff.add_argument("--summary", type=str, default=None, help="Concise sanitized handoff summary")
    p_handoff.add_argument("--task", type=str, default=None, help="Actionable next task brief for the target thread")
    p_handoff.add_argument("--brief", type=str, default=None, help="Combined brief text override")
    p_handoff.add_argument(
        "--hops",
        type=int,
        default=None,
        help="Explicit hop number override (auto-incremented from inbound baton if omitted)",
    )
    p_handoff.add_argument(
        "--max-hops",
        type=int,
        default=MAX_CROSSTALK_HOPS,
        help=f"Maximum hop budget (default: {MAX_CROSSTALK_HOPS}, hard ceiling: 3)",
    )
    p_handoff.add_argument(
        "--source-visibility",
        choices=["private", "oss"],
        default="private",
        help="Visibility tier of the source repository (default: private)",
    )
    p_handoff.add_argument(
        "--target-visibility",
        choices=["private", "oss"],
        default="private",
        help="Visibility tier of the target repository (Private -> OSS enables strict scrubbing)",
    )
    p_handoff.add_argument("--role", type=str, default=None, help="Optional role hint for SessionStart pinning")
    p_handoff.add_argument("--model", type=str, default="flash", help="Target model hint (default: flash)")
    p_handoff.add_argument("--group-id", type=str, default=None, help="Optional conversationGroupId to link threads")
    p_handoff.add_argument("--tags", type=str, default=None, help="Comma-separated extra conversation tags")
    p_handoff.add_argument("--checkpoint", type=str, default=None, help="Optional checkpoint markdown path to attach")
    p_handoff.add_argument("--include-checkpoint", action="store_true", help="Attach active CID checkpoint excerpt")
    p_handoff.add_argument("--ensure-project", action="store_true", help="Register target workspace in projects/*.json if needed")
    p_handoff.add_argument("--strict", action="store_true", help="Force strict redaction (emails, extra secret keys)")
    mode_group = p_handoff.add_mutually_exclusive_group()
    mode_group.add_argument(
        "--dry-run",
        action="store_true",
        help="Run sanitization, hop/cycle guards, and preflight preview without creating a conversation",
    )
    mode_group.add_argument(
        "--send",
        action="store_true",
        help="Dispatch live CreateConversation RPC and write Tier-1 baton ledgers",
    )
    p_handoff.add_argument("--workspace", "-w", type=Path, default=argparse.SUPPRESS, help="Source workspace path override")
    p_handoff.add_argument("--config-dir", type=Path, default=argparse.SUPPRESS, help="Optional configuration directory override")
    p_handoff.add_argument("--json", action="store_true", default=argparse.SUPPRESS, help="Output result in JSON format")


def register_crosstalk_parser(subparsers: argparse._SubParsersAction) -> None:
    """Register `agyis crosstalk` and its safe non-destructive subcommands."""
    p_xt = subparsers.add_parser(
        "crosstalk",
        help="Cross-conversation discovery, sanitized baton handoff, steering, and Generative UI widgets",
        description="Agyis Crosstalk: Cross-Project & Horizontal Context Succession Protocol",
    )
    p_xt.add_argument("--workspace", "-w", type=Path, default=None, help="Workspace root override")
    p_xt.add_argument("--config-dir", type=Path, default=None, help="Optional configuration directory override")
    p_xt.add_argument("--json", action="store_true", help="Output result in JSON format")

    xt_sub = p_xt.add_subparsers(
        dest="crosstalk_action",
        title="actions",
        description="Crosstalk discovery, handoff, steering, and widget commands",
    )

    # list
    p_list = xt_sub.add_parser("list", help="List discovered Desktop and CLI conversations")
    p_list.add_argument("--query", "-q", type=str, default=None, help="Optional search filter text")
    _add_common_query_flags(p_list)

    # search
    p_search = xt_sub.add_parser("search", help="Search conversations across SQLite FTS5 and live RPC")
    p_search.add_argument("query_arg", nargs="?", default=None, metavar="QUERY", help="Search query text")
    p_search.add_argument("--query", "-q", dest="query_flag", type=str, default=None, help="Search query text")
    _add_common_query_flags(p_search)

    # status
    p_status = xt_sub.add_parser("status", help="Inspect inbound baton, active hop count, surface, and recent threads")
    p_status.add_argument("--session", "--cid", dest="session", type=str, default=None, help="Active conversation ID override")
    p_status.add_argument("--workspace", "-w", type=Path, default=argparse.SUPPRESS, help="Workspace path override")
    p_status.add_argument("--surface", choices=["auto", "desktop", "cli"], default="auto", help="Surface detection override")
    p_status.add_argument("--limit", type=int, default=5, help="Recent threads count to include (default: 5)")
    p_status.add_argument("--config-dir", type=Path, default=argparse.SUPPRESS, help="Optional configuration directory override")
    p_status.add_argument("--json", action="store_true", default=argparse.SUPPRESS, help="Output result in JSON format")

    # inspect
    p_inspect = xt_sub.add_parser("inspect", help="Inspect conversation metadata and sanitized transcript tail")
    p_inspect.add_argument("conversation_id", type=str, help="Conversation ID to inspect")
    p_inspect.add_argument("--steps", "--tail", dest="steps", type=int, default=20, help="Trailing steps count (default: 20)")
    p_inspect.add_argument("--strict", action="store_true", help="Apply strict cross-project redaction to step previews")
    p_inspect.add_argument("--config-dir", type=Path, default=argparse.SUPPRESS, help="Optional configuration directory override")
    p_inspect.add_argument("--json", action="store_true", default=argparse.SUPPRESS, help="Output result in JSON format")

    # widget
    p_widget = xt_sub.add_parser("widget", help="Render Generative UI <agent-embed> widget or CLI fallback")
    p_widget.add_argument(
        "--kind", "--mode",
        dest="kind",
        choices=["preflight", "constellation"],
        default="constellation",
        help="Widget template kind (default: constellation)",
    )
    p_widget.add_argument("--payload", type=str, default=None, help="JSON payload file path, '-' for stdin, or inline JSON")
    p_widget.add_argument("--surface", choices=["auto", "desktop", "cli"], default="auto", help="Target UX surface (default: auto)")
    p_widget.add_argument("--title", type=str, default=None, help="Widget goal headline override")
    p_widget.add_argument("--summary", "--line", dest="summary", type=str, default=None, help="Widget summary line override")
    p_widget.add_argument("--from-project", type=str, default=None, help="Source project label override")
    p_widget.add_argument("--to-project", type=str, default=None, help="Target project label override")
    p_widget.add_argument("--artifact-dir", type=Path, default=None, help="Directory for rendered HTML artifact")
    p_widget.add_argument("--write", action="store_true", help="Write rendered HTML file to --artifact-dir or crosstalk artifact dir")
    p_widget.add_argument("--dry-run", action="store_true", help="Render in-memory without writing HTML files")
    p_widget.add_argument("--workspace", "-w", type=Path, default=argparse.SUPPRESS, help="Workspace path override")
    p_widget.add_argument("--config-dir", type=Path, default=argparse.SUPPRESS, help="Optional configuration directory override")
    p_widget.add_argument("--json", action="store_true", default=argparse.SUPPRESS, help="Output rendered payload in JSON format")

    # handoff
    _add_handoff_subparser(xt_sub)

    # send
    p_send = xt_sub.add_parser("send", help="Send a sanitized mid-flight steering message to an existing conversation")
    p_send.add_argument("target_pos", nargs="?", default=None, metavar="TARGET", help="Target conversation ID")
    p_send.add_argument("message_pos", nargs="?", default=None, metavar="MESSAGE", help="Steering message text")
    p_send.add_argument("--to", dest="to_cid", type=str, default=None, help="Target conversation ID")
    p_send.add_argument("--message", "-m", dest="message_flag", type=str, default=None, help="Steering message text")
    p_send.add_argument("--title", type=str, default=None, help="Optional notification/pill title")
    p_send.add_argument("--hops", type=int, default=1, help="Current hop number (default: 1)")
    p_send.add_argument("--max-hops", type=int, default=MAX_CROSSTALK_HOPS, help=f"Hop budget (default: {MAX_CROSSTALK_HOPS})")
    p_send.add_argument("--source-visibility", choices=["private", "oss"], default="private", help="Source visibility tier")
    p_send.add_argument("--target-visibility", choices=["private", "oss"], default="private", help="Target visibility tier")
    p_send.add_argument("--transport", choices=["auto", "agentapi", "ls_rpc"], default="auto", help="Steer transport preference")
    p_send.add_argument("--strict", action="store_true", help="Force strict redaction")
    p_send.add_argument("--dry-run", action="store_true", help="Validate and redact without sending")
    p_send.add_argument("--workspace", "-w", type=Path, default=argparse.SUPPRESS, help="Source workspace path override")
    p_send.add_argument("--config-dir", type=Path, default=argparse.SUPPRESS, help="Optional configuration directory override")
    p_send.add_argument("--json", action="store_true", default=argparse.SUPPRESS, help="Output result in JSON format")

    # archive (D6 safety: soft-archive only, NEVER expose delete)
    p_arch = xt_sub.add_parser("archive", help="Soft-archive or unarchive a conversation (non-destructive)")
    p_arch.add_argument("conversation_id", type=str, help="Conversation ID to soft-archive or unarchive")
    p_arch.add_argument("--unarchive", action="store_true", help="Restore an archived conversation")
    p_arch.add_argument("--dry-run", action="store_true", help="Preview UpdateConversation payload without calling RPC")
    p_arch.add_argument("--json", action="store_true", default=argparse.SUPPRESS, help="Output result in JSON format")


__all__ = ["register_crosstalk_parser"]
