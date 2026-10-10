#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Purrfect Software Limited (PSL)

"""
PSL Harness: PostToolUse Output Compactor & Telemetry Analyzer

Implements a smart 2KB compaction algorithm for tool execution outputs:
- Passes outputs <= 2048 chars unmodified.
- For outputs > 2048 chars:
  - If tool failed (exit_code != 0 or error present), preserves full diagnostic output.
  - If tool succeeded (exit_code == 0), preserves:
    1. First 500 characters (head context)
    2. Last 1,000 characters (tail/completion status)
    3. All lines in omitted middle containing exit code, fatal, error, or failure keywords.
- Caches compacted output and compaction metadata in /tmp/psl_agy_harness_state/.
- Emits valid JSON `{}` on stdout per the official Antigravity PostToolUse contract.
"""

from __future__ import annotations

from datetime import datetime, timezone
import json
import os
from pathlib import Path
import re
import sys
from typing import Any, Dict, List, Optional, Tuple

# Configuration Constants
MAX_OUTPUT_CHARS = 2048
HEAD_CHARS = 500
TAIL_CHARS = 1000
ERROR_KEYWORDS = ("exit code", "exit_code", "fatal", "error", "failure", "failed")

STATE_DIR = Path(os.environ.get("PSL_HARNESS_STATE_DIR", "/tmp/psl_agy_harness_state"))


def compact_output(
    output: Optional[str],
    exit_code: int = 0,
    is_error: bool = False,
    max_chars: int = MAX_OUTPUT_CHARS,
    head_chars: int = HEAD_CHARS,
    tail_chars: int = TAIL_CHARS,
) -> str:
    """
    Compacts tool output if it exceeds max_chars and the tool invocation succeeded.

    If exit_code != 0 or is_error is True, the full output is preserved unmodified.
    If len(output) <= max_chars, output is preserved unmodified.

    Returns:
        Compacted output string (or original string if not compacted).
    """
    if output is None:
        return ""
    if not isinstance(output, str):
        output = str(output)

    # Invariant: Failing output (non-zero exit code) -> full error preserved
    if exit_code != 0 or is_error:
        return output

    # Small output (<2KB) -> passed unmodified
    if len(output) <= max_chars:
        return output

    # If output is too short for head + tail separation, return unmodified
    if len(output) <= (head_chars + tail_chars):
        return output

    head = output[:head_chars]
    tail = output[-tail_chars:]
    middle = output[head_chars:-tail_chars]

    # Preserve all lines in middle containing error, fatal, failure, or exit code keywords
    middle_lines = middle.splitlines()
    preserved_diagnostic_lines: List[str] = [
        line.strip()
        for line in middle_lines
        if line.strip() and any(kw in line.lower() for kw in ERROR_KEYWORDS)
    ]

    omitted_chars = len(middle)

    if preserved_diagnostic_lines:
        diagnostic_block = "\n".join(preserved_diagnostic_lines)
        separator = (
            f"\n\n[... PSL Compactor: {omitted_chars:,} characters truncated | "
            f"{len(preserved_diagnostic_lines)} diagnostic lines preserved ...]\n"
            f"{diagnostic_block}\n"
            f"[... End preserved diagnostics ...]\n\n"
        )
    else:
        separator = f"\n\n[... PSL Compactor: {omitted_chars:,} characters truncated ...]\n\n"

    return f"{head}{separator}{tail}"


