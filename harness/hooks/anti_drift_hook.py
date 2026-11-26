#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Arafat Zahan (@kuasha420)
# Corporate Stewardship & Infrastructure: Purrfect Software Limited (PSL)
# Governed by: ICARO-42/b Ordinance (Company-Supported Personal IP Framework)

"""
PSL Harness: PreToolUse Anti-Drift Verification Gate (ADR-024)

Enforces plan boundaries by intercepting file modifications (write_to_file,
replace_file_content, edit_file) and checking them against declared file targets
in the active implementation plan (e.g. implementation_plan.md).
"""

from __future__ import annotations

import json
import os
from pathlib import Path
import sys
from typing import Callable, List, Optional

from harness.hooks.drift_guards import (
    _MUTATION_TOOL_NAMES,
    _extract_target_file,
    _is_mutating_shell_command,
    check_auditor_write_block,
    check_flight_director_write_guard,
    check_plan_mode_lock,
    is_exempt_file,
    reset_flight_director_edits,
)
from harness.hooks.drift_validators import (
    CLUSTER_TABLE_PATTERNS,
    check_ledger_cluster_tables,
    check_ledger_persona_truth,
    get_proof_file,
    has_cluster_status_table,
    has_telemetry_proof,
    record_telemetry_proof,
)
from harness.hooks.role_pinning import resolve_conv_and_brain
from harness.hooks.wire_compat import PRE_TOOL_WIRE_KEYS, strip_wire_keys
from harness.utils.plan_parser import (
    COMMON_FILE_EXTENSIONS,
    EXCLUDED_WORDS,
    SPECIAL_FILENAMES,
    _add_indexed_path,
    _is_candidate_filepath,
    extract_plan_files,
    find_active_plan,
    is_plan_completed,
    parse_plan_files,
)
from harness.utils.state import get_state_dir

# Pluggable modular domain validators (ADR-014 / ADR-031)
DRIFT_VALIDATORS: List[Callable[..., Optional[dict]]] = [
    check_ledger_cluster_tables,
    check_ledger_persona_truth,
]

__all__ = [
    "COMMON_FILE_EXTENSIONS",
    "SPECIAL_FILENAMES",
    "EXCLUDED_WORDS",
    "_is_candidate_filepath",
    "_add_indexed_path",
    "extract_plan_files",
    "parse_plan_files",
    "get_state_dir",
    "CLUSTER_TABLE_PATTERNS",
    "get_proof_file",
    "record_telemetry_proof",
    "has_telemetry_proof",
    "has_cluster_status_table",
    "check_ledger_cluster_tables",
    "check_ledger_persona_truth",
    "DRIFT_VALIDATORS",
    "is_exempt_file",
    "check_drift",
    "check_plan_mode_lock",
    "check_auditor_write_block",
    "check_flight_director_write_guard",
    "reset_flight_director_edits",
    "_is_mutating_shell_command",
    "_extract_target_file",
    "_MUTATION_TOOL_NAMES",
    "find_active_plan",
    "is_plan_completed",
    "main",
]


