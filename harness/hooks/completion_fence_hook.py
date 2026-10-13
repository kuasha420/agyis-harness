#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Arafat Zahan (@kuasha420)
# Corporate Stewardship & Infrastructure: Purrfect Software Limited (PSL)
# Governed by: ICARO-42/b Ordinance (Company-Supported Personal IP Framework)

"""
PSL Harness: Deterministic Stop-Hook Verification Fence (ADR-022)

Intercepts agent completion (`Stop` event) to ensure that code modifications
have been verified by running tests before allowing the agent to exit.
Intercepts file modifications in `PreToolUse` to mark session state dirty.
Features an anti-deadlock safety valve tripping after 2 blocks.
"""

from __future__ import annotations

from datetime import datetime, timezone
import json
import os
from pathlib import Path
import re
import sys

from harness.utils.state import get_state_dir



def get_state_file(conv_id: str = "default", state_dir: Path | None = None) -> Path:
    """Returns the state file path for a specific conversation."""
    target_dir = state_dir or get_state_dir()
    return target_dir / f"verification_state_{conv_id}.json"


# Non-code files that do not trigger code dirty state
EXEMPT_FILENAMES: frozenset[str] = frozenset({
    ".gitignore",
    ".gitattributes",
    ".editorconfig",
    "package-lock.json",
    "uv.lock",
    "poetry.lock",
    "cargo.lock",
    "yarn.lock",
    "pnpm-lock.yaml",
    ".pnpm-lock.yaml",
})

EXEMPT_EXTENSIONS: frozenset[str] = frozenset({
    ".md",
    ".markdown",
    ".txt",
    ".rst",
    ".adoc",
    ".png",
    ".jpg",
    ".jpeg",
    ".gif",
    ".svg",
    ".ico",
    ".webp",
    ".bmp",
    ".tiff",
    ".lock",
})

CODE_EXTENSIONS: frozenset[str] = frozenset({
    ".py",
    ".pyi",
    ".ts",
    ".tsx",
    ".js",
    ".jsx",
    ".mjs",
    ".cjs",
    ".rs",
    ".go",
    ".c",
    ".cpp",
    ".cc",
    ".cxx",
    ".h",
    ".hpp",
    ".java",
    ".kt",
    ".kts",
    ".scala",
    ".rb",
    ".php",
    ".sh",
    ".bash",
    ".zsh",
    ".swift",
    ".cs",
    ".sql",
    ".html",
    ".css",
    ".scss",
    ".sass",
    ".less",
    ".vue",
    ".svelte",
})


def is_code_file(path_str: str) -> bool:
    """
    Determines if a file path represents code that requires verification.
    Exempts documentation, asset/image files, lockfiles, and git configs.
    """
    p = Path(path_str)
    name = p.name.lower()
    suffix = p.suffix.lower()

    if name in EXEMPT_FILENAMES:
        return False
    if suffix in EXEMPT_EXTENSIONS or name.endswith(".lock"):
        return False
    return suffix in CODE_EXTENSIONS


def load_state(conv_id: str = "default", state_dir: Path | None = None) -> dict:
    """Loads state for conversation or returns clean baseline."""
    state_file = get_state_file(conv_id, state_dir)
    default_state = {
        "conversation_id": conv_id,
        "code_dirty": False,
        "last_modified_files": [],
        "block_count": 0,
        "last_verified_at": None,
    }
    if state_file.exists():
        try:
            content = state_file.read_text(encoding="utf-8")
            data = json.loads(content)
            if isinstance(data, dict):
                return {
                    "conversation_id": str(data.get("conversation_id", conv_id)),
                    "code_dirty": bool(data.get("code_dirty", False)),
                    "last_modified_files": list(data.get("last_modified_files", [])),
                    "block_count": int(data.get("block_count", 0)),
                    "last_verified_at": data.get("last_verified_at"),
                }
        except (json.JSONDecodeError, OSError, ValueError):
            return default_state
    return default_state


def save_state(state: dict, conv_id: str = "default", state_dir: Path | None = None) -> None:
    """Saves state atomically to disk."""
    target_dir = state_dir or get_state_dir()
    target_dir.mkdir(parents=True, exist_ok=True)
    state_file = get_state_file(conv_id, target_dir)
    tmp_file = target_dir / f".tmp_verification_state_{conv_id}_{os.getpid()}.json"
    try:
        tmp_file.write_text(json.dumps(state, indent=2), encoding="utf-8")
        tmp_file.replace(state_file)
    except OSError:
        state_file.write_text(json.dumps(state, indent=2), encoding="utf-8")


