#!/usr/bin/env python3
"""Measure counterfactual agent reactions following anti-loop denials."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sqlite3
import sys

REPO_ROOT = Path(__file__).resolve().parent.parent


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Analyze agent reactions after anti-loop denials.")
    parser.add_argument(
        "--db",
        default=str(REPO_ROOT / "data" / "telemetry.db"),
        help="Path to telemetry SQLite database.",
    )
    parser.add_argument("--since", default="2026-10-02", help="Start ISO date filter.")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    db_path = Path(args.db)
    if not db_path.is_file():
        print(f"Database not found: {db_path}", file=sys.stderr)
        return 1

    reactions = {
        "evasion_switch_tool": 0,
        "stopped_and_waited": 0,
        "retried_same_command": 0,
        "switched_strategy": 0,
        "user_intervened": 0,
    }

    conn = sqlite3.connect(db_path)
    try:
        c = conn.cursor()
        c.execute(
            """
            SELECT
                tc.session_id, tc.step_index, tc.tool_name, tc.command_line, tc.arguments_json, tc.error_snippet
            FROM tool_calls tc
            JOIN sessions s ON tc.session_id = s.session_id
            WHERE s.start_time >= ?
              AND tc.error_snippet LIKE '%denied by pre-tool hook%'
            ORDER BY s.start_time, tc.session_id, tc.step_index
            """,
            (args.since,),
        )
        denials = c.fetchall()

        for sid, step, tool, cmd, args_json, _err in denials:
            c.execute(
                """
                SELECT step_index, tool_name, command_line, arguments_json, status, error_snippet
                FROM tool_calls
                WHERE session_id = ? AND step_index > ?
                ORDER BY step_index
                LIMIT 3
                """,
                (sid, step),
            )
            next_calls = c.fetchall()

            c.execute(
                """
                SELECT step_index, prompt_text
                FROM user_interventions
                WHERE session_id = ? AND step_index BETWEEN ? AND ?
                """,
                (sid, step, step + 5),
            )
            interv = c.fetchall()

            if interv:
                reactions["user_intervened"] += 1
            elif not next_calls:
                reactions["stopped_and_waited"] += 1
            else:
                first_next = next_calls[0]
                n_tool = first_next[1]
                n_cmd = first_next[2] or ""
                n_args = json.loads(first_next[3]) if first_next[3] else {}
                prev_args = json.loads(args_json or "{}")

                prev_path = prev_args.get("Path") or prev_args.get("AbsolutePath")
                next_path = n_args.get("Path") or n_args.get("AbsolutePath") or ""

                if tool == "read_file" and n_tool == "run_command" and ("cat" in n_cmd or "stat" in n_cmd or "head" in n_cmd):
                    reactions["evasion_switch_tool"] += 1
                elif tool == "manage_task" and n_tool in ("read_file", "run_command") and "task" in (n_cmd or next_path):
                    reactions["evasion_switch_tool"] += 1
                elif n_tool == tool and (n_cmd == cmd or (prev_path and next_path == prev_path)):
                    reactions["retried_same_command"] += 1
                else:
                    reactions["switched_strategy"] += 1
    finally:
        conn.close()

    print("=== COUNTERFACTUAL AGENT REACTIONS TO ANTI-LOOP DENIALS ===")
    total = len(denials) or 1
    for r, cnt in reactions.items():
        print(f"{r:<25}: {cnt} ({cnt / total * 100:.1f}%)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
