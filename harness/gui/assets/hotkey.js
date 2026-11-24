// SPDX-License-Identifier: Apache-2.0
// Copyright (c) 2026 Arafat Zahan (@kuasha420)
// Corporate Stewardship & Infrastructure: Purrfect Software Limited (PSL)
// Governed by: ICARO-42/b Ordinance (Company-Supported Personal IP Framework)

/**
 * hotkey.js — Dynamic In-Situ Traversal & Hotkey Controller.
 * 
 * Provides:
 * 1. Multi-tier active conversation and subagent context extraction:
 *    - Priority 1: Subagent query parameter (?tab=subagent_convo__<uuid>)
 *    - Priority 2: Electron DOM focused pane (div[data-pane-id]:not([data-pane-unfocused]))
 *    - Priority 3: SPA pathname route (/c/:id)
 *    - Priority 4: URL search parameter (?cascadeId=...)
 * 2. Hotkey binding (F12 / Ctrl+Shift+T):
 *    - Toggles Trajectory Debug View visibility.
 *    - On toggle open: compares active conversation against current HUD context.
 *    - If conversation changed or code updated: purges stale DOM and styles (#agyis-trajectory-hud,
 *      #agyis-trajectory-hud-styles) and hydrates focused conversation with 0ms delay (PSL-INV-010).
 * 3. SPA Route & Focus Observers:
 *    - Listens to 'popstate' and 'agyis:routechange' events.
 *    - Observes focus transitions across multi-pane tiled subagent views.
 */

