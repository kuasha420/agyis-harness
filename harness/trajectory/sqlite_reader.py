# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Arafat Zahan (@kuasha420)
# Corporate Stewardship & Infrastructure: Purrfect Software Limited (PSL)
# Governed by: ICARO-42/b Ordinance (Company-Supported Personal IP Framework)

"""
Canonical Read-Only Antigravity Conversation SQLite Reader (ADR-035).

Single Source of Truth for:
- Epoch boundary detection (checkpoint step_type 23)
- Authoritative UsageMetadata (input + cacheRead) vs bounded provisional fallback
- Real per-epoch burn rate velocity (decoding protobuf timestamps + transcript fallback)
- Turn 0 & latest USER_INPUT (step_type=14) extraction
"""

from __future__ import annotations

import os
from pathlib import Path
import sqlite3
import sys
import time as _time
from typing import Any, Dict, List, Optional, Tuple

from harness.trajectory.health import (
    CRITICAL_BURN_RATE_PER_MIN,
    DEFAULT_CONTEXT_WINDOW_TOKENS,
    MAX_SAFE_BURN_RATE_PER_MIN,
    TrajectoryMetrics,
    get_scaled_thresholds,
    infer_model_context_window,
)
from harness.trajectory.protobuf import extract_compaction_summary_from_protobuf
from harness.trajectory.sqlite_step_parser import (
    _PB_UINT64_SENTINEL,
    _extract_prompt_from_step,
    _extract_step_fields,
    _extract_tool_from_step,
    _is_sdk_injection_text,
    _read_gen_metadata,
    parse_step_timestamp,
)
from harness.utils.context import get_app_data_dir_candidates
from harness.utils.tokens import estimate_tokens

MAX_LOCKED_CIDS: int = 256
LOCK_EXPIRY_SECONDS: float = 2.0
_LOCKED_CONVERSATIONS: Dict[str, float] = {}


def normalize_cid(conversation_id: str) -> str:
    """Strips suffixes like .db or .jsonl from conversation identifiers."""
    cid = (conversation_id or "").strip()
    for suffix in (".db", ".jsonl"):
        if cid.endswith(suffix):
            cid = cid[: -len(suffix)]
    return cid


def get_conversations_dir() -> Path:
    """Resolves directory containing Antigravity conversation SQLite DBs."""
    env_dir = (
        os.environ.get("AGYIS_CONVERSATIONS_DIR")
        or os.environ.get("ANTIGRAVITY_CONVERSATIONS_DIR")
        or os.environ.get("GEMINI_CONVERSATIONS_DIR")
    )
    if env_dir and env_dir.strip():
        return Path(env_dir.strip())
    env_app_data = os.environ.get("ANTIGRAVITY_APP_DATA_DIR")
    if env_app_data and env_app_data.strip():
        return Path(env_app_data.strip()) / "conversations"
    return Path.home() / ".gemini" / "antigravity" / "conversations"


def record_locked_conversation(cid: str) -> None:
    """Tracks a temporarily locked conversation DB with strict capacity bounds."""
    norm = normalize_cid(cid)
    if not norm:
        return
    if len(_LOCKED_CONVERSATIONS) >= MAX_LOCKED_CIDS:
        oldest = next(iter(_LOCKED_CONVERSATIONS))
        _LOCKED_CONVERSATIONS.pop(oldest, None)
    _LOCKED_CONVERSATIONS[norm] = _time.monotonic()


def is_conversation_locked(cid: str) -> bool:
    """Returns True if conversation DB recently raised sqlite3.OperationalError within TTL."""
    norm = normalize_cid(cid)
    if not norm:
        return False
    ts = _LOCKED_CONVERSATIONS.get(norm)
    if ts is None:
        return False
    if _time.monotonic() - ts < LOCK_EXPIRY_SECONDS:
        return True
    _LOCKED_CONVERSATIONS.pop(norm, None)
    return False


def clear_locked_conversations() -> None:
    """Clears the bounded locked-DB registry."""
    _LOCKED_CONVERSATIONS.clear()


def unlock_conversation(cid: str) -> None:
    """Removes a single conversation ID from the locked-DB registry."""
    norm = normalize_cid(cid)
    if norm:
        _LOCKED_CONVERSATIONS.pop(norm, None)


