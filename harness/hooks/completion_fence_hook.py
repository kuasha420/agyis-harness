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
import tempfile

from harness.utils.state import get_state_dir
from harness.utils.workspace import detect_project_test_runner, is_harness_workspace

__all__ = [
    "EXEMPT_EXTENSIONS",
    "EXEMPT_FILENAMES",
    "CODE_EXTENSIONS",
    "get_state_file",
    "is_code_file",
    "is_cleanroom_contract_file",
    "is_ephemeral_scratch_path",
    "is_test_command",
    "extract_exit_code",
    "load_state",
    "save_state",
    "record_edit",
    "record_verification",
    "reset_state",
    "evaluate_stop",
    "check_command_verification",
    "main",
]



def get_state_file(conv_id: str = "default", state_dir: Path | None = None) -> Path:
    """Returns the state file path for a specific conversation."""
    target_dir = state_dir or get_state_dir()
    safe_conv_id = re.sub(r"[^a-zA-Z0-9_\-]", "_", conv_id)
    return target_dir / f"verification_state_{safe_conv_id}.json"


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


def is_cleanroom_contract_file(path_str: str) -> bool:
    """
    Determines if a file path represents a cleanroom contract file
    (in docs/specs/** or .agents/ledger/**) that requires verification,
    overriding default .md and .json exemptions.
    """
    if not path_str or not isinstance(path_str, str):
        return False
    norm = path_str.replace("\\", "/").strip().lower()
    if norm.startswith("./"):
        norm = norm[2:]

    if norm.startswith("docs/specs/") or "/docs/specs/" in norm:
        return True
    if norm.startswith(".agents/ledger/") or "/.agents/ledger/" in norm:
        return True

    return False

def is_ephemeral_scratch_path(file_path: str, cwd: Path | str | None = None) -> bool:
    """
    Determines if a file path represents an ephemeral scratch file or is outside
    the target workspace root. Scratch files do not trigger code dirty state.

    Rules:
    1. Paths containing .gemini/antigravity/brain/ and /scratch/ return True.
    2. When cwd is provided: files outside cwd (not target_path.is_relative_to(workspace_root)) return True.
    3. When cwd is not provided: paths in system temp directories (/tmp/, /var/tmp/) return True.
    """
    if not file_path or not isinstance(file_path, str):
        return False

    norm = file_path.replace("\\", "/").strip()

    # Rule 1: Antigravity ephemeral scratch transcripts/scripts
    if ".gemini/antigravity/brain" in norm and "/scratch/" in norm:
        return True

    # Rule 2: When cwd is provided, check if path resolves outside cwd
    if cwd is not None:
        try:
            workspace_root = Path(cwd).resolve()
            p = Path(file_path)
            target_path = p.resolve() if p.is_absolute() else (workspace_root / p).resolve()
            if not target_path.is_relative_to(workspace_root):
                return True
        except (ValueError, OSError):
            pass
    else:
        # Rule 3: When cwd is not provided, paths in system temp directories return True
        if norm.startswith("/tmp/") or norm == "/tmp" or norm.startswith("/var/tmp/") or norm == "/var/tmp":
            return True
        try:
            p = Path(file_path)
            if p.is_absolute():
                resolved = p.resolve()
                for temp_base in (Path("/tmp"), Path("/var/tmp"), Path(tempfile.gettempdir())):
                    if resolved.is_relative_to(temp_base.resolve()):
                        return True
        except (ValueError, OSError):
            pass

    return False


