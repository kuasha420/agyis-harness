#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Arafat Zahan (@kuasha420)
# Corporate Stewardship & Infrastructure: Purrfect Software Limited (PSL)
# Governed by: ICARO-42/b Ordinance (Company-Supported Personal IP Framework)

"""
HUD JS dynamic context, epoch partitioning, and Antigravity v2.34.0 GUI compatibility tests.
Split from test_gui.py for sub-second ADR-015 verification.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
from unittest.mock import MagicMock, patch

from harness.commands.gui import find_page_target, inject_trajectory_debug
from harness.gui.trajectory_hud import (
    atc_context_layout,
    build_trajectory_hud_script,
    load_conversation_trajectory,
    ztc_row_count,
)


class TestHudJsDynamicContextAndEpochs(unittest.TestCase):
    """Track 6: End-to-end Node.js evaluation of hud.js epoch boundaries and dynamic context capacity."""

    def test_hud_js_epoch_splitting_nested_cwm_and_dynamic_rows_in_node(self) -> None:
        import shutil
        import subprocess

        if not shutil.which("node"):
            self.skipTest("node binary unavailable")

        script = build_trajectory_hud_script(
            convo_id="init-convo",
            trajectory_data={"conversation_id": "init-convo", "steps": []},
            conversations=[{"id": "route_test_1", "summary": '<img src=x onerror="alert(1)">', "mtime": 1700000000}],
            open_view=True,
            toggle=False,
        )

        # Build a hermetic Node DOM/fetch harness that runs the actual compiled hud.js script
        harness_prefix = """
const createdEls = [];
function mkEl(tag) {
    return {
        tagName: String(tag || "div").toUpperCase(),
        id: "",
        style: {},
        innerHTML: "",
        innerText: "",
        textContent: "",
        children: [],
        value: "",
        addEventListener() {},
        removeEventListener() {},
        appendChild(c) { this.children.push(c); return c; },
        remove() {},
        querySelector() { return null; },
        querySelectorAll() { return []; },
        scrollIntoView() {},
        getAttribute() { return null; },
        setAttribute() {},
    };
}
const hudContainer = mkEl("div");
let capturedHudDiv = null;
const document = {
    getElementById(id) {
        if (id === "agyis-trajectory-hud" && capturedHudDiv !== null) return hudContainer;
        return null;
    },
    createElement(tag) {
        if (tag === "div" && capturedHudDiv === null) {
            capturedHudDiv = hudContainer;
            return hudContainer;
        }
        const el = mkEl(tag);
        createdEls.push(el);
        return el;
    },
    head: { appendChild() {} },
    body: { appendChild() {} },
    querySelector() { return null; },
    addEventListener() {},
};
const winListeners = {};
const loadCalls = [];
const window = {
    location: { origin: "https://127.0.0.1:40623", pathname: "/c/init-convo" },
    addEventListener(ev, fn) { (winListeners[ev] = winListeners[ev] || []).push(fn); },
    removeEventListener(ev, fn) {
        if (!winListeners[ev]) return;
        winListeners[ev] = winListeners[ev].filter(f => f !== fn);
    },
    dispatchEvent(ev) {
        const list = winListeners[ev && ev.type] || [];
        for (const fn of list) fn(ev);
    },
    __APP_CONFIG__: { csrfToken: "test-csrf" },
};
function Event(type) { this.type = type; }
let mockScenario = null;
async function fetch(url, opts) {
    if (opts && opts.body) {
        try {
            const parsed = JSON.parse(opts.body);
            if (parsed.cascadeId && url.endsWith("/GetCascadeTrajectorySteps")) {
                loadCalls.push(parsed.cascadeId);
            }
        } catch (_) {}
    }
    return {
        ok: true,
        async json() {
            if (url.endsWith("/GetCascadeTrajectorySteps")) {
                return { steps: mockScenario.steps };
            }
            if (url.endsWith("/GetCascadeTrajectoryGeneratorMetadata")) {
                return { generatorMetadata: mockScenario.genMetas };
            }
            if (url.endsWith("/GetCascadeTrajectoryExecutorMetadatas")) {
                return { executorMetadatas: [] };
            }
            return {};
        },
    };
}
"""

        harness_suffix = """
