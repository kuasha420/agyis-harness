#!/usr/bin/env python3
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

def get_state_dir() -> Path:
    return Path(os.environ.get("PSL_HARNESS_STATE_DIR", "/tmp/psl_agy_harness_state"))


MAX_REPEATS = 3


def check_anti_loop(
    tool_name: str,
    tool_args: dict,
    conv_id: str = "default",
    state_dir: Path | None = None,
    max_repeats: int = MAX_REPEATS,
) -> dict:
    """
    Evaluates a tool call against recent history for the given conversation ID.

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
        except Exception:
            history = []

    # Current signature
    sig = {"name": tool_name, "args": tool_args}

    # Count consecutive matching signatures from end
    repeats = 0
    for prev in reversed(history):
        if prev.get("name") == sig["name"] and prev.get("args") == sig["args"]:
            repeats += 1
        else:
            break

    if repeats >= max_repeats:
        # Deny repetitive execution to force reasoning shift
        return {
            "decision": "deny",
            "reason": (
                f"PSL Anti-Loop Guard: Intercepted {repeats + 1} identical consecutive executions "
                f"of '{tool_name}'. Refine arguments, inspect prior outputs, or pursue an alternative strategy."
            ),
        }

    # Record into history (keep last 10)
    history.append(sig)
    history = history[-10:]
    try:
        history_file.write_text(json.dumps(history), encoding="utf-8")
    except Exception:
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
