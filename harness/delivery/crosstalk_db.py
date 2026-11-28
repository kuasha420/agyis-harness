# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Arafat Zahan (@kuasha420)
# Corporate Stewardship & Infrastructure: Purrfect Software Limited (PSL)
# Governed by: ICARO-42/b Ordinance (Company-Supported Personal IP Framework)

"""
Read-Only Crosstalk Conversation Discovery & Selective Transcript Reader.

Queries Desktop (`antigravity`) and CLI (`antigravity-cli`) `conversation_summaries.db`
read-only (`?mode=ro` + `PRAGMA query_only = ON`), supports `conversations_fts` FTS5
and `conversation_parents`, and inspects `<appDataDir>/brain/<cid>/.system_generated/logs/transcript.jsonl`
with selective `transcript_full.jsonl` hydration ONLY for `truncated_fields` rows.
"""

from __future__ import annotations

from collections import deque
import json
import os
from pathlib import Path
import re
import sqlite3
from typing import Any, Dict, List, Optional, Sequence, Set, Tuple, Union
import urllib.error
import urllib.request

from harness.delivery.projects import normalize_folder_uri, resolve_projects_config_dir
from harness.telemetry.redaction import sanitize_crosstalk_payload

_SURFACE_DIR_NAMES: tuple[str, ...] = (
    "antigravity",
    "antigravity-cli",
    "antigravity-ide",
)
_FTS_TOKEN_RE = re.compile(r"[A-Za-z0-9_.\-]+")


def infer_surface_name(app_dir: Path) -> str:
    """Infers Antigravity surface label ('desktop', 'cli', 'ide') from an appDataDir path."""
    name = app_dir.name.lower()
    if name.endswith("-cli"):
        return "cli"
    if name.endswith("-ide"):
        return "ide"
    return "desktop"


def resolve_app_data_roots(
    app_data_roots: Optional[Sequence[Union[str, Path]]] = None,
    config_dir: Optional[Union[str, Path]] = None,
) -> List[Path]:
    """
    Resolves ordered Antigravity appDataDir candidates without touching live host
    directories when explicit roots or test `config_dir` / `AGYIS_CONFIG_DIR` are supplied.
    """
    candidates: List[Path] = []
    if app_data_roots is not None:
        candidates = [Path(p).expanduser() for p in app_data_roots if str(p).strip()]
    elif config_dir is not None and str(config_dir).strip():
        base = resolve_projects_config_dir(config_dir).parent
        candidates = [base / name for name in _SURFACE_DIR_NAMES]
    elif os.environ.get("AGYIS_CONFIG_DIR") or os.environ.get("PSL_CONFIG_DIR"):
        base = resolve_projects_config_dir(None).parent
        candidates = [base / name for name in _SURFACE_DIR_NAMES]
    elif os.environ.get("ANTIGRAVITY_APP_DATA_DIR"):
        primary = Path(os.environ["ANTIGRAVITY_APP_DATA_DIR"].strip()).expanduser()
        candidates.append(primary)
        parent = primary.parent
        for name in _SURFACE_DIR_NAMES:
            sib = parent / name
            if sib.exists():
                candidates.append(sib)
    else:
        gemini_root = Path.home() / ".gemini"
        candidates = [gemini_root / name for name in _SURFACE_DIR_NAMES]

    deduped: List[Path] = []
    seen: Set[str] = set()
    for cand in candidates:
        try:
            key = str(cand.resolve())
        except OSError:
            key = str(cand)
        if key not in seen:
            seen.add(key)
            deduped.append(cand)
    return deduped


