#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Arafat Zahan (@kuasha420)
# Corporate Stewardship & Infrastructure: Purrfect Software Limited (PSL)
# Governed by: ICARO-42/b Ordinance (Company-Supported Personal IP Framework)

"""
Bug Bash GUI E2E Suite — SPA Routes, Subagent Tab Detection & Stale DOM Purge (F10, F11).
Executes real harness/gui/assets/hotkey.js, hud.js, and hud_header.js inside Node.js.
"""

from __future__ import annotations

import importlib.resources
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

from harness.gui.trajectory_hud import build_trajectory_hud_script


_DOM_PREAMBLE = r"""
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

const document = {
    body: makeElement("body"),
    head: makeElement("head"),
    activeElement: null,
    _docListeners: {},
    getElementById(id) {
        return this.head.querySelector("#" + id) || this.body.querySelector("#" + id);
    },
    createElement(tag) { return makeElement(tag); },
    querySelector(sel) { return this.body.querySelector(sel); },
    querySelectorAll(sel) { return this.body.querySelectorAll(sel); },
    addEventListener(ev, fn) { (this._docListeners[ev] = this._docListeners[ev] || []).push(fn); },
    removeEventListener(ev, fn) {
        if (this._docListeners[ev]) this._docListeners[ev] = this._docListeners[ev].filter(f => f !== fn);
    },
};
document.activeElement = document.body;

const windowListeners = [];
const storageMap = new Map();
const window = {
    location: { origin: "https://127.0.0.1:40623", pathname: "/c/convo-init", search: "", hash: "" },
    history: {
        _applyUrl(url) {
            if (!url) return;
            const s = String(url);
            const [beforeHash, hashPart] = s.split("#");
            const [pathPart, searchPart] = beforeHash.split("?");
            window.location.pathname = pathPart || "/";
            window.location.search = searchPart ? ("?" + searchPart) : "";
            window.location.hash = hashPart ? ("#" + hashPart) : "";
        },
        pushState(_state, _title, url) { this._applyUrl(url); },
        replaceState(_state, _title, url) { this._applyUrl(url); },
    },
    localStorage: {
        getItem(k) { return storageMap.has(k) ? storageMap.get(k) : null; },
        setItem(k, v) { storageMap.set(k, String(v)); },
    },
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
global.localStorage = window.localStorage;
global.Event = class Event { constructor(t) { this.type = t; } };
"""