(async () => {
    // Scenario 1: 512k model with chatStartMetadata.checkpointIndex back-references (must NOT split epochs)
    mockScenario = {
        steps: [
            { type: "CORTEX_STEP_TYPE_USER_INPUT", userInput: { userResponse: "Fix context window" } },
            { type: "CORTEX_STEP_TYPE_PLANNER_RESPONSE", plannerResponse: { response: "Inspecting files", thinking: "plan" } },
            { type: "CORTEX_STEP_TYPE_RUN_COMMAND", runCommand: { commandLine: "pytest", exitCode: 0 } },
            { type: "CORTEX_STEP_TYPE_PLANNER_RESPONSE", plannerResponse: { response: "All tests pass" } },
        ],
        genMetas: [
            {
                stepIndex: 1,
                chatStartMetadata: {
                    checkpointIndex: 0,
                    contextWindowMetadata: { estimatedTokensUsed: 120000, maxContextTokens: 512000 },
                },
            },
            {
                stepIndex: 3,
                chatStartMetadata: {
                    checkpointIndex: 0,
                    contextWindowMetadata: { estimatedTokensUsed: 374475, maxContextTokens: 512000 },
                },
            },
        ],
    };
    const data512 = await window.__agyis_hud_load_convo("convo-512k");
    const html512 = hudContainer.innerHTML;
    window.__agyis_hud_state.mainDeckTab = "timeline";
    window.__agyis_hud_render();
    const timelineHtml512 = hudContainer.innerHTML;

    // Scenario 2: Real CHECKPOINT + 1M context via metadata.chatStartMetadata.contextWindowMetadata (>750k -> 4 rows)
    window.__agyis_hud_state.mainDeckTab = "context";
    mockScenario = {
        steps: [
            { type: "CORTEX_STEP_TYPE_USER_INPUT", content: "A".repeat(70000) },
            { type: "CORTEX_STEP_TYPE_CHECKPOINT", checkpoint: { checkpointIndex: 1, sessionSummary: "Compacted turn 1" } },
            { type: "CORTEX_STEP_TYPE_USER_INPUT", userInput: { userResponse: "Continue" } },
            { type: "CORTEX_STEP_TYPE_PLANNER_RESPONSE", plannerResponse: { response: "Continuing on 1M window" } },
        ],
        genMetas: [
            {
                stepIndex: 3,
                chatStartMetadata: { checkpointIndex: 1 },
                metadata: {
                    chatStartMetadata: {
                        contextWindowMetadata: { estimatedTokensUsed: 800000, maxContextTokens: 1000000 },
                    },
                },
            },
        ],
    };
    const data1m = await window.__agyis_hud_load_convo("convo-1m");
    const html1m = hudContainer.innerHTML;
    // Switch back to historical Epoch 0: must render Epoch 0's own ~20k tokens / 1 row, NOT Epoch 1's 800k / unattributed
    window.__agyis_hud_state.activeEpochIndex = 0;
    window.__agyis_hud_render();
    const html1mEp0 = hudContainer.innerHTML;
    window.__agyis_hud_state.activeEpochIndex = 1;
    window.__agyis_hud_state.mainDeckTab = "timeline";
    window.__agyis_hud_render();
    const timelineHtml1m = hudContainer.innerHTML;

    // Scenario 3: Small estimatedTokensUsed (< activeEpochTokens + 7000) keeps total_tokens == sum(token_breakdown)
    mockScenario = {
        steps: [
            { type: "CORTEX_STEP_TYPE_USER_INPUT", content: "A".repeat(35000) },
            { type: "CORTEX_STEP_TYPE_PLANNER_RESPONSE", plannerResponse: { response: "B".repeat(3500) } },
        ],
        genMetas: [
            {
                stepIndex: 1,
                chatStartMetadata: {
                    contextWindowMetadata: { estimatedTokensUsed: 5000, maxContextTokens: 256000 },
                },
            },
        ],
    };
    const dataSmall = await window.__agyis_hud_load_convo("convo-small-est");

    // Scenario 4: Out-of-order stepIndex + authoritative modelUsage (inputTokens + cacheReadTokens) + >100% fill clamping
    mockScenario = {
        steps: [
            {
                stepIndex: 2,
                type: "CORTEX_STEP_TYPE_PLANNER_RESPONSE",
                plannerResponse: { response: "Done" },
                metadata: { modelUsage: { inputTokens: 20000, cacheReadTokens: 280000, outputTokens: 500 } },
            },
            { stepIndex: 0, type: "CORTEX_STEP_TYPE_USER_INPUT", userInput: { userResponse: "First message" } },
            { stepIndex: 1, type: "CORTEX_STEP_TYPE_RUN_COMMAND", runCommand: { commandLine: "ls", exitCode: 0 } },
        ],
        genMetas: [
            { stepIndex: 2, chatStartMetadata: { contextWindowMetadata: { maxContextTokens: 256000 } } },
        ],
    };
    window.__agyis_hud_state.mainDeckTab = "context";
    const dataAuth = await window.__agyis_hud_load_convo("convo-auth-oo-clamp");
    window.__agyis_hud_render();
    const htmlAuth = hudContainer.innerHTML;

    // Scenario 5: SPA routechange/popstate with underscore slug + subagent UUID filtering + HTML escaping
    mockScenario = {
        steps: [
            {
                type: "CORTEX_STEP_TYPE_RUN_COMMAND",
                runCommand: { commandLine: "echo ok", exitCode: 0, combinedOutput: { full: "unrelated 11111111-1111-1111-1111-111111111111" } },
            },
            {
                type: "CORTEX_STEP_TYPE_INVOKE_SUBAGENT",
                plannerResponse: {
                    toolCalls: [{
                        name: "invoke_subagent",
                        argumentsJson: JSON.stringify({ Role: '<b onclick="xss()">Scout</b>', Prompt: "Check" }),
                    }],
                },
                invokeSubagent: {
                    subagents: [{ conversationId: "22222222-2222-2222-2222-222222222222", role: '<b onclick="xss()">Scout</b>' }],
                },
            },
        ],
        genMetas: [],
    };
    window.location.pathname = "/c/route_test_1";
    window.dispatchEvent(new Event("agyis:routechange"));
    await new Promise(r => setTimeout(r, 15));
    window.location.pathname = "/c/route-test-2";
    window.dispatchEvent(new Event("popstate"));
    await new Promise(r => setTimeout(r, 15));
    window.__agyis_hud_state.filterQuery = '" onfocus="alert(2)';
    window.__agyis_hud_render();
    const htmlEscaped = hudContainer.innerHTML;
    const s5Subagents = (window.__agyis_hud_state.currentData && window.__agyis_hud_state.currentData.subagents) || [];

    // Scenario 6: #107.1 / #108.2 / #108.4 / #108.5
    mockScenario = {
        steps: [
            { type: "CORTEX_STEP_TYPE_GENERIC", generic: { text: "<summary>Harmless generic output</summary>" } },
            {
                type: "CORTEX_STEP_TYPE_VIEW_FILE",
                viewFile: {
                    absolutePathUri: "/workspace/README.md",
                    content: "<CONTEXT_SUMMARY>false alarm inside view_file</CONTEXT_SUMMARY>\\n" + ("R".repeat(7000)),
                },
            },
            {
                type: "CORTEX_STEP_TYPE_RUN_COMMAND",
                runCommand: {
                    commandLine: "cat transcript.jsonl",
                    exitCode: 0,
                    combinedOutput: { full: ("C".repeat(7000)) + "\\n<summary>quoted stdout</summary>" },
                },
            },
            { type: "CORTEX_STEP_TYPE_PLANNER_RESPONSE", plannerResponse: { response: "Analyzing <summary> tag in markdown" } },
            {
                type: "CORTEX_STEP_TYPE_CHECKPOINT",
                checkpoint: { sessionSummary: "Real epoch boundary checkpoint" },
            },
            {
                type: "CORTEX_STEP_TYPE_PLANNER_RESPONSE",
                plannerResponse: { response: "Epoch 2 resumed step" },
                metadata: { modelUsage: { inputTokens: 8000, cacheReadTokens: 48000 } },
            },
        ],
        genMetas: [
            { stepIndex: 99, chatStartMetadata: { contextWindowMetadata: { maxContextTokens: 1000000 } } },
            { stepIndices: [3], chatStartMetadata: { contextWindowMetadata: { maxContextTokens: 256000 } } },
            { stepIndices: [4], chatStartMetadata: { contextWindowMetadata: { maxContextTokens: 256000 } } },
            { chatStartMetadata: { contextWindowMetadata: { maxContextTokens: 512000 } } },
        ],
    };
    window.__agyis_hud_state.filterQuery = "";
    window.__agyis_hud_state.mainDeckTab = "context";
    const dataS6 = await window.__agyis_hud_load_convo("convo-s6-epoch-and-tools");
    window.__agyis_hud_render();
    const htmlS6Ep1 = hudContainer.innerHTML;
    window.__agyis_hud_state.activeEpochIndex = 0;
    window.__agyis_hud_render();
    const htmlS6Ep0 = hudContainer.innerHTML;

    console.log(JSON.stringify({
        s1_epochs: data512.epochs.length,
        s1_has_cp: data512.epochs[0].has_checkpoint,
        s1_max_ctx: data512.max_context_tokens,
        s1_total_tok: data512.total_tokens,
        s1_html: html512,
        s1_timeline: timelineHtml512,
        s2_epochs: data1m.epochs.length,
        s2_max_ctx: data1m.max_context_tokens,
        s2_total_tok: data1m.total_tokens,
        s2_user_tok: data1m.token_breakdown.user,
        s2_breakdown_sum: Object.values(data1m.token_breakdown || {}).reduce((a, b) => a + b, 0),
        s2_html: html1m,
        s2_ep0_html: html1mEp0,
        s2_timeline: timelineHtml1m,
        s3_total_tok: dataSmall.total_tokens,
        s3_breakdown_sum: Object.values(dataSmall.token_breakdown || {}).reduce((a, b) => a + b, 0),
        s3_provisional: dataSmall.is_provisional,
        s4_order: dataAuth.steps.map(s => s.step_index),
        s4_cache_tokens: dataAuth.cache_tokens,
        s4_provisional: dataAuth.is_provisional,
        s4_total_tok: dataAuth.total_tokens,
        s4_html: htmlAuth,
        s5_loads: loadCalls,
        s5_subagents: s5Subagents,
        s5_html: htmlEscaped,
        s6_epochs: dataS6.epochs.length,
        s6_view_tok: (dataS6.steps[1] && dataS6.steps[1].tokens) || 0,
        s6_cmd_tok: (dataS6.steps[2] && dataS6.steps[2].tokens) || 0,
        s6_ep1_cache: dataS6.epochs[1] ? dataS6.epochs[1].cache_tokens : -1,
        s6_total_tok: dataS6.total_tokens,
        s6_max_ctx: dataS6.max_context_tokens,
        s6_ep0_html: htmlS6Ep0,
        s6_ep1_html: htmlS6Ep1,
    }));
})();
"""
        res = subprocess.run(
            ["node", "-"],
            input=harness_prefix + "\n" + script + "\n" + harness_suffix,
            capture_output=True,
            text=True,
            check=True,
        )
        out = json.loads(res.stdout.strip())

        # Scenario 1 assertions (374,475 / 512,000 -> ceil(374475 / 128000) = 3 rows: 0k, 128k, 256k)
        self.assertEqual(out["s1_epochs"], 1, "chatStartMetadata.checkpointIndex must NOT split epochs")
        self.assertFalse(out["s1_has_cp"])
        self.assertEqual(out["s1_max_ctx"], 512000)
        self.assertEqual(out["s1_total_tok"], 374475)
        for label in ("0k", "128k", "256k"):
            self.assertIn(f">{label}</span>", out["s1_html"])
        self.assertNotIn(">384k</span>", out["s1_html"])
        self.assertIn("512k Context &bull; Live Trace", out["s1_timeline"])
        self.assertNotIn("256k Context Parity", out["s1_timeline"])
        self.assertIn("Active Context:", out["s1_html"])
        self.assertNotIn("/ 384,000 tokens", out["s1_html"])

        # Scenario 2 assertions (800,000 / 1,000,000 -> ceil(800000 / 250000) = 4 rows: 0k, 250k, 500k, 750k)
        self.assertEqual(out["s2_epochs"], 2)
        self.assertEqual(out["s2_max_ctx"], 1000000)
        self.assertEqual(out["s2_total_tok"], 800000)
        # Pre-checkpoint step had 20,000 tokens ("A"*70000 / 3.5); active epoch user step ("Continue") is ~2 tokens
        self.assertLess(out["s2_user_tok"], 100, "Pre-checkpoint user tokens must NOT inflate active epoch breakdown")
        self.assertEqual(out["s2_breakdown_sum"], 800000)
        for label in ("0k", "250k", "500k", "750k"):
            self.assertIn(f">{label}</span>", out["s2_html"])
        self.assertIn("1M Context &bull; Live Trace", out["s2_timeline"])
        self.assertNotIn("/ 1,000,000 tokens", out["s2_html"])

        # Scenario 3 assertion: total_tokens matches sum(token_breakdown) and marks provisional estimate
        self.assertEqual(out["s3_total_tok"], out["s3_breakdown_sum"])
        self.assertGreater(out["s3_total_tok"], 5000)
        self.assertTrue(out["s3_provisional"])

        # Scenario 4 assertions: out-of-order stepIndex sorted chronologically, authoritative UsageMetadata, clamped fill <= 100%
        self.assertEqual(out["s4_order"], [0, 1, 2])
        self.assertEqual(out["s4_cache_tokens"], 280000)
        self.assertFalse(out["s4_provisional"])
        self.assertEqual(out["s4_total_tok"], 300000)
        self.assertIn("100.0% over", out["s4_html"])
        self.assertIn("Cache: 280.0k", out["s4_html"])

        # Historical Epoch 0 assertions: must use Epoch 0's ~20k measured tokens and 1 row, NOT Epoch 1's 800k/Unattributed
        self.assertIn("Epoch 1 of 2", out["s2_ep0_html"])
        self.assertIn("Context Window (1 row)", out["s2_ep0_html"])
        self.assertNotIn("800,000", out["s2_ep0_html"])
        self.assertNotIn("Unattributed Overhead", out["s2_ep0_html"])

        # Scenario 5 assertions: SPA routechange/popstate, subagent UUID filtering, HTML escaping
        self.assertIn("route_test_1", out["s5_loads"])
        self.assertIn("route-test-2", out["s5_loads"])
        self.assertEqual(out["s5_subagents"], ["22222222-2222-2222-2222-222222222222"])
        self.assertNotIn("<img src=x", out["s5_html"])
        self.assertNotIn('<b onclick="xss()">', out["s5_html"])
        self.assertNotIn('" onfocus="alert(2)', out["s5_html"])
        self.assertIn("&lt;img src=x", out["s5_html"])

        # Scenario 6 assertions (#107.1, #108.2, #108.4, #108.5)
        self.assertEqual(out["s6_epochs"], 2, "Fake <summary>/<CONTEXT_SUMMARY> inside non-checkpoint steps must NOT split epochs")
        self.assertGreater(out["s6_view_tok"], 1500, "viewFile.content chars must be included in stepTok before breakdown")
        self.assertGreater(out["s6_cmd_tok"], 1500, "runCommand.combinedOutput.full chars must be included in stepTok before breakdown")
        self.assertEqual(out["s6_ep1_cache"], 48000)
        self.assertEqual(out["s6_total_tok"], 56000)
        self.assertEqual(out["s6_max_ctx"], 512000)
        # Historical Epoch 0 vs Authoritative Epoch 1 header badges (#108.4)
        self.assertIn("~est", out["s6_ep0_html"])
        self.assertNotIn("Cache: 48.0k", out["s6_ep0_html"])
        self.assertNotIn("~est", out["s6_ep1_html"])
        self.assertIn("Cache: 48.0k", out["s6_ep1_html"])
        self.assertIn("Active Context: <b style=\"color: #38bdf8;\">56,000</b>", out["s6_ep1_html"])

    def test_extract_hud_focused_convo_id_precedence_in_node(self) -> None:
        import importlib.resources
        import shutil
        import subprocess

        if not shutil.which("node"):
            self.skipTest("node binary unavailable")

        assets = importlib.resources.files("harness.gui.assets")
        hud_js = assets.joinpath("hud.js").read_text(encoding="utf-8")

        node_script = """
