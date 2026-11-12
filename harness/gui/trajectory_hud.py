# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Arafat Zahan (@kuasha420)
# Corporate Stewardship & Infrastructure: Purrfect Software Limited (PSL)
# Governed by: ICARO-42/b Ordinance (Company-Supported Personal IP Framework)

"""
Trajectory Debug View HUD Builder & Data Loader (ADR-014 / ADR-035 / PSL-INV-010).

Reads live conversation transcripts, resolves subagent hierarchies, delegates SQLite
metrics & lineage to `harness.trajectory`, and constructs a dynamic Chrome DevTools
overlay script from modular `harness/gui/assets/` components.
"""

from __future__ import annotations

import importlib.resources
import json
from pathlib import Path
import re
from typing import Any, Dict, List, Optional, Set, Tuple

from harness.trajectory.health import (
    DEFAULT_CONTEXT_WINDOW_TOKENS,
    TrajectoryMetrics,
    is_transcript_checkpoint_step,
)
from harness.trajectory.sqlite_reader import parse_step_timestamp, read_db_trajectory_state
from harness.trajectory.transcript_reader import (
    _load_meta_parent,
    extract_spawned_subagents,
    find_transcript_path,
    load_transcript_steps,
)
from harness.utils.context import get_active_brain_dir
from harness.utils.tokens import estimate_tokens as _ssot_estimate_tokens

_SYS_TAG_DEFS: Tuple[Tuple[str, str, str], ...] = (
    ("identity", "Identity", "#6366f1"), ("sandbox", "Sandbox", "#818cf8"), ("artifacts", "Artifacts", "#a78bfa"),
    ("conversation_transcript", "Transcript", "#c084fc"), ("guidelines", "Guidelines", "#e879f9"), ("communication_style", "Style", "#f472b6"),
    ("slash_commands", "Commands", "#fb7185"), ("messaging", "Messaging", "#9333ea"), ("mcp_servers", "MCP Servers", "#7c3aed"),
    ("subagents", "Subagents", "#6d28d9"), ("user_rules", "User Rules", "#5b21b6"), ("skills", "Skills", "#4c1d95"),
    ("featured_plugins", "Plugins", "#8b5cf6"), ("user_information", "UserInfo", "#a855f7"), ("subagent_reminder", "Reminders", "#d946ef"),
)
_TOOL_CATEGORY_SPEC: Tuple[Tuple[str, str, Tuple[str, ...]], ...] = (
    ("Filesystem Tools", "#06b6d4", ("read_file", "write_file", "edit_file", "replace_file_content", "write_to_file", "view_file")),
    ("Terminal Tools", "#0891b2", ("run_command", "bash")),
    ("Subagents", "#0e7490", ("invoke_subagent", "define_subagent", "manage_subagents", "send_message")),
)
_TC_TYPE_NEEDLES: Tuple[Tuple[str, str], ...] = (
    ("run_command", "RUN_COMMAND"), ("view_file", "VIEW_FILE"), ("replace_file_content", "REPLACE_FILE_CONTENT"),
    ("write_to_file", "WRITE_FILE"), ("grep_search", "GREP_SEARCH"), ("find_by_name", "FIND_FILES"),
    ("find_files", "FIND_FILES"), ("send_message", "SEND_MESSAGE"), ("invoke_subagent", "INVOKE_SUBAGENT"),
    ("subagent", "INVOKE_SUBAGENT"),
)


def _extract_cwm(step: Dict[str, Any]) -> Dict[str, Any]:
    """Returns contextWindowMetadata dict from top-level or nested step metadata."""
    meta = step.get("metadata") if isinstance(step.get("metadata"), dict) else {}
    for container in (
        step,
        step.get("chatStartMetadata"),
        meta,
        meta.get("chatStartMetadata"),
    ):
        if isinstance(container, dict) and isinstance(container.get("contextWindowMetadata"), dict):
            return container["contextWindowMetadata"]
    return {}


def _map_to_cortex_type(step: Dict[str, Any]) -> str:
    """Maps a transcript step to canonical Antigravity Cortex step types."""
    existing_type = step.get("type")
    tool_calls = step.get("tool_calls", [])
    source = str(step.get("source") or "").lower()
    role = str(step.get("role") or "").lower()
    content = str(step.get("content") or "")
    step_case = str(step.get("case") or step.get("step", {}).get("case") or "").lower()

    if is_transcript_checkpoint_step(step):
        return "CHECKPOINT"

    if existing_type and existing_type in (
        "PLANNER_RESPONSE", "USER_INPUT", "RUN_COMMAND", "VIEW_FILE",
        "REPLACE_FILE_CONTENT", "WRITE_FILE", "GREP_SEARCH", "FIND_FILES",
        "SEND_MESSAGE", "INVOKE_SUBAGENT", "MODEL_OUTPUT", "SYSTEM", "TOOL_CALL",
        "CHECKPOINT", "CODE_ACTION",
    ):
        return existing_type

    for field_k, case_k, ctype in (
        ("runCommand", "runcommand", "RUN_COMMAND"),
        ("viewFile", "viewfile", "VIEW_FILE"),
        ("codeAction", "codeaction", "CODE_ACTION"),
        ("invokeSubagent", "invokesubagent", "INVOKE_SUBAGENT"),
    ):
        if step.get(field_k) is not None or step_case == case_k:
            return ctype

    if source == "user" or role == "user":
        return "USER_INPUT"
    if source == "system" or role == "system":
        return "SYSTEM"

    if tool_calls:
        first_tc = str(tool_calls[0].get("name", "")).lower()
        return next((ctype for needle, ctype in _TC_TYPE_NEEDLES if needle in first_tc), "TOOL_CALL")

    if step.get("thinking"):
        return "PLANNER_RESPONSE"
    if source in ("model", "assistant") or role in ("model", "assistant"):
        return "MODEL_OUTPUT"
    return existing_type or "STEP"


