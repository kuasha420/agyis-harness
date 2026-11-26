# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Arafat Zahan (@kuasha420)
# Corporate Stewardship & Infrastructure: Purrfect Software Limited (PSL)
# Governed by: ICARO-42/b Ordinance (Company-Supported Personal IP Framework)

"""
Shared Role & Exact Agent-Name Resolver for Lifecycle Hooks (Wave 1.2 / RCA 450616c1).

Propagates both the normalized canonical role bucket (`deep_execution`, `forensic_auditor`,
`flight_director`, `swarm_orchestrator`) and exact specialist `agent_name` (`agyis_custodian`,
`agyis_investigator`, `agyis_builder`, `agyis_reviewer`, `agyis_planner`, `agyis_auditor`)
from payload, sticky CID state, and native `conversation_summaries.db` lineage.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

from harness.hooks.role_pinning import (
    _CANONICAL_ROLE_BUCKETS,
    _EPHEMERAL_CIDS,
    check_pillar_3_explicit_role,
    has_parent_conversation,
    load_sticky_role_state,
    resolve_cid_state_dir,
    resolve_conv_and_brain,
)
from harness.trajectory import (
    ROLE_DEEP_EXECUTION,
    ROLE_FLIGHT_DIRECTOR,
    normalize_role_str,
    read_conversation_lineage,
)

_EXPLICIT_ROLE_KEYS: Tuple[str, ...] = (
    "agentName",
    "agent_name",
    "subagentType",
    "subagent_role",
    "subagentRole",
    "typeName",
    "agentType",
    "agent_type",
    "archetype",
    "role",
)


def _extract_explicit_role_tokens(
    payload: Dict[str, Any],
    role: Optional[str],
) -> Tuple[Optional[str], Optional[str]]:
    """Extracts (normalized_role, exact_agent_name) from explicit role arg, payload, and env."""
    norm_role: Optional[str] = None
    exact_agent: Optional[str] = None

    if isinstance(role, str) and role.strip():
        raw_r = role.strip()
        matched_r = normalize_role_str(raw_r)
        if matched_r:
            norm_role = matched_r
            if raw_r.lower() not in _CANONICAL_ROLE_BUCKETS:
                exact_agent = raw_r

    holders = [
        payload,
        *(pd for pk in ("agent", "subagent", "metadata", "context") if isinstance((pd := payload.get(pk)), dict)),
    ]
    for holder in holders:
        for key in _EXPLICIT_ROLE_KEYS:
            val = holder.get(key)
            if not isinstance(val, str) or not val.strip():
                continue
            raw_v = val.strip()
            matched = normalize_role_str(raw_v)
            if not matched:
                continue
            if norm_role is None:
                norm_role = matched
            if exact_agent is None and raw_v.lower() not in _CANONICAL_ROLE_BUCKETS and matched == norm_role:
                exact_agent = raw_v
            if norm_role is not None and exact_agent is not None:
                return norm_role, exact_agent

    for env_key in ("AGYIS_AGENT_NAME", "AGYIS_ROLE", "PSL_AGENT_ROLE", "ANTIGRAVITY_AGENT_ROLE"):
        env_val = (os.environ.get(env_key) or "").strip()
        if not env_val:
            continue
        matched = normalize_role_str(env_val)
        if not matched:
            continue
        if norm_role is None:
            norm_role = matched
        if exact_agent is None and env_val.lower() not in _CANONICAL_ROLE_BUCKETS and matched == norm_role:
            exact_agent = env_val
    return norm_role, exact_agent


def _load_cid_sticky_state(
    eff_cid: str,
    payload: Dict[str, Any],
    state_dir: Optional[Path],
) -> Optional[Dict[str, Any]]:
    """Loads sticky role state from explicit state_dir or CID-scoped state directory."""
    if not eff_cid or eff_cid in _EPHEMERAL_CIDS:
        return None
    if state_dir is not None:
        st = load_sticky_role_state(state_dir, eff_cid)
        if st is not None:
            return st
        st_cp = load_sticky_role_state(state_dir / "checkpoints" / eff_cid, eff_cid)
        if st_cp is not None:
            return st_cp
        return None
    ws_dir: Optional[Path] = None
    ws_paths = payload.get("workspacePaths")
    if isinstance(ws_paths, (list, tuple)) and ws_paths:
        first = ws_paths[0]
        raw_ws = first if isinstance(first, str) else (first.get("path") if isinstance(first, dict) else None)
        if isinstance(raw_ws, str) and raw_ws.strip():
            ws_dir = Path(os.path.expanduser(raw_ws.strip()))
    elif isinstance(ws_paths, str) and ws_paths.strip():
        ws_dir = Path(os.path.expanduser(ws_paths.strip()))
    cand_dir = resolve_cid_state_dir(eff_cid, workspace_dir=ws_dir, payload=payload)
    return load_sticky_role_state(cand_dir, eff_cid) if cand_dir is not None else None


def resolve_hook_role_and_agent(
    payload: Optional[Dict[str, Any]],
    *,
    role: Optional[str] = None,
    conv_id: str = "",
    state_dir: Optional[Path] = None,
    brain_dir: Optional[Path] = None,
    db_dir: Optional[Path] = None,
) -> Tuple[Optional[str], Optional[str]]:
    """Resolves (normalized_role, exact_agent_name) for PreToolUse, PreInvocation, and Stop hooks."""
    eff_payload = payload if isinstance(payload, dict) else {}
    norm_role, exact_agent = _extract_explicit_role_tokens(eff_payload, role)
    if norm_role is not None and exact_agent is not None:
        return norm_role, exact_agent

    eff_cid, art_brain = resolve_conv_and_brain(eff_payload, conv_id)
    eff_brain = brain_dir or (art_brain.parent if (art_brain is not None and art_brain.name == eff_cid) else None)
    has_cid = bool(eff_cid and eff_cid not in _EPHEMERAL_CIDS)

    if has_cid or brain_dir is not None or db_dir is not None or has_parent_conversation(eff_payload, eff_cid, brain_dir=eff_brain, db_dir=db_dir):
        parent_cid, db_agent_name, depth = (
            read_conversation_lineage(eff_cid, brain_dir=eff_brain, db_dir=db_dir)
            if has_cid
            else (None, None, 0)
        )
        is_child = bool(
            parent_cid
            or depth > 0
            or has_parent_conversation(eff_payload, eff_cid, brain_dir=eff_brain, db_dir=db_dir)
        )

        if db_agent_name:
            db_role = normalize_role_str(db_agent_name)
            if norm_role is None and db_role:
                norm_role = db_role
            if exact_agent is None and (db_role == norm_role or norm_role is None):
                exact_agent = db_agent_name

        if has_cid and (norm_role is None or exact_agent is None):
            sticky = _load_cid_sticky_state(eff_cid, eff_payload, state_dir)
            if sticky:
                sticky_role = normalize_role_str(sticky.get("role"))
                sticky_agent = sticky.get("agent_name") if isinstance(sticky.get("agent_name"), str) else None
                sticky_agent_role = normalize_role_str(sticky_agent) if sticky_agent else None
                poisoned = bool(
                    (is_child and sticky_role == ROLE_FLIGHT_DIRECTOR and sticky_agent_role != ROLE_FLIGHT_DIRECTOR)
                    or (sticky_agent_role is not None and sticky_role != sticky_agent_role)
                )
                if not poisoned:
                    if norm_role is None and sticky_role:
                        norm_role = sticky_role
                    if exact_agent is None and sticky_agent and (normalize_role_str(sticky_agent) == norm_role or norm_role is None):
                        exact_agent = sticky_agent

        if norm_role is None:
            norm_role = check_pillar_3_explicit_role(eff_payload, conversation_id=eff_cid, is_child=is_child)

        if norm_role is None and is_child:
            norm_role = ROLE_DEEP_EXECUTION

    return norm_role, exact_agent


__all__ = ["resolve_hook_role_and_agent"]
