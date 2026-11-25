#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Arafat Zahan (@kuasha420)
# Corporate Stewardship & Infrastructure: Purrfect Software Limited (PSL)
# Governed by: ICARO-42/b Ordinance (Company-Supported Personal IP Framework)

"""
PSL Harness for Google Antigravity™
Taxonomy & Failure Classifier

Classifies workstation telemetry from data/telemetry.db into 4 buckets:
1. WHAT_WORKED (Clean trajectories, high tool success, fast convergence)
2. WHAT_FAILED (Errors, loops, exit codes, context cliff)
3. OPERATOR_GUIDANCE (Human-in-the-loop steering, rescue prompts)
4. HARNESS_OPPORTUNITY (Harness-level hooks, rules, and abstractions)

Generates data/reports/workstation-audit-report.md.
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import sqlite3
from typing import Any, Dict, List, Tuple


def run_classification_audit(db_path: Path) -> Dict[str, Any]:
    conn = sqlite3.connect(db_path)
    try:
        c = conn.cursor()

        # Reconciled high-level stats (compute tool counts/errors directly from tool_calls)
        c.execute("SELECT COUNT(*), COALESCE(SUM(total_steps), 0) FROM sessions")
        sess_cnt, total_steps = c.fetchone()
        c.execute("SELECT COUNT(*), COALESCE(SUM(CASE WHEN status != 'SUCCESS' OR (exit_code IS NOT NULL AND exit_code != 0) THEN 1 ELSE 0 END), 0) FROM tool_calls")
        total_tools, total_errors = c.fetchone()
        c.execute("SELECT COUNT(*) FROM user_interventions")
        total_interventions = c.fetchone()[0] or 0

        # Tool stats
        c.execute("""
            SELECT tool_name, COUNT(*) as total,
                   SUM(CASE WHEN status != 'SUCCESS' OR (exit_code IS NOT NULL AND exit_code != 0) THEN 1 ELSE 0 END) as fails,
                   ROUND(SUM(CASE WHEN status != 'SUCCESS' OR (exit_code IS NOT NULL AND exit_code != 0) THEN 1.0 ELSE 0 END) * 100.0 / COUNT(*), 2) as fail_pct
            FROM tool_calls
            GROUP BY tool_name
            ORDER BY fails DESC, total DESC
        """)
        tool_stats = [
            {"tool": r[0], "total": r[1], "fails": r[2], "fail_rate_pct": r[3]}
            for r in c.fetchall()
        ]

        # Command exit codes
        c.execute("""
            SELECT exit_code, COUNT(*) as cnt
            FROM tool_calls
            WHERE tool_name = 'run_command' AND (status != 'SUCCESS' OR (exit_code IS NOT NULL AND exit_code != 0))
            GROUP BY exit_code
            ORDER BY cnt DESC
            LIMIT 10
        """)
        exit_codes = [{"exit_code": r[0], "count": r[1]} for r in c.fetchall()]

        # Forensic breakdown of Exit Code 1
        c.execute("SELECT COUNT(*) FROM tool_calls WHERE tool_name = 'run_command' AND exit_code = 1")
        total_ec1 = c.fetchone()[0] or 0

        c.execute("""
            SELECT COUNT(*) FROM tool_calls
            WHERE tool_name = 'run_command' AND exit_code = 1
              AND (command_line LIKE '%grep%' OR command_line LIKE '%diff%' OR command_line LIKE '%rg %')
        """)
        ec1_grep_diff = c.fetchone()[0] or 0

        c.execute("""
            SELECT COUNT(*) FROM tool_calls
            WHERE tool_name = 'run_command' AND exit_code = 1
              AND error_snippet LIKE '%f-string expression part cannot include a backslash%'
        """)
        ec1_fstring_bs = c.fetchone()[0] or 0

        c.execute("""
            SELECT COUNT(*) FROM tool_calls
            WHERE tool_name = 'run_command' AND exit_code = 1
              AND error_snippet LIKE '%SyntaxError%'
        """)
        ec1_syntax_total = c.fetchone()[0] or 0

        c.execute("""
            SELECT COUNT(*) FROM tool_calls
            WHERE tool_name = 'run_command' AND exit_code = 1
              AND (error_snippet LIKE '%Traceback%' AND error_snippet NOT LIKE '%SyntaxError%')
        """)
        ec1_traceback = c.fetchone()[0] or 0

        ec1_other = max(0, total_ec1 - (ec1_grep_diff + ec1_syntax_total + ec1_traceback))

        exit_code_1_breakdown = {
            "total": total_ec1,
            "grep_diff_benign": ec1_grep_diff,
            "grep_diff_pct": round(ec1_grep_diff * 100.0 / total_ec1, 2) if total_ec1 else 0,
            "python_syntax_total": ec1_syntax_total,
            "python_syntax_pct": round(ec1_syntax_total * 100.0 / total_ec1, 2) if total_ec1 else 0,
            "fstring_backslash": ec1_fstring_bs,
            "fstring_backslash_pct": round(ec1_fstring_bs * 100.0 / total_ec1, 2) if total_ec1 else 0,
            "python_traceback": ec1_traceback,
            "python_traceback_pct": round(ec1_traceback * 100.0 / total_ec1, 2) if total_ec1 else 0,
            "other_cli": ec1_other,
            "other_cli_pct": round(ec1_other * 100.0 / total_ec1, 2) if total_ec1 else 0,
        }

        # Loop candidates by tool
        c.execute("""
            SELECT tool_name, COUNT(*) as cnt
            FROM tool_calls
            WHERE is_loop_candidate = 1
            GROUP BY tool_name
            ORDER BY cnt DESC
        """)
        loops_by_tool = [{"tool": r[0], "loop_calls": r[1]} for r in c.fetchall()]

        # Context cliff / session depth using reconciled tool_calls error counts
        c.execute("""
            WITH sess_err AS (
                SELECT session_id,
                       SUM(CASE WHEN status != 'SUCCESS' OR (exit_code IS NOT NULL AND exit_code != 0) THEN 1 ELSE 0 END) as tc_errors
                FROM tool_calls
                GROUP BY session_id
            ),
            sess_int AS (
                SELECT session_id, COUNT(*) as ui_cnt
                FROM user_interventions
                GROUP BY session_id
            )
            SELECT
                CASE
                    WHEN COALESCE(s.total_steps, 0) BETWEEN 0 AND 10 THEN '1-10 steps'
                    WHEN s.total_steps BETWEEN 11 AND 50 THEN '11-50 steps'
                    WHEN s.total_steps BETWEEN 51 AND 200 THEN '51-200 steps'
                    ELSE '200+ steps'
                END as step_bucket,
                COUNT(*) as session_count,
                ROUND(AVG(COALESCE(s.total_steps, 0)), 1) as avg_steps,
                ROUND(AVG(COALESCE(se.tc_errors, 0)), 2) as avg_errors,
                ROUND(AVG(COALESCE(si.ui_cnt, 0)), 2) as avg_interventions
            FROM sessions s
            LEFT JOIN sess_err se ON s.session_id = se.session_id
            LEFT JOIN sess_int si ON s.session_id = si.session_id
            GROUP BY step_bucket
            ORDER BY MIN(COALESCE(s.total_steps, 0)) ASC
        """)
        depth_stats = [
            {
                "bucket": r[0],
                "sessions": r[1],
                "avg_steps": r[2],
                "avg_errors": r[3],
                "avg_interventions": r[4],
            }
            for r in c.fetchall()
        ]

        # Clean sessions (>= 20 steps, <= 1 error, 0 interventions)
        c.execute("""
            SELECT session_id, total_steps, tool_call_count, model, workspace_path
            FROM sessions
            WHERE COALESCE(tool_error_count, 0) <= 1 AND COALESCE(intervention_count, 0) = 0 AND COALESCE(total_steps, 0) >= 20
            ORDER BY total_steps DESC
            LIMIT 10
        """)
        clean_sessions = [
            {"session_id": r[0], "steps": r[1], "tools": r[2], "model": r[3], "workspace": r[4]}
            for r in c.fetchall()
        ]

        # Interventions breakdown
        c.execute("""
            SELECT intervention_type, COUNT(*) as cnt
            FROM user_interventions
            GROUP BY intervention_type
            ORDER BY cnt DESC
        """)
        interventions_breakdown = [{"type": r[0], "count": r[1]} for r in c.fetchall()]

        # Frequent failing commands
        c.execute("""
            SELECT command_line, exit_code, COUNT(*) as cnt
            FROM tool_calls
            WHERE tool_name = 'run_command' AND (status != 'SUCCESS' OR (exit_code IS NOT NULL AND exit_code != 0))
              AND command_line IS NOT NULL
            GROUP BY command_line
            ORDER BY cnt DESC
            LIMIT 10
        """)
        failing_cmds = [{"command": r[0], "exit_code": r[1], "occurrences": r[2]} for r in c.fetchall()]
    finally:
        conn.close()

    return {
        "overview": {
            "total_sessions": sess_cnt,
            "total_steps": total_steps,
            "total_tool_calls": total_tools,
            "total_tool_errors": total_errors,
            "total_interventions": total_interventions,
            "overall_tool_error_rate_pct": round((total_errors / total_tools) * 100, 2) if total_tools else 0,
            "overall_session_intervention_rate": round(total_interventions / sess_cnt, 2) if sess_cnt else 0,
        },
        "tool_stats": tool_stats,
        "exit_codes": exit_codes,
        "loops_by_tool": loops_by_tool,
        "depth_stats": depth_stats,
        "clean_sessions": clean_sessions,
        "interventions": interventions_breakdown,
        "failing_commands": failing_cmds,
        "exit_code_1_breakdown": exit_code_1_breakdown,
    }


def generate_markdown_report(audit: Dict[str, Any], output_path: Path) -> None:
    overview = audit["overview"]
    tool_stats = audit["tool_stats"]
    exit_codes = audit["exit_codes"]
    loops = audit["loops_by_tool"]
    depth_stats = audit["depth_stats"]
    interventions = audit["interventions"]
    clean_sessions = audit.get("clean_sessions", [])
    total_err = overview["total_tool_errors"] or 0
    total_int = overview["total_interventions"] or 0
    run_cmd_stat = next((t for t in tool_stats if t["tool"] == "run_command"), {"fails": 0})
    run_cmd_fails = run_cmd_stat["fails"]
    run_cmd_share = round(run_cmd_fails * 100.0 / total_err, 1) if total_err else 0.0
    by_bucket = {d["bucket"]: d for d in depth_stats}
    b_low = by_bucket.get("1-10 steps", {})
    b_high = by_bucket.get("200+ steps", {})

    md = f"""<!-- SPDX-License-Identifier: Apache-2.0 -->
