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

    const _u = () => window.__agyis_utils || {};
    const cssEscape = (val) => (typeof _u().cssEscape === "function"
        ? _u().cssEscape(val)
        : (typeof CSS !== "undefined" && typeof CSS.escape === "function" ? CSS.escape(String(val ?? "")) : String(val ?? "").replace(/([^\w-])/g, "\\$1")));

    const syncToLatestState = (state) => {
        if (typeof _u().syncToLatestState === "function") return _u().syncToLatestState(state);
        if (!state || !state.currentData) return;
        const steps = state.currentData.steps || [], checkpoints = state.currentData.checkpoints || [];
        state.activeCheckpointIndex = checkpoints.length > 0 ? checkpoints.length - 1 : -1;
        state.selectedIndex = Math.max(0, steps.length - 1);
        state.tablePage = Math.max(0, Math.ceil(steps.length / (state.pageSize || 50)) - 1);
        state.timelinePage = Math.max(0, Math.ceil(steps.length / 200) - 1);
    };

    function extractHudFocusedConvoId() {
        const searchParams = (typeof window !== "undefined" && window.location && window.location.search) ? new URLSearchParams(window.location.search) : null;
        const isConvoSlug = (id) => typeof id === "string" && /^[0-9a-zA-Z_-]+$/.test(id) && !/^pane[-_]/i.test(id) && !/^(?:bgtask|side_question)__/i.test(id);
        const isUuidPattern = (id) => isConvoSlug(id) && (/^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i.test(id) || id.length >= 20);

        // Priority 1: Check active subagent tab query parameter (?tab=subagent_convo__<uuid>)
        // and split-pane focused query parameter (?focused=<uuid>); ignore bgtask__/side_question__ tabs.
        if (searchParams) {
            const tabParam = searchParams.get('tab');
            if (tabParam && tabParam.startsWith('subagent_convo__')) {
                const cand = tabParam.slice('subagent_convo__'.length);
                if (isConvoSlug(cand)) return cand;
            }
            const focusedParam = searchParams.get('focused');
            if (isConvoSlug(focusedParam)) return focusedParam;
        }

        // Priority 2: Delegate to global detector if available
        if (typeof window.detectActiveConversationContext === "function") {
            const detected = window.detectActiveConversationContext();
            if (detected) return detected;
        }

        const pathMatch = (window.location && window.location.pathname) ? window.location.pathname.match(/\/c\/([^/?#]+)/) : null;
        const routeParts = pathMatch && pathMatch[1] ? pathMatch[1].split("+").filter(Boolean) : [];
        const routeCascadeId = routeParts[0] || null;

        const focusedPane = typeof document !== "undefined" ? document.querySelector('div[data-pane-id]:not([data-pane-unfocused])') : null;
        const rawPaneId = focusedPane ? focusedPane.getAttribute('data-pane-id') : null;
        let focusedPaneId = isUuidPattern(rawPaneId) ? rawPaneId : null;
        if (!focusedPaneId && focusedPane && rawPaneId && /^pane[-_](\d+)$/i.test(rawPaneId)) {
            const attrConvo = focusedPane.getAttribute('data-conversation-id') || focusedPane.getAttribute('data-cascade-id');
            if (isConvoSlug(attrConvo)) {
                focusedPaneId = attrConvo;
            } else {
                const paneIdx = parseInt(rawPaneId.match(/^pane[-_](\d+)$/i)[1], 10) - 1;
                if (paneIdx >= 0 && paneIdx < routeParts.length) focusedPaneId = routeParts[paneIdx];
            }
        }

        const searchCascadeId = searchParams ? searchParams.get('cascadeId') : null;

        return focusedPaneId || routeCascadeId || searchCascadeId || null;
    }
    window.__agyis_extract_convo_id = extractHudFocusedConvoId;

    let existingHud = document.getElementById(HUD_ID);
    let toggleOpenedFromHidden = false;
    if (existingHud && isToggle) {
        const isHidden = existingHud.style.display === "none";
        existingHud.style.display = isHidden ? "flex" : "none";
        if (!isHidden) {
            return { success: true, open: false, toggled: true };
        }
        // Opening via newly-injected --toggle script: purge stale DOM/styles and re-mount fresh HUD (PSL-INV-007)
        toggleOpenedFromHidden = true;
    }

    const effectiveShouldOpen = toggleOpenedFromHidden ? true : shouldOpen;

    // Stale DOM Replacement: Purge existing HUD and styles on re-injection (PSL-INV-007)
    if (typeof window.__agyis_hud_route_cleanup === "function") {
        try { window.__agyis_hud_route_cleanup(); } catch (_) {}
    }
    if (typeof window.__agyis_splitter_cleanup === "function") {
        try { window.__agyis_splitter_cleanup(); } catch (_) {}
    }
    if (existingHud) existingHud.remove();
    const existingStyles = document.getElementById(STYLES_ID);
    if (existingStyles) existingStyles.remove();

    const styleEl = document.createElement("style");
    styleEl.id = STYLES_ID;
    styleEl.textContent = `/* __HUD_STYLES__ */`;
    document.head.appendChild(styleEl);

    hud = document.createElement("div");
    hud.id = HUD_ID;
    hud.style.display = effectiveShouldOpen ? "flex" : "none";

    const steps = (initialData && initialData.steps) || [];
    const checkpoints = (initialData && initialData.checkpoints) || [];

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
        activeCheckpointIndex: checkpoints.length > 0 ? checkpoints.length - 1 : -1,
        tablePage: Math.max(0, Math.ceil(steps.length / 50) - 1),
        timelinePage: Math.max(0, Math.ceil(steps.length / 200) - 1),
        pageSize: 50,
        filterQuery: "",
        searchMatchIndices: [],
        currentMatchIdx: -1,
        searchDebounceTimer: null,
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

    /* __HUD_THEME__ */
    /* __HUD_UTILS__ */
    /* __HUD_HEADER__ */
    /* __HUD_CONTEXT_BAR__ */
    /* __HUD_TIMELINE__ */
    /* __HUD_INSPECTOR__ */
    /* __HUD_DECK__ */
    /* __HUD_STREAM__ */
    /* __HUD_RPC__ */
    /* __HOTKEY__ */

    function _fallbackFilter(curSteps, filterQuery) {
        const q = (filterQuery || "").trim().toLowerCase();
        if (!q) return curSteps.map((_, i) => i);
        return curSteps.reduce((acc, s, i) => {
            const hay = `${s.type || ""} ${s.content || ""} ${s.thinking || ""} ${s.compaction_summary || ""} ${s.sessionSummary || ""} ${s.summary || ""} ${s.command || ""} ${s.filePath || ""} ${(s.tool_calls || []).map(t => (t.name || "") + " " + JSON.stringify(t.args || {})).join(" ")}`.toLowerCase();
            if (hay.includes(q)) acc.push(i);
            return acc;
        }, []);
    }

    function selectStep(sIdx, opts = {}) {
        const state = window.__agyis_hud_state, cur = state.currentData;
        const curSteps = (cur && cur.steps) || [], curCheckpoints = (cur && cur.checkpoints) || [], u = _u();
        state.hoveredItemKey = null;
        const filtered = typeof u.computeFilteredIndices === "function" ? u.computeFilteredIndices(curSteps, state.filterQuery) : _fallbackFilter(curSteps, state.filterQuery);
        if (typeof u.resolveCheckpointForStep === "function") {
            const nextIdx = u.resolveCheckpointForStep(curCheckpoints, sIdx, state.activeCheckpointIndex, Boolean(opts && opts.preserveCheckpoint));
            if (nextIdx >= 0) state.activeCheckpointIndex = nextIdx;
        }
        state.selectedIndex = sIdx;
        if (typeof u.syncPaginationForStep === "function") u.syncPaginationForStep(state, curSteps, filtered, sIdx);
        else { state.tablePage = Math.floor(Math.max(0, sIdx || 0) / (state.pageSize || 50)); state.timelinePage = Math.floor(Math.max(0, sIdx || 0) / 200); }
        renderHud();
        if (typeof u.scrollSelectedStepIntoView === "function") u.scrollSelectedStepIntoView(hud, state, sIdx);
    }

    function renderHud() {
        const state = window.__agyis_hud_state;
        const cur = state.currentData;
        const curSteps = (cur && cur.steps) || [];
        const currentStep = curSteps[state.selectedIndex] || null;
        const u = _u();

        const filteredIndices = typeof u.computeFilteredIndices === "function"
            ? u.computeFilteredIndices(curSteps, state.filterQuery)
            : _fallbackFilter(curSteps, state.filterQuery);
        state.searchMatchIndices = filteredIndices;

        const curCheckpoints = (cur && cur.checkpoints && cur.checkpoints.length > 0) ? cur.checkpoints : [{
            checkpoint_index: 0,
            start_index: 0,
            end_index: Math.max(0, curSteps.length - 1),
            step_count: curSteps.length,
            has_checkpoint: false,
            summary: "Initial Trajectory",
        }];
        if (state.activeCheckpointIndex === undefined || state.activeCheckpointIndex < 0 || state.activeCheckpointIndex >= curCheckpoints.length) {
            if (typeof u.resolveCheckpointForStep === "function") {
                state.activeCheckpointIndex = u.resolveCheckpointForStep(curCheckpoints, state.selectedIndex, -1, false);
            } else {
                state.activeCheckpointIndex = curCheckpoints.length - 1;
            }
        }
        const activeCheckpoint = curCheckpoints[state.activeCheckpointIndex] || curCheckpoints[curCheckpoints.length - 1];
        const checkpointSteps = curSteps.slice(activeCheckpoint.start_index, activeCheckpoint.end_index + 1);

        const gridPaneEl = hud && hud.querySelector ? hud.querySelector(".agyis-grid-pane") : null;
        const measuredGridW = gridPaneEl && gridPaneEl.clientWidth ? gridPaneEl.clientWidth : 0;
        const winW = (typeof window !== "undefined" && window.innerWidth) ? window.innerWidth : 1200;
        const fallbackW = (state.layoutOrientation === "vertical" || state.layoutOrientation === "stack")
            ? Math.round(winW * 0.90)
            : Math.max(420, Math.round(winW * 0.48));
        const containerWidth = measuredGridW > 100 ? measuredGridW : fallbackW;

        const headerHtml = window.renderHudHeader ? window.renderHudHeader(state, cur, conversationList) : "";
        const inspectorContentHtml = window.buildInspectorHtml ? window.buildInspectorHtml(currentStep, state, cur) : "";
        const deckHtml = window.renderMainDeck ? window.renderMainDeck(
            cur, state, curSteps, curCheckpoints, activeCheckpoint, checkpointSteps, filteredIndices, inspectorContentHtml, currentStep, containerWidth
        ) : "";

        if (!hud) hud = document.getElementById(HUD_ID);
        if (!hud) return;

        const snap = typeof u.captureHudUiSnapshot === "function" ? u.captureHudUiSnapshot(hud, state) : null;
        let fallbackActive = null;
        if (!snap) {
            try {
                const act = document.activeElement;
                if (act && (hud.contains(act) || act.id === "agyis-search-input") && act.id) {
                    fallbackActive = { id: act.id, s: act.selectionStart, e: act.selectionEnd, v: act.value };
                }
            } catch (_) {}
        }

        hud.innerHTML = `
            <div class="agyis-hud-box ${state.isMaximized ? "maximized" : ""}">
                ${headerHtml}
                ${deckHtml}
            </div>
        `;

        if (window.bindHudHeaderEvents) window.bindHudHeaderEvents(hud, state, cur, renderHud, selectStep);
        if (window.bindContextBarEvents) window.bindContextBarEvents(hud, state, cur, curCheckpoints, renderHud, selectStep);
        if (window.bindTimelineEvents) window.bindTimelineEvents(hud, state, renderHud, selectStep);
        if (window.bindInspectorEvents) window.bindInspectorEvents(hud, state, currentStep, selectStep);
        if (window.initDeckSplitterAndNav) window.initDeckSplitterAndNav(hud, state, curSteps, filteredIndices, renderHud, selectStep);

        if (window.__agyis_splitter_cleanup) {
            try { window.__agyis_splitter_cleanup(); } catch (_) {}
        }
        if (snap && typeof u.restoreHudUiSnapshot === "function") {
            u.restoreHudUiSnapshot(hud, state, snap);
        } else if (fallbackActive) {
            try {
                const el = hud.querySelector("#" + cssEscape(fallbackActive.id));
                if (el) {
                    if (typeof fallbackActive.v === "string" && el.value !== fallbackActive.v) el.value = fallbackActive.v;
                    if (typeof el.focus === "function") el.focus();
                    if (typeof fallbackActive.s === "number" && typeof el.setSelectionRange === "function") el.setSelectionRange(fallbackActive.s, fallbackActive.e);
                }
            } catch (_) {}
        }

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
                (streamState.executorMetadatasInSlice || []).filter(Boolean),
                null
            );
        }

        if (updatedData) {
            const prevSelected = state.selectedIndex;
            const prevCpIdx = state.activeCheckpointIndex;
            const prevTotal = state.currentData && state.currentData.steps ? state.currentData.steps.length : 0;
            const wasAtEnd = prevTotal === 0 || prevSelected >= prevTotal - 1;

            state.rootData = updatedData;
            state.currentData = updatedData;
            state.convoId = convoId;
            if (updatedData.model) state.sessionModel = updatedData.model;

            if (wasAtEnd) {
                syncToLatestState(state);
            } else {
                const steps = updatedData.steps || [];
                const cps = updatedData.checkpoints || [];
                const u = _u();
                state.selectedIndex = Math.min(prevSelected, Math.max(0, steps.length - 1));
                if (cps.length > 0 && typeof u.resolveCheckpointForStep === "function") {
                    state.activeCheckpointIndex = u.resolveCheckpointForStep(cps, state.selectedIndex, prevCpIdx, true);
                }
                const filtered = typeof u.computeFilteredIndices === "function"
                    ? u.computeFilteredIndices(steps, state.filterQuery)
                    : _fallbackFilter(steps, state.filterQuery);
                if (typeof u.syncPaginationForStep === "function") {
                    u.syncPaginationForStep(state, steps, filtered, state.selectedIndex);
                } else {
                    state.tablePage = Math.floor(state.selectedIndex / 50);
                    state.timelinePage = Math.floor(state.selectedIndex / 200);
                }
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

    function ensureHudDomAttached(openFlag) {
        if (!document.getElementById(STYLES_ID) && document.head) {
            document.head.appendChild(styleEl);
        }
        let curHud = document.getElementById(HUD_ID);
        if (!curHud) {
            curHud = hud;
            if (curHud && document.body) {
                document.body.appendChild(curHud);
            }
        }
        if (curHud && typeof openFlag === "boolean") {
            curHud.style.display = openFlag ? "flex" : "none";
        }
        return curHud;
    }

    window.__agyis_hud_mount = function(opts = {}) {
        const openFlag = opts.shouldOpen !== undefined ? Boolean(opts.shouldOpen) : true;
        const targetConvoId = opts.conversationId || extractHudFocusedConvoId();
        ensureHudDomAttached(openFlag);
        const state = window.__agyis_hud_state;
        if (targetConvoId && state && targetConvoId !== state.convoId && typeof window.__agyis_hud_load_convo === "function") {
            window.__agyis_hud_load_convo(targetConvoId);
        } else {
            renderHud();
        }
        return true;
    };

    window.__agyis_hud_render = renderHud;
    window.__agyis_hud_sync = syncToLatestState;
    window.__agyis_hud_start_stream = startStreamSubscription;
    let _loadConvoSeq = 0;

    window.__agyis_hud_load_convo = async function(convoId, opts = {}) {
        if (!convoId) return null;
        ensureHudDomAttached();
        const preserveCursor = typeof opts === "boolean" ? opts : Boolean(opts && opts.preserveCursor);
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
                    const prevConvoId = state.convoId;
                    const prevTotal = (state.currentData && Array.isArray(state.currentData.steps)) ? state.currentData.steps.length : 0;
                    const prevIdx = state.selectedIndex;
                    const prevCpIdx = state.activeCheckpointIndex;
                    const wasAtEnd = prevTotal === 0 || prevIdx >= prevTotal - 1;

                    state.rootData = data;
                    state.currentData = data;
                    state.convoId = convoId;
                    if (data.model) state.sessionModel = data.model;
                    if (preserveCursor && prevConvoId === convoId && prevTotal > 0 && !wasAtEnd && Array.isArray(data.steps) && data.steps.length > 0) {
                        const u = _u();
                        state.selectedIndex = Math.min(prevIdx, data.steps.length - 1);
                        const cps = data.checkpoints || [];
                        if (cps.length > 0 && typeof u.resolveCheckpointForStep === "function") {
                            state.activeCheckpointIndex = u.resolveCheckpointForStep(cps, state.selectedIndex, prevCpIdx, true);
                        }
                        const filtered = typeof u.computeFilteredIndices === "function"
                            ? u.computeFilteredIndices(data.steps, state.filterQuery)
                            : _fallbackFilter(data.steps, state.filterQuery);
                        if (typeof u.syncPaginationForStep === "function") {
                            u.syncPaginationForStep(state, data.steps, filtered, state.selectedIndex);
                        } else {
                            state.tablePage = Math.floor(state.selectedIndex / 50);
                            state.timelinePage = Math.floor(state.selectedIndex / 200);
                        }
                    } else {
                        syncToLatestState(state);
                    }
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
    if (toggleOpenedFromHidden) {
        const state = window.__agyis_hud_state;
        syncToLatestState(state);
        if (typeof renderHud === "function") renderHud();
        const selEl = state && hud.querySelector ? hud.querySelector(`.agyis-step-grid-item[data-index="${state.selectedIndex}"]`) : null;
        if (selEl) selEl.scrollIntoView({ block: "nearest" });
    }

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

    // Global Hotkey & Keyboard Navigation (shared bindHudKeyboardNav in hud_utils.js)
    window.__agyis_hud_hotkey_registered = true;
    window.__agyis_hud_last_toggle = window.__agyis_hud_last_toggle || 0;
    const handleToggleHotkey = (e, currentHud) => {
        if (typeof window.__agyis_hotkey_listener === "function") return true;
        e.preventDefault();
        e.stopImmediatePropagation();
        const now = Date.now();
        if (now - (window.__agyis_hud_last_toggle || 0) < 250) return true;
        window.__agyis_hud_last_toggle = now;
        if (typeof window.toggleAgyisHud === "function") {
            window.toggleAgyisHud();
        } else if (currentHud) {
            const isHidden = currentHud.style.display === "none";
            currentHud.style.display = isHidden ? "flex" : "none";
            if (isHidden) {
                const focusedConvoId = extractHudFocusedConvoId();
                const state = window.__agyis_hud_state;
                if (focusedConvoId && state && focusedConvoId !== state.convoId && typeof window.__agyis_hud_load_convo === "function") {
                    window.__agyis_hud_load_convo(focusedConvoId);
                } else if (state) {
                    syncToLatestState(state);
                    renderHud();
                }
            }
        }
        return true;
    };
    if (typeof _u().bindHudKeyboardNav === "function") {
        _u().bindHudKeyboardNav({
            hudId: HUD_ID,
            allowCloseHud: true,
            onToggleHotkey: handleToggleHotkey,
            renderHud,
            selectStep,
        });
    } else {
        if (window.__agyis_hud_active_listener) window.removeEventListener("keydown", window.__agyis_hud_active_listener, true);
        window.__agyis_hud_active_listener = (e) => {
            const currentHud = document.getElementById(HUD_ID);
            if (e.key === "F12" || ((e.ctrlKey || e.metaKey) && e.shiftKey && (e.key === "T" || e.key === "t"))) {
                handleToggleHotkey(e, currentHud);
                return;
            }
            if (e.key === "Escape" && currentHud && currentHud.style.display !== "none") {
                const searchInput = currentHud.querySelector("#agyis-search-input");
                const state = window.__agyis_hud_state;
                const isSearchFocused = (document.activeElement && document.activeElement.id === "agyis-search-input") || (e.target && e.target.id === "agyis-search-input");
                const hasText = (searchInput && searchInput.value && searchInput.value.length > 0) || (state && state.filterQuery && state.filterQuery.length > 0);
                if (isSearchFocused && hasText) {
                    e.preventDefault(); e.stopPropagation();
                    if (searchInput) searchInput.value = "";
                    if (state) { state.filterQuery = ""; state.currentMatchIdx = -1; state.tablePage = Math.floor(Math.max(0, state.selectedIndex || 0) / 50); }
                    renderHud();
                    const freshInput = currentHud.querySelector("#agyis-search-input");
                    if (freshInput && typeof freshInput.focus === "function") freshInput.focus();
                    return;
                }
                currentHud.style.display = "none";
            }
        };
        window.addEventListener("keydown", window.__agyis_hud_active_listener, true);
    }
    return { success: true, open: Boolean(effectiveShouldOpen), toggled: Boolean(isToggle) };
})();
