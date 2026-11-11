(() => {
    /* __HOTKEY_SCRIPT__ */
    let lastUrl = window.location.href;
    const observer = new MutationObserver(() => {
        if (window.location.href !== lastUrl) {
            lastUrl = window.location.href;
            if (!window.__agyis_hud_hotkey_registered) {
                /* __HOTKEY_SCRIPT__ */
            }
        }
    });
    if (document.body) {
        observer.observe(document.body, { childList: true, subtree: true });
    } else {
        document.addEventListener("DOMContentLoaded", () => {
            if (document.body) {
                observer.observe(document.body, { childList: true, subtree: true });
            }
        });
    }
})();
