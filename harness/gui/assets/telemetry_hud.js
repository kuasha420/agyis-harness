(() => {
    try {
        const data = __HUD_DATA__;
        if (data.remove) {
            const el = document.getElementById("agyis-telemetry-hud");
            if (el) {
                el.remove();
                return { success: true, removed: true, injected: false };
            }
            return { success: true, removed: false, injected: false };
        }
        const esc = (v) => String(v ?? "")
            .replace(/&/g, "&amp;")
            .replace(/</g, "&lt;")
            .replace(/>/g, "&gt;")
            .replace(/"/g, "&quot;")
            .replace(/'/g, "&#39;");
        const existingHud = document.getElementById("agyis-telemetry-hud");
        if (existingHud) {
            existingHud.remove();
        }
        if (!document.body) {
            return { success: false, error: "document.body is not ready" };
        }
        const hud = document.createElement("div");
        hud.id = "agyis-telemetry-hud";
        hud.style.position = "fixed";
        hud.style.top = "44px";
        hud.style.right = "16px";
        hud.style.zIndex = "999999";
        hud.style.fontFamily = '"JetBrains Mono", "Instrument Sans", ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace';
        hud.style.fontSize = "11px";
        hud.style.fontWeight = "600";
        hud.style.borderRadius = "8px";
        hud.style.padding = "6px 12px";
        hud.style.boxShadow = "0 4px 12px rgba(4, 8, 18, 0.55)";
        hud.style.display = "flex";
        hud.style.alignItems = "center";
        hud.style.gap = "8px";
        hud.style.pointerEvents = "auto";
        hud.style.cursor = "default";
        hud.style.backdropFilter = "blur(8px)";
        hud.style.transition = "border-color 0.2s ease, background-color 0.2s ease";
        hud.style.border = "1px solid " + data.border_color;
        hud.style.backgroundColor = data.bg_color;
        hud.style.color = "#F4F6FA";
        const shieldSvg = '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 128 128" width="14" height="14" aria-hidden="true" style="display:inline-block;vertical-align:middle;flex-shrink:0;"><defs><linearGradient id="agyis-telemetry-edge" x1="16" y1="12" x2="112" y2="116" gradientUnits="userSpaceOnUse"><stop offset="0%" stop-color="#1B4DFF"/><stop offset="52%" stop-color="#5C8AFF"/><stop offset="100%" stop-color="#26D0CE"/></linearGradient><linearGradient id="agyis-telemetry-body" x1="64" y1="12" x2="64" y2="116" gradientUnits="userSpaceOnUse"><stop offset="0%" stop-color="#101C33"/><stop offset="100%" stop-color="#080E1A"/></linearGradient></defs><path d="M40 12 L88 12 L112 32 L112 74 L64 116 L16 74 L16 32 Z" fill="url(#agyis-telemetry-body)" stroke="url(#agyis-telemetry-edge)" stroke-width="5"/><polygon points="31,83 52,31 61,31 42,83" fill="#F4F6FA"/><polygon points="97,83 76,31 67,31 86,83" fill="#F4F6FA"/><polygon points="64,47 64,63 53,63" fill="#A8C5FF"/><polygon points="64,47 75,63 64,63" fill="#5C8AFF"/><polygon points="53,63 64,63 64,79" fill="#1B4DFF"/><polygon points="64,63 75,63 64,79" fill="#26D0CE"/></svg>';
        hud.innerHTML = `
            ${shieldSvg}
            <span style="display:inline-block; width:8px; height:8px; border-radius:50%; background-color:${esc(data.border_color)};"></span>
            <span>${esc(data.tokens)} tok</span>
            <span style="color:#9AA8BE;">|</span>
            <span style="color:${esc(data.text_color)};">${esc(data.burn_rate)}</span>
            <span style="color:#9AA8BE;">|</span>
            <span style="color:#9AA8BE;">${esc(data.horizon)}</span>
            <span style="background-color:${esc(data.badge_bg)}; color:${esc(data.text_color)}; padding:2px 6px; border-radius:4px; font-size:10px; text-transform:uppercase;">${esc(data.tier)}</span>
        `;
        document.body.appendChild(hud);
        return {
            success: true,
            removed: false,
            injected: true,
            tokens: data.tokens,
            burn_rate: data.burn_rate,
            tier: data.tier
        };
    } catch (err) {
        return {
            success: false,
            error: (err && err.toString) ? err.toString() : String(err)
        };
    }
})();
