# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Arafat Zahan (@kuasha420)
# Corporate Stewardship & Infrastructure: Purrfect Software Limited (PSL)
# Governed by: ICARO-42/b Ordinance (Company-Supported Personal IP Framework)

"""
Cleanroom Telemetry Extractor & Transcript Parser (ADR-014, ADR-030).
Decoupled into harness package core to allow standalone daemon execution without pipeline dependency.
"""

from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path
import re
import sqlite3
from typing import Any, Dict, List, Optional, Tuple

from harness.telemetry.config import infer_client_surface, resolve_machine_id
from harness.telemetry.models import normalize_model, normalize_utc_iso
from harness.telemetry.schema import SCHEMA_SQL, ensure_sync_columns
from harness.telemetry.sibling_db import find_sibling_conversation_db, read_sibling_gen_metadata
from harness.trajectory.protobuf import extract_context_window_from_json


def parse_iso_ts(ts_str: Optional[str]) -> Optional[datetime]:
    """Parses ISO timestamp string to datetime object."""
    if not ts_str:
        return None
    cleaned = ts_str.strip().replace("Z", "+00:00")
    try:
        return datetime.fromisoformat(cleaned)
    except (ValueError, TypeError):
        return None


def calculate_duration(start_str: Optional[str], end_str: Optional[str]) -> Optional[float]:
    """Calculates elapsed seconds between two ISO timestamp strings."""
    t1 = parse_iso_ts(start_str)
    t2 = parse_iso_ts(end_str)
    if t1 and t2:
        if (t1.tzinfo is None) != (t2.tzinfo is None):
            if t1.tzinfo is None:
                t1 = t1.replace(tzinfo=timezone.utc)
            if t2.tzinfo is None:
                t2 = t2.replace(tzinfo=timezone.utc)
        return abs((t2 - t1).total_seconds())
    return None


_INTERVENTION_RULES: Tuple[Tuple[str, Tuple[str, ...]], ...] = (
    ("STEERING", ("stop", "don't", "dont", "wait", "no,", "no!", "wrong", "drifted", "cancel", "undo")),
    ("CONFIRMATION", ("lgtm", "looks good", "proceed", "approved", "go ahead", "yes, please", "sure", "approved this document")),
    ("CREDENTIALS", ("password", "token", "secret", "api_key", "credentials", "auth")),
    ("CONTINUATION", ("continue", "next", "keep going", "proceed with next")),
)


def classify_intervention(text: str, preceding_failed: bool) -> str:
    """Classifies user intervention prompt into behavioral category."""
    lower = text.lower().strip()
    if lower.startswith("/boost") or "/boost " in lower:
        return "BOOST_ORCHESTRATION"
    if lower.startswith("/plan") or "/plan " in lower:
        return "PLAN_INITIATION"
    if lower.startswith("/agent-builder") or "/agent-builder " in lower or "agent-builder" in lower:
        return "AGENT_BUILDER_INVOCATION"
    if preceding_failed:
        return "ERROR_RECOVERY"
    for label, keywords in _INTERVENTION_RULES:
        if any(k in lower for k in keywords):
            return label
    return "OPERATOR_GUIDANCE"


_COMMAND_SUBSTR_CATS: Tuple[Tuple[str, Tuple[str, ...]], ...] = (
    ("test_runner", (
        "pytest", "unittest", "test_", "-m unittest", "pnpm test", "npm test", "yarn test",
        "cargo test", "go test", "jest", "vitest", "mocha", "playwright", "cypress",
        "harness.cli test", "python3 -m unittest", "python -m unittest",
    )),
)

_COMMAND_PREFIX_CATS: Tuple[Tuple[str, Tuple[str, ...]], ...] = (
    ("git", ("git ", "gh ")),
    ("grep_search", ("grep ", "rg ", "ripgrep ", "ag ", "diff ")),
    ("file_search", ("find ", "fd ", "ls ", "tree ", "locate ")),
    ("package_manager", (
        "pnpm ", "npm ", "yarn ", "bun ", "pip ", "pip3 ", "uv ", "pacman ", "yay ",
        "apt ", "apt-get ", "cargo add", "cargo install",
    )),
    ("build_compile", ("tsc", "esbuild", "cargo build", "go build", "make", "gcc", "g++", "clang", "vite build", "webpack", "next build", "ninja")),
    ("python_exec", ("python ", "python3 ", "python3.12 ", "ipython ")),
    ("system_probe", ("which ", "command -v", "ps ", "top ", "htop ", "uname", "uptime", "whoami", "id ", "df ", "du ", "systemctl ", "journalctl ")),
    ("network", ("curl ", "wget ", "ping ", "ssh ", "scp ", "rsync ", "nc ")),
    ("file_system", ("cat ", "head ", "tail ", "mkdir ", "cp ", "mv ", "rm ", "touch ", "chmod ", "chown ", "sed ", "awk ")),
)


