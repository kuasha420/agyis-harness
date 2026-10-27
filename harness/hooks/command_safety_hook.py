#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Arafat Zahan (@kuasha420)
# Corporate Stewardship & Infrastructure: Purrfect Software Limited (PSL)
# Governed by: ICARO-42/b Ordinance (Company-Supported Personal IP Framework)

"""
PSL Harness: PreToolUse Command Safety & Hermetic Runtime Hook

Audits and optimizes terminal commands before execution:
1. Hard blocks prohibited destructive operations (e.g. rm -rf /).
2. Prevents interactive TUI traps (nano, vim, interactive ssh).
3. Ensures non-interactive execution (PAGER=cat).
4. Hermetic Python Runtime Injection: Transparently prepends certified Python 3.12+ from
   uv's cache to PATH for inline utility scripts (python3 -c / python -c),
   guaranteeing PEP 701 f-string safety without touching host pyenv config.
5. Decoupled Grep Tail: Automatic CommandLine mutation via `|| [ $? -eq 1 ]` is decoupled
   to preserve clean process exit codes and prioritize native grep_search.
6. User-Space Toolchain PATH Shim Recovery: Discovers existing user bin directories
   (~/.local/bin, ~/.cargo/bin, ~/.local/share/pnpm, ~/.pyenv/shims) and prepends
   export PATH="<shims>:$PATH"; <cmd> for non-login subshell reliability (ADR-023).
7. Network Probe Timeout Injection: Transparently injects non-blocking timeouts and
   BatchMode flags into ssh invocations to prevent hanging background tasks (ADR-023).
"""

from __future__ import annotations

import json
import os
from pathlib import Path
import re
import shlex
import shutil
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
    "agyis", "psl", "knot", "uv", "pnpm", "npm", "npx", "cargo", "rustc",
    "pytest", "ruff", "black", "mypy", "flake8", "tsc", "rea",
)

USER_TOOLCHAIN_REGEX = re.compile(
    r"(?:^|[;&|]\s*|\b(?:sudo|xargs|nohup|exec|env|time|command)(?:\s+-[^\s]+)*\s+)\s*(?:/[^\s]+/)?\b("
    + "|".join(USER_TOOLCHAINS)
    + r")\b"
)

COMMON_PACKAGE_SUGGESTIONS: Dict[str, str] = {
    "pnpm": "Install pnpm via 'npm install -g pnpm' or Corepack: 'corepack enable pnpm'.",
    "pawthy": "Verify pawthy installation or check PATH in ~/.local/bin.",
    "ollama": "Start or install Ollama service: 'curl -fsSL https://ollama.com/install.sh | sh'.",
    "cargo": "Install Rust and Cargo toolchain: 'curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh'.",
    "uv": "Install uv hermetic package manager: 'curl -LsSf https://astral.sh/uv/install.sh | sh'.",
    "qdbus": "Install Qt D-Bus tools via your system package manager (e.g. 'pacman -S qt5-tools').",
    "lxc-attach": "Install LXC container utilities via system package manager.",
    "rea": "Install via 'pnpm add -g rea-agents' or run with 'npx rea-agents'",
}

SHELL_BUILTINS: frozenset[str] = frozenset({
    "cd", "echo", "printf", "test", "exit", "true", "false", "export", "unset",
    "source", ".", "alias", "eval", "read", "set", "trap", "wait", "shift",
    "history", "pwd", "pushd", "popd", "dirs", "exec", "type", "command", "hash",
    "kill", "jobs", "fg", "bg", "umask", "shopt", "bind", "builtin",
})


def extract_command_binary(cmd: str) -> Optional[str]:
    """
    Extracts the root executable binary name from a command string,
    ignoring environment variable prefixes (FOO=bar), sudo, and wrappers.
    """
    stripped = cmd.strip()
    if not stripped:
        return None

    first_cmd = re.split(r"[;&|]", stripped)[0].strip()
    tokens = first_cmd.split()
    if not tokens:
        return None

    wrappers = {"sudo", "xargs", "nohup", "exec", "env", "time", "command"}
    idx = 0
    while idx < len(tokens):
        token = tokens[idx]
        if "=" in token and not token.startswith("-"):
            idx += 1
            continue
        if token in wrappers:
            idx += 1
            while idx < len(tokens) and tokens[idx].startswith("-"):
                idx += 1
            continue
        bin_name = token.split("/")[-1]
        return bin_name
    return None


