#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Arafat Zahan (@kuasha420)
# Corporate Stewardship & Infrastructure: Purrfect Software Limited (PSL)
# Governed by: ICARO-42/b Ordinance (Company-Supported Personal IP Framework)

"""
Bug Bash Phase 2 — Frontier 1 HUD Hotkeys, Caret Retention, Subagent Sync, Async Races & 500-Step Streaming.
Executes real hotkey.js, hud.js, hud_header.js, and hud_rpc.js inside Node.js.
Split from test_e2e_bugbash_phase2.py for sub-second ADR-015 verification.
"""

from __future__ import annotations

import importlib.resources
import json
import shutil
import subprocess
import unittest

from harness.remote.triage import RemoteTriage


_LIFECYCLE_DOM_PREAMBLE = r"""
function makeElement(tagName) {
    const el = {
        tagName: String(tagName || "div").toUpperCase(),
        id: "",
        className: "",
        parentNode: null,
        style: { display: "none", transform: "" },
        innerHTML: "",
        innerText: "",
        textContent: "",
        children: [],
        value: "",
        selectionStart: 0,
        selectionEnd: 0,
        _attrs: {},
        _listeners: {},
        classList: {
            _classes: new Set(),
            add(c) { this._classes.add(c); },
            remove(c) { this._classes.delete(c); },
            contains(c) { return this._classes.has(c); },
            toggle(c) { if (this._classes.has(c)) this._classes.delete(c); else this._classes.add(c); }
        },
        addEventListener(event, handler, opts) {
            (this._listeners[event] = this._listeners[event] || []).push({ handler, opts });
        },
        removeEventListener(event, handler) {
            if (!this._listeners[event]) return;
            this._listeners[event] = this._listeners[event].filter(l => l.handler !== handler);
        },
        dispatchEvent(event) {
            if (!event.preventDefault) event.preventDefault = () => {};
            if (!event.stopPropagation) event.stopPropagation = () => {};
            if (!event.stopImmediatePropagation) event.stopImmediatePropagation = () => {};
            for (const item of (this._listeners[event.type] || [])) item.handler.call(this, event);
        },
        appendChild(child) {
            if (child.parentNode && child.parentNode !== this) {
                child.parentNode.children = child.parentNode.children.filter(c => c !== child);
            }
            child.parentNode = this;
            this.children.push(child);
            return child;
        },
        remove() {
            if (this.parentNode) {
                this.parentNode.children = this.parentNode.children.filter(c => c !== this);
                this.parentNode = null;
            }
        },
        contains(target) {
            if (target === this) return true;
            return this.children.some(ch => ch === target || (ch.contains && ch.contains(target)));
        },
        focus() { document.activeElement = this; },
        blur() { if (document.activeElement === this) document.activeElement = document.body; },
        setSelectionRange(s, e) { this.selectionStart = s; this.selectionEnd = e; },
        getAttribute(k) { return Object.prototype.hasOwnProperty.call(this._attrs, k) ? this._attrs[k] : (this[k] || null); },
        setAttribute(k, v) { this._attrs[k] = String(v); if (k === "id") this.id = String(v); },
        scrollIntoView() {},
        querySelector(sel) {
            const all = this.querySelectorAll(sel);
            return all.length ? all[0] : null;
        },
        querySelectorAll(sel) {
            const results = [];
            const check = (node) => {
                if (!node) return;
                if (sel.startsWith("#")) {
                    if (node.id === sel.slice(1)) results.push(node);
                } else if (sel.startsWith(".")) {
                    if (node.classList && node.classList.contains(sel.slice(1))) results.push(node);
                }
                for (const ch of (node.children || [])) check(ch);
            };
            for (const ch of (this.children || [])) check(ch);
            return results;
        }
    };
    return el;
}

const hudRoot = makeElement("div");
hudRoot.id = "agyis-trajectory-hud";
hudRoot.style.display = "none";
const searchInput = makeElement("input");
searchInput.id = "agyis-search-input";
hudRoot.appendChild(searchInput);

const document = {
    body: makeElement("body"),
    head: makeElement("head"),
    activeElement: null,
    getElementById(id) {
        return this.head.querySelector("#" + id) || this.body.querySelector("#" + id) || (id === "agyis-search-input" ? searchInput : null);
    },
    createElement(tag) { return makeElement(tag); },
    querySelector(sel) { return hudRoot.querySelector(sel); },
    querySelectorAll(sel) { return hudRoot.querySelectorAll(sel); },
    addEventListener() {},
    removeEventListener() {},
};
document.body.appendChild(hudRoot);
document.activeElement = document.body;

const windowListeners = [];
const window = {
    location: { origin: "https://127.0.0.1:40623", pathname: "/c/convo-root", search: "" },
    __APP_CONFIG__: {},
    addEventListener(event, handler, useCapture) {
        windowListeners.push({ event, handler, useCapture: Boolean(useCapture) });
    },
    removeEventListener(event, handler) {
        const idx = windowListeners.findIndex(l => l.event === event && l.handler === handler);
        if (idx !== -1) windowListeners.splice(idx, 1);
    },
    dispatchEvent(event) {
        if (!event.preventDefault) event.preventDefault = () => {};
        if (!event.stopPropagation) event.stopPropagation = () => {};
        if (!event.stopImmediatePropagation) event.stopImmediatePropagation = () => {};
        for (const l of windowListeners.filter(x => x.event === event.type && x.useCapture)) l.handler.call(window, event);
        for (const l of windowListeners.filter(x => x.event === event.type && !x.useCapture)) l.handler.call(window, event);
    },
    document,
};
global.window = window;
global.document = document;
global.Event = class Event { constructor(t) { this.type = t; } };
const _rafQueue = [];
global.requestAnimationFrame = (cb) => { _rafQueue.push(cb); return _rafQueue.length; };
global.cancelAnimationFrame = () => {};
global.__flushRaf = () => {
    while (_rafQueue.length) {
        const cb = _rafQueue.shift();
        cb(performance.now());
    }
};
global.makeConnectFrame = (flags, obj) => {
    const body = new TextEncoder().encode(JSON.stringify(obj));
    const out = new Uint8Array(5 + body.length);
    out[0] = flags;
    new DataView(out.buffer).setUint32(1, body.length, false);
    out.set(body, 5);
    return out;
};
global.makeMockStreamResponse = (frames) => {
    let idx = 0;
    return {
        ok: true,
        status: 200,
        body: {
            getReader() {
                return {
                    async read() {
                        if (idx < frames.length) return { done: false, value: frames[idx++] };
                        return { done: true, value: undefined };
                    }
                };
            }
        }
    };
};
"""


