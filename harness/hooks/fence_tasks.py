# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Arafat Zahan (@kuasha420)
# Corporate Stewardship & Infrastructure: Purrfect Software Limited (PSL)
# Governed by: ICARO-42/b Ordinance (Company-Supported Personal IP Framework)

"""
Background Task Tracking, Shell Mutation & PostToolUse Handlers for Completion Fence Hook (ADR-022).
"""

from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path
import re
from typing import Optional

from harness.hooks.fence_classifiers import (
    SHELL_MUTATION_PATTERNS,
    classify_test_tier,
    is_cleanroom_contract_file,
    is_code_file,
    is_test_command,
)
from harness.hooks.fence_state import (
    clear_spec_dirty,
    get_brain_dir,
    load_state,
    record_edit,
    record_verification,
    save_state,
)


def check_background_task_detachment(
    tool_name: str,
    tool_args: dict,
    raw_output: str,
    conv_id: str = "default",
    state_dir: Path | None = None,
    cwd: Path | str | None = None,
) -> Optional[dict]:
    """
    Detects if a run_command tool execution was detached as a background task.
    If the command is a recognized test runner, registers it in pending_background_tests.
    """
    if tool_name not in ("run_command", "execute_command", "bash"):
        return None

    if "Tool is running as a background task with task id:" not in raw_output:
        return None

    m_task = re.search(r"task id:\s*([^\s\n\r]+)", raw_output)
    if not m_task:
        return None
    task_id = m_task.group(1).strip()

    cmd = tool_args.get("CommandLine") or tool_args.get("command") or ""
    effective_cwd = cwd or tool_args.get("Cwd")
    if not cmd or not is_test_command(cmd, cwd=effective_cwd):
        return None

    m_log = re.search(r"Task logs are available at:\s*(?:file://)?([^\s\n\r]+)", raw_output)
    log_path = m_log.group(1).strip() if m_log else None

    task_tier = classify_test_tier(cmd)
    state = load_state(conv_id=conv_id, state_dir=state_dir)
    pending = state.setdefault("pending_background_tests", {})
    pending[task_id] = {
        "command": cmd,
        "tier": task_tier,
        "cwd": str(effective_cwd) if effective_cwd else None,
        "log_path": log_path,
        "launched_at": datetime.now(timezone.utc).isoformat(),
    }
    save_state(state, conv_id=conv_id, state_dir=state_dir)
    return pending[task_id]