def _extract_compaction_summary(step: Dict[str, Any], is_checkpoint: Optional[bool] = None) -> Optional[str]:
    """Extracts compaction summary strictly from checkpoint steps or structured summary fields."""
    cp = step.get("checkpoint")
    if isinstance(cp, dict):
        s = cp.get("sessionSummary") or cp.get("userIntent") or cp.get("summary")
        if s:
            return str(s).strip()
    elif isinstance(cp, str):
        return cp.strip()

    for key in ("sessionSummary", "userIntent"):
        if step.get(key):
            return str(step[key]).strip()

    step_obj = step.get("step")
    if isinstance(step_obj, dict) and isinstance(step_obj.get("value"), dict):
        val = step_obj["value"]
        s = val.get("sessionSummary") or val.get("userIntent") or val.get("summary")
        if s:
            return str(s).strip()

    if is_checkpoint is None:
        is_checkpoint = is_transcript_checkpoint_step(step)
    if not is_checkpoint:
        return None
    for field in ("content", "thinking"):
        val = str(step.get(field) or "")
        m = re.search(r"<(?:CONTEXT_SUMMARY|summary)>([\s\S]*?)</(?:CONTEXT_SUMMARY|summary)>", val, re.I)
        if m:
            return m.group(1).strip()
    return None


def estimate_tokens(char_count: int) -> int:
    """Estimates token count using SSOT token helper at cleanroom HUD ratio (3.5 chars/token)."""
    return _ssot_estimate_tokens(char_count, chars_per_token=3.5)


def xtc_segment_width(segment_tokens: int, px_per_token: float, min_segment_px: float = 2.0) -> float:
    """Calculates pixel width for a segment with minimum pixel clamp (cleanroom xtc)."""
    tok = max(0, segment_tokens)
    return max(tok * px_per_token, min_segment_px) if tok > 0 else 0.0


def ytc_layout_pass(
    segments: List[Dict[str, Any]], capacity_tokens: int, container_width: float,
    min_segment_px: float = 2.0, rows_count: int = 1,
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
    segments: List[Dict[str, Any]], capacity_tokens: int, container_width: float,
    min_segment_px: float = 2.0, max_rows: int = 8,
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
    segments: List[Dict[str, Any]], capacity_tokens: int, container_width: float,
    min_segment_px: float = 2.0, max_rows: int = 8,
) -> Dict[str, Any]:
    """Authoritative dynamic context bar sizing and multi-row layout algorithm (cleanroom Atc)."""
    if not segments or capacity_tokens <= 0 or container_width <= 0:
        return {"rows": [], "inflation_px": 0.0}

    row_count = ztc_row_count(segments, capacity_tokens, container_width, min_segment_px, max_rows)
    layout = ytc_layout_pass(segments, capacity_tokens, container_width, min_segment_px, row_count)
    scale_factor = layout["capacity_px"] / layout["used_px"] if layout["used_px"] > layout["capacity_px"] else 1.0
    segment_widths = [xtc_segment_width(s.get("tokens", 0), layout["px_per_token"], min_segment_px) * scale_factor for s in segments]
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
        place_cell(seg, segment_widths[idx], f"{idx}:{seg.get('id', idx)}", next_seg is not None and next_seg.get("color_key") == seg.get("color_key"))
    if unused_px > 1e-6:
        place_cell(None, unused_px, "unused", False)

    return {"rows": rows, "inflation_px": layout["inflation_px"] * scale_factor}


def _extract_conversation_summary(convo_dir: Path, transcript_path: Path) -> str:
    """Extracts a short human-readable summary for a conversation."""
    meta_path = convo_dir / "meta.json"
    if meta_path.is_file():
        try:
            data = json.loads(meta_path.read_text(encoding="utf-8", errors="replace"))
            summary = data.get("summary") or data.get("title")
            if summary:
                return str(summary).strip()
        except (json.JSONDecodeError, OSError, ValueError, KeyError):
            pass
    if transcript_path.is_file():
        try:
            with open(transcript_path, "r", encoding="utf-8", errors="replace") as f:
                for line in f:
                    if not line.strip():
                        continue
                    try:
                        s = json.loads(line)
                        if (s.get("type") == "USER_INPUT" or "user" in str(s.get("source") or s.get("role") or "").lower()) and s.get("content"):
                            raw = str(s["content"]).strip()
                            m = re.search(r"<USER_REQUEST>(.*?)(?:</USER_REQUEST>|$)", raw, re.DOTALL)
                            clean = (m.group(1) if m else raw).strip()
                            if clean:
                                first_line = clean.splitlines()[0][:60].strip()
                                if first_line:
                                    return first_line
                    except (json.JSONDecodeError, ValueError, KeyError):
                        continue
        except OSError:
            pass
    return f"Session {convo_dir.name[:8]}"


