# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Arafat Zahan (@kuasha420)
# Corporate Stewardship & Infrastructure: Purrfect Software Limited (PSL)
# Governed by: ICARO-42/b Ordinance (Company-Supported Personal IP Framework)

"""
Verification State Lifecycle & Brain Directory Resolution for Completion Fence Hook (ADR-022).
"""

from __future__ import annotations

from datetime import datetime, timezone
import json
import os
from pathlib import Path
import re
import sys
from typing import Optional

from harness.hooks.fence_classifiers import (
    DECLARATIVE_SPEC_EXTENSIONS,
    TIER_RANKS,
    is_cleanroom_contract_file,
    is_code_file,
    is_ephemeral_scratch_path,
)
from harness.utils.state import get_state_dir

_ORIG_GET_STATE_DIR = get_state_dir


def _resolve_state_dir(state_dir: Path | None) -> Path:
    """Resolves state directory while honoring monkeypatches on fence_state or completion_fence_hook."""
    if state_dir is not None:
        return Path(state_dir)
    if get_state_dir is not _ORIG_GET_STATE_DIR:
        return Path(get_state_dir())
    facade = sys.modules.get("harness.hooks.completion_fence_hook")
    if facade is not None:
        facade_fn = getattr(facade, "get_state_dir", None)
        if callable(facade_fn) and facade_fn is not _ORIG_GET_STATE_DIR:
            return Path(facade_fn())
    return Path(get_state_dir())


def get_state_file(conv_id: str = "default", state_dir: Path | None = None) -> Path:
    """Returns the state file path for a specific conversation."""
    target_dir = _resolve_state_dir(state_dir)
    safe_conv_id = re.sub(r"[^a-zA-Z0-9_\-]", "_", conv_id)
    return target_dir / f"verification_state_{safe_conv_id}.json"


def load_state(conv_id: str = "default", state_dir: Path | None = None) -> dict:
    """Loads state for conversation or returns clean baseline."""
    state_file = get_state_file(conv_id, state_dir)
    default_state = {
        "conversation_id": conv_id,
        "code_dirty": False,
        "spec_dirty": False,
        "handoff_modified": False,
        "verified_tier": None,
        "mutation_verified": False,  # agyis: no-mutant default false load
        "surviving_mutants": [],
        "last_mutation_timestamp": None,
        "session_modified_files": [],
        "turn_mutated": False,
        "turn_modified_files": [],
        "active_turn_id": None,
        "last_modified_files": [],
        "block_count": 0,
        "gate2_block_count": 0,
        "last_verified_at": None,
        "last_dirtied_at": None,
        "cwd": None,
        "pending_background_tests": {},
        "processed_task_ids": [],
    }
    if state_file.exists():
        try:
            content = state_file.read_text(encoding="utf-8")
            data = json.loads(content)
            if isinstance(data, dict):
                return {
                    "conversation_id": str(data.get("conversation_id", conv_id)),
                    "code_dirty": bool(data.get("code_dirty", False)),
                    "spec_dirty": bool(data.get("spec_dirty", False)),
                    "handoff_modified": bool(data.get("handoff_modified", False)),
                    "verified_tier": data.get("verified_tier"),
                    "mutation_verified": bool(data.get("mutation_verified", False)),  # agyis: no-mutant load default false
                    "surviving_mutants": list(data.get("surviving_mutants", [])),
                    "last_mutation_timestamp": data.get("last_mutation_timestamp"),
                    "session_modified_files": list(data.get("session_modified_files", [])),
                    "turn_mutated": bool(data.get("turn_mutated", False)),
                    "turn_modified_files": list(data.get("turn_modified_files", [])),
                    "active_turn_id": data.get("active_turn_id"),
                    "last_modified_files": list(data.get("last_modified_files", [])),
                    "block_count": int(data.get("block_count", 0)),
                    "gate2_block_count": int(data.get("gate2_block_count", 0)),
                    "last_verified_at": data.get("last_verified_at"),
                    "last_dirtied_at": data.get("last_dirtied_at"),
                    "cwd": data.get("cwd"),
                    "pending_background_tests": dict(data.get("pending_background_tests", {})),
                    "processed_task_ids": list(data.get("processed_task_ids", [])),
                }
        except (json.JSONDecodeError, OSError, ValueError):
            return default_state
    return default_state


