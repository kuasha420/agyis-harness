#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Arafat Zahan (@kuasha420)
# Corporate Stewardship & Infrastructure: Purrfect Software Limited (PSL)
# Governed by: ICARO-42/b Ordinance (Company-Supported Personal IP Framework)

"""
PSL Harness for Google Antigravity™
Context Cliff & Token Dynamics Analyzer

Measures step-by-step context inflation, identifies top output bloaters,
maps the token saturation cliff, and simulates compaction savings.

Outputs data/reports/context-cliff-dynamics.md and data/context_dynamics_summary.json.
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import sqlite3
from typing import Any, Dict, List, Tuple


from harness.utils.tokens import estimate_tokens


_LEGACY_TOOL_STEP_TYPES = (
    "RUN_COMMAND", "READ_FILE", "VIEW_FILE", "WRITE_TO_FILE", "REPLACE_FILE_CONTENT",
    "GREP_SEARCH", "FIND_BY_NAME", "LIST_DIR", "TOOL_USE", "GENERIC",
)


def analyze_context_dynamics(db_path: Path) -> Dict[str, Any]:
    conn = sqlite3.connect(db_path)
    try:
        c = conn.cursor()
        c.execute("PRAGMA table_info(sessions)")
        sess_cols = {r[1] for r in c.fetchall()}
        c.execute("PRAGMA table_info(tool_calls)")
        tc_cols = {r[1] for r in c.fetchall()}
        has_out_len = "output_length_chars" in tc_cols
        has_ridx = "result_step_index" in tc_cols
        has_pb_tok = "total_input_tokens" in sess_cols

        c.execute("SELECT COUNT(*) FROM sessions")
        total_sessions = int(c.fetchone()[0] or 0)

        # 1. Largest tool bloaters (factoring output_length_chars + error_snippet)
        out_expr = "COALESCE(output_length_chars, 0)" if has_out_len else "0"
        c.execute(
            f"""
            SELECT session_id, step_index, tool_name, command_line, target_path,
                   MAX({out_expr}, COALESCE(LENGTH(error_snippet), 0)) as payload_len,
                   {out_expr} as out_len, duration_seconds, status, exit_code
            FROM tool_calls
            ORDER BY payload_len DESC
            LIMIT 50
            """
        )
        top_bloaters = []
        for r in c.fetchall():
            top_bloaters.append({
                "session_id": r[0],
                "step_index": r[1],
                "tool_name": r[2],
                "command_or_target": str(r[3] or r[4] or "")[:120].replace("\n", " "),
                "snippet_len_chars": r[5] or 0,
                "output_length_chars": r[6] or 0,
                "estimated_tokens": estimate_tokens(r[5] or 0),
                "status": r[8],
                "exit_code": r[9],
            })

        # 2. Step content volume by type (including TOOL_CALL:* output_length_chars fallback)
        if has_out_len:
            c.execute(
                """
                SELECT s.step_type, COUNT(*) as step_cnt,
                       SUM(CASE
                           WHEN (s.step_type LIKE 'TOOL_CALL%' OR s.step_type = 'TOOL_USE') AND COALESCE(s.content_length, 0) = 0
                           THEN COALESCE(tc_agg.tc_chars, 0)
                           ELSE COALESCE(s.content_length, 0)
                       END) as total_content_chars,
                       MAX(CASE
                           WHEN (s.step_type LIKE 'TOOL_CALL%' OR s.step_type = 'TOOL_USE') AND COALESCE(s.content_length, 0) = 0
                           THEN COALESCE(tc_agg.tc_max, 0)
                           ELSE COALESCE(s.content_length, 0)
                       END) as max_content_chars,
                       SUM(COALESCE(s.thinking_length, 0)) as total_thinking_chars,
                       SUM(CASE WHEN COALESCE(s.has_thinking, 0) = 1 OR COALESCE(s.thinking_length, 0) > 0 THEN 1 ELSE 0 END) as thinking_steps
                FROM steps s
                LEFT JOIN (
                    SELECT session_id, step_index,
                           SUM(COALESCE(output_length_chars, 0)) as tc_chars,
                           MAX(COALESCE(output_length_chars, 0)) as tc_max
                    FROM tool_calls
                    GROUP BY session_id, step_index
                ) tc_agg ON s.session_id = tc_agg.session_id AND s.step_index = tc_agg.step_index
                GROUP BY s.step_type
                ORDER BY total_content_chars DESC
                """
            )
        else:
            c.execute(
                """
                SELECT step_type, COUNT(*) as step_cnt,
                       SUM(COALESCE(content_length, 0)) as total_content_chars,
                       MAX(COALESCE(content_length, 0)) as max_content_chars,
                       SUM(COALESCE(thinking_length, 0)) as total_thinking_chars,
                       SUM(CASE WHEN COALESCE(has_thinking, 0) = 1 OR COALESCE(thinking_length, 0) > 0 THEN 1 ELSE 0 END) as thinking_steps
                FROM steps
                GROUP BY step_type
                ORDER BY total_content_chars DESC
                """
            )

        step_type_volumes = []
        total_tokens_all = 0
        thinking_steps_total = 0
        for stype, scnt, c_chars, max_c, th_chars, th_steps in c.fetchall():
            c_chars = int(c_chars or 0)
            th_chars = int(th_chars or 0)
            t_tokens = estimate_tokens(c_chars + th_chars)
            total_tokens_all += t_tokens
            thinking_steps_total += int(th_steps or 0)
            step_type_volumes.append({
                "step_type": stype,
                "step_count": scnt,
                "avg_chars": round(c_chars / scnt, 1) if scnt else 0.0,
                "max_chars": int(max_c or 0),
                "total_chars": c_chars,
                "total_thinking_chars": th_chars,
                "estimated_tokens": t_tokens,
            })

        # 3. Session token footprint vs Error rate buckets (persisted protobuf tokens + char fallback)
        pb_sel = (
            ", COALESCE(s.total_input_tokens, 0), COALESCE(s.total_cache_read_tokens, 0), "
            "COALESCE(s.total_output_tokens, 0), COALESCE(s.total_thought_tokens, 0), COALESCE(s.peak_context_tokens, 0)"
            if has_pb_tok else ", 0, 0, 0, 0, 0"
        )
        tc_sub = (
            "LEFT JOIN (SELECT session_id, SUM(COALESCE(output_length_chars, 0)) AS tc_out FROM tool_calls GROUP BY session_id) tc ON s.session_id = tc.session_id"
            if has_out_len else "LEFT JOIN (SELECT NULL AS session_id, 0 AS tc_out) tc ON 0=1"
        )
        c.execute(
            f"""
            SELECT s.session_id,
                   COALESCE(st.st_chars, 0) as step_chars,
                   COALESCE(tc.tc_out, 0) as tc_chars,
                   COALESCE(s.total_steps, 0),
                   COALESCE(s.tool_error_count, 0),
                   COALESCE(s.intervention_count, 0)
                   {pb_sel}
            FROM sessions s
            LEFT JOIN (
                SELECT session_id, SUM(COALESCE(content_length, 0) + COALESCE(thinking_length, 0)) as st_chars
                FROM steps
                GROUP BY session_id
            ) st ON s.session_id = st.session_id
            {tc_sub}
            """
        )

        volume_buckets = {
            "< 20k tokens": {"sessions": 0, "steps": 0, "errors": 0, "interv": 0, "tokens": 0},
            "20k - 50k tokens": {"sessions": 0, "steps": 0, "errors": 0, "interv": 0, "tokens": 0},
            "50k - 100k tokens": {"sessions": 0, "steps": 0, "errors": 0, "interv": 0, "tokens": 0},
            "100k - 200k tokens": {"sessions": 0, "steps": 0, "errors": 0, "interv": 0, "tokens": 0},
            "200k+ tokens": {"sessions": 0, "steps": 0, "errors": 0, "interv": 0, "tokens": 0},
        }
        pb_sessions = pb_in = pb_cache = pb_out = pb_thought = pb_peak_max = 0
        pb_peaks: List[int] = []

        for row in c.fetchall():
            _, st_chars, tc_chars, steps, errors, interv, s_in, s_ca, s_out, s_th, s_pk = row
            eff_chars = max(int(st_chars or 0), int(tc_chars or 0))
            char_tok = estimate_tokens(eff_chars)
            pb_tot = int(s_in or 0) + int(s_out or 0) + int(s_th or 0)
            if int(s_in or 0) > 0 or int(s_ca or 0) > 0 or int(s_pk or 0) > 0:
                pb_sessions += 1
                pb_in += int(s_in or 0)
                pb_cache += int(s_ca or 0)
                pb_out += int(s_out or 0)
                pb_thought += int(s_th or 0)
                if int(s_pk or 0) > 0:
                    pb_peaks.append(int(s_pk))
                    pb_peak_max = max(pb_peak_max, int(s_pk))
            t_tokens = max(char_tok, pb_tot)
            if t_tokens < 20_000:
                b = "< 20k tokens"
            elif t_tokens < 50_000:
                b = "20k - 50k tokens"
            elif t_tokens < 100_000:
                b = "50k - 100k tokens"
            elif t_tokens < 200_000:
                b = "100k - 200k tokens"
            else:
                b = "200k+ tokens"
            volume_buckets[b]["sessions"] += 1
            volume_buckets[b]["steps"] += steps
            volume_buckets[b]["errors"] += errors
            volume_buckets[b]["interv"] += interv
            volume_buckets[b]["tokens"] += t_tokens

        bucket_results = []
        for b_name, b_data in volume_buckets.items():
            s_cnt = b_data["sessions"]
            bucket_results.append({
                "bucket": b_name,
                "sessions": s_cnt,
                "avg_steps": round(b_data["steps"] / s_cnt, 1) if s_cnt else 0.0,
                "avg_errors": round(b_data["errors"] / s_cnt, 2) if s_cnt else 0.0,
                "avg_interventions": round(b_data["interv"] / s_cnt, 2) if s_cnt else 0.0,
                "avg_tokens": round(b_data["tokens"] / s_cnt, 0) if s_cnt else 0.0,
            })

        # 4. Compaction Simulation (2KB & 32KB) across BOTH legacy tool steps AND TOOL_CALL:* / tool_calls.output_length_chars
        oversized_2kb: List[int] = []
        oversized_32kb: List[int] = []
        seen_tool_results: set[Tuple[str, int]] = set()
        if has_out_len:
            ridx_col = "result_step_index" if has_ridx else "step_index"
            c.execute(f"SELECT session_id, {ridx_col}, output_length_chars FROM tool_calls WHERE COALESCE(output_length_chars, 0) > 2048")
            for sid, ridx, olen in c.fetchall():
                v = int(olen or 0)
                oversized_2kb.append(v)
                if v > 32768:
                    oversized_32kb.append(v)
                if sid and ridx is not None:
                    seen_tool_results.add((sid, int(ridx)))

        legacy_ph = ", ".join(f"'{t}'" for t in _LEGACY_TOOL_STEP_TYPES)
        c.execute(
            f"""
            SELECT session_id, step_index, content_length
            FROM steps
            WHERE (step_type IN ({legacy_ph}) OR step_type LIKE 'TOOL_CALL%')
              AND content_length > 2048
            """
        )
        for sid, sidx, clen in c.fetchall():
            if sid and sidx is not None and (sid, int(sidx)) in seen_tool_results:
                continue
            v = int(clen or 0)
            oversized_2kb.append(v)
            if v > 32768:
                oversized_32kb.append(v)

        total_oversized_chars = sum(oversized_2kb)
        char_savings = sum(max(0, v - 2048) for v in oversized_2kb)
        token_savings = estimate_tokens(char_savings)
        char_savings_32kb = sum(max(0, v - 32768) for v in oversized_32kb)
        token_savings_32kb = estimate_tokens(char_savings_32kb)
    finally:
        conn.close()

    pb_peaks.sort()
    pb_median_peak = pb_peaks[len(pb_peaks) // 2] if pb_peaks else 0

    return {
        "timestamp": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%SZ"),
        "total_sessions": total_sessions,
        "thinking_steps_count": thinking_steps_total,
        "total_estimated_tokens": total_tokens_all,
        "protobuf_token_summary": {
            "sessions_with_protobuf_tokens": pb_sessions,
            "total_input_tokens": pb_in,
            "total_cache_read_tokens": pb_cache,
            "total_output_tokens": pb_out,
            "total_thought_tokens": pb_thought,
            "median_peak_context_tokens": pb_median_peak,
            "max_peak_context_tokens": pb_peak_max,
        },
        "step_volumes": step_type_volumes,
        "token_saturation_buckets": bucket_results,
        "compaction_simulation": {
            "steps_exceeding_2kb": len(oversized_2kb),
            "total_oversized_chars": total_oversized_chars,
            "chars_saved_at_2kb_cap": char_savings,
            "estimated_token_savings": token_savings,
            "potential_savings_pct": round((token_savings / total_tokens_all) * 100, 2) if total_tokens_all else 0,
            "steps_exceeding_32kb": len(oversized_32kb),
            "chars_saved_at_32kb_cap": char_savings_32kb,
            "estimated_token_savings_32kb": token_savings_32kb,
        },
        "top_bloaters": top_bloaters[:15],
    }


def generate_markdown_report(data: Dict[str, Any], output_path: Path) -> None:
    buckets = data["token_saturation_buckets"]
    step_vols = data["step_volumes"]
    sim = data["compaction_simulation"]
    bloaters = data["top_bloaters"]
    total_sessions = data.get("total_sessions", sum(b["sessions"] for b in buckets))
    thinking_steps = data.get("thinking_steps_count", 0)
    pb = data.get("protobuf_token_summary", {})
    by_b = {b["bucket"]: b for b in buckets}
    low_err = by_b.get("< 20k tokens", {}).get("avg_errors", 0.0)
    high_err = by_b.get("200k+ tokens", {}).get("avg_errors", 0.0)
    high_int = by_b.get("200k+ tokens", {}).get("avg_interventions", 0.0)
    err_mult = round(high_err / low_err, 1) if low_err > 0 else 0.0

    md = f"""<!-- SPDX-License-Identifier: Apache-2.0 -->
