# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Arafat Zahan (@kuasha420)
# Corporate Stewardship & Infrastructure: Purrfect Software Limited (PSL)
# Governed by: ICARO-42/b Ordinance (Company-Supported Personal IP Framework)

"""Crash-safety backup registry, repo containment, canonical diff parser, and shell=False runner."""

from __future__ import annotations

import atexit
from dataclasses import dataclass
from pathlib import Path
import re
import shlex
import signal
import subprocess
import sys
import threading
import time
from typing import Any, Dict, Iterator, List, Optional, Set, Tuple

# Active file backups for crash safety: maps absolute Path -> original file text
MAX_ACTIVE_BACKUPS = 128
MAX_SIGNAL_HANDLERS = 32
ACTIVE_BACKUPS: Dict[Path, str] = {}
_SAFETY_HANDLERS_INSTALLED = False
_SAFETY_LOCK = threading.Lock()
_PREV_SIGNAL_HANDLERS: Dict[int, Any] = {}

MUTATABLE_EXTENSIONS: Set[str] = {".py", ".ts", ".tsx", ".js", ".jsx", ".rs", ".go"}
_SHELL_FORBIDDEN_TOKENS = frozenset({";", "|", "||", "&", ">", ">>", "<", "<<", "`"})
_MAX_BASELINE_CACHE = 64

PRAGMA_PATTERN = re.compile(r"(?:#|//)\s*(?:agyis:\s*no-mutant|no-mutant:)", re.IGNORECASE)
TYPE_ANNOTATION_ONLY = re.compile(
    r"^\s*[a-zA-Z_][a-zA-Z0-9_]*\s*:\s*[A-Za-z_][A-Za-z0-9_.\[\]\s,|]*\s*;?\s*(?:#.*|//.*)?$"
)
_JS_REQUIRE_RE = re.compile(r"^(?:(?:const|let|var)\s+[^=]+=\s*)?require\s*\(")
_DIFF_FILE_PAT = re.compile(r"^diff --git a/(.+?) b/(.+?)$")
_HUNK_PAT = re.compile(r"^@@ -\d+(?:,\d+)? \+(\d+)(?:,(\d+))? @@")


@dataclass
class MutationCandidate:
    """A target code line identified from a diff hunk."""
    file_path: str
    line_number: int
    content: str


def is_test_file(path_str: str) -> bool:
    """Checks whether a relative or absolute path represents a test file."""
    p = Path(path_str)
    if any(part in ("tests", "test", "__tests__") for part in p.parts):
        return True
    name = p.name
    return name.startswith("test_") or name.endswith(
        ("_test.py", ".test.ts", ".spec.ts", ".test.tsx", ".spec.tsx", ".test.js", ".spec.js")
    )


def has_no_mutant_pragma(line: str) -> bool:
    """Checks whether a line contains '# agyis: no-mutant' or '# no-mutant:'."""
    return bool(PRAGMA_PATTERN.search(line))


def is_arid_line(line: str) -> bool:
    """Checks whether a line is non-logic arid code (imports, types, comments, docstrings, logs)."""
    s = line.strip()
    if not s:
        return True
    if s.startswith(("#", "//", "/*", "*/", "* ")) or s == "*":
        return True
    if s.startswith('"""') or s.startswith("'''"):
        return True
    if s.startswith(("import ", "from ", "use ")) or _JS_REQUIRE_RE.match(s):
        return True
    if s.startswith(("type ", "interface ", "typedef ")) or TYPE_ANNOTATION_ONLY.match(s):
        return True
    if s.startswith(("print(", "console.log(", "console.error(", "console.warn(")):
        return True
    if re.match(r"^(?:logger|logging|log|console)\.(?:debug|info|warning|warn|error|critical|exception|log|trace)\b", s):
        return True
    return bool(re.match(r"^sys\.(?:stdout|stderr)\.write\(", s))