def _parse_workspace_uris(raw_val: Any) -> List[str]:
    """Parses `workspace_uris` column values (JSON array, CSV, or raw string) into normalized URIs."""
    if raw_val is None:
        return []
    raw_items: List[str] = []
    if isinstance(raw_val, list):
        raw_items = [str(x).strip() for x in raw_val if str(x).strip()]
    elif isinstance(raw_val, str):
        text = raw_val.strip()
        if not text:
            return []
        if text.startswith("["):
            try:
                parsed = json.loads(text)
                if isinstance(parsed, list):
                    raw_items = [str(x).strip() for x in parsed if str(x).strip()]
            except (json.JSONDecodeError, ValueError):
                raw_items = [text]
        elif "," in text:
            raw_items = [part.strip() for part in text.split(",") if part.strip()]
        else:
            raw_items = [text]

    normalized: List[str] = []
    seen: Set[str] = set()
    for item in raw_items:
        try:
            norm = normalize_folder_uri(item)
        except ValueError:
            norm = item
        if norm not in seen:
            seen.add(norm)
            normalized.append(norm)
    return normalized


def _build_fts5_query(raw_query: str) -> Optional[str]:
    """Builds a safe FTS5 prefix-token MATCH query string from user search terms."""
    tokens = _FTS_TOKEN_RE.findall(raw_query or "")
    if not tokens:
        return None
    escaped = [f'"{tok.replace(chr(34), chr(34) * 2)}"*' for tok in tokens[:12]]
    return " ".join(escaped)


def _build_summaries_where(
    cols: Set[str],
    *,
    project_id: Optional[str],
    parent_conversation_id: Optional[str],
    include_children: bool,
    parents_map: Dict[str, str],
    q_lower: str,
    fts_ids: Set[str],
) -> Tuple[str, List[Any]]:
    """Builds parameterized SQLite WHERE clauses for conversation_summaries pushdown."""
    clauses: List[str] = []
    params: List[Any] = []

    if project_id and project_id.strip() and "project_id" in cols:
        clauses.append("LOWER(TRIM(COALESCE(project_id, ''))) = ?")
        params.append(project_id.strip().lower())

    if parent_conversation_id is not None and "parent_conversation_id" in cols:
        p_target = parent_conversation_id.strip()
        if not p_target:
            clauses.append("TRIM(COALESCE(parent_conversation_id, '')) = ''")
        else:
            map_children = sorted(c for c, pid in parents_map.items() if pid == p_target)
            if not map_children:
                clauses.append("TRIM(COALESCE(parent_conversation_id, '')) = ?")
                params.append(p_target)
            elif len(map_children) <= 400:
                ph = ", ".join("?" for _ in map_children)
                clauses.append(f"(TRIM(COALESCE(parent_conversation_id, '')) = ? OR conversation_id IN ({ph}))")
                params.append(p_target)
                params.extend(map_children)
    elif not include_children and "parent_conversation_id" in cols:
        clauses.append("TRIM(COALESCE(parent_conversation_id, '')) = ''")

    if q_lower and len(fts_ids) <= 400:
        like_pat = "%" + q_lower.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "%"
        like_cols = [c for c in ("conversation_id", "title", "preview", "project_id", "workspace_uris") if c in cols]
        q_clauses = [f"LOWER(COALESCE({c}, '')) LIKE ? ESCAPE '\\'" for c in like_cols]
        q_params: List[Any] = [like_pat] * len(like_cols)
        if fts_ids:
            sorted_fts = sorted(fts_ids)
            ph = ", ".join("?" for _ in sorted_fts)
            q_clauses.append(f"conversation_id IN ({ph})")
            q_params.extend(sorted_fts)
        if q_clauses:
            clauses.append("(" + " OR ".join(q_clauses) + ")")
            params.extend(q_params)

    return ("WHERE " + " AND ".join(clauses)) if clauses else "", params