<!-- Copyright (c) 2026 Arafat Zahan (@kuasha420) -->
<!-- Corporate Stewardship & Infrastructure: Purrfect Software Limited (PSL) -->
<!-- Governed by: ICARO-42/b Ordinance (Company-Supported Personal IP Framework) -->

# 📉 Context Cliff & Token Dynamics Empirical Report
**Project**: Agyis Harness for Google Antigravity™ (`agyis-harness`)  
**Specification**: Horizon 1 — Context Dynamics Analysis  
**Generated At**: {data['timestamp']}  
**Data Source**: Telemetry database `data/telemetry.db`

---

## 1. Executive Summary: The Token Saturation Cliff

Our empirical analysis maps context size directly against agent error rates and operator intervention frequency. Across **{total_sessions:,} developer sessions**, total mined char-equivalent volume reached **~{data['total_estimated_tokens']:,} tokens** (with **{pb.get('sessions_with_protobuf_tokens', 0):,} sessions** carrying persisted protobuf usage totaling **{pb.get('total_input_tokens', 0) + pb.get('total_cache_read_tokens', 0):,}** prompt+cache tokens).

### The Context Saturation Curve
```text
┌───────────────────────────────────────────────────────────────────────────────────────┐
│                        Session Token Footprint vs Error Rates                         │
├────────────────────┬──────────┬───────────┬─────────────┬─────────────┬───────────────┤
│ Token Load Bucket  │ Sessions │ Avg Steps │ Avg Errors  │ Avg Interv  │ Avg Tokens    │
├────────────────────┼──────────┼───────────┼─────────────┼─────────────┼───────────────┤
"""

    for b in buckets:
        md += f"| {b['bucket']:18} | {b['sessions']:8} | {b['avg_steps']:9} | {b['avg_errors']:11} | {b['avg_interventions']:11} | {int(b['avg_tokens']):,} |\n"

    md += f"""└────────────────────┴──────────┴───────────┴─────────────┴─────────────┴───────────────┘
```

