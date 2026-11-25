# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Arafat Zahan (@kuasha420)
# Corporate Stewardship & Infrastructure: Purrfect Software Limited (PSL)
# Governed by: ICARO-42/b Ordinance (Company-Supported Personal IP Framework)

"""
Two-Pass Deterministic Tool-Call Deduplication Engine (ADR-014 / G0.1-B).

Supports:
- Same-step exact + canonical argument normalization (Pass 1)
- Cross-source (+/-2s UTC drift, +/-1 step offset, pyrepr/json, redaction equivalence) deduplication (Pass 2)
- Richest-row scoring & non-empty field backfill from absorbed duplicates
"""

from __future__ import annotations

import ast
from datetime import datetime, timezone
import json
import re
import sqlite3
from typing import Any, Dict, List, Optional, Set, Tuple

_TZ_OFFSET_RE = re.compile(r"[+-]\d{2}:?\d{2}$")
_WS_HOME_REL_RE = re.compile(r"^/(?:home|Users)/[^/]+/(.+)$")
_STRIP_DEV_RE = re.compile(r"(?:/(?:home|Users)/[A-Za-z0-9_.\-]+|\[USER_HOME\])(?:/Dev/[A-Za-z0-9_.\-]+)?")
_STRIP_USER_RE = re.compile(r"/(?:home|Users)/[A-Za-z0-9_.\-]+")


def parse_ts_epoch(ts: Optional[str]) -> Optional[int]:
    """Parses an ISO timestamp string into UTC integer epoch seconds."""
    if not ts or not isinstance(ts, str):
        return None
    line = ts.strip().splitlines()[0].strip() if ts.strip() else ""
    if not line:
        return None
    cand = line[:-1] + "+00:00" if line[-1] in ("Z", "z") else line
    try:
        dt = datetime.fromisoformat(cand)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return int(dt.timestamp())
    except ValueError:
        return None


def has_non_utc_offset(ts: Optional[str]) -> bool:
    """Returns True if timestamp carries a non-zero timezone offset suffix."""
    if not ts or not isinstance(ts, str):
        return False
    s = ts.strip().splitlines()[0].strip()
    m = _TZ_OFFSET_RE.search(s)
    return bool(m and m.group(0) not in ("+00:00", "+0000", "-00:00", "-0000"))


def _norm_value_for_dedup(val: str, workspace_path: str = "", strip_dev: bool = False) -> str:
    """Normalizes redacted and unredacted home/workspace path prefixes symmetrically."""
    if workspace_path and workspace_path.startswith("/") and len(workspace_path) > 1:
        val = val.replace(workspace_path, "")
        m_rel = _WS_HOME_REL_RE.match(workspace_path.rstrip("/"))
        if m_rel:
            ws_rel = m_rel.group(1)
            val = re.sub(rf"\[USER_HOME\]/{re.escape(ws_rel)}(?=/|$|[\"',\s\}}])", "", val)
    val = re.sub(r"/home\[WORKSPACE_ROOT\](?:\.\d+)?", "", val)
    val = re.sub(r"\[WORKSPACE_ROOT\](?:\.\d+)?", "", val)
    if strip_dev:
        val = _STRIP_DEV_RE.sub("", val)
    else:
        val = _STRIP_USER_RE.sub("", val)
    return val.replace("[USER_HOME]", "")


