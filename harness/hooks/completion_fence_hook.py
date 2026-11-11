#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Arafat Zahan (@kuasha420)
# Corporate Stewardship & Infrastructure: Purrfect Software Limited (PSL)
# Governed by: ICARO-42/b Ordinance (Company-Supported Personal IP Framework)

"""
PSL Harness: Deterministic Stop-Hook Verification Fence (ADR-022)

Thin CLI/hook facade delegating classification, state lifecycle, task tracking,
and gate evaluation to decomposed submodules while preserving 100% public and
test-imported symbol compatibility.
"""

from __future__ import annotations

from datetime import datetime, timezone
import json
import os
from pathlib import Path
import sys

from harness.discovery import detect_project_test_runner, get_git_modified_files
from harness.hooks.fence_classifiers import (
    CODE_EXTENSIONS, CODE_MUTATION_TOOLS, COMMAND_PREFIX, DECLARATIVE_SPEC_EXTENSIONS,
    EXECUTIONER_HORIZON_STEPS, EXEMPT_EXTENSIONS, EXEMPT_FILENAMES,
    HARNESS_TEST_RUNNER_PATTERNS, ROLE_DEEP_EXECUTION, ROLE_FLIGHT_DIRECTOR,
    ROLE_FORENSIC_AUDITOR, ROLE_SWARM_ORCHESTRATOR, SHELL_MUTATION_PATTERNS,
    TIER_RANKS, UNIVERSAL_TEST_RUNNER_PATTERNS, check_has_mutable_code,
    classify_test_tier, extract_exit_code, is_cleanroom_contract_file, is_code_file,
    is_commit_or_pr_command, is_ephemeral_scratch_path, is_manifest_verified,
    is_mutation_test_command, is_test_command, is_test_file, normalize_role,
)
from harness.hooks.fence_gates import check_completion_fence_pre_tool, check_pre_tool_use, evaluate_stop
from harness.hooks.fence_state import (
    clear_spec_dirty, get_brain_dir, get_state_file, load_state,
    record_edit, record_verification, reset_state, save_state,
)
from harness.hooks.fence_tasks import (
    check_background_task_detachment, check_command_verification,
    check_shell_command_mutation, handle_post_tool_use, sync_background_tasks,
)
from harness.utils.state import get_state_dir
from harness.utils.workspace import is_harness_workspace

__all__ = [
    "EXEMPT_EXTENSIONS", "EXEMPT_FILENAMES", "CODE_EXTENSIONS", "DECLARATIVE_SPEC_EXTENSIONS",
    "COMMAND_PREFIX", "UNIVERSAL_TEST_RUNNER_PATTERNS", "HARNESS_TEST_RUNNER_PATTERNS",
    "SHELL_MUTATION_PATTERNS", "get_state_file", "get_brain_dir", "is_code_file",
    "is_cleanroom_contract_file", "is_ephemeral_scratch_path", "is_test_command",
    "is_manifest_verified", "extract_exit_code", "load_state", "save_state", "record_edit",
    "record_verification", "clear_spec_dirty", "reset_state", "evaluate_stop",
    "check_command_verification", "check_background_task_detachment", "sync_background_tasks",
    "check_shell_command_mutation", "handle_post_tool_use", "classify_test_tier",
    "is_commit_or_pr_command", "is_test_file", "is_mutation_test_command",
    "check_has_mutable_code", "TIER_RANKS", "ROLE_DEEP_EXECUTION", "ROLE_FLIGHT_DIRECTOR",
    "ROLE_FORENSIC_AUDITOR", "ROLE_SWARM_ORCHESTRATOR", "EXECUTIONER_HORIZON_STEPS",
    "CODE_MUTATION_TOOLS", "normalize_role", "check_pre_tool_use",
    "check_completion_fence_pre_tool", "get_state_dir", "detect_project_test_runner",
    "get_git_modified_files", "is_harness_workspace", "main",
]


