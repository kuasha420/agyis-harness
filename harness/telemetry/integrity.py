# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Arafat Zahan (@kuasha420)
# Corporate Stewardship & Infrastructure: Purrfect Software Limited (PSL)
# Governed by: ICARO-42/b Ordinance (Company-Supported Personal IP Framework)

"""
Wheel-Portable Telemetry Database Integrity Audit & Repair Engine (ADR-014 / G0.1-B).

Detects and repairs:
- Same-step and cross-source tool_calls duplicates while keeping the richest row
- Desynchronized session counters (tool_call_count, tool_error_count, intervention_count, has_errors, total_steps)
- Non-UTC / mixed-offset ISO timestamps across sessions, steps, tool_calls, interventions, and watermarks
- Missing G0.1 metadata (client_surface, source_kind, local origin_machine) and sibling .db gen_metadata model recovery
"""

from __future__ import annotations

import os
from pathlib import Path
import sqlite3
from typing import Any, Dict, List, Optional, Tuple

from harness.telemetry.config import infer_client_surface, resolve_machine_id
from harness.telemetry.db import get_db_connection
from harness.telemetry.extractor import ensure_telemetry_schema
from harness.telemetry.integrity_dedup import (
    apply_dedup_mutations,
    get_table_cols,
    resolve_unique_conflict_group,
    scan_tool_call_duplicates,
)
from harness.telemetry.models import normalize_utc_iso
from harness.telemetry.sibling_db import find_sibling_conversation_db, read_sibling_gen_metadata

_LEGACY_MODEL_PLACEHOLDERS = frozenset({"", "Unknown", "unknown", "Gemini 3.5/Flash/Pro (Default)"})
_EXPECTED_G01_COLUMNS = (
    "origin_machine", "client_surface", "source_kind", "model_slug", "model_display_name",
    "max_context_tokens", "total_input_tokens", "total_cache_read_tokens",
    "total_output_tokens", "total_thought_tokens", "peak_context_tokens", "server_seq",
)


def _infer_source_kind(transcript_path: Optional[str]) -> Optional[str]:
    if not transcript_path:
        return None
    low = str(transcript_path).lower()
    if low.endswith("transcript_full.jsonl"):
        return "transcript_full"
    if low.endswith(".jsonl"):
        return "transcript"
    if low.endswith(".db"):
        return "sqlite_db"
    return None


def _resolve_sibling_db(
    session_id: str,
    transcript_path: Optional[str],
    origin_developer: Optional[str],
) -> Optional[Path]:
    if origin_developer not in (None, "", "local"):
        return None
    user_home = str(Path.home())
    if transcript_path:
        raw_tp = Path(str(transcript_path).replace("[USER_HOME]", user_home))
        if raw_tp.suffix == ".db" and raw_tp.is_file():
            return raw_tp
        sib = find_sibling_conversation_db(raw_tp, session_id)
        if sib is not None:
            return sib
    env_override = (
        os.environ.get("AGYIS_CONVERSATIONS_DIR")
        or os.environ.get("ANTIGRAVITY_CONVERSATIONS_DIR")
        or os.environ.get("GEMINI_CONVERSATIONS_DIR")
        or os.environ.get("ANTIGRAVITY_APP_DATA_DIR")
    )
    if env_override and env_override.strip():
        return find_sibling_conversation_db(Path("missing"), session_id)
    for base in (
        Path.home() / ".gemini" / "antigravity" / "conversations",
        Path.home() / ".gemini" / "antigravity-cli" / "conversations",
    ):
        cand = base / f"{session_id}.db"
        if cand.is_file():
            return cand
    return None


def _count_non_utc(cur: sqlite3.Cursor, table: str, cols: Tuple[str, ...]) -> int:
    tcols = get_table_cols(cur, table)
    active = [c for c in cols if c in tcols]
    if not active:
        return 0
    cur.execute(f"SELECT {', '.join(active)} FROM {table}")
    bad = 0
    while True:
        batch = cur.fetchmany(5000)
        if not batch:
            break
        for row in batch:
            for val in row:
                if isinstance(val, str) and val.strip():
                    norm = normalize_utc_iso(val)
                    if norm != val:
                        bad += 1
    return bad


