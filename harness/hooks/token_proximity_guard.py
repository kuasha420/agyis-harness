# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Arafat Zahan (@kuasha420)
# Corporate Stewardship & Infrastructure: Purrfect Software Limited (PSL)
# Governed by: ICARO-42/b Ordinance (Company-Supported Personal IP Framework)

"""
Agyis Harness: PreToolUse Token Proximity Guard Lifecycle Hook (ADR-014 / ADR-035).

Thin PreToolUse adapter delegating all protobuf decoding, SQLite trajectory reads,
compaction epoch splitting, and tok/min burn rate calculations to the canonical
SSOT engine (`harness.trajectory`).

Fail-open invariant:
- Never raises unhandled exceptions.
- sys.stdout always emits valid protojson decision: {"decision": "allow"}.
- Process always exits 0.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
import sqlite3
import sys
from typing import Any, Dict, Optional, TextIO

from harness.trajectory import (
    AMBER_THRESHOLD,
    CHECKPOINT_STEP_TYPE,
    COMPACTION_THRESHOLD,
    CONTEXT_WINDOW_TOKENS,
    CRITICAL_BURN_RATE_PER_MIN,
    MAX_SAFE_BURN_RATE_PER_MIN,
    RED_THRESHOLD,
    ROLE_DEEP_EXECUTION,
    SOFT_EPOCH_STEP_ADVISORY,
    clear_locked_conversations,
    extract_context_window_from_protobuf_metadata,
    extract_tokens_from_protobuf_metadata,
    get_conversations_dir,
    get_scaled_thresholds,
    get_urgency_tier,
    is_checkpoint_step,
    is_conversation_locked,
    normalize_cid as _normalize_cid,
    normalize_role_str as _normalize_role_str,
    parse_protobuf_varint,
    read_db_trajectory_state,
    record_locked_conversation,
    unlock_conversation,
)

LOCK_EXPIRY_SECONDS: float = 2.0


class _LockedConversationsProxy(set):
    """Set-compatible proxy delegating lock state cleanly to harness.trajectory."""

    def __contains__(self, item: object) -> bool:
        return isinstance(item, str) and is_conversation_locked(item)

    def add(self, element: Any) -> None:
        if isinstance(element, str):
            norm = _normalize_cid(element)
            if norm:
                record_locked_conversation(norm)
                super().add(norm)

    def discard(self, element: Any) -> None:
        if isinstance(element, str):
            norm = _normalize_cid(element)
            unlock_conversation(norm)
            super().discard(norm)
            super().discard(element)
        else:
            super().discard(element)

    def remove(self, element: Any) -> None:
        if isinstance(element, str):
            norm = _normalize_cid(element)
            unlock_conversation(norm)
        super().remove(element)

    def clear(self) -> None:
        clear_locked_conversations()
        super().clear()


LOCKED_CONVERSATION_IDS: _LockedConversationsProxy = _LockedConversationsProxy()


def _resolve_telemetry_db_fallback(conversation_id: str, db_dir: Optional[Path]) -> Optional[Path]:
    """Resolves telemetry.db fallback when conversation-specific .db is absent."""
    norm = _normalize_cid(conversation_id)
    base_dir = db_dir or get_conversations_dir()
    if (base_dir / f"{norm}.db").is_file() or Path(conversation_id).is_file():
        return None
    try:
        from harness.telemetry.config import get_telemetry_db_path
        cand = get_telemetry_db_path()
        if cand and cand.is_file():
            return cand
    except Exception:
        pass
    repo_telem = Path(__file__).resolve().parent.parent.parent / "data" / "telemetry.db"
    return repo_telem if repo_telem.is_file() else None


def get_active_conversation_context_window(
    conversation_id: str,
    db_dir: Optional[Path] = None,
    timeout: Optional[float] = None,
) -> Dict[str, Any]:
    """Reads epoch-scoped active tokens and context window thresholds via SSOT."""
    m = read_db_trajectory_state(conversation_id, db_dir=db_dir, timeout=timeout)
    return {
        "tokens": m.tokens,
        "raw_estimated_tokens": m.raw_estimated_tokens,
        "is_provisional": m.is_provisional,
        "max_context_tokens": m.max_context_tokens,
        "amber_threshold": m.amber_threshold,
        "red_threshold": m.red_threshold,
        "compaction_threshold": m.compaction_threshold,
        "has_explicit_max_context": m.has_explicit_max_context,
        "epoch_steps": m.epoch_steps,
        "epoch_start_idx": m.epoch_start_idx,
    }


def get_active_conversation_tokens(
    conversation_id: str,
    db_dir: Optional[Path] = None,
    timeout: Optional[float] = None,
) -> int:
    """Returns latest active-epoch token count from conversation DB (fail-open 0)."""
    return int(read_db_trajectory_state(conversation_id, db_dir=db_dir, timeout=timeout).tokens)


def _velocity_from_telemetry_db(db_path: Path, norm_cid: str, window_seconds: int) -> Dict[str, Any]:
    """Fallback burn-rate calculation against telemetry.db `steps` table by session_id."""
    from harness.trajectory.sqlite_reader import parse_step_timestamp

    conn = sqlite3.connect(f"file:{db_path.resolve()}?mode=ro", uri=True, timeout=0.5)
    try:
        cur = conn.cursor()
        cur.execute(
            "SELECT created_at, step_index FROM steps WHERE session_id = ? ORDER BY step_index ASC",
            (norm_cid,),
        )
        rows = cur.fetchall()
        cur.execute("SELECT total_tokens_est FROM sessions WHERE session_id = ?", (norm_cid,))
        srow = cur.fetchone()
        tot = int(srow[0] or 0) if srow else 0
        ts_list = [t for r in rows if (t := parse_step_timestamp(r[0])) is not None]
        if len(ts_list) >= 2 and tot > 0:
            dur = max(1.0, ts_list[-1] - ts_list[0])
            burn = (tot / dur) * 60.0
            mins = max(0.0, (RED_THRESHOLD - tot) / burn) if burn > 0 else None
            return {
                "tokens": tot,
                "burn_rate_tokens_per_min": burn,
                "mins_to_compaction": mins,
                "mins_to_50k": mins,
                "mins_to_100k": max(0.0, (100000 - tot) / burn) if burn > 0 else None,
                "velocity_tier": "CRITICAL" if burn >= CRITICAL_BURN_RATE_PER_MIN else ("ELEVATED" if burn >= MAX_SAFE_BURN_RATE_PER_MIN else "SAFE"),
                "sample_count": len(ts_list),
                "window_seconds": window_seconds,
                "max_context_tokens": CONTEXT_WINDOW_TOKENS,
                "amber_threshold": AMBER_THRESHOLD,
                "red_threshold": RED_THRESHOLD,
                "compaction_threshold": COMPACTION_THRESHOLD,
            }
    finally:
        conn.close()
    return {}


def _metrics_to_velocity_dict(
    m: Any,
    conversation_id: str,
    db_dir: Optional[Path] = None,
    window_seconds: int = 900,
) -> Dict[str, Any]:
    """Converts TrajectoryMetrics into the velocity payload dict, falling back to telemetry.db when empty."""
    if m.total_steps == 0 and m.tokens == 0:
        telem = _resolve_telemetry_db_fallback(conversation_id, db_dir)
        if telem is not None:
            try:
                fb = _velocity_from_telemetry_db(telem, _normalize_cid(conversation_id), window_seconds)
                if fb:
                    return fb
            except (sqlite3.Error, OSError, ValueError):
                pass
    burn = m.burn_rate_tokens_per_min
    mins_100k = (0.0 if m.tokens >= 100_000 else max(0.0, (100_000 - m.tokens) / burn)) if burn > 0 else None
    return {
        "tokens": m.tokens,
        "burn_rate_tokens_per_min": burn,
        "mins_to_compaction": m.mins_to_compaction,
        "mins_to_50k": m.mins_to_compaction,
        "mins_to_100k": mins_100k,
        "velocity_tier": m.velocity_tier,
        "sample_count": m.sample_count,
        "window_seconds": window_seconds,
        "max_context_tokens": m.max_context_tokens,
        "amber_threshold": m.amber_threshold,
        "red_threshold": m.red_threshold,
        "compaction_threshold": m.compaction_threshold,
        "epoch_steps": m.epoch_steps,
    }


def get_active_conversation_token_velocity(
    conversation_id: str,
    db_dir: Optional[Path] = None,
    window_seconds: int = 900,
) -> Dict[str, Any]:
    """Computes real-time active-epoch burn rate velocity (tokens/min) via SSOT."""
    m = read_db_trajectory_state(conversation_id, db_dir=db_dir, window_seconds=window_seconds)
    return _metrics_to_velocity_dict(m, conversation_id, db_dir=db_dir, window_seconds=window_seconds)


def format_terminal_gauge(
    tokens: int,
    threshold: int = CONTEXT_WINDOW_TOKENS,
    step_count: Optional[int] = None,
    role: Optional[str] = None,
    burn_rate: Optional[float] = None,
    mins_to_compaction: Optional[float] = None,
    velocity_tier: Optional[str] = None,
    amber_threshold: Optional[int] = None,
    red_threshold: Optional[int] = None,
    compaction_threshold: Optional[int] = None,
    is_provisional: bool = False,
) -> str:
    """Formats an ANSI progress gauge with scaled urgency, velocity ETA, and epoch-step advisory."""
    denom = threshold if threshold > 0 else CONTEXT_WINDOW_TOKENS
    scaled_amber, scaled_red = get_scaled_thresholds(denom if denom != CONTEXT_WINDOW_TOKENS else None)
    eff_amber = amber_threshold if amber_threshold is not None else scaled_amber
    eff_red = red_threshold if red_threshold is not None else scaled_red
    eff_comp = compaction_threshold if compaction_threshold is not None else eff_red

    percentage = min(100.0, (tokens / denom) * 100) if denom > 0 else 0.0
    filled_blocks = max(0, min(20, int((tokens / denom) * 20) if denom > 0 else 0))
    bar = "█" * filled_blocks + "░" * (20 - filled_blocks)

    vel_badge = ""
    if burn_rate is not None and burn_rate > 0:
        rate_int = int(round(burn_rate))
        if mins_to_compaction is not None:
            vel_badge = f" (+{rate_int:,} tok/min | ~{int(round(mins_to_compaction))}m to {int(round(eff_comp / 1000))}k)"
        else:
            vel_badge = f" (+{rate_int:,} tok/min)"

    if velocity_tier:
        v_upper = velocity_tier.upper()
        color = "\033[1;31m" if "CRITICAL" in v_upper else ("\033[1;33m" if "ELEVATED" in v_upper else "\033[1;32m")
        status, bell = velocity_tier, ("\a" if "CRITICAL" in v_upper else "")
    elif tokens >= eff_red or (burn_rate is not None and burn_rate >= CRITICAL_BURN_RATE_PER_MIN):
        color = "\033[1;31m"
        status = "CRITICAL (COMPACTION IMMINENT)" if tokens >= eff_red else "CRITICAL"
        bell = "\a"
    elif tokens >= eff_amber or (burn_rate is not None and burn_rate >= MAX_SAFE_BURN_RATE_PER_MIN):
        color, status, bell = "\033[1;33m", ("ELEVATED (APPROACHING THRESHOLD)" if tokens >= eff_amber else "ELEVATED"), ""
    else:
        color, status, bell = "\033[1;32m", "SAFE", ""

    horizon_str = ""
    if step_count is not None and step_count >= SOFT_EPOCH_STEP_ADVISORY and _normalize_role_str(role) == ROLE_DEEP_EXECUTION:
        horizon_str = f" [EPOCH HORIZON: {step_count}/{SOFT_EPOCH_STEP_ADVISORY} STEPS]"

    tok_prefix = "~" if is_provisional else ""
    return f"{bell}{color}[AGYIS TOKEN GAUGE]\033[0m [{bar}] {tok_prefix}{tokens:,} / {denom:,} ({percentage:.1f}%){vel_badge} - {color}{status}\033[0m{horizon_str}"


def render_terminal_gauge(tokens: int) -> str:
    """Convenience alias for format_terminal_gauge(tokens, CONTEXT_WINDOW_TOKENS)."""
    return format_terminal_gauge(tokens, CONTEXT_WINDOW_TOKENS)


def _evaluate_and_emit_gauge(
    metrics: Any,
    vel: Dict[str, Any],
    *,
    step_count: Optional[int],
    role: Optional[str],
    emit_stderr: bool = True,
    out_err: Optional[TextIO] = None,
) -> bool:
    """Formats and emits the ANSI token gauge when runway, horizon, or burn-rate thresholds trigger."""
    tokens = metrics.tokens or int(vel.get("tokens") or 0)
    burn_rate = float(vel.get("burn_rate_tokens_per_min", 0.0) or 0.0)
    horizon_active = (
        step_count is not None
        and step_count >= SOFT_EPOCH_STEP_ADVISORY
        and _normalize_role_str(role) == ROLE_DEEP_EXECUTION
    )
    rapid_burn = burn_rate >= MAX_SAFE_BURN_RATE_PER_MIN
    if not (tokens >= metrics.amber_threshold or horizon_active or rapid_burn):
        return False

    gauge = format_terminal_gauge(
        tokens,
        threshold=metrics.max_context_tokens,
        step_count=step_count,
        role=role,
        burn_rate=burn_rate,
        mins_to_compaction=vel.get("mins_to_compaction"),
        velocity_tier=str(vel.get("velocity_tier", "SAFE")) if rapid_burn and tokens < metrics.amber_threshold else None,
        amber_threshold=metrics.amber_threshold,
        red_threshold=metrics.red_threshold,
        compaction_threshold=metrics.compaction_threshold,
        is_provisional=metrics.is_provisional,
    )
    if emit_stderr:
        target_err = out_err if out_err is not None else sys.stderr
        try:
            target_err.write(f"\n{gauge}\n")
            target_err.flush()
        except OSError:
            pass
    return True


def check_token_proximity(
    conversation_id: str,
    db_dir: Optional[Path] = None,
    emit_stderr: bool = True,
    step_count: Optional[int] = None,
    role: Optional[str] = None,
) -> Dict[str, Any]:
    """Evaluates token proximity, epoch steps, and burn rate velocity via SSOT."""
    metrics = read_db_trajectory_state(conversation_id, db_dir=db_dir)
    vel = _metrics_to_velocity_dict(metrics, conversation_id, db_dir=db_dir)
    tokens = metrics.tokens or int(vel.get("tokens") or 0)
    max_ctx = metrics.max_context_tokens
    amber_t, red_t = metrics.amber_threshold, metrics.red_threshold
    tier = get_urgency_tier(tokens, max_context_tokens=max_ctx)

    eff_epoch_steps = metrics.epoch_steps if metrics.total_steps > 0 else step_count
    warned = _evaluate_and_emit_gauge(
        metrics,
        vel,
        step_count=eff_epoch_steps,
        role=role,
        emit_stderr=emit_stderr,
    )
    return {
        "decision": "allow",
        "tokens": tokens,
        "max_context_tokens": max_ctx,
        "amber_threshold": amber_t,
        "red_threshold": red_t,
        "tier": tier,
        "warned": warned,
        "velocity": vel,
        "epoch_steps": eff_epoch_steps,
        "is_provisional": metrics.is_provisional,
    }


def _extract_payload_step(parsed: Dict[str, Any]) -> Optional[int]:
    for k in ("step_count", "stepCount", "step", "current_step", "currentStep", "step_idx", "stepIdx", "initialNumSteps", "initial_num_steps", "invocationNum", "invocation_num"):
        v = parsed.get(k)
        if isinstance(v, (int, float)):
            return int(v)
        if isinstance(v, str) and v.strip().isdigit():
            return int(v.strip())
    return None


def run_token_proximity_guard(payload: Any, stderr: Optional[TextIO] = None) -> Dict[str, Any]:
    """PreToolUse dispatcher evaluating epoch-scoped tokens, velocity, and step horizon."""
    if isinstance(payload, str):
        try:
            parsed = json.loads(payload) if payload.strip() else {}
        except Exception:
            parsed = {}
    elif isinstance(payload, dict):
        parsed = payload
    else:
        parsed = {}

    conv_id = str(parsed.get("conversationId") or parsed.get("conversation_id") or "default")
    metrics = read_db_trajectory_state(conv_id)
    vel = _metrics_to_velocity_dict(metrics, conv_id)
    raw_step = _extract_payload_step(parsed)
    eff_epoch_steps = (
        max(0, raw_step - metrics.epoch_start_idx) if (raw_step is not None and metrics.epoch_start_idx > 0)
        else (metrics.epoch_steps if metrics.total_steps > 0 else raw_step)
    )
    role = parsed.get("role") or parsed.get("agent_role") or parsed.get("subagent_role") or parsed.get("archetype") or os.environ.get("AGYIS_ROLE") or os.environ.get("PSL_AGENT_ROLE")

    _evaluate_and_emit_gauge(
        metrics,
        vel,
        step_count=eff_epoch_steps,
        role=role,
        emit_stderr=True,
        out_err=stderr,
    )
    return {"decision": "allow"}


def main() -> None:
    """CLI / Hook entrypoint for PreToolUse lifecycle hook."""
    try:
        raw_stdin = sys.stdin.read()
        payload = json.loads(raw_stdin) if raw_stdin.strip() else {}
        if not isinstance(payload, dict):
            payload = {}
    except Exception:
        payload = {}

    conv_id = str(payload.get("conversationId") or payload.get("conversation_id") or "default")
    action = payload.get("action")
    if action == "get_tokens":
        ctx = get_active_conversation_context_window(conv_id)
        tokens, max_ctx = int(ctx["tokens"]), int(ctx["max_context_tokens"])
        print(json.dumps({"status": "ok", "tokens": tokens, "max_context_tokens": max_ctx, "tier": get_urgency_tier(tokens, max_context_tokens=max_ctx)}))
        return
    if action == "get_velocity":
        print(json.dumps({"status": "ok", "velocity": get_active_conversation_token_velocity(conv_id)}))
        return
    if action == "render_gauge":
        raw_max = payload.get("max_context_tokens") or payload.get("maxContextTokens") or payload.get("threshold")
        eff_max = int(raw_max) if raw_max and str(raw_max).isdigit() and int(raw_max) > 0 else CONTEXT_WINDOW_TOKENS
        sc = payload.get("step_count") or payload.get("stepCount")
        print(json.dumps({
            "status": "ok",
            "gauge": format_terminal_gauge(
                int(payload.get("tokens", 0)),
                threshold=eff_max,
                step_count=int(sc) if sc is not None else None,
                role=payload.get("role"),
                burn_rate=float(payload["burn_rate"]) if payload.get("burn_rate") is not None else None,
                mins_to_compaction=float(payload["mins_to_compaction"]) if payload.get("mins_to_compaction") is not None else None,
                velocity_tier=payload.get("velocity_tier"),
            ),
        }))
        return

    run_token_proximity_guard(payload)
    print(json.dumps({"decision": "allow"}))


if __name__ == "__main__":
    main()