def _resolve_lineage_and_subagents(
    conversation_id: str,
    raw_steps: List[Dict[str, Any]],
    base_brain: Path,
    parent_id: Optional[str],
) -> Tuple[Optional[str], List[str], List[Dict[str, Any]]]:
    """Resolves parent ID and backslash-free child subagent metadata via SSOT extractor."""
    spawned = extract_spawned_subagents(raw_steps, parent_cid=conversation_id)
    subagents: List[str] = []
    subagent_infos: List[Dict[str, Any]] = []
    details_by_sid: Dict[str, Tuple[str, str]] = {}

    for step in raw_steps:
        for tc in step.get("tool_calls", []):
            args = tc.get("args") if isinstance(tc.get("args"), dict) else {}
            if tc.get("name") == "invoke_subagent":
                combined = f"{tc.get('output', '')} {json.dumps(args)}"
                for m_cid in re.findall(r"([0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}|[a-zA-Z0-9_-]{8,64})", combined):
                    if m_cid in spawned:
                        details_by_sid[m_cid] = (
                            str(args.get("Role") or args.get("TypeName") or spawned[m_cid] or f"Subagent {m_cid[:8]}"),
                            str(args.get("Prompt") or args.get("objective") or "")[:80],
                        )
        if isinstance(step.get("invokeSubagent"), dict):
            for sub in step["invokeSubagent"].get("subagents", []):
                sid = str(sub.get("conversationId") or sub.get("id") or "").strip("\"' \t\r\n")
                if sid and sid != conversation_id and "\\" not in sid:
                    spawned.setdefault(sid, str(sub.get("role") or sub.get("name") or "subagent"))
                    details_by_sid.setdefault(
                        sid,
                        (str(sub.get("role") or sub.get("name") or f"Subagent {sid[:8]}"), str(sub.get("objective") or "")[:80]),
                    )

    for sid, default_role in spawned.items():
        clean_sid = sid.strip("\"' \t\r\n")
        if clean_sid != conversation_id and "\\" not in clean_sid and (base_brain / clean_sid).is_dir() and clean_sid not in subagents:
            subagents.append(clean_sid)
            name, summary = details_by_sid.get(clean_sid, (default_role or f"Subagent {clean_sid[:8]}", ""))
            subagent_infos.append({"id": clean_sid, "name": name, "summary": summary})

    meta_parent, _ = _load_meta_parent(base_brain / conversation_id)
    resolved_parent = parent_id or meta_parent
    if resolved_parent is None and base_brain.is_dir():
        try:
            cands = sorted(
                (d for d in base_brain.iterdir() if d.is_dir() and d.name not in (conversation_id, ".system_generated")),
                key=lambda d: d.stat().st_mtime,
                reverse=True,
            )[:30]
            for d in cands:
                t_log, _ = find_transcript_path(d)
                if t_log and t_log.is_file() and conversation_id in t_log.read_text(encoding="utf-8", errors="replace"):
                    resolved_parent = d.name
                    break
        except OSError:
            pass
    return resolved_parent, subagents, subagent_infos


def _resolve_session_metadata(
    convo_dir: Path,
    raw_steps: List[Dict[str, Any]],
    db_metrics: TrajectoryMetrics,
) -> Tuple[str, int]:
    """Resolves active model identifier and authoritative max context capacity."""
    session_model = ""
    meta_json: Dict[str, Any] = {}
    meta_path = convo_dir / "meta.json"
    if meta_path.is_file():
        try:
            parsed = json.loads(meta_path.read_text(encoding="utf-8", errors="replace"))
            if isinstance(parsed, dict):
                meta_json = parsed
                session_model = str(meta_json.get("model") or meta_json.get("responseModel") or "")
        except (json.JSONDecodeError, OSError, ValueError):
            pass

    for raw in raw_steps:
        raw_meta = raw.get("metadata") if isinstance(raw.get("metadata"), dict) else {}
        content_str = str(raw.get("content") or "")
        if "<USER_SETTINGS_CHANGE>" in content_str:
            m_set = re.search(r"(?:Model Selection|Model)[:\s]+([a-zA-Z0-9_\-\.]+)", content_str, re.I)
            if m_set:
                session_model = m_set.group(1).strip()
        m_cand = (
            raw.get("model") or raw.get("response_model") or raw.get("responseModel")
            or raw_meta.get("model") or raw_meta.get("responseModel")
            or (raw_meta.get("modelUsage") if isinstance(raw_meta.get("modelUsage"), dict) else {}).get("model")
        )
        if isinstance(m_cand, str) and m_cand.strip():
            session_model = m_cand.strip()
    if not session_model and db_metrics.model_name:
        session_model = db_metrics.model_name

    max_ctx = DEFAULT_CONTEXT_WINDOW_TOKENS
    for raw in reversed(raw_steps):
        if isinstance(raw, dict):
            mct = _extract_cwm(raw).get("maxContextTokens") or _extract_cwm(raw).get("max_context_tokens")
            if isinstance(mct, (int, float)) and mct > 0:
                return session_model, int(mct)

    mct_meta = meta_json.get("maxContextTokens") or (
        meta_json.get("contextWindowMetadata") if isinstance(meta_json.get("contextWindowMetadata"), dict) else {}
    ).get("maxContextTokens")
    if isinstance(mct_meta, (int, float)) and mct_meta > 0:
        return session_model, int(mct_meta)

    if db_metrics.max_context_tokens > 0:
        max_ctx = int(db_metrics.max_context_tokens)
    return session_model, max_ctx


