// SPDX-License-Identifier: Apache-2.0
// Copyright (c) 2026 Arafat Zahan (@kuasha420)
// Corporate Stewardship & Infrastructure: Purrfect Software Limited (PSL)
// Governed by: ICARO-42/b Ordinance (Company-Supported Personal IP Framework)

/**
 * hud.js — In-situ Trajectory Debug View Orchestrator & Mount Engine.
 * 
 * Assembles the modular frontend components:
 * 1. hud_header.js (Session switcher, badges, search, controls)
 * 2. hud_context_bar.js (Wtc proportional token bar & Atc multi-row packing)
 * 3. hud_timeline.js (lvc continuous ms Gantt visualizer & Buc idle collapsing)
 * 4. hud_inspector.js (ruc 4-tab step/invocation/execution/trajectory inspector)
 * 5. hud_deck.js (ovc split deck with resizable splitter clamps)
 * 6. hud_rpc.js (ConnectRPC client & SSOT token breakdown groups)
 */

(() => {
    const HUD_ID = "agyis-trajectory-hud";
    const STYLES_ID = "agyis-trajectory-hud-styles";
    const __PAYLOAD__ = null;
    const initialData = __PAYLOAD__ ? __PAYLOAD__.initialData : null;
    const conversationList = __PAYLOAD__ ? __PAYLOAD__.conversationList : [];
    const shouldOpen = __PAYLOAD__ ? __PAYLOAD__.shouldOpen : false;
    const isToggle = __PAYLOAD__ ? __PAYLOAD__.isToggle : false;
    let hud = document.getElementById(HUD_ID);

    function syncToLatestState(state) {
        if (!state || !state.currentData) return;
        const steps = state.currentData.steps || [];
        const epochs = state.currentData.epochs || [];

        state.activeEpochIndex = epochs.length > 0 ? epochs.length - 1 : -1;
        state.selectedIndex = Math.max(0, steps.length - 1);

        const totalSteps = steps.length;
        const pageSize = 50;
        const totalPages = Math.max(1, Math.ceil(totalSteps / pageSize));
        state.tablePage = totalPages - 1;
    }

    function extractHudFocusedConvoId() {
        if (typeof window.detectActiveConversationContext === "function") {
            const detected = window.detectActiveConversationContext();
            if (detected) return detected;
        }
        const searchParams = (typeof window !== "undefined" && window.location && window.location.search) ? new URLSearchParams(window.location.search) : null;
        const isUuidPattern = (id) => typeof id === "string" && (/^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i.test(id) || (!/^pane[-_]/i.test(id) && id.length >= 20));

        let tabSubagentId = null;
        if (searchParams) {
            const tabParam = searchParams.get('tab');
            if (tabParam && tabParam.startsWith('subagent_convo__')) {
                const cand = tabParam.slice('subagent_convo__'.length);
                if (isUuidPattern(cand)) tabSubagentId = cand;
            }
        }

        const pathMatch = (window.location && window.location.pathname) ? window.location.pathname.match(/\/c\/([a-zA-Z0-9_-]+)/) : null;
        const routeCascadeId = pathMatch ? pathMatch[1] : null;

        const focusedPane = typeof document !== "undefined" ? document.querySelector('div[data-pane-id]:not([data-pane-unfocused])') : null;
        const rawPaneId = focusedPane ? focusedPane.getAttribute('data-pane-id') : null;
        const focusedPaneId = isUuidPattern(rawPaneId) ? rawPaneId : null;

        const searchCascadeId = searchParams ? searchParams.get('cascadeId') : null;

        return tabSubagentId || routeCascadeId || focusedPaneId || searchCascadeId || null;
    }
    window.__agyis_extract_convo_id = extractHudFocusedConvoId;

    let existingHud = document.getElementById(HUD_ID);
    if (existingHud && isToggle) {
        const isHidden = existingHud.style.display === "none";
        existingHud.style.display = isHidden ? "flex" : "none";
        if (isHidden) {
            const focusedConvoId = extractHudFocusedConvoId();
            const state = window.__agyis_hud_state;
            if (focusedConvoId && state && focusedConvoId !== state.convoId && typeof window.__agyis_hud_load_convo === "function") {
                window.__agyis_hud_load_convo(focusedConvoId);
            } else if (state) {
                syncToLatestState(state);
                if (typeof renderHud === "function") renderHud();
                const selEl = document.querySelector(`.agyis-step-grid-item[data-index="${state.selectedIndex}"]`);
                if (selEl) selEl.scrollIntoView({ block: "nearest" });
            }
        }
        return { success: true, open: isHidden, toggled: true };
    }

    // Stale DOM Replacement: Purge existing HUD and styles on re-injection (PSL-INV-010)
    if (existingHud) existingHud.remove();
    const existingStyles = document.getElementById(STYLES_ID);
    if (existingStyles) existingStyles.remove();

    const styleEl = document.createElement("style");
    styleEl.id = STYLES_ID;
    styleEl.textContent = `/* __HUD_STYLES__ */`;
    document.head.appendChild(styleEl);

    hud = document.createElement("div");
    hud.id = HUD_ID;
    hud.style.display = shouldOpen ? "flex" : "none";

    const steps = (initialData && initialData.steps) || [];
    const epochs = (initialData && initialData.epochs) || [];

    // Initialize cleanroom state
    let savedOrientation = "horizontal";
    let savedInspectorWidth = null;
    let savedInspectorHeight = null;
    try {
        savedOrientation = localStorage.getItem("jetski_debug_v2_layout_orientation") || "horizontal";
        const w = parseInt(localStorage.getItem("jetski_debug_v2_inspector_width") || "", 10);
        if (!isNaN(w) && w >= 300) savedInspectorWidth = w;
        const h = parseInt(localStorage.getItem("jetski_debug_v2_inspector_height") || "", 10);
        if (!isNaN(h) && h >= 150) savedInspectorHeight = h;
    } catch (_) {}

    window.__agyis_hud_state = {
        rootData: initialData,
        currentData: initialData,
        sessionModel: (initialData && initialData.model) || "",
        convoId: (initialData && initialData.conversation_id) || "",
        selectedIndex: Math.max(0, steps.length - 1),
        activeEpochIndex: epochs.length > 0 ? epochs.length - 1 : -1,
        tablePage: Math.max(0, Math.ceil(steps.length / 50) - 1),
        pageSize: 50,
        filterQuery: "",
        searchMatchIndices: [],
        currentMatchIdx: -1,
        activeTab: "step",
        mainDeckTab: "context",
        timelineMode: "steps",
        layoutOrientation: savedOrientation,
        inspectorWidth: savedInspectorWidth,
        inspectorHeight: savedInspectorHeight,
        isMaximized: false,
        subagentsDropdownOpen: false,
        hoveredItemKey: null,
    };
    syncToLatestState(window.__agyis_hud_state);

    /* __HUD_HEADER__ */
    /* __HUD_CONTEXT_BAR__ */
    /* __HUD_TIMELINE__ */
    /* __HUD_INSPECTOR__ */
    /* __HUD_DECK__ */
    /* __HUD_RPC__ */
    /* __HOTKEY__ */

    function selectStep(sIdx) {
        const state = window.__agyis_hud_state;
        const cur = state.currentData;
        const curEpochs = (cur && cur.epochs) || [];
        const foundEp = curEpochs.find(ep => sIdx >= ep.start_index && sIdx <= ep.end_index);
        if (foundEp) state.activeEpochIndex = foundEp.epoch_index;
        state.selectedIndex = sIdx;
        renderHud();
        const rowEl = hud.querySelector(`.agyis-step-grid-item[data-index="${sIdx}"]`);
        if (rowEl) rowEl.scrollIntoView({ block: "nearest", behavior: "smooth" });
    }

    function renderHud() {
        const state = window.__agyis_hud_state;
        const cur = state.currentData;
        const curSteps = (cur && cur.steps) || [];
        const currentStep = curSteps[state.selectedIndex] || null;

        // Filter steps by search query
        const q = (state.filterQuery || "").trim().toLowerCase();
        const filteredIndices = [];
        for (let i = 0; i < curSteps.length; i++) {
            const s = curSteps[i];
            if (!q) {
                filteredIndices.push(i);
                continue;
            }
            const hay = `${s.type || ""} ${s.content || ""} ${s.thinking || ""} ${(s.tool_calls || []).map(t => (t.name || "") + " " + JSON.stringify(t.args || {})).join(" ")}`.toLowerCase();
            if (hay.includes(q)) filteredIndices.push(i);
        }
        state.searchMatchIndices = filteredIndices;

        const curEpochs = (cur && cur.epochs && cur.epochs.length > 0) ? cur.epochs : [{
            epoch_index: 0,
            start_index: 0,
            end_index: Math.max(0, curSteps.length - 1),
            step_count: curSteps.length,
            has_checkpoint: false,
            summary: "Initial Trajectory",
        }];
        if (state.activeEpochIndex === undefined || state.activeEpochIndex < 0 || state.activeEpochIndex >= curEpochs.length) {
            const foundEp = curEpochs.find(ep => state.selectedIndex >= ep.start_index && state.selectedIndex <= ep.end_index);
            state.activeEpochIndex = foundEp ? foundEp.epoch_index : (curEpochs.length - 1);
        }
        const activeEpoch = curEpochs[state.activeEpochIndex] || curEpochs[curEpochs.length - 1];
        const epochSteps = curSteps.slice(activeEpoch.start_index, activeEpoch.end_index + 1);

        const containerWidth = window.innerWidth * 0.95;

        // Render modular components
        const headerHtml = window.renderHudHeader ? window.renderHudHeader(state, cur, conversationList) : "";
        const inspectorContentHtml = window.buildInspectorHtml ? window.buildInspectorHtml(currentStep, state, cur) : "";
        const deckHtml = window.renderMainDeck ? window.renderMainDeck(
            cur, state, curSteps, curEpochs, activeEpoch, epochSteps, filteredIndices, inspectorContentHtml, currentStep, containerWidth
        ) : "";

        if (!hud) hud = document.getElementById(HUD_ID);
        if (!hud) return;

        hud.innerHTML = `
            <div class="agyis-hud-box ${state.isMaximized ? "maximized" : ""}">
                ${headerHtml}
                ${deckHtml}
            </div>
        `;

        // Bind modular events
        if (window.bindHudHeaderEvents) window.bindHudHeaderEvents(hud, state, cur, renderHud, selectStep);
        if (window.bindContextBarEvents) window.bindContextBarEvents(hud, state, cur, curEpochs, renderHud, selectStep);
        if (window.bindTimelineEvents) window.bindTimelineEvents(hud, state, renderHud, selectStep);
        if (window.bindInspectorEvents) window.bindInspectorEvents(hud, state, currentStep, selectStep);
        if (window.initDeckSplitterAndNav) window.initDeckSplitterAndNav(hud, state, curSteps, filteredIndices, renderHud, selectStep);

        // Prism syntax highlight
        if (window.Prism && typeof window.Prism.highlightAllUnder === "function") {
            const inspBody = hud.querySelector("#agyis-inspector-body");
            if (inspBody) { try { window.Prism.highlightAllUnder(inspBody); } catch (_) {} }
        }
    }

    window.__agyis_hud_render = renderHud;
    window.__agyis_hud_sync = syncToLatestState;
    window.__agyis_hud_load_convo = async function(convoId) {
        if (window.loadConversationViaRpc) {
            const data = await window.loadConversationViaRpc(convoId);
            if (data) {
                const state = window.__agyis_hud_state;
                if (state) {
                    state.rootData = data;
                    state.currentData = data;
                    state.convoId = convoId;
                    if (data.model) state.sessionModel = data.model;
                    syncToLatestState(state);
                    state.subagentsDropdownOpen = false;
                    renderHud();
                }
                return data;
            }
        }
        return null;
    };

    renderHud();
    document.body.appendChild(hud);

    // Initial check + SPA route sensitivity watcher (PSL-INV-010)
    const initialFocusedConvo = extractHudFocusedConvoId();
    if (initialFocusedConvo && initialFocusedConvo !== (initialData && initialData.conversation_id) && typeof window.__agyis_hud_load_convo === "function") {
        window.__agyis_hud_load_convo(initialFocusedConvo);
    }

    if (typeof window.__agyis_hud_route_cleanup === "function") {
        try { window.__agyis_hud_route_cleanup(); } catch (_) {}
    }
    if (!window.__agyis_hud_history_patched && window.history && typeof window.history.pushState === "function") {
        window.__agyis_hud_history_patched = true;
        ["pushState", "replaceState"].forEach(fnName => {
            const origFn = window.history[fnName];
            if (typeof origFn === "function") {
                window.history[fnName] = function(...args) {
                    const out = origFn.apply(this, args);
                    if (typeof window.dispatchEvent === "function" && typeof Event === "function") {
                        window.dispatchEvent(new Event("agyis:routechange"));
                    }
                    return out;
                };
            }
        });
    }
    const onSpaRouteChange = () => {
        const focusedConvoId = extractHudFocusedConvoId();
        const state = window.__agyis_hud_state;
        if (focusedConvoId && state && focusedConvoId !== state.convoId && typeof window.__agyis_hud_load_convo === "function") {
            window.__agyis_hud_load_convo(focusedConvoId);
        }
    };
    window.addEventListener("popstate", onSpaRouteChange);
    window.addEventListener("agyis:routechange", onSpaRouteChange);
    window.__agyis_hud_route_cleanup = () => {
        window.removeEventListener("popstate", onSpaRouteChange);
        window.removeEventListener("agyis:routechange", onSpaRouteChange);
    };

    if (window.__agyis_hud_doc_click) document.removeEventListener("click", window.__agyis_hud_doc_click);
    window.__agyis_hud_doc_click = (e) => {
        if (window.__agyis_hud_state && window.__agyis_hud_state.subagentsDropdownOpen) {
            const toggleBtn = hud ? hud.querySelector("#agyis-subagents-dropdown-toggle") : null;
            const menu = hud ? hud.querySelector("#agyis-subagents-menu") : null;
            if (e && ((toggleBtn && toggleBtn.contains(e.target)) || (menu && menu.contains(e.target)))) {
                return;
            }
            window.__agyis_hud_state.subagentsDropdownOpen = false;
            if (menu) menu.style.display = "none";
        }
    };
    document.addEventListener("click", window.__agyis_hud_doc_click);

    // Global Hotkey & Keyboard Navigation (j/k and ArrowDown/ArrowUp)
    window.__agyis_hud_hotkey_registered = true;
    window.__agyis_hud_last_toggle = window.__agyis_hud_last_toggle || 0;
    if (window.__agyis_hud_active_listener) {
        window.removeEventListener("keydown", window.__agyis_hud_active_listener, true);
    }
    window.__agyis_hud_active_listener = (e) => {
        const isF12 = e.key === "F12";
        const isCtrlShiftT = (e.ctrlKey || e.metaKey) && e.shiftKey && (e.key === "T" || e.key === "t");
        const currentHud = document.getElementById(HUD_ID);

        if (isF12 || isCtrlShiftT) {
            e.preventDefault();
            e.stopImmediatePropagation();
            const now = Date.now();
            if (now - (window.__agyis_hud_last_toggle || 0) < 250) return;
            window.__agyis_hud_last_toggle = now;
            if (currentHud) {
                const isHidden = (currentHud.style.display === "none");
                currentHud.style.display = isHidden ? "flex" : "none";
                if (isHidden) {
                    const focusedConvoId = extractHudFocusedConvoId();
                    const state = window.__agyis_hud_state;
                    if (focusedConvoId && state && focusedConvoId !== state.convoId && typeof window.__agyis_hud_load_convo === "function") {
                        window.__agyis_hud_load_convo(focusedConvoId);
                    } else if (state) {
                        syncToLatestState(state);
                        if (typeof renderHud === "function") renderHud();
                    }
                }
            }
        }

        if (e.key === "Escape" && currentHud && currentHud.style.display !== "none") {
            currentHud.style.display = "none";
        }

        // Keyboard navigation (j/k or ArrowDown/ArrowUp)
        if (currentHud && currentHud.style.display !== "none" && e.target && e.target.tagName !== "INPUT" && e.target.tagName !== "TEXTAREA" && e.target.tagName !== "SELECT" && !e.target.isContentEditable) {
            const state = window.__agyis_hud_state;
            if (!state) return;
            const curSteps = (state.currentData && state.currentData.steps) ? state.currentData.steps : [];

            if ((e.key === "ArrowDown" || e.key === "j") && state.selectedIndex < curSteps.length - 1) {
                e.preventDefault();
                selectStep(state.selectedIndex + 1);
            }
            if ((e.key === "ArrowUp" || e.key === "k") && state.selectedIndex > 0) {
                e.preventDefault();
                selectStep(state.selectedIndex - 1);
            }
            if (e.key === "ArrowLeft" && state.selectedIndex > 0) {
                e.preventDefault();
                selectStep(state.selectedIndex - 1);
            }
            if (e.key === "ArrowRight" && state.selectedIndex < curSteps.length - 1) {
                e.preventDefault();
                selectStep(state.selectedIndex + 1);
            }
        }
    };
    window.addEventListener("keydown", window.__agyis_hud_active_listener, true);
})();
