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
import os
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
    elif sub == "artifacts":
        from pipeline import audit_artifacts
        extra = []
        if getattr(args, "output_json", None):
            extra.extend(["--json-out", str(args.output_json)])
        if getattr(args, "output_report", None):
            extra.extend(["--output", str(args.output_report)])
        audit_artifacts.main(extra)
        return 0
    elif sub in ("configs", "project_configs", "project-configs"):
        from pipeline import audit_project_configs
        extra = []
        if getattr(args, "db", None):
            extra.extend(["--db", args.db])
        if getattr(args, "output_json", None):
            extra.extend(["--json-out", str(args.output_json)])
        if getattr(args, "output_report", None):
            extra.extend(["--output", str(args.output_report)])
        audit_project_configs.main(extra)
        return 0
    elif sub == "all":
        extra_db = ["--db", args.db] if getattr(args, "db", None) else ["--db", str(DEFAULT_DB)]

        if getattr(args, "backfill", False) or getattr(args, "conv_dir", None):
            print("▶ [Pre] Harvesting Transcripts & Volume Backfill...")
            from pipeline import extract_transcripts
            extract_extra = list(extra_db)
            if getattr(args, "backfill", False):
                extract_extra.append("--backfill-volumes")
            if getattr(args, "conv_dir", None):
                extract_extra.extend(["--conv-dir", args.conv_dir])
            extract_transcripts.main(extract_extra)

        print("▶ [1/11] Scanning Customization & Extension Inventory...")
        from pipeline import inventory_customizations
        inventory_customizations.main([])

        print("\n▶ [2/11] Classifying Failures & Workstation Metrics...")
        from pipeline import classify_failures
        classify_failures.main(extra_db)

        print("\n▶ [3/11] Summarizing Operator Interventions...")
        from pipeline import summarize_interventions
        summarize_interventions.main(extra_db)

        print("\n▶ [4/11] Analyzing Context Cliff & Token Dynamics...")
        from pipeline import analyze_context_dynamics
        analyze_context_dynamics.main(extra_db)

        print("\n▶ [5/11] Analyzing Tool & Command Character Volume Distributions...")
        from pipeline import analyze_volume_distributions
        vol_args = argparse.Namespace(
            db=getattr(args, "db", None) or str(DEFAULT_DB),
            backfill=getattr(args, "backfill", False),
            output_json=None,
            output_report=None,
            quiet=getattr(args, "quiet", False),
        )
        analyze_volume_distributions.main(vol_args)

        print("\n▶ [6/11] Analyzing Ultra-Deep 1,000+ Step Titan Sessions...")
        from pipeline import analyze_ultra_deep_sessions
        deep_args = argparse.Namespace(
            db=getattr(args, "db", None) or str(DEFAULT_DB),
            output_json=None,
            output_report=None,
            quiet=getattr(args, "quiet", False),
        )
        analyze_ultra_deep_sessions.main(deep_args)

        print("\n▶ [7/11] Analyzing Model Failure Clusters & Hotspots...")
        from pipeline import analyze_failure_clusters
        analyze_failure_clusters.main(extra_db)

        print("\n▶ [8/11] Benchmarking Reasoning Tiers...")
        from pipeline import benchmark_reasoning_tiers
        benchmark_reasoning_tiers.main(extra_db)

        print("\n▶ [9/11] Extracting Cognitive & Chain-of-Thought Traces...")
        from pipeline import extract_cognitive_traces
        extract_cognitive_traces.main(extra_db)

        print("\n▶ [10/11] Auditing Artifacts & Plan-Execution Drift...")
        from pipeline import audit_artifacts
        audit_artifacts.main([])

        print("\n▶ [11/11] Auditing Project Rules & Skills Ecosystem...")
        from pipeline import audit_project_configs
        audit_project_configs.main(extra_db)

        print("\n" + "=" * 75)
        print(" ✔ COMPLETE 360-DEGREE TELEMETRY PIPELINE EXECUTION FINISHED")
        print("=" * 75)
        return 0
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
    elif sub == "prune":
        from harness.telemetry.db import prune_historical_tool_arguments
        raw_db = getattr(args, "db", None)
        db_path = Path(raw_db) if raw_db else DEFAULT_DB
        days = getattr(args, "days", 90)
        dry_run = getattr(args, "dry_run", False)
        as_json = getattr(args, "json", False)

        if not db_path.exists():
            sys.stderr.write(f"Error: Database file not found at {db_path}\n")
            return 1

        result = prune_historical_tool_arguments(db_path, days=days, dry_run=dry_run)
        if as_json:
            print(json.dumps(result, indent=2))
        else:
            print_prune_summary(result, db_path)
        return 0
    elif sub == "certify":
        from harness.subagents.verdict import generate_audit_verdict
        import re
        import subprocess
        import time

        cwd = Path(getattr(args, "workspace", None) or Path.cwd()).resolve()
        task_id = getattr(args, "task_id", "DEFAULT") or "DEFAULT"
        verdict_str = getattr(args, "verdict", "VICTORY CONFIRMED") or "VICTORY CONFIRMED"
        skip_tests = getattr(args, "skip_tests", False)
        as_json = getattr(args, "json", False)

        test_suite_result = {
            "command": "./agyis test",
            "exit_code": 0,
            "total_tests": 0,
            "passed_tests": 0,
            "failed_tests": 0,
            "benchmark_latency_s": 0.0,
        }

        if not skip_tests:
            start_t = time.perf_counter()
            test_cmd = [sys.executable, "-m", "unittest", "discover", "-s", "tests"]
            proc = subprocess.run(test_cmd, capture_output=True, text=True, cwd=str(cwd))
            elapsed = time.perf_counter() - start_t
            test_suite_result["command"] = "./agyis test"
            test_suite_result["exit_code"] = proc.returncode
            test_suite_result["benchmark_latency_s"] = round(elapsed, 4)

            combined_out = proc.stderr + "\n" + proc.stdout
            m = re.search(r"Ran (\d+) tests", combined_out)
            total = int(m.group(1)) if m else 0
            test_suite_result["total_tests"] = total

            if proc.returncode == 0:
                test_suite_result["passed_tests"] = total
                test_suite_result["failed_tests"] = 0
            else:
                mf = re.search(r"failures=(\d+)", combined_out)
                me = re.search(r"errors=(\d+)", combined_out)
                f_count = int(mf.group(1)) if mf else 0
                e_count = int(me.group(1)) if me else 0
                fail_total = f_count + e_count
                if fail_total == 0:
                    fail_total = 1
                test_suite_result["failed_tests"] = fail_total
                test_suite_result["passed_tests"] = max(0, total - fail_total)

        # Doctor audit
        doctor_result = {"ok_count": 0, "missing_count": 0, "outdated_count": 0}
        try:
            from harness.runtime.doctor import audit_environment
            doc_res = audit_environment(workspace_root=cwd)
            doc_summary = doc_res.get("summary", {})
            doctor_result = {
                "ok_count": doc_summary.get("ok", 0),
                "missing_count": doc_summary.get("missing", 0),
                "outdated_count": doc_summary.get("outdated", 0),
            }
        except Exception:
            pass

        verdict_obj = generate_audit_verdict(
            workspace_dir=cwd,
            task_id=task_id,
            verdict=verdict_str,
            test_suite_result=test_suite_result,
            doctor_result=doctor_result,
            auditor_role="agyis_auditor",
        )

        if as_json:
            print(json.dumps(verdict_obj.to_dict(), indent=2))
        else:
            print("=" * 70)
            print(f"🛡️  Agyis Victory Auditor Certification ({verdict_obj.protocol_version})")
            print("=" * 70)
            print(f"Task ID:        {verdict_obj.task_id}")
            print(f"Verdict:        {verdict_obj.verdict}")
            print(f"Auditor:        {verdict_obj.auditor_role}")
            print(f"Timestamp:      {verdict_obj.timestamp}")
            print(f"Artifact:       {verdict_obj.path}")
            print("-" * 70)
            print(
                f"Test Suite:     {test_suite_result['passed_tests']}/{test_suite_result['total_tests']} passed "
                f"(latency: {test_suite_result['benchmark_latency_s']}s, exit code: {test_suite_result['exit_code']})"
            )
            print(
                f"Doctor Audit:   {doctor_result['ok_count']} ok, "
                f"{doctor_result['missing_count']} missing, {doctor_result['outdated_count']} outdated"
            )
            print("=" * 70)

        return 0 if (verdict_obj.verdict.upper() in ("VICTORY CONFIRMED", "PASS") and test_suite_result["exit_code"] == 0) else 1

    elif sub == "verdict":
        from harness.subagents.verdict import validate_audit_verdict
        cwd = Path(getattr(args, "workspace", None) or Path.cwd()).resolve()
        as_json = getattr(args, "json", False)
        allow_synth = bool(os.environ.get("AGYIS_SYNTHETIC_TEST") == "1")

        valid, reason, verdict_obj = validate_audit_verdict(
            workspace_dir=cwd,
            allow_synthetic=allow_synth,
        )

        if as_json:
            out = {
                "valid": valid,
                "reason": reason,
                "verdict": verdict_obj.to_dict() if verdict_obj else None,
            }
            print(json.dumps(out, indent=2))
        else:
            print("=" * 70)
            print("🛡️  Agyis Out-of-Band Audit Verdict Status")
            print("=" * 70)
            if valid and verdict_obj:
                print("Status:         CLEARANCE GRANTED (Valid Gate 2 Clearance)")
                print(f"Task ID:        {verdict_obj.task_id}")
                print(f"Verdict:        {verdict_obj.verdict}")
                print(f"Auditor:        {verdict_obj.auditor_role}")
                print(f"Timestamp:      {verdict_obj.timestamp}")
                print(f"Artifact:       {verdict_obj.path}")
            else:
                print("Status:         CLEARANCE BLOCKED")
                print(f"Reason:         {reason}")
                if verdict_obj:
                    print(f"Verdict:        {verdict_obj.verdict}")
                    print(f"Artifact:       {verdict_obj.path}")
            print("=" * 70)

        return 0 if valid else 1
    else:
        sys.stderr.write(f"Error: Unknown audit stage '{sub}'.\n")
        return 1

    return 0