> [!CAUTION]
> **Measured Saturation Inflection**:
> - `< 20k tokens`: **{low_err} errors/session** average.
> - `20k - 50k tokens`: **{by_b.get('20k - 50k tokens', {}).get('avg_errors', 0.0)} errors/session**.
> - `50k - 100k tokens`: **{by_b.get('50k - 100k tokens', {}).get('avg_errors', 0.0)} errors/session**.
> - `100k - 200k tokens`: **{by_b.get('100k - 200k tokens', {}).get('avg_errors', 0.0)} errors/session** and **{by_b.get('100k - 200k tokens', {}).get('avg_interventions', 0.0)} interventions/session**.
> - `200k+ tokens`: **{high_err} errors/session** ({f'**{err_mult}x** vs `< 20k`' if err_mult else 'elevated'}) and **{high_int} interventions/session**.

---

## 2. Where Do the Tokens Go? Volume by Step Type

| Step Type | Total Steps | Total Volume (Chars) | Estimated Tokens | % of Total Footprint |
| :--- | :--- | :--- | :--- | :--- |
"""

    tot = data["total_estimated_tokens"]
    for s in step_vols[:10]:
        pct = round((s['estimated_tokens'] / tot) * 100, 1) if tot else 0
        md += f"| `{s['step_type']}` | {s['step_count']:,} | {s['total_chars'] + s['total_thinking_chars']:,} | {s['estimated_tokens']:,} | {pct}% |\n"

    md += f"""
