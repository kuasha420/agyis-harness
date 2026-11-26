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
    const escapeHtml = (val) => String(val ?? "").replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;").replace(/'/g, "&#39;");
    const formatBytes = (bytes) => {
        if (!bytes || bytes <= 0) return "0 B";
        const sizes = ["B", "KB", "MB", "GB"];
        const idx = Math.min(sizes.length - 1, Math.floor(Math.log(bytes) / Math.log(1024)));
        return `${parseFloat((bytes / Math.pow(1024, idx)).toFixed(1))} ${sizes[idx]}`;
    };
    const cssEscape = (val) => (typeof CSS !== "undefined" && typeof CSS.escape === "function" ? CSS.escape(String(val ?? "")) : String(val ?? "").replace(/([^\w-])/g, "\\$1"));
    const bindItemKeyHover = (hudEl, state, selector) => {
        if (!hudEl || !hudEl.querySelectorAll) return;
        hudEl.querySelectorAll(selector).forEach(el => {
            el.addEventListener("mouseenter", () => {
                const itemKey = el.getAttribute("data-item-key");
                if (!itemKey) return;
                state.hoveredItemKey = itemKey;
                hudEl.querySelectorAll(`[data-item-key="${cssEscape(itemKey)}"]`).forEach(mEl => mEl.classList.add("context-cell-hovered"));
            });
            el.addEventListener("mouseleave", () => {
                const itemKey = el.getAttribute("data-item-key");
                if (!itemKey) return;
                state.hoveredItemKey = null;
                hudEl.querySelectorAll(`[data-item-key="${cssEscape(itemKey)}"]`).forEach(mEl => mEl.classList.remove("context-cell-hovered"));
            });
        });
    };
    const inferModelContextWindow = (modelName) => (global.__agyis_utils && typeof global.__agyis_utils._rpcInferCtx === "function" ? global.__agyis_utils._rpcInferCtx(modelName) : 256000);

    global.__agyis_utils = Object.assign(global.__agyis_utils || {}, { escapeHtml, formatBytes, cssEscape, bindItemKeyHover, inferModelContextWindow });

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
        const steps = (state.currentData && state.currentData.steps) || [];
        const epochs = (state.currentData && state.currentData.epochs) || [];
        state.activeEpochIndex = epochs.length > 0 ? epochs.length - 1 : -1;
        state.selectedIndex = Math.max(0, steps.length - 1);
        state.tablePage = Math.max(0, Math.ceil(steps.length / 50) - 1);
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
        const q = (state.filterQuery || "").trim().toLowerCase();
        const filteredIndices = [];
        for (let i = 0; i < curSteps.length; i++) {
            const st = curSteps[i];
            if (!q || `${st.type || ""} ${st.content || ""} ${st.thinking || ""}`.toLowerCase().includes(q)) filteredIndices.push(i);
        }
        state.searchMatchIndices = filteredIndices;
        const curEpochs = (cur.epochs && cur.epochs.length > 0) ? cur.epochs : [{ epoch_index: 0, start_index: 0, end_index: Math.max(0, curSteps.length - 1), step_count: curSteps.length, has_checkpoint: false, summary: "Initial Trajectory" }];
        if (state.activeEpochIndex < 0 || state.activeEpochIndex >= curEpochs.length) state.activeEpochIndex = curEpochs.length - 1;
        const activeEpoch = curEpochs[state.activeEpochIndex] || curEpochs[curEpochs.length - 1];
        const epochSteps = curSteps.slice(activeEpoch.start_index, activeEpoch.end_index + 1);
        const winW = global.innerWidth || 1200;
        const containerWidth = state.layoutOrientation === "vertical" ? Math.round(winW * 0.9) : Math.max(420, Math.round(winW * 0.48));
        const headerHtml = global.renderHudHeader ? global.renderHudHeader(state, cur, conversationList) : "";
        const inspHtml = global.buildInspectorHtml ? global.buildInspectorHtml(currentStep, state, cur) : "";
        const deckHtml = global.renderMainDeck ? global.renderMainDeck(cur, state, curSteps, curEpochs, activeEpoch, epochSteps, filteredIndices, inspHtml, currentStep, containerWidth) : "";
        hudEl.innerHTML = `<div class="agyis-hud-box">${headerHtml}${deckHtml}</div>`;
        const selectStep = (sIdx) => {
            const foundEp = curEpochs.find(ep => sIdx >= ep.start_index && sIdx <= ep.end_index);
            if (foundEp) state.activeEpochIndex = foundEp.epoch_index;
            state.selectedIndex = sIdx;
            renderPlaybackHud();
        };
        if (global.bindHudHeaderEvents) global.bindHudHeaderEvents(hudEl, state, cur, renderPlaybackHud, selectStep);
        if (global.bindContextBarEvents) global.bindContextBarEvents(hudEl, state, cur, curEpochs, renderPlaybackHud, selectStep);
        if (global.bindTimelineEvents) global.bindTimelineEvents(hudEl, state, renderPlaybackHud, selectStep);
        if (global.bindInspectorEvents) global.bindInspectorEvents(hudEl, state, currentStep, selectStep);
        if (global.initDeckSplitterAndNav) global.initDeckSplitterAndNav(hudEl, state, curSteps, filteredIndices, renderPlaybackHud, selectStep);
    }

    async function loadPlaybackConversation(convoId, preserveCursor = false) {
        if (!convoId) return null;
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
        const prevIdx = state.selectedIndex;
        state.rootData = data;
        state.currentData = data;
        state.convoId = convoId;
        state.sessionModel = data.model || "";
        state.subagentsDropdownOpen = false;
        if (preserveCursor && Array.isArray(data.steps) && data.steps.length > 0) {
            state.selectedIndex = Math.min(prevIdx, data.steps.length - 1);
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
            selectedIndex: 0, activeEpochIndex: -1, tablePage: 0, pageSize: 50,
            filterQuery: "", searchMatchIndices: [], currentMatchIdx: -1,
            activeTab: "step", mainDeckTab: "context", timelineMode: "steps",
            layoutOrientation: "horizontal", inspectorWidth: null, inspectorHeight: null,
            isMaximized: true, subagentsDropdownOpen: false, hoveredItemKey: null,
        };
        global.__agyis_hud_render = renderPlaybackHud;
        global.__agyis_hud_load_convo = loadPlaybackConversation;
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
