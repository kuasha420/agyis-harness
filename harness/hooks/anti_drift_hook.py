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

from datetime import datetime, timezone
import json
import os
from pathlib import Path
import re
import sys
from typing import Callable, List, Optional

from harness.hooks.drift_validators import (
    CLUSTER_TABLE_PATTERNS,
    check_ledger_cluster_tables,
    get_proof_file,
    has_cluster_status_table,
    has_telemetry_proof,
    record_telemetry_proof,
)
from harness.utils.plan_parser import (
    COMMON_FILE_EXTENSIONS,
    EXCLUDED_WORDS,
    SPECIAL_FILENAMES,
    _add_indexed_path,
    _is_candidate_filepath,
    extract_plan_files,
    find_active_plan,
    parse_plan_files,
)
from harness.utils.state import get_state_dir

# Pluggable modular domain validators (ADR-014 / ADR-031)
DRIFT_VALIDATORS: List[Callable[..., Optional[dict]]] = [
    check_ledger_cluster_tables,
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
    "DRIFT_VALIDATORS",
    "is_exempt_file",
    "check_drift",
    "check_plan_mode_lock",
    "check_auditor_write_block",
    "check_flight_director_write_guard",
    "reset_flight_director_edits",
    "find_active_plan",
    "main",
]


def is_exempt_file(path_str: str) -> bool:
    """
    Determines if a target file is exempt from anti-drift enforcement.
    Exemptions include:
    - Markdown documents (.md, .markdown)
    - Documentation / text (.txt, .rst, .adoc)
    - Artifact files (.agents/artifacts/*, brain directories)
    - Temporary scratch files (scratch/*, tmp/*, /tmp/*)
    """
    if not path_str or not path_str.strip():
        return True

    p = Path(path_str)
    suffix = p.suffix.lower()
    if suffix in (".md", ".markdown", ".txt", ".rst", ".adoc"):
        return True

    normalized = path_str.replace("\\", "/").lower()

    exempt_patterns = (
        ".agents/artifacts/",
        "scratch/",
        "/scratch/",
        "tmp/",
        "/tmp/",
        ".system_generated/",
        "/brain/",
        ".gemini/antigravity/",
    )
    for pattern in exempt_patterns:
        if pattern in normalized or normalized.startswith(pattern.lstrip("/")):
            return True

    parts = [part.lower() for part in p.parts]
    for exempt_dir in ("scratch", "tmp"):
        if exempt_dir in parts:
            return True

    return False


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


def _extract_target_file(payload: dict) -> str:
    """Extracts target file path from tool arguments or payload."""
    tool_call = payload.get("toolCall", {})
    tool_args = tool_call.get("args", {}) if isinstance(tool_call, dict) else {}
    if not isinstance(tool_args, dict):
        tool_args = {}

    target = (
        tool_args.get("TargetFile")
        or tool_args.get("target_file")
        or tool_args.get("FilePath")
        or tool_args.get("file_path")
        or tool_args.get("AbsolutePath")
        or tool_args.get("path")
        or payload.get("TargetFile")
        or payload.get("target_file")
        or payload.get("FilePath")
        or payload.get("file_path")
        or payload.get("AbsolutePath")
        or payload.get("path")
        or ""
    )
    return str(target).strip()


def check_plan_mode_lock(payload: dict) -> Optional[dict]:
    """
    PSL Native Plan-Mode Lock (ADR-031).

    Blocks code file modifications when the active session is in Plan Mode (/plan).
    Exempts documentation, implementation_plan.md, and scratch/tmp files.
    """
    if not isinstance(payload, dict):
        return None

    is_plan_mode = (
        payload.get("mode") == "plan"
        or payload.get("agent_mode") == "plan"
        or payload.get("agentMode") == "plan"
        or os.environ.get("ANTIGRAVITY_MODE") == "plan"
        or os.environ.get("AGY_MODE") == "plan"
        or os.environ.get("PSL_MODE") == "plan"
    )
    if not is_plan_mode:
        return None

    tool_call = payload.get("toolCall", {})
    if isinstance(tool_call, dict):
        tool_name = tool_call.get("name") or ""
    else:
        tool_name = ""
    if not tool_name:
        tool_name = payload.get("tool_name") or payload.get("action") or ""

    tool_lower = tool_name.strip().lower()
    if tool_lower in ("write_to_file", "replace_file_content", "edit_file"):
        target_path = _extract_target_file(payload)
        if target_path and is_exempt_file(target_path):
            return None
        return {
            "decision": "deny",
            "reason": (
                "PSL Native Plan-Mode Lock (ADR-031): Session is in Plan Mode (/plan). "
                "Code modifications are locked until plan approval."
            ),
        }

    return None


