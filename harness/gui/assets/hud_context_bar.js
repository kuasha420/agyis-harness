// SPDX-License-Identifier: Apache-2.0
// Copyright (c) 2026 Arafat Zahan (@kuasha420)
// Corporate Stewardship & Infrastructure: Purrfect Software Limited (PSL)
// Governed by: ICARO-42/b Ordinance (Company-Supported Personal IP Framework)

/**
 * hud_context_bar.js — Proportional Context Bar Component (Wtc / Atc Parity).
 * 
 * Implements the canonical Antigravity 2.26.0 Wtc context bar with Atc multi-row
 * slice packing, ztc dynamic inflation optimization (10% threshold / 2% width delta gate),
 * 2px sub-pixel clamping (xtc), normalized context capacity t = (m/n)*p, and full granular
 * attribution for individual system prompt sections and native/MCP tools.
 */

(function(global) {
    "use strict";

    const _u = () => global.__agyis_utils || {};
    const escapeHtml = (val) => (_u().escapeHtml ? _u().escapeHtml(val) : String(val ?? ""));
    const cssEscape = (val) => (_u().cssEscape ? _u().cssEscape(val) : String(val ?? ""));

    /**
     * Clamped segment width function (xtc).
     * Enforces a minimum clickable width (minSegmentPx, default 2px) for any segment with tokens > 0.
     */
    function xtc(segment, pxPerToken, minSegmentPx) {
        const tokens = segment && (segment.tokens || 0) > 0 ? segment.tokens : 0;
        return tokens > 0 ? Math.max(tokens * pxPerToken, minSegmentPx) : 0;
    }

    /**
     * Evaluates visual layout metrics and pixel inflation for a given row count candidate (ytc).
     */
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

    /**
     * Determines optimal row count using the two-gate inflation algorithm (ztc).
     * Gate 1: If inflation is <= 10% of true tokens, single or current row layout is acceptable.
     * Gate 2: If adding another row reduces visual distortion by < 2% of container width, terminate.
     */
    function ztc(segments, capacityTokens, containerWidth, minSegmentPx, maxRows) {
        let current = ytc(segments, capacityTokens, containerWidth, minSegmentPx, 1);
        for (let r = 1; r < maxRows; r++) {
            if (current.inflationPx <= 0.10 * current.trueUsedPx) {
                return r;
            }
            const next = ytc(segments, capacityTokens, containerWidth, minSegmentPx, r + 1);
            if (current.inflationPx - next.inflationPx < 0.02 * containerWidth) {
                return r;
            }
            current = next;
        }
        return maxRows;
    }

    /**
     * Multi-row continuous slice packing engine (Atc).
     * Computes optimal row count, scales overflow, and slices continuous segments across rows.
     */
    function Atc(segments, capacityTokens, containerWidth, options) {
        const opts = options || {};
        const minSegmentPx = opts.minSegmentPx ?? 2;
        const maxRows = Math.min(8, Math.max(1, opts.maxRows ?? 8));
        const emptyResult = { rows: [], rowCount: 1, inflationPx: 0 };

        if (!segments || segments.length === 0 || !Number.isFinite(containerWidth) || !Number.isFinite(capacityTokens) || containerWidth <= 0 || capacityTokens <= 0) {
            return emptyResult;
        }

        const rowCount = ztc(segments, capacityTokens, containerWidth, minSegmentPx, maxRows);
        const layout = ytc(segments, capacityTokens, containerWidth, minSegmentPx, rowCount);
        const scaleFactor = layout.usedPx > layout.capacityPx ? layout.capacityPx / layout.usedPx : 1.0;
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
                    sliceTokens: seg ? Math.round(seg.tokens * (sliceWidth / Math.max(1e-6, widthPx))) : Math.round(sliceWidth / Math.max(1e-6, layout.pxPerToken)),
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

        return { rows: rows, rowCount: rowCount, inflationPx: layout.inflationPx * scaleFactor, pxPerToken: layout.pxPerToken };
    }

    /**
     * Canonical palette lookup delegated to Orbital Aegis SSOT (hud_theme.js).
     */
    const getPromptPalette = () => (global.__agyis_theme && global.__agyis_theme.PROMPT_PALETTE) || {};

    /**
     * Builds individual segments from protobuf token breakdown groups (Group 1 & 2) and checkpoint window steps.
     * Implements the Operator Directive for granular individual section and tool attributions.
     */
    function extractGranularSegments(cur, state, steps, activeCheckpoint, checkpointSteps, maxTokens) {
        const segments = [];
        const breakdown = cur.token_breakdown || {};
        const promptPalette = getPromptPalette();

        // 1. Granular System Prompt Sections (from token_breakdown.groups Group 1 or system_prompt_slices)
        const sysSlices = cur.system_prompt_slices || [];
        if (sysSlices.length > 0) {
            sysSlices.forEach((sl, sidx) => {
                const tok = sl.tokens || 0;
                if (tok > 0) {
                    const tagKey = (sl.tag || sl.name || "").toLowerCase().replace(/[^a-z0-9_]/g, "_");
                    const color = sl.color || promptPalette[tagKey] || "#5C8AFF";
                    segments.push({
                        id: `prompt-section-${sidx}`,
                        itemKey: `prompt-section-${sidx}`,
                        type: "system_prompt_section",
                        sectionName: sl.name,
                        label: `Prompt: ${sl.name}`,
                        tokens: tok,
                        color: color,
                        colorKey: "bg-indigo-500",
                        tooltipContent: `System Prompt [${sl.name}]: ${tok.toLocaleString()} tokens`,
                    });
                }
            });
        } else if ((breakdown.system_prompt || 0) > 0) {
            segments.push({
                id: "prompt-section-root",
                itemKey: "prompt-section-root",
                type: "system_prompt",
                label: "System Prompt",
                tokens: breakdown.system_prompt,
                color: "#5C8AFF",
                colorKey: "bg-indigo-500",
                tooltipContent: `Base System Instructions: ${breakdown.system_prompt.toLocaleString()} tokens`,
            });
        }

        // 2. Granular Tool Definitions (from token_breakdown.groups Group 2/4 or tool_def_slices)
        const toolSlices = cur.tool_def_slices || [];
        if (toolSlices.length > 0) {
            toolSlices.forEach((tl, tidx) => {
                const tok = tl.tokens || 0;
                if (tok > 0) {
                    const isMcp = Boolean(tl.server_name || tl.is_mcp);
                    const color = tl.color || (isMcp ? "#1CB0AE" : "#26D0CE");
                    const itemKey = `tool-def-${tl.name}`;
                    segments.push({
                        id: `tool-def-${tidx}`,
                        itemKey: itemKey,
                        type: "tool_definition",
                        toolName: tl.name,
                        serverName: tl.server_name || "",
                        label: `Tool: ${tl.name}`,
                        tokens: tok,
                        color: color,
                        colorKey: "bg-cyan-500",
                        tooltipContent: isMcp
                            ? `MCP Tool [${tl.server_name} -> ${tl.name}]: ${tok.toLocaleString()} tokens`
                            : `Native Tool [${tl.name}]: ${tok.toLocaleString()} tokens`,
                    });
                }
            });
        } else if ((breakdown.tool_defs || 0) > 0) {
            segments.push({
                id: "tool-defs-root",
                itemKey: "tool-defs-root",
                type: "tool_definition",
                label: "Tool Definitions",
                tokens: breakdown.tool_defs,
                color: "#26D0CE",
                colorKey: "bg-cyan-500",
                tooltipContent: `Tool Schemas: ${breakdown.tool_defs.toLocaleString()} tokens`,
            });
        }

        // 3. Compaction Checkpoint Milestone (if checkpoint window starts with or contains checkpoint)
        const hasCpInWindow = checkpointSteps.some(s => s.type === "CHECKPOINT");
        const windowCpTok = (activeCheckpoint && activeCheckpoint.token_breakdown && activeCheckpoint.token_breakdown.checkpoint) || breakdown.checkpoint || 0;
        if (!hasCpInWindow && activeCheckpoint && activeCheckpoint.has_checkpoint && windowCpTok > 0) {
            segments.push({
                id: "checkpoint-summary",
                itemKey: `checkpoint-${activeCheckpoint.start_index}`,
                type: "checkpoint",
                label: "Compaction Checkpoint",
                tokens: windowCpTok,
                color: "#2AD089",
                colorKey: "bg-green-600",
                tooltipContent: activeCheckpoint.summary || "Compacted Context Summary",
            });
        }

        // 4. Checkpoint Window Steps (User prompts, Model outputs, Tool calls)
        checkpointSteps.forEach((s, offset) => {
            const arrIdx = activeCheckpoint ? (activeCheckpoint.start_index + offset) : offset;
            const displayIdx = s.step_index !== undefined ? s.step_index : arrIdx;
            const sTok = s.tokens || Math.round((s.size_bytes || 100) / 3.5);
            let segColor = "#1B4DFF";
            let segColorKey = "bg-blue-600";
            let segLabel = `Step #${displayIdx}: ${s.type || "STEP"}`;

            const stUpper = s.type || "";
            if (stUpper === "PLANNER_RESPONSE" || stUpper === "MODEL_OUTPUT") {
                segColor = "#F5B74F";
                segColorKey = "bg-amber-600";
            } else if (stUpper === "CHECKPOINT") {
                segColor = "#2AD089";
                segColorKey = "bg-green-600";
                segLabel = `Step #${displayIdx}: Checkpoint`;
            } else if (/COMMAND|TOOL|FILE|EDIT|WRITE|REPLACE|SEARCH|SWARM|BOARD|WORKFLOW|TASK|PLAN|FOCUS|STEPS|QUESTION|MCP|RESOURCE|MARKETPLACE|PLUGIN/.test(stUpper)) {
                segColor = "#26D0CE";
                segColorKey = "bg-teal-600";
            } else if (stUpper === "SYSTEM") {
                segColor = "#8FB0FF";
                segColorKey = "bg-purple-600";
            }

            let tip = s.thinking || s.content || "";
            if (s.type === "CHECKPOINT") tip = s.compaction_summary || s.summary || s.sessionSummary || tip || "Checkpoint";
            if (!tip && (s.tool_calls || []).length > 0) tip = s.tool_calls.map(tc => tc.name).join(", ");
            tip = tip.replace(/\n/g, " ").slice(0, 160);

            segments.push({
                id: `step-${arrIdx}`,
                itemKey: `step-${arrIdx}`,
                type: "step",
                stepIndex: arrIdx,
                label: segLabel,
                tokens: sTok,
                color: segColor,
                colorKey: segColorKey,
                tooltipContent: tip || segLabel,
            });
        });

        // 5. Unattributed Overhead (Remains 0 in honest SSOT mode)
        const unattrTok = Math.max(0, (activeCheckpoint && activeCheckpoint.unattributed !== undefined)
            ? activeCheckpoint.unattributed
            : ((breakdown && breakdown.unattributed) || 0));
        if (unattrTok > 0) {
            segments.push({
                id: "unattributed-context",
                itemKey: "unattributed-context",
                type: "unattributed",
                label: "Unattributed Overhead",
                tokens: unattrTok,
                color: "#6E7F9B",
                colorKey: "bg-slate-500",
                tooltipContent: `Unattributed Tokens: ${unattrTok.toLocaleString()}`,
            });
        }

        return segments;
    }

    /**
     * Main context bar rendering function.
     * Computes normalized capacity t = (m/n)*p and runs Atc multi-row layout.
     */
    function renderContextBar(cur, state, steps, activeCheckpoint, checkpointSteps, maxTokens, containerWidth) {
        const segments = extractGranularSegments(cur, state, steps, activeCheckpoint, checkpointSteps, maxTokens);
        const rawSegmentsSum = segments.reduce((acc, seg) => acc + (seg.tokens || 0), 0);
        const checkpoints = (cur && cur.checkpoints) || [];
        const isLatestCheckpoint = (state.activeCheckpointIndex === -1 || state.activeCheckpointIndex === checkpoints.length - 1);
        const selectedCheckpointTotal = (activeCheckpoint && activeCheckpoint.total_tokens !== undefined)
            ? (activeCheckpoint.total_tokens || 0)
            : (isLatestCheckpoint ? (cur.total_tokens || 0) : rawSegmentsSum);
        const activeTokensSum = selectedCheckpointTotal > 0 ? selectedCheckpointTotal : rawSegmentsSum;
        const totalTokens = activeTokensSum;

        const ROW_CAPACITY = Math.max(64000, Math.ceil(maxTokens / 4));
        const rowCount = Math.min(4, Math.max(1, Math.ceil(activeTokensSum / ROW_CAPACITY)));
        const totalActiveCapacity = rowCount * ROW_CAPACITY;
        const scaleFactor = (activeTokensSum > 0 && rawSegmentsSum > 0)
            ? (activeTokensSum / rawSegmentsSum)
            : 1.0;

        if (rawSegmentsSum === 0 && activeTokensSum > 0) {
            segments.push({ id: "context-gap", itemKey: "context-gap", type: "unattributed", label: "Unattributed Context", tokens: activeTokensSum, color: "#6E7F9B", colorKey: "bg-slate-500", tooltipContent: `Unattributed Context (${activeTokensSum.toLocaleString()} tokens)` });
        }

        const rows = [];
        for (let r = 0; r < rowCount; r++) rows.push([]);
        const rowPx = Math.max(200, Number.isFinite(containerWidth) && containerWidth > 0 ? containerWidth : 800);
        let tCursor = 0;
        let placedTotal = 0;
        segments.forEach((seg, sIdx) => {
            const rawScaled = Math.max(0, (seg.tokens || 0) * scaleFactor);
            let segTokens = Math.max(0, Math.round(rawScaled));
            if (scaleFactor !== 1.0 && sIdx === segments.length - 1) {
                const residual = Math.round(activeTokensSum - placedTotal);
                segTokens = Math.max(0, residual);
            }
            const segStart = tCursor;
            const segEnd = Math.min(rowCount * ROW_CAPACITY, tCursor + segTokens);
            tCursor = segStart + segTokens;
            placedTotal += segTokens;
            let sliceCursor = segStart;
            while (sliceCursor < segEnd) {
                const r = Math.min(rowCount - 1, Math.floor(sliceCursor / ROW_CAPACITY));
                const rowEndTokens = (r + 1) * ROW_CAPACITY;
                const sliceEnd = Math.min(segEnd, rowEndTokens);
                const sliceTokens = Math.max(0, sliceEnd - sliceCursor);
                const startFraction = Math.min(1, Math.max(0, (sliceCursor - r * ROW_CAPACITY) / ROW_CAPACITY));
                // Apply xtc minimum clickable pixel floor for non-zero segments
                const minSegPx = xtc({ tokens: sliceTokens }, rowPx / ROW_CAPACITY, 2);
                const minFraction = Math.min(1 - startFraction, minSegPx / rowPx);
                const widthFraction = Math.min(1 - startFraction, Math.max(minFraction, sliceTokens / ROW_CAPACITY));
                if (sliceTokens > 0) {
                    rows[r].push({ segment: seg, startFraction, widthFraction, sliceTokens });
                }
                sliceCursor = sliceEnd;
                if (sliceEnd >= rowEndTokens && r === rowCount - 1) break;
            }
        });

        let uCursor = Math.min(tCursor, totalActiveCapacity);
        while (uCursor < totalActiveCapacity) {
            const r = Math.min(rowCount - 1, Math.floor(uCursor / ROW_CAPACITY));
            const rowEndTokens = (r + 1) * ROW_CAPACITY;
            const sliceEnd = Math.min(totalActiveCapacity, rowEndTokens);
            const sliceTokens = Math.max(0, sliceEnd - uCursor);
            const startFraction = Math.min(1, Math.max(0, (uCursor - r * ROW_CAPACITY) / ROW_CAPACITY));
            const widthFraction = Math.min(1 - startFraction, Math.max(0, sliceTokens / ROW_CAPACITY));
            if (sliceTokens > 0) {
                rows[r].push({ segment: null, startFraction, widthFraction, sliceTokens });
            }
            uCursor = sliceEnd;
        }

        const inferCtx = _u().inferModelContextWindow;
        const p = maxTokens || (inferCtx ? inferCtx((cur && cur.model) || (state && state.sessionModel)) : 256000);
        const n = activeTokensSum;
        const rawFillPct = p > 0 ? (n / p) * 100 : 0;
        const clampedFillPct = Math.min(100, rawFillPct).toFixed(1);
        const effProvisional = (activeCheckpoint && activeCheckpoint.is_provisional !== undefined) ? activeCheckpoint.is_provisional : (cur && cur.is_provisional);
        const effCacheTokens = (activeCheckpoint && typeof activeCheckpoint.cache_tokens === "number") ? activeCheckpoint.cache_tokens : ((cur && cur.cache_tokens) || 0);
        const estBadge = effProvisional ? ' <span class="agyis-hud-pill agyis-hud-pill-amber" title="Provisional estimate">~est</span>' : "";
        const burnRate = (cur && cur.burn_rate_tokens_per_min) || 0;
        const burnBadge = burnRate > 0 ? ` <span class="agyis-hud-pill agyis-hud-pill-teal">${burnRate.toFixed(0)} tok/m</span>` : "";
        const cacheHitBadge = effCacheTokens > 0 ? ` <span class="agyis-hud-pill agyis-hud-pill-green">Cache: ${(effCacheTokens / 1000).toFixed(1)}k</span>` : "";

        const activeCpIdx = state.activeCheckpointIndex >= 0 ? state.activeCheckpointIndex : 0;
        const activeCp = checkpoints[activeCpIdx] || activeCheckpoint || { start_index: 0, end_index: steps.length - 1 };

        // Render rows HTML
        const trackHeight = rowCount <= 1 ? 24 : 14;
        let rowsHtml = "";
        rows.forEach((rowCells, rIdx) => {
            const cellsHtml = rowCells.map(cell => {
                const seg = cell.segment;
                const isUnused = seg === null;
                const isSelected = !isUnused && seg.stepIndex !== undefined && seg.stepIndex === state.selectedIndex;
                const isHovered = !isUnused && seg.itemKey && state.hoveredItemKey === seg.itemKey;
                const colorStyle = isUnused ? "background: #162238;" : `background: ${seg.color};`;
                const borderRight = isUnused ? "" : "border-right: 1px solid rgba(0, 0, 0, 0.35);";
                const leftPct = (cell.startFraction * 100).toFixed(4);
                const widthPct = (cell.widthFraction * 100).toFixed(4);
                const stepIdxAttr = (!isUnused && seg.stepIndex !== undefined) ? `data-step-index="${seg.stepIndex}"` : "";
                const itemKeyAttr = (!isUnused && seg.itemKey) ? `data-item-key="${escapeHtml(seg.itemKey)}"` : "";

                return `
                    <button type="button"
                            class="agyis-context-segment ${isUnused ? "context-cell-unused" : ""} ${isSelected ? "context-cell-selected" : ""} ${isHovered ? "context-cell-hovered" : ""}"
                            ${stepIdxAttr}
                            ${itemKeyAttr}
                            data-seg-id="${escapeHtml(isUnused ? "unused" : seg.id)}"
                            data-seg-name="${escapeHtml(isUnused ? "Unused Capacity" : seg.label)}"
                            data-seg-tokens="${isUnused ? cell.sliceTokens : seg.tokens}"
                            data-seg-pct="${Math.min(100, (((isUnused ? cell.sliceTokens : seg.tokens) / p) * 100)).toFixed(1)}"
                            data-tooltip="${isUnused ? "" : escapeHtml(seg.tooltipContent || "")}"
                            aria-label="${escapeHtml(isUnused ? `Unused capacity: ${cell.sliceTokens.toLocaleString()} tokens` : `${seg.label}: ${seg.tokens.toLocaleString()}`)}"
                            style="position: absolute; top: 0; bottom: 0; left: ${leftPct}%; width: ${widthPct}%; ${colorStyle} ${borderRight}">
                    </button>
                `;
            }).join("");

            rowsHtml += `
                <div class="agyis-context-row-wrap" style="display: flex; align-items: center; gap: 8px;">
                    <span class="agyis-context-row-label" style="font-family: var(--agyis-font-mono, monospace); font-size: 10px; color: #9AA8BE; width: 34px; text-align: right; flex-shrink: 0; user-select: none;">${Math.round((rIdx * ROW_CAPACITY) / 1000)}k</span>
                    <div class="agyis-context-row-track" style="flex: 1; height: ${trackHeight}px; position: relative; background: #0B1322; border-radius: 4px; overflow: hidden; border: 1px solid #1E2C47;">
                        ${cellsHtml}
                    </div>
                </div>
            `;
        });

        return `
            <div class="agyis-context-bar-wrap">
                <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 6px; flex-wrap: wrap; gap: 8px;">
                    <div style="display: flex; align-items: center; gap: 8px;">
                        <span style="font-size: 11px; font-weight: 700; color: #5C8AFF;">Context Window (${rowCount} row${rowCount > 1 ? "s" : ""})</span>
                        <div style="display: inline-flex; align-items: center; gap: 4px; background: #0B1322; border: 1px solid #1E2C47; border-radius: 6px; padding: 2px 6px;">
                            <button id="agyis-checkpoint-prev" class="agyis-hud-btn" style="padding: 2px 6px; font-size: 10px;" ${activeCpIdx <= 0 ? 'disabled style="opacity:0.4; cursor:default;"' : ""}>◀ Prev Checkpoint</button>
                            <span style="font-size: 10px; font-family: var(--agyis-font-mono, monospace); color: #F4F6FA; padding: 0 4px;">Checkpoint ${activeCpIdx + 1} of ${Math.max(1, checkpoints.length)} (Steps #${activeCp.start_index}-#${activeCp.end_index})</span>
                            <button id="agyis-checkpoint-next" class="agyis-hud-btn" style="padding: 2px 6px; font-size: 10px;" ${activeCpIdx >= checkpoints.length - 1 ? 'disabled style="opacity:0.4; cursor:default;"' : ""}>Next Checkpoint ▶</button>
                        </div>
                    </div>
                    <div style="font-family: var(--agyis-font-mono, monospace); font-size: 11px; color: #9AA8BE; display: flex; align-items: center; gap: 6px;">
                        <span>Active Context: <b style="color: #26D0CE;">${n.toLocaleString()}</b> / ${p.toLocaleString()} max (${clampedFillPct}%${rawFillPct > 100.05 ? " over" : ""})</span>${estBadge}${cacheHitBadge}${burnBadge}
                    </div>
                </div>
                <div class="agyis-context-track" style="display: flex; flex-direction: column; gap: 3px; background: transparent; border: none;">
                    ${rowsHtml}
                </div>
                <div id="agyis-hover-tooltip" class="agyis-context-tooltip" style="display: none;"></div>
                <div class="agyis-context-legend">
                    <div style="display: flex; gap: 10px; flex-wrap: wrap;">
                        <span class="agyis-legend-item"><span class="agyis-legend-dot" style="background: #5C8AFF;"></span> System Prompt</span>
                        <span class="agyis-legend-item"><span class="agyis-legend-dot" style="background: #26D0CE;"></span> Tool Defs</span>
                        <span class="agyis-legend-item"><span class="agyis-legend-dot" style="background: #2AD089;"></span> Checkpoint</span>
                        <span class="agyis-legend-item"><span class="agyis-legend-dot" style="background: #1B4DFF;"></span> User</span>
                        <span class="agyis-legend-item"><span class="agyis-legend-dot" style="background: #F5B74F;"></span> Model</span>
                        <span class="agyis-legend-item"><span class="agyis-legend-dot" style="background: #26D0CE;"></span> Tool</span>
                        <span class="agyis-legend-item"><span class="agyis-legend-dot" style="background: #8FB0FF;"></span> System</span>
                        <span class="agyis-legend-item"><span class="agyis-legend-dot" style="background: #1E2C47;"></span> Unused</span>
                    </div>
                </div>
            </div>
        `;
    }

    /**
     * Binds mouse and click events for the context bar, including bidirectional hover syncing.
     */
    function bindContextBarEvents(hudEl, state, cur, checkpoints, renderCallback, selectStepCallback) {
        if (!hudEl) return;

        // Checkpoint navigation
        hudEl.querySelector("#agyis-checkpoint-prev")?.addEventListener("click", () => {
            if (state.activeCheckpointIndex > 0) {
                state.activeCheckpointIndex -= 1;
                if (checkpoints[state.activeCheckpointIndex] && selectStepCallback) {
                    selectStepCallback(checkpoints[state.activeCheckpointIndex].start_index, { preserveCheckpoint: true });
                } else if (renderCallback) {
                    renderCallback();
                }
            }
        });

        hudEl.querySelector("#agyis-checkpoint-next")?.addEventListener("click", () => {
            if (state.activeCheckpointIndex < checkpoints.length - 1) {
                state.activeCheckpointIndex += 1;
                if (checkpoints[state.activeCheckpointIndex] && selectStepCallback) {
                    selectStepCallback(checkpoints[state.activeCheckpointIndex].start_index, { preserveCheckpoint: true });
                } else if (renderCallback) {
                    renderCallback();
                }
            }
        });

        // Hover tooltip & segment clicks
        const tooltipEl = hudEl.querySelector("#agyis-hover-tooltip");
        hudEl.querySelectorAll(".agyis-context-segment").forEach(el => {
            el.addEventListener("mouseenter", () => {
                const sName = el.getAttribute("data-seg-name");
                const sTok = parseInt(el.getAttribute("data-seg-tokens") || "0", 10);
                const sPct = el.getAttribute("data-seg-pct");
                const sTip = el.getAttribute("data-tooltip") || "";
                const itemKey = el.getAttribute("data-item-key");

                if (itemKey) {
                    state.hoveredItemKey = itemKey;
                    // Highlight matching elements across inspector or timeline
                    hudEl.querySelectorAll(`[data-item-key="${cssEscape(itemKey)}"]`).forEach(matchedEl => {
                        matchedEl.classList.add("context-cell-hovered");
                    });
                }

                if (tooltipEl) {
                    tooltipEl.style.display = "block";
                    tooltipEl.innerHTML = `<b style="color: #5C8AFF;">${escapeHtml(sName)}</b><br>Tokens: ${sTok.toLocaleString()} (${escapeHtml(sPct)}%)${sTip ? `<br><span style="color: #9AA8BE; font-style: italic;">${escapeHtml(sTip)}</span>` : ""}`;
                }
            });

            el.addEventListener("mouseleave", () => {
                const itemKey = el.getAttribute("data-item-key");
                if (itemKey) {
                    state.hoveredItemKey = null;
                    hudEl.querySelectorAll(`[data-item-key="${cssEscape(itemKey)}"]`).forEach(matchedEl => {
                        matchedEl.classList.remove("context-cell-hovered");
                    });
                }
                if (tooltipEl) tooltipEl.style.display = "none";
            });

            el.addEventListener("click", () => {
                const stepIdxAttr = el.getAttribute("data-step-index");
                if (stepIdxAttr !== null && stepIdxAttr !== undefined && stepIdxAttr !== "") {
                    const sIdx = parseInt(stepIdxAttr, 10);
                    if (!isNaN(sIdx) && selectStepCallback) {
                        selectStepCallback(sIdx, { preserveCheckpoint: true });
                    }
                }
            });
        });
    }

    // Export cleanroom sizing helpers strictly under the __agyis_context_bar namespace
    // to prevent colliding with Closure-minified globals (e.g. Antigravity 2.35.2's
    // WebSocket ConnectRPC transport functions xtc/ytc/ztc/Atc).
    global.__agyis_context_bar = { xtc, ytc, ztc, Atc };
    global.extractGranularSegments = extractGranularSegments;
    global.renderContextBar = renderContextBar;
    global.bindContextBarEvents = bindContextBarEvents;

})(typeof window !== "undefined" ? window : globalThis);
