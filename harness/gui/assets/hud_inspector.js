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

    const _u = () => global.__agyis_utils || {};
    const _theme = () => global.__agyis_theme || {};
    const escapeHtml = (val) => (_u().escapeHtml ? _u().escapeHtml(val) : String(val ?? ""));
    const cssEscape = (val) => (_u().cssEscape ? _u().cssEscape(val) : String(val ?? ""));
    const svgIcon = (name, size = 13) => (_theme().svgIcon ? _theme().svgIcon(name, size) : "");
    let codeBlockSeq = 0;

    function syntaxHighlightJson(jsonObj) {
        let jsonStr = typeof jsonObj !== "string" ? JSON.stringify(jsonObj, null, 2) : jsonObj;
        if (!jsonStr) return "";
        jsonStr = jsonStr.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
        return jsonStr.replace(/("(\\u[a-zA-Z0-9]{4}|\\[^u]|[^\\"])*"(\s*:)?|\b(true|false|null)\b|-?\d+(?:\.\d*)?(?:[eE][+\-]?\d+)?)/g, function(match) {
            let clsColor = "#F5B74F";
            if (/^"/.test(match)) clsColor = /:$/.test(match) ? "#26D0CE" : "#2AD089";
            else if (/true|false/.test(match)) clsColor = "#5C8AFF";
            else if (/null/.test(match)) clsColor = "#6E7F9B";
            return `<span style="color: ${clsColor};">${match}</span>`;
        });
    }

    function renderMarkdownPreview(rawText) {
        if (!rawText) return "<div style='color: #6E7F9B;'>No preview content</div>";

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
            const safeLang = escapeHtml(lang);
            const badge = safeLang ? `<span style="font-size: 10px; color: #9AA8BE; font-family: var(--agyis-font-mono, monospace); text-transform: uppercase;">${safeLang}</span>` : "<span></span>";
            const codeId = `agyis-code-${++codeBlockSeq}`;
            return `
                <div class="agyis-codeblock-wrap">
                    <div style="display: flex; justify-content: space-between; align-items: center; padding: 4px 10px; background: #10192B; border-bottom: 1px solid #1E2C47; border-top-left-radius: 6px; border-top-right-radius: 6px;">
                        ${badge}
                        <button class="agyis-hud-btn agyis-copy-code-btn" data-code-id="${codeId}" style="padding: 2px 6px; font-size: 10px;">${svgIcon("copy", 12)} Copy</button>
                    </div>
                    <pre id="${codeId}" class="agyis-codeblock" style="border: none; border-radius: 0 0 6px 6px; margin: 0; padding: 10px;"><code class="language-${safeLang || "none"}">${code.trim()}</code></pre>
                </div>
            `;
        });

        // Inline code
        escaped = escaped.replace(/`([^`]+)`/g, "<code style='background: #162238; padding: 2px 4px; border-radius: 4px; font-family: var(--agyis-font-mono, monospace);'>$1</code>");

        // Alerts [!NOTE], [!WARNING], [!TIP], etc.
        escaped = escaped.replace(/(?:^|\n)&gt;\s*\[!(NOTE|WARNING|TIP|IMPORTANT|CAUTION)\]([\s\S]*?)(?=(?:\n\n|\n&gt;\s*\[!|$))/gi, (m, alertType, body) => {
            const typeUpper = alertType.toUpperCase();
            let alertColor = "#5C8AFF";
            let alertIconName = "info";
            if (typeUpper === "WARNING") { alertColor = "#F5B74F"; alertIconName = "warn"; }
            else if (typeUpper === "TIP") { alertColor = "#2AD089"; alertIconName = "tip"; }
            else if (typeUpper === "IMPORTANT") { alertColor = "#26D0CE"; alertIconName = "alert"; }
            else if (typeUpper === "CAUTION") { alertColor = "#FF6B6B"; alertIconName = "caution"; }
            const alertContent = body.replace(/^\s*&gt;\s?/gm, "").trim().replace(/\n/g, "<br>");
            return `
                <div class="agyis-github-alert" style="border: 1px solid ${alertColor}; border-left: 4px solid ${alertColor};">
                    <div style="display: flex; align-items: center; gap: 6px; font-weight: 700; font-size: 11px; color: ${alertColor}; margin-bottom: 4px;">
                        ${svgIcon(alertIconName, 13)}<span>${typeUpper}</span>
                    </div>
                    <div style="font-size: 11px; color: #F4F6FA; line-height: 1.5;">${alertContent}</div>
                </div>
            `;
        });

        // XML tags callout
        escaped = escaped.replace(/&lt;([A-Z0-9_\-]+)&gt;([\s\S]*?)&lt;\/\1&gt;/g, (m, tag, body) => {
            let tagColor = "#F5B74F";
            let tagIconName = "pin";
            if (tag === "USER_REQUEST") { tagColor = "#5C8AFF"; tagIconName = "user"; }
            else if (tag === "CONTEXT_SUMMARY" || tag === "SUMMARY") { tagColor = "#2AD089"; tagIconName = "brain"; }
            else if (tag === "SYSTEM_MESSAGE") { tagColor = "#26D0CE"; tagIconName = "settings"; }
            const content = body.trim().replace(/\n/g, "<br>");
            return `
                <div class="agyis-xml-callout" style="border: 1px solid ${tagColor}; border-left: 4px solid ${tagColor};">
                    <div style="display: flex; align-items: center; gap: 6px; font-weight: 700; font-size: 11px; color: ${tagColor}; margin-bottom: 4px; text-transform: uppercase;">
                        ${svgIcon(tagIconName, 13)}<span>&lt;${tag}&gt;</span>
                    </div>
                    <div style="font-size: 11px; color: #F4F6FA; line-height: 1.5;">${content}</div>
                </div>
            `;
        });

        // Headers and formatting
        escaped = escaped.replace(/(?:^|\n)###\s+([^\n]+)/g, '<h3 style="font-size: 12px; font-weight: 700; color: #5C8AFF; margin: 8px 0 4px 0;">$1</h3>');
        escaped = escaped.replace(/(?:^|\n)##\s+([^\n]+)/g, '<h2 style="font-size: 13px; font-weight: 700; color: #5C8AFF; margin: 10px 0 6px 0;">$1</h2>');
        escaped = escaped.replace(/(?:^|\n)#\s+([^\n]+)/g, '<h1 style="font-size: 14px; font-weight: 700; color: #F4F6FA; margin: 12px 0 8px 0;">$1</h1>');
        escaped = escaped.replace(/\*\*([^*]+)\*\*/g, '<strong style="color: #F4F6FA;">$1</strong>');
        escaped = escaped.replace(/\*([^*]+)\*/g, '<em style="color: #9AA8BE;">$1</em>');
        escaped = escaped.replace(/(?:^|\n)(?:[-*]|\d+\.)\s+([^\n]+)/g, '<div style="padding-left: 12px; margin: 2px 0; color: #F4F6FA;">&bull; $1</div>');
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
            const exitNum = Number(exitCode);
            const exitBadgeClass = (!Number.isNaN(exitNum) && exitNum === 0) ? "agyis-hud-pill-green" : "agyis-hud-pill-red";
            const outputRaw = currentStep.output || (currentStep.tool_calls?.[0]?.output || "");
            const cleanOutput = String(outputRaw).replace(/\u001b\[[0-9;]*[a-zA-Z]/g, "");
            const lineCount = cleanOutput ? cleanOutput.split(/\r?\n/).length : 0;
            return `
                <div class="agyis-terminal-card" style="background: #10192B; border: 1px solid #1E2C47; border-radius: 6px; overflow: hidden; margin-bottom: 10px;">
                    <div style="display: flex; justify-content: space-between; align-items: center; padding: 6px 10px; background: #162238; border-bottom: 1px solid #1E2C47;">
                        <div style="font-family: var(--agyis-font-mono, monospace); font-size: 11px; color: #F4F6FA; display: flex; align-items: center; gap: 6px;">
                            <span style="color: #26D0CE;">$</span>
                            <span>${escapeHtml(cmd)}</span>
                        </div>
                        <span class="agyis-hud-pill ${exitBadgeClass}">exit ${escapeHtml(exitCode)}</span>
                    </div>
                    <div style="padding: 4px 10px; font-size: 10px; color: #6E7F9B; border-bottom: 1px solid #1E2C47; display: flex; justify-content: space-between;">
                        <span>Terminal Output (${lineCount} lines)</span>
                        <span>${currentStep.cwd ? `cwd: ${escapeHtml(currentStep.cwd)}` : ""}</span>
                    </div>
                    <pre class="agyis-codeblock" style="border: none; margin: 0; padding: 10px; max-height: 380px; overflow-y: auto;"><code class="language-bash">${escapeHtml(cleanOutput)}</code></pre>
                </div>
            `;
        }

        // View / Read File step (supports v2.34+ read_file Path arg)
        if (cType === "VIEW_FILE" || cType === "READ_FILE" || cType === "READ_RESOURCE" || (currentStep.filePath && currentStep.fileContent !== undefined)) {
            const args = currentStep.tool_calls?.[0]?.args || {};
            const fPath = currentStep.filePath || args.Path || args.AbsolutePath || args.path || args.filePath || args.Uri || "";
            const fContent = currentStep.fileContent || (currentStep.tool_calls?.[0]?.output || currentStep.content || "");
            const lineCount = fContent ? String(fContent).split(/\r?\n/).length : 0;
            return `
                <div class="agyis-file-card" style="background: #10192B; border: 1px solid #1E2C47; border-radius: 6px; overflow: hidden; margin-bottom: 10px;">
                    <div style="display: flex; justify-content: space-between; align-items: center; padding: 6px 10px; background: #162238; border-bottom: 1px solid #1E2C47;">
                        <span style="font-family: var(--agyis-font-mono, monospace); font-size: 11px; color: #26D0CE; display: inline-flex; align-items: center; gap: 6px;">${svgIcon("file", 13)} ${escapeHtml(fPath)}</span>
                        <span style="font-size: 10px; color: #9AA8BE;">${lineCount} lines</span>
                    </div>
                    <pre class="agyis-codeblock" style="border: none; margin: 0; padding: 10px; max-height: 400px; overflow-y: auto;"><code>${escapeHtml(fContent)}</code></pre>
                </div>
            `;
        }

        // Unified Diff / Code Action / Edit / Write step (supports v2.34+ edit_file/write_file Path arg)
        if (cType === "CODE_ACTION" || cType === "EDIT_FILE" || cType === "WRITE_FILE" || cType === "REPLACE_FILE_CONTENT" || currentStep.diffLines !== undefined) {
            const args = currentStep.tool_calls?.[0]?.args || {};
            const fPath = currentStep.filePath || args.Path || args.TargetFile || args.path || args.filePath || "";
            const diffLines = currentStep.diffLines || [];
            const editBody = args.Replacement || args.ReplacementContent || args.Content || args.CodeContent || "";
            const diffHtml = (Array.isArray(diffLines) && diffLines.length > 0)
                ? diffLines.map(dl => {
                    const txt = (dl && dl.text !== undefined) ? dl.text : (typeof dl === "string" ? dl : JSON.stringify(dl));
                    const isIns = txt.startsWith("+");
                    const isDel = txt.startsWith("-");
                    let lineBg = "transparent";
                    let lineCol = "#F4F6FA";
                    if (isIns) { lineBg = "rgba(42, 208, 137, 0.14)"; lineCol = "#2AD089"; }
                    else if (isDel) { lineBg = "rgba(255, 107, 107, 0.14)"; lineCol = "#FF6B6B"; }
                    return `<div style="background: ${lineBg}; color: ${lineCol}; padding: 1px 8px; font-family: var(--agyis-font-mono, monospace); font-size: 11px; white-space: pre-wrap;">${escapeHtml(txt)}</div>`;
                }).join("")
                : (editBody
                    ? `<pre class="agyis-codeblock" style="border: none; margin: 0; padding: 10px;"><code>${escapeHtml(editBody)}</code></pre>`
                    : `<div style="padding: 10px; color: #6E7F9B; font-family: var(--agyis-font-mono, monospace); font-size: 11px;">No unified diff lines available</div>`);
            return `
                <div class="agyis-diff-card" style="background: #10192B; border: 1px solid #1E2C47; border-radius: 6px; overflow: hidden; margin-bottom: 10px;">
                    <div style="display: flex; justify-content: space-between; align-items: center; padding: 6px 10px; background: #162238; border-bottom: 1px solid #1E2C47;">
                        <span style="font-family: var(--agyis-font-mono, monospace); font-size: 11px; color: #26D0CE; display: inline-flex; align-items: center; gap: 6px;">${svgIcon("diff", 13)} ${escapeHtml(fPath)}</span>
                        <span class="agyis-hud-pill agyis-hud-pill-green">Unified Diff</span>
                    </div>
                    <div style="max-height: 400px; overflow-y: auto; background: #080E1A;">${diffHtml}</div>
                </div>
            `;
        }

        // Delegate Subagent / Swarm step (supports v2.34+ swarm/define_subagent args)
        if (cType === "INVOKE_SUBAGENT" || cType === "SWARM" || cType === "DEFINE_SUBAGENT" || currentStep.subagent !== undefined) {
            const sub = currentStep.subagent || (currentStep.tool_calls?.[0]?.args || {});
            const typeName = sub.typeName || sub.TypeName || sub.agent_name || sub.name || sub.Name || "Specialist Subagent";
            const role = sub.role || sub.Role || sub.agent_role || sub.action || "Subagent Worker";
            const prompt = sub.initialPrompt || sub.Prompt || sub.prompt || sub.brief || sub.objective || sub.Description || "";
            return `
                <div class="agyis-subagent-card" style="background: #10192B; border: 1px solid #5C8AFF; border-radius: 6px; padding: 12px; margin-bottom: 10px;">
                    <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 8px;">
                        <div style="display: flex; align-items: center; gap: 8px;">
                            <span style="color: #5C8AFF; display: inline-flex;">${svgIcon("bot", 15)}</span>
                            <span style="font-weight: 700; color: #5C8AFF; font-size: 12px;">${escapeHtml(typeName)}</span>
                            <span class="agyis-hud-pill agyis-hud-pill-purple">${escapeHtml(role)}</span>
                        </div>
                        <span class="agyis-hud-pill agyis-hud-pill-green">Delegate Invoked</span>
                    </div>
                    <div style="font-size: 10px; color: #9AA8BE; margin-bottom: 4px; text-transform: uppercase;">Initial Prompt:</div>
                    <div style="background: #0B1322; border: 1px solid #1E2C47; border-radius: 4px; padding: 8px; font-family: var(--agyis-font-mono, monospace); font-size: 11px; color: #F4F6FA; max-height: 240px; overflow-y: auto;">
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
            const canJumpPrev = (state && typeof state.activeCheckpointIndex === "number" ? state.activeCheckpointIndex : 0) > 0;
            const jumpPrevStyle = `padding: 3px 8px; font-size: 11px; background: rgba(42, 208, 137, 0.16); border: 1px solid #2AD089; color: #2AD089; ${canJumpPrev ? "cursor: pointer;" : "opacity: 0.4; cursor: default;"}`;
            return `
                <div class="agyis-checkpoint-card" style="background: rgba(42, 208, 137, 0.08); border: 1px solid #2AD089; border-radius: 6px; padding: 14px; margin-bottom: 10px;">
                    <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 10px;">
                        <span class="agyis-hud-pill agyis-hud-pill-green" style="font-size: 12px; font-weight: 700;">
                            ${svgIcon("shield", 13)} Compaction Checkpoint #${escapeHtml(currentStep.checkpoint_index ?? currentStep.step_index ?? state.selectedIndex)}
                        </span>
                        <button id="agyis-jump-prev-checkpoint" class="agyis-hud-btn agyis-jump-prev-checkpoint" style="${jumpPrevStyle}" ${canJumpPrev ? "" : "disabled"}>
                            Jump to Previous Checkpoint ◀
                        </button>
                    </div>
                    <div style="font-family: var(--agyis-font-mono, monospace); font-size: 12px; color: #2AD089; margin-bottom: 10px; font-weight: 600; display: flex; align-items: center; gap: 6px;">${svgIcon("chart", 13)} ${escapeHtml(reclaimedMetric)}</div>
                    <div style="font-size: 10px; color: #2AD089; margin-bottom: 4px; text-transform: uppercase;">Compacted Session Summary:</div>
                    <div style="background: #0B1322; border: 1px solid rgba(42, 208, 137, 0.35); border-radius: 4px; padding: 10px; max-height: 280px; overflow-y: auto;">
                        ${renderMarkdownPreview(cpSummary)}
                    </div>
                </div>
            `;
        }

        // User input step
        if (cType === "USER_INPUT") {
            return `
                <div class="agyis-user-request-card" style="background: #10192B; border: 1px solid #1B4DFF; border-left: 4px solid #5C8AFF; border-radius: 6px; padding: 12px; margin-bottom: 10px;">
                    <div style="display: flex; align-items: center; gap: 6px; font-weight: 700; font-size: 11px; color: #5C8AFF; margin-bottom: 6px;">
                        ${svgIcon("user", 13)}<span>&lt;USER_REQUEST&gt;</span>
                    </div>
                    <div style="font-size: 12px; color: #F4F6FA; line-height: 1.5; white-space: pre-wrap;">${escapeHtml(currentStep.content || "")}</div>
                </div>
            `;
        }

        // Model responses
        if (cType === "PLANNER_RESPONSE" || cType === "MODEL_OUTPUT") {
            return currentStep.content ? `
                <h4 style="margin: 0 0 6px 0; font-size: 11px; color: #9AA8BE; text-transform: uppercase;">Response Preview</h4>
                ${renderMarkdownPreview(currentStep.content)}
            ` : "";
        }

        return currentStep.content ? `
            <h4 style="margin: 0 0 6px 0; font-size: 11px; color: #9AA8BE; text-transform: uppercase;">Step Preview</h4>
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
                 style="background: #10192B; border: 1px solid #1E2C47; border-radius: 6px; padding: 8px 10px; margin-bottom: 6px; cursor: pointer;">
                <div style="display: flex; justify-content: space-between; align-items: center;">
                    <div style="display: flex; align-items: center; gap: 6px;">
                        <span style="width: 8px; height: 8px; border-radius: 50%; background: ${escapeHtml(sl.color || "#5C8AFF")};"></span>
                        <span style="font-weight: 700; color: #8FB0FF; font-size: 11px;">${escapeHtml(sl.name)}</span>
                    </div>
                    <span style="font-family: var(--agyis-font-mono, monospace); font-size: 10px; color: #9AA8BE;">${(sl.tokens || 0).toLocaleString()} tokens</span>
                </div>
            </div>
        `).join("");

        const toolsHtml = toolSlices.map((tl, idx) => `
            <div class="agyis-inspector-item-card ${state.hoveredItemKey === `tool-def-${tl.name}` ? "context-cell-hovered" : ""}"
                 data-item-key="tool-def-${escapeHtml(tl.name)}"
                 style="background: #10192B; border: 1px solid #1E2C47; border-radius: 6px; padding: 8px 10px; margin-bottom: 6px; cursor: pointer;">
                <div style="display: flex; justify-content: space-between; align-items: center;">
                    <div style="display: flex; align-items: center; gap: 6px;">
                        <span style="width: 8px; height: 8px; border-radius: 50%; background: ${escapeHtml(tl.color || "#26D0CE")};"></span>
                        <span style="font-weight: 700; color: #26D0CE; font-family: var(--agyis-font-mono, monospace); font-size: 11px;">${escapeHtml(tl.name)}</span>
                        ${tl.server_name ? `<span class="agyis-hud-pill agyis-hud-pill-purple" style="font-size: 9px; padding: 1px 5px;">${escapeHtml(tl.server_name)}</span>` : ""}
                    </div>
                    <span style="font-family: var(--agyis-font-mono, monospace); font-size: 10px; color: #9AA8BE;">${(tl.tokens || 0).toLocaleString()} tokens</span>
                </div>
            </div>
        `).join("");

        const toolCallsHtml = `
            <div style="margin-top: 12px;">
                <h4 style="margin: 0 0 8px 0; font-size: 11px; color: #9AA8BE; text-transform: uppercase;">Step Tool Invocations (${tCalls.length})</h4>
                ${tCalls.length === 0 ? "<div style='color: #6E7F9B;'>No tool calls executed in this step</div>" : tCalls.map((t, tidx) => `
                    <div style="background: #10192B; border: 1px solid #1E2C47; border-radius: 6px; padding: 10px; margin-bottom: 8px;">
                        <div style="display: flex; justify-content: space-between; margin-bottom: 6px;">
                            <span style="font-weight: 700; color: #26D0CE; font-family: var(--agyis-font-mono, monospace);">#${tidx + 1} ${escapeHtml(t.name || "tool")}</span>
                            <span class="agyis-hud-pill agyis-hud-pill-green">${escapeHtml(t.status || "DONE")}</span>
                        </div>
                        <div style="font-size: 10px; color: #9AA8BE; margin-bottom: 4px;">Arguments:</div>
                        <pre class="agyis-codeblock" style="margin-bottom: 8px;"><code>${escapeHtml(JSON.stringify(t.args || {}, null, 2))}</code></pre>
                        ${t.output ? `<div style="font-size: 10px; color: #9AA8BE; margin-bottom: 4px;">Output:</div><pre class="agyis-codeblock" style="max-height: 200px;"><code>${escapeHtml(String(t.output))}</code></pre>` : ""}
                    </div>
                `).join("")}
            </div>
        `;

        return `
            <div style="margin-bottom: 12px;">
                <h4 style="margin: 0 0 8px 0; font-size: 11px; color: #9AA8BE; text-transform: uppercase;">
                    System Prompt Sections (${sysSlices.length})
                </h4>
                ${sysSectionsHtml || "<div style='color: #6E7F9B;'>No prompt sections detected</div>"}
            </div>
            <div>
                <h4 style="margin: 0 0 8px 0; font-size: 11px; color: #9AA8BE; text-transform: uppercase;">
                    Active Tool Definitions (${toolSlices.length})
                </h4>
                ${toolsHtml || "<div style='color: #6E7F9B;'>No tool definitions detected</div>"}
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
        const statusTransitions = em.statusTransitions || (currentStep.metadata && currentStep.metadata.statusTransitions) || currentStep.statusTransitions || [];

        const inTokVal = currentStep.input_tokens || modelUsage.inputTokens || 0;
        const outTokVal = currentStep.output_tokens || modelUsage.outputTokens || 0;
        const thinkTokVal = currentStep.thinking_tokens || modelUsage.thinkingOutputTokens || 0;
        const cacheTokVal = currentStep.cache_read_tokens || modelUsage.cacheReadTokens || 0;
        const modelDisplay = currentStep.response_model || (cur && cur.model) || "—";

        const transitionsRowsHtml = (Array.isArray(statusTransitions) && statusTransitions.length > 0)
            ? statusTransitions.map(st => `
                <tr>
                    <td style="font-family: var(--agyis-font-mono, monospace); font-size: 10px;">${escapeHtml(st.timestamp || "-")}</td>
                    <td><span class="agyis-hud-pill agyis-hud-pill-green">${escapeHtml(st.status || "-")}</span></td>
                    <td style="font-family: var(--agyis-font-mono, monospace); font-size: 10px;">${escapeHtml(st.executionId || "-")}</td>
                </tr>
            `).join("")
            : `<tr><td colspan="3" style="font-family: var(--agyis-font-mono, monospace); font-size: 10px; color: #9AA8BE;">No recorded transitions (status: ${escapeHtml(currentStep.status || "unknown")}${currentStep.created_at ? `, created_at: ${escapeHtml(currentStep.created_at)}` : ""})</td></tr>`;

        return `
            <h4 style="margin: 0 0 8px 0; font-size: 11px; color: #9AA8BE; text-transform: uppercase;">Status Transitions</h4>
            <table class="agyis-markdown-table" style="margin-bottom: 12px;">
                <tr><th>Timestamp</th><th>Status</th><th>Execution ID</th></tr>
                ${transitionsRowsHtml}
            </table>
            <h4 style="margin: 0 0 8px 0; font-size: 11px; color: #9AA8BE; text-transform: uppercase;">Model Usage Metrics</h4>
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
            <h4 style="margin: 0 0 8px 0; font-size: 11px; color: #9AA8BE; text-transform: uppercase;">Trajectory Telemetry</h4>
            <table class="agyis-markdown-table" style="margin-bottom: 12px;">
                <tr><td>Conversation ID</td><td style="font-family: var(--agyis-font-mono, monospace);">${escapeHtml(cur ? cur.conversation_id : "-")}</td></tr>
                <tr><td>Total Steps</td><td>${(cur && cur.steps ? cur.steps.length : 0).toLocaleString()}</td></tr>
                <tr><td>Total Context Tokens</td><td>${(cur && cur.total_tokens ? cur.total_tokens : 0).toLocaleString()}</td></tr>
                <tr><td>Active Subagents</td><td>${subagents.length}</td></tr>
            </table>

            ${cur && cur.parent_id ? `
                <h4 style="margin: 0 0 6px 0; font-size: 11px; color: #9AA8BE; text-transform: uppercase;">Parent Conversation</h4>
                <div style="margin-bottom: 12px;">
                    <button class="agyis-hud-btn agyis-parent-jump-btn" data-parent-id="${escapeHtml(cur.parent_id)}" style="display: flex; align-items: center; justify-content: space-between; width: 100%; padding: 6px 10px; background: rgba(27, 77, 255, 0.14); border: 1px solid rgba(92, 138, 255, 0.35); border-radius: 6px; cursor: pointer;">
                        <span style="color: #5C8AFF; font-weight: 600; font-size: 11px;">↑ Conversation ${escapeHtml(String(cur.parent_id).slice(0, 12))}...</span>
                        <span style="font-size: 10px; color: #8FB0FF;">Jump ↑</span>
                    </button>
                </div>
            ` : ""}

            <h4 style="margin: 0 0 8px 0; font-size: 11px; color: #9AA8BE; text-transform: uppercase;">Child Subagents (${subagents.length})</h4>
            ${subagents.length === 0 ? "<div style='color: #6E7F9B; margin-bottom: 12px;'>No child subagents spawned in this conversation</div>" : `
                <table class="agyis-markdown-table" style="margin-bottom: 12px;">
                    <tr><th>Name</th><th>Role / Summary</th><th>Action</th></tr>
                    ${subagents.map((sid, idx) => {
                        const info = subagentInfos.find(si => si.id === sid) || { name: `Subagent #${idx + 1}`, summary: sid };
                        return `
                            <tr>
                                <td style="font-weight: 600; color: #5C8AFF;">${escapeHtml(info.name)}</td>
                                <td>${escapeHtml(info.summary)}</td>
                                <td>
                                    <button class="agyis-hud-btn agyis-subagent-jump-btn" data-sub-id="${escapeHtml(sid)}" style="padding: 2px 6px; font-size: 10px; background: rgba(92, 138, 255, 0.18); color: #5C8AFF; border: none; cursor: pointer;">Jump →</button>
                                </td>
                            </tr>
                        `;
                    }).join("")}
                </table>
            `}

            <h4 style="margin: 0 0 8px 0; font-size: 11px; color: #9AA8BE; text-transform: uppercase;">SSOT Token Breakdown</h4>
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
        if (!currentStep) return "<div style='color: #6E7F9B; padding: 20px;'>Select a step in the timeline to inspect</div>";

        if (state.activeTab === "step") {
            const isModelStep = (currentStep.type === "PLANNER_RESPONSE" || currentStep.type === "MODEL_OUTPUT");
            const totalDurationMs = currentStep.total_duration_ms || 0;
            const timingBarHtml = (isModelStep && totalDurationMs > 0) ? `
                <div class="agyis-timing-bar-wrap">
                    <div style="display: flex; justify-content: space-between; font-size: 11px;">
                        <span><b style="color: #F5B74F;">TTFT:</b> ${((currentStep.thinking_duration_ms || 0) / 1000).toFixed(2)}s &nbsp;|&nbsp; <b style="color: #5C8AFF;">STREAMING:</b> ${((currentStep.streaming_duration_ms || 0) / 1000).toFixed(2)}s</span>
                        <span style="font-weight: 700; color: #F4F6FA;">Total: ${(totalDurationMs / 1000).toFixed(2)}s</span>
                    </div>
                </div>
            ` : "";

            const thinkingBlockHtml = currentStep.thinking ? `
                <details class="agyis-thinking-block" open>
                    <summary style="cursor: pointer; font-weight: 600; color: #5C8AFF; font-size: 11px; user-select: none; display: flex; align-items: center; gap: 6px;">
                        ${svgIcon("brain", 13)} Thought Process (${currentStep.thinking.length.toLocaleString()} chars &bull; ${currentStep.thinking_duration_ms || 0}ms)
                    </summary>
                    <div style="margin-top: 8px; font-size: 11px; color: #F4F6FA; line-height: 1.5; font-family: var(--agyis-font-mono, monospace); max-height: 320px; overflow-y: auto;">
                        ${renderMarkdownPreview(currentStep.thinking)}
                    </div>
                </details>
            ` : "";

            return `
                ${timingBarHtml}
                ${thinkingBlockHtml}
                ${buildStepBodyHtml(currentStep, state)}
                <div style="display: flex; justify-content: space-between; align-items: center; margin: 12px 0 8px 0;">
                    <h4 style="margin: 0; font-size: 11px; color: #9AA8BE; text-transform: uppercase;">Raw Step JSON</h4>
                    <button id="agyis-copy-btn" class="agyis-hud-btn" title="Copy entire Step JSON">${svgIcon("copy", 12)} Copy</button>
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

        // Raw JSON Copy button
        hudEl.querySelector("#agyis-copy-btn")?.addEventListener("click", () => {
            if (currentStep && navigator.clipboard && typeof navigator.clipboard.writeText === "function") {
                navigator.clipboard.writeText(JSON.stringify(currentStep, null, 2)).then(() => {
                    const btn = hudEl.querySelector("#agyis-copy-btn");
                    if (btn) btn.innerHTML = `${svgIcon("check", 12)} Copied!`;
                    setTimeout(() => { if (btn) btn.innerHTML = `${svgIcon("copy", 12)} Copy`; }, 1500);
                }).catch(err => {
                    console.warn("[agyis:hud] Failed to copy JSON:", err);
                });
            }
        });

        // Markdown code block Copy buttons
        hudEl.querySelectorAll(".agyis-copy-code-btn").forEach(btn => {
            btn.addEventListener("click", (e) => {
                e.stopPropagation();
                const codeId = btn.getAttribute("data-code-id");
                const preEl = codeId ? hudEl.querySelector("#" + cssEscape(codeId)) : null;
                const text = preEl ? (preEl.textContent || "") : "";
                if (text && navigator.clipboard && typeof navigator.clipboard.writeText === "function") {
                    navigator.clipboard.writeText(text).then(() => {
                        btn.innerHTML = `${svgIcon("check", 12)} Copied!`;
                        setTimeout(() => { btn.innerHTML = `${svgIcon("copy", 12)} Copy`; }, 1500);
                    }).catch(err => {
                        console.warn("[agyis:hud] Failed to copy code block:", err);
                    });
                }
            });
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

        // Jump to Previous Checkpoint button in Checkpoint card
        hudEl.querySelector("#agyis-jump-prev-checkpoint")?.addEventListener("click", () => {
            if (state.activeCheckpointIndex > 0) {
                state.activeCheckpointIndex -= 1;
                const checkpoints = (state.currentData && state.currentData.checkpoints) || [];
                const prevCp = checkpoints[state.activeCheckpointIndex];
                if (prevCp && typeof selectStepCallback === "function") {
                    selectStepCallback(prevCp.start_index, { preserveCheckpoint: true });
                } else if (typeof global.__agyis_hud_render === "function") {
                    global.__agyis_hud_render();
                }
            }
        });

        // Hover syncing on prompt section and tool cards
        if (typeof _u().bindItemKeyHover === "function") {
            _u().bindItemKeyHover(hudEl, state, ".agyis-inspector-item-card");
        }
    }

    // Export module onto window namespace
    global.buildInspectorHtml = buildInspectorHtml;
    global.bindInspectorEvents = bindInspectorEvents;
    global.syntaxHighlightJson = syntaxHighlightJson;
    global.renderMarkdownPreview = renderMarkdownPreview;

})(typeof window !== "undefined" ? window : globalThis);