def check_auditor_write_block(payload: dict) -> Optional[dict]:
    """
    PSL PreToolUse Write-Block Guard (ADR-024 / ADR-025).

    Blocks file modification tools (write_to_file, replace_file_content, edit_file)
    when the calling subagent role is an auditor, planner, coordinator, reviewer,
    or any agent declaring write: false.
    """
    if not isinstance(payload, dict):
        return None

    role = (
        payload.get("agent_role")
        or payload.get("agentRole")
        or payload.get("role")
        or payload.get("agent_name")
        or payload.get("agentName")
        or payload.get("agent")
        or os.environ.get("PSL_SUBAGENT_ROLE")
        or os.environ.get("PSL_AGENT_ROLE")
        or ""
    )
    r_lower = role.strip().lower().replace("-", "_")
    is_investigator = (
        r_lower in ("investigator", "agyis_investigator", "detective", "forensic")
        or "investigator" in r_lower
        or "detective" in r_lower
    )
    is_auditor = (
        r_lower in ("auditor", "harness_auditor", "agyis_auditor", "qa_verifier", "qa")
        or "auditor" in r_lower
    )
    is_planner = (
        r_lower in ("planner", "agyis_planner", "architect", "designer", "researcher")
        or "planner" in r_lower
    )
    is_coordinator = (
        r_lower in ("coordinator", "agyis_coordinator", "orchestrator", "swarm_lead")
        or "coordinator" in r_lower
    )
    is_reviewer = (
        r_lower in ("hammer", "reviewer", "inspector", "harness_reviewer", "agyis_reviewer")
        or "reviewer" in r_lower
    )
    is_custodian = (
        r_lower in ("custodian", "harness_custodian", "agyis_custodian", "git_custodian", "commit_gate")
        or "custodian" in r_lower
    )
    is_main = (
        r_lower in ("main", "psl_main", "lead", "agyis_architect")
        or "master" in r_lower
        or "agyis_architect" in r_lower
    )

    perms = payload.get("permissions")
    explicit_write_false = (
        payload.get("write") is False
        or payload.get("can_write") is False
        or (isinstance(perms, dict) and perms.get("write") is False)
    )

    is_builder = (
        r_lower in ("builder", "worker", "implementer", "harness_builder", "agyis_builder", "executioner")
        or "builder" in r_lower
    )
    if (is_builder or is_main) and not explicit_write_false:
        return None

    should_block = (
        is_investigator
        or is_auditor
        or is_planner
        or is_coordinator
        or is_reviewer
        or is_custodian
        or explicit_write_false
    )
    if not should_block:
        return None

    tool_call = payload.get("toolCall", {})
    if isinstance(tool_call, dict):
        tool_name = tool_call.get("name") or ""
    else:
        tool_name = ""
    if not tool_name:
        tool_name = payload.get("tool_name") or payload.get("action") or ""

    tool_lower = tool_name.strip().lower()
    if tool_lower in ("write_to_file", "replace_file_content", "edit_file"):
        target_path = _extract_target_file(payload)
        if is_investigator:
            if target_path and is_exempt_file(target_path):
                return None
            return {
                "decision": "deny",
                "reason": "PSL Investigator Invariant: agyis_investigator is strictly read-only on product code and can only write to scratch or artifacts.",
            }
        elif is_planner or is_coordinator:
            if target_path and is_exempt_file(target_path):
                return None
            agent_type = "coordinator" if is_coordinator else "planner"
            return {
                "decision": "deny",
                "reason": f"PSL Write-Block Guard: {role or agent_type} is artifact-only and cannot mutate code files directly.",
            }
        elif is_auditor:
            reason = "PSL Auditor Invariant: harness_auditor is strictly verification-only and cannot mutate files."
        elif is_custodian:
            reason = "PSL Custodian Invariant: custodian is strictly git commit gate / workspace hygiene and cannot mutate code files directly."
        else:
            reason = f"PSL Write-Block Guard: agent '{role or 'agent'}' has write: false and cannot mutate files."

        return {
            "decision": "deny",
            "reason": reason,
        }

    return None


