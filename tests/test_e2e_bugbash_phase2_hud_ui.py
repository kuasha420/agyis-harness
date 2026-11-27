#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Arafat Zahan (@kuasha420)
# Corporate Stewardship & Infrastructure: Purrfect Software Limited (PSL)
# Governed by: ICARO-42/b Ordinance (Company-Supported Personal IP Framework)

"""
Bug Bash Phase 2 — Frontier 1 HUD Context, Header, Dropdown & Context Bar (F01-F04, T2 B01).
Executes real hotkey.js, hud_header.js, hud_context_bar.js, hud.js, and trajectory_hud.py.
Split from test_e2e_bugbash_phase2.py for sub-second ADR-015 verification.
"""

from __future__ import annotations

import importlib.resources
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import time
import unittest

from harness.gui.trajectory_hud import (
    atc_context_layout,
    get_recent_conversations,
    load_conversation_trajectory,
    ztc_row_count,
)


_UI_DOM_PREAMBLE = r"""
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
                } else if (sel.includes("data-pane-id")) {
                    if (node.getAttribute("data-pane-id") !== null && node.getAttribute("data-pane-unfocused") === null) {
                        results.push(node);
                    }
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
const searchInput = makeElement("input");
searchInput.id = "agyis-search-input";
hudRoot.appendChild(searchInput);

const document = {
    body: makeElement("body"),
    head: makeElement("head"),
    activeElement: null,
    getElementById(id) {
        if (id === "agyis-trajectory-hud") return hudRoot;
        if (id === "agyis-search-input") return searchInput;
        return this.head.querySelector("#" + id) || this.body.querySelector("#" + id);
    },
    createElement(tag) { return makeElement(tag); },
    querySelector(sel) { return this.body.querySelector(sel) || hudRoot.querySelector(sel); },
    querySelectorAll(sel) { return hudRoot.querySelectorAll(sel); },
    addEventListener() {},
    removeEventListener() {},
};
document.body.appendChild(hudRoot);
document.activeElement = document.body;

const window = {
    location: { origin: "https://127.0.0.1:40623", pathname: "/c/convo-root", search: "" },
    addEventListener() {},
    removeEventListener() {},
    dispatchEvent() {},
    __agyis_hud_state: {
        convoId: "convo-root",
        selectedIndex: 0,
        activeCheckpointIndex: 0,
        tablePage: 0,
        isMaximized: false,
        filterQuery: "",
        subagentsDropdownOpen: false,
        rootData: null,
        currentData: null,
    },
    document,
};
global.window = window;
global.document = document;
"""