def record_edit(
    file_path: str,
    conv_id: str = "default",
    state_dir: Path | None = None,
) -> dict:
    """
    Records a file edit. If the file is a code file, marks code_dirty = True,
    resets block_count = 0 (re-arming the fence), and appends the path to last_modified_files.
    """
    state = load_state(conv_id=conv_id, state_dir=state_dir)
    if is_code_file(file_path):
        state["code_dirty"] = True
        state["block_count"] = 0
        modified = state.get("last_modified_files", [])
        if file_path not in modified:
            modified.append(file_path)
        state["last_modified_files"] = modified
        save_state(state, conv_id=conv_id, state_dir=state_dir)
    return state


def record_verification(
    success: bool = True,
    conv_id: str = "default",
    state_dir: Path | None = None,
) -> dict:
    """
    Records test verification results. If successful, clears code_dirty, resets
    last_modified_files and block_count, and sets last_verified_at.
    """
    state = load_state(conv_id=conv_id, state_dir=state_dir)
    if success:
        state["code_dirty"] = False
        state["last_modified_files"] = []
        state["block_count"] = 0
        state["last_verified_at"] = datetime.now(timezone.utc).isoformat()
        save_state(state, conv_id=conv_id, state_dir=state_dir)
    return state


def reset_state(
    conv_id: str = "default",
    state_dir: Path | None = None,
) -> dict:
    """Resets the verification state to clean baseline."""
    state = {
        "conversation_id": conv_id,
        "code_dirty": False,
        "last_modified_files": [],
        "block_count": 0,
        "last_verified_at": None,
    }
    save_state(state, conv_id=conv_id, state_dir=state_dir)
    return state


def evaluate_stop(
    conv_id: str = "default",
    state_dir: Path | None = None,
) -> dict:
    """
    Evaluates whether an agent may stop.
    If code is dirty and block_count < 2, blocks stop and requests test execution.
    If block_count >= 2, trips the anti-deadlock safety valve and allows exit.
    """
    state = load_state(conv_id=conv_id, state_dir=state_dir)
    if not state.get("code_dirty", False):
        return {"decision": "allow"}

    block_count = state.get("block_count", 0)
    if block_count < 2:
        state["block_count"] = block_count + 1
        save_state(state, conv_id=conv_id, state_dir=state_dir)
        modified_files = state.get("last_modified_files", [])
        files_str = ", ".join(modified_files) if modified_files else "untracked code files"
        return {
            "decision": "continue",
            "reason": (
                f"Verification Required: Unverified code edits detected in: {files_str}. "
                "Execute 'agyis test' (or 'python3 -m harness.cli test') or your project test suite before stopping."
            ),
        }
    else:
        return {
            "decision": "allow",
            "warning": "Anti-deadlock valve tripped after 2 verification blocks. Exiting despite unverified edits.",
        }


UNIVERSAL_TEST_RUNNER_PATTERNS: tuple[re.Pattern, ...] = (
    re.compile(r"(?:^|[;&|]\s*|\b(?:sudo|nohup|exec|env|time)\s+)\s*(?:pytest(?:\s|$)|python3?\s+-m\s+(?:unittest|pytest|harness(?:\.cli)?\s+test)\b)"),
    re.compile(r"(?:^|[;&|]\s*|\b(?:sudo|nohup|exec|env|time)\s+)\s*(?:(?:pnpm|npm|yarn|bun)\s+(?:run\s+)?test\b|\bvitest\b|\bjest\b|\bturbo\s+run\s+test\b)"),
    re.compile(r"(?:^|[;&|]\s*|\b(?:sudo|nohup|exec|env|time)\s+)\s*cargo\s+test\b"),
    re.compile(r"(?:^|[;&|]\s*|\b(?:sudo|nohup|exec|env|time)\s+)\s*go\s+test\b"),
    re.compile(r"(?:^|[;&|]\s*|\b(?:sudo|nohup|exec|env|time)\s+)\s*ctest\b"),
    re.compile(r"(?:^|[;&|]\s*|\b(?:sudo|nohup|exec|env|time)\s+)\s*(?:(?:agyis|\./agyis|psl|\./psl)\s+test\b)"),
)


