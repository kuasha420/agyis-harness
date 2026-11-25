# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Arafat Zahan (@kuasha420)
# Corporate Stewardship & Infrastructure: Purrfect Software Limited (PSL)
# Governed by: ICARO-42/b Ordinance (Company-Supported Personal IP Framework)

"""
Read-only sibling Antigravity conversation SQLite enrichment helpers (ADR-030 / G0.1).
Extracts token usage, context window limits, and model metadata from conversations/<cid>.db
without clobbering transcript paths or mutating source DBs.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
import sqlite3
from typing import Any, Dict, Optional

from harness.trajectory.protobuf import extract_context_window_from_json, extract_usage_from_protobuf


def find_sibling_conversation_db(transcript_path: Path, session_id: str) -> Optional[Path]:
    """Locates sibling conversations/<session_id>.db without probing arbitrary host directories."""
    for parent in transcript_path.parents:
        if parent.name == session_id:
            cand = parent.parent.parent / "conversations" / f"{session_id}.db"
            if cand.is_file():
                return cand
            break
    env_dir = (
        os.environ.get("AGYIS_CONVERSATIONS_DIR")
        or os.environ.get("ANTIGRAVITY_CONVERSATIONS_DIR")
        or os.environ.get("GEMINI_CONVERSATIONS_DIR")
    )
    if env_dir and env_dir.strip():
        cand = Path(env_dir.strip()).expanduser() / f"{session_id}.db"
        if cand.is_file():
            return cand
    env_app = os.environ.get("ANTIGRAVITY_APP_DATA_DIR")
    if env_app and env_app.strip():
        cand = Path(env_app.strip()).expanduser() / "conversations" / f"{session_id}.db"
        if cand.is_file():
            return cand
    return None


def parse_json_gen_row(raw_str: str) -> Dict[str, Any]:
    """Parses JSON-serialized gen_metadata row into normalized token/model fields."""
    try:
        d = json.loads(raw_str)
    except (json.JSONDecodeError, ValueError, TypeError):
        return {}
    if not isinstance(d, dict):
        return {}
    est, mct = extract_context_window_from_json(d)
    meta = d.get("metadata") if isinstance(d.get("metadata"), dict) else {}
    csm = d.get("chatStartMetadata") if isinstance(d.get("chatStartMetadata"), dict) else {}
    usage = d.get("usageMetadata") or d.get("modelUsage") or meta.get("modelUsage") or {}
    if not isinstance(usage, dict):
        usage = {}

    def _p(val: Any) -> int:
        return int(val) if isinstance(val, (int, float)) and int(val) > 0 else 0

    in_t = _p(usage.get("inputTokens") or usage.get("input_tokens") or usage.get("promptTokenCount") or d.get("input_tokens"))
    ca_t = _p(usage.get("cacheReadTokens") or usage.get("cache_read_tokens") or usage.get("cachedContentTokenCount") or d.get("cache_read_tokens"))
    out_t = _p(usage.get("outputTokens") or usage.get("output_tokens") or usage.get("candidatesTokenCount") or d.get("output_tokens"))
    th_t = _p(usage.get("thoughtTokens") or usage.get("thought_tokens") or usage.get("thoughtsTokenCount") or d.get("thought_tokens"))
    slug = d.get("modelSlug") or d.get("model_slug") or csm.get("modelSlug") or meta.get("modelSlug") or d.get("model")
    disp = d.get("modelDisplayName") or d.get("model_display_name") or csm.get("modelDisplayName") or meta.get("modelDisplayName")
    return {
        "in": in_t, "cache": ca_t, "out": out_t, "thought": th_t, "est": est, "mct": mct,
        "slug": slug.strip() if isinstance(slug, str) and slug.strip() else "",
        "disp": disp.strip() if isinstance(disp, str) and disp.strip() else "",
    }


def read_sibling_gen_metadata(db_path: Optional[Path]) -> Dict[str, Any]:
    """Reads token totals, max_context_tokens, and model names from sibling conversation DB."""
    if db_path is None or not db_path.is_file():
        return {}
    conn: Optional[sqlite3.Connection] = None
    gen_rows = []
    step_meta_rows = []
    try:
        conn = sqlite3.connect(f"file:{db_path.resolve()}?mode=ro", uri=True, timeout=0.5)
        conn.execute("PRAGMA query_only = ON")
        cur = conn.cursor()
        cur.execute("SELECT name FROM sqlite_master WHERE type='table'")
        tables = {r[0] for r in cur.fetchall()}

        if "gen_metadata" in tables:
            cur.execute("PRAGMA table_info(gen_metadata)")
            cols = {r[1] for r in cur.fetchall()}
            if "data" in cols:
                order_col = "idx" if "idx" in cols else "rowid"
                cur.execute(f"SELECT data FROM gen_metadata ORDER BY {order_col} DESC LIMIT 500")
                gen_rows = cur.fetchall()

        if "steps" in tables:
            cur.execute("PRAGMA table_info(steps)")
            s_cols = {r[1] for r in cur.fetchall()}
            if "metadata" in s_cols:
                order_col = "idx" if "idx" in s_cols else "rowid"
                cur.execute(f"SELECT metadata FROM steps WHERE metadata IS NOT NULL ORDER BY {order_col} DESC LIMIT 1000")
                step_meta_rows = cur.fetchall()
    except (sqlite3.Error, OSError):
        return {}
    finally:
        if conn is not None:
            try:
                conn.close()
            except sqlite3.Error:
                pass

    tot_in = tot_cache = tot_out = tot_thought = max_ctx = peak_ctx = 0
    slug = disp = ""
    for (raw,) in gen_rows:
        if not raw:
            continue
        if isinstance(raw, (bytes, bytearray)):
            gm = extract_usage_from_protobuf(bytes(raw))
            tot_in += gm.input_tokens
            tot_cache += gm.cache_read_tokens
            tot_out += gm.output_tokens
            tot_thought += gm.thought_tokens
            max_ctx = max(max_ctx, gm.max_context_tokens)
            peak_ctx = max(peak_ctx, gm.total_prompt_tokens or gm.estimated_tokens)
            slug = slug or gm.model_slug
            disp = disp or gm.model_display_name
        elif isinstance(raw, str):
            parsed = parse_json_gen_row(raw)
            if parsed:
                tot_in += parsed["in"]
                tot_cache += parsed["cache"]
                tot_out += parsed["out"]
                tot_thought += parsed["thought"]
                max_ctx = max(max_ctx, parsed["mct"])
                peak_ctx = max(peak_ctx, (parsed["in"] + parsed["cache"]) or parsed["est"])
                slug = slug or parsed["slug"]
                disp = disp or parsed["disp"]

    if (tot_in == 0 and tot_cache == 0) or (not slug and not disp):
        s_in = s_cache = s_out = s_thought = 0
        for (raw,) in step_meta_rows:
            if not isinstance(raw, (bytes, bytearray)):
                continue
            sm = extract_usage_from_protobuf(bytes(raw))
            if tot_in == 0 and tot_cache == 0:
                s_in += sm.input_tokens
                s_cache += sm.cache_read_tokens
                s_out += sm.output_tokens
                s_thought += sm.thought_tokens
                max_ctx = max(max_ctx, sm.max_context_tokens)
                peak_ctx = max(peak_ctx, sm.total_prompt_tokens or sm.estimated_tokens)
            slug = slug or sm.model_slug
            disp = disp or sm.model_display_name
        if tot_in == 0 and tot_cache == 0 and (s_in > 0 or s_cache > 0 or s_out > 0):
            tot_in, tot_cache, tot_out, tot_thought = s_in, s_cache, s_out, s_thought

    return {
        "model_slug": slug or None,
        "model_display_name": disp or None,
        "max_context_tokens": max_ctx or None,
        "total_input_tokens": tot_in if tot_in > 0 else None,
        "total_cache_read_tokens": tot_cache if tot_cache > 0 else None,
        "total_output_tokens": tot_out if tot_out > 0 else None,
        "total_thought_tokens": tot_thought if tot_thought > 0 else None,
        "peak_context_tokens": peak_ctx if peak_ctx > 0 else None,
    }


__all__ = [
    "find_sibling_conversation_db",
    "parse_json_gen_row",
    "read_sibling_gen_metadata",
]
