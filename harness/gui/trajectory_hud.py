# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Arafat Zahan (@kuasha420)
# Corporate Stewardship & Infrastructure: Purrfect Software Limited (PSL)
# Governed by: ICARO-42/b Ordinance (Company-Supported Personal IP Framework)

"""
Cleanroom In-Situ Trajectory Debug View HUD Generator (ADR-014 / PSL-INV-007).
Reimplements the Trajectory Debug View reverse-engineered from Google Antigravity 2.26.0
using in-situ DOM injection over the Chromium DevTools Protocol (CDP).
"""

from __future__ import annotations

import importlib.resources
import json
import os
from pathlib import Path
import re
from typing import Any, Dict, List, Optional, Set


def _map_to_cortex_type(step: Dict[str, Any]) -> str:
    """Maps a transcript step to standard Google Antigravity Cortex step types."""
    existing_type = step.get("type")
    tool_calls = step.get("tool_calls", [])
    source = str(step.get("source") or "").lower()
    role = str(step.get("role") or "").lower()
    content = str(step.get("content") or "")
    step_case = str(step.get("case") or step.get("step", {}).get("case") or "").lower()

    # Checkpoint detection from compaction summaries or step cases
    if (
        existing_type == "CHECKPOINT"
        or step_case == "checkpoint"
        or "<context_summary>" in content.lower()
        or "<summary>" in content.lower()
        or step.get("checkpoint") is not None
        or step.get("sessionSummary") is not None
        or step.get("userIntent") is not None
    ):
        return "CHECKPOINT"

    if existing_type and existing_type in (
        "PLANNER_RESPONSE", "USER_INPUT", "RUN_COMMAND", "VIEW_FILE",
        "REPLACE_FILE_CONTENT", "WRITE_FILE", "GREP_SEARCH", "FIND_FILES",
        "SEND_MESSAGE", "INVOKE_SUBAGENT", "MODEL_OUTPUT", "SYSTEM", "TOOL_CALL",
        "CHECKPOINT", "CODE_ACTION",
    ):
        return existing_type

    if step.get("runCommand") is not None or step_case == "runcommand":
        return "RUN_COMMAND"
    if step.get("viewFile") is not None or step_case == "viewfile":
        return "VIEW_FILE"
    if step.get("codeAction") is not None or step_case == "codeaction":
        return "CODE_ACTION"
    if step.get("invokeSubagent") is not None or step_case == "invokesubagent":
        return "INVOKE_SUBAGENT"

    if source == "user" or role == "user":
        return "USER_INPUT"
    if source == "system" or role == "system":
        return "SYSTEM"

    if tool_calls:
        first_tc = str(tool_calls[0].get("name", "")).lower()
        if "run_command" in first_tc:
            return "RUN_COMMAND"
        if "view_file" in first_tc:
            return "VIEW_FILE"
        if "replace_file_content" in first_tc:
            return "REPLACE_FILE_CONTENT"
        if "write_to_file" in first_tc:
            return "WRITE_FILE"
        if "grep_search" in first_tc:
            return "GREP_SEARCH"
        if "find_by_name" in first_tc or "find_files" in first_tc:
            return "FIND_FILES"
        if "send_message" in first_tc:
            return "SEND_MESSAGE"
        if "invoke_subagent" in first_tc or "subagent" in first_tc:
            return "INVOKE_SUBAGENT"
        return "TOOL_CALL"

    if step.get("thinking"):
        return "PLANNER_RESPONSE"
    if source in ("model", "assistant") or role in ("model", "assistant"):
        return "MODEL_OUTPUT"
    return existing_type or "STEP"


def _extract_compaction_summary(step: Dict[str, Any]) -> Optional[str]:
    """Extracts compaction summary from checkpoint step or xml summary blocks."""
    if step.get("checkpoint"):
        cp = step["checkpoint"]
        if isinstance(cp, dict):
            s = cp.get("sessionSummary") or cp.get("userIntent") or cp.get("summary")
            if s:
                return str(s).strip()
        elif isinstance(cp, str):
            return cp.strip()
    if step.get("sessionSummary"):
        return str(step["sessionSummary"]).strip()
    if step.get("userIntent"):
        return str(step["userIntent"]).strip()

    step_obj = step.get("step")
    if isinstance(step_obj, dict):
        val = step_obj.get("value")
        if isinstance(val, dict):
            s = val.get("sessionSummary") or val.get("userIntent") or val.get("summary")
            if s:
                return str(s).strip()

    for field in ("content", "thinking"):
        val = str(step.get(field) or "")
        m = re.search(r"<(?:CONTEXT_SUMMARY|summary)>([\s\S]*?)</(?:CONTEXT_SUMMARY|summary)>", val, re.I)
        if m:
            return m.group(1).strip()

    return None


def estimate_tokens(char_count: int) -> int:
    """Estimates token count from character count using authoritative 2.26.0 ratio (char_count / 3.5)."""
    return round(char_count / 3.5) if char_count > 0 else 0


def xtc_segment_width(segment_tokens: int, px_per_token: float, min_segment_px: float = 2.0) -> float:
    """Calculates pixel width for a segment with minimum pixel clamp (cleanroom xtc)."""
    tok = max(0, segment_tokens)
    return max(tok * px_per_token, min_segment_px) if tok > 0 else 0.0