<!-- Copyright (c) 2026 Arafat Zahan (@kuasha420) -->
<!-- Corporate Stewardship & Infrastructure: Purrfect Software Limited (PSL) -->
<!-- Governed by: ICARO-42/b Ordinance (Company-Supported Personal IP Framework) -->

# 📊 Workstation Empirical Telemetry & Audit Report
**Project**: Agyis Harness for Google Antigravity™ (`agyis-harness`)  
**Publisher**: Purrfect Software Limited (PSL)  
**License**: Apache-2.0  
**Generated At**: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%SZ')}  
**Data Source**: Reconciled workstation telemetry in `data/telemetry.db`

---

## Executive Summary

An empirical audit of **{overview['total_sessions']:,} developer sessions** was conducted using `agyis-harness`.

| Metric | Empirical Value | Significance |
| :--- | :--- | :--- |
| **Total Sessions Audited** | **{overview['total_sessions']:,}** | Reconciled empirical baseline across IDE and CLI surfaces. |
| **Total Trajectory Steps** | **{overview['total_steps']:,}** | Deep step-by-step telemetry covering planning, coding, and debugging. |
| **Total Tool Executions** | **{overview['total_tool_calls']:,}** | Deduplicated tool executions across file systems, terminals, and MCP. |
| **Tool Failures Encountered** | **{total_err:,}** ({overview['overall_tool_error_rate_pct']}%) | Reconciled directly from `tool_calls` failure and exit-code status. |
| **Human Operator Interventions** | **{total_int:,}** ({overview['overall_session_intervention_rate']} / session) | Direct steering, confirmations, corrections, or rescue prompts. |
| **Repeated Tool Loop Calls** | **{sum(l['loop_calls'] for l in loops):,}** | Redundant consecutive identical tool calls consuming context. |

