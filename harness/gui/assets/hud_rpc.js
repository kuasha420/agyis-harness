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

                // Group 1: SYSTEM_PROMPT (or 3: RULES, 5: SKILLS, 6: SUBAGENTS)
                if (gType === 1 || gType === 3 || gType === 5 || gType === 6 || (gType === 0 && /identity/i.test(gName))) {
                    if (children.length > 0) {
                        children.forEach(c => {
                            const cName = c.name || "section";
                            const cTok = Number(c.numTokens || c.num_tokens || 0);
                            if (cTok > 0) {
                                systemPromptSlices.push({
                                    name: cName,
                                    tag: cName.toLowerCase().replace(/[^a-z0-9_]/g, "_"),
                                    tokens: cTok,
                                });
                            }
                        });
                    } else if (gTokens > 0) {
                        systemPromptSlices.push({
                            name: gName || "System Instructions",
                            tag: "system_prompt",
                            tokens: gTokens,
                        });
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
                                    if (scTok > 0) {
                                        toolDefSlices.push({
                                            name: scName,
                                            server_name: cName,
                                            is_mcp: true,
                                            tokens: scTok,
                                        });
                                    }
                                });
                            } else {
                                const cTok = Number(c.numTokens || c.num_tokens || 0);
                                if (cTok > 0) {
                                    toolDefSlices.push({
                                        name: cName,
                                        server_name: gType === 4 ? (g.serverName || "") : "",
                                        is_mcp: gType === 4,
                                        tokens: cTok,
                                    });
                                }
                            }
                        });
                    } else if (gTokens > 0) {
                        toolDefSlices.push({
                            name: gName || "Tool Schemas",
                            tokens: gTokens,
                            is_mcp: gType === 4,
                        });
                    }
                }
            });
        }

        // Fallbacks
        if (toolDefSlices.length === 0 && chatModelData && Array.isArray(chatModelData.tools)) {
            chatModelData.tools.forEach(t => {
                const tName = t.name || "tool";
                const serverName = t.serverName || t.server_name || "";
                const tok = Math.max(15, Math.round(JSON.stringify(t).length / 3.5));
                toolDefSlices.push({
                    name: tName,
                    server_name: serverName,
                    is_mcp: Boolean(serverName),
                    tokens: tok,
                });
            });
        }

        if (systemPromptSlices.length === 0 && chatModelData && Array.isArray(chatModelData.promptSections)) {
            chatModelData.promptSections.forEach((sec, idx) => {
                const sName = sec.title || sec.name || `Section #${idx + 1}`;
                const content = sec.content || "";
                const tok = Math.max(10, Math.round(content.length / 3.5));
                systemPromptSlices.push({
                    name: sName,
                    tag: sName.toLowerCase().replace(/[^a-z0-9_]/g, "_"),
                    tokens: tok,
                });
            });
        }

        return { systemPromptSlices, toolDefSlices };
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

        // Index metadata streams
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
            while (stream.cursor < stream.list.length) {
                const entry = stream.list[stream.cursor++];
                if (!entry.keyed) return entry.item;
            }
            return null;
        };

        const genStream = indexMetaStream(genMetas);
        const execStream = indexMetaStream(execMetas);

        let activeChatStart = null;
        let activeTokenBreakdown = null;
        let cumulativeTokens = 0;
        let maxContextTokens = 256000;

        const steps = orderedRaw.map((rs, idx) => {
            const stepIdx = rs.stepIndex !== undefined ? rs.stepIndex : (rs.step_index !== undefined ? rs.step_index : idx);
            let cortexType = rs.type || rs.stepType || "STEP";
            if (typeof cortexType === "string" && cortexType.startsWith("CORTEX_STEP_TYPE_")) {
                cortexType = cortexType.replace("CORTEX_STEP_TYPE_", "");
            }
            const isModelStep = cortexType === "PLANNER_RESPONSE" || cortexType === "MODEL_OUTPUT";
            const isExecStep = !isModelStep && cortexType !== "USER_INPUT";

            const gm = nextAlignedMeta(genStream, stepIdx, idx, isModelStep);
            const em = nextAlignedMeta(execStream, stepIdx, idx, isExecStep);

            const tsMs = parseStepTimestampMs(rs, gm, em);
            const gmUsage = (gm && gm.usage) || (rs.metadata && rs.metadata.modelUsage) || {};

            if (gm && gm.chatModel && gm.chatModel.chatStartMetadata) {
                activeChatStart = gm.chatModel.chatStartMetadata;
                const cwm = activeChatStart.contextWindowMetadata;
                if (cwm) {
                    if (cwm.maxTokens) maxContextTokens = cwm.maxTokens;
                    if (cwm.tokenBreakdown) activeTokenBreakdown = cwm.tokenBreakdown;
                }
            }

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
            if (rs.runCommand) {
                extraFields.command = rs.runCommand.commandLine || "";
                extraFields.exitCode = rs.runCommand.exitCode;
                extraFields.output = (rs.runCommand.combinedOutput && rs.runCommand.combinedOutput.full) || "";
                extraFields.cwd = rs.runCommand.cwd || "";
            }
            if (rs.viewFile) {
                extraFields.filePath = rs.viewFile.absolutePathUri || "";
                extraFields.fileContent = rs.viewFile.content || "";
                extraFields.endLine = rs.viewFile.endLine;
            }
            if (rs.codeAction) {
                extraFields.diffLines = (rs.codeAction.actionResult?.edit?.diff?.unifiedDiff?.lines) || [];
                const actSpec = rs.codeAction.actionSpec || {};
                extraFields.filePath = actSpec.createFile?.path?.absoluteUri || actSpec.editFile?.path?.absoluteUri || "";
            }
            if (rs.invokeSubagent) extraFields.subagent = (rs.invokeSubagent.subagents && rs.invokeSubagent.subagents[0]) || null;
            if (rs.checkpoint) {
                extraFields.sessionSummary = rs.checkpoint.sessionSummary || "";
                extraFields.checkpoint_index = rs.checkpoint.checkpointIndex;
            }

            return Object.assign({
                step_index: stepIdx,
                type: cortexType,
                status: rs.status || "STATUS_COMPLETED",
                content: rs.content || rs.text || "",
                thinking: rs.thinking || rs.reasoning || "",
                tool_calls: rs.tool_calls || rs.toolCalls || [],
                timestamp_ms: tsMs,
                created_at: rs.created_at || (tsMs ? new Date(tsMs).toISOString() : null),
                tokens: stepTokens,
                cumulative_tokens: cumulativeTokens,
                input_tokens: inTok,
                output_tokens: outTok,
                thinking_tokens: thinkTok,
                cache_read_tokens: cacheTok,
                size_bytes: JSON.stringify(rs).length,
                thinking_duration_ms: thinkingDurationMs,
                streaming_duration_ms: streamingDurationMs,
                total_duration_ms: totalDurationMs,
                response_model: rs.response_model || (gm && gm.model) || "",
                generator_metadata: gm,
                executor_metadata: em,
                _hasAuthUsage: hasAuthUsage,
            }, extraFields);
        });

        // Extract Context Window Metadata from genMetas and raw steps
        maxContextTokens = 256000;
        let foundMaxContext = false;
        let latestEstimatedTokens = 0;
        const extractCwmFromObj = (obj) => {
            if (!obj || typeof obj !== "object") return;
            const cwmCandidates = [obj.contextWindowMetadata, obj.chatStartMetadata?.contextWindowMetadata, obj.metadata?.contextWindowMetadata, obj.metadata?.chatStartMetadata?.contextWindowMetadata, obj.chatModel?.chatStartMetadata?.contextWindowMetadata];
            for (let cIdx = 0; cIdx < cwmCandidates.length; cIdx++) {
                const cwm = cwmCandidates[cIdx];
                if (!cwm || typeof cwm !== "object") continue;
                if ((cwm.estimatedTokensUsed || cwm.estimated_tokens_used) && !latestEstimatedTokens) {
                    const est = parseInt(cwm.estimatedTokensUsed || cwm.estimated_tokens_used, 10) || 0;
                    if (est > 0) latestEstimatedTokens = est;
                }
                if ((cwm.maxContextTokens || cwm.max_context_tokens || cwm.maxTokens) && !foundMaxContext) {
                    const mct = parseInt(cwm.maxContextTokens || cwm.max_context_tokens || cwm.maxTokens, 10) || 0;
                    if (mct > 0) { maxContextTokens = mct; foundMaxContext = true; }
                }
                if (cwm.tokenBreakdown && !activeTokenBreakdown) {
                    activeTokenBreakdown = cwm.tokenBreakdown;
                }
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

        const extractEstFromObj = (obj) => {
            if (!obj || typeof obj !== "object") return 0;
            const cwmCandidates = [obj.contextWindowMetadata, obj.chatStartMetadata?.contextWindowMetadata, obj.metadata?.contextWindowMetadata, obj.metadata?.chatStartMetadata?.contextWindowMetadata, obj.chatModel?.chatStartMetadata?.contextWindowMetadata];
            for (let cIdx = 0; cIdx < cwmCandidates.length; cIdx++) {
                const cwm = cwmCandidates[cIdx];
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
        const ssotBreakdown = latestMetrics.token_breakdown;

        // Extract subagents
        const subagents = [];
        const subagentInfos = [];
        const subUuidRe = /[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}/g;
        const addSubagent = (uid, name, summary) => {
            const cleanUid = String(uid || "").trim();
            if (!cleanUid || cleanUid === convoId || subagents.includes(cleanUid)) return;
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
                const outCombined = `${JSON.stringify(args)} ${String(tc.output || tc.result || "")}`;
                const uuids = outCombined.match(subUuidRe) || [];
                uuids.forEach(uid => addSubagent(uid, args.TypeName || args.Role || args.name, args.Prompt || args.objective));
            });
        });

        let convoSummary = `Session ${convoId.slice(0, 8)}`;
        const firstUserStep = steps.find(s => s.type === "USER_INPUT");
        if (firstUserStep && firstUserStep.content) {
            convoSummary = String(firstUserStep.content).trim().split(/\r?\n/)[0].slice(0, 70);
        }

        let parentId = null;
        if (typeof window !== "undefined" && window.location) {
            const searchParams = window.location.search ? new URLSearchParams(window.location.search) : null;
            const tabParam = searchParams ? searchParams.get('tab') : null;
            const pathMatch = window.location.pathname ? window.location.pathname.match(/\/c\/([a-zA-Z0-9_-]+)/) : null;
            if (pathMatch && pathMatch[1] && pathMatch[1] !== convoId) {
                if (tabParam && tabParam.startsWith('subagent_convo__') && tabParam.slice('subagent_convo__'.length) === convoId) {
                    parentId = pathMatch[1];
                } else if (!tabParam) {
                    parentId = pathMatch[1];
                }
            }
        }

        return {
            conversation_id: convoId,
            summary: convoSummary,
            model: (chatModelData && chatModelData.model) || (steps.find(s => s.response_model)?.response_model) || "",
            steps: steps,
            step_count: steps.length,
            epochs: epochs,
            parent_id: parentId,
            subagents: subagents,
            subagent_infos: subagentInfos,
            subagent_trajectories: {},
            total_tokens: totalTokens,
            max_context_tokens: maxContextTokens,
            cache_tokens: cacheTokens,
            is_provisional: isProvisional,
            burn_rate_tokens_per_min: 0,
            token_breakdown: ssotBreakdown,
            system_prompt_slices: systemPromptSlices,
            tool_def_slices: toolDefSlices,
        };
    }

    /**
     * 60 FPS Jitter-Free StreamRenderCoordinator (Strand 2 Architecture).
     * Decouples network delta ingress (20-60Hz) from DOM mutations via an in-memory queue,
     * reconciling updates into a unified state and triggering a single render pass per 16.6ms frame.
     */
    class StreamRenderCoordinator {
        constructor(renderCallback) {
            this._renderCallback = renderCallback;
            this._pendingDeltas = [];
            this._rafId = null;
            this._state = {
                conversationId: "",
                trajectoryId: "",
                stepsInSlice: [],
                generatorMetadatasInSlice: [],
                totalStepsLength: 0,
                activeTokens: 0,
                tokenBreakdown: null,
                isStreaming: false,
            };
            this._dirty = { steps: false, tokens: false, timeline: false };
        }

        ingestUpdate(update) {
            this._pendingDeltas.push(update);
            if (!this._rafId && typeof requestAnimationFrame !== "undefined") {
                this._rafId = requestAnimationFrame(this._flushAndRender.bind(this));
            } else if (!this._rafId) {
                setTimeout(this._flushAndRender.bind(this), 16);
            }
        }

        _flushAndRender() {
            this._rafId = null;
            if (this._pendingDeltas.length === 0) return;

            while (this._pendingDeltas.length > 0) {
                const update = this._pendingDeltas.shift();
                this._reconcileUpdate(update);
            }

            if (this._dirty.steps || this._dirty.tokens || this._dirty.timeline) {
                if (typeof this._renderCallback === "function") {
                    this._renderCallback(this._state, this._dirty);
                }
                this._dirty.steps = false;
                this._dirty.tokens = false;
                this._dirty.timeline = false;
            }
        }

        _reconcileUpdate(update) {
            if (!update) return;
            this._state.conversationId = update.conversationId || this._state.conversationId;
            this._state.trajectoryId = update.trajectoryId || this._state.trajectoryId;

            const mtu = update.mainTrajectoryUpdate;
            if (!mtu) return;

            if (mtu.stepsUpdate) {
                const { indices, steps, totalLength } = mtu.stepsUpdate;
                if (indices && steps) {
                    for (let i = 0; i < indices.length; i++) {
                        const idx = indices[i];
                        this._state.stepsInSlice[idx] = steps[i];
                    }
                    this._dirty.steps = true;
                    this._dirty.timeline = true;
                }
                if (totalLength !== undefined) this._state.totalStepsLength = totalLength;
            }

            if (mtu.generatorMetadatasUpdate) {
                const { indices, generatorMetadatas } = mtu.generatorMetadatasUpdate;
                if (indices && generatorMetadatas) {
                    for (let i = 0; i < indices.length; i++) {
                        const idx = indices[i];
                        const gm = generatorMetadatas[i];
                        this._state.generatorMetadatasInSlice[idx] = gm;

                        const cwm = gm?.chatModel?.chatStartMetadata?.contextWindowMetadata;
                        if (cwm) {
                            this._state.activeTokens = cwm.estimatedTokensUsed || this._state.activeTokens;
                            if (cwm.tokenBreakdown) {
                                this._state.tokenBreakdown = cwm.tokenBreakdown;
                                this._dirty.tokens = true;
                            }
                        }
                    }
                }
            }
        }
    }

    /**
     * Resolves ConnectRPC endpoint (port, baseUrl, csrfToken) from options, runtime payloads, or window environment.
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
        const csrfToken = options.csrfToken || (appCfg && appCfg.csrfToken) || "";
        return { port, baseUrl, csrfToken };
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
            this.activeAbortController = null;
        }

        /**
         * Connects to StreamAgentStateUpdates over persistent HTTP/2 Connect streaming.
         */
        async streamConversation(conversationId, onStateChange) {
            if (this.activeAbortController) {
                this.activeAbortController.abort("Switching conversation");
            }
            this.activeAbortController = new AbortController();
            const coordinator = new StreamRenderCoordinator(onStateChange);

            const subscriberId = (typeof crypto !== "undefined" && crypto.randomUUID) ? crypto.randomUUID() : `sub-${Date.now()}`;
            const reqBody = {
                conversationId, subscriberId,
                initialStepsPageBounds: { startIndex: 0, endIndexExclusive: 500 },
                initialGeneratorMetadatasPageBounds: { startIndex: 0, endIndexExclusive: 500 },
                initialExecutorMetadatasPageBounds: { startIndex: 0, endIndexExclusive: 500 },
                trajectoryVerbosity: 2,
            };
            const jsonBytes = new TextEncoder().encode(JSON.stringify(reqBody));
            const framedReq = new Uint8Array(5 + jsonBytes.length);
            framedReq[0] = 0x00;
            new DataView(framedReq.buffer).setUint32(1, jsonBytes.length, false);
            framedReq.set(jsonBytes, 5);

            const url = `${this.baseUrl}/exa.language_server_pb.LanguageServerService/StreamAgentStateUpdates`;
            const headers = { "Content-Type": "application/connect+json", "Connect-Protocol-Version": "1" };
            if (this.csrfToken) headers["x-codeium-csrf-token"] = this.csrfToken;

            const response = await fetch(url, { method: "POST", headers, body: framedReq, signal: this.activeAbortController.signal });

            if (!response.ok) {
                throw new Error(`ConnectRPC stream failed with HTTP ${response.status}`);
            }

            const reader = response.body.getReader();
            let buffer = new Uint8Array(0);

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

                    const payloadBytes = buffer.subarray(5, 5 + length);
                    buffer = buffer.subarray(5 + length);

                    if (flags === 0x00) {
                        const jsonStr = new TextDecoder().decode(payloadBytes);
                        try {
                            const message = JSON.parse(jsonStr);
                            if (message.update) coordinator.ingestUpdate(message.update);
                        } catch (e) {
                            console.error("[InSituConnectClient] JSON decode error:", e);
                        }
                    } else if (flags === 0x02) {
                        break;
                    }
                }
            }
        }
    }

    /**
     * ConnectRPC conversation loader with fallback ladder.
     */
    async function loadConversationViaRpc(convoId) {
        if (!convoId) return null;
        try {
            const { baseUrl, csrfToken } = resolveRpcEndpoint();

            const headers = { "Content-Type": "application/json", "Connect-Protocol-Version": "1" };
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

            // Fallback to local HTTP server (dual query/path parameter support)
            if (!rawSteps || rawSteps.length === 0) {
                const encId = encodeURIComponent(convoId);
                let localHttpRes = await fetch(`http://127.0.0.1:40624/api/trajectory?id=${encId}`).catch(() => null);
                if (!localHttpRes || !localHttpRes.ok) {
                    localHttpRes = await fetch(`http://127.0.0.1:40624/api/trajectory/${encId}`).catch(() => null);
                }
                if (localHttpRes && localHttpRes.ok) {
                    const localData = await localHttpRes.json().catch(() => null);
                    if (localData && localData.steps) return localData;
                }

                if (typeof __PAYLOAD__ !== "undefined" && __PAYLOAD__ && __PAYLOAD__.initialData) {
                    return __PAYLOAD__.initialData;
                }
                return null;
            }

            const genJson = (genRes && genRes.ok) ? await genRes.json().catch(() => null) : null;
            const genMetas = (genJson && (genJson.generatorMetadata || genJson.generatorMetadatas || genJson.metadatas)) || [];
            const chatModelData = (genJson && (genJson.chatModel || (genMetas[0] && genMetas[0].chatModel))) || null;
            const execJson = (execRes && execRes.ok) ? await execRes.json().catch(() => null) : null;
            const execMetas = (execJson && (execJson.executorMetadatas || execJson.metadatas)) || [];

            return buildHudTrajectoryData(convoId, rawSteps, genMetas, execMetas, chatModelData);
        } catch (err) {
            console.warn("[agyis] ConnectRPC trajectory fetch failed:", err);
            if (typeof __PAYLOAD__ !== "undefined" && __PAYLOAD__ && __PAYLOAD__.initialData) {
                const fallbackData = __PAYLOAD__.initialData;
                return fallbackData;
            }
            return null;
        }
    }

    // Export module onto window namespace
    global.buildHudTrajectoryData = buildHudTrajectoryData;
    global.extractProtobufBreakdownSlices = extractProtobufBreakdownSlices;
    global.loadConversationViaRpc = loadConversationViaRpc;
    global.StreamRenderCoordinator = StreamRenderCoordinator;
    global.InSituConnectClient = InSituConnectClient;
    global.resolveRpcEndpoint = resolveRpcEndpoint;

})(typeof window !== "undefined" ? window : globalThis);
