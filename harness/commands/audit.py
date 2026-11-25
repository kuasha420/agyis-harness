# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Arafat Zahan (@kuasha420)
# Corporate Stewardship & Infrastructure: Purrfect Software Limited (PSL)
# Governed by: ICARO-42/b Ordinance (Company-Supported Personal IP Framework)

"""
Telemetry laboratory CLI dispatcher (ADR-014).
"""

from __future__ import annotations

import argparse
import importlib
import json
import os
from pathlib import Path
import sys
from typing import Any, List, Optional, Tuple

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
DEFAULT_DB = REPO_ROOT / "data" / "telemetry.db"


def _import_pipeline_module(module_name: str, stage: str) -> Optional[Any]:
    """Dynamically imports a `pipeline.*` stage module without static ADR-014 coupling."""
    try:
        return importlib.import_module(f"pipeline.{module_name}")
    except ModuleNotFoundError as exc:
        if exc.name == "pipeline" or (exc.name or "").startswith("pipeline."):
            sys.stderr.write(
                f"Error: Telemetry stage '{stage}' requires the 'pipeline' package from an "
                "agyis-harness source checkout (not included in wheel distributions). "
                "Run from a source checkout or use portable stages: aff, certify, verdict, prune, db-integrity.\n"
            )
            return None
        raise


def _run_pipeline_stage(module_name: str, arg: Any, stage: str) -> int:
    """Imports and runs a pipeline stage `main()`, preserving non-zero exit codes."""
    mod = _import_pipeline_module(module_name, stage)
    if mod is None:
        return 1
    try:
        rc = mod.main(arg)
    except SystemExit as exc:
        code = exc.code
        if code is None:
            return 0
        return int(code) if isinstance(code, int) else 1
    if isinstance(rc, bool):
        return 0 if rc else 1
    if isinstance(rc, int):
        return rc
    return 0


