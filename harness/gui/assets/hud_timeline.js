// SPDX-License-Identifier: Apache-2.0
// Copyright (c) 2026 Arafat Zahan (@kuasha420)
// Corporate Stewardship & Infrastructure: Purrfect Software Limited (PSL)
// Governed by: ICARO-42/b Ordinance (Company-Supported Personal IP Framework)

/**
 * hud_timeline.js — Gantt Timeline Visualizer Component (lvc / dnc Parity).
 * 
 * Implements the canonical Antigravity 2.26.0 timeline with piecewise continuous
 * millisecond coordinate scale ($6), collapsible idle blocks (Auc / Buc), step phase
 * breakdown (kuc), exponential wheel zoom, and dual-mode (virtual steps vs activity lanes Ouc).
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
     * Sub-minute (< 60s) duration formatting with ms or decimal seconds precision.
     */
    function formatShortDuration(ms) {
        ms = Math.max(0, ms || 0);
        if (ms < 1000) return `${Math.round(ms)}ms`;
        const sec = ms / 1000;
        if (sec < 10) return `${sec.toFixed(2)}s`;
        if (sec < 60) return `${sec.toFixed(1)}s`;
        const min = Math.floor(sec / 60);
        const remSec = Math.round(sec % 60);
        return remSec > 0 ? `${min}m ${remSec}s` : `${min}m`;
    }

    /**
     * Multi-minute (>= 60s) duration formatting.
     */
    function formatLongDuration(ms) {
        let sec = Math.max(1, Math.floor((ms || 0) / 1000));
        if (sec < 60) return `${sec}s`;
        let min = Math.floor(sec / 60);
        if (min < 60) return `${min}m`;
        let hr = Math.floor(min / 60);
        let day = Math.floor(hr / 24);
        min %= 60;
        if (day > 0) return `${day}d ${hr % 24}h ${min}m`;
        if (min > 0) return `${hr}h ${min}m`;
        return `${hr}h`;
    }

    /**
     * Master duration formatter (a7 / nO).
     */
    function formatDuration(ms) {
        return (ms || 0) < 60000 ? formatShortDuration(ms) : formatLongDuration(ms);
    }

    /**
     * Step timing phase extraction engine (kuc).
     * Extracts TTFT, streaming, arg gen, queue wait, and execution from step timestamps.
     */
    function extractStepPhases(step) {
        const meta = step.metadata || {};
        const c = step.timestamp_ms ?? parseEpochMs(step.created_at ?? step.createdAt ?? meta.createdAt);
        const e = parseEpochMs(step.viewable_at ?? step.viewableAt ?? meta.viewableAt);
        const f = parseEpochMs(step.started_at ?? step.startedAt ?? meta.startedAt);
        const g = parseEpochMs(step.completed_at ?? step.completedAt ?? step.finishedGeneratingAt ?? meta.completedAt);

        const h = c ?? e ?? f ?? g;
        const k = g ?? f ?? e ?? c;
        let totalMs = (h !== undefined && k !== undefined && k >= h) ? (k - h) : 0;
        const cortexType = step.type || "STEP";

        // Checkpoint steps
        if (cortexType === "CHECKPOINT") {
            const isIntentOnly = Boolean(step.userIntent && !step.sessionSummary);
            return {
                startMs: h || 0,
                endMs: k || (h || 0),
                totalMs: totalMs,
                thinkingDurationMs: 0,
                phases: totalMs > 0 ? [{
                    id: "checkpoint",
                    label: isIntentOnly ? "User Intent Generation" : "Context Summarization",
                    shortLabel: "Compaction",
                    durationMs: totalMs,
                    percentage: 100,
                    colorClass: "bg-cyan-500",
                    hexColor: "#06b6d4",
                }] : [],
            };
        }

        // Model responses (Planner / Model Output)
        if (cortexType === "PLANNER_RESPONSE" || cortexType === "MODEL_OUTPUT") {
            const ttft = (c !== undefined && e !== undefined) ? Math.max(0, e - c) : (step.thinking_duration_ms || 0);
            const streaming = (e !== undefined && g !== undefined) ? Math.max(0, g - e) : (step.streaming_duration_ms || totalMs);
            totalMs = Math.max(totalMs, ttft + streaming);
            const ttftPct = totalMs > 0 ? (ttft / totalMs) * 100 : (ttft > 0 ? 100 : 0);
            const streamPct = totalMs > 0 ? (streaming / totalMs) * 100 : (ttft === 0 ? 100 : 0);

            let thinkingMs = step.thinking_duration_ms || 0;
            if (step.thinkingDuration) {
                thinkingMs = (step.thinkingDuration.seconds || 0) * 1000 + ((step.thinkingDuration.nanos || 0) / 1e6);
            }

            const phases = [];
            if (ttft > 0) {
                phases.push({
                    id: "ttft",
                    label: "Time to First Token (TTFT)",
                    shortLabel: "TTFT",
                    durationMs: ttft,
                    percentage: ttftPct,
                    colorClass: "bg-amber-500",
                    hexColor: "#f59e0b",
                    startMs: c,
                    endMs: e ?? g,
                });
            }
            if (streaming > 0 || phases.length === 0) {
                phases.push({
                    id: "streaming",
                    label: "Model Output Streaming",
                    shortLabel: "Streaming",
                    durationMs: streaming,
                    percentage: streamPct,
                    colorClass: "bg-indigo-500",
                    hexColor: "#6366f1",
                    startMs: e ?? c,
                    endMs: g,
                });
            }
            return {
                startMs: h || 0,
                endMs: k || (h || 0),
                totalMs: totalMs,
                thinkingDurationMs: thinkingMs,
                phases: phases,
            };
        }

        // Tool calls / Terminal / View File
        const argGen = (c !== undefined && e !== undefined && e > c) ? (e - c) : 0;
        const r = e ?? c;
        const queueWait = (r !== undefined && f !== undefined && f > r) ? (f - r) : 0;
        const t = f ?? e ?? c;
        const execDuration = (t !== undefined && g !== undefined && g > t) ? (g - t) : (step.streaming_duration_ms || totalMs);
        totalMs = Math.max(totalMs, argGen + queueWait + execDuration);

        const phases = [];
        if (argGen > 0) {
            phases.push({
                id: "argGen",
                label: "Tool Call Generation",
                shortLabel: "Gen",
                durationMs: argGen,
                percentage: totalMs > 0 ? (argGen / totalMs) * 100 : 0,
                colorClass: "bg-blue-500",
                hexColor: "#3b82f6",
            });
        }
        if (queueWait > 0) {
            phases.push({
                id: "queue",
                label: "Queue Wait",
                shortLabel: "Queue",
                durationMs: queueWait,
                percentage: totalMs > 0 ? (queueWait / totalMs) * 100 : 0,
                colorClass: "bg-purple-500",
                hexColor: "#a855f7",
            });
        }
        if (execDuration > 0 || phases.length === 0) {
            phases.push({
                id: "execution",
                label: "Tool Execution",
                shortLabel: "Exec",
                durationMs: execDuration,
                percentage: totalMs > 0 ? (execDuration / totalMs) * 100 : 100,
                colorClass: "bg-teal-500",
                hexColor: "#14b8a6",
            });
        }

        return {
            startMs: h || 0,
            endMs: k || (h || 0),
            totalMs: totalMs,
            thinkingDurationMs: 0,
            phases: phases,
        };
    }

    function parseEpochMs(cand) {
        if (!cand) return undefined;
        if (typeof cand === "number") return cand > 1e12 ? cand : cand * 1000;
        const parsed = Date.parse(String(cand));
        return Number.isFinite(parsed) ? parsed : undefined;
    }

    /**
     * Idle gap extraction (Auc).
     * Extracts silent periods between active step executions.
     */
    function Auc(stepIntervals, domainStart, domainEnd) {
        if (!stepIntervals || stepIntervals.length === 0) return [];
        const sorted = stepIntervals
            .map(s => ({ startMs: Math.max(domainStart, s.startMs), endMs: Math.min(domainEnd, s.endMs) }))
            .filter(s => s.endMs > s.startMs)
            .sort((a, b) => a.startMs - b.startMs);

        if (sorted.length === 0) return [];

        // Merge overlapping
        const merged = [sorted[0]];
        for (let i = 1; i < sorted.length; i++) {
            const prev = merged[merged.length - 1];
            const curr = sorted[i];
            if (curr.startMs <= prev.endMs) {
                prev.endMs = Math.max(prev.endMs, curr.endMs);
            } else {
                merged.push(curr);
            }
        }

        // Invert to find gaps
        const gaps = [];
        for (let i = 0; i < merged.length - 1; i++) {
            const gapStart = merged[i].endMs;
            const gapEnd = merged[i + 1].startMs;
            if (gapEnd > gapStart) {
                gaps.push({ startMs: gapStart, endMs: gapEnd, durationMs: gapEnd - gapStart });
            }
        }
        return gaps;
    }

    /**
     * Collapsing gap selection algorithm (Buc).
     * Picks largest idle periods exceeding threshold (default 60s) up to visual budget.
     */
    function Buc(gaps, containerWidth, idleThresholdMs = 60000) {
        const budget = Math.max(6, Math.min(4000, Math.floor(containerWidth / 50)));
        const eligible = gaps.filter(g => g.durationMs >= idleThresholdMs);
        eligible.sort((a, b) => b.durationMs - a.durationMs);
        const selected = eligible.slice(0, budget);
        selected.sort((a, b) => a.startMs - b.startMs);
        return selected;
    }

    /**
     * Piecewise continuous coordinate scale engine ($6).
     * Maps continuous timestamps to pixels while collapsing idle intervals.
     */
    function createContinuousScale(domainStart, domainEnd, collapsedGaps, widthPx) {
        const width = Math.max(1, widthPx);
        const numGaps = collapsedGaps.length;
        const idleSegmentWidth = numGaps > 0
            ? Math.min(26, Math.max(6, (width * 0.33) / Math.max(1, numGaps)))
            : 0;
        const activeWidth = Math.max(1, width - numGaps * idleSegmentWidth);

        // Build continuous piecewise segments
        const segments = [];
        let cursorMs = domainStart;

        collapsedGaps.forEach(gap => {
            if (gap.startMs > cursorMs) {
                segments.push({ isIdle: false, startMs: cursorMs, endMs: gap.startMs, durationMs: gap.startMs - cursorMs });
            }
            segments.push({ isIdle: true, startMs: gap.startMs, endMs: gap.endMs, durationMs: gap.durationMs });
            cursorMs = gap.endMs;
        });

        if (cursorMs < domainEnd) {
            segments.push({ isIdle: false, startMs: cursorMs, endMs: domainEnd, durationMs: domainEnd - cursorMs });
        }

        const totalActiveDuration = segments.filter(s => !s.isIdle).reduce((acc, s) => acc + s.durationMs, 0);

        // Assign pixel widths
        let xCursor = 0;
        segments.forEach(s => {
            s.x0 = xCursor;
            if (s.isIdle) {
                s.widthPx = idleSegmentWidth;
            } else {
                s.widthPx = totalActiveDuration > 0 ? (s.durationMs / totalActiveDuration) * activeWidth : activeWidth;
            }
            s.x1 = s.x0 + s.widthPx;
            xCursor = s.x1;
        });

        function toPx(ms) {
            if (ms <= domainStart) return 0;
            if (ms >= domainEnd) return width;
            let low = 0, high = segments.length - 1;
            while (low <= high) {
                const mid = (low + high) >> 1;
                const s = segments[mid];
                if (ms < s.startMs) high = mid - 1;
                else if (ms > s.endMs) low = mid + 1;
                else {
                    const frac = s.durationMs > 0 ? (ms - s.startMs) / s.durationMs : 0;
                    return s.x0 + frac * s.widthPx;
                }
            }
            return 0;
        }

        function toMs(px) {
            if (px <= 0) return domainStart;
            if (px >= width) return domainEnd;
            let low = 0, high = segments.length - 1;
            while (low <= high) {
                const mid = (low + high) >> 1;
                const s = segments[mid];
                if (px < s.x0) high = mid - 1;
                else if (px > s.x1) low = mid + 1;
                else {
                    const frac = s.widthPx > 0 ? (px - s.x0) / s.widthPx : 0;
                    return s.startMs + frac * s.durationMs;
                }
            }
            return domainEnd;
        }

        return { toPx, toMs, segments, width, domainStart, domainEnd, idleSegmentWidth };
    }

    /**
     * Renders the complete Gantt Timeline Visualizer HTML.
     */
    function renderTimelineView(steps, state, containerWidth) {
        const baseWidth = Number.isFinite(containerWidth) && containerWidth > 300 ? containerWidth : 1200;
        const zoom = Math.max(0.5, Math.min(5.0, state.timelineZoom || 1.0));
        const width = Math.round(baseWidth * zoom);
        const stepTimings = steps.map((s, idx) => {
            const timing = extractStepPhases(s);
            return {
                stepIndex: s.step_index !== undefined ? s.step_index : idx,
                arrayIndex: idx,
                type: s.type || "STEP",
                summary: s.thinking || s.content || (s.tool_calls?.[0]?.name) || "",
                tokens: s.tokens || 0,
                timing: timing,
            };
        });

        // Determine domain
        const validStartMs = stepTimings.map(s => s.timing.startMs).filter(t => t > 0);
        const validEndMs = stepTimings.map(s => s.timing.endMs).filter(t => t > 0);
        const domainStart = validStartMs.length > 0 ? Math.min(...validStartMs) : 0;
        const domainEnd = validEndMs.length > 0 ? Math.max(...validEndMs) : (domainStart + 60000);
        const totalDuration = Math.max(1, domainEnd - domainStart);

        // Gaps & Scale
        const intervals = stepTimings.map(s => ({ startMs: s.timing.startMs, endMs: s.timing.endMs }));
        const rawGaps = Auc(intervals, domainStart, domainEnd);
        const collapsedGaps = Buc(rawGaps, width, 60000);
        const scale = createContinuousScale(domainStart, domainEnd, collapsedGaps, width - 40);

        // Timeline mode: steps (default) vs activity
        const mode = state.timelineMode || "steps";

        let tracksHtml = "";
        if (mode === "steps") {
            tracksHtml = stepTimings.map(s => {
                const isSelected = s.arrayIndex === state.selectedIndex;
                const isHovered = state.hoveredItemKey === `step-${s.arrayIndex}`;
                const x0 = Math.max(0, scale.toPx(s.timing.startMs));
                const x1 = Math.max(x0 + 2, scale.toPx(s.timing.endMs));
                const barWidth = Math.max(2, x1 - x0);

                const phasesHtml = s.timing.phases.map(p => `
                    <div style="width: ${p.percentage}%; height: 100%; background: ${p.hexColor};" title="${escapeHtml(p.label)}: ${formatDuration(p.durationMs)}"></div>
                `).join("");

                const durLabel = formatDuration(s.timing.totalMs);
                const showInside = barWidth > 60;

                return `
                    <div class="agyis-timeline-step-row ${isSelected ? "selected" : ""} ${isHovered ? "context-cell-hovered" : ""}"
                         data-step-index="${s.arrayIndex}"
                         data-item-key="step-${s.arrayIndex}"
                         style="display: flex; align-items: center; height: 24px; border-bottom: 1px solid #202024; cursor: pointer;">
                        <div class="agyis-timeline-step-label" style="width: 220px; flex-shrink: 0; font-family: monospace; font-size: 11px; color: #a1a1aa; padding-left: 8px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap;">
                            <span style="font-weight: 700; color: #fbbf24;">#${s.stepIndex}</span>
                            <span style="color: #cbd5e1; margin-left: 4px;">${escapeHtml(s.type)}</span>
                            <span style="color: #71717a; margin-left: 4px; font-size: 10px;">(${s.tokens.toLocaleString()}t)</span>
                        </div>
                        <div style="flex: 1; height: 16px; position: relative; background: #18181b;">
                            <div class="agyis-timeline-step-bar"
                                 style="position: absolute; left: ${x0}px; width: ${barWidth}px; height: 16px; border-radius: 3px; overflow: hidden; display: flex; box-shadow: 0 1px 3px rgba(0,0,0,0.5);">
                                ${phasesHtml}
                                ${showInside ? `<span style="position: absolute; right: 4px; top: 1px; font-size: 9px; font-weight: 700; color: #ffffff; text-shadow: 0 1px 2px #000;">${durLabel}</span>` : ""}
                            </div>
                            ${!showInside && barWidth > 0 ? `<span style="position: absolute; left: ${x1 + 6}px; top: 1px; font-size: 9px; font-family: monospace; color: #a1a1aa;">${durLabel}</span>` : ""}
                        </div>
                    </div>
                `;
            }).join("");
        } else {
            // Activity Mode (compact horizontal lanes)
            const activityLanes = [
                {
                    id: "model",
                    label: "Model & Thinking",
                    color: "#f59e0b",
                    predicate: s => s.type === "PLANNER_RESPONSE" || s.type === "MODEL_OUTPUT" || s.type === "USER_INPUT",
                },
                {
                    id: "terminal",
                    label: "Terminal Execution",
                    color: "#06b6d4",
                    predicate: s => s.type.includes("COMMAND") || s.type.includes("BASH") || (s.summary && (s.summary.startsWith("run_command") || s.summary.startsWith("bash"))),
                },
                {
                    id: "files",
                    label: "Files & Code",
                    color: "#10b981",
                    predicate: s => s.type.includes("FILE") || s.type.includes("WRITE") || s.type.includes("REPLACE") || s.type.includes("DIFF") || (s.summary && (s.summary.startsWith("view_file") || s.summary.startsWith("replace_file") || s.summary.startsWith("write_to_file"))),
                },
                {
                    id: "subagents",
                    label: "Search & Subagents",
                    color: "#a855f7",
                    predicate: s => s.type.includes("SUBAGENT") || s.type.includes("SEARCH") || s.type.includes("FIND") || (s.summary && (s.summary.startsWith("grep_search") || s.summary.startsWith("find_by_name") || s.summary.startsWith("invoke_subagent") || s.summary.startsWith("send_message"))),
                },
                {
                    id: "checkpoints",
                    label: "Compaction & System",
                    color: "#ec4899",
                    predicate: s => s.type === "CHECKPOINT" || s.type === "SYSTEM",
                },
            ];

            tracksHtml = activityLanes.map(lane => {
                const laneSteps = stepTimings.filter(s => lane.predicate(s) || (lane.id === "model" && !activityLanes.slice(1).some(l => l.predicate(s))));
                const laneBarsHtml = laneSteps.map(s => {
                    const isSelected = s.arrayIndex === state.selectedIndex;
                    const isHovered = state.hoveredItemKey === `step-${s.arrayIndex}`;
                    const x0 = Math.max(0, scale.toPx(s.timing.startMs));
                    const x1 = Math.max(x0 + 4, scale.toPx(s.timing.endMs));
                    const barWidth = Math.max(4, x1 - x0);
                    const durLabel = formatDuration(s.timing.totalMs);

                    return `
                        <div class="agyis-timeline-step-row agyis-timeline-step-block ${isSelected ? "selected" : ""} ${isHovered ? "context-cell-hovered" : ""}"
                             data-step-index="${s.arrayIndex}"
                             data-item-key="step-${s.arrayIndex}"
                             title="#${s.stepIndex} ${escapeHtml(s.type)} (${durLabel})"
                             style="position: absolute; left: ${x0}px; width: ${barWidth}px; height: 18px; top: 3px; background: ${lane.color}; border-radius: 2px; cursor: pointer; box-shadow: 0 1px 2px rgba(0,0,0,0.5); opacity: ${isSelected ? 1.0 : 0.85}; outline: ${isSelected ? "2px solid #fbbf24" : "none"}; outline-offset: 1px;">
                        </div>
                    `;
                }).join("");

                return `
                    <div class="agyis-timeline-lane-row" style="display: flex; align-items: center; height: 26px; border-bottom: 1px solid #202024;">
                        <div style="width: 220px; flex-shrink: 0; font-family: monospace; font-size: 11px; color: #a1a1aa; padding-left: 8px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; display: flex; align-items: center; gap: 6px;">
                            <span style="display: inline-block; width: 8px; height: 8px; border-radius: 50%; background: ${lane.color};"></span>
                            <span style="font-weight: 600; color: #e4e4e7;">${escapeHtml(lane.label)}</span>
                            <span style="color: #71717a; font-size: 10px;">(${laneSteps.length})</span>
                        </div>
                        <div style="flex: 1; height: 24px; position: relative; background: #18181b;">
                            ${laneBarsHtml}
                        </div>
                    </div>
                `;
            }).join("");
        }

        // Time Ruler markers
        const rulerTicks = 8;
        let ticksHtml = "";
        for (let i = 0; i <= rulerTicks; i++) {
            const frac = i / rulerTicks;
            const px = frac * (width - 40);
            const tickMs = scale.toMs(px);
            const relMs = tickMs - domainStart;
            ticksHtml += `
                <div style="position: absolute; left: ${px}px; top: 0; bottom: 0; display: flex; flex-direction: column; align-items: center;">
                    <div style="height: 4px; width: 1px; background: #52525b;"></div>
                    <span style="font-size: 9px; font-family: monospace; color: #71717a;">+${formatDuration(relMs)}</span>
                </div>
            `;
        }

        const maxTokens = (state.currentData && state.currentData.max_context_tokens) || 256000;
        const maxCtxLabel = (maxTokens >= 1000000 && maxTokens % 1000000 === 0) ? (maxTokens / 1000000) + "M" : Math.round(maxTokens / 1000) + "k";

        return `
            <div class="agyis-timeline-pane" style="display: flex; flex-direction: column; height: 100%; background: #141416; overflow: hidden;">
                <div style="display: flex; justify-content: space-between; align-items: center; padding: 8px 12px; background: #18181b; border-bottom: 1px solid #27272a; flex-shrink: 0;">
                    <div style="display: flex; align-items: center; gap: 10px;">
                        <span style="font-size: 12px; font-weight: 700; color: #fbbf24;">Timeline (${stepTimings.length} steps, ${formatDuration(totalDuration)})</span>
                        <span style="font-family: monospace; font-size: 11px; color: #a1a1aa;">${maxCtxLabel} Context &bull; Live Trace</span>
                        <div role="group" aria-label="View" style="display: inline-flex; border: 1px solid #3f3f46; border-radius: 4px; overflow: hidden;">
                            <button id="agyis-tl-mode-steps" class="agyis-hud-btn ${mode === "steps" ? "active" : ""}" style="border: none; padding: 2px 6px; font-size: 10px;" title="One row per step, in order — scroll to move through the run">Steps</button>
                            <button id="agyis-tl-mode-activity" class="agyis-hud-btn ${mode === "activity" ? "active" : ""}" style="border: none; padding: 2px 6px; font-size: 10px;" title="Every step packed into a lane per kind — no rows, no scrolling">Activity</button>
                        </div>
                    </div>
                    <div role="group" aria-label="Zoom" style="display: flex; align-items: center; gap: 6px;">
                        <button id="agyis-tl-zoom-in" class="agyis-hud-btn" style="padding: 2px 6px; font-size: 10px;" title="Zoom in">+</button>
                        <button id="agyis-tl-zoom-out" class="agyis-hud-btn" style="padding: 2px 6px; font-size: 10px;" title="Zoom out">−</button>
                        <button id="agyis-tl-zoom-reset" class="agyis-hud-btn" style="padding: 2px 6px; font-size: 10px;" title="Fit the whole trajectory">All</button>
                        <span style="font-size: 10px; color: #71717a; margin-left: 6px;" title="How long a quiet interval must be before it collapses">${collapsedGaps.length} idle collapsed</span>
                    </div>
                </div>
                <div class="agyis-timeline-ruler" style="height: 20px; position: relative; background: #18181b; border-bottom: 1px solid #27272a; margin-left: 220px; flex-shrink: 0;">
                    ${ticksHtml}
                </div>
                <div class="agyis-timeline-track-list" style="flex: 1; overflow-y: auto; overflow-x: hidden;">
                    ${tracksHtml}
                </div>
            </div>
        `;
    }

    /**
     * Binds mouse and zoom interactions on the timeline.
     */
    function bindTimelineEvents(hudEl, state, renderCallback, selectStepCallback) {
        if (!hudEl) return;

        hudEl.querySelector("#agyis-tl-mode-steps")?.addEventListener("click", () => {
            state.timelineMode = "steps";
            if (renderCallback) renderCallback();
        });
        hudEl.querySelector("#agyis-tl-mode-activity")?.addEventListener("click", () => {
            state.timelineMode = "activity";
            if (renderCallback) renderCallback();
        });

        // Timeline Zoom controls
        hudEl.querySelector("#agyis-tl-zoom-in")?.addEventListener("click", () => {
            state.timelineZoom = Math.min(5.0, (state.timelineZoom || 1.0) * 1.3);
            if (renderCallback) renderCallback();
        });
        hudEl.querySelector("#agyis-tl-zoom-out")?.addEventListener("click", () => {
            state.timelineZoom = Math.max(0.5, (state.timelineZoom || 1.0) / 1.3);
            if (renderCallback) renderCallback();
        });
        hudEl.querySelector("#agyis-tl-zoom-reset")?.addEventListener("click", () => {
            state.timelineZoom = 1.0;
            if (renderCallback) renderCallback();
        });

        // Step row selection and hover syncing
        hudEl.querySelectorAll(".agyis-timeline-step-row").forEach(el => {
            el.addEventListener("click", () => {
                const sIdx = parseInt(el.getAttribute("data-step-index") || "0", 10);
                if (selectStepCallback) selectStepCallback(sIdx);
            });

            el.addEventListener("mouseenter", () => {
                const itemKey = el.getAttribute("data-item-key");
                if (itemKey) {
                    state.hoveredItemKey = itemKey;
                    hudEl.querySelectorAll(`[data-item-key="${itemKey}"]`).forEach(mEl => {
                        mEl.classList.add("context-cell-hovered");
                    });
                }
            });

            el.addEventListener("mouseleave", () => {
                const itemKey = el.getAttribute("data-item-key");
                if (itemKey) {
                    state.hoveredItemKey = null;
                    hudEl.querySelectorAll(`[data-item-key="${itemKey}"]`).forEach(mEl => {
                        mEl.classList.remove("context-cell-hovered");
                    });
                }
            });
        });
    }

    // Export module onto window namespace
    global.extractStepPhases = extractStepPhases;
    global.createContinuousScale = createContinuousScale;
    global.formatDuration = formatDuration;
    global.formatShortDuration = formatShortDuration;
    global.formatLongDuration = formatLongDuration;
    global.renderTimelineView = renderTimelineView;
    global.bindTimelineEvents = bindTimelineEvents;

})(typeof window !== "undefined" ? window : globalThis);