def classify_command(cmd_line: Optional[str]) -> Optional[str]:
    """Classifies a shell command into high-level operational categories."""
    if not cmd_line or not isinstance(cmd_line, str) or not cmd_line.strip():
        return None
    lower = cmd_line.strip().lower()
    for cat, kws in _COMMAND_SUBSTR_CATS:
        if any(k in lower for k in kws):
            return cat
    for cat, kws in _COMMAND_PREFIX_CATS:
        if any(lower.startswith(k) or f" {k}" in lower for k in kws):
            return cat
    return "other"


def ensure_volume_columns(conn: sqlite3.Connection) -> None:
    """Non-destructively ensures volume & character distribution columns exist."""
    cur = conn.cursor()
    cur.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='tool_calls'")
    if not cur.fetchone():
        return
    cur.execute("PRAGMA table_info(tool_calls)")
    existing_cols = {row[1] for row in cur.fetchall()}

    new_cols = [
        ("output_length_chars", "INTEGER"),
        ("output_lines", "INTEGER"),
        ("arguments_length_chars", "INTEGER"),
        ("command_category", "TEXT"),
        ("is_truncated", "INTEGER DEFAULT 0"),
    ]
    for col_name, col_type in new_cols:
        if col_name not in existing_cols:
            try:
                cur.execute(f"ALTER TABLE tool_calls ADD COLUMN {col_name} {col_type}")
            except sqlite3.OperationalError:
                pass

    cur.execute("CREATE INDEX IF NOT EXISTS idx_tools_category ON tool_calls(command_category)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_tools_output_len ON tool_calls(output_length_chars)")
    conn.commit()


def ensure_telemetry_schema(conn: sqlite3.Connection) -> None:
    """Ensures all canonical telemetry tables, columns, and unique indexes exist."""
    cur = conn.cursor()
    cur.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='sessions'")
    if cur.fetchone():
        ensure_sync_columns(conn)
        ensure_volume_columns(conn)
    conn.cursor().executescript(SCHEMA_SQL)
    ensure_volume_columns(conn)
    ensure_sync_columns(conn)


_SOURCE_KIND_RANK: Dict[str, int] = {
    "sqlite_db": 1,
    "transcript": 2,
    "transcript_full": 3,
}


def _infer_source_kind_rank(source_kind: Optional[str], transcript_path: Optional[str]) -> int:
    if source_kind and source_kind in _SOURCE_KIND_RANK:
        return _SOURCE_KIND_RANK[source_kind]
    if transcript_path:
        low = str(transcript_path).lower()
        if low.endswith("transcript_full.jsonl"):
            return 3
        if low.endswith("transcript.jsonl"):
            return 2
        if low.endswith(".db"):
            return 1
    return 0


def _normalize_session_row_timestamps(row: Dict[str, Any]) -> Dict[str, Any]:
    out = dict(row)
    for k in ("start_time", "end_time", "remote_synced_at"):
        if out.get(k) is not None:
            out[k] = normalize_utc_iso(out[k])
    return out


def _normalize_child_rows(
    step_rows: List[Dict[str, Any]],
    tool_rows: List[Dict[str, Any]],
    interv_rows: List[Dict[str, Any]],
) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]], List[Dict[str, Any]]]:
    norm_steps = []
    for r in step_rows:
        nr = dict(r)
        if nr.get("created_at") is not None:
            nr["created_at"] = normalize_utc_iso(nr["created_at"])
        norm_steps.append(nr)
    norm_tools = []
    for r in tool_rows:
        nr = dict(r)
        for k in ("started_at", "completed_at"):
            if nr.get(k) is not None:
                nr[k] = normalize_utc_iso(nr[k])
        norm_tools.append(nr)
    norm_intervs = []
    for r in interv_rows:
        nr = dict(r)
        if nr.get("created_at") is not None:
            nr["created_at"] = normalize_utc_iso(nr["created_at"])
        norm_intervs.append(nr)
    return norm_steps, norm_tools, norm_intervs