def _audit_connection(conn: sqlite3.Connection) -> Dict[str, Any]:
    cur = conn.cursor()
    sess_cols = get_table_cols(cur, "sessions")
    missing_cols = [c for c in _EXPECTED_G01_COLUMNS if c not in sess_cols]
    has_watermarks = bool(get_table_cols(cur, "sync_watermarks"))

    def _opt(col: str, default_sql: str = "NULL") -> str:
        return col if col in sess_cols else f"{default_sql} AS {col}"

    cur.execute(
        f"""
        SELECT session_id, total_steps, tool_call_count, tool_error_count, intervention_count,
               has_errors, workspace_path, transcript_path, model,
               {_opt('origin_developer', "'local'")},
               {_opt('origin_machine')}, {_opt('client_surface')}, {_opt('source_kind')}
        FROM sessions
        """
    )
    sess_rows = cur.fetchall()
    ws_map = {r[0]: (r[6] or "") for r in sess_rows if r[0]}

    drop_ids, _, p1_dups, p2_dups, tc_total = scan_tool_call_duplicates(cur, ws_map)
    drop_set = set(drop_ids)

    tc_cols = get_table_cols(cur, "tool_calls")
    tc_clean_counts: Dict[str, int] = {}
    tc_clean_errs: Dict[str, int] = {}
    if tc_cols:
        ec_expr = "exit_code" if "exit_code" in tc_cols else "NULL"
        st_expr = "status" if "status" in tc_cols else "'SUCCESS'"
        cur.execute(f"SELECT id, session_id, {st_expr}, {ec_expr} FROM tool_calls")
        while True:
            batch = cur.fetchmany(5000)
            if not batch:
                break
            for rid, sid, status, ec in batch:
                if rid in drop_set:
                    continue
                tc_clean_counts[sid] = tc_clean_counts.get(sid, 0) + 1
                if (status is not None and status != "SUCCESS") or (ec is not None and ec != 0):
                    tc_clean_errs[sid] = tc_clean_errs.get(sid, 0) + 1

    step_counts: Dict[str, int] = {}
    if get_table_cols(cur, "steps"):
        cur.execute("SELECT session_id, COUNT(*) FROM steps GROUP BY session_id")
        step_counts = {r[0]: r[1] for r in cur.fetchall()}

    interv_counts: Dict[str, int] = {}
    if get_table_cols(cur, "user_interventions"):
        cur.execute("SELECT session_id, COUNT(*) FROM user_interventions GROUP BY session_id")
        interv_counts = {r[0]: r[1] for r in cur.fetchall()}

    mismatches = {
        "tool_call_count": 0, "tool_error_count": 0, "intervention_count": 0,
        "total_steps": 0, "has_errors": 0, "zero_step_orphans": 0,
    }
    missing_meta = {
        "client_surface": 0, "source_kind": 0,
        "origin_machine_local": 0, "legacy_default_or_unknown_models": 0,
    }

    for sid, st_steps, st_tc, st_err, st_int, st_has_err, _, tpath, model, orig_dev, orig_mach, surf, sk in sess_rows:
        act_tc = tc_clean_counts.get(sid, 0)
        act_err = tc_clean_errs.get(sid, 0)
        act_int = interv_counts.get(sid, 0)
        act_steps = step_counts.get(sid, 0)
        exp_has_err = 1 if act_err > 0 else 0

        if (st_tc or 0) != act_tc:
            mismatches["tool_call_count"] += 1
        if (st_err or 0) != act_err:
            mismatches["tool_error_count"] += 1
        if (st_int or 0) != act_int:
            mismatches["intervention_count"] += 1
        if (st_has_err or 0) != exp_has_err:
            mismatches["has_errors"] += 1
        if act_steps > 0 and (st_steps or 0) != act_steps:
            mismatches["total_steps"] += 1
        if act_steps == 0 and (st_steps or 0) == 0:
            mismatches["zero_step_orphans"] += 1

        if not surf:
            missing_meta["client_surface"] += 1
        if not sk and _infer_source_kind(tpath) is not None:
            missing_meta["source_kind"] += 1
        if (orig_dev in (None, "", "local")) and not orig_mach:
            missing_meta["origin_machine_local"] += 1
        if (model or "") in _LEGACY_MODEL_PLACEHOLDERS:
            missing_meta["legacy_default_or_unknown_models"] += 1

    non_utc = {
        "sessions": _count_non_utc(cur, "sessions", ("start_time", "end_time", "remote_synced_at")),
        "steps": _count_non_utc(cur, "steps", ("created_at",)),
        "tool_calls": _count_non_utc(cur, "tool_calls", ("started_at", "completed_at")),
        "user_interventions": _count_non_utc(cur, "user_interventions", ("created_at",)),
        "sync_watermarks": _count_non_utc(cur, "sync_watermarks", ("last_synced_at", "updated_at")),
    }
    non_utc["total"] = sum(non_utc.values())

    total_dups = p1_dups + p2_dups
    healthy = (
        not missing_cols
        and has_watermarks
        and total_dups == 0
        and mismatches["tool_call_count"] == 0
        and mismatches["tool_error_count"] == 0
        and mismatches["intervention_count"] == 0
        and mismatches["total_steps"] == 0
        and mismatches["has_errors"] == 0
        and non_utc["total"] == 0
        and missing_meta["client_surface"] == 0
        and missing_meta["source_kind"] == 0
        and missing_meta["origin_machine_local"] == 0
    )

    return {
        "healthy": healthy,
        "schema": {
            "missing_columns": missing_cols,
            "has_sync_watermarks": has_watermarks,
        },
        "counts": {
            "sessions": len(sess_rows),
            "steps": sum(step_counts.values()),
            "tool_calls": tc_total,
            "tool_calls_clean": tc_total - total_dups,
            "user_interventions": sum(interv_counts.values()),
        },
        "duplicate_tool_calls": {
            "pass1_same_step": p1_dups,
            "pass2_cross_source": p2_dups,
            "total": total_dups,
        },
        "counter_mismatches": mismatches,
        "non_utc_timestamps": non_utc,
        "missing_metadata": missing_meta,
    }


