# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Arafat Zahan (@kuasha420)
# Corporate Stewardship & Infrastructure: Purrfect Software Limited (PSL)
# Governed by: ICARO-42/b Ordinance (Company-Supported Personal IP Framework)

"""
Telemetry laboratory CLI dispatcher (ADR-014).
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
DEFAULT_DB = REPO_ROOT / "data" / "telemetry.db"


def cmd_audit(args: argparse.Namespace) -> int:
    """Dispatches telemetry laboratory subcommands."""
    sub = getattr(args, "stage", None) or "all"

    if sub == "extract":
        from pipeline import extract_transcripts
        extra = []
        if getattr(args, "db", None):
            extra.extend(["--db", args.db])
        else:
            extra.extend(["--db", str(DEFAULT_DB)])
        if getattr(args, "backfill", False):
            extra.append("--backfill-volumes")
        if getattr(args, "conv_dir", None):
            extra.extend(["--conv-dir", args.conv_dir])
        extract_transcripts.main(extra)
    elif sub == "benchmark":
        from pipeline import benchmark_reasoning_tiers
        extra = []
        if getattr(args, "db", None):
            extra.extend(["--db", args.db])
        if getattr(args, "output_json", None):
            extra.extend(["--output-json", str(args.output_json)])
        if getattr(args, "output_report", None):
            extra.extend(["--output-report", str(args.output_report)])
        benchmark_reasoning_tiers.main(extra)
        return 0
    elif sub == "classify":
        from pipeline import classify_failures
        extra = []
        if getattr(args, "db", None):
            extra.extend(["--db", args.db])
        classify_failures.main(extra)
        return 0
    elif sub == "inventory":
        from pipeline import inventory_customizations
        inventory_customizations.main([])
        return 0
    elif sub == "dynamics":
        from pipeline import analyze_context_dynamics
        extra = []
        if getattr(args, "db", None):
            extra.extend(["--db", args.db])
        analyze_context_dynamics.main(extra)
        return 0
    elif sub == "traces":
        from pipeline import extract_cognitive_traces
        extra = []
        if getattr(args, "db", None):
            extra.extend(["--db", args.db])
        extract_cognitive_traces.main(extra)
        return 0
    elif sub == "interventions":
        from pipeline import summarize_interventions
        extra = []
        if getattr(args, "db", None):
            extra.extend(["--db", args.db])
        summarize_interventions.main(extra)
        return 0
    elif sub == "volume":
        from pipeline import analyze_volume_distributions
        return analyze_volume_distributions.main(args)
    elif sub == "deep":
        from pipeline import analyze_ultra_deep_sessions
        return analyze_ultra_deep_sessions.main(args)
    elif sub == "clusters":
        from pipeline import analyze_failure_clusters
        extra = []
        if getattr(args, "db", None):
            extra.extend(["--db", args.db])
        if getattr(args, "output_json", None):
            extra.extend(["--output-json", str(args.output_json)])
        if getattr(args, "output_report", None):
            extra.extend(["--output-report", str(args.output_report)])
        return analyze_failure_clusters.main(extra)
    elif sub == "all":
        print("▶ [1/4] Scanning Customization Inventory...")
        from pipeline import inventory_customizations
        inventory_customizations.main([])

        print("\n▶ [2/4] Harvesting Transcripts...")
        from pipeline import extract_transcripts
        extra = []
        if getattr(args, "db", None):
            extra.extend(["--db", args.db])
        extract_transcripts.main(extra)

        print("\n▶ [3/4] Classifying Failures & Workstation Metrics...")
        from pipeline import classify_failures
        classify_failures.main(extra)

        print("\n▶ [4/4] Summarizing Operator Interventions...")
        from pipeline import summarize_interventions
        summarize_interventions.main(extra)
    elif sub in ("session", "live"):
        from pipeline import analyze_live_session
        session_id = getattr(args, "session_id", None)
        save_db = getattr(args, "save_db", False)
        out_path = getattr(args, "out", None)
        as_json = getattr(args, "json", False)

        if session_id:
            s_dir = Path.home() / ".gemini" / "antigravity" / "brain" / session_id
        else:
            s_dir = analyze_live_session.find_latest_session_dir()

        if not s_dir or not s_dir.exists():
            sys.stderr.write(f"Error: Session directory not found for {session_id or 'latest'}\n")
            return 1

        report = analyze_live_session.analyze_session(s_dir)

        if save_db:
            from pipeline import extract_transcripts
            import sqlite3
            from harness.telemetry import config
            from harness.telemetry.db import get_db_connection
            db_path = config.resolve_db_path(getattr(args, "db", None))
            conn = get_db_connection(db_path)
            extract_transcripts.ensure_sync_columns(conn)
            cur = conn.cursor()
            cur.executescript(extract_transcripts.SCHEMA_SQL)
            conn.commit()

            t_path = s_dir / ".system_generated" / "logs" / "transcript.jsonl"
            res = extract_transcripts.extract_session(t_path)
            if res:
                s_row, _, _, _ = res
                cur.execute("""
                    INSERT OR REPLACE INTO sessions (
                        session_id, start_time, end_time, duration_seconds, total_steps,
                        model, workspace_path, transcript_path, file_size_bytes, has_errors,
                        tool_call_count, tool_error_count, intervention_count
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    s_row["session_id"], s_row["start_time"], s_row["end_time"],
                    s_row["duration_seconds"], s_row["total_steps"], s_row["model"],
                    s_row["workspace_path"], s_row["transcript_path"], s_row["file_size_bytes"],
                    s_row["has_errors"], s_row["tool_call_count"], s_row["tool_error_count"],
                    s_row["intervention_count"]
                ))
                conn.commit()

            for sa in report["subagents"]:
                sub_p = s_dir.parent / sa["conversation_id"] / ".system_generated" / "logs" / "transcript.jsonl"
                sub_res = extract_transcripts.extract_session(sub_p)
                if sub_res:
                    s_row, _, _, _ = sub_res
                    cur.execute("""
                        INSERT OR REPLACE INTO sessions (
                            session_id, start_time, end_time, duration_seconds, total_steps,
                            model, workspace_path, transcript_path, file_size_bytes, has_errors,
                            tool_call_count, tool_error_count, intervention_count
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """, (
                        s_row["session_id"], s_row["start_time"], s_row["end_time"],
                        s_row["duration_seconds"], s_row["total_steps"], s_row["model"],
                        s_row["workspace_path"], s_row["transcript_path"], s_row["file_size_bytes"],
                        s_row["has_errors"], s_row["tool_call_count"], s_row["tool_error_count"],
                        s_row["intervention_count"]
                    ))
                    conn.commit()
            conn.close()
            if not as_json:
                print(f"✔ Synchronized session {report['session_id'][:8]} and {len(report['subagents'])} subagents into telemetry.db\n")

        if as_json:
            print(json.dumps(report, indent=2))
        else:
            analyze_live_session.print_report(report)

        if out_path:
            with open(out_path, "w", encoding="utf-8") as f:
                json.dump(report, f, indent=2)
            print(f"✔ Exported structured analysis to {out_path}")
        return 0
    else:
        sys.stderr.write(f"Error: Unknown audit stage '{sub}'.\n")
        return 1

    return 0
