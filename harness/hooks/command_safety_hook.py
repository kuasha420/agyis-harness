#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Arafat Zahan (@kuasha420)
# Corporate Stewardship & Infrastructure: Purrfect Software Limited (PSL)
# Governed by: ICARO-42/b Ordinance (Company-Supported Personal IP Framework)

"""
PSL Harness: PreToolUse Command Safety & Hermetic Runtime Hook

Audits, sanitizes, and normalizes terminal and MCP tool calls before execution:
1. Blocks destructive patterns and interactive TUI traps.
2. Enforces non-interactive PAGER=cat, gdb -batch, rizin -q, rea setup --yes, and SSH guards.
3. Resolves scratch promotion targets from workspacePaths into verified absolute paths
   only for genuine complex/multi-line scripts (preserving short pipelines and quoted strings).
4. Injects user PATH shims & CPython 3.12+ using keyword-safe `export PATH="..."; ` syntax.
5. Enforces Zero-Kill Swarm Parking gates and schema-driven MCP / run_command sanitization.
"""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import re
import shlex
import shutil
import sys
import tempfile
from typing import Any, Dict, List, Optional, Tuple

from harness.hooks.anti_clobber import WRITE_CLOBBER_TOOLS, check_anti_clobber
from harness.hooks.resource_semaphore import evaluate_resource_semaphore
from harness.hooks.mcp_normalizer import (
    FILE_PATH_TOOLS,
    REA_BYTE_TOOLS,
    REA_INSPECTION_TOOLS,
    REA_PROCEDURE_TOOLS,
    REA_SEARCH_TOOLS,
    get_schema_properties,
    load_mcp_tool_schema,
    normalize_mcp_tool_call,
    normalize_rea_mcp_tool_call,
)
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
from harness.utils.context import get_active_brain_dir, get_active_conversation_id

DANGEROUS_PATTERNS = [
    r"\brm\s+.*-[a-zA-Z]*r.*-[a-zA-Z]*f.*\s+(?:/\*?|\./\*?|\*|~|~/\*?|\$HOME|\${HOME})(?:\s|$)",
    r"\brm\s+.*-[a-zA-Z]*f.*-[a-zA-Z]*r.*\s+(?:/\*?|\./\*?|\*|~|~/\*?|\$HOME|\${HOME})(?:\s|$)",
    r"\brm\s+-[a-zA-Z]*[rR][a-zA-Z]*f[a-zA-Z]*\s+(?:/\*?|\./\*?|\*|~|~/\*?|\$HOME|\${HOME})(?:\s|$)",
    r"\brm\s+-[a-zA-Z]*f[a-zA-Z]*[rR][a-zA-Z]*\s+(?:/\*?|\./\*?|\*|~|~/\*?|\$HOME|\${HOME})(?:\s|$)",
    r"\bgit\s+reset\s+--hard\b",
    r"\bgit\s+checkout\s+--\s+\.",
    r"\bgit\s+clean\s+-[a-zA-Z]*f",
    r"\bmkfs\b", r"\bdd\s+if=.*?of=/dev/[sh]d[a-z]\b",
]
INTERACTIVE_COMMANDS = ["nano", "vim", "vi", "emacs", "less", "more", "top", "htop", "glances"]
USER_TOOLCHAINS = ("agyis", "psl", "knot", "uv", "pnpm", "npm", "npx", "cargo", "rustc", "pytest", "ruff", "black", "mypy", "flake8", "tsc", "rea")
USER_TOOLCHAIN_REGEX = re.compile(
    r"(?:^|[;&|]\s*|\b(?:sudo|xargs|nohup|exec|env|time|command)(?:\s+-[^\s]+)*\s+)"
    r"(?:[A-Za-z_][A-Za-z0-9_]*=(?:'[^']*'|\"[^\"]*\"|[^\s]*)\s+)*"
    r"(?:/[^\s]+/)?\b(" + "|".join(USER_TOOLCHAINS) + r")\b"
)
_EXPLICIT_PATH_ASSIGN_RE = re.compile(r"(?:^|[\s;|&])PATH=")
_QUOTED_STR_RE = re.compile(r"'[^']*'|\"(?:\\.|[^\"])*\"")
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
    "cd", "echo", "printf", "test", "exit", "true", "false", "export", "unset", "source", ".", "alias", "eval",
    "read", "set", "trap", "wait", "shift", "history", "pwd", "pushd", "popd", "dirs", "exec", "type", "command",
    "hash", "kill", "jobs", "fg", "bg", "umask", "shopt", "bind", "builtin",
})
_CMD_BOUNDARY = r"(?:^|[;&|(\n]\s*)(?:(?:sudo|xargs|nohup|exec|env|time|command)(?:\s+-[^\s]+)*\s+)*(?:[A-Za-z_][A-Za-z0-9_]*=[^\s]+\s+)*"
INLINE_INTERPRETER_CONFIGS: List[Tuple[str, Any, str, str]] = [
    ("python", re.compile(_CMD_BOUNDARY + r"\bpython3?(?:\.\d+)?\s+(?:-[^\s]+\s+)*-c\s*\$?('''|\"\"\"|'|\")((?:\\.|(?!\1).)*?)\1", re.DOTALL), "-c", ".py"),
    ("node", re.compile(_CMD_BOUNDARY + r"\bnode\s+(?:-[^\s]+\s+)*-e\s*\$?('''|\"\"\"|'|\")((?:\\.|(?!\1).)*?)\1", re.DOTALL), "-e", ".js"),
    ("bash", re.compile(_CMD_BOUNDARY + r"\bbash\s+(?:-[^\s]+\s+)*-c\s*\$?('''|\"\"\"|'|\")((?:\\.|(?!\1).)*?)\1", re.DOTALL), "-c", ".sh"),
    ("sh", re.compile(_CMD_BOUNDARY + r"\bsh\s+(?:-[^\s]+\s+)*-c\s*\$?('''|\"\"\"|'|\")((?:\\.|(?!\1).)*?)\1", re.DOTALL), "-c", ".sh"),
]
INLINE_INTERPRETER_PATTERNS = [cfg[1] for cfg in INLINE_INTERPRETER_CONFIGS]
INLINE_SCRIPT_DENY_REASON = (
    "[PSL-INV-003 VIOLATION] Multi-line or complex inline script detected (>250 chars or newlines). "
    "In accordance with PSL-INV-003, write multi-line scripts to a temporary scratch file "
    "('scratch/probe.py' or 'scratch/probe.sh') and execute the script file instead of fragile multi-line shell escaping."
)
PAUSE_GATE_FILES = (Path(".agents/artifacts/pause_gate.json"), Path(".pause_gate"), Path(".agents/artifacts/PARKED_STATE.md"), Path(".agents/teamwork/PARKED_STATE.md"))
PAUSE_KILL_SHELL_REGEX = re.compile(r"\b(?:kill|pkill|killall)\s+-(?:9|SIGKILL|KILL)\b")
RUN_COMMAND_ALLOWED_KEYS: frozenset[str] = frozenset({
    "CommandLine",
    "WaitMsBeforeAsync",
    "IsDaemon",
    "toolSummary",
    "NotificationTimeoutSeconds",
})

