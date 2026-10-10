#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Purrfect Software Limited (PSL)

"""
PSL Lifecycle Hooks: Standalone Fail-Safe Runner (ADR-016 / Issue #31)

Guarantees fail-open execution for Antigravity lifecycle hooks:
- Maps hook names directly to their target modules without dependency on harness.cli.
- Catches fatal exceptions (SyntaxError, ImportError, RuntimeError) to prevent
  circular hook deadlocks when harness code is being actively modified.
- Emits fallback {"decision": "allow"} and logs diagnostic trace to sys.stderr.
"""

from __future__ import annotations

import importlib
import io
import json
from pathlib import Path
import sys
import traceback
from typing import Dict, List, Optional

HOOK_MODULES: Dict[str, str] = {
    "anti-drift": "harness.hooks.anti_drift_hook",
    "anti-loop": "harness.hooks.anti_loop_hook",
    "command-safety": "harness.hooks.command_safety_hook",
    "compactor": "harness.hooks.output_compactor_hook",
    "verification-fence": "harness.hooks.completion_fence_hook",
}

ALIASES: Dict[str, str] = {
    "drift": "anti-drift",
    "anti_drift": "anti-drift",
    "loop": "anti-loop",
    "anti_loop": "anti-loop",
    "safety": "command-safety",
    "command_safety": "command-safety",
    "output-compactor": "compactor",
    "output_compactor": "compactor",
    "completion-fence": "verification-fence",
    "fence": "verification-fence",
    "stop-fence": "verification-fence",
    "stop": "verification-fence",
}


def resolve_hook_module(hook_name: str) -> str:
    """Resolves hook name or alias to canonical module path."""
    normalized = (hook_name or "").strip().lower().replace("_", "-")
    target = ALIASES.get(normalized, normalized)
    if target in HOOK_MODULES:
        return HOOK_MODULES[target]
    raise ValueError(
        f"Unknown hook '{hook_name}'. Supported hooks: {', '.join(sorted(HOOK_MODULES.keys()))}"
    )


def run_hook(hook_name: str, payload_str: Optional[str] = None) -> int:
    """
    Executes a lifecycle hook with fail-open deadlock protection.

    If any SyntaxError, ImportError, or unhandled exception occurs while
    loading or executing the hook:
    - Logs traceback to sys.stderr
    - Emits {"decision": "allow"} on sys.stdout
    - Returns 0
    """
    old_stdin = sys.stdin
    old_stdout = sys.stdout
    stdout_buf = io.StringIO()

    try:
        module_name = resolve_hook_module(hook_name)

        if payload_str is not None:
            sys.stdin = io.StringIO(payload_str)

        try:
            sys.stdout = stdout_buf
            mod = importlib.import_module(module_name)
            if not hasattr(mod, "main") or not callable(mod.main):
                raise AttributeError(f"Hook module '{module_name}' does not expose a callable 'main()'.")
            mod.main()

            # Hook executed cleanly; flush captured output to actual stdout
            old_stdout.write(stdout_buf.getvalue())
            old_stdout.flush()
        except SystemExit as se:
            if se.code in (0, None):
                old_stdout.write(stdout_buf.getvalue())
                old_stdout.flush()
                return 0
            raise
        finally:
            sys.stdout = old_stdout
            if payload_str is not None:
                sys.stdin = old_stdin

        return 0

    except (Exception, SystemExit) as exc:
        sys.stdout = old_stdout
        if payload_str is not None:
            sys.stdin = old_stdin

        if isinstance(exc, SystemExit) and exc.code in (0, None):
            return 0

        sys.stderr.write(
            f"[PSL FAIL-OPEN HOOK RUNNER] Hook execution failed for '{hook_name}':\n"
        )
        traceback.print_exc(file=sys.stderr)
        sys.stderr.flush()

        # Emit fail-open allow decision so Antigravity never locks out tool execution
        sys.stdout.write(json.dumps({"decision": "allow"}) + "\n")
        sys.stdout.flush()
        return 0


def main(argv: Optional[List[str]] = None) -> int:
    """CLI entrypoint for standalone fail-safe hook runner."""
    if argv is None:
        argv = sys.argv[1:]

    if not argv:
        sys.stderr.write("Usage: python3 -m harness.hooks.runner <hook_name>\n")
        sys.stdout.write(json.dumps({"decision": "allow"}) + "\n")
        sys.stdout.flush()
        return 0

    hook_name = argv[0]
    return run_hook(hook_name)


if __name__ == "__main__":
    sys.exit(main())
