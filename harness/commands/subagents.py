# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Purrfect Software Limited (PSL)

"""
Active subagents context status and inspection CLI command (ADR-014, ADR-025).
"""

from __future__ import annotations

import argparse
import json
from typing import Any, List


def format_subagents_table(statuses: List[Any]) -> str:
    """Format a list of SubagentContextStatus as an ASCII table."""
    if not statuses:
        return "No active subagents found."

    headers = [
        "Conversation ID",
        "Role",
        "Steps",
        "Tokens",
        "Health Zone",
        "Recommendation",
        "Latency",
    ]
    rows = []
    for s in statuses:
        cid = s.conversation_id[:12] if len(s.conversation_id) > 12 else s.conversation_id
        hz_badge = s.health_zone
        if s.health_zone == "HEALTHY":
            hz_badge = "🟢 HEALTHY"
        elif s.health_zone == "AMBER":
            hz_badge = "🟡 AMBER"
        elif s.health_zone == "RED_ALERT":
            hz_badge = "🔴 RED_ALERT"

        rows.append([
            cid,
            s.role[:20],
            str(s.step_count),
            f"{s.token_count:,}",
            hz_badge,
            s.recommendation,
            f"{s.latency_ms:.1f}ms",
        ])

    col_widths = [len(h) for h in headers]
    for row in rows:
        for i, val in enumerate(row):
            col_widths[i] = max(col_widths[i], len(val))

    sep = "+-" + "-+-".join("-" * w for w in col_widths) + "-+"
    header_str = (
        "| "
        + " | ".join(f"{h:<{col_widths[i]}}" for i, h in enumerate(headers))
        + " |"
    )

    table_lines = [sep, header_str, sep]
    for row in rows:
        line = (
            "| "
            + " | ".join(f"{val:<{col_widths[i]}}" for i, val in enumerate(row))
            + " |"
        )
        table_lines.append(line)
    table_lines.append(sep)
    return "\n".join(table_lines)


def cmd_subagents(args: argparse.Namespace) -> int:
    """Renders active subagents table and zero-token context health gauge."""
    from harness.subagents import list_active_subagent_statuses

    brain_dir = getattr(args, "brain_dir", None)
    statuses = list_active_subagent_statuses(brain_dir=brain_dir)

    if getattr(args, "json", False):
        data = [
            {
                "conversation_id": s.conversation_id,
                "role": s.role,
                "step_count": s.step_count,
                "token_count": s.token_count,
                "health_zone": s.health_zone,
                "recommendation": s.recommendation,
                "latency_ms": s.latency_ms,
            }
            for s in statuses
        ]
        print(json.dumps(data, indent=2))
        return 0

    if not statuses:
        print("No active subagents found in brain directory.")
        return 0

    print(f"PSL Active Subagents ({len(statuses)} active):")
    print(format_subagents_table(statuses))
    print()
    return 0
