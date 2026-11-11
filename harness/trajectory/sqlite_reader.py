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

from datetime import datetime
import json
import os
from pathlib import Path
import sqlite3
from typing import Any, Dict, List, Optional, Tuple

from harness.trajectory.health import (
    CRITICAL_BURN_RATE_PER_MIN,
    DEFAULT_CONTEXT_WINDOW_TOKENS,
    MAX_SAFE_BURN_RATE_PER_MIN,
    TrajectoryMetrics,
    get_scaled_thresholds,
    infer_model_context_window,
    is_checkpoint_step,
)
from harness.trajectory.protobuf import (
    extract_compaction_summary_from_protobuf,
    extract_context_window_from_json,
    extract_timestamp_from_protobuf,
    extract_tool_from_protobuf,
    extract_usage_from_protobuf,
    iter_pb_strings,
)
from harness.utils.tokens import estimate_tokens

import time as _time

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


def parse_step_timestamp(val: Any) -> Optional[float]:
    """Parses Unix timestamps, ISO strings, or protobuf metadata bytes to epoch seconds."""
    if val is None:
        return None
    if isinstance(val, (bytes, bytearray)):
        return extract_timestamp_from_protobuf(bytes(val))
    if isinstance(val, (int, float)):
        fval = float(val)
        if fval > 1e14:
            return fval / 1e6
        if fval > 1e11:
            return fval / 1e3
        return fval if fval > 0 else None
    if isinstance(val, str):
        s = val.strip()
        if not s:
            return None
        try:
            return parse_step_timestamp(float(s))
        except ValueError:
            pass
        try:
            return datetime.fromisoformat(s.replace("Z", "+00:00")).timestamp()
        except Exception:
            pass
        try:
            return datetime.strptime(s.split(".")[0], "%Y-%m-%d %H:%M:%S").timestamp()
        except Exception:
            pass
    return None


def _extract_step_fields(
    row: Tuple[Any, ...],
    col_map: Dict[str, int],
    transcript_timestamps: Optional[Dict[int, float]] = None,
) -> Dict[str, Any]:
    """Normalizes one SQLite `steps` row across live protobuf and test JSON schemas."""
    order_col = next(iter(col_map))
    idx_val = int(row[col_map[order_col]])
    st_val = row[col_map["step_type"]] if "step_type" in col_map else None

    data: Dict[str, Any] = {}
    if "step_data" in col_map and isinstance(row[col_map["step_data"]], str):
        try:
            parsed = json.loads(row[col_map["step_data"]])
            if isinstance(parsed, dict):
                data = parsed
                if st_val is None:
                    st_val = data.get("step_type")
        except Exception:
            pass

    meta_raw = row[col_map["metadata"]] if "metadata" in col_map else None
    meta_json: Dict[str, Any] = {}
    pb_ts: Optional[float] = None
    pb_input = pb_cache = pb_est = pb_mct = 0
    pb_model = ""

    if isinstance(meta_raw, str):
        try:
            parsed = json.loads(meta_raw)
            if isinstance(parsed, dict):
                meta_json = parsed
                if st_val is None:
                    st_val = meta_json.get("step_type")
        except Exception:
            pass
    elif isinstance(meta_raw, (bytes, bytearray)):
        meta_bytes = bytes(meta_raw)
        pb_metrics = extract_usage_from_protobuf(meta_bytes)
        pb_input = pb_metrics.input_tokens
        pb_cache = pb_metrics.cache_read_tokens
        pb_est = pb_metrics.estimated_tokens
        pb_mct = pb_metrics.max_context_tokens
        pb_model = pb_metrics.model_name
        pb_ts = extract_timestamp_from_protobuf(meta_bytes)

    auth_tokens = 0
    cache_read = pb_cache
    max_ctx = pb_mct

    if data:
        cwm_est, cwm_mct = extract_context_window_from_json(data)
        max_ctx = max_ctx or cwm_mct
        prompts = (
            data.get("generator_metadata", {}).get("metadata", {}).get("value", {}).get("message_prompts", [])
            if isinstance(data.get("generator_metadata"), dict)
            else []
        )
        if prompts and isinstance(prompts, list) and isinstance(prompts[0], dict):
            nt = prompts[0].get("num_tokens") or prompts[0].get("numTokens") or 0
            if isinstance(nt, (int, float)) and int(nt) > 0:
                auth_tokens = int(nt)
        if auth_tokens == 0:
            for k in ("token_count", "tokens", "num_tokens", "numTokens"):
                val = data.get(k)
                if isinstance(val, (int, float)) and int(val) > 0:
                    auth_tokens = int(val)
                    break
        if auth_tokens == 0 and cwm_est > 0:
            auth_tokens = cwm_est

    if auth_tokens == 0:
        for tk_col in ("token_count", "tokens", "num_tokens", "numTokens"):
            if tk_col in col_map and row[col_map[tk_col]] is not None:
                try:
                    t = int(row[col_map[tk_col]])
                    if t > 0:
                        auth_tokens = t
                        break
                except (ValueError, TypeError):
                    pass

    if auth_tokens == 0 and meta_json:
        cwm_est, cwm_mct = extract_context_window_from_json(meta_json)
        max_ctx = max_ctx or cwm_mct
        in_tok = int(meta_json.get("input_tokens") or meta_json.get("inputTokens") or 0)
        ca_tok = int(meta_json.get("cache_read_tokens") or meta_json.get("cacheReadTokens") or 0)
        if in_tok + ca_tok > 0:
            auth_tokens = in_tok + ca_tok
            cache_read = cache_read or ca_tok
        else:
            for k in ("num_tokens", "numTokens", "tokens", "token_count"):
                val = meta_json.get(k)
                if isinstance(val, (int, float)) and int(val) > 0:
                    auth_tokens = int(val)
                    break
            if auth_tokens == 0 and cwm_est > 0:
                auth_tokens = cwm_est

    if auth_tokens == 0 and pb_input + pb_cache > 0:
        auth_tokens = pb_input + pb_cache
    if auth_tokens == 0 and pb_est > 0:
        auth_tokens = pb_est

    ts: Optional[float] = None
    for ts_col in ("created_at", "timestamp", "time", "ts"):
        if ts_col in col_map and row[col_map[ts_col]] is not None:
            ts = parse_step_timestamp(row[col_map[ts_col]])
            if ts is not None:
                break
    if ts is None and data:
        ts = parse_step_timestamp(data.get("timestamp") or data.get("created_at") or data.get("time") or data.get("createdAt"))
    if ts is None and meta_json:
        ts = parse_step_timestamp(meta_json.get("timestamp") or meta_json.get("created_at") or meta_json.get("time"))
    if ts is None:
        ts = pb_ts
    if ts is None and transcript_timestamps:
        ts = transcript_timestamps.get(idx_val)

    return {
        "idx": idx_val,
        "step_type": st_val,
        "is_checkpoint": is_checkpoint_step(st_val),
        "auth_tokens": auth_tokens,
        "cache_read": cache_read,
        "max_ctx": max_ctx,
        "model": pb_model or str(data.get("model") or meta_json.get("model") or ""),
        "ts": ts,
        "payload_raw": row[col_map["step_payload"]] if "step_payload" in col_map else None,
        "data": data,
        "meta_raw": meta_raw,
        "meta_json": meta_json,
    }


