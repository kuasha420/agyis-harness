# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Arafat Zahan (@kuasha420)
# Corporate Stewardship & Infrastructure: Purrfect Software Limited (PSL)
# Governed by: ICARO-42/b Ordinance (Company-Supported Personal IP Framework)

"""
PreToolUse & Stop Gate Evaluators for Completion Fence Hook (ADR-022).
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Optional

from harness.discovery import detect_project_test_runner, get_git_modified_files
from harness.hooks.fence_classifiers import (
    CODE_MUTATION_TOOLS, DECLARATIVE_SPEC_EXTENSIONS,
    ROLE_DEEP_EXECUTION, ROLE_FLIGHT_DIRECTOR, ROLE_SWARM_ORCHESTRATOR, TIER_RANKS,
    check_has_mutable_code, is_cleanroom_contract_file, is_code_file,
    is_manifest_verified, is_test_file, normalize_role,
)
from harness.hooks.fence_state import clear_spec_dirty, get_brain_dir, load_state, save_state
from harness.hooks.fence_tasks import sync_background_tasks
from harness.trajectory.health import SOFT_EPOCH_STEP_ADVISORY
from harness.utils.workspace import is_harness_workspace


def check_pre_tool_use(
    tool_name: str,
    tool_args: dict,
    payload: dict | None = None,
    step_count: int | None = None,
    role: str | None = None,
    conv_id: str = "default",
    state_dir: Path | None = None,
    cwd: Path | str | None = None,
) -> dict:
    """
    Evaluates PreToolUse constraints including the Soft Epoch Horizon Advisory (Issue #109).
    When role is ROLE_DEEP_EXECUTION and epoch step_count >= SOFT_EPOCH_STEP_ADVISORY (80):
    Attaches a non-blocking horizon advisory on code mutation tools (write_to_file,
    replace_file_content, edit_file) without blocking execution.
    Exempts non-executioner roles (flight_director, forensic_auditor).
    """
    effective_step = step_count
    if effective_step is None and payload:
        for k in (
            "step_count", "stepCount", "step", "current_step", "currentStep",
            "step_idx", "stepIdx", "initialNumSteps", "initial_num_steps",
            "invocationNum", "invocation_num",
        ):
            if k in payload:
                v = payload[k]
                if isinstance(v, (int, float)):
                    effective_step = int(v)
                    break
                elif isinstance(v, str) and v.strip().isdigit():
                    effective_step = int(v.strip())
                    break

    effective_role = role
    if effective_role is None and payload:
        for rk in ("role", "agent_role", "subagent_role", "archetype", "agentType", "agent_type"):
            rv = payload.get(rk)
            if isinstance(rv, str) and rv.strip():
                effective_role = rv.strip()
                break
    if not effective_role:
        effective_role = os.environ.get("AGYIS_ROLE") or os.environ.get("PSL_AGENT_ROLE")

    norm_role = normalize_role(effective_role)
    if norm_role and norm_role != ROLE_DEEP_EXECUTION:
        return {"decision": "allow"}

    if norm_role == ROLE_DEEP_EXECUTION and effective_step is not None and effective_step >= SOFT_EPOCH_STEP_ADVISORY:
        if tool_name in CODE_MUTATION_TOOLS:
            return {
                "decision": "allow",
                "advisory": (
                    f"[EPOCH HORIZON: {effective_step}/{SOFT_EPOCH_STEP_ADVISORY} STEPS] "
                    "Extended epoch reached — verify diffs, update checkpoints, or compact when convenient."
                ),
            }

    return {"decision": "allow"}


check_completion_fence_pre_tool = check_pre_tool_use


def _evaluate_orchestrator_stop(
    state: dict,
    effective_cwd: Path | str,
    conv_id: str,
    state_dir: Path | None,
    brain_dir: Path | str | None,
    payload: Optional[dict],
) -> dict:
    """Evaluates Persona Truth Gate and Gate 2 Auditor Verdict Fence for orchestrator roles."""
    has_subagents = False
    teamwork_dir = Path(effective_cwd) / ".agents" / "teamwork"
    if teamwork_dir.is_dir():
        try:
            for child in teamwork_dir.iterdir():
                if child.is_dir() and not child.name.startswith("."):
                    has_subagents = True
                    break
        except Exception:
            pass

    if not has_subagents and payload and (payload.get("subagents_dispatched") or payload.get("dispatched_subagents")):
        has_subagents = True

    if has_subagents:
        from harness.subagents.truth import validate_transition_payload_truth
        allow_synth = bool(os.environ.get("AGYIS_SYNTHETIC_TEST") == "1")
        is_truth_valid, _ = validate_transition_payload_truth(Path(effective_cwd), allow_synthetic=allow_synth)
        if not is_truth_valid:
            block_count = state.get("block_count", 0)
            if block_count < 2:
                state["block_count"] = block_count + 1
                save_state(state, conv_id=conv_id, state_dir=state_dir)
                return {
                    "decision": "continue",
                    "reason": (
                        "Persona Truth Violation: Subagents were dispatched in this session, but no verified "
                        "psl_stage_transition_payload.json was found on disk. Root orchestrators cannot declare "
                        "completion without verified delegate artifacts (Anti-Code-Monkey Invariant)."
                    ),
                }
            state["block_count"] = 0
            save_state(state, conv_id=conv_id, state_dir=state_dir)
            return {
                "decision": "allow",
                "warning": "Anti-deadlock valve tripped after 2 verification blocks. Exiting despite persona truth violation.",
            }

        auditor_fence_disabled = (
            os.environ.get("PSL_AUDITOR_FENCE_DISABLED", "").lower() in ("1", "true", "yes")
            or os.environ.get("PSL_SOLO_MODE", "").lower() in ("1", "true", "yes")
        )
        if not auditor_fence_disabled:
            from harness.subagents.verdict import validate_audit_verdict
            effective_brain_dir = get_brain_dir(conv_id=conv_id, payload=payload, brain_dir=brain_dir)
            is_verdict_valid, verdict_reason, _ = validate_audit_verdict(
                Path(effective_cwd), brain_dir=effective_brain_dir, allow_synthetic=allow_synth,
            )
            if not is_verdict_valid:
                block_count = state.get("gate2_block_count", 0)
                if block_count < 2:
                    state["gate2_block_count"] = block_count + 1
                    save_state(state, conv_id=conv_id, state_dir=state_dir)
                    return {
                        "decision": "continue",
                        "reason": (
                            f"Dual-Gate Verification Fence (Gate 2): {verdict_reason}. "
                            "Root orchestrators and coordinators require independent out-of-band auditor "
                            "clearance (agyis audit certify) before claiming milestone completion."
                        ),
                    }
                state["gate2_block_count"] = 0
                save_state(state, conv_id=conv_id, state_dir=state_dir)
                return {
                    "decision": "allow",
                    "warning": (
                        "Anti-deadlock valve tripped after 2 Gate 2 verification blocks. "
                        "Exiting despite missing/rejected auditor verdict."
                    ),
                }
            state["gate2_block_count"] = 0
            save_state(state, conv_id=conv_id, state_dir=state_dir)

    return {"decision": "allow"}


def _evaluate_commit_gate(
    state: dict,
    effective_cwd: Path | str,
    verified_tier: str | None,
    session_has_code: bool,
    payload: Optional[dict],
) -> Optional[dict]:
    """Evaluates commit verification gate when explicitly requested in payload."""
    if not (payload and payload.get("gate_type") == "commit" and session_has_code):
        return None
    if TIER_RANKS.get(verified_tier or "", 0) < TIER_RANKS["pkg"]:
        return {
            "decision": "deny",
            "reason": (
                "Commit Verification Required: Git commit and PR creation require full package or workspace test suite "
                "('agyis test', 'agyis test --full', or 'pnpm test:full') before committing."
            ),
        }
    mutation_bypass = bool(os.environ.get("AGYIS_NO_MUTATION") == "1" or os.environ.get("PSL_FENCE_BYPASS") == "1")  # agyis: no-mutant bypass check
    has_mutables = False
    try:
        from harness.mutation.micro_probe import generate_mutants_for_diff
        if generate_mutants_for_diff(repo_root=Path(effective_cwd or Path.cwd())):
            has_mutables = True
    except Exception:
        pass
    if not has_mutables:
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


def _evaluate_smell_gate(
    state: dict,
    effective_cwd: Path | str,
    conv_id: str,
    state_dir: Path | None,
) -> Optional[dict]:
    """Evaluates Turn-Level Static AST Test Smell Linting Fence."""
    if os.environ.get("AGYIS_ANTI_SYNTHETIC_BYPASS") == "1" or os.environ.get("PSL_FENCE_BYPASS") == "1":  # agyis: no-mutant bypass check
        return None
    candidate_files = list(dict.fromkeys(state.get("turn_modified_files", []) + state.get("last_modified_files", [])))
    test_files = [f for f in candidate_files if is_test_file(f)]
    if not test_files:
        return None

    from harness.doctor.test_smells import audit_file_smells
    hard_rejections = []
    for tf in test_files:
        tf_path = Path(tf)
        if not tf_path.is_absolute() and effective_cwd:  # agyis: no-mutant path resolution
            tf_path = Path(effective_cwd) / tf_path
        if tf_path.is_file():
            try:
                for smell in audit_file_smells(tf_path):
                    if getattr(smell, "severity", "").lower() in ("hard_rejection", "error", "reject", "hard_reject"):
                        hard_rejections.append(smell)
            except Exception:
                pass
    if not hard_rejections:
        return None

    first_smell = hard_rejections[0]
    block_count = state.get("block_count", 0)
    if block_count < 2:
        state["block_count"] = block_count + 1
        save_state(state, conv_id=conv_id, state_dir=state_dir)
        return {
            "decision": "continue",
            "reason": (
                f"Anti-Synthetic AST Linter Error: Synthetic Test Smell Rejection ({first_smell.rule_id} / zero-state-tautology): {first_smell.message} "
                f"in {first_smell.file_path}:{first_smell.line_number}. "
                "Resolve the synthetic test smell before stopping, or bypass with # agyis: no-smell <reason>."
            ),
        }
    state["turn_mutated"] = False  # agyis: no-mutant anti-deadlock reset
    state["turn_modified_files"] = []
    state["block_count"] = 0
    save_state(state, conv_id=conv_id, state_dir=state_dir)
    return {"decision": "allow", "warning": "Anti-deadlock valve tripped after 2 verification blocks. Exiting despite synthetic test smell."}


def _evaluate_handoff_gate(
    state: dict,
    effective_cwd: Path | str,
    verified_tier: str | None,
    session_has_code: bool,
    conv_id: str,
    state_dir: Path | None,
    payload: Optional[dict],
) -> Optional[dict]:
    """Evaluates subagent handoff / milestone verification and micro-mutation gates."""
    is_handoff_gate = bool(state.get("handoff_modified", False))
    if payload and (payload.get("gate_type") in ("handoff", "milestone") or payload.get("action") == "evaluate_handoff"):
        is_handoff_gate = True
    if os.environ.get("PSL_COMPLETION_FENCE_GATE", "").lower() in ("handoff", "milestone"):
        is_handoff_gate = True

    all_mods = set(state.get("last_modified_files", []) + state.get("turn_modified_files", []) + state.get("session_modified_files", []))
    for f in all_mods:
        p_name = Path(f).name.lower()
        if p_name == "handoff.md" or (p_name.startswith("handoff") and p_name.endswith(".md")):
            is_handoff_gate = True
            break

    if not (is_handoff_gate and session_has_code):
        return None

    def _trip_handoff_deadlock() -> dict:
        state["turn_mutated"] = False  # agyis: no-mutant anti-deadlock reset
        state["turn_modified_files"] = []
        state["handoff_modified"] = False  # agyis: no-mutant handoff flag reset
        state["block_count"] = 0
        save_state(state, conv_id=conv_id, state_dir=state_dir)
        return {"decision": "allow", "warning": "Anti-deadlock valve tripped after 2 verification blocks. Exiting despite unverified handoff."}

    if TIER_RANKS.get(verified_tier or "", 0) < TIER_RANKS["affected"]:
        block_count = state.get("block_count", 0)
        if block_count < 2:
            state["block_count"] = block_count + 1
            save_state(state, conv_id=conv_id, state_dir=state_dir)
            return {
                "decision": "continue",
                "reason": (
                    "Handoff Verification Required: Subagent handoff detected ('handoff.md'). "
                    "Subagent handoffs and milestone completion require Tier 1B affected tests "
                    "('agyis test --affected' or 'pnpm test:affected') before completing handoff."
                ),
            }
        return _trip_handoff_deadlock()

    mutation_bypass = bool(os.environ.get("AGYIS_NO_MUTATION") == "1" or os.environ.get("PSL_FENCE_BYPASS") == "1")  # agyis: no-mutant bypass check
    has_mutables = check_has_mutable_code(state.get("session_modified_files", []), cwd=effective_cwd)
    if not mutation_bypass and has_mutables and not state.get("mutation_verified", False):  # agyis: no-mutant default false check
        block_count = state.get("block_count", 0)
        if block_count < 2:
            state["block_count"] = block_count + 1
            save_state(state, conv_id=conv_id, state_dir=state_dir)
            return {
                "decision": "continue",
                "reason": (
                    "Micro-Mutation Verification Required: Subagent handoff detected ('handoff.md'). "
                    "Subagent handoffs and milestone completion require verified diff-aware micro-mutation testing "
                    "('agyis test --mutation') on modified code before completing handoff."
                ),
            }
        return _trip_handoff_deadlock()

    return None


def evaluate_stop(
    conv_id: str = "default",
    state_dir: Path | None = None,
    cwd: Path | str | None = None,
    turn_id: str | None = None,
    brain_dir: Path | str | None = None,
    payload: Optional[dict] = None,
) -> dict:
    """
    Evaluates whether an agent may stop.
    Phase-aware cleanroom fence logic (ADR-022, ADR-028, RFC-051):
    1. Reconciles background tasks via sync_background_tasks().
    2. If neither code_dirty nor spec_dirty: allows stop.
    3. If turn_mutated is False: allows stop (unblocking conversational & read-only turns).
    4. If code_dirty is True and background test is in progress: waits for reactive wakeup.
    5. Pure spec_dirty: requires verified manifest.json or trips anti-deadlock.
    6. code_dirty: requires recognized project test suite pass or trips anti-deadlock.
    """
    if os.environ.get("PSL_COMPLETION_FENCE_DISABLED", "").lower() in ("1", "true", "yes"):
        return {"decision": "allow"}

    sync_background_tasks(conv_id=conv_id, state_dir=state_dir, cwd=cwd, brain_dir=brain_dir, payload=payload)
    state = load_state(conv_id=conv_id, state_dir=state_dir)
    effective_cwd = cwd if cwd is not None else (state.get("cwd") or Path.cwd())

    role = (
        (payload.get("agent_role") if payload else "")
        or (payload.get("agentRole") if payload else "")
        or (payload.get("role") if payload else "")
        or os.environ.get("AGYIS_ROLE", "")
        or os.environ.get("PSL_AGENT_ROLE", "")
    ).lower()
    is_orchestrator = (
        any(r in role for r in ("cockpit", "orchestrator", "flight_director", "sentinel", "coordinator", "main", "main_agent"))
        or normalize_role(role) in (ROLE_FLIGHT_DIRECTOR, ROLE_SWARM_ORCHESTRATOR)
    ) and role not in ("agyis_builder", "agyis_reviewer", "agyis_custodian", "agyis_auditor")

    if is_orchestrator:
        return _evaluate_orchestrator_stop(state, effective_cwd, conv_id, state_dir, brain_dir, payload)

    if turn_id is not None:
        current_turn = state.get("active_turn_id")
        if current_turn is not None and turn_id != current_turn:
            state["active_turn_id"] = turn_id
            state["turn_mutated"] = False
            state["turn_modified_files"] = []
            save_state(state, conv_id=conv_id, state_dir=state_dir)
        elif current_turn is None:
            state["active_turn_id"] = turn_id
            save_state(state, conv_id=conv_id, state_dir=state_dir)

    code_dirty = state.get("code_dirty", False)
    spec_dirty = state.get("spec_dirty", False)
    turn_mutated = state.get("turn_mutated", False)
    verified_tier = state.get("verified_tier")

    # Truth Anchor: reconcile empty last_modified_files against git status
    if code_dirty and not state.get("last_modified_files", []):
        git_mods = get_git_modified_files(effective_cwd)
        if not git_mods:
            state["code_dirty"] = False
            state["turn_mutated"] = False
            state["turn_modified_files"] = []
            state["block_count"] = 0
            save_state(state, conv_id=conv_id, state_dir=state_dir)
            code_dirty = False
        else:
            state["last_modified_files"] = git_mods
            save_state(state, conv_id=conv_id, state_dir=state_dir)

    session_has_code = any(
        is_code_file(f) or f == "<shell-mutation>" for f in state.get("session_modified_files", [])
    ) or bool(code_dirty)

    for gate_res in (
        _evaluate_commit_gate(state, effective_cwd, verified_tier, session_has_code, payload),
        _evaluate_smell_gate(state, effective_cwd, conv_id, state_dir),
        _evaluate_handoff_gate(state, effective_cwd, verified_tier, session_has_code, conv_id, state_dir, payload),
    ):
        if gate_res is not None:
            return gate_res

    if not code_dirty and not spec_dirty:
        state["turn_mutated"] = False
        state["turn_modified_files"] = []
        state["handoff_modified"] = False
        save_state(state, conv_id=conv_id, state_dir=state_dir)
        return {"decision": "allow"}

    if not turn_mutated:
        state["turn_mutated"] = False
        state["turn_modified_files"] = []
        save_state(state, conv_id=conv_id, state_dir=state_dir)
        return {"decision": "allow"}

    pending_tests = state.get("pending_background_tests", {})
    if code_dirty and pending_tests:
        active_list = ", ".join(f"{t}: {info.get('command')}" for t, info in pending_tests.items())
        block_count = state.get("block_count", 0)
        if block_count < 2:
            state["block_count"] = block_count + 1
            save_state(state, conv_id=conv_id, state_dir=state_dir)
            return {
                "decision": "continue",
                "reason": (
                    f"Background Test In Progress: Waiting for test task(s) to finish: [{active_list}]. "
                    "Await reactive wakeup before stopping."
                ),
            }

    if not code_dirty and spec_dirty:
        if is_manifest_verified(effective_cwd):
            clear_spec_dirty(conv_id=conv_id, state_dir=state_dir)
            state["turn_mutated"] = False
            state["turn_modified_files"] = []
            save_state(state, conv_id=conv_id, state_dir=state_dir)
            return {"decision": "allow"}

        block_count = state.get("block_count", 0)
        if block_count < 2:
            state["block_count"] = block_count + 1
            save_state(state, conv_id=conv_id, state_dir=state_dir)
            modified_files = [f for f in state.get("last_modified_files", []) if is_cleanroom_contract_file(f)]
            files_str = ", ".join(modified_files) if modified_files else "cleanroom contract files"
            return {
                "decision": "continue",
                "reason": (
                    f"Cleanroom Verification Required: Unverified cleanroom contract edits detected in: {files_str}. "
                    "Execute 'rea verify-reconstruction' or 'agyis verify --spec' before stopping."
                ),
            }
        state["turn_mutated"] = False
        state["turn_modified_files"] = []
        state["block_count"] = 0
        save_state(state, conv_id=conv_id, state_dir=state_dir)
        return {"decision": "allow", "warning": "Anti-deadlock valve tripped after 2 verification blocks. Exiting despite unverified edits."}

    block_count = state.get("block_count", 0)
    if block_count < 2:
        state["block_count"] = block_count + 1
        save_state(state, conv_id=conv_id, state_dir=state_dir)
        modified_files = state.get("last_modified_files", [])
        files_str = ", ".join(modified_files) if modified_files else "untracked code files"
        has_contract = any(is_cleanroom_contract_file(f) for f in modified_files)
        has_code = any(not is_cleanroom_contract_file(f) or (Path(f).suffix.lower() not in DECLARATIVE_SPEC_EXTENSIONS) for f in modified_files)
        category = "code and cleanroom contract edits" if (has_contract and has_code) else ("cleanroom contract edits" if has_contract else "code edits")

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
        return {"decision": "continue", "reason": reason}

    state["turn_mutated"] = False
    state["turn_modified_files"] = []
    state["block_count"] = 0
    save_state(state, conv_id=conv_id, state_dir=state_dir)
    return {"decision": "allow", "warning": "Anti-deadlock valve tripped after 2 verification blocks. Exiting despite unverified edits."}