def _query_single_summaries_db(
    db_path: Path,
    app_root: Path,
    surface_label: str,
    *,
    query: Optional[str],
    project_id: Optional[str],
    norm_ws_uri: Optional[str],
    parent_conversation_id: Optional[str],
    include_children: bool,
    limit: int,
    timeout: float,
) -> List[Dict[str, Any]]:
    """Queries a single conversation_summaries.db read-only and returns normalized records."""
    if not db_path.is_file():
        return []

    eff_timeout = min(max(float(timeout), 0.1), 2.0)
    q_lower = query.strip().lower() if query and query.strip() else ""
    conn: Optional[sqlite3.Connection] = None
    try:
        conn = sqlite3.connect(f"file:{db_path.resolve()}?mode=ro", uri=True, timeout=eff_timeout)
        conn.execute("PRAGMA query_only = ON")
        tables = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()}
        if "conversation_summaries" not in tables:
            return []

        cols = {r[1] for r in conn.execute("PRAGMA table_info(conversation_summaries)").fetchall()}
        if "conversation_id" not in cols:
            return []

        parents_map: Dict[str, str] = {}
        if "conversation_parents" in tables:
            p_cols = {r[1] for r in conn.execute("PRAGMA table_info(conversation_parents)").fetchall()}
            if "conversation_id" in p_cols and "parent_id" in p_cols:
                for cid_val, pid_val in conn.execute(
                    "SELECT conversation_id, parent_id FROM conversation_parents"
                ).fetchall():
                    if cid_val and pid_val:
                        parents_map[str(cid_val).strip()] = str(pid_val).strip()

        fts_ids: Set[str] = set()
        if q_lower and "conversations_fts" in tables:
            fts_expr = _build_fts5_query(query.strip())
            if fts_expr:
                try:
                    fts_rows = conn.execute(
                        "SELECT DISTINCT conversation_id FROM conversations_fts "
                        "WHERE conversations_fts MATCH ? LIMIT ?",
                        (fts_expr, max(limit * 10, 1000)),
                    ).fetchall()
                    fts_ids = {str(r[0]).strip() for r in fts_rows if r and r[0]}
                except sqlite3.OperationalError:
                    fts_ids = set()

        desired_cols = (
            "conversation_id", "title", "preview", "step_count", "last_modified_time",
            "workspace_uris", "status", "source", "project_id", "agent_name",
            "parent_conversation_id", "nesting_depth", "not_fully_idle", "killed",
            "last_user_input_time", "last_user_input_step_index", "app_data_dir", "group_id",
        )
        select_exprs = [col if col in cols else f"NULL AS {col}" for col in desired_cols]
        where_sql, where_params = _build_summaries_where(
            cols,
            project_id=project_id,
            parent_conversation_id=parent_conversation_id,
            include_children=include_children,
            parents_map=parents_map,
            q_lower=q_lower,
            fts_ids=fts_ids,
        )
        order_clause = "ORDER BY last_modified_time DESC" if "last_modified_time" in cols else ""
        batch_size = max(limit * 6, 300)
        max_scan = max(limit * 50, 10_000)
        sql = f"SELECT {', '.join(select_exprs)} FROM conversation_summaries {where_sql} {order_clause} LIMIT ? OFFSET ?"

        results: List[Dict[str, Any]] = []
        offset = 0
        result_cap = max(limit * 6, 300) if q_lower else limit
        while offset < max_scan:
            batch = conn.execute(sql, (*where_params, batch_size, offset)).fetchall()
            if not batch:
                break
            for row in batch:
                (
                    cid_raw, title_raw, preview_raw, step_cnt_raw, last_mod_raw,
                    ws_uris_raw, status_raw, source_raw, proj_raw, agent_raw,
                    parent_raw, depth_raw, idle_raw, killed_raw,
                    last_ui_time_raw, last_ui_idx_raw, row_app_dir_raw, group_raw,
                ) = row
                cid = str(cid_raw or "").strip()
                if not cid:
                    continue

                title = str(title_raw or "").strip()
                preview = str(preview_raw or "").strip()
                uris = _parse_workspace_uris(ws_uris_raw)
                row_proj = str(proj_raw or "").strip()
                effective_parent = str(parent_raw or "").strip() or parents_map.get(cid, "")

                if project_id and row_proj.lower() != project_id.strip().lower():
                    continue
                if norm_ws_uri and norm_ws_uri not in uris:
                    continue
                if parent_conversation_id is not None:
                    if effective_parent != parent_conversation_id.strip():
                        continue
                elif not include_children and effective_parent:
                    continue

                is_fts_hit = cid in fts_ids
                if q_lower:
                    haystack = " ".join((cid, title, preview, row_proj, " ".join(uris))).lower()
                    if not is_fts_hit and q_lower not in haystack:
                        continue

                not_idle = bool(idle_raw)
                results.append({
                    "conversation_id": cid, "title": title, "preview": preview,
                    "step_count": int(step_cnt_raw or 0),
                    "last_modified_time": str(last_mod_raw or "").strip(),
                    "workspace_uris": uris, "status": str(status_raw or "").strip(),
                    "run_state": "RUN_STATE_RUNNING" if not_idle else "RUN_STATE_IDLE",
                    "source": str(source_raw or "").strip(), "project_id": row_proj,
                    "agent_name": str(agent_raw or "").strip(),
                    "parent_conversation_id": effective_parent, "nesting_depth": int(depth_raw or 0),
                    "not_fully_idle": not_idle, "killed": bool(killed_raw),
                    "last_user_input_time": str(last_ui_time_raw or "").strip(),
                    "last_user_input_step_index": int(last_ui_idx_raw if last_ui_idx_raw is not None else -1),
                    "group_id": str(group_raw or "").strip(),
                    "app_data_dir": str(row_app_dir_raw or "").strip() or str(app_root),
                    "surface": surface_label, "surfaces": [surface_label],
                    "fts_matched": is_fts_hit, "live_rpc": False,
                })
                if len(results) >= result_cap:
                    break
            if len(results) >= result_cap or len(batch) < batch_size:
                break
            offset += batch_size
    except (sqlite3.Error, OSError):
        return []
    finally:
        if conn is not None:
            try:
                conn.close()
            except sqlite3.Error:
                pass

    return results


