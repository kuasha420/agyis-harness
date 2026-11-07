# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Arafat Zahan (@kuasha420)
# Corporate Stewardship & Infrastructure: Purrfect Software Limited (PSL)
# Governed by: ICARO-42/b Ordinance (Company-Supported Personal IP Framework)

"""
Cleanroom In-Situ Trajectory Debug View HUD Generator (ADR-014 / PSL-INV-007).
Reimplements the Trajectory Debug View reverse-engineered from Google Antigravity
using in-situ DOM injection over the Chromium DevTools Protocol (CDP).
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Dict, List, Optional


def load_conversation_trajectory(
    conversation_id: str,
    brain_dir: Optional[Path] = None,
) -> Dict[str, Any]:
    """Loads trajectory steps and metadata for a conversation directly from disk."""
    base_brain = brain_dir or (Path.home() / ".gemini" / "antigravity" / "brain")
    convo_dir = base_brain / conversation_id

    transcript_path = convo_dir / ".system_generated" / "logs" / "transcript.jsonl"
    if not transcript_path.is_file():
        transcript_path = convo_dir / "transcript.jsonl"

    steps: List[Dict[str, Any]] = []
    if transcript_path.is_file():
        try:
            with open(transcript_path, "r", encoding="utf-8", errors="replace") as f:
                for line in f:
                    line = line.strip()
                    if line:
                        try:
                            steps.append(json.loads(line))
                        except Exception:
                            continue
        except OSError:
            pass

    parent_id = None
    subagents: List[str] = []

    # Check for parent/child subagent relationships
    for step in steps:
        tool_calls = step.get("tool_calls", [])
        for tc in tool_calls:
            if tc.get("name") == "invoke_subagent":
                output_str = str(tc.get("output", ""))
                import re
                sub_m = re.search(r"conversationId[\"':\s]+([a-f0-9\-]{36})", output_str)
                if sub_m:
                    subagents.append(sub_m.group(1))

    # Check if this conversation itself is a subagent of another conversation
    if base_brain.is_dir():
        for d in base_brain.iterdir():
            if d.is_dir() and d.name != conversation_id and d.name != ".system_generated":
                t_log = d / ".system_generated" / "logs" / "transcript.jsonl"
                if t_log.is_file():
                    try:
                        with open(t_log, "r", encoding="utf-8", errors="replace") as f:
                            content = f.read()
                            if conversation_id in content:
                                parent_id = d.name
                                break
                    except OSError:
                        pass

    total_tokens = 0
    cache_tokens = 0
    for s in reversed(steps):
        if s.get("input_tokens") or s.get("output_tokens") or s.get("cache_read_tokens"):
            total_tokens = (s.get("input_tokens") or 0) + (s.get("output_tokens") or 0)
            cache_tokens = s.get("cache_read_tokens") or 0
            break

    return {
        "conversation_id": conversation_id,
        "transcript_path": str(transcript_path),
        "steps": steps,
        "step_count": len(steps),
        "parent_id": parent_id,
        "subagents": subagents,
        "total_tokens": total_tokens,
        "cache_tokens": cache_tokens,
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
                    conversations.append({
                        "id": d.name,
                        "mtime": mtime,
                    })
                except OSError:
                    continue

    conversations.sort(key=lambda c: c["mtime"], reverse=True)
    return conversations[:limit]


_HUD_TEMPLATE = """
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
                background: rgba(0, 0, 0, 0.7);
                backdrop-filter: blur(8px);
                font-family: ui-sans-serif, system-ui, -apple-system, sans-serif;
                color: #f4f4f5;
                box-sizing: border-box;
            }
            #agyis-trajectory-hud * { box-sizing: border-box; }
            .agyis-hud-box {
                width: 95vw;
                max-width: 1400px;
                height: 90vh;
                background: #18181b;
                border: 1px solid #27272a;
                border-radius: 12px;
                box-shadow: 0 25px 50px -12px rgba(0, 0, 0, 0.85);
                display: flex;
                flex-direction: column;
                overflow: hidden;
            }
            .agyis-hud-header {
                display: flex;
                align-items: center;
                justify-content: space-between;
                padding: 8px 16px;
                background: #121214;
                border-bottom: 1px solid #27272a;
                gap: 12px;
            }
            .agyis-hud-header-left { display: flex; align-items: center; gap: 10px; min-width: 0; }
            .agyis-hud-header-right { display: flex; align-items: center; gap: 10px; }
            .agyis-hud-pill {
                display: inline-flex;
                align-items: center;
                gap: 6px;
                padding: 4px 10px;
                border-radius: 9999px;
                font-size: 11px;
                font-weight: 600;
                text-transform: uppercase;
                letter-spacing: 0.05em;
            }
            .agyis-hud-pill-amber { background: rgba(245, 158, 11, 0.15); color: #f59e0b; border: 1px solid rgba(245, 158, 11, 0.3); }
            .agyis-hud-pill-blue { background: rgba(59, 130, 246, 0.15); color: #60a5fa; border: 1px solid rgba(59, 130, 246, 0.3); }
            .agyis-hud-pill-green { background: rgba(16, 185, 129, 0.15); color: #34d399; border: 1px solid rgba(16, 185, 129, 0.3); }
            .agyis-hud-pill-purple { background: rgba(139, 92, 246, 0.15); color: #a78bfa; border: 1px solid rgba(139, 92, 246, 0.3); }
            .agyis-hud-btn {
                background: #27272a;
                border: 1px solid #3f3f46;
                color: #f4f4f5;
                border-radius: 6px;
                padding: 5px 10px;
                font-size: 12px;
                cursor: pointer;
                display: inline-flex;
                align-items: center;
                gap: 6px;
                transition: background 0.15s, border-color 0.15s;
            }
            .agyis-hud-btn:hover { background: #3f3f46; border-color: #52525b; }
            .agyis-hud-btn.active { background: #d97706; border-color: #f59e0b; color: #fff; }
            .agyis-hud-select {
                background: #27272a;
                border: 1px solid #3f3f46;
                color: #f4f4f5;
                border-radius: 6px;
                padding: 5px 8px;
                font-size: 12px;
                outline: none;
                max-width: 280px;
                cursor: pointer;
            }
            .agyis-hud-search {
                background: #202023;
                border: 1px solid #3f3f46;
                color: #f4f4f5;
                border-radius: 6px;
                padding: 5px 10px;
                font-size: 12px;
                outline: none;
                width: 180px;
                transition: width 0.2s, border-color 0.2s;
            }
            .agyis-hud-search:focus { width: 260px; border-color: #f59e0b; }
            .agyis-hud-body { flex: 1; display: flex; overflow: hidden; background: #18181b; }
            .agyis-hud-list-pane {
                flex: 1;
                display: flex;
                flex-direction: column;
                border-right: 1px solid #27272a;
                min-width: 320px;
                overflow: hidden;
            }
            .agyis-hud-horizon-bar {
                padding: 10px 16px;
                background: #121214;
                border-bottom: 1px solid #27272a;
                display: flex;
                flex-direction: column;
                gap: 6px;
            }
            .agyis-hud-bar-track { height: 8px; background: #27272a; border-radius: 4px; overflow: hidden; display: flex; }
            .agyis-hud-cards {
                flex: 1;
                overflow-y: auto;
                padding: 8px;
                display: flex;
                flex-direction: column;
                gap: 6px;
            }
            .agyis-hud-step-card {
                background: #202023;
                border: 1px solid #2e2e33;
                border-radius: 8px;
                padding: 8px 12px;
                cursor: pointer;
                transition: border-color 0.15s, background 0.15s;
                display: flex;
                flex-direction: column;
                gap: 4px;
            }
            .agyis-hud-step-card:hover { background: #27272a; border-color: #52525b; }
            .agyis-hud-step-card.selected { background: #26231c; border-color: #f59e0b; box-shadow: 0 0 0 1px #f59e0b; }
            .agyis-hud-card-top { display: flex; align-items: center; justify-content: space-between; }
            .agyis-hud-card-snippet {
                font-size: 11px;
                color: #a1a1aa;
                overflow: hidden;
                text-overflow: ellipsis;
                white-space: nowrap;
                font-family: ui-monospace, monospace;
            }
            .agyis-hud-tools { display: flex; flex-wrap: wrap; gap: 4px; margin-top: 2px; }
            .agyis-hud-tool-chip {
                background: rgba(6, 182, 212, 0.12);
                color: #22d3ee;
                border: 1px solid rgba(6, 182, 212, 0.25);
                padding: 1px 6px;
                border-radius: 4px;
                font-size: 10px;
                font-family: ui-monospace, monospace;
            }
            .agyis-hud-splitter { width: 6px; background: #27272a; cursor: col-resize; transition: background 0.15s; }
            .agyis-hud-splitter:hover { background: #f59e0b; }
            .agyis-hud-inspector {
                flex: 1.2;
                display: flex;
                flex-direction: column;
                min-width: 400px;
                background: #18181b;
                overflow: hidden;
            }
            .agyis-hud-inspector-header {
                display: flex;
                align-items: center;
                justify-content: space-between;
                padding: 8px 14px;
                background: #121214;
                border-bottom: 1px solid #27272a;
            }
            .agyis-hud-inspector-tabs { display: flex; gap: 4px; padding: 6px 14px; background: #151518; border-bottom: 1px solid #27272a; }
            .agyis-hud-inspector-content { flex: 1; overflow-y: auto; padding: 14px; font-size: 13px; line-height: 1.6; }
            .agyis-hud-codeblock {
                background: #09090b;
                border: 1px solid #27272a;
                border-radius: 8px;
                padding: 12px;
                font-family: ui-monospace, monospace;
                font-size: 12px;
                white-space: pre-wrap;
                word-break: break-all;
                overflow-x: auto;
                color: #e4e4e7;
            }
            .agyis-hud-timeline-pane { flex: 1; display: flex; flex-direction: column; padding: 16px; overflow-y: auto; gap: 8px; }
            .agyis-hud-timeline-row { display: flex; align-items: center; gap: 12px; padding: 6px 0; border-bottom: 1px solid #27272a; }
            .agyis-hud-timeline-label { width: 100px; font-size: 11px; color: #a1a1aa; font-family: ui-monospace, monospace; flex-shrink: 0; }
            .agyis-hud-timeline-bar-wrap { flex: 1; background: #27272a; height: 14px; border-radius: 4px; overflow: hidden; position: relative; }
        `;
        document.head.appendChild(styleEl);
    }

    let existingHud = document.getElementById(HUD_ID);
    if (existingHud) {
        if (isToggle) {
            const isHidden = existingHud.style.display === "none";
            existingHud.style.display = isHidden ? "flex" : "none";
            return { success: true, open: isHidden, toggled: true };
        } else if (shouldOpen) {
            existingHud.style.display = "flex";
            return { success: true, open: true, toggled: false };
        } else {
            existingHud.style.display = "none";
            return { success: true, open: false, toggled: false };
        }
    }

    const hud = document.createElement("div");
    hud.id = HUD_ID;
    hud.style.display = shouldOpen ? "flex" : "none";

    window.__agyis_hud_state = {
        convoId: initialData.conversation_id,
        steps: initialData.steps || [],
        selectedIndex: Math.max(0, (initialData.steps || []).length - 1),
        filterQuery: "",
        activeTab: "context",
        inspectorTab: "thinking",
        layoutOrientation: "horizontal",
    };

    function renderHud() {
        const state = window.__agyis_hud_state;
        const steps = state.steps;
        const currentStep = steps[state.selectedIndex] || null;

        const filteredIndices = [];
        for (let i = 0; i < steps.length; i++) {
            const s = steps[i];
            if (!state.filterQuery) {
                filteredIndices.push(i);
                continue;
            }
            const q = state.filterQuery.toLowerCase();
            const matchesType = (s.type || "").toLowerCase().includes(q);
            const matchesSource = (s.source || "").toLowerCase().includes(q);
            const matchesContent = (s.content || "").toLowerCase().includes(q);
            const matchesThinking = (s.thinking || "").toLowerCase().includes(q);
            const matchesTool = (s.tool_calls || []).some(tc => (tc.name || "").toLowerCase().includes(q));
            if (matchesType || matchesSource || matchesContent || matchesThinking || matchesTool) {
                filteredIndices.push(i);
            }
        }

        const totalTokens = initialData.total_tokens || 0;
        const cacheTokens = initialData.cache_tokens || 0;
        const horizonPercent = Math.min(100, Math.round((totalTokens / 200000) * 100));
        let horizonColor = "#10b981";
        let horizonStatus = "Healthy (<50k)";
        if (totalTokens >= 200000) {
            horizonColor = "#ef4444";
            horizonStatus = "CRITICAL CLIFF (>200k)";
        } else if (totalTokens >= 100000) {
            horizonColor = "#f59e0b";
            horizonStatus = "Compaction Imminent (>100k)";
        } else if (totalTokens >= 50000) {
            horizonColor = "#eab308";
            horizonStatus = "Elevated (>50k)";
        }

        const convoOptions = conversationList.map(c => `
            <option value="${c.id}" ${c.id === state.convoId ? "selected" : ""}>
                ${c.id.slice(0, 12)}... (${new Date(c.mtime * 1000).toLocaleTimeString()})
            </option>
        `).join("");

        const cardsHtml = filteredIndices.map(idx => {
            const s = steps[idx];
            const isSel = idx === state.selectedIndex;
            const type = s.type || "STEP";
            const tools = s.tool_calls || [];
            const timeStr = s.created_at ? new Date(s.created_at).toLocaleTimeString() : "";
            let pillClass = "agyis-hud-pill-blue";
            if (type === "PLANNER_RESPONSE") pillClass = "agyis-hud-pill-purple";
            if (type === "TOOL_CALL" || tools.length > 0) pillClass = "agyis-hud-pill-amber";
            if (s.status === "ERROR") pillClass = "agyis-hud-pill-amber";

            let snippet = s.thinking ? s.thinking.slice(0, 120) : (s.content ? s.content.slice(0, 120) : (tools.length > 0 ? tools[0].name : ""));
            snippet = snippet.replace(/</g, "&lt;").replace(/>/g, "&gt;");

            const toolChips = tools.map(t => `<span class="agyis-hud-tool-chip">${t.name}</span>`).join("");

            return `
                <div class="agyis-hud-step-card ${isSel ? "selected" : ""}" data-index="${idx}">
                    <div class="agyis-hud-card-top">
                        <div style="display: flex; align-items: center; gap: 6px;">
                            <span style="font-weight: 700; font-size: 11px;">#${s.step_index ?? idx}</span>
                            <span class="agyis-hud-pill ${pillClass}">${type}</span>
                        </div>
                        <span style="font-size: 10px; color: #71717a;">${timeStr}</span>
                    </div>
                    <div class="agyis-hud-card-snippet">${snippet || "No textual payload"}</div>
                    ${tools.length > 0 ? `<div class="agyis-hud-tools">${toolChips}</div>` : ""}
                </div>
            `;
        }).join("");

        let inspectorBody = "";
        if (currentStep) {
            if (state.inspectorTab === "thinking") {
                const text = (currentStep.thinking || "No internal thinking recorded for this step.").replace(/</g, "&lt;").replace(/>/g, "&gt;");
                inspectorBody = `
                    <h4 style="margin: 0 0 8px 0; font-size: 12px; color: #a1a1aa; text-transform: uppercase;">Model Chain of Thought</h4>
                    <div class="agyis-hud-codeblock" style="color: #cbd5e1;">${text}</div>
                `;
            } else if (state.inspectorTab === "content") {
                const text = (currentStep.content || "No textual content.").replace(/</g, "&lt;").replace(/>/g, "&gt;");
                inspectorBody = `
                    <h4 style="margin: 0 0 8px 0; font-size: 12px; color: #a1a1aa; text-transform: uppercase;">Step Content</h4>
                    <div class="agyis-hud-codeblock">${text}</div>
                `;
            } else if (state.inspectorTab === "tools") {
                const tools = currentStep.tool_calls || [];
                if (tools.length > 0) {
                    inspectorBody = `
                        <h4 style="margin: 0 0 8px 0; font-size: 12px; color: #a1a1aa; text-transform: uppercase;">Tool Invocations (${tools.length})</h4>
                    ` + tools.map((t, tidx) => {
                        const argsStr = JSON.stringify(t.args || {}, null, 2).replace(/</g, "&lt;").replace(/>/g, "&gt;");
                        const outStr = (t.output || "").replace(/</g, "&lt;").replace(/>/g, "&gt;");
                        return `
                            <div style="background: #202023; border: 1px solid #3f3f46; border-radius: 8px; padding: 10px; margin-bottom: 10px;">
                                <div style="display: flex; justify-content: space-between; margin-bottom: 6px;">
                                    <span style="font-weight: 700; color: #22d3ee; font-family: monospace;">#${tidx + 1} ${t.name}</span>
                                    <span class="agyis-hud-pill agyis-hud-pill-green">${t.status || "DONE"}</span>
                                </div>
                                <div style="font-size: 11px; color: #a1a1aa; margin-bottom: 4px;">Arguments:</div>
                                <div class="agyis-hud-codeblock" style="margin-bottom: 8px;">${argsStr}</div>
                                ${outStr ? `<div style="font-size: 11px; color: #a1a1aa; margin-bottom: 4px;">Output:</div><div class="agyis-hud-codeblock" style="max-height: 250px;">${outStr}</div>` : ""}
                            </div>
                        `;
                    }).join("");
                } else {
                    inspectorBody = "<div style='color: #71717a;'>No tool calls executed in this step.</div>";
                }
            } else if (state.inspectorTab === "overview") {
                inspectorBody = `
                    <h4 style="margin: 0 0 8px 0; font-size: 12px; color: #a1a1aa; text-transform: uppercase;">Metadata & Metrics</h4>
                    <table style="width: 100%; border-collapse: collapse; font-size: 12px;">
                        <tr style="border-bottom: 1px solid #27272a;"><td style="padding: 6px; color: #a1a1aa;">Step Index</td><td style="padding: 6px; font-weight: 600;">${currentStep.step_index ?? state.selectedIndex}</td></tr>
                        <tr style="border-bottom: 1px solid #27272a;"><td style="padding: 6px; color: #a1a1aa;">Source</td><td style="padding: 6px;">${currentStep.source || "N/A"}</td></tr>
                        <tr style="border-bottom: 1px solid #27272a;"><td style="padding: 6px; color: #a1a1aa;">Type</td><td style="padding: 6px;">${currentStep.type || "N/A"}</td></tr>
                        <tr style="border-bottom: 1px solid #27272a;"><td style="padding: 6px; color: #a1a1aa;">Status</td><td style="padding: 6px;">${currentStep.status || "DONE"}</td></tr>
                        <tr style="border-bottom: 1px solid #27272a;"><td style="padding: 6px; color: #a1a1aa;">Timestamp</td><td style="padding: 6px;">${currentStep.created_at || "N/A"}</td></tr>
                        <tr style="border-bottom: 1px solid #27272a;"><td style="padding: 6px; color: #a1a1aa;">Input Tokens</td><td style="padding: 6px;">${currentStep.input_tokens ? currentStep.input_tokens.toLocaleString() : "N/A"}</td></tr>
                        <tr style="border-bottom: 1px solid #27272a;"><td style="padding: 6px; color: #a1a1aa;">Output Tokens</td><td style="padding: 6px;">${currentStep.output_tokens ? currentStep.output_tokens.toLocaleString() : "N/A"}</td></tr>
                        <tr style="border-bottom: 1px solid #27272a;"><td style="padding: 6px; color: #a1a1aa;">Cache Read Tokens</td><td style="padding: 6px;">${currentStep.cache_read_tokens ? currentStep.cache_read_tokens.toLocaleString() : "N/A"}</td></tr>
                        <tr><td style="padding: 6px; color: #a1a1aa;">Tool Calls</td><td style="padding: 6px;">${(currentStep.tool_calls || []).length}</td></tr>
                    </table>
                `;
            } else {
                const rawJson = JSON.stringify(currentStep, null, 2).replace(/</g, "&lt;").replace(/>/g, "&gt;");
                inspectorBody = `
                    <h4 style="margin: 0 0 8px 0; font-size: 12px; color: #a1a1aa; text-transform: uppercase;">Raw Step JSON</h4>
                    <div class="agyis-hud-codeblock">${rawJson}</div>
                `;
            }
        }

        const timelineRows = steps.slice(-50).map((s, idx) => {
            const stepNum = s.step_index ?? idx;
            const hasThinking = Boolean(s.thinking);
            const tools = s.tool_calls || [];
            const type = s.type || "";
            return `
                <div class="agyis-hud-timeline-row">
                    <div class="agyis-hud-timeline-label">#${stepNum} (${type.slice(0, 8)})</div>
                    <div class="agyis-hud-timeline-bar-wrap" title="Step #${stepNum}">
                        <div style="position: absolute; left: 0; width: ${hasThinking ? "60%" : "20%"}; height: 100%; background: ${hasThinking ? "#8b5cf6" : "#3b82f6"};" title="Generation"></div>
                        ${tools.length > 0 ? `<div style="position: absolute; left: 60%; width: 35%; height: 100%; background: #06b6d4;" title="Tool Execution"></div>` : ""}
                    </div>
                </div>
            `;
        }).join("");

        hud.innerHTML = `
            <div class="agyis-hud-box">
                <div class="agyis-hud-header">
                    <div class="agyis-hud-header-left">
                        <span class="agyis-hud-pill agyis-hud-pill-amber">⚡ Trajectory Debug HUD</span>
                        <select id="agyis-convo-select" class="agyis-hud-select" title="Switch Conversation">
                            ${convoOptions}
                        </select>
                        ${initialData.parent_id ? `
                            <button id="agyis-parent-jump" class="agyis-hud-pill agyis-hud-pill-blue" style="cursor: pointer;" title="Parent: ${initialData.parent_id}">
                                ↑ Parent (${initialData.parent_id.slice(0, 8)}...)
                            </button>
                        ` : ""}
                        <input id="agyis-search-input" class="agyis-hud-search" type="text" placeholder="Filter steps (tool, text)..." value="${state.filterQuery}">
                    </div>

                    <div class="agyis-hud-header-right">
                        <button id="agyis-tab-context" class="agyis-hud-btn ${state.activeTab === "context" ? "active" : ""}">Context Window</button>
                        <button id="agyis-tab-timeline" class="agyis-hud-btn ${state.activeTab === "timeline" ? "active" : ""}">Timeline</button>
                        <span class="agyis-hud-pill agyis-hud-pill-purple">${steps.length} Steps</span>
                        <button id="agyis-close-btn" class="agyis-hud-btn" title="Close (Escape)">✕</button>
                    </div>
                </div>

                <div class="agyis-hud-horizon-bar">
                    <div style="display: flex; justify-content: space-between; font-size: 11px;">
                        <span>Attention Horizon: <b style="color: ${horizonColor};">${totalTokens.toLocaleString()} tokens</b> (${horizonStatus})</span>
                        <span>Cache Read: <b>${cacheTokens.toLocaleString()} tokens</b></span>
                    </div>
                    <div class="agyis-hud-bar-track">
                        <div style="width: ${Math.max(2, horizonPercent)}%; background: ${horizonColor}; transition: width 0.3s;"></div>
                    </div>
                </div>

                <div class="agyis-hud-body">
                    ${state.activeTab === "context" ? `
                        <div class="agyis-hud-list-pane">
                            <div class="agyis-hud-cards">
                                ${cardsHtml}
                            </div>
                        </div>

                        <div class="agyis-hud-splitter"></div>

                        <div class="agyis-hud-inspector">
                            ${currentStep ? `
                                <div class="agyis-hud-inspector-header">
                                    <div style="display: flex; align-items: center; gap: 8px;">
                                        <span style="font-weight: 700; font-size: 13px;">Step #${currentStep.step_index ?? state.selectedIndex}</span>
                                        <span class="agyis-hud-pill agyis-hud-pill-purple">${currentStep.type || "STEP"}</span>
                                        <span class="agyis-hud-pill agyis-hud-pill-green">${currentStep.status || "DONE"}</span>
                                    </div>
                                    <div style="display: flex; gap: 6px;">
                                        <button id="agyis-step-prev" class="agyis-hud-btn" ${state.selectedIndex <= 0 ? "disabled style='opacity:0.4;'" : ""}>◀ Prev</button>
                                        <span style="font-size: 11px; align-self: center; color: #a1a1aa;">${state.selectedIndex + 1} / ${steps.length}</span>
                                        <button id="agyis-step-next" class="agyis-hud-btn" ${state.selectedIndex >= steps.length - 1 ? "disabled style='opacity:0.4;'" : ""}>Next ▶</button>
                                    </div>
                                </div>

                                <div class="agyis-hud-inspector-tabs">
                                    <button class="agyis-hud-btn ${state.inspectorTab === "thinking" ? "active" : ""}" data-tab="thinking">Thinking</button>
                                    <button class="agyis-hud-btn ${state.inspectorTab === "content" ? "active" : ""}" data-tab="content">Content</button>
                                    <button class="agyis-hud-btn ${state.inspectorTab === "tools" ? "active" : ""}" data-tab="tools">Tool Calls (${(currentStep.tool_calls || []).length})</button>
                                    <button class="agyis-hud-btn ${state.inspectorTab === "overview" ? "active" : ""}" data-tab="overview">Overview</button>
                                    <button class="agyis-hud-btn ${state.inspectorTab === "raw" ? "active" : ""}" data-tab="raw">Raw JSON</button>
                                    <button id="agyis-copy-step" class="agyis-hud-btn" style="margin-left: auto;">📋 Copy</button>
                                </div>

                                <div class="agyis-hud-inspector-content">
                                    ${inspectorBody}
                                </div>
                            ` : `
                                <div style="flex:1; display:flex; align-items:center; justify-content:center; color:#71717a;">
                                    Select a step to inspect
                                </div>
                            `}
                        </div>
                    ` : `
                        <div class="agyis-hud-timeline-pane">
                            <h3 style="margin: 0; font-size: 14px;">Activity Timeline Gantt</h3>
                            <div style="display: flex; flex-direction: column; gap: 4px;">
                                ${timelineRows}
                            </div>
                        </div>
                    `}
                </div>
            </div>
        `;

        hud.querySelector("#agyis-close-btn")?.addEventListener("click", () => {
            hud.style.display = "none";
        });

        hud.querySelector("#agyis-search-input")?.addEventListener("input", (e) => {
            state.filterQuery = e.target.value;
            renderHud();
        });

        hud.querySelector("#agyis-tab-context")?.addEventListener("click", () => {
            state.activeTab = "context";
            renderHud();
        });

        hud.querySelector("#agyis-tab-timeline")?.addEventListener("click", () => {
            state.activeTab = "timeline";
            renderHud();
        });

        hud.querySelectorAll(".agyis-hud-step-card").forEach(el => {
            el.addEventListener("click", () => {
                const idx = parseInt(el.getAttribute("data-index"), 10);
                state.selectedIndex = idx;
                renderHud();
            });
        });

        hud.querySelector("#agyis-step-prev")?.addEventListener("click", () => {
            if (state.selectedIndex > 0) {
                state.selectedIndex -= 1;
                renderHud();
            }
        });

        hud.querySelector("#agyis-step-next")?.addEventListener("click", () => {
            if (state.selectedIndex < steps.length - 1) {
                state.selectedIndex += 1;
                renderHud();
            }
        });

        hud.querySelectorAll(".agyis-hud-inspector-tabs .agyis-hud-btn[data-tab]").forEach(el => {
            el.addEventListener("click", () => {
                state.inspectorTab = el.getAttribute("data-tab");
                renderHud();
            });
        });

        hud.querySelector("#agyis-copy-step")?.addEventListener("click", () => {
            if (currentStep) {
                navigator.clipboard.writeText(JSON.stringify(currentStep, null, 2)).then(() => {
                    const btn = hud.querySelector("#agyis-copy-step");
                    if (btn) btn.textContent = "✔ Copied!";
                    setTimeout(() => { if (btn) btn.textContent = "📋 Copy"; }, 1500);
                });
            }
        });

        const splitter = hud.querySelector(".agyis-hud-splitter");
        const listPane = hud.querySelector(".agyis-hud-list-pane");
        if (splitter && listPane) {
            let isDragging = false;
            splitter.addEventListener("mousedown", (e) => {
                isDragging = true;
                e.preventDefault();
            });
            window.addEventListener("mousemove", (e) => {
                if (!isDragging) return;
                const rect = hud.querySelector(".agyis-hud-box").getBoundingClientRect();
                const newW = e.clientX - rect.left;
                if (newW >= 250 && newW <= rect.width - 350) {
                    listPane.style.flex = "none";
                    listPane.style.width = newW + "px";
                }
            });
            window.addEventListener("mouseup", () => { isDragging = false; });
        }
    }

    renderHud();
    document.body.appendChild(hud);

    if (!window.__agyis_hud_hotkey_registered) {
        window.__agyis_hud_hotkey_registered = true;
        window.addEventListener("keydown", (e) => {
            const isF12 = e.key === "F12";
            const isCtrlShiftT = (e.ctrlKey || e.metaKey) && e.shiftKey && (e.key === "T" || e.key === "t");
            if (isF12 || isCtrlShiftT) {
                e.preventDefault();
                e.stopPropagation();
                const isHidden = hud.style.display === "none";
                hud.style.display = isHidden ? "flex" : "none";
            }
            if (e.key === "Escape" && hud.style.display !== "none") {
                hud.style.display = "none";
            }
            if (hud.style.display !== "none" && (e.target.tagName !== "INPUT" && e.target.tagName !== "TEXTAREA")) {
                if (e.key === "ArrowLeft") {
                    const state = window.__agyis_hud_state;
                    if (state && state.selectedIndex > 0) {
                        state.selectedIndex -= 1;
                        renderHud();
                    }
                }
                if (e.key === "ArrowRight") {
                    const state = window.__agyis_hud_state;
                    if (state && state.selectedIndex < state.steps.length - 1) {
                        state.selectedIndex += 1;
                        renderHud();
                    }
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