def save_state(state: dict, conv_id: str = "default", state_dir: Path | None = None) -> None:
    """Saves state atomically to disk."""
    target_dir = _resolve_state_dir(state_dir)
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
    turn_id: str | None = None,
) -> dict:
    """
    Records a file edit. Phase-aware decoupling (ADR-028):
    - Cleanroom contracts (docs/specs/**, .agents/ledger/**) with declarative extensions
      (.md, .json, .yaml, etc.) set spec_dirty = True (pure spec dirty).
    - Non-declarative code files in specs (.py, .ts, .rs, etc.) trigger code_dirty = True
      and spec_dirty = True (DEF-01 code-in-specs dual dirty guard).
    - Code files outside specs set code_dirty = True.
    - Ephemeral scratch paths (.rea/**, decompiled/**, artifacts/rea/**, /scratch/)
      are filtered out without modifying state.
    """
    state = load_state(conv_id=conv_id, state_dir=state_dir)
    effective_cwd = cwd if cwd is not None else state.get("cwd")

    if is_ephemeral_scratch_path(file_path, cwd=effective_cwd):
        return state

    if turn_id is not None:
        current_turn = state.get("active_turn_id")
        if current_turn is not None and turn_id != current_turn:
            state["active_turn_id"] = turn_id
            state["turn_mutated"] = False
            state["turn_modified_files"] = []
            state["handoff_modified"] = False
        elif current_turn is None:
            state["active_turn_id"] = turn_id

    p = Path(file_path)
    suffix = p.suffix.lower()
    p_name = p.name.lower()

    is_handoff = (p_name == "handoff.md" or (p_name.startswith("handoff") and p_name.endswith(".md")))
    if is_handoff:
        state["handoff_modified"] = True

    dirtied = False
    if is_cleanroom_contract_file(file_path):
        if suffix in DECLARATIVE_SPEC_EXTENSIONS:
            state["spec_dirty"] = True
            state["turn_mutated"] = True
            dirtied = True
        else:
            # Code-in-Specs guard (DEF-01): non-declarative code in specs triggers dual dirty state
            state["code_dirty"] = True
            state["spec_dirty"] = True
            state["turn_mutated"] = True
            dirtied = True
    elif is_code_file(file_path):
        state["code_dirty"] = True
        state["turn_mutated"] = True
        dirtied = True

    if dirtied:
        state["block_count"] = 0
        state["last_dirtied_at"] = datetime.now(timezone.utc).isoformat()
        state["verified_tier"] = None
        is_code = bool(is_code_file(file_path) or file_path == "<shell-mutation>" or (is_cleanroom_contract_file(file_path) and suffix not in DECLARATIVE_SPEC_EXTENSIONS))  # agyis: no-mutant code file check
        if is_code:
            state["mutation_verified"] = False  # agyis: no-mutant invalidate mutation
            state["surviving_mutants"] = []
        modified = state.get("last_modified_files", [])
        if file_path not in modified:
            modified.append(file_path)
        state["last_modified_files"] = modified
        turn_mod = state.get("turn_modified_files", [])
        if file_path not in turn_mod:
            turn_mod.append(file_path)
        state["turn_modified_files"] = turn_mod
        sess_mod = state.get("session_modified_files", [])
        if file_path not in sess_mod and (is_code_file(file_path) or file_path == "<shell-mutation>"):
            sess_mod.append(file_path)
        state["session_modified_files"] = sess_mod
        if cwd is not None:
            state["cwd"] = str(cwd)
        save_state(state, conv_id=conv_id, state_dir=state_dir)
    elif is_handoff:
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
    tier: str = "full",
    conv_id: str = "default",
    state_dir: Path | None = None,
) -> dict:
    """
    Records test verification results with verification tier tracking (RFC-051 Phase 2 R4).
    If successful, clears code_dirty, spec_dirty, turn_mutated, resets last_modified_files,
    records verified_tier, and clears session_modified_files if tier in ('pkg', 'full').
    """
    state = load_state(conv_id=conv_id, state_dir=state_dir)
    if success:
        state["code_dirty"] = False
        state["spec_dirty"] = False
        state["turn_mutated"] = False
        state["turn_modified_files"] = []
        state["last_modified_files"] = []
        state["block_count"] = 0
        state["last_verified_at"] = datetime.now(timezone.utc).isoformat()
        if tier == "mutation":  # agyis: no-mutant tier string check
            state["mutation_verified"] = True
            state["surviving_mutants"] = []
            state["last_mutation_timestamp"] = datetime.now(timezone.utc).isoformat()
            existing_tier = state.get("verified_tier")
            if TIER_RANKS.get(existing_tier or "", 0) < TIER_RANKS.get("mutation", 0):  # agyis: no-mutant semantically equivalent rank update
                state["verified_tier"] = "mutation"
        else:
            state["verified_tier"] = tier
        if state.get("verified_tier") in ("pkg", "full") and state.get("mutation_verified", False):  # agyis: no-mutant mutation_verified requirement
            state["session_modified_files"] = []
        save_state(state, conv_id=conv_id, state_dir=state_dir)
    else:
        state["code_dirty"] = True
        state["verified_tier"] = None
        if tier == "mutation":  # agyis: no-mutant failure mutation tier check
            state["mutation_verified"] = False  # agyis: no-mutant failure mutation invalidation
        save_state(state, conv_id=conv_id, state_dir=state_dir)
    return state