_ACTIVE_CONVO_ID: Optional[str] = None


def extract_command_binary(cmd: str) -> Optional[str]:
    """Extracts the root executable binary name, skipping env assignments and wrappers."""
    stripped = cmd.strip()
    if not stripped:
        return None
    tokens = re.split(r"[;&|]", stripped)[0].strip().split()
    wrappers = {"sudo", "xargs", "nohup", "exec", "env", "time", "command"}
    idx = 0
    while idx < len(tokens):
        tok = tokens[idx]
        if "=" in tok and not tok.startswith("-"):
            idx += 1
        elif tok in wrappers:
            idx += 1
            while idx < len(tokens) and tokens[idx].startswith("-"):
                idx += 1
        else:
            return tok.split("/")[-1]
    return None


def check_preflight_tool_availability(cmd: str) -> Dict[str, Any]:
    """Audits root binary availability to prevent Exit Code 127 (ADR-013)."""
    bin_name = extract_command_binary(cmd)
    if not bin_name:
        return {"available": True, "binary": None, "reason": "No executable binary detected"}
    if bin_name in SHELL_BUILTINS or bin_name.startswith(("./", "../", "/")):
        return {"available": True, "binary": bin_name, "reason": "Shell builtin or explicit path"}

    resolved = shutil.which(bin_name) or next(
        (str(Path(s) / bin_name) for s in get_user_path_shims() if (Path(s) / bin_name).is_file() and os.access(Path(s) / bin_name, os.X_OK)),
        None,
    )
    if resolved:
        return {"available": True, "binary": bin_name, "path": resolved}
    suggestion = COMMON_PACKAGE_SUGGESTIONS.get(
        bin_name, f"Binary '{bin_name}' not found in PATH. Verify installation or use 'command -v {bin_name}' preflight probe."
    )
    return {
        "available": False, "binary": bin_name, "exit_code_risk": 127, "suggestion": suggestion,
        "warning": f"[AGYIS PREFLIGHT] (ADR-013): Missing CLI binary '{bin_name}'. {suggestion}",
    }