### Key Findings:
1. **Tool Outputs (`TOOL_CALL:*` / `RUN_COMMAND` / `VIEW_FILE` / `GENERIC`) dominate context**: They account for the overwhelming majority of raw text entering the model's history.
2. **Thinking Traces (`thinking`)**: Contributed **{sum(s['total_thinking_chars'] for s in step_vols):,} characters** (~{estimate_tokens(sum(s['total_thinking_chars'] for s in step_vols)):,} tokens) of internal Chain-of-Thought across {thinking_steps:,} steps.

---

## 3. PostToolUse Compaction Simulation: The 2KB & 32KB Caps

What happens if the harness mechanically truncates or summarizes tool output payloads that exceed **2KB (2,048 characters / ~512 tokens)** or **32KB**?

| Simulation Metric | Empirical Value |
| :--- | :--- |
| **Tool Execution Steps Exceeding 2KB** | **{sim['steps_exceeding_2kb']:,} steps** |
| **Raw Volume in Oversized Outputs** | **{sim['total_oversized_chars']:,} characters** |
| **Characters Saved by 2KB Cap** | **{sim['chars_saved_at_2kb_cap']:,} characters** |
| **Estimated Tokens Saved (2KB)** | **~{sim['estimated_token_savings']:,} tokens** |
| **Total Context Reduction Potential (2KB)** | **{sim['potential_savings_pct']}% of mined footprint** |
| **Tool Steps Exceeding 32KB** | **{sim.get('steps_exceeding_32kb', 0):,} steps (~{sim.get('estimated_token_savings_32kb', 0):,} tokens saved)** |

