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
from harness.delivery import DeliveryMode, PluginInstaller
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
        extra = []
        if getattr(args, "db", None):
            extra.extend(["--db", args.db])
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
        extra = []
        if getattr(args, "db", None):
            extra.extend(["--db", args.db])
        extract_transcripts.main(extra)

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
            from harness.telemetry import config
            db_path = config.resolve_db_path(getattr(args, "db", None))
            conn = sqlite3.connect(db_path)
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


def cmd_auth(args: argparse.Namespace) -> int:
    """Manages GitHub PAT authentication and telemetry credentials."""
    import urllib.error
    from harness.telemetry import config

    sub = getattr(args, "auth_cmd", None) or "status"

    if sub == "login":
        token = getattr(args, "token", None)
        endpoint = getattr(args, "endpoint", None) or config.get_sync_endpoint()

        if getattr(args, "gh", False):
            token = config.get_gh_cli_token()
            if not token:
                sys.stderr.write("Error: Failed to retrieve token from GitHub CLI ('gh auth token'). Ensure gh is installed and authenticated.\n")
                return 1

        if not token:
            if sys.stdin.isatty():
                gh_token = config.get_gh_cli_token()
                if gh_token:
                    try:
                        ans = input("GitHub CLI token detected. Use it for authentication? [Y/n]: ").strip().lower()
                    except (EOFError, KeyboardInterrupt):
                        sys.stderr.write("\nAborted.\n")
                        return 1
                    if ans in ("", "y", "yes"):
                        token = gh_token

            if not token:
                if sys.stdin.isatty():
                    import getpass
                    try:
                        token = getpass.getpass("Enter GitHub Personal Access Token (PAT): ").strip()
                    except (EOFError, KeyboardInterrupt):
                        sys.stderr.write("\nAborted.\n")
                        return 1
                else:
                    try:
                        token = input().strip()
                    except (EOFError, KeyboardInterrupt):
                        sys.stderr.write("Error: GitHub PAT required. Provide via --token or stdin.\n")
                        return 1

        if not token:
            sys.stderr.write("Error: GitHub PAT required.\n")
            return 1

        from harness.telemetry.sync import verify_auth_token
        try:
            verify_res = verify_auth_token(endpoint=endpoint, token=token)
        except urllib.error.HTTPError as exc:
            if exc.code == 401:
                sys.stderr.write("Error 401: Invalid GitHub Personal Access Token.\n")
            elif exc.code == 403:
                sys.stderr.write("Error 403: User is not an authorized member of the organization.\n")
            else:
                sys.stderr.write(f"Error {exc.code}: {exc.reason}\n")
            return 1
        except Exception as exc:
            sys.stderr.write(f"Error verifying authentication: {exc}\n")
            return 1

        username = verify_res.get("username")
        org = verify_res.get("org", "purrfectsoft")

        from datetime import datetime, timezone
        config.save_credentials({
            "token": token,
            "github_username": username,
            "updated_at": datetime.now(timezone.utc).isoformat(),
        })

        if getattr(args, "workspace_scope", False):
            ws_cfg = config.load_config()
            if getattr(args, "endpoint", None):
                ws_cfg["endpoint"] = endpoint
            config.save_config(ws_cfg, scope="workspace")
        elif getattr(args, "endpoint", None):
            cfg = config.load_config()
            cfg["endpoint"] = endpoint
            config.save_config(cfg, scope="global")

        if getattr(args, "json", False):
            print(json.dumps({
                "status": "success",
                "authenticated": True,
                "username": username,
                "org": org,
                "endpoint": endpoint,
            }, indent=2))
        else:
            print(f"✔ Successfully authenticated as {username} ({org})")
            print(f"  Endpoint: {endpoint}")
        return 0

    elif sub == "status":
        creds = config.load_credentials()
        cfg = config.load_config()
        endpoint = cfg.get("endpoint", "http://localhost:8000")
        token = creds.get("token")
        username = creds.get("github_username")
        is_auth = bool(token and username)

        masked = None
        if token:
            masked = f"{token[:4]}****{token[-4:]}" if len(token) > 8 else "****"

        if getattr(args, "json", False):
            print(json.dumps({
                "authenticated": is_auth,
                "username": username,
                "token_masked": masked,
                "endpoint": endpoint,
            }, indent=2))
            return 0 if is_auth else 1

        print("=" * 60)
        print(" PSL Telemetry Authentication Status")
        print("=" * 60)
        print(f"  Authenticated: {'Yes' if is_auth else 'No'}")
        print(f"  Username:      {username or 'Not logged in'}")
        print(f"  Token:         {masked or 'None'}")
        print(f"  Hub Endpoint:  {endpoint}")
        print("=" * 60)
        return 0 if is_auth else 1

    elif sub == "logout":
        config.clear_credentials()
        if getattr(args, "json", False):
            print(json.dumps({"status": "success", "message": "Credentials cleared successfully."}, indent=2))
        else:
            print("✔ Credentials cleared successfully.")
        return 0

    else:
        sys.stderr.write(f"Error: Unknown auth command '{sub}'. Use login, status, or logout.\n")
        return 1