def query_conversation_summaries(
    *,
    query: Optional[str] = None,
    project_id: Optional[str] = None,
    workspace_path: Optional[Union[str, Path]] = None,
    parent_conversation_id: Optional[str] = None,
    include_children: bool = False,
    surface: Optional[str] = None,
    limit: int = 50,
    app_data_roots: Optional[Sequence[Union[str, Path]]] = None,
    config_dir: Optional[Union[str, Path]] = None,
    timeout: float = 0.5,
) -> Tuple[List[Dict[str, Any]], Dict[str, int]]:
    """
    Queries Desktop and CLI `conversation_summaries.db` read-only, deduplicating across surfaces.
    Returns (records, counts_by_surface).
    """
    roots = resolve_app_data_roots(app_data_roots=app_data_roots, config_dir=config_dir)
    norm_ws_uri: Optional[str] = None
    if workspace_path is not None and str(workspace_path).strip():
        try:
            norm_ws_uri = normalize_folder_uri(workspace_path)
        except ValueError:
            norm_ws_uri = str(workspace_path).strip()

    surf_filter = surface.strip().lower() if isinstance(surface, str) and surface.strip() else ""
    if surf_filter == "all":
        surf_filter = ""

    merged: Dict[str, Dict[str, Any]] = {}
    surface_counts: Dict[str, int] = {}

    for app_root in roots:
        surf = infer_surface_name(app_root)
        if surf_filter and surf != surf_filter:
            continue
        db_path = app_root / "conversation_summaries.db"
        rows = _query_single_summaries_db(
            db_path,
            app_root,
            surf,
            query=query,
            project_id=project_id,
            norm_ws_uri=norm_ws_uri,
            parent_conversation_id=parent_conversation_id,
            include_children=include_children,
            limit=max(1, limit),
            timeout=timeout,
        )
        surface_counts[surf] = surface_counts.get(surf, 0) + len(rows)
        for rec in rows:
            cid = rec["conversation_id"]
            existing = merged.get(cid)
            if existing is None:
                merged[cid] = rec
            else:
                if surf not in existing["surfaces"]:
                    existing["surfaces"].append(surf)
                if rec.get("fts_matched"):
                    existing["fts_matched"] = True
                if (rec.get("last_modified_time", "") > existing.get("last_modified_time", "")) or (
                    not existing.get("title") and rec.get("title")
                ):
                    merged_surfs = list(existing["surfaces"])
                    merged_fts = bool(existing.get("fts_matched") or rec.get("fts_matched"))
                    merged[cid] = rec
                    merged[cid]["surfaces"] = merged_surfs
                    merged[cid]["fts_matched"] = merged_fts

    records = sorted(
        merged.values(),
        key=lambda item: (item.get("last_modified_time") or "", item.get("conversation_id") or ""),
        reverse=True,
    )
    return records[: max(1, limit)], surface_counts