def get_user_path_shims() -> List[str]:
    """Discovers existing user bin directories on the host."""
    cands = (".local/bin", ".cargo/bin", ".local/share/pnpm", ".npm-global/bin", ".pyenv/shims")
    return [str(Path.home() / rel) for rel in cands if (Path.home() / rel).is_dir()]


def inject_path_shims(cmd: str) -> Tuple[str, bool]:
    """Prepends keyword-safe `export PATH="<shims>:$PATH"; <cmd>` for user toolchains."""
    has_path = bool(_EXPLICIT_PATH_ASSIGN_RE.search(_QUOTED_STR_RE.sub("__Q__", cmd)))
    if not cmd.strip() or has_path or not USER_TOOLCHAIN_REGEX.search(cmd):
        return cmd, False
    shims = get_user_path_shims()
    cand_names = (".local/bin", ".cargo/bin", ".local/share/pnpm", ".npm-global/bin", ".pyenv/shims")
    if not shims or any(s in cmd for s in shims) or any(c in cmd for c in cand_names):
        return cmd, False
    escaped = ":".join(shims).replace("\\", "\\\\").replace('"', '\\"').replace("$", "\\$").replace("`", "\\`")
    return f'export PATH="{escaped}:$PATH"; {cmd.strip()}', True


def sanitize_ssh_remote_payload(cmd: str) -> Tuple[str, bool, List[str]]:
    """Inspects SSH remote execution payload via harness.remote.safety."""
    return _raw_sanitize_ssh_remote_payload(cmd, pattern_probe_sanitizer=should_sanitize_grep_or_diff)


def find_hermetic_uv_python_bin() -> Optional[Path]:
    """Finds installed CPython 3.12+ bin directory in uv's cache."""
    from harness.runtime.tool_checks_common import find_hermetic_uv_python

    py_bin = find_hermetic_uv_python()
    return py_bin.parent if py_bin is not None else None


def is_inline_python_command(cmd: str) -> bool:
    """Detects inline python -c / python3 -c invocations."""
    return bool(re.search(r"\b(?:python3?)\s+-c\b", cmd))


def is_python_command(cmd: str) -> bool:
    """Detects python / python3 invocations (inline -c, -m module, or script execution)."""
    if re.search(r"\bpython3?(?:\.\d+)?\b", cmd):
        return True
    bin_name = extract_command_binary(cmd)
    if bin_name and bin_name.endswith(".py"):
        return True
    return False


def _find_promotable_inline_matches(cmd: str) -> List[Tuple[Any, str, str, str, str]]:
    """Returns genuine complex/multi-line inline script matches requiring scratch promotion."""
    if not cmd or not cmd.strip() or os.environ.get("PSL_ALLOW_INLINE_SCRIPTS") == "1":
        return []
    cmd_lower = cmd.lower()
    if "# agyis: allow-inline-script" in cmd_lower or "# allow-inline" in cmd_lower:
        return []
    if re.search(r"<<-?\s*['\"]?[A-Za-z_][A-Za-z0-9_]*", cmd):
        return []

    matches: List[Tuple[Any, str, str, str, str]] = []
    for interp, pattern, flag, ext in INLINE_INTERPRETER_CONFIGS:
        for match in pattern.finditer(cmd):
            body = match.group(2)
            stripped = body.strip()
            has_real_nl = "\n" in body or "\r" in body
            if interp in ("bash", "sh"):
                if not has_real_nl and len(stripped) <= 250:
                    continue
                if has_real_nl and len(stripped) <= 250:
                    lines = [ln.strip() for ln in body.splitlines() if ln.strip()]
                    if len(lines) >= 2 and all(ln.endswith(("\\", "|", "&&", "||")) for ln in lines[:-1]) and not re.search(r"\b(?:for|while|if|case|function)\b", stripped):
                        continue
            elif not has_real_nl and len(stripped) <= 250:
                if "\\n" not in body or "\\n" not in re.sub(r"'(?:\\.|[^'])*'|\"(?:\\.|[^\"])*\"|\\\"(?:\\\\.|[^\"])*\\\"", "", body):
                    continue
            matches.append((match, interp, flag, ext, body))
    return matches


def resolve_scratch_target_path(ext: str, script_hash: str, workspace_dir: Optional[Path] = None) -> Tuple[Path, str]:
    """Resolves verified absolute scratch path (workspacePaths/cwd -> brain scratch -> tempdir)."""
    cid = _ACTIVE_CONVO_ID or os.environ.get("AGYIS_CONVERSATION_ID") or get_active_conversation_id() or "default"
    candidates: List[Path] = []
    base = workspace_dir or Path.cwd()
    if "/.gemini/config/plugins/" not in str(base) and "/site-packages/" not in str(base):
        candidates.append(base / "scratch" if (base / "scratch").is_dir() else base / ".agents" / "scratch")
    try:
        candidates.append(get_active_brain_dir() / cid / "scratch")
    except (OSError, ValueError):
        pass
    candidates.append(Path(tempfile.gettempdir()) / "agyis_scratch" / cid)
    for scratch_dir in candidates:
        try:
            scratch_dir.mkdir(parents=True, exist_ok=True)
            target = (scratch_dir / f"exec_{script_hash}{ext}").resolve()
            target.touch(exist_ok=True)
            t_str = str(target)
            return target, (shlex.quote(t_str) if any(c in t_str for c in " \t'\"$") else t_str)
        except (OSError, PermissionError):
            continue
    raise OSError("Unable to resolve writable scratch target directory")