def cmd_sync(args: argparse.Namespace) -> int:
    """Synchronizes telemetry with the central hub (push, pull, or bi-directional)."""
    db_path = getattr(args, "db", None)

    if getattr(args, "systemd", False):
        from harness.telemetry.sync import generate_systemd_service
        interval = getattr(args, "interval", 5.0) or 5.0
        unit = generate_systemd_service(interval_sec=interval)
        print(unit)
        return 0

    if getattr(args, "watch", False):
        from harness.telemetry.sync import watch_and_sync
        interval = getattr(args, "interval", 5.0) or 5.0
        endpoint = getattr(args, "remote", None)
        print(f"[*] Starting background telemetry watch & sync daemon (interval={interval}s)...")
        res = watch_and_sync(interval_sec=interval, db_path=db_path, endpoint=endpoint)
        if getattr(args, "json", False):
            print(json.dumps(res, indent=2))
        else:
            print(f"[✓] Watch daemon stopped: {res.get('iterations', 0)} iterations, {res.get('total_sessions_pushed', 0)} sessions pushed.")
        return 0

    if getattr(args, "session_id", None):
        try:
            from pipeline import analyze_live_session
            s_dir = analyze_live_session.find_session_dir(args.session_id)
            if s_dir and s_dir.exists():
                t_file = s_dir / ".system_generated" / "logs" / "transcript.jsonl"
                if t_file.exists():
                    from pipeline import extract_transcripts
                    from harness.telemetry import config
                    resolved_db = config.resolve_db_path(db_path)
                    extract_transcripts.extract_and_store([t_file], db_path=resolved_db)
        except Exception as exc:
            sys.stderr.write(f"Warning: Session ingestion failed: {exc}\n")

    push_flag = getattr(args, "push", False)
    pull_flag = getattr(args, "pull", False)
    if push_flag and not pull_flag:
        direction = "push"
    elif pull_flag and not push_flag:
        direction = "pull"
    else:
        direction = "both"

    endpoint = getattr(args, "remote", None)
    interactive = getattr(args, "interactive", False)
    review = getattr(args, "review", False)
    limit = getattr(args, "limit", None)
    dry_run = getattr(args, "dry_run", False)

    on_progress = None
    if not getattr(args, "json", False):
        def on_progress(batch_num: int, total_batches: int, stats: Dict[str, Any]) -> None:
            if total_batches > 1:
                print(f"  • Pushing batch {batch_num}/{total_batches} ({stats.get('sessions', 0)} sessions, {stats.get('steps', 0)} steps)...")

    from harness.telemetry.sync import sync_telemetry
    sync_kwargs: Dict[str, Any] = {
        "direction": direction,
        "interactive": interactive,
        "endpoint": endpoint,
        "db_path": db_path,
        "limit": limit,
        "dry_run": dry_run,
        "on_progress": on_progress,
    }
    if review:
        sync_kwargs["review"] = review

    try:
        res = sync_telemetry(**sync_kwargs)
    except Exception as exc:
        sys.stderr.write(f"Sync error: {exc}\n")
        return 1

    if getattr(args, "json", False):
        print(json.dumps(res, indent=2))
        return 0

    if res.get("status") == "aborted":
        print("✘ Sync aborted by user.")
        return 0

    mode_str = " (dry run)" if dry_run else ""
    print(f"✔ Telemetry sync completed successfully{mode_str}:")
    if res.get("push"):
        p = res["push"]
        print(f"  • Pushed: {p.get('sessions_pushed', 0)} sessions, {p.get('steps_pushed', 0)} steps, {p.get('tool_calls_pushed', 0)} tools")
    if res.get("pull"):
        pl = res["pull"]
        print(f"  • Pulled: {pl.get('sessions_inserted', pl.get('sessions_pulled', 0))} new sessions, {pl.get('steps_inserted', pl.get('steps_pulled', 0))} steps")
    return 0


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
    """Lists, inspects, creates, validates, or synchronizes specialist subagents."""
    from harness.subagents import (
        DEFAULT_AGENTS_DIR,
        REPO_ROOT,
        AgentArchetype,
        CAPABILITY_BUNDLES,
        get_agent_spec,
        inspect_workspace_context,
        list_agent_specs,
        scaffold_agent_markdown,
        sync_agent_definitions,
        validate_agent_spec,
    )

    action_or_name = getattr(args, "name", None)
    target_name = getattr(args, "target_name", None)

    # 0. agents rehydrate [--id <conv_id>] [--recent-hours <N>]
    if action_or_name == "rehydrate":
        from harness.subagents import list_active_subagent_statuses, rehydrate_subagent_session

        conv_id = getattr(args, "id", None) or target_name
        brain_dir = getattr(args, "brain_dir", None)

        if not conv_id:
            statuses = list_active_subagent_statuses(brain_dir=brain_dir)
            if not statuses:
                sys.stderr.write("No active subagent sessions found to rehydrate.\n")
                return 1
            conv_id = statuses[0].conversation_id

        try:
            res = rehydrate_subagent_session(conv_id=conv_id, brain_dir=brain_dir)
        except FileNotFoundError as exc:
            sys.stderr.write(f"Error: {exc}\n")
            return 1

        if getattr(args, "json", False):
            print(json.dumps(res, indent=2))
            return 0

        print(f"Rehydrated Subagent Session: {res['conversation_id']}")
        print(f"  Role:            {res['role']}")
        print(f"  Status:          {res['status']}")
        print(f"  Step Count:      {res['step_count']}")
        print(f"  Tool Calls:      {res['tool_calls_count']}")
        print(f"  Last Step:       {res['last_step_index']}")
        if res.get("completed_files"):
            print(f"  Completed Files ({len(res['completed_files'])}):")
            for cf in res["completed_files"]:
                print(f"    • {cf}")
        if res.get("error"):
            print(f"  Error:           {res['error']}")
        if res.get("prompt"):
            prompt_preview = res["prompt"][:150].replace("\n", " ")
            print(f"  Prompt:          {prompt_preview}...")
        return 0

    # 1. agents create <name>
    if action_or_name == "create":
        name = target_name
        if not name:
            if sys.stdin.isatty():
                try:
                    name = input("Enter agent name: ").strip()
                except (EOFError, KeyboardInterrupt):
                    sys.stderr.write("\nAborted.\n")
                    return 1
            if not name:
                sys.stderr.write("Error: Agent name is required for create.\n")
                return 1

        name = name.strip().lower().replace(" ", "_")
        arch_str = getattr(args, "archetype", None)
        if not arch_str:
            if sys.stdin.isatty():
                print("Available archetypes:")
                print("  1) main         (Lead Architect & Master Implementer)")
                print("  2) executioner  (Worker / Implementer)")
                print("  3) hammer       (Ruthless Reviewer)")
                print("  4) auditor      (QA Verifier)")
                print("  5) planner      (Architect / Planner)")
                print("  6) coordinator  (Swarm Coordinator)")
                try:
                    choice = input("Select archetype [1-6 or name] (default: executioner): ").strip()
                except (EOFError, KeyboardInterrupt):
                    sys.stderr.write("\nAborted.\n")
                    return 1
                mapping = {
                    "1": "main",
                    "2": "executioner",
                    "3": "hammer",
                    "4": "auditor",
                    "5": "planner",
                    "6": "coordinator",
                }
                arch_str = mapping.get(choice, choice) or "executioner"
            else:
                arch_str = "executioner"

        try:
            archetype = AgentArchetype.from_string(arch_str)
        except ValueError as exc:
            sys.stderr.write(f"Error: {exc}\n")
            return 1

        bundle_str = getattr(args, "bundle", None)
        if not bundle_str:
            if sys.stdin.isatty():
                print("Available capability bundles:")
                print("  1) read_only    (view_file, list_dir, grep_search, find_by_name, read_url, search_web)")
                print("  2) verifier     (read_only + run_command, manage_task)")
                print("  3) builder      (verifier + write_to_file, replace_file_content)")
                print("  4) orchestrator (read_only + invoke_subagent, send_message, manage_subagents, manage_task)")
                print("  5) full         (all platform tools enabled)")
                try:
                    choice = input("Select capability bundle [1-5 or name] (default: auto): ").strip()
                except (EOFError, KeyboardInterrupt):
                    sys.stderr.write("\nAborted.\n")
                    return 1
                b_map = {
                    "1": "read_only",
                    "2": "verifier",
                    "3": "builder",
                    "4": "orchestrator",
                    "5": "full",
                }
                bundle_str = b_map.get(choice, choice) or None

        scope = getattr(args, "scope", "project") or "project"
        if scope == "global":
            target_dir = Path.home() / ".gemini" / "config" / "agents"
        else:
            target_dir = REPO_ROOT / ".agents" / "agents"

        model = getattr(args, "model", "inherit") or "inherit"
        ws_ctx = inspect_workspace_context()
        content = scaffold_agent_markdown(
            name=name,
            archetype=archetype,
            bundle=bundle_str,
            model=model,
            workspace_context=ws_ctx,
        )

        target_dir.mkdir(parents=True, exist_ok=True)
        out_path = target_dir / f"{name}.md"
        out_path.write_text(content, encoding="utf-8")

        val_errors = validate_agent_spec(out_path)
        if val_errors:
            for e in val_errors:
                sys.stderr.write(f"Warning: {e}\n")

        print(f"✔ Created agent '{name}' ({archetype.value}) at {out_path}")
        return 0

    # 2. agents validate <path_or_name>
    if action_or_name == "validate":
        target = target_name
        if not target:
            sys.stderr.write("Error: Path or agent name required for validate.\n")
            return 1

        cand = Path(target)
        found_file: Optional[Path] = None
        if cand.is_file():
            found_file = cand
        else:
            for check_dir in (REPO_ROOT / ".agents" / "agents", DEFAULT_AGENTS_DIR):
                p1 = check_dir / f"{target}.md"
                p2 = check_dir / target
                if p1.is_file():
                    found_file = p1
                    break
                elif p2.is_file():
                    found_file = p2
                    break
            if not found_file:
                spec = get_agent_spec(target)
                if spec and spec.source_file and spec.source_file.is_file():
                    found_file = spec.source_file

        if not found_file:
            sys.stderr.write(f"Error: Agent file '{target}' not found.\n")
            return 1

        errors = validate_agent_spec(found_file)
        if not errors:
            print(f"✔ Agent '{found_file.name}' is valid.")
            return 0
        else:
            sys.stderr.write(f"✘ Agent '{found_file.name}' failed validation with {len(errors)} error(s):\n")
            for err in errors:
                sys.stderr.write(f"  • {err}\n")
            return 1

    # 3. agents --sync
    if getattr(args, "sync", False):
        synced = sync_agent_definitions()
        print(f"✔ Synchronized {len(synced)} agent definitions to .agents/agents/:")
        for p in synced:
            print(f"  • {p.name} -> {p}")
        return 0

    # 4. agents <name> (inspect)
    if action_or_name:
        spec = get_agent_spec(action_or_name)
        if not spec:
            sys.stderr.write(f"Error: Agent '{action_or_name}' not found.\n")
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