def extract_exit_code(payload: dict) -> int | None:
    """
    Robustly extracts exit code from direct payload (exitCode, exit_code)
    and nested structures (toolResponse, result).
    Returns integer exit code, or None if no exit code could be determined.
    """
    if not isinstance(payload, dict):
        return None

    # 1. Direct fields
    for key in ("exitCode", "exit_code", "returncode"):
        val = payload.get(key)
        if val is not None:
            try:
                return int(val)
            except (ValueError, TypeError):
                pass

    # 2. Check nested structures: toolResponse, result, response, output, toolOutput, content, stdout
    for key in ("toolResponse", "result", "response", "output", "toolOutput", "content", "stdout"):
        val = payload.get(key)
        if isinstance(val, dict):
            # Direct check in dict
            for sub_key in ("exitCode", "exit_code", "returncode", "code"):
                sub_val = val.get(sub_key)
                if sub_val is not None:
                    try:
                        return int(sub_val)
                    except (ValueError, TypeError):
                        pass
            # Check nested sub-dict inside val
            for sub_dict_key in ("result", "toolResponse", "response", "data"):
                sub_dict = val.get(sub_dict_key)
                if isinstance(sub_dict, dict):
                    for sub_key in ("exitCode", "exit_code", "returncode", "code"):
                        sub_val = sub_dict.get(sub_key)
                        if sub_val is not None:
                            try:
                                return int(sub_val)
                            except (ValueError, TypeError):
                                pass
            # Check string fields inside dict (e.g., output, content, stdout)
            for text_key in ("output", "content", "stdout"):
                text_val = val.get(text_key)
                if isinstance(text_val, str):
                    m = re.search(r"(?:failed with exit code|exited with code)\s*[:=]?\s*(\d+)", text_val, re.I)
                    if m:
                        try:
                            return int(m.group(1))
                        except (ValueError, TypeError):
                            pass
        elif isinstance(val, str):
            # String JSON parsing attempt
            try:
                parsed = json.loads(val)
                if isinstance(parsed, dict):
                    sub_code = extract_exit_code(parsed)
                    if sub_code is not None:
                        return sub_code
            except (json.JSONDecodeError, ValueError, TypeError):
                pass
            # Regex match on string content
            m = re.search(r"(?:failed with exit code|exited with code)\s*[:=]?\s*(\d+)", val, re.I)
            if m:
                try:
                    return int(m.group(1))
                except (ValueError, TypeError):
                    pass

    return None


def load_state(conv_id: str = "default", state_dir: Path | None = None) -> dict:
    """Loads state for conversation or returns clean baseline."""
    state_file = get_state_file(conv_id, state_dir)
    default_state = {
        "conversation_id": conv_id,
        "code_dirty": False,
        "last_modified_files": [],
        "block_count": 0,
        "last_verified_at": None,
        "cwd": None,
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
                    "cwd": data.get("cwd"),
                }
        except (json.JSONDecodeError, OSError, ValueError):
            return default_state
    return default_state


def save_state(state: dict, conv_id: str = "default", state_dir: Path | None = None) -> None:
    """Saves state atomically to disk."""
    target_dir = state_dir or get_state_dir()
    target_dir.mkdir(parents=True, exist_ok=True)
    state_file = get_state_file(conv_id, target_dir)
    safe_conv_id = re.sub(r"[^a-zA-Z0-9_\-]", "_", conv_id)
    tmp_file = target_dir / f".tmp_verification_state_{safe_conv_id}_{os.getpid()}.json"
    try:
        tmp_file.write_text(json.dumps(state, indent=2), encoding="utf-8")
        tmp_file.replace(state_file)
    except OSError:
        state_file.write_text(json.dumps(state, indent=2), encoding="utf-8")


def record_edit(
    file_path: str,
    conv_id: str = "default",
    state_dir: Path | None = None,
    cwd: Path | str | None = None,
) -> dict:
    """
    Records a file edit. If the file is a code file or cleanroom contract file,
    marks code_dirty = True, resets block_count = 0 (re-arming the fence),
    appends the path to last_modified_files, and records cwd if provided.
    Ephemeral scratch paths are filtered out without modifying state.
    """
    state = load_state(conv_id=conv_id, state_dir=state_dir)
    effective_cwd = cwd if cwd is not None else state.get("cwd")

    if is_ephemeral_scratch_path(file_path, cwd=effective_cwd):
        return state

    if is_cleanroom_contract_file(file_path) or is_code_file(file_path):
        state["code_dirty"] = True
        state["block_count"] = 0
        modified = state.get("last_modified_files", [])
        if file_path not in modified:
            modified.append(file_path)
        state["last_modified_files"] = modified
        if cwd is not None:
            state["cwd"] = str(cwd)
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
        "cwd": None,
    }
    save_state(state, conv_id=conv_id, state_dir=state_dir)
    return state