def audit_database_integrity(db_path: Path) -> Dict[str, Any]:
    """Read-only integrity audit across pre-G0.1 and G0.1 telemetry SQLite schemas."""
    target = Path(db_path)
    if not target.is_file():
        raise FileNotFoundError(f"Telemetry database not found at {target}")
    conn = get_db_connection(target, row_factory=False, read_only=True)
    try:
        report = _audit_connection(conn)
    finally:
        conn.close()
    report["db_path"] = str(target)
    return report


_TC_CONFLICT_WANT: Tuple[str, ...] = (
    "id", "session_id", "step_index", "tool_name", "started_at", "completed_at",
    "duration_seconds", "status", "exit_code", "arguments_json", "arguments_snippet",
    "output_length_chars", "output_lines", "arguments_length_chars",
    "command_category", "error_snippet", "target_path", "command_line",
)


def _resolve_normalized_tool_call_conflicts(conn: sqlite3.Connection) -> int:
    """Explicitly pre-merges idx_tool_calls_uniq collisions before started_at UTC normalization."""
    cur = conn.cursor()
    tc_cols = get_table_cols(cur, "tool_calls")
    if "started_at" not in tc_cols:
        return 0
    dirty_sids: set[str] = set()
    cur.execute("SELECT session_id, started_at FROM tool_calls WHERE session_id IS NOT NULL AND started_at IS NOT NULL")
    while True:
        batch = cur.fetchmany(5000)
        if not batch:
            break
        for sid, raw_ts in batch:
            if isinstance(raw_ts, str) and raw_ts.strip() and normalize_utc_iso(raw_ts) != raw_ts:
                dirty_sids.add(sid)
    if not dirty_sids:
        return 0

    cur.execute("SELECT session_id, workspace_path FROM sessions")
    ws_map = {r[0]: (r[1] or "") for r in cur.fetchall() if r[0]}
    sel_cols = [c if c in tc_cols else f"NULL AS {c}" for c in _TC_CONFLICT_WANT]

    drop_ids: List[int] = []
    backfills: Dict[int, Dict[str, Any]] = {}
    sid_list = sorted(dirty_sids)
    for i in range(0, len(sid_list), 500):
        chunk = sid_list[i : i + 500]
        placeholders = ",".join(["?"] * len(chunk))
        cur.execute(
            f"SELECT {', '.join(sel_cols)} FROM tool_calls "
            f"WHERE session_id IN ({placeholders}) "
            f"AND step_index IS NOT NULL AND tool_name IS NOT NULL "
            f"AND started_at IS NOT NULL AND arguments_snippet IS NOT NULL "
            f"ORDER BY session_id, step_index, id",
            chunk,
        )
        groups: Dict[Tuple[Any, ...], List[Dict[str, Any]]] = {}
        for row in cur.fetchall():
            rec = dict(zip(_TC_CONFLICT_WANT, row))
            norm_sa = normalize_utc_iso(rec["started_at"])
            ukey = (rec["session_id"], rec["step_index"], rec["tool_name"], norm_sa, rec["arguments_snippet"])
            groups.setdefault(ukey, []).append(rec)
        for ukey, grp in groups.items():
            if len(grp) > 1:
                d_ids, bfs = resolve_unique_conflict_group(grp, workspace_path=ws_map.get(ukey[0], ""))
                drop_ids.extend(d_ids)
                backfills.update(bfs)

    if drop_ids or backfills:
        apply_dedup_mutations(conn, drop_ids, backfills)
    return len(drop_ids)