def promote_inline_script_to_scratch(cmd: str, workspace_dir: Optional[Path] = None) -> Tuple[str, Optional[str], Optional[str]]:
    """Promotes complex/multi-line inline scripts into verified absolute scratch files."""
    matches = _find_promotable_inline_matches(cmd)
    if not matches:
        return ("allow", None, None)
    try:
        modified_cmd, promoted_paths = cmd, []
        for match, _interp, flag, ext, body in reversed(sorted(matches, key=lambda item: item[0].start())):
            script_body = body.replace(r'\"', '"').replace(r'\$', '$').replace(r'\\', '\\') if match.group(1) == '"' else body
            if "\n" not in script_body and r"\n" in script_body:
                script_body = script_body.replace(r"\n", "\n")
            if "\r" not in script_body and r"\r" in script_body:
                script_body = script_body.replace(r"\r", "\r")
            script_hash = hashlib.sha256(script_body.encode("utf-8")).hexdigest()[:8]
            target_file, exec_path = resolve_scratch_target_path(ext, script_hash, workspace_dir)
            header = "//" if ext == ".js" else "#"
            target_file.write_text(f"{header} Transparently promoted by PSL command_safety_hook (PSL-INV-003)\n{script_body}\n", encoding="utf-8")
            if ext == ".sh":
                target_file.chmod(target_file.stat().st_mode | 0o755)
            promoted_paths.append(exec_path)
            replace_start = match.start() + match.group(0)[: match.start(1) - match.start()].rfind(flag)
            modified_cmd = modified_cmd[:replace_start] + exec_path + modified_cmd[match.end() :]
        hint = (
            f"[AGYIS COGNITIVE HINT] In accordance with PSL-INV-003, your inline script was "
            f"transparently promoted to '{promoted_paths[-1]}' and executed. For subsequent complex scripts, "
            "author directly into temporary scratch files."
        )
        return ("allow", modified_cmd, hint)
    except Exception as e:
        sys.stderr.write(f"[AGYIS COMMAND SAFETY] Warning: Error during scratch promotion: {e}\n")
        return ("deny", None, INLINE_SCRIPT_DENY_REASON)


def check_inline_script_hygiene(
    cmd: str, route_to_promotion: bool = False, workspace_dir: Optional[Path] = None,
) -> Tuple[str, Optional[str]] | Tuple[str, Optional[str], Optional[str]]:
    """Validates inline script hygiene; allows short single-line commands and routes complex ones."""
    if not _find_promotable_inline_matches(cmd):
        return ("allow", None) if not route_to_promotion else ("allow", None, None)
    return promote_inline_script_to_scratch(cmd, workspace_dir=workspace_dir) if route_to_promotion else ("deny", INLINE_SCRIPT_DENY_REASON)


def split_shell_pipes(cmd: str, split_compound: bool = False) -> Tuple[List[str], bool]:
    """Splits command into pipeline (or compound) segments respecting quotes, returning (segments, has_control_flow)."""
    segments: List[str] = []
    cur: List[str] = []
    in_s = in_d = esc = has_cf = False
    i, n = 0, len(cmd)
    while i < n:
        c = cmd[i]
        if esc:
            cur.append(c); esc = False
        elif c == "\\":
            cur.append(c); esc = True
        elif c == "'" and not in_d:
            cur.append(c); in_s = not in_s
        elif c == '"' and not in_s:
            cur.append(c); in_d = not in_d
        elif not in_s and not in_d and c in (";", "&", "\n"):
            if c == "\n" and not split_compound:
                cur.append(c)
            else:
                has_cf = True
                if split_compound:
                    if c == "&" and i + 1 < n and cmd[i + 1] == "&":
                        i += 1
                    seg = "".join(cur).strip()
                    if seg:
                        segments.append(seg)
                    cur = []
                else:
                    cur.append(c)
        elif not in_s and not in_d and c == "|" and i + 1 < n and cmd[i + 1] == "|":
            has_cf = True
            if split_compound:
                seg = "".join(cur).strip()
                if seg:
                    segments.append(seg)
                cur = []
            else:
                cur.extend("||")
            i += 2; continue
        elif not in_s and not in_d and c == "|":
            seg = "".join(cur).strip()
            if seg or not split_compound:
                segments.append(seg)
            cur = []
        else:
            cur.append(c)
        i += 1
    tail = "".join(cur).strip()
    if tail or (cur and not split_compound):
        segments.append(tail)
    if split_compound and re.match(r"^(?:for|if|while|until|case)\b|^[{(]", cmd.lstrip()):
        has_cf = True
    elif not split_compound and not in_s and not in_d and re.search(r"\b(?:if|then|else|fi|test)\b|\[\s*\[?", cmd):
        has_cf = True
    return segments, has_cf