def ytc_layout_pass(
    segments: List[Dict[str, Any]],
    capacity_tokens: int,
    container_width: float,
    min_segment_px: float = 2.0,
    rows_count: int = 1,
) -> Dict[str, float]:
    """Calculates layout metrics and inflation for a given row count (cleanroom ytc)."""
    capacity_px = container_width * rows_count
    px_per_token = capacity_px / capacity_tokens if capacity_tokens > 0 else 0.0
    used_px = 0.0
    true_used_px = 0.0
    for s in segments:
        tok = s.get("tokens", 0)
        used_px += xtc_segment_width(tok, px_per_token, min_segment_px)
        true_used_px += max(0, tok) * px_per_token
    return {
        "capacity_px": capacity_px,
        "px_per_token": px_per_token,
        "used_px": used_px,
        "true_used_px": true_used_px,
        "inflation_px": used_px - true_used_px,
    }


def ztc_row_count(
    segments: List[Dict[str, Any]],
    capacity_tokens: int,
    container_width: float,
    min_segment_px: float = 2.0,
    max_rows: int = 8,
) -> int:
    """Determines optimal row count to minimize inflation (cleanroom ztc)."""
    current = ytc_layout_pass(segments, capacity_tokens, container_width, min_segment_px, 1)
    for r in range(1, max_rows):
        if current["inflation_px"] <= 0.1 * current["true_used_px"]:
            return r
        next_pass = ytc_layout_pass(segments, capacity_tokens, container_width, min_segment_px, r + 1)
        if current["inflation_px"] - next_pass["inflation_px"] < 0.02 * container_width:
            return r
        current = next_pass
    return max_rows