def find_conversation_transcripts(
    conversation_id: str,
    *,
    app_data_roots: Optional[Sequence[Union[str, Path]]] = None,
    config_dir: Optional[Union[str, Path]] = None,
) -> Tuple[Optional[Path], Optional[Path], Optional[Path]]:
    """
    Locates `(app_data_root, transcript_jsonl, transcript_full_jsonl)` for `conversation_id`
    across Desktop and CLI appDataDirs without traversing outside brain/.
    """
    cid = (conversation_id or "").strip()
    if not cid or "/" in cid or "\\" in cid or ".." in cid:
        return None, None, None

    for app_root in resolve_app_data_roots(app_data_roots=app_data_roots, config_dir=config_dir):
        convo_dir = app_root / "brain" / cid
        if not convo_dir.is_dir():
            continue
        logs_dir = convo_dir / ".system_generated" / "logs"
        compact = logs_dir / "transcript.jsonl"
        if not compact.is_file():
            alt_compact = convo_dir / "transcript.jsonl"
            compact = alt_compact if alt_compact.is_file() else compact

        full = logs_dir / "transcript_full.jsonl"
        if not full.is_file():
            alt_full = convo_dir / "transcript_full.jsonl"
            full = alt_full if alt_full.is_file() else full

        has_compact = compact.is_file()
        has_full = full.is_file()
        if has_compact or has_full:
            return (
                app_root,
                compact if has_compact else None,
                full if has_full else None,
            )

    return None, None, None


def _hydrate_truncated_steps(
    tail_steps: List[Dict[str, Any]],
    full_path: Path,
) -> List[int]:
    """
    Hydrates ONLY specific `step_index` rows carrying non-empty `truncated_fields`
    by streaming `transcript_full.jsonl` with early exit once all needed indices are matched.
    """
    need_by_idx: Dict[int, List[int]] = {}
    for pos, step in enumerate(tail_steps):
        trunc = step.get("truncated_fields")
        s_idx = step.get("step_index")
        if isinstance(trunc, list) and trunc and isinstance(s_idx, int):
            need_by_idx.setdefault(s_idx, []).append(pos)

    if not need_by_idx or not full_path.is_file():
        return []

    hydrated_indices: List[int] = []
    remaining = set(need_by_idx.keys())
    try:
        with open(full_path, "r", encoding="utf-8", errors="replace") as f:
            for raw_line in f:
                stripped = raw_line.strip()
                if not stripped:
                    continue
                try:
                    full_obj = json.loads(stripped)
                except (json.JSONDecodeError, ValueError):
                    continue
                if not isinstance(full_obj, dict):
                    continue
                s_idx = full_obj.get("step_index")
                if not isinstance(s_idx, int) or s_idx not in remaining:
                    continue
                for pos in need_by_idx[s_idx]:
                    target_step = tail_steps[pos]
                    trunc_fields = target_step.get("truncated_fields") or []
                    for field_name in trunc_fields:
                        if field_name in full_obj:
                            target_step[field_name] = full_obj[field_name]
                    if "content" in full_obj and "content" not in trunc_fields and not target_step.get("content"):
                        target_step["content"] = full_obj["content"]
                    target_step["hydrated_from_full"] = True
                hydrated_indices.append(s_idx)
                remaining.discard(s_idx)
                if not remaining:
                    break
    except OSError:
        return hydrated_indices

    return sorted(hydrated_indices)


