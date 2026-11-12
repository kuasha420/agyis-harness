// SPDX-License-Identifier: Apache-2.0
// Copyright (c) 2026 Arafat Zahan (@kuasha420)
// Corporate Stewardship & Infrastructure: Purrfect Software Limited (PSL)
// Governed by: ICARO-42/b Ordinance (Company-Supported Personal IP Framework)

/**
 * hud_inspector.js — Step / Invocation / Execution / Trajectory Inspector (ruc / jmc Parity).
 * 
 * Implements 4-tab inspector with bidirectional cross-pane hover syncing (hoveredItemKey),
 * granular individual prompt sections and native/MCP tool definitions (Operator Directive),
 * terminal output viewer, unified diff viewer, and syntax-highlighted step inspect.
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

    function formatBytes(bytes) {
        if (!bytes || bytes <= 0) return "0 B";
        const k = 1024;
        const sizes = ["B", "KB", "MB", "GB"];
        const i = Math.floor(Math.log(bytes) / Math.log(k));
        return parseFloat((bytes / Math.pow(k, i)).toFixed(1)) + " " + sizes[i];
    }

    function syntaxHighlightJson(jsonObj) {
        let jsonStr = typeof jsonObj !== "string" ? JSON.stringify(jsonObj, null, 2) : jsonObj;
        if (!jsonStr) return "";
        jsonStr = jsonStr.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
        return jsonStr.replace(/("(\\u[a-zA-Z0-9]{4}|\\[^u]|[^\\"])*"(\s*:)?|\b(true|false|null)\b|-?\d+(?:\.\d*)?(?:[eE][+\-]?\d+)?)/g, function(match) {
            let clsColor = "#f59e0b";
            if (/^"/.test(match)) clsColor = /:$/.test(match) ? "#38bdf8" : "#a3e635";
            else if (/true|false/.test(match)) clsColor = "#c084fc";
            else if (/null/.test(match)) clsColor = "#71717a";
            return `<span style="color: ${clsColor};">${match}</span>`;
        });
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

        // Code blocks
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

        // Inline code
        escaped = escaped.replace(/`([^`]+)`/g, "<code style='background: #27272a; padding: 2px 4px; border-radius: 4px; font-family: monospace;'>$1</code>");

        // Alerts [!NOTE], [!WARNING], [!TIP], etc.
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

        // XML tags callout
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

        // Headers and formatting
        escaped = escaped.replace(/(?:^|\n)###\s+([^\n]+)/g, '<h3 style="font-size: 12px; font-weight: 700; color: #fbbf24; margin: 8px 0 4px 0;">$1</h3>');
        escaped = escaped.replace(/(?:^|\n)##\s+([^\n]+)/g, '<h2 style="font-size: 13px; font-weight: 700; color: #f59e0b; margin: 10px 0 6px 0;">$1</h2>');
        escaped = escaped.replace(/(?:^|\n)#\s+([^\n]+)/g, '<h1 style="font-size: 14px; font-weight: 700; color: #f59e0b; margin: 12px 0 8px 0;">$1</h1>');
        escaped = escaped.replace(/\*\*([^*]+)\*\*/g, '<strong style="color: #f4f4f5;">$1</strong>');
        escaped = escaped.replace(/\*([^*]+)\*/g, '<em style="color: #cbd5e1;">$1</em>');
        escaped = escaped.replace(/(?:^|\n)(?:[-*]|\d+\.)\s+([^\n]+)/g, '<div style="padding-left: 12px; margin: 2px 0; color: #e4e4e7;">&bull; $1</div>');
        escaped = escaped.replace(/\n/g, "<br>");

        return `<div class="agyis-markdown-body" style="word-break: break-word;">${escaped}</div>`;
    }

    /**
     * Renders Step Body content based on step type (puc).
     */
    function buildStepBodyHtml(currentStep, state) {
        const cType = currentStep.type || "STEP";

        // Terminal Command step
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
                            <span>${escapeHtml(cmd)}</span>
                        </div>
                        <span class="agyis-hud-pill ${exitBadgeClass}">exit ${exitCode}</span>
                    </div>
                    <div style="padding: 4px 10px; font-size: 10px; color: #71717a; border-bottom: 1px solid #202023; display: flex; justify-content: space-between;">
                        <span>Terminal Output (${lineCount} lines)</span>
                        <span>${currentStep.cwd ? `cwd: ${escapeHtml(currentStep.cwd)}` : ""}</span>
                    </div>
                    <pre class="agyis-codeblock" style="border: none; margin: 0; padding: 10px; max-height: 380px; overflow-y: auto;"><code class="language-bash">${escapeHtml(cleanOutput)}</code></pre>
                </div>
            `;
        }

        // View File step
        if (cType === "VIEW_FILE" || (currentStep.filePath && currentStep.fileContent !== undefined)) {
            const fPath = currentStep.filePath || (currentStep.tool_calls?.[0]?.args?.AbsolutePath || currentStep.tool_calls?.[0]?.args?.filePath || "");
            const fContent = currentStep.fileContent || (currentStep.tool_calls?.[0]?.output || currentStep.content || "");
            const lineCount = fContent ? fContent.split(/\r?\n/).length : 0;
            return `
                <div class="agyis-file-card" style="background: #141416; border: 1px solid #27272a; border-radius: 6px; overflow: hidden; margin-bottom: 10px;">
                    <div style="display: flex; justify-content: space-between; align-items: center; padding: 6px 10px; background: #1c1c1f; border-bottom: 1px solid #27272a;">
                        <span style="font-family: monospace; font-size: 11px; color: #38bdf8;">📄 ${escapeHtml(fPath)}</span>
                        <span style="font-size: 10px; color: #a1a1aa;">${lineCount} lines</span>
                    </div>
                    <pre class="agyis-codeblock" style="border: none; margin: 0; padding: 10px; max-height: 400px; overflow-y: auto;"><code>${escapeHtml(fContent)}</code></pre>
                </div>
            `;
        }

        // Unified Diff / Code Action step
        if (cType === "CODE_ACTION" || currentStep.diffLines !== undefined) {
            const fPath = currentStep.filePath || (currentStep.tool_calls?.[0]?.args?.TargetFile || "");
            const diffLines = currentStep.diffLines || [];
            const diffHtml = (Array.isArray(diffLines) && diffLines.length > 0)
                ? diffLines.map(dl => {
                    const txt = (dl && dl.text !== undefined) ? dl.text : (typeof dl === "string" ? dl : JSON.stringify(dl));
                    const isIns = txt.startsWith("+");
                    const isDel = txt.startsWith("-");
                    let lineBg = "transparent";
                    let lineCol = "#cbd5e1";
                    if (isIns) { lineBg = "rgba(16, 185, 129, 0.15)"; lineCol = "#6ee7b7"; }
                    else if (isDel) { lineBg = "rgba(239, 68, 68, 0.15)"; lineCol = "#fca5a5"; }
                    return `<div style="background: ${lineBg}; color: ${lineCol}; padding: 1px 8px; font-family: monospace; font-size: 11px; white-space: pre-wrap;">${escapeHtml(txt)}</div>`;
                }).join("")
                : `<div style="padding: 10px; color: #71717a; font-family: monospace; font-size: 11px;">No unified diff lines available</div>`;
            return `
                <div class="agyis-diff-card" style="background: #141416; border: 1px solid #27272a; border-radius: 6px; overflow: hidden; margin-bottom: 10px;">
                    <div style="display: flex; justify-content: space-between; align-items: center; padding: 6px 10px; background: #1c1c1f; border-bottom: 1px solid #27272a;">
                        <span style="font-family: monospace; font-size: 11px; color: #38bdf8;">📝 ${escapeHtml(fPath)}</span>
                        <span class="agyis-hud-pill agyis-hud-pill-green">Unified Diff</span>
                    </div>
                    <div style="max-height: 400px; overflow-y: auto; background: #09090b;">${diffHtml}</div>
                </div>
            `;
        }

        // Delegate Subagent step
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
                            <span style="font-weight: 700; color: #c084fc; font-size: 12px;">${escapeHtml(typeName)}</span>
                            <span class="agyis-hud-pill agyis-hud-pill-purple">${escapeHtml(role)}</span>
                        </div>
                        <span class="agyis-hud-pill agyis-hud-pill-green">Delegate Invoked</span>
                    </div>
                    <div style="font-size: 10px; color: #a1a1aa; margin-bottom: 4px; text-transform: uppercase;">Initial Prompt:</div>
                    <div style="background: #141416; border: 1px solid #27272a; border-radius: 4px; padding: 8px; font-family: monospace; font-size: 11px; color: #cbd5e1; max-height: 240px; overflow-y: auto;">
                        ${escapeHtml(prompt)}
                    </div>
                </div>
            `;
        }

        // Checkpoint compaction step
        if (cType === "CHECKPOINT") {
            const cpSummary = currentStep.sessionSummary || currentStep.compaction_summary || currentStep.content || "";
            const cacheRead = currentStep.cacheReadTokens || currentStep.cache_read_tokens || 0;
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
                        <button id="agyis-jump-prev-epoch" class="agyis-hud-btn agyis-jump-prev-epoch" style="padding: 3px 8px; font-size: 11px; background: #166534; border: 1px solid #22c55e; cursor: pointer;">
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

        // User input step
        if (cType === "USER_INPUT") {
            return `
                <div class="agyis-user-request-card" style="background: #1e293b; border: 1px solid #3b82f6; border-left: 4px solid #3b82f6; border-radius: 6px; padding: 12px; margin-bottom: 10px;">
                    <div style="display: flex; align-items: center; gap: 6px; font-weight: 700; font-size: 11px; color: #38bdf8; margin-bottom: 6px;">
                        <span>👤</span><span>&lt;USER_REQUEST&gt;</span>
                    </div>
                    <div style="font-size: 12px; color: #f1f5f9; line-height: 1.5; white-space: pre-wrap;">${escapeHtml(currentStep.content || "")}</div>
                </div>
            `;
        }

        // Model responses
        if (cType === "PLANNER_RESPONSE" || cType === "MODEL_OUTPUT") {
            return currentStep.content ? `
                <h4 style="margin: 0 0 6px 0; font-size: 11px; color: #a1a1aa; text-transform: uppercase;">Response Preview</h4>
                ${renderMarkdownPreview(currentStep.content)}
            ` : "";
        }

        return currentStep.content ? `
            <h4 style="margin: 0 0 6px 0; font-size: 11px; color: #a1a1aa; text-transform: uppercase;">Step Preview</h4>
            ${renderMarkdownPreview(currentStep.content)}
        ` : "";
    }

    /**
     * Builds Invocation View (juc) with granular system prompt sections and tool definitions (Operator Directive).
     */
    function buildInvocationHtml(currentStep, cur, state) {
        const sysSlices = (cur && cur.system_prompt_slices) || [];
        const toolSlices = (cur && cur.tool_def_slices) || [];
        const tCalls = (currentStep && currentStep.tool_calls) || [];

        const sysSectionsHtml = sysSlices.map((sl, idx) => `
            <div class="agyis-inspector-item-card ${state.hoveredItemKey === `prompt-section-${idx}` ? "context-cell-hovered" : ""}"
                 data-item-key="prompt-section-${idx}"
                 style="background: #202023; border: 1px solid #3f3f46; border-radius: 6px; padding: 8px 10px; margin-bottom: 6px; cursor: pointer;">
                <div style="display: flex; justify-content: space-between; align-items: center;">
                    <div style="display: flex; align-items: center; gap: 6px;">
                        <span style="width: 8px; height: 8px; border-radius: 50%; background: ${sl.color || "#6366f1"};"></span>
                        <span style="font-weight: 700; color: #c084fc; font-size: 11px;">${escapeHtml(sl.name)}</span>
                    </div>
                    <span style="font-family: monospace; font-size: 10px; color: #cbd5e1;">${(sl.tokens || 0).toLocaleString()} tokens</span>
                </div>
            </div>
        `).join("");

        const toolsHtml = toolSlices.map((tl, idx) => `
            <div class="agyis-inspector-item-card ${state.hoveredItemKey === `tool-def-${tl.name}` ? "context-cell-hovered" : ""}"
                 data-item-key="tool-def-${tl.name}"
                 style="background: #202023; border: 1px solid #3f3f46; border-radius: 6px; padding: 8px 10px; margin-bottom: 6px; cursor: pointer;">
                <div style="display: flex; justify-content: space-between; align-items: center;">
                    <div style="display: flex; align-items: center; gap: 6px;">
                        <span style="width: 8px; height: 8px; border-radius: 50%; background: ${tl.color || "#06b6d4"};"></span>
                        <span style="font-weight: 700; color: #22d3ee; font-family: monospace; font-size: 11px;">${escapeHtml(tl.name)}</span>
                        ${tl.server_name ? `<span class="agyis-hud-pill agyis-hud-pill-purple" style="font-size: 9px; padding: 1px 5px;">${escapeHtml(tl.server_name)}</span>` : ""}
                    </div>
                    <span style="font-family: monospace; font-size: 10px; color: #cbd5e1;">${(tl.tokens || 0).toLocaleString()} tokens</span>
                </div>
            </div>
        `).join("");

        const toolCallsHtml = `
            <div style="margin-top: 12px;">
                <h4 style="margin: 0 0 8px 0; font-size: 11px; color: #a1a1aa; text-transform: uppercase;">Step Tool Invocations (${tCalls.length})</h4>
                ${tCalls.length === 0 ? "<div style='color: #71717a;'>No tool calls executed in this step</div>" : tCalls.map((t, tidx) => `
                    <div style="background: #202023; border: 1px solid #3f3f46; border-radius: 6px; padding: 10px; margin-bottom: 8px;">
                        <div style="display: flex; justify-content: space-between; margin-bottom: 6px;">
                            <span style="font-weight: 700; color: #22d3ee; font-family: monospace;">#${tidx + 1} ${escapeHtml(t.name || "tool")}</span>
                            <span class="agyis-hud-pill agyis-hud-pill-green">${escapeHtml(t.status || "DONE")}</span>
                        </div>
                        <div style="font-size: 10px; color: #a1a1aa; margin-bottom: 4px;">Arguments:</div>
                        <pre class="agyis-codeblock" style="margin-bottom: 8px;"><code>${escapeHtml(JSON.stringify(t.args || {}, null, 2))}</code></pre>
                        ${t.output ? `<div style="font-size: 10px; color: #a1a1aa; margin-bottom: 4px;">Output:</div><pre class="agyis-codeblock" style="max-height: 200px;"><code>${escapeHtml(String(t.output))}</code></pre>` : ""}
                    </div>
                `).join("")}
            </div>
        `;

        return `
            <div style="margin-bottom: 12px;">
                <h4 style="margin: 0 0 8px 0; font-size: 11px; color: #a1a1aa; text-transform: uppercase;">
                    System Prompt Sections (${sysSlices.length})
                </h4>
                ${sysSectionsHtml || "<div style='color: #71717a;'>No prompt sections detected</div>"}
            </div>
            <div>
                <h4 style="margin: 0 0 8px 0; font-size: 11px; color: #a1a1aa; text-transform: uppercase;">
                    Active Tool Definitions (${toolSlices.length})
                </h4>
                ${toolsHtml || "<div style='color: #71717a;'>No tool definitions detected</div>"}
            </div>
            ${toolCallsHtml}
        `;
    }

    /**
     * Builds Execution View (iuc) with status transitions and model usage telemetry.
     */
    function buildExecutionHtml(currentStep, cur, state) {
        const gm = currentStep.generator_metadata || {};
        const em = currentStep.executor_metadata || {};
        const modelUsage = gm.usage || (currentStep.metadata && currentStep.metadata.modelUsage) || {};
        const statusTransitions = em.statusTransitions || (currentStep.metadata && currentStep.metadata.statusTransitions) || [
            { timestamp: new Date().toISOString(), status: currentStep.status || "STATUS_COMPLETED", executionId: `exec-${currentStep.step_index ?? state.selectedIndex}` },
        ];

        const inTokVal = currentStep.input_tokens || modelUsage.inputTokens || 0;
        const outTokVal = currentStep.output_tokens || modelUsage.outputTokens || 0;
        const thinkTokVal = currentStep.thinking_tokens || modelUsage.thinkingOutputTokens || 0;
        const cacheTokVal = currentStep.cache_read_tokens || modelUsage.cacheReadTokens || 0;
        const modelDisplay = currentStep.response_model || (cur && cur.model) || "—";

        return `
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
                <tr><td>Model</td><td>${escapeHtml(modelDisplay)}</td></tr>
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

    /**
     * Builds Trajectory View (quc) with session summary and child subagents.
     */
    function buildTrajectoryHtml(cur) {
        const subagents = (cur && cur.subagents) || [];
        const subagentInfos = (cur && cur.subagent_infos) || [];
        const breakdown = (cur && cur.token_breakdown) || {};

        return `
            <h4 style="margin: 0 0 8px 0; font-size: 11px; color: #a1a1aa; text-transform: uppercase;">Trajectory Telemetry</h4>
            <table class="agyis-markdown-table" style="margin-bottom: 12px;">
                <tr><td>Conversation ID</td><td style="font-family: monospace;">${escapeHtml(cur ? cur.conversation_id : "-")}</td></tr>
                <tr><td>Total Steps</td><td>${(cur && cur.steps ? cur.steps.length : 0).toLocaleString()}</td></tr>
                <tr><td>Total Context Tokens</td><td>${(cur && cur.total_tokens ? cur.total_tokens : 0).toLocaleString()}</td></tr>
                <tr><td>Active Subagents</td><td>${subagents.length}</td></tr>
            </table>

            ${cur && cur.parent_id ? `
                <h4 style="margin: 0 0 6px 0; font-size: 11px; color: #a1a1aa; text-transform: uppercase;">Parent Conversation</h4>
                <div style="margin-bottom: 12px;">
                    <button class="agyis-hud-btn agyis-parent-jump-btn" data-parent-id="${escapeHtml(cur.parent_id)}" style="display: flex; align-items: center; justify-content: space-between; width: 100%; padding: 6px 10px; background: rgba(59, 130, 246, 0.1); border: 1px solid rgba(59, 130, 246, 0.3); border-radius: 6px; cursor: pointer;">
                        <span style="color: #60a5fa; font-weight: 600; font-size: 11px;">↑ Conversation ${escapeHtml(String(cur.parent_id).slice(0, 12))}...</span>
                        <span style="font-size: 10px; color: #93c5fd;">Jump ↑</span>
                    </button>
                </div>
            ` : ""}

            <h4 style="margin: 0 0 8px 0; font-size: 11px; color: #a1a1aa; text-transform: uppercase;">Child Subagents (${subagents.length})</h4>
            ${subagents.length === 0 ? "<div style='color: #71717a; margin-bottom: 12px;'>No child subagents spawned in this conversation</div>" : `
                <table class="agyis-markdown-table" style="margin-bottom: 12px;">
                    <tr><th>Name</th><th>Role / Summary</th><th>Action</th></tr>
                    ${subagents.map((sid, idx) => {
                        const info = subagentInfos.find(si => si.id === sid) || { name: `Subagent #${idx + 1}`, summary: sid };
                        return `
                            <tr>
                                <td style="font-weight: 600; color: #c084fc;">${escapeHtml(info.name)}</td>
                                <td>${escapeHtml(info.summary)}</td>
                                <td>
                                    <button class="agyis-hud-btn agyis-subagent-jump-btn" data-sub-id="${escapeHtml(sid)}" style="padding: 2px 6px; font-size: 10px; background: rgba(168, 85, 247, 0.2); color: #c084fc; border: none; cursor: pointer;">Jump →</button>
                                </td>
                            </tr>
                        `;
                    }).join("")}
                </table>
            `}

            <h4 style="margin: 0 0 8px 0; font-size: 11px; color: #a1a1aa; text-transform: uppercase;">SSOT Token Breakdown</h4>
            <table class="agyis-markdown-table">
                <tr><th>Category</th><th>Tokens</th></tr>
                <tr><td>System Prompt & Instructions</td><td>${(breakdown.system_prompt || 0).toLocaleString()}</td></tr>
                <tr><td>Tool Definitions</td><td>${(breakdown.tool_defs || 0).toLocaleString()}</td></tr>
                <tr><td>User Messages</td><td>${(breakdown.user || 0).toLocaleString()}</td></tr>
                <tr><td>Model Responses</td><td>${(breakdown.model || 0).toLocaleString()}</td></tr>
                <tr><td>Thinking / Thoughts</td><td>${(breakdown.thought || 0).toLocaleString()}</td></tr>
                <tr><td>Tool Execution Outputs</td><td>${(breakdown.tool || 0).toLocaleString()}</td></tr>
                <tr><td>Compacted Checkpoints</td><td>${(breakdown.checkpoint || 0).toLocaleString()}</td></tr>
                <tr><td>Unattributed Overhead</td><td>${(breakdown.unattributed || 0).toLocaleString()}</td></tr>
            </table>
        `;
    }

    /**
     * Master Inspector HTML Generator.
     */
    function buildInspectorHtml(currentStep, state, cur) {
        if (!currentStep) return "<div style='color: #71717a; padding: 20px;'>Select a step in the timeline to inspect</div>";

        if (state.activeTab === "step") {
            const isModelStep = (currentStep.type === "PLANNER_RESPONSE" || currentStep.type === "MODEL_OUTPUT");
            const totalDurationMs = currentStep.total_duration_ms || 0;
            const timingBarHtml = (isModelStep && totalDurationMs > 0) ? `
                <div class="agyis-timing-bar-wrap">
                    <div style="display: flex; justify-content: space-between; font-size: 11px;">
                        <span><b style="color: #f59e0b;">TTFT:</b> ${((currentStep.thinking_duration_ms || 0) / 1000).toFixed(2)}s &nbsp;|&nbsp; <b style="color: #6366f1;">STREAMING:</b> ${((currentStep.streaming_duration_ms || 0) / 1000).toFixed(2)}s</span>
                        <span style="font-weight: 700; color: #cbd5e1;">Total: ${(totalDurationMs / 1000).toFixed(2)}s</span>
                    </div>
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

            return `
                ${timingBarHtml}
                ${thinkingBlockHtml}
                ${buildStepBodyHtml(currentStep, state)}
                <div style="display: flex; justify-content: space-between; align-items: center; margin: 12px 0 8px 0;">
                    <h4 style="margin: 0; font-size: 11px; color: #a1a1aa; text-transform: uppercase;">Raw Step JSON</h4>
                    <button id="agyis-copy-btn" class="agyis-hud-btn" title="Copy entire Step JSON">📋 Copy</button>
                </div>
                <pre class="agyis-codeblock" style="max-height: 350px;"><code>${syntaxHighlightJson(currentStep)}</code></pre>
            `;
        }

        if (state.activeTab === "invocation") {
            return buildInvocationHtml(currentStep, cur, state);
        }

        if (state.activeTab === "execution") {
            return buildExecutionHtml(currentStep, cur, state);
        }

        if (state.activeTab === "trajectory") {
            return buildTrajectoryHtml(cur);
        }

        return "";
    }

    /**
     * Binds mouse and copy events for inspector views.
     */
    function bindInspectorEvents(hudEl, state, currentStep, selectStepCallback) {
        if (!hudEl) return;

        // Copy button
        hudEl.querySelector("#agyis-copy-btn")?.addEventListener("click", () => {
            if (currentStep) {
                navigator.clipboard.writeText(JSON.stringify(currentStep, null, 2)).then(() => {
                    const btn = hudEl.querySelector("#agyis-copy-btn");
                    if (btn) btn.textContent = "✔ Copied!";
                    setTimeout(() => { if (btn) btn.textContent = "📋 Copy"; }, 1500);
                });
            }
        });

        // Subagent jump button in Trajectory tab
        hudEl.querySelectorAll(".agyis-subagent-jump-btn").forEach(btn => {
            btn.addEventListener("click", (e) => {
                e.stopPropagation();
                const sid = btn.getAttribute("data-sub-id");
                if (sid && typeof window.__agyis_hud_load_convo === "function") {
                    window.__agyis_hud_load_convo(sid);
                }
            });
        });

        // Parent jump button in Trajectory tab
        hudEl.querySelector(".agyis-parent-jump-btn")?.addEventListener("click", (e) => {
            e.stopPropagation();
            const pid = hudEl.querySelector(".agyis-parent-jump-btn")?.getAttribute("data-parent-id");
            if (pid && typeof window.__agyis_hud_load_convo === "function") {
                window.__agyis_hud_load_convo(pid);
            }
        });

        // Jump to Previous Epoch button in Checkpoint card
        hudEl.querySelector("#agyis-jump-prev-epoch")?.addEventListener("click", () => {
            if (state.activeEpochIndex > 0) {
                state.activeEpochIndex--;
                if (typeof renderHud === "function") renderHud();
            }
        });

        // Hover syncing on prompt section and tool cards
        hudEl.querySelectorAll(".agyis-inspector-item-card").forEach(el => {
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
    global.buildInspectorHtml = buildInspectorHtml;
    global.bindInspectorEvents = bindInspectorEvents;
    global.syntaxHighlightJson = syntaxHighlightJson;
    global.renderMarkdownPreview = renderMarkdownPreview;

})(typeof window !== "undefined" ? window : globalThis);