class TestPhase2HudUiAndContextBar(unittest.TestCase):
    """Real Node.js + Python E2E verification for HUD context detection, header rendering, and context bar."""

    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.ws = Path(self.temp_dir.name).resolve()

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def _run_node(self, js_body: str) -> dict:
        node_bin = shutil.which("node")
        if not node_bin:
            self.skipTest("node binary unavailable in PATH")
        script = f"{_UI_DOM_PREAMBLE}\n(async () => {{\n{js_body}\n}})();\n"
        proc = subprocess.run([node_bin, "-e", script], capture_output=True, text=True, timeout=5, check=False)
        self.assertEqual(proc.returncode, 0, f"Node harness failed:\nSTDOUT:{proc.stdout}\nSTDERR:{proc.stderr}")
        lines = [line.strip() for line in proc.stdout.splitlines() if line.strip()]
        return json.loads(lines[-1])

    def _create_mock_conversations(self, base_dir: Path, count: int = 55, with_subagents: bool = True) -> list[dict]:
        convos = []
        now = time.time()
        for i in range(count):
            cid = f"convo_{i:03d}_{'sub' if with_subagents and i % 5 == 0 else 'root'}"
            cdir = base_dir / cid
            cdir.mkdir(parents=True, exist_ok=True)
            t_log = cdir / "transcript.jsonl"
            parent_id = f"convo_{i - 1:03d}_root" if (with_subagents and i % 5 == 0 and i > 0) else None
            first_line = {
                "step": 0,
                "type": "CORTEX_STEP_TYPE_USER_INPUT",
                "userInput": {"userResponse": f"Task instructions for session {cid}"},
            }
            if parent_id:
                first_line["parent_conversation_id"] = parent_id
                first_line["_meta"] = {"antigravity.google/root_conversation_id": parent_id}
            second_line = {
                "step": 1,
                "type": "CORTEX_STEP_TYPE_PLANNER_RESPONSE",
                "plannerResponse": {"response": f"Acknowledged task {i}"},
            }
            with open(t_log, "w", encoding="utf-8") as f:
                f.write(json.dumps(first_line) + "\n")
                f.write(json.dumps(second_line) + "\n")
            mtime = now - (count - i) * 60
            os.utime(t_log, (mtime, mtime))
            convos.append({"id": cid, "summary": f"Task instructions for session {cid}", "mtime": mtime, "parent_id": parent_id})
        return convos

    # --- F01: Active Tab Priority (real hotkey.js) ---

    def test_t1_f01_01_to_05_active_tab_priority_ladder(self) -> None:
        """F01.01-F01.05: Real hotkey.js enforces tab -> data-pane-id -> /c/:id -> ?cascadeId -> null priority."""
        hotkey_js = json.dumps(str(importlib.resources.files("harness.gui.assets").joinpath("hotkey.js")))
        res = self._run_node(f"""
        const fs = require('fs');
        eval(fs.readFileSync({hotkey_js}, 'utf8'));

        const paneEl = document.createElement("div");
        paneEl.setAttribute("data-pane-id", "b44d7023-e522-4467-b50a-4a25da7d0799");
        document.body.appendChild(paneEl);

        // 1. Subagent query tab beats pane-id and route
        window.location = {{ origin: "https://127.0.0.1:40623", pathname: "/c/parent-1234", search: "?tab=subagent_convo__child-uuid-5678" }};
        const subTabWin = window.detectActiveConversationContext();

        // 2. Focused data-pane-id beats route
        window.location.search = "";
        const paneWin = window.detectActiveConversationContext();
        paneEl.remove();

        // 3. Pathname /c/:id
        window.location.pathname = "/c/alpha-beta-gamma";
        const routeWin = window.detectActiveConversationContext();

        // 4. ?cascadeId fallback
        window.location.pathname = "/workspace";
        window.location.search = "?cascadeId=01234567-89ab-cdef-0123-456789abcdef";
        const cascadeWin = window.detectActiveConversationContext();

        // 5. Non-conversation path -> null
        window.location.pathname = "/settings";
        window.location.search = "";
        const unknownNull = window.detectActiveConversationContext();

        console.log(JSON.stringify({{ subTabWin, paneWin, routeWin, cascadeWin, unknownNull }}));
        """)
        self.assertEqual(res["subTabWin"], "child-uuid-5678")
        self.assertEqual(res["paneWin"], "b44d7023-e522-4467-b50a-4a25da7d0799")
        self.assertEqual(res["routeWin"], "alpha-beta-gamma")
        self.assertEqual(res["cascadeWin"], "01234567-89ab-cdef-0123-456789abcdef")
        self.assertIsNone(res["unknownNull"])

    # --- F02: Subagent Lineage & Parent Pill (real hud_header.js) ---

    def test_t1_f02_01_to_05_subagent_lineage_and_parent_pill(self) -> None:
        """F02.01-F02.05: Real hud_header.js renders (subagent), ← Parent pill, roles, and handles parent click."""
        header_js = json.dumps(str(importlib.resources.files("harness.gui.assets").joinpath("hud_header.js")))
        res = self._run_node(f"""
        const fs = require('fs');
        eval(fs.readFileSync({header_js}, 'utf8'));

        const childHtml = window.renderHudHeader({{}}, {{ conversation_id: "child-1", parent_id: "parent-root-123" }}, []);
        const rootHtml = window.renderHudHeader({{}}, {{ conversation_id: "root-only", parent_id: null }}, []);
        const subListHtml = window.renderHudHeader(
            {{ subagentsDropdownOpen: true }},
            {{ conversation_id: "root-convo", subagents: ["sub-uuid-1"], subagent_infos: [{{ id: "sub-uuid-1", name: "explorer_1" }}] }},
            []
        );

        let loadedConvo = null;
        window.__agyis_hud_load_convo = (pid) => {{ loadedConvo = pid; }};
        const parentBtn = makeElement("button");
        parentBtn.id = "agyis-parent-btn";
        hudRoot.appendChild(parentBtn);
        window.bindHudHeaderEvents(hudRoot, {{}}, {{ conversation_id: "child-1", parent_id: "target-parent-456" }}, () => {{}});
        parentBtn.dispatchEvent({{ type: "click" }});

        console.log(JSON.stringify({{
            childHasBadge: childHtml.includes("(subagent)"),
            childHasPill: childHtml.includes("← Parent") && childHtml.includes("agyis-parent-btn") && childHtml.includes("parent-root-123"),
            rootHasBadge: rootHtml.includes("(subagent)"),
            rootHasPill: rootHtml.includes("agyis-parent-btn"),
            subListHasRole: subListHtml.includes("explorer_1") && subListHtml.includes("sub-uuid-1"),
            loadedConvo
        }}));
        """)
        self.assertTrue(res["childHasBadge"])
        self.assertTrue(res["childHasPill"])
        self.assertFalse(res["rootHasBadge"])
        self.assertFalse(res["rootHasPill"])
        self.assertTrue(res["subListHasRole"])
        self.assertEqual(res["loadedConvo"], "target-parent-456")

    # --- F03: Session Dropdown Population (real get_recent_conversations + hud_header.js) ---

    def test_t1_f03_01_default_limit_100_retrieves_50_plus(self) -> None:
        """F03.01: get_recent_conversations default limit=100 retrieves 50+ conversations (DEF-BB-041)."""
        brain_dir = self.ws / "brain_55"
        self._create_mock_conversations(brain_dir, count=55)
        self.assertEqual(len(get_recent_conversations(brain_dir)), 55)

    def test_t1_f03_02_limit_none_retrieves_all(self) -> None:
        """F03.02: get_recent_conversations(limit=None) retrieves all conversations."""
        brain_dir = self.ws / "brain_60"
        self._create_mock_conversations(brain_dir, count=60)
        self.assertEqual(len(get_recent_conversations(brain_dir, limit=None)), 60)

    def test_t1_f03_03_parent_conversation_id_extraction(self) -> None:
        """F03.03: get_recent_conversations extracts parent_id / parentConversationId (DEF-BB-045)."""
        brain_dir = self.ws / "brain_sub"
        self._create_mock_conversations(brain_dir, count=10, with_subagents=True)
        convos = get_recent_conversations(brain_dir, limit=10)
        sub_convos = [c for c in convos if c.get("parent_id") or c.get("parentConversationId")]
        self.assertTrue(len(sub_convos) > 0)

    def test_t1_f03_04_mtime_descending_sorting(self) -> None:
        """F03.04: get_recent_conversations returns list strictly sorted by mtime descending."""
        brain_dir = self.ws / "brain_sort"
        self._create_mock_conversations(brain_dir, count=15)
        convos = get_recent_conversations(brain_dir)
        mtimes = [c["mtime"] for c in convos]
        self.assertEqual(mtimes, sorted(mtimes, reverse=True))

    def test_t1_f03_05_dropdown_renders_50_plus_options(self) -> None:
        """F03.05: Real hud_header.js mounts 55 conversations from get_recent_conversations in session select dropdown."""
        brain_dir = self.ws / "brain_node"
        self._create_mock_conversations(brain_dir, count=55)
        convos = get_recent_conversations(brain_dir)
        header_js = json.dumps(str(importlib.resources.files("harness.gui.assets").joinpath("hud_header.js")))
        convos_json = json.dumps(convos)
        res = self._run_node(f"""
        const fs = require('fs');
        eval(fs.readFileSync({header_js}, 'utf8'));
        const convos = {convos_json};
        const html = window.renderHudHeader({{}}, {{ conversation_id: convos[0].id, steps: [] }}, convos);
        const optionCount = (html.match(/<option\\b/g) || []).length;
        const hasSubNote = html.includes("subagent of");
        console.log(JSON.stringify({{ optionCount, hasSubNote }}));
        """)
        self.assertEqual(res["optionCount"], 55)
        self.assertTrue(res["hasSubNote"])

    # --- F04: Token Gauge & Context Bar (real trajectory_hud.py + hud_context_bar.js) ---

    def test_t1_f04_01_token_gauge_single_row_under_64k(self) -> None:
        """F04.01: Token gauge allocates single row under 64k tokens (ztc cleanroom layout)."""
        segments = [{"name": "System", "tokens": 15000}, {"name": "User", "tokens": 30000}]
        self.assertEqual(ztc_row_count(segments, capacity_tokens=200000, container_width=800.0), 1)

    def test_t1_f04_02_token_gauge_two_rows_under_128k(self) -> None:
        """F04.02: Real renderContextBar uses 2-row layout for 65k-128k active tokens on 256k window."""
        ctx_js = json.dumps(str(importlib.resources.files("harness.gui.assets").joinpath("hud_context_bar.js")))
        res = self._run_node(f"""
        const fs = require('fs');
        eval(fs.readFileSync({ctx_js}, 'utf8'));
        const cur = {{
            model: "default",
            total_tokens: 95000,
            token_breakdown: {{ system_prompt: 20000, user: 75000 }},
            checkpoints: [{{ start_index: 0, end_index: 0, total_tokens: 95000, token_breakdown: {{ system_prompt: 20000, user: 75000 }} }}]
        }};
        const html = window.renderContextBar(cur, {{ activeCheckpointIndex: 0 }}, [], cur.checkpoints[0], [], 256000, 800);
        const rowWraps = (html.match(/agyis-context-row-wrap/g) || []).length;
        console.log(JSON.stringify({{ rowWraps, hasTitle: html.includes("Context Window (2 rows)") }}));
        """)
        self.assertEqual(res["rowWraps"], 2)
        self.assertTrue(res["hasTitle"])

    def test_t1_f04_03_token_gauge_three_and_four_rows(self) -> None:
        """F04.03: Token gauge multi-row allocation scales dynamically with segment count and inflation."""
        segments = [{"name": f"Tool_{i}", "tokens": 5000} for i in range(30)]
        rows = ztc_row_count(segments, capacity_tokens=200000, container_width=300.0, min_segment_px=10.0)
        self.assertGreaterEqual(rows, 2)
        layout = atc_context_layout(segments, capacity_tokens=200000, container_width=300.0, min_segment_px=10.0)
        self.assertEqual(len(layout["rows"]), rows)

    def test_t1_f04_04_dynamic_calibration_scaling(self) -> None:
        """F04.04: Real renderContextBar scales placed visual width proportionally when active_tokens > raw_sum."""
        ctx_js = json.dumps(str(importlib.resources.files("harness.gui.assets").joinpath("hud_context_bar.js")))
        res = self._run_node(f"""
        const fs = require('fs');
        eval(fs.readFileSync({ctx_js}, 'utf8'));
        const cur = {{
            total_tokens: 100000,
            token_breakdown: {{ system_prompt: 40000, tool_defs: 40000 }},
            checkpoints: [{{ start_index: 0, end_index: 0, total_tokens: 100000 }}]
        }};
        const html = window.renderContextBar(cur, {{ activeCheckpointIndex: 0 }}, [], cur.checkpoints[0], [], 256000, 800);
        const btnMatches = [...html.matchAll(/<button[^>]*data-seg-id="([^"]+)"[^>]*data-seg-tokens="(\\d+)"[^>]*width:\\s*([\\d.]+)%/gs)];
        const widths = {{}};
        const tokens = {{}};
        for (const m of btnMatches) {{
            tokens[m[1]] = Number(m[2]);
            widths[m[1]] = (widths[m[1]] || 0) + Number(m[3]);
        }}
        console.log(JSON.stringify({{ tokens, widths }}));
        """)
        self.assertEqual(res["tokens"].get("prompt-section-root"), 40000)
        self.assertAlmostEqual(res["widths"].get("prompt-section-root"), 78.125, places=3)
        self.assertAlmostEqual(res["widths"].get("tool-defs-root"), 78.125, places=3)

    def test_t1_f04_05_over_capacity_and_checkpoint_nav_interactions(self) -> None:
        """F04.05+: Real renderContextBar emits 'over' badge and bindContextBarEvents passes preserveCheckpoint on Prev/Next/segment click."""
        ctx_js = json.dumps(str(importlib.resources.files("harness.gui.assets").joinpath("hud_context_bar.js")))
        utils_js = json.dumps(str(importlib.resources.files("harness.gui.assets").joinpath("hud_utils.js")))
        res = self._run_node(f"""
        const fs = require('fs');
        eval(fs.readFileSync({utils_js}, 'utf8'));
        eval(fs.readFileSync({ctx_js}, 'utf8'));
        const cur = {{
            total_tokens: 260000,
            token_breakdown: {{ system_prompt: 60000, user: 200000 }},
            checkpoints: [
                {{ checkpoint_index: 0, start_index: 0, end_index: 3, total_tokens: 40000 }},
                {{ checkpoint_index: 1, start_index: 4, end_index: 7, total_tokens: 260000 }}
            ]
        }};
        const html = window.renderContextBar(cur, {{ activeCheckpointIndex: 1 }}, [], cur.checkpoints[1], [], 256000, 800);
        const st = {{ activeCheckpointIndex: 0, selectedIndex: 0 }};
        const calls = [];
        const prevBtn = makeElement("button"); prevBtn.id = "agyis-checkpoint-prev";
        const nextBtn = makeElement("button"); nextBtn.id = "agyis-checkpoint-next";
        const segEl = makeElement("button"); segEl.classList.add("agyis-context-segment");
        segEl.setAttribute("data-step-index", "4");
        hudRoot.appendChild(prevBtn);
        hudRoot.appendChild(nextBtn);
        hudRoot.appendChild(segEl);
        const selectCb = (sIdx, opts) => calls.push({{ sIdx, opts, activeCp: st.activeCheckpointIndex }});
        window.bindContextBarEvents(hudRoot, st, cur, cur.checkpoints, () => {{}}, selectCb);
        nextBtn.dispatchEvent({{ type: "click" }});
        prevBtn.dispatchEvent({{ type: "click" }});
        segEl.dispatchEvent({{ type: "click" }});
        console.log(JSON.stringify({{
            hasOver: html.includes("100.0% over"),
            hasTotal: html.includes("260,000"),
            hasCheckpointLabel: html.includes("Checkpoint 2 of 2 (Steps #4-#7)"),
            calls
        }}));
        """)
        self.assertTrue(res["hasOver"])
        self.assertTrue(res["hasTotal"])
        self.assertTrue(res["hasCheckpointLabel"])
        self.assertEqual(res["calls"], [
            {"sIdx": 4, "opts": {"preserveCheckpoint": True}, "activeCp": 1},
            {"sIdx": 0, "opts": {"preserveCheckpoint": True}, "activeCp": 0},
            {"sIdx": 4, "opts": {"preserveCheckpoint": True}, "activeCp": 0},
        ])

    # --- T2 B01: Real XSS escaping & trajectory path safety ---

    def test_t2_b01_01_to_03_xss_sanitization_in_hud_header_and_trajectory_loader(self) -> None:
        """B01.01-B01.03: Real hud_header.js escapes <script>, <img onerror>, and parent_id attributes; loader blocks traversal."""
        header_js = json.dumps(str(importlib.resources.files("harness.gui.assets").joinpath("hud_header.js")))
        res = self._run_node(f"""
        const fs = require('fs');
        eval(fs.readFileSync({header_js}, 'utf8'));
        const html = window.renderHudHeader(
            {{ filterQuery: '<img src=x onerror=alert(1)>' }},
            {{ conversation_id: "c1", parent_id: 'javascript:alert(1)" onclick="alert(2)' }},
            [{{ id: "c1", summary: '<script>alert("xss")</script>' }}]
        );
        console.log(JSON.stringify({{
            hasRawScript: html.includes("<script>"),
            hasEscapedScript: html.includes("&lt;script&gt;"),
            hasRawImg: html.includes("<img src=x"),
            hasEscapedImg: html.includes("&lt;img src=x onerror=alert(1)&gt;"),
            hasHrefJs: html.includes('href="javascript:'),
            hasEscapedQuote: html.includes("&quot; onclick=&quot;")
        }}));
        """)
        self.assertFalse(res["hasRawScript"])
        self.assertTrue(res["hasEscapedScript"])
        self.assertFalse(res["hasRawImg"])
        self.assertTrue(res["hasEscapedImg"])
        self.assertFalse(res["hasHrefJs"])
        self.assertTrue(res["hasEscapedQuote"])
        with self.assertRaises(ValueError):
            load_conversation_trajectory("../escape", brain_dir=self.ws)


if __name__ == "__main__":
    unittest.main()