def evaluate_stop(
    conv_id: str = "default",
    state_dir: Path | None = None,
    cwd: Path | str | None = None,
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

        has_contract = any(is_cleanroom_contract_file(f) for f in modified_files)
        has_code = any(not is_cleanroom_contract_file(f) for f in modified_files)

        if has_contract and has_code:
            category = "code and cleanroom contract edits"
        elif has_contract:
            category = "cleanroom contract edits"
        else:
            category = "code edits"

        effective_cwd = cwd if cwd is not None else state.get("cwd")
        if effective_cwd is None:
            effective_cwd = Path.cwd()

        if is_harness_workspace(effective_cwd):
            reason = (
                f"Verification Required: Unverified {category} detected in: {files_str}. "
                "Execute 'agyis test' (or 'python3 -m harness.cli test') before stopping."
            )
        else:
            detected_runner = detect_project_test_runner(effective_cwd)
            runner_str = detected_runner if detected_runner else "e.g. npm test, cargo test, pytest"
            reason = (
                f"Verification Required: Unverified {category} detected in: {files_str}. "
                f"Execute your project test suite ({runner_str}) before stopping."
            )

        return {
            "decision": "continue",
            "reason": reason,
        }
    else:
        return {
            "decision": "allow",
            "warning": "Anti-deadlock valve tripped after 2 verification blocks. Exiting despite unverified edits.",
        }


UNIVERSAL_TEST_RUNNER_PATTERNS: tuple[re.Pattern, ...] = (
    re.compile(r"(?:^|[;&|]\s*|\b(?:sudo|nohup|exec|env|time)\s+)\s*(?:pytest(?:\s|$)|python3?\s+-m\s+(?:unittest|pytest|harness(?:\.cli)?\s+test)\b)"),
    re.compile(r"(?:^|[;&|]\s*|\b(?:sudo|nohup|exec|env|time)\s+)\s*(?:(?:pnpm|npm|yarn|bun)\s+(?:--filter\s+[^\s]+\s+)?(?:run\s+)?test(?:\s+--run)?\b|\bvitest\b|\bjest\b|\bturbo\s+run\s+test\b)"),
    re.compile(r"(?:^|[;&|]\s*|\b(?:sudo|nohup|exec|env|time)\s+)\s*cargo\s+test\b"),
    re.compile(r"(?:^|[;&|]\s*|\b(?:sudo|nohup|exec|env|time)\s+)\s*go\s+test\b"),
    re.compile(r"(?:^|[;&|]\s*|\b(?:sudo|nohup|exec|env|time)\s+)\s*ctest\b"),
    re.compile(r"(?:^|[;&|]\s*|\b(?:sudo|nohup|exec|env|time)\s+)\s*(?:(?:agyis|\./agyis|psl|\./psl)\s+test\b)"),
    re.compile(r"(?:^|[;&|]\s*|\b(?:sudo|nohup|exec|env|time)\s+)\s*make\s+(?:test|check|verify)\b"),
    re.compile(r"(?:^|[;&|]\s*|\b(?:sudo|nohup|exec|env|time)\s+)\s*(?:(?:bash|sh)\s+|\./)tests?/[^\s]+\.sh\b"),
)

HARNESS_TEST_RUNNER_PATTERNS: tuple[re.Pattern, ...] = (
    re.compile(r"(?:^|[;&|]\s*|\b(?:sudo|nohup|exec|env|time)\s+)\s*(?:(?:agyis|\./agyis|psl|\./psl)\s+test\b)"),
    re.compile(r"(?:^|[;&|]\s*|\b(?:sudo|nohup|exec|env|time)\s+)\s*python3?\s+-m\s+(?:harness(?:\.cli)?\s+test|unittest\b|pytest\b)"),
    re.compile(r"(?:^|[;&|]\s*|\b(?:sudo|nohup|exec|env|time)\s+)\s*pytest(?:\s|$)"),
)


def is_test_command(command: str, cwd: Path | str | None = None) -> bool:
    """
    Checks whether a command line executes a recognized test runner.
    If cwd is specified and is identified as the harness repository,
    strictly enforces harness test commands.
    Otherwise, recognizes universal and client test runner patterns
    (including cargo, pnpm, npm, pytest, make, shell test suites).
    """
    if not command or not command.strip():
        return False
    cmd_clean = command.strip()

    if cwd is not None and is_harness_workspace(cwd):
        return any(pat.search(cmd_clean) is not None for pat in HARNESS_TEST_RUNNER_PATTERNS)

    return any(pat.search(cmd_clean) is not None for pat in UNIVERSAL_TEST_RUNNER_PATTERNS)


def check_command_verification(
    command: str,
    exit_code: int = 0,
    conv_id: str = "default",
    state_dir: Path | None = None,
    cwd: Path | str | None = None,
) -> bool:
    """
    Evaluates whether a command invocation represents test verification.
    If the command matches a recognized test runner:
      - If exit_code == 0: auto-clears code dirty state via record_verification(success=True).
      - If exit_code != 0: records record_verification(success=False).
    Returns True if the command was recognized as a test runner, False otherwise.
    """
    effective_cwd = cwd
    if effective_cwd is None:
        state = load_state(conv_id=conv_id, state_dir=state_dir)
        effective_cwd = state.get("cwd")

    if not is_test_command(command, cwd=effective_cwd):
        return False

    success = (exit_code == 0)
    record_verification(success=success, conv_id=conv_id, state_dir=state_dir)
    if not success:
        state = load_state(conv_id=conv_id, state_dir=state_dir)
        state["block_count"] = 0
        save_state(state, conv_id=conv_id, state_dir=state_dir)
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
    workspace_paths = payload.get("workspacePaths") or []
    cwd = (
        payload.get("cwd")
        or payload.get("workspace")
        or payload.get("working_directory")
        or (workspace_paths[0] if workspace_paths else None)
    )

    if action == "record_edit":
        file_path = payload.get("file_path") or payload.get("path") or ""
        state = record_edit(file_path, conv_id=conv_id, cwd=cwd)
        print(json.dumps({"status": "ok", "state": state}))
    elif action == "record_verification":
        success = bool(payload.get("success", True))
        state = record_verification(success=success, conv_id=conv_id)
        print(json.dumps({"status": "ok", "state": state}))
    elif action == "check_command_verification":
        command = payload.get("command") or payload.get("CommandLine") or ""
        extracted = extract_exit_code(payload)
        exit_code = extracted if extracted is not None else 0
        matched = check_command_verification(command, exit_code=exit_code, conv_id=conv_id, cwd=cwd)
        state = load_state(conv_id=conv_id)
        print(json.dumps({"status": "ok", "matched": matched, "state": state}))
    elif action == "reset":
        state = reset_state(conv_id=conv_id)
        print(json.dumps({"status": "ok", "state": state}))
    elif action == "evaluate_stop":
        result = evaluate_stop(conv_id=conv_id, cwd=cwd)
        print(json.dumps(result))
    elif "toolCall" in payload:
        # PreToolUse / PostToolUse event: intercept file modifications and test runner commands
        tool_call = payload.get("toolCall") or {}
        tool_name = tool_call.get("name", "")
        tool_args = tool_call.get("args") or {}
        if cwd is None:
            cwd = tool_args.get("Cwd") or tool_args.get("cwd")
        event = str(payload.get("hookEvent") or payload.get("hook_event") or payload.get("event") or "").strip().lower()
        if event == "posttooluse":
            is_post_tool_use = True
        elif event == "pretooluse":
            is_post_tool_use = False
        else:
            is_post_tool_use = bool(
                "toolResponse" in payload
                or "tool_response" in payload
                or "toolOutput" in payload
                or "tool_output" in payload
                or "result" in payload
                or "exitCode" in payload
                or "exit_code" in payload
                or tool_name in ("run_command", "execute_command", "bash")
            )

        if tool_name in ("write_to_file", "replace_file_content", "edit_file"):
            target_file = (
                tool_args.get("TargetFile")
                or tool_args.get("FilePath")
                or tool_args.get("AbsolutePath")
                or tool_args.get("file_path", "")
            )
            if target_file:
                record_edit(target_file, conv_id=conv_id, cwd=cwd)
            print(json.dumps({"decision": "allow"}))
        elif tool_name in ("run_command", "execute_command", "bash"):
            cmd = tool_args.get("CommandLine") or tool_args.get("command") or ""
            exit_code = extract_exit_code(payload)
            if exit_code is not None and cmd:
                check_command_verification(cmd, exit_code=exit_code, conv_id=conv_id, cwd=cwd)

            # PostToolUse contract: Antigravity expects exact JSON {}
            if is_post_tool_use:
                print(json.dumps({}))
            else:
                print(json.dumps({"decision": "allow"}))
    elif "command" in payload or "CommandLine" in payload:
        cmd = payload.get("command") or payload.get("CommandLine") or ""
        extracted = extract_exit_code(payload)
        exit_code = extracted if extracted is not None else 0
        matched = check_command_verification(cmd, exit_code=exit_code, conv_id=conv_id, cwd=cwd)
        state = load_state(conv_id=conv_id)
        print(json.dumps({"status": "ok", "matched": matched, "state": state, "decision": "allow"}))
    else:
        # Default behavior: Stop hook evaluation
        result = evaluate_stop(conv_id=conv_id, cwd=cwd)
        print(json.dumps(result))



if __name__ == "__main__":
    main()
