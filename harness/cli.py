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
from harness.hooks import anti_loop_hook, command_safety_hook, output_compactor_hook
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
    else:
        sys.stderr.write(
            f"Error: Unknown hook '{args.hook_name}'. "
            "Supported hooks: command-safety, anti-loop, output-compactor\n"
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

    return 0 if result.wasSuccessful() else 1


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
    else:
        sys.stderr.write(f"Error: Unknown audit stage '{sub}'.\n")
        return 1

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
        except Exception:
            print(f" Telemetry DB:    {DEFAULT_DB.name} (present)")
    else:
        print(" Telemetry DB:    Not initialized")

    print("-" * 70)
    print(" Active Lifecycle Hooks:")
    print("   ✔ command-safety   (PreToolUse: CPython 3.12, f-string, grep sanitization)")
    print("   ✔ anti-loop        (PreToolUse: repetitive tool call breaker)")
    print("   ✔ output-compactor (PostToolUse: deterministic 2KB output truncation)")
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
        choices=["command-safety", "safety", "anti-loop", "loop", "output-compactor", "compactor"],
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
        choices=["all", "extract", "classify", "inventory", "dynamics", "traces", "interventions"],
        help="Audit pipeline stage to run (default: all)",
    )

    # status / info
    subparsers.add_parser("status", help="Print harness installation and health summary")

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
    elif args.subcommand == "status":
        return cmd_status(args)

    return 0


if __name__ == "__main__":
    sys.exit(main())