---

## 🔬 The Empirical Taxonomy: 4 Operational Buckets

### 🟢 1. WHAT WORKED (High-Fidelity Autonomous Trajectories)
- **Clean Autonomous Sessions (`>= 20` steps, `<= 1` error, `0` interventions)**: **{len(clean_sessions)}** top-depth sample sessions tracked cleanly.
"""
    for t in [x for x in tool_stats if x["total"] >= 10 and x["fail_rate_pct"] <= 5.0][:4]:
        success_pct = round(100.0 - float(t["fail_rate_pct"] or 0.0), 1)
        md += f"- **`{t['tool']}`**: **{success_pct}% success rate** across **{t['total']:,}** calls ({t['fails']:,} failures).\n"

    md += f"""
---

### 🔴 2. WHAT FAILED (Mechanistic & Operational Breakdowns)

#### Top Failing Tools Breakdown
| Tool Name | Total Calls | Failures | Failure Rate (%) | Primary Failure Mode |
| :--- | :--- | :--- | :--- | :--- |
"""

    for t in tool_stats[:8]:
        primary_reason = "Exit code != 0, command not found, SSH timeout" if t['tool'] == "run_command" else (
            "Syntax / pattern mismatch" if t['tool'] in ("grep_search", "run_command") else (
                "Task ID invalid or expired" if t['tool'] == "manage_task" else "Schema / target error"
            )
        )
        md += f"| `{t['tool']}` | {t['total']:,} | {t['fails']:,} | {t['fail_rate_pct']}% | {primary_reason} |\n"

    md += f"""