global.document = {
    getElementById(id) { return null; },
    createElement(tag) { return { id: "", style: {}, appendChild() {}, remove() {} }; },
    head: { appendChild() {} },
    body: { appendChild() {} },
    querySelector() { return null; },
    addEventListener() {},
    removeEventListener() {},
};
global.window = {
    location: { origin: "https://127.0.0.1:40623", pathname: "/c/init-convo", search: "" },
    addEventListener() {},
    removeEventListener() {},
};
""" + hud_js + """

// Test Case 1: Route UUID should take precedence over generic pane ID like "pane-1"
window.location = { pathname: "/c/uuid-route-1234-5678", search: "" };
global.document.querySelector = function(sel) {
    if (sel.includes("data-pane-id")) {
        return { getAttribute(a) { return a === "data-pane-id" ? "pane-1" : null; } };
    }
    return null;
};
const res1 = window.__agyis_extract_convo_id();
if (res1 !== "uuid-route-1234-5678") {
    console.error("FAIL 1: expected route uuid, got " + res1);
    process.exit(1);
}

// Test Case 2: If no route, but pane has a valid UUID, use pane UUID
window.location = { pathname: "/", search: "" };
global.document.querySelector = function(sel) {
    return { getAttribute(a) { return "e8c67662-8c67-4674-b4f0-4760bd3fec59"; } };
};
const res2 = window.__agyis_extract_convo_id();
if (res2 !== "e8c67662-8c67-4674-b4f0-4760bd3fec59") {
    console.error("FAIL 2: expected valid pane uuid, got " + res2);
    process.exit(1);
}

