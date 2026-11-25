#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Arafat Zahan (@kuasha420)
# Corporate Stewardship & Infrastructure: Purrfect Software Limited (PSL)
# Governed by: ICARO-42/b Ordinance (Company-Supported Personal IP Framework)

"""
Dynamic Git Era x Model Telemetry Engine (G0.1-B).

Derives longitudinal eras dynamically from `git log` and `git tag` boundaries
(falling back cleanly to built-in milestone defaults when `.git` is unavailable),
and computes controlled Era x Model and IDE vs CLI metrics across telemetry.db.
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
import math
from pathlib import Path
import sqlite3
import subprocess
import sys
from typing import Any, Dict, List, Optional, Tuple, Union

from harness.telemetry.config import infer_client_surface
from harness.telemetry.models import normalize_model, normalize_utc_iso

REPO_ROOT = Path(__file__).resolve().parent.parent
_COMPACTED_OUTPUT_LEN = 500 + 1000 + 120
_DEFAULT_MILESTONE_ERAS: Tuple[Tuple[str, str, Optional[str], Optional[str], Optional[str]], ...] = (
    ("0_Pre-Harness", "Pre-Harness Baseline (< 2026-10-02)", None, "2026-10-02T00:00:00Z", None),
    ("1_Bootstrap_Foundation", "Bootstrap & ADR-030 Sync (to v1.0.0-rc0)", "2026-10-02T00:00:00Z", "2026-10-13T02:31:42Z", "v1.0.0-rc0"),
    ("2_Early_RC_Harden", "Early RC Hardening (rc0..rc6)", "2026-10-13T02:31:42Z", "2026-10-18T14:53:00Z", "v1.0.0-rc6"),
    ("3_Swarm_HUD_SSOT", "Swarm Resilience & Trajectory SSOT (rc6..rc11)", "2026-10-18T14:53:00Z", "2026-11-15T16:26:17Z", "v1.0.0-rc11"),
    ("4_Antigravity_v234", "Antigravity v2.34 & REA Acceleration (rc11..rc14)", "2026-11-15T16:26:17Z", "2026-11-22T19:40:27Z", "v1.0.0-rc14"),
    ("5_CodexV2_GA", "Codex v2 & v1.0.0 GA Release (rc14..v1.0.0)", "2026-11-22T19:40:27Z", "2026-11-25T05:40:58Z", "v1.0.0"),
    ("6_PostGA_HEAD", "Post-GA Website & Two-Stream Uplift (v1.0.0..HEAD)", "2026-11-25T05:40:58Z", None, "HEAD"),
)


def _run_git(args: List[str], cwd: Path) -> Optional[str]:
    try:
        proc = subprocess.run(
            ["git"] + args,
            cwd=str(cwd),
            capture_output=True,
            text=True,
            timeout=2.0,
            check=False,
        )
        if proc.returncode == 0 and proc.stdout.strip():
            return proc.stdout.strip()
    except (OSError, subprocess.SubprocessError):
        pass
    return None


def _parse_utc_epoch(iso_str: Optional[str]) -> Optional[float]:
    norm = normalize_utc_iso(iso_str)
    if not norm:
        return None
    try:
        return datetime.fromisoformat(norm[:-1] + "+00:00").timestamp()
    except ValueError:
        return None


def derive_git_eras(repo_root: Optional[Path] = None) -> List[Dict[str, Any]]:
    """Derives historical milestone eras dynamically from git log/tag boundaries."""
    root = Path(repo_root).resolve() if repo_root else REPO_ROOT
    default_list = [
        {"era_id": eid, "label": lbl, "start_utc": s, "end_utc": e, "tag": t, "source": "default_milestones"}
        for eid, lbl, s, e, t in _DEFAULT_MILESTONE_ERAS
    ]
    if not (root / ".git").exists():
        return default_list

    first_raw = _run_git(["log", "--reverse", "--format=%aI", "--max-parents=0"], root)
    if not first_raw:
        first_raw = _run_git(["log", "--reverse", "--format=%aI"], root)
    head_raw = _run_git(["log", "-1", "--format=%aI"], root)
    tags_raw = _run_git(
        ["for-each-ref", "--sort=creatordate", "--format=%(refname:short)|%(creatordate:iso-strict)|%(subject)", "refs/tags"],
        root,
    )
    if not first_raw or not head_raw:
        return default_list

    first_iso = normalize_utc_iso(first_raw.splitlines()[0])
    head_iso = normalize_utc_iso(head_raw.splitlines()[0])
    if not first_iso or not head_iso:
        return default_list
    inception_day = f"{first_iso[:10]}T00:00:00Z"
    inc_ep = _parse_utc_epoch(inception_day) or 0.0

    raw_tags: List[Tuple[str, str, float, str]] = []
    if tags_raw:
        for line in tags_raw.splitlines():
            parts = line.split("|", 2)
            if len(parts) < 2:
                continue
            tag_name, tag_ts = parts[0].strip(), normalize_utc_iso(parts[1].strip())
            subj = parts[2].strip() if len(parts) > 2 else ""
            ep = _parse_utc_epoch(tag_ts)
            if tag_name and tag_ts and ep is not None and ep >= inc_ep:
                raw_tags.append((tag_name, tag_ts, ep, subj))

    if not raw_tags:
        return default_list

    if len(raw_tags) > 6:
        coalesced: List[Tuple[str, str, float, str]] = []
        for item in raw_tags:
            if not coalesced:
                coalesced.append(item)
                continue
            prev = coalesced[-1]
            if item[2] - prev[2] < 48 * 3600 and prev[0] != "v1.0.0-rc0":
                coalesced[-1] = item
            else:
                coalesced.append(item)
        raw_tags = coalesced

    eras: List[Dict[str, Any]] = [
        {
            "era_id": "0_Pre-Harness",
            "label": f"Pre-Harness Baseline (< {inception_day[:10]})",
            "start_utc": None,
            "end_utc": inception_day,
            "tag": None,
            "source": "git",
        }
    ]
    prev_iso = inception_day
    prev_tag = "init"
    for idx, (tag_name, tag_iso, _, _) in enumerate(raw_tags, 1):
        if tag_iso <= prev_iso:
            continue
        safe_tag = tag_name.replace("/", "_")
        eras.append({
            "era_id": f"{idx}_{safe_tag}",
            "label": f"{prev_tag} -> {tag_name} ({prev_iso[:10]}..{tag_iso[:10]})",
            "start_utc": prev_iso,
            "end_utc": tag_iso,
            "tag": tag_name,
            "source": "git",
        })
        prev_iso = tag_iso
        prev_tag = tag_name

    head_ep = _parse_utc_epoch(head_iso) or 0.0
    prev_ep = _parse_utc_epoch(prev_iso) or 0.0
    if head_ep >= prev_ep:
        eras.append({
            "era_id": f"{len(eras)}_Post_{prev_tag.replace('/', '_')}_HEAD",
            "label": f"{prev_tag} -> HEAD ({prev_iso[:10]}..)",
            "start_utc": prev_iso,
            "end_utc": None,
            "tag": "HEAD",
            "source": "git",
        })
    return eras


def _percentile(sorted_vals: List[int], pct: float) -> int:
    if not sorted_vals:
        return 0
    idx = max(0, min(len(sorted_vals) - 1, math.ceil(pct * len(sorted_vals)) - 1))
    return sorted_vals[idx]


def _compute_group_metrics(items: List[Dict[str, Any]]) -> Dict[str, Any]:
    s_cnt = len(items)
    if s_cnt == 0:
        return {
            "sessions": 0, "steps": 0, "tool_calls": 0, "tool_errors": 0,
            "errors_per_1k_calls": 0.0, "interventions": 0, "interventions_per_100_steps": 0.0,
            "loop_candidates": 0, "loop_candidates_per_1k_calls": 0.0,
            "compaction_savings_2kb_pct": 0.0, "compaction_savings_32kb_pct": 0.0,
            "median_steps": 0, "p95_steps": 0, "titan_sessions": 0, "titan_share_pct": 0.0,
        }
    steps_list = sorted(int(x["steps"]) for x in items)
    tot_steps = sum(steps_list)
    tot_calls = sum(int(x["calls"]) for x in items)
    tot_errs = sum(int(x["errors"]) for x in items)
    tot_ints = sum(int(x["interventions"]) for x in items)
    tot_loops = sum(int(x["loops"]) for x in items)
    tot_out = sum(int(x["out_chars"]) for x in items)
    saved_2k = sum(int(x["saved_2kb"]) for x in items)
    saved_32k = sum(int(x["saved_32kb"]) for x in items)
    titans = sum(1 for v in steps_list if v >= 1000)

    return {
        "sessions": s_cnt,
        "steps": tot_steps,
        "tool_calls": tot_calls,
        "tool_errors": tot_errs,
        "errors_per_1k_calls": round(tot_errs * 1000.0 / tot_calls, 2) if tot_calls else 0.0,
        "interventions": tot_ints,
        "interventions_per_100_steps": round(tot_ints * 100.0 / tot_steps, 2) if tot_steps else 0.0,
        "loop_candidates": tot_loops,
        "loop_candidates_per_1k_calls": round(tot_loops * 1000.0 / tot_calls, 2) if tot_calls else 0.0,
        "compaction_savings_2kb_pct": round(saved_2k * 100.0 / tot_out, 2) if tot_out else 0.0,
        "compaction_savings_32kb_pct": round(saved_32k * 100.0 / tot_out, 2) if tot_out else 0.0,
        "median_steps": _percentile(steps_list, 0.50),
        "p95_steps": _percentile(steps_list, 0.95),
        "titan_sessions": titans,
        "titan_share_pct": round(titans * 100.0 / s_cnt, 2),
    }


def _assign_era(ts_utc: Optional[str], eras: List[Dict[str, Any]]) -> str:
    if not ts_utc:
        return "unassigned"
    for era in eras:
        s_u, e_u = era["start_utc"], era["end_utc"]
        if (s_u is None or ts_utc >= s_u) and (e_u is None or ts_utc < e_u):
            return era["era_id"]
    return eras[-1]["era_id"] if eras else "unassigned"


def analyze_eras(
    db_path: Path,
    repo_root: Optional[Path] = None,
) -> Dict[str, Any]:
    """Computes dynamic era boundaries and controlled Era x Model + Surface metrics."""
    eras = derive_git_eras(repo_root)
    conn = sqlite3.connect(f"file:{Path(db_path).resolve()}?mode=ro", uri=True)
    try:
        c = conn.cursor()
        c.execute("PRAGMA table_info(sessions)")
        sess_cols = {r[1] for r in c.fetchall()}
        c.execute("PRAGMA table_info(tool_calls)")
        tc_cols = {r[1] for r in c.fetchall()}

        surf_col = "client_surface" if "client_surface" in sess_cols else "NULL"
        slug_col = "model_slug" if "model_slug" in sess_cols else "NULL"
        disp_col = "model_display_name" if "model_display_name" in sess_cols else "NULL"

        c.execute(
            f"""
            SELECT session_id, start_time, end_time, COALESCE(total_steps, 0),
                   model, transcript_path, {surf_col}, {slug_col}, {disp_col},
                   COALESCE(tool_call_count, 0), COALESCE(tool_error_count, 0), COALESCE(intervention_count, 0)
            FROM sessions
            """
        )
        session_rows = c.fetchall()

        tc_stats: Dict[str, Tuple[int, int, int, int, int, int]] = {}
        if tc_cols:
            out_expr = "COALESCE(output_length_chars, 0)" if "output_length_chars" in tc_cols else "0"
            ec_expr = "status != 'SUCCESS' OR (exit_code IS NOT NULL AND exit_code != 0)" if "exit_code" in tc_cols else "status != 'SUCCESS'"
            loop_expr = "CASE WHEN is_loop_candidate = 1 THEN 1 ELSE 0 END" if "is_loop_candidate" in tc_cols else "0"
            c.execute(
                f"""
                SELECT session_id, COUNT(*),
                       SUM(CASE WHEN {ec_expr} THEN 1 ELSE 0 END),
                       SUM({loop_expr}),
                       SUM({out_expr}),
                       SUM(CASE WHEN status = 'SUCCESS' AND {out_expr} > 2048 THEN {out_expr} - {_COMPACTED_OUTPUT_LEN} ELSE 0 END),
                       SUM(CASE WHEN status = 'SUCCESS' AND {out_expr} > 32768 THEN {out_expr} - {_COMPACTED_OUTPUT_LEN} ELSE 0 END)
                FROM tool_calls
                GROUP BY session_id
                """
            )
            for r in c.fetchall():
                tc_stats[r[0]] = (r[1] or 0, r[2] or 0, r[3] or 0, r[4] or 0, r[5] or 0, r[6] or 0)

        step_fallback: Dict[str, Tuple[int, int, int]] = {}
        c.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='steps'")
        if c.fetchone():
            c.execute(
                f"""
                SELECT session_id,
                       SUM(COALESCE(content_length, 0)),
                       SUM(CASE WHEN content_length > 2048 THEN content_length - {_COMPACTED_OUTPUT_LEN} ELSE 0 END),
                       SUM(CASE WHEN content_length > 32768 THEN content_length - {_COMPACTED_OUTPUT_LEN} ELSE 0 END)
                FROM steps
                WHERE step_type IN ('RUN_COMMAND', 'READ_FILE', 'VIEW_FILE', 'GENERIC', 'TOOL_USE')
                   OR step_type LIKE 'TOOL_CALL%'
                GROUP BY session_id
                """
            )
            for r in c.fetchall():
                step_fallback[r[0]] = (r[1] or 0, r[2] or 0, r[3] or 0)

        ui_counts: Dict[str, int] = {}
        c.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='user_interventions'")
        if c.fetchone():
            c.execute("SELECT session_id, COUNT(*) FROM user_interventions GROUP BY session_id")
            ui_counts = {r[0]: (r[1] or 0) for r in c.fetchall()}
    finally:
        conn.close()

    records_by_era: Dict[str, List[Dict[str, Any]]] = {e["era_id"]: [] for e in eras}
    unassigned_records: List[Dict[str, Any]] = []

    for sid, st_ts, en_ts, steps, model, tp, surf, slug, disp, st_calls, st_errs, st_ints in session_rows:
        ts_utc = normalize_utc_iso(st_ts) or normalize_utc_iso(en_ts)
        era_id = _assign_era(ts_utc, eras)
        t_info = tc_stats.get(sid)
        if t_info:
            calls, errs, loops, out_c, s2k, s32k = t_info
        else:
            calls, errs, loops, out_c, s2k, s32k = st_calls, st_errs, 0, 0, 0, 0
        if out_c == 0 and sid in step_fallback:
            out_c, s2k, s32k = step_fallback[sid]

        m_info = normalize_model(model, model_slug=slug, model_display_name=disp)
        surface = (surf or "").strip().lower() or infer_client_surface(tp)
        if surface not in ("ide", "cli"):
            surface = "ide"

        rec = {
            "session_id": sid,
            "era_id": era_id,
            "steps": steps,
            "calls": calls,
            "errors": errs,
            "interventions": ui_counts.get(sid, st_ints),
            "loops": loops,
            "out_chars": out_c,
            "saved_2kb": s2k,
            "saved_32kb": s32k,
            "surface": surface,
            "canonical_model": m_info.canonical_model,
            "model_family": m_info.family,
            "attribution_status": m_info.attribution_status,
        }
        if era_id in records_by_era:
            records_by_era[era_id].append(rec)
        else:
            unassigned_records.append(rec)

    era_results: List[Dict[str, Any]] = []
    controlled_map: Dict[str, List[Dict[str, Any]]] = {}

    for era in eras:
        eid = era["era_id"]
        recs = records_by_era[eid]
        overall = _compute_group_metrics(recs)
        surf_bd = {
            sf: _compute_group_metrics([r for r in recs if r["surface"] == sf])
            for sf in ("ide", "cli")
        }
        attr_groups: Dict[str, List[Dict[str, Any]]] = {}
        iso_groups: Dict[str, List[Dict[str, Any]]] = {}
        for r in recs:
            if r["attribution_status"] == "attributed":
                attr_groups.setdefault(r["canonical_model"], []).append(r)
            else:
                iso_groups.setdefault(r["canonical_model"], []).append(r)

        by_model = {}
        for mod_name, m_recs in sorted(attr_groups.items(), key=lambda x: len(x[1]), reverse=True):
            metrics = _compute_group_metrics(m_recs)
            metrics["model_family"] = m_recs[0]["model_family"]
            by_model[mod_name] = metrics
            controlled_map.setdefault(mod_name, []).append({
                "era_id": eid, "label": era["label"], **metrics,
            })

        isolated = {
            iso_k: _compute_group_metrics(iso_recs)
            for iso_k, iso_recs in sorted(iso_groups.items())
        }
        era_results.append({
            **era,
            **overall,
            "surface_breakdown": surf_bd,
            "by_model": by_model,
            "isolated_unattributed": isolated,
        })

    return {
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "database": str(db_path),
        "era_source": eras[0]["source"] if eras else "none",
        "era_boundaries": eras,
        "eras": era_results,
        "model_controlled_comparison": controlled_map,
        "unassigned_sessions": len(unassigned_records),
        "summary": {
            "total_eras": len(era_results),
            "total_sessions": sum(e["sessions"] for e in era_results) + len(unassigned_records),
            "total_attributed_models": len(controlled_map),
        },
    }


def generate_markdown_report(data: Dict[str, Any]) -> str:
    """Renders dynamic Era x Model longitudinal comparison report."""
    lines = [
        "<!-- SPDX-License-Identifier: Apache-2.0 -->",
        "<!-- Copyright (c) 2026 Arafat Zahan (@kuasha420) -->",
        "<!-- Corporate Stewardship & Infrastructure: Purrfect Software Limited (PSL) -->",
        "<!-- Governed by: ICARO-42/b Ordinance (Company-Supported Personal IP Framework) -->",
        "",
        "# Longitudinal Git Era x Model Telemetry Report",
        "",
        f"**Generated At**: {data['generated_at']}  ",
        f"**Boundary Source**: `{data['era_source']}`  ",
        f"**Total Sessions**: {data['summary']['total_sessions']:,}",
        "",
        "## 1. Per-Era Longitudinal Trajectory",
        "",
        "| Era | Sessions | Steps | Tool Calls | Err / 1k | Interv / 100s | Loops / 1k | 2KB Sav % | 32KB Sav % | Med / P95 Steps | Titan % | IDE / CLI |",
        "| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |",
    ]
    for e in data["eras"]:
        ide_s = e["surface_breakdown"]["ide"]["sessions"]
        cli_s = e["surface_breakdown"]["cli"]["sessions"]
        lines.append(
            f"| `{e['era_id']}` | {e['sessions']:,} | {e['steps']:,} | {e['tool_calls']:,} | "
            f"{e['errors_per_1k_calls']} | {e['interventions_per_100_steps']} | {e['loop_candidates_per_1k_calls']} | "
            f"{e['compaction_savings_2kb_pct']}% | {e['compaction_savings_32kb_pct']}% | "
            f"{e['median_steps']} / {e['p95_steps']} | {e['titan_share_pct']}% | {ide_s} / {cli_s} |"
        )
    lines.extend(["", "## 2. Controlled Era x Model Comparison (Attributed Models)", ""])
    for mod_name, series in data["model_controlled_comparison"].items():
        if sum(s["sessions"] for s in series) < 2 and len(series) < 2:
            continue
        lines.append(f"### `{mod_name}`")
        lines.append("| Era | Sessions | Steps | Err / 1k | Interv / 100s | Loops / 1k | Titan % |")
        lines.append("| :--- | :--- | :--- | :--- | :--- | :--- | :--- |")
        for row in series:
            lines.append(
                f"| `{row['era_id']}` | {row['sessions']:,} | {row['steps']:,} | "
                f"{row['errors_per_1k_calls']} | {row['interventions_per_100_steps']} | "
                f"{row['loop_candidates_per_1k_calls']} | {row['titan_share_pct']}% |"
            )
        lines.append("")
    return "\n".join(lines)


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Analyze longitudinal telemetry across dynamic Git eras and models.")
    parser.add_argument("--db", default="data/telemetry.db", help="Path to SQLite telemetry database")
    parser.add_argument("--json", action="store_true", help="Print JSON payload to stdout")
    parser.add_argument("--output-json", default="data/era_analysis.json", help="Path to write era analysis JSON")
    parser.add_argument("--output-report", default="data/reports/era-analysis-report.md", help="Path to write Markdown report")
    args = parser.parse_args(argv)

    db_path = Path(args.db)
    if not db_path.is_file():
        sys.stderr.write(f"Error: Telemetry database not found at {db_path}\n")
        return 1

    results = analyze_eras(db_path)
    out_json = Path(args.output_json)
    out_json.parent.mkdir(parents=True, exist_ok=True)
    out_json.write_text(json.dumps(results, indent=2), encoding="utf-8")

    out_md = Path(args.output_report)
    out_md.parent.mkdir(parents=True, exist_ok=True)
    out_md.write_text(generate_markdown_report(results), encoding="utf-8")

    if args.json:
        print(json.dumps(results, indent=2))
    else:
        print(f"✔ Analyzed {results['summary']['total_eras']} dynamic eras across {results['summary']['total_sessions']:,} sessions")
        print(f"  -> JSON:   {out_json}")
        print(f"  -> Report: {out_md}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
