#!/usr/bin/env python3
"""Inspect user prompts and harness tool calls for selected session IDs."""

from __future__ import annotations

import argparse
import os
from pathlib import Path
import sqlite3
import sys

REPO_ROOT = Path(__file__).resolve().parent.parent


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Inspect session conversation DB and telemetry tool calls.")
    parser.add_argument(
        "--db",
        default=str(REPO_ROOT / "data" / "telemetry.db"),
        help="Path to telemetry SQLite database.",
    )
    parser.add_argument(
        "--conversations-dir",
        default=os.environ.get(
            "AGYIS_CONVERSATIONS_DIR",
            str(Path.home() / ".gemini" / "antigravity" / "conversations"),
        ),
        help="Directory containing conversation SQLite files.",
    )
    parser.add_argument(
        "--session",
        action="append",
        dest="sessions",
        help="Session ID to inspect (repeatable; defaults to top sessions from telemetry.db).",
    )
    parser.add_argument("--limit", type=int, default=3, help="Max sessions to auto-select when --session is omitted.")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    db_path = Path(args.db)
    if not db_path.is_file():
        print(f"Database not found: {db_path}", file=sys.stderr)
        return 1

    conn_t = sqlite3.connect(db_path)
    try:
        ct = conn_t.cursor()
        if args.sessions:
            sessions = [(sid, sid) for sid in args.sessions]
        else:
            ct.execute(
                "SELECT COALESCE(workspace_path, 'unknown'), session_id FROM sessions ORDER BY total_steps DESC LIMIT ?",
                (args.limit,),
            )
            sessions = ct.fetchall()

        conv_dir = Path(args.conversations_dir)
        for name, sid in sessions:
            print("\n=======================================================")
            print(f"SESSION: {name} ({sid})")
            print("=======================================================")
            conv_path = conv_dir / f"{sid}.db"
            if conv_path.is_file():
                conn = sqlite3.connect(conv_path)
                try:
                    c = conn.cursor()
                    c.execute(
                        "SELECT idx, role, step_type, substr(content, 1, 500) FROM steps "
                        "WHERE role = 'user' OR step_type LIKE '%user%' ORDER BY idx"
                    )
                    rows = c.fetchall()
                    print(f"User steps count: {len(rows)}")
                    for r in rows:
                        print(f"--- Step {r[0]} | role: {r[1]} | type: {r[2]} ---")
                        print(r[3])
                except sqlite3.Error as exc:
                    print(f"Error reading conv db {conv_path}: {exc}", file=sys.stderr)
                finally:
                    conn.close()
            else:
                print(f"Conversation DB not found: {conv_path}")

            ct.execute(
                """
                SELECT step_index, tool_name, command_line, json_extract(arguments_json, '$.Cwd'), exit_code, status
                FROM tool_calls
                WHERE session_id = ? AND (
                    command_line LIKE '%harness%' OR
                    command_line LIKE '%agyis%' OR
                    command_line LIKE '%unittest%'
                )
                ORDER BY step_index
                """,
                (sid,),
            )
            t_rows = ct.fetchall()
            print(f"\nHarness-related tool calls ({len(t_rows)}):")
            for tr in t_rows:
                print(f"Step {tr[0]}: {tr[1]} | cmd: {tr[2]} | cwd: {tr[3]} | ec: {tr[4]}")
    finally:
        conn_t.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