def _enrich_and_sort_steps(
    raw_steps: List[Dict[str, Any]],
    raw_line_sizes: List[int],
    session_model: str,
) -> Tuple[List[Dict[str, Any]], Set[int]]:
    """Sorts steps chronologically by step_index, unpacks Cortex structures, and resets cumulative context per epoch."""
    paired = sorted(
        (
            (raw, raw_line_sizes[i] if i < len(raw_line_sizes) else 0, int(raw.get("step_index", i) if isinstance(raw.get("step_index"), (int, float)) else i), i)
            for i, raw in enumerate(raw_steps)
        ),
        key=lambda item: (item[2], item[3]),
    )

    steps: List[Dict[str, Any]] = []
    explicit_in_positions: Set[int] = set()
    cumulative_ctx = 0

    for pos, (raw, line_size, norm_step_idx, _) in enumerate(paired):
        s = dict(raw)
        s["step_index"] = raw.get("step_index", norm_step_idx)
        s["exec_index"] = s.get("exec_index", 1)
        s["inv_index"] = s.get("inv_index", 1)
        cortex_type = _map_to_cortex_type(s)
        s["type"] = cortex_type

        if not s.get("content"):
            sys_cand = s.get("systemMessage") or s.get("system_message") or s.get("message") or s.get("task_details") or s.get("error_details") or s.get("render_info")
            if sys_cand:
                s["content"] = sys_cand.get("content") or sys_cand.get("message") or sys_cand.get("text") or json.dumps(sys_cand, indent=2) if isinstance(sys_cand, dict) else str(sys_cand)

        comp_summary = _extract_compaction_summary(s, is_checkpoint=(cortex_type == "CHECKPOINT"))
        if comp_summary:
            s["compaction_summary"] = comp_summary

        s["size_bytes"] = line_size if line_size > 0 else len(json.dumps(s, default=str).encode("utf-8"))
        meta = s.get("metadata") if isinstance(s.get("metadata"), dict) else {}
        model_usage = meta.get("modelUsage") if isinstance(meta.get("modelUsage"), dict) else {}

        raw_tc = s.get("toolCall") or meta.get("toolCall")
        if isinstance(raw_tc, dict) and not s.get("tool_calls"):
            parsed_args = raw_tc.get("args") or raw_tc.get("arguments") or {}
            if raw_tc.get("argumentsJson"):
                try:
                    parsed_args = json.loads(raw_tc["argumentsJson"])
                except (json.JSONDecodeError, ValueError):
                    parsed_args = {"raw": raw_tc["argumentsJson"]}
            s["tool_calls"] = [{"id": raw_tc.get("id"), "name": raw_tc.get("name"), "args": parsed_args}]

        if isinstance(s.get("runCommand"), dict):
            rc = s["runCommand"]
            comb = rc.get("combinedOutput")
            s.update({"command": rc.get("commandLine"), "exitCode": rc.get("exitCode"), "output": comb.get("full") if isinstance(comb, dict) else str(comb or ""), "cwd": rc.get("cwd")})
        if isinstance(s.get("viewFile"), dict):
            vf = s["viewFile"]
            s.update({"filePath": vf.get("absolutePathUri"), "fileContent": vf.get("content"), "endLine": vf.get("endLine")})
        if isinstance(s.get("codeAction"), dict):
            ca = s["codeAction"]
            ediff = (ca.get("actionResult") or {}).get("edit", {}).get("diff", {}).get("unifiedDiff", {})
            spec = ca.get("actionSpec") or {}
            s["diffLines"] = ediff.get("lines", []) if isinstance(ediff, dict) else []
            s["filePath"] = ((spec.get("createFile") or {}).get("path") or {}).get("absoluteUri") or ((spec.get("editFile") or {}).get("path") or {}).get("absoluteUri") or ""
        if isinstance(s.get("invokeSubagent"), dict):
            subs = s["invokeSubagent"].get("subagents", [])
            s["subagent"] = subs[0] if (isinstance(subs, list) and subs) else None
        if isinstance(s.get("checkpoint"), dict):
            s["sessionSummary"] = s["checkpoint"].get("sessionSummary", "")
            retries = meta.get("retryInfos", [])
            usage = retries[0].get("usage", {}) if (isinstance(retries, list) and retries and isinstance(retries[0], dict)) else {}
            s["cacheReadTokens"] = int(usage.get("cacheReadTokens", 0) or 0)
            s["checkpointInputTokens"] = int(usage.get("inputTokens", 0) or 0)

        t_ms = s.get("thinking_duration_ms") or meta.get("thinking_duration_ms") or meta.get("ttft_ms")
        if t_ms is None:
            t_ms = min(20000, max(600, int(len(str(s["thinking"])) * 1.6))) if s.get("thinking") else 0
        s_ms = s.get("streaming_duration_ms") or meta.get("streaming_duration_ms")
        if s_ms is None:
            c_len = len(str(s.get("content") or "")) + sum(len(str(tc.get("output") or "")) for tc in s.get("tool_calls", []))
            s_ms = min(45000, max(400, int(c_len * 1.8)))
        s["thinking_duration_ms"] = int(t_ms or 0)
        s["streaming_duration_ms"] = int(s_ms or 0)
        s["total_duration_ms"] = s["thinking_duration_ms"] + s["streaming_duration_ms"]

        step_model = s.get("response_model") or s.get("model") or s.get("responseModel") or meta.get("responseModel") or meta.get("model") or model_usage.get("model")
        s["response_model"] = step_model.strip() if isinstance(step_model, str) and step_model.strip() else (session_model if cortex_type in ("PLANNER_RESPONSE", "MODEL_OUTPUT") else "")

        raw_in = s.get("input_tokens")
        if raw_in is None:
            raw_in = model_usage.get("inputTokens") or model_usage.get("promptTokenCount") or model_usage.get("inputTokenCount") or meta.get("input_tokens") or meta.get("promptTokenCount") or s.get("checkpointInputTokens")
        in_tok = int(raw_in or 0)
        if raw_in is not None and in_tok > 0:
            explicit_in_positions.add(pos)

        raw_out = s.get("output_tokens")
        if raw_out is None:
            raw_out = model_usage.get("outputTokens") or model_usage.get("candidatesTokenCount") or model_usage.get("responseOutputTokens") or meta.get("toolCallOutputTokens") or meta.get("output_tokens")
        out_tok = int(raw_out or 0)
        cache_tok = int(s.get("cache_read_tokens") or s.get("cacheReadTokens") or model_usage.get("cacheReadTokens") or model_usage.get("cachedContentTokenCount") or meta.get("cache_read_tokens") or meta.get("cachedContentTokenCount") or 0)

        explicit_tok = int(s.get("tokens") or 0)
        if explicit_tok > 0:
            step_tok = explicit_tok
        elif cortex_type in ("PLANNER_RESPONSE", "MODEL_OUTPUT"):
            step_tok = out_tok if out_tok > 0 else estimate_tokens(len(str(s.get("content") or "")) + len(str(s.get("thinking") or "")))
        elif cortex_type == "USER_INPUT":
            step_tok = in_tok or out_tok or estimate_tokens(len(str(s.get("content") or "")))
            in_tok = in_tok or step_tok
        elif cortex_type == "CHECKPOINT":
            step_tok = out_tok or in_tok or estimate_tokens(len(str(s.get("compaction_summary") or s.get("content") or "")))
        else:
            tool_chars = sum(len(str(tc.get("name") or "")) + len(json.dumps(tc.get("args") or "") if tc.get("args") else "") + len(str(tc.get("output") or "")) for tc in s.get("tool_calls", []))
            extra_chars = len(str(s.get("command") or "")) + len(str(s.get("output") or "")) + len(str(s.get("fileContent") or "")) + len("\n".join(str(x) for x in s.get("diffLines") or []))
            step_tok = out_tok or in_tok or estimate_tokens(tool_chars + extra_chars or len(str(s.get("content") or "")))

        if cortex_type == "CHECKPOINT":
            cumulative_ctx = step_tok
        elif step_tok > 0:
            cumulative_ctx += step_tok

        s.update({"input_tokens": in_tok, "output_tokens": out_tok, "cache_read_tokens": cache_tok, "tokens": step_tok, "cumulative_tokens": cumulative_ctx})
        steps.append(s)

    return steps, explicit_in_positions