def _handle_action(
    action: str, payload: dict, conv_id: str, state_dir: Path | None,
    cwd: Path | str | None, turn_id: str | None, brain_dir: Path | str | None,
) -> dict:
    """Dispatches explicit CLI action payloads to fence handlers."""
    if action == "record_edit":
        fp = payload.get("file_path") or payload.get("path") or ""
        return {"status": "ok", "state": record_edit(fp, conv_id=conv_id, state_dir=state_dir, cwd=cwd, turn_id=turn_id)}
    if action == "record_verification":
        st = record_verification(success=bool(payload.get("success", True)), conv_id=conv_id, state_dir=state_dir)
        return {"status": "ok", "state": st}
    if action == "task_completed":
        task_id = payload.get("task_id") or payload.get("taskId") or ""
        cmd = payload.get("command") or payload.get("CommandLine") or ""
        extracted = extract_exit_code(payload)
        exit_code = extracted if extracted is not None else 0
        state = load_state(conv_id=conv_id, state_dir=state_dir)
        matched = is_test_command(cmd, cwd=cwd)
        if matched:
            pending = state.get("pending_background_tests", {})
            task_tier = pending.get(task_id, {}).get("tier") or classify_test_tier(cmd)
            record_verification(success=(exit_code == 0), tier=task_tier, conv_id=conv_id, state_dir=state_dir)
            state = load_state(conv_id=conv_id, state_dir=state_dir)
            pending = state.get("pending_background_tests", {})
            pending.pop(task_id, None)
            for k in [k for k in pending if k.endswith("/" + task_id)]:
                del pending[k]
            processed = set(state.get("processed_task_ids", []))
            if task_id:
                processed.add(task_id)
            state["pending_background_tests"] = pending
            state["processed_task_ids"] = list(processed)
            save_state(state, conv_id=conv_id, state_dir=state_dir)
        return {"status": "ok", "matched": matched, "state": state}
    if action == "check_command_verification":
        cmd = payload.get("command") or payload.get("CommandLine") or ""
        extracted = extract_exit_code(payload)
        matched = check_command_verification(cmd, exit_code=(extracted if extracted is not None else 0), conv_id=conv_id, state_dir=state_dir, cwd=cwd)
        return {"status": "ok", "matched": matched, "state": load_state(conv_id=conv_id, state_dir=state_dir)}
    if action == "clear_spec_dirty":
        return {"status": "ok", "state": clear_spec_dirty(conv_id=conv_id, state_dir=state_dir)}
    if action == "reset":
        return {"status": "ok", "state": reset_state(conv_id=conv_id, state_dir=state_dir)}
    return evaluate_stop(conv_id=conv_id, state_dir=state_dir, cwd=cwd, turn_id=turn_id, brain_dir=brain_dir, payload=payload)


def _handle_pre_tool_commit_gate(cmd: str, payload: dict, conv_id: str, state_dir: Path | None, cwd: Path | str | None) -> dict | None:
    """Enforces full test suite and micro-mutation verification before git commit / PR commands."""
    if not (is_commit_or_pr_command(cmd) or (payload.get("gate_type") == "commit")):
        return None
    state = load_state(conv_id=conv_id, state_dir=state_dir)
    session_has_code = any(is_code_file(f) or f == "<shell-mutation>" for f in state.get("session_modified_files", [])) or bool(state.get("code_dirty"))
    if not session_has_code:
        return None
    if TIER_RANKS.get(state.get("verified_tier") or "", 0) < TIER_RANKS["pkg"]:
        return {
            "decision": "deny",
            "reason": (
                "Commit Verification Required: Git commit and PR creation require full package or workspace test suite "
                "('agyis test', 'agyis test --full', or 'pnpm test:full') before committing."
            ),
        }
    mutation_bypass = bool(os.environ.get("AGYIS_NO_MUTATION") == "1" or os.environ.get("PSL_FENCE_BYPASS") == "1")  # agyis: no-mutant bypass env check
    effective_cwd = cwd if cwd is not None else state.get("cwd")
    has_mutables = check_has_mutable_code(state.get("session_modified_files", []), cwd=effective_cwd)
    if not mutation_bypass and has_mutables and not state.get("mutation_verified", False):  # agyis: no-mutant default false check
        return {
            "decision": "deny",
            "reason": (
                "Commit Verification Required: Git commit and PR creation require verified diff-aware micro-mutation testing "
                "('agyis test --mutation') on modified code before committing (unverified mutants)."
            ),
        }
    return None


