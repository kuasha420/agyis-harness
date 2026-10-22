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
from typing import Any, Dict, Optional, TextIO

COMPACTION_THRESHOLD: int = 50000
AMBER_THRESHOLD: int = 35000
RED_THRESHOLD: int = 45000
CHECKPOINT_STEP_TYPE: int = 23  # Google Antigravity compaction checkpoint enum (0x17)

LOCKED_CONVERSATION_IDS: set[str] = set()


def clear_locked_conversations() -> None:
    """Clears recorded locked conversation identifiers."""
    LOCKED_CONVERSATION_IDS.clear()


def is_checkpoint_step(step_type: Any) -> bool:
    """Returns True if the step_type represents a compaction checkpoint (23 / 0x17)."""
    try:
        return int(step_type) == CHECKPOINT_STEP_TYPE
    except (ValueError, TypeError):
        return False


def get_conversations_dir() -> Path:
    """Resolves the directory containing Antigravity conversation SQLite databases."""
    env_dir = os.environ.get("ANTIGRAVITY_CONVERSATIONS_DIR") or os.environ.get("GEMINI_CONVERSATIONS_DIR")
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


def extract_tokens_from_protobuf_metadata(raw_bytes: bytes) -> int:
    """Extracts prompt or input token count from protobuf metadata if present."""
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
    return 0


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
    if not conversation_id or conversation_id == "default":
        return 0

    base_dir = db_dir or get_conversations_dir()
    db_path = base_dir / f"{conversation_id}.db"
    if not db_path.is_file():
        return 0

    conn: Optional[sqlite3.Connection] = None
    try:
        # Strict read-only mode with URI connection and bounded timeout (ADR-016)
        eff_timeout = timeout if timeout is not None else 0.5
        uri_path = f"file:{db_path.resolve()}?mode=ro"
        conn = sqlite3.connect(uri_path, uri=True, timeout=eff_timeout)
        cursor = conn.cursor()

        # Discover available tables
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
        tables = {row[0] for row in cursor.fetchall()}

        tokens_found = 0
        checkpoint_hit = False

        # Strategy 1: Check `steps` table
        if "steps" in tables:
            cursor.execute("PRAGMA table_info(steps)")
            col_names = {row[1] for row in cursor.fetchall()}

            # Chronological ordering resolution: idx DESC -> step_index DESC -> rowid DESC
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
                        # Compaction checkpoint barrier: older steps are pre-compaction
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

                        # Check generator_metadata
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

                        # Check direct token keys
                        direct_tokens = (
                            data.get("token_count")
                            or data.get("tokens")
                            or data.get("num_tokens")
                            or data.get("numTokens")
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
            if not tokens_found and not checkpoint_hit and "metadata" in col_names:
                cols = "metadata, step_type" if has_step_type else "metadata"
                cursor.execute(f"SELECT {cols} FROM steps {where_step_filter} {order_clause} LIMIT 10")
                for row in cursor.fetchall():
                    raw_meta = row[0]
                    st = row[1] if has_step_type else None
                    if has_step_type and is_checkpoint_step(st):
                        # Compaction checkpoint barrier: older steps are pre-compaction
                        checkpoint_hit = True
                        break
                    if not raw_meta:
                        continue
                    if isinstance(raw_meta, str):
                        try:
                            d = json.loads(raw_meta)
                            if isinstance(d, dict):
                                if is_checkpoint_step(d.get("step_type")):
                                    checkpoint_hit = True
                                    break
                                t = d.get("num_tokens") or d.get("numTokens") or d.get("tokens") or d.get("token_count")
                                if isinstance(t, (int, float)) and t > 0:
                                    tokens_found = int(t)
                                    break
                        except Exception:
                            pass
                    elif isinstance(raw_meta, bytes):
                        pb_tokens = extract_tokens_from_protobuf_metadata(raw_meta)
                        if pb_tokens > 0:
                            tokens_found = pb_tokens
                            break

        # Strategy 2: Check `gen_metadata` table if steps didn't yield tokens
        if not tokens_found and not checkpoint_hit and "gen_metadata" in tables:
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
                            t = d.get("num_tokens") or d.get("numTokens") or d.get("tokens")
                            if isinstance(t, (int, float)) and t > 0:
                                tokens_found = int(t)
                                break
                        except Exception:
                            pass
                    elif isinstance(gen_data, bytes):
                        pb_tokens = extract_tokens_from_protobuf_metadata(gen_data)
                        if pb_tokens > 0:
                            tokens_found = pb_tokens
                            break

        return tokens_found
    except sqlite3.OperationalError as oe:
        if "lock" in str(oe).lower() or "busy" in str(oe).lower():
            LOCKED_CONVERSATION_IDS.add(conversation_id)
        return 0
    except Exception:
        return 0
    finally:
        if conn is not None:
            try:
                conn.close()
            except Exception:
                pass


def get_urgency_tier(tokens: int) -> str:
    """Classifies token count into 3-tier urgency category."""
    if tokens >= RED_THRESHOLD:
        return "CRITICAL"
    elif tokens >= AMBER_THRESHOLD:
        return "ELEVATED"
    return "SAFE"


def format_terminal_gauge(tokens: int, threshold: int = COMPACTION_THRESHOLD) -> str:
    """Generates an ANSI terminal progress gauge with dynamic urgency color and bell alert."""
    denom = threshold if threshold > 0 else COMPACTION_THRESHOLD
    percentage = min(100.0, (tokens / denom) * 100) if denom > 0 else 0.0
    filled_blocks = int((tokens / denom) * 20) if denom > 0 else 0
    filled_blocks = max(0, min(20, filled_blocks))
    bar = "█" * filled_blocks + "░" * (20 - filled_blocks)

    if tokens >= RED_THRESHOLD:
        color = "\033[1;31m"  # Bold Red
        status = "CRITICAL (COMPACTION IMMINENT)"
        bell = "\a"
    elif tokens >= AMBER_THRESHOLD:
        color = "\033[1;33m"  # Bold Yellow/Amber
        status = "ELEVATED (APPROACHING THRESHOLD)"
        bell = ""
    else:
        color = "\033[1;32m"  # Bold Green
        status = "SAFE"
        bell = ""

    reset = "\033[0m"
    return f"{bell}{color}[AGYIS TOKEN GAUGE]{reset} [{bar}] {tokens:,} / {denom:,} ({percentage:.1f}%) - {color}{status}{reset}"


def render_terminal_gauge(tokens: int) -> str:
    """Convenience alias for format_terminal_gauge(tokens, COMPACTION_THRESHOLD)."""
    return format_terminal_gauge(tokens, COMPACTION_THRESHOLD)


def check_token_proximity(
    conversation_id: str,
    db_dir: Optional[Path] = None,
    emit_stderr: bool = True,
) -> Dict[str, Any]:
    """
    Evaluates active conversation token proximity and emits an ANSI warning
    to sys.stderr if tokens have reached or exceeded the amber threshold.
    Always returns a decision dict {"decision": "allow"}.
    """
    tokens = get_active_conversation_tokens(conversation_id, db_dir=db_dir)
    tier = get_urgency_tier(tokens)
    warned = False

    if tokens >= AMBER_THRESHOLD:
        gauge = format_terminal_gauge(tokens)
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
        "tier": tier,
        "warned": warned,
    }


def run_token_proximity_guard(
    payload: Any,
    stderr: Optional[TextIO] = None,
) -> Dict[str, Any]:
    """
    Core functional dispatcher for token proximity lifecycle hook.
    Parses turn payload from stdin or argument, monitors tokens, emits warning
    to stderr if >= 35,000 tokens, and returns allow decision.
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
    tokens = get_active_conversation_tokens(conv_id)

    if tokens >= AMBER_THRESHOLD:
        gauge = format_terminal_gauge(tokens)
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
        tokens = get_active_conversation_tokens(conv_id)
        print(json.dumps({"status": "ok", "tokens": tokens, "tier": get_urgency_tier(tokens)}))
        return
    elif action == "render_gauge":
        tokens = int(payload.get("tokens", 0))
        print(json.dumps({"status": "ok", "gauge": format_terminal_gauge(tokens)}))
        return

    # PreToolUse token proximity check
    run_token_proximity_guard(payload)
    print(json.dumps({"decision": "allow"}))


if __name__ == "__main__":
    main()