def _partition_epochs(steps: List[Dict[str, Any]], checkpoints: List[int]) -> List[Dict[str, Any]]:
    """Partitions steps into epochs delimited by compaction CHECKPOINT steps."""
    if not checkpoints:
        if not steps:
            return []
        return [{"epoch_index": 0, "start_index": 0, "end_index": len(steps) - 1, "step_count": len(steps), "has_checkpoint": False, "summary": "Initial Trajectory"}]

    c0 = checkpoints[0]
    epochs: List[Dict[str, Any]] = [{
        "epoch_index": 0, "start_index": 0, "end_index": c0, "step_count": c0 + 1, "has_checkpoint": True,
        "summary": steps[c0].get("compaction_summary") or f"Checkpoint #{c0}",
    }]
    for k, cur_cp in enumerate(checkpoints):
        end_idx = checkpoints[k + 1] if k + 1 < len(checkpoints) else (len(steps) - 1 if cur_cp < len(steps) - 1 else -1)
        if end_idx >= 0:
            epochs.append({
                "epoch_index": len(epochs), "start_index": cur_cp, "end_index": end_idx, "step_count": end_idx - cur_cp + 1,
                "has_checkpoint": True, "summary": steps[cur_cp].get("compaction_summary") or f"Checkpoint #{cur_cp}",
            })
    return epochs