def register_backup(path: Path, original_content: str) -> None:
    """Thread-safely registers an original file backup prior to mutation."""
    with _SAFETY_LOCK:
        if path not in ACTIVE_BACKUPS and len(ACTIVE_BACKUPS) >= MAX_ACTIVE_BACKUPS:
            ACTIVE_BACKUPS.pop(next(iter(ACTIVE_BACKUPS)))
        ACTIVE_BACKUPS[path] = original_content


def clear_backup(path: Path) -> None:
    """Thread-safely removes an original file backup after restoration."""
    with _SAFETY_LOCK:
        ACTIVE_BACKUPS.pop(path, None)


def _restore_all_backups_unlocked() -> None:
    """Restores active backups without acquiring _SAFETY_LOCK (signal-handler safe)."""
    items = list(ACTIVE_BACKUPS.items())
    ACTIVE_BACKUPS.clear()
    for path, original_content in items:
        try:
            if not path.is_symlink() and path.exists():
                path.write_text(original_content, encoding="utf-8")
        except OSError as exc:
            try:
                sys.stderr.write(f"[!] Warning: Failed to restore backup for {path}: {exc}\n")
            except OSError:
                pass


def _restore_all_backups() -> None:
    """Restores all active in-memory backups to disk on normal shutdown."""
    with _SAFETY_LOCK:
        _restore_all_backups_unlocked()


def _sig_handler(signum: int, frame: Any) -> None:
    """Signal trap for SIGINT and SIGTERM: restores backups lock-free and chains prior handler."""
    _restore_all_backups_unlocked()
    prev = _PREV_SIGNAL_HANDLERS.get(signum)
    if callable(prev):
        prev(signum, frame)
        return
    if prev == signal.SIG_IGN:
        return
    sys.exit(128 + signum)


def _install_safety_handlers() -> None:
    """Installs atexit and signal traps for hermetic crash recovery while preserving prior handlers."""
    global _SAFETY_HANDLERS_INSTALLED
    with _SAFETY_LOCK:
        if _SAFETY_HANDLERS_INSTALLED:
            return
        atexit.register(_restore_all_backups)
        try:
            if threading.current_thread() is threading.main_thread():
                for sig in (signal.SIGINT, signal.SIGTERM):
                    if sig not in _PREV_SIGNAL_HANDLERS and len(_PREV_SIGNAL_HANDLERS) >= MAX_SIGNAL_HANDLERS:
                        _PREV_SIGNAL_HANDLERS.pop(next(iter(_PREV_SIGNAL_HANDLERS)))
                    _PREV_SIGNAL_HANDLERS[sig] = signal.getsignal(sig)
                    signal.signal(sig, _sig_handler)
        except (ValueError, AttributeError):
            pass
        _SAFETY_HANDLERS_INSTALLED = True


def resolve_repo_target(repo_root: Path, rel_or_abs: str | Path) -> Optional[Path]:
    """Resolves a target file strictly inside repo_root, rejecting symlinks and path traversal."""
    root_res = Path(repo_root).resolve()
    raw = Path(rel_or_abs)
    candidate = raw if raw.is_absolute() else (root_res / raw)
    if candidate.is_symlink():
        return None
    try:
        resolved = candidate.resolve()
    except OSError:
        return None
    if not resolved.is_relative_to(root_res) or not resolved.is_file():
        return None
    return resolved


def run_targeted_test_cmd(
    cmd: str,
    env: Dict[str, str],
    cwd: Path,
    timeout: float,
) -> subprocess.CompletedProcess[str]:
    """Executes a targeted test command with shell=False, supporting unquoted && chains safely."""
    lexer = shlex.shlex(cmd, posix=True, punctuation_chars=True)
    lexer.whitespace_split = True
    tokens = list(lexer)
    if not tokens:
        raise ValueError("Empty test command")

    segments: List[List[str]] = []
    curr: List[str] = []
    for tok in tokens:
        if tok == "&&":
            if not curr:
                raise ValueError(f"Malformed && chain in test command: {cmd}")
            segments.append(curr)
            curr = []
        elif tok in _SHELL_FORBIDDEN_TOKENS or "$(" in tok:
            raise ValueError(f"Unsupported shell metacharacter '{tok}' in command: {cmd}")
        else:
            curr.append(tok)
    if curr:
        segments.append(curr)

    deadline = time.monotonic() + timeout
    last_proc: Optional[subprocess.CompletedProcess[str]] = None
    for argv in segments:
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise subprocess.TimeoutExpired(cmd=argv, timeout=timeout)
        last_proc = subprocess.run(
            argv,
            shell=False,
            env=env,
            cwd=str(cwd),
            capture_output=True,
            text=True,
            timeout=remaining,
        )
        if last_proc.returncode != 0:
            return last_proc

    assert last_proc is not None
    return last_proc


