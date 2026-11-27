# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Arafat Zahan (@kuasha420)
# Corporate Stewardship & Infrastructure: Purrfect Software Limited (PSL)
# Governed by: ICARO-42/b Ordinance (Company-Supported Personal IP Framework)

"""
Trajectory Catalog & Cleanroom Context Layout Math (ADR-014 / ADR-035).

Pure leaf module decoupling Cortex tool catalogs, Orbital Aegis system-prompt
slice tokens, and xtc/ytc/ztc/Atc proportional layout helpers from
`harness.gui.trajectory_hud` to preserve AFF line/definition headroom.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

from harness.utils.tokens import estimate_tokens as _ssot_estimate_tokens

_SYS_TAG_DEFS: Tuple[Tuple[str, str, str], ...] = (
    ("identity", "Identity", "#5C8AFF"),
    ("sandbox", "Sandbox", "#1B4DFF"),
    ("artifacts", "Artifacts", "#7DA4FF"),
    ("conversation_transcript", "Transcript", "#26D0CE"),
    ("guidelines", "Guidelines", "#2AD089"),
    ("communication_style", "Style", "#3B6CFF"),
    ("slash_commands", "Commands", "#52DFDD"),
    ("messaging", "Messaging", "#4F63D2"),
    ("mcp_servers", "MCP Servers", "#1CB0AE"),
    ("subagents", "Subagents", "#6E8CFF"),
    ("user_rules", "User Rules", "#3A8FE8"),
    ("skills", "Skills", "#1FAF72"),
    ("featured_plugins", "Plugins", "#6366F1"),
    ("user_information", "UserInfo", "#818CF8"),
    ("subagent_reminder", "Reminders", "#2EB8C8"),
)

_TOOL_CATEGORY_SPEC: Tuple[Tuple[str, str, Tuple[str, ...]], ...] = (
    ("Filesystem Tools", "#26D0CE", ("read_file", "write_file", "edit_file", "replace_file_content", "write_to_file", "view_file")),
    ("Terminal Tools", "#5C8AFF", ("run_command", "bash")),
    ("Subagents", "#1B4DFF", ("invoke_subagent", "define_subagent", "manage_subagents", "send_message", "swarm", "post_message", "read_board", "swarm_wait")),
    ("Workflow & Planning", "#4F63D2", (
        "update_focus", "update_steps", "enter_plan_mode", "exit_plan_mode",
        "ask_question", "search_marketplace", "list_plugin_accounts",
        "call_mcp_tool", "list_resources", "read_resource",
    )),
)

_TC_TYPE_NEEDLES: Tuple[Tuple[str, str], ...] = (
    ("run_command", "RUN_COMMAND"), ("bash", "RUN_COMMAND"),
    ("read_file", "READ_FILE"), ("view_file", "VIEW_FILE"),
    ("edit_file", "EDIT_FILE"), ("replace_file_content", "REPLACE_FILE_CONTENT"),
    ("write_file", "WRITE_FILE"), ("write_to_file", "WRITE_FILE"),
    ("grep_search", "GREP_SEARCH"), ("search_web", "SEARCH_WEB"),
    ("find_by_name", "FIND_FILES"), ("find_files", "FIND_FILES"),
    ("post_message", "POST_MESSAGE"), ("send_message", "SEND_MESSAGE"),
    ("read_board", "READ_BOARD"), ("swarm_wait", "SWARM_WAIT"),
    ("swarm", "SWARM"), ("run_workflow", "RUN_WORKFLOW"),
    ("define_subagent", "DEFINE_SUBAGENT"), ("manage_subagents", "MANAGE_SUBAGENTS"),
    ("manage_task", "MANAGE_TASK"),
    ("invoke_subagent", "INVOKE_SUBAGENT"), ("subagent", "INVOKE_SUBAGENT"),
    ("update_focus", "UPDATE_FOCUS"), ("update_steps", "UPDATE_STEPS"),
    ("enter_plan_mode", "ENTER_PLAN_MODE"), ("exit_plan_mode", "EXIT_PLAN_MODE"),
    ("ask_question", "ASK_QUESTION"), ("search_marketplace", "SEARCH_MARKETPLACE"),
    ("list_plugin_accounts", "LIST_PLUGIN_ACCOUNTS"), ("call_mcp_tool", "CALL_MCP_TOOL"),
    ("list_resources", "LIST_RESOURCES"), ("read_resource", "READ_RESOURCE"),
)


def estimate_tokens(char_count: int) -> int:
    """Estimates token count using SSOT token helper at cleanroom HUD ratio (3.5 chars/token)."""
    return _ssot_estimate_tokens(char_count, chars_per_token=3.5)


def xtc_segment_width(segment_tokens: int, px_per_token: float, min_segment_px: float = 2.0) -> float:
    """Calculates pixel width for a segment with minimum pixel clamp (cleanroom xtc)."""
    tok = max(0, segment_tokens)
    return max(tok * px_per_token, min_segment_px) if tok > 0 else 0.0


def ytc_layout_pass(
    segments: List[Dict[str, Any]], capacity_tokens: int, container_width: float,
    min_segment_px: float = 2.0, rows_count: int = 1,
) -> Dict[str, float]:
    """Calculates layout metrics and inflation for a given row count (cleanroom ytc)."""
    capacity_px = container_width * rows_count
    px_per_token = capacity_px / capacity_tokens if capacity_tokens > 0 else 0.0
    used_px = 0.0
    true_used_px = 0.0
    for s in segments:
        tok = s.get("tokens", 0)
        used_px += xtc_segment_width(tok, px_per_token, min_segment_px)
        true_used_px += max(0, tok) * px_per_token
    return {
        "capacity_px": capacity_px,
        "px_per_token": px_per_token,
        "used_px": used_px,
        "true_used_px": true_used_px,
        "inflation_px": used_px - true_used_px,
    }


def ztc_row_count(
    segments: List[Dict[str, Any]], capacity_tokens: int, container_width: float,
    min_segment_px: float = 2.0, max_rows: int = 8,
) -> int:
    """Determines optimal row count to minimize inflation (cleanroom ztc)."""
    current = ytc_layout_pass(segments, capacity_tokens, container_width, min_segment_px, 1)
    for r in range(1, max_rows):
        if current["inflation_px"] <= 0.1 * current["true_used_px"]:
            return r
        next_pass = ytc_layout_pass(segments, capacity_tokens, container_width, min_segment_px, r + 1)
        if current["inflation_px"] - next_pass["inflation_px"] < 0.02 * container_width:
            return r
        current = next_pass
    return max_rows


def atc_context_layout(
    segments: List[Dict[str, Any]], capacity_tokens: int, container_width: float,
    min_segment_px: float = 2.0, max_rows: int = 8,
) -> Dict[str, Any]:
    """Authoritative dynamic context bar sizing and multi-row layout algorithm (cleanroom Atc)."""
    if not segments or capacity_tokens <= 0 or container_width <= 0:
        return {"rows": [], "inflation_px": 0.0}

    row_count = ztc_row_count(segments, capacity_tokens, container_width, min_segment_px, max_rows)
    layout = ytc_layout_pass(segments, capacity_tokens, container_width, min_segment_px, row_count)
    scale_factor = layout["capacity_px"] / layout["used_px"] if layout["used_px"] > layout["capacity_px"] else 1.0
    segment_widths = [xtc_segment_width(s.get("tokens", 0), layout["px_per_token"], min_segment_px) * scale_factor for s in segments]
    unused_px = max(0.0, layout["capacity_px"] - layout["used_px"] * scale_factor)

    rows: List[List[Dict[str, Any]]] = [[] for _ in range(row_count)]
    cursor_px = 0.0

    def place_cell(seg: Optional[Dict[str, Any]], width_px: float, key_prefix: str, show_divider: bool) -> None:
        nonlocal cursor_px
        rem_width = width_px
        sub_idx = 0
        while rem_width > 1e-6:
            row_idx = min(len(rows) - 1, int((cursor_px + 1e-6) // container_width))
            row_start_px = cursor_px - row_idx * container_width
            avail_in_row = container_width - row_start_px
            if avail_in_row <= 1e-6:
                break
            slice_width = min(rem_width, avail_in_row)
            rem_width -= slice_width
            cursor_px += slice_width
            is_done = rem_width <= 1e-6
            fills_row = slice_width >= avail_in_row - 1e-6
            rows[row_idx].append({
                "key": f"{key_prefix}#{sub_idx}",
                "segment": seg,
                "start_fraction": row_start_px / container_width,
                "width_fraction": slice_width / container_width,
                "continues_from_previous_row": sub_idx > 0,
                "continues_on_next_row": not is_done,
                "show_divider_after": show_divider and is_done and not fills_row,
            })
            sub_idx += 1

    for idx, seg in enumerate(segments):
        next_seg = segments[idx + 1] if idx + 1 < len(segments) else None
        place_cell(seg, segment_widths[idx], f"{idx}:{seg.get('id', idx)}", next_seg is not None and next_seg.get("color_key") == seg.get("color_key"))
    if unused_px > 1e-6:
        place_cell(None, unused_px, "unused", False)

    return {"rows": rows, "inflation_px": layout["inflation_px"] * scale_factor}
