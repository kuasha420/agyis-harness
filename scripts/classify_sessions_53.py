#!/usr/bin/env python3
"""Classify sessions containing external harness CLI invocations in telemetry.db."""

from __future__ import annotations

import argparse
from pathlib import Path
import sqlite3
import sys

REPO_ROOT = Path(__file__).resolve().parent.parent


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Classify external harness invocations in telemetry.db.")
    parser.add_argument(
        "--db",
        default=str(REPO_ROOT / "data" / "telemetry.db"),
        help="Path to telemetry SQLite database.",
    )
    parser.add_argument("--since", default="2026-10-02", help="Start ISO date filter.")
    parser.add_argument(
        "--exclude-workspace",
        default="agyis-harness",
        help="Workspace substring to exclude as self-repository invocations.",
    )
    return parser.parse_args(argv)


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
            SELECT DISTINCT s.session_id, s.start_time, s.workspace_path, s.total_steps
            FROM tool_calls tc
            JOIN sessions s ON tc.session_id = s.session_id
            WHERE tc.tool_name = 'run_command'
              AND s.start_time >= ?
              AND (
                  tc.command_line LIKE '%harness.cli%'
                  OR tc.command_line LIKE '%agyis test%'
                  OR tc.command_line LIKE '%./agyis test%'
                  OR tc.command_line LIKE '%agyis doctor%'
                  OR tc.command_line LIKE '%./agyis doctor%'
                  OR tc.command_line LIKE '%python3 -m unittest discover -s tests -v%'
                  OR tc.command_line LIKE '%python3 -m harness%'
              )
              AND COALESCE(json_extract(tc.arguments_json, '$.Cwd'), '') NOT LIKE ?
            ORDER BY s.start_time
            """,
            (args.since, f"%{args.exclude_workspace}%"),
        )
        sessions = c.fetchall()

        fleet_onboarding_sessions = []
        user_commanded_governance = []
        unprompted_invariant_leaks = []

        for sid, start, _ws, _steps in sessions:
            c.execute(
                "SELECT prompt_text FROM user_interventions WHERE session_id = ? ORDER BY step_index",
                (sid,),
            )
            prompts = c.fetchall()
            all_prompts_text = " ".join(p[0] for p in prompts if p[0]).lower()

            c.execute(
                """
                SELECT step_index, command_line, json_extract(arguments_json, '$.Cwd')
                FROM tool_calls
                WHERE session_id = ? AND (
                    command_line LIKE '%harness.cli%'
                    OR command_line LIKE '%agyis test%'
                    OR command_line LIKE '%./agyis test%'
                    OR command_line LIKE '%agyis doctor%'
                    OR command_line LIKE '%./agyis doctor%'
                    OR command_line LIKE '%python3 -m unittest discover -s tests -v%'
                    OR command_line LIKE '%python3 -m harness%'
                )
                  AND COALESCE(json_extract(arguments_json, '$.Cwd'), '') NOT LIKE ?
                """,
                (sid, f"%{args.exclude_workspace}%"),
            )
            calls = c.fetchall()
            cwds = {cl[2] for cl in calls if cl[2]}

            is_fleet = (
                len(cwds) > 1
                or "onboard" in all_prompts_text
                or "fleet" in all_prompts_text
                or "wave 1" in all_prompts_text
            )
            is_user_governed = (
                "agyis" in all_prompts_text
                or "doctor" in all_prompts_text
                or "harmonize" in all_prompts_text
            )

            entry = (sid, start, len(cwds), len(calls), sorted(cwds)[:3])
            if is_fleet:
                fleet_onboarding_sessions.append(entry)
            elif is_user_governed:
                user_commanded_governance.append(entry)
            else:
                unprompted_invariant_leaks.append(entry)
    finally:
        conn.close()

    print(f"Fleet Onboarding Sessions: {len(fleet_onboarding_sessions)}")
    print(f"User Commanded Governance Sessions: {len(user_commanded_governance)}")
    print(f"Unprompted Invariant Leak Sessions: {len(unprompted_invariant_leaks)}")

    print("\n--- SAMPLE UNPROMPTED LEAK SESSIONS ---")
    for s in unprompted_invariant_leaks[:10]:
        print(f"ID: {s[0][:8]} | Date: {s[1][:10]} | Calls: {s[3]} | CWDs: {s[4]}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
