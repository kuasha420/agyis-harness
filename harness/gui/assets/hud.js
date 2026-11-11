(() => {
    const HUD_ID = "agyis-trajectory-hud";
    const STYLES_ID = "agyis-trajectory-hud-styles";
    const __PAYLOAD__ = null;
    const initialData = __PAYLOAD__.initialData;
    const conversationList = __PAYLOAD__.conversationList;
    const shouldOpen = __PAYLOAD__.shouldOpen;
    const isToggle = __PAYLOAD__.isToggle;
    let hud = document.getElementById(HUD_ID);

    function syncToLatestState(state) {
        if (!state || !state.currentData) return;
        const steps = state.currentData.steps || [];
        const epochs = state.currentData.epochs || [];

        // 1. Show latest epoch
        state.activeEpochIndex = epochs.length > 0 ? epochs.length - 1 : -1;

        // 2. Select latest step
        state.selectedIndex = Math.max(0, steps.length - 1);

        // 3. Show latest 50 steps on steps list (last table page)
        const totalSteps = steps.length;
        const pageSize = 50;
        const totalPages = Math.max(1, Math.ceil(totalSteps / pageSize));
        state.tablePage = totalPages - 1;
    }

    function extractHudFocusedConvoId() {
        const match = (window.location && window.location.pathname) ? window.location.pathname.match(/\/c\/([a-zA-Z0-9_-]+)/) : null;
        return match ? match[1] : null;
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

    const steps = initialData.steps || [];
    const epochs = initialData.epochs || [];
    window.__agyis_hud_state = {
        rootData: initialData,
        currentData: initialData,
        sessionModel: (initialData && initialData.model) || "",
        convoId: initialData.conversation_id,
        selectedIndex: Math.max(0, steps.length - 1),
        activeEpochIndex: epochs.length > 0 ? epochs.length - 1 : -1,
        tablePage: Math.max(0, Math.ceil(steps.length / 50) - 1),
        pageSize: 50,
        filterQuery: "",
        searchMatchIndices: [],
        currentMatchIdx: -1,
        activeTab: "step",
        mainDeckTab: "context",
        layoutOrientation: "horizontal",
        isMaximized: false,
        subagentsDropdownOpen: false,
        hoveredContextSegment: null,
    };
    syncToLatestState(window.__agyis_hud_state);

    /* __HUD_RPC__ */
    /* __HUD_VIEWS__ */
    /* __HUD_INSPECTOR__ */

    function renderHud() {
        const state = window.__agyis_hud_state;
        const cur = state.currentData;
        const curSteps = cur.steps || [];
        const currentStep = curSteps[state.selectedIndex] || null;

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

        const curEpochs = (cur.epochs && cur.epochs.length > 0) ? cur.epochs : [{
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

        const inspectorContentHtml = buildInspectorHtml(currentStep, state);
        const { html, totalPages, pageSize } = buildMainDeckViewHtml(
            cur, state, curSteps, curEpochs, activeEpoch, epochSteps, filteredIndices, inspectorContentHtml, currentStep, conversationList,
        );

        if (!hud) hud = document.getElementById(HUD_ID);
        if (!hud) return;
        hud.innerHTML = html;
        bindHudEventListeners(hud, state, cur, curSteps, curEpochs, filteredIndices, totalPages, pageSize, currentStep);
    }

    window.__agyis_hud_render = renderHud;
    window.__agyis_hud_sync = syncToLatestState;
    renderHud();
    document.body.appendChild(hud);
    const initialSelEl = document.querySelector(`.agyis-step-grid-item[data-index="${window.__agyis_hud_state.selectedIndex}"]`);
    if (initialSelEl) initialSelEl.scrollIntoView({ block: "nearest" });

    // Initial check + SPA route sensitivity watcher (PSL-INV-010)
    const initialFocusedConvo = extractHudFocusedConvoId();
    if (initialFocusedConvo && initialFocusedConvo !== initialData.conversation_id && typeof window.__agyis_hud_load_convo === "function") {
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
    window.__agyis_hud_doc_click = () => {
        if (window.__agyis_hud_state && window.__agyis_hud_state.subagentsDropdownOpen) {
            window.__agyis_hud_state.subagentsDropdownOpen = false;
            const menu = hud.querySelector("#agyis-subagents-menu");
            if (menu) menu.style.display = "none";
        }
    };
    document.addEventListener("click", window.__agyis_hud_doc_click);

    // Hotkey listener with stale listener cleanup
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
                        const selEl = document.querySelector(`.agyis-step-grid-item[data-index="${state.selectedIndex}"]`);
                        if (selEl) selEl.scrollIntoView({ block: "nearest" });
                    }
                }
            }
        }
        if (e.key === "Escape" && currentHud && currentHud.style.display !== "none") {
            currentHud.style.display = "none";
        }
        if (currentHud && currentHud.style.display !== "none" && e.target && e.target.tagName !== "INPUT" && e.target.tagName !== "TEXTAREA") {
            const state = window.__agyis_hud_state;
            if (!state) return;
            const curSteps = (state.currentData && state.currentData.steps) ? state.currentData.steps : [];
            if (e.key === "ArrowLeft" && state.selectedIndex > 0) {
                state.selectedIndex -= 1;
                const foundEp = ((state.currentData && state.currentData.epochs) || []).find(ep => state.selectedIndex >= ep.start_index && state.selectedIndex <= ep.end_index);
                if (foundEp) state.activeEpochIndex = foundEp.epoch_index;
                renderHud();
            }
            if (e.key === "ArrowRight" && state.selectedIndex < curSteps.length - 1) {
                state.selectedIndex += 1;
                const foundEp = ((state.currentData && state.currentData.epochs) || []).find(ep => state.selectedIndex >= ep.start_index && state.selectedIndex <= ep.end_index);
                if (foundEp) state.activeEpochIndex = foundEp.epoch_index;
                renderHud();
            }
        }
    };
    window.addEventListener("keydown", window.__agyis_hud_active_listener, true);

    return {
        success: true,
        open: shouldOpen,
        steps: initialData.step_count || 0,
        convo_id: initialData.conversation_id,
    };
})();