def _normalize_table_timestamps(conn: sqlite3.Connection, table: str, cols: Tuple[str, ...]) -> int:
    cur = conn.cursor()
    tcols = get_table_cols(cur, table)
    active = [c for c in cols if c in tcols]
    if not active:
        return 0
    if table == "tool_calls" and "started_at" in active:
        _resolve_normalized_tool_call_conflicts(conn)
    pk = "scope_key" if table == "sync_watermarks" else ("session_id" if table == "sessions" else "id")
    cur.execute(f"SELECT {pk}, {', '.join(active)} FROM {table}")
    updates: List[Tuple[Any, ...]] = []
    changed = 0
    while True:
        batch = cur.fetchmany(5000)
        if not batch:
            break
        for row in batch:
            row_id = row[0]
            new_vals = list(row[1:])
            dirty = False
            for idx, val in enumerate(new_vals):
                if isinstance(val, str) and val.strip():
                    norm = normalize_utc_iso(val)
                    if norm != val:
                        new_vals[idx] = norm
                        dirty = True
                        changed += 1
            if dirty:
                updates.append(tuple(new_vals) + (row_id,))
    if not updates:
        return 0
    set_sql = ", ".join(f"{c} = ?" for c in active)
    cur.executemany(f"UPDATE {table} SET {set_sql} WHERE {pk} = ?", updates)
    return changed