def _parse_args_canon(
    ajson: Optional[str],
    asnip: Optional[str],
    workspace_path: str = "",
    strip_dev: bool = False,
) -> Tuple[str, Optional[Dict[str, Any]], str]:
    raw = ajson or asnip or ""
    s = raw.lstrip()
    fmt = "json" if (s.startswith('{"') or s == "{}") else ("pyrepr" if s.startswith("{'") else "other")
    for parser in (json.loads, ast.literal_eval):
        try:
            d = parser(raw)
        except (ValueError, SyntaxError, TypeError):
            continue
        if isinstance(d, dict):
            cleaned: Dict[str, Any] = {}
            for k, v in d.items():
                if k in ("toolAction", "toolSummary"):
                    continue
                if isinstance(v, bool):
                    cleaned[k] = "true" if v else "false"
                elif isinstance(v, (int, float)):
                    cleaned[k] = str(v)
                elif isinstance(v, str):
                    vs = v
                    if len(vs) >= 2 and vs.startswith('"') and vs.endswith('"'):
                        try:
                            vs = json.loads(vs)
                        except (json.JSONDecodeError, ValueError):
                            pass
                    if vs in ("True", "False"):
                        vs = vs.lower()
                    cleaned[k] = _norm_value_for_dedup(str(vs), workspace_path, strip_dev=strip_dev)
                else:
                    cleaned[k] = v
            return fmt, cleaned, json.dumps(cleaned, sort_keys=True, ensure_ascii=False)
    norm = raw.replace("\\\\n", "\\n").replace("\\u0026", "&").replace("\\u003c", "<").replace("\\u003e", ">")
    norm = re.sub(r"\\(['\"])", r"\1", norm).replace('"', "").replace("'", "").replace(" ", "")
    norm = _norm_value_for_dedup(norm, workspace_path, strip_dev=strip_dev)
    return fmt, None, norm


def _is_failure_row(status: Optional[str], exit_code: Any) -> bool:
    """Returns True when a tool_call row reflects a non-success / non-zero failure state."""
    if status in ("FAILED", "ERROR") or (status is not None and status != "SUCCESS"):
        return True
    return exit_code is not None and exit_code != 0


def _score_tool_row(
    rid: int, fmt: str, ajson: Optional[str], asnip: Optional[str],
    olen: int, esnip: Optional[str], status: Optional[str], exit_code: Any,
    ep: Optional[int], has_tz_offset: bool,
) -> Tuple[int, ...]:
    is_fail = 1 if _is_failure_row(status, exit_code) else 0
    return (
        1 if fmt == "json" else 0,
        0 if "/home[WORKSPACE_ROOT]" in (asnip or "") else 1,
        1 if (ajson is not None and ajson != "") else 0,
        1 if olen > 0 else 0,
        is_fail,
        1 if (esnip is not None and str(esnip).strip() != "") else 0,
        1 if ep is not None else 0,
        0 if has_tz_offset else 1,
        olen,
        -rid,
    )


_FILL_FIELDS: Tuple[str, ...] = (
    "started_at", "completed_at", "duration_seconds", "output_length_chars",
    "output_lines", "arguments_length_chars", "command_category",
    "error_snippet", "target_path", "command_line",
)


def _prepare_tool_record(r: Dict[str, Any], workspace_path: str = "") -> Dict[str, Any]:
    ajson, asnip = r.get("arguments_json"), r.get("arguments_snippet")
    sat = r.get("started_at")
    ep = parse_ts_epoch(sat)
    fmt, pdict, ckey = _parse_args_canon(ajson, asnip, workspace_path, strip_dev=False)
    _, pdict_dev, ckey_dev = _parse_args_canon(ajson, asnip, workspace_path, strip_dev=True)
    has_tz = has_non_utc_offset(sat)
    raw_combo = (ajson or "") + (asnip or "")
    has_red = ("[USER_HOME]" in raw_combo) or ("[WORKSPACE_ROOT]" in raw_combo)
    olen = int(r.get("output_length_chars") or 0)
    score = _score_tool_row(
        r["id"], fmt, ajson, asnip, olen, r.get("error_snippet"),
        r.get("status"), r.get("exit_code"), ep, has_tz,
    )
    return {
        "raw": r, "id": r["id"], "sidx": r.get("step_index"), "tname": r.get("tool_name"),
        "ep": ep, "fmt": fmt, "pdict": pdict, "ckey": ckey,
        "pdict_dev": pdict_dev, "ckey_dev": ckey_dev,
        "has_tz": has_tz, "has_red": has_red, "score": score,
    }


