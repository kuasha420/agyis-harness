#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Arafat Zahan (@kuasha420)
# Corporate Stewardship & Infrastructure: Purrfect Software Limited (PSL)
# Governed by: ICARO-42/b Ordinance (Company-Supported Personal IP Framework)

"""
PSL Harness: PreToolUse Anti-Drift Role, Plan-Mode & Flight-Director Guards (Task 1.2A.3 / 1.2B.3).

Extracted modular guards for `anti_drift_hook.py`:
- File exemption predicates (`is_exempt_file`)
- Recursive shell mutation detection (`_is_mutating_shell_command`)
- Native Plan-Mode lock (`check_plan_mode_lock`)
- Live role & lineage write-block guard (`check_auditor_write_block`)
- Root Cockpit Flight Director anti-thrash guard (`check_flight_director_write_guard`, `reset_flight_director_edits`)
"""

from __future__ import annotations

import json
import os
from pathlib import Path
import re
import sys
from typing import List, Optional

from harness.hooks.role_lineage import resolve_hook_role_and_agent
from harness.hooks.role_pinning import resolve_conv_and_brain
from harness.hooks.wire_compat import emit_stderr_diagnostic, enqueue_pending_advisory
from harness.trajectory import ROLE_FLIGHT_DIRECTOR
from harness.utils.state import atomic_write_json, get_state_dir, sanitize_conv_id

_MUTATION_TOOL_NAMES = frozenset({
    "write_file",
    "edit_file",
    "create_file",
    "insert_edit_into_file",
    "write_to_file",
    "replace_file_content",
    "multi_replace_file_content",
})

_HARMLESS_REDIR_RE = re.compile(
    r"(?:(?<![A-Za-z0-9_])[12])?>&\s*(?:[12]\b|-)"
    r"|(?:(?<![A-Za-z0-9_])[12]|&)?>{1,2}\s*/dev/null(?=$|[\s;&|)])"
)
_QUOTED_LITERAL_RE = re.compile(r"'[^']*'|\"(?:\\.|[^\"])*\"")
_CMD_START_MUTATION_RE = re.compile(
    r"(?:^|[;&|()]\s*|\b(?:sudo|env|xargs|nohup|exec|time|command)(?:\s+-[^\s]+)*\s+)"
    r"(?:[A-Za-z_][A-Za-z0-9_]*=[^\s]+\s+)*"
    r"(?:rm|rmdir|mv|cp|touch|mkdir|chmod|chown|truncate|dd|tee|ln|patch)\b",
    re.I,
)
_INPLACE_OR_GIT_MUTATION_RE = re.compile(
    r"\bsed\s+(?:-[a-zA-Z]*i|--in-place)\b"
    r"|\bperl\s+-[a-zA-Z]*i\b"
    r"|\bgit\s+(?:add|commit|push|reset|rebase|merge|cherry-pick|stash|clean|apply|restore|checkout\s+--|tag|branch\s+-[dDmM])\b",
    re.I,
)
_INLINE_FILE_WRITE_RE = re.compile(
    r"(?:\bpython3?(?:\.\d+)?\s+(?:-[^\s]+\s+)*-c\b[^\n]*"
    r"(?:write_text|write_bytes|os\.remove|os\.unlink|os\.replace|os\.rename|os\.mkdir|os\.makedirs|os\.chmod|os\.chown"
    r"|\.unlink\s*\(|Path\([^)]*\)\.(?:rename|replace|mkdir|rmdir|touch|write_text|write_bytes)\s*\(|shutil\."
    r"|open\([^)]*(?:,\s*['\"][^'\"]*[wax+]|\bmode\s*=\s*['\"][^'\"]*[wax+]))"
    r"|\bnode\s+(?:-[^\s]+\s+)*-e\b[^\n]*(?:fs\.writeFile(?:Sync)?|fs\.appendFile(?:Sync)?|fs\.rm(?:Sync)?|fs\.unlink(?:Sync)?|fs\.mkdir(?:Sync)?|fs\.rename(?:Sync)?))",
    re.I,
)
_NESTED_SHELL_C_RE = re.compile(
    r"(?:^|[;&|(\n]\s*)(?:(?:sudo|env|xargs|nohup|exec|time|command)(?:\s+-[^\s]+)*\s+)*"
    r"(?:/[^\s]+/)?\b(?:bash|sh|zsh|dash)\b(?:\s+(?!-c\b)[^\s;|&]+)*\s+-[a-zA-Z]*c\b\s*"
    r"(?:\$?'([^']*)'|\$?\"((?:\\.|[^\"\\])*)\")",
    re.I | re.DOTALL,
)
_FILE_REDIR_RE = re.compile(r"(?:(?<![A-Za-z0-9_])[12]|&)?>{1,2}\s*([^\s;&|&]+)")
_QUOTED_PLACEHOLDER_RE = re.compile(r"^__Q(\d+)__$")