def cmd_audit(args: argparse.Namespace) -> int:
    """Dispatches telemetry laboratory subcommands."""
    sub = getattr(args, "stage", None) or "all"

    if sub == "extract":
        extra: List[str] = []
        if getattr(args, "db", None):
            extra.extend(["--db", args.db])
        else:
            extra.extend(["--db", str(DEFAULT_DB)])
        if getattr(args, "backfill", False):
            extra.append("--backfill-volumes")
        if getattr(args, "conv_dir", None):
            extra.extend(["--conv-dir", args.conv_dir])
        return _run_pipeline_stage("extract_transcripts", extra, sub)
    elif sub == "benchmark":
        extra = []
        if getattr(args, "db", None):
            extra.extend(["--db", args.db])
        if getattr(args, "output_json", None):
            extra.extend(["--output-json", str(args.output_json)])
        if getattr(args, "output_report", None):
            extra.extend(["--output-report", str(args.output_report)])
        return _run_pipeline_stage("benchmark_reasoning_tiers", extra, sub)
    elif sub == "classify":
        extra = []
        if getattr(args, "db", None):
            extra.extend(["--db", args.db])
        return _run_pipeline_stage("classify_failures", extra, sub)
    elif sub == "inventory":
        return _run_pipeline_stage("inventory_customizations", [], sub)
    elif sub == "dynamics":
        extra = []
        if getattr(args, "db", None):
            extra.extend(["--db", args.db])
        return _run_pipeline_stage("analyze_context_dynamics", extra, sub)
    elif sub == "traces":
        extra = []
        if getattr(args, "db", None):
            extra.extend(["--db", args.db])
        return _run_pipeline_stage("extract_cognitive_traces", extra, sub)
    elif sub == "interventions":
        extra = []
        if getattr(args, "db", None):
            extra.extend(["--db", args.db])
        return _run_pipeline_stage("summarize_interventions", extra, sub)
    elif sub == "volume":
        return _run_pipeline_stage("analyze_volume_distributions", args, sub)
    elif sub == "deep":
        return _run_pipeline_stage("analyze_ultra_deep_sessions", args, sub)
    elif sub == "clusters":
        extra = []
        if getattr(args, "db", None):
            extra.extend(["--db", args.db])
        if getattr(args, "output_json", None):
            extra.extend(["--output-json", str(args.output_json)])
        if getattr(args, "output_report", None):
            extra.extend(["--output-report", str(args.output_report)])
        return _run_pipeline_stage("analyze_failure_clusters", extra, sub)
    elif sub == "artifacts":
        extra = []
        if getattr(args, "output_json", None):
            extra.extend(["--json-out", str(args.output_json)])
        if getattr(args, "output_report", None):
            extra.extend(["--output", str(args.output_report)])
        return _run_pipeline_stage("audit_artifacts", extra, sub)
    elif sub in ("configs", "project_configs", "project-configs"):
        extra = []
        if getattr(args, "db", None):
            extra.extend(["--db", args.db])
        if getattr(args, "output_json", None):
            extra.extend(["--json-out", str(args.output_json)])
        if getattr(args, "output_report", None):
            extra.extend(["--output", str(args.output_report)])
        return _run_pipeline_stage("audit_project_configs", extra, sub)
    elif sub == "all":
        extra_db = ["--db", args.db] if getattr(args, "db", None) else ["--db", str(DEFAULT_DB)]
        if _import_pipeline_module("inventory_customizations", "all") is None:
            return 1

        failed_stages: List[Tuple[str, int]] = []

        if getattr(args, "backfill", False) or getattr(args, "conv_dir", None):
            print("▶ [Pre] Harvesting Transcripts & Volume Backfill...")
            extract_extra = list(extra_db)
            if getattr(args, "backfill", False):
                extract_extra.append("--backfill-volumes")
            if getattr(args, "conv_dir", None):
                extract_extra.extend(["--conv-dir", args.conv_dir])
            rc = _run_pipeline_stage("extract_transcripts", extract_extra, "extract")
            if rc != 0:
                failed_stages.append(("extract", rc))

        vol_args = argparse.Namespace(
            db=getattr(args, "db", None) or str(DEFAULT_DB),
            backfill=getattr(args, "backfill", False),
            output_json=None,
            output_report=None,
            quiet=getattr(args, "quiet", False),
        )
        deep_args = argparse.Namespace(
            db=getattr(args, "db", None) or str(DEFAULT_DB),
            output_json=None,
            output_report=None,
            quiet=getattr(args, "quiet", False),
        )
        stages: List[Tuple[str, str, str, Any]] = [
            ("inventory", "\n▶ [1/11] Scanning Customization & Extension Inventory...", "inventory_customizations", []),
            ("classify", "\n▶ [2/11] Classifying Failures & Workstation Metrics...", "classify_failures", extra_db),
            ("interventions", "\n▶ [3/11] Summarizing Operator Interventions...", "summarize_interventions", extra_db),
            ("dynamics", "\n▶ [4/11] Analyzing Context Cliff & Token Dynamics...", "analyze_context_dynamics", extra_db),
            ("volume", "\n▶ [5/11] Analyzing Tool & Command Character Volume Distributions...", "analyze_volume_distributions", vol_args),
            ("deep", "\n▶ [6/11] Analyzing Ultra-Deep 1,000+ Step Titan Sessions...", "analyze_ultra_deep_sessions", deep_args),
            ("clusters", "\n▶ [7/11] Analyzing Model Failure Clusters & Hotspots...", "analyze_failure_clusters", extra_db),
            ("benchmark", "\n▶ [8/11] Benchmarking Reasoning Tiers...", "benchmark_reasoning_tiers", extra_db),
            ("traces", "\n▶ [9/11] Extracting Cognitive & Chain-of-Thought Traces...", "extract_cognitive_traces", extra_db),
            ("artifacts", "\n▶ [10/11] Auditing Artifacts & Plan-Execution Drift...", "audit_artifacts", []),
            ("configs", "\n▶ [11/11] Auditing Project Rules & Skills Ecosystem...", "audit_project_configs", extra_db),
        ]
        for st_name, banner, mod_name, st_arg in stages:
            print(banner.lstrip("\n") if st_name == "inventory" else banner)
            rc = _run_pipeline_stage(mod_name, st_arg, st_name)
            if rc != 0:
                failed_stages.append((st_name, rc))

        print("\n" + "=" * 75)
        if failed_stages:
            summary = ", ".join(f"{name} (exit {code})" for name, code in failed_stages)
            print(f" ✘ TELEMETRY PIPELINE FAILED: {summary}")
            print("=" * 75)
            return failed_stages[0][1] or 1
        print(" ✔ COMPLETE 360-DEGREE TELEMETRY PIPELINE EXECUTION FINISHED")
        print("=" * 75)
        return 0
    elif sub in ("session", "live"):
        analyze_live_session = _import_pipeline_module("analyze_live_session", sub)
        if analyze_live_session is None:
            return 1
        session_id = getattr(args, "session_id", None)
        save_db = getattr(args, "save_db", False)
        out_path = getattr(args, "out", None)
        as_json = getattr(args, "json", False)

        if session_id:
            from harness.utils.context import get_active_brain_dir

            s_dir = get_active_brain_dir() / session_id
            if not s_dir.exists():
                cli_s_dir = Path.home() / ".gemini" / "antigravity-cli" / "brain" / session_id
                if cli_s_dir.exists():
                    s_dir = cli_s_dir
        else:
            s_dir = analyze_live_session.find_latest_session_dir()

        if not s_dir or not s_dir.exists():
            sys.stderr.write(f"Error: Session directory not found for {session_id or 'latest'}\n")
            return 1

        report = analyze_live_session.analyze_session(s_dir)

        if save_db:
            extract_transcripts = _import_pipeline_module("extract_transcripts", sub)
            if extract_transcripts is None:
                return 1
            from harness.telemetry import config
            from harness.telemetry.db import get_db_connection
            from harness.telemetry.extractor import upsert_session_telemetry

            db_path = config.resolve_db_path(getattr(args, "db", None))
            conn = get_db_connection(db_path)
            try:
                extract_transcripts.ensure_telemetry_schema(conn)

                from harness.trajectory.transcript_reader import find_transcript_path

                transcript_targets = []
                root_tp, _ = find_transcript_path(s_dir)
                if root_tp:
                    transcript_targets.append(root_tp)
                for sa in report.get("subagents", []):
                    sa_cid = sa.get("conversation_id")
                    if sa_cid:
                        sa_tp, _ = find_transcript_path(s_dir.parent / sa_cid)
                        if sa_tp:
                            transcript_targets.append(sa_tp)
                for t_path in transcript_targets:
                    res = extract_transcripts.extract_session(t_path)
                    if res:
                        upsert_session_telemetry(conn, *res, commit=False)
                conn.commit()
            finally:
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
    elif sub == "db-integrity":
        from harness.telemetry.integrity import audit_database_integrity, repair_database_integrity

        raw_db = getattr(args, "db", None)
        db_path = Path(raw_db) if raw_db else DEFAULT_DB
        if not db_path.exists():
            sys.stderr.write(f"Error: Database file not found at {db_path}\n")
            return 1

        do_repair = getattr(args, "repair", False)
        dry_run = getattr(args, "dry_run", False)
        as_json = getattr(args, "json", False)

        result = repair_database_integrity(db_path, dry_run=dry_run) if do_repair else audit_database_integrity(db_path)
        if as_json:
            print(json.dumps(result, indent=2))
        else:
            print_integrity_summary(result, db_path)
        return 0
    elif sub == "eras":
        extra = []
        if getattr(args, "db", None):
            extra.extend(["--db", str(args.db)])
        if getattr(args, "json", False):
            extra.append("--json")
        if getattr(args, "output_json", None):
            extra.extend(["--output-json", str(args.output_json)])
        if getattr(args, "output_report", None):
            extra.extend(["--output-report", str(args.output_report)])
        return _run_pipeline_stage("analyze_eras", extra, sub)
    elif sub == "export-site":
        extra = []
        if getattr(args, "db", None):
            extra.extend(["--db", str(args.db)])
        if getattr(args, "out", None):
            extra.extend(["--out", str(args.out)])
        if getattr(args, "json", False):
            extra.append("--json")
        return _run_pipeline_stage("export_website_metrics", extra, sub)
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

        # Architectural Fitness Function (AFF) audit
        aff_failed = False
        aff_result = {
            "status": "PASS",
            "score": 100.0,
            "scanned_files": 0,
            "defects_count": 0,
            "benchmark_latency_s": 0.0,
        }
        try:
            from harness.runtime.aff import audit_architectural_fitness
            aff_report = audit_architectural_fitness(workspace_root=cwd)
            all_aff_defects = (
                aff_report.boundary_defects + aff_report.cycle_defects + aff_report.smell_defects
            )
            has_crit_or_major = any(d.severity in ("CRITICAL", "MAJOR") for d in all_aff_defects)
            aff_failed = (aff_report.status == "FAIL" or has_crit_or_major)
            aff_result = {
                "status": aff_report.status,
                "score": round(aff_report.score, 2),
                "scanned_files": aff_report.scanned_files_count,
                "defects_count": len(all_aff_defects),
                "benchmark_latency_s": round(aff_report.benchmark_latency_s, 4),
            }
        except Exception as exc:
            aff_failed = True
            aff_result = {
                "status": "ERROR",
                "score": 0.0,
                "scanned_files": 0,
                "defects_count": 1,
                "benchmark_latency_s": 0.0,
                "error": str(exc),
            }
            sys.stderr.write(f"⚠️  AFF audit error: {exc}\n")

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
        except Exception as exc:
            sys.stderr.write(f"⚠️  Doctor audit warning: {exc}\n")

        if (not skip_tests and (test_suite_result["exit_code"] != 0 or test_suite_result["total_tests"] <= 0)) or aff_failed:
            if verdict_str.upper() in ("VICTORY CONFIRMED", "PASS"):
                verdict_str = "REJECTED"
        elif skip_tests and verdict_str.upper() in ("VICTORY CONFIRMED", "PASS", "PROVISIONAL"):
            # Never certify victory when tests were skipped (PSL-INV-001)
            verdict_str = "PROVISIONAL"

        verdict_obj = generate_audit_verdict(
            workspace_dir=cwd,
            task_id=task_id,
            verdict=verdict_str,
            test_suite_result=test_suite_result,
            doctor_result=doctor_result,
            aff_result=aff_result,
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
                f"AFF Audit:      {aff_result['status']} ({aff_result['score']:.1f}/100, "
                f"{aff_result['defects_count']} defects, {aff_result['benchmark_latency_s']}s)"
            )
            print(
                f"Doctor Audit:   {doctor_result['ok_count']} ok, "
                f"{doctor_result['missing_count']} missing, {doctor_result['outdated_count']} outdated"
            )
            print("=" * 70)

        certified = (
            not skip_tests
            and verdict_obj.verdict.upper() in ("VICTORY CONFIRMED", "PASS")
            and test_suite_result["exit_code"] == 0
            and test_suite_result["total_tests"] > 0
            and not aff_failed
        )
        return 0 if certified else 1

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
    elif sub in ("aff", "macro", "fitness"):
        from harness.runtime.aff import audit_architectural_fitness

        cwd = Path(getattr(args, "workspace", None) or Path.cwd()).resolve()
        as_json = getattr(args, "json", False)

        report = audit_architectural_fitness(workspace_root=cwd)

        if as_json:
            print(json.dumps(report.to_dict(), indent=2))
        else:
            print_aff_report(report, cwd)

        has_critical_or_major = any(
            d.severity in ("CRITICAL", "MAJOR")
            for d in (report.boundary_defects + report.cycle_defects + report.smell_defects)
        )
        return 1 if (report.status == "FAIL" or has_critical_or_major) else 0
    else:
        sys.stderr.write(f"Error: Unknown audit stage '{sub}'.\n")
        return 1

    return 0