def upsert_session_telemetry(
    conn: sqlite3.Connection,
    session_row: Dict[str, Any],
    step_rows: List[Dict[str, Any]],
    tool_rows: List[Dict[str, Any]],
    interv_rows: List[Dict[str, Any]],
    commit: bool = True,
) -> None:
    """Atomically upserts session, steps, tool_calls, and user_interventions via schema.py."""
    cur = conn.cursor()
    s_row = _normalize_session_row_timestamps(session_row)
    s_id = s_row["session_id"]

    # Ensure additive columns exist before reading/writing expanded schema
    cur.execute("PRAGMA table_info(sessions)")
    existing_cols = {r[1] for r in cur.fetchall()}
    if "source_kind" not in existing_cols:
        ensure_sync_columns(conn)

    cur.execute(
        "SELECT remote_synced_at, origin_developer, total_steps, source_kind, transcript_path "
        "FROM sessions WHERE session_id = ?",
        (s_id,),
    )
    existing = cur.fetchone()
    if existing:
        existing_synced_at, existing_origin, existing_steps, existing_sk, existing_tp = existing
        existing_rank = _infer_source_kind_rank(existing_sk, existing_tp)
        incoming_rank = _infer_source_kind_rank(s_row.get("source_kind"), s_row.get("transcript_path"))
        if incoming_rank < existing_rank:
            # Preserve richer transcript source and child rows; enrich only missing/superior metadata.
            cur.execute(
                """
                UPDATE sessions
                SET origin_machine = COALESCE(origin_machine, ?),
                    client_surface = COALESCE(client_surface, ?),
                    model = CASE WHEN model IS NULL OR model = 'Unknown' THEN COALESCE(?, model) ELSE model END,
                    model_slug = COALESCE(model_slug, ?),
                    model_display_name = COALESCE(model_display_name, ?),
                    max_context_tokens = COALESCE(max_context_tokens, ?),
                    total_input_tokens = CASE
                        WHEN ? IS NOT NULL AND (total_input_tokens IS NULL OR ? > total_input_tokens)
                        THEN ? ELSE total_input_tokens END,
                    total_cache_read_tokens = CASE
                        WHEN ? IS NOT NULL AND (total_cache_read_tokens IS NULL OR ? > total_cache_read_tokens)
                        THEN ? ELSE total_cache_read_tokens END,
                    total_output_tokens = CASE
                        WHEN ? IS NOT NULL AND (total_output_tokens IS NULL OR ? > total_output_tokens)
                        THEN ? ELSE total_output_tokens END,
                    total_thought_tokens = CASE
                        WHEN ? IS NOT NULL AND (total_thought_tokens IS NULL OR ? > total_thought_tokens)
                        THEN ? ELSE total_thought_tokens END,
                    peak_context_tokens = CASE
                        WHEN ? IS NOT NULL AND (peak_context_tokens IS NULL OR ? > peak_context_tokens)
                        THEN ? ELSE peak_context_tokens END
                WHERE session_id = ?
                """,
                (
                    s_row.get("origin_machine"),
                    s_row.get("client_surface"),
                    s_row.get("model"),
                    s_row.get("model_slug"),
                    s_row.get("model_display_name"),
                    s_row.get("max_context_tokens"),
                    s_row.get("total_input_tokens"), s_row.get("total_input_tokens"), s_row.get("total_input_tokens"),
                    s_row.get("total_cache_read_tokens"), s_row.get("total_cache_read_tokens"), s_row.get("total_cache_read_tokens"),
                    s_row.get("total_output_tokens"), s_row.get("total_output_tokens"), s_row.get("total_output_tokens"),
                    s_row.get("total_thought_tokens"), s_row.get("total_thought_tokens"), s_row.get("total_thought_tokens"),
                    s_row.get("peak_context_tokens"), s_row.get("peak_context_tokens"), s_row.get("peak_context_tokens"),
                    s_id,
                ),
            )
            if commit:
                conn.commit()
            return

        if existing_steps is not None and (s_row.get("total_steps") or 0) > existing_steps:
            s_row["remote_synced_at"] = None
        elif existing_synced_at and not s_row.get("remote_synced_at"):
            s_row["remote_synced_at"] = existing_synced_at
        if existing_origin and existing_origin != "local":
            s_row["origin_developer"] = existing_origin

    for tbl in ("tool_calls", "user_interventions", "steps"):
        cur.execute(f"DELETE FROM {tbl} WHERE session_id = ?", (s_id,))

    sess_cols = (
        "session_id", "start_time", "end_time", "duration_seconds", "total_steps",
        "model", "workspace_path", "transcript_path", "file_size_bytes", "has_errors",
        "tool_call_count", "tool_error_count", "intervention_count",
        "origin_developer", "remote_synced_at",
        "origin_machine", "client_surface", "source_kind",
        "model_slug", "model_display_name", "max_context_tokens",
        "total_input_tokens", "total_cache_read_tokens", "total_output_tokens",
        "total_thought_tokens", "peak_context_tokens", "server_seq",
    )
    sess_defaults = {
        "has_errors": 0, "tool_call_count": 0, "tool_error_count": 0,
        "intervention_count": 0, "origin_developer": "local",
    }
    sess_vals = tuple(s_row.get(c, sess_defaults.get(c)) for c in sess_cols)
    coalesce_cols = {
        "origin_machine", "client_surface", "source_kind",
        "model_slug", "model_display_name", "max_context_tokens",
        "total_input_tokens", "total_cache_read_tokens", "total_output_tokens",
        "total_thought_tokens", "peak_context_tokens", "server_seq",
    }
    update_parts = []
    for c in sess_cols[1:]:
        if c == "model":
            update_parts.append(
                "model=CASE WHEN excluded.model IS NOT NULL AND excluded.model != 'Unknown' "
                "THEN excluded.model ELSE COALESCE(sessions.model, excluded.model) END"
            )
        elif c in coalesce_cols:
            update_parts.append(f"{c}=COALESCE(excluded.{c}, sessions.{c})")
        else:
            update_parts.append(f"{c}=excluded.{c}")
    updates = ", ".join(update_parts)
    cur.execute(
        f"INSERT INTO sessions ({', '.join(sess_cols)}) VALUES ({', '.join(['?'] * len(sess_cols))}) "
        f"ON CONFLICT(session_id) DO UPDATE SET {updates}",
        sess_vals,
    )

    norm_steps, norm_tools, norm_intervs = _normalize_child_rows(step_rows, tool_rows, interv_rows)
    child_specs = (
        (
            "steps",
            ("session_id", "step_index", "step_type", "source", "status", "created_at",
             "content_length", "content_snippet", "has_thinking", "thinking_length", "tool_count"),
            {},
            norm_steps,
        ),
        (
            "tool_calls",
            ("session_id", "step_index", "result_step_index", "tool_name", "arguments_json",
             "arguments_snippet", "target_path", "command_line", "started_at", "completed_at",
             "duration_seconds", "status", "exit_code", "error_snippet", "is_loop_candidate",
             "output_length_chars", "output_lines", "arguments_length_chars", "command_category", "is_truncated"),
            {"is_loop_candidate": 0, "output_length_chars": 0, "output_lines": 0, "arguments_length_chars": 0, "is_truncated": 0},
            norm_tools,
        ),
        (
            "user_interventions",
            ("session_id", "step_index", "created_at", "prompt_text", "prompt_length",
             "preceding_tool_failed", "preceding_tool_name", "preceding_error_snippet", "intervention_type"),
            {"prompt_length": 0, "preceding_tool_failed": 0, "preceding_tool_name": "", "preceding_error_snippet": ""},
            norm_intervs,
        ),
    )
    for tbl, cols, defaults, rows in child_specs:
        if rows:
            cur.executemany(
                f"INSERT OR IGNORE INTO {tbl} ({', '.join(cols)}) VALUES ({', '.join(['?'] * len(cols))})",
                [tuple(r.get(c, defaults.get(c)) for c in cols) for r in rows],
            )

    if commit:
        conn.commit()