def print_prune_summary(result: dict, db_path: Path) -> None:
    """Renders human-readable summary of database pruning and compaction."""
    mode_str = "DRY RUN (no database modifications)" if result["dry_run"] else "ACTIVE PRUNING"
    vacuum_str = (
        "Completed successfully"
        if result["vacuum_executed"]
        else ("Skipped (dry-run)" if result["dry_run"] else "Not required (0 rows pruned)")
    )

    def format_bytes(n: int) -> str:
        if n >= 1024 * 1024 * 1024:
            return f"{n / (1024**3):.2f} GB"
        if n >= 1024 * 1024:
            return f"{n / (1024**2):.2f} MB"
        if n >= 1024:
            return f"{n / 1024:.2f} KB"
        return f"{n} bytes"

    print("=" * 70)
    print("✂ PSL Telemetry Compaction & Argument Pruning Policy (Issue #56)")
    print("=" * 70)
    print(f"Database:        {db_path}")
    print(f"Cutoff:          {result['days']} days (sessions completed before {result['cutoff_iso']})")
    print(f"Mode:            {mode_str}")
    print("-" * 70)
    print(f"Sessions:        {result['sessions_affected']:,} eligible sessions")
    print(f"Rows Affected:   {result['rows_affected']:,} tool_calls rows")
    print(f"Bytes Pruned:    {format_bytes(result['bytes_pruned'])} ({result['bytes_pruned']:,} raw string bytes)")
    if result.get("size_before_bytes", 0) > 0:
        before_str = format_bytes(result["size_before_bytes"])
        after_str = format_bytes(result["size_after_bytes"])
        reclaimed_str = format_bytes(result["disk_bytes_reclaimed"])
        print(f"Database Size:   {before_str} -> {after_str} (reclaimed: {reclaimed_str})")
    print(f"Vacuum:          {vacuum_str}")
    print("=" * 70)

