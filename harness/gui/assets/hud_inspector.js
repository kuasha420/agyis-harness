    function syntaxHighlightJson(jsonObj) {
        let jsonStr = typeof jsonObj !== "string" ? JSON.stringify(jsonObj, null, 2) : jsonObj;
        if (!jsonStr) return "";
        jsonStr = jsonStr.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
        return jsonStr.replace(/("(\\u[a-zA-Z0-9]{4}|\\[^u]|[^\\"])*"(\s*:)?|\b(true|false|null)\b|-?\d+(?:\.\d*)?(?:[eE][+\-]?\d+)?)/g, function (match) {
            let clsColor = "#f59e0b";
            if (/^"/.test(match)) clsColor = /:$/.test(match) ? "#38bdf8" : "#a3e635";
            else if (/true|false/.test(match)) clsColor = "#c084fc";
            else if (/null/.test(match)) clsColor = "#71717a";
            return `<span style="color: ${clsColor};">${match}</span>`;
        });
    }

    function escapeHtmlText(val) {
        return String(val || "").replace(/</g, "&lt;").replace(/>/g, "&gt;");
    }

    function escapeInspectorHtml(val) {
        return String(val ?? "")
            .replace(/&/g, "&amp;")
            .replace(/</g, "&lt;")
            .replace(/>/g, "&gt;")
            .replace(/"/g, "&quot;")
            .replace(/'/g, "&#39;");
    }

    function buildStepBodyHtml(currentStep, state, toolStripHtml, thinkingBlockHtml) {
        const cType = currentStep.type || "STEP";
        if (cType === "RUN_COMMAND" || currentStep.command !== undefined) {
            const cmd = currentStep.command || (currentStep.tool_calls?.[0]?.args?.CommandLine || currentStep.tool_calls?.[0]?.args?.command || "");
            const exitCode = currentStep.exitCode !== undefined ? currentStep.exitCode : (currentStep.tool_calls?.[0]?.args?.exitCode ?? 0);
            const exitBadgeClass = exitCode === 0 ? "agyis-hud-pill-green" : "agyis-hud-pill-red";
            const outputRaw = currentStep.output || (currentStep.tool_calls?.[0]?.output || "");
            const cleanOutput = String(outputRaw).replace(/\u001b\[[0-9;]*[a-zA-Z]/g, "");
            const lineCount = cleanOutput ? cleanOutput.split(/\r?\n/).length : 0;
            return `
                <div class="agyis-terminal-card" style="background: #141416; border: 1px solid #27272a; border-radius: 6px; overflow: hidden; margin-bottom: 10px;">
                    <div style="display: flex; justify-content: space-between; align-items: center; padding: 6px 10px; background: #1c1c1f; border-bottom: 1px solid #27272a;">
                        <div style="font-family: monospace; font-size: 11px; color: #f4f4f5; display: flex; align-items: center; gap: 6px;">
                            <span style="color: #38bdf8;">$</span>
                            <span>${escapeHtmlText(cmd)}</span>
                        </div>
                        <span class="agyis-hud-pill ${exitBadgeClass}">exit ${exitCode}</span>
                    </div>
                    <div style="padding: 4px 10px; font-size: 10px; color: #71717a; border-bottom: 1px solid #202023; display: flex; justify-content: space-between;">
                        <span>Terminal Output (${lineCount} lines)</span>
                        <span>${currentStep.cwd ? `cwd: ${escapeHtmlText(currentStep.cwd)}` : ""}</span>
                    </div>
                    <pre class="agyis-codeblock" style="border: none; margin: 0; padding: 10px; max-height: 380px; overflow-y: auto;"><code class="language-bash">${escapeHtmlText(cleanOutput)}</code></pre>
                </div>
            `;
        }
        if (cType === "VIEW_FILE" || (currentStep.filePath && currentStep.fileContent !== undefined)) {
            const fPath = currentStep.filePath || (currentStep.tool_calls?.[0]?.args?.AbsolutePath || currentStep.tool_calls?.[0]?.args?.filePath || "");
            const fContent = currentStep.fileContent || (currentStep.tool_calls?.[0]?.output || currentStep.content || "");
            const lineCount = fContent ? fContent.split(/\r?\n/).length : 0;
            return `
                <div class="agyis-file-card" style="background: #141416; border: 1px solid #27272a; border-radius: 6px; overflow: hidden; margin-bottom: 10px;">
                    <div style="display: flex; justify-content: space-between; align-items: center; padding: 6px 10px; background: #1c1c1f; border-bottom: 1px solid #27272a;">
                        <a href="file://${escapeHtmlText(fPath)}" target="_blank" style="font-family: monospace; font-size: 11px; color: #38bdf8; text-decoration: none;">
                            📄 ${escapeHtmlText(fPath)}
                        </a>
                        <span style="font-size: 10px; color: #a1a1aa;">${lineCount} lines</span>
                    </div>
                    <pre class="agyis-codeblock" style="border: none; margin: 0; padding: 10px; max-height: 400px; overflow-y: auto;"><code>${escapeHtmlText(fContent)}</code></pre>
                </div>
            `;
        }
        if (cType === "CODE_ACTION" || currentStep.diffLines !== undefined) {
            const fPath = currentStep.filePath || (currentStep.tool_calls?.[0]?.args?.TargetFile || "");
            const diffLines = currentStep.diffLines || [];
            const diffHtml = (Array.isArray(diffLines) && diffLines.length > 0)
                ? diffLines.map(dl => {
                    const txt = (dl && dl.text !== undefined) ? dl.text : (typeof dl === "string" ? dl : JSON.stringify(dl));
                    const type = (dl && dl.type) ? String(dl.type).toUpperCase() : (txt.startsWith("+") ? "INSERTION" : (txt.startsWith("-") ? "DELETION" : "NORMAL"));
                    let lineBg = "transparent";
                    let lineCol = "#cbd5e1";
                    if (type === "INSERTION" || type === "ADD" || txt.startsWith("+")) { lineBg = "rgba(16, 185, 129, 0.15)"; lineCol = "#6ee7b7"; }
                    else if (type === "DELETION" || type === "DELETE" || txt.startsWith("-")) { lineBg = "rgba(239, 68, 68, 0.15)"; lineCol = "#fca5a5"; }
                    return `<div style="background: ${lineBg}; color: ${lineCol}; padding: 1px 8px; font-family: monospace; font-size: 11px; white-space: pre-wrap;">${escapeHtmlText(txt)}</div>`;
                }).join("")
                : `<div style="padding: 10px; color: #71717a; font-family: monospace; font-size: 11px;">No unified diff lines available</div>`;
            return `
                <div class="agyis-diff-card" style="background: #141416; border: 1px solid #27272a; border-radius: 6px; overflow: hidden; margin-bottom: 10px;">
                    <div style="display: flex; justify-content: space-between; align-items: center; padding: 6px 10px; background: #1c1c1f; border-bottom: 1px solid #27272a;">
                        <span style="font-family: monospace; font-size: 11px; color: #38bdf8;">📝 ${escapeHtmlText(fPath)}</span>
                        <span class="agyis-hud-pill agyis-hud-pill-green">Unified Diff</span>
                    </div>
                    <div style="max-height: 400px; overflow-y: auto; background: #09090b;">${diffHtml}</div>
                </div>
            `;
        }
        if (cType === "INVOKE_SUBAGENT" || currentStep.subagent !== undefined) {
            const sub = currentStep.subagent || (currentStep.tool_calls?.[0]?.args || {});
            const typeName = sub.typeName || sub.agent_name || sub.name || "Specialist Subagent";
            const role = sub.role || sub.agent_role || "Subagent Worker";
            const prompt = sub.initialPrompt || sub.prompt || sub.objective || "";
            return `
                <div class="agyis-subagent-card" style="background: #18181b; border: 1px solid #7c3aed; border-radius: 6px; padding: 12px; margin-bottom: 10px;">
                    <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 8px;">
                        <div style="display: flex; align-items: center; gap: 8px;">
                            <span style="font-size: 16px;">🤖</span>
                            <span style="font-weight: 700; color: #c084fc; font-size: 12px;">${escapeHtmlText(typeName)}</span>
                            <span class="agyis-hud-pill agyis-hud-pill-purple">${escapeHtmlText(role)}</span>
                        </div>
                        <span class="agyis-hud-pill agyis-hud-pill-green">Delegate Invoked</span>
                    </div>
                    <div style="font-size: 10px; color: #a1a1aa; margin-bottom: 4px; text-transform: uppercase;">Initial Prompt:</div>
                    <div style="background: #141416; border: 1px solid #27272a; border-radius: 4px; padding: 8px; font-family: monospace; font-size: 11px; color: #cbd5e1; max-height: 240px; overflow-y: auto;">
                        ${escapeHtmlText(prompt)}
                    </div>
                </div>
            `;
        }
        if (cType === "CHECKPOINT") {
            const cpSummary = currentStep.sessionSummary || currentStep.compaction_summary || currentStep.content || "";
            const cacheRead = currentStep.cacheReadTokens || 0;
            const inTokens = currentStep.checkpointInputTokens || currentStep.input_tokens || 0;
            let reclaimedMetric = "Compacted Context Milestone";
            if (cacheRead > 0 && inTokens > 0) {
                const reclaimedPct = Math.round(((cacheRead - inTokens) / cacheRead) * 100);
                reclaimedMetric = `Compacted ${(cacheRead / 1000).toFixed(0)}k -> ${(inTokens / 1000).toFixed(1)}k tokens (${reclaimedPct}% reduction)`;
            }
            return `
                <div class="agyis-checkpoint-card" style="background: #142e1d; border: 1px solid #16a34a; border-radius: 6px; padding: 14px; margin-bottom: 10px;">
                    <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 10px;">
                        <span class="agyis-hud-pill agyis-hud-pill-green" style="font-size: 12px; font-weight: 700;">
                            🛡️ Compaction Checkpoint #${currentStep.checkpoint_index || currentStep.step_index || state.selectedIndex}
                        </span>
                        <button id="agyis-jump-prev-epoch" class="agyis-hud-btn" style="padding: 3px 8px; font-size: 11px; background: #166534; border: 1px solid #22c55e; cursor: pointer;">
                            Jump to Previous Epoch ◀
                        </button>
                    </div>
                    <div style="font-family: monospace; font-size: 12px; color: #86efac; margin-bottom: 10px; font-weight: 600;">📊 ${reclaimedMetric}</div>
                    <div style="font-size: 10px; color: #86efac; margin-bottom: 4px; text-transform: uppercase;">Compacted Session Summary:</div>
                    <div style="background: #0d1f14; border: 1px solid #166534; border-radius: 4px; padding: 10px; max-height: 280px; overflow-y: auto;">
                        ${renderMarkdownPreview(cpSummary)}
                    </div>
                </div>
            `;
        }
        if (cType === "USER_INPUT") {
            return `
                <div class="agyis-user-request-card" style="background: #1e293b; border: 1px solid #3b82f6; border-left: 4px solid #3b82f6; border-radius: 6px; padding: 12px; margin-bottom: 10px;">
                    <div style="display: flex; align-items: center; gap: 6px; font-weight: 700; font-size: 11px; color: #38bdf8; margin-bottom: 6px;">
                        <span>👤</span><span>&lt;USER_REQUEST&gt;</span>
                    </div>
                    <div style="font-size: 12px; color: #f1f5f9; line-height: 1.5; white-space: pre-wrap;">${escapeHtmlText(currentStep.content || "")}</div>
                </div>
            `;
        }
        if (cType === "PLANNER_RESPONSE" || cType === "MODEL_OUTPUT") {
            return `
                ${thinkingBlockHtml}
                ${currentStep.content ? `<h4 style="margin: 0 0 6px 0; font-size: 11px; color: #a1a1aa; text-transform: uppercase;">Response Preview</h4>${renderMarkdownPreview(currentStep.content)}` : ""}
            `;
        }
        if (cType.includes("SYSTEM") || cType.includes("EPHEMERAL")) {
            const sysContent = currentStep.content || currentStep.systemMessage || currentStep.system_message || currentStep.message || currentStep.task_details || currentStep.error_details || currentStep.render_info || "";
            const displaySys = typeof sysContent === "object" ? (sysContent.content || sysContent.message || sysContent.text || JSON.stringify(sysContent, null, 2)) : String(sysContent);
            return `
                <div class="agyis-system-card" style="background: #27272a; border: 1px solid #71717a; border-left: 4px solid #a855f7; border-radius: 6px; padding: 12px; margin-bottom: 10px;">
                    <div style="display: flex; align-items: center; gap: 6px; font-weight: 700; font-size: 11px; color: #c084fc; margin-bottom: 6px;">
                        <span>⚙️</span><span>SYSTEM MESSAGE</span>
                    </div>
                    <div style="font-size: 12px; color: #e4e4e7; line-height: 1.5;">${renderMarkdownPreview(displaySys || "")}</div>
                </div>
            `;
        }
        return `
            ${toolStripHtml}
            ${thinkingBlockHtml}
            ${currentStep.content ? `<h4 style="margin: 0 0 6px 0; font-size: 11px; color: #a1a1aa; text-transform: uppercase;">Step Preview</h4>${renderMarkdownPreview(currentStep.content)}` : ""}
        `;
    }

    function buildInspectorHtml(currentStep, state) {
        if (!currentStep) return "";
        const cType = currentStep.type || "STEP";
        const isModelStep = (cType === "PLANNER_RESPONSE" || cType === "MODEL_OUTPUT");
        const totalDurationMs = currentStep.total_duration_ms || 0;
        let timingBarHtml = "";
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

        const tCalls = currentStep.tool_calls || [];
        const toolStripHtml = tCalls.length > 0 ? `
            <div style="display: flex; gap: 6px; flex-wrap: wrap; margin-bottom: 10px; align-items: center;">
                <span style="font-size: 10px; font-weight: 700; color: #a1a1aa; text-transform: uppercase;">Tool Calls:</span>
                ${tCalls.map(tc => `<span class="agyis-hud-pill agyis-hud-pill-teal" style="font-family: monospace; font-size: 10px;">${tc.name || "tool"} <span style="opacity: 0.7;">(${tc.status || "DONE"})</span></span>`).join("")}
            </div>
        ` : "";

        const thinkingBlockHtml = currentStep.thinking ? `
            <details class="agyis-thinking-block" open>
                <summary style="cursor: pointer; font-weight: 600; color: #fbbf24; font-size: 11px; user-select: none;">
                    💭 Thought Process (${currentStep.thinking.length.toLocaleString()} chars &bull; ${currentStep.thinking_duration_ms || 0}ms)
                </summary>
                <div style="margin-top: 8px; font-size: 11px; color: #fef3c7; line-height: 1.5; font-family: ui-monospace, monospace; max-height: 320px; overflow-y: auto;">
                    ${renderMarkdownPreview(currentStep.thinking)}
                </div>
            </details>
        ` : "";

        if (state.activeTab === "step") {
            return `${timingBarHtml}${buildStepBodyHtml(currentStep, state, toolStripHtml, thinkingBlockHtml)}`;
        }
        if (state.activeTab === "invocation") {
            return `
                ${timingBarHtml}
                <h4 style="margin: 0 0 8px 0; font-size: 11px; color: #a1a1aa; text-transform: uppercase;">Tool Invocations (${tCalls.length})</h4>
                ${tCalls.length === 0 ? "<div style='color: #71717a;'>No tool calls executed in this step</div>" : tCalls.map((t, tidx) => `
                    <div style="background: #202023; border: 1px solid #3f3f46; border-radius: 6px; padding: 10px; margin-bottom: 8px;">
                        <div style="display: flex; justify-content: space-between; margin-bottom: 6px;">
                            <span style="font-weight: 700; color: #22d3ee; font-family: monospace;">#${tidx + 1} ${t.name || "tool"}</span>
                            <span class="agyis-hud-pill agyis-hud-pill-green">${t.status || "DONE"}</span>
                        </div>
                        <div style="font-size: 10px; color: #a1a1aa; margin-bottom: 4px;">Arguments:</div>
                        <pre class="agyis-codeblock" style="margin-bottom: 8px;"><code>${escapeHtmlText(JSON.stringify(t.args || {}, null, 2))}</code></pre>
                        ${t.output ? `<div style="font-size: 10px; color: #a1a1aa; margin-bottom: 4px;">Output:</div><pre class="agyis-codeblock" style="max-height: 200px;"><code>${escapeHtmlText(t.output)}</code></pre>` : ""}
                    </div>
                `).join("")}
            `;
        }
        if (state.activeTab === "execution") {
            const gm = currentStep.generator_metadata || {};
            const em = currentStep.executor_metadata || {};
            const modelUsage = gm.usage || (currentStep.metadata && currentStep.metadata.modelUsage) || {};
            const statusTransitions = em.statusTransitions || (currentStep.metadata && currentStep.metadata.statusTransitions) || [
                { timestamp: new Date().toISOString(), status: currentStep.status || "STATUS_COMPLETED", executionId: `exec-${currentStep.step_index ?? state.selectedIndex}` },
            ];
            let modelDisplay = "—";
            if (cType === "USER_INPUT") modelDisplay = "N/A (User Input)";
            else if (cType.includes("SYSTEM") || cType.includes("EPHEMERAL")) modelDisplay = "N/A (System Event)";
            else if (cType === "CHECKPOINT") modelDisplay = "N/A (Compaction Event)";
            else modelDisplay = currentStep.response_model || gm.responseModel || gm.model || state.sessionModel || (state.currentData && state.currentData.model) || "—";

            const inTokVal = currentStep.input_tokens || modelUsage.inputTokens || modelUsage.promptTokenCount || modelUsage.inputTokenCount || (currentStep.metadata && (currentStep.metadata.input_tokens || currentStep.metadata.promptTokenCount)) || 0;
            const outTokVal = currentStep.output_tokens || modelUsage.outputTokens || modelUsage.candidatesTokenCount || modelUsage.responseOutputTokens || (currentStep.metadata && (currentStep.metadata.toolCallOutputTokens || currentStep.metadata.output_tokens)) || 0;
            const thinkTokVal = currentStep.thinking_tokens || modelUsage.thinkingOutputTokens || 0;
            const cacheTokVal = currentStep.cacheReadTokens || currentStep.cache_read_tokens || modelUsage.cacheReadTokens || modelUsage.cachedContentTokenCount || (currentStep.metadata && (currentStep.metadata.cache_read_tokens || currentStep.metadata.cachedContentTokenCount)) || 0;

            return `
                ${timingBarHtml}
                <h4 style="margin: 0 0 8px 0; font-size: 11px; color: #a1a1aa; text-transform: uppercase;">Status Transitions</h4>
                <table class="agyis-markdown-table" style="margin-bottom: 12px;">
                    <tr><th>Timestamp</th><th>Status</th><th>Execution ID</th></tr>
                    ${statusTransitions.map(st => `
                        <tr>
                            <td style="font-family: monospace; font-size: 10px;">${st.timestamp || "-"}</td>
                            <td><span class="agyis-hud-pill agyis-hud-pill-green">${st.status || "-"}</span></td>
                            <td style="font-family: monospace; font-size: 10px;">${st.executionId || "-"}</td>
                        </tr>
                    `).join("")}
                </table>
                <h4 style="margin: 0 0 8px 0; font-size: 11px; color: #a1a1aa; text-transform: uppercase;">Model Usage Metrics</h4>
                <table class="agyis-markdown-table">
                    <tr><th>Metric</th><th>Value</th></tr>
                    <tr><td>Model</td><td>${modelDisplay}</td></tr>
                    <tr><td>Input Tokens</td><td>${inTokVal.toLocaleString()}</td></tr>
                    <tr><td>Output Tokens</td><td>${outTokVal.toLocaleString()}</td></tr>
                    <tr><td>Thinking Tokens</td><td>${thinkTokVal.toLocaleString()}</td></tr>
                    <tr><td>Cache Read Tokens</td><td>${cacheTokVal.toLocaleString()}</td></tr>
                    <tr><td>TTFT</td><td>${((currentStep.thinking_duration_ms || 0) / 1000).toFixed(2)}s</td></tr>
                    <tr><td>Streaming Duration</td><td>${((currentStep.streaming_duration_ms || 0) / 1000).toFixed(2)}s</td></tr>
                    <tr><td>Cumulative Context</td><td>${(currentStep.cumulative_tokens || 0).toLocaleString()} tokens</td></tr>
                </table>
            `;
        }
        return `
            <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 8px;">
                <h4 style="margin: 0; font-size: 11px; color: #a1a1aa; text-transform: uppercase;">Raw Step JSON</h4>
                <button id="agyis-copy-btn" class="agyis-hud-btn">📋 Copy</button>
            </div>
            <pre class="agyis-codeblock" style="max-height: 450px;"><code>${syntaxHighlightJson(currentStep)}</code></pre>
        `;
    }

    function bindHudEventListeners(hudEl, state, cur, steps, epochs, filteredIndices, totalPages, pageSize, currentStep) {
        const selectStepByIndex = (sIdx) => {
            const containingEp = epochs.find(ep => sIdx >= ep.start_index && sIdx <= ep.end_index);
            if (containingEp) state.activeEpochIndex = containingEp.epoch_index;
            state.selectedIndex = sIdx;
            renderHud();
        };

        hudEl.querySelector("#agyis-convo-select")?.addEventListener("change", (e) => {
            if (e.target.value && typeof window.__agyis_hud_load_convo === "function") window.__agyis_hud_load_convo(e.target.value);
        });
        hudEl.querySelector("#agyis-refresh-btn")?.addEventListener("click", () => {
            if (state.convoId && typeof window.__agyis_hud_load_convo === "function") {
                const btn = hudEl.querySelector("#agyis-refresh-btn");
                if (btn) btn.textContent = "⏳...";
                window.__agyis_hud_load_convo(state.convoId).finally(() => { if (btn) btn.textContent = "🔄 Refresh"; });
            }
        });
        hudEl.querySelector("#agyis-close-btn")?.addEventListener("click", () => { hudEl.style.display = "none"; });
        hudEl.querySelector("#agyis-maximize-btn")?.addEventListener("click", () => { state.isMaximized = !state.isMaximized; renderHud(); });
        hudEl.querySelector("#agyis-layout-side")?.addEventListener("click", () => { state.layoutOrientation = "horizontal"; renderHud(); });
        hudEl.querySelector("#agyis-layout-stack")?.addEventListener("click", () => { state.layoutOrientation = "vertical"; renderHud(); });

        hudEl.querySelector("#agyis-subagents-dropdown-toggle")?.addEventListener("click", (e) => {
            e.stopPropagation();
            state.subagentsDropdownOpen = !state.subagentsDropdownOpen;
            const menu = hudEl.querySelector("#agyis-subagents-menu");
            if (menu) menu.style.display = state.subagentsDropdownOpen ? "block" : "none";
        });
        hudEl.querySelectorAll(".agyis-subagent-item").forEach(el => {
            el.addEventListener("click", (e) => {
                e.stopPropagation();
                const sid = el.getAttribute("data-sub-id");
                const subTraj = cur.subagent_trajectories ? cur.subagent_trajectories[sid] : null;
                if (subTraj) {
                    state.currentData = subTraj;
                    state.selectedIndex = Math.max(0, (subTraj.steps || []).length - 1);
                    state.subagentsDropdownOpen = false;
                    renderHud();
                } else if (sid && typeof window.__agyis_hud_load_convo === "function") {
                    state.subagentsDropdownOpen = false;
                    window.__agyis_hud_load_convo(sid);
                }
            });
        });
        hudEl.querySelector("#agyis-parent-btn")?.addEventListener("click", () => {
            state.currentData = state.rootData;
            state.selectedIndex = Math.max(0, (state.rootData.steps || []).length - 1);
            renderHud();
        });

        let searchDebounceTimer = null;
        hudEl.querySelector("#agyis-search-input")?.addEventListener("input", (e) => {
            const val = e.target.value;
            clearTimeout(searchDebounceTimer);
            searchDebounceTimer = setTimeout(() => {
                state.filterQuery = val;
                state.currentMatchIdx = 0;
                state.tablePage = 0;
                renderHud();
                const inputEl = hudEl.querySelector("#agyis-search-input");
                if (inputEl) { inputEl.focus(); inputEl.setSelectionRange(val.length, val.length); }
            }, 150);
        });
        hudEl.querySelector("#agyis-search-input")?.addEventListener("keydown", (e) => {
            if (e.key === "Enter" && state.searchMatchIndices.length > 0) {
                e.preventDefault();
                state.currentMatchIdx = e.shiftKey
                    ? (state.currentMatchIdx - 1 + state.searchMatchIndices.length) % state.searchMatchIndices.length
                    : (state.currentMatchIdx + 1) % state.searchMatchIndices.length;
                selectStepByIndex(state.searchMatchIndices[state.currentMatchIdx]);
            } else if (e.key === "Escape") {
                state.filterQuery = "";
                state.tablePage = 0;
                renderHud();
            }
        });
        hudEl.querySelector("#agyis-search-clear")?.addEventListener("click", () => {
            state.filterQuery = "";
            state.tablePage = 0;
            renderHud();
        });

        hudEl.querySelector("#agyis-epoch-prev")?.addEventListener("click", () => {
            if (state.activeEpochIndex > 0) {
                state.activeEpochIndex -= 1;
                if (epochs[state.activeEpochIndex]) state.selectedIndex = epochs[state.activeEpochIndex].start_index;
                renderHud();
            }
        });
        hudEl.querySelector("#agyis-epoch-next")?.addEventListener("click", () => {
            if (state.activeEpochIndex < epochs.length - 1) {
                state.activeEpochIndex += 1;
                if (epochs[state.activeEpochIndex]) state.selectedIndex = epochs[state.activeEpochIndex].start_index;
                renderHud();
            }
        });
        hudEl.querySelector("#agyis-jump-prev-epoch")?.addEventListener("click", () => {
            if (state.activeEpochIndex > 0) {
                state.activeEpochIndex -= 1;
                if (epochs[state.activeEpochIndex]) state.selectedIndex = epochs[state.activeEpochIndex].start_index;
                renderHud();
            }
        });

        hudEl.querySelector("#agyis-page-prev")?.addEventListener("click", () => {
            if (state.tablePage > 0) { state.tablePage -= 1; renderHud(); }
        });
        hudEl.querySelector("#agyis-page-next")?.addEventListener("click", () => {
            if (state.tablePage < totalPages - 1) { state.tablePage += 1; renderHud(); }
        });
        hudEl.querySelector("#agyis-page-jump-selected")?.addEventListener("click", () => {
            const fIdx = filteredIndices.indexOf(state.selectedIndex);
            if (fIdx >= 0) {
                state.tablePage = Math.floor(fIdx / pageSize);
                renderHud();
                const rowEl = hudEl.querySelector(`.agyis-step-grid-item[data-index="${state.selectedIndex}"]`);
                if (rowEl) rowEl.scrollIntoView({ block: "nearest", behavior: "smooth" });
            }
        });

        const tooltipEl = hudEl.querySelector("#agyis-hover-tooltip");
        hudEl.querySelectorAll(".agyis-context-segment").forEach(el => {
            el.addEventListener("mouseenter", () => {
                const sName = el.getAttribute("data-seg-name");
                const sTok = parseInt(el.getAttribute("data-seg-tokens") || "0", 10);
                const sPct = el.getAttribute("data-seg-pct");
                const sTip = el.getAttribute("data-tooltip") || "";
                if (tooltipEl) {
                    tooltipEl.style.display = "block";
                    tooltipEl.innerHTML = `<b style="color: #fbbf24;">${escapeInspectorHtml(sName)}</b><br>Tokens: ${sTok.toLocaleString()} (${escapeInspectorHtml(sPct)}%)${sTip ? `<br><span style="color: #a1a1aa; font-style: italic;">${escapeInspectorHtml(sTip)}</span>` : ""}`;
                }
            });
            el.addEventListener("mouseleave", () => { if (tooltipEl) tooltipEl.style.display = "none"; });
            el.addEventListener("click", () => {
                const stepIdxAttr = el.getAttribute("data-step-index");
                if (stepIdxAttr !== null && stepIdxAttr !== undefined && stepIdxAttr !== "") {
                    const sIdx = parseInt(stepIdxAttr, 10);
                    if (!isNaN(sIdx)) {
                        selectStepByIndex(sIdx);
                        const rowEl = hudEl.querySelector(`.agyis-step-grid-item[data-index="${sIdx}"]`);
                        if (rowEl) rowEl.scrollIntoView({ block: "nearest", behavior: "smooth" });
                    }
                }
            });
        });

        hudEl.querySelectorAll(".agyis-main-tab-btn").forEach(el => {
            el.addEventListener("click", () => { state.mainDeckTab = el.getAttribute("data-main-tab"); renderHud(); });
        });
        hudEl.querySelectorAll(".agyis-timeline-card[data-index]").forEach(el => {
            el.addEventListener("click", () => {
                const sIdx = parseInt(el.getAttribute("data-index"), 10);
                if (!isNaN(sIdx)) selectStepByIndex(sIdx);
            });
        });
        hudEl.querySelector("#agyis-step-first")?.addEventListener("click", () => { if (steps.length > 0) selectStepByIndex(0); });
        hudEl.querySelector("#agyis-step-prev")?.addEventListener("click", () => { if (state.selectedIndex > 0) selectStepByIndex(state.selectedIndex - 1); });
        hudEl.querySelector("#agyis-step-next")?.addEventListener("click", () => { if (state.selectedIndex < steps.length - 1) selectStepByIndex(state.selectedIndex + 1); });
        hudEl.querySelector("#agyis-step-last")?.addEventListener("click", () => { if (steps.length > 0) selectStepByIndex(steps.length - 1); });
        hudEl.querySelectorAll(".agyis-inspector-tabs .agyis-hud-btn[data-tab]").forEach(el => {
            el.addEventListener("click", () => { state.activeTab = el.getAttribute("data-tab"); renderHud(); });
        });
        hudEl.querySelectorAll(".agyis-step-grid-item").forEach(el => {
            el.addEventListener("click", () => {
                const idx = parseInt(el.getAttribute("data-index"), 10);
                if (!isNaN(idx)) selectStepByIndex(idx);
            });
        });
        hudEl.querySelector("#agyis-copy-btn")?.addEventListener("click", () => {
            if (currentStep) {
                navigator.clipboard.writeText(JSON.stringify(currentStep, null, 2)).then(() => {
                    const btn = hudEl.querySelector("#agyis-copy-btn");
                    if (btn) btn.textContent = "✔ Copied!";
                    setTimeout(() => { if (btn) btn.textContent = "📋 Copy"; }, 1500);
                });
            }
        });
        hudEl.querySelectorAll(".agyis-copy-code-btn").forEach(btn => {
            btn.addEventListener("click", (e) => {
                e.stopPropagation();
                const codeEl = hudEl.querySelector("#" + btn.getAttribute("data-code-id"));
                if (codeEl) {
                    navigator.clipboard.writeText(codeEl.innerText).then(() => {
                        btn.textContent = "✔ Copied!";
                        setTimeout(() => { btn.textContent = "📋 Copy"; }, 1500);
                    });
                }
            });
        });
        if (window.Prism && typeof window.Prism.highlightAllUnder === "function") {
            const inspBody = hudEl.querySelector("#agyis-inspector-body");
            if (inspBody) { try { window.Prism.highlightAllUnder(inspBody); } catch (_) {} }
        }
    }
