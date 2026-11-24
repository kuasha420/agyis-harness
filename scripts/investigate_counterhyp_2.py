#!/usr/bin/env python3
"""Compare clean vs error cohorts for long sessions (>200 steps)."""

from __future__ import annotations

import argparse
from pathlib import Path
import sqlite3
import sys

REPO_ROOT = Path(__file__).resolve().parent.parent


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Analyze long-session cohorts in telemetry.db.")
    parser.add_argument(
        "--db",
        default=str(REPO_ROOT / "data" / "telemetry.db"),
        help="Path to telemetry SQLite database.",
    )
    parser.add_argument("--since", default="2026-10-02", help="Start ISO date filter.")
    parser.add_argument("--min-steps", type=int, default=200, help="Minimum total_steps threshold.")
    return parser.parse_args(argv)


def analyze_cohort(c: sqlite3.Cursor, cohort: list[tuple], name: str) -> None:
    sids = [s[0] for s in cohort]
    if not sids:
        print(f"Cohort {name} is empty")
        return
    placeholders = ",".join(["?"] * len(sids))

    c.execute(
        f"""
        SELECT count(*), count(distinct session_id)
        FROM tool_calls
        WHERE session_id IN ({placeholders})
          AND tool_name = 'manage_task'
          AND arguments_json LIKE '%"status"%'
        """,
        sids,
    )
    status_polls, status_sess = c.fetchone()

    c.execute(
        f"""
        SELECT count(*), count(distinct session_id)
        FROM tool_calls
        WHERE session_id IN ({placeholders})
          AND (
            (tool_name = 'read_file' AND (target_path LIKE '%/tasks/task-%.log' OR arguments_json LIKE '%/tasks/task-%.log'))
            OR (tool_name = 'run_command' AND (command_line LIKE '%/tasks/task-%.log' OR command_line LIKE '%tasks/task-%.log'))
          )
        """,
        sids,
    )
    log_reads, log_sess = c.fetchone()

    c.execute(
        f"""
        SELECT count(*), count(distinct session_id)
        FROM tool_calls
        WHERE session_id IN ({placeholders})
          AND error_snippet LIKE '%denied by pre-tool hook%'
        """,
        sids,
    )
    denials, denial_sess = c.fetchone()

    c.execute(
        f"""
        SELECT count(*), count(distinct session_id)
        FROM tool_calls
        WHERE session_id IN ({placeholders})
          AND tool_name = 'edit_file'
          AND status IN ('ERROR', 'FAILED')
        """,
        sids,
    )
    edit_fails, edit_sess = c.fetchone()

    tot_tools = sum(s[2] for s in cohort)
    tot_errors = sum(s[3] for s in cohort)
    tot_steps = sum(s[1] for s in cohort)
    avg_steps = tot_steps / len(cohort)
    avg_interv = sum(s[4] for s in cohort) / len(cohort)
    avg_dur = sum(s[6] for s in cohort) / len(cohort) / 60.0

    print(f"\n--- Cohort: {name} (N={len(cohort)}) ---")
    print(f"Avg steps: {avg_steps:.1f} | Avg duration: {avg_dur:.1f}m | Avg interventions: {avg_interv:.2f}")
    print(f"Total tools: {tot_tools} | Total errors: {tot_errors}")
    print(f"Status polls: {status_polls} across {status_sess} sessions ({status_polls/len(cohort):.2f}/sess)")
    print(f"Task log reads: {log_reads} across {log_sess} sessions ({log_reads/len(cohort):.2f}/sess)")
    print(f"Anti-loop denials: {denials} across {denial_sess} sessions ({denials/len(cohort):.2f}/sess)")
    print(f"Edit failures: {edit_fails} across {edit_sess} sessions ({edit_fails/len(cohort):.2f}/sess)")


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    db_path = Path(args.db)
    if not db_path.is_file():
        print(f"Database not found: {db_path}", file=sys.stderr)
        return 1

    conn = sqlite3.connect(db_path)
    try:
        c = conn.cursor()
        c.execute(
            """
            SELECT
                session_id, total_steps, tool_call_count, tool_error_count,
                intervention_count, has_errors, duration_seconds, workspace_path
            FROM sessions
            WHERE start_time >= ? AND total_steps > ?
            ORDER BY total_steps DESC
            """,
            (args.since, args.min_steps),
        )
        all_long = c.fetchall()
        print(f"Total sessions > {args.min_steps} steps: {len(all_long)}")
        if not all_long:
            return 0

        clean_long = [s for s in all_long if s[5] == 0]
        failed_long = [s for s in all_long if s[5] == 1]

        print(f"Clean sessions > {args.min_steps} steps (has_errors=0): {len(clean_long)} ({len(clean_long)/len(all_long)*100:.1f}%)")
        print(f"Failed sessions > {args.min_steps} steps (has_errors=1): {len(failed_long)} ({len(failed_long)/len(all_long)*100:.1f}%)")

        analyze_cohort(c, clean_long, f"Clean >{args.min_steps} Steps")
        analyze_cohort(c, failed_long, f"Failed >{args.min_steps} Steps")
    finally:
        conn.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
