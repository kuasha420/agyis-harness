(() => {
    /* __HOTKEY_SCRIPT__ */
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
    const ensureHotkeyOnRoute = () => {
        if (!window.__agyis_hud_hotkey_registered && typeof window.initAgyisHotkey === "function") {
            window.initAgyisHotkey();
        }
    };
    if (window.__agyis_persistent_route_listener) {
        window.removeEventListener("popstate", window.__agyis_persistent_route_listener);
        window.removeEventListener("agyis:routechange", window.__agyis_persistent_route_listener);
    }
    window.__agyis_persistent_route_listener = ensureHotkeyOnRoute;
    window.addEventListener("popstate", ensureHotkeyOnRoute);
    window.addEventListener("agyis:routechange", ensureHotkeyOnRoute);
})();
