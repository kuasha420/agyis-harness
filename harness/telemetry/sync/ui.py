# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Arafat Zahan (@kuasha420)
# Corporate Stewardship & Infrastructure: Purrfect Software Limited (PSL)
# Governed by: ICARO-42/b Ordinance (Company-Supported Personal IP Framework)

"""
Interactive session selection CLI UI (ADR-030).
"""

from __future__ import annotations

from pathlib import Path
import re
import sys
from typing import Any, Dict, List, Optional


def interactive_select_sessions(
    sessions: List[Dict[str, Any]],
    input_stream: Optional[Any] = None,
    output_stream: Optional[Any] = None,
) -> List[Dict[str, Any]]:
    """Interactively prompts the user to select which sessions to push.

    Shows candidate sessions (ID, duration, steps, tools, workspace).
    Supports:
      - 'all', empty string, or '*' to accept all candidates.
      - 'none', 'q', 'quit', 'abort', or '0' to reject all and abort.
      - Comma-separated or space-separated numbers (e.g. '1,2', '1 3') to select specific sessions.
    Zero external dependencies (pure stdlib).
    """
    if not sessions:
        if output_stream is not None:
            output_stream.write("No candidate sessions available for selection.\n")
            output_stream.flush()
        return []

    out = output_stream if output_stream is not None else sys.stdout
    inp = input_stream if input_stream is not None else sys.stdin

    out.write(f"\nCandidate Sessions Pending Push ({len(sessions)} available):\n")
    out.write("=" * 80 + "\n")
    for idx, s in enumerate(sessions, 1):
        s_id = str(s.get("session_id", "unknown"))
        dur = s.get("duration_seconds")
        dur_str = f"{dur:.1f}s" if dur is not None else "N/A"
        steps = s.get("total_steps") or 0
        tools = s.get("tool_call_count") or 0
        ws = s.get("workspace_path") or "default"
        ws_short = Path(ws).name if ws and ws != "default" else ws
        out.write(
            f"  [{idx:2d}] ID: {s_id[:16]}... | Duration: {dur_str:>7} | Steps: {steps:>4} | "
            f"Tools: {tools:>3} | Workspace: {ws_short}\n"
        )
    out.write("=" * 80 + "\n")
    out.write("Select sessions to push (comma-separated indices e.g. '1,2', 'all' [default], 'none'/'q' to cancel): ")
    out.flush()

    raw_input = inp.readline()
    if raw_input is None:
        return []
    ans = raw_input.strip()

    if not ans or ans.lower() in ("all", "a", "*"):
        return list(sessions)

    if ans.lower() in ("none", "n", "q", "quit", "abort", "0"):
        return []

    # Parse 1-based indices
    parts = re.split(r"[,;\s]+", ans)
    selected_indices: List[int] = []
    for p in parts:
        if not p:
            continue
        try:
            val = int(p)
            if 1 <= val <= len(sessions):
                if val not in selected_indices:
                    selected_indices.append(val)
            else:
                out.write(f"Warning: Index {val} out of range (1..{len(sessions)}), ignored.\n")
        except ValueError:
            out.write(f"Warning: Invalid token '{p}' ignored.\n")
    out.flush()

    return [sessions[i - 1] for i in selected_indices]