_PROMPT_JSON_KEYS = (
    "lastUserInput",
    "last_user_input",
    "prompt",
    "user_input",
    "userPrompt",
    "user_request",
    "message",
    "text",
    "query",
    "input",
    "content",
)


def _prompt_from_json_val(raw: Any) -> str:
    """Extracts a prompt string from a JSON string/bytes/dict if known prompt keys exist."""
    if isinstance(raw, (bytes, bytearray)):
        if not raw.lstrip().startswith(b"{"):
            return ""
        try:
            raw = json.loads(bytes(raw).decode("utf-8", errors="replace"))
        except Exception:
            return ""
    elif isinstance(raw, str):
        stripped = raw.strip()
        if not stripped.startswith("{"):
            return stripped
        try:
            raw = json.loads(stripped)
        except Exception:
            return ""
    if not isinstance(raw, dict):
        return ""
    for k in _PROMPT_JSON_KEYS:
        v = raw.get(k)
        if isinstance(v, str) and v.strip():
            return v.strip()
    return ""


def _extract_prompt_from_step(parsed: Dict[str, Any]) -> str:
    """Extracts readable prompt text from step_data, step_payload protobuf/JSON, or metadata."""
    for holder in (parsed.get("data"), parsed.get("meta_json")):
        if isinstance(holder, dict) and holder:
            hit = _prompt_from_json_val(holder)
            if hit:
                return hit
    if isinstance(parsed.get("meta_raw"), str):
        hit = _prompt_from_json_val(parsed["meta_raw"])
        if hit:
            return hit
    payload = parsed.get("payload_raw")
    if isinstance(payload, (bytes, bytearray)):
        raw_bytes = bytes(payload)
        if raw_bytes.lstrip().startswith(b"{"):
            return _prompt_from_json_val(raw_bytes)
        strings = [
            s.strip()
            for s in iter_pb_strings(raw_bytes, min_len=3)
            if len(s.strip()) > 3 and not s.strip().startswith("bot-")
        ]
        slash = [s for s in strings if s.lstrip().startswith("/")]
        return slash[0] if slash else (max(strings, key=len) if strings else "")
    if isinstance(payload, str) and payload.strip():
        return _prompt_from_json_val(payload)
    return ""