def _sanitize_step_for_crosstalk(
    step: Dict[str, Any],
    *,
    sanitize: bool,
    source_ws: Optional[Union[str, Path]],
    target_ws: Optional[Union[str, Path]],
    strict: bool,
    max_chars: int,
    totals: Dict[str, int],
) -> Dict[str, Any]:
    """Projects a raw transcript step into a compact, cross-boundary-sanitized dict."""
    def _clean_text(val: Any) -> str:
        raw = str(val or "")
        if max_chars > 0 and len(raw) > max_chars:
            raw = raw[:max_chars] + "...[truncated]"
        if not sanitize or not raw:
            return raw
        cleaned, report = sanitize_crosstalk_payload(
            raw,
            source_ws=source_ws,
            target_ws=target_ws,
            strict=strict,
        )
        totals["secrets_redacted"] += int(report.get("secrets_redacted", 0))
        totals["paths_anonymized"] += int(report.get("paths_anonymized", 0))
        totals["blocked_refs"] += int(report.get("blocked_refs", 0))
        return cleaned

    out: Dict[str, Any] = {
        "step_index": step.get("step_index"),
        "type": step.get("type") or "",
        "status": step.get("status") or "",
        "timestamp": step.get("created_at") or step.get("timestamp") or "",
        "hydrated_from_full": bool(step.get("hydrated_from_full", False)),
    }
    if step.get("truncated_fields"):
        out["truncated_fields"] = list(step["truncated_fields"])

    for key in ("content", "prompt", "thinking", "error"):
        val = step.get(key)
        if val is not None and str(val).strip():
            out[key] = _clean_text(val)

    raw_tcs = step.get("tool_calls") or step.get("toolCalls")
    if isinstance(raw_tcs, list) and raw_tcs:
        clean_tcs: List[Dict[str, Any]] = []
        for tc in raw_tcs[:10]:
            if not isinstance(tc, dict):
                continue
            tc_entry: Dict[str, Any] = {"name": str(tc.get("name") or "")}
            args_val = tc.get("args") if tc.get("args") is not None else tc.get("arguments")
            if args_val is not None:
                args_str = json.dumps(args_val) if isinstance(args_val, (dict, list)) else str(args_val)
                tc_entry["args_preview"] = _clean_text(args_str)
            res_val = tc.get("result") if tc.get("result") is not None else tc.get("output")
            if res_val is not None:
                res_str = json.dumps(res_val) if isinstance(res_val, (dict, list)) else str(res_val)
                tc_entry["result_preview"] = _clean_text(res_str)
            clean_tcs.append(tc_entry)
        if clean_tcs:
            out["tool_calls"] = clean_tcs

    return out