def clear_spec_dirty(
    conv_id: str = "default",
    state_dir: Path | None = None,
) -> dict:
    """
    Clears spec_dirty state following cleanroom verification.
    If code_dirty is False, removes cleanroom spec files from last_modified_files and resets block_count.
    """
    state = load_state(conv_id=conv_id, state_dir=state_dir)
    state["spec_dirty"] = False
    if not state.get("code_dirty", False):
        state["last_modified_files"] = [
            f for f in state.get("last_modified_files", [])
            if not is_cleanroom_contract_file(f)
        ]
        state["turn_modified_files"] = [
            f for f in state.get("turn_modified_files", [])
            if not is_cleanroom_contract_file(f)
        ]
        if not state["turn_modified_files"]:
            state["turn_mutated"] = False
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
        "spec_dirty": False,
        "handoff_modified": False,
        "verified_tier": None,
        "mutation_verified": False,  # agyis: no-mutant clean state default
        "surviving_mutants": [],
        "last_mutation_timestamp": None,
        "session_modified_files": [],
        "turn_mutated": False,
        "turn_modified_files": [],
        "active_turn_id": None,
        "last_modified_files": [],
        "block_count": 0,
        "gate2_block_count": 0,
        "last_verified_at": None,
        "last_dirtied_at": None,
        "cwd": None,
        "pending_background_tests": {},
        "processed_task_ids": [],
    }
    save_state(state, conv_id=conv_id, state_dir=state_dir)
    return state


def get_brain_dir(
    conv_id: str,
    payload: Optional[dict] = None,
    brain_dir: Optional[Path | str] = None,
) -> Optional[Path]:
    """
    Resolves the Antigravity conversation brain directory:
    1. Explicit brain_dir argument / override.
    2. payload['brain_dir'], payload['brainDirectory'], payload['artifactDirectoryPath'] or payload['transcriptPath'].
    3. Standard user location: ~/.gemini/antigravity/brain/<conv_id>.
    """
    if brain_dir:
        p = Path(brain_dir).resolve()
        if p.is_dir():
            return p

    if payload:
        for k in ("brain_dir", "brainDirectory", "brainPath"):
            val = payload.get(k)
            if val:
                p = Path(val).resolve()
                if p.is_dir():
                    return p
        artifact_path = payload.get("artifactDirectoryPath")
        if artifact_path:
            p = Path(artifact_path).resolve()
            if p.is_dir():
                return p
        transcript_path = payload.get("transcriptPath")
        if transcript_path:
            p = Path(transcript_path).resolve().parent.parent
            if p.is_dir():
                return p

    # Standard Antigravity user location
    candidate = Path.home() / ".gemini" / "antigravity" / "brain" / conv_id
    if candidate.is_dir():
        return candidate

    return None
