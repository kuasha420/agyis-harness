# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Arafat Zahan (@kuasha420)
# Corporate Stewardship & Infrastructure: Purrfect Software Limited (PSL)
# Governed by: ICARO-42/b Ordinance (Company-Supported Personal IP Framework)

"""
Agyis Harness: PreToolUse Token Proximity Guard Lifecycle Hook (ADR-014 / ADR-028)

Monitors real-time token accumulation in the active session's SQLite database
and surfaces non-invasive ANSI urgency warnings to stderr prior to tool execution:
- Tier 1: Safe (<35,000 tokens) -> Nominal silent operation.
- Tier 2: Elevated (>=35,000 tokens) -> Amber warning gauge.
- Tier 3: Critical (>=45,000 tokens) -> Bold Red pulse alert + terminal bell (\\a).

Zero Crash Risk Invariant:
- Read-only SQLite connection (file:{path}?mode=ro, uri=True, timeout=1.0).
- All exceptions caught and swallowed gracefully.
- sys.stdout always emits valid protojson decision: {"decision": "allow"}.
- Process always exits 0.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
import sqlite3
import sys
import time
from typing import Any, Dict, Optional, TextIO

CONTEXT_WINDOW_TOKENS: int = 256000
COMPACTION_THRESHOLD: int = 230000
AMBER_THRESHOLD: int = 180000
RED_THRESHOLD: int = 230000
CHECKPOINT_STEP_TYPE: int = 23  # Google Antigravity compaction checkpoint enum (0x17)
ROLE_DEEP_EXECUTION: str = "deep_execution"
MAX_SAFE_BURN_RATE_PER_MIN: float = 2000.0
CRITICAL_BURN_RATE_PER_MIN: float = 4000.0


def _normalize_role_str(val: Optional[str]) -> Optional[str]:
    """Normalizes role identifier to canonical taxonomy."""
    if not val or not isinstance(val, str):
        return None
    norm = val.strip().lower().replace("-", "_")
    if norm in (
        ROLE_DEEP_EXECUTION,
        "agyis_builder",
        "agyis_custodian",
        "agyis_architect",
        "architect",
        "implementer",
        "master_implementer",
        "executioner",
        "builder",
        "custodian",
        "harness_custodian",
        "git_custodian",
        "harness_builder",
        "deep_coding",
        "deep_coder",
        "coder",
        "execution",
        "monolithic_swe_pairing",
        "monolithic",
        "monolith",
        "swe_pairing",
        "pairing",
        "swe",
    ):
        return ROLE_DEEP_EXECUTION
    if (
        "executioner" in norm
        or "builder" in norm
        or "custodian" in norm
        or "deep_execution" in norm
        or "deep_coding" in norm
        or "monolith" in norm
        or "swe_pairing" in norm
        or "architect" in norm
    ):
        return ROLE_DEEP_EXECUTION
    return norm


_LOCKED_CONVERSATIONS: dict[str, float] = {}
LOCK_EXPIRY_SECONDS: float = 2.0


def _normalize_cid(cid: Any) -> str:
    """Normalizes conversation identifier by stripping trailing .db suffix and whitespace."""
    if not cid or not isinstance(cid, str):
        return ""
    norm = cid.strip()
    if norm.endswith(".db"):
        return norm[:-3]
    return norm


def is_conversation_locked(conversation_id: str) -> bool:
    """Returns True if the conversation database is currently marked as locked within the expiry window."""
    norm_cid = _normalize_cid(conversation_id)
    if not norm_cid:
        return False
    lock_time = _LOCKED_CONVERSATIONS.get(norm_cid)
    if lock_time is None:
        return False
    if time.monotonic() - lock_time < LOCK_EXPIRY_SECONDS:
        return True
    _LOCKED_CONVERSATIONS.pop(norm_cid, None)
    return False


def record_locked_conversation(conversation_id: str) -> None:
    """Records a conversation database as locked with current monotonic timestamp."""
    norm_cid = _normalize_cid(conversation_id)
    if norm_cid:
        _LOCKED_CONVERSATIONS[norm_cid] = time.monotonic()


def clear_locked_conversations() -> None:
    """Clears recorded locked conversation identifiers."""
    _LOCKED_CONVERSATIONS.clear()
    LOCKED_CONVERSATION_IDS._clear_internal()


class _LockedConversationsProxy(set):
    """Set-compatible proxy providing transparent TTL-based expiration for locked conversation IDs."""

    def __contains__(self, item: object) -> bool:
        if isinstance(item, str):
            return is_conversation_locked(item)
        return False

    def add(self, element: Any) -> None:
        if isinstance(element, str):
            norm = _normalize_cid(element)
            if norm:
                record_locked_conversation(norm)
                super().add(norm)

    def remove(self, element: Any) -> None:
        norm = _normalize_cid(element) if isinstance(element, str) else str(element)
        _LOCKED_CONVERSATIONS.pop(norm, None)
        if norm in self:
            super().remove(norm)

    def discard(self, element: Any) -> None:
        norm = _normalize_cid(element) if isinstance(element, str) else str(element)
        _LOCKED_CONVERSATIONS.pop(norm, None)
        super().discard(norm)

    def clear(self) -> None:
        clear_locked_conversations()
        super().clear()

    def _clear_internal(self) -> None:
        super().clear()


LOCKED_CONVERSATION_IDS: _LockedConversationsProxy = _LockedConversationsProxy()


def is_checkpoint_step(step_type: Any) -> bool:
    """Returns True if the step_type represents a compaction checkpoint (23 / 0x17)."""
    try:
        return int(step_type) == CHECKPOINT_STEP_TYPE
    except (ValueError, TypeError):
        return False


def get_conversations_dir() -> Path:
    """Resolves the directory containing Antigravity conversation SQLite databases."""
    env_dir = (
        os.environ.get("AGYIS_CONVERSATIONS_DIR")
        or os.environ.get("ANTIGRAVITY_CONVERSATIONS_DIR")
        or os.environ.get("GEMINI_CONVERSATIONS_DIR")
    )
    if env_dir:
        return Path(env_dir)
    return Path.home() / ".gemini" / "antigravity" / "conversations"


def parse_protobuf_varint(data: bytes, offset: int = 0) -> tuple[int, int]:
    """Helper to parse a protobuf varint without third-party libraries."""
    res = 0
    shift = 0
    idx = offset
    while idx < len(data):
        b = data[idx]
        idx += 1
        res |= (b & 0x7F) << shift
        if not (b & 0x80):
            break
        shift += 7
    return res, idx


def _parse_pb_fields(buf: bytes) -> Optional[list[tuple[int, int, Any]]]:
    """Strictly decodes top-level protobuf fields from buf, returning None on malformed/non-message bytes."""
    if not buf or not isinstance(buf, bytes):
        return None

    def _read_varint(data: bytes, offset: int) -> Optional[tuple[int, int]]:
        res = 0
        shift = 0
        idx = offset
        while idx < len(data):
            b = data[idx]
            idx += 1
            res |= (b & 0x7F) << shift
            if not (b & 0x80):
                return res, idx
            shift += 7
            if shift > 70:
                return None
        return None

    fields: list[tuple[int, int, Any]] = []
    idx = 0
    while idx < len(buf):
        tv = _read_varint(buf, idx)
        if tv is None:
            return None
        tag, idx = tv
        fn = tag >> 3
        wt = tag & 0x07
        if fn == 0:
            return None
        if wt == 0:
            vv = _read_varint(buf, idx)
            if vv is None:
                return None
            val, idx = vv
            fields.append((fn, wt, val))
        elif wt == 2:
            lv = _read_varint(buf, idx)
            if lv is None:
                return None
            length, idx = lv
            if length < 0 or idx + length > len(buf):
                return None
            fields.append((fn, wt, buf[idx : idx + length]))
            idx += length
        elif wt == 1:
            if idx + 8 > len(buf):
                return None
            fields.append((fn, wt, buf[idx : idx + 8]))
            idx += 8
        elif wt == 5:
            if idx + 4 > len(buf):
                return None
            fields.append((fn, wt, buf[idx : idx + 4]))
            idx += 4
        else:
            return None
    return fields


def extract_context_window_from_protobuf_metadata(raw_bytes: bytes) -> tuple[int, int]:
    """
    Extracts (estimatedTokensUsed, maxContextTokens) from protobuf gen_metadata or step metadata.
    Supports field 1 -> field 9 (chatStartMetadata) -> field 10 (contextWindowMetadata)
    where field 1 = estimatedTokensUsed and field 4 = maxContextTokens, plus direct
    field 9 -> field 10 and field 10 encodings without colliding with UsageMetadata (field 9 -> {2, 5}).
    """
    outer = _parse_pb_fields(raw_bytes)
    if not outer:
        return 0, 0

    def _parse_cwm(cwm_bytes: bytes) -> tuple[int, int]:
        cwm_fields = _parse_pb_fields(cwm_bytes)
        if not cwm_fields:
            return 0, 0
        est = 0
        mct = 0
        for fn, wt, val in cwm_fields:
            if wt == 0 and isinstance(val, int) and val > 0:
                if fn == 1:
                    est = val
                elif fn == 4:
                    mct = val
        return est, mct

    best_est = 0
    best_mct = 0

    try:
        # Path 1: field 1 -> field 9 (chatStartMetadata) -> field 10 (contextWindowMetadata)
        for fn1, wt1, val1 in outer:
            if fn1 == 1 and wt1 == 2 and isinstance(val1, bytes):
                f1_fields = _parse_pb_fields(val1)
                if not f1_fields:
                    continue
                for fn9, wt9, val9 in f1_fields:
                    if fn9 == 9 and wt9 == 2 and isinstance(val9, bytes):
                        f9_fields = _parse_pb_fields(val9)
                        if not f9_fields:
                            continue
                        for fn10, wt10, val10 in f9_fields:
                            if fn10 == 10 and wt10 == 2 and isinstance(val10, bytes):
                                est, mct = _parse_cwm(val10)
                                if est > 0 and best_est == 0:
                                    best_est = est
                                if mct > 0 and best_mct == 0:
                                    best_mct = mct

        if best_est > 0 or best_mct > 0:
            return best_est, best_mct

        # Path 2: field 9 -> field 10 (guarding against UsageMetadata field 9 -> {2, 5})
        for fn9, wt9, val9 in outer:
            if fn9 == 9 and wt9 == 2 and isinstance(val9, bytes):
                f9_fields = _parse_pb_fields(val9)
                if not f9_fields:
                    continue
                has_usage_varints = any(
                    swt == 0 and sfn in (2, 5) and isinstance(sval, int) and sval > 0
                    for sfn, swt, sval in f9_fields
                )
                for fn10, wt10, val10 in f9_fields:
                    if fn10 == 10 and wt10 == 2 and isinstance(val10, bytes):
                        est, mct = _parse_cwm(val10)
                        if not has_usage_varints or mct > 0:
                            if est > 0 and best_est == 0:
                                best_est = est
                            if mct > 0 and best_mct == 0:
                                best_mct = mct

        if best_est > 0 or best_mct > 0:
            return best_est, best_mct

        # Path 3: direct field 10 (contextWindowMetadata)
        for fn10, wt10, val10 in outer:
            if fn10 == 10 and wt10 == 2 and isinstance(val10, bytes):
                est, mct = _parse_cwm(val10)
                if est > 0 and best_est == 0:
                    best_est = est
                if mct > 0 and best_mct == 0:
                    best_mct = mct
    except Exception:
        return 0, 0

    return best_est, best_mct


def _extract_context_window_from_json(data: Any) -> tuple[int, int]:
    """Extracts (estimatedTokensUsed, maxContextTokens) from JSON metadata structures."""
    if not isinstance(data, dict):
        return 0, 0

    meta = data.get("metadata") if isinstance(data.get("metadata"), dict) else {}
    csm = data.get("chatStartMetadata") if isinstance(data.get("chatStartMetadata"), dict) else {}
    meta_csm = meta.get("chatStartMetadata") if isinstance(meta.get("chatStartMetadata"), dict) else {}
    gen = data.get("generator_metadata") if isinstance(data.get("generator_metadata"), dict) else {}
    gen_csm = gen.get("chatStartMetadata") if isinstance(gen.get("chatStartMetadata"), dict) else {}
    gen_meta = gen.get("metadata") if isinstance(gen.get("metadata"), dict) else {}
    gen_meta_csm = gen_meta.get("chatStartMetadata") if isinstance(gen_meta.get("chatStartMetadata"), dict) else {}

    def _to_pos_int(val: Any) -> int:
        if isinstance(val, (int, float)) and int(val) > 0:
            return int(val)
        if isinstance(val, str) and val.strip().isdigit() and int(val.strip()) > 0:
            return int(val.strip())
        return 0

    est = 0
    mct = 0
    for cwm in (
        data.get("contextWindowMetadata"),
        csm.get("contextWindowMetadata"),
        meta.get("contextWindowMetadata"),
        meta_csm.get("contextWindowMetadata"),
        gen.get("contextWindowMetadata"),
        gen_csm.get("contextWindowMetadata"),
        gen_meta.get("contextWindowMetadata"),
        gen_meta_csm.get("contextWindowMetadata"),
    ):
        if not isinstance(cwm, dict):
            continue
        if est <= 0:
            est = _to_pos_int(cwm.get("estimatedTokensUsed") or cwm.get("estimated_tokens_used"))
        if mct <= 0:
            mct = _to_pos_int(cwm.get("maxContextTokens") or cwm.get("max_context_tokens"))
        if est > 0 and mct > 0:
            break

    if est <= 0:
        est = _to_pos_int(data.get("estimatedTokensUsed") or data.get("estimated_tokens_used"))
    if mct <= 0:
        mct = _to_pos_int(data.get("maxContextTokens") or data.get("max_context_tokens"))

    return est, mct


def get_scaled_thresholds(max_context_tokens: Optional[int] = None) -> tuple[int, int]:
    """Returns proportionally scaled (amber_threshold, red_threshold) for the active context window."""
    if max_context_tokens is None or max_context_tokens <= 0 or max_context_tokens == CONTEXT_WINDOW_TOKENS:
        return AMBER_THRESHOLD, RED_THRESHOLD
    amber = int(round(max_context_tokens * AMBER_THRESHOLD / CONTEXT_WINDOW_TOKENS))
    red = int(round(max_context_tokens * RED_THRESHOLD / CONTEXT_WINDOW_TOKENS))
    return amber, red


def extract_tokens_from_protobuf_metadata(raw_bytes: bytes) -> int:
    """Extracts prompt+cached UsageMetadata tokens if present, else falls back to contextWindowMetadata."""
    if not raw_bytes or not isinstance(raw_bytes, bytes):
        return 0
    try:
        # Protobuf fields: tag = (field_number << 3) | wire_type
        # In steps.metadata, fn 9 contains token metrics with subfield 2 = prompt tokens, subfield 5 = cached content tokens
        idx = 0
        while idx < len(raw_bytes):
            tag, idx = parse_protobuf_varint(raw_bytes, idx)
            fn = tag >> 3
            wt = tag & 0x07
            if fn == 0:
                break
            if wt == 0:  # Varint
                val, idx = parse_protobuf_varint(raw_bytes, idx)
            elif wt == 2:  # Length-delimited
                length, idx = parse_protobuf_varint(raw_bytes, idx)
                if idx + length > len(raw_bytes):
                    break
                chunk = raw_bytes[idx : idx + length]
                idx += length
                if fn == 9 and chunk:
                    prompt_tokens = 0
                    cached_tokens = 0
                    s_idx = 0
                    while s_idx < len(chunk):
                        s_tag, s_idx = parse_protobuf_varint(chunk, s_idx)
                        s_fn = s_tag >> 3
                        s_wt = s_tag & 0x07
                        if s_fn == 0:
                            break
                        if s_wt == 0:
                            s_val, s_idx = parse_protobuf_varint(chunk, s_idx)
                            if s_fn == 2 and s_val > 0:  # promptTokenCount (uncached prompt delta)
                                prompt_tokens = s_val
                            elif s_fn == 5 and s_val > 0:  # cachedContentTokenCount (Vertex context cache hits)
                                cached_tokens = s_val
                        elif s_wt == 2:
                            s_len, s_idx = parse_protobuf_varint(chunk, s_idx)
                            if s_idx + s_len > len(chunk):
                                break
                            s_idx += s_len
                        elif s_wt == 1:
                            s_idx += 8
                        elif s_wt == 5:
                            s_idx += 4
                        else:
                            break
                    total = prompt_tokens + cached_tokens
                    if total > 0:
                        return total
            elif wt in (1, 5):
                idx += 8 if wt == 1 else 4
            else:
                break
    except Exception:
        pass
    est, _ = extract_context_window_from_protobuf_metadata(raw_bytes)
    return est


def get_active_conversation_context_window(
    conversation_id: str,
    db_dir: Optional[Path] = None,
    timeout: Optional[float] = None,
) -> Dict[str, Any]:
    """
    Reads active token count and dynamic maxContextTokens capacity from the local Antigravity
    conversation DB, returning scaled thresholds. Guarantees fail-open, zero-crash execution.
    """
    default_res: Dict[str, Any] = {
        "tokens": 0,
        "max_context_tokens": CONTEXT_WINDOW_TOKENS,
        "amber_threshold": AMBER_THRESHOLD,
        "red_threshold": RED_THRESHOLD,
        "compaction_threshold": COMPACTION_THRESHOLD,
        "has_explicit_max_context": False,
    }

    norm_cid = _normalize_cid(conversation_id)
    if not norm_cid or norm_cid == "default":
        return default_res

    if norm_cid in LOCKED_CONVERSATION_IDS:
        return default_res

    conn: Optional[sqlite3.Connection] = None
    try:
        base_dir = db_dir or get_conversations_dir()
        db_path = base_dir / f"{norm_cid}.db"
        if not db_path.is_file():
            return default_res

        # Strict read-only mode with URI connection and bounded timeout (ADR-016)
        if timeout is not None:
            try:
                t_val = float(timeout)
                eff_timeout = min(t_val, 0.5) if t_val > 0 else 0.5
            except (ValueError, TypeError):
                eff_timeout = 0.5
        else:
            eff_timeout = 0.5
        uri_path = f"file:{db_path.resolve()}?mode=ro"
        conn = sqlite3.connect(uri_path, uri=True, timeout=eff_timeout)
        cursor = conn.cursor()

        cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
        tables = {row[0] for row in cursor.fetchall()}

        tokens_found = 0
        max_ctx_found = 0
        checkpoint_hit = False

        # Strategy 1: Check `steps` table
        if "steps" in tables:
            cursor.execute("PRAGMA table_info(steps)")
            col_names = {row[1] for row in cursor.fetchall()}

            if "idx" in col_names:
                order_clause = "ORDER BY idx DESC"
            elif "step_index" in col_names:
                order_clause = "ORDER BY step_index DESC"
            else:
                order_clause = "ORDER BY rowid DESC"

            has_step_type = "step_type" in col_names
            where_step_filter = "WHERE step_type IN (15, 23)" if has_step_type else ""

            # 1.1 JSON format: `step_data` column
            if "step_data" in col_names:
                cols = "step_data, step_type" if has_step_type else "step_data"
                cursor.execute(f"SELECT {cols} FROM steps {where_step_filter} {order_clause} LIMIT 10")
                for row in cursor.fetchall():
                    raw_step = row[0]
                    st = row[1] if has_step_type else None
                    if has_step_type and is_checkpoint_step(st):
                        checkpoint_hit = True
                        break
                    if not raw_step:
                        continue
                    try:
                        data = json.loads(raw_step) if isinstance(raw_step, str) else {}
                        if not isinstance(data, dict):
                            continue
                        if is_checkpoint_step(data.get("step_type")):
                            checkpoint_hit = True
                            break

                        cwm_est, cwm_mct = _extract_context_window_from_json(data)
                        if cwm_mct > 0 and max_ctx_found == 0:
                            max_ctx_found = cwm_mct

                        gen_meta = data.get("generator_metadata", {})
                        if isinstance(gen_meta, dict):
                            val = gen_meta.get("metadata", {}).get("value", {})
                            if isinstance(val, dict):
                                prompts = val.get("message_prompts", [])
                                if prompts and isinstance(prompts, list) and isinstance(prompts[0], dict):
                                    num_t = prompts[0].get("num_tokens") or prompts[0].get("numTokens")
                                    if isinstance(num_t, (int, float)) and num_t > 0:
                                        tokens_found = int(num_t)
                                        break

                        direct_tokens = (
                            data.get("token_count")
                            or data.get("tokens")
                            or data.get("num_tokens")
                            or data.get("numTokens")
                            or cwm_est
                        )
                        if isinstance(direct_tokens, (int, float)) and direct_tokens > 0:
                            tokens_found = int(direct_tokens)
                            break
                    except Exception:
                        continue

            # 1.2 Dedicated token columns
            if not tokens_found and not checkpoint_hit and ("token_count" in col_names or "tokens" in col_names or "num_tokens" in col_names):
                col = "token_count" if "token_count" in col_names else ("tokens" if "tokens" in col_names else "num_tokens")
                cols = f"{col}, step_type" if has_step_type else col
                cursor.execute(f"SELECT {cols} FROM steps {where_step_filter} {order_clause} LIMIT 10")
                for row in cursor.fetchall():
                    st = row[1] if has_step_type else None
                    if has_step_type and is_checkpoint_step(st):
                        checkpoint_hit = True
                        break
                    val = row[0]
                    if val is not None:
                        try:
                            t = int(val)
                            if t > 0:
                                tokens_found = t
                                break
                        except (ValueError, TypeError):
                            pass

            # 1.3 Check `metadata` column in steps (JSON or protobuf)
            if not checkpoint_hit and "metadata" in col_names and (not tokens_found or max_ctx_found == 0):
                cols = "metadata, step_type" if has_step_type else "metadata"
                cursor.execute(f"SELECT {cols} FROM steps {where_step_filter} {order_clause} LIMIT 10")
                for row in cursor.fetchall():
                    raw_meta = row[0]
                    st = row[1] if has_step_type else None
                    if has_step_type and is_checkpoint_step(st):
                        if not tokens_found:
                            checkpoint_hit = True
                        break
                    if not raw_meta:
                        continue
                    if isinstance(raw_meta, str):
                        try:
                            d = json.loads(raw_meta)
                            if isinstance(d, dict):
                                if is_checkpoint_step(d.get("step_type")):
                                    if not tokens_found:
                                        checkpoint_hit = True
                                    break
                                cwm_est, cwm_mct = _extract_context_window_from_json(d)
                                if cwm_mct > 0 and max_ctx_found == 0:
                                    max_ctx_found = cwm_mct
                                if not tokens_found:
                                    t = d.get("num_tokens") or d.get("numTokens") or d.get("tokens") or d.get("token_count") or cwm_est
                                    if isinstance(t, (int, float)) and t > 0:
                                        tokens_found = int(t)
                                        break
                        except Exception:
                            pass
                    elif isinstance(raw_meta, bytes):
                        cwm_est, cwm_mct = extract_context_window_from_protobuf_metadata(raw_meta)
                        if cwm_mct > 0 and max_ctx_found == 0:
                            max_ctx_found = cwm_mct
                        if not tokens_found:
                            pb_tokens = extract_tokens_from_protobuf_metadata(raw_meta)
                            if pb_tokens > 0:
                                tokens_found = pb_tokens
                                break

        # Strategy 2: Always inspect `gen_metadata` for estimatedTokensUsed and maxContextTokens
        gen_estimated = 0
        gen_max_context = 0
        if "gen_metadata" in tables:
            cursor.execute("PRAGMA table_info(gen_metadata)")
            gen_cols = {row[1] for row in cursor.fetchall()}
            if "data" in gen_cols:
                gen_order = "ORDER BY idx DESC" if "idx" in gen_cols else "ORDER BY rowid DESC"
                cursor.execute(f"SELECT data FROM gen_metadata {gen_order} LIMIT 5")
                for (gen_data,) in cursor.fetchall():
                    if not gen_data:
                        continue
                    if isinstance(gen_data, str):
                        try:
                            d = json.loads(gen_data)
                            if isinstance(d, dict):
                                cwm_est, cwm_mct = _extract_context_window_from_json(d)
                                t = d.get("num_tokens") or d.get("numTokens") or d.get("tokens")
                                cand_est = cwm_est if cwm_est > 0 else (int(t) if isinstance(t, (int, float)) and t > 0 else 0)
                                if cand_est > 0 and gen_estimated == 0:
                                    gen_estimated = cand_est
                                if cwm_mct > 0 and gen_max_context == 0:
                                    gen_max_context = cwm_mct
                        except Exception:
                            pass
                    elif isinstance(gen_data, bytes):
                        cwm_est, cwm_mct = extract_context_window_from_protobuf_metadata(gen_data)
                        pb_tokens = extract_tokens_from_protobuf_metadata(gen_data)
                        cand_est = max(cwm_est, pb_tokens)
                        if cand_est > 0 and gen_estimated == 0:
                            gen_estimated = cand_est
                        if cwm_mct > 0 and gen_max_context == 0:
                            gen_max_context = cwm_mct
                    if gen_estimated > 0 and gen_max_context > 0:
                        break

        has_explicit_max = (gen_max_context > 0) or (max_ctx_found > 0)
        resolved_max_ctx = gen_max_context if gen_max_context > 0 else (max_ctx_found if max_ctx_found > 0 else CONTEXT_WINDOW_TOKENS)

        if checkpoint_hit:
            active_tokens = 0
        elif tokens_found > 0 and gen_estimated > 0:
            active_tokens = max(tokens_found, gen_estimated)
        else:
            active_tokens = tokens_found or gen_estimated

        amber_t, red_t = get_scaled_thresholds(resolved_max_ctx)
        return {
            "tokens": active_tokens,
            "max_context_tokens": resolved_max_ctx,
            "amber_threshold": amber_t,
            "red_threshold": red_t,
            "compaction_threshold": red_t,
            "has_explicit_max_context": has_explicit_max,
        }
    except sqlite3.OperationalError:
        LOCKED_CONVERSATION_IDS.add(norm_cid)
        return default_res
    except Exception:
        return default_res
    finally:
        if conn is not None:
            try:
                conn.close()
            except Exception:
                pass


def get_active_conversation_tokens(
    conversation_id: str,
    db_dir: Optional[Path] = None,
    timeout: Optional[float] = None,
) -> int:
    """
    Reads the latest accumulated token count from the local Antigravity conversation DB.
    Guarantees fail-open, zero-crash execution: returns 0 on any missing file, locked
    database, schema mismatch, or read exception.
    """
    return int(get_active_conversation_context_window(conversation_id, db_dir=db_dir, timeout=timeout)["tokens"])


def _parse_step_timestamp(val: Any) -> Optional[float]:
    """Parses epoch or ISO string timestamp into seconds float."""
    if val is None:
        return None
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
            f = float(s)
            if f > 1e14:
                return f / 1e6
            if f > 1e11:
                return f / 1e3
            return f if f > 0 else None
        except ValueError:
            pass
        try:
            from datetime import datetime
            dt = datetime.fromisoformat(s.replace("Z", "+00:00"))
            return dt.timestamp()
        except Exception:
            pass
        try:
            from datetime import datetime
            dt = datetime.strptime(s.split(".")[0], "%Y-%m-%d %H:%M:%S")
            return dt.timestamp()
        except Exception:
            pass
    return None


def get_active_conversation_token_velocity(
    conversation_id: str,
    db_dir: Optional[Path] = None,
    window_seconds: int = 900,
) -> Dict[str, Any]:
    """
    Computes real-time differential token burn rate velocity (tokens/min) and
    time-to-compaction projections from active conversation step history.
    Guarantees zero-crash fail-open execution: returns nominal SAFE tier on any error.
    """
    default_res: Dict[str, Any] = {
        "tokens": 0,
        "burn_rate_tokens_per_min": 0.0,
        "mins_to_compaction": None,
        "mins_to_50k": None,
        "mins_to_100k": None,
        "velocity_tier": "SAFE",
        "sample_count": 0,
        "window_seconds": window_seconds,
        "max_context_tokens": CONTEXT_WINDOW_TOKENS,
        "amber_threshold": AMBER_THRESHOLD,
        "red_threshold": RED_THRESHOLD,
        "compaction_threshold": COMPACTION_THRESHOLD,
    }

    norm_cid = _normalize_cid(conversation_id)
    if not norm_cid or norm_cid == "default":
        return default_res

    if norm_cid in LOCKED_CONVERSATION_IDS:
        return default_res

    base_dir = db_dir or get_conversations_dir()
    db_path = base_dir / f"{norm_cid}.db"
    if not db_path.is_file():
        # Check if conversation_id was already a direct path
        cand = Path(conversation_id)
        if cand.is_file():
            db_path = cand
        else:
            # Check fallback to telemetry.db
            telem_path = None
            try:
                from harness.telemetry.config import get_telemetry_db_path
                t_cand = get_telemetry_db_path()
                if t_cand and t_cand.is_file():
                    telem_path = t_cand
            except Exception:
                pass
            if telem_path is None:
                repo_telem = Path(__file__).resolve().parent.parent.parent / "data" / "telemetry.db"
                if repo_telem.is_file():
                    telem_path = repo_telem
            if telem_path is not None:
                db_path = telem_path
            else:
                return default_res

    ctx_win: Dict[str, Any] = {
        "tokens": 0,
        "max_context_tokens": CONTEXT_WINDOW_TOKENS,
        "amber_threshold": AMBER_THRESHOLD,
        "red_threshold": RED_THRESHOLD,
        "compaction_threshold": COMPACTION_THRESHOLD,
    }
    if db_path.name != "telemetry.db":
        ctx_win = get_active_conversation_context_window(db_path.stem, db_dir=db_path.parent)

    max_ctx = int(ctx_win.get("max_context_tokens") or CONTEXT_WINDOW_TOKENS)
    amber_t = int(ctx_win.get("amber_threshold") or AMBER_THRESHOLD)
    red_t = int(ctx_win.get("red_threshold") or RED_THRESHOLD)
    comp_t = int(ctx_win.get("compaction_threshold") or COMPACTION_THRESHOLD)
    default_res["max_context_tokens"] = max_ctx
    default_res["amber_threshold"] = amber_t
    default_res["red_threshold"] = red_t
    default_res["compaction_threshold"] = comp_t

    conn: Optional[sqlite3.Connection] = None
    try:
        uri_path = f"file:{db_path.resolve()}?mode=ro"
        conn = sqlite3.connect(uri_path, uri=True, timeout=0.5)
        cursor = conn.cursor()

        cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
        tables = {row[0] for row in cursor.fetchall()}
        if "steps" not in tables:
            tokens = int(ctx_win.get("tokens") or 0)
            if tokens <= 0:
                tokens = get_active_conversation_tokens(conversation_id, db_dir=db_dir)
            default_res["tokens"] = tokens
            return default_res

        cursor.execute("PRAGMA table_info(steps)")
        step_cols = {row[1] for row in cursor.fetchall()}

        if "idx" in step_cols:
            order_col = "idx"
        elif "step_index" in step_cols:
            order_col = "step_index"
        elif "id" in step_cols:
            order_col = "id"
        else:
            order_col = "rowid"

        select_cols = [order_col]
        for col in (
            "step_type",
            "created_at",
            "timestamp",
            "time",
            "ts",
            "token_count",
            "tokens",
            "num_tokens",
            "numTokens",
            "step_data",
            "metadata",
        ):
            if col in step_cols and col not in select_cols:
                select_cols.append(col)

        query = f"SELECT {', '.join(select_cols)} FROM steps"
        params = []
        if "session_id" in step_cols and db_path.name == "telemetry.db":
            query += " WHERE session_id = ?"
            params.append(norm_cid)
        query += f" ORDER BY {order_col} DESC LIMIT 200"

        cursor.execute(query, params)
        rows = cursor.fetchall()

        col_map = {col: idx for idx, col in enumerate(select_cols)}

        # Collect step samples: newest to oldest
        raw_samples: list[tuple[Optional[float], int, Any]] = []

        for row in rows:
            # 1. Compaction checkpoint check
            st = row[col_map["step_type"]] if "step_type" in col_map else None
            if is_checkpoint_step(st):
                break

            # 2. Extract step data JSON if present
            data: dict[str, Any] = {}
            if "step_data" in col_map:
                raw_sd = row[col_map["step_data"]]
                if raw_sd and isinstance(raw_sd, str):
                    try:
                        data = json.loads(raw_sd)
                        if is_checkpoint_step(data.get("step_type")):
                            break
                    except Exception:
                        data = {}

            # 3. Extract tokens
            step_tokens = 0
            for tk_col in ("token_count", "tokens", "num_tokens", "numTokens"):
                if tk_col in col_map and row[col_map[tk_col]] is not None:
                    try:
                        val = int(row[col_map[tk_col]])
                        if val > 0:
                            step_tokens = val
                            break
                    except (ValueError, TypeError):
                        pass

            if not step_tokens and data:
                gen_meta = data.get("generator_metadata", {})
                if isinstance(gen_meta, dict):
                    val = gen_meta.get("metadata", {}).get("value", {})
                    if isinstance(val, dict):
                        prompts = val.get("message_prompts", [])
                        if prompts and isinstance(prompts, list) and isinstance(prompts[0], dict):
                            num_t = prompts[0].get("num_tokens") or prompts[0].get("numTokens")
                            if isinstance(num_t, (int, float)) and num_t > 0:
                                step_tokens = int(num_t)
                if not step_tokens:
                    cwm_est, _ = _extract_context_window_from_json(data)
                    direct_t = (
                        data.get("token_count")
                        or data.get("tokens")
                        or data.get("num_tokens")
                        or data.get("numTokens")
                        or cwm_est
                    )
                    if isinstance(direct_t, (int, float)) and direct_t > 0:
                        step_tokens = int(direct_t)

            if not step_tokens and "metadata" in col_map:
                raw_meta = row[col_map["metadata"]]
                if raw_meta:
                    if isinstance(raw_meta, str):
                        try:
                            d = json.loads(raw_meta)
                            if is_checkpoint_step(d.get("step_type")):
                                break
                            cwm_est, _ = _extract_context_window_from_json(d)
                            t = d.get("num_tokens") or d.get("numTokens") or d.get("tokens") or d.get("token_count") or cwm_est
                            if isinstance(t, (int, float)) and t > 0:
                                step_tokens = int(t)
                        except Exception:
                            pass
                    elif isinstance(raw_meta, bytes):
                        pb_tokens = extract_tokens_from_protobuf_metadata(raw_meta)
                        if pb_tokens > 0:
                            step_tokens = pb_tokens

            # 4. Extract timestamp
            raw_ts = None
            for ts_col in ("created_at", "timestamp", "time", "ts"):
                if ts_col in col_map and row[col_map[ts_col]] is not None:
                    raw_ts = row[col_map[ts_col]]
                    break

            if raw_ts is None and data:
                raw_ts = (
                    data.get("timestamp")
                    or data.get("created_at")
                    or data.get("time")
                    or data.get("createdAt")
                )

            if raw_ts is None and "metadata" in col_map and isinstance(row[col_map["metadata"]], str):
                try:
                    d = json.loads(row[col_map["metadata"]])
                    raw_ts = d.get("timestamp") or d.get("created_at") or d.get("time")
                except Exception:
                    pass

            parsed_ts = _parse_step_timestamp(raw_ts)

            if step_tokens > 0:
                raw_samples.append((parsed_ts, step_tokens, row[col_map[order_col]]))

        if not raw_samples:
            tokens = int(ctx_win.get("tokens") or 0)
            if tokens <= 0:
                tokens = get_active_conversation_tokens(conversation_id, db_dir=db_dir)
            default_res["tokens"] = tokens
            return default_res

        chrono = list(reversed(raw_samples))
        latest_step = chrono[-1]
        active_tokens = max(latest_step[1], int(ctx_win.get("tokens") or 0))

        valid_ts_samples = [s for s in chrono if s[0] is not None]

        if len(valid_ts_samples) < 2:
            return {
                "tokens": active_tokens,
                "burn_rate_tokens_per_min": 0.0,
                "mins_to_compaction": None,
                "mins_to_50k": None,
                "mins_to_100k": None,
                "velocity_tier": "SAFE",
                "sample_count": len(chrono),
                "window_seconds": window_seconds,
                "max_context_tokens": max_ctx,
                "amber_threshold": amber_t,
                "red_threshold": red_t,
                "compaction_threshold": comp_t,
            }

        latest_ts = valid_ts_samples[-1][0]
        window_start = latest_ts - float(window_seconds)
        windowed = [s for s in valid_ts_samples if s[0] >= window_start]

        if len(windowed) < 2:
            windowed = valid_ts_samples

        earliest = windowed[0]
        latest = windowed[-1]

        delta_tokens = latest[1] - earliest[1]
        delta_time_s = latest[0] - earliest[0]

        if delta_tokens > 0 and delta_time_s > 0:
            burn_rate = (float(delta_tokens) / float(delta_time_s)) * 60.0
        else:
            burn_rate = 0.0

        mins_to_compaction: Optional[float] = None
        mins_to_100k: Optional[float] = None

        if burn_rate > 0:
            if active_tokens >= comp_t:
                mins_to_compaction = 0.0
            else:
                mins_to_compaction = max(0.0, (comp_t - active_tokens) / burn_rate)

            if active_tokens >= 100000:
                mins_to_100k = 0.0
            else:
                mins_to_100k = max(0.0, (100000 - active_tokens) / burn_rate)

        if burn_rate >= CRITICAL_BURN_RATE_PER_MIN:
            vel_tier = "CRITICAL"
        elif burn_rate >= MAX_SAFE_BURN_RATE_PER_MIN:
            vel_tier = "ELEVATED"
        else:
            vel_tier = "SAFE"

        return {
            "tokens": active_tokens,
            "burn_rate_tokens_per_min": burn_rate,
            "mins_to_compaction": mins_to_compaction,
            "mins_to_50k": mins_to_compaction,  # backward compatibility alias
            "mins_to_100k": mins_to_100k,
            "velocity_tier": vel_tier,
            "sample_count": len(windowed),
            "window_seconds": window_seconds,
            "max_context_tokens": max_ctx,
            "amber_threshold": amber_t,
            "red_threshold": red_t,
            "compaction_threshold": comp_t,
        }
    except sqlite3.OperationalError:
        LOCKED_CONVERSATION_IDS.add(norm_cid)
        return default_res
    except Exception:
        return default_res
    finally:
        if conn is not None:
            try:
                conn.close()
            except Exception:
                pass


def get_urgency_tier(tokens: int, max_context_tokens: Optional[int] = None) -> str:
    """Classifies token count into 3-tier urgency category scaled to active context window."""
    amber_t, red_t = get_scaled_thresholds(max_context_tokens)
    if tokens >= red_t:
        return "CRITICAL"
    elif tokens >= amber_t:
        return "ELEVATED"
    return "SAFE"


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
) -> str:
    """Generates an ANSI terminal progress gauge with dynamic urgency color, burn velocity, and bell alert."""
    denom = threshold if threshold > 0 else CONTEXT_WINDOW_TOKENS
    scaled_amber, scaled_red = get_scaled_thresholds(denom if denom != CONTEXT_WINDOW_TOKENS else None)
    eff_amber = amber_threshold if amber_threshold is not None else scaled_amber
    eff_red = red_threshold if red_threshold is not None else scaled_red
    eff_comp = compaction_threshold if compaction_threshold is not None else eff_red

    percentage = min(100.0, (tokens / denom) * 100) if denom > 0 else 0.0
    filled_blocks = int((tokens / denom) * 20) if denom > 0 else 0
    filled_blocks = max(0, min(20, filled_blocks))
    bar = "█" * filled_blocks + "░" * (20 - filled_blocks)

    vel_badge = ""
    if burn_rate is not None and burn_rate > 0:
        rate_int = int(round(burn_rate))
        if mins_to_compaction is not None:
            mins_int = int(round(mins_to_compaction))
            comp_k = int(round(eff_comp / 1000))
            vel_badge = f" (+{rate_int:,} tok/min | ~{mins_int}m to {comp_k}k)"
        else:
            vel_badge = f" (+{rate_int:,} tok/min)"

    if velocity_tier:
        v_upper = velocity_tier.upper()
        if "CRITICAL" in v_upper:
            color = "\033[1;31m"  # Bold Red
            status = velocity_tier
            bell = "\a"
        elif "ELEVATED" in v_upper:
            color = "\033[1;33m"  # Bold Yellow/Amber
            status = velocity_tier
            bell = ""
        else:
            color = "\033[1;32m"  # Bold Green
            status = velocity_tier
            bell = ""
    elif tokens >= eff_red or (burn_rate is not None and burn_rate >= CRITICAL_BURN_RATE_PER_MIN):
        color = "\033[1;31m"  # Bold Red
        status = "CRITICAL (COMPACTION IMMINENT)" if tokens >= eff_red else "CRITICAL"
        bell = "\a"
    elif tokens >= eff_amber or (burn_rate is not None and burn_rate >= MAX_SAFE_BURN_RATE_PER_MIN):
        color = "\033[1;33m"  # Bold Yellow/Amber
        status = "ELEVATED (APPROACHING THRESHOLD)" if tokens >= eff_amber else "ELEVATED"
        bell = ""
    else:
        color = "\033[1;32m"  # Bold Green
        status = "SAFE"
        bell = ""

    reset = "\033[0m"
    horizon_str = ""
    if step_count is not None and step_count >= 40:
        if _normalize_role_str(role) == ROLE_DEEP_EXECUTION:
            horizon_str = f" [HORIZON: {step_count}/50 STEPS]"

    return f"{bell}{color}[AGYIS TOKEN GAUGE]{reset} [{bar}] {tokens:,} / {denom:,} ({percentage:.1f}%){vel_badge} - {color}{status}{reset}{horizon_str}"


def render_terminal_gauge(tokens: int) -> str:
    """Convenience alias for format_terminal_gauge(tokens, CONTEXT_WINDOW_TOKENS)."""
    return format_terminal_gauge(tokens, CONTEXT_WINDOW_TOKENS)


def check_token_proximity(
    conversation_id: str,
    db_dir: Optional[Path] = None,
    emit_stderr: bool = True,
    step_count: Optional[int] = None,
    role: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Evaluates active conversation token proximity and velocity, emitting an ANSI warning
    to sys.stderr if tokens have reached or exceeded the scaled amber threshold,
    if step horizon is active (step_count >= 40 for executioner),
    or if token burn rate velocity is elevated/critical (>= MAX_SAFE_BURN_RATE_PER_MIN).
    Always returns a decision dict {"decision": "allow"}.
    """
    ctx_win = get_active_conversation_context_window(conversation_id, db_dir=db_dir)
    velocity = get_active_conversation_token_velocity(conversation_id, db_dir=db_dir)
    tokens = max(int(velocity.get("tokens", 0) or 0), int(ctx_win.get("tokens", 0) or 0))
    if tokens <= 0:
        tokens = get_active_conversation_tokens(conversation_id, db_dir=db_dir)
        velocity["tokens"] = tokens

    max_ctx = int(ctx_win.get("max_context_tokens") or velocity.get("max_context_tokens") or CONTEXT_WINDOW_TOKENS)
    amber_t = int(ctx_win.get("amber_threshold") or velocity.get("amber_threshold") or AMBER_THRESHOLD)
    red_t = int(ctx_win.get("red_threshold") or velocity.get("red_threshold") or RED_THRESHOLD)
    comp_t = int(ctx_win.get("compaction_threshold") or velocity.get("compaction_threshold") or COMPACTION_THRESHOLD)

    burn_rate = velocity.get("burn_rate_tokens_per_min", 0.0)
    mins_to_50k = velocity.get("mins_to_50k")
    vel_tier = velocity.get("velocity_tier", "SAFE")
    tier = get_urgency_tier(tokens, max_context_tokens=max_ctx)

    warned = False
    horizon_active = (step_count is not None and step_count >= 40 and _normalize_role_str(role) == ROLE_DEEP_EXECUTION)
    rapid_burn = burn_rate >= MAX_SAFE_BURN_RATE_PER_MIN

    if tokens >= amber_t or horizon_active or rapid_burn:
        gauge = format_terminal_gauge(
            tokens,
            threshold=max_ctx,
            step_count=step_count,
            role=role,
            burn_rate=burn_rate,
            mins_to_compaction=mins_to_50k,
            velocity_tier=vel_tier if rapid_burn and tokens < amber_t else None,
            amber_threshold=amber_t,
            red_threshold=red_t,
            compaction_threshold=comp_t,
        )
        warned = True
        if emit_stderr:
            try:
                sys.stderr.write(f"\n{gauge}\n")
                sys.stderr.flush()
            except OSError:
                pass

    return {
        "decision": "allow",
        "tokens": tokens,
        "max_context_tokens": max_ctx,
        "amber_threshold": amber_t,
        "red_threshold": red_t,
        "tier": tier,
        "warned": warned,
        "velocity": velocity,
    }


