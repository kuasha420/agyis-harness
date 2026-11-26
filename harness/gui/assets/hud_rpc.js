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
            let cortexType = rs.type || rs.stepType || "STEP";
            if (cortexType === 132 || cortexType === "132") {
                cortexType = "GENERIC";
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

            const tsMs = parseStepTimestampMs(rs, gm, em);
            const gmUsage = (gm && gm.usage) || (rs.metadata && rs.metadata.modelUsage) || {};

            const inTok = Number(rs.input_tokens || gmUsage.inputTokens || 0);
            const outTok = Number(rs.output_tokens || gmUsage.outputTokens || 0);
            const thinkTok = Number(rs.thinking_tokens || gmUsage.thinkingOutputTokens || 0);
            const cacheTok = Number(rs.cache_read_tokens || gmUsage.cacheReadTokens || 0);
            const hasAuthUsage = inTok > 0 || outTok > 0 || cacheTok > 0;

            const approxTok = Math.max(1, Math.round((JSON.stringify(rs).length || 100) / 3.5));
            const stepTokens = hasAuthUsage ? (outTok > 0 ? outTok : inTok) : (rs.tokens || approxTok);

            cumulativeTokens += stepTokens;

            const thinkingDurationMs = rs.thinking_duration_ms || (rs.thinkingDuration ? ((rs.thinkingDuration.seconds || 0) * 1000 + ((rs.thinkingDuration.nanos || 0) / 1e6)) : 0);
            const streamingDurationMs = rs.streaming_duration_ms || (rs.streamingDuration ? ((rs.streamingDuration.seconds || 0) * 1000 + ((rs.streamingDuration.nanos || 0) / 1e6)) : 0);
            const totalDurationMs = thinkingDurationMs + streamingDurationMs;

            const extraFields = {};
            if (rs.runCommand) Object.assign(extraFields, { command: rs.runCommand.commandLine || "", exitCode: rs.runCommand.exitCode, output: (rs.runCommand.combinedOutput && rs.runCommand.combinedOutput.full) || "", cwd: rs.runCommand.cwd || "" });
            if (rs.viewFile) Object.assign(extraFields, { filePath: rs.viewFile.absolutePathUri || "", fileContent: rs.viewFile.content || "", endLine: rs.viewFile.endLine });
            if (rs.codeAction) {
                const actSpec = rs.codeAction.actionSpec || {};
                extraFields.diffLines = (rs.codeAction.actionResult?.edit?.diff?.unifiedDiff?.lines) || [];
                extraFields.filePath = actSpec.createFile?.path?.absoluteUri || actSpec.editFile?.path?.absoluteUri || "";
            }
            if (rs.invokeSubagent) extraFields.subagent = (rs.invokeSubagent.subagents && rs.invokeSubagent.subagents[0]) || null;
            if (rs.checkpoint) Object.assign(extraFields, { sessionSummary: rs.checkpoint.sessionSummary || "", checkpoint_index: rs.checkpoint.checkpointIndex });
            if (rs.generic) {
                extraFields.generic = rs.generic;
                if (rs.generic.toolName) extraFields.toolName = rs.generic.toolName;
                if (rs.generic.output !== undefined) extraFields.output = rs.generic.output;
            }

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

        // Calculate epochs based on CHECKPOINT steps
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

        const computeEpochMetrics = (epSteps, epStart, epEnd, isLastEpoch) => {
            let explicitUsageTokens = 0;
            let epochCacheTokens = 0;
            let epochEstTokens = 0;
            for (let i = epSteps.length - 1; i >= 0; i--) {
                const st = epSteps[i];
                if (st.type === "CHECKPOINT") continue;
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

            let actualUserTok = 0, actualModelTok = 0, actualThoughtTok = 0, actualToolTok = 0, actualCheckpointTok = 0, actualSystemTok = 0;
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
            const epTotalTokens = explicitUsageTokens > 0
                ? explicitUsageTokens
                : (epochEstTokens > 0 ? Math.max(epochEstTokens, activeMeasuredSum) : activeMeasuredSum);
            const epIsProvisional = (explicitUsageTokens === 0) && (epTotalTokens > 0);
            const epUnattrTok = Math.max(0, epTotalTokens - activeMeasuredSum);
            return {
                total_tokens: epTotalTokens, unattributed: epUnattrTok, cache_tokens: epochCacheTokens, is_provisional: epIsProvisional,
                token_breakdown: { system_prompt: sysPromptTok, tool_defs: toolDefsTok, checkpoint: actualCheckpointTok, user: actualUserTok, model: actualModelTok, thought: actualThoughtTok, tool: actualToolTok, system: actualSystemTok, unattributed: epUnattrTok },
            };
        };

        epochs.forEach((ep, eIdx) => Object.assign(ep, computeEpochMetrics(steps.slice(ep.start_index, ep.end_index + 1), ep.start_index, ep.end_index, eIdx === epochs.length - 1)));

        const lastEpoch = epochs.length > 0 ? epochs[epochs.length - 1] : null;
        const latestMetrics = lastEpoch || computeEpochMetrics(steps, 0, Math.max(0, steps.length - 1), true);
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

        return {
            conversation_id: convoId, summary: convoSummary, model: resolvedModelName, steps, step_count: steps.length,
            epochs, parent_id: parentId, subagents, subagent_infos: subagentInfos, subagent_trajectories: {},
            total_tokens: totalTokens, max_context_tokens: maxContextTokens, cache_tokens: cacheTokens, is_provisional: isProvisional,
            burn_rate_tokens_per_min: 0, token_breakdown: ssotBreakdown, system_prompt_slices: systemPromptSlices, tool_def_slices: toolDefSlices,
        };
    }

    const MAX_PENDING_DELTAS = 256;
    const MAX_STREAM_SLICE = 2000;

    function _writeBoundedSlice(arr, idx, val, offsetKey, stateObj) {
        if (!Number.isInteger(idx) || idx < 0) return;
        const offset = stateObj[offsetKey] || 0;
        if (idx < offset) return;
        const rel = idx - offset;
        if (rel >= MAX_STREAM_SLICE) {
            const shift = rel - MAX_STREAM_SLICE + 1;
            arr.splice(0, Math.min(arr.length, shift));
            stateObj[offsetKey] = offset + shift;
        }
        arr[idx - (stateObj[offsetKey] || 0)] = val;
    }

    /**
     * 60 FPS Jitter-Free StreamRenderCoordinator (Strand 2 Architecture).
     * Decouples network delta ingress (20-60Hz) from DOM mutations via a bounded queue,
     * reconciling updates into a unified state and triggering a single render pass per 16.6ms frame.
     */
    class StreamRenderCoordinator {
        constructor(renderCallback) {
            this._renderCallback = renderCallback;
            this._pendingDeltas = [];
            this._rafId = null;
            this._rafKind = null;
            this._state = {
                conversationId: "", trajectoryId: "", stepsInSlice: [], generatorMetadatasInSlice: [], executorMetadatasInSlice: [],
                _stepsOffset: 0, _genOffset: 0, _execOffset: 0, totalStepsLength: 0, activeTokens: 0, maxContextTokens: 0, tokenBreakdown: null, isStreaming: false,
            };
            this._dirty = { steps: false, tokens: false, timeline: false };
        }

        destroy() {
            if (this._rafId !== null) {
                if (this._rafKind === "raf" && typeof cancelAnimationFrame === "function") cancelAnimationFrame(this._rafId);
                else clearTimeout(this._rafId);
                this._rafId = null;
                this._rafKind = null;
            }
            this._pendingDeltas.length = 0;
        }

        ingestUpdate(update) {
            if (!update) return;
            while (this._pendingDeltas.length >= MAX_PENDING_DELTAS) this._reconcileUpdate(this._pendingDeltas.shift());
            this._pendingDeltas.push(update);
            if (!this._rafId && typeof requestAnimationFrame !== "undefined") {
                this._rafKind = "raf";
                this._rafId = requestAnimationFrame(this._flushAndRender.bind(this));
            } else if (!this._rafId) {
                this._rafKind = "timeout";
                this._rafId = setTimeout(this._flushAndRender.bind(this), 16);
            }
        }

        _flushAndRender() {
            this._rafId = null;
            this._rafKind = null;
            if (this._pendingDeltas.length === 0) return;
            while (this._pendingDeltas.length > 0) this._reconcileUpdate(this._pendingDeltas.shift());
            if (this._dirty.steps || this._dirty.tokens || this._dirty.timeline) {
                if (typeof this._renderCallback === "function") this._renderCallback(this._state, this._dirty);
                this._dirty.steps = this._dirty.tokens = this._dirty.timeline = false;
            }
        }

        _reconcileUpdate(update) {
            if (!update) return;
            this._state.conversationId = update.conversationId || this._state.conversationId;
            this._state.trajectoryId = update.trajectoryId || this._state.trajectoryId;
            if (update.contextWindowUsage) {
                const cwu = update.contextWindowUsage;
                if (cwu.estimatedTokensUsed !== undefined) { this._state.activeTokens = cwu.estimatedTokensUsed; this._dirty.tokens = true; }
                if (cwu.maxContextTokens !== undefined) { this._state.maxContextTokens = cwu.maxContextTokens; this._dirty.tokens = true; }
                if (cwu.tokenGroups) { this._state.tokenBreakdown = { groups: cwu.tokenGroups }; this._dirty.tokens = true; }
            }
            const mtu = update.mainTrajectoryUpdate;
            if (!mtu) return;
            if (mtu.stepsUpdate) {
                const { indices, steps, totalLength } = mtu.stepsUpdate;
                if (indices && steps) {
                    for (let i = 0; i < indices.length; i++) _writeBoundedSlice(this._state.stepsInSlice, indices[i], steps[i], "_stepsOffset", this._state);
                    this._dirty.steps = this._dirty.timeline = true;
                }
                if (totalLength !== undefined) this._state.totalStepsLength = totalLength;
            }
            if (mtu.generatorMetadatasUpdate) {
                const { indices, generatorMetadatas } = mtu.generatorMetadatasUpdate;
                if (indices && generatorMetadatas) {
                    for (let i = 0; i < indices.length; i++) {
                        const gm = generatorMetadatas[i];
                        _writeBoundedSlice(this._state.generatorMetadatasInSlice, indices[i], gm, "_genOffset", this._state);
                        const cwm = gm?.chatModel?.chatStartMetadata?.contextWindowMetadata;
                        if (cwm) {
                            this._state.activeTokens = cwm.estimatedTokensUsed || this._state.activeTokens;
                            if (cwm.maxContextTokens || cwm.maxTokens) this._state.maxContextTokens = cwm.maxContextTokens || cwm.maxTokens;
                            if (cwm.tokenBreakdown) { this._state.tokenBreakdown = cwm.tokenBreakdown; this._dirty.tokens = true; }
                        }
                    }
                }
            }
            if (mtu.executorMetadatasUpdate) {
                const { indices, executorMetadatas, executorMetadata } = mtu.executorMetadatasUpdate;
                const execList = executorMetadatas || executorMetadata;
                if (indices && execList) {
                    for (let i = 0; i < indices.length; i++) _writeBoundedSlice(this._state.executorMetadatasInSlice, indices[i], execList[i], "_execOffset", this._state);
                    this._dirty.steps = true;
                }
            }
        }
    }

    /**
     * Resolves ConnectRPC endpoint (port, baseUrl, csrfToken, trajectoryServerUrl) from options, payloads, or window environment.
     */
    function resolveRpcEndpoint(options = {}) {
        const loc = typeof window !== "undefined" ? window.location : null;
        const isLoopback = !!(loc && (loc.hostname === "127.0.0.1" || loc.hostname === "localhost" || (loc.origin && (loc.origin.includes("127.0.0.1") || loc.origin.includes("localhost")))));
        const isHttps = !!(loc && loc.protocol === "https:");
        const locPort = (isHttps && isLoopback && loc.port) ? parseInt(loc.port, 10) : (isHttps && isLoopback && loc.origin && loc.origin.match(/:(\d+)/) ? parseInt(loc.origin.match(/:(\d+)/)[1], 10) : null);
        const appCfg = typeof window !== "undefined" && window.__APP_CONFIG__;
        const payload = typeof __PAYLOAD__ !== "undefined" ? __PAYLOAD__ : null;
        const port = options.port || (payload && payload.connectRpcPort) || (typeof window !== "undefined" && window.__AGYIS_CONNECT_PORT__) || (appCfg && appCfg.connectRpcPort) || locPort || 40623;
        const dynamicUrl = options.baseUrl || (payload && payload.connectRpcUrl) || (typeof window !== "undefined" && window.__AGYIS_CONNECT_URL__) || (appCfg && appCfg.connectRpcUrl);
        const proto = (loc && loc.protocol === "http:") ? "http:" : "https:";
        const fallbackOrigin = (isHttps && isLoopback && loc && loc.origin && loc.origin.startsWith("http")) ? loc.origin : null;
        const baseUrl = dynamicUrl || fallbackOrigin || (loc && loc.origin && loc.origin.startsWith("http") ? loc.origin : `${proto}//127.0.0.1:${port}`);
        const trajectoryServerUrl = options.trajectoryServerUrl
            || (payload && payload.trajectoryServerUrl)
            || (typeof window !== "undefined" && window.__AGYIS_TRAJECTORY_URL__)
            || `http://127.0.0.1:${options.httpPort || (payload && payload.trajectoryServerPort) || 40624}`;
        let sessionCsrf = "";
        try {
            if (typeof localStorage !== "undefined" && localStorage && typeof localStorage.getItem === "function") {
                sessionCsrf = localStorage.getItem("agy_session_csrf_token") || "";
            }
        } catch (_) {}
        const csrfToken = options.csrfToken || (appCfg && appCfg.csrfToken) || sessionCsrf || "";
        return { port, baseUrl, csrfToken, trajectoryServerUrl };
    }

    /**
     * In-Situ ConnectRPC Streaming & Unary Client.
     * Enforces Connect envelope framing (flags: uint8 + length: uint32be) and CSRF protection.
     */
    class InSituConnectClient {
        constructor(options = {}) {
            const ep = resolveRpcEndpoint(options);
            this.port = ep.port;
            this.baseUrl = ep.baseUrl;
            this.csrfToken = ep.csrfToken;
            this.trajectoryServerUrl = ep.trajectoryServerUrl;
            this.activeAbortController = null;
            this.activeCoordinator = null;
        }

        async _fetchRemainingStreamSlice(conversationId, coordinator, startIndex, totalLength, signal) {
            const headers = { "Content-Type": "application/json", "Connect-Protocol-Version": "1" };
            if (this.csrfToken) headers["x-codeium-csrf-token"] = this.csrfToken;
            let cursor = startIndex;
            while (cursor < totalLength && cursor < 20000) {
                if (signal && signal.aborted) break;
                const body = JSON.stringify({ cascadeId: conversationId, trajectoryVerbosity: 3, stepOffset: cursor });
                const res = await fetch(`${this.baseUrl}/exa.language_server_pb.LanguageServerService/GetCascadeTrajectorySteps`, { method: "POST", headers, body, signal }).catch(() => null);
                if (!res || !res.ok) break;
                const data = await res.json().catch(() => null);
                const pageSteps = data && Array.isArray(data.steps) ? data.steps : [];
                if (pageSteps.length === 0) break;
                if (pageSteps[0] && pageSteps[0].stepIndex !== undefined && pageSteps[0].stepIndex < cursor) break;
                const indices = pageSteps.map((s, idx) => (s && s.stepIndex !== undefined ? s.stepIndex : cursor + idx));
                coordinator.ingestUpdate({ conversationId, mainTrajectoryUpdate: { stepsUpdate: { indices, steps: pageSteps, totalLength } } });
                cursor += pageSteps.length;
            }
        }

        /** Connects to StreamAgentStateUpdates over persistent HTTP/2 Connect streaming. */
        async streamConversation(conversationId, onStateChange) {
            if (this.activeAbortController) this.activeAbortController.abort("Switching conversation");
            if (this.activeCoordinator) this.activeCoordinator.destroy();
            this.activeAbortController = new AbortController();
            const signal = this.activeAbortController.signal;
            const coordinator = new StreamRenderCoordinator(onStateChange);
            this.activeCoordinator = coordinator;
            const subscriberId = (typeof crypto !== "undefined" && crypto.randomUUID) ? crypto.randomUUID() : `sub-${Date.now()}`;
            const reqBody = {
                conversationId, subscriberId, trajectoryVerbosity: 3,
                initialStepsPageBounds: { startIndex: 0, endIndexExclusive: 500 },
                initialGeneratorMetadatasPageBounds: { startIndex: 0, endIndexExclusive: 500 },
                initialExecutorMetadatasPageBounds: { startIndex: 0, endIndexExclusive: 500 },
            };
            const jsonBytes = new TextEncoder().encode(JSON.stringify(reqBody));
            const framedReq = new Uint8Array(5 + jsonBytes.length);
            framedReq[0] = 0x00;
            new DataView(framedReq.buffer).setUint32(1, jsonBytes.length, false);
            framedReq.set(jsonBytes, 5);
            const url = `${this.baseUrl}/exa.language_server_pb.LanguageServerService/StreamAgentStateUpdates`;
            const headers = { "Content-Type": "application/connect+json", "Connect-Protocol-Version": "1" };
            if (this.csrfToken) headers["x-codeium-csrf-token"] = this.csrfToken;
            const response = await fetch(url, { method: "POST", headers, body: framedReq, signal });
            if (!response.ok) throw new Error(`ConnectRPC stream failed with HTTP ${response.status}`);
            const reader = response.body.getReader();
            let buffer = new Uint8Array(0), paginatedTail = false;
            while (true) {
                const { done, value } = await reader.read();
                if (done) break;
                const newBuf = new Uint8Array(buffer.length + value.length);
                newBuf.set(buffer);
                newBuf.set(value, buffer.length);
                buffer = newBuf;
                while (buffer.length >= 5) {
                    const flags = buffer[0];
                    const length = new DataView(buffer.buffer, buffer.byteOffset, 5).getUint32(1, false);
                    if (buffer.length < 5 + length) break;
                    const payloadBytes = buffer.slice(5, 5 + length);
                    const rest = buffer.subarray(5 + length);
                    buffer = rest.length > 0 ? new Uint8Array(rest) : new Uint8Array(0);
                    if (flags === 0x00) {
                        try {
                            const message = JSON.parse(new TextDecoder().decode(payloadBytes));
                            if (message.update) {
                                coordinator.ingestUpdate(message.update);
                                const totalLen = message.update.mainTrajectoryUpdate?.stepsUpdate?.totalLength;
                                if (!paginatedTail && Number.isFinite(totalLen) && totalLen > 500) {
                                    paginatedTail = true;
                                    this._fetchRemainingStreamSlice(conversationId, coordinator, 500, totalLen, signal).catch(err => console.warn("[InSituConnectClient] Paginated tail fetch failed:", err));
                                }
                            }
                        } catch (e) { console.error("[InSituConnectClient] JSON decode error:", e); }
                    } else if (flags === 0x02) {
                        const endStr = new TextDecoder().decode(payloadBytes);
                        let endMsg = null;
                        try { endMsg = endStr ? JSON.parse(endStr) : null; }
                        catch (_) { console.warn("[InSituConnectClient] Invalid EndStreamResponse JSON:", endStr); }
                        if (endMsg && endMsg.error) throw new Error(`ConnectRPC stream ended with error: ${endMsg.error.message || endMsg.error.code || JSON.stringify(endMsg.error)}`);
                        return;
                    }
                }
            }
        }
    }

    /** ConnectRPC conversation loader with pagination and strict same-session fallback ladder. */
    async function loadConversationViaRpc(convoId) {
        if (!convoId) return null;
        try {
            const { baseUrl, csrfToken, trajectoryServerUrl } = resolveRpcEndpoint();

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
            if (typeof __PAYLOAD__ !== "undefined" && __PAYLOAD__ && __PAYLOAD__.initialData) {
                const fallbackData = __PAYLOAD__.initialData;
                if (fallbackData.conversation_id === convoId) return fallbackData;
            }
            return null;
        }
    }

    Object.assign(global, {
        buildHudTrajectoryData, extractProtobufBreakdownSlices, loadConversationViaRpc,
        StreamRenderCoordinator, InSituConnectClient, resolveRpcEndpoint,
    });
})(typeof window !== "undefined" ? window : globalThis);