def check_preflight_tool_availability(cmd: str) -> Dict[str, Any]:
    """
    Audits root binary availability to prevent Exit Code 127 per ADR-013 §1.
    Returns status dict indicating availability, binary name, and actionable package suggestions.
    """
    bin_name = extract_command_binary(cmd)
    if not bin_name:
        return {"available": True, "binary": None, "reason": "No executable binary detected"}

    if bin_name in SHELL_BUILTINS or bin_name.startswith(("./", "../", "/")):
        return {"available": True, "binary": bin_name, "reason": "Shell builtin or explicit path"}

    resolved = shutil.which(bin_name)
    if not resolved:
        for shim in get_user_path_shims():
            candidate = Path(shim) / bin_name
            if candidate.is_file() and os.access(candidate, os.X_OK):
                resolved = str(candidate)
                break

    if resolved:
        return {"available": True, "binary": bin_name, "path": resolved}

    suggestion = COMMON_PACKAGE_SUGGESTIONS.get(
        bin_name,
        f"Binary '{bin_name}' not found in PATH. Verify installation or use 'command -v {bin_name}' preflight probe."
    )
    return {
        "available": False,
        "binary": bin_name,
        "exit_code_risk": 127,
        "suggestion": suggestion,
        "warning": f"PSL Preflight Guard (ADR-013): Missing CLI binary '{bin_name}'. {suggestion}",
    }


from harness.remote.safety import (
    REMOTE_TOOLCHAINS,
    REMOTE_TOOLCHAIN_REGEX,
    SSH_OPTION_FLAGS_WITH_ARG,
    SSH_PATTERN,
    SSH_TIMEOUT_OPTIONS,
    ensure_ssh_socket_dir,
    inject_ssh_timeouts,
    sanitize_ssh_remote_payload as _raw_sanitize_ssh_remote_payload,
)


def get_user_path_shims() -> List[str]:
    """
    Discovers existing candidate user bin directories on the host:
    ~/.local/bin, ~/.cargo/bin, ~/.local/share/pnpm, ~/.npm-global/bin, ~/.pyenv/shims.
    """
    candidates = [
        Path.home() / ".local/bin",
        Path.home() / ".cargo/bin",
        Path.home() / ".local/share/pnpm",
        Path.home() / ".npm-global/bin",
        Path.home() / ".pyenv/shims",
    ]
    return [str(p) for p in candidates if p.is_dir()]