def _handle_post_tool_run_command(
    tool_name: str, tool_args: dict, payload: dict, cmd: str,
    conv_id: str, state_dir: Path | None, cwd: Path | str | None, turn_id: str | None,
) -> None:
    """Processes PostToolUse state updates for shell commands."""
    raw_out = str(payload.get("toolResponse") or payload.get("result") or payload.get("toolOutput") or "")
    check_background_task_detachment(tool_name, tool_args, raw_out, conv_id=conv_id, state_dir=state_dir, cwd=cwd)
    check_shell_command_mutation(cmd, cwd=cwd, conv_id=conv_id, state_dir=state_dir, turn_id=turn_id)
    exit_code = extract_exit_code(payload)
    if exit_code is not None and cmd:
        check_command_verification(cmd, exit_code=exit_code, conv_id=conv_id, state_dir=state_dir, cwd=cwd)
        if is_mutation_test_command(cmd):
            state = load_state(conv_id=conv_id, state_dir=state_dir)
            if exit_code == 0:  # agyis: no-mutant mutation exit check
                state["mutation_verified"] = True  # agyis: no-mutant record pass
                state["surviving_mutants"] = []
                state["last_mutation_timestamp"] = datetime.now(timezone.utc).isoformat()
            else:
                state["mutation_verified"] = False  # agyis: no-mutant record fail
            save_state(state, conv_id=conv_id, state_dir=state_dir)  # agyis: no-mutant state persistence
        if exit_code == 0 and any(p in cmd.lower() for p in ("verify --spec", "verify-reconstruction", "agyis verify", "harness.cli verify")):
            clear_spec_dirty(conv_id=conv_id, state_dir=state_dir)


