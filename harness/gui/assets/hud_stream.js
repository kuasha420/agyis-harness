// SPDX-License-Identifier: Apache-2.0
// Copyright (c) 2026 Arafat Zahan (@kuasha420)
// Corporate Stewardship & Infrastructure: Purrfect Software Limited (PSL)
// Governed by: ICARO-42/b Ordinance (Company-Supported Personal IP Framework)

/**
 * hud_stream.js — 60 FPS StreamRenderCoordinator & InSituConnectClient Transport.
 * Decouples HTTP/2 ConnectRPC delta ingress from DOM mutations via a bounded frame queue.
 */

(function(global) {
    "use strict";

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

    Object.assign(global, {
        StreamRenderCoordinator,
        InSituConnectClient,
        resolveRpcEndpoint,
    });
})(typeof window !== "undefined" ? window : globalThis);