def should_sanitize_grep_or_diff(cmd: str) -> bool:
    """Returns True if cmd is a simple standalone grep/diff/rg pipeline eligible for exit-1 guard."""
    if re.search(r"\|\|\s*(?:true|:|\[\s*\\?\$\?\s*-eq\s*1\s*\])(?:\s|$|;|&)", cmd):
        return False
    segments, has_cf = split_shell_pipes(cmd)
    if has_cf or not segments or not segments[-1].split():
        return False
    return extract_command_binary(segments[-1]) in ("grep", "egrep", "fgrep", "diff", "pgrep", "rg")


def inject_disassembler_batch_flags(cmd: str) -> Tuple[str, bool, List[str]]:
    """Ensures non-interactive batch execution for gdb (-batch) and rizin (-q)."""
    bin_name = extract_command_binary(cmd)
    specs = {
        "gdb": (r"\b--?batch\b", r"(\b(?:[^\s]+/)?gdb\b)(?!\s+--?batch\b)", r"\1 -batch", "enforced non-interactive gdb -batch mode"),
        "rizin": (r"(?:^|\s)-q(?:\s|$)", r"(\b(?:[^\s]+/)?rizin\b)(?!\s+-q(?:\s|$))", r"\1 -q", "enforced non-interactive rizin -q batch mode"),
    }
    if bin_name not in specs:
        return cmd, False, []
    check_re, sub_re, repl, reason = specs[bin_name]
    if re.search(check_re, cmd):
        return cmd, False, []
    mod = re.sub(sub_re, repl, cmd, count=1)
    return (mod, True, [reason]) if mod != cmd else (cmd, False, [])


def inject_rea_setup_flags(cmd: str) -> Tuple[str, bool, List[str]]:
    """Ensures non-interactive `rea setup --yes` when neither -y nor --yes is given."""
    if not re.search(r"\b(?:[^\s]+/)?rea\s+setup\b", cmd) or re.search(r"(?:^|\s)(?:--yes|-y)(?:\s|$)", cmd):
        return cmd, False, []
    return re.sub(r"(\b(?:[^\s]+/)?rea\s+setup\b)", r"\1 --yes", cmd, count=1), True, ["enforced non-interactive rea setup --yes"]


def inject_rea_dirtyroom_env(cmd: str, workspace_dir: Optional[Path] = None) -> Tuple[str, bool, List[str]]:
    """Automatically injects REA direct-mount & pre-analyzed Ghidra project environment variables."""
    if not re.search(r"\b(?:[^\s]+/)?rea\s+(?:decompile|disasm|xrefs|read-bytes|search|procedure_pseudo_code|inspect-native)\b", cmd):
        return cmd, False, []
    if "REA_GHIDRA_PROJECT_DIR" in cmd or "REA_GHIDRA_DIRECT_MOUNT" in cmd:
        return cmd, False, []
    try:
        from harness.re.scaffold import get_dirtyroom_root
        dr = get_dirtyroom_root(workspace_dir)
        if not dr or not (dr / "ghidra").is_dir():
            return cmd, False, []
        gprs = list((dr / "ghidra").glob("*.gpr"))
        if not gprs:
            return cmd, False, []
        import shlex
        gpr = gprs[0]
        env_prefix = (
            f"REA_GHIDRA_PROJECT_DIR={shlex.quote(str(dr / 'ghidra'))} "
            f"REA_GHIDRA_PROJECT_NAME={shlex.quote(gpr.stem)} "
            f"REA_GHIDRA_PROJECT_PATH={shlex.quote(str(gpr))} "
            f'REA_GHIDRA_DIRECT_MOUNT="1" '
            f"AGYIS_DIRTYROOM={shlex.quote(str(dr))} "
        )
        return env_prefix + cmd, True, ["injected dirtyroom REA direct-mount environment"]
    except Exception as exc:
        sys.stderr.write(f"[AGYIS COMMAND SAFETY] Warning: Failed to resolve dirtyroom REA env: {exc}\n")
        return cmd, False, []