_MODEL_ID_PATTERN = re.compile(
    r"\b(gemini-4-(?:neon|hydrogen|argon|1m)(?:-[a-z0-9._-]+)?|"
    r"gemini-3\.8-flash(?:-[a-z0-9._-]+)?|"
    r"gemini-[234](?:\.\d+)?-(?:pro|flash|ultra)(?:-[a-z0-9._-]+)?|"
    r"claude-(?:sonnet|opus|haiku)-[0-9a-z._-]+|"
    r"claude-[0-9._-]+-(?:sonnet|opus|haiku)(?:-[a-z0-9._-]+)?|"
    r"gpt-oss-120b(?:-[a-z0-9._-]+)?|"
    r"gpt-[45](?:\.\d+)?(?:-[a-z0-9._-]+)?)\b",
    re.IGNORECASE,
)

_WORKSPACE_PATTERNS: Tuple[re.Pattern[str], ...] = (
    re.compile(r"Active Workspaces:\s*\n\s*-\s*(/[^\n\r]+)"),
    re.compile(r"Command Working Directory:\s*(/[^\n\r]+)"),
    re.compile(r"(/(?:home|Users|root|workspace|var|opt|srv)(?:/[a-zA-Z0-9_.\-]+)*/Dev/[a-zA-Z0-9_.\-]+)"),
)


