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
        let hud = document.getElementById("agyis-telemetry-hud");
        if (!hud) {
            hud = document.createElement("div");
            hud.id = "agyis-telemetry-hud";
            hud.style.position = "fixed";
            hud.style.top = "12px";
            hud.style.right = "16px";
            hud.style.zIndex = "999999";
            hud.style.fontFamily = "-apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, monospace";
            hud.style.fontSize = "11px";
            hud.style.fontWeight = "600";
            hud.style.borderRadius = "8px";
            hud.style.padding = "6px 12px";
            hud.style.boxShadow = "0 4px 12px rgba(0, 0, 0, 0.4)";
            hud.style.display = "flex";
            hud.style.alignItems = "center";
            hud.style.gap = "8px";
            hud.style.pointerEvents = "auto";
            hud.style.cursor = "default";
            hud.style.backdropFilter = "blur(8px)";
            hud.style.transition = "all 0.3s ease";
            document.body.appendChild(hud);
        }
        hud.style.border = "1px solid " + data.border_color;
        hud.style.backgroundColor = data.bg_color;
        hud.style.color = "#f1f5f9";
        hud.innerHTML = `
            <span style="display:inline-block; width:8px; height:8px; border-radius:50%; background-color:${esc(data.border_color)};"></span>
            <span>${esc(data.tokens)} tok</span>
            <span style="color:#94a3b8;">|</span>
            <span style="color:${esc(data.text_color)};">${esc(data.burn_rate)}</span>
            <span style="color:#94a3b8;">|</span>
            <span style="color:#cbd5e1;">${esc(data.horizon)}</span>
            <span style="background-color:${esc(data.badge_bg)}; color:${esc(data.text_color)}; padding:2px 6px; border-radius:4px; font-size:10px; text-transform:uppercase;">${esc(data.tier)}</span>
        `;
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
