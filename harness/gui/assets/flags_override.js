(() => {
    try {
        const key = "__FLAG_KEY__";
        let current = {};
        try {
            const raw = localStorage.getItem(key);
            if (raw) current = JSON.parse(raw);
            Object.assign(current, __FLAGS_JSON__);
            localStorage.setItem(key, JSON.stringify(current));
            window.dispatchEvent(new StorageEvent("storage", { key: key, newValue: JSON.stringify(current) }));
        } catch (_) {}
    } catch (_) {}
})();