def is_test_command(command: str) -> bool:
    """
    Checks whether a command line executes a recognized universal test runner
    across Python, Node/TypeScript, Rust, Go, or C/C++ ecosystems.
    """
    if not command or not command.strip():
        return False
    cmd_clean = command.strip()
    return any(pat.search(cmd_clean) is not None for pat in UNIVERSAL_TEST_RUNNER_PATTERNS)


def check_command_verification(
    command: str,
    exit_code: int = 0,
    conv_id: str = "default",
    state_dir: Path | None = None,
) -> bool:
    """
    Evaluates whether a command invocation represents test verification.
    If the command matches a recognized universal test runner:
      - If exit_code == 0: auto-clears code dirty state via record_verification(success=True).
      - If exit_code != 0: records record_verification(success=False).
    Returns True if the command was recognized as a test runner, False otherwise.
    """
    if not is_test_command(command):
        return False

    success = (exit_code == 0)
    record_verification(success=success, conv_id=conv_id, state_dir=state_dir)
    return True


def main() -> None:
    """CLI / hook entry point consuming protojson from stdin and writing to stdout."""
    try:
        raw_stdin = sys.stdin.read()
        if not raw_stdin.strip():
            result = evaluate_stop("default")
            print(json.dumps(result))
            return
        payload = json.loads(raw_stdin)
        if not isinstance(payload, dict):
            result = evaluate_stop("default")
            print(json.dumps(result))
            return
    except (json.JSONDecodeError, OSError):
        print(json.dumps({"decision": "allow"}))
        return

    conv_id = str(payload.get("conversationId") or payload.get("conversation_id") or "default")
    action = payload.get("action")

    if action == "record_edit":
        file_path = payload.get("file_path") or payload.get("path") or ""
        state = record_edit(file_path, conv_id=conv_id)
        print(json.dumps({"status": "ok", "state": state}))
    elif action == "record_verification":
        success = bool(payload.get("success", True))
        state = record_verification(success=success, conv_id=conv_id)
        print(json.dumps({"status": "ok", "state": state}))
    elif action == "check_command_verification":
        command = payload.get("command") or payload.get("CommandLine") or ""
        exit_code = int(payload.get("exit_code", payload.get("exitCode", 0)))
        matched = check_command_verification(command, exit_code=exit_code, conv_id=conv_id)
        state = load_state(conv_id=conv_id)
        print(json.dumps({"status": "ok", "matched": matched, "state": state}))
    elif action == "reset":
        state = reset_state(conv_id=conv_id)
        print(json.dumps({"status": "ok", "state": state}))
    elif action == "evaluate_stop":
        result = evaluate_stop(conv_id=conv_id)
        print(json.dumps(result))
    elif "toolCall" in payload:
        # PreToolUse / PostToolUse event: intercept file modifications and test runner commands
        tool_call = payload.get("toolCall") or {}
        tool_name = tool_call.get("name", "")
        tool_args = tool_call.get("args") or {}

        if tool_name in ("write_to_file", "replace_file_content", "edit_file"):
            target_file = (
                tool_args.get("TargetFile")
                or tool_args.get("FilePath")
                or tool_args.get("AbsolutePath")
                or tool_args.get("file_path", "")
            )
            if target_file:
                record_edit(target_file, conv_id=conv_id)
        elif tool_name in ("run_command", "execute_command", "bash"):
            cmd = tool_args.get("CommandLine") or tool_args.get("command") or ""
            raw_exit = payload.get("exitCode") if payload.get("exitCode") is not None else payload.get("exit_code")
            if raw_exit is not None and cmd:
                exit_code = int(raw_exit)
                check_command_verification(cmd, exit_code=exit_code, conv_id=conv_id)
        print(json.dumps({"decision": "allow"}))
    elif "command" in payload or "CommandLine" in payload:
        cmd = payload.get("command") or payload.get("CommandLine") or ""
        exit_code = int(payload.get("exitCode", payload.get("exit_code", 0)))
        matched = check_command_verification(cmd, exit_code=exit_code, conv_id=conv_id)
        state = load_state(conv_id=conv_id)
        print(json.dumps({"status": "ok", "matched": matched, "state": state, "decision": "allow"}))
    else:
        # Default behavior: Stop hook evaluation
        result = evaluate_stop(conv_id=conv_id)
        print(json.dumps(result))


if __name__ == "__main__":
    main()
