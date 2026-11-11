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

    function parseStepTimestampMs(rawStep, gm, em) {
        const cand = (rawStep && (rawStep.created_at || rawStep.createdAt || rawStep.timestamp)) ||
            (gm && (gm.createdAt || gm.timestamp)) ||
            (em && (em.completedAt || em.startedAt || em.timestamp)) || null;
        if (!cand) return null;
        if (typeof cand === "number") return cand > 1e12 ? cand : cand * 1000;
        const parsed = Date.parse(String(cand));
        return Number.isFinite(parsed) ? parsed : null;
    }

    function resolveMeasuredSlices(rawSysPrompt, promptSections, rawChatTools) {
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
        const systemPromptSlices = [];
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
            if (systemPromptSlices.length === 0) {
                systemPromptSlices.push({
                    name: "System Prompt",
                    tokens: Math.max(1, Math.round(rawSysPrompt.length / 3.5)),
                    color: "#6366f1",
                });
            }
        } else if (promptSections && promptSections.length > 0) {
            const palette = ["#6366f1", "#818cf8", "#a78bfa", "#c084fc", "#e879f9", "#f472b6", "#fb7185", "#9333ea", "#7c3aed", "#6d28d9", "#5b21b6", "#4c1d95", "#8b5cf6", "#a855f7", "#d946ef"];
            promptSections.forEach((sec, sidx) => {
                const sName = sec.name || sec.title || `Section #${sidx + 1}`;
                const sContent = sec.content || sec.text || "";
                if (sContent) {
                    systemPromptSlices.push({
                        name: sName,
                        tokens: Math.max(1, Math.round(sContent.length / 3.5)),
                        color: palette[sidx % palette.length],
                    });
                }
            });
        }

        const toolCatMap = {
            filesystem: { name: "Filesystem Tools", color: "#06b6d4", tokens: 0, tools: ["read_file", "write_file", "edit_file", "replace_file_content", "write_to_file", "view_file"] },
            terminal: { name: "Terminal Tools", color: "#0891b2", tokens: 0, tools: ["run_command", "bash"] },
            subagents: { name: "Subagents", color: "#0e7490", tokens: 0, tools: ["invoke_subagent", "define_subagent", "manage_subagents", "send_message"] },
            automation: { name: "Automation & Tasks", color: "#14b8a6", tokens: 0, tools: ["schedule", "manage_task", "call_mcp_tool", "list_resources", "read_resource", "search_web", "search_marketplace", "list_plugin_accounts", "ask_question"] },
        };
        const toolDefSlices = [];
        if (rawChatTools && rawChatTools.length > 0) {
            rawChatTools.forEach(t => {
                const tName = (t.name || "").toLowerCase();
                const tok = Math.max(15, Math.round(JSON.stringify(t).length / 3.5));
                if (toolCatMap.filesystem.tools.some(k => tName.includes(k))) toolCatMap.filesystem.tokens += tok;
                else if (toolCatMap.terminal.tools.some(k => tName.includes(k))) toolCatMap.terminal.tokens += tok;
                else if (toolCatMap.subagents.tools.some(k => tName.includes(k))) toolCatMap.subagents.tokens += tok;
                else toolCatMap.automation.tokens += tok;
            });
            Object.values(toolCatMap).forEach(cat => {
                if (cat.tokens > 0) {
                    toolDefSlices.push({ name: cat.name, tokens: cat.tokens, color: cat.color });
                }
            });
        }
        return { systemPromptSlices, toolDefSlices };
    }

    function buildHudTrajectoryData(convoId, rawSteps, genMetas, execMetas, chatModelData) {
        const orderedRaw = rawSteps
            .map((rs, idx) => ({ raw: rs, origIdx: idx }))
            .sort((a, b) => {
                const sa = Number(a.raw && (a.raw.stepIndex !== undefined ? a.raw.stepIndex : (a.raw.step_index !== undefined ? a.raw.step_index : a.origIdx)));
                const sb = Number(b.raw && (b.raw.stepIndex !== undefined ? b.raw.stepIndex : (b.raw.step_index !== undefined ? b.raw.step_index : b.origIdx)));
                if (Number.isFinite(sa) && Number.isFinite(sb) && sa !== sb) return sa - sb;
                return a.origIdx - b.origIdx;
            })
            .map(item => item.raw);

        const indexMetaStream = (rawList) => {
            const byStep = {};
            const list = [];
            (rawList || []).forEach(item => {
                if (!item) return;
                const idxs = Array.isArray(item.stepIndices) ? item.stepIndices.slice() : [];
                if (item.stepIndex !== undefined && item.stepIndex !== null) idxs.push(item.stepIndex);
                idxs.forEach(k => { byStep[k] = item; });
                list.push({ item, keyed: idxs.length > 0 });
            });
            return { byStep, list, cursor: 0 };
        };
        const nextAlignedMeta = (stream, rawIdx, seqIdx, isEligible) => {
            const hit = stream.byStep[rawIdx] || stream.byStep[seqIdx] || null;
            if (hit) {
                const pos = stream.list.findIndex(e => e.item === hit);
                if (pos >= stream.cursor) stream.cursor = pos + 1;
                return hit;
            }
            if (!isEligible) return null;
            while (stream.cursor < stream.list.length && stream.list[stream.cursor].keyed) stream.cursor++;
            return stream.cursor < stream.list.length ? stream.list[stream.cursor++].item : null;
        };
        const genStream = indexMetaStream(genMetas);
        const execStream = indexMetaStream(execMetas);
        let cumulativeCtx = 0;
        const steps = [];

        orderedRaw.forEach((rawStep, idx) => {
            const rawStepIdx = rawStep.stepIndex !== undefined ? rawStep.stepIndex : (rawStep.step_index !== undefined ? rawStep.step_index : idx);
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
            if (!content) {
                const sysCandidate = rawStep.systemMessage || rawStep.system_message || rawStep.message || rawStep.task_details || rawStep.error_details || rawStep.render_info;
                if (sysCandidate) {
                    content = typeof sysCandidate === "object"
                        ? (sysCandidate.content || sysCandidate.message || sysCandidate.text || JSON.stringify(sysCandidate, null, 2))
                        : String(sysCandidate);
                }
            }

            const thinking = rawStep.thinking || (rawStep.plannerResponse && rawStep.plannerResponse.thinking) || "";
            let toolCalls = rawStep.tool_calls || rawStep.toolCalls || [];
            if (!Array.isArray(toolCalls) && rawStep.toolCall) toolCalls = [rawStep.toolCall];
            const rawTc = rawStep.toolCall || (rawStep.metadata && rawStep.metadata.toolCall);
            if (toolCalls.length === 0 && rawTc) {
                let parsedArgs = rawTc.arguments || rawTc.args || {};
                if (rawTc.argumentsJson) {
                    try { parsedArgs = JSON.parse(rawTc.argumentsJson); } catch (_) { parsedArgs = { raw: rawTc.argumentsJson }; }
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
            const srcLow = String(rawStep.source || rawStep.role || "").toLowerCase();
            const isNonCpType = [
                "GENERIC", "TOOL_CALL", "RUN_COMMAND", "VIEW_FILE", "CODE_ACTION",
                "GREP_SEARCH", "FIND_FILES", "PLANNER_RESPONSE", "MODEL_OUTPUT",
                "REPLACE_FILE_CONTENT", "WRITE_FILE", "SEND_MESSAGE", "INVOKE_SUBAGENT",
            ].includes(cortexType);
            const hasToolData = Boolean(toolCalls.length > 0 || rawStep.runCommand || rawStep.viewFile || rawStep.codeAction || rawStep.invokeSubagent || thinking);
            const isGenuineCtxSummary = !isNonCpType && !hasToolData && srcLow !== "model" && srcLow !== "assistant" && content.includes("<CONTEXT_SUMMARY>") && (srcLow === "system" || srcLow === "system_sdk" || /^\s*<CONTEXT_SUMMARY>/.test(content) || content.includes("RESUMING MY OWN TASK"));
            if (cortexType !== "CHECKPOINT" && (rawStep.checkpoint || rawStep.sessionSummary || rawStep.userIntent || isGenuineCtxSummary)) {
                cortexType = "CHECKPOINT";
            }
            if (!compSummary && cortexType === "CHECKPOINT" && content) {
                const m = String(content).match(/<(?:CONTEXT_SUMMARY|summary)>([\s\S]*?)<\/(?:CONTEXT_SUMMARY|summary)>/i);
                if (m) compSummary = m[1].trim();
            }

            const isModelStep = (cortexType === "PLANNER_RESPONSE" || cortexType === "MODEL_OUTPUT");
            const gm = nextAlignedMeta(genStream, rawStepIdx, idx, isModelStep);

            const isToolStep = (cortexType === "TOOL_CALL" || cortexType.includes("COMMAND") || cortexType.includes("FILE") || cortexType.includes("SEARCH") || cortexType === "CODE_ACTION");
            const em = nextAlignedMeta(execStream, rawStepIdx, idx, isToolStep);

            let thinkingMs = (gm && parseInt(gm.timeToFirstToken || 0, 10)) || 0;
            let streamingMs = (gm && parseInt(gm.streamingDuration || 0, 10)) || 0;
            if (!thinkingMs && thinking) thinkingMs = Math.min(20000, Math.max(600, Math.floor(thinking.length * 1.6)));
            if (!streamingMs && isModelStep) streamingMs = Math.min(45000, Math.max(400, Math.floor(content.length * 1.8)));
            if (em && em.executionDurationMs) streamingMs = parseInt(em.executionDurationMs, 10) || 0;
            const totalDurationMs = thinkingMs + streamingMs;

            const retryUsage = (rawStep.metadata && rawStep.metadata.retryInfos && rawStep.metadata.retryInfos[0] && rawStep.metadata.retryInfos[0].usage) || {};
            const extraFields = {};
            let extraToolText = "";
            if (rawStep.runCommand) {
                extraFields.command = rawStep.runCommand.commandLine || "";
                extraFields.exitCode = rawStep.runCommand.exitCode;
                extraFields.output = (rawStep.runCommand.combinedOutput && rawStep.runCommand.combinedOutput.full) || "";
                extraFields.cwd = rawStep.runCommand.cwd;
                extraToolText += extraFields.command + extraFields.output;
            }
            if (rawStep.viewFile) {
                extraFields.filePath = rawStep.viewFile.absolutePathUri;
                extraFields.fileContent = rawStep.viewFile.content || "";
                extraFields.endLine = rawStep.viewFile.endLine;
                extraToolText += extraFields.fileContent;
            }
            if (rawStep.codeAction) {
                extraFields.diffLines = (rawStep.codeAction.actionResult && rawStep.codeAction.actionResult.edit && rawStep.codeAction.actionResult.edit.diff && rawStep.codeAction.actionResult.edit.diff.unifiedDiff && rawStep.codeAction.actionResult.edit.diff.unifiedDiff.lines) || [];
                const actSpec = rawStep.codeAction.actionSpec || {};
                extraFields.filePath = (actSpec.createFile && actSpec.createFile.path && actSpec.createFile.path.absoluteUri) || (actSpec.editFile && actSpec.editFile.path && actSpec.editFile.path.absoluteUri) || "";
                extraToolText += extraFields.diffLines.join("\n");
            }
            if (rawStep.invokeSubagent) extraFields.subagent = (rawStep.invokeSubagent.subagents && rawStep.invokeSubagent.subagents[0]) || null;
            if (rawStep.checkpoint) {
                extraFields.sessionSummary = rawStep.checkpoint.sessionSummary || "";
                extraFields.cacheReadTokens = parseInt(retryUsage.cacheReadTokens || 0, 10) || 0;
                extraFields.checkpointInputTokens = parseInt(retryUsage.inputTokens || 0, 10) || 0;
            }

            const gmUsage = (gm && gm.usage) || (rawStep.metadata && rawStep.metadata.modelUsage) || {};
            let inTok = parseInt(rawStep.input_tokens || gmUsage.inputTokens || gmUsage.promptTokenCount || gmUsage.inputTokenCount || extraFields.checkpointInputTokens || 0, 10) || 0;
            let outTok = parseInt(rawStep.output_tokens || 0, 10) || 0;
            let cacheTok = parseInt(rawStep.cache_read_tokens || rawStep.cacheReadTokens || gmUsage.cacheReadTokens || gmUsage.cachedContentTokenCount || retryUsage.cacheReadTokens || 0, 10) || 0;
            let thinkOutTok = parseInt(gmUsage.thinkingOutputTokens || 0, 10) || 0;
            if (!outTok && (gmUsage.outputTokens || gmUsage.candidatesTokenCount || gmUsage.responseOutputTokens || thinkOutTok)) {
                const respOut = parseInt(gmUsage.outputTokens || gmUsage.candidatesTokenCount || gmUsage.responseOutputTokens || 0, 10) || 0;
                outTok = respOut + thinkOutTok;
            }

            let stepTok = parseInt(rawStep.tokens || 0, 10) || 0;
            if (stepTok <= 0) {
                if (isModelStep) {
                    stepTok = outTok > 0 ? outTok : Math.round((content.length + thinking.length) / 3.5);
                    if (outTok <= 0) outTok = stepTok;
                } else if (cortexType === "USER_INPUT") {
                    stepTok = Math.round(content.length / 3.5);
                    if (inTok <= 0) inTok = stepTok;
                } else if (cortexType === "CHECKPOINT") {
                    stepTok = Math.round(((compSummary ? compSummary.length : content.length) || 100) / 3.5);
                } else {
                    let charCount = extraToolText.length;
                    toolCalls.forEach(tc => {
                        charCount += (tc.name || "").length + JSON.stringify(tc.args || {}).length + String(tc.output || "").length;
                    });
                    if (charCount === 0) charCount = content.length;
                    stepTok = Math.round(charCount / 3.5);
                    if (outTok <= 0) outTok = stepTok;
                }
            }

            if (cortexType === "CHECKPOINT") cumulativeCtx = stepTok;
            else if (stepTok > 0) cumulativeCtx += stepTok;

            const stepObj = Object.assign({
                step_index: rawStepIdx,
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
                thinking_tokens: thinkOutTok,
                cache_read_tokens: cacheTok,
                tokens: stepTok,
                cumulative_tokens: cumulativeCtx,
                compaction_summary: compSummary,
                checkpoint_index: checkpointIndex,
                response_model: (gm && (gm.responseModel || gm.model)) || "",
                generator_metadata: gm,
                executor_metadata: em,
                timestamp_ms: parseStepTimestampMs(rawStep, gm, em),
                _hasExplicitInput: (rawStep.input_tokens !== undefined || Boolean(gmUsage.inputTokens || gmUsage.promptTokenCount || gmUsage.inputTokenCount || extraFields.checkpointInputTokens)),
                _hasAuthUsage: (inTok + cacheTok > 0) && (cortexType !== "USER_INPUT" || rawStep.input_tokens !== undefined || Boolean(gmUsage.inputTokens || gmUsage.promptTokenCount || cacheTok > 0)),
            }, extraFields);
            steps.push(stepObj);
        });

        const checkpoints = [];
        steps.forEach((s, i) => {
            if (s.type === "CHECKPOINT" || Boolean(orderedRaw[i] && orderedRaw[i].checkpoint)) {
                checkpoints.push(i);
            }
        });

        const epochs = [];
        if (checkpoints.length === 0) {
            if (steps.length > 0) {
                epochs.push({ epoch_index: 0, start_index: 0, end_index: steps.length - 1, step_count: steps.length, has_checkpoint: false, summary: "Initial Trajectory" });
            }
        } else {
            const c0 = checkpoints[0];
            epochs.push({ epoch_index: 0, start_index: 0, end_index: c0, step_count: c0 + 1, has_checkpoint: true, summary: steps[c0].compaction_summary || `Checkpoint #${c0}` });
            for (let k = 0; k < checkpoints.length; k++) {
                const curCp = checkpoints[k];
                const endIdx = (k + 1 < checkpoints.length) ? checkpoints[k + 1] : (curCp < steps.length - 1 ? steps.length - 1 : -1);
                if (endIdx >= 0) {
                    epochs.push({
                        epoch_index: epochs.length,
                        start_index: curCp,
                        end_index: endIdx,
                        step_count: endIdx - curCp + 1,
                        has_checkpoint: true,
                        summary: steps[curCp].compaction_summary || `Checkpoint #${curCp}`,
                    });
                }
            }
        }

        let maxContextTokens = 256000;
        let foundMaxContext = false;
        let latestEstimatedTokens = 0;
        const extractCwmFromObj = (obj) => {
            if (!obj || typeof obj !== "object") return;
            const cwmCandidates = [
                obj.contextWindowMetadata,
                obj.chatStartMetadata && obj.chatStartMetadata.contextWindowMetadata,
                obj.metadata && obj.metadata.contextWindowMetadata,
                obj.metadata && obj.metadata.chatStartMetadata && obj.metadata.chatStartMetadata.contextWindowMetadata,
            ];
            for (let cIdx = 0; cIdx < cwmCandidates.length; cIdx++) {
                const cwm = cwmCandidates[cIdx];
                if (!cwm || typeof cwm !== "object") continue;
                if (cwm.estimatedTokensUsed && !latestEstimatedTokens) {
                    const est = parseInt(cwm.estimatedTokensUsed, 10) || 0;
                    if (est > 0) latestEstimatedTokens = est;
                }
                if (cwm.maxContextTokens && !foundMaxContext) {
                    const mct = parseInt(cwm.maxContextTokens, 10) || 0;
                    if (mct > 0) { maxContextTokens = mct; foundMaxContext = true; }
                }
            }
        };
        for (let i = genMetas.length - 1; i >= 0; i--) {
            extractCwmFromObj(genMetas[i]);
            if (latestEstimatedTokens > 0 && foundMaxContext) break;
        }
        if (!foundMaxContext || latestEstimatedTokens === 0) {
            for (let i = orderedRaw.length - 1; i >= 0; i--) {
                extractCwmFromObj(orderedRaw[i]);
                if (latestEstimatedTokens > 0 && foundMaxContext) break;
            }
        }

        const extractEstFromObj = (obj) => {
            if (!obj || typeof obj !== "object") return 0;
            const cwmCandidates = [
                obj.contextWindowMetadata,
                obj.chatStartMetadata && obj.chatStartMetadata.contextWindowMetadata,
                obj.metadata && obj.metadata.contextWindowMetadata,
                obj.metadata && obj.metadata.chatStartMetadata && obj.metadata.chatStartMetadata.contextWindowMetadata,
            ];
            for (let cIdx = 0; cIdx < cwmCandidates.length; cIdx++) {
                const cwm = cwmCandidates[cIdx];
                if (cwm && typeof cwm === "object" && cwm.estimatedTokensUsed) {
                    const est = parseInt(cwm.estimatedTokensUsed, 10) || 0;
                    if (est > 0) return est;
                }
            }
            return 0;
        };

        const rawSysPrompt = (chatModelData && chatModelData.systemPrompt) || "";
        const rawChatTools = (chatModelData && chatModelData.tools) || [];
        const promptSections = (chatModelData && chatModelData.promptSections) ||
            (genMetas[0] && genMetas[0].plannerConfig && genMetas[0].plannerConfig.declarativeMixinConfig && genMetas[0].plannerConfig.declarativeMixinConfig.promptSections) ||
            (orderedRaw[0] && orderedRaw[0].declarativeMixinConfig && orderedRaw[0].declarativeMixinConfig.promptSections) || [];
        const { systemPromptSlices, toolDefSlices } = resolveMeasuredSlices(rawSysPrompt, promptSections, rawChatTools);
        const sysPromptTok = systemPromptSlices.reduce((acc, sl) => acc + (sl.tokens || 0), 0);
        const toolDefsTok = toolDefSlices.reduce((acc, sl) => acc + (sl.tokens || 0), 0);

        const computeEpochMetrics = (epSteps, epStart, epEnd, isLastEpoch) => {
            let explicitUsageTokens = 0;
            let epochCacheTokens = 0;
            let epochEstTokens = 0;
            for (let i = epSteps.length - 1; i >= 0; i--) {
                const st = epSteps[i];
                if (epochCacheTokens === 0 && st.cache_read_tokens > 0) epochCacheTokens = st.cache_read_tokens;
                if (explicitUsageTokens === 0 && st._hasAuthUsage) {
                    explicitUsageTokens = st.input_tokens + st.cache_read_tokens;
                }
                if (epochEstTokens === 0) {
                    epochEstTokens = extractEstFromObj(st.generator_metadata) || extractEstFromObj(orderedRaw[epStart + i]);
                }
            }
            if (epochEstTokens === 0) {
                for (let gIdx = genMetas.length - 1; gIdx >= 0; gIdx--) {
                    const gm = genMetas[gIdx];
                    const gmStep = (gm && gm.stepIndex !== undefined) ? gm.stepIndex : -1;
                    if (gmStep >= epStart && gmStep <= epEnd) {
                        epochEstTokens = extractEstFromObj(gm);
                        if (epochEstTokens > 0) break;
                    }
                }
            }
            if (isLastEpoch && epochEstTokens === 0) epochEstTokens = latestEstimatedTokens;

            let actualUserTok = 0;
            let actualModelTok = 0;
            let actualThoughtTok = 0;
            let actualToolTok = 0;
            let actualCheckpointTok = 0;
            let actualSystemTok = 0;

            epSteps.forEach(s => {
                const t = s.type;
                const tok = s.tokens || 0;
                if (t === "USER_INPUT") actualUserTok += tok;
                else if (t === "PLANNER_RESPONSE" || t === "MODEL_OUTPUT") {
                    const rawThink = s.thinking_tokens || (s.thinking ? Math.round(s.thinking.length / 3.5) : 0);
                    const thinkPart = Math.min(tok, rawThink);
                    actualThoughtTok += thinkPart;
                    actualModelTok += Math.max(0, tok - thinkPart);
                } else if (t === "CHECKPOINT") actualCheckpointTok += tok;
                else if (t === "SYSTEM") actualSystemTok += tok;
                else actualToolTok += tok;
            });

            const activeMeasuredSum = sysPromptTok + toolDefsTok + actualCheckpointTok + actualUserTok + actualModelTok + actualThoughtTok + actualToolTok + actualSystemTok;
            const explicitBest = explicitUsageTokens > 0 ? explicitUsageTokens : epochEstTokens;
            const epTotalTokens = explicitBest > 0 ? Math.max(explicitBest, activeMeasuredSum) : activeMeasuredSum;
            const epIsProvisional = (explicitUsageTokens === 0) && (epTotalTokens > 0);
            const epUnattrTok = Math.max(0, epTotalTokens - activeMeasuredSum);
            return {
                total_tokens: epTotalTokens,
                unattributed: epUnattrTok,
                cache_tokens: epochCacheTokens,
                is_provisional: epIsProvisional,
                token_breakdown: {
                    system_prompt: sysPromptTok,
                    tool_defs: toolDefsTok,
                    checkpoint: actualCheckpointTok,
                    user: actualUserTok,
                    model: actualModelTok,
                    thought: actualThoughtTok,
                    tool: actualToolTok,
                    system: actualSystemTok,
                    unattributed: epUnattrTok,
                },
            };
        };

        epochs.forEach((ep, eIdx) => {
            const epSlice = steps.slice(ep.start_index, ep.end_index + 1);
            const epMetrics = computeEpochMetrics(epSlice, ep.start_index, ep.end_index, eIdx === epochs.length - 1);
            ep.total_tokens = epMetrics.total_tokens;
            ep.unattributed = epMetrics.unattributed;
            ep.cache_tokens = epMetrics.cache_tokens;
            ep.is_provisional = epMetrics.is_provisional;
            ep.token_breakdown = epMetrics.token_breakdown;
        });

        const lastEpoch = epochs.length > 0 ? epochs[epochs.length - 1] : null;
        const activeEpochSteps = lastEpoch ? steps.slice(lastEpoch.start_index, lastEpoch.end_index + 1) : steps;
        const latestMetrics = lastEpoch || computeEpochMetrics(activeEpochSteps, 0, Math.max(0, steps.length - 1), true);
        const totalTokens = latestMetrics.total_tokens;
        const cacheTokens = latestMetrics.cache_tokens;
        const isProvisional = latestMetrics.is_provisional;
        const tokenBreakdown = latestMetrics.token_breakdown;
        steps.forEach(s => { delete s._hasExplicitInput; delete s._hasAuthUsage; });

        const velSamples = activeEpochSteps
            .filter(s => s.timestamp_ms !== null && (s.input_tokens + s.cache_read_tokens + s.cumulative_tokens) > 0)
            .map(s => ({ t: s.timestamp_ms, tok: (s.input_tokens + s.cache_read_tokens) || s.cumulative_tokens }));
        let burnRatePerMin = 0;
        if (velSamples.length >= 2) {
            const dtMs = velSamples[velSamples.length - 1].t - velSamples[0].t;
            const dTok = velSamples[velSamples.length - 1].tok - velSamples[0].tok;
            if (dtMs > 0 && dTok > 0) burnRatePerMin = (dTok / (dtMs / 60000));
        }

        const subagents = [];
        const subagentInfos = [];
        const subUuidRe = /[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}/g;
        const addSubagent = (uid, name, summary) => {
            const cleanUid = String(uid || "").trim();
            if (!cleanUid || cleanUid === convoId || cleanUid.includes("\\") || subagents.includes(cleanUid)) return;
            subagents.push(cleanUid);
            subagentInfos.push({
                id: cleanUid,
                name: name || `Subagent ${cleanUid.slice(0, 8)}`,
                summary: String(summary || "").slice(0, 80),
            });
        };
        steps.forEach(s => {
            if (s.subagent && (s.subagent.conversationId || s.subagent.id)) {
                addSubagent(s.subagent.conversationId || s.subagent.id, s.subagent.role || s.subagent.name, s.subagent.objective);
            }
            (s.tool_calls || []).forEach(tc => {
                const tcName = String(tc.name || "").toLowerCase();
                if (tcName !== "invoke_subagent" && tcName !== "send_message") return;
                const args = (tc.args && typeof tc.args === "object") ? tc.args : {};
                const roleName = args.TypeName || args.Role || args.name || args.agent_role || (tcName === "send_message" ? "Peer Agent" : "");
                const promptText = args.Prompt || args.objective || args.prompt || "";
                const explicitUid = args.conversationId || args.conversation_id || args.Recipient || "";
                const outCombined = (tcName === "invoke_subagent")
                    ? `${JSON.stringify(args)} ${String(tc.output || tc.result || "")}`
                    : `${explicitUid} ${String(tc.output || tc.result || "")}`;
                const uuids = outCombined.match(subUuidRe) || [];
                uuids.forEach(uid => addSubagent(uid, roleName, promptText));
            });
        });

        let convoSummary = `Session ${convoId.slice(0, 8)}`;
        const firstUserStep = steps.find(s => s.type === "USER_INPUT");
        if (firstUserStep && firstUserStep.content) convoSummary = String(firstUserStep.content).slice(0, 80).replace(/\r?\n/g, " ");

        const resolvedModel = (chatModelData && (chatModelData.model || chatModelData.modelName)) ||
            (genMetas[0] && (genMetas[0].responseModel || genMetas[0].model)) ||
            (steps.find(s => s.response_model) && steps.find(s => s.response_model).response_model) ||
            (window.__agyis_hud_state && window.__agyis_hud_state.sessionModel) || "";

        return {
            conversation_id: convoId,
            summary: convoSummary,
            model: resolvedModel,
            steps: steps,
            step_count: steps.length,
            epochs: epochs,
            parent_id: null,
            subagents: subagents,
            subagent_infos: subagentInfos,
            subagent_trajectories: {},
            total_tokens: totalTokens,
            max_context_tokens: maxContextTokens,
            cache_tokens: cacheTokens,
            is_provisional: isProvisional,
            burn_rate_tokens_per_min: Math.round(burnRatePerMin * 10) / 10,
            token_breakdown: tokenBreakdown,
            system_prompt_slices: systemPromptSlices,
            tool_def_slices: toolDefSlices,
        };
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
            if (csrfToken) headers["x-codeium-csrf-token"] = csrfToken;

            const reqBody = JSON.stringify({ cascadeId: convoId });
            const [trajRes, stepsRes, genRes, execRes] = await Promise.all([
                fetch(`${baseUrl}/exa.language_server_pb.LanguageServerService/GetCascadeTrajectory`, { method: "POST", headers, body: reqBody }).catch(() => null),
                fetch(`${baseUrl}/exa.language_server_pb.LanguageServerService/GetCascadeTrajectorySteps`, { method: "POST", headers, body: reqBody }).catch(() => null),
                fetch(`${baseUrl}/exa.language_server_pb.LanguageServerService/GetCascadeTrajectoryGeneratorMetadata`, { method: "POST", headers, body: reqBody }).catch(() => null),
                fetch(`${baseUrl}/exa.language_server_pb.LanguageServerService/GetCascadeTrajectoryExecutorMetadatas`, { method: "POST", headers, body: reqBody }).catch(() => null),
            ]);

            let rawSteps = null;
            if (stepsRes && stepsRes.ok) {
                const stepsJson = await stepsRes.json().catch(() => null);
                if (stepsJson && Array.isArray(stepsJson.steps)) rawSteps = stepsJson.steps;
            }
            if (!rawSteps && trajRes && trajRes.ok) {
                const trajJson = await trajRes.json().catch(() => null);
                if (trajJson && trajJson.trajectory && Array.isArray(trajJson.trajectory.steps)) rawSteps = trajJson.trajectory.steps;
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
                if (execJson) execMetas = execJson.executorMetadatas || execJson.metadatas || [];
            }

            const data = buildHudTrajectoryData(convoId, rawSteps, genMetas, execMetas, chatModelData);
            const state = window.__agyis_hud_state;
            if (state) {
                state.rootData = data;
                state.currentData = data;
                state.convoId = convoId;
                if (data.model) state.sessionModel = data.model;
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
