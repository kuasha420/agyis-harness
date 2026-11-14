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
        const searchParams = (typeof window !== "undefined" && window.location && window.location.search) ? new URLSearchParams(window.location.search) : null;
        const isUuidPattern = (id) => typeof id === "string" && (/^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i.test(id) || (!/^pane[-_]/i.test(id) && id.length >= 20));

        // Priority 1: Check active subagent tab query parameter (?tab=subagent_convo__<uuid>)
        if (searchParams) {
            const tabParam = searchParams.get('tab');
            if (tabParam && tabParam.startsWith('subagent_convo__')) {
                const cand = tabParam.slice('subagent_convo__'.length);
                if (cand && /^[0-9a-zA-Z_-]+$/.test(cand)) return cand;
            }
        }

        // Priority 2: Delegate to global detector if available
        if (typeof window.detectActiveConversationContext === "function") {
            const detected = window.detectActiveConversationContext();
            if (detected) return detected;
        }

        const pathMatch = (window.location && window.location.pathname) ? window.location.pathname.match(/\/c\/([a-zA-Z0-9_-]+)/) : null;
        const routeCascadeId = pathMatch ? pathMatch[1] : null;

        const focusedPane = typeof document !== "undefined" ? document.querySelector('div[data-pane-id]:not([data-pane-unfocused])') : null;
        const rawPaneId = focusedPane ? focusedPane.getAttribute('data-pane-id') : null;
        const focusedPaneId = isUuidPattern(rawPaneId) ? rawPaneId : null;

        const searchCascadeId = searchParams ? searchParams.get('cascadeId') : null;

        return routeCascadeId || focusedPaneId || searchCascadeId || null;
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

        let activeElId = null;
        let activeSelStart = null;
        let activeSelEnd = null;
        let activeValue = null;
        try {
            const activeEl = document.activeElement;
            if (activeEl && (hud.contains(activeEl) || activeEl.id === "agyis-search-input") && activeEl.id) {
                activeElId = activeEl.id;
                if (typeof activeEl.selectionStart === "number") {
                    activeSelStart = activeEl.selectionStart;
                    activeSelEnd = activeEl.selectionEnd;
                }
                if (typeof activeEl.value === "string") {
                    activeValue = activeEl.value;
                }
            }
        } catch (_) {}

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

        // Restore focus and cursor caret positions immediately after mounting
        if (activeElId) {
            try {
                const restoredEl = hud.querySelector("#" + activeElId);
                if (restoredEl) {
                    if (activeValue !== null && restoredEl.value !== activeValue) {
                        restoredEl.value = activeValue;
                    }
                    if (typeof restoredEl.focus === "function") {
                        restoredEl.focus();
                    }
                    if (typeof activeSelStart === "number" && typeof restoredEl.setSelectionRange === "function") {
                        restoredEl.setSelectionRange(activeSelStart, activeSelEnd);
                    }
                }
            } catch (_) {}
        }

        // Prism syntax highlight
        if (window.Prism && typeof window.Prism.highlightAllUnder === "function") {
            const inspBody = hud.querySelector("#agyis-inspector-body");
            if (inspBody) { try { window.Prism.highlightAllUnder(inspBody); } catch (_) {} }
        }
    }

    let activeStreamClient = null;

    function handleStreamStateChange(streamState, dirty) {
        const state = window.__agyis_hud_state;
        if (!state) return;
        const convoId = streamState.conversationId || state.convoId;
        const rawSteps = (streamState.stepsInSlice || []).filter(Boolean);
        if (rawSteps.length === 0 && !dirty.tokens) return;

        let updatedData = null;
        if (typeof window.buildHudTrajectoryData === "function" && rawSteps.length > 0) {
            updatedData = window.buildHudTrajectoryData(
                convoId,
                rawSteps,
                (streamState.generatorMetadatasInSlice || []).filter(Boolean),
                [],
                null
            );
        }

        if (updatedData) {
            const prevSelected = state.selectedIndex;
            const prevTotal = state.currentData && state.currentData.steps ? state.currentData.steps.length : 0;
            const wasAtEnd = prevTotal === 0 || prevSelected >= prevTotal - 1;

            state.rootData = updatedData;
            state.currentData = updatedData;
            state.convoId = convoId;
            if (updatedData.model) state.sessionModel = updatedData.model;

            if (wasAtEnd) {
                syncToLatestState(state);
            } else {
                // Historical inspection: preserve user step selection and active epoch
                const steps = updatedData.steps || [];
                const epochs = updatedData.epochs || [];
                state.selectedIndex = Math.min(prevSelected, Math.max(0, steps.length - 1));
                if (epochs.length > 0) {
                    const foundEp = epochs.find(ep => state.selectedIndex >= ep.start_index && state.selectedIndex <= ep.end_index);
                    state.activeEpochIndex = foundEp ? foundEp.epoch_index : (epochs.length - 1);
                }
                state.tablePage = Math.floor(state.selectedIndex / 50);
            }
            renderHud();
        } else if (dirty.tokens && streamState.tokenBreakdown && state.currentData) {
            state.currentData.total_tokens = streamState.activeTokens || state.currentData.total_tokens;
            state.currentData.token_breakdown = streamState.tokenBreakdown;
            renderHud();
        }
    }

    function startStreamSubscription(convoId) {
        if (!convoId || typeof window.InSituConnectClient !== "function") return;
        try {
            if (!activeStreamClient) {
                activeStreamClient = new window.InSituConnectClient();
            }
            activeStreamClient.streamConversation(convoId, handleStreamStateChange).catch(err => {
                if (err && (err.name === "AbortError" || String(err).includes("abort") || String(err).includes("Switching conversation"))) return;
                console.warn("[agyis:hud] ConnectRPC stream error:", err);
            });
        } catch (err) {
            console.warn("[agyis:hud] Failed to start ConnectRPC stream subscription:", err);
        }
    }

    window.__agyis_hud_render = renderHud;
    window.__agyis_hud_sync = syncToLatestState;
    window.__agyis_hud_start_stream = startStreamSubscription;
    let _loadConvoSeq = 0;

    window.__agyis_hud_load_convo = async function(convoId) {
        if (!convoId) return null;
        const seq = ++_loadConvoSeq;
        startStreamSubscription(convoId);
        if (window.loadConversationViaRpc) {
            const data = await window.loadConversationViaRpc(convoId);
            if (seq !== _loadConvoSeq) {
                // Superseded by a newer conversation load request; discard stale response
                return null;
            }
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
    const activeMountConvo = initialFocusedConvo || (initialData && initialData.conversation_id);
    if (activeMountConvo) {
        if (initialFocusedConvo && initialFocusedConvo !== (initialData && initialData.conversation_id) && typeof window.__agyis_hud_load_convo === "function") {
            window.__agyis_hud_load_convo(initialFocusedConvo);
        } else {
            startStreamSubscription(activeMountConvo);
        }
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
        if (activeStreamClient && activeStreamClient.activeAbortController) {
            try { activeStreamClient.activeAbortController.abort("HUD cleanup"); } catch (_) {}
        }
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
            const searchInput = currentHud.querySelector("#agyis-search-input");
            const isSearchFocused = (document.activeElement && document.activeElement.id === "agyis-search-input") || (e.target && e.target.id === "agyis-search-input");
            const state = window.__agyis_hud_state;
            const hasText = (searchInput && searchInput.value && searchInput.value.length > 0) || (state && state.filterQuery && state.filterQuery.length > 0);

            if (isSearchFocused && hasText) {
                e.preventDefault();
                e.stopPropagation();
                if (searchInput) searchInput.value = "";
                if (state) {
                    state.filterQuery = "";
                    state.tablePage = 0;
                    state.currentMatchIdx = 0;
                }
                if (typeof renderHud === "function") renderHud();
                const freshInput = currentHud.querySelector("#agyis-search-input");
                if (freshInput && typeof freshInput.focus === "function") freshInput.focus();
                return;
            }
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