def sync_background_tasks(
    conv_id: str = "default",
    state_dir: Path | None = None,
    cwd: Path | str | None = None,
    brain_dir: Path | str | None = None,
    payload: Optional[dict] = None,
) -> bool:
    """
    Scans background task completion messages in .system_generated/messages/
    and reconciles completed test runner tasks against the dirty state.

    Returns True if an exit code 0 test runner completion cleared code_dirty.
    """
    state = load_state(conv_id=conv_id, state_dir=state_dir)

    # Fast exit if clean and no pending tasks
    if not state.get("code_dirty") and not state.get("pending_background_tests"):
        return False

    target_brain = get_brain_dir(conv_id, payload=payload, brain_dir=brain_dir)
    if not target_brain:
        return False

    messages_dir = target_brain / ".system_generated" / "messages"
    if not messages_dir.is_dir():
        return False

    pending_tests = state.get("pending_background_tests", {})
    processed_ids = set(state.get("processed_task_ids", []))
    last_dirtied_at = state.get("last_dirtied_at")

    cleared_state = False

    try:
        msg_files = list(messages_dir.glob("*.json"))
    except OSError:
        return False

    parsed_messages = []
    for msg_file in msg_files:
        try:
            data = json.loads(msg_file.read_text(encoding="utf-8"))
            if not isinstance(data, dict):
                continue
            ts_str = data.get("timestamp")
            sort_val = 0.0
            if ts_str and isinstance(ts_str, str):
                try:
                    clean_ts = ts_str.replace("Z", "+00:00")
                    sort_val = datetime.fromisoformat(clean_ts).timestamp()
                except (ValueError, TypeError):
                    sort_val = 0.0
            if sort_val == 0.0:
                try:
                    sort_val = msg_file.stat().st_mtime
                except OSError:
                    sort_val = 0.0
            parsed_messages.append((sort_val, msg_file, data))
        except (OSError, json.JSONDecodeError):
            continue

    parsed_messages.sort(key=lambda x: x[0])

    for _, msg_file, data in parsed_messages:
        try:
            sender = str(data.get("sender", ""))
            content = str(data.get("content", ""))

            if not ("/task-" in sender or "task-" in sender or "The command exited with code" in content or "failed with exit code" in content):
                continue

            task_id = sender.split("/")[-1] if "/task-" in sender else None
            if not task_id:
                m_id = re.search(r"Task id\s*\"(?:[^\"]+/)?(task-\d+)\"", content)
                if m_id:
                    task_id = m_id.group(1)

            if not task_id or task_id in processed_ids:
                continue

            m_exit = re.search(r"(?:failed with exit code|exited with code)\s*[:=]?\s*(\d+)", content)
            if not m_exit:
                continue
            exit_code = int(m_exit.group(1))

            cmd = None
            cmd_cwd = cwd
            source_meta = data.get("sourceMetadata")
            if isinstance(source_meta, dict):
                tool_obj = source_meta.get("tool") if isinstance(source_meta, dict) else None
                tool_call_obj = tool_obj.get("toolCall") if isinstance(tool_obj, dict) else None
                args_json_str = tool_call_obj.get("argumentsJson") if isinstance(tool_call_obj, dict) else None
                if args_json_str:
                    try:
                        args_obj = json.loads(args_json_str)
                        if isinstance(args_obj, dict):
                            cmd = args_obj.get("CommandLine") or args_obj.get("command")
                            cmd_cwd = args_obj.get("Cwd") or cmd_cwd
                    except (json.JSONDecodeError, TypeError):
                        pass

            if not cmd and task_id in pending_tests:
                cmd = pending_tests[task_id].get("command")
                cmd_cwd = pending_tests[task_id].get("cwd") or cmd_cwd

            if not cmd:
                for pending_k, pending_v in pending_tests.items():
                    if pending_k.endswith(task_id):
                        cmd = pending_v.get("command")
                        cmd_cwd = pending_v.get("cwd") or cmd_cwd
                        break

            if not cmd or not is_test_command(cmd, cwd=cmd_cwd):
                continue

            msg_timestamp = data.get("timestamp")
            if last_dirtied_at and msg_timestamp and msg_timestamp < last_dirtied_at:
                continue

            task_tier = pending_tests.get(task_id, {}).get("tier") or classify_test_tier(cmd)
            if exit_code == 0:
                record_verification(success=True, tier=task_tier, conv_id=conv_id, state_dir=state_dir)
                cleared_state = True
            else:
                record_verification(success=False, tier=task_tier, conv_id=conv_id, state_dir=state_dir)
                cur_st = load_state(conv_id=conv_id, state_dir=state_dir)
                cur_st["code_dirty"] = True
                cur_st["verified_tier"] = None
                save_state(cur_st, conv_id=conv_id, state_dir=state_dir)
                cleared_state = False

            processed_ids.add(task_id)
            to_del = [k for k in pending_tests if k == task_id or k.endswith("/" + task_id)]
            for k in to_del:
                del pending_tests[k]
        except Exception:
            continue

    state = load_state(conv_id=conv_id, state_dir=state_dir)
    state["processed_task_ids"] = list(processed_ids)
    state["pending_background_tests"] = pending_tests
    save_state(state, conv_id=conv_id, state_dir=state_dir)

    return cleared_state


