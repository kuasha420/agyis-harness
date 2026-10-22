# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Arafat Zahan (@kuasha420)
# Corporate Stewardship & Infrastructure: Purrfect Software Limited (PSL)
# Governed by: ICARO-42/b Ordinance (Company-Supported Personal IP Framework)

"""
Agyis Harness: PreInvocation Lifecycle Hook & Role-Tailored Compaction Advisory (Issue #83)

Monitors token accumulation prior to model prompt dispatch and surfaces role-tailored
"Compaction Imminent" advisories to eliminate agent diff amnesia, cognitive thrashing,
and human re-explanation fatigue across context compaction boundaries.

Fail-Open Invariants:
- Read-only SQLite connection (mode=ro, uri=True, timeout=0.5).
- All exceptions caught and swallowed gracefully.
- sys.stdout always emits valid protojson: {"injectSteps": []} or {"injectSteps": [{"ephemeralMessage": ...}]}.
- Process always exits 0.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
import sqlite3
import sys
import traceback
from typing import Any, Dict, List, Optional

from harness.hooks.token_proximity_guard import (
    get_active_conversation_tokens,
    get_conversations_dir,
)

DEFAULT_COMPACTION_ADVISORY_THRESHOLD: int = 230_000

ROLE_FLIGHT_DIRECTOR: str = "flight_director"
ROLE_SWARM_ORCHESTRATOR: str = "swarm_orchestrator"
ROLE_DEEP_EXECUTION: str = "deep_execution"
ROLE_FORENSIC_AUDITOR: str = "forensic_auditor"


def get_compaction_advisory_threshold() -> int:
    """Returns the effective compaction advisory threshold with env override support."""
    env_thresh = os.environ.get("AGYIS_COMPACTION_THRESHOLD") or os.environ.get("PSL_COMPACTION_THRESHOLD")
    if env_thresh:
        try:
            val = int(env_thresh.strip())
            if val > 0:
                return val
        except (ValueError, TypeError):
            pass
    return DEFAULT_COMPACTION_ADVISORY_THRESHOLD


def _normalize_role_str(val: Optional[str]) -> Optional[str]:
    """Normalizes input string into a canonical role identifier if recognized."""
    if not val or not isinstance(val, str):
        return None
    norm = val.strip().lower().replace("-", "_")

    if norm in (
        ROLE_DEEP_EXECUTION,
        "executioner",
        "builder",
        "harness_builder",
        "deep_coding",
        "deep_coder",
        "coder",
        "execution",
    ):
        return ROLE_DEEP_EXECUTION
    if norm in (
        ROLE_FORENSIC_AUDITOR,
        "auditor",
        "hammer",
        "forensic",
        "forensics",
        "inspector",
    ):
        return ROLE_FORENSIC_AUDITOR
    if norm in (
        ROLE_SWARM_ORCHESTRATOR,
        "orchestrator",
        "swarm",
        "mesh_coordinator",
        "mesh",
    ):
        return ROLE_SWARM_ORCHESTRATOR
    if norm in (
        ROLE_FLIGHT_DIRECTOR,
        "flight",
        "director",
        "cockpit",
        "coordinator",
        "root",
    ):
        return ROLE_FLIGHT_DIRECTOR

    # Substring / pattern matching
    if "executioner" in norm or "builder" in norm or "deep_execution" in norm or "deep_coding" in norm:
        return ROLE_DEEP_EXECUTION
    if "hammer" in norm or "auditor" in norm or "forensic" in norm:
        return ROLE_FORENSIC_AUDITOR
    if "orchestrator" in norm or "swarm" in norm:
        return ROLE_SWARM_ORCHESTRATOR
    if "flight" in norm or "cockpit" in norm:
        return ROLE_FLIGHT_DIRECTOR

    return None


def classify_agent_role(
    payload: Dict[str, Any],
    conversation_id: str = "",
    db_dir: Optional[Path] = None,
) -> str:
    """
    Classifies the active agent role into one of the four canonical archetypes:
    - ROLE_FLIGHT_DIRECTOR: Root cockpit / plan coordinator.
    - ROLE_SWARM_ORCHESTRATOR: Multi-node mesh and strand coordinator.
    - ROLE_DEEP_EXECUTION: Specialist builder / executioner.
    - ROLE_FORENSIC_AUDITOR: Hammer verification / auditor.

    Heuristics:
    1. Direct or nested role/archetype metadata in payload.
    2. Workspaces, worktrees, or paths in payload.
    3. Environment variables (AGYIS_ROLE, ANTIGRAVITY_AGENT_ROLE, PSL_AGENT_ROLE).
    4. Fast inspection of conversation SQLite steps if available.
    5. Default to ROLE_FLIGHT_DIRECTOR.
    """
    try:
        # Heuristic 1: Explicit role/subagent properties in payload
        for key in (
            "role",
            "archetype",
            "typeName",
            "agentName",
            "agent_name",
            "subagent_role",
            "subagentRole",
            "subagentType",
            "agent_type",
            "agentType",
        ):
            if key in payload and isinstance(payload[key], str):
                matched = _normalize_role_str(payload[key])
                if matched:
                    return matched

        for parent_key in ("agent", "subagent", "metadata", "context"):
            parent_dict = payload.get(parent_key)
            if isinstance(parent_dict, dict):
                for key in (
                    "role",
                    "archetype",
                    "typeName",
                    "agentName",
                    "agent_name",
                    "subagent_role",
                    "subagentRole",
                ):
                    if key in parent_dict and isinstance(parent_dict[key], str):
                        matched = _normalize_role_str(parent_dict[key])
                        if matched:
                            return matched

        # Heuristic 2: Workspace paths, worktree names, or cwd in payload
        ws_candidates: List[str] = []
        for k in ("workspace", "worktree", "cwd", "workspacePath", "workspaceDir", "worktreePath", "path"):
            v = payload.get(k)
            if isinstance(v, str):
                ws_candidates.append(v)
            elif isinstance(v, dict) and "path" in v and isinstance(v["path"], str):
                ws_candidates.append(v["path"])

        if "activeWorkspaces" in payload and isinstance(payload["activeWorkspaces"], list):
            for ws in payload["activeWorkspaces"]:
                if isinstance(ws, str):
                    ws_candidates.append(ws)
                elif isinstance(ws, dict) and "path" in ws and isinstance(ws["path"], str):
                    ws_candidates.append(ws["path"])

        for ws_path in ws_candidates:
            matched = _normalize_role_str(ws_path)
            if matched:
                return matched

        # Heuristic 3: Environment variables
        env_role = (
            os.environ.get("AGYIS_ROLE")
            or os.environ.get("ANTIGRAVITY_AGENT_ROLE")
            or os.environ.get("PSL_AGENT_ROLE")
        )
        if env_role:
            matched = _normalize_role_str(env_role)
            if matched:
                return matched

        # Heuristic 4: Fast inspection of conversation SQLite steps
        if conversation_id and conversation_id != "default":
            base_dir = db_dir or get_conversations_dir()
            db_path = base_dir / f"{conversation_id}.db"
            if db_path.is_file():
                try:
                    uri_path = f"file:{db_path.resolve()}?mode=ro"
                    with sqlite3.connect(uri_path, uri=True, timeout=0.5) as conn:
                        cur = conn.cursor()
                        cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='steps'")
                        if cur.fetchone():
                            cur.execute("PRAGMA table_info(steps)")
                            cols = {row[1] for row in cur.fetchall()}
                            if "step_data" in cols:
                                cur.execute("SELECT step_data FROM steps ORDER BY rowid ASC LIMIT 2")
                                for (raw_step,) in cur.fetchall():
                                    if raw_step:
                                        matched = _normalize_role_str(str(raw_step))
                                        if matched:
                                            return matched
                except Exception:
                    pass

    except Exception:
        pass

    # Heuristic 5: Fallback default
    return ROLE_FLIGHT_DIRECTOR


def build_compaction_advisory(
    role: str,
    tokens: int,
    threshold: int = DEFAULT_COMPACTION_ADVISORY_THRESHOLD,
) -> str:
    """
    Generates a role-tailored system advisory directive alerting the agent to imminent compaction.
    Codifies AC4 (Work Preservation Contract), AC5 (Zero Repo Pollution), and AC6 (Autonomous Continuation).
    """
    if role == ROLE_DEEP_EXECUTION:
        return (
            f"[AGYIS SYSTEM DIRECTIVE: COMPACTION IMMINENT (~{tokens:,} / {threshold:,} TOKENS)]\n"
            "ROLE: Deep Execution (Executioner / Builder)\n\n"
            "CRITICAL INSTRUCTIONS BEFORE CONTEXT COMPACTION:\n"
            "1. WORK PRESERVATION CONTRACT (MANDATORY):\n"
            "   - STRICTLY PROHIBIT executing destructive git commands: NEVER run 'git checkout -- .', 'git reset --hard', or delete uncommitted files.\n"
            "   - Keep all partial work and uncommitted edits intact on disk. Do NOT clean or discard active changes.\n"
            "2. ZERO REPO DOCUMENT POLLUTION:\n"
            "   - Save temporary recovery state or scratch files strictly to local artifacts/scratch (.agents/artifacts/ or brain directory).\n"
            "   - Zero git commits for temporary progress markers, scratch notes, or WIP files.\n"
            "3. AUTONOMOUS POST-COMPACTION CONTINUATION:\n"
            "   - Immediately upon post-compaction wake-up, run 'git status' and 'git diff' to inspect in-flight modifications.\n"
            "   - Re-verify unit tests using the project test runner, review task instructions, and resume execution autonomously without asking the operator what happened."
        )

    elif role == ROLE_SWARM_ORCHESTRATOR:
        return (
            f"[AGYIS SYSTEM DIRECTIVE: COMPACTION IMMINENT (~{tokens:,} / {threshold:,} TOKENS)]\n"
            "ROLE: Swarm Orchestrator (Mesh Coordinator)\n\n"
            "CRITICAL INSTRUCTIONS BEFORE CONTEXT COMPACTION:\n"
            "1. SWARM STATE SURVIVAL & ZERO REPO POLLUTION:\n"
            "   - Flush strand assignments, node statuses, worker branch names, and barrier join states strictly to local scratch or artifacts (.agents/artifacts/).\n"
            "   - Zero git commits for ephemeral coordinator markers.\n"
            "2. WORK PRESERVATION CONTRACT:\n"
            "   - Preserve all local worktree changes. STRICTLY PROHIBIT 'git checkout -- .' and 'git reset --hard'.\n"
            "3. AUTONOMOUS POST-COMPACTION CONTINUATION:\n"
            "   - Post-compaction, verify worker branch status and in-flight worktrees via 'git status' and 'git diff'.\n"
            "   - Resume swarm barrier joins and multi-node orchestration autonomously without manual intervention or operator re-prompting."
        )

    elif role == ROLE_FORENSIC_AUDITOR:
        return (
            f"[AGYIS SYSTEM DIRECTIVE: COMPACTION IMMINENT (~{tokens:,} / {threshold:,} TOKENS)]\n"
            "ROLE: Forensic Auditor (Auditor / Hammer)\n\n"
            "CRITICAL INSTRUCTIONS BEFORE CONTEXT COMPACTION:\n"
            "1. EVIDENCE PRESERVATION & ZERO REPO POLLUTION:\n"
            "   - Preserve uncommitted defect reports, audit findings, and verification matrices in session scratch or artifacts (.agents/artifacts/).\n"
            "   - Zero git commits for unverified or ephemeral audit markers.\n"
            "2. WORK PRESERVATION CONTRACT:\n"
            "   - Retain all test scripts and diagnostics on disk. STRICTLY PROHIBIT 'git checkout -- .' and 'git reset --hard'.\n"
            "3. AUTONOMOUS POST-COMPACTION CONTINUATION:\n"
            "   - Post-compaction, re-execute verification suites on HEAD, inspect 'git status' and 'git diff', verify exit codes, and issue formal certification autonomously."
        )

    elif role == ROLE_FLIGHT_DIRECTOR:
        return (
            f"[AGYIS SYSTEM DIRECTIVE: COMPACTION IMMINENT (~{tokens:,} / {threshold:,} TOKENS)]\n"
            "ROLE: Flight Director (Cockpit Coordinator)\n\n"
            "CRITICAL INSTRUCTIONS BEFORE CONTEXT COMPACTION:\n"
            "1. ZERO REPO DOCUMENT POLLUTION:\n"
            "   - Store current session state, remaining phase tasks, and open decisions strictly in local session artifacts (.agents/artifacts/ or brain directory) or scratch.\n"
            "   - Do NOT commit temporary state or session coordination files to git. Zero repository pollution.\n"
            "2. WORK PRESERVATION CONTRACT:\n"
            "   - Preserve all workspace changes. STRICTLY PROHIBIT 'git checkout -- .' and 'git reset --hard'.\n"
            "3. AUTONOMOUS POST-COMPACTION CONTINUATION:\n"
            "   - On next wake-up, immediately inspect the active phase plan in .agents/artifacts/ and run 'git status'.\n"
            "   - Resume ladder orchestration and subagent coordination autonomously without human re-explanation."
        )

    return (
        f"[AGYIS SYSTEM DIRECTIVE: COMPACTION IMMINENT (~{tokens:,} / {threshold:,} TOKENS)]\n"
        "ROLE: General Agent\n\n"
        "CRITICAL INSTRUCTIONS BEFORE CONTEXT COMPACTION:\n"
        "1. WORK PRESERVATION CONTRACT: STRICTLY PROHIBIT 'git checkout -- .' and 'git reset --hard'. Keep all work on disk.\n"
        "2. ZERO REPO DOCUMENT POLLUTION: Save recovery state strictly to local artifacts/scratch. Zero git commits for temporary markers.\n"
        "3. AUTONOMOUS POST-COMPACTION CONTINUATION: Inspect 'git status' and 'git diff' post-compaction and resume execution without asking operator what happened."
    )


def evaluate_pre_invocation(
    payload_str: str,
    threshold: Optional[int] = None,
    db_dir: Optional[Path] = None,
) -> Dict[str, Any]:
    """
    Evaluates token proximity for a PreInvocation event.
    Returns:
    - {"injectSteps": []} if below threshold or on error.
    - {"injectSteps": [{"ephemeralMessage": advisory}]} if at or above threshold.
    """
    try:
        payload = json.loads(payload_str) if payload_str and payload_str.strip() else {}
        if not isinstance(payload, dict):
            payload = {}
    except Exception:
        payload = {}

    try:
        conv_id = str(payload.get("conversationId") or payload.get("conversation_id") or "default")
        effective_threshold = (
            int(threshold)
            if threshold is not None
            else get_compaction_advisory_threshold()
        )

        tokens = get_active_conversation_tokens(conv_id, db_dir=db_dir)
        if tokens == 0:
            for k in ("tokens", "token_count", "tokenCount", "num_tokens", "numTokens"):
                val = payload.get(k)
                if isinstance(val, (int, float)) and val > 0:
                    tokens = int(val)
                    break

        if tokens < effective_threshold:
            return {"injectSteps": []}

        role = classify_agent_role(payload, conversation_id=conv_id, db_dir=db_dir)
        advisory = build_compaction_advisory(role, tokens, effective_threshold)
        return {"injectSteps": [{"ephemeralMessage": advisory}]}
    except Exception:
        return {"injectSteps": []}


def main(argv: Optional[List[str]] = None) -> int:
    """Fail-open CLI entrypoint for PreInvocation lifecycle hook."""
    try:
        raw_stdin = sys.stdin.read()
    except Exception:
        raw_stdin = ""

    try:
        res = evaluate_pre_invocation(raw_stdin)
    except Exception as exc:
        sys.stderr.write(f"[PSL PRE-INVOCATION HOOK] Error during evaluation: {exc}\n")
        traceback.print_exc(file=sys.stderr)
        sys.stderr.flush()
        res = {"injectSteps": []}

    try:
        sys.stdout.write(json.dumps(res) + "\n")
        sys.stdout.flush()
    except Exception:
        pass

    return 0


if __name__ == "__main__":
    sys.exit(main())