def _extract_tool_from_step(parsed: Dict[str, Any]) -> Optional[Tuple[str, str]]:
    """Extracts (tool_name, args_str) from a normalized SQLite step record."""
    for holder in (parsed.get("data"), parsed.get("meta_json")):
        if isinstance(holder, dict):
            tn = holder.get("tool_name") or holder.get("tool") or holder.get("name")
            if tn:
                args = holder.get("arguments") or holder.get("command") or holder.get("args") or ""
                return str(tn), str(args)
    for raw in (parsed.get("meta_raw"), parsed.get("payload_raw")):
        if isinstance(raw, (bytes, bytearray)):
            raw_b = bytes(raw)
            if raw_b.lstrip().startswith(b"{"):
                try:
                    d = json.loads(raw_b.decode("utf-8", errors="replace"))
                    if isinstance(d, dict) and (d.get("tool_name") or d.get("tool") or d.get("name")):
                        tn = d.get("tool_name") or d.get("tool") or d.get("name")
                        args = d.get("arguments") or d.get("command") or d.get("args") or ""
                        return str(tn), str(args)
                except Exception:
                    pass
            else:
                tn, args = extract_tool_from_protobuf(raw_b)
                if tn:
                    return tn, args
    return None


def _read_gen_metadata(cursor: sqlite3.Cursor, tables: set[str]) -> Tuple[int, int, int, int, str]:
    """Reads (estimated_tokens, max_context_tokens, usage_tokens, checkpoint_idx, model_name)."""
    if "gen_metadata" not in tables:
        return 0, 0, 0, 0, ""
    cursor.execute("PRAGMA table_info(gen_metadata)")
    cols = {r[1] for r in cursor.fetchall()}
    if "data" not in cols:
        return 0, 0, 0, 0, ""
    order_col = "idx" if "idx" in cols else "rowid"
    cursor.execute(f"SELECT data FROM gen_metadata ORDER BY {order_col} DESC LIMIT 5")
    est = mct = usage = ckpt_idx = 0
    model = ""
    for (raw,) in cursor.fetchall():
        if not raw:
            continue
        if isinstance(raw, str):
            try:
                d = json.loads(raw)
                if isinstance(d, dict):
                    c_est, c_mct = extract_context_window_from_json(d)
                    t = d.get("num_tokens") or d.get("numTokens") or d.get("tokens") or 0
                    est = est or c_est or (int(t) if isinstance(t, (int, float)) else 0)
                    mct = mct or c_mct
                    model = model or str(d.get("model") or "")
            except Exception:
                pass
        elif isinstance(raw, (bytes, bytearray)):
            gm = extract_usage_from_protobuf(bytes(raw))
            est = est or gm.estimated_tokens
            mct = mct or gm.max_context_tokens
            usage = usage or gm.total_prompt_tokens
            ckpt_idx = ckpt_idx or gm.checkpoint_idx
            model = model or gm.model_name
        if est > 0 and mct > 0:
            break
    return est, mct, usage, ckpt_idx, model


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
    if not db_path.is_file():
        cand = Path(conversation_id)
        if cand.is_file():
            db_path = cand
        else:
            return base_metrics

    eff_timeout = min(float(timeout), 0.5) if (timeout is not None and float(timeout) > 0) else 0.5
    conn: Optional[sqlite3.Connection] = None
    try:
        conn = sqlite3.connect(f"file:{db_path.resolve()}?mode=ro", uri=True, timeout=eff_timeout)
        conn.execute("PRAGMA query_only = ON")
        cursor = conn.cursor()

        cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
        tables = {r[0] for r in cursor.fetchall()}

        gen_est, gen_mct, gen_usage, gen_ckpt_idx, gen_model = _read_gen_metadata(cursor, tables)

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

        # Turn 0 & latest USER_INPUT (step_type=14) extraction
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
        if not turn0_prompt and epoch_parsed:
            for item in epoch_parsed[:4]:
                p = _extract_prompt_from_step(item)
                if p:
                    turn0_prompt = p
                    break
        if not latest_user_prompt and epoch_parsed:
            for item in reversed(epoch_parsed[-3:]):
                p = _extract_prompt_from_step(item)
                if p:
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
            gen_for_new_epoch = gen_ckpt_idx >= latest_cp_idx and (gen_ckpt_idx > 0 or len(epoch_parsed) > 0)
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
            except Exception:
                pass


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