def _extract_measured_slices(raw_steps: List[Dict[str, Any]]) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    """Extracts ONLY genuine measured systemPrompt and tool schema slices when explicitly present."""
    raw_sys = ""
    raw_tools: List[Any] = []
    prompt_sections: List[Any] = []
    for raw in raw_steps:
        meta = raw.get("metadata") if isinstance(raw.get("metadata"), dict) else {}
        chat_model = raw.get("chatModel") or meta.get("chatModel")
        if isinstance(chat_model, dict):
            raw_sys = raw_sys or str(chat_model.get("systemPrompt") or "")
            if not raw_tools and isinstance(chat_model.get("tools"), list):
                raw_tools = chat_model["tools"]
            if not prompt_sections and isinstance(chat_model.get("promptSections"), list):
                prompt_sections = chat_model["promptSections"]
        if not prompt_sections:
            dmc = raw.get("declarativeMixinConfig") or (meta.get("plannerConfig") or {}).get("declarativeMixinConfig") or {}
            if isinstance(dmc, dict) and isinstance(dmc.get("promptSections"), list):
                prompt_sections = dmc["promptSections"]

    sys_slices: List[Dict[str, Any]] = []
    if raw_sys:
        for tag, name, color in _SYS_TAG_DEFS:
            m = re.search(rf"<{tag}>([\s\S]*?)</{tag}>", raw_sys, re.I)
            if m and m.group(1):
                sys_slices.append({"name": name, "tag": tag, "tokens": max(1, estimate_tokens(len(m.group(1)))), "color": color})
        if not sys_slices:
            sys_slices.append({"name": "System Prompt", "tokens": max(1, estimate_tokens(len(raw_sys))), "color": "#6366f1"})
    elif prompt_sections:
        palette = [c for _, _, c in _SYS_TAG_DEFS]
        for idx, sec in enumerate(prompt_sections):
            if isinstance(sec, dict) and (sec.get("content") or sec.get("text")):
                content_s = str(sec.get("content") or sec.get("text") or "")
                sys_slices.append({"name": str(sec.get("name") or sec.get("title") or f"Section #{idx + 1}"), "tokens": max(1, estimate_tokens(len(content_s))), "color": palette[idx % len(palette)]})

    tool_slices: List[Dict[str, Any]] = []
    if raw_tools:
        buckets: Dict[str, int] = {name: 0 for name, _, _ in _TOOL_CATEGORY_SPEC} | {"Automation & Tasks": 0}
        colors = {name: col for name, col, _ in _TOOL_CATEGORY_SPEC} | {"Automation & Tasks": "#14b8a6"}
        for tool in raw_tools:
            tname = str((tool.get("name") if isinstance(tool, dict) else "") or "").lower()
            matched = next((cname for cname, _, kws in _TOOL_CATEGORY_SPEC if any(k in tname for k in kws)), "Automation & Tasks")
            buckets[matched] += max(15, estimate_tokens(len(json.dumps(tool))))
        tool_slices = [{"name": cname, "tokens": tok, "color": colors[cname]} for cname, tok in buckets.items() if tok > 0]
    return sys_slices, tool_slices


