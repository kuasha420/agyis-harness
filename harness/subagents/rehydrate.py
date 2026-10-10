# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Purrfect Software Limited (PSL)

"""
Subagent Session Rehydration (ADR-025).
"""

from __future__ import annotations

import json
import os
from pathlib import Path
import re
from typing import Any, Dict, List, Optional

from harness.subagents.context import extract_role_from_text


class StepSummary(dict):
    """Step information that behaves as a dictionary and compares equal to its step_index."""

    def __int__(self) -> int:
        return int(self.get("step_index", 0))

    def __eq__(self, other: Any) -> bool:
        if isinstance(other, int):
            return self.get("step_index", 0) == other
        return super().__eq__(other)


def rehydrate_subagent_session(
    conv_id: str,
    brain_dir: Optional[Path] = None,
) -> Dict[str, Any]:
    """
    Inspects subagent session transcript to reconstruct state after crash or completion.

    Detects:
    - Status: REHYDRATED_COMPLETED, REHYDRATED_INTERRUPTED, or REHYDRATED_FAILED.
    - Role, prompt, completed files, diffs, and last step details.

    Args:
        conv_id: Conversation / session identifier, directory name, or transcript file path.
        brain_dir: Optional brain directory. Defaults to environment or ~/.gemini/antigravity/brain.

    Returns:
        Structured rehydration dictionary.
    """
    b_dir = brain_dir or Path(
        os.environ.get(
            "ANTIGRAVITY_BRAIN_DIR",
            os.environ.get(
                "GEMINI_BRAIN_DIR", Path.home() / ".gemini" / "antigravity" / "brain"
            ),
        )
    )

    t_path: Optional[Path] = None
    target_conv_id = conv_id

    # 1. Check if conv_id is already a direct file path
    direct_path = Path(conv_id)
    if direct_path.is_file():
        t_path = direct_path
        target_conv_id = direct_path.parent.name
        if target_conv_id in ("logs", ".system_generated"):
            parts = direct_path.parts
            if ".system_generated" in parts:
                idx = parts.index(".system_generated")
                if idx > 0:
                    target_conv_id = parts[idx - 1]
    elif direct_path.is_dir():
        cand1 = direct_path / ".system_generated" / "logs" / "transcript.jsonl"
        cand2 = direct_path / "transcript.jsonl"
        cand3 = direct_path / ".system_generated" / "logs" / "transcript_full.jsonl"
        if cand1.is_file():
            t_path = cand1
        elif cand2.is_file():
            t_path = cand2
        elif cand3.is_file():
            t_path = cand3
        target_conv_id = direct_path.name
    else:
        # Search within brain_dir
        cand_dir = b_dir / conv_id
        if cand_dir.is_dir():
            cand1 = cand_dir / ".system_generated" / "logs" / "transcript.jsonl"
            cand2 = cand_dir / "transcript.jsonl"
            cand3 = cand_dir / ".system_generated" / "logs" / "transcript_full.jsonl"
            if cand1.is_file():
                t_path = cand1
            elif cand2.is_file():
                t_path = cand2
            elif cand3.is_file():
                t_path = cand3
        else:
            # Prefix or fuzzy search in b_dir
            if b_dir.exists() and b_dir.is_dir():
                for item in b_dir.iterdir():
                    if item.is_dir() and item.name.startswith(conv_id):
                        cand1 = item / ".system_generated" / "logs" / "transcript.jsonl"
                        cand2 = item / "transcript.jsonl"
                        if cand1.is_file():
                            t_path = cand1
                            target_conv_id = item.name
                            break
                        elif cand2.is_file():
                            t_path = cand2
                            target_conv_id = item.name
                            break

    if not t_path or not t_path.is_file():
        raise FileNotFoundError(
            f"Session transcript not found for conversation '{conv_id}' in brain dir '{b_dir}'"
        )

    # 2. Parse transcript lines
    steps: List[Dict[str, Any]] = []
    try:
        with open(t_path, "r", encoding="utf-8", errors="replace") as f:
            for line in f:
                s_line = line.strip()
                if not s_line:
                    continue
                try:
                    steps.append(json.loads(s_line))
                except (json.JSONDecodeError, ValueError):
                    continue
    except OSError as exc:
        raise FileNotFoundError(f"Failed to read transcript at {t_path}: {exc}") from exc

    if not steps:
        empty_last = StepSummary({"step_index": 0, "status": "EMPTY", "content": ""})
        return {
            "conversation_id": target_conv_id,
            "status": "REHYDRATED_FAILED",
            "role": "unknown",
            "prompt": "",
            "completed_files": [],
            "diffs": [],
            "last_step": empty_last,
            "last_step_index": 0,
            "step_count": 0,
            "tool_calls_count": 0,
            "error": "Empty transcript file",
        }

    # 3. Extract role, prompt, completed files, and diffs
    detected_role = ""
    prompt_text = ""
    completed_files: List[str] = []
    diffs: List[str] = []
    total_tool_calls = 0
    has_send_message = False

    for s in steps:
        content = str(s.get("content", ""))

        # Role extraction
        if not detected_role:
            r_val = s.get("role") or s.get("Role") or ""
            if str(r_val).strip().lower() not in ("user", "assistant", "system", "tool", "model"):
                detected_role = str(r_val).strip()
            if not detected_role:
                detected_role = extract_role_from_text(content) or ""

        # Prompt extraction
        if not prompt_text:
            s_type = str(s.get("type", ""))
            s_source = str(s.get("source", ""))
            if "<USER_REQUEST>" in content:
                m_req = re.search(r"<USER_REQUEST>([\s\S]*?)</USER_REQUEST>", content)
                if m_req:
                    prompt_text = m_req.group(1).strip()
            elif s_type == "USER_INPUT" or s_source == "USER_EXPLICIT":
                clean_p = re.sub(
                    r"<ADDITIONAL_METADATA>[\s\S]*?</ADDITIONAL_METADATA>",
                    "",
                    content,
                ).strip()
                if clean_p and not clean_p.startswith("<subagent_reminder>"):
                    prompt_text = clean_p

        # Tool calls & modifications
        raw_tools = s.get("tool_calls", [])
        if isinstance(raw_tools, list):
            for tc in raw_tools:
                if not isinstance(tc, dict):
                    continue
                total_tool_calls += 1
                t_name = str(tc.get("name", ""))
                t_args = tc.get("args", {})
                if not isinstance(t_args, dict):
                    t_args = {}

                if t_name == "send_message":
                    has_send_message = True

                if t_name in ("write_to_file", "replace_file_content", "edit_file"):
                    tf = str(
                        t_args.get("TargetFile")
                        or t_args.get("file_path")
                        or t_args.get("path")
                        or ""
                    ).strip()
                    if tf and tf not in completed_files:
                        completed_files.append(tf)

                    if t_name == "replace_file_content":
                        target_c = str(t_args.get("TargetContent", ""))
                        repl_c = str(t_args.get("ReplacementContent", ""))
                        diffs.append(
                            f"--- {tf}\n+++ {tf}\n- {target_c}\n+ {repl_c}"
                        )
                    elif t_name == "write_to_file":
                        diffs.append(f"+++ {tf} (created/written)")

    # 4. Status determination & last step synthesis
    last_dict = steps[-1]
    last_idx = int(last_dict.get("step_index", len(steps)))
    raw_status = str(last_dict.get("status", "")).strip().upper()
    content_last = str(last_dict.get("content", ""))
    error_msg = str(last_dict.get("error", "")).strip()

    status = "REHYDRATED_COMPLETED"

    if raw_status in ("FAILED", "ERROR", "REHYDRATED_FAILED"):
        status = "REHYDRATED_FAILED"
        if not error_msg:
            error_msg = f"Step status: {raw_status}"
    elif raw_status in ("INTERRUPTED", "CANCELLED", "ABORTED", "REHYDRATED_INTERRUPTED"):
        status = "REHYDRATED_INTERRUPTED"
    elif error_msg:
        status = "REHYDRATED_FAILED"
    elif "traceback (most recent call last)" in content_last.lower():
        status = "REHYDRATED_FAILED"
        error_msg = "Fatal exception traceback detected in last step"
    elif has_send_message or raw_status in ("COMPLETED", "SUCCESS", "REHYDRATED_COMPLETED"):
        status = "REHYDRATED_COMPLETED"
    elif last_dict.get("tool_calls") and not (
        last_dict.get("tool_result") or last_dict.get("output") or len(steps) > last_idx
    ):
        # Truncated or interrupted right at tool invocation without receiving tool execution output
        status = "REHYDRATED_INTERRUPTED"
    elif any(
        kw in content_last.lower()
        for kw in (
            "task complete",
            "execution complete",
            "all tests pass",
            "passed",
            "finished",
            "lgtm",
            "success",
        )
    ):
        status = "REHYDRATED_COMPLETED"
    elif len(steps) == 1 and not last_dict.get("tool_calls"):
        status = "REHYDRATED_INTERRUPTED"
    elif raw_status == "RUNNING" or raw_status == "IN_PROGRESS":
        status = "REHYDRATED_INTERRUPTED"

    last_summary = StepSummary({
        "step_index": last_idx,
        "status": raw_status or status,
        "type": last_dict.get("type", "UNKNOWN"),
        "content": content_last[:500],
    })

    return {
        "conversation_id": target_conv_id,
        "status": status,
        "role": detected_role or "subagent",
        "prompt": prompt_text,
        "completed_files": completed_files,
        "diffs": diffs,
        "last_step": last_summary,
        "last_step_index": last_idx,
        "step_count": len(steps),
        "tool_calls_count": total_tool_calls,
        "error": error_msg,
    }