> [!TIP]
> A deterministic `PostToolUse` output compactor that limits tool stdout to 2KB (preserving full error diagnostics when exit code != 0) would eliminate **~{sim['potential_savings_pct']}%** of mined token bloat!

---

## 4. Top Context Bloaters (Sample)

| Session ID | Step | Tool Name | Target / Command | Output Chars |
| :--- | :--- | :--- | :--- | :--- |
"""

    for tb in bloaters[:10]:
        md += f"| `{tb['session_id'][:8]}...` | {tb['step_index']} | `{tb['tool_name']}` | `{tb['command_or_target'][:45]}` | {tb['snippet_len_chars']:,} |\n"

    md += """
---

## 5. Next Steps for Harness Implementation

1. **Implement `harness/hooks/output_compactor_hook.py`**:
   - Register on `PostToolUse` for `run_command` (>2KB) and `read_file` (>32KB).
   - Emit `overwriteResult` compacted output when exit code is 0; preserve full diagnostic output when exit code != 0.
2. **Incorporate into Active Reference Rules**:
   - Add prompt rules directing agents to pipe commands through `head -n 20` or `tail -n 20`.
"""

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(md, encoding="utf-8")
    print(f"[✓] Generated context dynamics report: {output_path}")


def main(argv: Optional[List[str]] = None) -> None:
    parser = argparse.ArgumentParser(description="Analyze context cliff and token dynamics.")
    parser.add_argument("--db", default="data/telemetry.db", help="Path to SQLite database")
    parser.add_argument("--output", "-o", default="data/reports/context-cliff-dynamics.md", help="Path to markdown output")
    parser.add_argument("--json-out", default="data/context_dynamics_summary.json", help="Path to JSON output")
    args = parser.parse_args(argv)

    db_path = Path(args.db)
    if not db_path.exists():
        print(f"Error: Database {db_path} does not exist.")
        return

    data = analyze_context_dynamics(db_path)

    json_path = Path(args.json_out)
    json_path.parent.mkdir(parents=True, exist_ok=True)
    json_path.write_text(json.dumps(data, indent=2), encoding="utf-8")

    md_path = Path(args.output)
    generate_markdown_report(data, md_path)

    print("=" * 70)
    print(" 📉 CONTEXT DYNAMICS ANALYSIS COMPLETE")
    print("=" * 70)
    print(f"Total Mined Volume:           ~{data['total_estimated_tokens']:,} tokens")
    print(f"Compaction Savings Potential: {data['compaction_simulation']['potential_savings_pct']}% (~{data['compaction_simulation']['estimated_token_savings']:,} tokens)")
    print(f"Report:                       {md_path}")
    print(f"JSON:                         {json_path}")
    print("=" * 70)


if __name__ == "__main__":
    main()
