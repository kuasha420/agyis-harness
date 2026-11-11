    function escapeHtml(val) {
        return String(val ?? "")
            .replace(/&/g, "&amp;")
            .replace(/</g, "&lt;")
            .replace(/>/g, "&gt;")
            .replace(/"/g, "&quot;")
            .replace(/'/g, "&#39;");
    }

    function formatBytes(bytes) {
        if (!bytes || bytes <= 0) return "0 B";
        const k = 1024;
        const sizes = ["B", "KB", "MB", "GB"];
        const i = Math.floor(Math.log(bytes) / Math.log(k));
        return parseFloat((bytes / Math.pow(k, i)).toFixed(1)) + " " + sizes[i];
    }

    function renderMarkdownPreview(rawText) {
        if (!rawText) return "<div style='color: #71717a;'>No preview content</div>";

        let trimmed = String(rawText).trim();
        if ((trimmed.startsWith("{") && trimmed.endsWith("}")) || (trimmed.startsWith("[") && trimmed.endsWith("]"))) {
            try {
                const parsedJson = JSON.parse(trimmed);
                trimmed = JSON.stringify(parsedJson, null, 2);
                rawText = "```json\n" + trimmed + "\n```";
            } catch (_) {}
        }

        let escaped = String(rawText).replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");

        escaped = escaped.replace(/```([a-zA-Z0-9_-]*)\n([\s\S]*?)```/g, (m, lang, code) => {
            const badge = lang ? `<span style="font-size: 10px; color: #a1a1aa; font-family: monospace; text-transform: uppercase;">${lang}</span>` : "<span></span>";
            const codeId = "code-" + Math.random().toString(36).substr(2, 9);
            return `
                <div class="agyis-codeblock-wrap">
                    <div style="display: flex; justify-content: space-between; align-items: center; padding: 4px 10px; background: #141416; border-bottom: 1px solid #27272a; border-top-left-radius: 6px; border-top-right-radius: 6px;">
                        ${badge}
                        <button class="agyis-hud-btn agyis-copy-code-btn" data-code-id="${codeId}" style="padding: 2px 6px; font-size: 10px;">📋 Copy</button>
                    </div>
                    <pre id="${codeId}" class="agyis-codeblock" style="border: none; border-radius: 0 0 6px 6px; margin: 0; padding: 10px;"><code class="language-${lang || "none"}">${code.trim()}</code></pre>
                </div>
            `;
        });

        escaped = escaped.replace(/`([^`]+)`/g, "<code style='background: #27272a; padding: 2px 4px; border-radius: 4px; font-family: monospace;'>$1</code>");

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
                        <span>${alertIcon}</span><span>${typeUpper}</span>
                    </div>
                    <div style="font-size: 11px; color: #e4e4e7; line-height: 1.5;">${alertContent}</div>
                </div>
            `;
        });

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
                        <span>${tagIcon}</span><span>&lt;${tag}&gt;</span>
                    </div>
                    <div style="font-size: 11px; color: #e4e4e7; line-height: 1.5;">${content}</div>
                </div>
            `;
        });

        escaped = escaped.replace(/(?:^|\n)###\s+([^\n]+)/g, '<h3 style="font-size: 12px; font-weight: 700; color: #fbbf24; margin: 8px 0 4px 0;">$1</h3>');
        escaped = escaped.replace(/(?:^|\n)##\s+([^\n]+)/g, '<h2 style="font-size: 13px; font-weight: 700; color: #f59e0b; margin: 10px 0 6px 0;">$1</h2>');
        escaped = escaped.replace(/(?:^|\n)#\s+([^\n]+)/g, '<h1 style="font-size: 14px; font-weight: 700; color: #f59e0b; margin: 12px 0 8px 0;">$1</h1>');
        escaped = escaped.replace(/\*\*([^*]+)\*\*/g, '<strong style="color: #f4f4f5;">$1</strong>');
        escaped = escaped.replace(/\*([^*]+)\*/g, '<em style="color: #cbd5e1;">$1</em>');
        escaped = escaped.replace(/(?:^|\n)(?:[-*]|\d+\.)\s+([^\n]+)/g, '<div style="padding-left: 12px; margin: 2px 0; color: #e4e4e7;">&bull; $1</div>');

        if (escaped.includes("|") && escaped.includes("\n")) {
            const lines = escaped.split("\n");
            let inTable = false;
            let tableHtml = "<table class='agyis-markdown-table'>";
            const remainingLines = [];
            for (let i = 0; i < lines.length; i++) {
                const line = lines[i].trim();
                if (line.startsWith("|") && line.endsWith("|")) {
                    if (!inTable) inTable = true;
                    const cols = line.split("|").slice(1, -1).map(c => c.trim());
                    if (cols.every(c => c.match(/^:?-+:?$/))) continue;
                    const tag = tableHtml.indexOf("<tr>") === -1 ? "th" : "td";
                    tableHtml += `<tr>${cols.map(c => `<${tag}>${c}</${tag}>`).join("")}</tr>`;
                } else {
                    if (inTable) { inTable = false; tableHtml += "</table>"; remainingLines.push(tableHtml); }
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

    function stepPillClassForType(type) {
        if (type === "PLANNER_RESPONSE") return "agyis-hud-pill-amber";
        if (type === "CHECKPOINT") return "agyis-hud-pill-green";
        if (type.includes("COMMAND") || type.includes("TOOL")) return "agyis-hud-pill-teal";
        if (type.includes("FILE") || type.includes("WRITE") || type.includes("REPLACE")) return "agyis-hud-pill-green";
        if (type === "INVOKE_SUBAGENT") return "agyis-hud-pill-purple";
        if (type === "SYSTEM") return "agyis-hud-pill-zinc";
        return "agyis-hud-pill-blue";
    }

    function buildContextSegmentsAndRows(cur, state, steps, activeEpoch, epochSteps, maxTokens) {
        const breakdown = cur.token_breakdown || { system_prompt: 0, tool_defs: 0, checkpoint: 0, user: 0, model: 0, tool: 0, thought: 0, system: 0, unattributed: 0 };
        const segments = [];

        const sysSlices = cur.system_prompt_slices || [];
        if (sysSlices.length > 0) {
            sysSlices.forEach((sl, sidx) => {
                if ((sl.tokens || 0) > 0) {
                    segments.push({
                        id: `sys-${(sl.name || "sec").toLowerCase().replace(/[^a-z0-9]/g, "-")}-${sidx}`,
                        type: "system_prompt",
                        label: `System: ${sl.name}`,
                        tokens: sl.tokens,
                        color: sl.color || "#6366f1",
                        colorKey: "bg-indigo-500",
                        tooltipContent: `${sl.name} (${sl.tokens.toLocaleString()} tokens)`,
                    });
                }
            });
        } else if ((breakdown.system_prompt || 0) > 0) {
            segments.push({ id: "sys-prompt", type: "system_prompt", label: "System Prompt", tokens: breakdown.system_prompt, color: "#6366f1", colorKey: "bg-indigo-500", tooltipContent: "Measured system instructions" });
        }

        const toolSlices = cur.tool_def_slices || [];
        if (toolSlices.length > 0) {
            toolSlices.forEach((sl, tidx) => {
                if ((sl.tokens || 0) > 0) {
                    segments.push({
                        id: `tool-${(sl.name || "tool").toLowerCase().replace(/[^a-z0-9]/g, "-")}-${tidx}`,
                        type: "tool_definition",
                        label: `Tools: ${sl.name}`,
                        tokens: sl.tokens,
                        color: sl.color || "#06b6d4",
                        colorKey: "bg-cyan-500",
                        tooltipContent: `${sl.name} (${sl.tokens.toLocaleString()} tokens)`,
                    });
                }
            });
        } else if ((breakdown.tool_defs || 0) > 0) {
            segments.push({ id: "tool-defs", type: "tool_definition", label: "Tool Defs", tokens: breakdown.tool_defs, color: "#06b6d4", colorKey: "bg-cyan-500", tooltipContent: "Measured tool schemas" });
        }

        const curEpochs = cur.epochs || [];
        const isLatestEpoch = curEpochs.length === 0 || state.activeEpochIndex >= curEpochs.length - 1;
        const epochBreakdown = (activeEpoch && activeEpoch.token_breakdown) || (isLatestEpoch ? breakdown : null);

        const hasCpInEpoch = epochSteps.some(s => s.type === "CHECKPOINT");
        const epochCpTok = (epochBreakdown && epochBreakdown.checkpoint) || 0;
        if (!hasCpInEpoch && activeEpoch.has_checkpoint && epochCpTok > 0) {
            segments.push({ id: "checkpoint-summary", type: "checkpoint", label: "Checkpoint", tokens: epochCpTok, color: "#16a34a", colorKey: "bg-green-600", tooltipContent: activeEpoch.summary || "Compacted context summary" });
        }

        epochSteps.forEach((s, offset) => {
            const arrIdx = activeEpoch.start_index + offset;
            const displayIdx = s.step_index !== undefined ? s.step_index : arrIdx;
            const sTok = s.tokens || Math.round((s.size_bytes || 100) / 3.5);
            let segColor = "#3b82f6";
            let segColorKey = "bg-blue-600";
            let segLabel = `Step #${displayIdx}: ${s.type || "STEP"}`;

            if (s.type === "PLANNER_RESPONSE" || s.type === "MODEL_OUTPUT") {
                segColor = "#f59e0b"; segColorKey = "bg-amber-600";
            } else if (s.type === "CHECKPOINT") {
                segColor = "#16a34a"; segColorKey = "bg-green-600";
                segLabel = `Step #${displayIdx}: Checkpoint`;
            } else if ((s.type || "").includes("COMMAND") || (s.type || "").includes("TOOL") || (s.type || "").includes("FILE") || (s.type || "").includes("WRITE") || (s.type || "").includes("REPLACE") || (s.type || "").includes("SEARCH")) {
                segColor = "#14b8a6"; segColorKey = "bg-teal-600";
            } else if (s.type === "SYSTEM") {
                segColor = "#a855f7"; segColorKey = "bg-purple-600";
            }

            let tip = s.thinking || s.content || "";
            if (s.type === "CHECKPOINT") tip = s.compaction_summary || s.summary || s.sessionSummary || tip || "Checkpoint";
            if (!tip && (s.tool_calls || []).length > 0) tip = s.tool_calls.map(tc => tc.name).join(", ");
            tip = tip.replace(/\n/g, " ").slice(0, 160);

            segments.push({
                id: `step-${arrIdx}`,
                type: "step",
                stepIndex: arrIdx,
                label: segLabel,
                tokens: sTok,
                color: segColor,
                colorKey: segColorKey,
                tooltipContent: tip,
            });
        });

        const unattrTok = Math.max(
            0,
            (activeEpoch && activeEpoch.unattributed !== undefined)
                ? activeEpoch.unattributed
                : ((epochBreakdown && epochBreakdown.unattributed) || 0)
        );
        if (unattrTok > 0) {
            segments.push({
                id: "unattributed-context",
                type: "unattributed",
                label: "Unattributed Overhead",
                tokens: unattrTok,
                color: "#64748b",
                colorKey: "bg-slate-500",
                tooltipContent: `Unattributed context tokens (${unattrTok.toLocaleString()})`,
            });
        }

        const rawSegmentsSum = segments.reduce((acc, seg) => acc + (seg.tokens || 0), 0);
        let activeTokensSum = segments.reduce((acc, seg) => acc + (seg.tokens || 0), 0);
        const selectedEpochTotal = (activeEpoch && activeEpoch.total_tokens !== undefined)
            ? (activeEpoch.total_tokens || 0)
            : (isLatestEpoch ? (cur.total_tokens || 0) : rawSegmentsSum);
        activeTokensSum = Math.max(selectedEpochTotal, activeTokensSum);
        const totalTokens = Math.max(selectedEpochTotal, activeTokensSum);

        const ROW_CAPACITY = Math.max(64000, Math.ceil(maxTokens / 4));
        const rowCount = Math.min(4, Math.max(1, Math.ceil(activeTokensSum / ROW_CAPACITY)));
        const totalActiveCapacity = rowCount * ROW_CAPACITY;
        const scaleFactor = (selectedEpochTotal > 0 && rawSegmentsSum > 0 && selectedEpochTotal > rawSegmentsSum)
            ? (activeTokensSum / rawSegmentsSum)
            : 1.0;

        if (rawSegmentsSum === 0 && activeTokensSum > 0) {
            segments.push({ id: "context-gap", type: "unattributed", label: "Unattributed Context", tokens: activeTokensSum, color: "#64748b", colorKey: "bg-slate-500", tooltipContent: `Unattributed Context (${activeTokensSum.toLocaleString()} tokens)` });
        }

        const rows = [];
        for (let r = 0; r < rowCount; r++) rows.push([]);
        let tCursor = 0;
        segments.forEach((seg, sIdx) => {
            let segTokens = Math.max(0, Math.round((seg.tokens || 0) * scaleFactor));
            if (scaleFactor > 1.0 && sIdx === segments.length - 1) segTokens = Math.max(0, activeTokensSum - tCursor);
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

        let barSegmentsHtml = "";
        rows.forEach((row, rIdx) => {
            const cellsHtml = row.map(cell => {
                const seg = cell.segment;
                const isUnused = seg === null;
                const isSelected = !isUnused && seg.stepIndex !== undefined && seg.stepIndex === state.selectedIndex;
                const colorStyle = isUnused ? "background: #27272a;" : `background: ${seg.color};`;
                const borderRight = isUnused ? "" : "border-right: 1px solid rgba(0, 0, 0, 0.35);";
                const ariaLabel = isUnused ? `Unused capacity: ${cell.sliceTokens.toLocaleString()} tokens` : `${seg.label}: ${seg.tokens.toLocaleString()} tokens`;
                const leftPct = (cell.startFraction * 100).toFixed(4);
                const widthPct = (cell.widthFraction * 100).toFixed(4);
                const stepIdxAttr = (!isUnused && seg.stepIndex !== undefined) ? `data-step-index="${seg.stepIndex}"` : "";
                return `
                    <button type="button"
                            class="agyis-context-segment ${isUnused ? "context-cell-unused" : ""} ${isSelected ? "context-cell-selected" : ""}"
                            ${stepIdxAttr}
                            data-seg-id="${escapeHtml(isUnused ? "unused" : seg.id)}"
                            data-seg-name="${escapeHtml(isUnused ? "Unused Capacity" : seg.label)}"
                            data-seg-tokens="${isUnused ? cell.sliceTokens : seg.tokens}"
                            data-seg-pct="${Math.min(100, (((isUnused ? cell.sliceTokens : seg.tokens) / maxTokens) * 100)).toFixed(1)}"
                            data-tooltip="${isUnused ? "" : escapeHtml(seg.tooltipContent || "")}"
                            aria-label="${escapeHtml(ariaLabel)}"
                            style="position: absolute; top: 0; bottom: 0; left: ${leftPct}%; width: ${widthPct}%; ${colorStyle} ${borderRight}">
                    </button>
                `;
            }).join("");
            barSegmentsHtml += `
                <div class="agyis-context-row-wrap" style="display: flex; align-items: center; gap: 8px;">
                    <span class="agyis-context-row-label" style="font-family: ui-monospace, monospace; font-size: 10px; color: #a1a1aa; width: 34px; text-align: right; flex-shrink: 0; user-select: none;">${Math.round((rIdx * ROW_CAPACITY) / 1000)}k</span>
                    <div class="agyis-context-row-track" style="flex: 1; height: 18px; position: relative; background: #27272a; border-radius: 4px; overflow: hidden; border: 1px solid #3f3f46;">
                        ${cellsHtml}
                    </div>
                </div>
            `;
        });

        return { activeTokensSum, totalTokens, rowCount, totalActiveCapacity, barSegmentsHtml };
    }

    function buildMainDeckViewHtml(cur, state, steps, epochs, activeEpoch, epochSteps, filteredIndices, inspectorContentHtml, currentStep, conversationList) {
        const maxTokens = cur.max_context_tokens || 256000;
        const { activeTokensSum, totalTokens, rowCount, totalActiveCapacity, barSegmentsHtml } =
            buildContextSegmentsAndRows(cur, state, steps, activeEpoch, epochSteps, maxTokens);

        const rawFillPct = maxTokens > 0 ? (activeTokensSum / maxTokens) * 100 : 0;
        const clampedFillPct = Math.min(100, rawFillPct).toFixed(1);
        const effProvisional = (activeEpoch && activeEpoch.is_provisional !== undefined) ? activeEpoch.is_provisional : cur.is_provisional;
        const effCacheTokens = (activeEpoch && typeof activeEpoch.cache_tokens === "number") ? activeEpoch.cache_tokens : (cur.cache_tokens || 0);
        const estBadge = effProvisional ? ' <span class="agyis-hud-pill agyis-hud-pill-amber" title="Provisional estimate">~est</span>' : "";
        const burnRate = cur.burn_rate_tokens_per_min || 0;
        const burnBadge = burnRate > 0 ? ` <span class="agyis-hud-pill agyis-hud-pill-teal">${burnRate.toFixed(0)} tok/m</span>` : "";
        const cacheHitBadge = effCacheTokens > 0 ? ` <span class="agyis-hud-pill agyis-hud-pill-green">Cache: ${(effCacheTokens / 1000).toFixed(1)}k</span>` : "";

        const subagents = cur.subagents || [];
        const subagentInfos = cur.subagent_infos || [];
        const isChildView = Boolean(cur.parent_id);
        const subagentsDropdownHtml = subagents.length > 0 ? `
            <div style="position: relative;">
                <button id="agyis-subagents-dropdown-toggle" class="agyis-hud-pill agyis-hud-pill-purple" style="cursor: pointer;">
                    [ ${subagents.length} Child Subagent${subagents.length === 1 ? "" : "s"} ▾ ]
                </button>
                <div id="agyis-subagents-menu" style="display: ${state.subagentsDropdownOpen ? "block" : "none"}; position: absolute; top: 100%; left: 0; margin-top: 4px; background: #18181b; border: 1px solid #3f3f46; border-radius: 6px; box-shadow: 0 10px 25px rgba(0,0,0,0.8); z-index: 200; min-width: 240px; max-height: 220px; overflow-y: auto;">
                    ${subagents.map((sid, idx) => {
                        const info = subagentInfos.find(si => si.id === sid) || { name: `Subagent #${idx + 1}`, summary: sid };
                        return `
                            <div class="agyis-subagent-item" data-sub-id="${escapeHtml(sid)}" style="padding: 6px 10px; cursor: pointer; border-bottom: 1px solid #27272a; transition: background 0.15s;" onmouseover="this.style.background='#27272a'" onmouseout="this.style.background='transparent'">
                                <div style="font-weight: 600; color: #c084fc; font-size: 11px;">${escapeHtml(info.name)}</div>
                                <div style="font-size: 10px; color: #a1a1aa; font-family: monospace;">${escapeHtml(sid.slice(0, 16))}...</div>
                            </div>
                        `;
                    }).join("")}
                </div>
            </div>
        ` : "";

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
            const type = s.type || "STEP";
            const pillClass = stepPillClassForType(type);
            const status = s.status || "DONE";
            let statusPillClass = "agyis-hud-pill-green";
            if (status === "ERROR") statusPillClass = "agyis-hud-pill-red";
            else if (status === "RUNNING") statusPillClass = "agyis-hud-pill-blue";
            else if (status === "WAITING") statusPillClass = "agyis-hud-pill-amber";
            let details = s.thinking || s.content || "";
            if (type === "CHECKPOINT") details = s.compaction_summary || s.summary || s.sessionSummary || details || "Checkpoint";
            if (!details && (s.tool_calls || []).length > 0) details = s.tool_calls.map(tc => tc.name + "(" + JSON.stringify(tc.args || {}) + ")").join("; ");
            details = details.replace(/\n/g, " ").slice(0, 160).replace(/</g, "&lt;").replace(/>/g, "&gt;");
            return `
                <div class="agyis-step-grid-row agyis-step-grid-item ${idx === state.selectedIndex ? "selected" : ""}" data-index="${idx}">
                    <div style="color: #71717a;">${s.exec_index || 1}</div>
                    <div style="color: #71717a;">${s.inv_index || 1}</div>
                    <div style="font-weight: 700;">#${s.step_index ?? idx}</div>
                    <div><span class="agyis-hud-pill ${pillClass}">${type}</span></div>
                    <div style="color: #a1a1aa; overflow: hidden; text-overflow: ellipsis; white-space: nowrap;">${details || "—"}</div>
                    <div><span class="agyis-hud-pill ${statusPillClass}">${status}</span></div>
                    <div style="text-align: right; color: #cbd5e1;">${(s.tokens || 0).toLocaleString()}</div>
                    <div style="text-align: right; color: #71717a;">${formatBytes(s.size_bytes)}</div>
                </div>
            `;
        }).join("");

        const timelineCardsHtml = steps.map((s, idx) => {
            const type = s.type || "STEP";
            const pillClass = stepPillClassForType(type);
            let details = s.thinking || s.content || "";
            if (type === "CHECKPOINT") details = s.compaction_summary || s.summary || s.sessionSummary || details || "Checkpoint";
            if (!details && (s.tool_calls || []).length > 0) details = s.tool_calls.map(tc => tc.name).join("; ");
            details = details.replace(/\n/g, " ").slice(0, 140).replace(/</g, "&lt;").replace(/>/g, "&gt;");
            const ttftSec = ((s.thinking_duration_ms || 0) / 1000).toFixed(2);
            const streamSec = ((s.streaming_duration_ms || 0) / 1000).toFixed(2);
            const totalSec = ((s.total_duration_ms || 0) / 1000).toFixed(2);
            const totalMs = Math.max(1, s.total_duration_ms || 1);
            const ttftPct = Math.round(((s.thinking_duration_ms || 0) / totalMs) * 100);
            const streamPct = 100 - ttftPct;
            return `
                <div class="agyis-timeline-card ${idx === state.selectedIndex ? "selected" : ""}" data-index="${idx}">
                    <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 6px;">
                        <div style="display: flex; align-items: center; gap: 8px;">
                            <span style="font-weight: 700; color: #fbbf24;">#${s.step_index ?? idx}</span>
                            <span class="agyis-hud-pill ${pillClass}">${type}</span>
                        </div>
                        <span style="font-size: 10px; color: #a1a1aa;">${(s.tokens || 0).toLocaleString()} tok &bull; ${formatBytes(s.size_bytes)}</span>
                    </div>
                    <div style="font-size: 11px; color: #cbd5e1; margin-bottom: 6px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap;">${details || "—"}</div>
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

        const q = (state.filterQuery || "").trim().toLowerCase();
        const matchCount = state.searchMatchIndices.length;
        const matchDisplay = q ? `${matchCount > 0 ? state.currentMatchIdx + 1 : 0}/${matchCount}` : `${steps.length}/${steps.length}`;
        const maxCtxLabel = (maxTokens >= 1000000 && maxTokens % 1000000 === 0) ? (maxTokens / 1000000) + "M" : Math.round(maxTokens / 1000) + "k";

        const html = `
            <div class="agyis-hud-box ${state.isMaximized ? "maximized" : ""}">
                <div class="agyis-hud-header">
                    <div class="agyis-hud-header-left">
                        <span class="agyis-hud-pill agyis-hud-pill-amber">⚡ Trajectory Debug View</span>
                        <select id="agyis-convo-select" class="agyis-hud-select" title="Switch Conversation">
                            ${conversationList.map(c => `<option value="${escapeHtml(c.id)}" ${c.id === cur.conversation_id ? "selected" : ""}>${escapeHtml(c.summary || c.id.slice(0, 12))} (${new Date(c.mtime * 1000).toLocaleTimeString()})</option>`).join("")}
                        </select>
                        <button id="agyis-refresh-btn" class="agyis-hud-btn" title="Refresh Trajectory from Server">🔄 Refresh</button>
                        ${isChildView ? '<button id="agyis-parent-btn" class="agyis-hud-pill agyis-hud-pill-blue" style="cursor: pointer;" title="Back to parent conversation">↑ Parent</button>' : ""}
                        ${subagentsDropdownHtml}
                        <div class="agyis-hud-search-box">
                            <input id="agyis-search-input" class="agyis-hud-search-input" type="text" placeholder="Search steps..." value="${escapeHtml(state.filterQuery || "")}">
                            <span class="agyis-hud-search-counter">${matchDisplay}</span>
                            ${q ? '<button id="agyis-search-clear" style="background: none; border: none; color: #a1a1aa; cursor: pointer; padding: 0 2px;">✕</button>' : ""}
                        </div>
                    </div>
                    <div class="agyis-hud-header-right">
                        <div style="display: inline-flex; border: 1px solid #3f3f46; border-radius: 6px; overflow: hidden;">
                            <button id="agyis-layout-side" class="agyis-hud-btn ${state.layoutOrientation === "horizontal" ? "active" : ""}" style="border: none; border-radius: 0;" title="Side-by-side layout">◫ Side-by-Side</button>
                            <button id="agyis-layout-stack" class="agyis-hud-btn ${state.layoutOrientation === "vertical" ? "active" : ""}" style="border: none; border-radius: 0;" title="Stacked layout">☰ Stacked</button>
                        </div>
                        <button id="agyis-maximize-btn" class="agyis-hud-btn" title="Toggle Maximize">${state.isMaximized ? "❐ Restore" : "⛶ Maximize"}</button>
                        <button id="agyis-close-btn" class="agyis-hud-btn" title="Close (Escape)">✕</button>
                    </div>
                </div>
                <div id="agyis-hud-deck" class="agyis-hud-main-deck ${state.layoutOrientation}">
                    <div class="agyis-grid-pane">
                        <div class="agyis-main-deck-tabs">
                            <button class="agyis-main-tab-btn ${state.mainDeckTab === "context" ? "active" : ""}" data-main-tab="context">[ Context Window ]</button>
                            <button class="agyis-main-tab-btn ${state.mainDeckTab === "timeline" ? "active" : ""}" data-main-tab="timeline">[ Timeline ]</button>
                        </div>
                        ${state.mainDeckTab === "context" ? `
                            <div class="agyis-context-bar-wrap">
                                <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 6px; flex-wrap: wrap; gap: 8px;">
                                    <div style="display: flex; align-items: center; gap: 8px;">
                                        <span style="font-size: 11px; font-weight: 700; color: #fbbf24;">Context Window (${rowCount} row${rowCount > 1 ? "s" : ""})</span>
                                        <div style="display: inline-flex; align-items: center; gap: 4px; background: #202023; border: 1px solid #3f3f46; border-radius: 6px; padding: 2px 6px;">
                                            <button id="agyis-epoch-prev" class="agyis-hud-btn" style="padding: 2px 6px; font-size: 10px;" ${state.activeEpochIndex <= 0 ? 'disabled style="opacity:0.4; cursor:default;"' : ""}>◀ Prev Epoch</button>
                                            <span style="font-size: 10px; font-family: monospace; color: #cbd5e1; padding: 0 4px;">Epoch ${state.activeEpochIndex + 1} of ${epochs.length} (Steps #${activeEpoch.start_index}-#${activeEpoch.end_index})</span>
                                            <button id="agyis-epoch-next" class="agyis-hud-btn" style="padding: 2px 6px; font-size: 10px;" ${state.activeEpochIndex >= epochs.length - 1 ? 'disabled style="opacity:0.4; cursor:default;"' : ""}>Next Epoch ▶</button>
                                        </div>
                                    </div>
                                    <div style="font-family: monospace; font-size: 11px; color: #a1a1aa; display: flex; align-items: center; gap: 6px;">
                                        <span>Active Context: <b style="color: #38bdf8;">${activeTokensSum.toLocaleString()}</b> / ${maxTokens.toLocaleString()} max (${clampedFillPct}%${rawFillPct > 100.05 ? " over" : ""})</span>${estBadge}${cacheHitBadge}${burnBadge}
                                    </div>
                                </div>
                                <div class="agyis-context-track" style="display: flex; flex-direction: column; gap: 3px; background: transparent; border: none;">${barSegmentsHtml}</div>
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
                                        <span class="agyis-legend-item"><span class="agyis-legend-dot" style="background: #64748b;"></span> Unattributed</span>
                                        <span class="agyis-legend-item"><span class="agyis-legend-dot" style="background: #3f3f46;"></span> Unused</span>
                                    </div>
                                </div>
                            </div>
                            <div class="agyis-step-grid-row agyis-step-grid-header">
                                <div>EXEC</div><div>INV</div><div>STEP</div><div>TYPE</div><div>DETAILS</div><div>STATUS</div>
                                <div style="text-align: right;">TOKENS</div><div style="text-align: right;">SIZE</div>
                            </div>
                            <div class="agyis-step-grid-body">${gridRowsHtml || "<div style='padding: 20px; text-align: center; color: #71717a;'>No steps match current search query</div>"}</div>
                            <div class="agyis-step-grid-pagination" style="display: flex; justify-content: space-between; align-items: center; padding: 6px 10px; background: #141416; border-top: 1px solid #27272a; font-size: 11px;">
                                <div style="display: flex; gap: 4px; align-items: center;">
                                    <button id="agyis-page-prev" class="agyis-hud-btn" ${state.tablePage <= 0 ? 'disabled style="opacity:0.4; cursor:default;"' : ""}>◀ Prev 50</button>
                                    <span style="font-family: monospace; color: #cbd5e1; padding: 0 6px;">Page ${state.tablePage + 1} of ${totalPages} (${totalFiltered > 0 ? pageStart + 1 : 0}-${pageEnd} of ${totalFiltered})</span>
                                    <button id="agyis-page-next" class="agyis-hud-btn" ${state.tablePage >= totalPages - 1 ? 'disabled style="opacity:0.4; cursor:default;"' : ""}>Next 50 ▶</button>
                                </div>
                                <button id="agyis-page-jump-selected" class="agyis-hud-btn" title="Jump to selected step">Jump to Selected</button>
                            </div>
                        ` : `
                            <div class="agyis-timeline-pane">
                                <div style="display: flex; justify-content: space-between; align-items: center; padding: 6px 10px; background: #141416; border: 1px solid #27272a; border-radius: 6px; font-size: 11px; color: #a1a1aa;">
                                    <span><b>Trajectory Timeline:</b> ${steps.length} steps (${totalTokens.toLocaleString()} tokens)${estBadge}${burnBadge}</span>
                                    <span style="font-family: monospace;">${maxCtxLabel} Context &bull; Live Trace</span>
                                </div>
                                ${timelineCardsHtml || "<div style='padding: 20px; text-align: center; color: #71717a;'>No timeline steps available</div>"}
                            </div>
                        `}
                    </div>
                    <div id="agyis-splitter" class="agyis-splitter"></div>
                    <div class="agyis-inspector-pane">
                        <div class="agyis-inspector-header">
                            <div style="display: flex; align-items: center; gap: 8px;">
                                <span style="font-weight: 700; font-size: 12px;">Step #${currentStep ? (currentStep.step_index ?? state.selectedIndex) : "-"}</span>
                                ${currentStep ? `<span class="agyis-hud-pill agyis-hud-pill-amber">${escapeHtml(currentStep.type || "STEP")}</span>` : ""}
                            </div>
                            <div style="display: flex; gap: 4px; align-items: center;">
                                <button id="agyis-step-first" class="agyis-hud-btn" ${state.selectedIndex <= 0 ? 'disabled style="opacity:0.4;"' : ""}>«</button>
                                <button id="agyis-step-prev" class="agyis-hud-btn" ${state.selectedIndex <= 0 ? 'disabled style="opacity:0.4;"' : ""}>‹</button>
                                <span style="font-size: 11px; font-family: monospace; padding: 0 4px; color: #a1a1aa;">${steps.length > 0 ? state.selectedIndex + 1 : 0} / ${steps.length}</span>
                                <button id="agyis-step-next" class="agyis-hud-btn" ${state.selectedIndex >= steps.length - 1 ? 'disabled style="opacity:0.4;"' : ""}>›</button>
                                <button id="agyis-step-last" class="agyis-hud-btn" ${state.selectedIndex >= steps.length - 1 ? 'disabled style="opacity:0.4;"' : ""}>»</button>
                            </div>
                        </div>
                        <div class="agyis-inspector-tabs">
                            <button class="agyis-hud-btn ${state.activeTab === "step" ? "active" : ""}" data-tab="step">Step</button>
                            <button class="agyis-hud-btn ${state.activeTab === "invocation" ? "active" : ""}" data-tab="invocation">Invocation</button>
                            <button class="agyis-hud-btn ${state.activeTab === "execution" ? "active" : ""}" data-tab="execution">Execution</button>
                            <button class="agyis-hud-btn ${state.activeTab === "trajectory" ? "active" : ""}" data-tab="trajectory">Trajectory</button>
                        </div>
                        <div class="agyis-inspector-content" id="agyis-inspector-body">${inspectorContentHtml}</div>
                    </div>
                </div>
            </div>
        `;
        return { html, totalPages, pageSize };
    }