def inspect_conversation_steps(
    conversation_id: str,
    *,
    tail: int = 20,
    app_data_roots: Optional[Sequence[Union[str, Path]]] = None,
    config_dir: Optional[Union[str, Path]] = None,
    sanitize: bool = True,
    source_ws: Optional[Union[str, Path]] = None,
    target_ws: Optional[Union[str, Path]] = None,
    strict: bool = False,
    max_chars_per_step: int = 2000,
) -> Dict[str, Any]:
    """
    Reads the tail of a conversation's `transcript.jsonl`, hydrating ONLY specific
    `step_index` rows carrying `truncated_fields` from `transcript_full.jsonl`,
    and applies cross-project sanitization before returning bounded step summaries.
    """
    cid = (conversation_id or "").strip()
    app_root, compact_path, full_path = find_conversation_transcripts(
        cid,
        app_data_roots=app_data_roots,
        config_dir=config_dir,
    )
    primary_path = compact_path or full_path
    base_err: Dict[str, Any] = {
        "success": False,
        "conversation_id": cid,
        "app_data_dir": str(app_root) if app_root else None,
        "surface": infer_surface_name(app_root) if app_root else None,
        "transcript_path": str(primary_path) if primary_path else None,
        "full_transcript_path": str(full_path) if full_path else None,
        "used_full_fallback": False,
        "hydrated_step_indices": [],
        "step_count": 0,
        "steps": [],
        "redaction": {"secrets_redacted": 0, "paths_anonymized": 0, "blocked_refs": 0},
    }
    if primary_path is None:
        return {**base_err, "error": f"No transcript found for conversation '{cid}'."}

    tail_limit = max(1, min(int(tail), 200))
    tail_buf: deque[Dict[str, Any]] = deque(maxlen=tail_limit)
    try:
        with open(primary_path, "r", encoding="utf-8", errors="replace") as f:
            for idx, raw_line in enumerate(f):
                stripped = raw_line.strip()
                if not stripped:
                    continue
                try:
                    obj = json.loads(stripped)
                except (json.JSONDecodeError, ValueError):
                    continue
                if not isinstance(obj, dict):
                    continue
                if "step_index" not in obj or not isinstance(obj.get("step_index"), int):
                    obj["step_index"] = idx
                tail_buf.append(obj)
    except OSError as exc:
        return {**base_err, "error": f"Failed reading transcript '{primary_path}': {exc}"}

    raw_steps = list(tail_buf)
    hydrated_indices: List[int] = []
    if compact_path is not None and full_path is not None and full_path != compact_path:
        hydrated_indices = _hydrate_truncated_steps(raw_steps, full_path)

    redaction_totals = {"secrets_redacted": 0, "paths_anonymized": 0, "blocked_refs": 0}
    steps_out = [
        _sanitize_step_for_crosstalk(
            step,
            sanitize=sanitize,
            source_ws=source_ws,
            target_ws=target_ws,
            strict=strict,
            max_chars=max_chars_per_step,
            totals=redaction_totals,
        )
        for step in raw_steps
    ]

    return {
        "success": True,
        "conversation_id": cid,
        "app_data_dir": str(app_root) if app_root else None,
        "surface": infer_surface_name(app_root) if app_root else None,
        "transcript_path": str(primary_path),
        "full_transcript_path": str(full_path) if full_path else None,
        "used_full_fallback": bool(hydrated_indices) or (compact_path is None and full_path is not None),
        "hydrated_step_indices": hydrated_indices,
        "step_count": len(steps_out),
        "steps": steps_out,
        "redaction": redaction_totals,
    }


def resolve_ls_credentials(
    ls_address: Optional[str] = None,
    csrf_token: Optional[str] = None,
) -> Tuple[Optional[str], Optional[str]]:
    """Resolves (host:port, csrf_token) from explicit args or ANTIGRAVITY_LS_ADDRESS / ANTIGRAVITY_CSRF_TOKEN."""
    addr = (ls_address if ls_address is not None else os.environ.get("ANTIGRAVITY_LS_ADDRESS") or "").strip()
    token = (csrf_token if csrf_token is not None else os.environ.get("ANTIGRAVITY_CSRF_TOKEN") or "").strip()
    for prefix in ("http://", "https://"):
        if addr.startswith(prefix):
            addr = addr[len(prefix):]
    return (addr.rstrip("/") or None), (token or None)


def is_sandbox_refusal(status_code: Optional[int], detail: str) -> bool:
    """Detects terminal HTTP sandbox refusal (`403` / `Port ... not allowed for HTTP` / EPERM)."""
    low = (detail or "").lower()
    return status_code == 403 or "not allowed for http" in low or "operation not permitted" in low or (
        "sandbox" in low and "refused" in low
    )


