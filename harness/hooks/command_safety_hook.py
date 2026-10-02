#!/usr/bin/env python3
"""
PSL Harness: PreToolUse Command Safety & Hermetic Runtime Hook

Audits and optimizes terminal commands before execution:
1. Hard blocks prohibited destructive operations (e.g. rm -rf /).
2. Prevents interactive TUI traps (nano, vim, interactive ssh).
3. Ensures non-interactive execution (PAGER=cat).
4. Hermetic Python Runtime Injection: Transparently prepends certified Python 3.12+ from
   uv's cache to PATH for inline utility scripts (python3 -c / python -c),
   guaranteeing PEP 701 f-string safety without touching host pyenv config.
5. F-string Escape Sanitization: Neutralizes spurious backslashes before quotes inside
   f-string expressions in inline python scripts.
6. Surgical Tail Sanitization: Neutralizes false-positive Exit Code 1 failures on
   standalone grep/diff pattern probes via `|| [ $? -eq 1 ]`, while preserving
   genuine Exit Code 2 errors.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
import re
import sys
from typing import Any, Dict, List, Optional, Tuple


DANGEROUS_PATTERNS = [
    r"\brm\s+.*-[a-zA-Z]*r.*-[a-zA-Z]*f.*\s+(?:/\*?|\./\*?|\*)(?:\s|$)",
    r"\brm\s+.*-[a-zA-Z]*f.*-[a-zA-Z]*r.*\s+(?:/\*?|\./\*?|\*)(?:\s|$)",
    r"\brm\s+-[a-zA-Z]*[rR][a-zA-Z]*f[a-zA-Z]*\s+(?:/\*?|\./\*?|\*)(?:\s|$)",
    r"\brm\s+-[a-zA-Z]*f[a-zA-Z]*[rR][a-zA-Z]*\s+(?:/\*?|\./\*?|\*)(?:\s|$)",
    r"\bmkfs\b",
    r"\bdd\s+if=.*?of=/dev/[sh]d[a-z]\b",
]

INTERACTIVE_COMMANDS = [
    "nano", "vim", "vi", "emacs", "less", "more", "top", "htop", "glances"
]


def find_hermetic_uv_python_bin() -> Optional[Path]:
    """Find installed CPython 3.12+ bin directory in uv's toolchain directory."""
    uv_python_dir = Path.home() / ".local/share/uv/python"
    if not uv_python_dir.exists():
        return None

    for candidate in sorted(uv_python_dir.glob("cpython-3.1[2-9]*/bin/python3"), reverse=True):
        if candidate.is_file() and os.access(candidate, os.X_OK):
            return candidate.parent
    return None


def is_inline_python_command(cmd: str) -> bool:
    """Detect if command executes an inline python one-liner (python3 -c or python -c)."""
    return bool(re.search(r"\b(?:python3?)\s+-c\b", cmd))


def sanitize_fstring_expressions(cmd: str) -> str:
    """
    Sanitize spurious backslashes before quotes inside f-string expressions {...}
    in inline python one-liners (converting e.g. {d.get(\"key\")} to {d.get("key")}).
    """
    def repl(m: re.Match) -> str:
        expr = m.group(0)
        return expr.replace('\\"', '"')

    # Target expressions inside curly braces
    return re.sub(r"\{[^{}]*\}", repl, cmd)


def split_shell_pipes(cmd: str) -> Tuple[List[str], bool]:
    """
    Splits command line into pipeline segments, respecting single and double quotes.
    Returns: (segments, contains_forbidden_control_flow)
    """
    segments = []
    current: List[str] = []
    in_single = False
    in_double = False
    escaped = False
    has_control_flow = False

    i = 0
    n = len(cmd)
    while i < n:
        c = cmd[i]
        if escaped:
            current.append(c)
            escaped = False
            i += 1
            continue
        if c == "\\":
            escaped = True
            current.append(c)
            i += 1
            continue
        if c == "'" and not in_double:
            in_single = not in_single
            current.append(c)
            i += 1
            continue
        if c == '"' and not in_single:
            in_double = not in_double
            current.append(c)
            i += 1
            continue

        # Look for shell control flow outside of quotes
        if not in_single and not in_double:
            if c in (";", "&"):
                has_control_flow = True
            elif c == "|" and i + 1 < n and cmd[i + 1] == "|":
                has_control_flow = True
                i += 2
                continue
            elif c == "|":
                segments.append("".join(current).strip())
                current = []
                i += 1
                continue

        current.append(c)
        i += 1

    if current:
        segments.append("".join(current).strip())

    # Check for reserved conditional words outside quotes
    if not in_single and not in_double:
        if re.search(r"\b(?:if|then|else|fi|test)\b|\[\s*\[?", cmd):
            has_control_flow = True

    return segments, has_control_flow


