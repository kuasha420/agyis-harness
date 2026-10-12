#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Arafat Zahan (@kuasha420)
# Corporate Stewardship & Infrastructure: Purrfect Software Limited (PSL)
# Governed by: ICARO-42/b Ordinance (Company-Supported Personal IP Framework)

"""
PSL Harness: PreToolUse Anti-Loop Hook

Intercepts consecutive redundant tool calls to prevent agent thrashing loops
(such as repeated view_file or grep_search calls).
"""

from __future__ import annotations

import json
import os
from pathlib import Path
import sys

from harness.utils.state import get_state_dir



MAX_REPEATS = 3
HISTORY_WINDOW = 30
FREQUENCY_WINDOW = 15
MAX_FREQUENCY_REPEATS = 4
CYCLE_PERIODS = (2, 3, 4, 5)
MAX_TASK_INSPECTION_CONSECUTIVE = 2
MAX_TASK_INSPECTION_WINDOW_FREQUENCY = 3
TASK_INSPECTION_WINDOW = 10


def _signatures_match(sig1: dict, sig2: dict) -> bool:
    """Helper to check if two tool call signatures are identical."""
    if sig1.get("name") != sig2.get("name"):
        return False
    return sig1.get("args") == sig2.get("args")


def _is_task_log_inspection(sig: dict) -> bool:
    """Helper to detect if a tool call is inspecting background task status/logs."""
    name = sig.get("name", "")
    args = sig.get("args", {})
    if name == "manage_task":
        return args.get("Action") == "status"
    if name == "view_file":
        path = args.get("AbsolutePath", "")
        return (".system_generated/tasks" in path or "/tasks/task-" in path) and path.endswith(".log")
    if name == "grep_search":
        search_path = args.get("SearchPath", "")
        return (".system_generated/tasks" in search_path or "/tasks/task-" in search_path) and (search_path.endswith(".log") or search_path.endswith("/tasks"))
    if name == "run_command":
        cmd = args.get("CommandLine", "")
        return (".system_generated/tasks" in cmd or "/tasks/task-" in cmd) and ".log" in cmd
    return False


def check_anti_loop(
    tool_name: str,
    tool_args: dict,
    conv_id: str = "default",
    state_dir: Path | None = None,
    max_repeats: int = MAX_REPEATS,
) -> dict:
    """
    Evaluates a tool call against recent history for the given conversation ID:
    1. Consecutive repeat check (denies on >= max_repeats consecutive identical calls).
    2. Rolling frequency-window check (denies if identical signature appears >= 4 times within sliding window of 15 calls).
    3. N-gram cyclic pattern check (denies if repeating sequences of length P in [2, 5] repeat >= 2 consecutive cycles).

    Returns:
        {"decision": "allow"} or {"decision": "deny", "reason": ...}
    """
    target_dir = state_dir or get_state_dir()
    target_dir.mkdir(parents=True, exist_ok=True)
    history_file = target_dir / f"history_{conv_id}.json"

    history = []
    if history_file.exists():
        try:
            history = json.loads(history_file.read_text(encoding="utf-8"))
            if not isinstance(history, list):
                history = []
        except (json.JSONDecodeError, OSError):
            history = []

    # Current signature
    sig = {"name": tool_name, "args": tool_args}

    # 0. Background task log polling check (prevents manual background task sniffing loops)
    if _is_task_log_inspection(sig):
        consecutive_inspections = 0
        for prev in reversed(history):
            if _is_task_log_inspection(prev):
                consecutive_inspections += 1
            else:
                break
        if consecutive_inspections >= MAX_TASK_INSPECTION_CONSECUTIVE:
            return {
                "decision": "deny",
                "reason": (
                    f"PSL Anti-Loop Guard: Intercepted {consecutive_inspections + 1} consecutive background task inspections. "
                    "Never poll background task logs ('tail', 'cat', 'view_file' on .system_generated/tasks/ or manage_task 'status') "
                    "for progress updates. Stop calling tools and await reactive wakeup."
                ),
            }

        window_tasks = (history + [sig])[-TASK_INSPECTION_WINDOW:]
        freq_tasks = sum(1 for item in window_tasks if _is_task_log_inspection(item))
        if freq_tasks >= MAX_TASK_INSPECTION_WINDOW_FREQUENCY:
            return {
                "decision": "deny",
                "reason": (
                    f"PSL Anti-Loop Guard: Background task inspection appeared {freq_tasks} times "
                    f"within sliding window of {len(window_tasks)} calls. "
                    "Never poll background task logs or status. Stop calling tools and await reactive wakeup."
                ),
            }

    # 1. Consecutive matching signatures from end
    repeats = 0
    for prev in reversed(history):
        if _signatures_match(prev, sig):
            repeats += 1
        else:
            break

    if repeats >= max_repeats:
        return {
            "decision": "deny",
            "reason": (
                f"PSL Anti-Loop Guard: Intercepted {repeats + 1} identical consecutive executions "
                f"of '{tool_name}'. Refine arguments, inspect prior outputs, or pursue an alternative strategy."
            ),
        }

    # 2. Rolling frequency-window check (sliding window of 15 calls including proposed call)
    window_seq = (history + [sig])[-FREQUENCY_WINDOW:]
    freq_count = sum(1 for item in window_seq if _signatures_match(item, sig))
    if freq_count >= MAX_FREQUENCY_REPEATS:
        return {
            "decision": "deny",
            "reason": (
                f"PSL Anti-Loop Guard: Tool signature '{tool_name}' appeared {freq_count} times "
                f"within a sliding window of {len(window_seq)} calls (threshold is {MAX_FREQUENCY_REPEATS}). "
                "Denying execution to prevent thrashing loop. Refine arguments or pursue an alternative strategy."
            ),
        }

    # 3. N-gram cyclic pattern detection (periods P in 2..5)
    full_seq = history + [sig]
    for p in CYCLE_PERIODS:
        if len(full_seq) >= 2 * p:
            cycle1 = full_seq[-2 * p : -p]
            cycle2 = full_seq[-p :]
            if all(_signatures_match(cycle1[i], cycle2[i]) for i in range(p)):
                cycle_names = " -> ".join(item.get("name", "unknown") for item in cycle2)
                return {
                    "decision": "deny",
                    "reason": (
                        f"PSL Anti-Loop Guard: Intercepted cyclic tool execution pattern of period {p} "
                        f"({cycle_names}) repeating >= 2 consecutive cycles. "
                        "Break the cycle by altering parameters, inspecting past outputs, or changing approach."
                    ),
                }

    # Record into history (keep last 30)
    history.append(sig)
    history = history[-HISTORY_WINDOW:]
    try:
        history_file.write_text(json.dumps(history), encoding="utf-8")
    except OSError:
        pass

    return {"decision": "allow"}


def main() -> None:
    try:
        raw_stdin = sys.stdin.read()
        if not raw_stdin.strip():
            print(json.dumps({"decision": "allow"}))
            return
        payload = json.loads(raw_stdin)
        if not isinstance(payload, dict):
            print(json.dumps({"decision": "allow"}))
            return
    except Exception:
        # Default allow if input cannot be read
        print(json.dumps({"decision": "allow"}))
        return

    conv_id = payload.get("conversationId", "default")
    tool_call = payload.get("toolCall", {})
    tool_name = tool_call.get("name", "")
    tool_args = tool_call.get("args", {})

    result = check_anti_loop(tool_name, tool_args, conv_id=conv_id)
    print(json.dumps(result))


if __name__ == "__main__":
    main()
