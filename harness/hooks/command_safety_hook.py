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
7. User-Space Toolchain PATH Shim Recovery: Discovers existing user bin directories
   (~/.local/bin, ~/.cargo/bin, ~/.local/share/pnpm, ~/.pyenv/shims) and prepends
   export PATH="<shims>:$PATH"; <cmd> for non-login subshell reliability (ADR-023).
8. Network Probe Timeout Injection: Transparently injects non-blocking timeouts and
   BatchMode flags into ssh invocations to prevent hanging background tasks (ADR-023).
"""

from __future__ import annotations

import json
import os
from pathlib import Path
import re
import shlex
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

USER_TOOLCHAINS = (
    "psl", "uv", "pnpm", "npm", "npx", "cargo", "rustc",
    "pytest", "ruff", "black", "mypy", "flake8", "tsc",
)

USER_TOOLCHAIN_REGEX = re.compile(
    r"(?:^|[;&|]\s*|\b(?:sudo|xargs|nohup|exec|env|time)\s+)\s*(?:/[^\s]+/)?\b("
    + "|".join(USER_TOOLCHAINS)
    + r")\b"
)

REMOTE_TOOLCHAINS = ("pm2", "node", "pnpm", "cargo", "nvm", "uv")

REMOTE_TOOLCHAIN_REGEX = re.compile(
    r"(?:^|[;&|]\s*|\b(?:sudo|xargs|nohup|exec|env|time)\s+)\s*(?:/[^\s]+/)?\b("
    + "|".join(REMOTE_TOOLCHAINS)
    + r")\b"
)

SSH_TIMEOUT_OPTIONS = (
    "-o ControlMaster=auto "
    "-o ControlPath=~/.cache/psl/ssh/cm_%C "
    "-o ControlPersist=10m "
    "-o BatchMode=yes "
    "-o ConnectTimeout=10 "
    "-o ServerAliveInterval=15"
)

SSH_OPTION_FLAGS_WITH_ARG = {
    "-b", "-c", "-D", "-E", "-e", "-F", "-I", "-i", "-J",
    "-L", "-l", "-m", "-O", "-o", "-p", "-Q", "-R", "-S",
    "-W", "-w",
}

SSH_PATTERN = re.compile(
    r"(^|[;&|]\s*|(?:sudo|nohup|timeout\s+\S+)\s+)((?:\S+/)?ssh)(\s+|$)"
)


def get_user_path_shims() -> List[str]:
    """
    Discovers existing candidate user bin directories on the host:
    ~/.local/bin, ~/.cargo/bin, ~/.local/share/pnpm, ~/.pyenv/shims.
    """
    candidates = [
        Path.home() / ".local/bin",
        Path.home() / ".cargo/bin",
        Path.home() / ".local/share/pnpm",
        Path.home() / ".pyenv/shims",
    ]
    return [str(p) for p in candidates if p.is_dir()]


def inject_path_shims(cmd: str) -> Tuple[str, bool]:
    """
    Prepend export PATH="<shims>:$PATH"; <cmd> if user toolchains
    (uv, pnpm, npm, npx, cargo, rustc, pytest, ruff, black, mypy, flake8, tsc)
    are invoked and PATH= is not already defined. Idempotent.
    """
    if not cmd.strip():
        return cmd, False

    if "PATH=" in cmd:
        return cmd, False

    if not USER_TOOLCHAIN_REGEX.search(cmd):
        return cmd, False

    shims = get_user_path_shims()
    if not shims:
        return cmd, False

    candidate_names = (".local/bin", ".cargo/bin", ".local/share/pnpm", ".pyenv/shims")
    if any(shim in cmd for shim in shims) or any(cand in cmd for cand in candidate_names):
        return cmd, False

    shim_str = ":".join(shims)
    return f'export PATH="{shim_str}:$PATH"; {cmd.strip()}', True


def ensure_ssh_socket_dir() -> Path:
    """
    Ensures ~/.cache/psl/ssh/ socket directory exists with 0700 permissions.
    Supports PSL_HARNESS_STATE_DIR if configured.
    """
    state_dir = os.environ.get("PSL_HARNESS_STATE_DIR")
    if state_dir:
        ssh_dir = Path(state_dir) / "ssh"
    else:
        ssh_dir = Path.home() / ".cache/psl/ssh"
    try:
        ssh_dir.mkdir(parents=True, exist_ok=True)
        ssh_dir.chmod(0o700)
    except OSError:
        pass
    return ssh_dir


def inject_ssh_timeouts(cmd: str) -> Tuple[str, bool]:
    """
    When ssh is called without -o ConnectTimeout= or -o ControlMaster=, injects:
    OpenSSH multiplexing and non-blocking timeout options:
    -o ControlMaster=auto -o ControlPath=~/.cache/psl/ssh/cm_%C -o ControlPersist=10m
    -o BatchMode=yes -o ConnectTimeout=10 -o ServerAliveInterval=15.
    Idempotent.
    """
    if not cmd.strip():
        return cmd, False

    if re.search(r"\b(?:ConnectTimeout=|ControlMaster=)", cmd, re.IGNORECASE):
        return cmd, False

    m = SSH_PATTERN.search(cmd)
    if not m:
        return cmd, False

    ensure_ssh_socket_dir()

    prefix = m.group(1)
    ssh_bin = m.group(2)
    sep = m.group(3) or " "
    span_start = m.start()
    span_end = m.end()

    injected = f"{prefix}{ssh_bin} {SSH_TIMEOUT_OPTIONS}{sep}"
    res = (cmd[:span_start] + injected + cmd[span_end:]).strip()
    return res, True


def sanitize_ssh_remote_payload(cmd: str) -> Tuple[str, bool, List[str]]:
    """
    Inspects SSH remote execution payload to apply ADR-013 pattern probe
    sanitization (|| [ $? -eq 1 ]) and selective toolchain login-shell promotion
    (bash -l -c '...').
    """
    if not cmd.strip():
        return cmd, False, []

    m = SSH_PATTERN.search(cmd)
    if not m:
        return cmd, False, []

    ssh_start = m.start(2)
    prefix = cmd[:ssh_start]
    rest = cmd[ssh_start:]

    # Locate top-level shell separators outside quotes
    in_single = False
    in_double = False
    escaped = False
    sep_idx = -1
    i = 0
    n = len(rest)
    while i < n:
        c = rest[i]
        if escaped:
            escaped = False
            i += 1
            continue
        if c == "\\":
            escaped = True
            i += 1
            continue
        if c == "'" and not in_double:
            in_single = not in_single
            i += 1
            continue
        if c == '"' and not in_single:
            in_double = not in_double
            i += 1
            continue
        if not in_single and not in_double:
            if c in (";", "&"):
                sep_idx = i
                break
            if c == "|" and i + 1 < n and rest[i + 1] == "|":
                sep_idx = i
                break
            if c == "|":
                sep_idx = i
                break
        i += 1

    if sep_idx != -1:
        ssh_part = rest[:sep_idx].strip()
        suffix = rest[sep_idx:]
    else:
        ssh_part = rest.strip()
        suffix = ""

    try:
        tokens = shlex.split(ssh_part)
    except ValueError:
        return cmd, False, []

    if len(tokens) < 2:
        return cmd, False, []

    ssh_bin = tokens[0]
    idx = 1
    ssh_opts: List[str] = []
    target: Optional[str] = None
    remote_tokens: List[str] = []

    while idx < len(tokens):
        tok = tokens[idx]
        if target is None:
            if tok.startswith("-"):
                if tok in SSH_OPTION_FLAGS_WITH_ARG:
                    ssh_opts.append(tok)
                    if idx + 1 < len(tokens):
                        idx += 1
                        ssh_opts.append(tokens[idx])
                else:
                    ssh_opts.append(tok)
                idx += 1
            else:
                target = tok
                idx += 1
        else:
            remote_tokens.append(tokens[idx])
            idx += 1

    if not target or not remote_tokens:
        return cmd, False, []

    target_pos = ssh_part.find(target)
    after_target = ssh_part[target_pos + len(target):].strip()
    quote_style = None
    if after_target.startswith("'") and after_target.endswith("'") and len(after_target) >= 2:
        quote_style = "'"
    elif after_target.startswith('"') and after_target.endswith('"') and len(after_target) >= 2:
        quote_style = '"'

    remote_cmd = remote_tokens[0] if len(remote_tokens) == 1 else " ".join(remote_tokens)
    modified_remote = remote_cmd
    reasons: List[str] = []

    # Check if toolchain login-shell promotion will wrap the payload in single quotes bash -l -c '...'
    is_login_shell = bool(re.search(r"\b(?:bash|zsh|sh)\s+-[a-zA-Z]*l\b", modified_remote))
    has_explicit_path = "PATH=" in modified_remote
    will_wrap_toolchain = REMOTE_TOOLCHAIN_REGEX.search(modified_remote) and not is_login_shell and not has_explicit_path

    # Outer quotes will be single quotes ONLY IF quote_style is "'" AND no single quotes inside AND not wrapping toolchain
    will_use_single_quotes = (quote_style == "'") and ("'" not in modified_remote) and not will_wrap_toolchain

    # 1. ADR-013 pattern probe sanitization (grep, diff, pgrep)
    if should_sanitize_grep_or_diff(modified_remote):
        dollar_probe = "|| [ $? -eq 1 ]" if will_use_single_quotes else "|| [ \\$? -eq 1 ]"
        modified_remote = f"{modified_remote} {dollar_probe}"
        reasons.append("sanitized remote pattern search against benign Exit Code 1")

    # 2. Toolchain login-shell promotion (pm2, node, pnpm, cargo, nvm, uv)
    if will_wrap_toolchain:
        escaped = modified_remote.replace("'", "'\\''")
        modified_remote = f"bash -l -c '{escaped}'"
        reasons.append("wrapped remote command in login shell (bash -l) for toolchain PATH availability")

    if modified_remote == remote_cmd:
        return cmd, False, []

    if will_use_single_quotes:
        formatted_remote = f"'{modified_remote}'"
    else:
        formatted_remote = f'"{modified_remote}"'

    opts_str = f" {' '.join(ssh_opts)}" if ssh_opts else ""
    new_ssh_part = f"{ssh_bin}{opts_str} {target} {formatted_remote}"
    new_cmd = f"{prefix}{new_ssh_part}{suffix}"
    return new_cmd, True, reasons


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
    # 1. Do not touch if already guarded with || true, || :, or [ $? -eq 1 ] / [ \$? -eq 1 ]
    if re.search(r"\|\|\s*(?:true|:|\s*\[\s*\\?\$\?\s*-eq\s*1\s*\])\b", cmd):
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
    return bin_name in ("grep", "egrep", "fgrep", "diff", "pgrep")


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

    # 4. SSH timeout and multiplexing guards
    mod_ssh, ssh_injected = inject_ssh_timeouts(modified_cmd)
    if ssh_injected:
        modified_cmd = mod_ssh
        reasons.append("injected non-blocking SSH timeout and batch mode guards")

    # 5. Remote SSH payload inspection (ADR-013 pattern probe sanitization and toolchain login-shell promotion)
    mod_remote, remote_injected, remote_reasons = sanitize_ssh_remote_payload(modified_cmd)
    if remote_injected:
        modified_cmd = mod_remote
        reasons.extend(remote_reasons)

    # 6. User-space toolchain PATH shim injection
    mod_path, path_injected = inject_path_shims(modified_cmd)
    if path_injected:
        modified_cmd = mod_path
        reasons.append("injected user-space toolchain PATH shims")

    # 7. Hermetic Python Runtime Injection & f-string expression sanitization
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

    # 8. Surgical Tail Sanitization for simple grep / diff pattern searches
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
