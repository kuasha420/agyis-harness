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

    function escapeHtml(val) {
        return String(val ?? "")
            .replace(/&/g, "&amp;")
            .replace(/</g, "&lt;")
            .replace(/>/g, "&gt;")
            .replace(/"/g, "&quot;")
            .replace(/'/g, "&#39;");
    }

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
     * Canonical palette colors for prompt sections and tools (matching stock 2.26.0 Wtc).
     */
    const PROMPT_PALETTE = {
        identity: "#6366f1",
        artifacts: "#a78bfa",
        guidelines: "#e879f9",
        communication_style: "#f472b6",
        slash_commands: "#fb7185",
        messaging: "#9333ea",
        mcp_servers: "#7c3aed",
        subagents: "#6d28d9",
        user_rules: "#5b21b6",
        skills: "#4c1d95",
        featured_plugins: "#8b5cf6",
        user_information: "#a855f7",
        sandbox: "#818cf8",
        subagent_reminder: "#d946ef",
    };

    /**
     * Builds individual segments from protobuf token breakdown groups (Group 1 & 2) and epoch steps.
     * Implements the Operator Directive for granular individual section and tool attributions.
     */
    function extractGranularSegments(cur, state, steps, activeEpoch, epochSteps, maxTokens) {
        const segments = [];
        const breakdown = cur.token_breakdown || {};

        // 1. Granular System Prompt Sections (from token_breakdown.groups Group 1 or system_prompt_slices)
        const sysSlices = cur.system_prompt_slices || [];
        if (sysSlices.length > 0) {
            sysSlices.forEach((sl, sidx) => {
                const tok = sl.tokens || 0;
                if (tok > 0) {
                    const tagKey = (sl.tag || sl.name || "").toLowerCase().replace(/[^a-z0-9_]/g, "_");
                    const color = sl.color || PROMPT_PALETTE[tagKey] || "#6366f1";
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
                color: "#6366f1",
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
                    const color = tl.color || (isMcp ? "#0891b2" : "#06b6d4");
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
                color: "#06b6d4",
                colorKey: "bg-cyan-500",
                tooltipContent: `Tool Schemas: ${breakdown.tool_defs.toLocaleString()} tokens`,
            });
        }

        // 3. Compaction Checkpoint Milestone (if epoch starts with or contains checkpoint)
        const hasCpInEpoch = epochSteps.some(s => s.type === "CHECKPOINT");
        const epochCpTok = (activeEpoch && activeEpoch.token_breakdown && activeEpoch.token_breakdown.checkpoint) || breakdown.checkpoint || 0;
        if (!hasCpInEpoch && activeEpoch && activeEpoch.has_checkpoint && epochCpTok > 0) {
            segments.push({
                id: "checkpoint-summary",
                itemKey: `checkpoint-${activeEpoch.start_index}`,
                type: "checkpoint",
                label: "Compaction Checkpoint",
                tokens: epochCpTok,
                color: "#16a34a",
                colorKey: "bg-green-600",
                tooltipContent: activeEpoch.summary || "Compacted Context Summary",
            });
        }

        // 4. Epoch Steps (User prompts, Model outputs, Tool calls)
        epochSteps.forEach((s, offset) => {
            const arrIdx = activeEpoch ? (activeEpoch.start_index + offset) : offset;
            const displayIdx = s.step_index !== undefined ? s.step_index : arrIdx;
            const sTok = s.tokens || Math.round((s.size_bytes || 100) / 3.5);
            let segColor = "#3b82f6";
            let segColorKey = "bg-blue-600";
            let segLabel = `Step #${displayIdx}: ${s.type || "STEP"}`;

            if (s.type === "PLANNER_RESPONSE" || s.type === "MODEL_OUTPUT") {
                segColor = "#f59e0b";
                segColorKey = "bg-amber-600";
            } else if (s.type === "CHECKPOINT") {
                segColor = "#16a34a";
                segColorKey = "bg-green-600";
                segLabel = `Step #${displayIdx}: Checkpoint`;
            } else if ((s.type || "").includes("COMMAND") || (s.type || "").includes("TOOL") || (s.type || "").includes("FILE") || (s.type || "").includes("WRITE") || (s.type || "").includes("REPLACE") || (s.type || "").includes("SEARCH")) {
                segColor = "#14b8a6";
                segColorKey = "bg-teal-600";
            } else if (s.type === "SYSTEM") {
                segColor = "#a855f7";
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
        const unattrTok = Math.max(0, (activeEpoch && activeEpoch.unattributed !== undefined)
            ? activeEpoch.unattributed
            : ((breakdown && breakdown.unattributed) || 0));
        if (unattrTok > 0) {
            segments.push({
                id: "unattributed-context",
                itemKey: "unattributed-context",
                type: "unattributed",
                label: "Unattributed Overhead",
                tokens: unattrTok,
                color: "#64748b",
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
    function renderContextBar(cur, state, steps, activeEpoch, epochSteps, maxTokens, containerWidth) {
        const segments = extractGranularSegments(cur, state, steps, activeEpoch, epochSteps, maxTokens);
        const rawSegmentsSum = segments.reduce((acc, seg) => acc + (seg.tokens || 0), 0);
        const epochs = (cur && cur.epochs) || [];
        const isLatestEpoch = (state.activeEpochIndex === -1 || state.activeEpochIndex === epochs.length - 1);
        const selectedEpochTotal = (activeEpoch && activeEpoch.total_tokens !== undefined)
            ? (activeEpoch.total_tokens || 0)
            : (isLatestEpoch ? (cur.total_tokens || 0) : rawSegmentsSum);
        const activeTokensSum = selectedEpochTotal > 0 ? selectedEpochTotal : rawSegmentsSum;
        const totalTokens = activeTokensSum;

        const ROW_CAPACITY = Math.max(64000, Math.ceil(maxTokens / 4));
        const rowCount = Math.min(4, Math.max(1, Math.ceil(activeTokensSum / ROW_CAPACITY)));
        const totalActiveCapacity = rowCount * ROW_CAPACITY;
        const scaleFactor = (activeTokensSum > 0 && rawSegmentsSum > 0)
            ? (activeTokensSum / rawSegmentsSum)
            : 1.0;

        if (rawSegmentsSum === 0 && activeTokensSum > 0) {
            segments.push({ id: "context-gap", itemKey: "context-gap", type: "unattributed", label: "Unattributed Context", tokens: activeTokensSum, color: "#64748b", colorKey: "bg-slate-500", tooltipContent: `Unattributed Context (${activeTokensSum.toLocaleString()} tokens)` });
        }

        const rows = [];
        for (let r = 0; r < rowCount; r++) rows.push([]);
        let tCursor = 0;
        segments.forEach((seg, sIdx) => {
            let segTokens = Math.max(0, Math.round((seg.tokens || 0) * scaleFactor));
            if (scaleFactor !== 1.0 && sIdx === segments.length - 1) segTokens = Math.max(0, activeTokensSum - tCursor);
            const segStart = tCursor;
            const segEnd = Math.min(rowCount * ROW_CAPACITY, tCursor + segTokens);
            tCursor = segStart + segTokens;
            let sliceCursor = segStart;
            while (sliceCursor < segEnd) {
                const r = Math.min(rowCount - 1, Math.floor(sliceCursor / ROW_CAPACITY));
                const rowEndTokens = (r + 1) * ROW_CAPACITY;
                const sliceEnd = Math.min(segEnd, rowEndTokens);
                const sliceTokens = Math.max(0, sliceEnd - sliceCursor);
                const startFraction = Math.min(1, Math.max(0, (sliceCursor - r * ROW_CAPACITY) / ROW_CAPACITY));
                const widthFraction = Math.min(1 - startFraction, Math.max(0, sliceTokens / ROW_CAPACITY));
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

        const p = maxTokens || 256000;
        const n = activeTokensSum;
        const rawFillPct = p > 0 ? (n / p) * 100 : 0;
        const clampedFillPct = Math.min(100, rawFillPct).toFixed(1);
        const effProvisional = (activeEpoch && activeEpoch.is_provisional !== undefined) ? activeEpoch.is_provisional : (cur && cur.is_provisional);
        const effCacheTokens = (activeEpoch && typeof activeEpoch.cache_tokens === "number") ? activeEpoch.cache_tokens : ((cur && cur.cache_tokens) || 0);
        const estBadge = effProvisional ? ' <span class="agyis-hud-pill agyis-hud-pill-amber" title="Provisional estimate">~est</span>' : "";
        const burnRate = (cur && cur.burn_rate_tokens_per_min) || 0;
        const burnBadge = burnRate > 0 ? ` <span class="agyis-hud-pill agyis-hud-pill-teal">${burnRate.toFixed(0)} tok/m</span>` : "";
        const cacheHitBadge = effCacheTokens > 0 ? ` <span class="agyis-hud-pill agyis-hud-pill-green">Cache: ${(effCacheTokens / 1000).toFixed(1)}k</span>` : "";

        const activeEpIdx = state.activeEpochIndex >= 0 ? state.activeEpochIndex : 0;
        const activeEp = epochs[activeEpIdx] || activeEpoch || { start_index: 0, end_index: steps.length - 1 };

        // Render rows HTML
        const trackHeight = rowCount <= 1 ? 24 : 14;
        let rowsHtml = "";
        rows.forEach((rowCells, rIdx) => {
            const cellsHtml = rowCells.map(cell => {
                const seg = cell.segment;
                const isUnused = seg === null;
                const isSelected = !isUnused && seg.stepIndex !== undefined && seg.stepIndex === state.selectedIndex;
                const isHovered = !isUnused && seg.itemKey && state.hoveredItemKey === seg.itemKey;
                const colorStyle = isUnused ? "background: #27272a;" : `background: ${seg.color};`;
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
                    <span class="agyis-context-row-label" style="font-family: ui-monospace, monospace; font-size: 10px; color: #a1a1aa; width: 34px; text-align: right; flex-shrink: 0; user-select: none;">${Math.round((rIdx * ROW_CAPACITY) / 1000)}k</span>
                    <div class="agyis-context-row-track" style="flex: 1; height: ${trackHeight}px; position: relative; background: #27272a; border-radius: 4px; overflow: hidden; border: 1px solid #3f3f46;">
                        ${cellsHtml}
                    </div>
                </div>
            `;
        });

        return `
            <div class="agyis-context-bar-wrap">
                <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 6px; flex-wrap: wrap; gap: 8px;">
                    <div style="display: flex; align-items: center; gap: 8px;">
                        <span style="font-size: 11px; font-weight: 700; color: #fbbf24;">Context Window (${rowCount} row${rowCount > 1 ? "s" : ""})</span>
                        <div style="display: inline-flex; align-items: center; gap: 4px; background: #202023; border: 1px solid #3f3f46; border-radius: 6px; padding: 2px 6px;">
                            <button id="agyis-epoch-prev" class="agyis-hud-btn" style="padding: 2px 6px; font-size: 10px;" ${activeEpIdx <= 0 ? 'disabled style="opacity:0.4; cursor:default;"' : ""}>◀ Prev Epoch</button>
                            <span style="font-size: 10px; font-family: monospace; color: #cbd5e1; padding: 0 4px;">Epoch ${activeEpIdx + 1} of ${Math.max(1, epochs.length)} (Steps #${activeEp.start_index}-#${activeEp.end_index})</span>
                            <button id="agyis-epoch-next" class="agyis-hud-btn" style="padding: 2px 6px; font-size: 10px;" ${activeEpIdx >= epochs.length - 1 ? 'disabled style="opacity:0.4; cursor:default;"' : ""}>Next Epoch ▶</button>
                        </div>
                    </div>
                    <div style="font-family: monospace; font-size: 11px; color: #a1a1aa; display: flex; align-items: center; gap: 6px;">
                        <span>Active Context: <b style="color: #38bdf8;">${n.toLocaleString()}</b> / ${p.toLocaleString()} max (${clampedFillPct}%${rawFillPct > 100.05 ? " over" : ""})</span>${estBadge}${cacheHitBadge}${burnBadge}
                    </div>
                </div>
                <div class="agyis-context-track" style="display: flex; flex-direction: column; gap: 3px; background: transparent; border: none;">
                    ${rowsHtml}
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
                </div>
            </div>
        `;
    }

    /**
     * Binds mouse and click events for the context bar, including bidirectional hover syncing.
     */
    function bindContextBarEvents(hudEl, state, cur, epochs, renderCallback, selectStepCallback) {
        if (!hudEl) return;

        // Epoch navigation
        hudEl.querySelector("#agyis-epoch-prev")?.addEventListener("click", () => {
            if (state.activeEpochIndex > 0) {
                state.activeEpochIndex -= 1;
                if (epochs[state.activeEpochIndex] && selectStepCallback) {
                    selectStepCallback(epochs[state.activeEpochIndex].start_index);
                } else if (renderCallback) {
                    renderCallback();
                }
            }
        });

        hudEl.querySelector("#agyis-epoch-next")?.addEventListener("click", () => {
            if (state.activeEpochIndex < epochs.length - 1) {
                state.activeEpochIndex += 1;
                if (epochs[state.activeEpochIndex] && selectStepCallback) {
                    selectStepCallback(epochs[state.activeEpochIndex].start_index);
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
                    hudEl.querySelectorAll(`[data-item-key="${itemKey}"]`).forEach(matchedEl => {
                        matchedEl.classList.add("context-cell-hovered");
                    });
                }

                if (tooltipEl) {
                    tooltipEl.style.display = "block";
                    tooltipEl.innerHTML = `<b style="color: #fbbf24;">${escapeHtml(sName)}</b><br>Tokens: ${sTok.toLocaleString()} (${escapeHtml(sPct)}%)${sTip ? `<br><span style="color: #a1a1aa; font-style: italic;">${escapeHtml(sTip)}</span>` : ""}`;
                }
            });

            el.addEventListener("mouseleave", () => {
                const itemKey = el.getAttribute("data-item-key");
                if (itemKey) {
                    state.hoveredItemKey = null;
                    hudEl.querySelectorAll(`[data-item-key="${itemKey}"]`).forEach(matchedEl => {
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
                        selectStepCallback(sIdx);
                    }
                }
            });
        });
    }

    // Export module onto window namespace
    global.xtc = xtc;
    global.ytc = ytc;
    global.ztc = ztc;
    global.Atc = Atc;
    global.extractGranularSegments = extractGranularSegments;
    global.renderContextBar = renderContextBar;
    global.bindContextBarEvents = bindContextBarEvents;

})(typeof window !== "undefined" ? window : globalThis);