def sanitize_command(raw_cmd: str, check_preflight: bool = False, promote_scratch: bool = True, workspace_dir: Optional[Path] = None) -> Tuple[Optional[str], Optional[str], Optional[str]]:
    """Audits and transforms a shell command before execution."""
    cmd = raw_cmd.strip()
    if not cmd:
        return ("allow", None, None)
    original_cmd = cmd
    if check_preflight:
        pf = check_preflight_tool_availability(cmd)
        if not pf.get("available", True):
            return ("deny", None, pf.get("warning") or f"[AGYIS COMMAND SAFETY] Binary '{pf.get('binary')}' not found.")

    modified_cmd, reasons = cmd, []
    hygiene_dec, hygiene_reason = check_inline_script_hygiene(cmd)
    if hygiene_dec == "deny":
        if not promote_scratch:
            return ("deny", None, hygiene_reason)
        promo_dec, promo_cmd, promo_reason = promote_inline_script_to_scratch(cmd, workspace_dir=workspace_dir)
        if promo_dec != "allow" or promo_cmd is None:
            return ("deny", None, promo_reason or hygiene_reason)
        modified_cmd = cmd = promo_cmd
        if promo_reason:
            reasons.append(promo_reason)

    for pattern in DANGEROUS_PATTERNS:
        if re.search(pattern, cmd):
            return ("deny", None, f"[AGYIS COMMAND SAFETY] Command matches prohibited destructive pattern: {pattern}")
    first_token = cmd.split()[0].split("/")[-1]
    if first_token in INTERACTIVE_COMMANDS:
        return ("deny", None, f"[AGYIS COMMAND SAFETY] Interactive command '{first_token}' blocked. Agent execution must be strictly non-interactive. Use batch or script alternatives.")

    for fn in (inject_disassembler_batch_flags, inject_rea_setup_flags):
        mod_f, changed_f, r_f = fn(modified_cmd)
        if changed_f:
            modified_cmd = mod_f; reasons.extend(r_f)
    mod_rea, rea_env_injected, rea_reasons = inject_rea_dirtyroom_env(modified_cmd, workspace_dir=workspace_dir)
    if rea_env_injected:
        modified_cmd = mod_rea; reasons.extend(rea_reasons)
    segments, is_compound = split_shell_pipes(modified_cmd, split_compound=True)
    cmd_bins = [b for b in (extract_command_binary(seg) for seg in segments) if b]
    already_has_pager = bool(re.search(r"--no-pager|\bPAGER=", modified_cmd))
    already_has_systemd_pager = bool(re.search(r"--no-pager|\bSYSTEMD_PAGER=|\bPAGER=", modified_cmd))
    if any(b in ("git", "gh") for b in cmd_bins) and not already_has_pager:
        if is_compound or first_token not in ("git", "gh"):
            modified_cmd = f"export PAGER=cat; {modified_cmd}"
        else:
            modified_cmd = f"PAGER=cat {modified_cmd}"
        reasons.append("enforced non-interactive PAGER=cat")
    if any(b in ("systemctl", "journalctl", "udevadm") for b in cmd_bins) and not already_has_systemd_pager:
        if is_compound or first_token not in ("systemctl", "journalctl", "udevadm"):
            modified_cmd = f"export SYSTEMD_PAGER=cat; {modified_cmd}"
        else:
            modified_cmd = f"SYSTEMD_PAGER=cat {modified_cmd}"
        reasons.append("enforced non-interactive SYSTEMD_PAGER=cat")
    mod_ssh, ssh_injected = inject_ssh_timeouts(modified_cmd)
    if ssh_injected:
        modified_cmd = mod_ssh; reasons.append("injected non-blocking SSH timeout and batch mode guards")
    mod_remote, remote_injected, remote_reasons = sanitize_ssh_remote_payload(modified_cmd)
    if remote_injected:
        modified_cmd = mod_remote; reasons.extend(remote_reasons)
    if should_sanitize_grep_or_diff(modified_cmd):
        modified_cmd = f"{modified_cmd} || [ $? -eq 1 ]"
        reasons.append("sanitized pattern search against benign Exit Code 1")
    mod_path, path_injected = inject_path_shims(modified_cmd)
    if path_injected:
        modified_cmd = mod_path; reasons.append("injected user-space toolchain PATH shims")

    if is_python_command(modified_cmd):
        hermetic_bin = find_hermetic_uv_python_bin()
        if hermetic_bin:
            hb_esc = str(hermetic_bin).replace("\\", "\\\\").replace('"', '\\"').replace("$", "\\$").replace("`", "\\`")
            if hb_esc not in modified_cmd:
                if modified_cmd.startswith('export PATH="'):
                    modified_cmd = f'export PATH="{hb_esc}:' + modified_cmd[len('export PATH="'):]
                    reasons.append("injected hermetic CPython >= 3.12 for PEP 701 f-string safety")
                elif not _EXPLICIT_PATH_ASSIGN_RE.search(_QUOTED_STR_RE.sub("__Q__", modified_cmd)):
                    modified_cmd = f'export PATH="{hb_esc}:$PATH"; {modified_cmd}'
                    reasons.append("injected hermetic CPython >= 3.12 for PEP 701 f-string safety")

    if modified_cmd == original_cmd:
        return ("allow", None, None)
    hints = [r for r in reasons if r.startswith("[AGYIS COGNITIVE HINT]")]
    others = [r for r in reasons if not r.startswith("[AGYIS COGNITIVE HINT]")]
    out_parts = (["[AGYIS COMMAND SAFETY] " + "; ".join(others)] if others else []) + hints
    return ("allow", modified_cmd, "; ".join(out_parts) if out_parts else None)