def _reconcile_sessions(conn: sqlite3.Connection) -> Dict[str, Any]:
    cur = conn.cursor()
    cur.execute(
        "SELECT session_id, COUNT(*), "
        "SUM(CASE WHEN (status IS NOT NULL AND status != 'SUCCESS') OR (exit_code IS NOT NULL AND exit_code != 0) THEN 1 ELSE 0 END) "
        "FROM tool_calls GROUP BY session_id"
    )
    tc_map = {r[0]: (r[1], r[2] or 0) for r in cur.fetchall()}
    cur.execute("SELECT session_id, COUNT(*) FROM steps GROUP BY session_id")
    step_map = {r[0]: r[1] for r in cur.fetchall()}
    cur.execute("SELECT session_id, COUNT(*) FROM user_interventions GROUP BY session_id")
    ui_map = {r[0]: r[1] for r in cur.fetchall()}

    cur.execute(
        """
        SELECT session_id, total_steps, model, workspace_path, transcript_path,
               has_errors, tool_call_count, tool_error_count, intervention_count,
               origin_developer, origin_machine, client_surface, source_kind,
               model_slug, model_display_name, max_context_tokens,
               total_input_tokens, total_cache_read_tokens, total_output_tokens,
               total_thought_tokens, peak_context_tokens
        FROM sessions
        """
    )
    rows = cur.fetchall()
    zero_step_orphans: List[str] = []
    updated_counters = enriched_meta = repaired_models = 0

    for r in rows:
        (sid, st_steps, model, ws, tp, has_err, st_tc, st_err, st_int,
         orig_dev, orig_mach, surf, sk, m_slug, m_disp, max_ctx,
         in_t, ca_t, out_t, th_t, pk_t) = r

        act_tc, act_err = tc_map.get(sid, (0, 0))
        act_int = ui_map.get(sid, 0)
        act_steps = step_map.get(sid, 0)
        new_steps = act_steps if act_steps > 0 else (st_steps or 0)
        new_has_err = 1 if act_err > 0 else 0
        if act_steps == 0 and new_steps == 0:
            zero_step_orphans.append(sid)

        new_surf = surf or infer_client_surface(tp)
        new_sk = sk or _infer_source_kind(tp)
        new_mach = orig_mach
        if (orig_dev in (None, "", "local")) and not new_mach:
            new_mach = resolve_machine_id(ws or None)

        new_model, new_slug, new_disp, new_mct = model, m_slug, m_disp, max_ctx
        new_in, new_ca, new_out, new_th, new_pk = in_t, ca_t, out_t, th_t, pk_t

        needs_sib = (
            (model or "") in _LEGACY_MODEL_PLACEHOLDERS
            or not m_slug or not max_ctx or in_t is None
        )
        if needs_sib:
            sib_db = _resolve_sibling_db(sid, tp, orig_dev)
            if sib_db is not None:
                gm = read_sibling_gen_metadata(sib_db)
                if gm:
                    sib_model = gm.get("model_slug") or gm.get("model_display_name")
                    if (new_model or "") in _LEGACY_MODEL_PLACEHOLDERS and sib_model and sib_model not in _LEGACY_MODEL_PLACEHOLDERS:
                        new_model = sib_model
                        repaired_models += 1
                    new_slug = new_slug or gm.get("model_slug")
                    new_disp = new_disp or gm.get("model_display_name")
                    new_mct = new_mct or gm.get("max_context_tokens")
                    new_in = new_in if new_in is not None else gm.get("total_input_tokens")
                    new_ca = new_ca if new_ca is not None else gm.get("total_cache_read_tokens")
                    new_out = new_out if new_out is not None else gm.get("total_output_tokens")
                    new_th = new_th if new_th is not None else gm.get("total_thought_tokens")
                    new_pk = new_pk if new_pk is not None else gm.get("peak_context_tokens")

        if (new_surf != surf or new_sk != sk or new_mach != orig_mach or new_slug != m_slug or new_mct != max_ctx or new_in != in_t):
            enriched_meta += 1
        if (new_steps != st_steps or act_tc != st_tc or act_err != st_err or act_int != st_int or new_has_err != has_err):
            updated_counters += 1

        cur.execute(
            """
            UPDATE sessions
            SET total_steps = ?, has_errors = ?, tool_call_count = ?, tool_error_count = ?,
                intervention_count = ?, model = ?, origin_machine = ?, client_surface = ?,
                source_kind = ?, model_slug = ?, model_display_name = ?, max_context_tokens = ?,
                total_input_tokens = ?, total_cache_read_tokens = ?, total_output_tokens = ?,
                total_thought_tokens = ?, peak_context_tokens = ?
            WHERE session_id = ?
            """,
            (
                new_steps, new_has_err, act_tc, act_err, act_int, new_model,
                new_mach, new_surf, new_sk, new_slug, new_disp, new_mct,
                new_in, new_ca, new_out, new_th, new_pk, sid,
            ),
        )

    return {
        "sessions_counters_updated": updated_counters,
        "sessions_metadata_enriched": enriched_meta,
        "models_repaired_from_sibling_db": repaired_models,
        "zero_step_orphans_count": len(zero_step_orphans),
        "zero_step_orphans_sample": zero_step_orphans[:25],
    }


