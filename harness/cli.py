#!/usr/bin/env python3
"""
PSL Harness for Google Antigravity™ (Unified Developer CLI)

Primary console entrypoint for the PSL Harness runtime, providing:
- psl doctor: Workstation runtime diagnostic & auto-healing
- psl hook <name>: Deterministic lifecycle hook execution
- psl test: Test suite discovery & verification
- psl audit [stage]: Empirical telemetry lab runner
- psl status: System & customization health overview
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
import unittest
from typing import List, Optional

import harness
from harness.hooks import anti_drift_hook, anti_loop_hook, command_safety_hook, completion_fence_hook, output_compactor_hook
from pipeline import psl_doctor

REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_MATRIX = REPO_ROOT / "harness/runtime/matrix.json"
DEFAULT_DB = REPO_ROOT / "data/telemetry.db"


def cmd_doctor(args: argparse.Namespace) -> int:
    """Executes the workstation runtime audit and optional auto-healing."""
    matrix_path = Path(args.matrix) if args.matrix else DEFAULT_MATRIX
    if not matrix_path.exists():
        # Fallback to local package directory if installed
        pkg_matrix = Path(__file__).parent / "runtime/matrix.json"
        if pkg_matrix.exists():
            matrix_path = pkg_matrix
        else:
            sys.stderr.write(f"Error: matrix.json not found at {matrix_path}\n")
            return 1

    audit = psl_doctor.run_doctor(matrix_path)

    if args.json:
        print(json.dumps(audit, indent=2))
        return 0

    psl_doctor.print_cli_report(audit)

    if args.heal:
        print("\n🔧 Executing Auto-Healing...")
        actions = psl_doctor.heal_environment(audit, matrix_path)
        for act in actions:
            print(f"  ✔ {act}")
        print()

    if audit["summary"]["missing"] > 0 or audit["summary"]["outdated"] > 0:
        return 1
    return 0


def cmd_hook(args: argparse.Namespace) -> int:
    """Dispatches lifecycle hook execution from stdin to stdout."""
    hook_name = args.hook_name.lower().replace("_", "-")

    if hook_name in ("safety", "command-safety", "command_safety"):
        command_safety_hook.main()
        return 0
    elif hook_name in ("anti-loop", "anti_loop", "loop"):
        anti_loop_hook.main()
        return 0
    elif hook_name in ("compactor", "output-compactor", "output_compactor"):
        output_compactor_hook.main()
        return 0
    elif hook_name in ("verification-fence", "fence", "stop-fence", "stop", "completion-fence"):
        completion_fence_hook.main()
        return 0
    elif hook_name in ("anti-drift", "anti_drift", "drift"):
        anti_drift_hook.main()
        return 0
    else:
        sys.stderr.write(
            f"Error: Unknown hook '{args.hook_name}'. "
            "Supported hooks: command-safety, anti-loop, output-compactor, verification-fence, anti-drift\n"
        )
        return 1


def cmd_test(args: argparse.Namespace) -> int:
    """Runs the test suite."""
    test_dir = Path(args.start_dir) if args.start_dir else (REPO_ROOT / "tests")
    if not test_dir.exists():
        sys.stderr.write(f"Error: test directory not found at {test_dir}\n")
        return 1

    loader = unittest.TestLoader()
    suite = loader.discover(start_dir=str(test_dir), pattern="test_*.py")
    verbosity = 2 if args.verbose else 1
    runner = unittest.TextTestRunner(verbosity=verbosity)
    result = runner.run(suite)

    success = result.wasSuccessful()
    completion_fence_hook.record_verification(success=success)
    state_dir = completion_fence_hook.get_state_dir()
    if state_dir.exists():
        for sf in state_dir.glob("verification_state_*.json"):
            cid = sf.stem.replace("verification_state_", "")
            completion_fence_hook.record_verification(success=success, conv_id=cid)
    return 0 if success else 1


def cmd_audit(args: argparse.Namespace) -> int:
    """Dispatches telemetry laboratory subcommands."""
    sub = args.stage or "all"

    if sub == "extract":
        from pipeline import extract_transcripts
        extract_transcripts.main()
    elif sub == "classify":
        from pipeline import classify_failures
        classify_failures.main()
    elif sub == "inventory":
        from pipeline import inventory_customizations
        inventory_customizations.main()
    elif sub == "dynamics":
        from pipeline import analyze_context_dynamics
        analyze_context_dynamics.main()
    elif sub == "traces":
        from pipeline import extract_cognitive_traces
        extract_cognitive_traces.main()
    elif sub == "interventions":
        from pipeline import summarize_interventions
        summarize_interventions.main()
    elif sub == "volume":
        from pipeline import analyze_volume_distributions
        return analyze_volume_distributions.main(args)
    elif sub == "deep":
        from pipeline import analyze_ultra_deep_sessions
        return analyze_ultra_deep_sessions.main(args)
    elif sub == "all":
        print("▶ [1/4] Scanning Customization Inventory...")
        from pipeline import inventory_customizations
        inventory_customizations.main()

        print("\n▶ [2/4] Harvesting Transcripts...")
        from pipeline import extract_transcripts
        extract_transcripts.main()

        print("\n▶ [3/4] Classifying Failures & Workstation Metrics...")
        from pipeline import classify_failures
        classify_failures.main()

        print("\n▶ [4/4] Summarizing Operator Interventions...")
        from pipeline import summarize_interventions
        summarize_interventions.main()
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
            db_path = DEFAULT_DB
            conn = sqlite3.connect(db_path)
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


def cmd_sync(args: argparse.Namespace) -> int:
    """Shortcut command to audit and synchronize the current session into telemetry.db."""
    args.stage = "session"
    args.save_db = True
    args.out = None
    return cmd_audit(args)


def cmd_skills(args: argparse.Namespace) -> int:
    """Lists, inspects, or synchronizes modular product skills."""
    from harness.skills import get_skill, list_skills, sync_skills

    if getattr(args, "sync", False):
        synced = sync_skills()
        print(f"✔ Synchronized {len(synced)} skills to .agents/skills/:")
        for p in synced:
            print(f"  • {p.parent.name} -> {p}")
        return 0

    if getattr(args, "name", None):
        spec = get_skill(args.name)
        if not spec:
            sys.stderr.write(f"Error: Skill '{args.name}' not found.\n")
            return 1
        if getattr(args, "json", False):
            print(
                json.dumps(
                    {
                        "name": spec.name,
                        "description": spec.description,
                        "path": str(spec.path),
                        "frontmatter": spec.frontmatter,
                    },
                    indent=2,
                )
            )
            return 0
        print(f"Skill: {spec.name}")
        print(f"Path:  {spec.path}")
        print(f"Description:\n  {spec.description}\n")
        print("=" * 60)
        print(spec.body.strip())
        return 0

    skills = list_skills()
    if getattr(args, "json", False):
        print(
            json.dumps(
                [
                    {
                        "name": s.name,
                        "description": s.description,
                        "path": str(s.path),
                    }
                    for s in skills
                ],
                indent=2,
            )
        )
        return 0

    print(f"PSL Modular Skills ({len(skills)} available):")
    print("-" * 60)
    for s in skills:
        print(f"  • {s.name:<24} {s.description}")
    print()
    return 0


def cmd_agents(args: argparse.Namespace) -> int:
    """Lists, inspects, or synchronizes specialist subagents."""
    from harness.subagents import get_agent_spec, list_agent_specs, sync_agent_definitions

    if getattr(args, "sync", False):
        synced = sync_agent_definitions()
        print(f"✔ Synchronized {len(synced)} agent definitions to .agents/agents/:")
        for p in synced:
            print(f"  • {p.name} -> {p}")
        return 0

    if getattr(args, "name", None):
        spec = get_agent_spec(args.name)
        if not spec:
            sys.stderr.write(f"Error: Agent '{args.name}' not found.\n")
            return 1
        if getattr(args, "json", False):
            print(
                json.dumps(
                    {
                        "name": spec.name,
                        "archetype": spec.archetype.value,
                        "role": spec.role,
                        "description": spec.description,
                        "permissions": {
                            "read": spec.permissions.read,
                            "write": spec.permissions.write,
                            "execute": spec.permissions.execute,
                            "subagent": spec.permissions.subagent,
                            "mcp": spec.permissions.mcp,
                        },
                        "allowed_tools": spec.allowed_tools,
                        "source_file": str(spec.source_file) if spec.source_file else None,
                    },
                    indent=2,
                )
            )
            return 0
        print(f"Agent:       {spec.name}")
        print(f"Archetype:   {spec.archetype.value}")
        print(f"Role:        {spec.role}")
        print(
            f"Permissions: write={spec.can_write}, exec={spec.can_execute}, subagent={spec.can_subagent}"
        )
        print(f"Allowed Tools ({len(spec.allowed_tools)}): {', '.join(spec.allowed_tools)}")
        print(f"Description:\n  {spec.description}\n")
        print("=" * 60)
        print(spec.system_prompt)
        return 0

    agents = list_agent_specs()
    if getattr(args, "json", False):
        print(
            json.dumps(
                [
                    {
                        "name": a.name,
                        "archetype": a.archetype.value,
                        "role": a.role,
                        "description": a.description,
                        "can_write": a.can_write,
                        "can_execute": a.can_execute,
                        "tools_count": len(a.allowed_tools),
                    }
                    for a in agents
                ],
                indent=2,
            )
        )
        return 0

    print(f"PSL Specialist Subagents ({len(agents)} registered):")
    print("-" * 60)
    for a in agents:
        caps = []
        if a.can_write:
            caps.append("write")
        else:
            caps.append("read-only")
        if a.can_execute:
            caps.append("exec")
        if a.can_subagent:
            caps.append("subagent")
        cap_str = f"[{' | '.join(caps)}]"
        print(f"  • {a.name:<18} ({a.role}) {cap_str}")
        print(f"    {a.description}")
        print(f"    Tools ({len(a.allowed_tools)}): {', '.join(a.allowed_tools)}")
    print()
    return 0


def format_subagents_table(statuses: List[Any]) -> str:
    """Format a list of SubagentContextStatus as an ASCII table."""
    if not statuses:
        return "No active subagents found."

    headers = [
        "Conversation ID",
        "Role",
        "Steps",
        "Tokens",
        "Health Zone",
        "Recommendation",
        "Latency",
    ]
    rows = []
    for s in statuses:
        cid = s.conversation_id[:12] if len(s.conversation_id) > 12 else s.conversation_id
        hz_badge = s.health_zone
        if s.health_zone == "HEALTHY":
            hz_badge = "🟢 HEALTHY"
        elif s.health_zone == "AMBER":
            hz_badge = "🟡 AMBER"
        elif s.health_zone == "RED_ALERT":
            hz_badge = "🔴 RED_ALERT"

        rows.append([
            cid,
            s.role[:20],
            str(s.step_count),
            f"{s.token_count:,}",
            hz_badge,
            s.recommendation,
            f"{s.latency_ms:.1f}ms",
        ])

    col_widths = [len(h) for h in headers]
    for row in rows:
        for i, val in enumerate(row):
            col_widths[i] = max(col_widths[i], len(val))

    sep = "+-" + "-+-".join("-" * w for w in col_widths) + "-+"
    header_str = (
        "| "
        + " | ".join(f"{h:<{col_widths[i]}}" for i, h in enumerate(headers))
        + " |"
    )

    table_lines = [sep, header_str, sep]
    for row in rows:
        line = (
            "| "
            + " | ".join(f"{val:<{col_widths[i]}}" for i, val in enumerate(row))
            + " |"
        )
        table_lines.append(line)
    table_lines.append(sep)
    return "\n".join(table_lines)


def cmd_subagents(args: argparse.Namespace) -> int:
    """Renders active subagents table and zero-token context health gauge."""
    from harness.subagents import list_active_subagent_statuses

    brain_dir = getattr(args, "brain_dir", None)
    statuses = list_active_subagent_statuses(brain_dir=brain_dir)

    if getattr(args, "json", False):
        data = [
            {
                "conversation_id": s.conversation_id,
                "role": s.role,
                "step_count": s.step_count,
                "token_count": s.token_count,
                "health_zone": s.health_zone,
                "recommendation": s.recommendation,
                "latency_ms": s.latency_ms,
            }
            for s in statuses
        ]
        print(json.dumps(data, indent=2))
        return 0

    if not statuses:
        print("No active subagents found in brain directory.")
        return 0

    print(f"PSL Active Subagents ({len(statuses)} active):")
    print(format_subagents_table(statuses))
    print()
    return 0


def cmd_status(args: argparse.Namespace) -> int:
    """Prints a high-level status summary of the PSL Harness."""
    print("=" * 70)
    print(f" 🐾 PSL Harness for Google Antigravity™ (v{harness.__version__})")
    print("=" * 70)
    print(f" Repository Root: {REPO_ROOT}")
    print(f" Platform:        {sys.platform} (Python {sys.version.split()[0]})")
    herm_py = psl_doctor.find_hermetic_uv_python()
    if herm_py:
        print(f" Hermetic Python: {herm_py} (Ready)")
    else:
        print(" Hermetic Python: Not found in uv cache")

    from harness.skills import list_skills
    from harness.subagents import list_active_subagent_statuses, list_agent_specs

    skills = list_skills()
    agents = list_agent_specs()
    active_subagents = list_active_subagent_statuses()
    print(f" Modular Skills:  {len(skills)} installed")
    print(
        f" Subagents:       {len(agents)} registered ({', '.join(a.archetype.value for a in agents)})"
    )

    # Quick count of telemetry
    if DEFAULT_DB.exists():
        import sqlite3

        try:
            conn = sqlite3.connect(DEFAULT_DB)
            c = conn.cursor()
            c.execute("SELECT COUNT(*) FROM sessions")
            sess_cnt = c.fetchone()[0]
            c.execute("SELECT COUNT(*) FROM steps")
            step_cnt = c.fetchone()[0]
            conn.close()
            print(f" Telemetry DB:    {DEFAULT_DB.name} ({sess_cnt:,} sessions, {step_cnt:,} steps)")
        except (sqlite3.Error, OSError):
            print(f" Telemetry DB:    {DEFAULT_DB.name} (present)")
    else:
        print(" Telemetry DB:    Not initialized")

    print("-" * 70)
    print(" Active Lifecycle Hooks:")
    print("   ✔ command-safety   (PreToolUse: CPython 3.12, f-string, grep sanitization)")
    print("   ✔ anti-loop        (PreToolUse: repetitive tool call breaker)")
    print("   ✔ output-compactor (PostToolUse: deterministic 2KB output truncation)")
    print("   ✔ verification-fence (Stop: unverified code edit completion guard)")
    print("   ✔ anti-drift       (PreToolUse: plan boundary & cognitive anchor gate)")
    print("-" * 70)
    print(" Cognitive Attention Horizon Gauge:")
    print("   🟢 Healthy Zone: <50k tokens / <50 steps (High Attention Aperture)")
    print("   🟡 Amber Zone:   50k–100k tokens / 50–100 steps (Attention Compaction Advised)")
    print("   🔴 Red Alert:    >100k tokens / >100 steps (Context Cliff Active)")
    print("-" * 70)
    print(" Specialist Subagents:")
    for ag in agents:
        caps = ["write" if ag.can_write else "read-only"]
        if ag.can_execute:
            caps.append("exec")
        print(f"   ✔ {ag.name:<18} ({ag.role}) [{' | '.join(caps)}]")
    print("-" * 70)
    print(" Modular Skills:")
    for sk in skills:
        print(f"   ✔ {sk.name:<22} - {sk.description[:42]}...")
    if active_subagents:
        print("-" * 70)
        print(f" Live Active Subagents ({len(active_subagents)} active):")
        for line in format_subagents_table(active_subagents).splitlines():
            print(f"   {line}")
    print("=" * 70)
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="psl",
        description="PSL Harness for Google Antigravity™ — Unified Developer CLI",
    )
    parser.add_argument(
        "-v", "--version", action="version", version=f"psl-agy-harness {harness.__version__}"
    )

    subparsers = parser.add_subparsers(dest="subcommand", help="Available subcommands")

    # doctor
    p_doc = subparsers.add_parser("doctor", help="Audit host workstation runtimes and auto-heal")
    p_doc.add_argument("--matrix", type=Path, default=None, help="Path to matrix.json")
    p_doc.add_argument("--heal", action="store_true", help="Execute safe user-space auto-healing")
    p_doc.add_argument("--json", action="store_true", help="Output audit report in JSON format")

    # hook
    p_hook = subparsers.add_parser("hook", help="Run a lifecycle hook handler directly")
    p_hook.add_argument(
        "hook_name",
        choices=[
            "command-safety", "safety",
            "anti-loop", "loop",
            "output-compactor", "compactor",
            "verification-fence", "fence", "stop-fence", "stop", "completion-fence",
            "anti-drift", "drift", "anti_drift",
        ],
        help="Name of the lifecycle hook to invoke",
    )

    # test
    p_test = subparsers.add_parser("test", help="Run the test suite")
    p_test.add_argument("-v", "--verbose", action="store_true", help="Verbose test runner output")
    p_test.add_argument("-s", "--start-dir", type=Path, default=None, help="Start directory for tests")

    # audit
    p_audit = subparsers.add_parser("audit", help="Run empirical telemetry laboratory pipelines")
    p_audit.add_argument(
        "stage",
        nargs="?",
        default="all",
        choices=["all", "extract", "classify", "inventory", "dynamics", "traces", "interventions", "volume", "deep", "session", "live"],
        help="Audit pipeline stage to run (default: all)",
    )
    p_audit.add_argument("--db", type=str, default=None, help="Path to SQLite database")
    p_audit.add_argument("--backfill", action="store_true", help="Force volume backfill from transcripts")
    p_audit.add_argument("--session-id", "-s", type=str, default=None, help="Target session ID for session audit")
    p_audit.add_argument("--save-db", action="store_true", help="Sync audited session into data/telemetry.db")
    p_audit.add_argument("--out", type=Path, default=None, help="Export session analysis JSON path")
    p_audit.add_argument("--json", action="store_true", help="Output session report in JSON format")
    p_audit.add_argument("--output-json", type=Path, default=None, help="Export analysis JSON path")
    p_audit.add_argument("--output-report", type=Path, default=None, help="Export analysis report Markdown path")
    p_audit.add_argument("--quiet", action="store_true", help="Suppress verbose stdout in pipeline stages")

    # skills
    p_skills = subparsers.add_parser("skills", help="List and inspect modular product skills")
    p_skills.add_argument("name", nargs="?", default=None, help="Name of specific skill to view")
    p_skills.add_argument("--sync", action="store_true", help="Sync skills to .agents/skills")
    p_skills.add_argument("--json", action="store_true", help="Output skills in JSON format")

    # agents
    p_agents = subparsers.add_parser("agents", help="List and inspect specialist subagent archetypes")
    p_agents.add_argument("name", nargs="?", default=None, help="Name of specific agent to view")
    p_agents.add_argument("--sync", action="store_true", help="Sync agent definitions to .agents/agents")
    p_agents.add_argument("--json", action="store_true", help="Output agents in JSON format")

    # subagents
    p_subagents = subparsers.add_parser(
        "subagents", help="List active subagents and context health gauge"
    )
    p_subagents.add_argument(
        "--json", action="store_true", help="Output subagents in JSON format"
    )
    p_subagents.add_argument(
        "--brain-dir", type=Path, default=None, help="Custom brain directory path"
    )

    # status / info
    subparsers.add_parser("status", help="Print harness installation and health summary")

    # sync (shortcut for audit session --save-db)
    p_sync = subparsers.add_parser("sync", help="Audit and synchronize the active session into telemetry.db")
    p_sync.add_argument("--session-id", "-s", type=str, default=None, help="Target session ID (default: latest)")
    p_sync.add_argument("--json", action="store_true", help="Output session report in JSON format")

    return parser


def main(argv: Optional[List[str]] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if not args.subcommand:
        parser.print_help()
        return 0

    if args.subcommand == "doctor":
        return cmd_doctor(args)
    elif args.subcommand == "hook":
        return cmd_hook(args)
    elif args.subcommand == "test":
        return cmd_test(args)
    elif args.subcommand == "audit":
        return cmd_audit(args)
    elif args.subcommand == "sync":
        return cmd_sync(args)
    elif args.subcommand == "skills":
        return cmd_skills(args)
    elif args.subcommand == "agents":
        return cmd_agents(args)
    elif args.subcommand == "subagents":
        return cmd_subagents(args)
    elif args.subcommand == "status":
        return cmd_status(args)

    return 0


if __name__ == "__main__":
    sys.exit(main())
