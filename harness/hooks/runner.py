#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Arafat Zahan (@kuasha420)
# Corporate Stewardship & Infrastructure: Purrfect Software Limited (PSL)
# Governed by: ICARO-42/b Ordinance (Company-Supported Personal IP Framework)

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
    "token-proximity": "harness.hooks.token_proximity_guard",
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
    "token-proximity": "token-proximity",
    "token_proximity": "token-proximity",
    "token-guard": "token-proximity",
    "token_guard": "token-proximity",
    "token-proximity-guard": "token-proximity",
    "token_proximity_guard": "token-proximity",
    "token": "token-proximity",
    "post-verification-fence": "verification-fence",
    "post_verification_fence": "verification-fence",
    "post-fence": "verification-fence",
    "post_fence": "verification-fence",
    "pre-invocation": "pre-invocation",
    "pre_invocation": "pre-invocation",
    "preinvocation": "pre-invocation",
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


def is_pre_invocation_context(hook_name: str, payload_str: Optional[str] = None) -> bool:
    """
    Determines whether the execution context represents a PreInvocation event
    where the protojson contract requires emitting {"injectSteps": []} instead of {"decision": "allow"}.
    """
    normalized = (hook_name or "").strip().lower().replace("_", "-")
    canonical = ALIASES.get(normalized, normalized)
    if canonical in ("pre-invocation", "preinvocation") or "invocation" in normalized:
        return True

    if payload_str:
        try:
            data = json.loads(payload_str)
            if isinstance(data, dict):
                event = str(data.get("hookEvent") or data.get("hook_event") or data.get("event") or "").strip().lower()
                if "invocation" in event or "pre-invocation" in event or "preinvocation" in event:
                    return True
                if "invocationNum" in data or "invocation_num" in data:
                    return True
        except Exception:
            pass

    return False


def is_post_tool_use_context(hook_name: str, payload_str: Optional[str] = None) -> bool:
    """
    Determines whether the execution context represents a PostToolUse event
    where the protojson contract requires emitting {} instead of {"decision": "allow"}.
    """
    if is_pre_invocation_context(hook_name, payload_str):
        return False

    normalized = (hook_name or "").strip().lower().replace("_", "-")
    canonical = ALIASES.get(normalized, normalized)
    if canonical == "compactor" or normalized.startswith("post-"):
        return True

    if payload_str:
        try:
            data = json.loads(payload_str)
            if isinstance(data, dict):
                event = str(data.get("hookEvent") or data.get("hook_event") or data.get("event") or "").strip().lower()
                if "pre" in event:
                    return False
                if "post" in event:
                    return True
                if "error" in data:
                    return True
                if (
                    "toolResponse" in data
                    or "tool_response" in data
                    or "toolOutput" in data
                    or "tool_output" in data
                    or "toolResult" in data
                    or "tool_result" in data
                    or "result" in data
                    or "response" in data
                ):
                    return True
                if "exitCode" in data or "exit_code" in data or "output" in data:
                    return True
        except Exception:
            pass

    return False


def run_hook(hook_name: str, payload_str: Optional[str] = None) -> int:
    """
    Executes a lifecycle hook with fail-open deadlock protection.

    If any SyntaxError, ImportError, or unhandled exception occurs while
    loading or executing the hook:
    - Logs traceback to sys.stderr
    - Emits {} for PostToolUse events, or {"decision": "allow"} for PreToolUse/Stop
    - Returns 0
    """
    old_stdin = sys.stdin
    old_stdout = sys.stdout
    stdout_buf = io.StringIO()

    try:
        module_name = resolve_hook_module(hook_name)

        if payload_str is None:
            try:
                if hasattr(sys.stdin, "isatty") and not sys.stdin.isatty():
                    payload_str = sys.stdin.read()
                elif not hasattr(sys.stdin, "isatty"):
                    payload_str = sys.stdin.read()
                else:
                    payload_str = ""
            except Exception:
                payload_str = ""

        is_post = is_post_tool_use_context(hook_name, payload_str)
        if is_post:
            try:
                data = json.loads(payload_str) if payload_str else {}
                if isinstance(data, dict) and "hookEvent" not in data and "event" not in data:
                    data["hookEvent"] = "PostToolUse"
                    payload_str = json.dumps(data)
            except Exception:
                pass

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
            sys.stdin = old_stdin

        return 0

    except (Exception, SystemExit) as exc:
        sys.stdout = old_stdout
        sys.stdin = old_stdin

        if isinstance(exc, SystemExit) and exc.code in (0, None):
            return 0

        sys.stderr.write(
            f"[PSL FAIL-OPEN HOOK RUNNER] Hook execution failed for '{hook_name}':\n"
        )
        traceback.print_exc(file=sys.stderr)
        sys.stderr.flush()

        # Emit fail-open response tailored to hook event type
        if is_pre_invocation_context(hook_name, payload_str):
            sys.stdout.write(json.dumps({"injectSteps": []}) + "\n")
        elif is_post_tool_use_context(hook_name, payload_str):
            sys.stdout.write(json.dumps({}) + "\n")
        else:
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