def _build_winner_backfill(
    w_raw: Dict[str, Any],
    losers: List[Dict[str, Any]],
    fill_fields: Tuple[str, ...] = _FILL_FIELDS,
) -> Dict[str, Any]:
    patch_row: Dict[str, Any] = {}
    for l_item in losers:
        l_raw = l_item["raw"]
        for fld in fill_fields:
            cur_val = patch_row.get(fld, w_raw.get(fld))
            cand_val = l_raw.get(fld)
            if (cur_val is None or cur_val == "" or (fld in ("output_length_chars", "output_lines", "arguments_length_chars") and cur_val == 0)) and cand_val not in (None, "", 0):
                patch_row[fld] = cand_val
        if not _is_failure_row(patch_row.get("status", w_raw.get("status")), patch_row.get("exit_code", w_raw.get("exit_code"))):
            l_status, l_ec = l_raw.get("status"), l_raw.get("exit_code")
            if _is_failure_row(l_status, l_ec):
                patch_row["status"] = l_status if (l_status is not None and l_status != "SUCCESS") else "FAILED"
                if l_ec is not None and l_ec != 0:
                    patch_row["exit_code"] = l_ec
                if l_raw.get("error_snippet") and not patch_row.get("error_snippet", w_raw.get("error_snippet")):
                    patch_row["error_snippet"] = l_raw.get("error_snippet")
    return patch_row


def resolve_unique_conflict_group(
    rows: List[Dict[str, Any]],
    workspace_path: str = "",
) -> Tuple[List[int], Dict[int, Dict[str, Any]]]:
    """Selects the richest survivor from rows colliding on idx_tool_calls_uniq after UTC normalization."""
    if len(rows) <= 1:
        return [], {}
    prepared = [_prepare_tool_record(r, workspace_path) for r in rows]
    prepared.sort(key=lambda x: x["score"], reverse=True)
    winner, losers = prepared[0], prepared[1:]
    drop_ids = [item["id"] for item in losers]
    fill_fields = ("arguments_json",) + tuple(f for f in _FILL_FIELDS if f != "started_at")
    patch = _build_winner_backfill(winner["raw"], losers, fill_fields=fill_fields)
    return drop_ids, ({winner["id"]: patch} if patch else {})


def plan_session_dedup(
    rows: List[Dict[str, Any]],
    workspace_path: str = "",
) -> Tuple[List[int], Dict[int, Dict[str, Any]], int, int]:
    """Runs two-pass exact + cross-source deduplication for one session's tool_calls."""
    parsed = [_prepare_tool_record(r, workspace_path) for r in rows]

    by_p1: Dict[Tuple[Any, Any, Any, str], List[Dict[str, Any]]] = {}
    for p in parsed:
        by_p1.setdefault((p["sidx"], p["tname"], p["ep"], p["ckey"]), []).append(p)

    kept1: List[Dict[str, Any]] = []
    merged_from: Dict[int, List[Dict[str, Any]]] = {}
    p1_drops = 0
    for grp in by_p1.values():
        grp.sort(key=lambda x: x["score"], reverse=True)
        winner = grp[0]
        kept1.append(winner)
        if len(grp) > 1:
            p1_drops += len(grp) - 1
            merged_from.setdefault(winner["id"], []).extend(grp[1:])

    kept1.sort(key=lambda x: x["score"], reverse=True)
    kept2: List[Dict[str, Any]] = []
    by_bucket: Dict[Tuple[Optional[str], int], List[Dict[str, Any]]] = {}
    p2_drops = 0
    for p in kept1:
        matched_prev: Optional[Dict[str, Any]] = None
        cur_sidx = p["sidx"] or 0
        for cand_sidx in (cur_sidx - 1, cur_sidx, cur_sidx + 1):
            for prev in by_bucket.get((p["tname"], cand_sidx), ()):
                if abs(cur_sidx - (prev["sidx"] or 0)) > 1:
                    continue
                diff_source = (
                    p["fmt"] != prev["fmt"]
                    or p["has_tz"] != prev["has_tz"]
                    or p["has_red"] != prev["has_red"]
                    or (p["ep"] is None) != (prev["ep"] is None)
                )
                if not diff_source:
                    continue
                if p["ep"] is not None and prev["ep"] is not None and abs(p["ep"] - prev["ep"]) > 2:
                    continue
                if p["pdict"] is not None and prev["pdict"] is not None:
                    args_eq = (p["pdict"] == prev["pdict"]) or (
                        (p["has_red"] != prev["has_red"]) and (p["pdict_dev"] == prev["pdict_dev"])
                    )
                else:
                    c1, c2 = (p["ckey_dev"], prev["ckey_dev"]) if (p["has_red"] != prev["has_red"]) else (p["ckey"], prev["ckey"])
                    mlen = min(len(c1), len(c2))
                    args_eq = (c1 == c2) or bool(mlen >= 50 and c1[:mlen] == c2[:mlen])
                if args_eq:
                    matched_prev = prev
                    break
            if matched_prev is not None:
                break
        if matched_prev is not None:
            p2_drops += 1
            merged_from.setdefault(matched_prev["id"], []).extend([p] + merged_from.pop(p["id"], []))
        else:
            kept2.append(p)
            by_bucket.setdefault((p["tname"], cur_sidx), []).append(p)

    kept_ids = {p["id"] for p in kept2}
    drop_ids = [p["id"] for p in parsed if p["id"] not in kept_ids]
    backfills: Dict[int, Dict[str, Any]] = {}
    for winner in kept2:
        losers = merged_from.get(winner["id"])
        if not losers:
            continue
        patch_row = _build_winner_backfill(winner["raw"], losers)
        if patch_row:
            backfills[winner["id"]] = patch_row

    return drop_ids, backfills, p1_drops, p2_drops


