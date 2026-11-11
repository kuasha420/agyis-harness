# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Arafat Zahan (@kuasha420)
# Corporate Stewardship & Infrastructure: Purrfect Software Limited (PSL)
# Governed by: ICARO-42/b Ordinance (Company-Supported Personal IP Framework)

"""
Agyis Harness: PreInvocation Lifecycle Hook & Role-Tailored Compaction Advisory (#83, #109, #110).

Fail-Open Invariants:
- Read-only SQLite access delegated to `harness.trajectory` SSOT.
- Emits valid protojson: `{"injectSteps": []}` or nested `{"systemMessage": {"systemMessage": ..., "metadata": {}}}` / `{"ephemeralMessage": ...}`.
- Process always exits 0.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
import re
import sys
import time
import traceback
from typing import Any, Dict, List, Optional, Tuple, Union

from harness.hooks.role_pinning import (
    CODING_KEYWORDS,
    DEFAULT_ROLE_PINNING_CADENCE,
    NATIVE_SYSTEM_SLASH_COMMANDS,
    ORCHESTRATOR_KEYWORDS,
    ROLE_PERSONA_PROMPTS,
    TEST_RUNNER_KEYWORDS,
    build_compaction_advisory,
    build_post_compaction_persona_prompt,
    build_role_persona_prompt,
    build_role_reanchor_advisory,
    check_pillar_1_intent,
    check_pillar_2_behavior,
    check_pillar_3_explicit_role,
    classify_agent_role,
    get_role_pinning_cadence,
    is_native_slash_command,
    load_sticky_role_state,
    resolve_cid_state_dir,
    resolve_conv_and_brain,
    save_sticky_role_state,
)
from harness.trajectory import (
    CONTEXT_WINDOW_TOKENS,
    ROLE_DEEP_EXECUTION,
    ROLE_FLIGHT_DIRECTOR,
    ROLE_FORENSIC_AUDITOR,
    ROLE_SWARM_ORCHESTRATOR,
    SOFT_EPOCH_STEP_ADVISORY,
    get_scaled_thresholds,
    normalize_cid,
    normalize_role_str,
    read_db_trajectory_state,
)

DEFAULT_COMPACTION_ADVISORY_THRESHOLD: int = 230_000
DEFAULT_SQLITE_TIMEOUT: float = 0.5
MAX_PAYLOAD_BYTES: int = 524_288
EXECUTIONER_HORIZON_STEPS: int = SOFT_EPOCH_STEP_ADVISORY

CALIBRATION_METADATA: Dict[str, Any] = {
    "calibrated_threshold": 230_000,
    "compaction_trigger_min": 227_529,
    "compaction_trigger_max": 262_127,
    "compaction_trigger_avg": 245_941,
    "safety_runway_tokens": 15_941,
    "estimated_runway_turns": "3-6 turns",
    "danger_zone_velocity_per_turn": "2,500 - 4,800 tokens",
}

_normalize_role_str = normalize_role_str
_PROMPT_KEYS = ("lastUserInput", "last_user_input", "prompt", "user_prompt", "userPrompt",
                "message", "text", "query", "input", "initial_prompt", "task", "command",
                "slash_command", "slashCommand", "user_input", "content")


def get_compaction_sqlite_timeout(override: Optional[float] = None) -> float:
    """Returns the effective SQLite connection timeout in seconds (strictly <= 0.5s)."""
    for cand in (override, os.environ.get("AGYIS_SQLITE_TIMEOUT")):
        if cand is not None:
            try:
                val = float(str(cand).strip())
                if val > 0:
                    return min(val, DEFAULT_SQLITE_TIMEOUT)
            except (ValueError, TypeError):
                pass
    return DEFAULT_SQLITE_TIMEOUT


def get_compaction_advisory_threshold(max_context_tokens: Optional[int] = None) -> int:
    """Returns effective compaction advisory threshold with env override and dynamic scaling."""
    env_thresh = os.environ.get("AGYIS_COMPACTION_THRESHOLD") or os.environ.get("PSL_COMPACTION_THRESHOLD")
    if env_thresh:
        try:
            val = int(env_thresh.strip())
            if val > 0:
                return val
        except (ValueError, TypeError):
            pass
    _, red_t = get_scaled_thresholds(max_context_tokens)
    return red_t


def extract_prompt_text(
    payload: Dict[str, Any],
    conversation_id: Optional[str] = None,
    db_dir: Optional[Path] = None,
    timeout: Optional[float] = None,
) -> str:
    """Extracts raw user prompt from incoming payload or latest native-command DB step."""
    for k in _PROMPT_KEYS:
        v = payload.get(k)
        if isinstance(v, str) and v.strip():
            return v.strip()
    steps = payload.get("steps")
    if isinstance(steps, list):
        for s in reversed(steps):
            if isinstance(s, dict):
                for sk in _PROMPT_KEYS:
                    sv = s.get(sk)
                    if isinstance(sv, str) and sv.strip():
                        return sv.strip()
    norm_cid = normalize_cid(conversation_id or "")
    if norm_cid and norm_cid != "default":
        metrics = read_db_trajectory_state(norm_cid, db_dir=db_dir, timeout=get_compaction_sqlite_timeout(timeout))
        if metrics.latest_user_prompt and is_native_slash_command(metrics.latest_user_prompt):
            return metrics.latest_user_prompt
    return ""


def _parse_int_field(payload: Dict[str, Any], keys: Tuple[str, ...]) -> Optional[int]:
    for k in keys:
        if k in payload:
            v = payload[k]
            if isinstance(v, (int, float)):
                return int(v)
            if isinstance(v, str) and v.strip().isdigit():
                return int(v.strip())
    return None


def _resolve_workspace(payload: Dict[str, Any], explicit_ws: Optional[Path]) -> Optional[Path]:
    if explicit_ws is not None:
        return explicit_ws
    for k in ("workspace", "workspacePath", "workspacePaths", "activeWorkspaces", "cwd"):
        wv = payload.get(k)
        s = wv if isinstance(wv, str) else (
            wv[0] if isinstance(wv, (list, tuple)) and wv and isinstance(wv[0], str) else (
                wv[0].get("path") if isinstance(wv, (list, tuple)) and wv and isinstance(wv[0], dict) else None
            )
        )
        if isinstance(s, str) and s.strip():
            return Path(os.path.expanduser(s.strip()))
    return None


def _parse_payload(payload_str: Union[str, bytes, bytearray, Dict[str, Any]]) -> Dict[str, Any]:
    try:
        if isinstance(payload_str, dict):
            return payload_str
        if isinstance(payload_str, (bytes, bytearray)):
            text = bytes(payload_str[:MAX_PAYLOAD_BYTES]).decode("utf-8", errors="replace")
        elif isinstance(payload_str, str):
            text = payload_str[:MAX_PAYLOAD_BYTES]
        else:
            return {}
        parsed = json.loads(text) if text and text.strip() else {}
        return parsed if isinstance(parsed, dict) else {}
    except Exception:
        return {}


def evaluate_pre_invocation(
    payload_str: Union[str, bytes, bytearray, Dict[str, Any]] = "",
    threshold: Optional[int] = None,
    db_dir: Optional[Path] = None,
    workspace_dir: Optional[Path] = None,
    sqlite_timeout: Optional[float] = None,
) -> Dict[str, Any]:
    """Evaluates PreInvocation event for sticky role pinning, soft epoch horizon, and compaction alerts."""
    payload = _parse_payload(payload_str)
    try:
        conv_id, _ = resolve_conv_and_brain(payload, str(payload.get("conversationId") or payload.get("conversation_id") or ""))
        eff_ws = _resolve_workspace(payload, workspace_dir)
        to = get_compaction_sqlite_timeout(sqlite_timeout)
        db_metrics = read_db_trajectory_state(conv_id, db_dir=db_dir, timeout=to) if conv_id != "default" else None

        prompt_text = ""
        for k in _PROMPT_KEYS:
            v = payload.get(k)
            if isinstance(v, str) and v.strip():
                prompt_text = v.strip()
                break
        if not prompt_text and db_metrics and db_metrics.latest_user_prompt and is_native_slash_command(db_metrics.latest_user_prompt):
            prompt_text = db_metrics.latest_user_prompt
        if is_native_slash_command(prompt_text):
            return {"injectSteps": []}

        csm = payload.get("chatStartMetadata") if isinstance(payload.get("chatStartMetadata"), dict) else {}
        cwm = payload.get("contextWindowMetadata") or csm.get("contextWindowMetadata") or {}
        payload_mct = _parse_int_field(payload, ("maxContextTokens", "max_context_tokens")) or (
            _parse_int_field(cwm, ("maxContextTokens", "max_context_tokens")) if isinstance(cwm, dict) else None
        )
        max_ctx = payload_mct or (db_metrics.max_context_tokens if db_metrics else CONTEXT_WINDOW_TOKENS)
        eff_thresh = int(threshold) if threshold is not None else get_compaction_advisory_threshold(max_ctx)
        payload_tokens = _parse_int_field(payload, ("tokens", "token_count", "tokenCount", "num_tokens", "numTokens")) or 0
        tokens = max(db_metrics.tokens if db_metrics else 0, payload_tokens)

        step_count = _parse_int_field(payload, ("step_count", "stepCount", "step", "currentStep", "initialNumSteps", "initial_num_steps", "stepIdx", "step_idx", "invocationNum", "invocation_num"))
        has_explicit_step = step_count is not None
        if db_metrics and db_metrics.checkpoint_count > 0:
            step_count = db_metrics.epoch_steps
            has_explicit_step = True

        stage_role_data = None
        if eff_ws is not None or conv_id != "default":
            try:
                from harness.subagents.stage_role import read_stage_role
                stage_role_data = read_stage_role(
                    eff_ws,
                    conversation_id=conv_id if conv_id != "default" else None,
                )
            except Exception:
                pass
        if not has_explicit_step and stage_role_data is not None:
            step_count = 0
            has_explicit_step = True

        state_dir = resolve_cid_state_dir(conv_id, eff_ws, payload)
        sticky = load_sticky_role_state(state_dir, conv_id)
        epoch_idx = db_metrics.epoch_index if db_metrics else 0

        is_post_compaction = bool(
            re.search(r"#\s*Resuming from a compaction", prompt_text, re.IGNORECASE)
            or payload.get("isPostCompaction")
            or payload.get("resumedFromCompaction")
            or (
                db_metrics
                and db_metrics.checkpoint_count > 0
                and (
                    (sticky is not None and int(sticky.get("epoch", -1)) < epoch_idx)
                    or (sticky is None and db_metrics.epoch_steps == 0)
                )
            )
        )

        role = classify_agent_role(
            payload, conversation_id=conv_id, db_dir=db_dir, workspace_dir=eff_ws,
            tokens=tokens, timeout=to, db_metrics=db_metrics, is_post_compaction=is_post_compaction,
        )
        if state_dir and conv_id != "default" and (not sticky or int(sticky.get("epoch", -1)) != epoch_idx):
            save_sticky_role_state(state_dir, {"conversation_id": conv_id, "epoch": epoch_idx, "role": role, "pinned_at": time.time()})

        cadence = get_role_pinning_cadence()
        cp_rel = f".agents/artifacts/checkpoints/{conv_id}.md" if conv_id != "default" else ".agents/artifacts/checkpoints/session.md"
        inject_steps: List[Dict[str, Any]] = []

        if is_post_compaction:
            inject_steps.append({"systemMessage": {"systemMessage": build_post_compaction_persona_prompt(role, checkpoint_path=cp_rel), "metadata": {}}})
        elif has_explicit_step and step_count == 0:
            inject_steps.append({"systemMessage": {"systemMessage": build_role_persona_prompt(role), "metadata": {}}})
        elif has_explicit_step and step_count is not None and step_count > 0:
            if step_count >= SOFT_EPOCH_STEP_ADVISORY and (step_count == SOFT_EPOCH_STEP_ADVISORY or step_count % cadence == 0):
                reanchor = build_role_reanchor_advisory(role, step_count, cadence)
                soft_adv = f"[AGYIS EPOCH HORIZON ADVISORY: Epoch step {step_count}/{SOFT_EPOCH_STEP_ADVISORY} — consider verifying diff & checkpoints]"
                inject_steps.append({"ephemeralMessage": f"{soft_adv}\n\n{reanchor}"})
            elif step_count % cadence == 0:
                inject_steps.append({"ephemeralMessage": build_role_reanchor_advisory(role, step_count, cadence)})

        alert_file = state_dir / f".compaction_alert_{conv_id}.json" if state_dir and conv_id != "default" else None
        if tokens >= eff_thresh:
            already_alerted = False
            if alert_file and alert_file.is_file():
                try:
                    sdata = json.loads(alert_file.read_text(encoding="utf-8"))
                    already_alerted = (sdata.get("session_id") == conv_id and (time.time() - sdata.get("timestamp", 0) < 900))
                except Exception:
                    pass
            if eff_ws is not None:
                try:
                    from harness.delivery.compaction_checkpoint import generate_compaction_checkpoint
                    cp_target = eff_ws / ".agents" / "artifacts" / "checkpoints" / (f"{conv_id}.md" if conv_id != "default" else "session.md")
                    if not cp_target.is_file() or (time.time() - cp_target.stat().st_mtime) >= 5.0:
                        generate_compaction_checkpoint(workspace_dir=eff_ws, session_id=conv_id if conv_id != "default" else None, orchestrator_role=role, trigger_tokens=eff_thresh)
                except Exception as exc:
                    sys.stderr.write(f"[AGYIS PRE-INVOCATION HOOK] Failed to serialize compaction checkpoint: {exc}\n")
                    sys.stderr.flush()

            if not already_alerted:
                inject_steps.append({"ephemeralMessage": build_compaction_advisory(role, tokens, eff_thresh, max_context_tokens=max_ctx, checkpoint_path=cp_rel)})
                if alert_file and state_dir:
                    try:
                        state_dir.mkdir(parents=True, exist_ok=True)
                        alert_file.write_text(json.dumps({"session_id": conv_id, "tokens": tokens, "threshold": eff_thresh, "timestamp": time.time()}), encoding="utf-8")
                    except OSError:
                        pass
            else:
                inject_steps.append({"ephemeralMessage": f"[AGYIS TOKEN GAUGE: ~{tokens:,} / {max_ctx:,} TOKENS | Compaction Checkpoint Active]"})
        elif alert_file and alert_file.is_file():
            try:
                alert_file.unlink(missing_ok=True)
            except OSError:
                pass

        return {"injectSteps": inject_steps}
    except Exception:
        return {"injectSteps": []}


def main(argv: Optional[List[str]] = None) -> int:
    """Fail-open CLI entrypoint for PreInvocation lifecycle hook."""
    try:
        if hasattr(sys.stdin, "isatty") and sys.stdin.isatty():
            raw_stdin = ""
        elif hasattr(sys.stdin, "buffer"):
            raw_stdin = sys.stdin.buffer.read(MAX_PAYLOAD_BYTES).decode("utf-8", errors="replace")
        else:
            raw_stdin = sys.stdin.read(MAX_PAYLOAD_BYTES)
        res = evaluate_pre_invocation(raw_stdin)
    except Exception as exc:
        sys.stderr.write(f"[PSL PRE-INVOCATION HOOK] Error: {exc}\n")
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