def _handle_tool_call_event(
    payload: dict, conv_id: str, state_dir: Path | None, cwd: Path | str | None, turn_id: str | None,
) -> dict:
    """Processes PreToolUse / PostToolUse hook payloads."""
    tool_call = payload.get("toolCall") or {}
    tool_name = tool_call.get("name", "")
    tool_args = tool_call.get("args") or {}
    if cwd is None:
        cwd = tool_args.get("Cwd") or tool_args.get("cwd")

    event = str(payload.get("hookEvent") or payload.get("hook_event") or payload.get("event") or "").strip().lower()
    if "post" in event:
        is_post = True
    elif "pre" in event:
        is_post = False
    else:
        is_post = any(k in payload for k in (
            "error", "toolResponse", "tool_response", "toolOutput", "tool_output",
            "toolResult", "tool_result", "result", "response", "exitCode", "exit_code",
        ))

    if turn_id is not None:
        state = load_state(conv_id=conv_id, state_dir=state_dir)
        if state.get("active_turn_id") is not None and turn_id != state.get("active_turn_id"):
            state.update({"active_turn_id": turn_id, "turn_mutated": False, "turn_modified_files": []})
            save_state(state, conv_id=conv_id, state_dir=state_dir)
        elif state.get("active_turn_id") is None:
            state["active_turn_id"] = turn_id
            save_state(state, conv_id=conv_id, state_dir=state_dir)

    if not is_post:
        pre_check = check_pre_tool_use(tool_name=tool_name, tool_args=tool_args, payload=payload, conv_id=conv_id, state_dir=state_dir, cwd=cwd)
        if pre_check.get("decision") == "deny":
            return pre_check

    if tool_name in CODE_MUTATION_TOOLS:
        target = tool_args.get("TargetFile") or tool_args.get("FilePath") or tool_args.get("AbsolutePath") or tool_args.get("file_path", "")
        if target:
            record_edit(target, conv_id=conv_id, state_dir=state_dir, cwd=cwd, turn_id=turn_id)
    elif tool_name in ("run_command", "execute_command", "bash"):
        cmd = tool_args.get("CommandLine") or tool_args.get("command") or ""
        if not is_post and cmd:
            deny = _handle_pre_tool_commit_gate(cmd, payload, conv_id, state_dir, cwd)
            if deny is not None:
                return deny
            check_shell_command_mutation(cmd, cwd=cwd, conv_id=conv_id, state_dir=state_dir, turn_id=turn_id)
        elif is_post:
            _handle_post_tool_run_command(tool_name, tool_args, payload, cmd, conv_id, state_dir, cwd, turn_id)

    if is_post:
        raw_res = payload.get("toolResponse") or payload.get("result") or payload.get("toolOutput") or {}
        if isinstance(raw_res, str):
            try:
                res_dict = json.loads(raw_res)
            except (json.JSONDecodeError, ValueError):
                res_dict = {"output": raw_res}
        else:
            res_dict = raw_res if isinstance(raw_res, dict) else {}
        handle_post_tool_use(tool_name, tool_args, res_dict, conv_id=conv_id, state_dir=state_dir)
        return {}
    return {"decision": "allow"}


def main() -> None:
    """CLI / hook entry point consuming protojson from stdin and writing to stdout."""
    try:
        raw_stdin = sys.stdin.read()
        if not raw_stdin.strip():
            print(json.dumps(evaluate_stop("default")))
            return
        payload = json.loads(raw_stdin)
        if not isinstance(payload, dict):
            print(json.dumps(evaluate_stop("default")))
            return
    except (json.JSONDecodeError, OSError):
        print(json.dumps({"decision": "allow"}))
        return

    conv_id = str(payload.get("conversationId") or payload.get("conversation_id") or "default")
    action = payload.get("action")
    ws_paths = payload.get("workspacePaths") or []
    cwd = payload.get("cwd") or payload.get("workspace") or payload.get("working_directory") or (ws_paths[0] if ws_paths else None)
    turn_id = payload.get("turnId") or payload.get("turn_id")
    raw_sd = payload.get("state_dir") if "state_dir" in payload else payload.get("stateDir")
    state_dir = Path(raw_sd) if raw_sd is not None else None
    brain_dir = payload.get("brain_dir") or payload.get("brainDirectory") or payload.get("brainPath")

    if action in ("record_edit", "record_verification", "task_completed", "check_command_verification", "clear_spec_dirty", "reset", "evaluate_stop"):
        result = _handle_action(action, payload, conv_id, state_dir, cwd, turn_id, brain_dir)
    elif "toolCall" in payload:
        result = _handle_tool_call_event(payload, conv_id, state_dir, cwd, turn_id)
    elif "command" in payload or "CommandLine" in payload:
        cmd = payload.get("command") or payload.get("CommandLine") or ""
        extracted = extract_exit_code(payload)
        matched = check_command_verification(cmd, exit_code=(extracted if extracted is not None else 0), conv_id=conv_id, state_dir=state_dir, cwd=cwd)
        result = {"status": "ok", "matched": matched, "state": load_state(conv_id=conv_id, state_dir=state_dir), "decision": "allow"}
    else:
        result = evaluate_stop(conv_id=conv_id, state_dir=state_dir, cwd=cwd, turn_id=turn_id, brain_dir=brain_dir, payload=payload)
    print(json.dumps(result))


if __name__ == "__main__":
    main()
