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
import re
import sys

from harness.utils.state import get_state_dir, load_history, save_history



MAX_REPEATS = 3
HISTORY_WINDOW = 30
FREQUENCY_WINDOW = 15
MAX_FREQUENCY_REPEATS = 4
MAX_IDEMPOTENT_FREQUENCY_REPEATS = 8
CYCLE_PERIODS = (2, 3, 4, 5)
MAX_TASK_INSPECTION_CONSECUTIVE = 2
MAX_TASK_INSPECTION_WINDOW_FREQUENCY = 3
TASK_INSPECTION_WINDOW = 10

CODE_EDIT_TOOLS = frozenset({"write_to_file", "replace_file_content"})

TEST_VERIFICATION_PATTERNS = (
    r"(?:^|[\s;&|])(?:\./)?agyis\s+test\b",
    r"(?:^|[\s;&|])python3?\s+-m\s+harness(?:\.cli)?\s+test\b",
    r"(?:^|[\s;&|])python3?\s+-m\s+unittest\b",
    r"(?:^|[\s;&|])pytest\b",
    r"(?:^|[\s;&|])cargo\s+test\b",
    r"(?:^|[\s;&|])pnpm(?:\s+--filter\s+\S+)?\s+test\b",
    r"(?:^|[\s;&|])npm\s+test\b",
    r"(?:^|[\s;&|])yarn\s+test\b",
    r"(?:^|[\s;&|])go\s+test\b",
)


def _signatures_match(sig1: dict, sig2: dict) -> bool:
    """Helper to check if two tool call signatures are identical."""
    if sig1.get("name") != sig2.get("name"):
        return False
    return sig1.get("args") == sig2.get("args")


def _is_peer_heartbeat(tool_name: str, tool_args: dict) -> bool:
    """
    Exempts read-only inspections of peer heartbeat files.
    If tool_name == 'view_file' and the path ends with 'progress.md' or contains '/.agents/teamwork/',
    never flag as a loop denial.
    """
    if tool_name != "view_file":
        return False
    path = str(tool_args.get("AbsolutePath") or tool_args.get("Path") or "")
    return path.endswith("progress.md") or "/.agents/teamwork/" in path or ".agents/teamwork/" in path


def _is_code_edit(sig: dict) -> bool:
    """Helper to check if a tool call is a code edit mutation."""
    return sig.get("name") in CODE_EDIT_TOOLS


def _is_test_verification_command(sig: dict) -> bool:
    """Helper to check if a tool call is a test verification runner invocation."""
    if sig.get("name") != "run_command":
        return False
    cmd = sig.get("args", {}).get("CommandLine", "").strip()
    return any(re.search(pat, cmd) for pat in TEST_VERIFICATION_PATTERNS)


def _is_idempotent_status_command(sig: dict) -> bool:
    """
    Helper to detect idempotent read-only inspection commands:
    ('git status', 'git branch', 'stat', 'pwd').
    """
    if sig.get("name") != "run_command":
        return False
    cmd = sig.get("args", {}).get("CommandLine", "").strip()
    if cmd.startswith("PAGER=cat "):
        cmd = cmd[len("PAGER=cat "):].strip()
    tokens = cmd.split()
    if not tokens:
        return False
    if tokens[0] in ("pwd", "stat"):
        return True
    if len(tokens) >= 2 and tokens[0] == "git" and tokens[1] in ("status", "branch"):
        return True
    return False


def _is_manage_task_status(sig: dict) -> bool:
    """Helper to detect manage_task(Action='status') background task inspections."""
    return sig.get("name") == "manage_task" and sig.get("args", {}).get("Action") == "status"


def _is_task_log_inspection(sig: dict) -> bool:
    """Helper to detect if a tool call is inspecting background task logs."""
    name = sig.get("name", "")
    args = sig.get("args", {})
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

    Relaxations (PSL-SPEC-2026-DRA-001 Phase 2):
    - Peer Heartbeat Exemption: view_file on progress.md or /.agents/teamwork/ is never denied.
    - Verification Reset Invariant: Code edits clear test runner frequency/repeats counters.
    - Idempotent Status Command Relaxation: git status, git branch, stat, pwd allow up to at least 8 executions.
    - Non-Blocking Advisory: manage_task(Action='status') returns non-blocking advisory allow.

    Returns:
        {"decision": "allow"} or {"decision": "deny", "reason": ...}
    """
    target_dir = state_dir or get_state_dir()
    try:
        target_dir.mkdir(parents=True, exist_ok=True)
    except OSError:
        pass

    history = load_history(conv_id, target_dir=target_dir)

    # Current signature
    sig = {"name": tool_name, "args": tool_args}

    # -1. Peer Heartbeat Exemption (progress.md or teamwork metadata inspection)
    if _is_peer_heartbeat(tool_name, tool_args):
        history.append(sig)
        history = history[-HISTORY_WINDOW:]
        try:
            save_history(conv_id, history, target_dir=target_dir)
        except OSError:
            pass
        return {"decision": "allow"}

    # -2. Non-Blocking Advisory for Background Tasks: manage_task(Action='status')
    if _is_manage_task_status(sig):
        history.append(sig)
        history = history[-HISTORY_WINDOW:]
        try:
            save_history(conv_id, history, target_dir=target_dir)
        except OSError:
            pass
        return {
            "decision": "allow",
            "reason": "Advisory: Background tasks notify reactively upon exit. Avoid polling status to conserve steps.",
        }

    # -3. Verification Reset Invariant:
    # When any code edit tool is called, automatically clear/reset the
    # sliding-window frequency counters or history for test verification commands.
    if _is_code_edit(sig):
        history = [item for item in history if not _is_test_verification_command(item)]

    # If the current call is a test verification command preceded by any code edit,
    # reset previous test runner history so verification following edits is never blocked as a loop.
    if _is_test_verification_command(sig) and any(_is_code_edit(item) for item in history):
        history = [item for item in history if not _is_test_verification_command(item)]

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

    is_idempotent = _is_idempotent_status_command(sig)
    effective_max_repeats = (
        MAX_IDEMPOTENT_FREQUENCY_REPEATS
        if is_idempotent
        else max_repeats
    )
    if repeats >= effective_max_repeats:
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
    max_freq = MAX_IDEMPOTENT_FREQUENCY_REPEATS if is_idempotent else MAX_FREQUENCY_REPEATS

    if freq_count > max_freq if is_idempotent else freq_count >= max_freq:
        return {
            "decision": "deny",
            "reason": (
                f"PSL Anti-Loop Guard: Tool signature '{tool_name}' appeared {freq_count} times "
                f"within a sliding window of {len(window_seq)} calls (threshold is {max_freq}). "
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
        save_history(conv_id, history, target_dir=target_dir)
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
