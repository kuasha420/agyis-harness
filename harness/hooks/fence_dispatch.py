# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Arafat Zahan (@kuasha420)
# Corporate Stewardship & Infrastructure: Purrfect Software Limited (PSL)
# Governed by: ICARO-42/b Ordinance (Company-Supported Personal IP Framework)

"""
Subagent Dispatch Truth & Orchestrator Stop Gate Evaluators (ADR-022 / Crosstalk).

Extracted from `fence_gates.py` so Stop gate evaluation and native/legacy/crosstalk
dispatch classification remain cleanly bounded (<650L) and modular.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
import sqlite3
import sys
from typing import Optional

from harness.hooks.fence_state import get_brain_dir, save_state
from harness.hooks.wire_compat import emit_stderr_diagnostic, enqueue_pending_advisory
from harness.subagents.liveness import TEAMWORK_IGNORED_DIRS
from harness.trajectory.transcript_reader import (
    extract_spawned_subagents,
    find_transcript_path,
    load_transcript_steps,
)
from harness.utils.context import (
    get_active_app_data_dir,
    get_active_brain_dir,
    is_in_live_home_gemini,
    is_in_temp_dir,
)


def _emit_stop_deadlock_diagnostic(conv_id: str, msg: str, state_dir: Path | None) -> dict:
    """Emit Stop anti-deadlock diagnostic to stderr and bounded PreInvocation queue without phantom wire keys."""
    emit_stderr_diagnostic(msg)
    enqueue_pending_advisory(conv_id, msg, state_dir=state_dir)
    return {"decision": "allow"}


def _resolve_isolated_native_dirs(
    effective_cwd: Path | str,
    payload: Optional[dict],
    eff_cid: str,
    brain_dir: Optional[Path | str] = None,
) -> tuple[Optional[Path], Optional[Path]]:
    """
    Resolves (brain_root, app_data_dir) for native subagent probing while preventing
    /tmp test workspaces from leaking into host ~/.gemini/antigravity.
    """
    cwd_is_temp = is_in_temp_dir(Path(effective_cwd))
    explicit_brain: Optional[Path] = None
    explicit_app: Optional[Path] = None

    if brain_dir is not None and str(brain_dir).strip():
        cand = Path(os.path.expanduser(str(brain_dir).strip()))
        explicit_brain = cand.parent if cand.name == eff_cid else cand
    elif payload:
        for k in ("brain_dir", "brainDirectory", "brainPath", "artifactDirectoryPath"):
            val = payload.get(k)
            if isinstance(val, str) and val.strip():
                cand = Path(os.path.expanduser(val.strip()))
                explicit_brain = cand.parent if cand.name == eff_cid else cand
                break

    if explicit_brain is None:
        for env_k in ("ANTIGRAVITY_BRAIN_DIR", "GEMINI_BRAIN_DIR"):
            val = (os.environ.get(env_k) or "").strip()
            if val:
                cand = Path(os.path.expanduser(val))
                if not (cwd_is_temp and is_in_live_home_gemini(cand)):
                    explicit_brain = cand.parent if cand.name == eff_cid else cand
                    break

    env_app = (os.environ.get("ANTIGRAVITY_APP_DATA_DIR") or "").strip()
    if env_app:
        cand_app = Path(os.path.expanduser(env_app))
        if not (cwd_is_temp and is_in_live_home_gemini(cand_app)):
            explicit_app = cand_app
            if explicit_brain is None:
                explicit_brain = cand_app / "brain"

    if explicit_brain is None and explicit_app is None:
        if cwd_is_temp:
            return None, None
        return get_active_brain_dir(), get_active_app_data_dir()

    eff_app = explicit_app or (explicit_brain.parent if explicit_brain is not None else None)
    return explicit_brain, eff_app


def _has_crosstalk_handoff(
    effective_cwd: Path | str,
    conv_id: Optional[str] = None,
) -> bool:
    """
    Returns True when this workspace/conversation has an active unconsumed `/crosstalk`
    handover baton in `.agents/artifacts/crosstalk/*.json` originating from `conv_id`.
    """
    crosstalk_dir = Path(effective_cwd) / ".agents" / "artifacts" / "crosstalk"
    if not crosstalk_dir.is_dir():
        return False

    eff_cid = str(conv_id or "").strip()
    try:
        entries = sorted(crosstalk_dir.glob("*.json"))
    except OSError:
        return False

    for path in entries:
        if not path.is_file():
            continue
        try:
            data = json.loads(path.read_text(encoding="utf-8", errors="replace"))
        except (OSError, json.JSONDecodeError, ValueError, TypeError):
            continue
        if not isinstance(data, dict):
            continue
        if data.get("consumed") is True or str(data.get("status") or "").strip().lower() == "consumed":
            continue

        origin = str(
            data.get("from_cid")
            or data.get("origin_cid")
            or data.get("source_cid")
            or data.get("from_conversation_id")
            or ""
        ).strip()
        target = str(data.get("to_cid") or data.get("target_cid") or "").strip()

        if eff_cid and eff_cid != "default":
            if origin == eff_cid:
                return True
            if not origin and path.name == f"outbound_{eff_cid}.json":
                return True
            if target == eff_cid:
                continue
        else:
            if path.name.startswith(("inbound_", "outbound_", "handoff_")) or origin:
                return True
    return False


def _classify_dispatched_subagents(
    effective_cwd: Path | str,
    payload: Optional[dict],
    *,
    conv_id: Optional[str] = None,
    brain_dir: Optional[Path | str] = None,
) -> str:
    """Classifies subagent dispatches as 'legacy', 'native', or 'none' (ignoring crosstalk batons)."""
    teamwork_dir = Path(effective_cwd) / ".agents" / "teamwork"
    if teamwork_dir.is_dir():
        try:
            for child in teamwork_dir.iterdir():
                if (
                    child.is_dir()
                    and not child.name.startswith(".")
                    and child.name not in TEAMWORK_IGNORED_DIRS
                    and child.name != "crosstalk"
                ):
                    return "legacy"
        except OSError as exc:
            sys.stderr.write(f"[AGYIS FENCE] Warning: Failed reading teamwork dir '{teamwork_dir}': {exc}\n")

    if payload and (payload.get("subagents_dispatched") or payload.get("dispatched_subagents")):
        return "legacy"

    eff_cid = str(
        conv_id
        or (payload.get("conversationId") or payload.get("conversation_id") if isinstance(payload, dict) else "")
        or ""
    ).strip()
    if not eff_cid or eff_cid == "default":
        return "none"

    eff_brain, eff_app = _resolve_isolated_native_dirs(
        effective_cwd, payload, eff_cid, brain_dir=brain_dir
    )
    if eff_brain is None and eff_app is None:
        return "none"

    # a. Native swarm plan.json
    if eff_brain is not None:
        plan_path = eff_brain / eff_cid / ".system_generated" / "swarm" / "plan.json"
        if plan_path.is_file():
            try:
                plan_data = json.loads(plan_path.read_text(encoding="utf-8", errors="replace"))
                if isinstance(plan_data, dict):
                    for key in ("workers", "members", "agents", "nodes"):
                        items = plan_data.get(key)
                        if isinstance(items, (list, dict)) and len(items) > 0:
                            return "native"
            except (OSError, json.JSONDecodeError, ValueError, TypeError):
                pass

        # b. Native transcript inspection (invoke_subagent / run_workflow / swarm add / manage_subagents spawn)
        t_path, resolved_id = find_transcript_path(eff_cid, brain_dir=eff_brain)
        if t_path is not None:
            steps, _, _ = load_transcript_steps(t_path)
            if extract_spawned_subagents(steps, parent_cid=resolved_id):
                return "native"
            for step in steps:
                if not isinstance(step, dict):
                    continue
                raw_tcs = step.get("tool_calls") or step.get("toolCalls") or []
                if not isinstance(raw_tcs, list):
                    continue
                for tc in raw_tcs:
                    if not isinstance(tc, dict):
                        continue
                    t_name = str(tc.get("name") or "").strip()
                    if t_name in ("invoke_subagent", "run_workflow"):
                        return "native"
                    t_args = tc.get("args") or tc.get("arguments") or {}
                    if isinstance(t_args, str):
                        try:
                            t_args = json.loads(t_args)
                        except (json.JSONDecodeError, ValueError, TypeError):
                            t_args = {}
                    if not isinstance(t_args, dict):
                        continue
                    action_val = str(t_args.get("action") or t_args.get("Action") or "").strip().lower()
                    if t_name in ("swarm", "swarm_manage") and action_val == "add":
                        return "native"
                    if t_name == "manage_subagents" and action_val in ("spawn", "create", "start", "add", "launch"):
                        return "native"

    # c. Read-only conversation_summaries.db check (0.2s timeout)
    if eff_app is not None:
        summaries_db = eff_app / "conversation_summaries.db"
        if summaries_db.is_file():
            try:
                conn = sqlite3.connect(f"file:{summaries_db.resolve()}?mode=ro", uri=True, timeout=0.2)
                try:
                    cur = conn.execute(
                        "SELECT 1 FROM conversation_summaries WHERE parent_conversation_id = ? LIMIT 1",
                        (eff_cid,),
                    )
                    if cur.fetchone() is not None:
                        return "native"
                finally:
                    conn.close()
            except sqlite3.Error:
                pass

    return "none"


def _has_dispatched_subagents(
    effective_cwd: Path | str,
    payload: Optional[dict],
    *,
    conv_id: Optional[str] = None,
    brain_dir: Optional[Path | str] = None,
) -> bool:
    """Returns True when subagents were dispatched via teamwork dirs, payload metadata, or native Antigravity tools."""
    return _classify_dispatched_subagents(effective_cwd, payload, conv_id=conv_id, brain_dir=brain_dir) != "none"


def _evaluate_orchestrator_stop(
    state: dict,
    effective_cwd: Path | str,
    conv_id: str,
    state_dir: Path | None,
    brain_dir: Path | str | None,
    payload: Optional[dict],
) -> dict:
    """Evaluates Pause Gate, Crosstalk Handover, Persona Truth Gate (legacy), and Gate 2 Auditor Verdict Fence."""
    from harness.subagents.truth import (
        has_active_native_subagents,
        is_pause_gate_active,
        validate_transition_payload_truth,
    )

    ws_path = Path(effective_cwd)
    if is_pause_gate_active(ws_path):
        return {"decision": "allow"}

    if _has_crosstalk_handoff(ws_path, conv_id=conv_id):
        return {"decision": "allow"}

    dispatch_mode = _classify_dispatched_subagents(effective_cwd, payload, conv_id=conv_id, brain_dir=brain_dir)
    if dispatch_mode == "none":
        return {"decision": "allow"}

    allow_synth = bool(os.environ.get("AGYIS_SYNTHETIC_TEST") == "1")
    auditor_fence_disabled = (
        os.environ.get("PSL_AUDITOR_FENCE_DISABLED", "").lower() in ("1", "true", "yes")
        or os.environ.get("PSL_SOLO_MODE", "").lower() in ("1", "true", "yes")
    )
    truth_brain_root, _ = _resolve_isolated_native_dirs(effective_cwd, payload, conv_id, brain_dir=brain_dir)

    def _enforce_gate2(verdict_reason: str, guidance: str) -> dict:
        block_count = state.get("gate2_block_count", 0)
        if block_count < 2:
            state["gate2_block_count"] = block_count + 1
            save_state(state, conv_id=conv_id, state_dir=state_dir)
            return {
                "decision": "continue",
                "reason": f"Dual-Gate Verification Fence (Gate 2): {verdict_reason}. {guidance}",
            }
        state["gate2_block_count"] = 0
        save_state(state, conv_id=conv_id, state_dir=state_dir)
        return _emit_stop_deadlock_diagnostic(
            conv_id,
            "Anti-deadlock valve tripped after 2 Gate 2 verification blocks. Exiting despite missing/rejected auditor verdict.",
            state_dir,
        )

    if dispatch_mode == "native":
        from harness.subagents.verdict import validate_audit_verdict
        effective_brain_dir = get_brain_dir(conv_id=conv_id, payload=payload, brain_dir=brain_dir)
        is_verdict_valid, verdict_reason, _ = validate_audit_verdict(
            ws_path, brain_dir=effective_brain_dir, allow_synthetic=allow_synth,
        )
        if is_verdict_valid:
            state["block_count"] = 0
            state["gate2_block_count"] = 0
            save_state(state, conv_id=conv_id, state_dir=state_dir)
            return {"decision": "allow"}
        if (not state.get("code_dirty") and not state.get("spec_dirty")) or auditor_fence_disabled:
            return {"decision": "allow"}
        if has_active_native_subagents(ws_path, brain_dir=truth_brain_root, conv_id=conv_id):
            return {"decision": "allow"}
        return _enforce_gate2(
            verdict_reason,
            "Native subagents modified files; run agyis audit certify before claiming completion.",
        )

    is_truth_valid, truth_errors = validate_transition_payload_truth(
        ws_path, brain_dir=truth_brain_root, conv_id=conv_id, allow_synthetic=allow_synth,
    )
    if not is_truth_valid:
        block_count = state.get("block_count", 0)
        if block_count < 2:
            state["block_count"] = block_count + 1
            save_state(state, conv_id=conv_id, state_dir=state_dir)
            detail = (
                "; ".join(truth_errors)
                if truth_errors
                else "no verified psl_stage_transition_payload.json was found on disk"
            )
            return {
                "decision": "continue",
                "reason": (
                    f"Persona Truth Violation: {detail}. "
                    "Subagents were dispatched in this session; root orchestrators cannot declare "
                    "completion without verified delegate artifacts (Anti-Code-Monkey Invariant)."
                ),
            }
        state["block_count"] = 0
        save_state(state, conv_id=conv_id, state_dir=state_dir)
        return _emit_stop_deadlock_diagnostic(
            conv_id,
            "Anti-deadlock valve tripped after 2 verification blocks. Exiting despite persona truth violation.",
            state_dir,
        )

    if not auditor_fence_disabled:
        from harness.subagents.verdict import validate_audit_verdict
        effective_brain_dir = get_brain_dir(conv_id=conv_id, payload=payload, brain_dir=brain_dir)
        is_verdict_valid, verdict_reason, _ = validate_audit_verdict(
            ws_path, brain_dir=effective_brain_dir, allow_synthetic=allow_synth,
        )
        if not is_verdict_valid:
            return _enforce_gate2(
                verdict_reason,
                "Root orchestrators and coordinators require independent out-of-band auditor "
                "clearance (agyis audit certify) before claiming milestone completion.",
            )
        state["gate2_block_count"] = 0
        save_state(state, conv_id=conv_id, state_dir=state_dir)

    return {"decision": "allow"}
