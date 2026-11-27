#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Arafat Zahan (@kuasha420)
# Corporate Stewardship & Infrastructure: Purrfect Software Limited (PSL)
# Governed by: ICARO-42/b Ordinance (Company-Supported Personal IP Framework)

"""
PSL Harness: PreToolUse Memory Guard & Cross-Worktree Concurrency Semaphore (Issue #67).

Prevents OOM kills and runaway parallel browser/build thrashing across git worktrees:
1. Classifies heavy verification/build commands (`playwright`, `puppeteer`, `cypress`,
   `vitest --browser`, `e2e`/`vrt` runners, `cargo build --all-targets`, `docker run`,
   `next build`) while explicitly bypassing fast unit-test runners (`unittest`, `pytest`,
   single-target `cargo test`, `agyis audit`/`doctor`/`status`).
2. Probes Linux `/proc/meminfo` (`MemAvailable`) with zero dependencies and fails open
   when `/proc/meminfo` is absent; denies heavy commands when free RAM falls below
   `system_thresholds.min_free_ram_mb` in `harness/runtime/matrix.json`.
3. Serializes heavy commands across all worktrees of a repository onto a single OS lock
   key under `get_state_dir()` via `flock -w` (with portable Python `fcntl.flock` CLI
   fallback) while leaving zero untracked files inside target repositories.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shlex
import shutil
import subprocess
import sys
import time
from typing import Any, Dict, List, Optional, Tuple

from harness.utils.state import get_state_dir

try:
    import fcntl as _fcntl
except ImportError:  # pragma: no cover - non-POSIX fallback
    _fcntl = None  # type: ignore[assignment]

DEFAULT_MIN_FREE_RAM_MB: int = 1536
DEFAULT_SEMAPHORE_WAIT_SECONDS: int = 300
DEFAULT_MEMINFO_PATH: Path = Path("/proc/meminfo")
MATRIX_JSON_PATH: Path = Path(__file__).resolve().parent.parent / "runtime" / "matrix.json"

_MEM_AVAILABLE_RE = re.compile(r"^MemAvailable:\s+(\d+)\s+kB\b", re.MULTILINE)
_QUOTED_LITERAL_RE = re.compile(r"'[^']*'|\"(?:\\.|[^\"])*\"")
_ENV_ASSIGN_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*=")
_COMMAND_WRAPPERS: frozenset[str] = frozenset({
    "sudo", "env", "time", "nohup", "exec", "command", "xargs", "xvfb-run", "timeout",
})
_NON_VERIFICATION_BINARIES: frozenset[str] = frozenset({
    "echo", "printf", "rg", "grep", "egrep", "fgrep", "awk", "sed",
    "cat", "head", "tail", "less", "more", "wc", "ls", "find", "fd",
    "true", "false", "cd", "export", "unset", "mkdir", "rm", "cp", "mv",
    "touch", "chmod", "chown", "ln", "pwd", "which", "type", "stat",
})
_RUNNER_CONTEXT_BINARIES: frozenset[str] = frozenset({
    "npm", "pnpm", "yarn", "bun", "npx", "pnpx", "make", "just", "turbo", "nx",
    "pytest", "vitest", "jest", "playwright", "cypress", "puppeteer", "mocha",
    "go", "cargo", "bash", "sh", "zsh", "task", "mise", "python", "python3", "uv",
})

_HEAVY_BROWSER_RE = re.compile(r"\b(?:playwright|puppeteer|cypress)\b", re.IGNORECASE)
_HEAVY_VITEST_BROWSER_RE = re.compile(r"\bvitest\b.*(?:^|\s)--browser(?:\b|=)", re.IGNORECASE)
_HEAVY_PYTEST_BROWSER_RE = re.compile(r"\bpytest\b.*(?:^|\s)--browser(?:\b|=)", re.IGNORECASE)
_HEAVY_E2E_VRT_RE = re.compile(r"\b(?:e2e|vrt)\b", re.IGNORECASE)
_HEAVY_CARGO_ALL_RE = re.compile(r"\bcargo\s+(?:build|test)\b.*(?:^|\s)--all-targets\b", re.IGNORECASE)
_HEAVY_CARGO_TEST_WORKSPACE_RE = re.compile(r"\bcargo\s+test\b.*(?:^|\s)--workspace\b", re.IGNORECASE)
_HEAVY_DOCKER_RUN_RE = re.compile(r"\bdocker\s+run\b", re.IGNORECASE)
_HEAVY_NEXT_BUILD_RE = re.compile(r"\bnext\s+build\b", re.IGNORECASE)
_INFO_ONLY_FLAG_RE = re.compile(r"(?:^|\s)(?:--help|-h|--version)(?:\s|$)")


def _load_system_thresholds(matrix_path: Optional[Path] = None) -> Dict[str, Any]:
    """Loads `system_thresholds` block from `harness/runtime/matrix.json`."""
    path = matrix_path or MATRIX_JSON_PATH
    if not path.is_file():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        thresholds = data.get("system_thresholds")
        return thresholds if isinstance(thresholds, dict) else {}
    except (OSError, json.JSONDecodeError, ValueError) as exc:
        sys.stderr.write(f"[PSL Memory Guard] Warning: Failed reading thresholds from '{path}': {exc}\n")
        return {}


def get_min_free_ram_mb(matrix_path: Optional[Path] = None) -> int:
    """Resolves minimum required MemAvailable (MB): env override -> matrix.json -> 1536."""
    env_val = os.environ.get("AGYIS_MIN_FREE_RAM_MB", "").strip()
    if env_val:
        try:
            parsed = int(env_val)
            if parsed > 0:
                return parsed
        except ValueError:
            pass
    thresholds = _load_system_thresholds(matrix_path=matrix_path)
    raw = thresholds.get("min_free_ram_mb")
    if isinstance(raw, int) and raw > 0:
        return raw
    return DEFAULT_MIN_FREE_RAM_MB


def get_semaphore_wait_seconds(matrix_path: Optional[Path] = None) -> int:
    """Resolves lock acquisition wait timeout (seconds): env override -> matrix.json -> 300."""
    env_val = os.environ.get("AGYIS_SEMAPHORE_WAIT_SECONDS", "").strip()
    if env_val:
        try:
            parsed = int(env_val)
            if parsed >= 0:
                return parsed
        except ValueError:
            pass
    thresholds = _load_system_thresholds(matrix_path=matrix_path)
    raw = thresholds.get("semaphore_wait_seconds")
    if isinstance(raw, int) and raw >= 0:
        return raw
    return DEFAULT_SEMAPHORE_WAIT_SECONDS


def _split_command_segments(cmd: str) -> List[str]:
    """Splits compound shell commands (`;`, `&&`, `||`, `|`, newlines) respecting quotes."""
    segments: List[str] = []
    cur: List[str] = []
    in_s = in_d = esc = False
    i, n = 0, len(cmd)
    while i < n:
        ch = cmd[i]
        if esc:
            cur.append(ch)
            esc = False
        elif ch == "\\" and not in_s:
            cur.append(ch)
            esc = True
        elif ch == "'" and not in_d:
            cur.append(ch)
            in_s = not in_s
        elif ch == '"' and not in_s:
            cur.append(ch)
            in_d = not in_d
        elif not in_s and not in_d and ch in (";", "\n"):
            seg = "".join(cur).strip()
            if seg:
                segments.append(seg)
            cur = []
        elif not in_s and not in_d and ch in ("&", "|"):
            if i + 1 < n and cmd[i + 1] == ch:
                i += 1
            seg = "".join(cur).strip()
            if seg:
                segments.append(seg)
            cur = []
        else:
            cur.append(ch)
        i += 1
    tail = "".join(cur).strip()
    if tail:
        segments.append(tail)
    return segments


def _extract_segment_binary_and_tokens(unquoted_segment: str) -> Tuple[Optional[str], List[str]]:
    """Extracts the effective binary basename and remaining tokens, skipping env/wrappers."""
    tokens = unquoted_segment.strip().split()
    idx = 0
    while idx < len(tokens):
        tok = tokens[idx]
        if _ENV_ASSIGN_RE.match(tok):
            idx += 1
        elif tok in _COMMAND_WRAPPERS:
            idx += 1
            while idx < len(tokens) and tokens[idx].startswith("-"):
                idx += 1
            if tok == "timeout" and idx < len(tokens) and re.match(r"^\d+[smhd]?$", tokens[idx]):
                idx += 1
        else:
            return (tok.split("/")[-1].lower(), tokens[idx:])
    return (None, [])


def _is_segment_heavy(segment: str) -> bool:
    """Evaluates a single command segment for heavy verification/build workloads."""
    unquoted = _QUOTED_LITERAL_RE.sub(" ", segment).strip()
    if not unquoted or _INFO_ONLY_FLAG_RE.search(unquoted):
        return False

    binary, rest = _extract_segment_binary_and_tokens(unquoted)
    if not binary:
        return False

    # Non-executing probes / print utilities and git commands are never heavy runners
    if binary in _NON_VERIFICATION_BINARIES or binary == "git":
        return False

    # Explicit lightweight unit-test & diagnostic CLI bypasses
    if binary in ("agyis", "psl") and len(rest) >= 2 and rest[1].lower() in ("audit", "doctor", "status"):
        return False
    if binary.startswith("python"):
        if re.search(r"(?:^|\s)-m\s+harness(?:\.cli)?\s+(?:audit|doctor|status)\b", unquoted):
            return False
        if re.search(r"(?:^|\s)-m\s+unittest\b", unquoted):
            return False
        if re.search(r"(?:^|\s)-m\s+pytest\b", unquoted):
            if not (
                _HEAVY_PYTEST_BROWSER_RE.search(unquoted)
                or _HEAVY_BROWSER_RE.search(unquoted)
                or _HEAVY_E2E_VRT_RE.search(unquoted)
            ):
                return False
    if binary == "pytest":
        if not (
            _HEAVY_PYTEST_BROWSER_RE.search(unquoted)
            or _HEAVY_BROWSER_RE.search(unquoted)
            or _HEAVY_E2E_VRT_RE.search(unquoted)
        ):
            return False
    if binary == "cargo" and len(rest) >= 2 and rest[1].lower() == "test":
        if not (
            _HEAVY_CARGO_ALL_RE.search(unquoted)
            or _HEAVY_CARGO_TEST_WORKSPACE_RE.search(unquoted)
            or _HEAVY_E2E_VRT_RE.search(unquoted)
        ):
            return False

    # Heavy verification / build classifiers
    if _HEAVY_BROWSER_RE.search(unquoted):
        return True
    if _HEAVY_VITEST_BROWSER_RE.search(unquoted) or _HEAVY_PYTEST_BROWSER_RE.search(unquoted):
        return True
    if _HEAVY_CARGO_ALL_RE.search(unquoted) or _HEAVY_CARGO_TEST_WORKSPACE_RE.search(unquoted):
        return True
    if _HEAVY_DOCKER_RUN_RE.search(unquoted):
        return True
    if _HEAVY_NEXT_BUILD_RE.search(unquoted):
        return True
    if _HEAVY_E2E_VRT_RE.search(unquoted):
        raw_first = rest[0] if rest else ""
        if binary in _RUNNER_CONTEXT_BINARIES or raw_first.startswith(("./", "../", "/")):
            return True

    return False


def is_heavy_verification_command(cmd: str) -> bool:
    """
    Returns True if `cmd` invokes a heavy browser/E2E/VRT/container/full-build workload
    that should be gated by `/proc/meminfo` and serialized by the cross-worktree semaphore.
    """
    if not cmd or not cmd.strip():
        return False
    return any(_is_segment_heavy(seg) for seg in _split_command_segments(cmd))


def get_available_ram_mb(meminfo_path: Optional[Path] = None) -> Optional[int]:
    """
    Reads `MemAvailable` from `/proc/meminfo` in megabytes.
    Fails open (returns `None`) on non-Linux hosts or unreadable/missing procfs.
    """
    target = meminfo_path if meminfo_path is not None else DEFAULT_MEMINFO_PATH
    if not target.is_file():
        return None
    try:
        raw = target.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None
    match = _MEM_AVAILABLE_RE.search(raw)
    if not match:
        return None
    try:
        return int(match.group(1)) // 1024
    except ValueError:
        return None


def check_memory_guard(
    cmd: str,
    workspace_dir: Optional[Path | str] = None,
    meminfo_path: Optional[Path] = None,
    min_free_ram_mb: Optional[int] = None,
) -> Optional[Dict[str, Any]]:
    """
    Denies heavy verification commands when Linux `MemAvailable` drops below the
    configured threshold. Fails open when `/proc/meminfo` is absent.
    """
    del workspace_dir  # Reserved for future per-workspace threshold overrides
    if not cmd or not is_heavy_verification_command(cmd):
        return None
    threshold = min_free_ram_mb if min_free_ram_mb is not None else get_min_free_ram_mb()
    avail_mb = get_available_ram_mb(meminfo_path=meminfo_path)
    if avail_mb is None:
        return None
    if avail_mb < threshold:
        return {
            "decision": "deny",
            "reason": (
                f"[PSL Memory Guard] Insufficient MemAvailable ({avail_mb} MB < {threshold} MB threshold) "
                "for heavy verification command. Close parallel browser/build workers or free RAM before retrying."
            ),
        }
    return None


def _resolve_git_common_scope(base: Path) -> Path:
    """Resolves canonical repository root shared across all `git worktree` checkouts."""
    git_bin = shutil.which("git")
    if not git_bin or not base.exists():
        return base
    try:
        proc = subprocess.run(
            [git_bin, "-C", str(base), "rev-parse", "--git-common-dir"],
            capture_output=True,
            text=True,
            timeout=2.0,
            check=False,
        )
        if proc.returncode == 0 and proc.stdout.strip():
            common_dir = Path(proc.stdout.strip())
            if not common_dir.is_absolute():
                common_dir = (base / common_dir).resolve()
            else:
                common_dir = common_dir.resolve()
            return common_dir.parent if common_dir.name == ".git" else common_dir
    except (OSError, subprocess.SubprocessError):
        pass
    return base


def resolve_semaphore_lock_path(
    workspace_dir: Optional[Path | str] = None,
    lock_path: Optional[Path | str] = None,
    state_dir: Optional[Path] = None,
) -> Path:
    """
    Resolves the cross-worktree lockfile path without creating untracked files inside repos.

    Priority:
    1. Explicit `lock_path` argument.
    2. `AGYIS_SEMAPHORE_LOCK_FILE` environment variable.
    3. `(state_dir or get_state_dir()) / f"concurrency_semaphore_{sha256[:12]}.lock"`
       keyed by `git rev-parse --git-common-dir` canonical repo scope (or workspace path).
    """
    if lock_path is not None:
        return Path(lock_path)
    env_lock = os.environ.get("AGYIS_SEMAPHORE_LOCK_FILE", "").strip()
    if env_lock:
        return Path(env_lock)

    base = Path(workspace_dir).resolve() if workspace_dir else Path.cwd().resolve()
    scope = _resolve_git_common_scope(base)
    scope_hash = hashlib.sha256(str(scope).encode("utf-8")).hexdigest()[:12]
    target_state_dir = state_dir or get_state_dir()
    return target_state_dir / f"concurrency_semaphore_{scope_hash}.lock"


def wrap_with_concurrency_semaphore(
    cmd: str,
    workspace_dir: Optional[Path | str] = None,
    lock_path: Optional[Path | str] = None,
    state_dir: Optional[Path] = None,
    wait_seconds: Optional[int] = None,
    flock_binary: Optional[str] = None,
) -> Tuple[str, bool]:
    """
    Wraps heavy verification commands with an exclusive cross-worktree OS lock held for
    the full child process lifetime. Idempotent when `AGYIS_SEMAPHORE_LOCKED=1` is active.
    """
    if not cmd or not cmd.strip():
        return (cmd, False)
    if (
        "AGYIS_SEMAPHORE_LOCKED=1" in cmd
        or os.environ.get("AGYIS_SEMAPHORE_LOCKED") == "1"
        or "harness.hooks.resource_semaphore" in cmd
    ):
        return (cmd, False)
    if not is_heavy_verification_command(cmd):
        return (cmd, False)

    resolved_lock = resolve_semaphore_lock_path(
        workspace_dir=workspace_dir, lock_path=lock_path, state_dir=state_dir,
    )
    try:
        resolved_lock.parent.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        sys.stderr.write(f"[PSL Concurrency Semaphore] Warning: Could not create lock dir '{resolved_lock.parent}': {exc}\n")

    wait_s = wait_seconds if wait_seconds is not None else get_semaphore_wait_seconds()
    flock_bin = flock_binary if flock_binary is not None else shutil.which("flock")
    q_dir = shlex.quote(str(resolved_lock.parent))
    q_lock = shlex.quote(str(resolved_lock))
    q_cmd = shlex.quote(cmd)

    if flock_bin:
        wrapped = f"mkdir -p {q_dir} && AGYIS_SEMAPHORE_LOCKED=1 flock -w {wait_s} {q_lock} bash -c {q_cmd}"
    else:
        q_py = shlex.quote(sys.executable)
        wrapped = (
            f"AGYIS_SEMAPHORE_LOCKED=1 {q_py} -m harness.hooks.resource_semaphore "
            f"--lock {q_lock} --wait {wait_s} --cmd {q_cmd}"
        )
    return (wrapped, True)


def evaluate_resource_semaphore(
    cmd: str,
    workspace_dir: Optional[Path | str] = None,
    meminfo_path: Optional[Path] = None,
    min_free_ram_mb: Optional[int] = None,
    lock_path: Optional[Path | str] = None,
    state_dir: Optional[Path] = None,
    wait_seconds: Optional[int] = None,
    flock_binary: Optional[str] = None,
) -> Tuple[str, Optional[str], Optional[str]]:
    """
    Unified PreToolUse helper combining `/proc/meminfo` guard and cross-worktree
    concurrency semaphore wrapping.

    Returns `(decision, modified_cmd, reason)`.
    """
    mem_deny = check_memory_guard(
        cmd, workspace_dir=workspace_dir, meminfo_path=meminfo_path, min_free_ram_mb=min_free_ram_mb,
    )
    if mem_deny is not None:
        return ("deny", None, mem_deny["reason"])

    wrapped, did_wrap = wrap_with_concurrency_semaphore(
        cmd,
        workspace_dir=workspace_dir,
        lock_path=lock_path,
        state_dir=state_dir,
        wait_seconds=wait_seconds,
        flock_binary=flock_binary,
    )
    if did_wrap:
        return (
            "allow",
            wrapped,
            "[PSL Concurrency Semaphore] Serialized heavy verification command via cross-worktree lock.",
        )
    return ("allow", None, None)


def run_locked_command(lock_path: Path, wait_seconds: int, cmd: str) -> int:
    """
    Portable lock runner holding an OS exclusive lock across child execution and
    forwarding the child process's exact exit code.
    """
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    deadline = time.monotonic() + max(0, wait_seconds)
    env = {**os.environ, "AGYIS_SEMAPHORE_LOCKED": "1"}
    shell_bin = shutil.which("bash")

    if _fcntl is not None:
        with open(lock_path, "a+", encoding="utf-8") as lock_file:
            acquired = False
            while True:
                try:
                    _fcntl.flock(lock_file.fileno(), _fcntl.LOCK_EX | _fcntl.LOCK_NB)
                    acquired = True
                    break
                except BlockingIOError:
                    if time.monotonic() >= deadline:
                        break
                    time.sleep(0.05)
            if not acquired:
                sys.stderr.write(
                    f"[PSL Concurrency Semaphore] Timed out after {wait_seconds}s waiting for lock '{lock_path}'.\n"
                )
                return 1
            try:
                proc = subprocess.run([shell_bin, "-c", cmd], env=env, check=False) if shell_bin else subprocess.run(cmd, shell=True, env=env, check=False)
                return int(proc.returncode)
            finally:
                _fcntl.flock(lock_file.fileno(), _fcntl.LOCK_UN)
    else:  # pragma: no cover - non-POSIX atomic lockfile fallback
        fd: Optional[int] = None
        while fd is None:
            try:
                fd = os.open(str(lock_path), os.O_CREAT | os.O_EXCL | os.O_RDWR)
            except FileExistsError:
                if time.monotonic() >= deadline:
                    sys.stderr.write(
                        f"[PSL Concurrency Semaphore] Timed out after {wait_seconds}s waiting for lock '{lock_path}'.\n"
                    )
                    return 1
                time.sleep(0.05)
        try:
            proc = subprocess.run(cmd, shell=True, env=env, check=False)
            return int(proc.returncode)
        finally:
            os.close(fd)
            try:
                lock_path.unlink()
            except OSError:
                pass


def main(argv: Optional[List[str]] = None) -> int:
    """CLI entrypoint for portable fallback concurrency lock runner."""
    parser = argparse.ArgumentParser(description="PSL Cross-Worktree Concurrency Semaphore Runner")
    parser.add_argument("--lock", required=True, help="Path to exclusive lock file")
    parser.add_argument("--wait", type=int, default=DEFAULT_SEMAPHORE_WAIT_SECONDS, help="Wait timeout in seconds")
    parser.add_argument("--cmd", required=True, help="Shell command to execute under lock")
    args = parser.parse_args(argv)
    return run_locked_command(Path(args.lock), args.wait, args.cmd)


__all__ = [
    "DEFAULT_MIN_FREE_RAM_MB",
    "DEFAULT_SEMAPHORE_WAIT_SECONDS",
    "MATRIX_JSON_PATH",
    "get_min_free_ram_mb",
    "get_semaphore_wait_seconds",
    "is_heavy_verification_command",
    "get_available_ram_mb",
    "check_memory_guard",
    "resolve_semaphore_lock_path",
    "wrap_with_concurrency_semaphore",
    "evaluate_resource_semaphore",
    "run_locked_command",
    "main",
]

if __name__ == "__main__":
    sys.exit(main())