def inject_path_shims(cmd: str) -> Tuple[str, bool]:
    """
    Prepend export PATH="<shims>:$PATH"; <cmd> if user toolchains
    (uv, pnpm, npm, npx, cargo, rustc, pytest, ruff, black, mypy, flake8, tsc, rea)
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

    candidate_names = (".local/bin", ".cargo/bin", ".local/share/pnpm", ".npm-global/bin", ".pyenv/shims")
    if any(shim in cmd for shim in shims) or any(cand in cmd for cand in candidate_names):
        return cmd, False

    shim_str = ":".join(shims)
    return f'export PATH="{shim_str}:$PATH"; {cmd.strip()}', True


def sanitize_ssh_remote_payload(cmd: str) -> Tuple[str, bool, List[str]]:
    """
    Inspects SSH remote execution payload to apply ADR-013 pattern probe
    sanitization (|| [ $? -eq 1 ]) and selective toolchain login-shell promotion
    (bash -l -c '...'). Delegated to harness.remote.safety.
    """
    return _raw_sanitize_ssh_remote_payload(cmd, pattern_probe_sanitizer=should_sanitize_grep_or_diff)


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


INLINE_INTERPRETER_PATTERNS = [
    re.compile(r"\bpython[3]?(?:\.\d+)?\s+(?:-[^\s]+\s+)*-c\s*\$?('''|\"\"\"|'|\")((?:\\.|(?!\1).)*?)\1", re.DOTALL),
    re.compile(r"\bnode\s+(?:-[^\s]+\s+)*-e\s*\$?('''|\"\"\"|'|\")((?:\\.|(?!\1).)*?)\1", re.DOTALL),
    re.compile(r"\bbash\s+(?:-[^\s]+\s+)*-c\s*\$?('''|\"\"\"|'|\")((?:\\.|(?!\1).)*?)\1", re.DOTALL),
    re.compile(r"\bsh\s+(?:-[^\s]+\s+)*-c\s*\$?('''|\"\"\"|'|\")((?:\\.|(?!\1).)*?)\1", re.DOTALL),
]

INLINE_SCRIPT_DENY_REASON = (
    "[PSL-INV-002 VIOLATION] Multi-line or complex inline script detected (>100 chars or newlines). "
    "In accordance with PSL-INV-002 §4, write multi-line scripts to a temporary scratch file "
    "('scratch/probe.py' or 'scratch/probe.sh') and execute the script file instead of fragile "
    "multi-line shell escaping."
)


def check_inline_script_hygiene(cmd: str) -> Tuple[str, Optional[str]]:
    """
    Validates inline script hygiene per PSL-INV-002 §4.
    Blocks complex or multi-line inline scripts in python, node, bash, or sh
    exceeding 100 chars or containing newlines, steering towards temporary scratch files.
    """
    if not cmd or not cmd.strip():
        return ("allow", None)

    # 1. Environment bypass
    if os.environ.get("PSL_ALLOW_INLINE_SCRIPTS") == "1":
        return ("allow", None)

    # 2. Inline directive bypass
    cmd_lower = cmd.lower()
    if "# agyis: allow-inline-script" in cmd_lower or "# allow-inline" in cmd_lower:
        return ("allow", None)

    for pattern in INLINE_INTERPRETER_PATTERNS:
        for match in pattern.finditer(cmd):
            body = match.group(2)
            stripped = body.strip()
            if "\n" in body or "\r" in body or "\\n" in body or len(stripped) > 100:
                return ("deny", INLINE_SCRIPT_DENY_REASON)

    return ("allow", None)


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


def inject_disassembler_batch_flags(cmd: str) -> Tuple[str, bool, List[str]]:
    """
    Ensures non-interactive batch execution for interactive disassemblers
    (gdb -> gdb -batch, rizin -> rizin -q).
    """
    bin_name = extract_command_binary(cmd)
    if not bin_name or bin_name not in ("gdb", "rizin"):
        return cmd, False, []

    reasons: List[str] = []
    modified = cmd

    if bin_name == "gdb":
        if not re.search(r"\b--?batch\b", modified):
            modified = re.sub(
                r"(\b(?:[^\s]+/)?gdb\b)(?!\s+--?batch\b)",
                r"\1 -batch",
                modified,
                count=1,
            )
            if modified != cmd:
                reasons.append("enforced non-interactive gdb -batch mode")

    elif bin_name == "rizin":
        if not re.search(r"(?:^|\s)-q(?:\s|$)", modified):
            modified = re.sub(
                r"(\b(?:[^\s]+/)?rizin\b)(?!\s+-q(?:\s|$))",
                r"\1 -q",
                modified,
                count=1,
            )
            if modified != cmd:
                reasons.append("enforced non-interactive rizin -q batch mode")

    changed = modified != cmd
    return modified, changed, reasons


def inject_rea_setup_flags(cmd: str) -> Tuple[str, bool, List[str]]:
    """
    Ensures non-interactive execution for 'rea setup' by injecting '--yes' flag
    if neither '--yes' nor '-y' is present.
    """
    if not re.search(r"\b(?:[^\s]+/)?rea\s+setup\b", cmd):
        return cmd, False, []

    if re.search(r"(?:^|\s)(?:--yes|-y)(?:\s|$)", cmd):
        return cmd, False, []

    reasons = ["enforced non-interactive rea setup --yes"]
    modified = re.sub(
        r"(\b(?:[^\s]+/)?rea\s+setup\b)",
        r"\1 --yes",
        cmd,
        count=1,
    )
    return modified, True, reasons


def sanitize_command(raw_cmd: str, check_preflight: bool = False) -> Tuple[Optional[str], Optional[str], Optional[str]]:
    """
    Evaluates and sanitizes a raw command line string.
    Returns: (decision, modified_command_or_none, reason_or_none)
    """
    cmd = raw_cmd.strip()
    if not cmd:
        return ("allow", None, None)

    # 0. Preflight binary availability check (Exit 127 prevention per ADR-013 §1)
    if check_preflight:
        pf = check_preflight_tool_availability(cmd)
        if not pf.get("available", True):
            return (
                "deny",
                None,
                pf.get("warning") or f"PSL Safety Gate: Binary '{pf.get('binary')}' not found."
            )

    # 0b. Inline script hygiene check (PSL-INV-002 §4)
    hygiene_decision, hygiene_reason = check_inline_script_hygiene(cmd)
    if hygiene_decision == "deny":
        return ("deny", None, hygiene_reason)

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

    # 3. Disassembler batch mode optimization
    mod_disasm, disasm_injected, disasm_reasons = inject_disassembler_batch_flags(modified_cmd)
    if disasm_injected:
        modified_cmd = mod_disasm
        reasons.extend(disasm_reasons)

    # 3b. REA non-interactive setup optimization
    mod_rea, rea_injected, rea_reasons = inject_rea_setup_flags(modified_cmd)
    if rea_injected:
        modified_cmd = mod_rea
        reasons.extend(rea_reasons)

    # 4. Pager / non-interactive optimization
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

    # 7. Hermetic Python Runtime Injection
    if is_inline_python_command(modified_cmd):
        hermetic_bin = find_hermetic_uv_python_bin()
        if hermetic_bin and "PATH=" not in modified_cmd:
            modified_cmd = f'PATH="{hermetic_bin}:$PATH" {modified_cmd}'
            reasons.append("injected hermetic CPython >= 3.12 for PEP 701 f-string safety")

    if modified_cmd != cmd:
        return ("allow", modified_cmd, "PSL PreToolUse: " + "; ".join(reasons))

    return ("allow", None, None)


check_command_safety = sanitize_command


PAUSE_GATE_FILES = (
    Path(".agents/artifacts/pause_gate.json"),
    Path(".pause_gate"),
    Path(".agents/artifacts/PARKED_STATE.md"),
    Path(".agents/teamwork/PARKED_STATE.md"),
)

PAUSE_KILL_SHELL_REGEX = re.compile(r"\b(?:kill|pkill|killall)\s+-(?:9|SIGKILL|KILL)\b")


def is_pause_gate_active(workspace_dir: Optional[Path] = None) -> bool:
    """
    Checks if an active pause gate exists in the workspace.
    Fails open (returns False) on JSON parsing or OS read errors.
    """
    base_dir = workspace_dir or Path.cwd()
    for rel_path in PAUSE_GATE_FILES:
        target = base_dir / rel_path
        if not target.is_file():
            continue
        try:
            if target.name.endswith(".json"):
                data = json.loads(target.read_text(encoding="utf-8"))
                if isinstance(data, dict):
                    status = str(data.get("status", "")).strip().lower()
                    if status in ("paused", "pausing"):
                        return True
            elif target.name.endswith(".md"):
                text = target.read_text(encoding="utf-8", errors="replace")
                if re.search(r"status:\s*[\"']?(?:paused|pausing)[\"']?", text, re.IGNORECASE):
                    return True
            else:
                return True
        except Exception as e:
            sys.stderr.write(f"PSL Command Safety Warning: Error reading pause gate '{target}': {e}\n")
            continue
    return False


def check_pause_safety(
    tool_name: str,
    arguments: Dict[str, Any],
    workspace_dir: Optional[Path] = None,
) -> Tuple[str, Optional[str]]:
    """
    Evaluates whether the tool call violates the Zero-Kill Swarm Parking Invariant.
    Returns: ("deny", reason) or ("allow", None).
    """
    try:
        if not is_pause_gate_active(workspace_dir):
            return ("allow", None)

        prohibited_reason = (
            "PSL Safety Gate (Zero-Kill Swarm Parking Invariant): "
            "Subagent termination via 'kill' is prohibited while workspace is parked. "
            "Dispatch a graceful resume message or remove .agents/artifacts/pause_gate.json after state handoff."
        )

        norm_tool = (tool_name or "").strip().lower()
        if norm_tool == "manage_subagents":
            action = str(arguments.get("Action") or arguments.get("action") or "").strip().lower()
            if action in ("kill", "kill_all", "cancel"):
                return ("deny", prohibited_reason)

        elif norm_tool == "manage_task":
            action = str(arguments.get("Action") or arguments.get("action") or "").strip().lower()
            if action in ("kill", "cancel"):
                return ("deny", prohibited_reason)

        elif norm_tool == "run_command":
            cmd = str(arguments.get("CommandLine") or arguments.get("command") or "").strip()
            if PAUSE_KILL_SHELL_REGEX.search(cmd):
                return ("deny", prohibited_reason)

        return ("allow", None)
    except Exception as e:
        sys.stderr.write(f"PSL Command Safety Warning: Unexpected error in check_pause_safety: {e}\n")
        return ("allow", None)


def main() -> None:
    try:
        payload = json.load(sys.stdin)
    except Exception:
        print(json.dumps({"decision": "allow"}))
        return

    tool_call = payload.get("toolCall") or {}
    tool_name = tool_call.get("name") or payload.get("tool_name") or "run_command"
    tool_args = tool_call.get("args") or payload.get("tool_args") or {}

    raw_cmd = (tool_args.get("CommandLine") or payload.get("command") or payload.get("CommandLine") or "").strip()

    if payload.get("check_preflight") or payload.get("action") == "check_preflight":
        preflight_info = check_preflight_tool_availability(raw_cmd)
        print(json.dumps(preflight_info))
        return

    pause_decision, pause_reason = check_pause_safety(
        tool_name,
        tool_args if tool_args else {"CommandLine": raw_cmd},
    )
    if pause_decision == "deny":
        print(json.dumps({
            "decision": "deny",
            "reason": pause_reason
        }))
        return

    if tool_name in ("manage_subagents", "manage_task"):
        print(json.dumps({"decision": "allow"}))
        return

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