def cmd_remote(args: argparse.Namespace) -> int:
    """Dispatches remote execution, script streaming, and triage subcommands."""
    sub = getattr(args, "remote_cmd", None)
    if not sub:
        sys.stderr.write("Usage: psl remote <exec|script|triage|socket> ...\n")
        return 1

    from harness.remote import RemoteRunner, ScriptStreamer, RemoteTriage

    runner = RemoteRunner()

    if sub == "exec":
        login_shell = getattr(args, "login_shell", False)
        if not login_shell:
            from harness.hooks.command_safety_hook import REMOTE_TOOLCHAIN_REGEX
            if REMOTE_TOOLCHAIN_REGEX.search(args.command):
                login_shell = True

        res = runner.run(
            target=args.target,
            remote_cmd=args.command,
            port=args.port,
            timeout=args.timeout,
            login_shell=login_shell,
            capture_output=True,
            text=True,
        )
        if res.stdout:
            sys.stdout.write(res.stdout)
        if res.stderr:
            sys.stderr.write(res.stderr)
        return res.returncode

    elif sub == "script":
        script_path = Path(args.script)
        if not script_path.exists():
            sys.stderr.write(f"Error: Local script not found: {script_path}\n")
            return 1

        script_args = getattr(args, "args", [])
        if getattr(args, "stage", False):
            res = ScriptStreamer.stage_script(
                runner=runner,
                target=args.target,
                script_path=script_path,
                args=script_args,
                port=args.port,
                timeout=args.timeout,
            )
        else:
            res = ScriptStreamer.stream_script(
                runner=runner,
                target=args.target,
                script_path=script_path,
                args=script_args,
                port=args.port,
                timeout=args.timeout,
            )

        if res.stdout:
            sys.stdout.write(res.stdout)
        if res.stderr:
            sys.stderr.write(res.stderr)
        return res.returncode

    elif sub == "triage":
        report_data = RemoteTriage.run_triage(
            runner=runner,
            target=args.target,
            profile=args.profile,
            service=args.service,
            lines=args.lines,
            port=args.port,
            timeout=args.timeout,
        )

        if getattr(args, "json", False):
            print(json.dumps(report_data, indent=2))
        else:
            print(report_data["report_markdown"])
        return int(report_data.get("exit_code", 0))

    elif sub == "socket":
        action = getattr(args, "socket_action", None) or "status"
        if action == "cleanup":
            removed = runner.cleanup_sockets()
            print(f"🧹 Cleaned up {len(removed)} active ControlMaster socket(s).")
            for sock in removed:
                print(f"  ✔ Removed: {sock.name}")
            return 0
        else:
            sockets = runner.list_sockets()
            if not sockets:
                print(f"No active OpenSSH ControlMaster sockets found in {runner.socket_dir}")
                return 0
            print(f"Active OpenSSH ControlMaster sockets ({len(sockets)}):")
            for sock in sockets:
                print(f"  ✔ {sock['name']} (Path: {sock['path']})")
            return 0

    elif sub == "screens":
        from harness.remote.display_bridge import capture_fleet_screens

        raw_data = getattr(args, "data", None)
        json_data = None
        if raw_data:
            p = Path(raw_data)
            if p.is_file():
                try:
                    json_data = json.loads(p.read_text(encoding="utf-8", errors="replace"))
                except Exception as exc:
                    sys.stderr.write(f"Error parsing JSON from {p}: {exc}\n")
                    return 1
            else:
                try:
                    json_data = json.loads(raw_data)
                except Exception as exc:
                    sys.stderr.write(f"Error parsing inline JSON: {exc}\n")
                    return 1

        md_path = capture_fleet_screens(
            brain_dir=getattr(args, "brain_dir", None),
            json_data=json_data,
        )
        if getattr(args, "json", False):
            print(json.dumps({"artifact": str(md_path), "status": "ok"}, indent=2))
        else:
            print(f"✔ Fleet screens carousel generated at {md_path}")
        return 0

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