#### Exit Code Distribution for `run_command` ({run_cmd_fails:,} Total Failures)
The terminal tool (`run_command`) accounts for **{run_cmd_share}%** of all reconciled tool failures ({run_cmd_fails:,} / {total_err:,}).
"""
    for ec in exit_codes[:7]:
        desc = "General error (test failure, git diff grep non-zero, process failure)" if ec['exit_code'] == 1 else (
            "Misuse of shell built-ins or CLI syntax" if ec['exit_code'] == 2 else (
                "Command not found (`PATH` issues, uninstalled binary)" if ec['exit_code'] == 127 else (
                    "SSH / remote node connection failure or remote host unreachable" if ec['exit_code'] == 255 else (
                        "Invalid git argument / fatal repository error" if ec['exit_code'] == 128 else f"Process exit code {ec['exit_code']}"
                    )
                )
            )
        )
        md += f"- **Exit Code {ec['exit_code']}** ({ec['count']:,} occurrences): {desc}\n"

    ec1 = audit.get("exit_code_1_breakdown", {})
    if ec1:
        md += f"""
##### Forensic Sub-Distribution of Exit Code 1 ({ec1.get('total', 0):,} Total Occurrences)
| Failure Sub-Category | Occurrences | % of Exit Code 1 | Root Cause & Mitigation |
| :--- | :--- | :--- | :--- |
| **Grep / Diff Pattern No-Match** | {ec1.get('grep_diff_benign', 0):,} | {ec1.get('grep_diff_pct', 0)}% | Benign zero-match exits; mitigated by PreToolUse `\\|\\| [ $? -eq 1 ]` sanitization |
| **Python Syntax Errors** | {ec1.get('python_syntax_total', 0):,} | {ec1.get('python_syntax_pct', 0)}% | Parsing failures in `python3 -c` (includes {ec1.get('fstring_backslash', 0)} f-string backslash errors); mitigated by CPython >= 3.12 |
| **Python Runtime Tracebacks** | {ec1.get('python_traceback', 0):,} | {ec1.get('python_traceback_pct', 0)}% | Unhandled exceptions and missing library imports in inline scripts |
| **Other CLI / Build Failures** | {ec1.get('other_cli', 0):,} | {ec1.get('other_cli_pct', 0)}% | Test suite failures, compile errors, linter violations |
"""

    md += f"""