def repair_database_integrity(db_path: Path, dry_run: bool = False) -> Dict[str, Any]:
    """Safely upgrades schema, deduplicates tool_calls, normalizes UTC timestamps, and reconciles sessions."""
    target = Path(db_path)
    if not target.is_file():
        raise FileNotFoundError(f"Telemetry database not found at {target}")

    audit_before = audit_database_integrity(target)
    if dry_run:
        return {
            "db_path": str(target),
            "dry_run": True,
            "repaired": False,
            "audit_before": audit_before,
            "actions": {
                "would_drop_tool_calls": audit_before["duplicate_tool_calls"]["total"],
                "would_normalize_timestamps": audit_before["non_utc_timestamps"]["total"],
                "would_upgrade_columns": audit_before["schema"]["missing_columns"],
            },
        }

    conn = get_db_connection(target, row_factory=False, read_only=False)
    total_p1 = total_p2 = total_drops = total_enriched = 0
    try:
        cur = conn.cursor()
        cur.execute("SELECT name FROM sqlite_master WHERE type='index'")
        indexes = {r[0] for r in cur.fetchall()}
        tc_cols = get_table_cols(cur, "tool_calls")
        if tc_cols and "idx_tool_calls_uniq" not in indexes:
            cur.execute("SELECT session_id, workspace_path FROM sessions")
            ws_map = {r[0]: (r[1] or "") for r in cur.fetchall() if r[0]}
            pre_drops, pre_bfs, pre_p1, pre_p2, _ = scan_tool_call_duplicates(cur, ws_map)
            total_p1 += pre_p1
            total_p2 += pre_p2
            total_drops += len(pre_drops)
            total_enriched += len(pre_bfs)
            if pre_drops or pre_bfs:
                apply_dedup_mutations(conn, pre_drops, pre_bfs)
                conn.commit()

        ensure_telemetry_schema(conn)

        cur.execute("SELECT session_id, workspace_path FROM sessions")
        ws_map = {r[0]: (r[1] or "") for r in cur.fetchall() if r[0]}
        drop_ids, backfills, p1_drops, p2_drops, _ = scan_tool_call_duplicates(cur, ws_map)
        total_p1 += p1_drops
        total_p2 += p2_drops
        total_drops += len(drop_ids)
        total_enriched += len(backfills)
        if drop_ids or backfills:
            apply_dedup_mutations(conn, drop_ids, backfills)

        ts_norm = {
            "sessions": _normalize_table_timestamps(conn, "sessions", ("start_time", "end_time", "remote_synced_at")),
            "steps": _normalize_table_timestamps(conn, "steps", ("created_at",)),
            "tool_calls": _normalize_table_timestamps(conn, "tool_calls", ("started_at", "completed_at")),
            "user_interventions": _normalize_table_timestamps(conn, "user_interventions", ("created_at",)),
            "sync_watermarks": _normalize_table_timestamps(conn, "sync_watermarks", ("last_synced_at", "updated_at")),
        }
        reconcile_stats = _reconcile_sessions(conn)
        conn.commit()
    finally:
        conn.close()

    audit_after = audit_database_integrity(target)
    return {
        "db_path": str(target),
        "dry_run": False,
        "repaired": True,
        "audit_before": audit_before,
        "audit_after": audit_after,
        "actions": {
            "tool_calls_dropped_pass1": total_p1,
            "tool_calls_dropped_pass2": total_p2,
            "tool_calls_dropped_total": total_drops,
            "tool_calls_enriched_from_dups": total_enriched,
            "timestamps_normalized": ts_norm,
            **reconcile_stats,
        },
    }


__all__ = [
    "audit_database_integrity",
    "repair_database_integrity",
]