def get_table_cols(cur: sqlite3.Cursor, table: str) -> Set[str]:
    """Returns column names for an existing SQLite table, or empty set if absent."""
    cur.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (table,))
    if not cur.fetchone():
        return set()
    cur.execute(f"PRAGMA table_info({table})")
    return {r[1] for r in cur.fetchall()}


def scan_tool_call_duplicates(cur: sqlite3.Cursor, ws_map: Dict[str, str]) -> Tuple[List[int], Dict[int, Dict[str, Any]], int, int, int]:
    """Streams tool_calls grouped by session_id and computes dedup drop IDs and richest-row backfills."""
    tc_cols = get_table_cols(cur, "tool_calls")
    if not tc_cols:
        return [], {}, 0, 0, 0
    want = [
        "id", "session_id", "step_index", "tool_name", "started_at", "completed_at",
        "duration_seconds", "status", "exit_code", "arguments_json", "arguments_snippet",
        "output_length_chars", "output_lines", "arguments_length_chars",
        "command_category", "error_snippet", "target_path", "command_line",
    ]
    sel_cols = [c if c in tc_cols else f"NULL AS {c}" for c in want]
    cur.execute(f"SELECT {', '.join(sel_cols)} FROM tool_calls ORDER BY session_id, step_index, id")

    all_drops: List[int] = []
    all_backfills: Dict[int, Dict[str, Any]] = {}
    p1_total = p2_total = tc_total = 0
    cur_sid: Optional[str] = None
    buf: List[Dict[str, Any]] = []

    def _flush(sid: Optional[str], items: List[Dict[str, Any]]) -> None:
        nonlocal p1_total, p2_total
        if not items:
            return
        d_ids, bfs, d1, d2 = plan_session_dedup(items, workspace_path=ws_map.get(sid or "", ""))
        all_drops.extend(d_ids)
        all_backfills.update(bfs)
        p1_total += d1
        p2_total += d2

    while True:
        batch = cur.fetchmany(5000)
        if not batch:
            break
        for row in batch:
            tc_total += 1
            rec = dict(zip(want, row))
            sid = rec["session_id"]
            if cur_sid is not None and sid != cur_sid:
                _flush(cur_sid, buf)
                buf = []
            cur_sid = sid
            buf.append(rec)
    _flush(cur_sid, buf)
    return all_drops, all_backfills, p1_total, p2_total, tc_total


def apply_dedup_mutations(
    conn: sqlite3.Connection, drop_ids: List[int], backfills: Dict[int, Dict[str, Any]],
) -> None:
    """Deletes deduplicated tool_calls IDs first (avoiding unique index conflicts), then backfills winners."""
    cur = conn.cursor()
    tcols = get_table_cols(cur, "tool_calls")
    for i in range(0, len(drop_ids), 900):
        chunk = drop_ids[i : i + 900]
        cur.execute(f"DELETE FROM tool_calls WHERE id IN ({','.join(['?'] * len(chunk))})", chunk)
    for row_id, patch in backfills.items():
        valid_patch = {k: v for k, v in patch.items() if k in tcols}
        if not valid_patch:
            continue
        set_sql = ", ".join(f"{k} = ?" for k in valid_patch)
        cur.execute(f"UPDATE tool_calls SET {set_sql} WHERE id = ?", list(valid_patch.values()) + [row_id])