def check_drift(target_file: str, plan_files: set[str], strict: bool = False) -> dict:
    """
    Evaluates whether modifying target_file constitutes plan drift.

    Returns:
        {"decision": "allow"} when target_file is declared or exempt.
        {"decision": "ask", "reason": ...} when undeclared and strict mode is active.
        {"decision": "allow", "reason": ...} when undeclared under default non-strict mode.
    """
    if not target_file:
        return {"decision": "allow"}

    if is_exempt_file(target_file):
        return {"decision": "allow"}

    if not plan_files:
        return {"decision": "allow"}

    target_clean = target_file.replace("\\", "/").strip()
    target_name = Path(target_clean).name

    # 1. Exact match or basename match
    if target_clean in plan_files or target_clean.lstrip("/") in plan_files or target_name in plan_files:
        return {"decision": "allow"}

    # 2. Suffix / relative match
    for pf in plan_files:
        pf_clean = pf.replace("\\", "/").strip().lstrip("/")
        tgt_stripped = target_clean.lstrip("/")
        if tgt_stripped == pf_clean:
            return {"decision": "allow"}
        if tgt_stripped.endswith("/" + pf_clean):
            return {"decision": "allow"}
        if pf_clean.endswith("/" + tgt_stripped):
            return {"decision": "allow"}

    # Undeclared file detected
    is_strict = strict or (os.environ.get("PSL_STRICT_ANTI_DRIFT", "").strip().lower() in ("1", "true", "yes"))

    if is_strict:
        return {
            "decision": "ask",
            "reason": (
                f"PSL Anti-Drift Gate: Target file '{target_file}' is not listed in implementation_plan.md. "
                "Please confirm intentional edit."
            ),
        }
    else:
        return {
            "decision": "allow",
            "reason": (
                f"PSL Anti-Drift Notice: Target file '{target_file}' was not declared in implementation_plan.md; "
                "permitted under non-strict mode."
            ),
        }