def cmd_install(args: argparse.Namespace) -> int:
    """Installs the PSL harness globally as a Google Antigravity plugin."""
    mode = DeliveryMode.COPY if getattr(args, "copy", False) else DeliveryMode.SYMLINK
    bin_dir = Path(args.bin_dir) if getattr(args, "bin_dir", None) else None
    installer = PluginInstaller(bin_dir=bin_dir)
    target_dir = Path(args.target) if getattr(args, "target", None) else None
    all_surfaces = getattr(args, "all_surfaces", False)
    result = installer.install(
        mode=mode,
        dry_run=getattr(args, "dry_run", False),
        target_dir=target_dir,
        all_surfaces=all_surfaces,
    )

    if getattr(args, "json", False):
        print(json.dumps({
            "success": result.success,
            "mode": result.mode,
            "target_dir": str(result.target_dir),
            "source_dir": str(result.source_dir),
            "items_installed": result.items_installed,
            "message": result.message,
        }, indent=2))
        return 0 if result.success else 1

    if result.success:
        print(f"✔ {result.message}")
        return 0
    else:
        sys.stderr.write(f"✘ Error: {result.message}\n")
        return 1


def cmd_uninstall(args: argparse.Namespace) -> int:
    """Uninstalls the PSL harness global plugin."""
    bin_dir = Path(args.bin_dir) if getattr(args, "bin_dir", None) else None
    installer = PluginInstaller(bin_dir=bin_dir)
    target_dir = Path(args.target) if getattr(args, "target", None) else None
    result = installer.uninstall(dry_run=getattr(args, "dry_run", False), target_dir=target_dir)

    if getattr(args, "json", False):
        print(json.dumps({
            "success": result.success,
            "mode": result.mode,
            "target_dir": str(result.target_dir),
            "source_dir": str(result.source_dir),
            "items_installed": result.items_installed,
            "message": result.message,
        }, indent=2))
        return 0 if result.success else 1

    if result.success:
        print(f"✔ {result.message}")
        return 0
    else:
        sys.stderr.write(f"✘ Error: {result.message}\n")
        return 1


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
        choices=["all", "extract", "benchmark", "classify", "inventory", "dynamics", "traces", "interventions", "volume", "deep", "session", "live"],
        help="Audit pipeline stage to run (default: all)",
    )
    p_audit.add_argument("--db", type=str, default=None, help="Path to SQLite database")
    p_audit.add_argument("--conv-dir", type=str, default=None, help="Path to conversations directory containing .db files")
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
    p_agents = subparsers.add_parser("agents", help="List, inspect, create, validate, or rehydrate specialist subagents")
    p_agents.add_argument("name", nargs="?", default=None, help="Name of specific agent to view, or action (create, validate, rehydrate)")
    p_agents.add_argument("target_name", nargs="?", default=None, help="Target agent name for create or file/name for validate/rehydrate")
    p_agents.add_argument("--sync", action="store_true", help="Sync agent definitions to .agents/agents")
    p_agents.add_argument("--json", action="store_true", help="Output agents in JSON format")
    p_agents.add_argument("--id", type=str, default=None, help="Conversation ID to rehydrate")
    p_agents.add_argument("--recent-hours", type=int, default=4, help="Recent hours window for subagent discovery")
    p_agents.add_argument("--brain-dir", type=Path, default=None, help="Custom brain directory path")
    p_agents.add_argument("--archetype", "-a", type=str, default=None, help="Agent archetype for creation (main, executioner, hammer, auditor, planner, coordinator)")
    p_agents.add_argument("--bundle", "-b", type=str, default=None, help="Capability bundle (read_only, verifier, builder, orchestrator, full)")
    p_agents.add_argument("--scope", type=str, choices=["project", "global"], default="project", help="Target scope (project or global)")
    p_agents.add_argument("--model", "-m", type=str, default="inherit", help="Model specification (default: inherit)")

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

    # remote
    p_remote = subparsers.add_parser(
        "remote", help="Remote agentic execution, script streaming & triage (ADR-027)"
    )
    p_remote_subs = p_remote.add_subparsers(dest="remote_cmd", help="Remote subcommands")

    # remote exec
    p_rexec = p_remote_subs.add_parser(
        "exec", help="Execute command on target over multiplexed SSH"
    )
    p_rexec.add_argument("target", help="Remote target (user@host or host)")
    p_rexec.add_argument("command", help="Command to execute remotely")
    p_rexec.add_argument("-p", "--port", type=int, default=None, help="SSH port")
    p_rexec.add_argument(
        "-l", "--login-shell", action="store_true", help="Wrap in login shell (bash -l -c)"
    )
    p_rexec.add_argument(
        "-t", "--timeout", type=int, default=30, help="Command timeout in seconds"
    )

    # remote script
    p_rscript = p_remote_subs.add_parser(
        "script", help="Stream or stage local script to remote target"
    )
    p_rscript.add_argument("target", help="Remote target (user@host or host)")
    p_rscript.add_argument("script", type=Path, help="Local script file to execute remotely")
    p_rscript.add_argument(
        "--stage", action="store_true", help="Stage file on remote target with trap cleanup"
    )
    p_rscript.add_argument("-p", "--port", type=int, default=None, help="SSH port")
    p_rscript.add_argument(
        "-t", "--timeout", type=int, default=60, help="Command timeout in seconds"
    )
    p_rscript.add_argument("args", nargs="*", default=[], help="Arguments to pass to script")

    # remote triage
    p_rtriage = p_remote_subs.add_parser(
        "triage", help="Run bounded diagnostic audit on remote host"
    )
    p_rtriage.add_argument("target", help="Remote target (user@host or host)")
    p_rtriage.add_argument(
        "--profile",
        choices=["all", "ports", "services", "resources", "logs"],
        default="all",
        help="Diagnostic profile filter (default: all)",
    )
    p_rtriage.add_argument(
        "--service", type=str, default=None, help="Target service name for log inspection"
    )
    p_rtriage.add_argument("-n", "--lines", type=int, default=50, help="Log line count limit")
    p_rtriage.add_argument("-p", "--port", type=int, default=None, help="SSH port")
    p_rtriage.add_argument(
        "-t", "--timeout", type=int, default=30, help="Probe timeout in seconds"
    )
    p_rtriage.add_argument("--json", action="store_true", help="Output report in JSON format")

    # remote socket
    p_rsock = p_remote_subs.add_parser(
        "socket", help="Inspect or clean up ControlMaster sockets"
    )
    p_rsock.add_argument(
        "socket_action",
        nargs="?",
        choices=["cleanup", "status"],
        default="status",
        help="Socket action to perform (default: status)",
    )

    # remote screens
    p_rscreens = p_remote_subs.add_parser(
        "screens", help="Capture and generate fleet screens carousel artifact"
    )
    p_rscreens.add_argument(
        "--brain-dir", type=Path, default=None, help="Custom brain directory path"
    )
    p_rscreens.add_argument(
        "--data", type=str, default=None, help="Path to JSON file or inline JSON with screen captures"
    )
    p_rscreens.add_argument(
        "--json", action="store_true", help="Output result in JSON format"
    )

    # auth
    p_auth = subparsers.add_parser("auth", help="Manage GitHub organization authentication for telemetry")
    auth_subs = p_auth.add_subparsers(dest="auth_cmd", help="Auth subcommands")

    p_auth_login = auth_subs.add_parser("login", help="Authenticate with GitHub Personal Access Token")
    p_auth_login.add_argument("--token", "-t", type=str, default=None, help="GitHub Personal Access Token")
    p_auth_login.add_argument("--gh", action="store_true", help="Lift token directly from GitHub CLI ('gh auth token')")
    p_auth_login.add_argument("--workspace", "-w", dest="workspace_scope", action="store_true", help="Store endpoint in workspace config (.psl/config.json)")
    p_auth_login.add_argument("--endpoint", "-e", type=str, default=None, help="Central telemetry hub endpoint URL")
    p_auth_login.add_argument("--json", action="store_true", help="Output result in JSON format")

    p_auth_status = auth_subs.add_parser("status", help="Display current telemetry authentication status")
    p_auth_status.add_argument("--json", action="store_true", help="Output status in JSON format")

    p_auth_logout = auth_subs.add_parser("logout", help="Log out and clear stored telemetry credentials")
    p_auth_logout.add_argument("--json", action="store_true", help="Output result in JSON format")

    # sync
    p_sync = subparsers.add_parser("sync", help="Synchronize telemetry with the central hub (bi-directional default)")
    p_sync.add_argument("--push", action="store_true", help="Push local unsynced telemetry to remote hub")
    p_sync.add_argument("--pull", action="store_true", help="Pull remote telemetry deltas into local database")
    p_sync.add_argument("--remote", "-r", type=str, default=None, help="Central telemetry hub endpoint URL")
    p_sync.add_argument("--db", type=str, default=None, help="Path to SQLite telemetry database")
    p_sync.add_argument("--interactive", "-i", action="store_true", help="Interactively confirm batch push")
    p_sync.add_argument("--review", action="store_true", help="Interactively review and select candidate sessions to push")
    p_sync.add_argument("--watch", action="store_true", help="Continuously watch and sync telemetry in the background")
    p_sync.add_argument("--interval", type=float, default=5.0, help="Poll interval in seconds for watch mode (default: 5.0)")
    p_sync.add_argument("--systemd", action="store_true", help="Output systemd user service unit definition")
    p_sync.add_argument("--limit", "-l", type=int, default=None, help="Maximum number of sessions to push")
    p_sync.add_argument("--dry-run", action="store_true", help="Simulate synchronization without modifications")
    p_sync.add_argument("--session-id", "-s", type=str, default=None, help="Target session ID to ingest before syncing")
    p_sync.add_argument("--json", action="store_true", help="Output sync summary in JSON format")

    # install
    p_install = subparsers.add_parser(
        "install", help="Install PSL harness globally as Google Antigravity plugin"
    )
    p_install.add_argument("--global", "-g", dest="global_install", action="store_true", help="Install standalone psl CLI into user bin path (~/.local/bin)")
    p_install.add_argument("--bin-dir", type=Path, default=None, help="Custom binary directory for standalone CLI executable")
    p_install.add_argument("--copy", action="store_true", help="Install via copy mode")
    p_install.add_argument("--symlink", action="store_true", help="Install via symlink mode (default)")
    p_install.add_argument("--dry-run", action="store_true", help="Simulate installation without writing to disk")
    p_install.add_argument("--all-surfaces", action="store_true", help="Sync all Antigravity surfaces to canonical config")
    p_install.add_argument("--target", type=Path, default=None, help="Custom target installation directory")
    p_install.add_argument("--json", action="store_true", help="Output result in JSON format")

    # uninstall
    p_uninstall = subparsers.add_parser(
        "uninstall", help="Uninstall PSL harness global plugin"
    )
    p_uninstall.add_argument("--bin-dir", type=Path, default=None, help="Custom binary directory for standalone CLI executable")
    p_uninstall.add_argument("--dry-run", action="store_true", help="Simulate uninstallation without removing files")
    p_uninstall.add_argument("--target", type=Path, default=None, help="Custom target installation directory")
    p_uninstall.add_argument("--json", action="store_true", help="Output result in JSON format")

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
    elif args.subcommand == "auth":
        return cmd_auth(args)
    elif args.subcommand == "sync":
        return cmd_sync(args)
    elif args.subcommand == "skills":
        return cmd_skills(args)
    elif args.subcommand == "agents":
        return cmd_agents(args)
    elif args.subcommand == "subagents":
        return cmd_subagents(args)
    elif args.subcommand == "remote":
        return cmd_remote(args)
    elif args.subcommand == "status":
        return cmd_status(args)
    elif args.subcommand == "install":
        return cmd_install(args)
    elif args.subcommand == "uninstall":
        return cmd_uninstall(args)

    return 0


if __name__ == "__main__":
    sys.exit(main())
