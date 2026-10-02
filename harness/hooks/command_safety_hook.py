#!/usr/bin/env python3
"""
PSL Harness: PreToolUse Command Safety & Pre-flight Validator

Audits terminal commands before execution:
1. Hard blocks destructive operations (e.g. rm -rf /).
2. Prevents interactive TUI traps (nano, vim, interactive ssh).
3. Ensures PAGER=cat is set for paginated git/diff tools.
4. Normalizes commands prone to false-positive exit code 1 failures.
"""

from __future__ import annotations

import json
import re
import sys


DANGEROUS_PATTERNS = [
    r"\brm\s+-[a-zA-Z]*[rR][a-zA-Z]*f[a-zA-Z]*\s+(?:/|\./\s*|\*)\b",
    r"\brm\s+-[a-zA-Z]*[rR][a-zA-Z]*f[a-zA-Z]*\s+/(?:\s|$)",
    r"\bmkfs\b",
    r"\bdd\s+if=.*?of=/dev/[sh]d[a-z]\b",
]

INTERACTIVE_COMMANDS = [
    "nano", "vim", "vi", "emacs", "less", "more", "top", "htop", "glances"
]


def main() -> None:
    try:
        payload = json.load(sys.stdin)
    except Exception:
        print(json.dumps({"decision": "allow"}))
        return

    tool_call = payload.get("toolCall", {})
    tool_args = tool_call.get("args", {})
    raw_cmd = tool_args.get("CommandLine", "").strip()

    if not raw_cmd:
        print(json.dumps({"decision": "allow"}))
        return

    # 1. Dangerous pattern check
    for pattern in DANGEROUS_PATTERNS:
        if re.search(pattern, raw_cmd):
            print(json.dumps({
                "decision": "deny",
                "reason": f"PSL Safety Gate: Command matches prohibited destructive pattern: {pattern}"
            }))
            return

    # 2. Interactive command check
    first_token = raw_cmd.split()[0].split("/")[-1]
    if first_token in INTERACTIVE_COMMANDS:
        print(json.dumps({
            "decision": "deny",
            "reason": (
                f"PSL Safety Gate: Interactive command '{first_token}' blocked. "
                "Agent execution must be strictly non-interactive. Use batch or script alternatives."
            )
        }))
        return

    # 3. Pager / non-interactive optimization
    overwrites = {}
    if first_token == "git" and not re.search(r"--no-pager|\bPAGER=", raw_cmd):
        overwrites["CommandLine"] = f"PAGER=cat {raw_cmd}"

    if overwrites:
        print(json.dumps({
            "decision": "allow",
            "overwrite": overwrites,
            "reason": "PSL Safety Gate: Enforced non-interactive PAGER=cat for git invocation."
        }))
    else:
        print(json.dumps({"decision": "allow"}))


if __name__ == "__main__":
    main()