def _extract_step_model(step: Dict[str, Any]) -> Optional[str]:
    """Extracts explicit model identifier from step fields or nested metadata (incl. Gemini 4 Neon/Hydrogen)."""
    for key in ("model", "response_model", "responseModel", "model_id", "modelId"):
        val = step.get(key)
        if isinstance(val, str) and val.strip():
            return val.strip()
    meta = step.get("metadata")
    if isinstance(meta, dict):
        for sub_key in ("modelUsage", "model_usage", "generatorMetadata", "generator_metadata"):
            sub = meta.get(sub_key)
            if isinstance(sub, dict):
                for m_key in ("model", "responseModel", "response_model", "modelId"):
                    val = sub.get(m_key)
                    if isinstance(val, str) and val.strip():
                        return val.strip()
        for m_key in ("model", "responseModel", "response_model"):
            val = meta.get(m_key)
            if isinstance(val, str) and val.strip():
                return val.strip()
    return None


def _extract_step_usage_and_model(
    step: Dict[str, Any],
) -> Tuple[Optional[str], Optional[str], int, int, int, int, int, int]:
    """Extracts (model_slug, model_display_name, in_tok, cache_tok, out_tok, thought_tok, est_tok, max_ctx)."""
    meta = step.get("metadata") if isinstance(step.get("metadata"), dict) else {}
    usage = meta.get("modelUsage") or meta.get("model_usage") or {}
    if not isinstance(usage, dict):
        usage = {}
    slug = step.get("model_slug") or step.get("modelSlug") or meta.get("modelSlug") or meta.get("model_slug") or usage.get("modelSlug")
    disp = step.get("model_display_name") or step.get("modelDisplayName") or meta.get("modelDisplayName") or meta.get("model_display_name")
    slug_s = slug.strip() if isinstance(slug, str) and slug.strip() else None
    disp_s = disp.strip() if isinstance(disp, str) and disp.strip() else None

    def _int(val: Any) -> int:
        return int(val) if isinstance(val, (int, float)) and int(val) > 0 else 0

    in_tok = _int(step.get("input_tokens") or step.get("inputTokens") or usage.get("inputTokens") or usage.get("input_tokens") or usage.get("promptTokenCount"))
    cache_tok = _int(step.get("cache_read_tokens") or step.get("cacheReadTokens") or usage.get("cacheReadTokens") or usage.get("cache_read_tokens") or usage.get("cachedContentTokenCount"))
    out_tok = _int(step.get("output_tokens") or step.get("outputTokens") or usage.get("outputTokens") or usage.get("output_tokens") or usage.get("candidatesTokenCount"))
    thought_tok = _int(step.get("thought_tokens") or step.get("thoughtTokens") or usage.get("thoughtTokens") or usage.get("thought_tokens") or usage.get("thoughtsTokenCount"))
    est_tok, max_ctx = extract_context_window_from_json(step)
    return slug_s, disp_s, in_tok, cache_tok, out_tok, thought_tok, est_tok, max_ctx


