// SPDX-License-Identifier: Apache-2.0
// Copyright (c) 2026 Arafat Zahan (@kuasha420)
// Corporate Stewardship & Infrastructure: Purrfect Software Limited (PSL)
// Governed by: ICARO-42/b Ordinance (Company-Supported Personal IP Framework)

/**
 * hud_deck.js — Split Deck Layout & Splitter Manager (ovc Parity).
 * 
 * Implements canonical Antigravity 2.26.0 ovc split deck layout with resizable
 * splitter clamps (Horizontal: container >= 700px, inspector [300, W-400];
 * Vertical: container >= 350px, inspector [150, H-200]), double-click reset to flex,
 * below-min flex fallback, 8-column CSS grid step history table, and keyboard navigation.
 */

(function(global) {
    "use strict";

    const _u = () => global.__agyis_utils || {};
    const escapeHtml = (val) => (_u().escapeHtml ? _u().escapeHtml(val) : String(val ?? ""));
    const formatBytes = (bytes) => (_u().formatBytes ? _u().formatBytes(bytes) : "0 B");

    function stepPillClassForType(type) {
        if (!type) return "agyis-hud-pill-blue";
        if (type === "PLANNER_RESPONSE" || type === "MODEL_OUTPUT") return "agyis-hud-pill-amber";
        if (type === "CHECKPOINT") return "agyis-hud-pill-green";
        if (/COMMAND|TOOL|TASK|SEARCH|PLAN|FOCUS|STEPS|QUESTION|MCP|MARKETPLACE|PLUGIN/.test(type)) return "agyis-hud-pill-teal";
        if (/FILE|EDIT|READ|WRITE|REPLACE|RESOURCE/.test(type)) return "agyis-hud-pill-green";
        if (type === "INVOKE_SUBAGENT" || /SWARM|BOARD|WORKFLOW|SUBAGENT/.test(type)) return "agyis-hud-pill-purple";
        if (type === "SYSTEM") return "agyis-hud-pill-zinc";
        return "agyis-hud-pill-blue";
    }

    /**
     * Renders the complete Split Deck HTML (main pane, splitter, inspector pane).
     */
    function renderMainDeck(cur, state, steps, checkpoints, activeCheckpoint, checkpointSteps, filteredIndices, inspectorContentHtml, currentStep, containerWidth) {
        const rawOrientation = state.layoutOrientation || "horizontal";
        const orientation = (rawOrientation === "vertical" || rawOrientation === "stack") ? "vertical" : "horizontal";
        const pageSize = 50;
        const totalFiltered = filteredIndices.length;
        const totalPages = Math.max(1, Math.ceil(totalFiltered / pageSize));

        if (state.tablePage === undefined || state.tablePage < 0) state.tablePage = 0;
        if (state.tablePage >= totalPages) state.tablePage = totalPages - 1;

        const pageStart = state.tablePage * pageSize;
        const pageEnd = Math.min(totalFiltered, pageStart + pageSize);
        const pagedIndices = filteredIndices.slice(pageStart, pageEnd);

        // 8-column CSS Grid History Rows (rmc parity)
        const gridRowsHtml = pagedIndices.map(idx => {
            const s = steps[idx];
            const type = s.type || "STEP";
            const pillClass = stepPillClassForType(type);
            const status = s.status || "DONE";
            let statusPillClass = "agyis-hud-pill-green";
            if (status === "ERROR") statusPillClass = "agyis-hud-pill-red";
            else if (status === "RUNNING") statusPillClass = "agyis-hud-pill-blue";
            else if (status === "WAITING") statusPillClass = "agyis-hud-pill-amber";

            let details = s.thinking || s.content || "";
            if (type === "CHECKPOINT") details = s.compaction_summary || s.summary || s.sessionSummary || details || "Checkpoint";
            if (!details && (s.tool_calls || []).length > 0) {
                details = s.tool_calls.map(tc => tc.name + "(" + JSON.stringify(tc.args || {}) + ")").join("; ");
            }
            details = details.replace(/\n/g, " ").slice(0, 160);

            const isSelected = idx === state.selectedIndex;
            const isHovered = state.hoveredItemKey === `step-${idx}`;

            return `
                <div class="agyis-step-grid-row agyis-step-grid-item ${isSelected ? "selected" : ""} ${isHovered ? "context-cell-hovered" : ""}"
                     data-index="${idx}"
                     data-item-key="step-${idx}">
                    <div style="color: #6E7F9B;">${s.exec_index || 1}</div>
                    <div style="color: #6E7F9B;">${s.inv_index || 1}</div>
                    <div style="font-weight: 700;">#${s.step_index ?? idx}</div>
                    <div><span class="agyis-hud-pill ${pillClass}">${escapeHtml(type)}</span></div>
                    <div style="color: #9AA8BE; overflow: hidden; text-overflow: ellipsis; white-space: nowrap;">${escapeHtml(details || "—")}</div>
                    <div><span class="agyis-hud-pill ${statusPillClass}">${escapeHtml(status)}</span></div>
                    <div style="text-align: right; color: #F4F6FA;">${(s.tokens || 0).toLocaleString()}</div>
                    <div style="text-align: right; color: #6E7F9B;">${formatBytes(s.size_bytes)}</div>
                </div>
            `;
        }).join("");

        // Content of Main Pane: Context Window View vs Timeline View
        let mainPaneBodyHtml = "";
        if (state.mainDeckTab === "timeline") {
            mainPaneBodyHtml = typeof global.renderTimelineView === "function"
                ? global.renderTimelineView(steps, state, containerWidth)
                : "<div style='padding: 20px;'>Timeline Module Loading...</div>";
        } else {
            const inferCtx = _u().inferModelContextWindow;
            const maxTokens = (cur && cur.max_context_tokens)
                || (inferCtx ? inferCtx((cur && cur.model) || (state && state.sessionModel)) : 256000);
            const contextBarHtml = typeof global.renderContextBar === "function"
                ? global.renderContextBar(cur, state, steps, activeCheckpoint, checkpointSteps, maxTokens, containerWidth)
                : "<div style='padding: 20px;'>Context Bar Loading...</div>";

            mainPaneBodyHtml = `
                ${contextBarHtml}
                <div class="agyis-step-grid-row agyis-step-grid-header">
                    <div>EXEC</div><div>INV</div><div>STEP</div><div>TYPE</div><div>DETAILS</div><div>STATUS</div>
                    <div style="text-align: right;" title="Non-model response token counts are estimations. The model API does not return per-message token counts.">TOKENS</div>
                    <div style="text-align: right;" title="Serialized size of the step as received by this view, which subscribes at FULL verbosity (untruncated). The production UI receives smaller payloads: at PROD_UI verbosity the server strips fields it does not render (raw tool outputs, planner tool calls, thinking signatures, ...).">SIZE</div>
                </div>
                <div class="agyis-step-grid-body">
                    ${gridRowsHtml || "<div style='padding: 20px; text-align: center; color: #6E7F9B;'>No results found</div>"}
                </div>
                <div class="agyis-step-grid-pagination" style="display: flex; justify-content: space-between; align-items: center; padding: 6px 10px; background: #10192B; border-top: 1px solid #1E2C47; font-size: 11px; flex-shrink: 0;">
                    <div style="display: flex; gap: 4px; align-items: center;">
                        <button id="agyis-page-prev" class="agyis-hud-btn" ${state.tablePage <= 0 ? 'disabled style="opacity:0.4; cursor:default;"' : ""} aria-label="Load earlier steps">◀ Prev 50</button>
                        <span style="font-family: var(--agyis-font-mono, monospace); color: #F4F6FA; padding: 0 6px;">Page ${state.tablePage + 1} of ${totalPages} (${totalFiltered > 0 ? pageStart + 1 : 0}-${pageEnd} of ${totalFiltered})</span>
                        <button id="agyis-page-next" class="agyis-hud-btn" ${state.tablePage >= totalPages - 1 ? 'disabled style="opacity:0.4; cursor:default;"' : ""} aria-label="Load later steps">Next 50 ▶</button>
                    </div>
                    <button id="agyis-page-jump-selected" class="agyis-hud-btn" title="Jump to selected step">Jump to Selected</button>
                </div>
            `;
        }

        // Inspector sizing style
        let inspectorStyle = "";
        if (orientation === "horizontal" && state.inspectorWidth) {
            inspectorStyle = `width: ${state.inspectorWidth}px; flex: none;`;
        } else if (orientation === "vertical" && state.inspectorHeight) {
            inspectorStyle = `height: ${state.inspectorHeight}px; flex: none;`;
        }

        const hasFilter = Boolean((state.filterQuery || "").trim());
        const navIndices = hasFilter ? filteredIndices : steps.map((_, i) => i);
        const navPos = navIndices.indexOf(state.selectedIndex);
        const canFirst = navIndices.length > 0 && state.selectedIndex !== navIndices[0];
        const canPrev = navIndices.length > 0 && (navPos > 0 || (navPos === -1 && navIndices.some(idx => idx < state.selectedIndex)));
        const canNext = navIndices.length > 0 && (navPos !== -1 ? navPos < navIndices.length - 1 : navIndices.some(idx => idx > state.selectedIndex));
        const canLast = navIndices.length > 0 && state.selectedIndex !== navIndices[navIndices.length - 1];
        const navCounterLabel = navIndices.length > 0 ? `${navPos >= 0 ? navPos + 1 : "-"} / ${navIndices.length}` : "0 / 0";

        return `
            <div id="agyis-hud-deck" class="agyis-hud-main-deck ${orientation}">
                <div class="agyis-grid-pane">
                    <div class="agyis-main-deck-tabs">
                        <button class="agyis-main-tab-btn ${state.mainDeckTab !== "timeline" ? "active" : ""}" data-main-tab="context">Context Window</button>
                        <button class="agyis-main-tab-btn ${state.mainDeckTab === "timeline" ? "active" : ""}" data-main-tab="timeline">Timeline</button>
                    </div>
                    ${mainPaneBodyHtml}
                </div>
                <div id="agyis-splitter" class="agyis-splitter" title="Double-click to reset panel sizes"></div>
                <div class="agyis-inspector-pane" style="${inspectorStyle}">
                    <div class="agyis-inspector-header">
                        <div style="display: flex; align-items: center; gap: 8px;">
                            <span style="font-weight: 700; font-size: 12px;">Step #${currentStep ? (currentStep.step_index ?? state.selectedIndex) : "-"}</span>
                            ${currentStep ? `<span class="agyis-hud-pill agyis-hud-pill-cobalt">${escapeHtml(currentStep.type || "STEP")}</span>` : ""}
                        </div>
                        <div style="display: flex; gap: 4px; align-items: center;">
                            <button id="agyis-step-first" class="agyis-hud-btn" ${!canFirst ? 'disabled style="opacity:0.4;"' : ""} title="First step">«</button>
                            <button id="agyis-step-prev" class="agyis-hud-btn" ${!canPrev ? 'disabled style="opacity:0.4;"' : ""} title="Previous step">‹</button>
                            <span style="font-size: 11px; font-family: var(--agyis-font-mono, monospace); padding: 0 4px; color: #9AA8BE;">${navCounterLabel}</span>
                            <button id="agyis-step-next" class="agyis-hud-btn" ${!canNext ? 'disabled style="opacity:0.4;"' : ""} title="Next step">›</button>
                            <button id="agyis-step-last" class="agyis-hud-btn" ${!canLast ? 'disabled style="opacity:0.4;"' : ""} title="Last step">»</button>
                        </div>
                    </div>
                    <div class="agyis-inspector-tabs">
                        <button class="agyis-hud-btn ${state.activeTab === "step" ? "active" : ""}" data-tab="step">Step</button>
                        <button class="agyis-hud-btn ${state.activeTab === "invocation" ? "active" : ""}" data-tab="invocation">Invocation</button>
                        <button class="agyis-hud-btn ${state.activeTab === "execution" ? "active" : ""}" data-tab="execution">Execution</button>
                        <button class="agyis-hud-btn ${state.activeTab === "trajectory" ? "active" : ""}" data-tab="trajectory">Trajectory</button>
                    </div>
                    <div class="agyis-inspector-content" id="agyis-inspector-body">
                        ${inspectorContentHtml}
                    </div>
                </div>
            </div>
        `;
    }

    /**
     * Initializes the interactive resizable splitter clamps (ovc) and navigation.
     */
    function initDeckSplitterAndNav(hudEl, state, steps, filteredIndices, renderCallback, selectStepCallback) {
        if (!hudEl) return;
        const deckEl = hudEl.querySelector("#agyis-hud-deck");
        const splitterEl = hudEl.querySelector("#agyis-splitter");
        if (!deckEl || !splitterEl) return;

        // Double-click to reset splitter to flex layout
        splitterEl.addEventListener("dblclick", () => {
            state.inspectorWidth = null;
            state.inspectorHeight = null;
            try {
                localStorage.removeItem("jetski_debug_v2_inspector_width");
                localStorage.removeItem("jetski_debug_v2_inspector_height");
            } catch (_) {}
            if (renderCallback) renderCallback();
        });

        // Mouse drag resizing with canonical ovc clamps
        splitterEl.addEventListener("mousedown", (downEvent) => {
            downEvent.preventDefault();
            const rawOrientation = state.layoutOrientation || "horizontal";
            const orientation = (rawOrientation === "vertical" || rawOrientation === "stack") ? "vertical" : "horizontal";
            const deckRect = deckEl.getBoundingClientRect();

            const onMouseMove = (moveEvent) => {
                if (orientation === "horizontal") {
                    const containerWidth = deckRect.width;
                    if (containerWidth < 700) return; // Below-min fallback
                    const inspectorWidth = deckRect.right - moveEvent.clientX;
                    // Horizontal Clamps: Inspector [300, W-400]
                    if (inspectorWidth >= 300 && inspectorWidth <= containerWidth - 400) {
                        state.inspectorWidth = inspectorWidth;
                        const inspPane = hudEl.querySelector(".agyis-inspector-pane");
                        if (inspPane) {
                            inspPane.style.width = `${inspectorWidth}px`;
                            inspPane.style.flex = "none";
                        }
                    }
                } else {
                    const containerHeight = deckRect.height;
                    if (containerHeight < 350) return; // Below-min fallback
                    const inspectorHeight = deckRect.bottom - moveEvent.clientY;
                    // Vertical Clamps: Inspector [150, H-200]
                    if (inspectorHeight >= 150 && inspectorHeight <= containerHeight - 200) {
                        state.inspectorHeight = inspectorHeight;
                        const inspPane = hudEl.querySelector(".agyis-inspector-pane");
                        if (inspPane) {
                            inspPane.style.height = `${inspectorHeight}px`;
                            inspPane.style.flex = "none";
                        }
                    }
                }
            };

            const onMouseUp = () => {
                document.removeEventListener("mousemove", onMouseMove);
                document.removeEventListener("mouseup", onMouseUp);
                if (typeof window !== "undefined") window.removeEventListener("blur", onMouseUp);
                if (global.__agyis_splitter_cleanup === onMouseUp) {
                    global.__agyis_splitter_cleanup = null;
                }
                try {
                    if (state.inspectorWidth) localStorage.setItem("jetski_debug_v2_inspector_width", String(state.inspectorWidth));
                    if (state.inspectorHeight) localStorage.setItem("jetski_debug_v2_inspector_height", String(state.inspectorHeight));
                } catch (_) {}
            };

            if (typeof global.__agyis_splitter_cleanup === "function") {
                try { global.__agyis_splitter_cleanup(); } catch (_) {}
            }
            global.__agyis_splitter_cleanup = onMouseUp;
            document.addEventListener("mousemove", onMouseMove);
            document.addEventListener("mouseup", onMouseUp);
            if (typeof window !== "undefined") window.addEventListener("blur", onMouseUp);
        });

        // Tab switching: Context Window vs Timeline
        hudEl.querySelectorAll(".agyis-main-tab-btn").forEach(btn => {
            btn.addEventListener("click", () => {
                state.mainDeckTab = btn.getAttribute("data-main-tab");
                if (renderCallback) renderCallback();
            });
        });

        // Inspector tabs
        hudEl.querySelectorAll(".agyis-inspector-tabs .agyis-hud-btn[data-tab]").forEach(btn => {
            btn.addEventListener("click", () => {
                state.activeTab = btn.getAttribute("data-tab");
                if (renderCallback) renderCallback();
            });
        });

        // Step arrow navigation (respects active filter when present)
        const hasFilter = Boolean((state.filterQuery || "").trim());
        const navIndices = hasFilter ? filteredIndices : steps.map((_, i) => i);
        const navPos = navIndices.indexOf(state.selectedIndex);
        hudEl.querySelector("#agyis-step-first")?.addEventListener("click", () => {
            if (navIndices.length > 0 && selectStepCallback) selectStepCallback(navIndices[0]);
        });
        hudEl.querySelector("#agyis-step-prev")?.addEventListener("click", () => {
            if (!selectStepCallback || navIndices.length === 0) return;
            if (navPos > 0) selectStepCallback(navIndices[navPos - 1]);
            else if (navPos === -1) {
                const prevHits = navIndices.filter(idx => idx < state.selectedIndex);
                if (prevHits.length > 0) selectStepCallback(prevHits[prevHits.length - 1]);
            }
        });
        hudEl.querySelector("#agyis-step-next")?.addEventListener("click", () => {
            if (!selectStepCallback || navIndices.length === 0) return;
            if (navPos >= 0 && navPos < navIndices.length - 1) selectStepCallback(navIndices[navPos + 1]);
            else if (navPos === -1) {
                const nextHit = navIndices.find(idx => idx > state.selectedIndex);
                if (nextHit !== undefined) selectStepCallback(nextHit);
            }
        });
        hudEl.querySelector("#agyis-step-last")?.addEventListener("click", () => {
            if (navIndices.length > 0 && selectStepCallback) selectStepCallback(navIndices[navIndices.length - 1]);
        });

        // Step grid row clicks & hover
        hudEl.querySelectorAll(".agyis-step-grid-item").forEach(rowEl => {
            rowEl.addEventListener("click", () => {
                const idx = parseInt(rowEl.getAttribute("data-index") || "0", 10);
                if (!isNaN(idx) && selectStepCallback) selectStepCallback(idx);
            });
        });
        if (typeof _u().bindItemKeyHover === "function") {
            _u().bindItemKeyHover(hudEl, state, ".agyis-step-grid-item");
        }

        // Pagination buttons
        hudEl.querySelector("#agyis-page-prev")?.addEventListener("click", () => {
            if (state.tablePage > 0) {
                state.tablePage -= 1;
                if (renderCallback) renderCallback();
            }
        });
        hudEl.querySelector("#agyis-page-next")?.addEventListener("click", () => {
            const pageSize = 50;
            const totalPages = Math.max(1, Math.ceil(filteredIndices.length / pageSize));
            if (state.tablePage < totalPages - 1) {
                state.tablePage += 1;
                if (renderCallback) renderCallback();
            }
        });
        hudEl.querySelector("#agyis-page-jump-selected")?.addEventListener("click", () => {
            const pageSize = 50;
            const fIdx = filteredIndices.indexOf(state.selectedIndex);
            if (fIdx >= 0) {
                state.tablePage = Math.floor(fIdx / pageSize);
                if (renderCallback) renderCallback();
                if (typeof _u().scrollSelectedStepIntoView === "function") {
                    _u().scrollSelectedStepIntoView(hudEl, state, state.selectedIndex);
                } else {
                    const rowEl = hudEl.querySelector(`.agyis-step-grid-item[data-index="${state.selectedIndex}"]`);
                    if (rowEl) rowEl.scrollIntoView({ block: "nearest", inline: "nearest" });
                }
            }
        });
    }

    // Export module onto window namespace
    global.renderMainDeck = renderMainDeck;
    global.initDeckSplitterAndNav = initDeckSplitterAndNav;

})(typeof window !== "undefined" ? window : globalThis);