def _extract_subagent_prompt_from_101(
    cursor: sqlite3.Cursor,
    cols_sql: str,
    col_map: Dict[str, int],
    order_col: str,
    *,
    ascending: bool,
) -> str:
    """Extracts subagent parent task prompts from step_type=101 while excluding PreInvocation SDK injections."""
    direction = "ASC" if ascending else "DESC"
    cursor.execute(f"SELECT {cols_sql} FROM steps WHERE step_type = 101 ORDER BY {order_col} {direction} LIMIT 16")
    for row in cursor.fetchall():
        parsed = _extract_step_fields(row, col_map)
        src = str(parsed["data"].get("source") or parsed["meta_json"].get("source") or "").strip().upper()
        if src == "SYSTEM_SDK":
            continue
        prompt = _extract_prompt_from_step(parsed)
        if not prompt or _is_sdk_injection_text(prompt):
            continue
        if "[Message]" in prompt or "Message from Parent Agent" in prompt:
            return prompt
    return ""


def _compute_velocity(
    epoch_rows: List[Dict[str, Any]],
    compaction_threshold: int,
    active_tokens: int,
    window_seconds: int,
) -> Tuple[float, Optional[float], str, int]:
    """Calculates per-epoch burn rate (tokens/min) strictly within active epoch samples."""
    samples = [(r["ts"], r["auth_tokens"]) for r in epoch_rows if r["ts"] is not None and r["auth_tokens"] > 0]
    if len(samples) < 2:
        return 0.0, None, "SAFE", len(samples)

    latest_ts = samples[-1][0]
    windowed = [s for s in samples if s[0] >= latest_ts - float(window_seconds)]
    if len(windowed) < 2:
        windowed = samples

    delta_tok = windowed[-1][1] - windowed[0][1]
    delta_s = windowed[-1][0] - windowed[0][0]
    burn_rate = (float(delta_tok) / float(delta_s)) * 60.0 if delta_tok > 0 and delta_s > 0 else 0.0

    mins_to_comp: Optional[float] = None
    if burn_rate > 0:
        mins_to_comp = 0.0 if active_tokens >= compaction_threshold else max(0.0, (compaction_threshold - active_tokens) / burn_rate)

    if burn_rate >= CRITICAL_BURN_RATE_PER_MIN:
        tier = "CRITICAL"
    elif burn_rate >= MAX_SAFE_BURN_RATE_PER_MIN:
        tier = "ELEVATED"
    else:
        tier = "SAFE"
    return burn_rate, mins_to_comp, tier, len(windowed)