def main() -> None:
    """PreToolUse anti-drift entry point consuming protojson from stdin."""
    try:
        raw_stdin = sys.stdin.read()
        if not raw_stdin.strip():
            print(json.dumps({"decision": "allow"}))
            return
        payload = json.loads(raw_stdin)
        if not isinstance(payload, dict):
            print(json.dumps({"decision": "allow"}))
            return
    except Exception as exc:
        print(f"PSL Anti-Drift: Error parsing stdin: {exc}", file=sys.stderr)
        print(json.dumps({"decision": "allow"}))
        return

    # Action override for direct testing/IPC
    action = payload.get("action")
    if action == "check_auditor_write_block":
        result = check_auditor_write_block(payload)
        print(json.dumps(strip_wire_keys(result or {"decision": "allow"}, allowed_keys=PRE_TOOL_WIRE_KEYS)))
        return
    if action == "check_flight_director_write_guard":
        result = check_flight_director_write_guard(payload)
        print(json.dumps(strip_wire_keys(result or {"decision": "allow"}, allowed_keys=PRE_TOOL_WIRE_KEYS)))
        return
    if action == "reset_flight_director_edits":
        reset_flight_director_edits(conv_id=resolve_conv_and_brain(payload)[0])
        print(json.dumps({"status": "ok", "reset": True}))
        return
    if action == "check_drift":
        target = payload.get("target_file", "")
        plan_files = set(payload.get("plan_files", []))
        strict = bool(payload.get("strict", False))
        result = check_drift(target, plan_files, strict=strict)
        print(json.dumps(result))
        return
    if action == "record_telemetry_proof":
        command = payload.get("command") or payload.get("CommandLine") or ""
        conv_id = str(payload.get("conversationId") or payload.get("conversation_id") or "default")
        ok = record_telemetry_proof(command, conv_id=conv_id)
        print(json.dumps({"status": "ok", "recorded": ok}))
        return
    if action == "has_telemetry_proof":
        conv_id = str(payload.get("conversationId") or payload.get("conversation_id") or "default")
        has_proof = has_telemetry_proof(conv_id=conv_id, payload=payload)
        print(json.dumps({"status": "ok", "verified": has_proof}))
        return
    if action in ("check_ledger", "check_ledger_cluster_tables"):
        target = payload.get("target_file", "")
        content = payload.get("content", "")
        conv_id = str(payload.get("conversationId") or payload.get("conversation_id") or "default")
        result = check_ledger_cluster_tables(target, content, conv_id=conv_id, payload=payload)
        print(json.dumps(result or {"decision": "allow"}))
        return

    # Phase 0: PSL Native Plan-Mode Lock (ADR-031)
    plan_mode_block = check_plan_mode_lock(payload)
    if plan_mode_block:
        print(json.dumps(plan_mode_block))
        return

    # Phase 0.5: PSL Subagent Write-Block Guard (ADR-024 / ADR-025)
    write_block = check_auditor_write_block(payload)
    if write_block:
        print(json.dumps(write_block))
        return

    # Phase 0.6: PSL Flight Director Anti-Thrash Guard (Issue #92)
    fd_guard = check_flight_director_write_guard(payload)
    if fd_guard and fd_guard.get("decision") == "deny":
        print(json.dumps(fd_guard))
        return

    conv_id = payload.get("conversationId") or payload.get("conversation_id")
    workspace_paths = payload.get("workspacePaths") or []
    workspace_root = workspace_paths[0] if workspace_paths else None
    artifact_dir = payload.get("artifactDirectoryPath")

    tool_call = payload.get("toolCall", {})
    tool_name = tool_call.get("name", "") if isinstance(tool_call, dict) else ""
    tool_args = tool_call.get("args", {}) if isinstance(tool_call, dict) else {}
    if not isinstance(tool_args, dict):
        tool_args = {}

    tool_lower = str(tool_name).strip().lower()
    tool_action = str(tool_args.get("action") or tool_args.get("Action") or "").strip().lower()
    # Wire Flight Director edit counter reset when delegating to subagents/swarm/workflows
    if (
        tool_lower in ("invoke_subagent", "run_workflow")
        or (tool_lower == "swarm" and tool_action in ("add", ""))
        or (tool_lower == "manage_subagents" and tool_action in ("spawn", "create", "start", "add", "launch", ""))
    ):
        reset_flight_director_edits(conv_id=resolve_conv_and_brain(payload)[0])

    # Auto-record telemetry proof if run_command is executed with knot status / knot ledger
    if tool_lower in ("run_command", "execute_command", "bash"):
        cmd = tool_args.get("CommandLine") or tool_args.get("command") or ""
        if cmd:
            record_telemetry_proof(cmd, conv_id=str(conv_id or "default"))

    target_file = _extract_target_file(payload)

    if not target_file:
        print(json.dumps({"decision": "allow"}))
        return

    content = (
        tool_args.get("Content")
        or tool_args.get("Replacement")
        or tool_args.get("CodeContent")
        or tool_args.get("ReplacementContent")
        or tool_args.get("content")
        or payload.get("Content")
        or payload.get("Replacement")
        or payload.get("CodeContent")
        or payload.get("ReplacementContent")
        or payload.get("content")
        or ""
    )

    # Pluggable modular domain validators (ADR-014 / ADR-031)
    for validator in DRIFT_VALIDATORS:
        block = validator(
            target_file,
            content,
            conv_id=str(conv_id or "default"),
            workspace=workspace_root,
            payload=payload,
        )
        if block:
            print(json.dumps(block))
            return

    plan_path = find_active_plan(conv_id=conv_id, workspace_root=workspace_root, brain_dir=artifact_dir)
    if not plan_path or not plan_path.is_file():
        print(json.dumps(strip_wire_keys(fd_guard or {"decision": "allow"}, allowed_keys=PRE_TOOL_WIRE_KEYS)))
        return

    try:
        plan_content = plan_path.read_text(encoding="utf-8")
    except OSError:
        print(json.dumps(strip_wire_keys(fd_guard or {"decision": "allow"}, allowed_keys=PRE_TOOL_WIRE_KEYS)))
        return

    try:
        plan_files = parse_plan_files(plan_content)
    except Exception as exc:
        print(f"PSL Anti-Drift: Error parsing plan files: {exc}", file=sys.stderr)
        print(json.dumps(strip_wire_keys(fd_guard or {"decision": "allow"}, allowed_keys=PRE_TOOL_WIRE_KEYS)))
        return

    strict = os.environ.get("PSL_STRICT_ANTI_DRIFT", "").strip().lower() in ("1", "true", "yes")
    result = check_drift(target_file, plan_files, strict=strict)
    print(json.dumps(strip_wire_keys(result, allowed_keys=PRE_TOOL_WIRE_KEYS)))


if __name__ == "__main__":
    main()