// Test Case 3: If no route and generic pane ID "pane-2", reject pane ID and fallback to search param
window.location = { pathname: "/", search: "?cascadeId=cascade-uuid-9999" };
global.document.querySelector = function(sel) {
    return { getAttribute(a) { return "pane-2"; } };
};
const res3 = window.__agyis_extract_convo_id();
if (res3 !== "cascade-uuid-9999") {
    console.error("FAIL 3: expected search param fallback, got " + res3);
    process.exit(1);
}

// Test Case 4: If viewing a subagent tab, subagent tab UUID takes precedence over parent route UUID
window.location = { pathname: "/c/parent-uuid-1111", search: "?tab=subagent_convo__b5796a47-98bf-499f-b185-2d2f5f7977e0" };
const res4 = window.__agyis_extract_convo_id();
if (res4 !== "b5796a47-98bf-499f-b185-2d2f5f7977e0") {
    console.error("FAIL 4: expected subagent tab uuid, got " + res4);
    process.exit(1);
}

console.log("PASS");
"""
        proc = subprocess.run(["node", "-e", node_script], capture_output=True, text=True)
        self.assertEqual(proc.returncode, 0, f"Node extraction failed: {proc.stderr}")
        self.assertIn("PASS", proc.stdout)

    def test_subagent_convo_id_extraction_with_both_hotkey_and_hud_loaded(self) -> None:
        """Asserts subagent convo ID extraction when both hotkey.js and hud.js are loaded (DEF-BB-010)."""
        import importlib.resources
        import shutil
        import subprocess

        if not shutil.which("node"):
            self.skipTest("node binary unavailable")

        assets = importlib.resources.files("harness.gui.assets")
        hotkey_js = assets.joinpath("hotkey.js").read_text(encoding="utf-8")
        hud_js = assets.joinpath("hud.js").read_text(encoding="utf-8")

        node_script = """