def check_shell_command_mutation(
    cmd: str,
    cwd: Path | str | None = None,
    conv_id: str = "default",
    state_dir: Path | None = None,
    turn_id: str | None = None,
) -> bool:
    """Detects if a shell command mutated project code files."""
    if not cmd or not cmd.strip():
        return False
    cmd_clean = cmd.strip()

    # Redirection check: extract target filename
    m_redir = re.search(r"(?:>>|>)\s*([^\s;&|]+)", cmd_clean)
    if m_redir:
        target = m_redir.group(1).strip("\"'")
        is_benign = (
            target in ("/dev/null", "/tmp", "&1", "&2")
            or target.startswith(("/dev/", "/tmp/", "&"))
        )
        if not is_benign:
            if is_code_file(target) or is_cleanroom_contract_file(target):
                record_edit(target, conv_id=conv_id, state_dir=state_dir, cwd=cwd, turn_id=turn_id)
                return True

    # Tee check
    m_tee = re.search(r"\btee\s+(?:-[a-zA-Z]*a\s+)?([^\s;&|]+)", cmd_clean)
    if m_tee:
        target = m_tee.group(1).strip("\"'")
        is_benign = (
            target in ("/dev/null", "/tmp", "&1", "&2")
            or target.startswith(("/dev/", "/tmp/", "&"))
        )
        if not is_benign:
            if is_code_file(target) or is_cleanroom_contract_file(target):
                record_edit(target, conv_id=conv_id, state_dir=state_dir, cwd=cwd, turn_id=turn_id)
                return True

    # In-place sed, git apply, patch
    for pat in SHELL_MUTATION_PATTERNS:
        if pat.search(cmd_clean):
            m_sed_file = re.search(r"\bsed\s+-[^\s]*i[^\s]*\s+(?:'[^']*'|\"[^\"]*\"|[^\s]+)\s+([^\s;&|]+)", cmd_clean)
            target = m_sed_file.group(1).strip("\"'") if m_sed_file else "<shell-mutation>"
            record_edit(target, conv_id=conv_id, state_dir=state_dir, cwd=cwd, turn_id=turn_id)
            return True

    return False


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

    tier = classify_test_tier(command)
    success = (exit_code == 0)
    record_verification(success=success, tier=tier, conv_id=conv_id, state_dir=state_dir)
    if not success:
        state = load_state(conv_id=conv_id, state_dir=state_dir)
        state["block_count"] = 0
        save_state(state, conv_id=conv_id, state_dir=state_dir)
    return True


def handle_post_tool_use(
    tool_name: str,
    args: dict,
    result: dict,
    conv_id: str = "default",
    state_dir: Path | None = None,
) -> None:
    """
    PostToolUse handler: intercepts MCP tools (verify_reconstruction,
    evaluate_reconstruction_coverage) and clears spec_dirty state upon success.
    """
    if tool_name == "call_mcp_tool":
        inner_tool = args.get("ToolName", "")
        if inner_tool in ("verify_reconstruction", "evaluate_reconstruction_coverage"):
            status = result.get("status") if isinstance(result, dict) else None
            is_err = result.get("isError") or result.get("is_error") if isinstance(result, dict) else False
            if status != "error" and not is_err:
                clear_spec_dirty(conv_id=conv_id, state_dir=state_dir)
    elif "verify_reconstruction" in tool_name or "evaluate_reconstruction_coverage" in tool_name:
        status = result.get("status") if isinstance(result, dict) else None
        is_err = result.get("isError") or result.get("is_error") if isinstance(result, dict) else False
        if status != "error" and not is_err:
            clear_spec_dirty(conv_id=conv_id, state_dir=state_dir)
    elif tool_name in ("run_command", "execute_command", "bash"):
        cmd = args.get("CommandLine") or args.get("command") or ""
        exit_code = result.get("exit_code") or result.get("returncode")
        if exit_code is None:
            is_err = result.get("isError") or result.get("is_error") or False
            status = result.get("status")
            if status != "error" and not is_err:
                exit_code = 0
        if exit_code == 0 and cmd:
            cmd_lower = cmd.lower()
            if any(
                p in cmd_lower
                for p in ("verify --spec", "verify-reconstruction", "agyis verify", "harness.cli verify")
            ):
                clear_spec_dirty(conv_id=conv_id, state_dir=state_dir)