def read_db_trajectory_state(
    conversation_id: str,
    db_dir: Optional[Path] = None,
    timeout: Optional[float] = None,
    window_seconds: int = 900,
    transcript_timestamps: Optional[Dict[int, float]] = None,
) -> TrajectoryMetrics:
    """Reads authoritative epoch-scoped trajectory metrics from a conversation SQLite DB."""
    norm_cid = normalize_cid(conversation_id)
    base_metrics = TrajectoryMetrics(conversation_id=norm_cid)
    if not norm_cid or norm_cid == "default" or is_conversation_locked(norm_cid):
        return base_metrics

    db_path = (db_dir or get_conversations_dir()) / f"{norm_cid}.db"
    try:
        if not db_path.is_file() and db_dir is None and not (
            os.environ.get("AGYIS_CONVERSATIONS_DIR")
            or os.environ.get("ANTIGRAVITY_CONVERSATIONS_DIR")
            or os.environ.get("GEMINI_CONVERSATIONS_DIR")
            or os.environ.get("ANTIGRAVITY_APP_DATA_DIR")
        ):
            for app_dir in get_app_data_dir_candidates():
                cand_db = app_dir / "conversations" / f"{norm_cid}.db"
                if cand_db.is_file():
                    db_path = cand_db
                    break
        if not db_path.is_file():
            cand = Path(conversation_id)
            if cand.is_file():
                db_path = cand
            else:
                return base_metrics
    except (PermissionError, OSError):
        return base_metrics

    eff_timeout = min(float(timeout), 0.5) if (timeout is not None and float(timeout) > 0) else 0.5
    conn: Optional[sqlite3.Connection] = None
    try:
        conn = sqlite3.connect(f"file:{db_path.resolve()}?mode=ro", uri=True, timeout=eff_timeout)
        conn.execute("PRAGMA query_only = ON")
        cursor = conn.cursor()

        cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
        tables = {r[0] for r in cursor.fetchall()}

        gen_est, gen_mct, gen_usage, gen_ckpt_idx, gen_model, tb_extras = _read_gen_metadata(cursor, tables)

        if "steps" not in tables:
            resolved_max = gen_mct or infer_model_context_window(gen_model) or DEFAULT_CONTEXT_WINDOW_TOKENS
            amber_t, red_t = get_scaled_thresholds(resolved_max)
            raw_est = max(gen_est, gen_usage)
            active = min(raw_est, resolved_max) if raw_est > 0 else 0
            return TrajectoryMetrics(
                conversation_id=norm_cid,
                tokens=active,
                raw_estimated_tokens=raw_est,
                is_provisional=active > 0 and gen_usage == 0,
                max_context_tokens=resolved_max,
                has_explicit_max_context=gen_mct > 0,
                model_name=gen_model,
                amber_threshold=amber_t,
                red_threshold=red_t,
                compaction_threshold=red_t,
            )

        cursor.execute("PRAGMA table_info(steps)")
        step_cols = {r[1] for r in cursor.fetchall()}
        order_col = "idx" if "idx" in step_cols else ("step_index" if "step_index" in step_cols else ("id" if "id" in step_cols else "rowid"))

        select_cols = [order_col]
        for col in ("step_type", "created_at", "timestamp", "time", "ts", "token_count", "tokens", "num_tokens", "numTokens", "step_data", "step_payload", "metadata"):
            if col in step_cols and col not in select_cols:
                select_cols.append(col)
        col_map = {c: i for i, c in enumerate(select_cols)}
        cols_sql = ", ".join(select_cols)

        has_step_type = "step_type" in step_cols
        cursor.execute("SELECT COUNT(*) FROM steps")
        total_steps = int(cursor.fetchone()[0] or 0)

        checkpoint_count = 0
        latest_cp_row: Optional[Dict[str, Any]] = None
        epoch_step_count = total_steps
        if has_step_type:
            cursor.execute("SELECT COUNT(*) FROM steps WHERE step_type = 23")
            checkpoint_count = int(cursor.fetchone()[0] or 0)
            cursor.execute(f"SELECT {cols_sql} FROM steps WHERE step_type = 23 ORDER BY {order_col} DESC LIMIT 1")
            raw_cp = cursor.fetchone()
            if raw_cp:
                latest_cp_row = _extract_step_fields(raw_cp, col_map, transcript_timestamps)
                cursor.execute(f"SELECT COUNT(*) FROM steps WHERE {order_col} > ?", (latest_cp_row["idx"],))
                epoch_step_count = int(cursor.fetchone()[0] or 0)
                cursor.execute(f"SELECT {cols_sql} FROM steps WHERE {order_col} > ? ORDER BY {order_col} DESC LIMIT 500", (latest_cp_row["idx"],))
                raw_epoch_rows = list(reversed(cursor.fetchall()))
            else:
                cursor.execute(f"SELECT {cols_sql} FROM steps ORDER BY {order_col} DESC LIMIT 500")
                raw_epoch_rows = list(reversed(cursor.fetchall()))
        else:
            cursor.execute(f"SELECT {cols_sql} FROM steps ORDER BY {order_col} DESC LIMIT 500")
            all_recent = [_extract_step_fields(r, col_map, transcript_timestamps) for r in reversed(cursor.fetchall())]
            cp_indices = [i for i, item in enumerate(all_recent) if item["is_checkpoint"]]
            checkpoint_count = len(cp_indices)
            if cp_indices:
                latest_cp_row = all_recent[cp_indices[-1]]
                epoch_parsed = all_recent[cp_indices[-1] + 1 :]
                epoch_step_count = len(epoch_parsed)
            else:
                epoch_parsed = all_recent
            raw_epoch_rows = []

        if has_step_type:
            epoch_parsed = [_extract_step_fields(r, col_map, transcript_timestamps) for r in raw_epoch_rows]

        # Turn 0 & latest USER_INPUT (step_type=14) or subagent step_type=101 [Message] extraction
        turn0_prompt = latest_user_prompt = ""
        if has_step_type:
            cursor.execute(f"SELECT {cols_sql} FROM steps WHERE step_type = 14 ORDER BY {order_col} ASC LIMIT 1")
            r0 = cursor.fetchone()
            if r0:
                turn0_prompt = _extract_prompt_from_step(_extract_step_fields(r0, col_map))
            cursor.execute(f"SELECT {cols_sql} FROM steps WHERE step_type = 14 ORDER BY {order_col} DESC LIMIT 1")
            rl = cursor.fetchone()
            if rl:
                latest_user_prompt = _extract_prompt_from_step(_extract_step_fields(rl, col_map))
            if not turn0_prompt:
                turn0_prompt = _extract_subagent_prompt_from_101(cursor, cols_sql, col_map, order_col, ascending=True)
            if not latest_user_prompt:
                latest_user_prompt = _extract_subagent_prompt_from_101(cursor, cols_sql, col_map, order_col, ascending=False)
        _NON_PROMPT_STEP_TYPES = frozenset({15, 17, 23, 90, 101, 132})
        if not turn0_prompt and epoch_parsed:
            for item in epoch_parsed[:4]:
                st_i = item.get("step_type")
                p = _extract_prompt_from_step(item)
                if not p or _is_sdk_injection_text(p):
                    continue
                if st_i == 101:
                    src = str(item["data"].get("source") or item["meta_json"].get("source") or "").strip().upper()
                    if src != "SYSTEM_SDK" and ("[Message]" in p or "Message from Parent Agent" in p):
                        turn0_prompt = p
                        break
                    continue
                if st_i in _NON_PROMPT_STEP_TYPES:
                    continue
                turn0_prompt = p
                break
        if not latest_user_prompt and epoch_parsed:
            for item in reversed(epoch_parsed[-3:]):
                st_i = item.get("step_type")
                p = _extract_prompt_from_step(item)
                if not p or _is_sdk_injection_text(p):
                    continue
                if st_i == 101:
                    src = str(item["data"].get("source") or item["meta_json"].get("source") or "").strip().upper()
                    if src != "SYSTEM_SDK" and ("[Message]" in p or "Message from Parent Agent" in p):
                        latest_user_prompt = p
                        break
                    continue
                if st_i in _NON_PROMPT_STEP_TYPES:
                    continue
                latest_user_prompt = p
                break

        recent_tools_list: List[Tuple[str, str]] = []
        for item in epoch_parsed:
            t_pair = _extract_tool_from_step(item)
            if t_pair is not None:
                recent_tools_list.append(t_pair)
        if not recent_tools_list and "tool_calls" in tables:
            cursor.execute("PRAGMA table_info(tool_calls)")
            t_cols = {r[1] for r in cursor.fetchall()}
            n_col = "tool_name" if "tool_name" in t_cols else ("name" if "name" in t_cols else None)
            a_col = "arguments" if "arguments" in t_cols else ("command" if "command" in t_cols else "''")
            if n_col:
                cursor.execute(f"SELECT {n_col}, {a_col} FROM tool_calls LIMIT 500")
                for row_t in cursor.fetchall():
                    if row_t[0]:
                        recent_tools_list.append((str(row_t[0]), str(row_t[1] or "")))

        auth_tokens = 0
        auth_cache = 0
        step_mct = 0
        step_model = ""
        for item in reversed(epoch_parsed):
            if item["is_checkpoint"]:
                continue
            step_mct = step_mct or item["max_ctx"]
            step_model = step_model or item["model"]
            if auth_tokens == 0 and item["auth_tokens"] > 0:
                auth_tokens = item["auth_tokens"]
                auth_cache = item["cache_read"]

        model_name = gen_model or step_model
        has_explicit_max = (gen_mct > 0) or (step_mct > 0)
        resolved_max = gen_mct or step_mct or infer_model_context_window(model_name) or DEFAULT_CONTEXT_WINDOW_TOKENS
        amber_t, red_t = get_scaled_thresholds(resolved_max)

        comp_summary = ""
        if latest_cp_row is not None:
            cp_raw = latest_cp_row.get("payload_raw")
            if isinstance(cp_raw, (bytes, bytearray)):
                comp_summary = extract_compaction_summary_from_protobuf(bytes(cp_raw))
            elif isinstance(cp_raw, str):
                comp_summary = cp_raw.strip()
            elif isinstance(latest_cp_row.get("data"), dict):
                comp_summary = str(latest_cp_row["data"].get("summary") or latest_cp_row["data"].get("content") or "")

        is_provisional = False
        raw_estimated = gen_est
        latest_cp_idx = latest_cp_row["idx"] if latest_cp_row is not None else -1

        if auth_tokens > 0:
            active_tokens = auth_tokens
        elif latest_cp_row is not None:
            valid_gen_ckpt = 0 <= gen_ckpt_idx < _PB_UINT64_SENTINEL
            gen_for_new_epoch = (
                valid_gen_ckpt
                and gen_ckpt_idx >= latest_cp_idx
                and (gen_ckpt_idx > 0 or len(epoch_parsed) > 0)
            )
            if gen_for_new_epoch and gen_usage > 0:
                active_tokens = gen_usage
            elif gen_for_new_epoch and gen_est > 0:
                active_tokens = min(gen_est, resolved_max)
                is_provisional = True
            else:
                post_cp_est = sum(estimate_tokens(_extract_prompt_from_step(item)) for item in epoch_parsed)
                summary_est = estimate_tokens(comp_summary) if len(comp_summary) >= 50 else 0
                combined = summary_est + post_cp_est
                if combined > 0:
                    active_tokens = min(combined, resolved_max)
                    raw_estimated = max(raw_estimated, combined)
                    is_provisional = True
                else:
                    active_tokens = 0
        else:
            if gen_usage > 0:
                active_tokens = gen_usage
            elif gen_est > 0:
                active_tokens = min(gen_est, resolved_max)
                is_provisional = True
            else:
                active_tokens = 0

        burn_rate, mins_to_comp, vel_tier, sample_cnt = _compute_velocity(
            epoch_parsed, red_t, active_tokens, window_seconds
        )

        return TrajectoryMetrics(
            conversation_id=norm_cid,
            tokens=active_tokens,
            raw_estimated_tokens=raw_estimated,
            is_provisional=is_provisional,
            cache_read_tokens=auth_cache,
            max_context_tokens=resolved_max,
            has_explicit_max_context=has_explicit_max,
            total_steps=total_steps,
            epoch_steps=epoch_step_count,
            epoch_index=checkpoint_count,
            epoch_start_idx=(latest_cp_idx + 1) if latest_cp_row is not None else 0,
            checkpoint_count=checkpoint_count,
            compaction_summary=comp_summary,
            turn0_prompt=turn0_prompt,
            latest_user_prompt=latest_user_prompt,
            model_name=model_name,
            burn_rate_tokens_per_min=burn_rate,
            mins_to_compaction=mins_to_comp,
            velocity_tier=vel_tier,
            sample_count=sample_cnt,
            amber_threshold=amber_t,
            red_threshold=red_t,
            compaction_threshold=red_t,
            recent_tools=tuple(recent_tools_list),
            extras=dict(tb_extras, has_token_breakdown=1 if tb_extras else 0),
        )
    except sqlite3.OperationalError:
        record_locked_conversation(norm_cid)
        return base_metrics
    except (sqlite3.Error, OSError, ValueError, TypeError, KeyError, IndexError):
        return base_metrics
    finally:
        if conn is not None:
            try:
                conn.close()
            except sqlite3.Error as exc:
                sys.stderr.write(f"[AGYIS TRAJECTORY] Failed closing SQLite connection: {exc}\n")