global.document = {
    getElementById(id) { return null; },
    createElement(tag) { return { id: "", style: {}, appendChild() {}, remove() {} }; },
    head: { appendChild() {} },
    body: { appendChild() {} },
    querySelector() { return null; },
    querySelectorAll() { return []; },
    addEventListener() {},
    removeEventListener() {},
};
global.window = {
    location: { origin: "https://127.0.0.1:33315", pathname: "/c/parent-1111", search: "?tab=subagent_convo__sub-2222" },
    addEventListener() {},
    removeEventListener() {},
};
""" + hotkey_js + "\n" + hud_js + """
// 1. Both detectors must return subagent ID when tab parameter is present
const detectedFromHotkey = window.detectActiveConversationContext();
if (detectedFromHotkey !== "sub-2222") {
    console.error("FAIL: detectActiveConversationContext returned " + detectedFromHotkey + ", expected sub-2222");
    process.exit(1);
}
const detectedFromHud = window.__agyis_extract_convo_id();
if (detectedFromHud !== "sub-2222") {
    console.error("FAIL: __agyis_extract_convo_id returned " + detectedFromHud + ", expected sub-2222");
    process.exit(1);
}

// 2. When subagent tab is absent, fall back to pathname /c/:id
window.location.search = "";
window.location.pathname = "/c/parent-1111";
const parentFromHotkey = window.detectActiveConversationContext();
if (parentFromHotkey !== "parent-1111") {
    console.error("FAIL: expected parent-1111 from hotkey, got " + parentFromHotkey);
    process.exit(1);
}
const parentFromHud = window.__agyis_extract_convo_id();
if (parentFromHud !== "parent-1111") {
    console.error("FAIL: expected parent-1111 from hud, got " + parentFromHud);
    process.exit(1);
}

