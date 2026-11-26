# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Arafat Zahan (@kuasha420)
# Corporate Stewardship & Infrastructure: Purrfect Software Limited (PSL)
# Governed by: ICARO-42/b Ordinance (Company-Supported Personal IP Framework)

"""
SQLite Step Field, Timestamp, Prompt, and Gen-Metadata Parsers (ADR-035).

Leaf parser submodule extracted from `sqlite_reader.py` to maintain AFF limits
and centralize PreInvocation SDK injection filtering for subagent prompts.
"""

from __future__ import annotations

from datetime import datetime
import json
import sqlite3
from typing import Any, Dict, Optional, Tuple

from harness.trajectory.health import is_checkpoint_step
from harness.trajectory.protobuf import (
    extract_context_window_from_json,
    extract_timestamp_from_protobuf,
    extract_token_breakdown_from_protobuf,
    extract_tool_from_protobuf,
    extract_usage_from_protobuf,
    iter_pb_strings,
)

_PB_UINT64_SENTINEL: int = (1 << 63) - 1

_SDK_INJECTION_MARKERS: Tuple[str, ...] = (
    "injected by a preinvocation hook:",
    "[agyis role ",
    "[agyis subagent context",
    "[agyis system directive:",
    "[agyis post-compaction succession directive]",
    "[agyis checkpoint horizon advisory:",
    "[agyis epoch horizon advisory:",
    "[agyis token gauge:",
)

_PROMPT_JSON_KEYS: Tuple[str, ...] = (
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


def _is_sdk_injection_text(text: Optional[str]) -> bool:
    """Returns True if text is a PreInvocation SDK/harness injection rather than a user or parent prompt."""
    if not text or not isinstance(text, str):
        return False
    lower = text.lower()
    return any(marker in lower for marker in _SDK_INJECTION_MARKERS)


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
        except (ValueError, TypeError):
            pass
        try:
            return datetime.strptime(s.split(".")[0], "%Y-%m-%d %H:%M:%S").timestamp()
        except (ValueError, TypeError):
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
        except (json.JSONDecodeError, ValueError, TypeError):
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
        except (json.JSONDecodeError, ValueError, TypeError):
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


def _prompt_from_json_val(raw: Any) -> str:
    """Extracts a prompt string from a JSON string/bytes/dict if known prompt keys exist."""
    if isinstance(raw, (bytes, bytearray)):
        if not raw.lstrip().startswith(b"{"):
            return ""
        try:
            raw = json.loads(bytes(raw).decode("utf-8", errors="replace"))
        except (json.JSONDecodeError, ValueError, TypeError):
            return ""
    elif isinstance(raw, str):
        stripped = raw.strip()
        if not stripped.startswith("{"):
            return stripped
        try:
            raw = json.loads(stripped)
        except (json.JSONDecodeError, ValueError, TypeError):
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
        msg_strings = [
            s
            for s in strings
            if ("[Message]" in s or "Message from Parent Agent" in s) and not _is_sdk_injection_text(s)
        ]
        if msg_strings:
            return max(msg_strings, key=len)
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
                except (json.JSONDecodeError, ValueError, TypeError):
                    pass
            else:
                tn, args = extract_tool_from_protobuf(raw_b)
                if tn:
                    return tn, args
    return None


def _read_gen_metadata(cursor: sqlite3.Cursor, tables: set[str]) -> Tuple[int, int, int, int, str, Dict[str, int]]:
    """Reads (estimated_tokens, max_context_tokens, usage_tokens, checkpoint_idx, model_name, tb_extras)."""
    if "gen_metadata" not in tables:
        return 0, 0, 0, 0, "", {}
    cursor.execute("PRAGMA table_info(gen_metadata)")
    cols = {r[1] for r in cursor.fetchall()}
    if "data" not in cols:
        return 0, 0, 0, 0, "", {}
    order_col = "idx" if "idx" in cols else "rowid"
    cursor.execute(f"SELECT data FROM gen_metadata ORDER BY {order_col} DESC LIMIT 5")
    est = mct = usage = ckpt_idx = 0
    model = ""
    tb_extras: Dict[str, int] = {}
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
            except (json.JSONDecodeError, ValueError, TypeError):
                pass
        elif isinstance(raw, (bytes, bytearray)):
            gm = extract_usage_from_protobuf(bytes(raw))
            est = est or gm.estimated_tokens
            mct = mct or gm.max_context_tokens
            usage = usage or gm.total_prompt_tokens
            if 0 < gm.checkpoint_idx < _PB_UINT64_SENTINEL:
                ckpt_idx = ckpt_idx or gm.checkpoint_idx
            model = model or gm.model_name
            if not tb_extras and len(raw) > 5000:
                tb = extract_token_breakdown_from_protobuf(bytes(raw))
                if tb:
                    tb_extras = {
                        "system_prompt_tokens": tb.system_tokens,
                        "tool_defs_tokens": tb.tool_tokens + tb.mcp_tool_tokens,
                        "chat_message_tokens": tb.chat_message_tokens,
                        "total_breakdown_tokens": tb.total_tokens,
                    }
        if est > 0 and mct > 0:
            break
    return est, mct, usage, ckpt_idx, model, tb_extras


__all__ = [
    "_PB_UINT64_SENTINEL",
    "_extract_prompt_from_step",
    "_extract_step_fields",
    "_extract_tool_from_step",
    "_is_sdk_injection_text",
    "_prompt_from_json_val",
    "_read_gen_metadata",
    "parse_step_timestamp",
]