_ROLE_EXTRACT_KEYS = (
    "subagent_role",
    "subagentRole",
    "agent_role",
    "agentRole",
    "agent_type",
    "agentType",
    "role",
    "agent_name",
    "agentName",
    "agent",
)
_ROLE_EXTRACT_ENV_KEYS = (
    "PSL_SUBAGENT_ROLE",
    "PSL_AGENT_ROLE",
    "AGYIS_ROLE",
    "AGYIS_AGENT_NAME",
    "ANTIGRAVITY_AGENT_ROLE",
)


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


def _is_mutating_shell_command(cmd: str, allow_scratch: bool = False, _depth: int = 0) -> bool:
    """Returns True when a shell command performs filesystem or git mutations."""
    if not cmd or not cmd.strip():
        return False
    if _INLINE_FILE_WRITE_RE.search(cmd):
        return True
    if _depth < 3:
        for nested in _NESTED_SHELL_C_RE.finditer(cmd):
            single_body, double_body = nested.group(1), nested.group(2)
            inner_cmd = single_body if single_body is not None else (double_body or "").replace('\\"', '"').replace("\\\\", "\\")
            if inner_cmd and _is_mutating_shell_command(inner_cmd, allow_scratch=allow_scratch, _depth=_depth + 1):
                return True
    stripped = _HARMLESS_REDIR_RE.sub(" ", cmd)
    quoted_vals: List[str] = []

    def _mask_quote(match: re.Match[str]) -> str:
        idx = len(quoted_vals)
        quoted_vals.append(match.group(0)[1:-1])
        return f"__Q{idx}__"

    unquoted = _QUOTED_LITERAL_RE.sub(_mask_quote, stripped)
    if _CMD_START_MUTATION_RE.search(unquoted) or _INPLACE_OR_GIT_MUTATION_RE.search(unquoted):
        return True
    for m in _FILE_REDIR_RE.finditer(unquoted):
        target = m.group(1)
        qm = _QUOTED_PLACEHOLDER_RE.match(target)
        if qm:
            target = quoted_vals[int(qm.group(1))]
        target_norm = target.replace("\\", "/").strip()
        if ".." in Path(target_norm).parts:
            return True
        if target_norm == "/dev/null" or target_norm.startswith(("/dev/null", "/tmp/", ".agents/artifacts/")):
            continue
        if allow_scratch and (target_norm.startswith("scratch/") or "/scratch/" in target_norm):
            continue
        return True
    return False


def _extract_target_file(payload: dict) -> str:
    """Extracts target file path from tool arguments or payload."""
    tool_call = payload.get("toolCall", {})
    tool_args = tool_call.get("args", {}) if isinstance(tool_call, dict) else {}
    if not isinstance(tool_args, dict):
        tool_args = {}

    target = (
        tool_args.get("Path")
        or tool_args.get("TargetFile")
        or tool_args.get("target_file")
        or tool_args.get("FilePath")
        or tool_args.get("file_path")
        or tool_args.get("AbsolutePath")
        or tool_args.get("path")
        or payload.get("Path")
        or payload.get("TargetFile")
        or payload.get("target_file")
        or payload.get("FilePath")
        or payload.get("file_path")
        or payload.get("AbsolutePath")
        or payload.get("path")
        or ""
    )
    return str(target).strip()


