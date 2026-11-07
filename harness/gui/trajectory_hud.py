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

    if existing_type and existing_type in (
        "PLANNER_RESPONSE", "USER_INPUT", "RUN_COMMAND", "VIEW_FILE",
        "REPLACE_FILE_CONTENT", "WRITE_FILE", "GREP_SEARCH", "FIND_FILES",
        "SEND_MESSAGE", "INVOKE_SUBAGENT", "MODEL_OUTPUT", "SYSTEM", "TOOL_CALL"
    ):
        return existing_type

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
    if transcript_path.is_file():
        try:
            with open(transcript_path, "r", encoding="utf-8", errors="replace") as f:
                for line in f:
                    line = line.strip()
                    if line:
                        try:
                            raw_steps.append(json.loads(line))
                        except (json.JSONDecodeError, UnicodeDecodeError, ValueError):
                            continue
        except OSError:
            pass

    resolved_parent_id: Optional[str] = parent_id
    subagents: List[str] = []
    subagent_infos: List[Dict[str, Any]] = []

    # Check for direct child subagent invocations
    for step in raw_steps:
        tool_calls = step.get("tool_calls", [])
        for tc in tool_calls:
            tc_name = str(tc.get("name", ""))
            output_str = str(tc.get("output", ""))
            args_str = str(tc.get("args", ""))
            combined = output_str + " " + args_str

            found_ids: List[str] = []
            m_convo = re.search(r"conversation[_-]?id[\"':\s]+([a-zA-Z0-9_\-]+)", combined, re.I)
            if m_convo:
                found_ids.append(m_convo.group(1))
            uuids = re.findall(r"[0-9a-zA-Z]{8}-[0-9a-zA-Z]{4}-[0-9a-zA-Z]{4}-[0-9a-zA-Z]{4}-[0-9a-zA-Z]{12}", combined)
            for u in uuids:
                if u not in found_ids:
                    found_ids.append(u)

            for sid in found_ids:
                if sid != conversation_id and sid not in subagents:
                    subagents.append(sid)
                    subagent_infos.append({
                        "id": sid,
                        "name": tc.get("args", {}).get("name") or tc.get("args", {}).get("agent_role") or f"Subagent {sid[:8]}",
                        "summary": str(tc.get("args", {}).get("objective") or tc.get("args", {}).get("prompt") or "")[:80],
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

    # Enrich steps: timing metrics, byte sizes, cortex types, cumulative context tokens
    steps: List[Dict[str, Any]] = []
    total_tokens = 0
    cache_tokens = 0
    cumulative_ctx = 0

    token_breakdown = {
        "system_prompt": 3800,
        "tool_defs": 3200,
        "checkpoint": 0,
        "user": 0,
        "model": 0,
        "tool": 0,
        "system": 0,
    }

    for idx, raw in enumerate(raw_steps):
        s = dict(raw)
        s["step_index"] = s.get("step_index", idx)
        s["exec_index"] = s.get("exec_index", 1)
        s["inv_index"] = s.get("inv_index", 1)
        cortex_type = _map_to_cortex_type(s)
        s["type"] = cortex_type

        # Payload byte size calculation (SIZE column)
        try:
            s["size_bytes"] = len(json.dumps(s).encode("utf-8"))
        except (TypeError, ValueError):
            s["size_bytes"] = 0

        # Step timing metrics: thinking_duration_ms (TTFT) and streaming_duration_ms
        meta = s.get("metadata", {})
        thinking_ms = s.get("thinking_duration_ms")
        if thinking_ms is None:
            thinking_ms = meta.get("thinking_duration_ms") or meta.get("ttft_ms")
            if thinking_ms is None:
                if s.get("thinking"):
                    # Derive empirical TTFT estimate based on thinking tokens length
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

        # Tokens metrics
        in_tok = int(s.get("input_tokens") or 0)
        out_tok = int(s.get("output_tokens") or 0)
        step_tok = in_tok + out_tok
        if step_tok > 0:
            cumulative_ctx = in_tok + out_tok
        s["tokens"] = step_tok or int(s.get("tokens") or 0)
        s["cumulative_tokens"] = cumulative_ctx
        steps.append(s)

    for s in reversed(steps):
        if s.get("input_tokens") or s.get("output_tokens") or s.get("cache_read_tokens"):
            total_tokens = (s.get("input_tokens") or 0) + (s.get("output_tokens") or 0)
            cache_tokens = s.get("cache_read_tokens") or 0
            break

    if total_tokens <= 0:
        total_tokens = max(1000, len(steps) * 150)

    # Proportional token breakdown normalized to exactly total_tokens (sum == total_tokens)
    sys_prompt_tok = min(4000, max(400, int(total_tokens * 0.15))) if total_tokens >= 4000 else min(total_tokens // 4, 1000)
    tool_defs_tok = min(3500, max(300, int(total_tokens * 0.12))) if total_tokens >= 4000 else min(total_tokens // 4, 800)
    checkpoint_tok = 0

    remaining = max(0, total_tokens - (sys_prompt_tok + tool_defs_tok + checkpoint_tok))

    user_weight = sum(1 for s in steps if s.get("type") == "USER_INPUT") or 1
    model_weight = sum(1 for s in steps if s.get("type") in ("PLANNER_RESPONSE", "MODEL_OUTPUT")) or 1
    tool_weight = sum(1 for s in steps if s.get("type") in ("TOOL_CALL", "RUN_COMMAND", "VIEW_FILE", "REPLACE_FILE_CONTENT", "WRITE_FILE", "GREP_SEARCH", "FIND_FILES")) or 1
    system_weight = sum(1 for s in steps if s.get("type") == "SYSTEM") or 0
    total_weight = user_weight + model_weight + tool_weight + system_weight or 1

    user_tok = int(remaining * (user_weight / total_weight))
    model_tok = int(remaining * (model_weight / total_weight))
    tool_tok = int(remaining * (tool_weight / total_weight))
    system_tok = max(0, remaining - (user_tok + model_tok + tool_tok))

    token_breakdown = {
        "system_prompt": sys_prompt_tok,
        "tool_defs": tool_defs_tok,
        "checkpoint": checkpoint_tok,
        "user": user_tok,
        "model": model_tok,
        "tool": tool_tok,
        "system": system_tok,
    }
    # Guarantee sum(token_breakdown.values()) == total_tokens exactly
    diff = total_tokens - sum(token_breakdown.values())
    token_breakdown["model"] += diff

    # Pre-bundle direct child subagents recursively into subagent_trajectories map
    subagent_trajectories: Dict[str, Any] = {}
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

    summary = _extract_conversation_summary(convo_dir, transcript_path)

    return {
        "conversation_id": conversation_id,
        "transcript_path": str(transcript_path),
        "summary": summary,
        "steps": steps,
        "step_count": len(steps),
        "parent_id": resolved_parent_id,
        "subagents": subagents,
        "subagent_infos": subagent_infos,
        "subagent_trajectories": subagent_trajectories,
        "total_tokens": total_tokens,
        "cache_tokens": cache_tokens,
        "token_breakdown": token_breakdown,
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


_HUD_TEMPLATE = r"""
(() => {
    const HUD_ID = "agyis-trajectory-hud";
    const STYLES_ID = "agyis-trajectory-hud-styles";
    const __PAYLOAD__ = null;
    const initialData = __PAYLOAD__.initialData;
    const conversationList = __PAYLOAD__.conversationList;
    const shouldOpen = __PAYLOAD__.shouldOpen;
    const isToggle = __PAYLOAD__.isToggle;

    if (!document.getElementById(STYLES_ID)) {
        const styleEl = document.createElement("style");
        styleEl.id = STYLES_ID;
        styleEl.textContent = `
            #agyis-trajectory-hud {
                position: fixed;
                inset: 0;
                z-index: 99999;
                display: flex;
                align-items: center;
                justify-content: center;
                background: rgba(0, 0, 0, 0.75);
                backdrop-filter: blur(8px);
                font-family: ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
                color: #f4f4f5;
                box-sizing: border-box;
            }
            #agyis-trajectory-hud * { box-sizing: border-box; }
            .agyis-hud-box {
                width: 95vw;
                max-width: 1440px;
                height: 90vh;
                background: #18181b;
                border: 1px solid #27272a;
                border-radius: 12px;
                box-shadow: 0 25px 50px -12px rgba(0, 0, 0, 0.9);
                display: flex;
                flex-direction: column;
                overflow: hidden;
                transition: all 0.2s ease-in-out;
            }
            .agyis-hud-box.maximized {
                width: 100vw !important;
                max-width: 100vw !important;
                height: 100vh !important;
                border-radius: 0 !important;
                border: none !important;
            }
            .agyis-hud-header {
                display: flex;
                align-items: center;
                justify-content: space-between;
                padding: 8px 14px;
                background: #121214;
                border-bottom: 1px solid #27272a;
                gap: 10px;
                flex-wrap: wrap;
                position: relative;
                z-index: 100;
            }
            .agyis-hud-header-left { display: flex; align-items: center; gap: 8px; min-width: 0; flex-wrap: wrap; }
            .agyis-hud-header-right { display: flex; align-items: center; gap: 8px; }
            .agyis-hud-pill {
                display: inline-flex;
                align-items: center;
                gap: 5px;
                padding: 3px 8px;
                border-radius: 9999px;
                font-size: 11px;
                font-weight: 600;
                line-height: 1.2;
                border: 1px solid transparent;
            }
            .agyis-hud-pill-purple { background: rgba(168, 85, 247, 0.12); color: #c084fc; border-color: rgba(168, 85, 247, 0.3); }
            .agyis-hud-pill-blue { background: rgba(59, 130, 246, 0.12); color: #60a5fa; border-color: rgba(59, 130, 246, 0.3); }
            .agyis-hud-pill-amber { background: rgba(245, 158, 11, 0.12); color: #fbbf24; border-color: rgba(245, 158, 11, 0.3); }
            .agyis-hud-pill-green { background: rgba(16, 185, 129, 0.12); color: #34d399; border-color: rgba(16, 185, 129, 0.3); }
            .agyis-hud-pill-teal { background: rgba(20, 184, 166, 0.12); color: #2dd4bf; border-color: rgba(20, 184, 166, 0.3); }
            .agyis-hud-pill-red { background: rgba(239, 68, 68, 0.12); color: #f87171; border-color: rgba(239, 68, 68, 0.3); }
            .agyis-hud-pill-zinc { background: rgba(113, 113, 122, 0.12); color: #a1a1aa; border-color: rgba(113, 113, 122, 0.3); }
            .agyis-hud-btn {
                background: #27272a;
                border: 1px solid #3f3f46;
                color: #f4f4f5;
                border-radius: 6px;
                padding: 4px 8px;
                font-size: 11px;
                font-weight: 500;
                cursor: pointer;
                display: inline-flex;
                align-items: center;
                gap: 5px;
                transition: background 0.15s, border-color 0.15s;
                user-select: none;
            }
            .agyis-hud-btn:hover { background: #3f3f46; border-color: #52525b; }
            .agyis-hud-btn.active { background: #3f3f46; border-color: #f59e0b; color: #fbbf24; font-weight: 600; }
            .agyis-hud-select {
                background: #202023;
                border: 1px solid #3f3f46;
                color: #f4f4f5;
                border-radius: 6px;
                padding: 4px 8px;
                font-size: 11px;
                outline: none;
                max-width: 260px;
                cursor: pointer;
            }
            .agyis-hud-search-box {
                display: flex;
                align-items: center;
                background: #202023;
                border: 1px solid #3f3f46;
                border-radius: 6px;
                padding: 0 6px;
                height: 26px;
                position: relative;
            }
            .agyis-hud-search-input {
                background: transparent;
                border: none;
                color: #f4f4f5;
                font-size: 11px;
                outline: none;
                width: 130px;
                transition: width 0.2s;
            }
            .agyis-hud-search-input:focus { width: 180px; }
            .agyis-hud-search-counter { font-size: 10px; color: #a1a1aa; margin: 0 4px; font-family: monospace; white-space: nowrap; }

            /* 2.26.0 Context Window Bar ('Dlc' Parity) */
            .context-cell-selected {
                box-shadow: 0 0 0 2px #eab308 !important;
            }
            .context-cell-hovered,
            .context-cell-unused:hover {
                box-shadow: 0 0 0 1px rgba(234, 179, 8, 0.8) !important;
            }
            .context-tooltip {
                border-color: rgba(234, 179, 8, 0.8) !important;
            }
            .agyis-context-bar-wrap {
                padding: 8px 14px;
                background: #151518;
                border-bottom: 1px solid #27272a;
                display: flex;
                flex-direction: column;
                gap: 6px;
                position: relative;
                z-index: 50;
            }
            .agyis-context-track {
                width: 100%;
                height: 18px;
                background: #27272a;
                border-radius: 4px;
                border: 1px solid #3f3f46;
                position: relative;
                overflow: hidden;
                display: flex;
            }
            .agyis-context-segment {
                height: 100%;
                cursor: pointer;
                transition: filter 0.15s, opacity 0.15s;
                position: relative;
                border-right: 1px solid rgba(0, 0, 0, 0.35);
            }
            .agyis-context-segment:hover { filter: brightness(1.25); z-index: 20; }
            .agyis-context-tooltip {
                position: absolute;
                top: 100%;
                margin-top: 6px;
                left: 14px;
                background: #18181b;
                border: 1px solid rgba(234, 179, 8, 0.8);
                border-radius: 6px;
                padding: 6px 10px;
                font-size: 11px;
                font-family: ui-monospace, monospace;
                color: #f4f4f5;
                box-shadow: 0 10px 25px rgba(0, 0, 0, 0.8);
                z-index: 100;
                pointer-events: none;
                max-width: 400px;
                white-space: pre-wrap;
            }
            .agyis-context-legend {
                display: flex;
                align-items: center;
                justify-content: space-between;
                font-size: 11px;
                color: #a1a1aa;
                gap: 12px;
                flex-wrap: wrap;
            }
            .agyis-legend-item { display: inline-flex; align-items: center; gap: 4px; }
            .agyis-legend-dot { width: 8px; height: 8px; border-radius: 50%; }

            /* 8-column CSS Grid History Table ('rmc' Parity) */
            .agyis-hud-main-deck {
                flex: 1;
                display: flex;
                overflow: hidden;
                background: #18181b;
            }
            .agyis-hud-main-deck.vertical { flex-direction: column; }
            .agyis-grid-pane {
                flex: 1;
                display: flex;
                flex-direction: column;
                min-width: 480px;
                min-height: 200px;
                border-right: 1px solid #27272a;
                overflow: hidden;
                background: #18181b;
            }
            .agyis-hud-main-deck.vertical .agyis-grid-pane { border-right: none; border-bottom: 1px solid #27272a; }
            .agyis-step-grid-row {
                display: grid;
                grid-template-columns: 50px 50px 55px 140px 1fr 70px 80px 80px;
                height: 32px;
                align-items: center;
                font-size: 11px;
                border-bottom: 1px solid #232326;
                padding: 0 8px;
                gap: 6px;
            }
            .agyis-step-grid-header {
                background: #141416;
                font-weight: 700;
                color: #71717a;
                text-transform: uppercase;
                letter-spacing: 0.05em;
                position: sticky;
                top: 0;
                z-index: 10;
                border-bottom: 1px solid #27272a;
            }
            .agyis-step-grid-body {
                flex: 1;
                overflow-y: auto;
            }
            .agyis-step-grid-item {
                cursor: pointer;
                transition: background 0.1s;
                font-family: ui-monospace, monospace;
            }
            .agyis-step-grid-item:hover { background: #202024; }
            .agyis-step-grid-item.selected {
                background: #27241d;
                border-left: 2px solid #eab308;
            }

            /* Resizable Splitter */
            .agyis-splitter {
                width: 6px;
                background: #27272a;
                cursor: col-resize;
                transition: background 0.15s;
                flex-shrink: 0;
            }
            .agyis-hud-main-deck.vertical .agyis-splitter {
                width: 100%;
                height: 6px;
                cursor: row-resize;
            }
            .agyis-splitter:hover { background: #f59e0b; }

            /* Step Inspector ('jmc' & 'fmc' Parity) */
            .agyis-inspector-pane {
                flex: 1.1;
                display: flex;
                flex-direction: column;
                min-width: 420px;
                min-height: 200px;
                overflow: hidden;
                background: #18181b;
            }
            .agyis-inspector-header {
                display: flex;
                align-items: center;
                justify-content: space-between;
                padding: 8px 14px;
                background: #141416;
                border-bottom: 1px solid #27272a;
                gap: 8px;
            }
            .agyis-inspector-tabs {
                display: flex;
                gap: 4px;
                padding: 6px 14px;
                background: #18181b;
                border-bottom: 1px solid #27272a;
            }
            .agyis-inspector-content {
                flex: 1;
                overflow-y: auto;
                padding: 14px;
                font-size: 12px;
                line-height: 1.5;
            }
            .agyis-timing-bar-wrap {
                background: #202023;
                border: 1px solid #3f3f46;
                border-radius: 6px;
                padding: 8px 12px;
                margin-bottom: 12px;
                display: flex;
                flex-direction: column;
                gap: 6px;
            }
            .agyis-timing-bar {
                height: 10px;
                background: #27272a;
                border-radius: 4px;
                overflow: hidden;
                display: flex;
            }
            .agyis-codeblock {
                background: #0d0d0f;
                border: 1px solid #27272a;
                border-radius: 6px;
                padding: 10px;
                font-family: ui-monospace, monospace;
                font-size: 11px;
                white-space: pre-wrap;
                word-break: break-all;
                overflow-x: auto;
                color: #e4e4e7;
            }
            .agyis-markdown-table {
                width: 100%;
                border-collapse: collapse;
                margin: 8px 0;
                font-size: 11px;
            }
            .agyis-markdown-table th, .agyis-markdown-table td {
                border: 1px solid #3f3f46;
                padding: 6px 8px;
                text-align: left;
            }
            .agyis-markdown-table th { background: #202023; color: #fbbf24; }
        `;
        document.head.appendChild(styleEl);
    }

    let existingHud = document.getElementById(HUD_ID);
    if (existingHud) {
        if (isToggle) {
            const isHidden = existingHud.style.display === "none";
            if (isHidden) {
                const match = window.location.pathname.match(/\/c\/([a-f0-9\-]+)/);
                const focusedConvoId = match ? match[1] : null;
                const state = window.__agyis_hud_state;
                if (focusedConvoId && state && focusedConvoId !== state.convoId && typeof window.__agyis_hud_load_convo === "function") {
                    window.__agyis_hud_load_convo(focusedConvoId);
                }
            }
            existingHud.style.display = isHidden ? "flex" : "none";
            return { success: true, open: isHidden, toggled: true };
        }
        // Stale DOM Replacement: Purge existing HUD and styles on re-injection (PSL-INV-010)
        existingHud.remove();
        const existingStyles = document.getElementById(STYLES_ID);
        if (existingStyles) existingStyles.remove();
    }

    const hud = document.createElement("div");
    hud.id = HUD_ID;
    hud.style.display = shouldOpen ? "flex" : "none";

    window.__agyis_hud_state = {
        rootData: initialData,
        currentData: initialData,
        convoId: initialData.conversation_id,
        selectedIndex: Math.max(0, (initialData.steps || []).length - 1),
        filterQuery: "",
        searchMatchIndices: [],
        currentMatchIdx: -1,
        activeTab: "step", // step, invocation, execution, trajectory
        layoutOrientation: "horizontal", // horizontal (side-by-side) vs vertical (stacked)
        isMaximized: false,
        subagentsDropdownOpen: false,
        hoveredContextSegment: null,
    };

    window.__agyis_hud_load_convo = async function(convoId) {
        if (!convoId) return null;
        try {
            const resp = await fetch("http://127.0.0.1:40624/api/trajectory?id=" + encodeURIComponent(convoId));
            if (resp.ok) {
                const data = await resp.json();
                const state = window.__agyis_hud_state;
                if (state) {
                    state.rootData = data;
                    state.currentData = data;
                    state.convoId = data.conversation_id || convoId;
                    state.selectedIndex = Math.max(0, (data.steps || []).length - 1);
                    state.subagentsDropdownOpen = false;
                    renderHud();
                }
                return data;
            }
        } catch (err) {
            console.warn("[agyis] Trajectory server fetch failed, using local fallback data:", err);
        }
        return null;
    };

    function formatBytes(bytes) {
        if (!bytes || bytes <= 0) return "0 B";
        const k = 1024;
        const dm = 1;
        const sizes = ["B", "KB", "MB", "GB"];
        const i = Math.floor(Math.log(bytes) / Math.log(k));
        return parseFloat((bytes / Math.pow(k, i)).toFixed(dm)) + " " + sizes[i];
    }

    function renderMarkdownPreview(rawText) {
        if (!rawText) return "<div style='color: #71717a;'>No preview content</div>";
        let escaped = rawText.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");

        // Code blocks
        escaped = escaped.replace(/```([a-zA-Z0-9_-]*)\n([\s\S]*?)```/g, (m, lang, code) => {
            return `<pre class="agyis-codeblock"><code class="language-${lang || 'none'}">${code.trim()}</code></pre>`;
        });

        // Inline code
        escaped = escaped.replace(/`([^`]+)`/g, "<code style='background: #27272a; padding: 2px 4px; border-radius: 4px; font-family: monospace;'>$1</code>");

        // Simple Markdown Tables
        if (escaped.includes("|") && escaped.includes("\n")) {
            const lines = escaped.split("\n");
            let inTable = false;
            let tableHtml = "<table class='agyis-markdown-table'>";
            let remainingLines = [];

            for (let i = 0; i < lines.length; i++) {
                const line = lines[i].trim();
                if (line.startsWith("|") && line.endsWith("|")) {
                    if (!inTable) { inTable = true; }
                    const cols = line.split("|").slice(1, -1).map(c => c.trim());
                    if (cols.every(c => c.match(/^:?-+:?$/))) {
                        continue; // table header separator
                    }
                    const isTh = tableHtml.indexOf("<tr>") === -1;
                    const tag = isTh ? "th" : "td";
                    tableHtml += `<tr>${cols.map(c => `<${tag}>${c}</${tag}>`).join("")}</tr>`;
                } else {
                    if (inTable) {
                        inTable = false;
                        tableHtml += "</table>";
                        remainingLines.push(tableHtml);
                    }
                    remainingLines.push(line);
                }
            }
            if (inTable) { tableHtml += "</table>"; remainingLines.push(tableHtml); }
            escaped = remainingLines.join("<br>");
        } else {
            escaped = escaped.replace(/\n/g, "<br>");
        }

        return `<div class="agyis-markdown-body" style="word-break: break-word;">${escaped}</div>`;
    }

    function renderHud() {
        const state = window.__agyis_hud_state;
        const cur = state.currentData;
        const steps = cur.steps || [];
        const currentStep = steps[state.selectedIndex] || null;

        // Filter and Search Matching
        const q = (state.filterQuery || "").trim().toLowerCase();
        const filteredIndices = [];
        for (let i = 0; i < steps.length; i++) {
            const s = steps[i];
            if (!q) {
                filteredIndices.push(i);
                continue;
            }
            const typeStr = (s.type || "").toLowerCase();
            const contentStr = (s.content || "").toLowerCase();
            const thinkStr = (s.thinking || "").toLowerCase();
            const toolStr = (s.tool_calls || []).map(t => (t.name || "") + " " + JSON.stringify(t.args || {})).join(" ").toLowerCase();
            if (typeStr.includes(q) || contentStr.includes(q) || thinkStr.includes(q) || toolStr.includes(q)) {
                filteredIndices.push(i);
            }
        }
        state.searchMatchIndices = filteredIndices;

        // Context Window Bar Calculations ('Dlc' Parity)
        const totalTokens = cur.total_tokens || 0;
        const maxTokens = 200000;
        const unusedTokens = Math.max(0, maxTokens - totalTokens);
        const breakdown = cur.token_breakdown || {
            system_prompt: 3800,
            tool_defs: 3200,
            checkpoint: 0,
            user: 0,
            model: 0,
            tool: 0,
            system: 0,
        };

        const segmentsDef = [
            { id: "sys-prompt", name: "System Prompt", tokens: breakdown.system_prompt || 3800, color: "#6366f1", bgClass: "bg-indigo-500" },
            { id: "tool-defs", name: "Tool Defs", tokens: breakdown.tool_defs || 3200, color: "#06b6d4", bgClass: "bg-cyan-500" },
            { id: "checkpoint", name: "Checkpoint", tokens: breakdown.checkpoint || 0, color: "#16a34a", bgClass: "bg-green-600" },
            { id: "user", name: "User", tokens: breakdown.user || 0, color: "#3b82f6", bgClass: "bg-blue-500" },
            { id: "model", name: "Model", tokens: breakdown.model || 0, color: "#f59e0b", bgClass: "bg-amber-500" },
            { id: "tool", name: "Tool", tokens: breakdown.tool || 0, color: "#14b8a6", bgClass: "bg-teal-500" },
            { id: "system", name: "System", tokens: breakdown.system || 0, color: "#a855f7", bgClass: "bg-purple-500" },
            { id: "unused", name: "Unused", tokens: unusedTokens, color: "#27272a", bgClass: "bg-muted/60" },
        ];

        let barSegmentsHtml = "";
        segmentsDef.forEach(seg => {
            if (seg.tokens <= 0 && seg.id !== "unused") return;
            const pct = Math.max(0.2, (seg.tokens / maxTokens) * 100);
            const isUnused = seg.id === "unused";
            barSegmentsHtml += `
                <div class="agyis-context-segment ${isUnused ? 'context-cell-unused' : ''}"
                     data-seg-id="${seg.id}"
                     data-seg-name="${seg.name}"
                     data-seg-tokens="${seg.tokens}"
                     data-seg-pct="${((seg.tokens / maxTokens) * 100).toFixed(1)}"
                     style="width: ${pct}%; background: ${seg.color};">
                </div>
            `;
        });

        // Subagents Map & Dropdown
        const subagents = cur.subagents || [];
        const subagentInfos = cur.subagent_infos || [];
        const isChildView = Boolean(cur.parent_id);

        let subagentsDropdownHtml = "";
        if (subagents.length > 0) {
            const items = subagents.map((sid, idx) => {
                const info = subagentInfos.find(si => si.id === sid) || { name: `Subagent #${idx + 1}`, summary: sid };
                return `
                    <div class="agyis-subagent-item" data-sub-id="${sid}" style="padding: 6px 10px; cursor: pointer; border-bottom: 1px solid #27272a; transition: background 0.15s;" onmouseover="this.style.background='#27272a'" onmouseout="this.style.background='transparent'">
                        <div style="font-weight: 600; color: #c084fc; font-size: 11px;">${info.name}</div>
                        <div style="font-size: 10px; color: #a1a1aa; font-family: monospace;">${sid.slice(0, 16)}...</div>
                    </div>
                `;
            }).join("");

            subagentsDropdownHtml = `
                <div style="position: relative;">
                    <button id="agyis-subagents-dropdown-toggle" class="agyis-hud-pill agyis-hud-pill-purple" style="cursor: pointer;">
                        [ ${subagents.length} Child Subagent${subagents.length === 1 ? '' : 's'} ▾ ]
                    </button>
                    <div id="agyis-subagents-menu" style="display: ${state.subagentsDropdownOpen ? 'block' : 'none'}; position: absolute; top: 100%; left: 0; margin-top: 4px; background: #18181b; border: 1px solid #3f3f46; border-radius: 6px; box-shadow: 0 10px 25px rgba(0,0,0,0.8); z-index: 200; min-width: 240px; max-height: 220px; overflow-y: auto;">
                        ${items}
                    </div>
                </div>
            `;
        }

        // History Table Grid Rows ('rmc' Parity)
        const gridRowsHtml = filteredIndices.map(idx => {
            const s = steps[idx];
            const isSel = idx === state.selectedIndex;
            const type = s.type || "STEP";
            let pillClass = "agyis-hud-pill-blue";
            if (type === "PLANNER_RESPONSE") pillClass = "agyis-hud-pill-amber";
            else if (type.includes("COMMAND") || type.includes("TOOL")) pillClass = "agyis-hud-pill-teal";
            else if (type.includes("FILE") || type.includes("WRITE") || type.includes("REPLACE")) pillClass = "agyis-hud-pill-green";
            else if (type === "INVOKE_SUBAGENT") pillClass = "agyis-hud-pill-purple";
            else if (type === "SYSTEM") pillClass = "agyis-hud-pill-zinc";

            const status = s.status || "DONE";
            let statusPillClass = "agyis-hud-pill-green";
            if (status === "ERROR") statusPillClass = "agyis-hud-pill-red";
            else if (status === "RUNNING") statusPillClass = "agyis-hud-pill-blue";
            else if (status === "WAITING") statusPillClass = "agyis-hud-pill-amber";

            let details = s.thinking ? s.thinking : (s.content ? s.content : "");
            if (!details && (s.tool_calls || []).length > 0) {
                details = s.tool_calls.map(tc => tc.name + "(" + JSON.stringify(tc.args || {}) + ")").join("; ");
            }
            details = details.replace(/\n/g, " ").slice(0, 160).replace(/</g, "&lt;").replace(/>/g, "&gt;");

            const sizeStr = formatBytes(s.size_bytes);
            const tokensStr = (s.tokens || 0).toLocaleString();

            return `
                <div class="agyis-step-grid-row agyis-step-grid-item ${isSel ? 'selected' : ''}" data-index="${idx}">
                    <div style="color: #71717a;">${s.exec_index || 1}</div>
                    <div style="color: #71717a;">${s.inv_index || 1}</div>
                    <div style="font-weight: 700;">#${s.step_index ?? idx}</div>
                    <div><span class="agyis-hud-pill ${pillClass}">${type}</span></div>
                    <div style="color: #a1a1aa; overflow: hidden; text-overflow: ellipsis; white-space: nowrap;">${details || "—"}</div>
                    <div><span class="agyis-hud-pill ${statusPillClass}">${status}</span></div>
                    <div style="text-align: right; color: #cbd5e1;">${tokensStr}</div>
                    <div style="text-align: right; color: #71717a;">${sizeStr}</div>
                </div>
            `;
        }).join("");

        // Step Inspector Body
        let inspectorContentHtml = "";
        let timingBarHtml = "";
        if (currentStep) {
            const ttftSec = ((currentStep.thinking_duration_ms || 0) / 1000).toFixed(2);
            const streamSec = ((currentStep.streaming_duration_ms || 0) / 1000).toFixed(2);
            const totalSec = ((currentStep.total_duration_ms || 0) / 1000).toFixed(2);
            const totalMs = Math.max(1, (currentStep.total_duration_ms || 1));
            const ttftPct = Math.round(((currentStep.thinking_duration_ms || 0) / totalMs) * 100);
            const streamPct = 100 - ttftPct;

            timingBarHtml = `
                <div class="agyis-timing-bar-wrap">
                    <div style="display: flex; justify-content: space-between; font-size: 11px;">
                        <span><b style="color: #f59e0b;">TTFT:</b> ${ttftSec}s (${ttftPct}%) &nbsp;|&nbsp; <b style="color: #6366f1;">STREAMING:</b> ${streamSec}s (${streamPct}%)</span>
                        <span style="font-weight: 700; color: #cbd5e1;">Total: ${totalSec}s</span>
                    </div>
                    <div class="agyis-timing-bar">
                        <div style="width: ${ttftPct}%; background: #f59e0b;" title="TTFT / Thinking"></div>
                        <div style="width: ${streamPct}%; background: #6366f1;" title="Streaming / Output"></div>
                    </div>
                </div>
            `;

            if (state.activeTab === "step") {
                const text = currentStep.content || currentStep.thinking || JSON.stringify(currentStep, null, 2);
                inspectorContentHtml = `
                    ${timingBarHtml}
                    <h4 style="margin: 0 0 6px 0; font-size: 11px; color: #a1a1aa; text-transform: uppercase;">Step Preview</h4>
                    ${renderMarkdownPreview(text)}
                `;
            } else if (state.activeTab === "invocation") {
                const tools = currentStep.tool_calls || [];
                inspectorContentHtml = `
                    ${timingBarHtml}
                    <h4 style="margin: 0 0 8px 0; font-size: 11px; color: #a1a1aa; text-transform: uppercase;">Tool Invocations (${tools.length})</h4>
                    ${tools.length === 0 ? "<div style='color: #71717a;'>No tool calls executed in this step.</div>" : tools.map((t, tidx) => `
                        <div style="background: #202023; border: 1px solid #3f3f46; border-radius: 6px; padding: 10px; margin-bottom: 8px;">
                            <div style="display: flex; justify-content: space-between; margin-bottom: 6px;">
                                <span style="font-weight: 700; color: #22d3ee; font-family: monospace;">#${tidx + 1} ${t.name}</span>
                                <span class="agyis-hud-pill agyis-hud-pill-green">${t.status || "DONE"}</span>
                            </div>
                            <div style="font-size: 10px; color: #a1a1aa; margin-bottom: 4px;">Arguments:</div>
                            <pre class="agyis-codeblock" style="margin-bottom: 8px;"><code>${JSON.stringify(t.args || {}, null, 2).replace(/</g, "&lt;").replace(/>/g, "&gt;")}</code></pre>
                            ${t.output ? `<div style="font-size: 10px; color: #a1a1aa; margin-bottom: 4px;">Output:</div><pre class="agyis-codeblock" style="max-height: 200px;"><code>${String(t.output).replace(/</g, "&lt;").replace(/>/g, "&gt;")}</code></pre>` : ""}
                        </div>
                    `).join("")}
                `;
            } else if (state.activeTab === "execution") {
                inspectorContentHtml = `
                    ${timingBarHtml}
                    <h4 style="margin: 0 0 8px 0; font-size: 11px; color: #a1a1aa; text-transform: uppercase;">Execution Metadata</h4>
                    <table class="agyis-markdown-table">
                        <tr><th>Field</th><th>Value</th></tr>
                        <tr><td>Step Index</td><td>#${currentStep.step_index ?? state.selectedIndex}</td></tr>
                        <tr><td>Type</td><td>${currentStep.type || "N/A"}</td></tr>
                        <tr><td>Status</td><td>${currentStep.status || "DONE"}</td></tr>
                        <tr><td>Input Tokens</td><td>${(currentStep.input_tokens || 0).toLocaleString()}</td></tr>
                        <tr><td>Output Tokens</td><td>${(currentStep.output_tokens || 0).toLocaleString()}</td></tr>
                        <tr><td>Cumulative Context</td><td>${(currentStep.cumulative_tokens || 0).toLocaleString()} tokens</td></tr>
                        <tr><td>Payload Size</td><td>${formatBytes(currentStep.size_bytes)}</td></tr>
                    </table>
                `;
            } else { // trajectory / raw
                const rawJson = JSON.stringify(currentStep, null, 2).replace(/</g, "&lt;").replace(/>/g, "&gt;");
                inspectorContentHtml = `
                    <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 8px;">
                        <h4 style="margin: 0; font-size: 11px; color: #a1a1aa; text-transform: uppercase;">Raw Step JSON</h4>
                        <button id="agyis-copy-btn" class="agyis-hud-btn">📋 Copy</button>
                    </div>
                    <pre class="agyis-codeblock" style="max-height: 450px;"><code>${rawJson}</code></pre>
                `;
            }
        }

        const matchCount = state.searchMatchIndices.length;
        const matchDisplay = q ? `${matchCount > 0 ? (state.currentMatchIdx + 1) : 0}/${matchCount}` : `${steps.length}/${steps.length}`;

        hud.innerHTML = `
            <div class="agyis-hud-box ${state.isMaximized ? 'maximized' : ''}">
                <!-- Header ('Avc' Parity) -->
                <div class="agyis-hud-header">
                    <div class="agyis-hud-header-left">
                        <span class="agyis-hud-pill agyis-hud-pill-amber">⚡ Trajectory Debug View</span>
                        <select id="agyis-convo-select" class="agyis-hud-select" title="Switch Conversation">
                            ${conversationList.map(c => `
                                <option value="${c.id}" ${c.id === cur.conversation_id ? "selected" : ""}>
                                    ${c.summary || c.id.slice(0, 12)} (${new Date(c.mtime * 1000).toLocaleTimeString()})
                                </option>
                            `).join("")}
                        </select>
                        <button id="agyis-refresh-btn" class="agyis-hud-btn" title="Refresh Trajectory from Server">🔄 Refresh</button>
                        ${isChildView ? `
                            <button id="agyis-parent-btn" class="agyis-hud-pill agyis-hud-pill-blue" style="cursor: pointer;" title="Back to parent conversation">
                                ↑ Parent
                            </button>
                        ` : ""}
                        ${subagentsDropdownHtml}
                        <div class="agyis-hud-search-box">
                            <input id="agyis-search-input" class="agyis-hud-search-input" type="text" placeholder="Search steps..." value="${state.filterQuery}">
                            <span class="agyis-hud-search-counter">${matchDisplay}</span>
                            ${q ? `<button id="agyis-search-clear" style="background: none; border: none; color: #a1a1aa; cursor: pointer; padding: 0 2px;">✕</button>` : ""}
                        </div>
                    </div>

                    <div class="agyis-hud-header-right">
                        <!-- Layout Toggle: Side-by-Side vs Stacked -->
                        <div style="display: inline-flex; border: 1px solid #3f3f46; border-radius: 6px; overflow: hidden;">
                            <button id="agyis-layout-side" class="agyis-hud-btn ${state.layoutOrientation === 'horizontal' ? 'active' : ''}" style="border: none; border-radius: 0;" title="Side-by-side layout">◫ Side-by-Side</button>
                            <button id="agyis-layout-stack" class="agyis-hud-btn ${state.layoutOrientation === 'vertical' ? 'active' : ''}" style="border: none; border-radius: 0;" title="Stacked layout">☰ Stacked</button>
                        </div>
                        <button id="agyis-maximize-btn" class="agyis-hud-btn" title="Toggle Maximize">${state.isMaximized ? '❐ Restore' : '⛶ Maximize'}</button>
                        <button id="agyis-close-btn" class="agyis-hud-btn" title="Close (Escape)">✕</button>
                    </div>
                </div>

                <!-- Context Window Bar ('Dlc' Parity) -->
                <div class="agyis-context-bar-wrap">
                    <div class="agyis-context-track">
                        ${barSegmentsHtml}
                    </div>
                    <div id="agyis-hover-tooltip" class="agyis-context-tooltip" style="display: none;"></div>
                    <div class="agyis-context-legend">
                        <div style="display: flex; gap: 10px; flex-wrap: wrap;">
                            <span class="agyis-legend-item"><span class="agyis-legend-dot" style="background: #6366f1;"></span> System Prompt</span>
                            <span class="agyis-legend-item"><span class="agyis-legend-dot" style="background: #06b6d4;"></span> Tool Defs</span>
                            <span class="agyis-legend-item"><span class="agyis-legend-dot" style="background: #16a34a;"></span> Checkpoint</span>
                            <span class="agyis-legend-item"><span class="agyis-legend-dot" style="background: #3b82f6;"></span> User</span>
                            <span class="agyis-legend-item"><span class="agyis-legend-dot" style="background: #f59e0b;"></span> Model</span>
                            <span class="agyis-legend-item"><span class="agyis-legend-dot" style="background: #14b8a6;"></span> Tool</span>
                            <span class="agyis-legend-item"><span class="agyis-legend-dot" style="background: #a855f7;"></span> System</span>
                            <span class="agyis-legend-item"><span class="agyis-legend-dot" style="background: #3f3f46;"></span> Unused</span>
                        </div>
                        <div style="font-family: monospace; font-weight: 700; color: #cbd5e1;">
                            ${totalTokens.toLocaleString()} / 200,000 tokens
                        </div>
                    </div>
                </div>

                <!-- Deck Deck Splitter Layout -->
                <div id="agyis-hud-deck" class="agyis-hud-main-deck ${state.layoutOrientation}">
                    <!-- History Table Grid ('rmc' Parity) -->
                    <div class="agyis-grid-pane">
                        <div class="agyis-step-grid-row agyis-step-grid-header">
                            <div>EXEC</div>
                            <div>INV</div>
                            <div>STEP</div>
                            <div>TYPE</div>
                            <div>DETAILS</div>
                            <div>STATUS</div>
                            <div style="text-align: right;">TOKENS</div>
                            <div style="text-align: right;">SIZE</div>
                        </div>
                        <div class="agyis-step-grid-body">
                            ${gridRowsHtml || "<div style='padding: 20px; text-align: center; color: #71717a;'>No steps match current search query</div>"}
                        </div>
                    </div>

                    <div id="agyis-splitter" class="agyis-splitter"></div>

                    <!-- Step Inspector ('jmc' & 'fmc' Parity) -->
                    <div class="agyis-inspector-pane">
                        <div class="agyis-inspector-header">
                            <div style="display: flex; align-items: center; gap: 8px;">
                                <span style="font-weight: 700; font-size: 12px;">Step #${currentStep ? (currentStep.step_index ?? state.selectedIndex) : '-'}</span>
                                ${currentStep ? `<span class="agyis-hud-pill agyis-hud-pill-amber">${currentStep.type || 'STEP'}</span>` : ''}
                            </div>
                            <div style="display: flex; gap: 4px; align-items: center;">
                                <button id="agyis-step-first" class="agyis-hud-btn" ${state.selectedIndex <= 0 ? 'disabled style="opacity:0.4;"' : ''}>«</button>
                                <button id="agyis-step-prev" class="agyis-hud-btn" ${state.selectedIndex <= 0 ? 'disabled style="opacity:0.4;"' : ''}>‹</button>
                                <span style="font-size: 11px; font-family: monospace; padding: 0 4px; color: #a1a1aa;">${steps.length > 0 ? (state.selectedIndex + 1) : 0} / ${steps.length}</span>
                                <button id="agyis-step-next" class="agyis-hud-btn" ${state.selectedIndex >= steps.length - 1 ? 'disabled style="opacity:0.4;"' : ''}>›</button>
                                <button id="agyis-step-last" class="agyis-hud-btn" ${state.selectedIndex >= steps.length - 1 ? 'disabled style="opacity:0.4;"' : ''}>»</button>
                            </div>
                        </div>

                        <div class="agyis-inspector-tabs">
                            <button class="agyis-hud-btn ${state.activeTab === 'step' ? 'active' : ''}" data-tab="step">Step</button>
                            <button class="agyis-hud-btn ${state.activeTab === 'invocation' ? 'active' : ''}" data-tab="invocation">Invocation</button>
                            <button class="agyis-hud-btn ${state.activeTab === 'execution' ? 'active' : ''}" data-tab="execution">Execution</button>
                            <button class="agyis-hud-btn ${state.activeTab === 'trajectory' ? 'active' : ''}" data-tab="trajectory">Trajectory</button>
                        </div>

                        <div class="agyis-inspector-content" id="agyis-inspector-body">
                            ${inspectorContentHtml}
                        </div>
                    </div>
                </div>
            </div>
        `;

        // Event Listeners
        hud.querySelector("#agyis-convo-select")?.addEventListener("change", (e) => {
            const selectedId = e.target.value;
            if (selectedId && typeof window.__agyis_hud_load_convo === "function") {
                window.__agyis_hud_load_convo(selectedId);
            }
        });

        hud.querySelector("#agyis-refresh-btn")?.addEventListener("click", () => {
            const state = window.__agyis_hud_state;
            if (state && state.convoId && typeof window.__agyis_hud_load_convo === "function") {
                const btn = hud.querySelector("#agyis-refresh-btn");
                if (btn) btn.textContent = "⏳...";
                window.__agyis_hud_load_convo(state.convoId).finally(() => {
                    if (btn) btn.textContent = "🔄 Refresh";
                });
            }
        });

        hud.querySelector("#agyis-close-btn")?.addEventListener("click", () => {
            hud.style.display = "none";
        });

        hud.querySelector("#agyis-maximize-btn")?.addEventListener("click", () => {
            state.isMaximized = !state.isMaximized;
            renderHud();
        });

        hud.querySelector("#agyis-layout-side")?.addEventListener("click", () => {
            state.layoutOrientation = "horizontal";
            renderHud();
        });

        hud.querySelector("#agyis-layout-stack")?.addEventListener("click", () => {
            state.layoutOrientation = "vertical";
            renderHud();
        });

        hud.querySelector("#agyis-subagents-dropdown-toggle")?.addEventListener("click", (e) => {
            e.stopPropagation();
            state.subagentsDropdownOpen = !state.subagentsDropdownOpen;
            const menu = hud.querySelector("#agyis-subagents-menu");
            if (menu) menu.style.display = state.subagentsDropdownOpen ? "block" : "none";
        });

        hud.querySelectorAll(".agyis-subagent-item").forEach(el => {
            el.addEventListener("click", (e) => {
                e.stopPropagation();
                const sid = el.getAttribute("data-sub-id");
                const subTraj = cur.subagent_trajectories ? cur.subagent_trajectories[sid] : null;
                if (subTraj) {
                    state.currentData = subTraj;
                    state.selectedIndex = Math.max(0, (subTraj.steps || []).length - 1);
                    state.subagentsDropdownOpen = false;
                    renderHud();
                }
            });
        });

        hud.querySelector("#agyis-parent-btn")?.addEventListener("click", () => {
            state.currentData = state.rootData;
            state.selectedIndex = Math.max(0, (state.rootData.steps || []).length - 1);
            renderHud();
        });

        hud.querySelector("#agyis-search-input")?.addEventListener("input", (e) => {
            state.filterQuery = e.target.value;
            state.currentMatchIdx = 0;
            renderHud();
        });

        hud.querySelector("#agyis-search-input")?.addEventListener("keydown", (e) => {
            if (e.key === "Enter") {
                e.preventDefault();
                if (state.searchMatchIndices.length > 0) {
                    if (e.shiftKey) {
                        state.currentMatchIdx = (state.currentMatchIdx - 1 + state.searchMatchIndices.length) % state.searchMatchIndices.length;
                    } else {
                        state.currentMatchIdx = (state.currentMatchIdx + 1) % state.searchMatchIndices.length;
                    }
                    state.selectedIndex = state.searchMatchIndices[state.currentMatchIdx];
                    renderHud();
                }
            } else if (e.key === "Escape") {
                state.filterQuery = "";
                renderHud();
            }
        });

        hud.querySelector("#agyis-search-clear")?.addEventListener("click", () => {
            state.filterQuery = "";
            renderHud();
        });

        // Context segment tooltips
        const tooltipEl = hud.querySelector("#agyis-hover-tooltip");
        hud.querySelectorAll(".agyis-context-segment").forEach(el => {
            el.addEventListener("mouseenter", () => {
                const sName = el.getAttribute("data-seg-name");
                const sTok = parseInt(el.getAttribute("data-seg-tokens") || "0", 10);
                const sPct = el.getAttribute("data-seg-pct");
                if (tooltipEl) {
                    tooltipEl.style.display = "block";
                    tooltipEl.innerHTML = `<b style="color: #fbbf24;">${sName}</b><br>Tokens: ${sTok.toLocaleString()} (${sPct}%)`;
                }
            });
            el.addEventListener("mouseleave", () => {
                if (tooltipEl) tooltipEl.style.display = "none";
            });
        });

        // Stepper buttons
        hud.querySelector("#agyis-step-first")?.addEventListener("click", () => {
            if (steps.length > 0) { state.selectedIndex = 0; renderHud(); }
        });
        hud.querySelector("#agyis-step-prev")?.addEventListener("click", () => {
            if (state.selectedIndex > 0) { state.selectedIndex -= 1; renderHud(); }
        });
        hud.querySelector("#agyis-step-next")?.addEventListener("click", () => {
            if (state.selectedIndex < steps.length - 1) { state.selectedIndex += 1; renderHud(); }
        });
        hud.querySelector("#agyis-step-last")?.addEventListener("click", () => {
            if (steps.length > 0) { state.selectedIndex = steps.length - 1; renderHud(); }
        });

        // Inspector tabs
        hud.querySelectorAll(".agyis-inspector-tabs .agyis-hud-btn[data-tab]").forEach(el => {
            el.addEventListener("click", () => {
                state.activeTab = el.getAttribute("data-tab");
                renderHud();
            });
        });

        // Step grid selection
        hud.querySelectorAll(".agyis-step-grid-item").forEach(el => {
            el.addEventListener("click", () => {
                const idx = parseInt(el.getAttribute("data-index"), 10);
                state.selectedIndex = idx;
                renderHud();
            });
        });

        // Copy button
        hud.querySelector("#agyis-copy-btn")?.addEventListener("click", () => {
            if (currentStep) {
                navigator.clipboard.writeText(JSON.stringify(currentStep, null, 2)).then(() => {
                    const btn = hud.querySelector("#agyis-copy-btn");
                    if (btn) btn.textContent = "✔ Copied!";
                    setTimeout(() => { if (btn) btn.textContent = "📋 Copy"; }, 1500);
                });
            }
        });

        // Syntax highlighting integration with window.Prism if available
        if (window.Prism && typeof window.Prism.highlightAllUnder === "function") {
            const inspBody = hud.querySelector("#agyis-inspector-body");
            if (inspBody) {
                try { window.Prism.highlightAllUnder(inspBody); } catch (_) {}
            }
        }
    }

    renderHud();
    document.body.appendChild(hud);

    // Initial check for focused conversation route mismatch (PSL-INV-010)
    const initialRouteMatch = window.location.pathname.match(/\/c\/([a-f0-9\-]+)/);
    const initialFocusedConvo = initialRouteMatch ? initialRouteMatch[1] : null;
    if (initialFocusedConvo && initialFocusedConvo !== initialData.conversation_id && typeof window.__agyis_hud_load_convo === "function") {
        window.__agyis_hud_load_convo(initialFocusedConvo);
    }

    // Global click listener to dismiss subagent dropdown
    document.addEventListener("click", () => {
        if (window.__agyis_hud_state && window.__agyis_hud_state.subagentsDropdownOpen) {
            window.__agyis_hud_state.subagentsDropdownOpen = false;
            const menu = hud.querySelector("#agyis-subagents-menu");
            if (menu) menu.style.display = "none";
        }
    });

    if (!window.__agyis_hud_hotkey_registered) {
        window.__agyis_hud_hotkey_registered = true;
        window.addEventListener("keydown", (e) => {
            const isF12 = e.key === "F12";
            const isCtrlShiftT = (e.ctrlKey || e.metaKey) && e.shiftKey && (e.key === "T" || e.key === "t");
            if (isF12 || isCtrlShiftT) {
                e.preventDefault();
                e.stopPropagation();
                const isHidden = hud.style.display === "none";
                if (isHidden) {
                    const match = window.location.pathname.match(/\/c\/([a-f0-9\-]+)/);
                    const focusedConvoId = match ? match[1] : null;
                    const state = window.__agyis_hud_state;
                    if (focusedConvoId && state && focusedConvoId !== state.convoId && typeof window.__agyis_hud_load_convo === "function") {
                        window.__agyis_hud_load_convo(focusedConvoId);
                    }
                }
                hud.style.display = isHidden ? "flex" : "none";
            }
            if (e.key === "Escape" && hud.style.display !== "none") {
                hud.style.display = "none";
            }
            if (hud.style.display !== "none" && (e.target.tagName !== "INPUT" && e.target.tagName !== "TEXTAREA")) {
                const state = window.__agyis_hud_state;
                if (!state) return;
                const steps = (state.currentData && state.currentData.steps) ? state.currentData.steps : [];
                if (e.key === "ArrowLeft" && state.selectedIndex > 0) {
                    state.selectedIndex -= 1;
                    renderHud();
                }
                if (e.key === "ArrowRight" && state.selectedIndex < steps.length - 1) {
                    state.selectedIndex += 1;
                    renderHud();
                }
            }
        }, true);
    }

    return {
        success: true,
        open: shouldOpen,
        steps: initialData.step_count || 0,
        convo_id: initialData.conversation_id,
    };
})();
"""


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
    return _HUD_TEMPLATE.replace(target_token, replacement, 1)
