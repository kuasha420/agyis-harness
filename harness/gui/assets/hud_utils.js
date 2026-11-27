// SPDX-License-Identifier: Apache-2.0
// Copyright (c) 2026 Arafat Zahan (@kuasha420)
// Corporate Stewardship & Infrastructure: Purrfect Software Limited (PSL)
// Governed by: ICARO-42/b Ordinance (Company-Supported Personal IP Framework)

/**
 * hud_utils.js — Shared HUD Selection, Pagination, Snapshot & Keyboard Helpers.
 *
 * Shared SSOT consumed by both Electron HUD (hud.js) and :40624 playback shell (playback_boot.js),
 * enforcing zero <=4-char global exports for Antigravity 2.35.2 Closure compatibility.
 */

(function(global) {
    "use strict";

    const escapeHtml = (val) => String(val ?? "")
        .replace(/&/g, "&amp;")
        .replace(/</g, "&lt;")
        .replace(/>/g, "&gt;")
        .replace(/"/g, "&quot;")
        .replace(/'/g, "&#39;");

    const formatBytes = (bytes) => {
        if (!bytes || bytes <= 0) return "0 B";
        const k = 1024;
        const sizes = ["B", "KB", "MB", "GB"];
        const idx = Math.min(sizes.length - 1, Math.floor(Math.log(bytes) / Math.log(k)));
        return `${parseFloat((bytes / Math.pow(k, idx)).toFixed(1))} ${sizes[idx]}`;
    };

    const cssEscape = (val) => {
        const s = String(val ?? "");
        if (typeof CSS !== "undefined" && typeof CSS.escape === "function") {
            return CSS.escape(s);
        }
        return s.replace(/([^\w-])/g, "\\$1");
    };

    const bindItemKeyHover = (hudEl, state, selector) => {
        if (!hudEl || !hudEl.querySelectorAll) return;
        hudEl.querySelectorAll(selector).forEach(el => {
            el.addEventListener("mouseenter", () => {
                const itemKey = el.getAttribute("data-item-key");
                if (!itemKey) return;
                state.hoveredItemKey = itemKey;
                hudEl.querySelectorAll(`[data-item-key="${cssEscape(itemKey)}"]`).forEach(mEl => {
                    mEl.classList.add("context-cell-hovered");
                });
            });
            el.addEventListener("mouseleave", () => {
                const itemKey = el.getAttribute("data-item-key");
                if (!itemKey) return;
                state.hoveredItemKey = null;
                hudEl.querySelectorAll(`[data-item-key="${cssEscape(itemKey)}"]`).forEach(mEl => {
                    mEl.classList.remove("context-cell-hovered");
                });
            });
        });
    };

    const inferModelContextWindow = (modelName) => (
        global.__agyis_utils && typeof global.__agyis_utils._rpcInferCtx === "function"
            ? global.__agyis_utils._rpcInferCtx(modelName)
            : 256000
    );

    /**
     * Resolves canonical checkpoint window index for a step using reverse scan (findLast)
     * plus optional active-window preservation when navigating inside the currently displayed bar.
     */
    function resolveCheckpointForStep(checkpoints, stepIdx, currentActiveIdx, preserveIfWithinActive = false) {
        if (!Array.isArray(checkpoints) || checkpoints.length === 0) return -1;
        if (preserveIfWithinActive && Number.isInteger(currentActiveIdx) && currentActiveIdx >= 0 && currentActiveIdx < checkpoints.length) {
            const directWin = checkpoints[currentActiveIdx];
            const activeWin = (directWin && (directWin.checkpoint_index === undefined || directWin.checkpoint_index === currentActiveIdx))
                ? directWin
                : (checkpoints.find(c => c && c.checkpoint_index === currentActiveIdx) || directWin);
            if (activeWin && stepIdx >= activeWin.start_index && stepIdx <= activeWin.end_index) {
                return activeWin.checkpoint_index !== undefined ? activeWin.checkpoint_index : currentActiveIdx;
            }
        }
        for (let i = checkpoints.length - 1; i >= 0; i--) {
            const cp = checkpoints[i];
            if (cp && stepIdx >= cp.start_index && stepIdx <= cp.end_index) {
                return cp.checkpoint_index !== undefined ? cp.checkpoint_index : i;
            }
        }
        const firstStart = checkpoints[0] ? checkpoints[0].start_index : 0;
        if (stepIdx < firstStart) {
            return checkpoints[0] && checkpoints[0].checkpoint_index !== undefined ? checkpoints[0].checkpoint_index : 0;
        }
        const lastCp = checkpoints[checkpoints.length - 1];
        return lastCp && lastCp.checkpoint_index !== undefined ? lastCp.checkpoint_index : (checkpoints.length - 1);
    }

    function computeFilteredIndices(steps, filterQuery) {
        const list = Array.isArray(steps) ? steps : [];
        const q = String(filterQuery || "").trim().toLowerCase();
        const filtered = [];
        for (let i = 0; i < list.length; i++) {
            if (!q) {
                filtered.push(i);
                continue;
            }
            const s = list[i] || {};
            const toolText = (s.tool_calls || []).map(t => `${t.name || ""} ${JSON.stringify(t.args || {})}`).join(" ");
            const hay = `${s.type || ""} ${s.content || ""} ${s.thinking || ""} ${s.compaction_summary || ""} ${s.sessionSummary || ""} ${s.summary || ""} ${s.command || ""} ${s.filePath || ""} ${toolText}`.toLowerCase();
            if (hay.includes(q)) filtered.push(i);
        }
        return filtered;
    }

    function syncPaginationForStep(state, steps, filteredIndices, stepIdx) {
        if (!state) return;
        const pageSize = state.pageSize || 50;
        const fList = Array.isArray(filteredIndices) ? filteredIndices : [];
        const matchPos = fList.indexOf(stepIdx);
        const pos = matchPos >= 0 ? matchPos : Math.max(0, stepIdx || 0);
        state.tablePage = Math.floor(pos / pageSize);
        state.timelinePage = Math.floor(Math.max(0, stepIdx || 0) / 200);
    }

    function syncToLatestState(state) {
        if (!state || !state.currentData) return;
        const steps = state.currentData.steps || [];
        const checkpoints = state.currentData.checkpoints || [];
        state.activeCheckpointIndex = checkpoints.length > 0 ? checkpoints.length - 1 : -1;
        state.selectedIndex = Math.max(0, steps.length - 1);
        const totalSteps = steps.length;
        const pageSize = 50;
        const totalPages = Math.max(1, Math.ceil(totalSteps / pageSize));
        state.tablePage = totalPages - 1;
        state.timelinePage = Math.max(0, Math.ceil(totalSteps / 200) - 1);
    }

    function captureHudUiSnapshot(hudEl, state) {
        const snap = {
            activeElId: null,
            activeSelStart: null,
            activeSelEnd: null,
            activeValue: null,
            gridScrollTop: 0,
            gridScrollLeft: 0,
            timelineScrollTop: 0,
            timelineScrollLeft: 0,
            inspectorScrollTop: 0,
            inspectorScrollLeft: 0,
            thinkingStates: [],
            prevConvoId: state ? state._lastRenderedConvoId : undefined,
            prevSelectedIndex: state ? state._lastRenderedSelectedIndex : undefined,
            prevActiveTab: state ? state._lastRenderedActiveTab : undefined,
            prevTablePage: state ? state._lastRenderedTablePage : undefined,
            prevTimelinePage: state ? state._lastRenderedTimelinePage : undefined,
        };
        if (!hudEl || typeof hudEl.querySelector !== "function") return snap;
        try {
            const doc = typeof document !== "undefined" ? document : null;
            const activeEl = doc ? doc.activeElement : null;
            if (activeEl && ((hudEl.contains && hudEl.contains(activeEl)) || activeEl.id === "agyis-search-input") && activeEl.id) {
                snap.activeElId = activeEl.id;
                if (typeof activeEl.selectionStart === "number") {
                    snap.activeSelStart = activeEl.selectionStart;
                    snap.activeSelEnd = activeEl.selectionEnd;
                }
                if (typeof activeEl.value === "string") snap.activeValue = activeEl.value;
            }
            const gridBody = hudEl.querySelector(".agyis-step-grid-body");
            if (gridBody) {
                snap.gridScrollTop = gridBody.scrollTop || 0;
                snap.gridScrollLeft = gridBody.scrollLeft || 0;
            }
            const tlWrap = hudEl.querySelector(".agyis-timeline-scroll-wrap");
            if (tlWrap) {
                snap.timelineScrollTop = tlWrap.scrollTop || 0;
                snap.timelineScrollLeft = tlWrap.scrollLeft || 0;
            }
            const inspBody = hudEl.querySelector("#agyis-inspector-body");
            if (inspBody) {
                snap.inspectorScrollTop = inspBody.scrollTop || 0;
                snap.inspectorScrollLeft = inspBody.scrollLeft || 0;
                if (typeof inspBody.querySelectorAll === "function") {
                    snap.thinkingStates = Array.from(inspBody.querySelectorAll("details.agyis-thinking-block")).map(det => (
                        typeof det.open === "boolean" ? det.open : (det.getAttribute && det.getAttribute("open") !== null)
                    ));
                }
            }
        } catch (_) {}
        return snap;
    }

    function restoreHudUiSnapshot(hudEl, state, snap) {
        if (!hudEl || !state) return;
        if (snap) {
            try {
                const sameTablePage = snap.prevTablePage === undefined || snap.prevTablePage === state.tablePage;
                const sameTimelinePage = snap.prevTimelinePage === undefined || snap.prevTimelinePage === state.timelinePage;
                const sameInspector = snap.prevConvoId === state.convoId && snap.prevSelectedIndex === state.selectedIndex && snap.prevActiveTab === state.activeTab;

                const gridBody = hudEl.querySelector(".agyis-step-grid-body");
                if (gridBody && sameTablePage) {
                    gridBody.scrollTop = snap.gridScrollTop || 0;
                    gridBody.scrollLeft = snap.gridScrollLeft || 0;
                }
                const tlWrap = hudEl.querySelector(".agyis-timeline-scroll-wrap");
                if (tlWrap && sameTimelinePage) {
                    tlWrap.scrollTop = snap.timelineScrollTop || 0;
                    tlWrap.scrollLeft = snap.timelineScrollLeft || 0;
                }
                const inspBody = hudEl.querySelector("#agyis-inspector-body");
                if (inspBody && sameInspector) {
                    inspBody.scrollTop = snap.inspectorScrollTop || 0;
                    inspBody.scrollLeft = snap.inspectorScrollLeft || 0;
                    if (snap.thinkingStates.length > 0 && typeof inspBody.querySelectorAll === "function") {
                        inspBody.querySelectorAll("details.agyis-thinking-block").forEach((det, idx) => {
                            if (idx >= snap.thinkingStates.length) return;
                            const isOpen = Boolean(snap.thinkingStates[idx]);
                            det.open = isOpen;
                            if (isOpen && typeof det.setAttribute === "function") det.setAttribute("open", "");
                            else if (!isOpen && typeof det.removeAttribute === "function") det.removeAttribute("open");
                        });
                    }
                }
                if (snap.activeElId) {
                    const restoredEl = hudEl.querySelector("#" + cssEscape(snap.activeElId));
                    if (restoredEl) {
                        if (snap.activeValue !== null && restoredEl.value !== snap.activeValue) {
                            restoredEl.value = snap.activeValue;
                        }
                        if (typeof restoredEl.focus === "function") restoredEl.focus();
                        if (typeof snap.activeSelStart === "number" && typeof restoredEl.setSelectionRange === "function") {
                            const maxLen = typeof restoredEl.value === "string" ? restoredEl.value.length : snap.activeSelEnd;
                            restoredEl.setSelectionRange(Math.min(snap.activeSelStart, maxLen), Math.min(snap.activeSelEnd, maxLen));
                        }
                    }
                }
            } catch (_) {}
        }
        state._lastRenderedConvoId = state.convoId;
        state._lastRenderedSelectedIndex = state.selectedIndex;
        state._lastRenderedActiveTab = state.activeTab;
        state._lastRenderedTablePage = state.tablePage;
        state._lastRenderedTimelinePage = state.timelinePage;
    }

    function scrollSelectedStepIntoView(hudEl, state, sIdx) {
        if (!hudEl || !hudEl.querySelector || !state) return;
        const selector = state.mainDeckTab === "timeline"
            ? `.agyis-timeline-step-row[data-step-index="${sIdx}"]`
            : `.agyis-step-grid-item[data-index="${sIdx}"]`;
        const rowEl = hudEl.querySelector(selector);
        if (rowEl && typeof rowEl.scrollIntoView === "function") {
            rowEl.scrollIntoView({ block: "nearest", inline: "nearest" });
        }
    }

    function bindHudKeyboardNav(opts = {}) {
        const hudId = opts.hudId || "agyis-trajectory-hud";
        if (global.__agyis_hud_active_listener && typeof global.removeEventListener === "function") {
            global.removeEventListener("keydown", global.__agyis_hud_active_listener, true);
        }
        global.__agyis_hud_active_listener = (e) => {
            const currentHud = typeof document !== "undefined" ? document.getElementById(hudId) : null;
            const isF12 = e.key === "F12";
            const isCtrlShiftT = (e.ctrlKey || e.metaKey) && e.shiftKey && (e.key === "T" || e.key === "t");
            if ((isF12 || isCtrlShiftT) && typeof opts.onToggleHotkey === "function") {
                if (opts.onToggleHotkey(e, currentHud) === true) return;
            }
            if (!currentHud || currentHud.style.display === "none") return;

            const state = global.__agyis_hud_state;
            if (e.key === "Escape") {
                const searchInput = currentHud.querySelector ? currentHud.querySelector("#agyis-search-input") : null;
                const doc = typeof document !== "undefined" ? document : null;
                const isSearchFocused = (doc && doc.activeElement && doc.activeElement.id === "agyis-search-input") || (e.target && e.target.id === "agyis-search-input");
                const hasText = (searchInput && searchInput.value && searchInput.value.length > 0) || (state && state.filterQuery && state.filterQuery.length > 0);
                if (isSearchFocused && hasText) {
                    if (typeof e.preventDefault === "function") e.preventDefault();
                    if (typeof e.stopPropagation === "function") e.stopPropagation();
                    if (searchInput) searchInput.value = "";
                    if (state) {
                        if (state.searchDebounceTimer) { clearTimeout(state.searchDebounceTimer); state.searchDebounceTimer = null; }
                        state.filterQuery = "";
                        state.currentMatchIdx = -1;
                        state.tablePage = Math.floor(Math.max(0, state.selectedIndex || 0) / (state.pageSize || 50));
                    }
                    if (typeof opts.renderHud === "function") opts.renderHud();
                    const freshInput = currentHud.querySelector ? currentHud.querySelector("#agyis-search-input") : null;
                    if (freshInput && typeof freshInput.focus === "function") freshInput.focus();
                    return;
                }
                const subMenu = currentHud.querySelector ? currentHud.querySelector("#agyis-subagents-menu") : null;
                if ((state && state.subagentsDropdownOpen) || (subMenu && subMenu.style.display === "block")) {
                    if (typeof e.preventDefault === "function") e.preventDefault();
                    if (typeof e.stopPropagation === "function") e.stopPropagation();
                    if (state) state.subagentsDropdownOpen = false;
                    if (subMenu) subMenu.style.display = "none";
                    const arrow = currentHud.querySelector ? currentHud.querySelector("#agyis-subagents-dropdown-toggle .agyis-subagents-arrow, #agyis-subagents-dropdown-toggle span:last-child") : null;
                    if (arrow) arrow.style.transform = "rotate(0deg)";
                    return;
                }
                if (opts.allowCloseHud) currentHud.style.display = "none";
                return;
            }

            if (e.ctrlKey || e.metaKey || e.altKey) return;
            const tgt = e.target;
            if (tgt && (tgt.tagName === "INPUT" || tgt.tagName === "TEXTAREA" || tgt.tagName === "SELECT" || tgt.isContentEditable)) return;
            if (!state || typeof opts.selectStep !== "function") return;
            const curSteps = (state.currentData && state.currentData.steps) ? state.currentData.steps : [];
            const hasFilter = Boolean((state.filterQuery || "").trim());
            const navIndices = hasFilter ? (state.searchMatchIndices || []) : curSteps.map((_, i) => i);
            if (navIndices.length === 0) return;

            const isNext = e.key === "ArrowDown" || e.key === "j" || e.key === "ArrowRight";
            const isPrev = e.key === "ArrowUp" || e.key === "k" || e.key === "ArrowLeft";
            if (!isNext && !isPrev) return;
            if (typeof e.preventDefault === "function") e.preventDefault();
            if (typeof e.stopPropagation === "function") e.stopPropagation();
            const pos = navIndices.indexOf(state.selectedIndex);
            if (isNext) {
                if (pos === -1) {
                    const nextHit = navIndices.find(idx => idx > state.selectedIndex);
                    opts.selectStep(nextHit !== undefined ? nextHit : navIndices[0]);
                } else if (pos < navIndices.length - 1) {
                    opts.selectStep(navIndices[pos + 1]);
                }
            } else {
                if (pos === -1) {
                    const prevHits = navIndices.filter(idx => idx < state.selectedIndex);
                    opts.selectStep(prevHits.length > 0 ? prevHits[prevHits.length - 1] : navIndices[navIndices.length - 1]);
                } else if (pos > 0) {
                    opts.selectStep(navIndices[pos - 1]);
                }
            }
        };
        if (typeof global.addEventListener === "function") {
            global.addEventListener("keydown", global.__agyis_hud_active_listener, true);
        }
    }

    global.__agyis_utils = Object.assign(global.__agyis_utils || {}, {
        escapeHtml, formatBytes, cssEscape, bindItemKeyHover, inferModelContextWindow,
        resolveCheckpointForStep, computeFilteredIndices, syncPaginationForStep, syncToLatestState,
        captureHudUiSnapshot, restoreHudUiSnapshot, scrollSelectedStepIntoView, bindHudKeyboardNav,
    });
    global.syncToLatestState = syncToLatestState;
})(typeof window !== "undefined" ? window : globalThis);
