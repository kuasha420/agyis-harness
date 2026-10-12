#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Arafat Zahan (@kuasha420)
# Corporate Stewardship & Infrastructure: Purrfect Software Limited (PSL)
# Governed by: ICARO-42/b Ordinance (Company-Supported Personal IP Framework)

"""
PSL Harness for Google Antigravity™
Operator Interventions & Trajectory Shift Summarizer

Analyzes human operator interventions stored in data/telemetry.db:
- Categorizes human-in-the-loop overrides
- Identifies recurrent correction patterns and drift keywords
- Correlates preceding tool failures with human rescue prompts
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import re
import sqlite3
from typing import Any, Dict, List


def summarize_interventions(db_path: Path) -> Dict[str, Any]:
    conn = sqlite3.connect(db_path)
    c = conn.cursor()

    # 1. Total counts by category
    c.execute("""
        SELECT intervention_type, COUNT(*) as cnt
        FROM user_interventions
        GROUP BY intervention_type
        ORDER BY cnt DESC
    """)
    type_counts = {row[0]: row[1] for row in c.fetchall()}

    # 2. Preceding tool failures
    c.execute("""
        SELECT preceding_tool_name, COUNT(*) as cnt
        FROM user_interventions
        WHERE preceding_tool_failed = 1
        GROUP BY preceding_tool_name
        ORDER BY cnt DESC
    """)
    preceding_failures = {row[0]: row[1] for row in c.fetchall() if row[0]}

    # 3. Steering patterns & keywords
    steering_clusters = {
        "drift_or_off_track": [],
        "stop_or_hold": [],
        "clarification_or_planning": [],
        "mesh_or_remote_node": [],
        "credential_or_auth": [],
        "reversion_or_undo": []
    }

    c.execute("""
        SELECT session_id, step_index, prompt_text, preceding_tool_name
        FROM user_interventions
        WHERE intervention_type IN ('STEERING', 'ERROR_RECOVERY')
    """)
    for session_id, step_idx, prompt, prev_tool in c.fetchall():
        p_lower = prompt.lower()
        entry = {
            "session_id": session_id,
            "step_index": step_idx,
            "prompt_snippet": prompt[:160].replace("\n", " "),
            "preceding_tool": prev_tool
        }
        if any(w in p_lower for w in ["drift", "off track", "wrong plan", "initial plan", "not what i asked"]):
            steering_clusters["drift_or_off_track"].append(entry)
        elif any(w in p_lower for w in ["stop", "pause", "wait", "hold on", "don't do that"]):
            steering_clusters["stop_or_hold"].append(entry)
        elif any(w in p_lower for w in ["clarify", "plan", "spec", "design", "interview", "architecture"]):
            steering_clusters["clarification_or_planning"].append(entry)
        elif any(w in p_lower for w in ["mesh", "laptop", "deck", "steamdeck", "rog", "knot", "remote", "ssh"]):
            steering_clusters["mesh_or_remote_node"].append(entry)
        elif any(w in p_lower for w in ["password", "token", "key", "secret", "auth", "login"]):
            steering_clusters["credential_or_auth"].append(entry)
        elif any(w in p_lower for w in ["undo", "revert", "wipe", "restore", "reset"]):
            steering_clusters["reversion_or_undo"].append(entry)

    # 4. Top multi-intervention sessions (high cognitive load on operator)
    c.execute("""
        SELECT session_id, COUNT(*) as interv_cnt, total_steps, model, SUBSTR(workspace_path, 1, 40)
        FROM user_interventions
        JOIN sessions USING (session_id)
        GROUP BY session_id
        ORDER BY interv_cnt DESC
        LIMIT 10
    """)
    fatigue_sessions = [
        {
            "session_id": row[0],
            "interventions": row[1],
            "total_steps": row[2],
            "model": row[3],
            "workspace": row[4]
        }
        for row in c.fetchall()
    ]

    conn.close()

    return {
        "total_interventions": sum(type_counts.values()),
        "breakdown_by_type": type_counts,
        "preceding_failed_tools": preceding_failures,
        "steering_cluster_counts": {k: len(v) for k, v in steering_clusters.items()},
        "sample_clusters": {k: v[:5] for k, v in steering_clusters.items()},
        "operator_fatigue_sessions": fatigue_sessions
    }


def main(argv: Optional[List[str]] = None) -> None:
    parser = argparse.ArgumentParser(description="Summarize user interventions and operator guidance.")
    parser.add_argument("--db", default="data/telemetry.db", help="Path to SQLite database")
    parser.add_argument("--output", "-o", default="data/operator_interventions_summary.json", help="Path to output JSON")
    args = parser.parse_args(argv)

    db_path = Path(args.db)
    if not db_path.exists():
        print(f"Error: Database {db_path} does not exist. Run extract_transcripts.py first.")
        return

    summary = summarize_interventions(db_path)

    out_file = Path(args.output)
    out_file.parent.mkdir(parents=True, exist_ok=True)
    out_file.write_text(json.dumps(summary, indent=2), encoding="utf-8")

    print("=" * 70)
    print(" 🧑‍💻 PSL HARNESS: OPERATOR INTERVENTION SUMMARY")
    print("=" * 70)
    print(f"Total Operator Interventions: {summary['total_interventions']}")
    print("-" * 70)
    print("Intervention Categories:")
    for itype, cnt in summary["breakdown_by_type"].items():
        pct = (cnt / summary["total_interventions"]) * 100
        print(f"  • {itype:20}: {cnt:4} ({pct:4.1f}%)")
    print("-" * 70)
    print("Preceding Tool Failures Leading to Operator Rescue:")
    for tool, cnt in summary["preceding_failed_tools"].items():
        print(f"  • {tool:20}: {cnt:4} rescues")
    print("-" * 70)
    print("Steering Triggers:")
    for cluster, cnt in summary["steering_cluster_counts"].items():
        print(f"  • {cluster:25}: {cnt:3} incidents")
    print("=" * 70)
    print(f"Detailed summary written to {out_file}")
    print("=" * 70)


if __name__ == "__main__":
    main()
