// SPDX-License-Identifier: Apache-2.0
// Copyright (c) 2026 Arafat Zahan (@kuasha420)
// Corporate Stewardship & Infrastructure: Purrfect Software Limited (PSL)
// Governed by: ICARO-42/b Ordinance (Company-Supported Personal IP Framework)

/**
 * playback_boot.js — Standalone HTTP :40624 Trajectory Playback Shell Controller.
 * Mounts modular Orbital Aegis HUD components directly over /api/conversations & /api/trajectory.
 */

(function(global) {
    "use strict";

    const HUD_ID = "agyis-trajectory-hud";
    const _u = () => global.__agyis_utils || {};
    const escapeHtml = (val) => (_u().escapeHtml ? _u().escapeHtml(val) : String(val ?? "").replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;").replace(/'/g, "&#39;"));

    let conversationList = [];
    let liveIntervalId = null;
    let loadSeq = 0;

    function setPlaybackStatus(text, isError = false) {
        const el = document.getElementById("agyis-playback-status");
        if (!el) return;
        el.textContent = text;
        el.className = isError ? "agyis-playback-status is-error" : "agyis-playback-status";
    }

    function syncLatest(state) {
        if (typeof _u().syncToLatestState === "function") {
            _u().syncToLatestState(state);
            return;
        }
        const steps = (state.currentData && state.currentData.steps) || [];
        const checkpoints = (state.currentData && state.currentData.checkpoints) || [];
        state.activeCheckpointIndex = checkpoints.length > 0 ? checkpoints.length - 1 : -1;
        state.selectedIndex = Math.max(0, steps.length - 1);
        state.tablePage = Math.max(0, Math.ceil(steps.length / 50) - 1);
        state.timelinePage = Math.max(0, Math.ceil(steps.length / 200) - 1);
    }

    function selectStep(sIdx, opts = {}) {
        const hudEl = document.getElementById(HUD_ID);
        const state = global.__agyis_hud_state;
        if (!state || !state.currentData) return;
        const curSteps = state.currentData.steps || [];
        const curCheckpoints = state.currentData.checkpoints || [];
        state.hoveredItemKey = null;
        if (typeof _u().resolveCheckpointForStep === "function") {
            const nextCpIdx = _u().resolveCheckpointForStep(curCheckpoints, sIdx, state.activeCheckpointIndex, Boolean(opts && opts.preserveCheckpoint));
            if (nextCpIdx >= 0) state.activeCheckpointIndex = nextCpIdx;
        } else {
            for (let i = curCheckpoints.length - 1; i >= 0; i--) {
                const cp = curCheckpoints[i];
                if (sIdx >= cp.start_index && sIdx <= cp.end_index) {
                    state.activeCheckpointIndex = cp.checkpoint_index !== undefined ? cp.checkpoint_index : i;
                    break;
                }
            }
        }
        state.selectedIndex = sIdx;
        const filtered = typeof _u().computeFilteredIndices === "function"
            ? _u().computeFilteredIndices(curSteps, state.filterQuery)
            : curSteps.map((_, i) => i);
        if (typeof _u().syncPaginationForStep === "function") {
            _u().syncPaginationForStep(state, curSteps, filtered, sIdx);
        } else {
            const matchPos = filtered.indexOf(sIdx);
            state.tablePage = Math.floor((matchPos >= 0 ? matchPos : Math.max(0, sIdx || 0)) / (state.pageSize || 50));
            state.timelinePage = Math.floor(Math.max(0, sIdx || 0) / 200);
        }
        renderPlaybackHud();
        if (typeof _u().scrollSelectedStepIntoView === "function") {
            _u().scrollSelectedStepIntoView(hudEl, state, sIdx);
        }
    }

    function renderPlaybackHud() {
        const hudEl = document.getElementById(HUD_ID);
        const state = global.__agyis_hud_state;
        if (!hudEl || !state) return;
        const cur = state.currentData;
        if (!cur) {
            hudEl.innerHTML = `<div class="agyis-hud-box" style="align-items:center;justify-content:center;color:#9AA8BE;font-size:13px;">Select or record a conversation to inspect its trajectory.</div>`;
            return;
        }
        const curSteps = cur.steps || [];
        const currentStep = curSteps[state.selectedIndex] || null;
        const filteredIndices = typeof _u().computeFilteredIndices === "function"
            ? _u().computeFilteredIndices(curSteps, state.filterQuery)
            : curSteps.map((_, i) => i);
        state.searchMatchIndices = filteredIndices;
        const curCheckpoints = (cur.checkpoints && cur.checkpoints.length > 0) ? cur.checkpoints : [{ checkpoint_index: 0, start_index: 0, end_index: Math.max(0, curSteps.length - 1), step_count: curSteps.length, has_checkpoint: false, summary: "Initial Trajectory" }];
        if (state.activeCheckpointIndex === undefined || state.activeCheckpointIndex < 0 || state.activeCheckpointIndex >= curCheckpoints.length) {
            state.activeCheckpointIndex = typeof _u().resolveCheckpointForStep === "function"
                ? _u().resolveCheckpointForStep(curCheckpoints, state.selectedIndex, -1, false)
                : (curCheckpoints.length - 1);
        }
        const activeCheckpoint = curCheckpoints[state.activeCheckpointIndex] || curCheckpoints[curCheckpoints.length - 1];
        const checkpointSteps = curSteps.slice(activeCheckpoint.start_index, activeCheckpoint.end_index + 1);
        const winW = global.innerWidth || 1200;
        const containerWidth = state.layoutOrientation === "vertical" ? Math.round(winW * 0.9) : Math.max(420, Math.round(winW * 0.48));
        const headerHtml = global.renderHudHeader ? global.renderHudHeader(state, cur, conversationList) : "";
        const inspHtml = global.buildInspectorHtml ? global.buildInspectorHtml(currentStep, state, cur) : "";
        const deckHtml = global.renderMainDeck ? global.renderMainDeck(cur, state, curSteps, curCheckpoints, activeCheckpoint, checkpointSteps, filteredIndices, inspHtml, currentStep, containerWidth) : "";
        const snap = typeof _u().captureHudUiSnapshot === "function" ? _u().captureHudUiSnapshot(hudEl, state) : null;
        hudEl.innerHTML = `<div class="agyis-hud-box">${headerHtml}${deckHtml}</div>`;
        if (global.bindHudHeaderEvents) global.bindHudHeaderEvents(hudEl, state, cur, renderPlaybackHud, selectStep);
        if (global.bindContextBarEvents) global.bindContextBarEvents(hudEl, state, cur, curCheckpoints, renderPlaybackHud, selectStep);
        if (global.bindTimelineEvents) global.bindTimelineEvents(hudEl, state, renderPlaybackHud, selectStep);
        if (global.bindInspectorEvents) global.bindInspectorEvents(hudEl, state, currentStep, selectStep);
        if (global.initDeckSplitterAndNav) global.initDeckSplitterAndNav(hudEl, state, curSteps, filteredIndices, renderPlaybackHud, selectStep);
        if (typeof _u().restoreHudUiSnapshot === "function") _u().restoreHudUiSnapshot(hudEl, state, snap);
    }

    async function loadPlaybackConversation(convoId, opts = false) {
        if (!convoId) return null;
        const preserveCursor = typeof opts === "boolean" ? opts : Boolean(opts && opts.preserveCursor);
        const seq = ++loadSeq;
        setPlaybackStatus(`Loading ${convoId.slice(0, 8)}...`);
        const res = await fetch(`/api/trajectory?id=${encodeURIComponent(convoId)}`).catch(() => null);
        if (seq !== loadSeq) return null;
        if (!res || !res.ok) {
            setPlaybackStatus(`Failed to load ${convoId.slice(0, 8)} (${res ? res.status : "network"})`, true);
            return null;
        }
        const data = await res.json().catch(() => null);
        if (!data || seq !== loadSeq) return null;
        const state = global.__agyis_hud_state;
        const prevConvoId = state.convoId;
        const prevTotal = (state.currentData && Array.isArray(state.currentData.steps)) ? state.currentData.steps.length : 0;
        const prevIdx = state.selectedIndex;
        const prevCpIdx = state.activeCheckpointIndex;
        const wasAtEnd = prevTotal === 0 || prevIdx >= prevTotal - 1;

        state.rootData = data;
        state.currentData = data;
        state.convoId = convoId;
        state.sessionModel = data.model || "";
        state.subagentsDropdownOpen = false;
        if (preserveCursor && prevConvoId === convoId && prevTotal > 0 && !wasAtEnd && Array.isArray(data.steps) && data.steps.length > 0) {
            state.selectedIndex = Math.min(prevIdx, data.steps.length - 1);
            const cps = data.checkpoints || [];
            if (cps.length > 0 && typeof _u().resolveCheckpointForStep === "function") {
                state.activeCheckpointIndex = _u().resolveCheckpointForStep(cps, state.selectedIndex, prevCpIdx, true);
            }
            const filtered = typeof _u().computeFilteredIndices === "function"
                ? _u().computeFilteredIndices(data.steps, state.filterQuery)
                : data.steps.map((_, i) => i);
            if (typeof _u().syncPaginationForStep === "function") {
                _u().syncPaginationForStep(state, data.steps, filtered, state.selectedIndex);
            }
        } else {
            syncLatest(state);
        }
        const shellSelect = document.getElementById("agyis-playback-convo");
        if (shellSelect && shellSelect.value !== convoId) shellSelect.value = convoId;
        setPlaybackStatus(`${(data.steps || []).length} steps • ${(data.total_tokens || 0).toLocaleString()} tok`);
        renderPlaybackHud();
        return data;
    }

    async function bootPlaybackShell() {
        global.__agyis_hud_state = {
            rootData: null, currentData: null, sessionModel: "", convoId: "",
            selectedIndex: 0, activeCheckpointIndex: -1, tablePage: 0, timelinePage: 0, pageSize: 50,
            filterQuery: "", searchMatchIndices: [], currentMatchIdx: -1, searchDebounceTimer: null,
            activeTab: "step", mainDeckTab: "context", timelineMode: "steps",
            layoutOrientation: "horizontal", inspectorWidth: null, inspectorHeight: null,
            isMaximized: true, subagentsDropdownOpen: false, hoveredItemKey: null,
        };
        global.__agyis_hud_render = renderPlaybackHud;
        global.__agyis_hud_sync = syncLatest;
        global.__agyis_hud_load_convo = loadPlaybackConversation;
        if (typeof _u().bindHudKeyboardNav === "function") {
            _u().bindHudKeyboardNav({
                hudId: HUD_ID,
                allowCloseHud: false,
                renderHud: renderPlaybackHud,
                selectStep,
            });
        }
        const res = await fetch("/api/conversations?limit=50").catch(() => null);
        const json = (res && res.ok) ? await res.json().catch(() => null) : null;
        conversationList = (json && Array.isArray(json.conversations)) ? json.conversations : [];
        const shellSelect = document.getElementById("agyis-playback-convo");
        if (shellSelect) {
            shellSelect.innerHTML = conversationList.map(c => `<option value="${escapeHtml(c.id)}">${escapeHtml(c.summary || c.id)}</option>`).join("");
            shellSelect.addEventListener("change", (ev) => { if (ev.target.value) loadPlaybackConversation(ev.target.value); });
        }
        document.getElementById("agyis-playback-reload")?.addEventListener("click", () => {
            if (global.__agyis_hud_state.convoId) loadPlaybackConversation(global.__agyis_hud_state.convoId, true);
        });
        document.getElementById("agyis-playback-live")?.addEventListener("change", (ev) => {
            if (liveIntervalId) { clearInterval(liveIntervalId); liveIntervalId = null; }
            if (ev.target.checked) {
                liveIntervalId = setInterval(() => {
                    if (global.__agyis_hud_state.convoId) loadPlaybackConversation(global.__agyis_hud_state.convoId, true);
                }, 3000);
            }
        });
        const params = new URLSearchParams(global.location ? global.location.search : "");
        const initialId = params.get("id") || params.get("conversation_id") || (conversationList[0] && conversationList[0].id);
        if (initialId) await loadPlaybackConversation(initialId);
        else { setPlaybackStatus("No conversations found"); renderPlaybackHud(); }
    }

    if (typeof document !== "undefined") {
        if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", bootPlaybackShell, { once: true });
        else bootPlaybackShell();
    }
})(typeof window !== "undefined" ? window : globalThis);