def check_baseline_cached(
    cache: Dict[str, Tuple[bool, str]],
    clean_cmd: str,
    guarded_env: Dict[str, str],
    repo_root: Path,
    timeout_sec: float,
) -> Tuple[bool, str]:
    """Runs and caches (bounded to 64 entries) a pre-mutation baseline test verification."""
    if clean_cmd in cache:
        return cache[clean_cmd]
    try:
        base_proc = run_targeted_test_cmd(clean_cmd, guarded_env, repo_root, timeout=max(timeout_sec, 10.0))
        outcome = (
            (True, "")
            if base_proc.returncode == 0
            else (False, f"Baseline test failed (exit {base_proc.returncode}) before mutation: {clean_cmd}")
        )
    except (subprocess.TimeoutExpired, OSError, ValueError) as exc:
        outcome = (False, f"Baseline test error before mutation: {exc}")
    if len(cache) >= _MAX_BASELINE_CACHE:
        cache.pop(next(iter(cache)))
    cache[clean_cmd] = outcome
    return outcome


def _iter_diff_added_lines(diff_text: str) -> Iterator[Tuple[str, Optional[int], str]]:
    """Yields (file_path, line_number_or_None_for_file_header, content) across unified diffs."""
    current_file: Optional[str] = None
    current_line = 0
    in_hunk = False

    for raw_line in diff_text.splitlines():
        m_file = _DIFF_FILE_PAT.match(raw_line)
        if m_file:
            current_file = m_file.group(2)
            in_hunk = False
            yield (current_file, None, "")
            continue
        if raw_line.startswith("+++ "):
            path_part = raw_line[4:].strip()
            if path_part.startswith("b/"):
                path_part = path_part[2:]
            in_hunk = False
            if path_part and path_part != "/dev/null":
                current_file = path_part
                yield (current_file, None, "")
            else:
                current_file = None
            continue
        m_hunk = _HUNK_PAT.match(raw_line)
        if m_hunk:
            current_line = int(m_hunk.group(1))
            in_hunk = True
            continue
        if in_hunk and current_file:
            if raw_line.startswith("+") and not raw_line.startswith("+++"):
                yield (current_file, current_line, raw_line[1:])
                current_line += 1
            elif raw_line.startswith(" "):
                current_line += 1


def parse_diff_lines(diff_text: str) -> Dict[str, Set[int]]:
    """Parses unified diff text into {relative_file_path: {1-indexed added line numbers}}."""
    modified: Dict[str, Set[int]] = {}
    for file_path, line_no, _ in _iter_diff_added_lines(diff_text):
        bucket = modified.setdefault(file_path, set())
        if line_no is not None:
            bucket.add(line_no)
    return modified


def extract_diff_mutation_candidates(diff_text: str) -> List[MutationCandidate]:
    """Extracts candidate modified lines from a unified git diff, filtering arid/test/pragma lines."""
    candidates: List[MutationCandidate] = []
    for file_path, line_no, content in _iter_diff_added_lines(diff_text):
        if line_no is None:
            continue
        if Path(file_path).suffix not in MUTATABLE_EXTENSIONS or is_test_file(file_path):
            continue
        if not is_arid_line(content) and not has_no_mutant_pragma(content):
            candidates.append(MutationCandidate(file_path=file_path, line_number=line_no, content=content))
    return candidates