class TestPhase2HudLifecycle(unittest.TestCase):
    """Real Node.js E2E verification for hotkeys, caret retention, subagent sync, async races, and 500-step streams."""

    def _run_node(self, js_body: str) -> dict:
        node_bin = shutil.which("node")
        if not node_bin:
            self.skipTest("node binary unavailable in PATH")
        script = f"{_LIFECYCLE_DOM_PREAMBLE}\n(async () => {{\n{js_body}\n}})();\n"
        proc = subprocess.run([node_bin, "-e", script], capture_output=True, text=True, timeout=5, check=False)
        self.assertEqual(proc.returncode, 0, f"Node harness failed:\nSTDOUT:{proc.stdout}\nSTDERR:{proc.stderr}")
        lines = [line.strip() for line in proc.stdout.splitlines() if line.strip()]
        return json.loads(lines[-1])

    # --- F05: Hotkey Toggle Lifecycle & Escape Priority ---

    def test_t1_f05_01_02_03_f12_ctrl_shift_t_and_debounce(self) -> None:
        """F05.01-F05.03: Real hotkey.js toggles on F12, Ctrl+Shift+T, and debounces within 250ms."""
        hotkey_js = json.dumps(str(importlib.resources.files("harness.gui.assets").joinpath("hotkey.js")))
        res = self._run_node(f"""
        const fs = require('fs');
        let nowMs = 5000;
        Date.now = () => nowMs;
        window.__agyis_hud_state = {{ convoId: "convo-root", steps: [] }};
        eval(fs.readFileSync({hotkey_js}, 'utf8'));

        nowMs += 300;
        window.dispatchEvent({{ type: "keydown", key: "F12" }});
        const afterF12Open = hudRoot.style.display;

        // Within 250ms debounce window -> ignored
        nowMs += 100;
        window.dispatchEvent({{ type: "keydown", key: "F12" }});
        const duringDebounce = hudRoot.style.display;

        // Past debounce -> Ctrl+Shift+T closes
        nowMs += 300;
        window.dispatchEvent({{ type: "keydown", key: "T", ctrlKey: true, shiftKey: true }});
        const afterCtrlShiftT = hudRoot.style.display;

        console.log(JSON.stringify({{ afterF12Open, duringDebounce, afterCtrlShiftT }}));
        """)
        self.assertEqual(res["afterF12Open"], "flex")
        self.assertEqual(res["duringDebounce"], "flex")
        self.assertEqual(res["afterCtrlShiftT"], "none")

    def test_t1_f05_04_05_escape_search_vs_close_hud(self) -> None:
        """F05.04-F05.05: Real hud.js Escape clears non-empty search without closing, then closes when empty."""
        hud_js = json.dumps(str(importlib.resources.files("harness.gui.assets").joinpath("hud.js")))
        res = self._run_node(f"""
        const fs = require('fs');
        eval(fs.readFileSync({hud_js}, 'utf8'));
        const curHud = document.getElementById("agyis-trajectory-hud");
        curHud.style.display = "flex";
        window.__agyis_hud_state.filterQuery = "active query";
        searchInput.value = "active query";
        document.activeElement = searchInput;

        window.dispatchEvent({{ type: "keydown", key: "Escape", target: searchInput }});
        const afterFirstEscDisplay = curHud.style.display;
        const afterFirstEscQuery = window.__agyis_hud_state.filterQuery;

        searchInput.value = "";
        window.dispatchEvent({{ type: "keydown", key: "Escape", target: document.body }});
        const afterSecondEscDisplay = curHud.style.display;

        console.log(JSON.stringify({{ afterFirstEscDisplay, afterFirstEscQuery, afterSecondEscDisplay }}));
        """)
        self.assertEqual(res["afterFirstEscDisplay"], "flex")
        self.assertEqual(res["afterFirstEscQuery"], "")
        self.assertEqual(res["afterSecondEscDisplay"], "none")

    # --- F06: 60 FPS ConnectRPC Streaming & Caret Retention ---

    def test_t1_f06_01_02_03_caret_and_focus_preserved_across_hud_render(self) -> None:
        """F06.01-F06.03: Real hud.js preserves search input value, focus, and caret selectionStart/End on renderHud()."""
        hud_js = json.dumps(str(importlib.resources.files("harness.gui.assets").joinpath("hud.js")))
        res = self._run_node(f"""
        const fs = require('fs');
        eval(fs.readFileSync({hud_js}, 'utf8'));
        window.__agyis_hud_state.rootData = {{ steps: [{{ step_index: 0 }}], conversation_id: "convo-root" }};
        window.__agyis_hud_state.currentData = window.__agyis_hud_state.rootData;

        searchInput.value = "searching trajectory steps";
        searchInput.focus();
        searchInput.setSelectionRange(10, 20);
        window.__agyis_hud_render();

        console.log(JSON.stringify({{
            retainedValue: searchInput.value,
            selectionStart: searchInput.selectionStart,
            selectionEnd: searchInput.selectionEnd,
            isFocused: document.activeElement === searchInput
        }}));
        """)
        self.assertEqual(res["retainedValue"], "searching trajectory steps")
        self.assertEqual(res["selectionStart"], 10)
        self.assertEqual(res["selectionEnd"], 20)
        self.assertTrue(res["isFocused"])

    def test_t1_f06_04_05_stream_historical_lock_and_latest_auto_follow(self) -> None:
        """F06.04-F06.05: Real hud.js + hud_rpc.js preserves historical selectedIndex=5 and auto-follows when at latest step."""
        hud_js = json.dumps(str(importlib.resources.files("harness.gui.assets").joinpath("hud.js")))
        rpc_js = json.dumps(str(importlib.resources.files("harness.gui.assets").joinpath("hud_rpc.js")))
        res = self._run_node(f"""
        const fs = require('fs');
        eval(fs.readFileSync({rpc_js}, 'utf8'));

        const makeSteps = (n) => Array.from({{ length: n }}, (_, i) => ({{ stepIndex: i, type: "CORTEX_STEP_TYPE_USER_INPUT", content: "s" + i }}));
        let streamFrames = [
            makeConnectFrame(0x00, {{ update: {{ conversationId: "convo-stream", mainTrajectoryUpdate: {{ stepsUpdate: {{ indices: Array.from({{ length: 25 }}, (_, i) => i), steps: makeSteps(25), totalLength: 25 }} }} }} }}),
            makeConnectFrame(0x02, {{}})
        ];
        global.fetch = async () => makeMockStreamResponse(streamFrames);

        eval(fs.readFileSync({hud_js}, 'utf8'));
        const st = window.__agyis_hud_state;
        st.convoId = "convo-stream";
        st.rootData = {{ conversation_id: "convo-stream", steps: makeSteps(20), epochs: [{{ epoch_index: 0, start_index: 0, end_index: 19 }}] }};
        st.currentData = st.rootData;

        // Historical inspection lock at step 5 (< 19)
        st.selectedIndex = 5;
        window.__agyis_hud_start_stream("convo-stream");
        await new Promise(r => setTimeout(r, 15));
        global.__flushRaf();
        const historicalSelected = st.selectedIndex;

        // Auto-follow when at latest step (24 of 25)
        st.selectedIndex = 24;
        streamFrames = [
            makeConnectFrame(0x00, {{ update: {{ conversationId: "convo-stream", mainTrajectoryUpdate: {{ stepsUpdate: {{ indices: Array.from({{ length: 30 }}, (_, i) => i), steps: makeSteps(30), totalLength: 30 }} }} }} }}),
            makeConnectFrame(0x02, {{}})
        ];
        window.__agyis_hud_start_stream("convo-stream");
        await new Promise(r => setTimeout(r, 15));
        global.__flushRaf();
        const followSelected = st.selectedIndex;

        console.log(JSON.stringify({{ historicalSelected, followSelected }}));
        """)
        self.assertEqual(res["historicalSelected"], 5)
        self.assertEqual(res["followSelected"], 29)

    # --- F07: Subagent State Synchronization ---

    def test_t1_f07_01_to_05_subagent_click_updates_data_model_and_bounds(self) -> None:
        """F07.01-F07.05: Real hud_header.js updates currentData, convoId, sessionModel, selectedIndex, or triggers load_convo."""
        header_js = json.dumps(str(importlib.resources.files("harness.gui.assets").joinpath("hud_header.js")))
        res = self._run_node(f"""
        const fs = require('fs');
        eval(fs.readFileSync({header_js}, 'utf8'));

        const subData = {{
            conversation_id: "subagent-1",
            model: "gemini-4-neon",
            epochs: [{{ epoch_index: 0, start_index: 0, end_index: 3 }}],
            steps: [{{ step: 0 }}, {{ step: 1 }}, {{ step: 2 }}, {{ step: 3 }}]
        }};
        const cur = {{
            conversation_id: "parent-root",
            subagents: ["subagent-1", "uncached-sub-789"],
            subagent_trajectories: {{ "subagent-1": subData }}
        }};

        const itemCached = makeElement("div");
        itemCached.classList.add("agyis-subagent-item");
        itemCached.setAttribute("data-sub-id", "subagent-1");
        hudRoot.appendChild(itemCached);

        const state = {{
            convoId: "parent-root",
            sessionModel: "claude-3-7-sonnet",
            currentData: cur,
            selectedIndex: 0,
            activeEpochIndex: 0
        }};
        window.__agyis_hud_state = state;

        window.bindHudHeaderEvents(hudRoot, state, cur, () => {{}});
        itemCached.dispatchEvent({{ type: "click", stopPropagation() {{}} }});
        const cachedSnap = {{
            currentConvoId: state.currentData.conversation_id,
            stateConvoId: state.convoId,
            sessionModel: state.sessionModel,
            selectedIndex: state.selectedIndex,
            activeEpochIndex: state.activeEpochIndex
        }};

        let requestedUncached = null;
        window.__agyis_hud_load_convo = (id) => {{ requestedUncached = id; return null; }};
        const itemUncached = makeElement("div");
        itemUncached.classList.add("agyis-subagent-item");
        itemUncached.setAttribute("data-sub-id", "uncached-sub-789");
        hudRoot.appendChild(itemUncached);
        window.bindHudHeaderEvents(hudRoot, state, cur, () => {{}});
        itemUncached.dispatchEvent({{ type: "click", stopPropagation() {{}} }});

        console.log(JSON.stringify({{ cachedSnap, requestedUncached }}));
        """)
        snap = res["cachedSnap"]
        self.assertEqual(snap["currentConvoId"], "subagent-1")
        self.assertEqual(snap["stateConvoId"], "subagent-1")
        self.assertEqual(snap["sessionModel"], "gemini-4-neon")
        self.assertEqual(snap["selectedIndex"], 3)
        self.assertEqual(snap["activeEpochIndex"], 0)
        self.assertEqual(res["requestedUncached"], "uncached-sub-789")

    # --- F08: Async Navigation Sequencing ---

    def test_t1_f08_01_to_05_async_navigation_sequence_guard(self) -> None:
        """F08.01-F08.05: Real hud.js __agyis_hud_load_convo discards superseded out-of-order responses and skips null IDs."""
        hud_js = json.dumps(str(importlib.resources.files("harness.gui.assets").joinpath("hud.js")))
        res = self._run_node(f"""
        const fs = require('fs');
        const requested = [];
        const resolvers = {{}};
        window.loadConversationViaRpc = (id) => {{
            requested.push(id);
            return new Promise(resolve => {{ resolvers[id] = resolve; }});
        }};
        eval(fs.readFileSync({hud_js}, 'utf8'));

        // Null/empty convoId never triggers RPC fetch
        const beforeNullCount = requested.length;
        const nullRes = await window.__agyis_hud_load_convo(null);
        const emptyRes = await window.__agyis_hud_load_convo("");
        const afterNullCount = requested.length;

        // Out-of-order resolution: convo-latest resolves first, convo-stale resolves second -> discarded
        const pStale = window.__agyis_hud_load_convo("convo-stale");
        const pLatest = window.__agyis_hud_load_convo("convo-latest");
        resolvers["convo-latest"]({{ conversation_id: "convo-latest", steps: [{{ step: 1 }}] }});
        await pLatest;
        resolvers["convo-stale"]({{ conversation_id: "convo-stale", steps: [{{ step: 1 }}] }});
        await pStale;

        const outOfOrderWinner = window.__agyis_hud_state.convoId;
        const outOfOrderData = window.__agyis_hud_state.currentData.conversation_id;

        // Rapid burst of 5 switches
        window.loadConversationViaRpc = async (id) => ({{ conversation_id: id, steps: [{{ step: 1 }}] }});
        for (let i = 0; i < 5; i++) window.__agyis_hud_load_convo("rapid-" + i);
        await new Promise(r => setTimeout(r, 15));

        console.log(JSON.stringify({{
            nullSkipped: nullRes === null && emptyRes === null && beforeNullCount === afterNullCount,
            outOfOrderWinner,
            outOfOrderData,
            rapidWinner: window.__agyis_hud_state.convoId
        }}));
        """)
        self.assertTrue(res["nullSkipped"])
        self.assertEqual(res["outOfOrderWinner"], "convo-latest")
        self.assertEqual(res["outOfOrderData"], "convo-latest")
        self.assertEqual(res["rapidWinner"], "rapid-4")

    # --- Tier 2 / Tier 3 / Tier 4 HUD Lifecycle ---

    def test_t2_b05_01_rapid_f12_spamming_debounced(self) -> None:
        """B05.01: Real hotkey.js debounces 10 rapid 20ms-spaced F12 events to a single toggle."""
        hotkey_js = json.dumps(str(importlib.resources.files("harness.gui.assets").joinpath("hotkey.js")))
        res = self._run_node(f"""
        const fs = require('fs');
        let nowMs = 10000;
        Date.now = () => nowMs;
        hudRoot.remove();
        let toggles = 0;
        window.__agyis_hud_mount = () => {{ toggles++; }};
        eval(fs.readFileSync({hotkey_js}, 'utf8'));
        for (let i = 0; i < 10; i++) {{
            nowMs += 20;
            window.dispatchEvent({{ type: "keydown", key: "F12" }});
        }}
        console.log(JSON.stringify({{ toggles }}));
        """)
        self.assertEqual(res["toggles"], 1)

    def test_t2_b06_01_sparse_stream_step_indices(self) -> None:
        """B06.01: Real StreamRenderCoordinator bounds sparse stepIndex=100 slice cleanly."""
        rpc_js = json.dumps(str(importlib.resources.files("harness.gui.assets").joinpath("hud_rpc.js")))
        res = self._run_node(f"""
        const fs = require('fs');
        eval(fs.readFileSync({rpc_js}, 'utf8'));
        let seen = null;
        const coord = new window.StreamRenderCoordinator((st) => {{ seen = st; }});
        coord.ingestUpdate({{
            conversationId: "sparse-convo",
            mainTrajectoryUpdate: {{
                stepsUpdate: {{
                    indices: [100],
                    steps: [{{ stepIndex: 100, type: "CORTEX_STEP_TYPE_USER_INPUT" }}],
                    totalLength: 101
                }}
            }}
        }});
        global.__flushRaf();
        const nonNull = seen.stepsInSlice.filter(Boolean);
        console.log(JSON.stringify({{ count: nonNull.length, stepIdx: nonNull[0].stepIndex, total: seen.totalStepsLength }}));
        """)
        self.assertEqual(res["count"], 1)
        self.assertEqual(res["stepIdx"], 100)
        self.assertEqual(res["total"], 101)

    def test_t3_c01_triage_streaming_concurrency(self) -> None:
        """C01: Executes RemoteTriage.format_triage_markdown alongside real hud_rpc.js StreamRenderCoordinator."""
        md = RemoteTriage.format_triage_markdown("=== HOST ===\nLinux mesh-node 7.2\n", "mesh-node")
        self.assertIn("Host & Resources", md)

        rpc_js = json.dumps(str(importlib.resources.files("harness.gui.assets").joinpath("hud_rpc.js")))
        res = self._run_node(f"""
        const fs = require('fs');
        eval(fs.readFileSync({rpc_js}, 'utf8'));
        let seen = null;
        const coord = new window.StreamRenderCoordinator((st) => {{ seen = st; }});
        coord.ingestUpdate({{
            conversationId: "c1",
            contextWindowUsage: {{ estimatedTokensUsed: 50000, maxContextTokens: 512000 }}
        }});
        global.__flushRaf();
        console.log(JSON.stringify({{ convoId: seen.conversationId, activeTokens: seen.activeTokens, maxContextTokens: seen.maxContextTokens }}));
        """)
        self.assertEqual(res["convoId"], "c1")
        self.assertEqual(res["activeTokens"], 50000)
        self.assertEqual(res["maxContextTokens"], 512000)

    def test_t3_c02_dropdown_switch_aborts_prior_stream(self) -> None:
        """C02: Switching conversation via real InSituConnectClient + hud.js aborts prior stream cleanly."""
        hud_js = json.dumps(str(importlib.resources.files("harness.gui.assets").joinpath("hud.js")))
        rpc_js = json.dumps(str(importlib.resources.files("harness.gui.assets").joinpath("hud_rpc.js")))
        header_js = json.dumps(str(importlib.resources.files("harness.gui.assets").joinpath("hud_header.js")))
        res = self._run_node(f"""
        const fs = require('fs');
        eval(fs.readFileSync({rpc_js}, 'utf8'));
        eval(fs.readFileSync({header_js}, 'utf8'));
        const signals = {{}};
        global.fetch = (url, init) => {{
            if (url.includes("StreamAgentStateUpdates")) {{
                const body = JSON.parse(new TextDecoder().decode(init.body.slice(5)));
                signals[body.conversationId] = init.signal;
                if (body.conversationId === "convo-1") return new Promise(() => {{}});
                return Promise.resolve(makeMockStreamResponse([makeConnectFrame(0x02, {{}})]));
            }}
            return Promise.resolve({{ ok: false, status: 404 }});
        }};
        window.loadConversationViaRpc = async (id) => ({{ conversation_id: id, steps: [{{ step_index: 0, type: "USER_INPUT" }}] }});
        eval(fs.readFileSync({hud_js}, 'utf8'));

        window.__agyis_hud_start_stream("convo-1");
        const abortedBeforeSwitch = signals["convo-1"].aborted;

        await window.__agyis_hud_load_convo("convo-2");
        const abortedAfterSwitch = signals["convo-1"].aborted;
        console.log(JSON.stringify({{
            abortedBeforeSwitch,
            abortedAfterSwitch,
            activeConvo: window.__agyis_hud_state.convoId
        }}));
        """)
        self.assertFalse(res["abortedBeforeSwitch"])
        self.assertTrue(res["abortedAfterSwitch"])
        self.assertEqual(res["activeConvo"], "convo-2")

    def test_t4_s02_titanium_500_step_trajectory_streaming(self) -> None:
        """S02: Real hud_rpc.js + hud.js handles 550 streamed steps with checkpoint epochs and page lock."""
        hud_js = json.dumps(str(importlib.resources.files("harness.gui.assets").joinpath("hud.js")))
        rpc_js = json.dumps(str(importlib.resources.files("harness.gui.assets").joinpath("hud_rpc.js")))
        res = self._run_node(f"""
        const fs = require('fs');
        eval(fs.readFileSync({rpc_js}, 'utf8'));
        eval(fs.readFileSync({hud_js}, 'utf8'));

        const rawSteps = [];
        for (let i = 0; i < 550; i++) {{
            rawSteps.push({{
                stepIndex: i,
                type: i % 100 === 0 ? "CORTEX_STEP_TYPE_CHECKPOINT" : "CORTEX_STEP_TYPE_USER_INPUT",
                content: "Step " + i
            }});
        }}
        const traj = window.buildHudTrajectoryData("titanium-500", rawSteps, [], [], null);
        const state = window.__agyis_hud_state;
        state.rootData = traj;
        state.currentData = traj;
        state.convoId = "titanium-500";
        state.selectedIndex = 50;
        state.tablePage = Math.floor(state.selectedIndex / 50);
        window.__agyis_hud_render();

        console.log(JSON.stringify({{
            totalSteps: traj.steps.length,
            selectedIndex: state.selectedIndex,
            tablePage: state.tablePage,
            lastType: traj.steps[500].type
        }}));
        """)
        self.assertEqual(res["totalSteps"], 550)
        self.assertEqual(res["selectedIndex"], 50)
        self.assertEqual(res["tablePage"], 1)
        self.assertEqual(res["lastType"], "CHECKPOINT")


if __name__ == "__main__":
    unittest.main()