def check_flight_director_write_guard(payload: dict) -> Optional[dict]:
    """
    Flight Director Anti-Thrash Guard (Issue #92 / PSL-SPEC-2026-COCKPIT-DIRECTOR-001 Pillar 1).

    When the active role is ROLE_FLIGHT_DIRECTOR, cockpit_director, or root cockpit,
    tracks continuous direct product code file modifications. If >3 product files
    are modified without specialist subagent delegation, emits an advisory warning
    (or blocks if PSL_STRICT_FLIGHT_DIRECTOR=1).
    """
    if not isinstance(payload, dict):
        return None

    role = (
        payload.get("agent_role")
        or payload.get("agentRole")
        or payload.get("role")
        or payload.get("agent_name")
        or payload.get("agentName")
        or payload.get("agent")
        or os.environ.get("PSL_SUBAGENT_ROLE")
        or os.environ.get("PSL_AGENT_ROLE")
        or os.environ.get("AGYIS_ROLE")
        or ""
    )
    r_lower = role.strip().lower().replace("-", "_")
    is_flight_director = (
        r_lower in ("flight_director", "cockpit_director", "cockpit", "role_flight_director")
        or "flight_director" in r_lower
        or "cockpit_director" in r_lower
    )
    if not is_flight_director:
        return None

    tool_call = payload.get("toolCall", {})
    tool_name = tool_call.get("name") if isinstance(tool_call, dict) else ""
    if not tool_name:
        tool_name = payload.get("tool_name") or payload.get("action") or ""
    tool_lower = tool_name.strip().lower()

    if tool_lower not in ("write_to_file", "replace_file_content", "edit_file"):
        return None

    target_path = _extract_target_file(payload)
    if not target_path or is_exempt_file(target_path):
        return None

    # Track direct product code modifications
    conv_id = str(payload.get("conversationId") or payload.get("conversation_id") or "default")
    state_dir = get_state_dir()
    edits_file = state_dir / f"cockpit_direct_edits_{conv_id}.json"

    files_modified = set()
    if edits_file.exists():
        try:
            content = edits_file.read_text(encoding="utf-8")
            data = json.loads(content)
            if isinstance(data, dict):
                files_modified = set(data.get("files", []))
        except Exception:
            files_modified = set()

    files_modified.add(target_path)
    try:
        edits_file.write_text(json.dumps({"files": sorted(list(files_modified))}), encoding="utf-8")
    except Exception:
        pass

    count = len(files_modified)
    if count > 3:
        strict = os.environ.get("PSL_STRICT_FLIGHT_DIRECTOR", "").strip().lower() in ("1", "true", "yes")
        reason = (
            f"PSL Flight Director Advisory: Root cockpit has modified {count} product code files "
            f"directly without delegating to an agyis_builder or specialist subagent. "
            f"The root cockpit is an Air Traffic Control Tower, not a construction site. "
            f"Delegate execution downstream to subagent-router to prevent context thrash."
        )
        if strict:
            return {
                "decision": "deny",
                "reason": reason,
                "advisory": reason,
                "direct_edits_count": count,
            }
        else:
            return {
                "decision": "allow",
                "warning": reason,
                "advisory": reason,
                "direct_edits_count": count,
            }

    return None


def reset_flight_director_edits(conv_id: str = "default") -> None:
    """Resets the direct edit counter for a given conversation when subagent delegation occurs."""
    state_dir = get_state_dir()
    edits_file = state_dir / f"cockpit_direct_edits_{conv_id}.json"
    if edits_file.exists():
        try:
            edits_file.unlink()
        except OSError:
            pass




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
        print(json.dumps(result or {"decision": "allow"}))
        return
    if action == "check_flight_director_write_guard":
        result = check_flight_director_write_guard(payload)
        print(json.dumps(result or {"decision": "allow"}))
        return
    if action == "reset_flight_director_edits":
        conv_id = str(payload.get("conversationId") or payload.get("conversation_id") or "default")
        reset_flight_director_edits(conv_id=conv_id)
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
    tool_name = tool_call.get("name", "")
    tool_args = tool_call.get("args", {})

    # Auto-record telemetry proof if run_command is executed with knot status / knot ledger
    if tool_name in ("run_command", "execute_command", "bash"):
        cmd = tool_args.get("CommandLine") or tool_args.get("command") or ""
        if cmd:
            record_telemetry_proof(cmd, conv_id=str(conv_id or "default"))

    target_file = _extract_target_file(payload)

    if not target_file:
        print(json.dumps({"decision": "allow"}))
        return

    content = (
        tool_args.get("CodeContent")
        or tool_args.get("ReplacementContent")
        or tool_args.get("content")
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
            payload=payload,
        )
        if block:
            print(json.dumps(block))
            return

    plan_path = find_active_plan(conv_id=conv_id, workspace_root=workspace_root, brain_dir=artifact_dir)
    if not plan_path or not plan_path.is_file():
        print(json.dumps(fd_guard or {"decision": "allow"}))
        return

    try:
        plan_content = plan_path.read_text(encoding="utf-8")
    except OSError:
        print(json.dumps(fd_guard or {"decision": "allow"}))
        return

    try:
        plan_files = parse_plan_files(plan_content)
    except Exception as exc:
        print(f"PSL Anti-Drift: Error parsing plan files: {exc}", file=sys.stderr)
        print(json.dumps(fd_guard or {"decision": "allow"}))
        return

    strict = os.environ.get("PSL_STRICT_ANTI_DRIFT", "").strip().lower() in ("1", "true", "yes")
    result = check_drift(target_file, plan_files, strict=strict)
    if fd_guard and "warning" in fd_guard and result.get("decision") == "allow":
        result["warning"] = fd_guard["warning"]
        result["advisory"] = fd_guard.get("advisory", "")
    print(json.dumps(result))


if __name__ == "__main__":
    main()
