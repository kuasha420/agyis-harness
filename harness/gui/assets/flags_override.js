(() => {
    try {
        const key = "__FLAG_KEY__";
        let current = {};
        const raw = localStorage.getItem(key);
        if (raw) {
            try {
                const parsed = JSON.parse(raw);
                if (parsed && typeof parsed === "object" && !Array.isArray(parsed)) {
                    current = parsed;
                }
            } catch (parseErr) {
                console.warn("[agyis:flags] Ignoring corrupt localStorage flag payload:", parseErr);
            }
        }
        Object.assign(current, __FLAGS_JSON__);
        const encoded = JSON.stringify(current);
        localStorage.setItem(key, encoded);
        if (typeof StorageEvent === "function") {
            window.dispatchEvent(new StorageEvent("storage", { key: key, newValue: encoded }));
        }
    } catch (err) {
        console.warn("[agyis:flags] Failed to update localStorage flags:", err);
    }
})();
