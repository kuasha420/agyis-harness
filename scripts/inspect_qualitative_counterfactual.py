#!/usr/bin/env python3
"""Print qualitative samples of subsequent tool calls after anti-loop denials."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sqlite3
import sys

REPO_ROOT = Path(__file__).resolve().parent.parent


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Inspect qualitative follow-up calls after anti-loop denials.")
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

        sample_indices = [0, 5, 15, 25, 35, 45, 55]
        for idx in sample_indices:
            if idx >= len(denials):
                continue
            sid, step, tool, cmd, args_json, err = denials[idx]
            parsed_args = json.loads(args_json) if args_json else {}
            target = cmd or parsed_args.get("Path") or parsed_args.get("AbsolutePath") or parsed_args.get("Action")
            print("\n=======================================================")
            print(f"CASE {idx}: Session {sid[:8]} Step {step} | Tool: {tool}")
            print(f"Denied Target: {target}")
            print(f"Error: {err[:120]}")
            print("Subsequent 3 calls:")

            c.execute(
                """
                SELECT step_index, tool_name, command_line, arguments_json, status
                FROM tool_calls
                WHERE session_id = ? AND step_index > ?
                ORDER BY step_index
                LIMIT 3
                """,
                (sid, step),
            )
            for r in c.fetchall():
                r_args = json.loads(r[3]) if r[3] else {}
                r_target = r[2] or r_args.get("Path") or r_args.get("AbsolutePath") or r_args.get("Action") or r_args.get("CommandLine")
                print(f"  Step {r[0]}: {r[1]} -> {str(r_target)[:80]} (status: {r[4]})")
    finally:
        conn.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
