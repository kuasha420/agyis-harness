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
    "pre-invocation": "harness.hooks.pre_invocation_hook",
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
    "session-start": "pre-invocation",
    "session_start": "pre-invocation",
    "sessionstart": "pre-invocation",
    "compaction-advisory": "pre-invocation",
    "compaction_advisory": "pre-invocation",
    "compaction": "pre-invocation",
    "advisory": "pre-invocation",
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
    Determines whether the execution context represents a PreInvocation or SessionStart event
    where the protojson contract requires emitting {"injectSteps": []} instead of {"decision": "allow"}.
    """
    normalized = (hook_name or "").strip().lower().replace("_", "-")
    canonical = ALIASES.get(normalized, normalized)
    if (
        canonical in ("pre-invocation", "preinvocation", "session-start", "sessionstart")
        or "invocation" in normalized
        or "session-start" in normalized
        or "sessionstart" in normalized
        or "compaction" in normalized
        or "advisory" in normalized
    ):
        return True

    if payload_str:
        try:
            data = json.loads(payload_str)
            if isinstance(data, dict):
                event = str(data.get("hookEventName") or data.get("hookEvent") or data.get("hook_event") or data.get("event") or "").strip().lower()
                if (
                    "invocation" in event
                    or "pre-invocation" in event
                    or "preinvocation" in event
                    or "sessionstart" in event
                    or "session-start" in event
                    or "session_start" in event
                    or "compaction" in event
                    or "advisory" in event
                ):
                    return True
                if "invocationNum" in data or "invocation_num" in data:
                    return True
        except (json.JSONDecodeError, ValueError, TypeError):
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
    if normalized in ("stop", "stop-fence"):
        return False
    if canonical == "compactor" or normalized.startswith("post-"):
        return True

    if payload_str:
        try:
            data = json.loads(payload_str)
            if isinstance(data, dict):
                event = str(
                    data.get("hookEventName")
                    or data.get("hookEvent")
                    or data.get("hook_event")
                    or data.get("event")
                    or ""
                ).strip().lower()
                if "pre" in event or "stop" in event:
                    return False
                if "post" in event:
                    return True
                if (
                    "toolResponse" in data
                    or "tool_response" in data
                    or "toolOutput" in data
                    or "tool_output" in data
                    or "toolResult" in data
                    or "tool_result" in data
                ):
                    return True
                # Only treat generic keys like error/result/response/exitCode/output
                # as PostToolUse when tied to a tool call and not an explicit Stop payload.
                if (
                    data.get("action") == "evaluate_stop"
                    or "stopReason" in data
                    or "stop_reason" in data
                ):
                    return False
                has_tool_call = any(
                    k in data for k in ("toolCall", "tool_call", "toolName", "tool_name")
                )
                if has_tool_call and any(
                    k in data for k in ("error", "result", "response", "exitCode", "exit_code", "output")
                ):
                    return True
        except (json.JSONDecodeError, ValueError, TypeError):
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
                    if hasattr(sys.stdin, "buffer"):
                        raw_bytes = sys.stdin.buffer.read(10_485_760)
                        payload_str = raw_bytes.decode("utf-8", errors="replace")
                    else:
                        payload_str = sys.stdin.read(10_485_760)
                elif not hasattr(sys.stdin, "isatty"):
                    if hasattr(sys.stdin, "buffer"):
                        raw_bytes = sys.stdin.buffer.read(10_485_760)
                        payload_str = raw_bytes.decode("utf-8", errors="replace")
                    else:
                        payload_str = sys.stdin.read(10_485_760)
                else:
                    payload_str = ""
            except Exception as exc:
                sys.stderr.write(f"[AGYIS HOOK RUNNER] Failed reading stdin for '{hook_name}': {exc}\n")
                payload_str = ""
        elif isinstance(payload_str, (bytes, bytearray)):
            if len(payload_str) > 10_485_760:
                payload_str = payload_str[:10_485_760]
            payload_str = payload_str.decode("utf-8", errors="replace")
        elif isinstance(payload_str, str):
            if len(payload_str) > 10_485_760:
                payload_str = payload_str[:10_485_760]

        is_post = is_post_tool_use_context(hook_name, payload_str)
        if is_post:
            try:
                data = json.loads(payload_str) if payload_str else {}
                if isinstance(data, dict) and not any(
                    k in data for k in ("hookEventName", "hookEvent", "hook_event", "event")
                ):
                    data["hookEvent"] = "PostToolUse"
                    payload_str = json.dumps(data)
            except (json.JSONDecodeError, ValueError, TypeError):
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
            f"[AGYIS FAIL-OPEN HOOK RUNNER] Hook execution failed for '{hook_name}':\n"
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