class TestBugBashGuiRoutes(unittest.TestCase):
    """Real Node.js DOM execution of hotkey.js, hud.js, and hud_header.js (F10, F11, T2, T3)."""

    def _run_node(self, js_body: str) -> dict:
        node_bin = shutil.which("node")
        if not node_bin:
            self.skipTest("node binary unavailable in PATH")
        script = f"{_DOM_PREAMBLE}\n(async () => {{\n{js_body}\n}})();\n"
        proc = subprocess.run([node_bin, "-e", script], capture_output=True, text=True, timeout=5, check=False)
        self.assertEqual(proc.returncode, 0, f"Node harness failed:\nSTDOUT:{proc.stdout}\nSTDERR:{proc.stderr}")
        lines = [line.strip() for line in proc.stdout.splitlines() if line.strip()]
        return json.loads(lines[-1])

    def test_t1_f10_01_02_pushstate_and_route_extraction(self) -> None:
        """F10.1-F10.2: Executes real hud.js + hotkey.js pushState patching and /c/:id extraction."""
        assets = importlib.resources.files("harness.gui.assets")
        hud_path = json.dumps(str(assets.joinpath("hud.js")))
        hotkey_path = json.dumps(str(assets.joinpath("hotkey.js")))
        res = self._run_node(f"""
        const fs = require('fs');
        eval(fs.readFileSync({hud_path}, 'utf8'));
        eval(fs.readFileSync({hotkey_path}, 'utf8'));

        let routeEvents = 0;
        window.addEventListener("agyis:routechange", () => {{ routeEvents++; }});
        window.history.pushState({{}}, "", "/c/e8c67662-8c67-4674-b4f0-4760bd3fec59");
        const hudExtracted = window.__agyis_extract_convo_id();
        const hotkeyExtracted = window.detectActiveConversationContext();

        window.history.replaceState({{}}, "", "/c/replaced-id-999");
        const afterReplace = window.detectActiveConversationContext();
        console.log(JSON.stringify({{ routeEvents, hudExtracted, hotkeyExtracted, afterReplace }}));
        """)
        self.assertEqual(res["routeEvents"], 2)
        self.assertEqual(res["hudExtracted"], "e8c67662-8c67-4674-b4f0-4760bd3fec59")
        self.assertEqual(res["hotkeyExtracted"], "e8c67662-8c67-4674-b4f0-4760bd3fec59")
        self.assertEqual(res["afterReplace"], "replaced-id-999")

    def test_t1_f10_03_04_route_change_context_and_cleanup(self) -> None:
        """F10.3-F10.4: Real hud.js onSpaRouteChange updates context and __agyis_hud_route_cleanup detaches popstate."""
        assets = importlib.resources.files("harness.gui.assets")
        hud_path = json.dumps(str(assets.joinpath("hud.js")))
        res = self._run_node(f"""
        const fs = require('fs');
        const loaded = [];
        window.loadConversationViaRpc = async (id) => {{
            loaded.push(id);
            return {{ conversation_id: id, steps: [{{ type: "USER_INPUT", content: "hi" }}] }};
        }};
        eval(fs.readFileSync({hud_path}, 'utf8'));

        window.history.pushState({{}}, "", "/c/route-alpha");
        await new Promise(r => setTimeout(r, 15));
        const afterPush = window.__agyis_hud_state.convoId;

        window.location.pathname = "/c/route-beta";
        window.dispatchEvent(new Event("popstate"));
        await new Promise(r => setTimeout(r, 15));
        const afterPop = window.__agyis_hud_state.convoId;

        window.__agyis_hud_route_cleanup();
        window.location.pathname = "/c/route-after-cleanup";
        window.dispatchEvent(new Event("popstate"));
        await new Promise(r => setTimeout(r, 15));
        console.log(JSON.stringify({{ afterPush, afterPop, loaded }}));
        """)
        self.assertEqual(res["afterPush"], "route-alpha")
        self.assertEqual(res["afterPop"], "route-beta")
        self.assertEqual(res["loaded"], ["convo-init", "route-alpha", "route-beta"])

    def test_t1_f10_05_stale_dom_purged_on_route_switch(self) -> None:
        """F10.5: Real build_trajectory_hud_script & hotkey.js purge stale DOM/styles (PSL-INV-007)."""
        script = build_trajectory_hud_script(
            "convo-fresh",
            {"conversation_id": "convo-fresh", "steps": [], "epochs": []},
            [],
            open_view=True,
        )
        with tempfile.TemporaryDirectory() as td:
            script_file = Path(td) / "hud_bundle.js"
            script_file.write_text(script, encoding="utf-8")
            script_path = json.dumps(str(script_file))
            res = self._run_node(f"""
            const fs = require('fs');
            const staleHud = document.createElement("div");
            staleHud.id = "agyis-trajectory-hud";
            staleHud.setAttribute("data-stale", "old");
            document.body.appendChild(staleHud);
            const staleStyles = document.createElement("style");
            staleStyles.id = "agyis-trajectory-hud-styles";
            staleStyles.textContent = "/* old */";
            document.head.appendChild(staleStyles);

            eval(fs.readFileSync({script_path}, 'utf8'));
            const curHud = document.getElementById("agyis-trajectory-hud");
            const curStyles = document.getElementById("agyis-trajectory-hud-styles");
            const hudNodes = document.body.children.filter(c => c.id === "agyis-trajectory-hud");
            const styleNodes = document.head.children.filter(c => c.id === "agyis-trajectory-hud-styles");
            console.log(JSON.stringify({{
                staleRemoved: staleHud.parentNode === null && staleStyles.parentNode === null,
                newMounted: curHud !== null && curHud.getAttribute("data-stale") === null,
                hudCount: hudNodes.length,
                styleCount: styleNodes.length,
                convoId: window.__agyis_hud_state.convoId,
                open: curHud.style.display
            }}));
            """)
        self.assertTrue(res["staleRemoved"])
        self.assertTrue(res["newMounted"])
        self.assertEqual(res["hudCount"], 1)
        self.assertEqual(res["styleCount"], 1)
        self.assertEqual(res["convoId"], "convo-fresh")
        self.assertEqual(res["open"], "flex")

    def test_t1_f11_01_02_05_subagent_tab_priority_and_fallback(self) -> None:
        """F11.1, F11.2, F11.5: Executes hotkey.js & hud.js subagent tab precedence and route fallback."""
        assets = importlib.resources.files("harness.gui.assets")
        hud_path = json.dumps(str(assets.joinpath("hud.js")))
        hotkey_path = json.dumps(str(assets.joinpath("hotkey.js")))
        sub_a = "b5796a47-98bf-499f-b185-2d2f5f7977e0"
        sub_b = "76a09f40-ea1b-4bde-8da3-c6507be1acf2"
        res = self._run_node(f"""
        const fs = require('fs');
        eval(fs.readFileSync({hud_path}, 'utf8'));
        eval(fs.readFileSync({hotkey_path}, 'utf8'));

        window.location.pathname = "/c/parent-convo-1234-5678";
        window.location.search = "?tab=subagent_convo__{sub_a}";
        const prioritySub = window.detectActiveConversationContext();

        window.location.search = "?tab=subagent_convo__{sub_b}";
        const hudSub = window.__agyis_extract_convo_id();

        window.location.pathname = "/c/parent-convo-9999";
        window.location.search = "";
        const routeFallback = window.detectActiveConversationContext();
        console.log(JSON.stringify({{ prioritySub, hudSub, routeFallback }}));
        """)
        self.assertEqual(res["prioritySub"], sub_a)
        self.assertEqual(res["hudSub"], sub_b)
        self.assertEqual(res["routeFallback"], "parent-convo-9999")

    def test_t1_f11_03_04_subagent_badge_and_parent_pill(self) -> None:
        """F11.3-F11.4: Executes real hud_header.js renderHudHeader for (subagent) badge and ← Parent pill."""
        assets = importlib.resources.files("harness.gui.assets")
        header_path = json.dumps(str(assets.joinpath("hud_header.js")))
        res = self._run_node(f"""
        const fs = require('fs');
        eval(fs.readFileSync({header_path}, 'utf8'));
        const cur = {{ conversation_id: "sub-1", parent_id: "parent-root-007", steps: [] }};
        const html = window.renderHudHeader({{}}, cur, []);
        console.log(JSON.stringify({{
            hasBadge: html.includes("(subagent)"),
            hasParentPill: html.includes("← Parent") && html.includes("agyis-parent-btn"),
            hasParentTitle: html.includes("parent-root-007")
        }}));
        """)
        self.assertTrue(res["hasBadge"])
        self.assertTrue(res["hasParentPill"])
        self.assertTrue(res["hasParentTitle"])

    def test_t2_f10_01_02_04_05_spa_route_boundaries(self) -> None:
        """F10.B1, B2, B4, B5: Executes real detectActiveConversationContext on malformed/special/hash routes."""
        assets = importlib.resources.files("harness.gui.assets")
        hotkey_path = json.dumps(str(assets.joinpath("hotkey.js")))
        res = self._run_node(f"""
        const fs = require('fs');
        eval(fs.readFileSync({hotkey_path}, 'utf8'));

        window.location = {{ origin: "https://127.0.0.1:40623", pathname: "/c/", search: "", hash: "" }};
        const emptyC = window.detectActiveConversationContext();

        window.location.pathname = "/c/convo-test_1234-abcd_5678";
        const specialId = window.detectActiveConversationContext();

        window.location.pathname = "/settings";
        const settingsRoute = window.detectActiveConversationContext();

        window.location.pathname = "/c/uuid-1234";
        window.location.hash = "#step-42";
        const hashRoute = window.detectActiveConversationContext();
        console.log(JSON.stringify({{ emptyC, specialId, settingsRoute, hashRoute }}));
        """)
        self.assertIsNone(res["emptyC"])
        self.assertEqual(res["specialId"], "convo-test_1234-abcd_5678")
        self.assertIsNone(res["settingsRoute"])
        self.assertEqual(res["hashRoute"], "uuid-1234")

    def test_t2_f10_03_rapid_f12_hotkey_debounce(self) -> None:
        """F10.B3: Real hotkey.js initAgyisHotkey enforces 250ms debounce on rapid F12 keydowns."""
        assets = importlib.resources.files("harness.gui.assets")
        hotkey_path = json.dumps(str(assets.joinpath("hotkey.js")))
        res = self._run_node(f"""
        const fs = require('fs');
        let nowMs = 10000;
        Date.now = () => nowMs;
        const hud = document.createElement("div");
        hud.id = "agyis-trajectory-hud";
        hud.style.display = "none";
        document.body.appendChild(hud);
        window.__agyis_hud_state = {{ convoId: "convo-init", steps: [] }};

        eval(fs.readFileSync({hotkey_path}, 'utf8'));
        let toggleCount = 0;
        const origToggle = window.toggleAgyisHud;
        window.toggleAgyisHud = (...args) => {{ toggleCount++; return origToggle(...args); }};

        // Press F12 4 times within 120ms -> hotkey.js checks Date.now() - lastToggleTime < 250
        for (let i = 0; i < 4; i++) {{
            nowMs += 40;
            window.dispatchEvent({{ type: "keydown", key: "F12" }});
        }}
        const displayAfterSpam = hud.style.display;
        nowMs += 300;
        window.dispatchEvent({{ type: "keydown", key: "F12" }});
        const displayAfterCooldown = hud.style.display;
        console.log(JSON.stringify({{ displayAfterSpam, displayAfterCooldown, toggleCount }}));
        """)
        self.assertEqual(res["displayAfterSpam"], "flex")
        self.assertEqual(res["displayAfterCooldown"], "none")

    def test_t2_f11_01_to_05_subagent_query_boundaries(self) -> None:
        """F11.B1-B5: Real hotkey.js extract handles multi-tab, empty prefix, nested parent, non-subagent, encoded params."""
        assets = importlib.resources.files("harness.gui.assets")
        hotkey_path = json.dumps(str(assets.joinpath("hotkey.js")))
        uid = "76a09f40-ea1b-4bde-8da3-c6507be1acf2"
        res = self._run_node(f"""
        const fs = require('fs');
        eval(fs.readFileSync({hotkey_path}, 'utf8'));

        window.location = {{ origin: "https://127.0.0.1:40623", pathname: "/c/parent-fallback", search: "?view=split&tab=subagent_convo__sub-123&tab=terminal" }};
        const multiTab = window.detectActiveConversationContext();

        window.location.search = "?tab=subagent_convo__";
        const emptySub = window.detectActiveConversationContext();

        window.location.search = "?tab=subagent_convo__{uid}&parent=6f4b4fbb-7c6f-41c6-b2aa-67ddc3b2732d";
        const nestedSub = window.detectActiveConversationContext();

        window.location.search = "?tab=terminal";
        const nonSubTab = window.detectActiveConversationContext();

        window.location.search = "?tab=" + encodeURIComponent("subagent_convo__uuid-encoded");
        const encodedSub = window.detectActiveConversationContext();
        console.log(JSON.stringify({{ multiTab, emptySub, nestedSub, nonSubTab, encodedSub }}));
        """)
        self.assertEqual(res["multiTab"], "sub-123")
        self.assertEqual(res["emptySub"], "parent-fallback")
        self.assertEqual(res["nestedSub"], uid)
        self.assertEqual(res["nonSubTab"], "parent-fallback")
        self.assertEqual(res["encodedSub"], "uuid-encoded")

    def test_t3_c09_spa_route_switch_and_subagent_detection(self) -> None:
        """C09 (F10 x F11): Real hud.js pushState switch to subagent tab selects subagent ID over parent ID."""
        assets = importlib.resources.files("harness.gui.assets")
        hud_path = json.dumps(str(assets.joinpath("hud.js")))
        hotkey_path = json.dumps(str(assets.joinpath("hotkey.js")))
        parent_id = "00000000-0000-0000-0000-000000000001"
        sub_id = "11111111-1111-1111-1111-111111111111"
        res = self._run_node(f"""
        const fs = require('fs');
        const rpcCalls = [];
        window.loadConversationViaRpc = async (id) => {{
            rpcCalls.push(id);
            return {{ conversation_id: id, parent_id: "{parent_id}", steps: [] }};
        }};
        eval(fs.readFileSync({hud_path}, 'utf8'));
        eval(fs.readFileSync({hotkey_path}, 'utf8'));

        window.history.pushState({{}}, "", "/c/{parent_id}?tab=subagent_convo__{sub_id}");
        await new Promise(r => setTimeout(r, 15));
        console.log(JSON.stringify({{
            detected: window.detectActiveConversationContext(),
            activeConvo: window.__agyis_hud_state.convoId,
            rpcCalls
        }}));
        """)
        self.assertEqual(res["detected"], sub_id)
        self.assertEqual(res["activeConvo"], sub_id)
        self.assertEqual(res["rpcCalls"], ["convo-init", sub_id])


if __name__ == "__main__":
    unittest.main()