(function(global) {
    "use strict";

    const HUD_ID = "agyis-trajectory-hud";
    const STYLES_ID = "agyis-trajectory-hud-styles";
    const HOTKEY_DEBOUNCE_MS = 250;

    /**
     * Multi-tier active conversation and subagent context extractor.
     * Evaluates DOM pane focus, SPA route pathname, and URL search parameters.
     * @returns {string|null} Extracted active cascade/conversation UUID or null.
     */
    function detectActiveConversationContext() {
        try {
            // Priority 1: Check active subagent tab query parameter (?tab=subagent_convo__<uuid>)
            // and split-pane focused query parameter (?focused=<uuid>)
            if (typeof window !== "undefined" && window.location && window.location.search) {
                const searchParams = new URLSearchParams(window.location.search);
                const tabParam = searchParams.get("tab");
                if (tabParam && tabParam.startsWith("subagent_convo__")) {
                    const subId = tabParam.slice("subagent_convo__".length);
                    if (subId && /^[a-zA-Z0-9_-]+$/.test(subId)) {
                        return subId;
                    }
                }
                const focusedParam = searchParams.get("focused");
                if (focusedParam && /^[a-zA-Z0-9_-]+$/.test(focusedParam)) {
                    return focusedParam;
                }
            }

            // Priority 2: Inspect Electron DOM focused pane (only when pane-id is a UUID, not "pane-1")
            if (typeof document !== "undefined") {
                const focusedPane = document.querySelector('div[data-pane-id]:not([data-pane-unfocused])');
                if (focusedPane) {
                    const paneId = focusedPane.getAttribute("data-pane-id");
                    if (
                        paneId
                        && !/^pane[-_]/i.test(paneId)
                        && (/^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i.test(paneId) || (paneId.length >= 20 && /^[0-9a-zA-Z_-]+$/.test(paneId)))
                    ) {
                        return paneId;
                    }
                }
            }

            // Priority 3: Match active SPA URL pathname (/c/:id or /c/:id1+:id2)
            if (typeof window !== "undefined" && window.location && window.location.pathname) {
                const pathMatch = window.location.pathname.match(/\/c\/([^/?#]+)/);
                if (pathMatch && pathMatch[1]) {
                    const firstId = pathMatch[1].split("+")[0];
                    if (firstId && /^[a-zA-Z0-9_-]+$/.test(firstId)) {
                        return firstId;
                    }
                }
            }

            // Priority 4: Fall back to URL search parameter (?cascadeId=...)
            if (typeof window !== "undefined" && window.location && window.location.search) {
                const searchParams = new URLSearchParams(window.location.search);
                const searchCascadeId = searchParams.get("cascadeId");
                if (searchCascadeId && /^[0-9a-fA-F-]+$/.test(searchCascadeId)) {
                    return searchCascadeId;
                }
            }
        } catch (err) {
            console.warn("[agyis:hotkey] Error detecting conversation context:", err);
        }

        return null;
    }

    /**
     * Purges stale singleton state, existing DOM elements, and superseded style sheets (PSL-INV-010).
     */
    function purgeStaleHudDom() {
        if (typeof document === "undefined") return;
        const existingHud = document.getElementById(HUD_ID);
        if (existingHud) {
            existingHud.remove();
        }
        const existingStyles = document.getElementById(STYLES_ID);
        if (existingStyles) {
            existingStyles.remove();
        }
    }

    /**
     * Toggles the Trajectory Debug View HUD open or closed.
     * On open, detects the focused conversation and automatically hydrates context.
     * @param {Object} [options] - Optional toggle settings
     * @returns {boolean} True if HUD is now open, false if closed.
     */
    function toggleAgyisHud(options = {}) {
        if (typeof document === "undefined") return false;
        const currentHud = document.getElementById(HUD_ID);
        const activeConvoId = detectActiveConversationContext();

        if (currentHud) {
            const isCurrentlyHidden = (currentHud.style.display === "none");

            if (isCurrentlyHidden) {
                // Opening existing HUD: check if active conversation changed
                const state = global.__agyis_hud_state;
                if (activeConvoId && state && activeConvoId !== state.convoId) {
                    // Conversation changed: purge stale DOM and reload for new conversation (PSL-INV-010)
                    purgeStaleHudDom();
                    if (typeof global.__agyis_hud_mount === "function") {
                        global.__agyis_hud_mount({ shouldOpen: true, conversationId: activeConvoId });
                    } else if (typeof global.__agyis_hud_load_convo === "function") {
                        global.__agyis_hud_load_convo(activeConvoId);
                    }
                    return true;
                }

                // Same conversation: unhide, sync/render immediately, and refresh live data
                currentHud.style.display = "flex";
                if (state && typeof global.__agyis_hud_sync === "function") {
                    global.__agyis_hud_sync(state);
                }
                if (typeof global.__agyis_hud_render === "function") {
                    global.__agyis_hud_render();
                }
                const targetId = activeConvoId || (state && state.convoId);
                if (targetId && typeof global.__agyis_hud_load_convo === "function") {
                    global.__agyis_hud_load_convo(targetId);
                }
                return true;
            } else {
                // Closing visible HUD
                currentHud.style.display = "none";
                return false;
            }
        } else {
            // HUD not yet mounted: mount fresh instance
            if (typeof global.__agyis_hud_mount === "function") {
                global.__agyis_hud_mount({ shouldOpen: true, conversationId: activeConvoId });
                return true;
            }
            return false;
        }
    }

    /**
     * Initializes the global keyboard hotkey listener and SPA route watcher.
     * Hotkeys: F12, Ctrl+Shift+T (Cmd+Shift+T on macOS), Escape (to dismiss).
     * Always cleans up prior listeners/observers so re-injection updates cleanly.
     */
    function initAgyisHotkey() {
        if (typeof window === "undefined") return;

        if (typeof global.__agyis_hotkey_cleanup === "function") {
            try {
                global.__agyis_hotkey_cleanup();
            } catch (_) {}
        }
        if (global.__agyis_hotkey_listener) {
            window.removeEventListener("keydown", global.__agyis_hotkey_listener, true);
        }
        if (global.__agyis_focus_observer) {
            try {
                global.__agyis_focus_observer.disconnect();
            } catch (_) {}
            global.__agyis_focus_observer = null;
        }

        global.__agyis_hotkey_initialized = true;
        global.__agyis_hud_hotkey_registered = true;

        let lastToggleTime = 0;

        const handleKeydown = (e) => {
            const isF12 = e.key === "F12";
            const isCtrlShiftT = (e.ctrlKey || e.metaKey) && e.shiftKey && (e.key === "T" || e.key === "t");

            if (isF12 || isCtrlShiftT) {
                e.preventDefault();
                e.stopImmediatePropagation();

                const now = Date.now();
                if (now - lastToggleTime < HOTKEY_DEBOUNCE_MS) return;
                lastToggleTime = now;

                toggleAgyisHud();
                return;
            }

            // Dismiss on Escape if HUD is open (defer to hud.js listener if mounted)
            if (e.key === "Escape") {
                if (typeof global.__agyis_hud_active_listener === "function") {
                    return;
                }
                const currentHud = document.getElementById(HUD_ID);
                if (currentHud && currentHud.style.display !== "none") {
                    const searchInput = currentHud.querySelector("#agyis-search-input");
                    const isSearchFocused = (document.activeElement && document.activeElement.id === "agyis-search-input") || (e.target && e.target.id === "agyis-search-input");
                    const hasText = (searchInput && searchInput.value && searchInput.value.length > 0) || (global.__agyis_hud_state && global.__agyis_hud_state.filterQuery && global.__agyis_hud_state.filterQuery.length > 0);
                    if (isSearchFocused && hasText) {
                        return;
                    }
                    const menu = currentHud.querySelector("#agyis-subagents-menu");
                    if (menu && menu.style.display === "block") {
                        menu.style.display = "none";
                        if (global.__agyis_hud_state) global.__agyis_hud_state.subagentsDropdownOpen = false;
                        e.stopPropagation();
                        return;
                    }
                    currentHud.style.display = "none";
                }
            }
        };

        global.__agyis_hotkey_listener = handleKeydown;
        window.addEventListener("keydown", handleKeydown, true);

        // SPA Route Sensitivity & Focus Transition Observer (PSL-INV-007)
        const onRouteOrFocusChange = () => {
            const currentHud = document.getElementById(HUD_ID);
            if (!currentHud || currentHud.style.display === "none") return;

            const activeConvoId = detectActiveConversationContext();
            const state = global.__agyis_hud_state;
            if (activeConvoId && state && activeConvoId !== state.convoId) {
                if (typeof global.__agyis_hud_load_convo === "function") {
                    global.__agyis_hud_load_convo(activeConvoId);
                }
            }
        };

        window.addEventListener("popstate", onRouteOrFocusChange);
        window.addEventListener("agyis:routechange", onRouteOrFocusChange);

        let focusDebounceTimer = null;
        let domReadyHandler = null;
        const attachFocusObserver = () => {
            if (typeof MutationObserver === "undefined" || typeof document === "undefined" || !document.body) {
                return false;
            }
            if (global.__agyis_focus_observer) {
                try { global.__agyis_focus_observer.disconnect(); } catch (_) {}
            }
            const focusObserver = new MutationObserver((mutations) => {
                let relevant = false;
                for (let i = 0; i < mutations.length; i++) {
                    const m = mutations[i];
                    if (m.type === "attributes" && (m.attributeName === "data-pane-unfocused" || m.attributeName === "data-pane-id")) {
                        relevant = true;
                        break;
                    }
                }
                if (relevant) {
                    clearTimeout(focusDebounceTimer);
                    focusDebounceTimer = setTimeout(onRouteOrFocusChange, 100);
                }
            });

            focusObserver.observe(document.body, {
                attributes: true,
                subtree: true,
                attributeFilter: ["data-pane-unfocused", "data-pane-id"],
            });

            global.__agyis_focus_observer = focusObserver;
            return true;
        };

        if (!attachFocusObserver() && typeof document !== "undefined" && typeof document.addEventListener === "function") {
            domReadyHandler = () => {
                attachFocusObserver();
            };
            document.addEventListener("DOMContentLoaded", domReadyHandler, { once: true });
        }

        global.__agyis_hotkey_cleanup = () => {
            window.removeEventListener("keydown", handleKeydown, true);
            window.removeEventListener("popstate", onRouteOrFocusChange);
            window.removeEventListener("agyis:routechange", onRouteOrFocusChange);
            if (domReadyHandler && typeof document !== "undefined" && typeof document.removeEventListener === "function") {
                document.removeEventListener("DOMContentLoaded", domReadyHandler);
            }
            if (focusDebounceTimer) {
                clearTimeout(focusDebounceTimer);
                focusDebounceTimer = null;
            }
            if (global.__agyis_focus_observer) {
                try { global.__agyis_focus_observer.disconnect(); } catch (_) {}
                global.__agyis_focus_observer = null;
            }
        };
    }

    // Export module onto window/global namespace
    global.detectActiveConversationContext = detectActiveConversationContext;
    global.purgeStaleHudDom = purgeStaleHudDom;
    global.toggleAgyisHud = toggleAgyisHud;
    global.initAgyisHotkey = initAgyisHotkey;

    // Self-initialize if in browser environment
    if (typeof window !== "undefined") {
        initAgyisHotkey();
    }

})(typeof window !== "undefined" ? window : globalThis);
