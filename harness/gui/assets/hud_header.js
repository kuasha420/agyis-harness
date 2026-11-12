// SPDX-License-Identifier: Apache-2.0
// Copyright (c) 2026 Arafat Zahan (@kuasha420)
// Corporate Stewardship & Infrastructure: Purrfect Software Limited (PSL)
// Governed by: ICARO-42/b Ordinance (Company-Supported Personal IP Framework)

/**
 * hud_header.js — In-situ HUD Header Component (Avc / snc Parity).
 * 
 * Provides:
 * 1. Top navigation bar with verbatim stock Antigravity copy.
 * 2. Dynamic subagent indicator badge "(subagent)" next to title.
 * 3. 1-click "← Parent" jump pill with stock styling.
 * 4. Child subagents dropdown pill "${count} Child Subagent(s)" and menu.
 * 5. Conversation history dropdown with "• subagent of '...'" annotations.
 * 6. Search steps input with match counter and keyboard navigation (Enter/Shift+Enter/Esc).
 * 7. Layout orientation toggles ("Side-by-Side" vs "Stacked").
 */

(function(global) {
    "use strict";

    function escapeHeaderHtml(val) {
        return String(val ?? "")
            .replace(/&/g, "&amp;")
            .replace(/</g, "&lt;")
            .replace(/>/g, "&gt;")
            .replace(/"/g, "&quot;")
            .replace(/'/g, "&#39;");
    }

    /**
     * Renders the top HUD navigation header HTML.
     * @param {Object} state - Active HUD state
     * @param {Object} cur - Current trajectory data
     * @param {Array} conversationList - Recent conversation summaries
     * @returns {string} HTML string for the header
     */
    function renderHudHeader(state, cur, conversationList) {
        const isChildView = Boolean(cur && cur.parent_id);
        const subagents = (cur && cur.subagents) || [];
        const subagentInfos = (cur && cur.subagent_infos) || [];
        const parentId = cur && cur.parent_id ? String(cur.parent_id) : "";

        // Build effective conversation list including active if missing
        const effectiveConvoList = (conversationList || []).slice();
        if (cur && cur.conversation_id && !effectiveConvoList.some(c => c.id === cur.conversation_id)) {
            effectiveConvoList.unshift({
                id: cur.conversation_id,
                summary: cur.summary || `Conversation ${cur.conversation_id.slice(0, 12)}`,
                mtime: Math.floor(Date.now() / 1000),
                parentConversationId: cur.parent_id || null,
            });
        }

        // Child subagents dropdown (snc parity)
        const subagentsDropdownHtml = subagents.length > 0 ? `
            <div style="position: relative;">
                <button id="agyis-subagents-dropdown-toggle"
                        class="agyis-hud-pill agyis-hud-pill-purple"
                        style="cursor: pointer; background: rgba(168, 85, 247, 0.1); color: rgb(192, 132, 252); border: 1px solid rgba(168, 85, 247, 0.2); border-radius: 9999px; padding: 2px 10px; font-size: 11px; display: inline-flex; align-items: center; gap: 4px;"
                        title="View child subagents">
                    <span>${subagents.length} Child Subagent${subagents.length === 1 ? "" : "s"}</span>
                    <span style="font-size: 9px; transform: ${state.subagentsDropdownOpen ? "rotate(180deg)" : "rotate(0deg)"}; transition: transform 0.15s;">▼</span>
                </button>
                <div id="agyis-subagents-menu"
                     style="display: ${state.subagentsDropdownOpen ? "block" : "none"}; position: absolute; top: 100%; left: 0; margin-top: 4px; background: #18181b; border: 1px solid #3f3f46; border-radius: 6px; box-shadow: 0 10px 25px rgba(0,0,0,0.8); z-index: 200; min-width: 260px; max-height: 240px; overflow-y: auto;">
                    <div style="font-size: 10px; font-weight: 600; text-transform: uppercase; letter-spacing: 0.05em; color: #a1a1aa; padding: 6px 10px; border-bottom: 1px solid #27272a;">
                        Child Subagents (${subagents.length})
                    </div>
                    ${subagents.map((sid, idx) => {
                        const info = subagentInfos.find(si => si.id === sid) || { name: `Subagent #${idx + 1}`, summary: sid };
                        return `
                            <div class="agyis-subagent-item"
                                 data-sub-id="${escapeHeaderHtml(sid)}"
                                 style="padding: 6px 10px; cursor: pointer; border-bottom: 1px solid #27272a; transition: background 0.15s;"
                                 onmouseover="this.style.background='#27272a'"
                                 onmouseout="this.style.background='transparent'">
                                <div style="font-weight: 600; color: #c084fc; font-size: 11px;">${escapeHeaderHtml(info.name)}</div>
                                <div style="font-size: 10px; color: #a1a1aa; font-family: monospace;">${escapeHeaderHtml(sid.slice(0, 16))}...</div>
                            </div>
                        `;
                    }).join("")}
                </div>
            </div>
        ` : "";

        // 1-Click Jump to Parent Pill (snc / Avc parity)
        const parentPillHtml = isChildView ? `
            <button id="agyis-parent-btn"
                    class="agyis-hud-pill agyis-hud-pill-blue"
                    style="cursor: pointer; background: rgba(59, 130, 246, 0.1); color: rgb(96, 165, 250); border: 1px solid rgba(59, 130, 246, 0.2); border-radius: 9999px; padding: 2px 10px; font-size: 11px;"
                    title="Navigate up to parent: ${escapeHeaderHtml(parentId)}">
                ← Parent
            </button>
        ` : "";

        // Search counter display
        const q = (state.filterQuery || "").trim().toLowerCase();
        const steps = (cur && cur.steps) || [];
        const matchCount = state.searchMatchIndices ? state.searchMatchIndices.length : 0;
        const matchDisplay = q ? `${matchCount > 0 ? (state.currentMatchIdx || 0) + 1 : 0}/${matchCount}` : `${steps.length}/${steps.length}`;

        return `
            <div class="agyis-hud-header">
                <div class="agyis-hud-header-left">
                    <div style="display: inline-flex; align-items: center; gap: 4px;">
                        <span class="agyis-hud-pill agyis-hud-pill-amber" style="font-weight: 700;">Trajectory Debug View</span>
                        ${isChildView ? '<span class="text-muted-foreground shrink-0" style="color: #a1a1aa; font-size: 11px; margin-left: 2px;">(subagent)</span>' : ""}
                    </div>
                    <select id="agyis-convo-select" class="agyis-hud-select" title="Search conversations (by name or Cascade ID)">
                        ${effectiveConvoList.map(c => {
                            const isSelected = cur && c.id === cur.conversation_id;
                            const pId = c.parentConversationId || c.parent_id;
                            const subNote = pId ? ` • subagent of "${escapeHeaderHtml(String(pId).slice(0, 12))}..."` : "";
                            const titleText = `${c.summary || `Conversation ${c.id.slice(0, 8)}`}${subNote}`;
                            return `<option value="${escapeHeaderHtml(c.id)}" ${isSelected ? "selected" : ""}>${escapeHeaderHtml(titleText)}</option>`;
                        }).join("")}
                    </select>
                    <button id="agyis-refresh-btn" class="agyis-hud-btn" title="Refresh Trajectory from Server">🔄 Refresh</button>
                    ${parentPillHtml}
                    ${subagentsDropdownHtml}
                    <div class="agyis-hud-search-box">
                        <input id="agyis-search-input"
                               class="agyis-hud-search-input"
                               type="text"
                               placeholder="Search steps..."
                               value="${escapeHeaderHtml(state.filterQuery || "")}">
                        <span class="agyis-hud-search-counter" title="Search match counter">${matchDisplay}</span>
                        ${q ? '<button id="agyis-search-clear" title="Clear search (Esc)" style="background: none; border: none; color: #a1a1aa; cursor: pointer; padding: 0 2px;">✕</button>' : ""}
                    </div>
                </div>
                <div class="agyis-hud-header-right">
                    <div role="group" aria-label="Debug view layout" style="display: inline-flex; border: 1px solid #3f3f46; border-radius: 6px; overflow: hidden;">
                        <button id="agyis-layout-side"
                                class="agyis-hud-btn ${state.layoutOrientation === "horizontal" ? "active" : ""}"
                                style="border: none; border-radius: 0;"
                                title="Side-by-side layout">◫ Side-by-Side</button>
                        <button id="agyis-layout-stack"
                                class="agyis-hud-btn ${state.layoutOrientation === "vertical" ? "active" : ""}"
                                style="border: none; border-radius: 0;"
                                title="Stacked layout">☰ Stacked</button>
                    </div>
                    <button id="agyis-maximize-btn" class="agyis-hud-btn" title="Toggle Maximize">${state.isMaximized ? "❐ Restore" : "⛶ Maximize"}</button>
                    <button id="agyis-close-btn" class="agyis-hud-btn" title="Close (Escape)">✕</button>
                </div>
            </div>
        `;
    }

    /**
     * Binds event listeners for all interactive header controls.
     */
    function bindHudHeaderEvents(hudEl, state, cur, renderCallback, selectStepCallback) {
        if (!hudEl) return;

        // Conversation dropdown selection
        hudEl.querySelector("#agyis-convo-select")?.addEventListener("change", (e) => {
            if (e.target.value && typeof window.__agyis_hud_load_convo === "function") {
                window.__agyis_hud_load_convo(e.target.value);
            }
        });

        // Refresh button
        hudEl.querySelector("#agyis-refresh-btn")?.addEventListener("click", () => {
            const focusedId = (typeof window.detectActiveConversationContext === "function" ? window.detectActiveConversationContext() : null)
                || (typeof window.__agyis_extract_convo_id === "function" ? window.__agyis_extract_convo_id() : null)
                || state.convoId;
            if (focusedId && typeof window.__agyis_hud_load_convo === "function") {
                const btn = hudEl.querySelector("#agyis-refresh-btn");
                if (btn) btn.textContent = "⏳...";
                window.__agyis_hud_load_convo(focusedId).finally(() => {
                    if (btn) btn.textContent = "🔄 Refresh";
                });
            }
        });

        // Close & Maximize buttons
        hudEl.querySelector("#agyis-close-btn")?.addEventListener("click", () => {
            hudEl.style.display = "none";
        });
        hudEl.querySelector("#agyis-maximize-btn")?.addEventListener("click", () => {
            state.isMaximized = !state.isMaximized;
            if (renderCallback) renderCallback();
        });

        // Layout orientation buttons
        hudEl.querySelector("#agyis-layout-side")?.addEventListener("click", () => {
            state.layoutOrientation = "horizontal";
            try { localStorage.setItem("jetski_debug_v2_layout_orientation", "horizontal"); } catch (_) {}
            if (renderCallback) renderCallback();
        });
        hudEl.querySelector("#agyis-layout-stack")?.addEventListener("click", () => {
            state.layoutOrientation = "vertical";
            try { localStorage.setItem("jetski_debug_v2_layout_orientation", "vertical"); } catch (_) {}
            if (renderCallback) renderCallback();
        });

        // Subagents dropdown toggle
        hudEl.querySelector("#agyis-subagents-dropdown-toggle")?.addEventListener("click", (e) => {
            e.stopPropagation();
            state.subagentsDropdownOpen = !state.subagentsDropdownOpen;
            const menu = hudEl.querySelector("#agyis-subagents-menu");
            if (menu) menu.style.display = state.subagentsDropdownOpen ? "block" : "none";
        });

        // Subagent item click (jump directly to child subagent conversation)
        hudEl.querySelectorAll(".agyis-subagent-item").forEach(el => {
            el.addEventListener("click", (e) => {
                e.stopPropagation();
                const sid = el.getAttribute("data-sub-id");
                state.subagentsDropdownOpen = false;
                const menu = hudEl.querySelector("#agyis-subagents-menu");
                if (menu) menu.style.display = "none";

                const subTraj = cur && cur.subagent_trajectories ? cur.subagent_trajectories[sid] : null;
                if (subTraj) {
                    state.currentData = subTraj;
                    state.selectedIndex = Math.max(0, (subTraj.steps || []).length - 1);
                    if (renderCallback) renderCallback();
                } else if (sid && typeof window.__agyis_hud_load_convo === "function") {
                    window.__agyis_hud_load_convo(sid);
                }
            });
        });

        // Parent conversation return button (1-click ← Parent jump)
        hudEl.querySelector("#agyis-parent-btn")?.addEventListener("click", () => {
            if (cur && cur.parent_id && typeof window.__agyis_hud_load_convo === "function") {
                window.__agyis_hud_load_convo(cur.parent_id);
            } else if (state.rootData) {
                state.currentData = state.rootData;
                state.selectedIndex = Math.max(0, (state.rootData.steps || []).length - 1);
                if (renderCallback) renderCallback();
            }
        });

        // Debounced search input
        let searchDebounceTimer = null;
        hudEl.querySelector("#agyis-search-input")?.addEventListener("input", (e) => {
            const val = e.target.value;
            clearTimeout(searchDebounceTimer);
            searchDebounceTimer = setTimeout(() => {
                state.filterQuery = val;
                state.currentMatchIdx = 0;
                state.tablePage = 0;
                if (renderCallback) renderCallback();
                const inputEl = hudEl.querySelector("#agyis-search-input");
                if (inputEl) {
                    inputEl.focus();
                    inputEl.setSelectionRange(val.length, val.length);
                }
            }, 150);
        });

        // Search keyboard navigation (Enter: Next match, Shift+Enter: Prev match, Esc: Clear)
        hudEl.querySelector("#agyis-search-input")?.addEventListener("keydown", (e) => {
            if (e.key === "Enter" && state.searchMatchIndices && state.searchMatchIndices.length > 0) {
                e.preventDefault();
                const len = state.searchMatchIndices.length;
                state.currentMatchIdx = e.shiftKey
                    ? ((state.currentMatchIdx || 0) - 1 + len) % len
                    : ((state.currentMatchIdx || 0) + 1) % len;
                if (selectStepCallback) {
                    selectStepCallback(state.searchMatchIndices[state.currentMatchIdx]);
                }
            } else if (e.key === "Escape") {
                state.filterQuery = "";
                state.tablePage = 0;
                if (renderCallback) renderCallback();
            }
        });

        // Clear search button
        hudEl.querySelector("#agyis-search-clear")?.addEventListener("click", () => {
            state.filterQuery = "";
            state.tablePage = 0;
            if (renderCallback) renderCallback();
        });
    }

    // Export module onto window namespace
    global.renderHudHeader = renderHudHeader;
    global.bindHudHeaderEvents = bindHudHeaderEvents;

})(typeof window !== "undefined" ? window : globalThis);
