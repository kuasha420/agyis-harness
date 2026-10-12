# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Arafat Zahan (@kuasha420)
# Corporate Stewardship & Infrastructure: Purrfect Software Limited (PSL)
# Governed by: ICARO-42/b Ordinance (Company-Supported Personal IP Framework)

"""
Remote SSH command inspection, timeout injection, and payload sanitization (ADR-027).
"""

from __future__ import annotations

import os
from pathlib import Path
import re
import shlex
from typing import Callable, List, Optional, Tuple

SSH_TIMEOUT_OPTIONS = (
    "-o ControlMaster=auto "
    "-o ControlPath=~/.cache/psl/ssh/cm_%C "
    "-o ControlPersist=10m "
    "-o BatchMode=yes "
    "-o ConnectTimeout=10 "
    "-o ServerAliveInterval=15"
)

SSH_PATTERN = re.compile(
    r"(^|[;&|]\s*|(?:sudo|nohup|timeout\s+\S+)\s+)((?:\S+/)?(?:ssh|knot\s+exec|(?:agyis|psl)\s+remote\s+exec))(\s+|$)"
)

SSH_OPTION_FLAGS_WITH_ARG = {
    "-b", "-c", "-D", "-E", "-e", "-F", "-I", "-i", "-J",
    "-L", "-l", "-m", "-O", "-o", "-p", "-Q", "-R", "-S",
    "-W", "-w",
}

REMOTE_TOOLCHAINS = ("pm2", "node", "pnpm", "cargo", "nvm", "uv")

REMOTE_TOOLCHAIN_REGEX = re.compile(
    r"(?:^|[;&|]\s*|\b(?:sudo|xargs|nohup|exec|env|time)\s+)\s*(?:/[^\s]+/)?\b("
    + "|".join(REMOTE_TOOLCHAINS)
    + r")\b"
)


def ensure_ssh_socket_dir() -> Path:
    """
    Ensures ~/.cache/psl/ssh/ socket directory exists with 0700 permissions.
    Supports AGYIS_HARNESS_STATE_DIR and PSL_HARNESS_STATE_DIR if configured.
    """
    state_dir = os.environ.get("AGYIS_HARNESS_STATE_DIR") or os.environ.get("PSL_HARNESS_STATE_DIR")
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

    prefix = m.group(1)
    ssh_bin = m.group(2)
    sep = m.group(3) or " "
    span_start = m.start()
    span_end = m.end()

    # OpenSSH options only apply directly to the ssh client binary
    if not (ssh_bin == "ssh" or ssh_bin.endswith("/ssh")):
        return cmd, False

    ensure_ssh_socket_dir()

    injected = f"{prefix}{ssh_bin} {SSH_TIMEOUT_OPTIONS}{sep}"
    res = (cmd[:span_start] + injected + cmd[span_end:]).strip()
    return res, True


def sanitize_ssh_remote_payload(
    cmd: str,
    pattern_probe_sanitizer: Optional[Callable[[str], bool]] = None,
) -> Tuple[str, bool, List[str]]:
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

    runner_match = m.group(2).strip()
    runner_words = runner_match.split()
    runner_word_count = len(runner_words)
    if len(tokens) <= runner_word_count:
        return cmd, False, []

    ssh_bin = " ".join(tokens[:runner_word_count])
    idx = runner_word_count
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

    target_pos = ssh_part.find(target, len(ssh_bin))
    after_target = ssh_part[target_pos + len(target):].strip()
    quote_style = None
    if after_target.startswith("'") and after_target.endswith("'") and len(after_target) >= 2:
        quote_style = "'"
    elif after_target.startswith('"') and after_target.endswith('"') and len(after_target) >= 2:
        quote_style = '"'

    remote_cmd = remote_tokens[0] if len(remote_tokens) == 1 else " ".join(remote_tokens)
    modified_remote = remote_cmd
    reasons: List[str] = []

    is_login_shell = bool(re.search(r"\b(?:bash|zsh|sh)\s+(?:-[a-zA-Z]*l|--login)\b", modified_remote))
    has_explicit_path = "PATH=" in modified_remote
    will_wrap_toolchain = REMOTE_TOOLCHAIN_REGEX.search(modified_remote) and not is_login_shell and not has_explicit_path

    will_use_single_quotes = (quote_style == "'") and ("'" not in modified_remote) and not will_wrap_toolchain

    # 1. ADR-013 pattern probe sanitization (grep, diff, pgrep)
    should_sanitize = False
    if pattern_probe_sanitizer:
        should_sanitize = pattern_probe_sanitizer(modified_remote)
    else:
        # Default probe check
        should_sanitize = bool(re.search(r"\b(?:grep|diff|pgrep)\b", modified_remote)) and ("||" not in modified_remote)

    if should_sanitize:
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