check_command_safety = sanitize_command


def is_pause_gate_active(workspace_dir: Optional[Path] = None) -> bool:
    """Checks whether any Zero-Kill Swarm Parking pause gate is active (fails open on errors)."""
    base_dir = workspace_dir or Path.cwd()
    for rel_path in PAUSE_GATE_FILES:
        target = base_dir / rel_path
        if not target.is_file():
            continue
        try:
            if target.name.endswith(".json"):
                data = json.loads(target.read_text(encoding="utf-8"))
                if isinstance(data, dict) and str(data.get("status", "")).strip().lower() in ("paused", "pausing"):
                    return True
            elif target.name.endswith(".md"):
                if re.search(r"status:\s*[\"']?(?:paused|pausing)[\"']?", target.read_text(encoding="utf-8", errors="replace"), re.I):
                    return True
            else:
                return True
        except Exception as e:
            sys.stderr.write(f"[AGYIS COMMAND SAFETY] Warning: Error reading pause gate '{target}': {e}\n")
    return False


def check_pause_safety(tool_name: str, arguments: Dict[str, Any], workspace_dir: Optional[Path] = None) -> Tuple[str, Optional[str]]:
    """Enforces the Zero-Kill Swarm Parking Invariant while a pause gate is active."""
    try:
        if not is_pause_gate_active(workspace_dir):
            return ("allow", None)
        reason = (
            "[AGYIS COMMAND SAFETY] (Zero-Kill Swarm Parking Invariant): "
            "Subagent termination via 'kill' is prohibited while workspace is parked. "
            "Dispatch a graceful resume message or remove .agents/artifacts/pause_gate.json after state handoff."
        )
        norm = (tool_name or "").strip().lower()
        action = str(arguments.get("Action") or arguments.get("action") or "").strip().lower()
        cmd = str(arguments.get("CommandLine") or arguments.get("command") or "").strip()
        if (norm in ("manage_subagents", "swarm") and action in ("kill", "kill_all", "cancel")) or (norm == "manage_task" and action in ("kill", "cancel")) or (norm == "run_command" and PAUSE_KILL_SHELL_REGEX.search(cmd)):
            return ("deny", reason)
        return ("allow", None)
    except Exception as e:
        sys.stderr.write(f"[AGYIS COMMAND SAFETY] Warning: Unexpected error in check_pause_safety: {e}\n")
        return ("allow", None)


def sanitize_run_command_args(tool_args: Dict[str, Any], fallback_cmd: str = "") -> Tuple[Dict[str, Any], bool, List[str]]:
    """Converts foreign Cwd/command args and strips non-native keys for run_command (Issue #104)."""
    cleaned: Dict[str, Any] = {}
    reasons: List[str] = []
    modified = False
    cwd_val = tool_args.get("Cwd") or tool_args.get("cwd")
    base_cmd = str(tool_args.get("CommandLine") or tool_args.get("command") or tool_args.get("cmd") or fallback_cmd or "").strip()
    if cwd_val:
        modified = True
        cwd_str = str(cwd_val).strip()
        base_cmd = f'cd "{cwd_str}" && {base_cmd}' if base_cmd else f'cd "{cwd_str}"'
        reasons.append(f'prepended directory navigation: cd "{cwd_str}" &&')
    cleaned["CommandLine"] = base_cmd

    for key, value in tool_args.items():
        if key in ("Cwd", "cwd"):
            modified = True
        elif key in RUN_COMMAND_ALLOWED_KEYS:
            if key != "CommandLine":
                cleaned[key] = value
        elif key in ("command", "cmd"):
            modified = True; reasons.append(f"mapped foreign argument '{key}' -> 'CommandLine'")
        else:
            modified = True; reasons.append(f"stripped unrecognized foreign argument '{key}'")
    if "CommandLine" in tool_args and tool_args["CommandLine"] != base_cmd:
        modified = True
    return cleaned, modified, reasons