console.log("PASS");
"""
        proc = subprocess.run(["node", "-e", node_script], capture_output=True, text=True)
        self.assertEqual(proc.returncode, 0, f"Node subagent extraction failed: {proc.stderr}")
        self.assertIn("PASS", proc.stdout)

    def test_hud_rpc_dynamic_port_fallback(self) -> None:
        """Asserts InSituConnectClient port fallback reads window.location.port on loopback https (DEF-BB-012)."""
        import importlib.resources
        import shutil
        import subprocess

        if not shutil.which("node"):
            self.skipTest("node binary unavailable")

        assets = importlib.resources.files("harness.gui.assets")
        hud_rpc_js = assets.joinpath("hud_rpc.js").read_text(encoding="utf-8")

        node_script = """
global.window = {
    location: { protocol: "https:", hostname: "127.0.0.1", port: "33315", origin: "https://127.0.0.1:33315" },
    __APP_CONFIG__: { csrfToken: "csrf-test" },
};
""" + hud_rpc_js + """
const client1 = new window.InSituConnectClient();
if (client1.port !== 33315) {
    console.error("FAIL: client1.port expected 33315, got " + client1.port);
    process.exit(1);
}
if (client1.baseUrl !== "https://127.0.0.1:33315") {
    console.error("FAIL: client1.baseUrl expected https://127.0.0.1:33315, got " + client1.baseUrl);
    process.exit(1);
}