def run_token_proximity_guard(
    payload: Any,
    stderr: Optional[TextIO] = None,
) -> Dict[str, Any]:
    """
    Core functional dispatcher for token proximity lifecycle hook.
    Parses turn payload from stdin or argument, monitors tokens, burn velocity, and step horizon,
    emits warning to stderr when scaled threshold, burn_rate >= 2,000 tok/min, or step_count >= 40 for executioner,
    and returns allow decision.
    """
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
    ctx_win = get_active_conversation_context_window(conv_id)
    velocity = get_active_conversation_token_velocity(conv_id)
    tokens = max(int(velocity.get("tokens", 0) or 0), int(ctx_win.get("tokens", 0) or 0))
    if tokens <= 0:
        tokens = get_active_conversation_tokens(conv_id)
        velocity["tokens"] = tokens

    max_ctx = int(ctx_win.get("max_context_tokens") or velocity.get("max_context_tokens") or CONTEXT_WINDOW_TOKENS)
    amber_t = int(ctx_win.get("amber_threshold") or velocity.get("amber_threshold") or AMBER_THRESHOLD)
    red_t = int(ctx_win.get("red_threshold") or velocity.get("red_threshold") or RED_THRESHOLD)
    comp_t = int(ctx_win.get("compaction_threshold") or velocity.get("compaction_threshold") or COMPACTION_THRESHOLD)

    burn_rate = velocity.get("burn_rate_tokens_per_min", 0.0)
    mins_to_50k = velocity.get("mins_to_50k")
    vel_tier = velocity.get("velocity_tier", "SAFE")

    step_count = None
    for k in (
        "step_count",
        "stepCount",
        "step",
        "current_step",
        "currentStep",
        "step_idx",
        "stepIdx",
        "initialNumSteps",
        "initial_num_steps",
        "invocationNum",
        "invocation_num",
    ):
        if k in parsed:
            v = parsed[k]
            if isinstance(v, (int, float)):
                step_count = int(v)
                break
            elif isinstance(v, str) and v.strip().isdigit():
                step_count = int(v.strip())
                break

    role = parsed.get("role") or parsed.get("agent_role") or parsed.get("subagent_role") or parsed.get("archetype")
    if not role:
        role = os.environ.get("AGYIS_ROLE") or os.environ.get("PSL_AGENT_ROLE")

    horizon_active = (step_count is not None and step_count >= 40 and _normalize_role_str(role) == ROLE_DEEP_EXECUTION)
    rapid_burn = burn_rate >= MAX_SAFE_BURN_RATE_PER_MIN

    if tokens >= amber_t or horizon_active or rapid_burn:
        gauge = format_terminal_gauge(
            tokens,
            threshold=max_ctx,
            step_count=step_count,
            role=role,
            burn_rate=burn_rate,
            mins_to_compaction=mins_to_50k,
            velocity_tier=vel_tier if rapid_burn and tokens < amber_t else None,
            amber_threshold=amber_t,
            red_threshold=red_t,
            compaction_threshold=comp_t,
        )
        out_err = stderr if stderr is not None else sys.stderr
        try:
            out_err.write(f"\n{gauge}\n")
            out_err.flush()
        except OSError:
            pass

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

    # Optional testing actions
    action = payload.get("action")
    if action == "get_tokens":
        ctx_win = get_active_conversation_context_window(conv_id)
        tokens = int(ctx_win.get("tokens") or 0)
        if tokens <= 0:
            tokens = get_active_conversation_tokens(conv_id)
        max_ctx = int(ctx_win.get("max_context_tokens") or CONTEXT_WINDOW_TOKENS)
        print(
            json.dumps(
                {
                    "status": "ok",
                    "tokens": tokens,
                    "max_context_tokens": max_ctx,
                    "tier": get_urgency_tier(tokens, max_context_tokens=max_ctx),
                }
            )
        )
        return
    elif action == "get_velocity":
        vel = get_active_conversation_token_velocity(conv_id)
        print(json.dumps({"status": "ok", "velocity": vel}))
        return
    elif action == "render_gauge":
        tokens = int(payload.get("tokens", 0))
        raw_max_ctx = payload.get("max_context_tokens") or payload.get("maxContextTokens") or payload.get("threshold")
        eff_max_ctx = CONTEXT_WINDOW_TOKENS
        if raw_max_ctx is not None:
            try:
                parsed_ctx = int(raw_max_ctx)
                if parsed_ctx > 0:
                    eff_max_ctx = parsed_ctx
            except (ValueError, TypeError):
                pass
        sc = payload.get("step_count") or payload.get("stepCount")
        sc_val = int(sc) if sc is not None else None
        r_val = payload.get("role")
        br_val = payload.get("burn_rate")
        br = float(br_val) if br_val is not None else None
        mc_val = payload.get("mins_to_compaction")
        mc = float(mc_val) if mc_val is not None else None
        vt_val = payload.get("velocity_tier")
        print(json.dumps({
            "status": "ok",
            "gauge": format_terminal_gauge(
                tokens,
                threshold=eff_max_ctx,
                step_count=sc_val,
                role=r_val,
                burn_rate=br,
                mins_to_compaction=mc,
                velocity_tier=vt_val,
            )
        }))
        return

    # PreToolUse token proximity check
    run_token_proximity_guard(payload)
    print(json.dumps({"decision": "allow"}))


if __name__ == "__main__":
    main()