def print_aff_report(report: Any, cwd: Path) -> None:
    """Renders beautifully styled terminal report for Architectural Fitness Functions."""
    badge = (
        "\033[32mPASS\033[0m"
        if report.status == "PASS"
        else ("\033[33mWARN\033[0m" if report.status == "WARNING" else "\033[31mFAIL\033[0m")
    )
    print("=" * 75)
    print(f" 🏛️  Agyis Architectural Fitness Function (AFF) Report [{badge}]")
    print("    Macro Governance & Structural Invariant Verification")
    print("=" * 75)
    print(f" Status:          {report.status}")
    print(f" Fitness Score:   {report.score:.1f}/100")
    print(f" Scanned Files:   {report.scanned_files_count} Python files")
    print(f" Latency:         {report.benchmark_latency_s:.4f}s (<0.25s benchmark)")
    print(f" Workspace Root:  {cwd}")
    print("-" * 75)

    total_defects = len(report.boundary_defects) + len(report.cycle_defects) + len(report.smell_defects)
    if total_defects == 0:
        print(" ✔ Zero architectural defects detected. Invariants strictly satisfied.")
    else:
        if report.boundary_defects:
            print(f"\n▶ BOUNDARY DEFECTS ({len(report.boundary_defects)}):")
            for d in report.boundary_defects:
                sev_color = "\033[31mCRIT\033[0m" if d.severity == "CRITICAL" else "\033[33mWARN\033[0m"
                print(f"  [{sev_color}] {d.source_file}:{d.line_number} -> Forbidden import '{d.imported_module}' [{d.rule_name}]")
                if d.remediation:
                    print(f"         Remediation: {d.remediation}")

        if report.cycle_defects:
            print(f"\n▶ DEPENDENCY CYCLE DEFECTS ({len(report.cycle_defects)}):")
            for c in report.cycle_defects:
                cycle_str = " -> ".join(c.cycle_path)
                print(f"  [\033[31mCRIT\033[0m] Circular Loop: {cycle_str}")
                if c.remediation:
                    print(f"         Remediation: {c.remediation}")

        if report.smell_defects:
            print(f"\n▶ STRUCTURAL SMELLS ({len(report.smell_defects)}):")
            for s in report.smell_defects:
                sev_color = (
                    "\033[31mCRIT\033[0m"
                    if s.severity == "CRITICAL"
                    else ("\033[33mMAJR\033[0m" if s.severity == "MAJOR" else "\033[34mWARN\033[0m")
                )
                print(f"  [{sev_color}] {s.file}:{s.line_number} -> {s.smell_type}: {s.description}")
                if s.remediation:
                    print(f"         Remediation: {s.remediation}")

    print("=" * 75)



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


