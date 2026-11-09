(() => {
    const HUD_ID = "agyis-trajectory-hud";
    const STYLES_ID = "agyis-trajectory-hud-styles";
    const __PAYLOAD__ = null;
    const initialData = __PAYLOAD__.initialData;
    const conversationList = __PAYLOAD__.conversationList;
    const shouldOpen = __PAYLOAD__.shouldOpen;
    const isToggle = __PAYLOAD__.isToggle;
    let hud = document.getElementById(HUD_ID);

    function syncToLatestState(state) {
        if (!state || !state.currentData) return;
        const steps = state.currentData.steps || [];
        const epochs = state.currentData.epochs || [];

        // 1. Show latest epoch
        state.activeEpochIndex = epochs.length > 0 ? epochs.length - 1 : -1;

        // 2. Select latest step
        state.selectedIndex = Math.max(0, steps.length - 1);

        // 3. Show latest 50 steps on steps list (last table page)
        const totalSteps = steps.length;
        const pageSize = 50;
        const totalPages = Math.max(1, Math.ceil(totalSteps / pageSize));
        state.tablePage = totalPages - 1;
    }

    let existingHud = document.getElementById(HUD_ID);
    if (existingHud && isToggle) {
        const isHidden = existingHud.style.display === "none";
        existingHud.style.display = isHidden ? "flex" : "none";
        if (isHidden) {
            const match = window.location.pathname.match(/\/c\/([a-f0-9\-]+)/);
            const focusedConvoId = match ? match[1] : null;
            const state = window.__agyis_hud_state;
            if (focusedConvoId && state && focusedConvoId !== state.convoId && typeof window.__agyis_hud_load_convo === "function") {
                window.__agyis_hud_load_convo(focusedConvoId);
            } else if (state) {
                syncToLatestState(state);
                if (typeof renderHud === "function") renderHud();
                const selEl = document.querySelector(`.agyis-step-grid-item[data-index="${state.selectedIndex}"]`);
                if (selEl) selEl.scrollIntoView({ block: "nearest" });
            }
        }
        return { success: true, open: isHidden, toggled: true };
    }

    // Stale DOM Replacement: Purge existing HUD and styles on re-injection (PSL-INV-010)
    if (existingHud) existingHud.remove();
    const existingStyles = document.getElementById(STYLES_ID);
    if (existingStyles) existingStyles.remove();

    const styleEl = document.createElement("style");
        styleEl.id = STYLES_ID;
        styleEl.textContent = `
            #agyis-trajectory-hud {
                position: fixed;
                top: 38px;
                left: 0;
                right: 0;
                bottom: 0;
                z-index: 99999;
                display: flex;
                align-items: center;
                justify-content: center;
                background: rgba(0, 0, 0, 0.75);
                backdrop-filter: blur(8px);
                font-family: ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
                color: #f4f4f5;
                box-sizing: border-box;
            }
            #agyis-trajectory-hud * { box-sizing: border-box; }
            .agyis-hud-box {
                width: 95vw;
                max-width: 1440px;
                height: 90vh;
                background: #18181b;
                border: 1px solid #27272a;
                border-radius: 12px;
                box-shadow: 0 25px 50px -12px rgba(0, 0, 0, 0.9);
                display: flex;
                flex-direction: column;
                overflow: hidden;
                transition: all 0.2s ease-in-out;
                -webkit-app-region: no-drag;
            }
            .agyis-hud-box.maximized {
                width: 100vw !important;
                max-width: 100vw !important;
                height: calc(100vh - 38px) !important;
                border-radius: 0 !important;
                border: none !important;
            }
            .agyis-hud-header {
                display: flex;
                align-items: center;
                justify-content: space-between;
                padding: 8px 14px;
                background: #121214;
                border-bottom: 1px solid #27272a;
                gap: 10px;
                flex-wrap: wrap;
                position: relative;
                z-index: 100;
                -webkit-app-region: no-drag;
            }
            .agyis-hud-header-left { display: flex; align-items: center; gap: 8px; min-width: 0; flex-wrap: wrap; }
            .agyis-hud-header-right { display: flex; align-items: center; gap: 8px; }
            .agyis-hud-pill {
                display: inline-flex;
                align-items: center;
                gap: 5px;
                padding: 3px 8px;
                border-radius: 9999px;
                font-size: 11px;
                font-weight: 600;
                line-height: 1.2;
                border: 1px solid transparent;
            }
            .agyis-hud-pill-purple { background: rgba(168, 85, 247, 0.12); color: #c084fc; border-color: rgba(168, 85, 247, 0.3); }
            .agyis-hud-pill-blue { background: rgba(59, 130, 246, 0.12); color: #60a5fa; border-color: rgba(59, 130, 246, 0.3); }
            .agyis-hud-pill-amber { background: rgba(245, 158, 11, 0.12); color: #fbbf24; border-color: rgba(245, 158, 11, 0.3); }
            .agyis-hud-pill-green { background: rgba(16, 185, 129, 0.12); color: #34d399; border-color: rgba(16, 185, 129, 0.3); }
            .agyis-hud-pill-teal { background: rgba(20, 184, 166, 0.12); color: #2dd4bf; border-color: rgba(20, 184, 166, 0.3); }
            .agyis-hud-pill-red { background: rgba(239, 68, 68, 0.12); color: #f87171; border-color: rgba(239, 68, 68, 0.3); }
            .agyis-hud-pill-zinc { background: rgba(113, 113, 122, 0.12); color: #a1a1aa; border-color: rgba(113, 113, 122, 0.3); }
            .agyis-hud-btn {
                background: #27272a;
                border: 1px solid #3f3f46;
                color: #f4f4f5;
                border-radius: 6px;
                padding: 4px 8px;
                font-size: 11px;
                font-weight: 500;
                cursor: pointer;
                display: inline-flex;
                align-items: center;
                gap: 5px;
                transition: background 0.15s, border-color 0.15s;
                user-select: none;
                -webkit-app-region: no-drag;
            }
            .agyis-hud-btn:hover { background: #3f3f46; border-color: #52525b; }
            .agyis-hud-btn.active { background: #3f3f46; border-color: #f59e0b; color: #fbbf24; font-weight: 600; }
            .agyis-hud-select {
                background: #202023;
                border: 1px solid #3f3f46;
                color: #f4f4f5;
                border-radius: 6px;
                padding: 4px 8px;
                font-size: 11px;
                outline: none;
                max-width: 260px;
                cursor: pointer;
            }
            .agyis-hud-search-box {
                display: flex;
                align-items: center;
                background: #202023;
                border: 1px solid #3f3f46;
                border-radius: 6px;
                padding: 0 6px;
                height: 26px;
                position: relative;
            }
            .agyis-hud-search-input {
                background: transparent;
                border: none;
                color: #f4f4f5;
                font-size: 11px;
                outline: none;
                width: 130px;
                transition: width 0.2s;
            }
            .agyis-hud-search-input:focus { width: 180px; }
            .agyis-hud-search-counter { font-size: 10px; color: #a1a1aa; margin: 0 4px; font-family: monospace; white-space: nowrap; }

            /* 2.26.0 Context Window Bar ('Dlc' Parity) */
            .context-cell-selected {
                box-shadow: 0 0 0 2px #eab308 !important;
            }
            .context-cell-hovered,
            .context-cell-unused:hover {
                box-shadow: 0 0 0 1px rgba(234, 179, 8, 0.8) !important;
            }
            .context-cell-unused {
                background: #27272a !important;
                opacity: 0.6;
            }
            .context-tooltip {
                border-color: rgba(234, 179, 8, 0.8) !important;
            }
            .agyis-context-bar-wrap {
                padding: 8px 14px;
                background: #151518;
                border-bottom: 1px solid #27272a;
                display: flex;
                flex-direction: column;
                gap: 6px;
                position: relative;
                z-index: 50;
            }
            .agyis-context-track {
                width: 100%;
                background: #27272a;
                border-radius: 4px;
                border: 1px solid #3f3f46;
                position: relative;
                overflow: hidden;
                display: flex;
                flex-direction: column;
                gap: 2px;
            }
            .agyis-context-row {
                position: relative;
                width: 100%;
                overflow: hidden;
            }
            .agyis-context-segment {
                height: 100%;
                cursor: pointer;
                transition: filter 0.15s, opacity 0.15s;
                position: relative;
                border: none;
                padding: 0;
                margin: 0;
                -webkit-app-region: no-drag;
            }
            .agyis-context-segment:hover { filter: brightness(1.25); z-index: 20; }

            /* Main Deck Tabs: Context Window vs Timeline (2.26.0 Parity) */
            .agyis-main-deck-tabs {
                display: flex;
                align-items: center;
                gap: 4px;
                padding: 0 10px;
                background: #141416;
                border-bottom: 1px solid #27272a;
                user-select: none;
                flex-shrink: 0;
            }
            .agyis-main-tab-btn {
                padding: 6px 12px;
                font-size: 11px;
                font-weight: 600;
                color: #a1a1aa;
                background: transparent;
                border: none;
                border-bottom: 2px solid transparent;
                margin-bottom: -1px;
                cursor: pointer;
                transition: color 0.15s, border-color 0.15s;
            }
            .agyis-main-tab-btn:hover {
                color: #f4f4f5;
            }
            .agyis-main-tab-btn.active {
                color: #fbbf24;
                border-bottom: 2px solid #eab308;
            }

            /* Timeline View ('lvc' Parity) */
            .agyis-timeline-pane {
                flex: 1;
                display: flex;
                flex-direction: column;
                overflow-y: auto;
                background: #18181b;
                padding: 12px;
                gap: 8px;
            }
            .agyis-timeline-card {
                background: #202023;
                border: 1px solid #3f3f46;
                border-radius: 6px;
                padding: 8px 12px;
                cursor: pointer;
                transition: background 0.1s, border-color 0.15s;
                font-family: ui-monospace, monospace;
            }
            .agyis-timeline-card:hover {
                background: #27272c;
                border-color: #52525b;
            }
            .agyis-timeline-card.selected {
                background: #27241d;
                border-color: #eab308;
                box-shadow: 0 0 0 1px #eab308;
            }
            .agyis-context-tooltip {
                position: absolute;
                top: 100%;
                margin-top: 6px;
                left: 14px;
                background: #18181b;
                border: 1px solid rgba(234, 179, 8, 0.8);
                border-radius: 6px;
                padding: 6px 10px;
                font-size: 11px;
                font-family: ui-monospace, monospace;
                color: #f4f4f5;
                box-shadow: 0 10px 25px rgba(0, 0, 0, 0.8);
                z-index: 100;
                pointer-events: none;
                max-width: 400px;
                white-space: pre-wrap;
            }
            .agyis-context-legend {
                display: flex;
                align-items: center;
                justify-content: space-between;
                font-size: 11px;
                color: #a1a1aa;
                gap: 12px;
                flex-wrap: wrap;
            }
            .agyis-legend-item { display: inline-flex; align-items: center; gap: 4px; }
            .agyis-legend-dot { width: 8px; height: 8px; border-radius: 50%; }

            /* 8-column CSS Grid History Table ('rmc' Parity) */
            .agyis-hud-main-deck {
                flex: 1;
                display: flex;
                overflow: hidden;
                background: #18181b;
            }
            .agyis-hud-main-deck.vertical { flex-direction: column; }
            .agyis-grid-pane {
                flex: 1;
                display: flex;
                flex-direction: column;
                min-width: 480px;
                min-height: 200px;
                border-right: 1px solid #27272a;
                overflow: hidden;
                background: #18181b;
            }
            .agyis-hud-main-deck.vertical .agyis-grid-pane { border-right: none; border-bottom: 1px solid #27272a; }
            .agyis-step-grid-row {
                display: grid;
                grid-template-columns: 50px 50px 55px 140px 1fr 70px 80px 80px;
                height: 32px;
                align-items: center;
                font-size: 11px;
                border-bottom: 1px solid #232326;
                padding: 0 8px;
                gap: 6px;
            }
            .agyis-step-grid-header {
                background: #141416;
                font-weight: 700;
                color: #71717a;
                text-transform: uppercase;
                letter-spacing: 0.05em;
                position: sticky;
                top: 0;
                z-index: 10;
                border-bottom: 1px solid #27272a;
            }
            .agyis-step-grid-body {
                flex: 1;
                overflow-y: auto;
            }
            .agyis-step-grid-item {
                cursor: pointer;
                transition: background 0.1s;
                font-family: ui-monospace, monospace;
            }
            .agyis-step-grid-item:hover { background: #202024; }
            .agyis-step-grid-item.selected {
                background: #27241d;
                border-left: 2px solid #eab308;
            }

            /* Resizable Splitter */
            .agyis-splitter {
                width: 6px;
                background: #27272a;
                cursor: col-resize;
                transition: background 0.15s;
                flex-shrink: 0;
            }
            .agyis-hud-main-deck.vertical .agyis-splitter {
                width: 100%;
                height: 6px;
                cursor: row-resize;
            }
            .agyis-splitter:hover { background: #f59e0b; }

            /* Step Inspector ('jmc' & 'fmc' Parity) */
            .agyis-inspector-pane {
                flex: 1.1;
                display: flex;
                flex-direction: column;
                min-width: 420px;
                min-height: 200px;
                overflow: hidden;
                background: #18181b;
            }
            .agyis-inspector-header {
                display: flex;
                align-items: center;
                justify-content: space-between;
                padding: 8px 14px;
                background: #141416;
                border-bottom: 1px solid #27272a;
                gap: 8px;
            }
            .agyis-inspector-tabs {
                display: flex;
                gap: 4px;
                padding: 6px 14px;
                background: #18181b;
                border-bottom: 1px solid #27272a;
            }
            .agyis-inspector-content {
                flex: 1;
                overflow-y: auto;
                padding: 14px;
                font-size: 12px;
                line-height: 1.5;
            }
            .agyis-timing-bar-wrap {
                background: #202023;
                border: 1px solid #3f3f46;
                border-radius: 6px;
                padding: 8px 12px;
                margin-bottom: 12px;
                display: flex;
                flex-direction: column;
                gap: 6px;
            }
            .agyis-timing-bar {
                height: 10px;
                background: #27272a;
                border-radius: 4px;
                overflow: hidden;
                display: flex;
            }
            .agyis-codeblock {
                background: #0d0d0f;
                border: 1px solid #27272a;
                border-radius: 6px;
                padding: 10px;
                font-family: ui-monospace, monospace;
                font-size: 11px;
                white-space: pre-wrap;
                word-break: break-all;
                overflow-x: auto;
                color: #e4e4e7;
            }
            .agyis-markdown-table {
                width: 100%;
                border-collapse: collapse;
                margin: 8px 0;
                font-size: 11px;
            }
            .agyis-markdown-table th, .agyis-markdown-table td {
                border: 1px solid #3f3f46;
                padding: 6px 8px;
                text-align: left;
            }
            .agyis-markdown-table th { background: #202023; color: #fbbf24; }
            .agyis-context-row-wrap {
                display: flex;
                align-items: center;
                gap: 8px;
            }
            .agyis-context-row-label {
                font-family: ui-monospace, monospace;
                font-size: 10px;
                color: #a1a1aa;
                width: 34px;
                text-align: right;
                flex-shrink: 0;
                user-select: none;
            }
            .agyis-context-row-track {
                flex: 1;
                height: 18px;
                position: relative;
                background: #27272a;
                border-radius: 4px;
                overflow: hidden;
                border: 1px solid #3f3f46;
            }
            .agyis-codeblock-wrap {
                position: relative;
                margin: 8px 0;
                background: #0d0d0f;
                border: 1px solid #27272a;
                border-radius: 6px;
            }
            .agyis-thinking-block {
                background: rgba(245, 158, 11, 0.08);
                border: 1px solid rgba(245, 158, 11, 0.3);
                border-radius: 6px;
                margin-bottom: 12px;
                padding: 8px 12px;
            }
            .agyis-xml-callout {
                background: rgba(24, 24, 27, 0.9);
                border-radius: 6px;
                padding: 10px 12px;
                margin: 8px 0;
            }
            .agyis-github-alert {
                background: rgba(30, 30, 36, 0.85);
                border-radius: 6px;
                padding: 10px 12px;
                margin: 8px 0;
            }
        `;
        document.head.appendChild(styleEl);

    hud = document.createElement("div");
    hud.id = HUD_ID;
    hud.style.display = shouldOpen ? "flex" : "none";

    const steps = initialData.steps || [];
    const epochs = initialData.epochs || [];
    window.__agyis_hud_state = {
        rootData: initialData,
        currentData: initialData,
        convoId: initialData.conversation_id,
        selectedIndex: Math.max(0, steps.length - 1),
        activeEpochIndex: epochs.length > 0 ? epochs.length - 1 : -1,
        tablePage: Math.max(0, Math.ceil(steps.length / 50) - 1),
        pageSize: 50,
        filterQuery: "",
        searchMatchIndices: [],
        currentMatchIdx: -1,
        activeTab: "step", // step, invocation, execution, trajectory
        mainDeckTab: "context", // context vs timeline
        layoutOrientation: "horizontal", // horizontal (side-by-side) vs vertical (stacked)
        isMaximized: false,
        subagentsDropdownOpen: false,
        hoveredContextSegment: null,
    };
    syncToLatestState(window.__agyis_hud_state);

    function xtc(segment, pxPerToken, minSegmentPx) {
        const tokens = segment && segment.tokens > 0 ? segment.tokens : 0;
        return tokens > 0 ? Math.max(tokens * pxPerToken, minSegmentPx) : 0;
    }

    function ytc(segments, capacityTokens, containerWidth, minSegmentPx, rowsCount) {
        const capacityPx = containerWidth * rowsCount;
        const pxPerToken = capacityTokens > 0 ? capacityPx / capacityTokens : 0;
        let usedPx = 0;
        let trueUsedPx = 0;
        for (let i = 0; i < segments.length; i++) {
            const tok = segments[i].tokens || 0;
            usedPx += xtc(segments[i], pxPerToken, minSegmentPx);
            trueUsedPx += (tok > 0 ? tok : 0) * pxPerToken;
        }
        return {
            capacityPx: capacityPx,
            pxPerToken: pxPerToken,
            usedPx: usedPx,
            trueUsedPx: trueUsedPx,
            inflationPx: usedPx - trueUsedPx,
        };
    }

    function ztc(segments, capacityTokens, containerWidth, minSegmentPx, maxRows) {
        let current = ytc(segments, capacityTokens, containerWidth, minSegmentPx, 1);
        for (let r = 1; r < maxRows; r++) {
            if (current.inflationPx <= 0.1 * current.trueUsedPx) return r;
            const next = ytc(segments, capacityTokens, containerWidth, minSegmentPx, r + 1);
            if (current.inflationPx - next.inflationPx < 0.02 * containerWidth) return r;
            current = next;
        }
        return maxRows;
    }

    function Atc(segments, capacityTokens, containerWidth, options) {
        const opts = options || {};
        const minSegmentPx = opts.minSegmentPx ?? 2;
        const maxRows = Math.min(8, Math.max(1, opts.maxRows ?? 8));
        const emptyResult = { rows: [], inflationPx: 0 };
        if (!segments || segments.length === 0 || !Number.isFinite(containerWidth) || !Number.isFinite(capacityTokens) || containerWidth <= 0 || capacityTokens <= 0) {
            return emptyResult;
        }

        const rowCount = ztc(segments, capacityTokens, containerWidth, minSegmentPx, maxRows);
        const layout = ytc(segments, capacityTokens, containerWidth, minSegmentPx, rowCount);
        const scaleFactor = layout.usedPx > layout.capacityPx ? layout.capacityPx / layout.usedPx : 1;
        const segmentWidths = segments.map(s => xtc(s, layout.pxPerToken, minSegmentPx) * scaleFactor);
        const unusedPx = Math.max(0, layout.capacityPx - layout.usedPx * scaleFactor);

        const rows = [];
        for (let r = 0; r < rowCount; r++) rows.push([]);

        let cursorPx = 0;
        const placeCell = (seg, widthPx, keyPrefix, showDivider) => {
            let remainingWidth = widthPx;
            let subIndex = 0;
            while (remainingWidth > 1e-6) {
                const rowIndex = Math.min(rows.length - 1, Math.floor((cursorPx + 1e-6) / containerWidth));
                const rowStartPx = cursorPx - rowIndex * containerWidth;
                const availableInRow = containerWidth - rowStartPx;
                if (availableInRow <= 1e-6) break;

                const sliceWidth = Math.min(remainingWidth, availableInRow);
                remainingWidth -= sliceWidth;
                cursorPx += sliceWidth;

                const isDone = remainingWidth <= 1e-6;
                const fillsRow = sliceWidth >= availableInRow - 1e-6;

                rows[rowIndex].push({
                    key: `${keyPrefix}#${subIndex}`,
                    segment: seg,
                    startFraction: rowStartPx / containerWidth,
                    widthFraction: sliceWidth / containerWidth,
                    continuesFromPreviousRow: subIndex > 0,
                    continuesOnNextRow: !isDone,
                    showDividerAfter: showDivider && isDone && !fillsRow,
                });
                subIndex++;
            }
        };

        segments.forEach((seg, idx) => {
            const nextSeg = segments[idx + 1];
            const showDivider = nextSeg !== undefined && nextSeg.colorKey === seg.colorKey;
            placeCell(seg, segmentWidths[idx], `${idx}:${seg.id}`, showDivider);
        });

        if (unusedPx > 1e-6) {
            placeCell(null, unusedPx, "unused", false);
        }

        return { rows: rows, inflationPx: layout.inflationPx * scaleFactor };
    }

    window.__agyis_hud_load_convo = async function(convoId) {
        if (!convoId) return null;
        try {
            const csrfToken = (window.__APP_CONFIG__ && window.__APP_CONFIG__.csrfToken) || "";
            const baseUrl = (window.location && window.location.origin && window.location.origin.startsWith("http"))
                ? window.location.origin
                : "https://127.0.0.1:40623";

            const headers = {
                "Content-Type": "application/json",
                "Connect-Protocol-Version": "1",
            };
            if (csrfToken) {
                headers["x-codeium-csrf-token"] = csrfToken;
            }

            const reqBody = JSON.stringify({ cascadeId: convoId });
            const [trajRes, stepsRes, genRes, execRes] = await Promise.all([
                fetch(`${baseUrl}/exa.language_server_pb.LanguageServerService/GetCascadeTrajectory`, {
                    method: "POST",
                    headers: headers,
                    body: reqBody,
                }).catch(() => null),
                fetch(`${baseUrl}/exa.language_server_pb.LanguageServerService/GetCascadeTrajectorySteps`, {
                    method: "POST",
                    headers: headers,
                    body: reqBody,
                }).catch(() => null),
                fetch(`${baseUrl}/exa.language_server_pb.LanguageServerService/GetCascadeTrajectoryGeneratorMetadata`, {
                    method: "POST",
                    headers: headers,
                    body: reqBody,
                }).catch(() => null),
                fetch(`${baseUrl}/exa.language_server_pb.LanguageServerService/GetCascadeTrajectoryExecutorMetadatas`, {
                    method: "POST",
                    headers: headers,
                    body: reqBody,
                }).catch(() => null),
            ]);

            let rawSteps = null;
            if (stepsRes && stepsRes.ok) {
                const stepsJson = await stepsRes.json().catch(() => null);
                if (stepsJson && Array.isArray(stepsJson.steps)) {
                    rawSteps = stepsJson.steps;
                }
            }

            if (!rawSteps && trajRes && trajRes.ok) {
                const trajJson = await trajRes.json().catch(() => null);
                if (trajJson && trajJson.trajectory && Array.isArray(trajJson.trajectory.steps)) {
                    rawSteps = trajJson.trajectory.steps;
                }
            }

            if (!rawSteps || rawSteps.length === 0) {
                if (__PAYLOAD__ && __PAYLOAD__.initialData) {
                    const fallbackData = __PAYLOAD__.initialData;
                    const state = window.__agyis_hud_state;
                    if (state) {
                        state.rootData = fallbackData;
                        state.currentData = fallbackData;
                        state.convoId = fallbackData.conversation_id || convoId;
                        syncToLatestState(state);
                        state.subagentsDropdownOpen = false;
                        renderHud();
                        const selEl = document.querySelector(`.agyis-step-grid-item[data-index="${state.selectedIndex}"]`);
                        if (selEl) selEl.scrollIntoView({ block: "nearest" });
                    }
                    return fallbackData;
                }
                return null;
            }

            let genMetas = [];
            let chatModelData = null;
            if (genRes && genRes.ok) {
                const genJson = await genRes.json().catch(() => null);
                if (genJson) {
                    genMetas = genJson.generatorMetadata || genJson.generatorMetadatas || genJson.metadatas || [];
                    chatModelData = genJson.chatModel || (genMetas[0] && genMetas[0].chatModel) || null;
                }
            }

            let execMetas = [];
            if (execRes && execRes.ok) {
                const execJson = await execRes.json().catch(() => null);
                if (execJson) {
                    execMetas = execJson.executorMetadatas || execJson.metadatas || [];
                }
            }

            const genMetaByStep = {};
            const genMetaList = [];
            genMetas.forEach(gm => {
                if (gm && gm.stepIndex !== undefined && gm.stepIndex !== null) {
                    genMetaByStep[gm.stepIndex] = gm;
                } else if (gm) {
                    genMetaList.push(gm);
                }
            });

            const execMetaByStep = {};
            const execMetaList = [];
            execMetas.forEach(em => {
                if (em && em.stepIndex !== undefined && em.stepIndex !== null) {
                    execMetaByStep[em.stepIndex] = em;
                } else if (em) {
                    execMetaList.push(em);
                }
            });

            let plannerIdx = 0;
            let toolIdx = 0;
            let cumulativeCtx = 0;
            const steps = [];

            rawSteps.forEach((rawStep, idx) => {
                let cortexType = rawStep.type || rawStep.stepType || "";
                if (typeof cortexType === "string" && cortexType.startsWith("CORTEX_STEP_TYPE_")) {
                    cortexType = cortexType.replace("CORTEX_STEP_TYPE_", "");
                }
                if (!cortexType) {
                    if (rawStep.userInput) cortexType = "USER_INPUT";
                    else if (rawStep.checkpoint) cortexType = "CHECKPOINT";
                    else if (rawStep.plannerResponse) cortexType = "PLANNER_RESPONSE";
                    else if (rawStep.runCommand) cortexType = "RUN_COMMAND";
                    else if (rawStep.viewFile) cortexType = "VIEW_FILE";
                    else if (rawStep.codeAction) cortexType = "CODE_ACTION";
                    else if (rawStep.invokeSubagent) cortexType = "INVOKE_SUBAGENT";
                    else if (rawStep.toolCalls || rawStep.toolCall || (rawStep.metadata && rawStep.metadata.toolCall)) cortexType = "TOOL_CALL";
                    else {
                        const src = String(rawStep.source || rawStep.role || "").toLowerCase();
                        if (src === "user") cortexType = "USER_INPUT";
                        else if (src === "system") cortexType = "SYSTEM";
                        else if (src === "model" || src === "assistant") cortexType = "MODEL_OUTPUT";
                        else cortexType = "STEP";
                    }
                }

                let content = rawStep.content || "";
                if (!content && rawStep.userInput) {
                    content = rawStep.userInput.userResponse ||
                        (rawStep.userInput.items && rawStep.userInput.items[0] && (rawStep.userInput.items[0].text || rawStep.userInput.items[0].content)) || "";
                }
                if (!content && rawStep.plannerResponse) {
                    content = rawStep.plannerResponse.response || rawStep.plannerResponse.text || rawStep.plannerResponse.content || "";
                }

                let thinking = rawStep.thinking || (rawStep.plannerResponse && rawStep.plannerResponse.thinking) || "";

                let toolCalls = rawStep.tool_calls || rawStep.toolCalls || [];
                if (!Array.isArray(toolCalls) && rawStep.toolCall) {
                    toolCalls = [rawStep.toolCall];
                }
                const rawTc = rawStep.toolCall || (rawStep.metadata && rawStep.metadata.toolCall);
                if (toolCalls.length === 0 && rawTc) {
                    let parsedArgs = rawTc.arguments || rawTc.args || {};
                    if (rawTc.argumentsJson) {
                        try {
                            parsedArgs = JSON.parse(rawTc.argumentsJson);
                        } catch (_) {
                            parsedArgs = { raw: rawTc.argumentsJson };
                        }
                    }
                    toolCalls = [{ id: rawTc.id, name: rawTc.name, args: parsedArgs }];
                }

                let compSummary = null;
                let checkpointIndex = null;
                if (rawStep.checkpoint) {
                    const cp = rawStep.checkpoint;
                    if (typeof cp === "object" && cp !== null) {
                        compSummary = cp.sessionSummary || cp.userIntent || cp.summary || null;
                        if (cp.checkpointIndex !== undefined) checkpointIndex = cp.checkpointIndex;
                    } else if (typeof cp === "string") {
                        compSummary = cp;
                    }
                }
                if (!compSummary && rawStep.sessionSummary) compSummary = String(rawStep.sessionSummary).trim();
                if (!compSummary && rawStep.userIntent) compSummary = String(rawStep.userIntent).trim();
                if (!compSummary && content) {
                    const m = String(content).match(/<(?:CONTEXT_SUMMARY|summary)>([\s\S]*?)<\/(?:CONTEXT_SUMMARY|summary)>/i);
                    if (m) compSummary = m[1].trim();
                }
                if (compSummary && cortexType !== "CHECKPOINT") {
                    cortexType = "CHECKPOINT";
                }

                const isModelStep = (cortexType === "PLANNER_RESPONSE" || cortexType === "MODEL_OUTPUT");
                let gm = genMetaByStep[idx] || null;
                if (!gm && isModelStep && plannerIdx < genMetaList.length) {
                    gm = genMetaList[plannerIdx++];
                }
                if (gm && gm.chatStartMetadata && gm.chatStartMetadata.checkpointIndex !== undefined) {
                    checkpointIndex = gm.chatStartMetadata.checkpointIndex;
                }

                const isToolStep = (cortexType === "TOOL_CALL" || cortexType.includes("COMMAND") || cortexType.includes("FILE") || cortexType.includes("SEARCH"));
                let em = execMetaByStep[idx] || null;
                if (!em && isToolStep && toolIdx < execMetaList.length) {
                    em = execMetaList[toolIdx++];
                }

                let thinkingMs = 0;
                let streamingMs = 0;
                if (gm) {
                    if (gm.timeToFirstToken) thinkingMs = parseInt(gm.timeToFirstToken) || 0;
                    if (gm.streamingDuration) streamingMs = parseInt(gm.streamingDuration) || 0;
                }
                if (!thinkingMs && thinking) {
                    thinkingMs = Math.min(20000, Math.max(600, Math.floor(thinking.length * 1.6)));
                }
                if (!streamingMs && isModelStep) {
                    streamingMs = Math.min(45000, Math.max(400, Math.floor(content.length * 1.8)));
                }
                if (em && em.executionDurationMs) {
                    streamingMs = parseInt(em.executionDurationMs) || 0;
                }
                const totalDurationMs = thinkingMs + streamingMs;

                let inTok = 0;
                let outTok = 0;
                let stepTok = 0;

                if (isModelStep) {
                    if (gm && gm.usage) {
                        inTok = parseInt(gm.usage.inputTokens || 0) || 0;
                        const respOut = parseInt(gm.usage.responseOutputTokens || 0) || 0;
                        const thinkOut = parseInt(gm.usage.thinkingOutputTokens || 0) || 0;
                        outTok = respOut + thinkOut;
                    }
                    stepTok = outTok;
                    if (stepTok <= 0) {
                        stepTok = Math.round((content.length + thinking.length) / 3.5);
                        outTok = stepTok;
                    }
                } else if (cortexType === "USER_INPUT") {
                    stepTok = Math.round(content.length / 3.5);
                    inTok = stepTok;
                } else if (cortexType === "CHECKPOINT") {
                    const charCount = (compSummary ? compSummary.length : content.length) || 100;
                    stepTok = Math.round(charCount / 3.5);
                } else {
                    let charCount = 0;
                    toolCalls.forEach(tc => {
                        charCount += (tc.name || "").length + JSON.stringify(tc.args || {}).length + String(tc.output || "").length;
                    });
                    if (charCount === 0) charCount = content.length;
                    stepTok = Math.round(charCount / 3.5);
                    outTok = stepTok;
                }

                if (stepTok <= 0 && rawStep.tokens) {
                    stepTok = parseInt(rawStep.tokens) || 0;
                }
                if (stepTok > 0) cumulativeCtx += stepTok;

                const stepObj = {
                    step_index: idx,
                    exec_index: rawStep.exec_index || 1,
                    inv_index: rawStep.inv_index || 1,
                    type: cortexType,
                    content: content,
                    thinking: thinking,
                    tool_calls: toolCalls,
                    status: rawStep.status || "STATUS_COMPLETED",
                    size_bytes: JSON.stringify(rawStep).length,
                    thinking_duration_ms: thinkingMs,
                    streaming_duration_ms: streamingMs,
                    total_duration_ms: totalDurationMs,
                    input_tokens: inTok,
                    output_tokens: outTok,
                    tokens: stepTok,
                    cumulative_tokens: cumulativeCtx,
                    compaction_summary: compSummary,
                    checkpoint_index: checkpointIndex,
                    response_model: (gm && (gm.responseModel || gm.model)) || "",
                    generator_metadata: gm,
                    executor_metadata: em,
                };

                if (rawStep.runCommand) {
                    stepObj.command = rawStep.runCommand.commandLine;
                    stepObj.exitCode = rawStep.runCommand.exitCode;
                    stepObj.output = (rawStep.runCommand.combinedOutput && rawStep.runCommand.combinedOutput.full) || "";
                    stepObj.cwd = rawStep.runCommand.cwd;
                }
                if (rawStep.viewFile) {
                    stepObj.filePath = rawStep.viewFile.absolutePathUri;
                    stepObj.fileContent = rawStep.viewFile.content;
                    stepObj.endLine = rawStep.viewFile.endLine;
                }
                if (rawStep.codeAction) {
                    stepObj.diffLines = (rawStep.codeAction.actionResult && rawStep.codeAction.actionResult.edit && rawStep.codeAction.actionResult.edit.diff && rawStep.codeAction.actionResult.edit.diff.unifiedDiff && rawStep.codeAction.actionResult.edit.diff.unifiedDiff.lines) || [];
                    const actSpec = rawStep.codeAction.actionSpec || {};
                    stepObj.filePath = (actSpec.createFile && actSpec.createFile.path && actSpec.createFile.path.absoluteUri) || (actSpec.editFile && actSpec.editFile.path && actSpec.editFile.path.absoluteUri) || "";
                }
                if (rawStep.invokeSubagent) {
                    stepObj.subagent = (rawStep.invokeSubagent.subagents && rawStep.invokeSubagent.subagents[0]) || null;
                }
                if (rawStep.checkpoint) {
                    stepObj.sessionSummary = rawStep.checkpoint.sessionSummary || "";
                    const retryUsage = (rawStep.metadata && rawStep.metadata.retryInfos && rawStep.metadata.retryInfos[0] && rawStep.metadata.retryInfos[0].usage) || {};
                    stepObj.cacheReadTokens = parseInt(retryUsage.cacheReadTokens || 0) || 0;
                    stepObj.checkpointInputTokens = parseInt(retryUsage.inputTokens || 0) || 0;
                }

                steps.push(stepObj);
            });

            const checkpoints = [];
            steps.forEach((s, i) => {
                if (s.type === "CHECKPOINT" || s.checkpoint_index !== null || s.compaction_summary !== null) {
                    checkpoints.push(i);
                }
            });

            const epochs = [];
            if (checkpoints.length === 0) {
                if (steps.length > 0) {
                    epochs.push({
                        epoch_index: 0,
                        start_index: 0,
                        end_index: steps.length - 1,
                        step_count: steps.length,
                        has_checkpoint: false,
                        summary: "Initial Trajectory",
                    });
                }
            } else {
                const c0 = checkpoints[0];
                epochs.push({
                    epoch_index: 0,
                    start_index: 0,
                    end_index: c0,
                    step_count: c0 + 1,
                    has_checkpoint: true,
                    summary: steps[c0].compaction_summary || `Checkpoint #${c0}`,
                });
                for (let k = 0; k < checkpoints.length; k++) {
                    const curCp = checkpoints[k];
                    if (k + 1 < checkpoints.length) {
                        const nextCp = checkpoints[k + 1];
                        epochs.push({
                            epoch_index: epochs.length,
                            start_index: curCp,
                            end_index: nextCp,
                            step_count: nextCp - curCp + 1,
                            has_checkpoint: true,
                            summary: steps[curCp].compaction_summary || `Checkpoint #${curCp}`,
                        });
                    } else if (curCp < steps.length - 1) {
                        epochs.push({
                            epoch_index: epochs.length,
                            start_index: curCp,
                            end_index: steps.length - 1,
                            step_count: (steps.length - 1) - curCp + 1,
                            has_checkpoint: true,
                            summary: steps[curCp].compaction_summary || `Checkpoint #${curCp}`,
                        });
                    }
                }
            }

            let maxContextTokens = 256000;
            let latestEstimatedTokens = 0;
            for (let i = genMetas.length - 1; i >= 0; i--) {
                const cwm = genMetas[i].contextWindowMetadata;
                if (cwm) {
                    if (cwm.estimatedTokensUsed && !latestEstimatedTokens) {
                        latestEstimatedTokens = parseInt(cwm.estimatedTokensUsed) || 0;
                    }
                    if (cwm.maxContextTokens) {
                        maxContextTokens = parseInt(cwm.maxContextTokens) || 256000;
                    }
                }
            }

            const stepSum = steps.reduce((acc, s) => acc + (s.tokens || 0), 0);
            const lastEpoch = epochs.length > 0 ? epochs[epochs.length - 1] : null;
            const activeEpochSteps = lastEpoch ? steps.slice(lastEpoch.start_index, lastEpoch.end_index + 1) : steps;
            const activeEpochTokens = activeEpochSteps.reduce((acc, s) => acc + (s.tokens || 0), 0);

            const sysPromptTok = stepSum > 0 ? Math.min(4000, Math.max(400, Math.floor(stepSum * 0.05))) : 3800;
            const toolDefsTok = stepSum > 0 ? Math.min(3500, Math.max(300, Math.floor(stepSum * 0.04))) : 3200;

            const totalTokens = latestEstimatedTokens > 0
                ? latestEstimatedTokens
                : (activeEpochTokens + sysPromptTok + toolDefsTok);

            let actualUserTok = 0;
            let actualModelTok = 0;
            let actualToolTok = 0;
            let actualCheckpointTok = 0;
            let actualSystemTok = 0;

            steps.forEach(s => {
                const t = s.type;
                const tok = s.tokens || 0;
                if (t === "USER_INPUT") actualUserTok += tok;
                else if (t === "PLANNER_RESPONSE" || t === "MODEL_OUTPUT") actualModelTok += tok;
                else if (t === "CHECKPOINT") actualCheckpointTok += tok;
                else if (t === "SYSTEM") actualSystemTok += tok;
                else actualToolTok += tok;
            });

            const tokenBreakdown = {
                system_prompt: sysPromptTok,
                tool_defs: toolDefsTok,
                checkpoint: actualCheckpointTok,
                user: actualUserTok,
                model: actualModelTok,
                tool: actualToolTok,
                system: actualSystemTok,
            };

            const breakdownSum = sysPromptTok + toolDefsTok + actualCheckpointTok + actualUserTok + actualModelTok + actualToolTok + actualSystemTok;
            const diff = totalTokens - breakdownSum;
            if (diff > 0) {
                tokenBreakdown.model += diff;
            }

            // Granular System Prompt & Tool Def Slices (ADR-014 / Cleanroom Parity)
            const rawSysPrompt = (chatModelData && chatModelData.systemPrompt) || "";
            const rawChatTools = (chatModelData && chatModelData.tools) || [];
            const promptSections = (chatModelData && chatModelData.promptSections) ||
                (genMetas[0] && genMetas[0].plannerConfig && genMetas[0].plannerConfig.declarativeMixinConfig && genMetas[0].plannerConfig.declarativeMixinConfig.promptSections) ||
                (rawSteps[0] && rawSteps[0].declarativeMixinConfig && rawSteps[0].declarativeMixinConfig.promptSections) || [];

            const sysTagDefs = [
                { tag: "identity", name: "Identity", color: "#6366f1" },
                { tag: "sandbox", name: "Sandbox", color: "#818cf8" },
                { tag: "artifacts", name: "Artifacts", color: "#a78bfa" },
                { tag: "conversation_transcript", name: "Transcript", color: "#c084fc" },
                { tag: "guidelines", name: "Guidelines", color: "#e879f9" },
                { tag: "communication_style", name: "Style", color: "#f472b6" },
                { tag: "slash_commands", name: "Commands", color: "#fb7185" },
                { tag: "messaging", name: "Messaging", color: "#9333ea" },
                { tag: "mcp_servers", name: "MCP Servers", color: "#7c3aed" },
                { tag: "subagents", name: "Subagents", color: "#6d28d9" },
                { tag: "user_rules", name: "User Rules", color: "#5b21b6" },
                { tag: "skills", name: "Skills", color: "#4c1d95" },
                { tag: "featured_plugins", name: "Plugins", color: "#8b5cf6" },
                { tag: "user_information", name: "UserInfo", color: "#a855f7" },
                { tag: "subagent_reminder", name: "Reminders", color: "#d946ef" },
            ];

            let systemPromptSlices = [];
            if (rawSysPrompt) {
                sysTagDefs.forEach(def => {
                    const re = new RegExp(`<${def.tag}>([\\s\\S]*?)</${def.tag}>`, "i");
                    const m = rawSysPrompt.match(re);
                    if (m && m[1]) {
                        systemPromptSlices.push({
                            name: def.name,
                            tag: def.tag,
                            tokens: Math.max(10, Math.round(m[1].length / 3.5)),
                            color: def.color,
                        });
                    }
                });
            } else if (promptSections && promptSections.length > 0) {
                promptSections.forEach((sec, sidx) => {
                    const sName = sec.name || sec.title || `Section #${sidx + 1}`;
                    const sContent = sec.content || sec.text || "";
                    const tok = Math.max(10, Math.round((sContent.length || 350) / 3.5));
                    const palette = ["#6366f1", "#818cf8", "#a78bfa", "#c084fc", "#e879f9", "#f472b6", "#fb7185", "#9333ea", "#7c3aed", "#6d28d9", "#5b21b6", "#4c1d95", "#8b5cf6", "#a855f7", "#d946ef"];
                    systemPromptSlices.push({
                        name: sName,
                        tokens: tok,
                        color: palette[sidx % palette.length],
                    });
                });
            }

            if (systemPromptSlices.length === 0) {
                systemPromptSlices = [
                    { name: "Identity", tokens: Math.round(sysPromptTok * 0.15), color: "#6366f1" },
                    { name: "Sandbox", tokens: Math.round(sysPromptTok * 0.05), color: "#818cf8" },
                    { name: "Artifacts", tokens: Math.round(sysPromptTok * 0.08), color: "#a78bfa" },
                    { name: "Transcript", tokens: Math.round(sysPromptTok * 0.07), color: "#c084fc" },
                    { name: "Guidelines", tokens: Math.round(sysPromptTok * 0.12), color: "#e879f9" },
                    { name: "Style", tokens: Math.round(sysPromptTok * 0.05), color: "#f472b6" },
                    { name: "Commands", tokens: Math.round(sysPromptTok * 0.06), color: "#fb7185" },
                    { name: "Messaging", tokens: Math.round(sysPromptTok * 0.07), color: "#9333ea" },
                    { name: "MCP Servers", tokens: Math.round(sysPromptTok * 0.05), color: "#7c3aed" },
                    { name: "Subagents", tokens: Math.round(sysPromptTok * 0.06), color: "#6d28d9" },
                    { name: "User Rules", tokens: Math.round(sysPromptTok * 0.08), color: "#5b21b6" },
                    { name: "Skills", tokens: Math.round(sysPromptTok * 0.08), color: "#4c1d95" },
                    { name: "Plugins", tokens: Math.round(sysPromptTok * 0.04), color: "#8b5cf6" },
                    { name: "UserInfo", tokens: Math.max(10, sysPromptTok - Math.round(sysPromptTok * 0.96)), color: "#a855f7" },
                ];
            } else {
                const sliceSum = systemPromptSlices.reduce((acc, sl) => acc + sl.tokens, 0);
                if (sliceSum > 0) {
                    systemPromptSlices.forEach(sl => {
                        sl.tokens = Math.max(1, Math.round((sl.tokens / sliceSum) * sysPromptTok));
                    });
                }
            }

            const toolCatMap = {
                filesystem: { name: "Filesystem Tools", color: "#06b6d4", tokens: 0, tools: ["read_file", "write_file", "edit_file", "replace_file_content", "write_to_file", "view_file"] },
                terminal: { name: "Terminal Tools", color: "#0891b2", tokens: 0, tools: ["run_command", "bash"] },
                subagents: { name: "Subagents", color: "#0e7490", tokens: 0, tools: ["invoke_subagent", "define_subagent", "manage_subagents", "send_message"] },
                automation: { name: "Automation & Tasks", color: "#14b8a6", tokens: 0, tools: ["schedule", "manage_task", "call_mcp_tool", "list_resources", "read_resource", "search_web", "search_marketplace", "list_plugin_accounts", "ask_question"] },
            };

            if (rawChatTools && rawChatTools.length > 0) {
                rawChatTools.forEach(t => {
                    const tName = (t.name || "").toLowerCase();
                    const tok = Math.max(15, Math.round(JSON.stringify(t).length / 3.5));
                    if (toolCatMap.filesystem.tools.some(k => tName.includes(k))) {
                        toolCatMap.filesystem.tokens += tok;
                    } else if (toolCatMap.terminal.tools.some(k => tName.includes(k))) {
                        toolCatMap.terminal.tokens += tok;
                    } else if (toolCatMap.subagents.tools.some(k => tName.includes(k))) {
                        toolCatMap.subagents.tokens += tok;
                    } else {
                        toolCatMap.automation.tokens += tok;
                    }
                });
            }

            let toolDefSlices = [
                { name: "Filesystem Tools", tokens: toolCatMap.filesystem.tokens || Math.round(toolDefsTok * 0.25), color: "#06b6d4" },
                { name: "Terminal Tools", tokens: toolCatMap.terminal.tokens || Math.round(toolDefsTok * 0.20), color: "#0891b2" },
                { name: "Subagents", tokens: toolCatMap.subagents.tokens || Math.round(toolDefsTok * 0.25), color: "#0e7490" },
                { name: "Automation & Tasks", tokens: toolCatMap.automation.tokens || Math.max(10, toolDefsTok - Math.round(toolDefsTok * 0.70)), color: "#14b8a6" },
            ];
            const toolSliceSum = toolDefSlices.reduce((acc, sl) => acc + sl.tokens, 0);
            if (toolSliceSum > 0) {
                toolDefSlices.forEach(sl => {
                    sl.tokens = Math.max(1, Math.round((sl.tokens / toolSliceSum) * toolDefsTok));
                });
            }

            tokenBreakdown.system_prompt_slices = systemPromptSlices;
            tokenBreakdown.tool_def_slices = toolDefSlices;

            const subagents = [];
            const subagentInfos = [];
            steps.forEach(s => {
                (s.tool_calls || []).forEach(tc => {
                    const combined = JSON.stringify(tc.args || {}) + " " + String(tc.output || "");
                    const uuids = combined.match(/[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}/g) || [];
                    uuids.forEach(uid => {
                        if (uid !== convoId && !subagents.includes(uid)) {
                            subagents.push(uid);
                            subagentInfos.push({
                                id: uid,
                                name: (tc.args && (tc.args.name || tc.args.agent_role)) || `Subagent ${uid.slice(0, 8)}`,
                                summary: String((tc.args && (tc.args.objective || tc.args.prompt)) || "").slice(0, 80),
                            });
                        }
                    });
                });
            });

            let convoSummary = `Session ${convoId.slice(0, 8)}`;
            const firstUserStep = steps.find(s => s.type === "USER_INPUT");
            if (firstUserStep && firstUserStep.content) {
                convoSummary = String(firstUserStep.content).slice(0, 80).replace(/\r?\n/g, " ");
            }

            const data = {
                conversation_id: convoId,
                summary: convoSummary,
                steps: steps,
                step_count: steps.length,
                epochs: epochs,
                parent_id: null,
                subagents: subagents,
                subagent_infos: subagentInfos,
                subagent_trajectories: {},
                total_tokens: totalTokens,
                max_context_tokens: maxContextTokens,
                cache_tokens: 0,
                token_breakdown: tokenBreakdown,
                system_prompt_slices: systemPromptSlices,
                tool_def_slices: toolDefSlices,
            };

            const state = window.__agyis_hud_state;
            if (state) {
                state.rootData = data;
                state.currentData = data;
                state.convoId = convoId;
                syncToLatestState(state);
                state.subagentsDropdownOpen = false;
                renderHud();
                const selEl = document.querySelector(`.agyis-step-grid-item[data-index="${state.selectedIndex}"]`);
                if (selEl) selEl.scrollIntoView({ block: "nearest" });
            }
            return data;
        } catch (err) {
            console.warn("[agyis] ConnectRPC trajectory fetch failed, using fallback:", err);
            if (__PAYLOAD__ && __PAYLOAD__.initialData) {
                const fallbackData = __PAYLOAD__.initialData;
                const state = window.__agyis_hud_state;
                if (state) {
                    state.rootData = fallbackData;
                    state.currentData = fallbackData;
                    state.convoId = fallbackData.conversation_id || convoId;
                    syncToLatestState(state);
                    state.subagentsDropdownOpen = false;
                    renderHud();
                    const selEl = document.querySelector(`.agyis-step-grid-item[data-index="${state.selectedIndex}"]`);
                    if (selEl) selEl.scrollIntoView({ block: "nearest" });
                }
                return fallbackData;
            }
            return null;
        }
    };

    function formatBytes(bytes) {
        if (!bytes || bytes <= 0) return "0 B";
        const k = 1024;
        const dm = 1;
        const sizes = ["B", "KB", "MB", "GB"];
        const i = Math.floor(Math.log(bytes) / Math.log(k));
        return parseFloat((bytes / Math.pow(k, i)).toFixed(dm)) + " " + sizes[i];
    }

    function renderMarkdownPreview(rawText) {
        if (!rawText) return "<div style='color: #71717a;'>No preview content</div>";

        // Auto-formatted JSON detection
        let trimmed = String(rawText).trim();
        if ((trimmed.startsWith("{") && trimmed.endsWith("}")) || (trimmed.startsWith("[") && trimmed.endsWith("]"))) {
            try {
                const parsedJson = JSON.parse(trimmed);
                trimmed = JSON.stringify(parsedJson, null, 2);
                rawText = "```json\n" + trimmed + "\n```";
            } catch (_) {}
        }

        let escaped = String(rawText).replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");

        // Code blocks with syntax badge and copy button
        escaped = escaped.replace(/```([a-zA-Z0-9_-]*)\n([\s\S]*?)```/g, (m, lang, code) => {
            const badge = lang ? `<span style="font-size: 10px; color: #a1a1aa; font-family: monospace; text-transform: uppercase;">${lang}</span>` : "<span></span>";
            const codeId = "code-" + Math.random().toString(36).substr(2, 9);
            return `
                <div class="agyis-codeblock-wrap">
                    <div style="display: flex; justify-content: space-between; align-items: center; padding: 4px 10px; background: #141416; border-bottom: 1px solid #27272a; border-top-left-radius: 6px; border-top-right-radius: 6px;">
                        ${badge}
                        <button class="agyis-hud-btn agyis-copy-code-btn" data-code-id="${codeId}" style="padding: 2px 6px; font-size: 10px;">📋 Copy</button>
                    </div>
                    <pre id="${codeId}" class="agyis-codeblock" style="border: none; border-radius: 0 0 6px 6px; margin: 0; padding: 10px;"><code class="language-${lang || 'none'}">${code.trim()}</code></pre>
                </div>
            `;
        });

        // Inline code
        escaped = escaped.replace(/`([^`]+)`/g, "<code style='background: #27272a; padding: 2px 4px; border-radius: 4px; font-family: monospace;'>$1</code>");

        // GitHub alerts (> [!NOTE], > [!WARNING], > [!TIP], > [!IMPORTANT], > [!CAUTION])
        escaped = escaped.replace(/(?:^|\n)&gt;\s*\[!(NOTE|WARNING|TIP|IMPORTANT|CAUTION)\]([\s\S]*?)(?=(?:\n\n|\n&gt;\s*\[!|$))/gi, (m, alertType, body) => {
            const typeUpper = alertType.toUpperCase();
            let alertColor = "#3b82f6";
            let alertIcon = "ℹ️";
            if (typeUpper === "WARNING") { alertColor = "#f59e0b"; alertIcon = "⚠️"; }
            else if (typeUpper === "TIP") { alertColor = "#10b981"; alertIcon = "💡"; }
            else if (typeUpper === "IMPORTANT") { alertColor = "#a855f7"; alertIcon = "❗"; }
            else if (typeUpper === "CAUTION") { alertColor = "#ef4444"; alertIcon = "🛑"; }

            const alertContent = body.replace(/^\s*&gt;\s?/gm, "").trim().replace(/\n/g, "<br>");
            return `
                <div class="agyis-github-alert" style="border: 1px solid ${alertColor}; border-left: 4px solid ${alertColor};">
                    <div style="display: flex; align-items: center; gap: 6px; font-weight: 700; font-size: 11px; color: ${alertColor}; margin-bottom: 4px;">
                        <span>${alertIcon}</span>
                        <span>${typeUpper}</span>
                    </div>
                    <div style="font-size: 11px; color: #e4e4e7; line-height: 1.5;">${alertContent}</div>
                </div>
            `;
        });

        // XML Callouts (&lt;USER_REQUEST&gt;, &lt;CONTEXT_SUMMARY&gt;, &lt;SYSTEM_MESSAGE&gt;)
        escaped = escaped.replace(/&lt;([A-Z0-9_\-]+)&gt;([\s\S]*?)&lt;\/\1&gt;/g, (m, tag, body) => {
            let tagColor = "#f59e0b";
            let tagIcon = "📌";
            if (tag === "USER_REQUEST") { tagColor = "#3b82f6"; tagIcon = "👤"; }
            else if (tag === "CONTEXT_SUMMARY" || tag === "SUMMARY") { tagColor = "#10b981"; tagIcon = "🧠"; }
            else if (tag === "SYSTEM_MESSAGE") { tagColor = "#a855f7"; tagIcon = "⚙️"; }

            const content = body.trim().replace(/\n/g, "<br>");
            return `
                <div class="agyis-xml-callout" style="border: 1px solid ${tagColor}; border-left: 4px solid ${tagColor};">
                    <div style="display: flex; align-items: center; gap: 6px; font-weight: 700; font-size: 11px; color: ${tagColor}; margin-bottom: 4px; text-transform: uppercase;">
                        <span>${tagIcon}</span>
                        <span>&lt;${tag}&gt;</span>
                    </div>
                    <div style="font-size: 11px; color: #e4e4e7; line-height: 1.5;">${content}</div>
                </div>
            `;
        });

        // Headings (#, ##, ###)
        escaped = escaped.replace(/(?:^|\n)###\s+([^\n]+)/g, '<h3 style="font-size: 12px; font-weight: 700; color: #fbbf24; margin: 8px 0 4px 0;">$1</h3>');
        escaped = escaped.replace(/(?:^|\n)##\s+([^\n]+)/g, '<h2 style="font-size: 13px; font-weight: 700; color: #f59e0b; margin: 10px 0 6px 0;">$1</h2>');
        escaped = escaped.replace(/(?:^|\n)#\s+([^\n]+)/g, '<h1 style="font-size: 14px; font-weight: 700; color: #f59e0b; margin: 12px 0 8px 0;">$1</h1>');

        // Bold and Italic
        escaped = escaped.replace(/\*\*([^*]+)\*\*/g, '<strong style="color: #f4f4f5;">$1</strong>');
        escaped = escaped.replace(/\*([^*]+)\*/g, '<em style="color: #cbd5e1;">$1</em>');

        // Lists (- or * or 1.)
        escaped = escaped.replace(/(?:^|\n)(?:[-*]|\d+\.)\s+([^\n]+)/g, '<div style="padding-left: 12px; margin: 2px 0; color: #e4e4e7;">&bull; $1</div>');

        // Simple Markdown Tables
        if (escaped.includes("|") && escaped.includes("\n")) {
            const lines = escaped.split("\n");
            let inTable = false;
            let tableHtml = "<table class='agyis-markdown-table'>";
            let remainingLines = [];

            for (let i = 0; i < lines.length; i++) {
                const line = lines[i].trim();
                if (line.startsWith("|") && line.endsWith("|")) {
                    if (!inTable) { inTable = true; }
                    const cols = line.split("|").slice(1, -1).map(c => c.trim());
                    if (cols.every(c => c.match(/^:?-+:?$/))) {
                        continue; // table header separator
                    }
                    const isTh = tableHtml.indexOf("<tr>") === -1;
                    const tag = isTh ? "th" : "td";
                    tableHtml += `<tr>${cols.map(c => `<${tag}>${c}</${tag}>`).join("")}</tr>`;
                } else {
                    if (inTable) {
                        inTable = false;
                        tableHtml += "</table>";
                        remainingLines.push(tableHtml);
                    }
                    remainingLines.push(line);
                }
            }
            if (inTable) { tableHtml += "</table>"; remainingLines.push(tableHtml); }
            escaped = remainingLines.join("<br>");
        } else {
            escaped = escaped.replace(/\n/g, "<br>");
        }

        return `<div class="agyis-markdown-body" style="word-break: break-word;">${escaped}</div>`;
    }

    function renderHud() {
        const state = window.__agyis_hud_state;
        const cur = state.currentData;
        const steps = cur.steps || [];
        const currentStep = steps[state.selectedIndex] || null;

        // Filter and Search Matching
        const q = (state.filterQuery || "").trim().toLowerCase();
        const filteredIndices = [];
        for (let i = 0; i < steps.length; i++) {
            const s = steps[i];
            if (!q) {
                filteredIndices.push(i);
                continue;
            }
            const typeStr = (s.type || "").toLowerCase();
            const contentStr = (s.content || "").toLowerCase();
            const thinkStr = (s.thinking || "").toLowerCase();
            const toolStr = (s.tool_calls || []).map(t => (t.name || "") + " " + JSON.stringify(t.args || {})).join(" ").toLowerCase();
            if (typeStr.includes(q) || contentStr.includes(q) || thinkStr.includes(q) || toolStr.includes(q)) {
                filteredIndices.push(i);
            }
        }
        state.searchMatchIndices = filteredIndices;

        // Epoch Detection & Slicing (PSL-INV-010 / ADR-014)
        const epochs = (cur.epochs && cur.epochs.length > 0) ? cur.epochs : [{
            epoch_index: 0,
            start_index: 0,
            end_index: Math.max(0, steps.length - 1),
            step_count: steps.length,
            has_checkpoint: false,
            summary: "Initial Trajectory",
        }];

        if (state.activeEpochIndex === undefined || state.activeEpochIndex < 0 || state.activeEpochIndex >= epochs.length) {
            const foundEp = epochs.find(ep => state.selectedIndex >= ep.start_index && state.selectedIndex <= ep.end_index);
            state.activeEpochIndex = foundEp ? foundEp.epoch_index : (epochs.length - 1);
        }

        const activeEpoch = epochs[state.activeEpochIndex] || epochs[epochs.length - 1];
        const epochSteps = steps.slice(activeEpoch.start_index, activeEpoch.end_index + 1);

        // Context Window Bar Calculations (Dynamic 4-Row 64k Scoping)
        const maxTokens = cur.max_context_tokens || 256000;
        const breakdown = cur.token_breakdown || {
            system_prompt: 3800,
            tool_defs: 3200,
            checkpoint: 0,
            user: 0,
            model: 0,
            tool: 0,
            system: 0,
        };

        const segments = [];
        const sysSlices = cur.system_prompt_slices || (breakdown.system_prompt_slices) || [];
        if (sysSlices.length > 0) {
            sysSlices.forEach((sl, sidx) => {
                if ((sl.tokens || 0) > 0) {
                    segments.push({
                        id: `sys-${(sl.name || 'sec').toLowerCase().replace(/[^a-z0-9]/g, '-')}-${sidx}`,
                        type: "system_prompt",
                        label: `System: ${sl.name}`,
                        tokens: sl.tokens,
                        color: sl.color || "#6366f1",
                        colorKey: "bg-indigo-500",
                        titleColorClass: "text-indigo-400",
                        tooltipContent: `${sl.name} (${sl.tokens.toLocaleString()} tokens)`,
                    });
                }
            });
        } else if ((breakdown.system_prompt || 0) > 0) {
            segments.push({
                id: "sys-prompt",
                type: "system_prompt",
                label: "System Prompt",
                tokens: breakdown.system_prompt,
                color: "#6366f1",
                colorKey: "bg-indigo-500",
                titleColorClass: "text-indigo-400",
                tooltipContent: "System instructions and role configuration",
            });
        }

        const toolSlices = cur.tool_def_slices || (breakdown.tool_def_slices) || [];
        if (toolSlices.length > 0) {
            toolSlices.forEach((sl, tidx) => {
                if ((sl.tokens || 0) > 0) {
                    segments.push({
                        id: `tool-${(sl.name || 'tool').toLowerCase().replace(/[^a-z0-9]/g, '-')}-${tidx}`,
                        type: "tool_definition",
                        label: `Tools: ${sl.name}`,
                        tokens: sl.tokens,
                        color: sl.color || "#06b6d4",
                        colorKey: "bg-cyan-500",
                        titleColorClass: "text-cyan-400",
                        tooltipContent: `${sl.name} (${sl.tokens.toLocaleString()} tokens)`,
                    });
                }
            });
        } else if ((breakdown.tool_defs || 0) > 0) {
            segments.push({
                id: "tool-defs",
                type: "tool_definition",
                label: "Tool Defs",
                tokens: breakdown.tool_defs,
                color: "#06b6d4",
                colorKey: "bg-cyan-500",
                titleColorClass: "text-cyan-400",
                tooltipContent: "Tool definitions and schemas",
            });
        }

        let hasCheckpointInEpoch = false;
        for (let i = 0; i < epochSteps.length; i++) {
            if (epochSteps[i].type === "CHECKPOINT") {
                hasCheckpointInEpoch = true;
                break;
            }
        }
        if (!hasCheckpointInEpoch && activeEpoch.has_checkpoint && (breakdown.checkpoint || 0) > 0) {
            segments.push({
                id: "checkpoint-summary",
                type: "checkpoint",
                label: "Checkpoint",
                tokens: breakdown.checkpoint,
                color: "#16a34a",
                colorKey: "bg-green-600",
                titleColorClass: "text-green-400",
                tooltipContent: activeEpoch.summary || "Compacted context summary",
            });
        }

        if (epochSteps.length > 0) {
            epochSteps.forEach((s) => {
                const actualIdx = s.step_index !== undefined ? s.step_index : steps.indexOf(s);
                const sTok = s.tokens || Math.round((s.size_bytes || 100) / 3.5);
                let segColor = "#3b82f6";
                let segColorKey = "bg-blue-600";
                let segTitleColor = "text-blue-400";
                let segLabel = `Step #${actualIdx}: ${s.type || 'STEP'}`;

                if (s.type === "PLANNER_RESPONSE" || s.type === "MODEL_OUTPUT") {
                    segColor = "#f59e0b";
                    segColorKey = "bg-amber-600";
                    segTitleColor = "text-amber-400";
                } else if (s.type === "CHECKPOINT") {
                    segColor = "#16a34a";
                    segColorKey = "bg-green-600";
                    segTitleColor = "text-green-400";
                    segLabel = `Step #${actualIdx}: Checkpoint`;
                } else if (s.type.includes("COMMAND") || s.type.includes("TOOL") || s.type.includes("FILE") || s.type.includes("WRITE") || s.type.includes("REPLACE") || s.type.includes("SEARCH")) {
                    segColor = "#14b8a6";
                    segColorKey = "bg-teal-600";
                    segTitleColor = "text-teal-400";
                } else if (s.type === "SYSTEM") {
                    segColor = "#a855f7";
                    segColorKey = "bg-purple-600";
                    segTitleColor = "text-purple-400";
                }

                let tip = s.thinking ? s.thinking : (s.content ? s.content : "");
                if (s.type === "CHECKPOINT") {
                    tip = s.compaction_summary || s.summary || s.sessionSummary || tip || "Checkpoint";
                }
                if (!tip && (s.tool_calls || []).length > 0) {
                    tip = s.tool_calls.map(tc => tc.name).join(", ");
                }
                tip = tip.replace(/\n/g, " ").slice(0, 160);

                segments.push({
                    id: `step-${actualIdx}`,
                    type: "step",
                    stepIndex: actualIdx,
                    label: segLabel,
                    tokens: sTok,
                    color: segColor,
                    colorKey: segColorKey,
                    titleColorClass: segTitleColor,
                    tooltipContent: tip,
                });
            });
        }

        const rawSegmentsSum = segments.reduce((acc, seg) => acc + (seg.tokens || 0), 0);
        let activeTokensSum = segments.reduce((acc, seg) => acc + (seg.tokens || 0), 0);
        activeTokensSum = Math.max(cur.total_tokens || 0, activeTokensSum);
        const totalTokens = Math.max(cur.total_tokens || 0, activeTokensSum);
        const ROW_CAPACITY = 64000;
        const rowCount = Math.min(4, Math.max(1, Math.ceil(activeTokensSum / ROW_CAPACITY)));
        const totalActiveCapacity = rowCount * ROW_CAPACITY;

        const scaleFactor = (cur.total_tokens > 0 && rawSegmentsSum > 0 && cur.total_tokens > rawSegmentsSum)
            ? (activeTokensSum / rawSegmentsSum)
            : 1.0;

        if (rawSegmentsSum === 0 && activeTokensSum > 0) {
            segments.push({
                id: "context-gap",
                type: "system",
                label: "Active Context",
                tokens: activeTokensSum,
                color: "#6366f1",
                colorKey: "bg-indigo-500",
                titleColorClass: "text-indigo-400",
                tooltipContent: `Active Context (${activeTokensSum.toLocaleString()} tokens)`,
            });
        }

        const rows = [];
        for (let r = 0; r < rowCount; r++) rows.push([]);

        let tCursor = 0;
        segments.forEach((seg, sIdx) => {
            let segTokens = Math.max(0, Math.round((seg.tokens || 0) * scaleFactor));
            if (scaleFactor > 1.0 && sIdx === segments.length - 1) {
                segTokens = Math.max(0, activeTokensSum - tCursor);
            }
            const segStart = tCursor;
            const segEnd = tCursor + segTokens;
            tCursor = segEnd;

            let sliceCursor = segStart;
            while (sliceCursor < segEnd) {
                const r = Math.min(rowCount - 1, Math.floor(sliceCursor / ROW_CAPACITY));
                const rowEndTokens = (r + 1) * ROW_CAPACITY;
                const sliceEnd = Math.min(segEnd, rowEndTokens);
                const sliceTokens = sliceEnd - sliceCursor;

                const startFraction = (sliceCursor - r * ROW_CAPACITY) / ROW_CAPACITY;
                const widthFraction = sliceTokens / ROW_CAPACITY;

                rows[r].push({
                    segment: seg,
                    startFraction: startFraction,
                    widthFraction: widthFraction,
                    sliceTokens: sliceTokens,
                });

                sliceCursor = sliceEnd;
                if (r === rowCount - 1 && sliceEnd >= rowEndTokens) {
                    break;
                }
            }
        });

        // Unused capacity in active rows up to totalActiveCapacity
        let uCursor = Math.min(tCursor, totalActiveCapacity);
        while (uCursor < totalActiveCapacity) {
            const r = Math.min(rowCount - 1, Math.floor(uCursor / ROW_CAPACITY));
            const rowEndTokens = (r + 1) * ROW_CAPACITY;
            const sliceEnd = Math.min(totalActiveCapacity, rowEndTokens);
            const sliceTokens = sliceEnd - uCursor;

            const startFraction = (uCursor - r * ROW_CAPACITY) / ROW_CAPACITY;
            const widthFraction = sliceTokens / ROW_CAPACITY;

            rows[r].push({
                segment: null,
                startFraction: startFraction,
                widthFraction: widthFraction,
                sliceTokens: sliceTokens,
            });

            uCursor = sliceEnd;
        }

        let barSegmentsHtml = "";
        rows.forEach((row, rIdx) => {
            let cellsHtml = "";
            row.forEach(cell => {
                const seg = cell.segment;
                const isUnused = seg === null;
                const isSelected = (!isUnused && seg.stepIndex !== undefined && seg.stepIndex === state.selectedIndex);
                const cellClass = isUnused ? "context-cell-unused" : "";
                const selClass = isSelected ? "context-cell-selected" : "";
                const colorStyle = isUnused ? "background: #27272a;" : `background: ${seg.color};`;
                const borderRight = isUnused ? "" : "border-right: 1px solid rgba(0, 0, 0, 0.35);";
                const ariaLabel = isUnused ? `Unused capacity: ${cell.sliceTokens.toLocaleString()} tokens` : `${seg.label}: ${seg.tokens.toLocaleString()} tokens`;
                const leftPct = (cell.startFraction * 100).toFixed(4);
                const widthPct = (cell.widthFraction * 100).toFixed(4);
                const stepIdxAttr = (!isUnused && seg.stepIndex !== undefined) ? `data-step-index="${seg.stepIndex}"` : "";

                cellsHtml += `
                    <button type="button"
                            class="agyis-context-segment ${cellClass} ${selClass}"
                            ${stepIdxAttr}
                            data-seg-id="${isUnused ? 'unused' : seg.id}"
                            data-seg-name="${isUnused ? 'Unused Capacity' : seg.label}"
                            data-seg-tokens="${isUnused ? cell.sliceTokens : seg.tokens}"
                            data-seg-pct="${(((isUnused ? cell.sliceTokens : seg.tokens) / maxTokens) * 100).toFixed(1)}"
                            data-tooltip="${isUnused ? '' : (seg.tooltipContent || '').replace(/"/g, '&quot;')}"
                            aria-label="${ariaLabel}"
                            style="position: absolute; top: 0; bottom: 0; left: ${leftPct}%; width: ${widthPct}%; ${colorStyle} ${borderRight}">
                    </button>
                `;
            });
            barSegmentsHtml += `
                <div class="agyis-context-row-wrap" style="display: flex; align-items: center; gap: 8px;">
                    <span class="agyis-context-row-label" style="font-family: ui-monospace, monospace; font-size: 10px; color: #a1a1aa; width: 34px; text-align: right; flex-shrink: 0; user-select: none;">${rIdx * 64}k</span>
                    <div class="agyis-context-row-track" style="flex: 1; height: 18px; position: relative; background: #27272a; border-radius: 4px; overflow: hidden; border: 1px solid #3f3f46;">
                        ${cellsHtml}
                    </div>
                </div>
            `;
        });

        // Subagents Map & Dropdown
        const subagents = cur.subagents || [];
        const subagentInfos = cur.subagent_infos || [];
        const isChildView = Boolean(cur.parent_id);

        let subagentsDropdownHtml = "";
        if (subagents.length > 0) {
            const items = subagents.map((sid, idx) => {
                const info = subagentInfos.find(si => si.id === sid) || { name: `Subagent #${idx + 1}`, summary: sid };
                return `
                    <div class="agyis-subagent-item" data-sub-id="${sid}" style="padding: 6px 10px; cursor: pointer; border-bottom: 1px solid #27272a; transition: background 0.15s;" onmouseover="this.style.background='#27272a'" onmouseout="this.style.background='transparent'">
                        <div style="font-weight: 600; color: #c084fc; font-size: 11px;">${info.name}</div>
                        <div style="font-size: 10px; color: #a1a1aa; font-family: monospace;">${sid.slice(0, 16)}...</div>
                    </div>
                `;
            }).join("");

            subagentsDropdownHtml = `
                <div style="position: relative;">
                    <button id="agyis-subagents-dropdown-toggle" class="agyis-hud-pill agyis-hud-pill-purple" style="cursor: pointer;">
                        [ ${subagents.length} Child Subagent${subagents.length === 1 ? '' : 's'} ▾ ]
                    </button>
                    <div id="agyis-subagents-menu" style="display: ${state.subagentsDropdownOpen ? 'block' : 'none'}; position: absolute; top: 100%; left: 0; margin-top: 4px; background: #18181b; border: 1px solid #3f3f46; border-radius: 6px; box-shadow: 0 10px 25px rgba(0,0,0,0.8); z-index: 200; min-width: 240px; max-height: 220px; overflow-y: auto;">
                        ${items}
                    </div>
                </div>
            `;
        }

        // History Table Grid Rows with 50-step pagination ('rmc' Parity)
        const pageSize = 50;
        const totalFiltered = filteredIndices.length;
        const totalPages = Math.max(1, Math.ceil(totalFiltered / pageSize));
        if (state.tablePage === undefined || state.tablePage < 0) state.tablePage = 0;
        if (state.tablePage >= totalPages) state.tablePage = totalPages - 1;

        const pageStart = state.tablePage * pageSize;
        const pageEnd = Math.min(totalFiltered, pageStart + pageSize);
        const pagedIndices = filteredIndices.slice(pageStart, pageEnd);

        const gridRowsHtml = pagedIndices.map(idx => {
            const s = steps[idx];
            const isSel = idx === state.selectedIndex;
            const type = s.type || "STEP";
            let pillClass = "agyis-hud-pill-blue";
            if (type === "PLANNER_RESPONSE") pillClass = "agyis-hud-pill-amber";
            else if (type === "CHECKPOINT") pillClass = "agyis-hud-pill-green";
            else if (type.includes("COMMAND") || type.includes("TOOL")) pillClass = "agyis-hud-pill-teal";
            else if (type.includes("FILE") || type.includes("WRITE") || type.includes("REPLACE")) pillClass = "agyis-hud-pill-green";
            else if (type === "INVOKE_SUBAGENT") pillClass = "agyis-hud-pill-purple";
            else if (type === "SYSTEM") pillClass = "agyis-hud-pill-zinc";

            const status = s.status || "DONE";
            let statusPillClass = "agyis-hud-pill-green";
            if (status === "ERROR") statusPillClass = "agyis-hud-pill-red";
            else if (status === "RUNNING") statusPillClass = "agyis-hud-pill-blue";
            else if (status === "WAITING") statusPillClass = "agyis-hud-pill-amber";

            let details = s.thinking ? s.thinking : (s.content ? s.content : "");
            if (type === "CHECKPOINT") {
                details = s.compaction_summary || s.summary || s.sessionSummary || details || "Checkpoint";
            }
            if (!details && (s.tool_calls || []).length > 0) {
                details = s.tool_calls.map(tc => tc.name + "(" + JSON.stringify(tc.args || {}) + ")").join("; ");
            }
            details = details.replace(/\n/g, " ").slice(0, 160).replace(/</g, "&lt;").replace(/>/g, "&gt;");

            const sizeStr = formatBytes(s.size_bytes);
            const tokensStr = (s.tokens || 0).toLocaleString();

            return `
                <div class="agyis-step-grid-row agyis-step-grid-item ${isSel ? 'selected' : ''}" data-index="${idx}">
                    <div style="color: #71717a;">${s.exec_index || 1}</div>
                    <div style="color: #71717a;">${s.inv_index || 1}</div>
                    <div style="font-weight: 700;">#${s.step_index ?? idx}</div>
                    <div><span class="agyis-hud-pill ${pillClass}">${type}</span></div>
                    <div style="color: #a1a1aa; overflow: hidden; text-overflow: ellipsis; white-space: nowrap;">${details || "—"}</div>
                    <div><span class="agyis-hud-pill ${statusPillClass}">${status}</span></div>
                    <div style="text-align: right; color: #cbd5e1;">${tokensStr}</div>
                    <div style="text-align: right; color: #71717a;">${sizeStr}</div>
                </div>
            `;
        }).join("");

        // Timeline View Body ('lvc' Parity)
        const timelineCardsHtml = steps.map((s, idx) => {
            const isSel = idx === state.selectedIndex;
            const type = s.type || "STEP";
            let pillClass = "agyis-hud-pill-blue";
            if (type === "PLANNER_RESPONSE") pillClass = "agyis-hud-pill-amber";
            else if (type === "CHECKPOINT") pillClass = "agyis-hud-pill-green";
            else if (type.includes("COMMAND") || type.includes("TOOL")) pillClass = "agyis-hud-pill-teal";
            else if (type.includes("FILE") || type.includes("WRITE") || type.includes("REPLACE")) pillClass = "agyis-hud-pill-green";
            else if (type === "INVOKE_SUBAGENT") pillClass = "agyis-hud-pill-purple";
            else if (type === "SYSTEM") pillClass = "agyis-hud-pill-zinc";

            let details = s.thinking ? s.thinking : (s.content ? s.content : "");
            if (type === "CHECKPOINT") {
                details = s.compaction_summary || s.summary || s.sessionSummary || details || "Checkpoint";
            }
            if (!details && (s.tool_calls || []).length > 0) {
                details = s.tool_calls.map(tc => tc.name).join("; ");
            }
            details = details.replace(/\n/g, " ").slice(0, 140).replace(/</g, "&lt;").replace(/>/g, "&gt;");

            const ttftSec = ((s.thinking_duration_ms || 0) / 1000).toFixed(2);
            const streamSec = ((s.streaming_duration_ms || 0) / 1000).toFixed(2);
            const totalSec = ((s.total_duration_ms || 0) / 1000).toFixed(2);
            const totalMs = Math.max(1, (s.total_duration_ms || 1));
            const ttftPct = Math.round(((s.thinking_duration_ms || 0) / totalMs) * 100);
            const streamPct = 100 - ttftPct;

            return `
                <div class="agyis-timeline-card ${isSel ? 'selected' : ''}" data-index="${idx}">
                    <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 6px;">
                        <div style="display: flex; align-items: center; gap: 8px;">
                            <span style="font-weight: 700; color: #fbbf24;">#${s.step_index ?? idx}</span>
                            <span class="agyis-hud-pill ${pillClass}">${type}</span>
                        </div>
                        <span style="font-size: 10px; color: #a1a1aa;">${(s.tokens || 0).toLocaleString()} tok &bull; ${formatBytes(s.size_bytes)}</span>
                    </div>
                    <div style="font-size: 11px; color: #cbd5e1; margin-bottom: 6px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap;">
                        ${details || "—"}
                    </div>
                    <div style="display: flex; justify-content: space-between; font-size: 10px; color: #71717a; margin-bottom: 2px;">
                        <span>TTFT: ${ttftSec}s | Stream: ${streamSec}s</span>
                        <span style="font-weight: 700;">${totalSec}s</span>
                    </div>
                    <div style="height: 4px; background: #27272a; border-radius: 2px; overflow: hidden; display: flex;">
                        <div style="width: ${ttftPct}%; background: #f59e0b;"></div>
                        <div style="width: ${streamPct}%; background: #6366f1;"></div>
                    </div>
                </div>
            `;
        }).join("");

        // Step Inspector Body
        let inspectorContentHtml = "";
        let timingBarHtml = "";
        if (currentStep) {
            const isModelStep = (currentStep.type === "PLANNER_RESPONSE" || currentStep.type === "MODEL_OUTPUT");
            const totalDurationMs = currentStep.total_duration_ms || 0;
            if (isModelStep && totalDurationMs > 0) {
                const ttftSec = ((currentStep.thinking_duration_ms || 0) / 1000).toFixed(2);
                const streamSec = ((currentStep.streaming_duration_ms || 0) / 1000).toFixed(2);
                const totalSec = (totalDurationMs / 1000).toFixed(2);
                const totalMs = Math.max(1, totalDurationMs);
                const ttftPct = Math.round(((currentStep.thinking_duration_ms || 0) / totalMs) * 100);
                const streamPct = 100 - ttftPct;

                timingBarHtml = `
                    <div class="agyis-timing-bar-wrap">
                        <div style="display: flex; justify-content: space-between; font-size: 11px;">
                            <span><b style="color: #f59e0b;">TTFT:</b> ${ttftSec}s (${ttftPct}%) &nbsp;|&nbsp; <b style="color: #6366f1;">STREAMING:</b> ${streamSec}s (${streamPct}%)</span>
                            <span style="font-weight: 700; color: #cbd5e1;">Total: ${totalSec}s</span>
                        </div>
                        <div class="agyis-timing-bar">
                            <div style="width: ${ttftPct}%; background: #f59e0b;" title="TTFT / Thinking"></div>
                            <div style="width: ${streamPct}%; background: #6366f1;" title="Streaming / Output"></div>
                        </div>
                    </div>
                `;
            }

            // Tool calls summary strip
            let toolStripHtml = "";
            const tCalls = currentStep.tool_calls || [];
            if (tCalls.length > 0) {
                toolStripHtml = `
                    <div style="display: flex; gap: 6px; flex-wrap: wrap; margin-bottom: 10px; align-items: center;">
                        <span style="font-size: 10px; font-weight: 700; color: #a1a1aa; text-transform: uppercase;">Tool Calls:</span>
                        ${tCalls.map(tc => `
                            <span class="agyis-hud-pill agyis-hud-pill-teal" style="font-family: monospace; font-size: 10px;">
                                ${tc.name || 'tool'} <span style="opacity: 0.7;">(${tc.status || 'DONE'})</span>
                            </span>
                        `).join("")}
                    </div>
                `;
            }

            // Dedicated collapsible thinking disclosure block
            let thinkingBlockHtml = "";
            if (currentStep.thinking) {
                const tLen = currentStep.thinking.length;
                const tMs = currentStep.thinking_duration_ms || 0;
                thinkingBlockHtml = `
                    <details class="agyis-thinking-block" open>
                        <summary style="cursor: pointer; font-weight: 600; color: #fbbf24; font-size: 11px; user-select: none;">
                            💭 Thought Process (${tLen.toLocaleString()} chars &bull; ${tMs}ms)
                        </summary>
                        <div style="margin-top: 8px; font-size: 11px; color: #fef3c7; line-height: 1.5; font-family: ui-monospace, monospace; max-height: 320px; overflow-y: auto;">
                            ${renderMarkdownPreview(currentStep.thinking)}
                        </div>
                    </details>
                `;
            }

            if (state.activeTab === "step") {
                const cType = currentStep.type || "STEP";
                let stepBodyHtml = "";

                if (cType === "RUN_COMMAND" || currentStep.command !== undefined) {
                    const cmd = currentStep.command || (currentStep.tool_calls?.[0]?.args?.CommandLine || currentStep.tool_calls?.[0]?.args?.command || "");
                    const exitCode = currentStep.exitCode !== undefined ? currentStep.exitCode : (currentStep.tool_calls?.[0]?.args?.exitCode ?? 0);
                    const exitBadgeClass = exitCode === 0 ? "agyis-hud-pill-green" : "agyis-hud-pill-red";
                    const outputRaw = currentStep.output || (currentStep.tool_calls?.[0]?.output || "");
                    const cleanOutput = String(outputRaw).replace(/\u001b\[[0-9;]*[a-zA-Z]/g, '');
                    const lineCount = cleanOutput ? cleanOutput.split(/\r?\n/).length : 0;

                    stepBodyHtml = `
                        <div class="agyis-terminal-card" style="background: #141416; border: 1px solid #27272a; border-radius: 6px; overflow: hidden; margin-bottom: 10px;">
                            <div style="display: flex; justify-content: space-between; align-items: center; padding: 6px 10px; background: #1c1c1f; border-bottom: 1px solid #27272a;">
                                <div style="font-family: monospace; font-size: 11px; color: #f4f4f5; display: flex; align-items: center; gap: 6px;">
                                    <span style="color: #38bdf8;">$</span>
                                    <span>${String(cmd).replace(/</g, "&lt;").replace(/>/g, "&gt;")}</span>
                                </div>
                                <span class="agyis-hud-pill ${exitBadgeClass}">exit ${exitCode}</span>
                            </div>
                            <div style="padding: 4px 10px; font-size: 10px; color: #71717a; border-bottom: 1px solid #202023; display: flex; justify-content: space-between;">
                                <span>Terminal Output (${lineCount} lines)</span>
                                <span>${currentStep.cwd ? `cwd: ${currentStep.cwd}` : ''}</span>
                            </div>
                            <pre class="agyis-codeblock" style="border: none; margin: 0; padding: 10px; max-height: 380px; overflow-y: auto;"><code class="language-bash">${cleanOutput.replace(/</g, "&lt;").replace(/>/g, "&gt;")}</code></pre>
                        </div>
                    `;
                } else if (cType === "VIEW_FILE" || (currentStep.filePath && currentStep.fileContent !== undefined)) {
                    const fPath = currentStep.filePath || (currentStep.tool_calls?.[0]?.args?.AbsolutePath || currentStep.tool_calls?.[0]?.args?.filePath || "");
                    const fContent = currentStep.fileContent || (currentStep.tool_calls?.[0]?.output || currentStep.content || "");
                    const lineCount = fContent ? fContent.split(/\r?\n/).length : 0;

                    stepBodyHtml = `
                        <div class="agyis-file-card" style="background: #141416; border: 1px solid #27272a; border-radius: 6px; overflow: hidden; margin-bottom: 10px;">
                            <div style="display: flex; justify-content: space-between; align-items: center; padding: 6px 10px; background: #1c1c1f; border-bottom: 1px solid #27272a;">
                                <a href="file://${fPath}" target="_blank" style="font-family: monospace; font-size: 11px; color: #38bdf8; text-decoration: none;">
                                    📄 ${String(fPath).replace(/</g, "&lt;").replace(/>/g, "&gt;")}
                                </a>
                                <span style="font-size: 10px; color: #a1a1aa;">${lineCount} lines</span>
                            </div>
                            <pre class="agyis-codeblock" style="border: none; margin: 0; padding: 10px; max-height: 400px; overflow-y: auto;"><code>${String(fContent).replace(/</g, "&lt;").replace(/>/g, "&gt;")}</code></pre>
                        </div>
                    `;
                } else if (cType === "CODE_ACTION" || currentStep.diffLines !== undefined) {
                    const fPath = currentStep.filePath || (currentStep.tool_calls?.[0]?.args?.TargetFile || "");
                    const diffLines = currentStep.diffLines || [];

                    let diffHtml = "";
                    if (Array.isArray(diffLines) && diffLines.length > 0) {
                        diffHtml = diffLines.map(dl => {
                            const txt = (dl && dl.text !== undefined) ? dl.text : (typeof dl === "string" ? dl : JSON.stringify(dl));
                            const type = (dl && dl.type) ? String(dl.type).toUpperCase() : (txt.startsWith("+") ? "INSERTION" : (txt.startsWith("-") ? "DELETION" : "NORMAL"));
                            let lineBg = "transparent";
                            let lineCol = "#cbd5e1";
                            if (type === "INSERTION" || type === "ADD" || txt.startsWith("+")) {
                                lineBg = "rgba(16, 185, 129, 0.15)";
                                lineCol = "#6ee7b7";
                            } else if (type === "DELETION" || type === "DELETE" || txt.startsWith("-")) {
                                lineBg = "rgba(239, 68, 68, 0.15)";
                                lineCol = "#fca5a5";
                            }
                            return `<div style="background: ${lineBg}; color: ${lineCol}; padding: 1px 8px; font-family: monospace; font-size: 11px; white-space: pre-wrap;">${String(txt).replace(/</g, "&lt;").replace(/>/g, "&gt;")}</div>`;
                        }).join("");
                    } else {
                        diffHtml = `<div style="padding: 10px; color: #71717a; font-family: monospace; font-size: 11px;">No unified diff lines available</div>`;
                    }

                    stepBodyHtml = `
                        <div class="agyis-diff-card" style="background: #141416; border: 1px solid #27272a; border-radius: 6px; overflow: hidden; margin-bottom: 10px;">
                            <div style="display: flex; justify-content: space-between; align-items: center; padding: 6px 10px; background: #1c1c1f; border-bottom: 1px solid #27272a;">
                                <span style="font-family: monospace; font-size: 11px; color: #38bdf8;">
                                    📝 ${String(fPath).replace(/</g, "&lt;").replace(/>/g, "&gt;")}
                                </span>
                                <span class="agyis-hud-pill agyis-hud-pill-green">Unified Diff</span>
                            </div>
                            <div style="max-height: 400px; overflow-y: auto; background: #09090b;">
                                ${diffHtml}
                            </div>
                        </div>
                    `;
                } else if (cType === "INVOKE_SUBAGENT" || currentStep.subagent !== undefined) {
                    const sub = currentStep.subagent || (currentStep.tool_calls?.[0]?.args || {});
                    const typeName = sub.typeName || sub.agent_name || sub.name || "Specialist Subagent";
                    const role = sub.role || sub.agent_role || "Subagent Worker";
                    const prompt = sub.initialPrompt || sub.prompt || sub.objective || "";

                    stepBodyHtml = `
                        <div class="agyis-subagent-card" style="background: #18181b; border: 1px solid #7c3aed; border-radius: 6px; padding: 12px; margin-bottom: 10px;">
                            <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 8px;">
                                <div style="display: flex; align-items: center; gap: 8px;">
                                    <span style="font-size: 16px;">🤖</span>
                                    <span style="font-weight: 700; color: #c084fc; font-size: 12px;">${String(typeName).replace(/</g, "&lt;").replace(/>/g, "&gt;")}</span>
                                    <span class="agyis-hud-pill agyis-hud-pill-purple">${String(role).replace(/</g, "&lt;").replace(/>/g, "&gt;")}</span>
                                </div>
                                <span class="agyis-hud-pill agyis-hud-pill-green">Delegate Invoked</span>
                            </div>
                            <div style="font-size: 10px; color: #a1a1aa; margin-bottom: 4px; text-transform: uppercase;">Initial Prompt:</div>
                            <div style="background: #141416; border: 1px solid #27272a; border-radius: 4px; padding: 8px; font-family: monospace; font-size: 11px; color: #cbd5e1; max-height: 240px; overflow-y: auto;">
                                ${String(prompt).replace(/</g, "&lt;").replace(/>/g, "&gt;")}
                            </div>
                        </div>
                    `;
                } else if (cType === "CHECKPOINT") {
                    const cpSummary = currentStep.sessionSummary || currentStep.compaction_summary || currentStep.content || "";
                    const cacheRead = currentStep.cacheReadTokens || 0;
                    const inTokens = currentStep.checkpointInputTokens || currentStep.input_tokens || 0;
                    let reclaimedMetric = "Compacted Context Milestone";
                    if (cacheRead > 0 && inTokens > 0) {
                        const reclaimedPct = Math.round(((cacheRead - inTokens) / cacheRead) * 100);
                        reclaimedMetric = `Compacted ${(cacheRead/1000).toFixed(0)}k -> ${(inTokens/1000).toFixed(1)}k tokens (${reclaimedPct}% reduction)`;
                    }

                    stepBodyHtml = `
                        <div class="agyis-checkpoint-card" style="background: #142e1d; border: 1px solid #16a34a; border-radius: 6px; padding: 14px; margin-bottom: 10px;">
                            <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 10px;">
                                <div style="display: flex; align-items: center; gap: 8px;">
                                    <span class="agyis-hud-pill agyis-hud-pill-green" style="font-size: 12px; font-weight: 700;">
                                        🛡️ Compaction Checkpoint #${currentStep.checkpoint_index || currentStep.step_index || state.selectedIndex}
                                    </span>
                                </div>
                                <button id="agyis-jump-prev-epoch" class="agyis-hud-btn" style="padding: 3px 8px; font-size: 11px; background: #166534; border: 1px solid #22c55e; cursor: pointer;">
                                    Jump to Previous Epoch ◀
                                </button>
                            </div>
                            <div style="font-family: monospace; font-size: 12px; color: #86efac; margin-bottom: 10px; font-weight: 600;">
                                📊 ${reclaimedMetric}
                            </div>
                            <div style="font-size: 10px; color: #86efac; margin-bottom: 4px; text-transform: uppercase;">Compacted Session Summary:</div>
                            <div style="background: #0d1f14; border: 1px solid #166534; border-radius: 4px; padding: 10px; max-height: 280px; overflow-y: auto;">
                                ${renderMarkdownPreview(cpSummary)}
                            </div>
                        </div>
                    `;
                } else if (cType === "USER_INPUT") {
                    stepBodyHtml = `
                        <div class="agyis-user-request-card" style="background: #1e293b; border: 1px solid #3b82f6; border-left: 4px solid #3b82f6; border-radius: 6px; padding: 12px; margin-bottom: 10px;">
                            <div style="display: flex; align-items: center; gap: 6px; font-weight: 700; font-size: 11px; color: #38bdf8; margin-bottom: 6px;">
                                <span>👤</span>
                                <span>&lt;USER_REQUEST&gt;</span>
                            </div>
                            <div style="font-size: 12px; color: #f1f5f9; line-height: 1.5; white-space: pre-wrap;">${String(currentStep.content || "").replace(/</g, "&lt;").replace(/>/g, "&gt;")}</div>
                        </div>
                    `;
                } else if (cType === "PLANNER_RESPONSE" || cType === "MODEL_OUTPUT") {
                    stepBodyHtml = `
                        ${thinkingBlockHtml}
                        ${currentStep.content ? `
                            <h4 style="margin: 0 0 6px 0; font-size: 11px; color: #a1a1aa; text-transform: uppercase;">Response Preview</h4>
                            ${renderMarkdownPreview(currentStep.content)}
                        ` : ""}
                    `;
                } else if (cType.includes("SYSTEM") || cType.includes("EPHEMERAL")) {
                    stepBodyHtml = `
                        <div class="agyis-system-card" style="background: #27272a; border: 1px solid #71717a; border-left: 4px solid #a855f7; border-radius: 6px; padding: 12px; margin-bottom: 10px;">
                            <div style="display: flex; align-items: center; gap: 6px; font-weight: 700; font-size: 11px; color: #c084fc; margin-bottom: 6px;">
                                <span>⚙️</span>
                                <span>SYSTEM MESSAGE</span>
                            </div>
                            <div style="font-size: 12px; color: #e4e4e7; line-height: 1.5;">${renderMarkdownPreview(currentStep.content || "")}</div>
                        </div>
                    `;
                } else {
                    stepBodyHtml = `
                        ${toolStripHtml}
                        ${thinkingBlockHtml}
                        ${currentStep.content ? `
                            <h4 style="margin: 0 0 6px 0; font-size: 11px; color: #a1a1aa; text-transform: uppercase;">Step Preview</h4>
                            ${renderMarkdownPreview(currentStep.content)}
                        ` : ""}
                    `;
                }

                inspectorContentHtml = `
                    ${timingBarHtml}
                    ${stepBodyHtml}
                `;
            } else if (state.activeTab === "invocation") {
                const tools = currentStep.tool_calls || [];
                inspectorContentHtml = `
                    ${timingBarHtml}
                    <h4 style="margin: 0 0 8px 0; font-size: 11px; color: #a1a1aa; text-transform: uppercase;">Tool Invocations (${tools.length})</h4>
                    ${tools.length === 0 ? "<div style='color: #71717a;'>No tool calls executed in this step</div>" : tools.map((t, tidx) => `
                        <div style="background: #202023; border: 1px solid #3f3f46; border-radius: 6px; padding: 10px; margin-bottom: 8px;">
                            <div style="display: flex; justify-content: space-between; margin-bottom: 6px;">
                                <span style="font-weight: 700; color: #22d3ee; font-family: monospace;">#${tidx + 1} ${t.name || 'tool'}</span>
                                <span class="agyis-hud-pill agyis-hud-pill-green">${t.status || "DONE"}</span>
                            </div>
                            <div style="font-size: 10px; color: #a1a1aa; margin-bottom: 4px;">Arguments:</div>
                            <pre class="agyis-codeblock" style="margin-bottom: 8px;"><code>${JSON.stringify(t.args || {}, null, 2).replace(/</g, "&lt;").replace(/>/g, "&gt;")}</code></pre>
                            ${t.output ? `<div style="font-size: 10px; color: #a1a1aa; margin-bottom: 4px;">Output:</div><pre class="agyis-codeblock" style="max-height: 200px;"><code>${String(t.output).replace(/</g, "&lt;").replace(/>/g, "&gt;")}</code></pre>` : ""}
                        </div>
                    `).join("")}
                `;
            } else if (state.activeTab === "execution") {
                const gm = currentStep.generator_metadata || {};
                const em = currentStep.executor_metadata || {};
                const modelUsage = gm.usage || (currentStep.metadata && currentStep.metadata.modelUsage) || {};
                const statusTransitions = (em.statusTransitions) || (currentStep.metadata && currentStep.metadata.statusTransitions) || [
                    { timestamp: new Date().toISOString(), status: currentStep.status || "STATUS_COMPLETED", executionId: `exec-${currentStep.step_index ?? state.selectedIndex}` }
                ];

                inspectorContentHtml = `
                    ${timingBarHtml}
                    <h4 style="margin: 0 0 8px 0; font-size: 11px; color: #a1a1aa; text-transform: uppercase;">Status Transitions</h4>
                    <table class="agyis-markdown-table" style="margin-bottom: 12px;">
                        <tr><th>Timestamp</th><th>Status</th><th>Execution ID</th></tr>
                        ${statusTransitions.map(st => `
                            <tr>
                                <td style="font-family: monospace; font-size: 10px;">${st.timestamp || '-'}</td>
                                <td><span class="agyis-hud-pill agyis-hud-pill-green">${st.status || '-'}</span></td>
                                <td style="font-family: monospace; font-size: 10px;">${st.executionId || '-'}</td>
                            </tr>
                        `).join("")}
                    </table>

                    <h4 style="margin: 0 0 8px 0; font-size: 11px; color: #a1a1aa; text-transform: uppercase;">Model Usage Metrics</h4>
                    <table class="agyis-markdown-table">
                        <tr><th>Metric</th><th>Value</th></tr>
                        <tr><td>Model</td><td>${currentStep.response_model || gm.responseModel || gm.model || "gemini-2.5-pro"}</td></tr>
                        <tr><td>Input Tokens</td><td>${(currentStep.input_tokens || modelUsage.inputTokens || 0).toLocaleString()}</td></tr>
                        <tr><td>Output Tokens</td><td>${(currentStep.output_tokens || modelUsage.outputTokens || 0).toLocaleString()}</td></tr>
                        <tr><td>Thinking Tokens</td><td>${(modelUsage.thinkingOutputTokens || 0).toLocaleString()}</td></tr>
                        <tr><td>Cache Read Tokens</td><td>${(currentStep.cacheReadTokens || modelUsage.cacheReadTokens || 0).toLocaleString()}</td></tr>
                        <tr><td>TTFT</td><td>${((currentStep.thinking_duration_ms || 0) / 1000).toFixed(2)}s</td></tr>
                        <tr><td>Streaming Duration</td><td>${((currentStep.streaming_duration_ms || 0) / 1000).toFixed(2)}s</td></tr>
                        <tr><td>Cumulative Context</td><td>${(currentStep.cumulative_tokens || 0).toLocaleString()} tokens</td></tr>
                    </table>
                `;
            } else { // trajectory / raw
                const rawJson = JSON.stringify(currentStep, null, 2).replace(/</g, "&lt;").replace(/>/g, "&gt;");
                inspectorContentHtml = `
                    <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 8px;">
                        <h4 style="margin: 0; font-size: 11px; color: #a1a1aa; text-transform: uppercase;">Raw Step JSON</h4>
                        <button id="agyis-copy-btn" class="agyis-hud-btn">📋 Copy</button>
                    </div>
                    <pre class="agyis-codeblock" style="max-height: 450px;"><code>${rawJson}</code></pre>
                `;
            }
        }

        const matchCount = state.searchMatchIndices.length;
        const matchDisplay = q ? `${matchCount > 0 ? (state.currentMatchIdx + 1) : 0}/${matchCount}` : `${steps.length}/${steps.length}`;

        if (!hud) hud = document.getElementById(HUD_ID);
        if (!hud) return;

        hud.innerHTML = `
            <div class="agyis-hud-box ${state.isMaximized ? 'maximized' : ''}">
                <!-- Header ('Avc' Parity) -->
                <div class="agyis-hud-header">
                    <div class="agyis-hud-header-left">
                        <span class="agyis-hud-pill agyis-hud-pill-amber">⚡ Trajectory Debug View</span>
                        <select id="agyis-convo-select" class="agyis-hud-select" title="Switch Conversation">
                            ${conversationList.map(c => `
                                <option value="${c.id}" ${c.id === cur.conversation_id ? "selected" : ""}>
                                    ${c.summary || c.id.slice(0, 12)} (${new Date(c.mtime * 1000).toLocaleTimeString()})
                                </option>
                            `).join("")}
                        </select>
                        <button id="agyis-refresh-btn" class="agyis-hud-btn" title="Refresh Trajectory from Server">🔄 Refresh</button>
                        ${isChildView ? `
                            <button id="agyis-parent-btn" class="agyis-hud-pill agyis-hud-pill-blue" style="cursor: pointer;" title="Back to parent conversation">
                                ↑ Parent
                            </button>
                        ` : ""}
                        ${subagentsDropdownHtml}
                        <div class="agyis-hud-search-box">
                            <input id="agyis-search-input" class="agyis-hud-search-input" type="text" placeholder="Search steps..." value="${state.filterQuery}">
                            <span class="agyis-hud-search-counter">${matchDisplay}</span>
                            ${q ? `<button id="agyis-search-clear" style="background: none; border: none; color: #a1a1aa; cursor: pointer; padding: 0 2px;">✕</button>` : ""}
                        </div>
                    </div>

                    <div class="agyis-hud-header-right">
                        <!-- Layout Toggle: Side-by-Side vs Stacked -->
                        <div style="display: inline-flex; border: 1px solid #3f3f46; border-radius: 6px; overflow: hidden;">
                            <button id="agyis-layout-side" class="agyis-hud-btn ${state.layoutOrientation === 'horizontal' ? 'active' : ''}" style="border: none; border-radius: 0;" title="Side-by-side layout">◫ Side-by-Side</button>
                            <button id="agyis-layout-stack" class="agyis-hud-btn ${state.layoutOrientation === 'vertical' ? 'active' : ''}" style="border: none; border-radius: 0;" title="Stacked layout">☰ Stacked</button>
                        </div>
                        <button id="agyis-maximize-btn" class="agyis-hud-btn" title="Toggle Maximize">${state.isMaximized ? '❐ Restore' : '⛶ Maximize'}</button>
                        <button id="agyis-close-btn" class="agyis-hud-btn" title="Close (Escape)">✕</button>
                    </div>
                </div>

                <!-- Main Deck Splitter Layout -->
                <div id="agyis-hud-deck" class="agyis-hud-main-deck ${state.layoutOrientation}">
                    <!-- Left Deck Pane with Sub-Tabs ('Context Window' vs 'Timeline') -->
                    <div class="agyis-grid-pane">
                        <div class="agyis-main-deck-tabs">
                            <button class="agyis-main-tab-btn ${state.mainDeckTab === 'context' ? 'active' : ''}" data-main-tab="context">[ Context Window ]</button>
                            <button class="agyis-main-tab-btn ${state.mainDeckTab === 'timeline' ? 'active' : ''}" data-main-tab="timeline">[ Timeline ]</button>
                        </div>

                        ${state.mainDeckTab === 'context' ? `
                            <!-- Context Window Bar ('Dlc' / Atc Parity) -->
                            <div class="agyis-context-bar-wrap">
                                <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 6px; flex-wrap: wrap; gap: 8px;">
                                    <div style="display: flex; align-items: center; gap: 8px;">
                                        <span style="font-size: 11px; font-weight: 700; color: #fbbf24;">Context Window (${rowCount} row${rowCount > 1 ? 's' : ''})</span>
                                        <div style="display: inline-flex; align-items: center; gap: 4px; background: #202023; border: 1px solid #3f3f46; border-radius: 6px; padding: 2px 6px;">
                                            <button id="agyis-epoch-prev" class="agyis-hud-btn" style="padding: 2px 6px; font-size: 10px;" ${state.activeEpochIndex <= 0 ? 'disabled style="opacity:0.4; cursor:default;"' : ''}>◀ Prev Epoch</button>
                                            <span style="font-size: 10px; font-family: monospace; color: #cbd5e1; padding: 0 4px;">
                                                Epoch ${state.activeEpochIndex + 1} of ${epochs.length} (Steps #${activeEpoch.start_index}-#${activeEpoch.end_index})
                                            </span>
                                            <button id="agyis-epoch-next" class="agyis-hud-btn" style="padding: 2px 6px; font-size: 10px;" ${state.activeEpochIndex >= epochs.length - 1 ? 'disabled style="opacity:0.4; cursor:default;"' : ''}>Next Epoch ▶</button>
                                        </div>
                                    </div>
                                    <div style="font-family: monospace; font-size: 11px; color: #a1a1aa;">
                                        Active Context: <b style="color: #38bdf8;">${activeTokensSum.toLocaleString()}</b> / ${(maxTokens).toLocaleString()} max (${((activeTokensSum / maxTokens) * 100).toFixed(1)}%)
                                    </div>
                                </div>
                                <div class="agyis-context-track" style="display: flex; flex-direction: column; gap: 3px; background: transparent; border: none;">
                                    ${barSegmentsHtml}
                                </div>
                                <div id="agyis-hover-tooltip" class="agyis-context-tooltip" style="display: none;"></div>
                                <div class="agyis-context-legend">
                                    <div style="display: flex; gap: 10px; flex-wrap: wrap;">
                                        <span class="agyis-legend-item"><span class="agyis-legend-dot" style="background: #6366f1;"></span> System Prompt</span>
                                        <span class="agyis-legend-item"><span class="agyis-legend-dot" style="background: #06b6d4;"></span> Tool Defs</span>
                                        <span class="agyis-legend-item"><span class="agyis-legend-dot" style="background: #16a34a;"></span> Checkpoint</span>
                                        <span class="agyis-legend-item"><span class="agyis-legend-dot" style="background: #3b82f6;"></span> User</span>
                                        <span class="agyis-legend-item"><span class="agyis-legend-dot" style="background: #f59e0b;"></span> Model</span>
                                        <span class="agyis-legend-item"><span class="agyis-legend-dot" style="background: #14b8a6;"></span> Tool</span>
                                        <span class="agyis-legend-item"><span class="agyis-legend-dot" style="background: #a855f7;"></span> System</span>
                                        <span class="agyis-legend-item"><span class="agyis-legend-dot" style="background: #3f3f46;"></span> Unused</span>
                                    </div>
                                    <div style="font-family: monospace; font-weight: 700; color: #cbd5e1;">
                                        ${activeTokensSum.toLocaleString()} / ${totalActiveCapacity.toLocaleString()} tokens
                                    </div>
                                </div>
                            </div>

                            <!-- History Table Grid Header ('rmc' Parity) -->
                            <div class="agyis-step-grid-row agyis-step-grid-header">
                                <div>EXEC</div>
                                <div>INV</div>
                                <div>STEP</div>
                                <div>TYPE</div>
                                <div>DETAILS</div>
                                <div>STATUS</div>
                                <div style="text-align: right;">TOKENS</div>
                                <div style="text-align: right;">SIZE</div>
                            </div>
                            <div class="agyis-step-grid-body">
                                ${gridRowsHtml || "<div style='padding: 20px; text-align: center; color: #71717a;'>No steps match current search query</div>"}
                            </div>
                            <div class="agyis-step-grid-pagination" style="display: flex; justify-content: space-between; align-items: center; padding: 6px 10px; background: #141416; border-top: 1px solid #27272a; font-size: 11px;">
                                <div style="display: flex; gap: 4px; align-items: center;">
                                    <button id="agyis-page-prev" class="agyis-hud-btn" ${state.tablePage <= 0 ? 'disabled style="opacity:0.4; cursor:default;"' : ''}>◀ Prev 50</button>
                                    <span style="font-family: monospace; color: #cbd5e1; padding: 0 6px;">
                                        Page ${state.tablePage + 1} of ${totalPages} (${totalFiltered > 0 ? pageStart + 1 : 0}-${pageEnd} of ${totalFiltered})
                                    </span>
                                    <button id="agyis-page-next" class="agyis-hud-btn" ${state.tablePage >= totalPages - 1 ? 'disabled style="opacity:0.4; cursor:default;"' : ''}>Next 50 ▶</button>
                                </div>
                                <button id="agyis-page-jump-selected" class="agyis-hud-btn" title="Jump to selected step">Jump to Selected</button>
                            </div>
                        ` : `
                            <!-- Timeline View Pane ('lvc' Parity) -->
                            <div class="agyis-timeline-pane">
                                <div style="display: flex; justify-content: space-between; align-items: center; padding: 6px 10px; background: #141416; border: 1px solid #27272a; border-radius: 6px; font-size: 11px; color: #a1a1aa;">
                                    <span><b>Trajectory Timeline:</b> ${steps.length} steps (${totalTokens.toLocaleString()} tokens)</span>
                                    <span style="font-family: monospace;">256k Context Parity &bull; Live Trace</span>
                                </div>
                                ${timelineCardsHtml || "<div style='padding: 20px; text-align: center; color: #71717a;'>No timeline steps available</div>"}
                            </div>
                        `}
                    </div>

                    <div id="agyis-splitter" class="agyis-splitter"></div>

                    <!-- Step Inspector ('jmc' & 'fmc' Parity) -->
                    <div class="agyis-inspector-pane">
                        <div class="agyis-inspector-header">
                            <div style="display: flex; align-items: center; gap: 8px;">
                                <span style="font-weight: 700; font-size: 12px;">Step #${currentStep ? (currentStep.step_index ?? state.selectedIndex) : '-'}</span>
                                ${currentStep ? `<span class="agyis-hud-pill agyis-hud-pill-amber">${currentStep.type || 'STEP'}</span>` : ''}
                            </div>
                            <div style="display: flex; gap: 4px; align-items: center;">
                                <button id="agyis-step-first" class="agyis-hud-btn" ${state.selectedIndex <= 0 ? 'disabled style="opacity:0.4;"' : ''}>«</button>
                                <button id="agyis-step-prev" class="agyis-hud-btn" ${state.selectedIndex <= 0 ? 'disabled style="opacity:0.4;"' : ''}>‹</button>
                                <span style="font-size: 11px; font-family: monospace; padding: 0 4px; color: #a1a1aa;">${steps.length > 0 ? (state.selectedIndex + 1) : 0} / ${steps.length}</span>
                                <button id="agyis-step-next" class="agyis-hud-btn" ${state.selectedIndex >= steps.length - 1 ? 'disabled style="opacity:0.4;"' : ''}>›</button>
                                <button id="agyis-step-last" class="agyis-hud-btn" ${state.selectedIndex >= steps.length - 1 ? 'disabled style="opacity:0.4;"' : ''}>»</button>
                            </div>
                        </div>

                        <div class="agyis-inspector-tabs">
                            <button class="agyis-hud-btn ${state.activeTab === 'step' ? 'active' : ''}" data-tab="step">Step</button>
                            <button class="agyis-hud-btn ${state.activeTab === 'invocation' ? 'active' : ''}" data-tab="invocation">Invocation</button>
                            <button class="agyis-hud-btn ${state.activeTab === 'execution' ? 'active' : ''}" data-tab="execution">Execution</button>
                            <button class="agyis-hud-btn ${state.activeTab === 'trajectory' ? 'active' : ''}" data-tab="trajectory">Trajectory</button>
                        </div>

                        <div class="agyis-inspector-content" id="agyis-inspector-body">
                            ${inspectorContentHtml}
                        </div>
                    </div>
                </div>
            </div>
        `;

        // Event Listeners
        hud.querySelector("#agyis-convo-select")?.addEventListener("change", (e) => {
            const selectedId = e.target.value;
            if (selectedId && typeof window.__agyis_hud_load_convo === "function") {
                window.__agyis_hud_load_convo(selectedId);
            }
        });

        hud.querySelector("#agyis-refresh-btn")?.addEventListener("click", () => {
            const state = window.__agyis_hud_state;
            if (state && state.convoId && typeof window.__agyis_hud_load_convo === "function") {
                const btn = hud.querySelector("#agyis-refresh-btn");
                if (btn) btn.textContent = "⏳...";
                window.__agyis_hud_load_convo(state.convoId).finally(() => {
                    if (btn) btn.textContent = "🔄 Refresh";
                });
            }
        });

        hud.querySelector("#agyis-close-btn")?.addEventListener("click", () => {
            hud.style.display = "none";
        });

        hud.querySelector("#agyis-maximize-btn")?.addEventListener("click", () => {
            state.isMaximized = !state.isMaximized;
            renderHud();
        });

        hud.querySelector("#agyis-layout-side")?.addEventListener("click", () => {
            state.layoutOrientation = "horizontal";
            renderHud();
        });

        hud.querySelector("#agyis-layout-stack")?.addEventListener("click", () => {
            state.layoutOrientation = "vertical";
            renderHud();
        });

        hud.querySelector("#agyis-subagents-dropdown-toggle")?.addEventListener("click", (e) => {
            e.stopPropagation();
            state.subagentsDropdownOpen = !state.subagentsDropdownOpen;
            const menu = hud.querySelector("#agyis-subagents-menu");
            if (menu) menu.style.display = state.subagentsDropdownOpen ? "block" : "none";
        });

        hud.querySelectorAll(".agyis-subagent-item").forEach(el => {
            el.addEventListener("click", (e) => {
                e.stopPropagation();
                const sid = el.getAttribute("data-sub-id");
                const subTraj = cur.subagent_trajectories ? cur.subagent_trajectories[sid] : null;
                if (subTraj) {
                    state.currentData = subTraj;
                    state.selectedIndex = Math.max(0, (subTraj.steps || []).length - 1);
                    state.subagentsDropdownOpen = false;
                    renderHud();
                }
            });
        });

        hud.querySelector("#agyis-parent-btn")?.addEventListener("click", () => {
            state.currentData = state.rootData;
            state.selectedIndex = Math.max(0, (state.rootData.steps || []).length - 1);
            renderHud();
        });

        let searchDebounceTimer = null;
        hud.querySelector("#agyis-search-input")?.addEventListener("input", (e) => {
            const val = e.target.value;
            clearTimeout(searchDebounceTimer);
            searchDebounceTimer = setTimeout(() => {
                state.filterQuery = val;
                state.currentMatchIdx = 0;
                state.tablePage = 0;
                renderHud();
                const inputEl = hud.querySelector("#agyis-search-input");
                if (inputEl) {
                    inputEl.focus();
                    inputEl.setSelectionRange(val.length, val.length);
                }
            }, 150);
        });

        hud.querySelector("#agyis-search-input")?.addEventListener("keydown", (e) => {
            if (e.key === "Enter") {
                e.preventDefault();
                if (state.searchMatchIndices.length > 0) {
                    if (e.shiftKey) {
                        state.currentMatchIdx = (state.currentMatchIdx - 1 + state.searchMatchIndices.length) % state.searchMatchIndices.length;
                    } else {
                        state.currentMatchIdx = (state.currentMatchIdx + 1) % state.searchMatchIndices.length;
                    }
                    state.selectedIndex = state.searchMatchIndices[state.currentMatchIdx];
                    const containingEp = epochs.find(ep => state.selectedIndex >= ep.start_index && state.selectedIndex <= ep.end_index);
                    if (containingEp) state.activeEpochIndex = containingEp.epoch_index;
                    renderHud();
                }
            } else if (e.key === "Escape") {
                state.filterQuery = "";
                state.tablePage = 0;
                renderHud();
            }
        });

        hud.querySelector("#agyis-search-clear")?.addEventListener("click", () => {
            state.filterQuery = "";
            state.tablePage = 0;
            renderHud();
        });

        // Epoch Switcher Listeners
        hud.querySelector("#agyis-epoch-prev")?.addEventListener("click", () => {
            if (state.activeEpochIndex > 0) {
                state.activeEpochIndex -= 1;
                const targetEp = epochs[state.activeEpochIndex];
                if (targetEp) {
                    state.selectedIndex = targetEp.start_index;
                }
                renderHud();
            }
        });

        hud.querySelector("#agyis-epoch-next")?.addEventListener("click", () => {
            if (state.activeEpochIndex < epochs.length - 1) {
                state.activeEpochIndex += 1;
                const targetEp = epochs[state.activeEpochIndex];
                if (targetEp) {
                    state.selectedIndex = targetEp.start_index;
                }
                renderHud();
            }
        });

        hud.querySelector("#agyis-jump-prev-epoch")?.addEventListener("click", () => {
            if (state.activeEpochIndex > 0) {
                state.activeEpochIndex -= 1;
                const targetEp = epochs[state.activeEpochIndex];
                if (targetEp) {
                    state.selectedIndex = targetEp.start_index;
                }
                renderHud();
            }
        });

        // Pagination Listeners
        hud.querySelector("#agyis-page-prev")?.addEventListener("click", () => {
            if (state.tablePage > 0) {
                state.tablePage -= 1;
                renderHud();
            }
        });

        hud.querySelector("#agyis-page-next")?.addEventListener("click", () => {
            if (state.tablePage < totalPages - 1) {
                state.tablePage += 1;
                renderHud();
            }
        });

        hud.querySelector("#agyis-page-jump-selected")?.addEventListener("click", () => {
            const fIdx = filteredIndices.indexOf(state.selectedIndex);
            if (fIdx >= 0) {
                state.tablePage = Math.floor(fIdx / pageSize);
                renderHud();
                const rowEl = hud.querySelector(`.agyis-step-grid-item[data-index="${state.selectedIndex}"]`);
                if (rowEl) {
                    rowEl.scrollIntoView({ block: "nearest", behavior: "smooth" });
                }
            }
        });

        // Context segment tooltips & interactive step selection
        const tooltipEl = hud.querySelector("#agyis-hover-tooltip");
        hud.querySelectorAll(".agyis-context-segment").forEach(el => {
            el.addEventListener("mouseenter", () => {
                const sName = el.getAttribute("data-seg-name");
                const sTok = parseInt(el.getAttribute("data-seg-tokens") || "0", 10);
                const sPct = el.getAttribute("data-seg-pct");
                const sTip = el.getAttribute("data-tooltip") || "";
                if (tooltipEl) {
                    tooltipEl.style.display = "block";
                    tooltipEl.innerHTML = `<b style="color: #fbbf24;">${sName}</b><br>Tokens: ${sTok.toLocaleString()} (${sPct}%)${sTip ? `<br><span style="color: #a1a1aa; font-style: italic;">${sTip}</span>` : ''}`;
                }
            });
            el.addEventListener("mouseleave", () => {
                if (tooltipEl) tooltipEl.style.display = "none";
            });
            el.addEventListener("click", () => {
                const stepIdxAttr = el.getAttribute("data-step-index");
                if (stepIdxAttr !== null && stepIdxAttr !== undefined && stepIdxAttr !== "") {
                    const sIdx = parseInt(stepIdxAttr, 10);
                    if (!isNaN(sIdx)) {
                        const containingEp = epochs.find(ep => sIdx >= ep.start_index && sIdx <= ep.end_index);
                        if (containingEp) state.activeEpochIndex = containingEp.epoch_index;
                        state.selectedIndex = sIdx;
                        renderHud();
                        const rowEl = hud.querySelector(`.agyis-step-grid-item[data-index="${sIdx}"]`);
                        if (rowEl) {
                            rowEl.scrollIntoView({ block: "nearest", behavior: "smooth" });
                        }
                    }
                }
            });
        });

        // Main deck sub-tabs
        hud.querySelectorAll(".agyis-main-tab-btn").forEach(el => {
            el.addEventListener("click", () => {
                state.mainDeckTab = el.getAttribute("data-main-tab");
                renderHud();
            });
        });

        // Timeline cards click
        hud.querySelectorAll(".agyis-timeline-card[data-index]").forEach(el => {
            el.addEventListener("click", () => {
                const sIdx = parseInt(el.getAttribute("data-index"), 10);
                if (!isNaN(sIdx)) {
                    const containingEp = epochs.find(ep => sIdx >= ep.start_index && sIdx <= ep.end_index);
                    if (containingEp) state.activeEpochIndex = containingEp.epoch_index;
                    state.selectedIndex = sIdx;
                    renderHud();
                }
            });
        });

        // Stepper buttons
        hud.querySelector("#agyis-step-first")?.addEventListener("click", () => {
            if (steps.length > 0) {
                state.selectedIndex = 0;
                const containingEp = epochs.find(ep => 0 >= ep.start_index && 0 <= ep.end_index);
                if (containingEp) state.activeEpochIndex = containingEp.epoch_index;
                renderHud();
            }
        });
        hud.querySelector("#agyis-step-prev")?.addEventListener("click", () => {
            if (state.selectedIndex > 0) {
                state.selectedIndex -= 1;
                const containingEp = epochs.find(ep => state.selectedIndex >= ep.start_index && state.selectedIndex <= ep.end_index);
                if (containingEp) state.activeEpochIndex = containingEp.epoch_index;
                renderHud();
            }
        });
        hud.querySelector("#agyis-step-next")?.addEventListener("click", () => {
            if (state.selectedIndex < steps.length - 1) {
                state.selectedIndex += 1;
                const containingEp = epochs.find(ep => state.selectedIndex >= ep.start_index && state.selectedIndex <= ep.end_index);
                if (containingEp) state.activeEpochIndex = containingEp.epoch_index;
                renderHud();
            }
        });
        hud.querySelector("#agyis-step-last")?.addEventListener("click", () => {
            if (steps.length > 0) {
                state.selectedIndex = steps.length - 1;
                const containingEp = epochs.find(ep => state.selectedIndex >= ep.start_index && state.selectedIndex <= ep.end_index);
                if (containingEp) state.activeEpochIndex = containingEp.epoch_index;
                renderHud();
            }
        });

        // Inspector tabs
        hud.querySelectorAll(".agyis-inspector-tabs .agyis-hud-btn[data-tab]").forEach(el => {
            el.addEventListener("click", () => {
                state.activeTab = el.getAttribute("data-tab");
                renderHud();
            });
        });

        // Step grid selection
        hud.querySelectorAll(".agyis-step-grid-item").forEach(el => {
            el.addEventListener("click", () => {
                const idx = parseInt(el.getAttribute("data-index"), 10);
                const containingEp = epochs.find(ep => idx >= ep.start_index && idx <= ep.end_index);
                if (containingEp) state.activeEpochIndex = containingEp.epoch_index;
                state.selectedIndex = idx;
                renderHud();
            });
        });

        // Copy button
        hud.querySelector("#agyis-copy-btn")?.addEventListener("click", () => {
            if (currentStep) {
                navigator.clipboard.writeText(JSON.stringify(currentStep, null, 2)).then(() => {
                    const btn = hud.querySelector("#agyis-copy-btn");
                    if (btn) btn.textContent = "✔ Copied!";
                    setTimeout(() => { if (btn) btn.textContent = "📋 Copy"; }, 1500);
                });
            }
        });

        // Code block copy buttons
        hud.querySelectorAll(".agyis-copy-code-btn").forEach(btn => {
            btn.addEventListener("click", (e) => {
                e.stopPropagation();
                const codeId = btn.getAttribute("data-code-id");
                const codeEl = hud.querySelector("#" + codeId);
                if (codeEl) {
                    navigator.clipboard.writeText(codeEl.innerText).then(() => {
                        btn.textContent = "✔ Copied!";
                        setTimeout(() => { if (btn) btn.textContent = "📋 Copy"; }, 1500);
                    });
                }
            });
        });

        // Syntax highlighting integration with window.Prism if available
        if (window.Prism && typeof window.Prism.highlightAllUnder === "function") {
            const inspBody = hud.querySelector("#agyis-inspector-body");
            if (inspBody) {
                try { window.Prism.highlightAllUnder(inspBody); } catch (_) {}
            }
        }
    }

    window.__agyis_hud_render = renderHud;
    window.__agyis_hud_sync = syncToLatestState;
    renderHud();
    document.body.appendChild(hud);
    const initialSelEl = document.querySelector(`.agyis-step-grid-item[data-index="${window.__agyis_hud_state.selectedIndex}"]`);
    if (initialSelEl) initialSelEl.scrollIntoView({ block: "nearest" });

    // Initial check for focused conversation route mismatch (PSL-INV-010)
    const initialRouteMatch = window.location.pathname.match(/\/c\/([a-f0-9\-]+)/);
    const initialFocusedConvo = initialRouteMatch ? initialRouteMatch[1] : null;
    if (initialFocusedConvo && initialFocusedConvo !== initialData.conversation_id && typeof window.__agyis_hud_load_convo === "function") {
        window.__agyis_hud_load_convo(initialFocusedConvo);
    }

    // Global click listener to dismiss subagent dropdown
    document.addEventListener("click", () => {
        if (window.__agyis_hud_state && window.__agyis_hud_state.subagentsDropdownOpen) {
            window.__agyis_hud_state.subagentsDropdownOpen = false;
            const menu = hud.querySelector("#agyis-subagents-menu");
            if (menu) menu.style.display = "none";
        }
    });

    // Keydown listener with dynamic element lookup and re-injection cleanup
    window.__agyis_hud_hotkey_registered = true;
    window.__agyis_hud_last_toggle = window.__agyis_hud_last_toggle || 0;
    if (window.__agyis_hud_active_listener) {
        window.removeEventListener("keydown", window.__agyis_hud_active_listener, true);
    }
    window.__agyis_hud_active_listener = (e) => {
        const isF12 = e.key === "F12";
        const isCtrlShiftT = (e.ctrlKey || e.metaKey) && e.shiftKey && (e.key === "T" || e.key === "t");
        const currentHud = document.getElementById(HUD_ID);
        if (isF12 || isCtrlShiftT) {
            e.preventDefault();
            e.stopImmediatePropagation();
            const now = Date.now();
            if (now - (window.__agyis_hud_last_toggle || 0) < 250) return;
            window.__agyis_hud_last_toggle = now;
            if (currentHud) {
                const isHidden = (currentHud.style.display === "none");
                currentHud.style.display = isHidden ? "flex" : "none";
                if (isHidden) {
                    const match = window.location.pathname.match(/\/c\/([a-f0-9\-]+)/);
                    const focusedConvoId = match ? match[1] : null;
                    const state = window.__agyis_hud_state;
                    if (focusedConvoId && state && focusedConvoId !== state.convoId && typeof window.__agyis_hud_load_convo === "function") {
                        window.__agyis_hud_load_convo(focusedConvoId);
                    } else if (state) {
                        syncToLatestState(state);
                        if (typeof renderHud === "function") renderHud();
                        const selEl = document.querySelector(`.agyis-step-grid-item[data-index="${state.selectedIndex}"]`);
                        if (selEl) selEl.scrollIntoView({ block: "nearest" });
                    }
                }
            }
        }
        if (e.key === "Escape" && currentHud && currentHud.style.display !== "none") {
            currentHud.style.display = "none";
        }
        if (currentHud && currentHud.style.display !== "none" && e.target && (e.target.tagName !== "INPUT" && e.target.tagName !== "TEXTAREA")) {
            const state = window.__agyis_hud_state;
            if (!state) return;
            const steps = (state.currentData && state.currentData.steps) ? state.currentData.steps : [];
            if (e.key === "ArrowLeft" && state.selectedIndex > 0) {
                state.selectedIndex -= 1;
                const epochs = (state.currentData && state.currentData.epochs) || [];
                const foundEp = epochs.find(ep => state.selectedIndex >= ep.start_index && state.selectedIndex <= ep.end_index);
                if (foundEp) state.activeEpochIndex = foundEp.epoch_index;
                renderHud();
            }
            if (e.key === "ArrowRight" && state.selectedIndex < steps.length - 1) {
                state.selectedIndex += 1;
                const epochs = (state.currentData && state.currentData.epochs) || [];
                const foundEp = epochs.find(ep => state.selectedIndex >= ep.start_index && state.selectedIndex <= ep.end_index);
                if (foundEp) state.activeEpochIndex = foundEp.epoch_index;
                renderHud();
            }
        }
    };
    window.addEventListener("keydown", window.__agyis_hud_active_listener, true);

    return {
        success: true,
        open: shouldOpen,
        steps: initialData.step_count || 0,
        convo_id: initialData.conversation_id,
    };
})();