def _extract_explicit_raw_role(payload: dict) -> str:
    """Extracts raw role/agent string from legacy payload keys or environment variables."""
    for key in _ROLE_EXTRACT_KEYS:
        val = payload.get(key)
        if isinstance(val, str) and val.strip():
            return val.strip()
    for env_key in _ROLE_EXTRACT_ENV_KEYS:
        val = os.environ.get(env_key)
        if isinstance(val, str) and val.strip():
            return val.strip()
    return ""


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
    tool_name = tool_call.get("name") or "" if isinstance(tool_call, dict) else ""
    if not tool_name:
        tool_name = payload.get("tool_name") or payload.get("action") or ""

    tool_lower = tool_name.strip().lower()
    if tool_lower in _MUTATION_TOOL_NAMES:
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

    if tool_lower in ("run_command", "execute_command", "bash"):
        tool_args = tool_call.get("args", {}) if isinstance(tool_call, dict) else {}
        if not isinstance(tool_args, dict):
            tool_args = {}
        cmd = (
            tool_args.get("CommandLine")
            or tool_args.get("command")
            or payload.get("CommandLine")
            or payload.get("command")
            or ""
        )
        if _is_mutating_shell_command(str(cmd), allow_scratch=True):
            return {
                "decision": "deny",
                "reason": (
                    "PSL Native Plan-Mode Lock (ADR-031): Session is in Plan Mode (/plan). "
                    "Mutating shell commands are locked until plan approval."
                ),
            }

    return None