def print_integrity_summary(result: dict, db_path: Path) -> None:
    """Renders human-readable summary for database integrity audit and repair."""
    audit = result.get("audit_after") or result.get("audit_before") or result
    counts = audit.get("counts", {})
    dups = audit.get("duplicate_tool_calls", {})
    mm = audit.get("counter_mismatches", {})
    non_utc = audit.get("non_utc_timestamps", {})
    print("=" * 70)
    print(" 🛡️  Agyis Telemetry Database Integrity Audit")
    print("=" * 70)
    print(f"Database:        {db_path}")
    print(f"Status:          {'HEALTHY' if audit.get('healthy') else 'NEEDS_REPAIR'}")
    if result.get("repaired"):
        act = result.get("actions", {})
        print(f"Repaired:        Dropped {act.get('tool_calls_dropped_total', 0):,} duplicate tool_calls, "
              f"updated {act.get('sessions_counters_updated', 0):,} session counters")
    elif result.get("dry_run"):
        print("Mode:            DRY RUN (no database modifications)")
    print("-" * 70)
    print(f"Rows:            {counts.get('sessions', 0):,} sessions | {counts.get('steps', 0):,} steps | "
          f"{counts.get('tool_calls', 0):,} tool_calls | {counts.get('user_interventions', 0):,} interventions")
    print(f"Duplicates:      {dups.get('total', 0):,} (pass1={dups.get('pass1_same_step', 0):,}, pass2={dups.get('pass2_cross_source', 0):,})")
    print(f"Mismatches:      calls={mm.get('tool_call_count', 0)}, errors={mm.get('tool_error_count', 0)}, "
          f"interventions={mm.get('intervention_count', 0)}, steps={mm.get('total_steps', 0)}, orphans={mm.get('zero_step_orphans', 0)}")
    print(f"Non-UTC TS:      {non_utc.get('total', 0):,}")
    print("=" * 70)

