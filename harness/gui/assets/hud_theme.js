// SPDX-License-Identifier: Apache-2.0
// Copyright (c) 2026 Arafat Zahan (@kuasha420)
// Corporate Stewardship & Infrastructure: Purrfect Software Limited (PSL)
// Governed by: ICARO-42/b Ordinance (Company-Supported Personal IP Framework)

/**
 * hud_theme.js — Orbital Aegis Design Tokens, Prompt Palette, Shield Mark & Hairline SVG Icons.
 * Single Source of Truth (SSOT) for HUD theming across Electron overlay & :40624 playback shell.
 */

(function(global) {
    "use strict";

    const TOKENS = {
        bg: "#080E1A",
        surface: "#10192B",
        inset: "#0B1322",
        elevated: "#162238",
        border: "#1E2C47",
        borderStrong: "#283A5E",
        ink: "#F4F6FA",
        muted: "#9AA8BE",
        subtle: "#6E7F9B",
        cobalt: "#1B4DFF",
        optical: "#5C8AFF",
        cyan: "#26D0CE",
        pass: "#2AD089",
        warn: "#F5B74F",
        fail: "#FF6B6B",
        fontSans: '"Instrument Sans", system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif',
        fontMono: '"JetBrains Mono", ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace',
    };

    const PROMPT_PALETTE = {
        identity: "#5C8AFF",
        sandbox: "#1B4DFF",
        artifacts: "#7DA4FF",
        conversation_transcript: "#26D0CE",
        guidelines: "#2AD089",
        communication_style: "#3B6CFF",
        slash_commands: "#52DFDD",
        messaging: "#4F63D2",
        mcp_servers: "#1CB0AE",
        subagents: "#6E8CFF",
        user_rules: "#3A8FE8",
        skills: "#1FAF72",
        featured_plugins: "#6366F1",
        user_information: "#818CF8",
        subagent_reminder: "#2EB8C8",
    };

    function renderShieldMarkSvg(size = 16, idPrefix = "agyis-hud") {
        const edgeId = `${idPrefix}-edge`;
        const bodyId = `${idPrefix}-body`;
        return `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 128 128" width="${size}" height="${size}" aria-hidden="true" style="display:inline-block;vertical-align:middle;flex-shrink:0;">`
            + `<defs>`
            + `<linearGradient id="${edgeId}" x1="16" y1="12" x2="112" y2="116" gradientUnits="userSpaceOnUse"><stop offset="0%" stop-color="#1B4DFF"/><stop offset="52%" stop-color="#5C8AFF"/><stop offset="100%" stop-color="#26D0CE"/></linearGradient>`
            + `<linearGradient id="${bodyId}" x1="64" y1="12" x2="64" y2="116" gradientUnits="userSpaceOnUse"><stop offset="0%" stop-color="#101C33"/><stop offset="100%" stop-color="#080E1A"/></linearGradient>`
            + `</defs>`
            + `<path d="M40 12 L88 12 L112 32 L112 74 L64 116 L16 74 L16 32 Z" fill="url(#${bodyId})" stroke="url(#${edgeId})" stroke-width="4" stroke-linejoin="miter"/>`
            + `<path d="M43 19 L85 19 L105 35.5 L105 70.5 L64 106.5 L23 70.5 L23 35.5 Z" fill="none" stroke="#233659" stroke-width="1.5"/>`
            + `<polygon points="31,83 52,31 61,31 42,83" fill="#F4F6FA"/>`
            + `<polygon points="97,83 76,31 67,31 86,83" fill="#F4F6FA"/>`
            + `<polygon points="64,47 64,63 53,63" fill="#A8C5FF"/><polygon points="64,47 75,63 64,63" fill="#5C8AFF"/>`
            + `<polygon points="53,63 64,63 64,79" fill="#1B4DFF"/><polygon points="64,63 75,63 64,79" fill="#26D0CE"/>`
            + `<path d="M54 91 L64 99.5 L74 91" fill="none" stroke="url(#${edgeId})" stroke-width="3.2" stroke-linecap="square" stroke-linejoin="miter"/>`
            + `</svg>`;
    }

    const SHIELD_MARK_SVG = renderShieldMarkSvg(16, "agyis-hud");

    const ICON_PATHS = {
        refresh: '<path d="M13.5 7A5.5 5.5 0 1 1 12 3.4"/><path d="M13.5 2.5v3h-3"/>',
        split: '<rect x="2" y="3" width="12" height="10" rx="1.5"/><path d="M8 3v10"/>',
        stack: '<rect x="2" y="3" width="12" height="10" rx="1.5"/><path d="M2 8h12"/>',
        maximize: '<path d="M3 6V3h3M10 3h3v3M13 10v3h-3M6 13H3v-3"/>',
        restore: '<path d="M6 3v3H3M10 3v3h3M13 10h-3v3M3 10h3v3"/>',
        close: '<path d="M4 4l8 8M12 4l-8 8"/>',
        copy: '<rect x="5" y="5" width="8" height="9" rx="1.2"/><path d="M3 11V3.5A1.5 1.5 0 0 1 4.5 2H11"/>',
        check: '<path d="M3.5 8.5l3 3 6-6.5"/>',
        info: '<circle cx="8" cy="8" r="6"/><path d="M8 7.5v4M8 5h.01"/>',
        warn: '<path d="M8 2.5l6 11H2l6-11z"/><path d="M8 6.5v3.5M8 11.8h.01"/>',
        tip: '<path d="M6 12h4M6.5 14h3M5.5 9.5A3.5 3.5 0 1 1 10.5 9.5c-.5.6-.8 1.2-.8 2H6.3c0-.8-.3-1.4-.8-2z"/>',
        alert: '<circle cx="8" cy="8" r="6"/><path d="M8 4.8v4M8 11.2h.01"/>',
        caution: '<path d="M5.2 2h5.6L14 5.2v5.6L10.8 14H5.2L2 10.8V5.2L5.2 2z"/><path d="M8 5v3.5M8 11h.01"/>',
        user: '<circle cx="8" cy="5.2" r="2.5"/><path d="M3.2 13.5a4.8 4.8 0 0 1 9.6 0"/>',
        brain: '<path d="M6 3a2.5 2.5 0 0 0-2.5 2.5c0 .5.1.9.3 1.3A2.3 2.3 0 0 0 3 8.5a2.3 2.3 0 0 0 1.2 2A2.5 2.5 0 0 0 8 13V3.5A2 2 0 0 0 6 3zm4 0a2.5 2.5 0 0 1 2.5 2.5c0 .5-.1.9-.3 1.3a2.3 2.3 0 0 1 .8 1.7 2.3 2.3 0 0 1-1.2 2A2.5 2.5 0 0 1 8 13V3.5A2 2 0 0 1 10 3z"/>',
        settings: '<circle cx="8" cy="8" r="2.3"/><path d="M8 2v1.6M8 12.4V14M2 8h1.6M12.4 8H14M3.8 3.8l1.1 1.1M11.1 11.1l1.1 1.1M12.2 3.8l-1.1 1.1M4.9 11.1l-1.1 1.1"/>',
        file: '<path d="M4 2h5.5L13 5.5V14H4V2z"/><path d="M9 2v4h4"/>',
        diff: '<path d="M4 2h5.5L13 5.5V14H4V2z"/><path d="M6.5 8h3M8 6.5v3M6.5 11.5h3"/>',
        bot: '<rect x="3" y="4.5" width="10" height="8" rx="1.8"/><path d="M8 2v2.5M6 8.2h.01M10 8.2h.01M6 10.5h4"/>',
        shield: '<path d="M8 2l5 2v4c0 3.3-2.2 5.4-5 6.5C5.2 13.4 3 11.3 3 8V4l5-2z"/>',
        chart: '<path d="M2.5 13.5h11M4.5 11V8M8 11V4.5M11.5 11V6.5"/>',
        pin: '<path d="M5.5 3h5l-.8 4.2 1.8 1.8v1H4.5v-1l1.8-1.8L5.5 3zM8 10v4"/>',
    };

    function svgIcon(name, size = 13) {
        const body = ICON_PATHS[name] || ICON_PATHS.info;
        return `<svg viewBox="0 0 16 16" width="${size}" height="${size}" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true" style="display:inline-block;vertical-align:middle;flex-shrink:0;">${body}</svg>`;
    }

    global.__agyis_theme = {
        TOKENS,
        PROMPT_PALETTE,
        SHIELD_MARK_SVG,
        renderShieldMarkSvg,
        svgIcon,
    };
})(typeof window !== "undefined" ? window : globalThis);