def main() -> None:
    """Hook CLI entrypoint reading toolCall JSON from stdin and emitting allow/deny/overwrite."""
    global _ACTIVE_CONVO_ID
    try:
        raw_stdin = sys.stdin.read()
        if not raw_stdin.strip():
            print(json.dumps({"decision": "allow"}))
            return
        payload = json.loads(raw_stdin)
    except Exception as exc:
        sys.stderr.write(f"[AGYIS COMMAND SAFETY] Warning: Error parsing stdin payload: {exc}\n")
        print(json.dumps({"decision": "allow"}))
        return

    if not isinstance(payload, dict):
        print(json.dumps({"decision": "allow"}))
        return

    tool_call = payload.get("toolCall") or {}
    tool_name = tool_call.get("name") or payload.get("tool_name") or "run_command"
    tool_args = tool_call.get("args") or payload.get("tool_args") or {}
    _ACTIVE_CONVO_ID = str(payload.get("conversation_id") or payload.get("conversationId") or "").strip() or None
    try:
        ws_list = payload.get("workspacePaths") or payload.get("workspace_paths") or []
        cands = ([ws_list[0]] if isinstance(ws_list, list) and ws_list else []) + [
            payload.get("workspace_dir"), tool_args.get("Cwd"), tool_args.get("cwd"), payload.get("cwd")
        ]
        ws_dir = next((Path(c.strip()) for c in cands if isinstance(c, str) and c.strip() and Path(c.strip()).is_dir()), None)

        args_modified, args_reasons, sanitized_args = False, [], {}
        if tool_name == "run_command":
            fallback = str(payload.get("command") or payload.get("CommandLine") or "").strip()
            sanitized_args, args_modified, args_reasons = sanitize_run_command_args(tool_args, fallback_cmd=fallback)
            raw_cmd = sanitized_args.get("CommandLine", "")
        else:
            raw_cmd = str(tool_args.get("CommandLine") or payload.get("command") or payload.get("CommandLine") or "").strip()

        if payload.get("check_preflight") or payload.get("action") == "check_preflight":
            print(json.dumps(check_preflight_tool_availability(raw_cmd)))
            return

        pause_dec, pause_reason = check_pause_safety(
            tool_name, sanitized_args if tool_name == "run_command" else (tool_args or {"CommandLine": raw_cmd}), workspace_dir=ws_dir
        )
        if pause_dec == "deny":
            print(json.dumps({"decision": "deny", "reason": pause_reason}))
            return
        if tool_name in ("manage_subagents", "manage_task", "swarm", "run_workflow"):
            print(json.dumps({"decision": "allow"}))
            return
        if tool_name == "call_mcp_tool" or tool_name.startswith("mcp_"):
            m_dec, m_ow, m_rsn = normalize_mcp_tool_call(tool_name, tool_args)
            print(json.dumps({"decision": m_dec, **({"overwrite": m_ow} if m_ow is not None else {}), **({"reason": m_rsn} if m_rsn else {})}))
            return
        if str(tool_name).strip().lower() in WRITE_CLOBBER_TOOLS:
            clobber = check_anti_clobber(payload, workspace_dir=ws_dir)
            print(json.dumps(clobber or {"decision": "allow"}))
            return

        decision, mod_cmd, reason = sanitize_command(raw_cmd, workspace_dir=ws_dir)
        if decision == "deny":
            print(json.dumps({"decision": "deny", "reason": reason}))
            return

        effective_cmd = mod_cmd if mod_cmd is not None else raw_cmd
        sem_dec, sem_cmd, sem_rsn = evaluate_resource_semaphore(effective_cmd, workspace_dir=ws_dir)
        if sem_dec == "deny":
            print(json.dumps({"decision": "deny", "reason": sem_rsn}))
            return
        if sem_cmd is not None:
            effective_cmd, mod_cmd = sem_cmd, sem_cmd
            reason = "; ".join(p for p in (reason, sem_rsn) if p)
        all_reasons = list(args_reasons) + ([reason] if reason else [])
        if tool_name == "run_command" and (args_modified or mod_cmd is not None):
            print(json.dumps({"decision": "allow", "overwrite": {**sanitized_args, "CommandLine": effective_cmd}, **({"reason": "; ".join(all_reasons)} if all_reasons else {})}))
        elif mod_cmd is not None:
            print(json.dumps({"decision": "allow", "overwrite": {"CommandLine": mod_cmd}, **({"reason": reason} if reason else {})}))
        else:
            print(json.dumps({"decision": "allow"}))
    finally:
        _ACTIVE_CONVO_ID = None


if __name__ == "__main__":
    main()