def extract_output_and_status(payload: Dict[str, Any]) -> Tuple[str, int, bool]:
    """
    Extracts output string, exit code, and error status from a PostToolUse payload.
    Supports payload fields:
      - output, toolOutput, content, toolResponse, result, stdout
      - error string or object
      - exitCode, exit_code
      - transcriptPath fallback
    """
    raw_output = ""
    for key in ("output", "toolOutput", "content", "toolResponse", "result", "stdout"):
        val = payload.get(key)
        if val is not None:
            if isinstance(val, dict):
                raw_output = str(val.get("content") or val.get("output") or json.dumps(val))
            else:
                raw_output = str(val)
            if raw_output:
                break

    # If output not directly in payload, attempt transcript lookup
    if not raw_output and payload.get("transcriptPath"):
        t_path = Path(payload["transcriptPath"])
        step_idx = payload.get("stepIdx") or payload.get("step_index")
        if t_path.exists() and step_idx is not None:
            try:
                with open(t_path, encoding="utf-8", errors="replace") as f:
                    for line in f:
                        if not line.strip():
                            continue
                        step_data = json.loads(line)
                        s_idx = step_data.get("step_index")
                        # Tool output is either at step_idx or step_idx + 1
                        if s_idx in (step_idx, step_idx + 1) and step_data.get("content"):
                            raw_output = str(step_data["content"])
                            break
            except Exception:
                pass

    # Status and exit code detection
    exit_code = 0
    is_error = False

    # 1. Explicit exit code
    for code_key in ("exitCode", "exit_code"):
        if code_key in payload and payload[code_key] is not None:
            try:
                exit_code = int(payload[code_key])
                if exit_code != 0:
                    is_error = True
            except (ValueError, TypeError):
                pass

    # 2. Error field in payload
    error_val = payload.get("error")
    if error_val:
        is_error = True
        err_str = str(error_val)
        m = re.search(r"(?:exit status|exit code|code)\s*[:=]?\s*(\d+)", err_str, re.I)
        if m:
            exit_code = int(m.group(1))
        elif exit_code == 0:
            exit_code = 1

    # 3. Status string
    status = str(payload.get("status", "")).upper()
    if status in ("ERROR", "FAILED"):
        is_error = True
        if exit_code == 0:
            exit_code = 1

    # 4. Content-based exit code detection
    if raw_output:
        m_exit = re.search(r"(?:failed with exit code|exited with code)\s*[:=]?\s*(\d+)", raw_output, re.I)
        if m_exit:
            code = int(m_exit.group(1))
            if code != 0:
                exit_code = code
                is_error = True
        elif "Encountered error in tool execution:" in raw_output:
            is_error = True
            if exit_code == 0:
                exit_code = 1

    return raw_output, exit_code, is_error


def process_payload(payload: Dict[str, Any], state_dir: Optional[Path] = None) -> Dict[str, Any]:
    """
    Processes the hook payload, executes compaction, caches state, and returns metrics.
    """
    target_state_dir = state_dir or STATE_DIR
    conv_id = str(payload.get("conversationId") or "default")
    step_idx = payload.get("stepIdx", payload.get("step_index", 0))
    tool_call = payload.get("toolCall", {})
    tool_name = tool_call.get("name", "unknown") if isinstance(tool_call, dict) else "unknown"

    raw_output, exit_code, is_error = extract_output_and_status(payload)
    compacted = compact_output(raw_output, exit_code=exit_code, is_error=is_error)

    was_compacted = len(compacted) < len(raw_output)
    saved_chars = max(0, len(raw_output) - len(compacted))

    record = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "conversationId": conv_id,
        "stepIdx": step_idx,
        "toolName": tool_name,
        "originalChars": len(raw_output),
        "compactedChars": len(compacted),
        "savedChars": saved_chars,
        "wasCompacted": was_compacted,
        "exitCode": exit_code,
        "isError": is_error,
        "compactedOutput": compacted,
    }

    # Cache state and diagnostics safely
    try:
        target_state_dir.mkdir(parents=True, exist_ok=True)
        # Write latest compaction metadata
        (target_state_dir / f"compactor_{conv_id}.json").write_text(
            json.dumps(record, indent=2), encoding="utf-8"
        )
        (target_state_dir / "last_compaction.json").write_text(
            json.dumps(record, indent=2), encoding="utf-8"
        )

        # Write compacted output if compacted or needed for inspection
        if was_compacted:
            (target_state_dir / f"compacted_{conv_id}_{step_idx}.txt").write_text(
                compacted, encoding="utf-8"
            )
            (target_state_dir / "last_compacted_output.txt").write_text(
                compacted, encoding="utf-8"
            )

        # Append to diagnostic log
        log_line = (
            f"[{record['timestamp']}] [{conv_id}] Step {step_idx} ({tool_name}): "
            f"{len(raw_output)} -> {len(compacted)} chars (saved {saved_chars}, "
            f"exit={exit_code}, compacted={was_compacted})\n"
        )
        with open(target_state_dir / "compactor_diagnostics.log", "a", encoding="utf-8") as f:
            f.write(log_line)
    except Exception:
        pass

    return record


def main() -> None:
    """CLI hook entrypoint adhering to the official PostToolUse contract."""
    try:
        raw_stdin = sys.stdin.read()
        if not raw_stdin.strip():
            print(json.dumps({}))
            return
        payload = json.loads(raw_stdin)
        if not isinstance(payload, dict):
            print(json.dumps({}))
            return
        process_payload(payload)
    except Exception:
        pass

    # PostToolUse contract expects an empty JSON object
    print(json.dumps({}))


if __name__ == "__main__":
    main()
