# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Arafat Zahan (@kuasha420)
# Corporate Stewardship & Infrastructure: Purrfect Software Limited (PSL)
# Governed by: ICARO-42/b Ordinance (Company-Supported Personal IP Framework)

"""
Active subagents context status and inspection CLI command (ADR-014, ADR-025).
"""

from __future__ import annotations

import argparse
import json
from typing import Any, List, Optional


def format_subagents_table(statuses: List[Any], heartbeat: Optional[dict] = None) -> str:
    """Format a list of SubagentContextStatus as an ASCII table."""
    if not statuses:
        return "No active subagents found."

    if heartbeat is None:
        try:
            from harness.subagents.heartbeat import read_stage_heartbeat
            heartbeat = read_stage_heartbeat()
        except Exception:
            heartbeat = None

    is_active = bool(
        heartbeat
        and not heartbeat.get("is_stale", False)
        and heartbeat.get("status") in {"dispatched", "in_progress", "verifying"}
    )
    stage = heartbeat.get("stage", "") if is_active else ""
    active_agent_id = heartbeat.get("active_agent_id", "") if is_active else ""
    subagent_role = heartbeat.get("subagent_role", "") if is_active else ""

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

        role_display = s.role
        if is_active:
            matches = (
                (active_agent_id and (active_agent_id in s.conversation_id or s.conversation_id in active_agent_id))
                or (stage and stage.lower() in s.role.lower())
                or (subagent_role and s.role.lower() in subagent_role.lower())
                or len(statuses) == 1
            )
            if matches:
                stage_badge = stage.title()
                if f"({stage_badge})" not in role_display:
                    role_display = f"{role_display} ({stage_badge})"

        rows.append([
            cid,
            role_display[:28],
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
    try:
        from harness.subagents.heartbeat import read_stage_heartbeat
        workspace_dir = getattr(args, "workspace_dir", None)
        heartbeat = read_stage_heartbeat(workspace_dir=workspace_dir)
    except Exception:
        heartbeat = None

    brain_dir = getattr(args, "brain_dir", None)
    statuses = list_active_subagent_statuses(brain_dir=brain_dir)

    is_active = bool(
        heartbeat
        and not heartbeat.get("is_stale", False)
        and heartbeat.get("status") in {"dispatched", "in_progress", "verifying"}
    )
    stage = heartbeat.get("stage", "") if is_active else ""
    active_agent_id = heartbeat.get("active_agent_id", "") if is_active else ""
    subagent_role = heartbeat.get("subagent_role", "") if is_active else ""

    if getattr(args, "json", False):
        data = []
        for s in statuses:
            matches = is_active and (
                (active_agent_id and (active_agent_id in s.conversation_id or s.conversation_id in active_agent_id))
                or (stage and stage.lower() in s.role.lower())
                or (subagent_role and s.role.lower() in subagent_role.lower())
                or len(statuses) == 1
            )
            item = {
                "conversation_id": s.conversation_id,
                "role": s.role,
                "step_count": s.step_count,
                "token_count": s.token_count,
                "health_zone": s.health_zone,
                "recommendation": s.recommendation,
                "latency_ms": s.latency_ms,
            }
            if matches:
                item["ladder_stage"] = stage
            data.append(item)
        print(json.dumps(data, indent=2))
        return 0

    if not statuses:
        if is_active:
            print(f"Active Ladder Stage: {stage.title()} [{heartbeat.get('status', '').upper()}] (Task: {heartbeat.get('task_id', 'N/A')})")
        print("No active subagents found in brain directory.")
        return 0

    if is_active:
        print(f"Active Ladder Stage: {stage.title()} [{heartbeat.get('status', '').upper()}] (Task: {heartbeat.get('task_id', 'N/A')})")
    print(f"Agyis Active Subagents ({len(statuses)} active):")
    print(format_subagents_table(statuses, heartbeat=heartbeat))
    print()
    return 0