_CUMULATIVE_STEP_KEYS = (
    "step_count", "stepCount", "step", "current_step", "currentStep",
    "step_idx", "stepIdx", "initialNumSteps", "initial_num_steps",
    "invocationNum", "invocation_num",
)


def resolve_epoch_step_count(
    payload: Optional[Dict[str, Any]] = None,
    conv_id: str = "default",
    explicit_step: Optional[int] = None,
    db_metrics: Optional[TrajectoryMetrics] = None,
    db_dir: Optional[Path] = None,
    timeout: Optional[float] = None,
) -> Optional[int]:
    """Resolves active-epoch step depth, replacing raw cumulative step counts across checkpoints."""
    if explicit_step is not None:
        return int(explicit_step)
    epoch_step: Optional[int] = None
    cum_step: Optional[int] = None
    if isinstance(payload, dict):
        for ek in ("epoch_steps", "epochSteps"):
            val = payload.get(ek)
            if isinstance(val, (int, float)):
                epoch_step = int(val)
                break
            if isinstance(val, str) and val.strip().isdigit():
                epoch_step = int(val.strip())
                break
        for k in _CUMULATIVE_STEP_KEYS:
            val = payload.get(k)
            if isinstance(val, (int, float)):
                cum_step = int(val)
                break
            if isinstance(val, str) and val.strip().isdigit():
                cum_step = int(val.strip())
                break
    if epoch_step is not None:
        return epoch_step
    norm_cid = normalize_cid(conv_id)
    if norm_cid and norm_cid != "default":
        metrics = db_metrics if db_metrics is not None else read_db_trajectory_state(norm_cid, db_dir=db_dir, timeout=timeout)
        if metrics.checkpoint_count > 0:
            return metrics.epoch_steps
        if cum_step is None and metrics.total_steps > 0:
            return metrics.epoch_steps
    return cum_step