// Loopback with localhost
window.location = { protocol: "https:", hostname: "localhost", port: "49999", origin: "https://localhost:49999" };
const client2 = new window.InSituConnectClient();
if (client2.port !== 49999) {
    console.error("FAIL: client2.port expected 49999, got " + client2.port);
    process.exit(1);
}
if (client2.baseUrl !== "https://localhost:49999") {
    console.error("FAIL: client2.baseUrl expected https://localhost:49999, got " + client2.baseUrl);
    process.exit(1);
}

console.log("PASS");
"""
        proc = subprocess.run(["node", "-e", node_script], capture_output=True, text=True)
        self.assertEqual(proc.returncode, 0, f"Dynamic port fallback test failed: {proc.stderr}")
        self.assertIn("PASS", proc.stdout)

    def test_stream_render_coordinator_raf_batching_in_node(self) -> None:
        """Asserts StreamRenderCoordinator batches deltas at 60 FPS via rAF queue (DEF-BB-011)."""
        import importlib.resources
        import shutil
        import subprocess

        if not shutil.which("node"):
            self.skipTest("node binary unavailable")

        assets = importlib.resources.files("harness.gui.assets")
        hud_rpc_js = assets.joinpath("hud_rpc.js").read_text(encoding="utf-8")

        node_script = """
let rafCallbacks = [];
global.requestAnimationFrame = function(cb) {
    rafCallbacks.push(cb);
    return rafCallbacks.length;
};
global.window = {};
""" + hud_rpc_js + """
let renderCallCount = 0;
let lastRenderedState = null;
const coordinator = new window.StreamRenderCoordinator((state, dirty) => {
    renderCallCount++;
    lastRenderedState = state;
});

// Rapidly ingest 5 delta updates in a single frame
for (let i = 0; i < 5; i++) {
    coordinator.ingestUpdate({
        conversationId: "test-convo-stream",
        mainTrajectoryUpdate: {
            stepsUpdate: {
                indices: [i],
                steps: [{ stepIndex: i, type: "MODEL_OUTPUT", content: "Delta frame #" + i }]
            }
        }
    });
}

// Before rAF fires: exactly 1 rAF request scheduled, 0 renders executed
if (rafCallbacks.length !== 1) {
    console.error("FAIL: expected 1 rAF callback scheduled, got " + rafCallbacks.length);
    process.exit(1);
}
if (renderCallCount !== 0) {
    console.error("FAIL: render should not be called synchronously before rAF, called: " + renderCallCount);
    process.exit(1);
}

// Fire the scheduled rAF frame
const frameCallback = rafCallbacks.shift();
frameCallback();

if (renderCallCount !== 1) {
    console.error("FAIL: expected 1 batched render call, got " + renderCallCount);
    process.exit(1);
}
if (!lastRenderedState || lastRenderedState.stepsInSlice.length !== 5) {
    console.error("FAIL: expected 5 steps in slice after batch, got " + (lastRenderedState ? lastRenderedState.stepsInSlice.length : null));
    process.exit(1);
}