def _call_connect_rpc(
    service_fqn: str,
    method: str,
    payload: Optional[Dict[str, Any]] = None,
    *,
    ls_address: Optional[str] = None,
    csrf_token: Optional[str] = None,
    timeout: float = 5.0,
) -> Dict[str, Any]:
    """Executes a single Connect HTTP+JSON POST against Antigravity LS without blind retries."""
    addr, token = resolve_ls_credentials(ls_address, csrf_token)
    base = {
        "ok": False, "status_code": None, "sandbox_blocked": False,
        "missing_env": False, "connection_refused": False, "data": None, "error": None,
    }
    if not addr or not token:
        return {**base, "missing_env": True, "error": "ANTIGRAVITY_LS_ADDRESS and ANTIGRAVITY_CSRF_TOKEN are required."}

    req = urllib.request.Request(
        f"http://{addr}/{service_fqn}/{method}",
        data=json.dumps(payload if payload is not None else {}).encode("utf-8"),
        method="POST",
        headers={
            "Content-Type": "application/json",
            "Connect-Protocol-Version": "1",
            "x-antigravity-csrf-token": token,
        },
    )
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    try:
        with opener.open(req, timeout=float(timeout)) as resp:
            raw = resp.read().decode("utf-8", errors="replace")
            return {**base, "ok": True, "status_code": getattr(resp, "status", 200), "data": json.loads(raw) if raw.strip() else {}}
    except urllib.error.HTTPError as exc:
        try:
            detail = exc.read().decode("utf-8", errors="replace").strip() or str(exc)
        except OSError:
            detail = str(exc)
        finally:
            try:
                exc.close()
            except OSError:
                pass
        sb = is_sandbox_refusal(exc.code, detail)
        msg = f"Terminal sandbox blocked loopback HTTP ({exc.code}: {detail}). Rerun outside sandbox or use CLI fallback." if sb else f"HTTP {exc.code} from {method}: {detail}"
        return {**base, "status_code": exc.code, "sandbox_blocked": sb, "error": msg}
    except urllib.error.URLError as exc:
        reason = exc.reason
        detail = str(reason or exc)
        return {
            **base,
            "sandbox_blocked": bool(isinstance(reason, PermissionError) or is_sandbox_refusal(None, detail)),
            "connection_refused": bool(isinstance(reason, ConnectionRefusedError) or "connection refused" in detail.lower()),
            "error": detail,
        }
    except (OSError, json.JSONDecodeError, ValueError) as exc:
        detail = str(exc)
        return {**base, "sandbox_blocked": is_sandbox_refusal(None, detail), "error": detail}


def call_conversation_service(
    method: str,
    payload: Optional[Dict[str, Any]] = None,
    *,
    ls_address: Optional[str] = None,
    csrf_token: Optional[str] = None,
    timeout: float = 5.0,
) -> Dict[str, Any]:
    """Calls `product.v1.ConversationService/<method>` over Connect HTTP+JSON."""
    return _call_connect_rpc("product.v1.ConversationService", method, payload, ls_address=ls_address, csrf_token=csrf_token, timeout=timeout)


def call_ls_service(
    method: str,
    payload: Optional[Dict[str, Any]] = None,
    *,
    ls_address: Optional[str] = None,
    csrf_token: Optional[str] = None,
    timeout: float = 5.0,
) -> Dict[str, Any]:
    """Calls `exa.language_server_pb.LanguageServerService/<method>` over Connect HTTP+JSON."""
    return _call_connect_rpc("exa.language_server_pb.LanguageServerService", method, payload, ls_address=ls_address, csrf_token=csrf_token, timeout=timeout)


__all__ = [
    "call_conversation_service",
    "call_ls_service",
    "find_conversation_transcripts",
    "infer_surface_name",
    "inspect_conversation_steps",
    "is_sandbox_refusal",
    "query_conversation_summaries",
    "resolve_app_data_roots",
    "resolve_ls_credentials",
]
