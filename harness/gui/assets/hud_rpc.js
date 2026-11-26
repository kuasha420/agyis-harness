// SPDX-License-Identifier: Apache-2.0
// Copyright (c) 2026 Arafat Zahan (@kuasha420)
// Corporate Stewardship & Infrastructure: Purrfect Software Limited (PSL)
// Governed by: ICARO-42/b Ordinance (Company-Supported Personal IP Framework)

/**
 * hud_rpc.js — ConnectRPC Trajectory Client, SSOT Token Parser & 60 FPS Streaming Engine (lvc/ovc).
 * ConnectRPC streaming over /exa.language_server_pb.LanguageServerService/StreamAgentStateUpdates,
 * 60 FPS StreamRenderCoordinator, Protobuf SSOT Token Breakdown Parser, and dynamic fallback ladder.
 */

(function(global) {
    "use strict";

    function inferModelContextWindow(modelName) {
        if (!modelName) return 256000;
        const lower = String(modelName).toLowerCase();
        if (lower.includes("1m") || lower.includes("1000k") || lower.includes("1048576")) return 1000000;
        if (lower.includes("gpt-oss-120b") || lower.includes("gpt oss 120b")) return 80000;
        if (["claude-sonnet-4-6", "claude-sonnet-4.6", "claude sonnet 4.6", "claude-4-6-sonnet", "claude-4.6-sonnet"].some(t => lower.includes(t))) return 160000;
        if (["claude-sonnet-5-5", "claude-sonnet-5.5", "claude sonnet 5.5", "claude-5-5-sonnet", "claude-5.5-sonnet", "claude-opus-5-5", "claude-opus-5.5", "claude opus 5.5", "claude-5-5-opus", "claude-5.5-opus"].some(t => lower.includes(t))) return 840000;
        if (lower.includes("512k") || ["gemini-4-hydrogen", "gemini-4-neon", "gemini-4-argon", "gemini-4-carbon", "gemini 4 hydrogen", "gemini 4 neon", "gemini 4 argon", "gemini 4 carbon", "gemini-pro-orchestrator", "gemini pro orchestrator", "gemini-pro-coordinator", "gemini pro coordinator", "orchestrator (", "gemini-3.8-flash-s", "gemini-3.8-flash-h", "gemini-3.8-flash-medium", "gemini-3.8-flash-low", "gemini 3.8 flash"].some(t => lower.includes(t))) return 512000;
        if (lower.includes("200k")) return 200000;
        if (lower.includes("128k")) return 128000;
        return 256000;
    }

    global.__agyis_utils = Object.assign(global.__agyis_utils || {}, { inferModelContextWindow, _rpcInferCtx: inferModelContextWindow });

    const _V234_TOOL_MAP = {
        run_command: "RUN_COMMAND", bash: "RUN_COMMAND", read_file: "READ_FILE", view_file: "VIEW_FILE",
        edit_file: "EDIT_FILE", replace_file_content: "REPLACE_FILE_CONTENT", write_file: "WRITE_FILE", write_to_file: "WRITE_FILE",
        grep_search: "GREP_SEARCH", search_web: "SEARCH_WEB", find_by_name: "FIND_FILES", find_files: "FIND_FILES",
        post_message: "POST_MESSAGE", send_message: "SEND_MESSAGE", read_board: "READ_BOARD", swarm_wait: "SWARM_WAIT",
        swarm: "SWARM", run_workflow: "RUN_WORKFLOW", define_subagent: "DEFINE_SUBAGENT",
        manage_subagents: "MANAGE_SUBAGENTS", manage_task: "MANAGE_TASK", invoke_subagent: "INVOKE_SUBAGENT",
        update_focus: "UPDATE_FOCUS", update_steps: "UPDATE_STEPS", enter_plan_mode: "ENTER_PLAN_MODE",
        exit_plan_mode: "EXIT_PLAN_MODE", ask_question: "ASK_QUESTION", search_marketplace: "SEARCH_MARKETPLACE",
        list_plugin_accounts: "LIST_PLUGIN_ACCOUNTS", call_mcp_tool: "CALL_MCP_TOOL",
        list_resources: "LIST_RESOURCES", read_resource: "READ_RESOURCE",
    };

    /**
     * Parses step timestamp in epoch milliseconds from varied metadata formats.
     */
    function parseStepTimestampMs(rawStep, gm, em) {
        const cand = (rawStep && (rawStep.created_at || rawStep.createdAt || rawStep.timestamp)) ||
            (gm && (gm.createdAt || gm.timestamp)) ||
            (em && (em.completedAt || em.startedAt || em.timestamp)) || null;
        if (!cand) return null;
        if (typeof cand === "number") return cand > 1e12 ? cand : cand * 1000;
        const parsed = Date.parse(String(cand));
        return Number.isFinite(parsed) ? parsed : null;
    }

    /**
     * Decodes granular token attribution slices from protobuf tokenBreakdown.groups (Strand 2 SSOT).
     */
    function extractProtobufBreakdownSlices(tokenBreakdown, chatModelData, genMetas) {
        const systemPromptSlices = [];
        const toolDefSlices = [];

        const groups = (tokenBreakdown && tokenBreakdown.groups) || [];
        if (groups.length > 0) {
            groups.forEach(g => {
                const gType = Number(g.type);
                const gName = g.name || "";
                const gTokens = Number(g.numTokens || g.num_tokens || 0);
                const children = g.children || [];

                // Group 1: SYSTEM_PROMPT (or 3: RULES, 5: SKILLS, 6: SUBAGENTS, 8: WORKFLOWS, 9: PLUGINS, 10: FLOWS)
                if (gType === 1 || gType === 3 || gType === 5 || gType === 6 || gType === 8 || gType === 9 || gType === 10 || (gType === 0 && /identity/i.test(gName))) {
                    const fallbackGroupNames = { 1: "System Instructions", 3: "Rules", 5: "Skills", 6: "Subagents", 8: "Workflows", 9: "Plugins", 10: "Flows" };
                    if (children.length > 0) {
                        children.forEach(c => {
                            const cName = c.name || "section";
                            const cTok = Number(c.numTokens || c.num_tokens || 0);
                            if (cTok > 0) systemPromptSlices.push({ name: cName, tag: cName.toLowerCase().replace(/[^a-z0-9_]/g, "_"), tokens: cTok });
                        });
                    } else if (gTokens > 0) {
                        const label = gName || fallbackGroupNames[gType] || "System Instructions";
                        systemPromptSlices.push({ name: label, tag: label.toLowerCase().replace(/[^a-z0-9_]/g, "_"), tokens: gTokens });
                    }
                }

                // Group 2: TOOLS (Native) or Group 4: MCP_TOOLS
                if (gType === 2 || gType === 4) {
                    if (children.length > 0) {
                        children.forEach(c => {
                            const cName = c.name || "tool";
                            const subChildren = c.children || [];
                            if (subChildren.length > 0) {
                                subChildren.forEach(sc => {
                                    const scName = sc.name || "tool";
                                    const scTok = Number(sc.numTokens || sc.num_tokens || 0);
                                    if (scTok > 0) toolDefSlices.push({ name: scName, server_name: cName, is_mcp: true, tokens: scTok });
                                });
                            } else {
                                const cTok = Number(c.numTokens || c.num_tokens || 0);
                                if (cTok > 0) toolDefSlices.push({ name: cName, server_name: gType === 4 ? (g.serverName || "") : "", is_mcp: gType === 4, tokens: cTok });
                            }
                        });
                    } else if (gTokens > 0) {
                        toolDefSlices.push({ name: gName || "Tool Schemas", tokens: gTokens, is_mcp: gType === 4 });
                    }
                }
            });
        }

        // Fallbacks
        if (toolDefSlices.length === 0 && chatModelData && Array.isArray(chatModelData.tools)) {
            chatModelData.tools.forEach(t => {
                const serverName = t.serverName || t.server_name || "";
                toolDefSlices.push({ name: t.name || "tool", server_name: serverName, is_mcp: Boolean(serverName), tokens: Math.max(15, Math.round(JSON.stringify(t).length / 3.5)) });
            });
        }
        if (systemPromptSlices.length === 0 && chatModelData && Array.isArray(chatModelData.promptSections)) {
            chatModelData.promptSections.forEach((sec, idx) => {
                const sName = sec.title || sec.name || `Section #${idx + 1}`;
                systemPromptSlices.push({ name: sName, tag: sName.toLowerCase().replace(/[^a-z0-9_]/g, "_"), tokens: Math.max(10, Math.round((sec.content || "").length / 3.5)) });
            });
        }
        return { systemPromptSlices, toolDefSlices };
    }

    function _cwmList(obj) {
        if (!obj || typeof obj !== "object") return [];
        return [obj.contextWindowMetadata, obj.chatStartMetadata?.contextWindowMetadata, obj.metadata?.contextWindowMetadata, obj.metadata?.chatStartMetadata?.contextWindowMetadata, obj.chatModel?.chatStartMetadata?.contextWindowMetadata];
    }

    /**
     * Builds the unified Trajectory Model from raw steps, generator metadata, and executor metadata.
     */
    function buildHudTrajectoryData(convoId, rawSteps, genMetas, execMetas, chatModelData) {
        const orderedRaw = (rawSteps || [])
            .map((rs, idx) => ({ raw: rs, origIdx: idx }))
            .sort((a, b) => {
                const sa = Number(a.raw && (a.raw.stepIndex !== undefined ? a.raw.stepIndex : (a.raw.step_index !== undefined ? a.raw.step_index : a.origIdx)));
                const sb = Number(b.raw && (b.raw.stepIndex !== undefined ? b.raw.stepIndex : (b.raw.step_index !== undefined ? b.raw.step_index : b.origIdx)));
                if (Number.isFinite(sa) && Number.isFinite(sb) && sa !== sb) return sa - sb;
                return a.origIdx - b.origIdx;
            })
            .map(item => item.raw);

        // Index metadata streams with O(1) position lookup
        const indexMetaStream = (rawList) => {
            const byStep = {};
            const list = [];
            const posMap = new Map();
            (rawList || []).forEach((item, pos) => {
                if (!item) return;
                const idxs = Array.isArray(item.stepIndices) ? item.stepIndices.slice() : [];
                if (item.stepIndex !== undefined && item.stepIndex !== null) idxs.push(item.stepIndex);
                idxs.forEach(k => { byStep[k] = item; });
                const entryIdx = list.length;
                posMap.set(item, entryIdx);
                list.push({ item, keyed: idxs.length > 0 });
            });
            return { byStep, list, posMap, cursor: 0 };
        };

        const nextAlignedMeta = (stream, rawIdx, seqIdx, isEligible) => {
            const hit = stream.byStep[rawIdx] || stream.byStep[seqIdx] || null;
            if (hit) {
                const pos = stream.posMap.get(hit);
                if (pos !== undefined && pos >= stream.cursor) stream.cursor = pos + 1;
                return hit;
            }
            if (!isEligible) return null;
            while (stream.cursor < stream.list.length) {
                const entry = stream.list[stream.cursor++];
                if (!entry.keyed) return entry.item;
            }
            return null;
        };

        const genStream = indexMetaStream(genMetas);
        const execStream = indexMetaStream(execMetas);

        let cumulativeTokens = 0;

        const steps = orderedRaw.map((rs, idx) => {
            const stepIdx = rs.stepIndex !== undefined ? rs.stepIndex : (rs.step_index !== undefined ? rs.step_index : idx);
            let cortexType = rs.type !== undefined ? rs.type : (rs.stepType !== undefined ? rs.stepType : "STEP");
            if (cortexType === 132 || cortexType === "132") {
                cortexType = "GENERIC";
            } else if (cortexType === 23 || cortexType === "23" || Boolean(rs.checkpoint)) {
                cortexType = "CHECKPOINT";
            } else if (typeof cortexType === "string" && cortexType.startsWith("CORTEX_STEP_TYPE_")) {
                cortexType = cortexType.replace("CORTEX_STEP_TYPE_", "");
            }
            const tCalls = rs.tool_calls || rs.toolCalls || [];
            if ((cortexType === "STEP" || cortexType === "TOOL_CALL") && Array.isArray(tCalls) && tCalls.length > 0) {
                const firstTcName = String(tCalls[0]?.name || "").toLowerCase();
                for (const [needle, mappedType] of Object.entries(_V234_TOOL_MAP)) {
                    if (firstTcName.includes(needle)) {
                        cortexType = mappedType;
                        break;
                    }
                }
            } else if (cortexType === "GENERIC" && rs.generic && rs.generic.toolName) {
                const gName = String(rs.generic.toolName).toLowerCase();
                if (_V234_TOOL_MAP[gName]) cortexType = _V234_TOOL_MAP[gName];
            }
            const isModelStep = cortexType === "PLANNER_RESPONSE" || cortexType === "MODEL_OUTPUT";
            const isExecStep = !isModelStep && cortexType !== "USER_INPUT";

            const gm = nextAlignedMeta(genStream, stepIdx, idx, isModelStep);
            const em = nextAlignedMeta(execStream, stepIdx, idx, isExecStep);

            const extraFields = {};
            if (rs.runCommand) Object.assign(extraFields, { command: rs.runCommand.commandLine || "", exitCode: rs.runCommand.exitCode, output: (rs.runCommand.combinedOutput && rs.runCommand.combinedOutput.full) || "", cwd: rs.runCommand.cwd || "" });
            if (rs.viewFile) Object.assign(extraFields, { filePath: rs.viewFile.absolutePathUri || "", fileContent: rs.viewFile.content || "", endLine: rs.viewFile.endLine });
            if (rs.codeAction) {
                const actSpec = rs.codeAction.actionSpec || {};
                extraFields.diffLines = (rs.codeAction.actionResult?.edit?.diff?.unifiedDiff?.lines) || [];
                extraFields.filePath = actSpec.createFile?.path?.absoluteUri || actSpec.editFile?.path?.absoluteUri || "";
            }
            if (rs.invokeSubagent) extraFields.subagent = (rs.invokeSubagent.subagents && rs.invokeSubagent.subagents[0]) || null;
            if (rs.checkpoint && typeof rs.checkpoint === "object") {
                const cpSum = rs.checkpoint.sessionSummary || rs.checkpoint.userIntent || rs.checkpoint.summary || "";
                extraFields.sessionSummary = rs.checkpoint.sessionSummary || "";
                if (cpSum) extraFields.compaction_summary = String(cpSum).trim();
                const cpIdx = rs.checkpoint.checkpointIndex ?? rs.checkpoint.checkpoint_index;
                if (cpIdx !== undefined) extraFields.checkpoint_index = cpIdx;
            } else if (typeof rs.checkpoint === "string" && rs.checkpoint.trim()) {
                extraFields.compaction_summary = rs.checkpoint.trim();
            }
            if (!extraFields.compaction_summary && (rs.compaction_summary || rs.sessionSummary || rs.userIntent)) {
                extraFields.compaction_summary = String(rs.compaction_summary || rs.sessionSummary || rs.userIntent).trim();
            }
            if (cortexType === "CHECKPOINT" && !extraFields.compaction_summary) {
                const m = String(rs.content || rs.thinking || "").match(/<(?:CONTEXT_SUMMARY|summary)>([\s\S]*?)<\/(?:CONTEXT_SUMMARY|summary)>/i);
                if (m && m[1]) extraFields.compaction_summary = m[1].trim();
            }
            const retries = (rs.metadata && Array.isArray(rs.metadata.retryInfos)) ? rs.metadata.retryInfos : [];
            const retryUsage = (retries[0] && typeof retries[0] === "object" && retries[0].usage) || {};
            if (cortexType === "CHECKPOINT" || rs.checkpoint) {
                extraFields.cacheReadTokens = Number(retryUsage.cacheReadTokens || 0);
                extraFields.checkpointInputTokens = Number(retryUsage.inputTokens || 0);
            }
            if (rs.generic) {
                extraFields.generic = rs.generic;
                if (rs.generic.toolName) extraFields.toolName = rs.generic.toolName;
                if (rs.generic.output !== undefined) extraFields.output = rs.generic.output;
            }

            const tsMs = parseStepTimestampMs(rs, gm, em);
            const gmUsage = (gm && gm.usage) || (rs.metadata && rs.metadata.modelUsage) || {};

            const inTok = Number(rs.input_tokens || gmUsage.inputTokens || extraFields.checkpointInputTokens || 0);
            const outTok = Number(rs.output_tokens || gmUsage.outputTokens || 0);
            const thinkTok = Number(rs.thinking_tokens || gmUsage.thinkingOutputTokens || 0);
            const cacheTok = Number(rs.cache_read_tokens || gmUsage.cacheReadTokens || 0);
            const hasAuthUsage = inTok > 0 || outTok > 0 || cacheTok > 0;

            const approxTok = cortexType === "CHECKPOINT"
                ? Math.max(1, Math.round(String(extraFields.compaction_summary || rs.content || "").length / 3.5))
                : Math.max(1, Math.round((JSON.stringify(rs).length || 100) / 3.5));
            const stepTokens = hasAuthUsage ? (outTok > 0 ? outTok : inTok) : (rs.tokens || approxTok);

            if (cortexType === "CHECKPOINT") {
                cumulativeTokens = stepTokens;
            } else if (stepTokens > 0) {
                cumulativeTokens += stepTokens;
            }

            const thinkingDurationMs = rs.thinking_duration_ms || (rs.thinkingDuration ? ((rs.thinkingDuration.seconds || 0) * 1000 + ((rs.thinkingDuration.nanos || 0) / 1e6)) : 0);
            const streamingDurationMs = rs.streaming_duration_ms || (rs.streamingDuration ? ((rs.streamingDuration.seconds || 0) * 1000 + ((rs.streamingDuration.nanos || 0) / 1e6)) : 0);
            const totalDurationMs = thinkingDurationMs + streamingDurationMs;

            return Object.assign({
                step_index: stepIdx, type: cortexType, status: rs.status || "STATUS_COMPLETED",
                content: rs.content || rs.text || "", thinking: rs.thinking || rs.reasoning || "",
                tool_calls: rs.tool_calls || rs.toolCalls || [], timestamp_ms: tsMs,
                created_at: rs.created_at || (tsMs ? new Date(tsMs).toISOString() : null),
                tokens: stepTokens, cumulative_tokens: cumulativeTokens,
                input_tokens: inTok, output_tokens: outTok, thinking_tokens: thinkTok, cache_read_tokens: cacheTok,
                size_bytes: JSON.stringify(rs).length, thinking_duration_ms: thinkingDurationMs,
                streaming_duration_ms: streamingDurationMs, total_duration_ms: totalDurationMs,
                response_model: rs.response_model || (gm && gm.model) || "",
                generator_metadata: gm, executor_metadata: em, _hasAuthUsage: hasAuthUsage,
            }, extraFields);
        });

        // Extract latest Context Window Metadata & TokenBreakdown via reverse scan (newest wins)
        const resolvedModelName = (chatModelData && chatModelData.model) || (steps.slice().reverse().find(s => s.response_model)?.response_model) || "";
        let maxContextTokens = 0, activeTokenBreakdown = null, foundMaxContext = false, latestEstimatedTokens = 0;
        const extractCwmFromObj = (obj) => {
            for (const cwm of _cwmList(obj)) {
                if (!cwm || typeof cwm !== "object") continue;
                if ((cwm.estimatedTokensUsed || cwm.estimated_tokens_used) && !latestEstimatedTokens) {
                    const est = parseInt(cwm.estimatedTokensUsed || cwm.estimated_tokens_used, 10) || 0;
                    if (est > 0) latestEstimatedTokens = est;
                }
                if ((cwm.maxContextTokens || cwm.max_context_tokens || cwm.maxTokens) && !foundMaxContext) {
                    const mct = parseInt(cwm.maxContextTokens || cwm.max_context_tokens || cwm.maxTokens, 10) || 0;
                    if (mct > 0) { maxContextTokens = mct; foundMaxContext = true; }
                }
                if (cwm.tokenBreakdown && !activeTokenBreakdown) activeTokenBreakdown = cwm.tokenBreakdown;
            }
        };
        for (let i = genMetas.length - 1; i >= 0; i--) {
            extractCwmFromObj(genMetas[i]);
            if (latestEstimatedTokens > 0 && foundMaxContext && activeTokenBreakdown) break;
        }
        if (!foundMaxContext || latestEstimatedTokens === 0 || !activeTokenBreakdown) {
            for (let i = orderedRaw.length - 1; i >= 0; i--) {
                extractCwmFromObj(orderedRaw[i]);
                if (latestEstimatedTokens > 0 && foundMaxContext && activeTokenBreakdown) break;
            }
        }
        if (!foundMaxContext || maxContextTokens <= 0) maxContextTokens = inferModelContextWindow(resolvedModelName);

        const extractEstFromObj = (obj) => {
            for (const cwm of _cwmList(obj)) {
                if (cwm && typeof cwm === "object" && (cwm.estimatedTokensUsed || cwm.estimated_tokens_used)) {
                    const est = parseInt(cwm.estimatedTokensUsed || cwm.estimated_tokens_used, 10) || 0;
                    if (est > 0) return est;
                }
            }
            return 0;
        };

        // Slice attributions
        const { systemPromptSlices, toolDefSlices } = extractProtobufBreakdownSlices(activeTokenBreakdown, chatModelData, genMetas);
        const sysPromptTok = systemPromptSlices.reduce((acc, s) => acc + (s.tokens || 0), 0);
        const toolDefsTok = toolDefSlices.reduce((acc, s) => acc + (s.tokens || 0), 0);

        // Calculate checkpoint windows based on CHECKPOINT steps (Option B disjoint partitioning)
        const cpIndices = [];
        steps.forEach((s, i) => {
            if (s.type === "CHECKPOINT" || Boolean(orderedRaw[i] && orderedRaw[i].checkpoint)) {
                cpIndices.push(i);
            }
        });

        const checkpoints = [];
        if (cpIndices.length === 0) {
            if (steps.length > 0) {
                checkpoints.push({
                    checkpoint_index: 0, start_index: 0, end_index: steps.length - 1,
                    step_count: steps.length, has_checkpoint: false, summary: "Initial Trajectory",
                });
            }
        } else {
            const c0 = cpIndices[0];
            if (c0 > 0) {
                checkpoints.push({
                    checkpoint_index: 0, start_index: 0, end_index: c0 - 1,
                    step_count: c0, has_checkpoint: false, summary: "Initial Trajectory",
                });
            }
            for (let k = 0; k < cpIndices.length; k++) {
                const curCp = cpIndices[k];
                const endIdx = (k + 1 < cpIndices.length) ? (cpIndices[k + 1] - 1) : (steps.length - 1);
                if (endIdx >= curCp) {
                    checkpoints.push({
                        checkpoint_index: checkpoints.length,
                        start_index: curCp,
                        end_index: endIdx,
                        step_count: endIdx - curCp + 1,
                        has_checkpoint: true,
                        summary: steps[curCp].compaction_summary || steps[curCp].sessionSummary || `Checkpoint #${curCp}`,
                    });
                }
            }
        }

        const computeCheckpointMetrics = (cpSteps, cpStart, isLastWindow) => {
            let explicitUsageTokens = 0;
            let cpCacheTokens = 0;
            let cpEstTokens = 0;
            const cpStepIndices = new Set(cpSteps.map(s => s.step_index));
            for (let i = cpSteps.length - 1; i >= 0; i--) {
                const st = cpSteps[i];
                if (st.type === "CHECKPOINT") continue;
                if (cpCacheTokens === 0 && st.cache_read_tokens > 0) cpCacheTokens = st.cache_read_tokens;
                if (explicitUsageTokens === 0 && st._hasAuthUsage) {
                    explicitUsageTokens = st.input_tokens + st.cache_read_tokens;
                }
                if (cpEstTokens === 0) {
                    cpEstTokens = extractEstFromObj(st.generator_metadata) || extractEstFromObj(orderedRaw[cpStart + i]);
                }
            }
            if (cpEstTokens === 0) {
                for (let gIdx = genMetas.length - 1; gIdx >= 0; gIdx--) {
                    const gm = genMetas[gIdx];
                    const gmIndices = [];
                    if (gm && gm.stepIndex !== undefined && gm.stepIndex !== null) gmIndices.push(gm.stepIndex);
                    if (gm && Array.isArray(gm.stepIndices)) gmIndices.push(...gm.stepIndices);
                    if (gmIndices.some(si => cpStepIndices.has(si))) {
                        cpEstTokens = extractEstFromObj(gm);
                        if (cpEstTokens > 0) break;
                    }
                }
            }
            if (isLastWindow && cpEstTokens === 0) cpEstTokens = latestEstimatedTokens;

            let actualUserTok = 0, actualModelTok = 0, actualThoughtTok = 0, actualToolTok = 0, actualCheckpointTok = 0, actualSystemTok = 0;
            cpSteps.forEach(s => {
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
            const cpTotalTokens = explicitUsageTokens > 0
                ? explicitUsageTokens
                : (cpEstTokens > 0 ? Math.max(cpEstTokens, activeMeasuredSum) : activeMeasuredSum);
            const cpIsProvisional = (explicitUsageTokens === 0) && (cpTotalTokens > 0);
            const cpUnattrTok = Math.max(0, cpTotalTokens - activeMeasuredSum);
            return {
                total_tokens: cpTotalTokens, unattributed: cpUnattrTok, cache_tokens: cpCacheTokens, is_provisional: cpIsProvisional,
                utilization_pct: maxContextTokens > 0 ? Math.round(Math.min(100, (cpTotalTokens / maxContextTokens) * 1000)) / 10 : 0,
                token_breakdown: { system_prompt: sysPromptTok, tool_defs: toolDefsTok, checkpoint: actualCheckpointTok, user: actualUserTok, model: actualModelTok, thought: actualThoughtTok, tool: actualToolTok, system: actualSystemTok, unattributed: cpUnattrTok },
            };
        };

        checkpoints.forEach((cp, cIdx) => Object.assign(cp, computeCheckpointMetrics(steps.slice(cp.start_index, cp.end_index + 1), cp.start_index, cIdx === checkpoints.length - 1)));

        const lastCheckpoint = checkpoints.length > 0 ? checkpoints[checkpoints.length - 1] : null;
        const latestMetrics = lastCheckpoint || computeCheckpointMetrics(steps, 0, true);
        const { total_tokens: totalTokens, cache_tokens: cacheTokens, is_provisional: isProvisional, token_breakdown: ssotBreakdown } = latestMetrics;

        // Extract subagents
        const subagents = [], subagentInfos = [];
        const subUuidRe = /[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}/g;
        const addSubagent = (uid, name, summary) => {
            const cleanUid = String(uid || "").trim();
            if (!cleanUid || cleanUid === convoId || subagents.includes(cleanUid)) return;
            subagents.push(cleanUid);
            subagentInfos.push({ id: cleanUid, name: name || `Subagent ${cleanUid.slice(0, 8)}`, summary: String(summary || "").slice(0, 80) });
        };

        steps.forEach(s => {
            if (s.subagent && (s.subagent.conversationId || s.subagent.id)) addSubagent(s.subagent.conversationId || s.subagent.id, s.subagent.role || s.subagent.name, s.subagent.objective);
            (s.tool_calls || []).forEach(tc => {
                const tcName = String(tc.name || "").toLowerCase();
                if (!["invoke_subagent", "send_message", "swarm", "define_subagent", "post_message"].includes(tcName)) return;
                const args = (tc.args && typeof tc.args === "object") ? tc.args : {};
                const outCombined = `${JSON.stringify(args)} ${String(tc.output || tc.result || "")}`;
                (outCombined.match(subUuidRe) || []).forEach(uid => addSubagent(uid, args.TypeName || args.Role || args.name, args.Prompt || args.brief || args.objective));
            });
        });

        let convoSummary = `Session ${convoId.slice(0, 8)}`;
        const firstUserStep = steps.find(s => s.type === "USER_INPUT");
        if (firstUserStep && firstUserStep.content) convoSummary = String(firstUserStep.content).trim().split(/\r?\n/)[0].slice(0, 70);

        let parentId = null;
        if (typeof window !== "undefined" && window.location) {
            const searchParams = window.location.search ? new URLSearchParams(window.location.search) : null;
            const tabParam = searchParams ? searchParams.get('tab') : null;
            const focusedParam = searchParams ? searchParams.get('focused') : null;
            const pathMatch = window.location.pathname ? window.location.pathname.match(/\/c\/([^/?#]+)/) : null;
            const paneIds = pathMatch && pathMatch[1] ? pathMatch[1].split("+").filter(Boolean) : [];
            if (paneIds.length > 0) {
                const primaryId = paneIds[0];
                if (tabParam && tabParam.startsWith('subagent_convo__') && tabParam.slice('subagent_convo__'.length) === convoId && primaryId !== convoId) parentId = primaryId;
                else if (!tabParam && !focusedParam && paneIds.length === 1 && primaryId !== convoId) parentId = primaryId;
            }
        }

        const checkpointSteps = cpIndices.length > 0 ? steps.length - cpIndices[cpIndices.length - 1] : steps.length;
        return {
            conversation_id: convoId, summary: convoSummary, model: resolvedModelName, steps, step_count: steps.length,
            checkpoints, checkpoint_index: checkpoints.length > 0 ? checkpoints.length - 1 : 0,
            checkpoint_steps: checkpointSteps, checkpoint_count: cpIndices.length,
            parent_id: parentId, subagents, subagent_infos: subagentInfos, subagent_trajectories: {},
            total_tokens: totalTokens, max_context_tokens: maxContextTokens, cache_tokens: cacheTokens, is_provisional: isProvisional,
            burn_rate_tokens_per_min: 0, token_breakdown: ssotBreakdown, system_prompt_slices: systemPromptSlices, tool_def_slices: toolDefSlices,
        };
    }

    /** ConnectRPC conversation loader with pagination and strict same-session fallback ladder. */
    async function loadConversationViaRpc(convoId) {
        if (!convoId) return null;
        try {
            const { baseUrl, csrfToken, trajectoryServerUrl } = typeof global.resolveRpcEndpoint === "function"
                ? global.resolveRpcEndpoint()
                : { baseUrl: "https://127.0.0.1:40623", csrfToken: "", trajectoryServerUrl: "http://127.0.0.1:40624" };

            const headers = { "Content-Type": "application/json", "Connect-Protocol-Version": "1" };
            if (csrfToken) headers["x-codeium-csrf-token"] = csrfToken;

            const safePost = async (url, bodyObj, optional) => {
                try {
                    const r = await fetch(url, { method: "POST", headers, body: JSON.stringify(bodyObj) });
                    if (!r.ok && !optional) console.warn(`[agyis] ConnectRPC HTTP ${r.status}: ${url}`);
                    return r;
                } catch (err) {
                    if (!optional) console.warn(`[agyis] ConnectRPC error (${url}):`, err && err.message ? err.message : err);
                    return null;
                }
            };
            const baseReq = { cascadeId: convoId, trajectoryVerbosity: 3 };
            const rpcRoot = `${baseUrl}/exa.language_server_pb.`;
            const [trajRes, stepsRes, genRes, execRes] = await Promise.all([
                safePost(`${rpcRoot}LanguageServerService/GetCascadeTrajectory`, baseReq),
                safePost(`${rpcRoot}LanguageServerService/GetCascadeTrajectorySteps`, { ...baseReq, stepOffset: 0 }),
                safePost(`${rpcRoot}LanguageServerService/GetCascadeTrajectoryGeneratorMetadata`, { ...baseReq, generatorMetadataOffset: 0 }),
                safePost(`${rpcRoot}LanguageServerService/GetCascadeTrajectoryExecutorMetadatas`, baseReq, true).catch(() => null),
            ]);
            let rawSteps = null;
            if (stepsRes && stepsRes.ok) {
                const stepsJson = await stepsRes.json().catch(() => null);
                if (stepsJson && Array.isArray(stepsJson.steps)) {
                    rawSteps = stepsJson.steps.slice();
                    let totalLen = Number(stepsJson.totalLength || stepsJson.totalSteps || 0);
                    let nextIdx = rawSteps.length, lastPageLen = rawSteps.length;
                    while (((totalLen > nextIdx) || (totalLen === 0 && lastPageLen >= 500)) && nextIdx > 0 && nextIdx < 20000) {
                        const pageRes = await safePost(`${rpcRoot}LanguageServerService/GetCascadeTrajectorySteps`, { cascadeId: convoId, trajectoryVerbosity: 3, stepOffset: nextIdx });
                        if (!pageRes || !pageRes.ok) break;
                        const pageJson = await pageRes.json().catch(() => null);
                        const pageSteps = pageJson && Array.isArray(pageJson.steps) ? pageJson.steps : [];
                        if (pageSteps.length === 0 || (totalLen === 0 && pageSteps[0] && pageSteps[0].stepIndex !== undefined && pageSteps[0].stepIndex < nextIdx)) break;
                        rawSteps.push(...pageSteps);
                        lastPageLen = pageSteps.length;
                        nextIdx += pageSteps.length;
                        if (pageJson && (pageJson.totalLength || pageJson.totalSteps)) totalLen = Number(pageJson.totalLength || pageJson.totalSteps);
                    }
                }
            }
            if (!rawSteps && trajRes && trajRes.ok) {
                const trajJson = await trajRes.json().catch(() => null);
                if (trajJson && trajJson.trajectory && Array.isArray(trajJson.trajectory.steps)) rawSteps = trajJson.trajectory.steps;
            }
            if (!rawSteps || rawSteps.length === 0) {
                const encId = encodeURIComponent(convoId);
                let localHttpRes = await fetch(`${trajectoryServerUrl}/api/trajectory?id=${encId}`).catch(() => null);
                if (!localHttpRes || !localHttpRes.ok) localHttpRes = await fetch(`${trajectoryServerUrl}/api/trajectory/${encId}`).catch(() => null);
                if (localHttpRes && localHttpRes.ok) {
                    const localData = await localHttpRes.json().catch(() => null);
                    if (localData && localData.steps) return localData;
                }
                if (typeof __PAYLOAD__ !== "undefined" && __PAYLOAD__ && __PAYLOAD__.initialData && __PAYLOAD__.initialData.conversation_id === convoId) return __PAYLOAD__.initialData;
                return null;
            }
            const genJson = (genRes && genRes.ok) ? await genRes.json().catch(() => null) : null;
            const genMetas = ((genJson && (genJson.generatorMetadata || genJson.generatorMetadatas || genJson.metadatas)) || []).slice();
            let totalGenLen = Number((genJson && (genJson.totalLength || genJson.totalCount || genJson.totalMetadataCount)) || 0);
            let genOffset = genMetas.length, lastGenLen = genMetas.length;
            while (((totalGenLen > genOffset) || (totalGenLen === 0 && lastGenLen >= 500)) && genOffset > 0 && genOffset < 20000) {
                const gRes = await safePost(`${rpcRoot}LanguageServerService/GetCascadeTrajectoryGeneratorMetadata`, { cascadeId: convoId, trajectoryVerbosity: 3, generatorMetadataOffset: genOffset });
                if (!gRes || !gRes.ok) break;
                const gJson = await gRes.json().catch(() => null);
                const pageGen = (gJson && (gJson.generatorMetadata || gJson.generatorMetadatas || gJson.metadatas)) || [];
                if (!Array.isArray(pageGen) || pageGen.length === 0) break;
                genMetas.push(...pageGen);
                lastGenLen = pageGen.length;
                genOffset += pageGen.length;
                if (gJson && (gJson.totalLength || gJson.totalCount || gJson.totalMetadataCount)) totalGenLen = Number(gJson.totalLength || gJson.totalCount || gJson.totalMetadataCount);
            }
            const chatModelData = (genJson && (genJson.chatModel || (genMetas[0] && genMetas[0].chatModel))) || null;
            const execJson = (execRes && execRes.ok) ? await execRes.json().catch(() => null) : null;
            const execMetas = (execJson && (execJson.executorMetadata || execJson.executorMetadatas || execJson.metadatas)) || [];
            return buildHudTrajectoryData(convoId, rawSteps, genMetas, execMetas, chatModelData);
        } catch (err) {
            console.warn("[agyis] ConnectRPC trajectory fetch failed:", err);
            const fallbackData = typeof __PAYLOAD__ !== "undefined" && __PAYLOAD__ && __PAYLOAD__.initialData;
            return (fallbackData && fallbackData.conversation_id === convoId) ? fallbackData : null;
        }
    }

    Object.assign(global, { buildHudTrajectoryData, extractProtobufBreakdownSlices, loadConversationViaRpc });
})(typeof window !== "undefined" ? window : globalThis);