def extract_session(
    transcript_path: Path,
) -> Optional[Tuple[Dict[str, Any], List[Dict[str, Any]], List[Dict[str, Any]], List[Dict[str, Any]]]]:
    """Extracts session, steps, tool calls, and user interventions from transcript JSONL."""
    session_id = transcript_path.parts[-4] if len(transcript_path.parts) >= 4 else transcript_path.parent.name
    try:
        raw_size = transcript_path.stat().st_size
    except OSError:
        return None

    with open(transcript_path, encoding="utf-8", errors="replace") as f:
        steps: List[Dict[str, Any]] = []
        for line in f:
            if line.strip():
                try:
                    obj = json.loads(line)
                    if isinstance(obj, dict):
                        steps.append(obj)
                except (json.JSONDecodeError, ValueError):
                    continue

    if not steps:
        return None

    def _step_key(s: Any) -> int:
        if isinstance(s, dict):
            idx = s.get("step_index")
            if isinstance(idx, int):
                return idx
        return 0

    steps.sort(key=_step_key)
    start_time = normalize_utc_iso(steps[0].get("created_at"))
    end_time = normalize_utc_iso(steps[-1].get("created_at"))
    duration_s = calculate_duration(start_time, end_time)

    model_detected = "Unknown"
    model_slug: Optional[str] = None
    model_display_name: Optional[str] = None
    step_in_tot = step_cache_tot = step_out_tot = step_thought_tot = step_max_ctx = step_peak_ctx = 0
    workspace_detected = ""
    tool_calls_extracted: List[Dict[str, Any]] = []
    interventions_extracted: List[Dict[str, Any]] = []
    has_errors, tool_error_count = False, 0
    step_by_idx = {
        s.get("step_index"): s
        for s in steps
        if isinstance(s, dict) and isinstance(s.get("step_index"), int)
    }
    recent_tool_failed, recent_tool_name, recent_error_snippet = False, "", ""
    last_tool_sig, repeated_tool_count = None, 0

    for i, s in enumerate(steps):
        if not isinstance(s, dict):
            continue
        raw_idx = s.get("step_index")
        s_idx = raw_idx if isinstance(raw_idx, int) else i
        s_type, source = s.get("type", "UNKNOWN"), s.get("source", "UNKNOWN")
        content = str(s.get("content", ""))

        s_slug, s_disp, s_in, s_cache, s_out, s_thought, s_est, s_mct = _extract_step_usage_and_model(s)
        if s_slug:
            model_slug = s_slug
        if s_disp:
            model_display_name = s_disp
        step_in_tot += s_in
        step_cache_tot += s_cache
        step_out_tot += s_out
        step_thought_tot += s_thought
        step_max_ctx = max(step_max_ctx, s_mct)
        step_peak_ctx = max(step_peak_ctx, (s_in + s_cache) or s_est)

        s_model = _extract_step_model(s)
        if s_model:
            model_detected = s_model
        elif model_detected == "Unknown" and s_type in ("SYSTEM_MESSAGE", "USER_INPUT", "PLANNER_RESPONSE"):
            if "Model Selection" in content:
                m = re.search(r"Model Selection` from .*? to ([^\n\r`]+)", content)
                if m:
                    model_detected = m.group(1).strip().rstrip(".")
            if model_detected == "Unknown":
                m_id = _MODEL_ID_PATTERN.search(content)
                if m_id:
                    model_detected = m_id.group(1).strip()

        if not workspace_detected and content:
            for ws_pat in _WORKSPACE_PATTERNS:
                m = ws_pat.search(content)
                if m:
                    workspace_detected = m.group(1).strip()
                    break

        if s_idx > 0 and (s_type == "USER_INPUT" or source == "USER_EXPLICIT"):
            clean_prompt = re.sub(
                r"<USER_REQUEST>|\</USER_REQUEST\>|<ADDITIONAL_METADATA>[\s\S]*?</ADDITIONAL_METADATA>",
                "", content,
            ).strip()
            if clean_prompt:
                interventions_extracted.append({
                    "session_id": session_id, "step_index": s_idx,
                    "created_at": normalize_utc_iso(s.get("created_at")),
                    "prompt_text": clean_prompt, "prompt_length": len(clean_prompt),
                    "preceding_tool_failed": 1 if recent_tool_failed else 0,
                    "preceding_tool_name": recent_tool_name,
                    "preceding_error_snippet": recent_error_snippet[:500],
                    "intervention_type": classify_intervention(clean_prompt, recent_tool_failed),
                })

        raw_tools = s.get("tool_calls", [])
        if raw_tools and isinstance(raw_tools, list):
            for tool_offset, tc in enumerate(raw_tools):
                if not isinstance(tc, dict):
                    continue
                t_name = tc.get("name", "unknown")
                t_args = tc.get("modified_args") or tc.get("modifiedArgs") or tc.get("args", {})
                if isinstance(t_args, str):
                    try:
                        parsed_args = json.loads(t_args)
                        if isinstance(parsed_args, dict):
                            t_args = parsed_args
                    except (json.JSONDecodeError, ValueError):
                        pass
                target_path = (
                    t_args.get("Path")
                    or t_args.get("TargetFile")
                    or t_args.get("AbsolutePath")
                    or t_args.get("FilePath")
                    or t_args.get("Target")
                    or t_args.get("SearchPath")
                    or t_args.get("DirectoryPath")
                ) if isinstance(t_args, dict) else None
                cmd_line = t_args.get("CommandLine") if isinstance(t_args, dict) else None

                tool_sig = (t_name, str(target_path or cmd_line or t_args))
                is_loop = 0
                if tool_sig == last_tool_sig:
                    repeated_tool_count += 1
                    is_loop = 1 if repeated_tool_count >= 2 else 0
                else:
                    last_tool_sig, repeated_tool_count = tool_sig, 1

                res_idx = (s_idx + 1 + tool_offset) if isinstance(s_idx, int) else None
                res_step = step_by_idx.get(res_idx) if res_idx is not None else None
                t_status, exit_code, err_snippet = "SUCCESS", 0, ""
                res_content = str(res_step.get("content", "")) if isinstance(res_step, dict) else ""
                step_err = res_step.get("error") if isinstance(res_step, dict) else None
                started_at = completed_at = tool_duration = None

                if res_content:
                    m_created = re.search(r"Created At:\s*([^\n\r]+)", res_content)
                    m_completed = re.search(r"Completed At:\s*([^\n\r]+)", res_content)
                    if m_created and m_completed:
                        started_at = normalize_utc_iso(m_created.group(1).strip())
                        completed_at = normalize_utc_iso(m_completed.group(1).strip())
                        tool_duration = calculate_duration(started_at, completed_at)

                    m_exit = re.search(r"(?:failed with exit code:|exited with code)\s*(\d+)", res_content, re.IGNORECASE)
                    if m_exit:
                        exit_code = int(m_exit.group(1))
                        if exit_code != 0:
                            t_status, has_errors = "FAILED", True
                            tool_error_count += 1
                            err_snippet = res_content[:800]
                    elif step_err or "Encountered error in tool execution:" in res_content or (isinstance(res_step, dict) and res_step.get("status") == "ERROR"):
                        t_status = "ERROR"
                        exit_code = -1
                        has_errors = True
                        tool_error_count += 1
                        err_snippet = (str(step_err) if step_err else res_content)[:800]
                elif step_err or (isinstance(res_step, dict) and res_step.get("status") == "ERROR"):
                    t_status = "ERROR"
                    exit_code = -1
                    has_errors = True
                    tool_error_count += 1
                    err_snippet = str(step_err or "ERROR")[:800]

                if t_status in ("FAILED", "ERROR"):
                    recent_tool_failed, recent_tool_name, recent_error_snippet = True, t_name, err_snippet
                else:
                    recent_tool_failed, recent_tool_name, recent_error_snippet = False, "", ""

                args_json = json.dumps(t_args) if isinstance(t_args, dict) else str(t_args)
                is_trunc = 1 if (
                    res_content and ("<truncated" in res_content or "content" in (res_step or {}).get("truncated_fields", ()))
                ) else 0
                tool_calls_extracted.append({
                    "session_id": session_id, "step_index": s_idx, "result_step_index": res_idx if res_step else None,
                    "tool_name": t_name, "arguments_json": args_json, "arguments_snippet": str(t_args)[:250],
                    "target_path": str(target_path) if target_path else None,
                    "command_line": str(cmd_line) if cmd_line else None,
                    "started_at": started_at, "completed_at": completed_at, "duration_seconds": tool_duration,
                    "status": t_status, "exit_code": exit_code, "error_snippet": err_snippet,
                    "is_loop_candidate": is_loop, "output_length_chars": len(res_content) if res_content else 0,
                    "output_lines": (res_content.count("\n") + 1) if res_content else 0,
                    "arguments_length_chars": len(args_json),
                    "command_category": classify_command(cmd_line) if cmd_line else None, "is_truncated": is_trunc,
                })

    gen_meta = read_sibling_gen_metadata(find_sibling_conversation_db(transcript_path, session_id))
    model_slug = model_slug or gen_meta.get("model_slug")
    model_display_name = model_display_name or gen_meta.get("model_display_name")
    if model_detected == "Unknown":
        model_detected = model_slug or model_display_name or "Unknown"

    norm_model = normalize_model(model_detected, model_slug=model_slug, model_display_name=model_display_name)
    if not model_slug and norm_model.attribution_status == "attributed":
        if " " not in model_detected and "(" not in model_detected:
            model_slug = model_detected
        else:
            model_slug = norm_model.canonical_model
    if not model_display_name and model_detected != "Unknown" and (" " in model_detected or "(" in model_detected):
        model_display_name = model_detected

    resolved_max_ctx = step_max_ctx or gen_meta.get("max_context_tokens") or norm_model.context_window_tokens
    total_in = max(step_in_tot, gen_meta.get("total_input_tokens") or 0) or None
    total_cache = max(step_cache_tot, gen_meta.get("total_cache_read_tokens") or 0) or None
    total_out = max(step_out_tot, gen_meta.get("total_output_tokens") or 0) or None
    total_thought = max(step_thought_tot, gen_meta.get("total_thought_tokens") or 0) or None
    peak_ctx = max(step_peak_ctx, gen_meta.get("peak_context_tokens") or 0) or None

    step_rows = [
        {
            "session_id": session_id, "step_index": s.get("step_index", 0), "step_type": s.get("type", "UNKNOWN"),
            "source": s.get("source", "UNKNOWN"), "status": s.get("status", "DONE"),
            "created_at": normalize_utc_iso(s.get("created_at")),
            "content_length": len(str(s.get("content", ""))),
            "content_snippet": str(s.get("content", ""))[:200] if s.get("content") else None,
            "has_thinking": 1 if s.get("thinking") else 0, "thinking_length": len(str(s.get("thinking", ""))),
            "tool_count": len(s.get("tool_calls", [])) if isinstance(s.get("tool_calls"), list) else 0,
        }
        for s in steps
    ]

    source_kind = "transcript_full" if transcript_path.name == "transcript_full.jsonl" else "transcript"
    session_row = {
        "session_id": session_id, "start_time": start_time, "end_time": end_time,
        "duration_seconds": duration_s, "total_steps": len(steps), "model": model_detected,
        "workspace_path": workspace_detected, "transcript_path": str(transcript_path),
        "file_size_bytes": raw_size, "has_errors": 1 if has_errors else 0,
        "tool_call_count": len(tool_calls_extracted), "tool_error_count": tool_error_count,
        "intervention_count": len(interventions_extracted), "origin_developer": "local", "remote_synced_at": None,
        "origin_machine": resolve_machine_id(workspace_detected or None),
        "client_surface": infer_client_surface(transcript_path),
        "source_kind": source_kind,
        "model_slug": model_slug,
        "model_display_name": model_display_name,
        "max_context_tokens": resolved_max_ctx,
        "total_input_tokens": total_in,
        "total_cache_read_tokens": total_cache,
        "total_output_tokens": total_out,
        "total_thought_tokens": total_thought,
        "peak_context_tokens": peak_ctx,
    }
    return session_row, step_rows, tool_calls_extracted, interventions_extracted


__all__ = [
    "SCHEMA_SQL", "calculate_duration", "classify_command", "classify_intervention",
    "ensure_sync_columns", "ensure_telemetry_schema", "ensure_volume_columns",
    "extract_session", "parse_iso_ts", "upsert_session_telemetry",
]
