# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Arafat Zahan (@kuasha420)
# Corporate Stewardship & Infrastructure: Purrfect Software Limited (PSL)
# Governed by: ICARO-42/b Ordinance (Company-Supported Personal IP Framework)

"""
Agyis Harness: PreInvocation Lifecycle Hook & Role-Tailored Compaction Advisory (#83, #109, #110).

Fail-Open Invariants:
- Read-only SQLite access delegated to `harness.trajectory` SSOT.
- Emits valid protojson: `{"injectSteps": []}` or nested `{"systemMessage": {"systemMessage": ..., "metadata": {}}}`.
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
    classify_agent_role_details,
    get_role_pinning_cadence,
    has_parent_conversation,
    is_native_slash_command,
    load_sticky_role_state,
    resolve_cid_state_dir,
    resolve_conv_and_brain,
    save_sticky_role_state,
)
from harness.hooks.wire_compat import (
    build_system_message_step,
    drain_pending_advisories,
    drain_pending_advisory_steps,
)
from harness.trajectory import (
    CONTEXT_WINDOW_TOKENS,
    ROLE_DEEP_EXECUTION,
    ROLE_FLIGHT_DIRECTOR,
    ROLE_FORENSIC_AUDITOR,
    ROLE_SWARM_ORCHESTRATOR,
    SOFT_CHECKPOINT_STEP_ADVISORY,
    get_scaled_step_horizon,
    get_scaled_thresholds,
    infer_model_context_window,
    normalize_cid,
    normalize_role_str,
    read_db_trajectory_state,
    resolve_checkpoint_step_count,
)
from harness.utils.state import atomic_write_json, sanitize_conv_id
from harness.ux.pills import conversation_pill

DEFAULT_COMPACTION_ADVISORY_THRESHOLD: int = 230_000
DEFAULT_SQLITE_TIMEOUT: float = 0.5
MAX_PAYLOAD_BYTES: int = 10_485_760
EXECUTIONER_HORIZON_STEPS: int = SOFT_CHECKPOINT_STEP_ADVISORY

CALIBRATION_METADATA: Dict[str, Any] = {
    "calibrated_threshold": 230_000,
    "compaction_trigger_min": 227_529,
    "compaction_trigger_max": 262_127,
    "compaction_trigger_avg": 245_941,
    "safety_runway_tokens": 15_941,
    "estimated_runway_turns": "3-6 turns",
    "danger_zone_velocity_per_turn": "2,500 - 4,800 tokens",
}

_ORIG_CLASSIFY_AGENT_ROLE = classify_agent_role
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


def _has_native_compaction_marker(text: str) -> bool:
    """Detects manual /compact resume headers and Antigravity native auto-compaction <CONTEXT_SUMMARY> frames."""
    if not text or not isinstance(text, str):
        return False
    if re.search(r"#\s*Resuming from a compaction", text, re.IGNORECASE):
        return True
    if "<CONTEXT_SUMMARY>" in text and (
        text.lstrip().startswith("<CONTEXT_SUMMARY>")
        or "RESUMING MY OWN TASK" in text
        or "summary of the conversation history" in text.lower()
    ):
        return True
    return False


def extract_prompt_text(
    payload: Dict[str, Any],
    conversation_id: Optional[str] = None,
    db_dir: Optional[Path] = None,
    timeout: Optional[float] = None,
    *,
    db_metrics: Optional[Any] = None,
) -> str:
    """Extracts raw user prompt from incoming payload, payload steps, or DB slash/compaction prompt."""
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
    metrics = db_metrics
    if metrics is None and norm_cid and norm_cid != "default":
        metrics = read_db_trajectory_state(norm_cid, db_dir=db_dir, timeout=get_compaction_sqlite_timeout(timeout))
    latest = getattr(metrics, "latest_user_prompt", "") if metrics is not None else ""
    if latest and (is_native_slash_command(latest) or _has_native_compaction_marker(latest)):
        return latest
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
    except (json.JSONDecodeError, ValueError, TypeError):
        return {}


def _should_emit_horizon_advisory(
    state_dir: Path,
    conv_id: str,
    cp_idx: int,
    step_count: int,
    horizon: int,
    horizon_cadence: int,
) -> bool:
    """Gates checkpoint horizon advisories through a CID-scoped cooldown state file."""
    alert_path = state_dir / f".horizon_alert_{sanitize_conv_id(conv_id)}.json"
    existing: Dict[str, Any] = {}
    if alert_path.is_file():
        try:
            parsed = json.loads(alert_path.read_text(encoding="utf-8"))
            if isinstance(parsed, dict):
                existing = parsed
        except (OSError, json.JSONDecodeError, ValueError, TypeError):
            existing = {}

    prev_cp = existing.get("checkpoint")
    prev_horizon = existing.get("horizon")
    prev_step = existing.get("last_step")
    same_window = (
        isinstance(prev_cp, int)
        and prev_cp == cp_idx
        and isinstance(prev_horizon, int)
        and prev_horizon == horizon
        and isinstance(prev_step, int)
    )
    if same_window and (step_count - prev_step) < horizon_cadence:
        return False

    try:
        state_dir.mkdir(parents=True, exist_ok=True)
        atomic_write_json(
            alert_path,
            {
                "session_id": conv_id,
                "checkpoint": cp_idx,
                "horizon": horizon,
                "last_step": step_count,
                "timestamp": time.time(),
            },
        )
    except OSError:
        pass
    return True


def _collect_workspaces(payload: Dict[str, Any], explicit_ws: Optional[Path]) -> List[Path]:
    """Collects ordered unique workspace paths without falling back to CWD."""
    cands: List[Path] = []
    seen: set[str] = set()
    raw_items: List[Any] = [str(explicit_ws)] if explicit_ws is not None else []
    raw_items.extend(payload.get(k) for k in ("workspace", "workspacePath", "cwd"))
    for k in ("workspacePaths", "activeWorkspaces", "workspace_paths", "active_workspaces"):
        if isinstance((lst := payload.get(k)), (list, tuple)):
            raw_items.extend(lst)
    for item in raw_items:
        raw = item if isinstance(item, str) else (item.get("path") if isinstance(item, dict) else None)
        if isinstance(raw, str) and raw.strip():
            p = Path(os.path.expanduser(raw.strip()))
            if str(p) not in seen:
                seen.add(str(p))
                cands.append(p)
    return cands


def is_session_start_event(payload: Dict[str, Any]) -> bool:
    """Returns True when payload represents a SessionStart lifecycle hook invocation."""
    if not isinstance(payload, dict):
        return False
    event = str(
        payload.get("hookEventName") or payload.get("hookEvent") or payload.get("hook_event") or payload.get("event") or ""
    ).strip().lower().replace("-", "").replace("_", "")
    return event == "sessionstart"


def _read_baton_json(path: Path) -> Optional[Dict[str, Any]]:
    try:
        if not path.is_file() or not (0 < path.stat().st_size <= 131_072):
            return None
        data = json.loads(path.read_text(encoding="utf-8", errors="replace"))
        return data if isinstance(data, dict) else None
    except (OSError, json.JSONDecodeError, ValueError):
        return None


def _mark_baton_consumed(path: Path, data: Dict[str, Any], conv_id: str) -> None:
    updated = dict(data)
    updated["consumed"] = True
    updated["consumed_at"] = time.time()
    if conv_id and conv_id != "default":
        updated["consumed_by"] = conv_id
    try:
        atomic_write_json(path, updated, indent=2)
    except OSError as exc:
        sys.stderr.write(f"[AGYIS SESSION START] Warning: Failed marking baton consumed '{path}': {exc}\n")


def _is_fresh_latest_baton(data: Dict[str, Any], path: Path, max_age_s: float = 3600.0) -> bool:
    from datetime import datetime
    ts: Optional[float] = None
    for tk in ("created_at", "timestamp", "createdAt", "ts"):
        val = data.get(tk)
        if isinstance(val, (int, float)) and not isinstance(val, bool) and val > 0:
            fval = float(val)
            ts = fval / 1e6 if fval > 1e14 else (fval / 1e3 if fval > 1e11 else fval)
            break
        if isinstance(val, str) and val.strip():
            try:
                ts = float(val.strip())
                break
            except ValueError:
                try:
                    ts = datetime.fromisoformat(val.strip().replace("Z", "+00:00")).timestamp()
                    break
                except (ValueError, TypeError):
                    pass
    if ts is None:
        try:
            ts = path.stat().st_mtime
        except OSError:
            return False
    return (time.time() - ts) <= max_age_s


def _latest_baton_matches_workspaces(data: Dict[str, Any], ws: Path, active_ws: List[Path]) -> bool:
    declared: List[str] = [
        v.strip() for k in ("to_workspace", "target_workspace", "workspace_path", "workspace")
        if isinstance((v := data.get(k)), str) and v.strip()
    ]
    for item in (data.get("workspacePaths") or data.get("workspace_paths") or []):
        raw = item if isinstance(item, str) else (item.get("path") if isinstance(item, dict) else None)
        if isinstance(raw, str) and raw.strip():
            declared.append(raw.strip())
    if not declared:
        return True
    active_resolved = {ws.resolve()}
    for aws in active_ws:
        try:
            active_resolved.add(aws.resolve())
        except OSError:
            pass
    for raw_p in declared:
        dp = Path(os.path.expanduser(raw_p))
        try:
            if dp.resolve() in active_resolved:
                return True
        except OSError:
            if str(dp) == str(ws):
                return True
    return False


def _consume_inbound_baton(conv_id: str, workspaces: List[Path]) -> Optional[Tuple[Dict[str, Any], Path, Path]]:
    """Finds and atomically marks one unconsumed inbound crosstalk baton as consumed."""
    for ws in workspaces:
        xt_dir = ws / ".agents" / "artifacts" / "crosstalk"
        if not xt_dir.is_dir():
            continue
        consumed_sig: Optional[Tuple[Any, Any, Any]] = None
        if conv_id and conv_id != "default":
            cands = list(dict.fromkeys([xt_dir / f"inbound_{sanitize_conv_id(conv_id)}.json", xt_dir / f"inbound_{conv_id}.json"]))
            for cand in cands:
                if (data := _read_baton_json(cand)) is None:
                    continue
                if data.get("consumed") or data.get("consumed_at") or data.get("consumed_by"):
                    consumed_sig = (
                        data.get("baton_id"),
                        str(data.get("from_cid") or data.get("origin_cid") or data.get("source_cid") or "").strip(),
                        data.get("created_at") or data.get("timestamp"),
                    )
                    continue
                _mark_baton_consumed(cand, data, conv_id)
                return data, cand, ws

        latest_path = xt_dir / "inbound_latest.json"
        if (data := _read_baton_json(latest_path)) is None:
            continue
        if data.get("consumed") or data.get("consumed_at") or data.get("consumed_by"):
            continue
        target_cid = str(data.get("target_cid") or data.get("to_cid") or data.get("conversation_id") or "").strip()
        from_cid = str(data.get("from_cid") or data.get("origin_cid") or data.get("source_cid") or "").strip()
        if (target_cid and conv_id != "default" and target_cid != conv_id) or (from_cid and conv_id != "default" and from_cid == conv_id):
            continue
        sig = (data.get("baton_id"), from_cid, data.get("created_at") or data.get("timestamp"))
        if consumed_sig is not None and any(consumed_sig) and sig == consumed_sig:
            continue
        if not _is_fresh_latest_baton(data, latest_path) or not _latest_baton_matches_workspaces(data, ws, workspaces):
            continue
        _mark_baton_consumed(latest_path, data, conv_id)
        return data, latest_path, ws
    return None


def _build_crosstalk_session_boot_step(baton: Dict[str, Any], baton_file: Path, ws: Path) -> Dict[str, Any]:
    """Formats one-shot user_markdown handover banner and compact model systemMessage."""
    from_cid = str(baton.get("from_cid") or baton.get("origin_cid") or baton.get("source_cid") or "").strip()
    from_title = str(baton.get("from_title") or baton.get("origin_title") or baton.get("title") or "Origin").strip() or "Origin"
    from_proj = str(baton.get("from_project") or baton.get("source_project") or baton.get("from_repo") or "").strip()
    to_proj = str(baton.get("to_project") or baton.get("target_project") or baton.get("to_repo") or ws.name or "workspace").strip()
    hop, max_hops = int(baton.get("hop", 1) or 1), int(baton.get("max_hops", 2) or 2)
    role_hint = str(baton.get("role_hint") or baton.get("role") or "").strip()
    cp_raw = str(baton.get("checkpoint_path") or baton.get("checkpoint") or "").strip()
    baton_ref = str(baton.get("baton_path") or baton.get("artifact_path") or baton_file).strip()
    intent = str(baton.get("intent") or baton.get("summary") or "").strip()
    redacted_flag = bool(baton.get("redacted")) or bool(str(baton.get("redaction_summary") or "").strip())

    safe_origin_title = (
        re.sub(r"\s+", " ", re.sub(r"[\r\n\t\x00-\x1f\x7f]+", " ", from_title))
        .strip()
        .replace("[", "(")
        .replace("]", ")")[:120]
        or "Origin"
    )
    if from_cid:
        try:
            origin_pill = conversation_pill(from_cid, from_title, surface="desktop")
        except ValueError:
            origin_pill = safe_origin_title
    else:
        origin_pill = safe_origin_title
    proj_badge = f"`{from_proj}` -> `{to_proj}`" if from_proj else f"`{to_proj}`"
    privacy_badge = " · Redacted OK" if redacted_flag else ""
    cp_pill = ""
    if cp_raw:
        cp_url = cp_raw if cp_raw.startswith(("file://", "http://", "https://")) else f"file://{Path(cp_raw) if Path(cp_raw).is_absolute() else (ws / cp_raw)}"
        cp_pill = f" · [Checkpoint]({cp_url})"

    user_markdown = f"> **Crosstalk Baton** from {origin_pill} ({proj_badge} · Hop `{hop}/{max_hops}`{privacy_badge}){cp_pill}"
    model_lines = [
        "[AGYIS CROSSTALK SESSION BOOT]",
        f"Role Hint: {role_hint or 'general'} | Hop Budget: {hop}/{max_hops} (remaining: {max(0, max_hops - hop)})",
        f"Baton Artifact: {baton_ref}" + (f" | Checkpoint: {cp_raw}" if cp_raw else ""),
    ]
    if intent:
        model_lines.append(f"Intent: {intent[:160]}")
    return build_system_message_step("\n".join(model_lines), user_markdown=user_markdown)


def _drain_cid_pending_steps(conv_id: str, state_dir: Optional[Path]) -> List[Dict[str, Any]]:
    has_state_env = any((os.environ.get(k) or "").strip() for k in ("AGYIS_HARNESS_STATE_DIR", "PSL_HARNESS_STATE_DIR", "PLUGIN_DATA"))
    if conv_id == "default" and not has_state_env:
        return []
    steps = drain_pending_advisory_steps(conv_id)
    if state_dir is not None and conv_id != "default":
        for extra in drain_pending_advisory_steps(conv_id, state_dir=state_dir):
            if extra not in steps:
                steps.append(extra)
    return steps


def evaluate_session_start(
    payload_str: Union[str, bytes, bytearray, Dict[str, Any]] = "",
    db_dir: Optional[Path] = None,
    workspace_dir: Optional[Path] = None,
    sqlite_timeout: Optional[float] = None,
) -> Dict[str, Any]:
    """Evaluates SessionStart for one-shot inbound crosstalk handover banners and queued advisories."""
    payload = _parse_payload(payload_str)
    try:
        conv_id, brain_path = resolve_conv_and_brain(payload, str(payload.get("conversationId") or payload.get("conversation_id") or ""))
        eff_ws, workspaces = _resolve_workspace(payload, workspace_dir), _collect_workspaces(payload, workspace_dir)
        state_dir = resolve_cid_state_dir(conv_id, eff_ws, payload) or (brain_path / ".agyis" if brain_path else None)
        inject_steps: List[Dict[str, Any]] = []

        if (consumed := _consume_inbound_baton(conv_id, workspaces)) is not None:
            baton, baton_file, matched_ws = consumed
            inject_steps.append(_build_crosstalk_session_boot_step(baton, baton_file, matched_ws))
            raw_role = str(baton.get("role_hint") or baton.get("role") or "").strip()
            norm_role = normalize_role_str(raw_role) if raw_role else None
            if norm_role and state_dir and conv_id != "default" and not load_sticky_role_state(state_dir, conv_id):
                ag_name = raw_role if raw_role.lower() not in (
                    ROLE_DEEP_EXECUTION, ROLE_FLIGHT_DIRECTOR, ROLE_FORENSIC_AUDITOR, ROLE_SWARM_ORCHESTRATOR,
                ) else None
                save_sticky_role_state(state_dir, {
                    "conversation_id": conv_id, "checkpoint": 0, "role": norm_role,
                    "agent_name": ag_name, "parent_conversation_id": None,
                    "source": "crosstalk_baton", "is_fallback": False, "pinned_at": time.time(),
                })

        inject_steps.extend(_drain_cid_pending_steps(conv_id, state_dir))
        return {"injectSteps": inject_steps}
    except Exception as exc:
        sys.stderr.write(f"[AGYIS SESSION START] Unexpected evaluation error: {exc}\n")
        return {"injectSteps": []}


def evaluate_pre_invocation(
    payload_str: Union[str, bytes, bytearray, Dict[str, Any]] = "",
    threshold: Optional[int] = None,
    db_dir: Optional[Path] = None,
    workspace_dir: Optional[Path] = None,
    sqlite_timeout: Optional[float] = None,
) -> Dict[str, Any]:
    """Evaluates PreInvocation (and SessionStart) events for handover banners, role pinning, and compaction alerts."""
    payload = _parse_payload(payload_str)
    if is_session_start_event(payload):
        return evaluate_session_start(
            payload,
            db_dir=db_dir,
            workspace_dir=workspace_dir,
            sqlite_timeout=sqlite_timeout,
        )
    try:
        conv_id, brain_path = resolve_conv_and_brain(payload, str(payload.get("conversationId") or payload.get("conversation_id") or ""))
        eff_ws = _resolve_workspace(payload, workspace_dir)
        to = get_compaction_sqlite_timeout(sqlite_timeout)
        db_metrics = read_db_trajectory_state(conv_id, db_dir=db_dir, timeout=to) if conv_id != "default" else None

        prompt_text = extract_prompt_text(
            payload, conversation_id=conv_id, db_dir=db_dir, timeout=to, db_metrics=db_metrics
        )
        if is_native_slash_command(prompt_text):
            return {"injectSteps": []}

        csm = payload.get("chatStartMetadata") if isinstance(payload.get("chatStartMetadata"), dict) else {}
        cwm = payload.get("contextWindowMetadata") or csm.get("contextWindowMetadata") or {}
        payload_mct = _parse_int_field(payload, ("maxContextTokens", "max_context_tokens")) or (
            _parse_int_field(cwm, ("maxContextTokens", "max_context_tokens")) if isinstance(cwm, dict) else None
        )
        payload_model = str(
            payload.get("model")
            or payload.get("modelName")
            or payload.get("model_name")
            or csm.get("model")
            or csm.get("modelName")
            or ""
        ).strip()
        if payload_mct:
            max_ctx = payload_mct
        elif db_metrics and db_metrics.has_explicit_max_context:
            max_ctx = db_metrics.max_context_tokens
        elif payload_model and not (db_metrics and db_metrics.model_name):
            max_ctx = infer_model_context_window(payload_model)
        elif db_metrics:
            max_ctx = db_metrics.max_context_tokens
        else:
            max_ctx = CONTEXT_WINDOW_TOKENS
        eff_thresh = int(threshold) if threshold is not None else get_compaction_advisory_threshold(max_ctx)
        payload_tokens = _parse_int_field(payload, ("tokens", "token_count", "tokenCount", "num_tokens", "numTokens")) or 0
        tokens = max(db_metrics.tokens if db_metrics else 0, payload_tokens)

        step_count = resolve_checkpoint_step_count(payload, conv_id=conv_id, db_metrics=db_metrics)
        has_explicit_step = step_count is not None

        stage_role_data = None
        if eff_ws is not None or conv_id != "default":
            try:
                from harness.subagents.stage_role import read_stage_role
                stage_role_data = read_stage_role(
                    eff_ws,
                    conversation_id=conv_id if conv_id != "default" else None,
                )
            except Exception as exc:
                sys.stderr.write(f"[AGYIS PRE-INVOCATION HOOK] Failed reading stage role: {exc}\n")
        stage_num = int(stage_role_data.get("stage", 0) or 0) if stage_role_data else -1
        stage_cid = str(stage_role_data.get("conversation_id") or "").strip() if stage_role_data else ""
        stage_matches_cid = stage_role_data is not None and (conv_id == "default" or stage_cid == conv_id)
        if not has_explicit_step and stage_matches_cid:
            step_count = 0
            has_explicit_step = True

        state_dir = resolve_cid_state_dir(conv_id, eff_ws, payload) or (brain_path / ".agyis" if brain_path else None)
        sticky = load_sticky_role_state(state_dir, conv_id)
        payload_cp_idx = _parse_int_field(payload, ("checkpoint_index", "checkpointIndex"))
        cp_idx = (
            db_metrics.checkpoint_index
            if (db_metrics and db_metrics.total_steps > 0)
            else (payload_cp_idx if payload_cp_idx is not None else 0)
        )

        is_post_compaction = bool(
            _has_native_compaction_marker(prompt_text)
            or (db_metrics and _has_native_compaction_marker(db_metrics.latest_user_prompt))
            or payload.get("isPostCompaction")
            or payload.get("resumedFromCompaction")
            or (
                db_metrics
                and db_metrics.checkpoint_count > 0
                and (
                    (sticky is not None and int(sticky.get("checkpoint", sticky.get("epoch", -1))) < cp_idx)
                    or (sticky is None and db_metrics.checkpoint_steps == 0)
                )
            )
        )

        if classify_agent_role is not _ORIG_CLASSIFY_AGENT_ROLE:
            role = classify_agent_role(
                payload, conversation_id=conv_id, db_dir=db_dir, workspace_dir=eff_ws,
                tokens=tokens, timeout=to, db_metrics=db_metrics, is_post_compaction=is_post_compaction,
            )
            role_meta: Dict[str, Any] = {"agent_name": None, "parent_conversation_id": None, "source": "custom", "is_fallback": False}
        else:
            role, role_meta = classify_agent_role_details(
                payload, conversation_id=conv_id, db_dir=db_dir, workspace_dir=eff_ws,
                tokens=tokens, timeout=to, db_metrics=db_metrics, is_post_compaction=is_post_compaction,
            )

        agent_name = role_meta.get("agent_name")
        parent_cid = role_meta.get("parent_conversation_id")
        role_source = str(role_meta.get("source") or "unknown")
        is_fallback = bool(role_meta.get("is_fallback", False))

        if state_dir and conv_id != "default":
            needs_persist = (
                not sticky
                or int(sticky.get("checkpoint", sticky.get("epoch", -1))) != cp_idx
                or normalize_role_str(sticky.get("role")) != role
                or (agent_name is not None and sticky.get("agent_name") != agent_name)
                or (parent_cid is not None and sticky.get("parent_conversation_id") != parent_cid)
                or (bool(sticky.get("is_fallback")) and not is_fallback)
                or ("source" not in sticky)
            )
            if needs_persist:
                save_sticky_role_state(
                    state_dir,
                    {
                        "conversation_id": conv_id,
                        "checkpoint": cp_idx,
                        "role": role,
                        "agent_name": agent_name,
                        "parent_conversation_id": parent_cid,
                        "source": role_source,
                        "is_fallback": is_fallback,
                        "pinned_at": time.time(),
                    },
                )

        cadence = get_role_pinning_cadence()
        cp_rel = f".agents/artifacts/checkpoints/{conv_id}.md" if conv_id != "default" else ".agents/artifacts/checkpoints/session.md"
        inject_steps: List[Dict[str, Any]] = []

        if is_post_compaction:
            inject_steps.append(build_system_message_step(build_post_compaction_persona_prompt(role, checkpoint_path=cp_rel)))
        elif has_explicit_step and step_count == 0:
            inject_steps.append(build_system_message_step(build_role_persona_prompt(role)))
        elif has_explicit_step and step_count is not None and step_count > 0:
            horizon = get_scaled_step_horizon(max_ctx)
            horizon_cadence = max(25, horizon // 4)
            emit_horizon = False
            if step_count >= horizon:
                if conv_id == "default" or state_dir is None:
                    emit_horizon = (step_count == horizon or step_count % cadence == 0)
                else:
                    emit_horizon = _should_emit_horizon_advisory(
                        state_dir, conv_id, cp_idx, step_count, horizon, horizon_cadence
                    )
            if emit_horizon:
                reanchor = build_role_reanchor_advisory(role, step_count, cadence)
                soft_adv = f"[AGYIS CHECKPOINT HORIZON ADVISORY: Checkpoint step {step_count}/{horizon} — consider verifying diff & checkpoints]"
                inject_steps.append(build_system_message_step(f"{soft_adv}\n\n{reanchor}"))
            elif step_count % cadence == 0:
                inject_steps.append(build_system_message_step(build_role_reanchor_advisory(role, step_count, cadence)))

        is_specialist_stage = bool(stage_role_data and stage_num > 0 and conv_id != "default" and stage_cid == conv_id)
        eff_brain_parent = brain_path.parent if (brain_path is not None and brain_path.name == conv_id) else None
        is_subagent = bool(parent_cid) or has_parent_conversation(payload, conv_id, brain_dir=eff_brain_parent, db_dir=db_dir) or is_specialist_stage
        alert_file = state_dir / f".compaction_alert_{conv_id}.json" if state_dir and conv_id != "default" else None
        existing_alert: Dict[str, Any] = {}
        if alert_file and alert_file.is_file():
            try:
                parsed_alert = json.loads(alert_file.read_text(encoding="utf-8"))
                if isinstance(parsed_alert, dict):
                    existing_alert = parsed_alert
            except (OSError, json.JSONDecodeError, ValueError) as exc:
                sys.stderr.write(f"[AGYIS PRE-INVOCATION HOOK] Failed reading alert state '{alert_file}': {exc}\n")
        if tokens >= eff_thresh:
            already_alerted = bool(
                existing_alert
                and existing_alert.get("session_id") == conv_id
                and int(existing_alert.get("checkpoint", existing_alert.get("epoch", -1))) == cp_idx
                and existing_alert.get("active", True)
                and (time.time() - existing_alert.get("timestamp", 0) < 900)
            )
            if eff_ws is not None:
                try:
                    from harness.delivery.compaction_checkpoint import generate_compaction_checkpoint
                    cp_target = eff_ws / ".agents" / "artifacts" / "checkpoints" / (f"{conv_id}.md" if conv_id != "default" else "session.md")
                    if not cp_target.is_file() or (time.time() - cp_target.stat().st_mtime) >= 5.0:
                        generate_compaction_checkpoint(
                            workspace_dir=eff_ws,
                            session_id=conv_id if conv_id != "default" else None,
                            orchestrator_role=role,
                            trigger_tokens=eff_thresh,
                            brain_dir=brain_path,
                        )
                except Exception as exc:
                    sys.stderr.write(f"[AGYIS PRE-INVOCATION HOOK] Failed to serialize compaction checkpoint: {exc}\n")
                    sys.stderr.flush()

            if not already_alerted:
                inject_steps.append(build_system_message_step(build_compaction_advisory(role, tokens, eff_thresh, max_context_tokens=max_ctx, checkpoint_path=cp_rel, is_subagent=is_subagent)))
                if alert_file and state_dir:
                    try:
                        state_dir.mkdir(parents=True, exist_ok=True)
                        raw_hist = existing_alert.get("alerted_checkpoints") or existing_alert.get("alerted_epochs")
                        hist = raw_hist if isinstance(raw_hist, list) else []
                        alerted_checkpoints = sorted({int(x) for x in hist if isinstance(x, (int, float))} | {cp_idx})
                        alert_file.write_text(json.dumps({
                            "session_id": conv_id, "checkpoint": cp_idx, "active": True,
                            "tokens": tokens, "threshold": eff_thresh, "timestamp": time.time(),
                            "alerted_checkpoints": alerted_checkpoints,
                        }), encoding="utf-8")
                    except OSError:
                        pass
            else:
                gauge_tag = "Subagent Auto-Compaction Ready" if is_subagent else "Compaction Checkpoint Active"
                inject_steps.append(build_system_message_step(f"[AGYIS TOKEN GAUGE: ~{tokens:,} / {max_ctx:,} TOKENS | {gauge_tag}]"))
        elif alert_file and alert_file.is_file():
            try:
                updated = dict(existing_alert)
                if "alerted_checkpoints" not in updated and isinstance(updated.get("alerted_epochs"), list):
                    updated["alerted_checkpoints"] = list(updated["alerted_epochs"])
                updated.update({"session_id": conv_id, "checkpoint": cp_idx, "active": False, "tokens": tokens, "cleared_at": time.time()})
                alert_file.write_text(json.dumps(updated), encoding="utf-8")
            except OSError:
                pass

        inject_steps.extend(_drain_cid_pending_steps(conv_id, state_dir))

        return {"injectSteps": inject_steps}
    except Exception as exc:
        sys.stderr.write(f"[AGYIS PRE-INVOCATION HOOK] Unexpected evaluation error: {exc}\n")
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
        sys.stderr.write(f"[AGYIS PRE-INVOCATION HOOK] Error: {exc}\n")
        traceback.print_exc(file=sys.stderr)
        sys.stderr.flush()
        res = {"injectSteps": []}
    try:
        sys.stdout.write(json.dumps(res) + "\n")
        sys.stdout.flush()
    except OSError as exc:
        sys.stderr.write(f"[AGYIS PRE-INVOCATION HOOK] Failed writing stdout: {exc}\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