def should_sanitize_grep_or_diff(cmd: str) -> bool:
    """
    Check if command is a simple, standalone grep or diff pattern search
    that should be sanitized against false-positive exit code 1.
    """
    # 1. Do not touch if already guarded with || true, || :, or [ $? -eq 1 ]
    if re.search(r"\|\|\s*(?:true|:|\s*\[\s*\$\?\s*-eq\s*1\s*\])\b", cmd):
        return False

    # 2. Split pipeline segments cleanly
    segments, has_control_flow = split_shell_pipes(cmd)
    if has_control_flow or not segments:
        return False

    # 3. Check if the terminal pipeline segment ends with grep or diff
    last_seg = segments[-1]
    tokens = last_seg.split()
    if not tokens:
        return False

    bin_name = tokens[0].split("/")[-1]
    return bin_name in ("grep", "egrep", "fgrep", "diff")


def sanitize_command(raw_cmd: str) -> Tuple[Optional[str], Optional[str], Optional[str]]:
    """
    Evaluates and sanitizes a raw command line string.
    Returns: (decision, modified_command_or_none, reason_or_none)
    """
    cmd = raw_cmd.strip()
    if not cmd:
        return ("allow", None, None)

    # 1. Dangerous pattern check
    for pattern in DANGEROUS_PATTERNS:
        if re.search(pattern, cmd):
            return (
                "deny",
                None,
                f"PSL Safety Gate: Command matches prohibited destructive pattern: {pattern}"
            )

    # 2. Interactive command check
    first_token = cmd.split()[0].split("/")[-1]
    if first_token in INTERACTIVE_COMMANDS:
        return (
            "deny",
            None,
            f"PSL Safety Gate: Interactive command '{first_token}' blocked. "
            "Agent execution must be strictly non-interactive. Use batch or script alternatives."
        )

    modified_cmd = cmd
    reasons = []

    # 3. Pager / non-interactive optimization
    if first_token in ("git", "gh") and not re.search(r"--no-pager|\bPAGER=", modified_cmd):
        modified_cmd = f"PAGER=cat {modified_cmd}"
        reasons.append("enforced non-interactive PAGER=cat")

    # 4. Hermetic Python Runtime Injection & f-string expression sanitization
    if is_inline_python_command(modified_cmd):
        # Sanitize spurious backslashes in f-strings
        sanitized_py = sanitize_fstring_expressions(modified_cmd)
        if sanitized_py != modified_cmd:
            modified_cmd = sanitized_py
            reasons.append("sanitized f-string expression quotes")

        hermetic_bin = find_hermetic_uv_python_bin()
        if hermetic_bin and "PATH=" not in modified_cmd:
            modified_cmd = f'PATH="{hermetic_bin}:$PATH" {modified_cmd}'
            reasons.append("injected hermetic CPython >= 3.12 for PEP 701 f-string safety")

    # 5. Surgical Tail Sanitization for simple grep / diff pattern searches
    if should_sanitize_grep_or_diff(cmd):
        modified_cmd = f"{modified_cmd} || [ $? -eq 1 ]"
        reasons.append("sanitized pattern search against benign Exit Code 1")

    if modified_cmd != cmd:
        return ("allow", modified_cmd, "PSL PreToolUse: " + "; ".join(reasons))

    return ("allow", None, None)


def main() -> None:
    try:
        payload = json.load(sys.stdin)
    except Exception:
        print(json.dumps({"decision": "allow"}))
        return

    tool_call = payload.get("toolCall", {})
    tool_args = tool_call.get("args", {})
    raw_cmd = tool_args.get("CommandLine", "").strip()

    decision, mod_cmd, reason = sanitize_command(raw_cmd)

    if decision == "deny":
        print(json.dumps({
            "decision": "deny",
            "reason": reason
        }))
        return

    if mod_cmd is not None:
        print(json.dumps({
            "decision": "allow",
            "overwrite": {
                "CommandLine": mod_cmd
            },
            "reason": reason
        }))
    else:
        print(json.dumps({"decision": "allow"}))


if __name__ == "__main__":
    main()