def _compute_honest_breakdown(
    steps: List[Dict[str, Any]],
    checkpoints: List[int],
    explicit_in_positions: Set[int],
    raw_steps: List[Dict[str, Any]],
    db_metrics: TrajectoryMetrics,
    epochs: Optional[List[Dict[str, Any]]] = None,
) -> Tuple[int, int, bool, Dict[str, int], List[Dict[str, Any]], List[Dict[str, Any]]]:
    """Computes per-epoch honest breakdowns (`unattributed` gap, zero synthetic 40/60 or `model += diff`)."""
    sys_slices, tool_slices = _extract_measured_slices(raw_steps)
    sys_prompt_tok = sum(sl["tokens"] for sl in sys_slices)
    tool_defs_tok = sum(sl["tokens"] for sl in tool_slices)

    def _score_slice(ep_start: int, ep_end: int, is_last: bool) -> Tuple[int, int, bool, Dict[str, int]]:
        ep_steps = steps[ep_start:ep_end + 1] if ep_end >= ep_start else []
        cache_tokens = explicit_usage = explicit_est = 0
        for rev_pos in range(len(ep_steps) - 1, -1, -1):
            s = ep_steps[rev_pos]
            if cache_tokens == 0 and s.get("cache_read_tokens"):
                cache_tokens = int(s["cache_read_tokens"] or 0)
            in_val, ca_val = int(s.get("input_tokens") or 0), int(s.get("cache_read_tokens") or 0)
            is_exp = (ep_start + rev_pos) in explicit_in_positions
            if explicit_usage == 0 and (s.get("type") != "USER_INPUT" or is_exp or ca_val > 0) and (in_val + ca_val > 0):
                explicit_usage = in_val + ca_val
            meta = s.get("metadata") if isinstance(s.get("metadata"), dict) else {}
            model_usage = meta.get("modelUsage") if isinstance(meta.get("modelUsage"), dict) else {}
            cwm = _extract_cwm(s)
            if cwm:
                etu = cwm.get("estimatedTokensUsed") or cwm.get("estimated_tokens_used")
                if isinstance(etu, (int, float)) and int(etu) > explicit_est:
                    explicit_est = int(etu)
            cum = meta.get("cumulative_context_tokens") or meta.get("cumulative_tokens") or meta.get("contextTokens") or model_usage.get("totalTokens")
            if isinstance(cum, (int, float)) and int(cum) > explicit_est:
                explicit_est = int(cum)
        if is_last:
            if cache_tokens == 0 and db_metrics.cache_read_tokens > 0:
                cache_tokens = int(db_metrics.cache_read_tokens)
            if explicit_usage == 0 and db_metrics.tokens > 0 and not db_metrics.is_provisional:
                explicit_usage = int(db_metrics.tokens)
            if explicit_est == 0 and db_metrics.tokens > 0:
                explicit_est = int(db_metrics.tokens)
        user_t = model_t = thought_t = tool_t = cp_t = sys_t = 0
        for s in ep_steps:
            stype, tok = s.get("type", ""), int(s.get("tokens") or 0)
            if stype == "USER_INPUT":
                user_t += tok
            elif stype == "CHECKPOINT":
                cp_t += tok
            elif stype == "SYSTEM":
                sys_t += tok
            elif stype in ("PLANNER_RESPONSE", "MODEL_OUTPUT"):
                raw_think = estimate_tokens(len(str(s.get("thinking") or ""))) if s.get("thinking") else 0
                raw_content = estimate_tokens(len(str(s.get("content") or "")))
                t_part = min(tok, round(tok * raw_think / (raw_think + raw_content))) if (raw_think > 0 and raw_content > 0 and tok > 0) else min(tok, raw_think)
                thought_t += t_part
                model_t += max(0, tok - t_part)
            else:
                tool_t += tok
        measured = sys_prompt_tok + tool_defs_tok + cp_t + user_t + model_t + thought_t + tool_t + sys_t
        total_tokens = explicit_usage if explicit_usage > 0 else (max(explicit_est, measured) if explicit_est > 0 else measured)
        is_provisional = (explicit_usage == 0) and (total_tokens > 0)
        unattributed = max(0, total_tokens - measured)
        bd = {
            "system_prompt": sys_prompt_tok, "tool_defs": tool_defs_tok, "checkpoint": cp_t,
            "user": user_t, "model": model_t, "thought": thought_t, "tool": tool_t, "system": sys_t, "unattributed": unattributed,
        }
        return total_tokens, cache_tokens, is_provisional, bd

    target_epochs = epochs if epochs else [{"start_index": checkpoints[-1] if checkpoints else 0, "end_index": len(steps) - 1}]
    last_res: Tuple[int, int, bool, Dict[str, int]] = (0, 0, False, {"system_prompt": sys_prompt_tok, "tool_defs": tool_defs_tok, "checkpoint": 0, "user": 0, "model": 0, "thought": 0, "tool": 0, "system": 0, "unattributed": 0})
    for idx, ep in enumerate(target_epochs):
        ep_res = _score_slice(int(ep.get("start_index", 0)), int(ep.get("end_index", -1)), idx == len(target_epochs) - 1)
        if epochs is not None:
            ep["total_tokens"], ep["cache_tokens"], ep["is_provisional"], ep["token_breakdown"] = ep_res
            ep["unattributed"] = ep_res[3]["unattributed"]
        last_res = ep_res
    return last_res[0], last_res[1], last_res[2], last_res[3], sys_slices, tool_slices