def check_auditor_write_block(payload: dict) -> Optional[dict]:
    """
    PSL PreToolUse Write-Block Guard (ADR-024 / ADR-025).

    Blocks file modification tools (write_to_file, replace_file_content, edit_file)
    when the calling subagent role is an auditor, planner, coordinator, reviewer,
    investigator (non-exempt), custodian, or any agent declaring write: false.
    """
    if not isinstance(payload, dict):
        return None

    explicit_raw = _extract_explicit_raw_role(payload)
    conv_id = str(payload.get("conversationId") or payload.get("conversation_id") or "default")
    resolved_role, exact_agent = resolve_hook_role_and_agent(
        payload,
        role=explicit_raw or None,
        conv_id=conv_id,
    )
    if exact_agent and (
        not explicit_raw
        or explicit_raw.strip().lower() in ("deep_execution", "forensic_auditor", "swarm_orchestrator", "flight_director")
    ):
        role = exact_agent
    else:
        role = explicit_raw or exact_agent or resolved_role or ""
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
        r_lower in ("planner", "agyis_planner", "designer", "researcher")
        or "planner" in r_lower
    )
    is_coordinator = (
        r_lower in ("coordinator", "agyis_coordinator", "orchestrator", "swarm_lead", "swarm_orchestrator")
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
        r_lower in ("main", "psl_main", "lead", "architect", "agyis_architect")
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
        r_lower in ("builder", "worker", "implementer", "harness_builder", "agyis_builder", "executioner", "deep_execution")
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
    tool_name = tool_call.get("name") or "" if isinstance(tool_call, dict) else ""
    if not tool_name:
        tool_name = payload.get("tool_name") or payload.get("action") or ""

    tool_lower = tool_name.strip().lower()
    if tool_lower in _MUTATION_TOOL_NAMES:
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

    if tool_lower in ("run_command", "execute_command", "bash"):
        if not is_custodian and (is_reviewer or is_planner or is_coordinator or is_auditor or is_investigator or explicit_write_false):
            tool_args = tool_call.get("args", {}) if isinstance(tool_call, dict) else {}
            if not isinstance(tool_args, dict):
                tool_args = {}
            cmd = tool_args.get("CommandLine") or tool_args.get("command") or payload.get("CommandLine") or payload.get("command") or ""
            allow_scratch = is_investigator and not (is_reviewer or is_planner or is_coordinator or is_auditor)
            if _is_mutating_shell_command(cmd, allow_scratch=allow_scratch):
                return {
                    "decision": "deny",
                    "reason": (
                        f"PSL Shell Mutation Guard: Agent role '{role or 'agent'}' is restricted from executing "
                        "mutating shell commands (filesystem modifications, git write operations, or unexempted output redirections)."
                    ),
                }

    return None


def check_flight_director_write_guard(payload: dict) -> Optional[dict]:
    """
    Flight Director Anti-Thrash Guard (Issue #92 / PSL-SPEC-2026-COCKPIT-DIRECTOR-001 Pillar 1).

    When the active role resolves to Flight Director / Cockpit Director, tracks
    continuous direct product code file modifications. If >3 product files are
    modified without delegation, logs stderr diagnostics and enqueues a bounded
    one-shot PreInvocation nudge (or denies when PSL_STRICT_FLIGHT_DIRECTOR=1).
    """
    if not isinstance(payload, dict):
        return None

    explicit_raw = _extract_explicit_raw_role(payload)
    conv_id = sanitize_conv_id(resolve_conv_and_brain(payload)[0])
    resolved_role, exact_agent = resolve_hook_role_and_agent(
        payload,
        role=explicit_raw or None,
        conv_id=conv_id,
    )
    role = exact_agent or explicit_raw or resolved_role or ""
    r_lower = role.strip().lower().replace("-", "_")
    is_flight_director = (
        resolved_role == ROLE_FLIGHT_DIRECTOR
        or r_lower in ("flight_director", "cockpit_director", "cockpit", "role_flight_director")
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

    if tool_lower not in _MUTATION_TOOL_NAMES:
        return None

    target_path = _extract_target_file(payload)
    if not target_path or is_exempt_file(target_path):
        return None

    state_dir = get_state_dir()
    edits_file = state_dir / f"cockpit_direct_edits_{conv_id}.json"

    files_modified = set()
    if edits_file.exists():
        try:
            data = json.loads(edits_file.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                files_modified = set(data.get("files", []))
        except (OSError, json.JSONDecodeError, ValueError) as exc:
            sys.stderr.write(f"PSL Anti-Drift: Failed reading cockpit edits state: {exc}\n")
            files_modified = set()

    files_modified.add(target_path)
    try:
        atomic_write_json(edits_file, {"files": sorted(list(files_modified))})
    except OSError as exc:
        sys.stderr.write(f"PSL Anti-Drift: Failed writing cockpit edits state: {exc}\n")

    count = len(files_modified)
    if count > 3:
        strict = os.environ.get("PSL_STRICT_FLIGHT_DIRECTOR", "").strip().lower() in ("1", "true", "yes")
        reason = (
            f"PSL Flight Director Advisory: Root cockpit has modified {count} product code files "
            f"directly without delegating to an agyis_builder or specialist subagent. "
            f"The root cockpit is an Air Traffic Control Tower, not a construction site. "
            f"Delegate execution downstream to subagent-router to prevent context thrash."
        )
        emit_stderr_diagnostic(reason)
        if strict:
            return {
                "decision": "deny",
                "reason": reason,
            }
        enqueue_pending_advisory(conv_id, reason, state_dir=state_dir)
        return {"decision": "allow"}

    return None


def reset_flight_director_edits(conv_id: str = "default") -> None:
    """Resets the direct edit counter for a given conversation when subagent delegation occurs."""
    safe_conv = sanitize_conv_id(conv_id)
    state_dir = get_state_dir()
    edits_file = state_dir / f"cockpit_direct_edits_{safe_conv}.json"
    if edits_file.exists():
        try:
            edits_file.unlink()
        except OSError as exc:
            sys.stderr.write(f"PSL Anti-Drift: Failed resetting cockpit edits state: {exc}\n")