def atc_context_layout(
    segments: List[Dict[str, Any]],
    capacity_tokens: int,
    container_width: float,
    min_segment_px: float = 2.0,
    max_rows: int = 8,
) -> Dict[str, Any]:
    """Authoritative dynamic context bar sizing and multi-row layout algorithm (cleanroom Atc)."""
    if not segments or capacity_tokens <= 0 or container_width <= 0:
        return {"rows": [], "inflation_px": 0.0}

    row_count = ztc_row_count(segments, capacity_tokens, container_width, min_segment_px, max_rows)
    layout = ytc_layout_pass(segments, capacity_tokens, container_width, min_segment_px, row_count)
    scale_factor = layout["capacity_px"] / layout["used_px"] if layout["used_px"] > layout["capacity_px"] else 1.0

    segment_widths = [
        xtc_segment_width(s.get("tokens", 0), layout["px_per_token"], min_segment_px) * scale_factor
        for s in segments
    ]
    unused_px = max(0.0, layout["capacity_px"] - layout["used_px"] * scale_factor)

    rows: List[List[Dict[str, Any]]] = [[] for _ in range(row_count)]
    cursor_px = 0.0

    def place_cell(seg: Optional[Dict[str, Any]], width_px: float, key_prefix: str, show_divider: bool) -> None:
        nonlocal cursor_px
        rem_width = width_px
        sub_idx = 0
        while rem_width > 1e-6:
            row_idx = min(len(rows) - 1, int((cursor_px + 1e-6) // container_width))
            row_start_px = cursor_px - row_idx * container_width
            avail_in_row = container_width - row_start_px
            if avail_in_row <= 1e-6:
                break

            slice_width = min(rem_width, avail_in_row)
            rem_width -= slice_width
            cursor_px += slice_width

            is_done = rem_width <= 1e-6
            fills_row = slice_width >= avail_in_row - 1e-6

            rows[row_idx].append({
                "key": f"{key_prefix}#{sub_idx}",
                "segment": seg,
                "start_fraction": row_start_px / container_width,
                "width_fraction": slice_width / container_width,
                "continues_from_previous_row": sub_idx > 0,
                "continues_on_next_row": not is_done,
                "show_divider_after": show_divider and is_done and not fills_row,
            })
            sub_idx += 1

    for idx, seg in enumerate(segments):
        next_seg = segments[idx + 1] if idx + 1 < len(segments) else None
        show_div = next_seg is not None and next_seg.get("color_key") == seg.get("color_key")
        place_cell(seg, segment_widths[idx], f"{idx}:{seg.get('id', idx)}", show_div)

    if unused_px > 1e-6:
        place_cell(None, unused_px, "unused", False)

    return {"rows": rows, "inflation_px": layout["inflation_px"] * scale_factor}


def _extract_conversation_summary(convo_dir: Path, transcript_path: Path) -> str:
    """Extracts a short human-readable summary for a conversation."""
    meta_path = convo_dir / "meta.json"
    if meta_path.is_file():
        try:
            with open(meta_path, "r", encoding="utf-8", errors="replace") as f:
                data = json.load(f)
                summary = data.get("summary") or data.get("title")
                if summary:
                    return str(summary).strip()
        except (json.JSONDecodeError, OSError, ValueError, KeyError):
            pass

    if transcript_path.is_file():
        try:
            with open(transcript_path, "r", encoding="utf-8", errors="replace") as f:
                for line in f:
                    line = line.strip()
                    if line:
                        try:
                            s = json.loads(line)
                            source = str(s.get("source") or s.get("role") or "").lower()
                            if source == "user" and s.get("content"):
                                first_line = str(s["content"]).strip().splitlines()[0]
                                return first_line[:60]
                        except (json.JSONDecodeError, UnicodeDecodeError, ValueError, KeyError):
                            continue
        except OSError:
            pass

    return f"Session {convo_dir.name[:8]}"


def load_conversation_trajectory(
    conversation_id: str,
    brain_dir: Optional[Path] = None,
    _visited: Optional[Set[str]] = None,
    parent_id: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Loads trajectory steps, timing metrics, and hierarchical direct child subagents directly from disk.
    Enforces 0ms in-memory subagent pre-bundling and Cortex data parity with Antigravity 2.26.0.
    """
    if _visited is None:
        _visited = set()
    _visited.add(conversation_id)

    base_brain = brain_dir or (Path.home() / ".gemini" / "antigravity" / "brain")
    convo_dir = base_brain / conversation_id

    transcript_path = convo_dir / ".system_generated" / "logs" / "transcript.jsonl"
    if not transcript_path.is_file():
        transcript_path = convo_dir / "transcript.jsonl"

    raw_steps: List[Dict[str, Any]] = []
    raw_line_sizes: List[int] = []
    if transcript_path.is_file():
        try:
            with open(transcript_path, "r", encoding="utf-8", errors="replace") as f:
                for line in f:
                    line_str = line.strip()
                    if line_str:
                        try:
                            parsed = json.loads(line_str)
                            raw_steps.append(parsed)
                            raw_line_sizes.append(len(line.encode("utf-8")))
                        except (json.JSONDecodeError, UnicodeDecodeError, ValueError):
                            continue
        except OSError:
            pass

    resolved_parent_id: Optional[str] = parent_id
    subagents: List[str] = []
    subagent_infos: List[Dict[str, Any]] = []

    # Check for direct child subagent invocations (strictly invoke_subagent calls)
    for idx, step in enumerate(raw_steps):
        # 1. Standard tool_calls: inspect invoke_subagent calls
        tool_calls = step.get("tool_calls", [])
        for tc in tool_calls:
            tc_name = str(tc.get("name", ""))
            if tc_name == "invoke_subagent":
                output_str = str(tc.get("output", ""))
                args_dict = tc.get("args") if isinstance(tc.get("args"), dict) else {}
                args_str = json.dumps(args_dict) if args_dict else str(tc.get("args", ""))
                
                # Also check adjacent step if this step has no inline output
                next_content = ""
                if idx + 1 < len(raw_steps):
                    next_s = raw_steps[idx + 1]
                    if next_s.get("type") in ("GENERIC", "TOOL_OUTPUT") or next_s.get("source") in ("SYSTEM", "SYSTEM_SDK"):
                        next_content = str(next_s.get("content", ""))

                combined = output_str + " " + args_str + " " + next_content
                m_convos = re.findall(
                    r"(?:conversation[_-]?id|conversationId)[\"':\s=]+([a-zA-Z0-9_\-]{8,64})",
                    combined,
                    re.I,
                )
                for sid in m_convos:
                    sid = sid.strip("\"' \t\r\n")
                    if sid != conversation_id and (base_brain / sid).is_dir() and sid not in subagents:
                        subagents.append(sid)
                        subagent_infos.append({
                            "id": sid,
                            "name": args_dict.get("Role") or args_dict.get("TypeName") or f"Subagent {sid[:8]}",
                            "summary": str(args_dict.get("Prompt") or args_dict.get("objective") or "")[:80],
                        })

        # 2. Check for "Created the following subagent" in generic steps
        content_str = str(step.get("content") or "")
        if "Created the following subagent" in content_str:
            m_convos = re.findall(
                r"(?:conversation[_-]?id|conversationId)[\"':\s=]+([a-zA-Z0-9_\-]{8,64})",
                content_str,
                re.I,
            )
            for sid in m_convos:
                sid = sid.strip("\"' \t\r\n")
                if sid != conversation_id and (base_brain / sid).is_dir() and sid not in subagents:
                    subagents.append(sid)
                    subagent_infos.append({
                        "id": sid,
                        "name": f"Subagent {sid[:8]}",
                        "summary": "",
                    })

        # 3. Protobuf invokeSubagent
        if isinstance(step.get("invokeSubagent"), dict):
            for sub in step["invokeSubagent"].get("subagents", []):
                sid = sub.get("conversationId") or sub.get("id")
                if sid:
                    sid = str(sid).strip("\"' \t\r\n")
                    if sid != conversation_id and (base_brain / sid).is_dir() and sid not in subagents:
                        subagents.append(sid)
                        subagent_infos.append({
                            "id": sid,
                            "name": sub.get("role") or sub.get("name") or f"Subagent {sid[:8]}",
                            "summary": str(sub.get("objective") or "")[:80],
                        })

    # Check if this conversation itself is a subagent of another conversation (bounded to top 30 recent)
    if resolved_parent_id is None and base_brain.is_dir():
        cand_dirs = []
        try:
            for d in base_brain.iterdir():
                if d.is_dir() and d.name != conversation_id and d.name != ".system_generated":
                    try:
                        cand_dirs.append((d, d.stat().st_mtime))
                    except OSError:
                        continue
        except OSError:
            pass

        cand_dirs.sort(key=lambda x: x[1], reverse=True)
        for d, _ in cand_dirs[:30]:
            t_log = d / ".system_generated" / "logs" / "transcript.jsonl"
            if not t_log.is_file():
                t_log = d / "transcript.jsonl"
            if t_log.is_file():
                try:
                    with open(t_log, "r", encoding="utf-8", errors="replace") as f:
                        for line in f:
                            if conversation_id in line:
                                resolved_parent_id = d.name
                                break
                    if resolved_parent_id is not None:
                        break
                except OSError:
                    pass

    # Dynamic session model resolution from steps, headers, or settings
    session_model = ""
    meta_path = convo_dir / "meta.json"
    if meta_path.is_file():
        try:
            with open(meta_path, "r", encoding="utf-8", errors="replace") as f:
                meta_json = json.load(f)
                session_model = meta_json.get("model") or meta_json.get("responseModel") or ""
        except (json.JSONDecodeError, OSError, ValueError):
            pass

    for raw in raw_steps:
        raw_meta = raw.get("metadata", {}) if isinstance(raw.get("metadata"), dict) else {}
        content_str = str(raw.get("content") or "")
        if "<USER_SETTINGS_CHANGE>" in content_str:
            m_set = re.search(r"(?:Model Selection|Model)[:\s]+([a-zA-Z0-9_\-\.]+)", content_str, re.I)
            if m_set:
                session_model = m_set.group(1).strip()
        m_cand = (
            raw.get("model")
            or raw.get("response_model")
            or raw.get("responseModel")
            or raw_meta.get("model")
            or raw_meta.get("responseModel")
            or (raw.get("chatStartMetadata", {}) if isinstance(raw.get("chatStartMetadata"), dict) else {}).get("model")
            or (raw_meta.get("chatStartMetadata", {}) if isinstance(raw_meta.get("chatStartMetadata"), dict) else {}).get("model")
            or (raw_meta.get("modelUsage", {}) if isinstance(raw_meta.get("modelUsage"), dict) else {}).get("model")
        )
        if m_cand and isinstance(m_cand, str):
            session_model = m_cand.strip()

    # 1. Authoritative Max Context Tokens (256k default parity with 2.26.0)
    max_context_tokens = 256000
    found_explicit_max_ctx = False
    for raw in reversed(raw_steps):
        if not isinstance(raw, dict):
            continue
        meta_d = raw.get("metadata") if isinstance(raw.get("metadata"), dict) else {}
        csm_d = raw.get("chatStartMetadata") if isinstance(raw.get("chatStartMetadata"), dict) else {}
        meta_csm_d = meta_d.get("chatStartMetadata") if isinstance(meta_d.get("chatStartMetadata"), dict) else {}
        cwm = (
            raw.get("contextWindowMetadata")
            or csm_d.get("contextWindowMetadata")
            or meta_csm_d.get("contextWindowMetadata")
            or meta_d.get("contextWindowMetadata")
        )
        if isinstance(cwm, dict):
            mct = cwm.get("maxContextTokens") or cwm.get("max_context_tokens")
            if mct and isinstance(mct, (int, float)) and mct > 0:
                max_context_tokens = int(mct)
                found_explicit_max_ctx = True
                break

    if not found_explicit_max_ctx:
        meta_path = convo_dir / "meta.json"
        if meta_path.is_file():
            try:
                with open(meta_path, "r", encoding="utf-8", errors="replace") as f:
                    meta_data = json.load(f)
                    mct = (
                        meta_data.get("maxContextTokens")
                        or (meta_data.get("contextWindowMetadata") if isinstance(meta_data.get("contextWindowMetadata"), dict) else {}).get("maxContextTokens")
                    )
                    if mct and isinstance(mct, (int, float)) and mct > 0:
                        max_context_tokens = int(mct)
                        found_explicit_max_ctx = True
            except (json.JSONDecodeError, OSError, ValueError):
                pass

    if not found_explicit_max_ctx:
        try:
            from harness.hooks.token_proximity_guard import get_active_conversation_context_window
            ctx_win = get_active_conversation_context_window(conversation_id)
            db_mct = int(ctx_win.get("max_context_tokens") or 0)
            if db_mct > 0:
                max_context_tokens = db_mct
        except Exception:
            pass

    # Enrich steps: timing metrics, byte sizes, cortex types, cumulative context tokens
    steps: List[Dict[str, Any]] = []
    explicit_input_step_indices: Set[int] = set()
    total_tokens = 0
    cache_tokens = 0
    cumulative_ctx = 0

    for idx, raw in enumerate(raw_steps):
        s = dict(raw)
        s["step_index"] = s.get("step_index", idx)
        s["exec_index"] = s.get("exec_index", 1)
        s["inv_index"] = s.get("inv_index", 1)
        cortex_type = _map_to_cortex_type(s)
        s["type"] = cortex_type

        # Extract system message or task details if content is missing
        if not s.get("content"):
            sys_cand = (
                s.get("systemMessage")
                or s.get("system_message")
                or s.get("message")
                or s.get("task_details")
                or s.get("error_details")
                or s.get("render_info")
            )
            if sys_cand:
                if isinstance(sys_cand, dict):
                    s["content"] = sys_cand.get("content") or sys_cand.get("message") or sys_cand.get("text") or json.dumps(sys_cand, indent=2)
                else:
                    s["content"] = str(sys_cand)

        # Extract compaction summary if present
        comp_summary = _extract_compaction_summary(s)
        if comp_summary:
            s["compaction_summary"] = comp_summary

        # Payload byte size calculation (SIZE column)
        if idx < len(raw_line_sizes):
            s["size_bytes"] = raw_line_sizes[idx]
        else:
            try:
                s["size_bytes"] = len(json.dumps(s).encode("utf-8"))
            except (TypeError, ValueError):
                s["size_bytes"] = 0

        # Authoritative step timing metrics
        meta = s.get("metadata", {}) if isinstance(s.get("metadata"), dict) else {}
        model_usage = meta.get("modelUsage", {}) if isinstance(meta.get("modelUsage"), dict) else {}

        # Unpack ConnectRPC typed tool call & sub-objects (ADR-014 / Cleanroom Parity)
        raw_tc = s.get("toolCall") or meta.get("toolCall")
        if raw_tc and isinstance(raw_tc, dict) and not s.get("tool_calls"):
            parsed_args = raw_tc.get("args") or raw_tc.get("arguments") or {}
            if raw_tc.get("argumentsJson"):
                try:
                    parsed_args = json.loads(raw_tc["argumentsJson"])
                except (json.JSONDecodeError, ValueError):
                    parsed_args = {"raw": raw_tc["argumentsJson"]}
            s["tool_calls"] = [{"id": raw_tc.get("id"), "name": raw_tc.get("name"), "args": parsed_args}]

        if isinstance(s.get("runCommand"), dict):
            rc = s["runCommand"]
            s["command"] = rc.get("commandLine")
            s["exitCode"] = rc.get("exitCode")
            comb = rc.get("combinedOutput")
            s["output"] = comb.get("full") if isinstance(comb, dict) else str(comb or "")
            s["cwd"] = rc.get("cwd")

        if isinstance(s.get("viewFile"), dict):
            vf = s["viewFile"]
            s["filePath"] = vf.get("absolutePathUri")
            s["fileContent"] = vf.get("content")
            s["endLine"] = vf.get("endLine")

        if isinstance(s.get("codeAction"), dict):
            ca = s["codeAction"]
            edit_diff = (ca.get("actionResult") or {}).get("edit", {}).get("diff", {}).get("unifiedDiff", {})
            s["diffLines"] = edit_diff.get("lines", []) if isinstance(edit_diff, dict) else []
            spec = ca.get("actionSpec") or {}
            cr = spec.get("createFile") or {}
            ed = spec.get("editFile") or {}
            s["filePath"] = (cr.get("path") or {}).get("absoluteUri") or (ed.get("path") or {}).get("absoluteUri") or ""

        if isinstance(s.get("invokeSubagent"), dict):
            subs = s["invokeSubagent"].get("subagents", [])
            s["subagent"] = subs[0] if (isinstance(subs, list) and subs) else None

        if isinstance(s.get("checkpoint"), dict):
            cp = s["checkpoint"]
            s["sessionSummary"] = cp.get("sessionSummary", "")
            retries = meta.get("retryInfos", [])
            usage = retries[0].get("usage", {}) if (isinstance(retries, list) and retries and isinstance(retries[0], dict)) else {}
            s["cacheReadTokens"] = int(usage.get("cacheReadTokens", 0) or 0)
            s["checkpointInputTokens"] = int(usage.get("inputTokens", 0) or 0)

        thinking_ms = s.get("thinking_duration_ms")
        if thinking_ms is None:
            thinking_ms = meta.get("thinking_duration_ms") or meta.get("ttft_ms")
            if thinking_ms is None:
                if s.get("thinking"):
                    thinking_ms = min(20000, max(600, int(len(str(s["thinking"])) * 1.6)))
                else:
                    thinking_ms = 0
        s["thinking_duration_ms"] = int(thinking_ms or 0)

        streaming_ms = s.get("streaming_duration_ms")
        if streaming_ms is None:
            streaming_ms = meta.get("streaming_duration_ms")
            if streaming_ms is None:
                content_len = len(str(s.get("content") or ""))
                tool_out_len = sum(len(str(tc.get("output") or "")) for tc in s.get("tool_calls", []))
                streaming_ms = min(45000, max(400, int((content_len + tool_out_len) * 1.8)))
        s["streaming_duration_ms"] = int(streaming_ms or 0)
        s["total_duration_ms"] = s["thinking_duration_ms"] + s["streaming_duration_ms"]

        # Step model resolution
        step_model = (
            s.get("response_model")
            or s.get("model")
            or s.get("responseModel")
            or meta.get("responseModel")
            or meta.get("model")
            or model_usage.get("model")
        )
        if step_model and isinstance(step_model, str):
            s["response_model"] = step_model.strip()
        elif cortex_type in ("PLANNER_RESPONSE", "MODEL_OUTPUT") and session_model:
            s["response_model"] = session_model
        else:
            s["response_model"] = s.get("response_model") or ""

        # Authoritative token metrics extraction
        raw_in_tok = s.get("input_tokens")
        if raw_in_tok is None:
            raw_in_tok = (
                model_usage.get("inputTokens")
                or model_usage.get("promptTokenCount")
                or model_usage.get("inputTokenCount")
                or meta.get("input_tokens")
                or meta.get("promptTokenCount")
            )
        has_explicit_in_tok = raw_in_tok is not None
        in_tok = int(raw_in_tok or 0)
        if has_explicit_in_tok and in_tok > 0:
            explicit_input_step_indices.add(idx)

        out_tok = s.get("output_tokens")
        if out_tok is None:
            out_tok = (
                model_usage.get("outputTokens")
                or model_usage.get("candidatesTokenCount")
                or model_usage.get("responseOutputTokens")
                or meta.get("toolCallOutputTokens")
                or meta.get("output_tokens")
            )
        out_tok = int(out_tok or 0)

        cache_tok = s.get("cache_read_tokens")
        if cache_tok is None:
            cache_tok = (
                model_usage.get("cacheReadTokens")
                or model_usage.get("cachedContentTokenCount")
                or meta.get("cache_read_tokens")
                or meta.get("cachedContentTokenCount")
            )
        s["cache_read_tokens"] = int(cache_tok or 0)

        explicit_tok = int(s.get("tokens") or 0)
        if explicit_tok > 0:
            step_tok = explicit_tok
        elif cortex_type in ("PLANNER_RESPONSE", "MODEL_OUTPUT"):
            if out_tok > 0:
                step_tok = out_tok
            else:
                char_count = len(str(s.get("content") or "")) + len(str(s.get("thinking") or ""))
                step_tok = estimate_tokens(char_count)
        elif cortex_type == "USER_INPUT":
            if in_tok > 0:
                step_tok = in_tok
            elif out_tok > 0:
                step_tok = out_tok
            else:
                char_count = len(str(s.get("content") or ""))
                step_tok = estimate_tokens(char_count)
            if in_tok <= 0:
                in_tok = step_tok
        elif cortex_type == "CHECKPOINT":
            if out_tok > 0:
                step_tok = out_tok
            elif in_tok > 0:
                step_tok = in_tok
            else:
                char_count = len(str(s.get("compaction_summary") or s.get("content") or ""))
                step_tok = estimate_tokens(char_count)
        else:
            if out_tok > 0:
                step_tok = out_tok
            elif in_tok > 0:
                step_tok = in_tok
            else:
                char_count = 0
                for tc in s.get("tool_calls", []):
                    char_count += len(str(tc.get("name") or ""))
                    tc_args = tc.get("args")
                    if tc_args:
                        char_count += len(json.dumps(tc_args) if isinstance(tc_args, (dict, list)) else str(tc_args))
                    char_count += len(str(tc.get("output") or ""))
                if char_count == 0:
                    char_count = len(str(s.get("content") or ""))
                step_tok = estimate_tokens(char_count)

        s["input_tokens"] = in_tok
        s["output_tokens"] = out_tok
        s["tokens"] = step_tok
        if step_tok > 0:
            cumulative_ctx += step_tok
        s["cumulative_tokens"] = cumulative_ctx
        steps.append(s)

    explicit_cum_tokens = 0
    for step_pos in range(len(steps) - 1, -1, -1):
        s = steps[step_pos]
        if cache_tokens == 0 and s.get("cache_read_tokens"):
            cache_tokens = s.get("cache_read_tokens") or 0
        in_tok_val = int(s.get("input_tokens") or 0)
        cache_tok_val = int(s.get("cache_read_tokens") or 0)
        is_explicit_input = step_pos in explicit_input_step_indices
        if (s.get("type") != "USER_INPUT" or is_explicit_input or cache_tok_val > 0) and (in_tok_val + cache_tok_val > 0):
            explicit_cum_tokens = in_tok_val + cache_tok_val
            break

    if explicit_cum_tokens == 0:
        for s in reversed(steps):
            meta = s.get("metadata", {}) if isinstance(s.get("metadata"), dict) else {}
            model_usage = meta.get("modelUsage", {}) if isinstance(meta.get("modelUsage"), dict) else {}
            meta_csm = meta.get("chatStartMetadata") if isinstance(meta.get("chatStartMetadata"), dict) else {}
            step_csm = s.get("chatStartMetadata") if isinstance(s.get("chatStartMetadata"), dict) else {}
            cwm = (
                meta.get("contextWindowMetadata")
                or s.get("contextWindowMetadata")
                or meta_csm.get("contextWindowMetadata")
                or step_csm.get("contextWindowMetadata")
            )
            if isinstance(cwm, dict):
                etu = cwm.get("estimatedTokensUsed") or cwm.get("estimated_tokens_used")
                if etu and isinstance(etu, (int, float)) and int(etu) > explicit_cum_tokens:
                    explicit_cum_tokens = int(etu)
            cum = (
                meta.get("cumulative_context_tokens")
                or meta.get("cumulative_tokens")
                or meta.get("contextTokens")
                or model_usage.get("totalTokens")
            )
            if cum and isinstance(cum, (int, float)) and int(cum) > explicit_cum_tokens:
                explicit_cum_tokens = int(cum)

    if explicit_cum_tokens == 0:
        try:
            from harness.hooks.token_proximity_guard import get_active_conversation_tokens
            explicit_cum_tokens = get_active_conversation_tokens(conversation_id)
        except Exception:
            explicit_cum_tokens = 0

    # Partition checkpoints first so active-epoch token breakdown avoids pre-checkpoint inflation
    checkpoints = [i for i, s in enumerate(steps) if s.get("type") == "CHECKPOINT"]
    breakdown_steps = (steps[checkpoints[-1]:] if checkpoints else steps) if explicit_cum_tokens > 0 else steps
    breakdown_step_sum = sum(s.get("tokens", 0) for s in breakdown_steps)

    # Native Upc context allocation (Google Antigravity Parity)
    if explicit_cum_tokens > 0 and breakdown_step_sum > 0:
        instruction_tok = max(7000, explicit_cum_tokens - breakdown_step_sum)
        sys_prompt_tok = int(instruction_tok * 0.40)
        tool_defs_tok = instruction_tok - sys_prompt_tok
        total_tokens = max(breakdown_step_sum + instruction_tok, explicit_cum_tokens)
    elif breakdown_step_sum > 0:
        sys_prompt_tok = min(4000, max(400, int(breakdown_step_sum * 0.05)))
        tool_defs_tok = min(3500, max(300, int(breakdown_step_sum * 0.04)))
        total_tokens = breakdown_step_sum + sys_prompt_tok + tool_defs_tok
    else:
        sys_prompt_tok = 3800
        tool_defs_tok = 3200
        total_tokens = max(sys_prompt_tok + tool_defs_tok, explicit_cum_tokens)

    actual_user_tok = sum(s["tokens"] for s in breakdown_steps if s.get("type") == "USER_INPUT")
    actual_model_tok = sum(s["tokens"] for s in breakdown_steps if s.get("type") in ("PLANNER_RESPONSE", "MODEL_OUTPUT"))
    actual_tool_tok = sum(s["tokens"] for s in breakdown_steps if (
        s.get("type") in ("TOOL_CALL", "RUN_COMMAND", "VIEW_FILE", "REPLACE_FILE_CONTENT", "WRITE_FILE", "GREP_SEARCH", "FIND_FILES", "SEND_MESSAGE", "INVOKE_SUBAGENT")
        or any(k in str(s.get("type", "")) for k in ("COMMAND", "TOOL", "FILE", "WRITE", "REPLACE", "SEARCH", "MESSAGE", "SUBAGENT"))
    ))
    actual_checkpoint_tok = sum(s["tokens"] for s in breakdown_steps if s.get("type") == "CHECKPOINT")
    actual_system_tok = sum(s["tokens"] for s in breakdown_steps if s.get("type") == "SYSTEM")

    categorized_sum = actual_user_tok + actual_model_tok + actual_tool_tok + actual_checkpoint_tok + actual_system_tok
    if breakdown_step_sum > categorized_sum:
        actual_model_tok += (breakdown_step_sum - categorized_sum)

    token_breakdown = {
        "system_prompt": sys_prompt_tok,
        "tool_defs": tool_defs_tok,
        "checkpoint": actual_checkpoint_tok,
        "user": actual_user_tok,
        "model": actual_model_tok,
        "tool": actual_tool_tok,
        "system": actual_system_tok,
    }
    # Guarantee sum(token_breakdown.values()) == total_tokens exactly
    diff = total_tokens - sum(token_breakdown.values())
    token_breakdown["model"] += diff

    # Pre-bundle direct child subagents into subagent_trajectories map (depth 1 only)
    subagent_trajectories: Dict[str, Any] = {}
    if parent_id is None:
        for sid in subagents:
            if sid not in _visited:
                try:
                    sub_traj = load_conversation_trajectory(
                        sid,
                        brain_dir=base_brain,
                        _visited=_visited,
                        parent_id=conversation_id,
                    )
                    subagent_trajectories[sid] = sub_traj
                except (OSError, ValueError, KeyError, json.JSONDecodeError):
                    continue

    # Partition trajectory into Epochs based on CHECKPOINT steps (ADR-014 / PSL-INV-010)
    epochs: List[Dict[str, Any]] = []
    if not checkpoints:
        if steps:
            epochs.append({
                "epoch_index": 0,
                "start_index": 0,
                "end_index": len(steps) - 1,
                "step_count": len(steps),
                "has_checkpoint": False,
                "summary": "Initial Trajectory",
            })
    else:
        c0 = checkpoints[0]
        epochs.append({
            "epoch_index": 0,
            "start_index": 0,
            "end_index": c0,
            "step_count": c0 + 1,
            "has_checkpoint": True,
            "summary": steps[c0].get("compaction_summary") or f"Checkpoint #{c0}",
        })
        for k in range(len(checkpoints)):
            cur_cp = checkpoints[k]
            if k + 1 < len(checkpoints):
                next_cp = checkpoints[k + 1]
                epochs.append({
                    "epoch_index": len(epochs),
                    "start_index": cur_cp,
                    "end_index": next_cp,
                    "step_count": next_cp - cur_cp + 1,
                    "has_checkpoint": True,
                    "summary": steps[cur_cp].get("compaction_summary") or f"Checkpoint #{cur_cp}",
                })
            elif cur_cp < len(steps) - 1:
                epochs.append({
                    "epoch_index": len(epochs),
                    "start_index": cur_cp,
                    "end_index": len(steps) - 1,
                    "step_count": (len(steps) - 1) - cur_cp + 1,
                    "has_checkpoint": True,
                    "summary": steps[cur_cp].get("compaction_summary") or f"Checkpoint #{cur_cp}",
                })

    summary = _extract_conversation_summary(convo_dir, transcript_path)

    sys_prompt_slices = [
        {"name": "Identity", "tokens": int(sys_prompt_tok * 0.15), "color": "#6366f1"},
        {"name": "Sandbox", "tokens": int(sys_prompt_tok * 0.05), "color": "#818cf8"},
        {"name": "Artifacts", "tokens": int(sys_prompt_tok * 0.08), "color": "#a78bfa"},
        {"name": "Transcript", "tokens": int(sys_prompt_tok * 0.07), "color": "#c084fc"},
        {"name": "Guidelines", "tokens": int(sys_prompt_tok * 0.12), "color": "#e879f9"},
        {"name": "Style", "tokens": int(sys_prompt_tok * 0.05), "color": "#f472b6"},
        {"name": "Commands", "tokens": int(sys_prompt_tok * 0.06), "color": "#fb7185"},
        {"name": "Messaging", "tokens": int(sys_prompt_tok * 0.07), "color": "#9333ea"},
        {"name": "MCP Servers", "tokens": int(sys_prompt_tok * 0.05), "color": "#7c3aed"},
        {"name": "Subagents", "tokens": int(sys_prompt_tok * 0.06), "color": "#6d28d9"},
        {"name": "User Rules", "tokens": int(sys_prompt_tok * 0.08), "color": "#5b21b6"},
        {"name": "Skills", "tokens": int(sys_prompt_tok * 0.08), "color": "#4c1d95"},
        {"name": "Plugins", "tokens": int(sys_prompt_tok * 0.04), "color": "#8b5cf6"},
        {"name": "UserInfo", "tokens": max(0, sys_prompt_tok - sum(int(sys_prompt_tok * f) for f in [0.15, 0.05, 0.08, 0.07, 0.12, 0.05, 0.06, 0.07, 0.05, 0.06, 0.08, 0.08, 0.04])), "color": "#a855f7"},
    ]
    tool_def_slices = [
        {"name": "Filesystem Tools", "tokens": int(tool_defs_tok * 0.25), "color": "#06b6d4"},
        {"name": "Terminal Tools", "tokens": int(tool_defs_tok * 0.20), "color": "#0891b2"},
        {"name": "Subagents", "tokens": int(tool_defs_tok * 0.25), "color": "#0e7490"},
        {"name": "Automation & Tasks", "tokens": max(0, tool_defs_tok - (int(tool_defs_tok * 0.25) + int(tool_defs_tok * 0.20) + int(tool_defs_tok * 0.25))), "color": "#14b8a6"},
    ]

    return {
        "conversation_id": conversation_id,
        "transcript_path": str(transcript_path),
        "summary": summary,
        "model": session_model,
        "steps": steps,
        "step_count": len(steps),
        "epochs": epochs,
        "parent_id": resolved_parent_id,
        "subagents": subagents,
        "subagent_infos": subagent_infos,
        "subagent_trajectories": subagent_trajectories,
        "total_tokens": total_tokens,
        "max_context_tokens": max_context_tokens,
        "cache_tokens": cache_tokens,
        "token_breakdown": token_breakdown,
        "system_prompt_slices": sys_prompt_slices,
        "tool_def_slices": tool_def_slices,
    }


def get_recent_conversations(
    brain_dir: Optional[Path] = None,
    limit: int = 30,
) -> List[Dict[str, Any]]:
    """Discovers and returns recent Antigravity conversations sorted by modification time."""
    base_brain = brain_dir or (Path.home() / ".gemini" / "antigravity" / "brain")
    if not base_brain.is_dir():
        return []

    conversations: List[Dict[str, Any]] = []
    for d in base_brain.iterdir():
        if d.is_dir() and d.name != ".system_generated":
            t_log = d / ".system_generated" / "logs" / "transcript.jsonl"
            if not t_log.is_file():
                t_log = d / "transcript.jsonl"

            if t_log.is_file():
                try:
                    mtime = t_log.stat().st_mtime
                    summary = _extract_conversation_summary(d, t_log)
                    conversations.append({
                        "id": d.name,
                        "summary": summary,
                        "mtime": mtime,
                    })
                except OSError:
                    continue

    conversations.sort(key=lambda c: c["mtime"], reverse=True)
    return conversations[:limit]


_CACHED_HUD_TEMPLATE: Optional[str] = None


def _load_hud_template() -> str:
    """Loads the HUD in-situ JavaScript template from packaged assets (ADR-014, PSL-INV-011)."""
    global _CACHED_HUD_TEMPLATE
    if _CACHED_HUD_TEMPLATE is None:
        ref = importlib.resources.files("harness.gui.assets").joinpath("hud.js")
        _CACHED_HUD_TEMPLATE = ref.read_text(encoding="utf-8")
    return _CACHED_HUD_TEMPLATE


def build_trajectory_hud_script(
    convo_id: str,
    trajectory_data: Dict[str, Any],
    conversations: List[Dict[str, Any]],
    open_view: bool = True,
    toggle: bool = False,
) -> str:
    """Builds the complete self-contained in-situ DOM injection script for the Trajectory Debug View HUD."""
    payload = {
        "initialData": trajectory_data,
        "conversationList": conversations,
        "shouldOpen": open_view,
        "isToggle": toggle,
    }
    payload_json = json.dumps(payload)

    target_token = "const __PAYLOAD__ = null;"
    replacement = f"const __PAYLOAD__ = {payload_json};"
    return _load_hud_template().replace(target_token, replacement, 1)