#### Tool Thrashing & Loop Traps ({sum(l['loop_calls'] for l in loops):,} Occurrences)
Redundant consecutive tool calls on identical arguments:
"""
    for l in loops[:6]:
        md += f"- **`{l['tool']}`**: **{l['loop_calls']:,} repeated calls**.\n"

    md += """
#### The Context Cliff: Trajectory Length vs Error Escalation
"""
    for d in depth_stats:
        md += f"- **{d['bucket']}** ({d['sessions']:,} sessions): Avg Errors = **{d['avg_errors']}**, Avg Operator Interventions = **{d['avg_interventions']}**\n"

    md += f"""
> [!CAUTION]
> **Measured 200+ Step Scaling**: At `200+ steps` ({b_high.get('sessions', 0):,} sessions), average errors reach **{b_high.get('avg_errors', 0)}/session** and operator interventions reach **{b_high.get('avg_interventions', 0)}/session** (compared to **{b_low.get('avg_errors', 0)}** errors and **{b_low.get('avg_interventions', 0)}** interventions in `1-10 steps`).

---

### 🟡 3. OPERATOR GUIDANCE (Human-in-the-Loop Interventions)

Across **{overview['total_sessions']:,} sessions**, human operators intervened **{total_int:,} times**:
"""
    for it in interventions:
        pct = round(it['count'] * 100.0 / total_int, 1) if total_int else 0.0
        md += f"- **`{it['type']}`**: **{it['count']:,}** occurrences ({pct}%)\n"

    md += """
---

### 🚀 4. HARNESS OPPORTUNITIES (Actionable Safeguards in `agyis-harness`)

1. **`PreToolUse` Anti-Loop Guard**: Intercept consecutive identical `read_file` or `run_command` thrashing before context is wasted.
2. **`PreToolUse` Pre-flight Command Validator**: Normalize benign non-zero probes (`grep`/`diff`) and guard missing toolchain binaries.
3. **`PostToolUse` Output Truncator**: Compact tool outputs exceeding 2KB (`run_command`) / 32KB (`read_file`) while preserving full failure diagnostics.
4. **Remote Execution Wrapper (`agyis remote`)**: ControlMaster SSH multiplexing and login-shell promotion.
"""

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(md, encoding="utf-8")
    print(f"[✓] Generated empirical audit report: {output_path}")


def main(argv: Optional[List[str]] = None) -> None:
    parser = argparse.ArgumentParser(description="Classify failure modes and generate audit report.")
    parser.add_argument("--db", default="data/telemetry.db", help="Path to SQLite database")
    parser.add_argument("--output", "-o", default="data/reports/workstation-audit-report.md", help="Path to output markdown report")
    parser.add_argument("--json-out", default="data/classified_failures.json", help="Path to output structured JSON")
    args = parser.parse_args(argv)

    db_path = Path(args.db)
    if not db_path.exists():
        print(f"Error: Database {db_path} does not exist. Run extract_transcripts.py first.")
        return

    audit = run_classification_audit(db_path)

    # Save JSON
    json_path = Path(args.json_out)
    json_path.parent.mkdir(parents=True, exist_ok=True)
    json_path.write_text(json.dumps(audit, indent=2), encoding="utf-8")

    # Save Markdown Report
    md_path = Path(args.output)
    generate_markdown_report(audit, md_path)

    print("=" * 70)
    print(" 🎯 AUDIT REPORT GENERATED SUCCESSFULLY")
    print("=" * 70)
    print(f"Total Sessions Audited:        {audit['overview']['total_sessions']}")
    print(f"Total Steps Audited:           {audit['overview']['total_steps']:,}")
    print(f"Total Tool Calls:              {audit['overview']['total_tool_calls']:,}")
    print(f"Top Failing Tool:              {audit['tool_stats'][0]['tool']} ({audit['tool_stats'][0]['fails']} failures)")
    print(f"Markdown Report:               {md_path}")
    print(f"Structured JSON:               {json_path}")
    print("=" * 70)


if __name__ == "__main__":
    main()
