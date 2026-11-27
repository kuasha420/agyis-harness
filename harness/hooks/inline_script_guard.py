#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Arafat Zahan (@kuasha420)
# Corporate Stewardship & Infrastructure: Purrfect Software Limited (PSL)
# Governed by: ICARO-42/b Ordinance (Company-Supported Personal IP Framework)

"""
Agyis Harness: POSIX Shell Scanner & Inline Script Scratch Promotion Guard (#101).

Replaces fragile regex script extraction with a lightweight POSIX shell tokenizer
handling single-quoted spans (including `'\\''` splices), double-quoted escapes,
ANSI-C `$'...'` literals, multiline bodies, and embedded triple-quoted Python text.
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import os
from pathlib import Path
import re
import shlex
import sys
import tempfile
from typing import Any, Dict, List, Optional, Tuple

from harness.utils.context import get_active_brain_dir, get_active_conversation_id

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

_WRAPPERS: frozenset[str] = frozenset({"sudo", "xargs", "nohup", "exec", "env", "time", "command"})
_WRAPPER_ARG_FLAGS: Dict[str, frozenset[str]] = {
    "env": frozenset({"-u", "-C", "-S", "--unset", "--chdir"}),
    "sudo": frozenset({"-u", "-g", "-C", "-D", "-h", "-p", "-r", "-t", "-U", "-T", "-R"}),
    "xargs": frozenset({"-I", "-L", "-n", "-P", "-s", "-d", "-a", "-E", "-J"}),
}
_INTERP_ARG_FLAGS: Dict[str, frozenset[str]] = {
    "python": frozenset({"-W", "-X", "-m", "--check-hash-based-pycs"}),
    "node": frozenset({"-r", "--require", "--loader", "--import", "--env-file", "-e", "--eval", "-p", "--print"}),
    "bash": frozenset({"-o", "+o"}),
    "sh": frozenset({"-o", "+o"}),
}
_PYTHON_BIN_RE = re.compile(r"^python3?(?:\.\d+)?$")
_ENV_ASSIGN_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*=")
_ANSI_SIMPLE_ESCAPES: Dict[str, str] = {
    "a": chr(7), "b": "\b", "e": "\x1b", "E": "\x1b", "f": "\f",
    "n": "\n", "r": "\r", "t": "\t", "v": "\v", "\\": "\\",
    "'": "'", '"': '"', "?": "?",
}
_CMD_SEPARATORS: frozenset[str] = frozenset({";", ";;", "&", "&&", "|", "||", "\n", "(", ")"})


@dataclass(frozen=True)
class _ShellWord:
    raw: str
    value: str
    start: int
    end: int
    is_operator: bool = False
    had_unquoted_eq: bool = False
    is_quoted: bool = False


@dataclass(frozen=True)
class _InlineMatch:
    start: int
    end: int
    exec_bin: str
    interp: str
    flag: str
    ext: str
    body: str
    raw_payload: str


def _decode_ansi_c_escape(cmd: str, idx: int) -> Tuple[str, int]:
    """Decodes one backslash escape starting right after '\\' inside `$'...'`."""
    n = len(cmd)
    if idx >= n:
        return "\\", idx
    ch = cmd[idx]
    if ch in _ANSI_SIMPLE_ESCAPES:
        return _ANSI_SIMPLE_ESCAPES[ch], idx + 1
    if ch == "x":
        m = re.match(r"[0-9A-Fa-f]{1,2}", cmd[idx + 1 : idx + 3])
        if m:
            return chr(int(m.group(0), 16)), idx + 1 + len(m.group(0))
    elif ch == "u":
        m = re.match(r"[0-9A-Fa-f]{1,4}", cmd[idx + 1 : idx + 5])
        if m:
            return chr(int(m.group(0), 16)), idx + 1 + len(m.group(0))
    elif ch == "U":
        m = re.match(r"[0-9A-Fa-f]{1,8}", cmd[idx + 1 : idx + 9])
        if m:
            code = int(m.group(0), 16)
            return (chr(code) if code <= 0x10FFFF else "\\U" + m.group(0)), idx + 1 + len(m.group(0))
    elif ch in "01234567":
        m = re.match(r"[0-7]{1,3}", cmd[idx : idx + 3])
        if m:
            return chr(int(m.group(0), 8) & 0xFF), idx + len(m.group(0))
    elif ch == "c" and idx + 1 < n:
        ctrl = cmd[idx + 1]
        return ("\x7f" if ctrl == "?" else chr(ord(ctrl.upper()) & 0x1F)), idx + 2
    return "\\" + ch, idx + 1


def _scan_double_quoted(cmd: str, start: int) -> Tuple[str, int, bool]:
    """Scans POSIX double-quoted segment starting at `start` (the opening quote)."""
    parts: List[str] = []
    j, n = start + 1, len(cmd)
    while j < n:
        ch = cmd[j]
        if ch == "\\" and j + 1 < n:
            nxt = cmd[j + 1]
            if nxt in ('"', "\\", "$", "`"):
                parts.append(nxt)
            elif nxt != "\n":
                parts.append("\\" + nxt)
            j += 2
            continue
        if ch == '"':
            return "".join(parts), j + 1, True
        parts.append(ch)
        j += 1
    return "".join(parts), n, False


def _scan_ansi_c_quoted(cmd: str, start: int) -> Tuple[str, int, bool]:
    """Scans ANSI-C `$'...'` segment starting at `start` (index of `$`)."""
    parts: List[str] = []
    j, n = start + 2, len(cmd)
    while j < n:
        ch = cmd[j]
        if ch == "\\":
            decoded, j = _decode_ansi_c_escape(cmd, j + 1)
            parts.append(decoded)
            continue
        if ch == "'":
            return "".join(parts), j + 1, True
        parts.append(ch)
        j += 1
    return "".join(parts), n, False


def _tokenize_posix_shell(cmd: str) -> Tuple[List[_ShellWord], bool, bool]:
    """Tokenizes POSIX shell command into words/operators with exact source spans."""
    tokens: List[_ShellWord] = []
    has_heredoc = False
    unclosed = False
    i, n = 0, len(cmd)

    while i < n:
        c = cmd[i]
        if c in (" ", "\t", "\r"):
            i += 1
            continue
        if c == "\n":
            tokens.append(_ShellWord("\n", "\n", i, i + 1, is_operator=True))
            i += 1
            continue
        if c == "#":
            nl = cmd.find("\n", i)
            i = nl if nl != -1 else n
            continue
        if c in ";|&()<>":
            if cmd.startswith("<<<", i):
                op = "<<<"
            elif cmd[i : i + 3] == "<<-":
                op = "<<-"
                if re.match(r"\s*['\"]?[A-Za-z_][A-Za-z0-9_]*", cmd[i + 3 :]):
                    has_heredoc = True
            elif cmd[i : i + 2] == "<<":
                op = "<<"
                if re.match(r"\s*['\"]?[A-Za-z_][A-Za-z0-9_]*", cmd[i + 2 :]):
                    has_heredoc = True
            elif cmd[i : i + 2] in ("&&", "||", ";;", ">>", "<&", ">&"):
                op = cmd[i : i + 2]
            else:
                op = c
            tokens.append(_ShellWord(op, op, i, i + len(op), is_operator=True))
            i += len(op)
            continue

        word_start = i
        parts: List[str] = []
        had_unquoted_eq = False
        is_quoted = False
        while i < n:
            ch = cmd[i]
            if ch in (" ", "\t", "\r", "\n", ";", "|", "&", "(", ")", "<", ">"):
                break
            if ch == "'":
                is_quoted = True
                close_idx = cmd.find("'", i + 1)
                if close_idx == -1:
                    unclosed = True
                    parts.append(cmd[i + 1 :])
                    i = n
                    break
                parts.append(cmd[i + 1 : close_idx])
                i = close_idx + 1
            elif ch == "$" and i + 1 < n and cmd[i + 1] == "'":
                is_quoted = True
                seg, i, ok = _scan_ansi_c_quoted(cmd, i)
                parts.append(seg)
                if not ok:
                    unclosed = True
                    break
            elif ch == '"' or (ch == "$" and i + 1 < n and cmd[i + 1] == '"'):
                is_quoted = True
                q_idx = i + 1 if ch == "$" else i
                seg, i, ok = _scan_double_quoted(cmd, q_idx)
                parts.append(seg)
                if not ok:
                    unclosed = True
                    break
            elif ch == "\\":
                if i + 1 < n:
                    if cmd[i + 1] != "\n":
                        parts.append(cmd[i + 1])
                    i += 2
                else:
                    parts.append("\\")
                    i += 1
            else:
                if ch == "=" and not is_quoted:
                    had_unquoted_eq = True
                parts.append(ch)
                i += 1

        tokens.append(
            _ShellWord(
                raw=cmd[word_start:i],
                value="".join(parts),
                start=word_start,
                end=i,
                is_operator=False,
                had_unquoted_eq=had_unquoted_eq,
                is_quoted=is_quoted,
            )
        )
    return tokens, has_heredoc, unclosed


def _extract_inline_invocations(tokens: List[_ShellWord]) -> List[_InlineMatch]:
    """Extracts interpreter inline `-c`/`-e` spans from tokenized simple commands."""
    commands: List[List[_ShellWord]] = []
    cur: List[_ShellWord] = []
    for tok in tokens:
        if tok.is_operator:
            if tok.value in _CMD_SEPARATORS:
                if cur:
                    commands.append(cur)
                    cur = []
            continue
        cur.append(tok)
    if cur:
        commands.append(cur)

    matches: List[_InlineMatch] = []
    for seg in commands:
        idx = 0
        while idx < len(seg):
            tok = seg[idx]
            if tok.had_unquoted_eq and _ENV_ASSIGN_RE.match(tok.raw):
                idx += 1
                continue
            base = tok.value.rsplit("/", 1)[-1]
            if base in _WRAPPERS:
                arg_flags = _WRAPPER_ARG_FLAGS.get(base, frozenset())
                idx += 1
                while idx < len(seg):
                    wt = seg[idx]
                    if wt.value.startswith("-") and wt.value != "-":
                        idx += 2 if wt.value in arg_flags else 1
                    elif base == "env" and wt.had_unquoted_eq and _ENV_ASSIGN_RE.match(wt.raw):
                        idx += 1
                    else:
                        break
                continue
            break

        if idx >= len(seg):
            continue
        interp_tok = seg[idx]
        if interp_tok.value == "{" and idx + 1 < len(seg):
            idx += 1
            interp_tok = seg[idx]
        base = interp_tok.value.rsplit("/", 1)[-1]
        if _PYTHON_BIN_RE.match(base):
            interp, flag, ext = "python", "-c", ".py"
        elif base == "node":
            interp, flag, ext = "node", "-e", ".js"
        elif base in ("bash", "sh"):
            interp, flag, ext = base, "-c", ".sh"
        else:
            continue

        j = idx + 1
        arg_flags = _INTERP_ARG_FLAGS.get(interp, frozenset())
        while j < len(seg):
            t = seg[j]
            if t.value == flag or (interp in ("bash", "sh") and re.fullmatch(r"-[A-Za-z]+c", t.value)):
                if j + 1 < len(seg):
                    pt = seg[j + 1]
                    matches.append(_InlineMatch(interp_tok.start, pt.end, interp_tok.raw, interp, flag, ext, pt.value, pt.raw))
                break
            if interp == "node" and t.value == "--eval":
                if j + 1 < len(seg):
                    pt = seg[j + 1]
                    matches.append(_InlineMatch(interp_tok.start, pt.end, interp_tok.raw, interp, flag, ext, pt.value, pt.raw))
                break
            if t.raw.startswith(flag) and len(t.raw) > 2 and t.raw[2] in ("'", '"', "$", "\\"):
                matches.append(_InlineMatch(interp_tok.start, t.end, interp_tok.raw, interp, flag, ext, t.value[2:], t.raw[2:]))
                break
            if t.value == "-m" and interp == "python":
                break
            if t.value in arg_flags:
                j += 2
                continue
            if (t.value.startswith("-") or t.value.startswith("+")) and len(t.value) > 1:
                j += 1
                continue
            break
    return matches


def _strip_inner_quotes(text: str) -> str:
    """Strips single/double/triple quoted strings inside a script body before checking unquoted escapes."""
    return re.sub(
        r"'''[\s\S]*?'''|\"\"\"[\s\S]*?\"\"\"|'(?:\\.|[^'])*'|\"(?:\\.|[^\"])*\"",
        "",
        text,
    )


def _unescape_outer_newlines(body: str) -> str:
    """Converts literal \\n/\\r outside Python/JS string quotes into real newlines when no real newline exists."""
    out: List[str] = []
    in_sq = in_dq = False
    i, n = 0, len(body)
    while i < n:
        ch = body[i]
        if (in_sq or in_dq) and ch == "\\" and i + 1 < n:
            out.append(ch + body[i + 1])
            i += 2
            continue
        if ch == "'" and not in_dq:
            in_sq = not in_sq
            out.append(ch)
            i += 1
            continue
        if ch == '"' and not in_sq:
            in_dq = not in_dq
            out.append(ch)
            i += 1
            continue
        if not in_sq and not in_dq and ch == "\\" and i + 1 < n and body[i + 1] in ("n", "r"):
            out.append("\n" if body[i + 1] == "n" else "\r")
            i += 2
            continue
        out.append(ch)
        i += 1
    return "".join(out)


def _is_promotable_body(interp: str, body: str) -> bool:
    """Evaluates whether an extracted inline script body exceeds complexity/newline thresholds."""
    stripped = body.strip()
    has_real_nl = "\n" in body or "\r" in body
    if interp in ("bash", "sh"):
        if not has_real_nl and len(stripped) <= 250:
            return False
        if has_real_nl and len(stripped) <= 250:
            lines = [ln.strip() for ln in body.splitlines() if ln.strip()]
            if (
                len(lines) >= 2
                and all(ln.endswith(("\\", "|", "&&", "||")) for ln in lines[:-1])
                and not re.search(r"\b(?:for|while|if|case|function)\b", stripped)
            ):
                return False
        return True
    if not has_real_nl and len(stripped) <= 250:
        return r"\n" in body and r"\n" in _strip_inner_quotes(body)
    return True


def _find_promotable_inline_matches(cmd: str) -> List[_InlineMatch]:
    """Returns genuine complex/multi-line inline script matches requiring scratch promotion."""
    if not cmd or not cmd.strip() or os.environ.get("PSL_ALLOW_INLINE_SCRIPTS") == "1":
        return []
    cmd_lower = cmd.lower()
    if "# agyis: allow-inline-script" in cmd_lower or "# allow-inline" in cmd_lower:
        return []
    tokens, has_heredoc, unclosed = _tokenize_posix_shell(cmd)
    if has_heredoc or unclosed:
        return []
    return [m for m in _extract_inline_invocations(tokens) if _is_promotable_body(m.interp, m.body)]


def extract_command_binary(cmd: str) -> Optional[str]:
    """Extracts the root executable binary name, skipping env assignments and wrappers."""
    stripped = cmd.strip()
    if not stripped:
        return None
    tokens = re.split(r"[;&|]", stripped)[0].strip().split()
    idx = 0
    while idx < len(tokens):
        tok = tokens[idx]
        if "=" in tok and not tok.startswith("-"):
            idx += 1
        elif tok in _WRAPPERS:
            idx += 1
            while idx < len(tokens) and tokens[idx].startswith("-"):
                idx += 1
        else:
            return tok.split("/")[-1]
    return None


def is_inline_python_command(cmd: str) -> bool:
    """Detects inline python -c / python3 -c invocations."""
    return bool(re.search(r"\b(?:python3?)\s+-c\b", cmd))


def is_python_command(cmd: str) -> bool:
    """Detects python / python3 invocations (inline -c, -m module, or script execution)."""
    if re.search(r"\bpython3?(?:\.\d+)?\b", cmd):
        return True
    bin_name = extract_command_binary(cmd)
    return bool(bin_name and bin_name.endswith(".py"))


def resolve_scratch_target_path(ext: str, script_hash: str, workspace_dir: Optional[Path] = None) -> Tuple[Path, str]:
    """Resolves verified absolute scratch path (workspacePaths/cwd -> brain scratch -> tempdir)."""
    csh = sys.modules.get("harness.hooks.command_safety_hook")
    active_cid = getattr(csh, "_ACTIVE_CONVO_ID", None) if csh is not None else None
    get_cid_fn = getattr(csh, "get_active_conversation_id", get_active_conversation_id) if csh is not None else get_active_conversation_id
    get_brain_fn = getattr(csh, "get_active_brain_dir", get_active_brain_dir) if csh is not None else get_active_brain_dir

    cid = active_cid or os.environ.get("AGYIS_CONVERSATION_ID") or get_cid_fn() or "default"
    candidates: List[Path] = []
    base = workspace_dir or Path.cwd()
    if "/.gemini/config/plugins/" not in str(base) and "/site-packages/" not in str(base):
        candidates.append(base / "scratch" if (base / "scratch").is_dir() else base / ".agents" / "scratch")
    try:
        candidates.append(get_brain_fn() / cid / "scratch")
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
    csh = sys.modules.get("harness.hooks.command_safety_hook")
    resolver_fn = getattr(csh, "resolve_scratch_target_path", resolve_scratch_target_path) if csh is not None else resolve_scratch_target_path
    try:
        modified_cmd, promoted_paths = cmd, []
        for item in sorted(matches, key=lambda m: m.start, reverse=True):
            script_body = item.body
            if "\n" not in script_body and r"\n" in script_body:
                script_body = _unescape_outer_newlines(script_body)
            script_hash = hashlib.sha256(script_body.encode("utf-8")).hexdigest()[:8]
            target_file, exec_path = resolver_fn(item.ext, script_hash, workspace_dir)
            header = "//" if item.ext == ".js" else "#"
            target_file.write_text(f"{header} Transparently promoted by PSL command_safety_hook (PSL-INV-003)\n{script_body}\n", encoding="utf-8")
            if item.ext == ".sh":
                target_file.chmod(target_file.stat().st_mode | 0o755)
            promoted_paths.append(exec_path)
            modified_cmd = modified_cmd[: item.start] + f"{item.exec_bin} {exec_path}" + modified_cmd[item.end :]
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