console.log("PASS");
"""
        proc = subprocess.run(["node", "-e", node_script], capture_output=True, text=True)
        self.assertEqual(proc.returncode, 0, f"StreamRenderCoordinator test failed: {proc.stderr}")
        self.assertIn("PASS", proc.stdout)

    def test_inject_trajectory_debug_prioritizes_subagent_tab(self) -> None:
        """Asserts inject_trajectory_debug detects tab=subagent_convo__ and sets parent_id (DEF-BB-010)."""
        mock_client = MagicMock()
        mock_client.evaluate.return_value = (
            "https://127.0.0.1:33315/c/parent-1111?project=proj-abc&tab=subagent_convo__sub-2222"
        )
        mock_client.send_command.return_value = {"scriptId": "1"}

        with patch("harness.gui.trajectory_hud.load_conversation_trajectory") as mock_load, \
             patch("harness.gui.trajectory_hud.build_trajectory_hud_script") as mock_build, \
             patch("harness.commands.gui.build_hotkey_script") as mock_hotkey, \
             patch("harness.commands.gui.discover_language_server_endpoint") as mock_ls, \
             patch("harness.gui.server.ensure_trajectory_server"):
            mock_ls.return_value = {"port": 33315, "url": "https://127.0.0.1:33315"}
            mock_load.return_value = {"conversation_id": "sub-2222", "parent_id": "parent-1111", "steps": []}
            mock_build.return_value = "/* hud_script */"
            mock_hotkey.return_value = "/* hotkey_script */"

            res = inject_trajectory_debug(client=mock_client)
            self.assertTrue(res.get("success"))
            self.assertEqual(res.get("convo_id"), "sub-2222")

            # Assert load_conversation_trajectory was called with convo_id='sub-2222' and parent_id='parent-1111'
            mock_load.assert_called_once()
            args, kwargs = mock_load.call_args
            self.assertEqual(args[0], "sub-2222")
            self.assertEqual(kwargs.get("parent_id"), "parent-1111")


class TestV234GuiAndHudCompatibility(unittest.TestCase):
    """Regression tests for Antigravity v2.34.0 GUI, CDP, and HUD compatibility."""

    def test_install_cdp_launcher_writes_desktop_file(self) -> None:
        from harness.gui.launcher import install_cdp_launcher

        with tempfile.TemporaryDirectory() as tmp:
            desktop_path = Path(tmp) / "applications" / "antigravity.desktop"
            res = install_cdp_launcher(desktop_path=desktop_path, system_desktop_path=Path(tmp) / "missing.desktop")
            self.assertTrue(res["success"])
            self.assertTrue(desktop_path.is_file())
            content = desktop_path.read_text(encoding="utf-8")
            self.assertIn("Exec=/usr/bin/antigravity --remote-debugging-port=0 %U", content)

    def test_detect_antigravity_without_cdp_filters_helpers(self) -> None:
        from harness.gui.launcher import detect_antigravity_without_cdp

        with tempfile.TemporaryDirectory() as tmp:
            proc = Path(tmp)
            (proc / "101").mkdir()
            (proc / "101" / "cmdline").write_bytes(b"/opt/Antigravity/antigravity\x00--no-sandbox\x00")
            (proc / "102").mkdir()
            (proc / "102" / "cmdline").write_bytes(b"/opt/Antigravity/antigravity\x00--type=renderer\x00")
            (proc / "103").mkdir()
            (proc / "103" / "cmdline").write_bytes(b"/opt/Antigravity/antigravity\x00--remote-debugging-port=0\x00")

            found = detect_antigravity_without_cdp(proc_root=proc)
            self.assertEqual([p["pid"] for p in found], [101])

    def test_find_page_target_prefers_hub_port_over_playback_and_browser_wcv(self) -> None:
        targets = [
            {"id": "WCV1", "type": "page", "title": "Local App", "url": "http://127.0.0.1:40624/c/other"},
            {"id": "WCV2", "type": "page", "title": "Dev App", "url": "http://127.0.0.1:5173/c/dev"},
            {"id": "HUB1", "type": "page", "title": "Antigravity", "url": "https://127.0.0.1:40729/c/abc"},
        ]
        chosen = find_page_target(targets, expected_hub_port=40729)
        self.assertIsNotNone(chosen)
        self.assertEqual(chosen["id"], "HUB1")

        chosen_no_hint = find_page_target(targets)
        self.assertIsNotNone(chosen_no_hint)
        self.assertEqual(chosen_no_hint["id"], "HUB1")

    def test_hud_js_assets_v234_contracts(self) -> None:
        from harness.commands.gui import _load_gui_asset

        rpc_js = _load_gui_asset("hud_rpc.js")
        self.assertIn("agy_session_csrf_token", rpc_js)
        self.assertIn("trajectoryVerbosity: 3", rpc_js)
        self.assertIn("execJson.executorMetadata", rpc_js)
        self.assertIn("update.contextWindowUsage", rpc_js)
        self.assertIn("cwm.maxContextTokens", rpc_js)
        self.assertIn("gType === 8 || gType === 9 || gType === 10", rpc_js)
        self.assertIn('"GENERIC"', rpc_js)

        hud_js = _load_gui_asset("hud.js")
        self.assertIn("window.__agyis_hud_mount", hud_js)
        self.assertIn("CSS.escape", hud_js)

        hotkey_js = _load_gui_asset("hotkey.js")
        self.assertIn('searchParams.get("focused")', hotkey_js)

        header_js = _load_gui_asset("hud_header.js")
        self.assertNotIn("text-muted-foreground shrink-0", header_js)

    def test_discover_ls_endpoint_rejects_plain_text_401(self) -> None:
        import urllib.error
        from harness.commands.gui import discover_language_server_endpoint

        def _fake_urlopen(req, timeout=0.25, context=None):
            if ":41335/" in req.full_url:
                raise urllib.error.HTTPError(
                    req.full_url, 401, "Unauthorized", {"Content-Type": "text/plain"}, None
                )
            raise urllib.error.HTTPError(
                req.full_url, 401, "Unauthorized", {"Content-Type": "application/json"}, None
            )

        with patch("subprocess.check_output", return_value=""), \
             patch("urllib.request.urlopen", side_effect=_fake_urlopen):
            ep = discover_language_server_endpoint(candidate_ports=[41335, 42381])
            self.assertIsNotNone(ep)
            self.assertEqual(ep["port"], 42381)


if __name__ == "__main__":
    unittest.main()