def load_conversation_trajectory(
    conversation_id: str,
    brain_dir: Optional[Path] = None,
    _visited: Optional[Set[str]] = None,
    parent_id: Optional[str] = None,
) -> Dict[str, Any]:
    """Loads trajectory steps, SSOT metrics, and direct child subagents from disk & SQLite."""
    visited = _visited if _visited is not None else set()
    visited.add(conversation_id)

    base_brain = get_active_brain_dir(brain_dir)
    convo_dir = base_brain / conversation_id
    transcript_path, _ = find_transcript_path(convo_dir)
    raw_steps, raw_line_sizes, ts_map = load_transcript_steps(transcript_path) if transcript_path else ([], [], {})
    db_metrics = read_db_trajectory_state(conversation_id, transcript_timestamps=ts_map)

    resolved_parent_id, subagents, subagent_infos = _resolve_lineage_and_subagents(conversation_id, raw_steps, base_brain, parent_id)
    session_model, max_context_tokens = _resolve_session_metadata(convo_dir, raw_steps, db_metrics)
    steps, explicit_in_positions = _enrich_and_sort_steps(raw_steps, raw_line_sizes, session_model)
    checkpoints = [i for i, s in enumerate(steps) if s.get("type") == "CHECKPOINT"]
    epochs = _partition_epochs(steps, checkpoints)

    total_tokens, cache_tokens, is_provisional, breakdown, sys_slices, tool_slices = _compute_honest_breakdown(
        steps, checkpoints, explicit_in_positions, raw_steps, db_metrics, epochs=epochs
    )

    burn_rate = db_metrics.burn_rate_tokens_per_min
    if burn_rate <= 0.0:
        active_steps = steps[checkpoints[-1]:] if checkpoints else steps
        samples = [
            (parse_step_timestamp(s.get("created_at") or s.get("timestamp")) or ts_map.get(int(s["step_index"])), int(s.get("input_tokens", 0) + s.get("cache_read_tokens", 0)) or int(s.get("cumulative_tokens", 0)))
            for s in active_steps
        ]
        valid = [(t, tok) for t, tok in samples if t is not None and tok > 0]
        if len(valid) >= 2 and valid[-1][0] > valid[0][0] and valid[-1][1] > valid[0][1]:
            burn_rate = ((valid[-1][1] - valid[0][1]) / (valid[-1][0] - valid[0][0])) * 60.0

    subagent_trajectories: Dict[str, Any] = {}
    if parent_id is None:
        for sid in subagents:
            if sid not in visited:
                try:
                    subagent_trajectories[sid] = load_conversation_trajectory(sid, brain_dir=base_brain, _visited=visited, parent_id=conversation_id)
                except (OSError, ValueError, KeyError, json.JSONDecodeError):
                    continue

    return {
        "conversation_id": conversation_id,
        "transcript_path": str(transcript_path or (convo_dir / ".system_generated" / "logs" / "transcript.jsonl")),
        "summary": _extract_conversation_summary(convo_dir, transcript_path or (convo_dir / "transcript.jsonl")),
        "model": session_model,
        "steps": steps,
        "step_count": len(steps),
        "epochs": epochs,
        "epoch_index": len(checkpoints),
        "epoch_steps": len(steps) - (checkpoints[-1] + 1 if checkpoints else 0),
        "checkpoint_count": len(checkpoints),
        "parent_id": resolved_parent_id,
        "subagents": subagents,
        "subagent_infos": subagent_infos,
        "subagent_trajectories": subagent_trajectories,
        "total_tokens": total_tokens,
        "max_context_tokens": max_context_tokens,
        "cache_tokens": cache_tokens,
        "is_provisional": is_provisional,
        "burn_rate_tokens_per_min": round(float(burn_rate), 1),
        "velocity_tier": db_metrics.velocity_tier,
        "token_breakdown": breakdown,
        "system_prompt_slices": sys_slices,
        "tool_def_slices": tool_slices,
    }


def get_recent_conversations(brain_dir: Optional[Path] = None, limit: int = 30) -> List[Dict[str, Any]]:
    """Discovers recent Antigravity conversations sorted by modification time."""
    base_brain = get_active_brain_dir(brain_dir)
    if not base_brain.is_dir():
        return []

    conversations: List[Dict[str, Any]] = []
    for d in base_brain.iterdir():
        if d.is_dir() and d.name != ".system_generated":
            t_log, _ = find_transcript_path(d)
            if t_log and t_log.is_file():
                try:
                    conversations.append({"id": d.name, "summary": _extract_conversation_summary(d, t_log), "mtime": t_log.stat().st_mtime})
                except OSError:
                    continue

    conversations.sort(key=lambda c: c["mtime"], reverse=True)
    return conversations[:limit]


def _load_hud_template() -> str:
    """Dynamically composes the HUD in-situ JS/CSS template from modular assets (PSL-INV-011)."""
    assets = importlib.resources.files("harness.gui.assets")
    return (
        assets.joinpath("hud.js").read_text(encoding="utf-8")
        .replace("/* __HUD_STYLES__ */", assets.joinpath("hud_styles.css").read_text(encoding="utf-8"), 1)
        .replace("/* __HUD_HEADER__ */", assets.joinpath("hud_header.js").read_text(encoding="utf-8"), 1)
        .replace("/* __HUD_CONTEXT_BAR__ */", assets.joinpath("hud_context_bar.js").read_text(encoding="utf-8"), 1)
        .replace("/* __HUD_TIMELINE__ */", assets.joinpath("hud_timeline.js").read_text(encoding="utf-8"), 1)
        .replace("/* __HUD_INSPECTOR__ */", assets.joinpath("hud_inspector.js").read_text(encoding="utf-8"), 1)
        .replace("/* __HUD_DECK__ */", assets.joinpath("hud_deck.js").read_text(encoding="utf-8"), 1)
        .replace("/* __HUD_RPC__ */", assets.joinpath("hud_rpc.js").read_text(encoding="utf-8"), 1)
    )


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
    return _load_hud_template().replace("const __PAYLOAD__ = null;", f"const __PAYLOAD__ = {json.dumps(payload)};", 1)
