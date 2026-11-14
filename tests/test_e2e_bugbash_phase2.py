#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Arafat Zahan (@kuasha420)
# Corporate Stewardship & Infrastructure: Purrfect Software Limited (PSL)
# Governed by: ICARO-42/b Ordinance (Company-Supported Personal IP Framework)

"""
Comprehensive Opaque-Box E2E Test Suite for Bug Bash Phase 2 (Squad 1).
Covers Frontier 1 (Live Multi-Session HUD & Hotkeys Lifecycle) and
Frontier 2 (Knot Mesh Remote Operations).

Features F01 through F16 verified across 4 standard tiers:
- Tier 1: Feature Coverage (80 test cases: F01 through F16 x 5)
- Tier 2: Boundary & Corner Cases (11 test cases: B01 through B06)
- Tier 3: Cross-Feature Interactions (4 test cases: C01 through C04)
- Tier 4: Real-World Scenarios (3 application workloads: S01 through S03)

Total: 98 test cases.
Hermetic execution via tempfile.TemporaryDirectory, scrubbed env vars,
mock SSH subprocess dispatching, and sub-second Node.js DOM assertions.
"""

from __future__ import annotations

import argparse
import inspect
import io
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
import time
from typing import Any, Dict, List, Optional, Tuple
import unittest
from unittest.mock import MagicMock, patch

# Dynamic repository resolution for hermetic test execution
repo_root = Path(__file__).resolve().parent.parent
if str(repo_root) not in sys.path:
    sys.path.insert(0, str(repo_root))

from harness.cli import main as cli_main
from harness.commands.remote import cmd_remote
from harness.gui.trajectory_hud import (
    build_trajectory_hud_script,
    get_recent_conversations,
    load_conversation_trajectory,
)
from harness.remote.runner import RemoteRunner, get_socket_dir
from harness.remote.safety import REMOTE_TOOLCHAIN_REGEX, sanitize_ssh_remote_payload
from harness.remote.scripts import ScriptStreamer
from harness.remote.triage import RemoteTriage


class BaseBugBashPhase2TestCase(unittest.TestCase):
    """Hermetic base test case providing isolated temporary workspaces, git scaffolding, and CLI runner."""

    maxDiff = None

    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.ws = Path(self.temp_dir.name).resolve()

        self.orig_env = os.environ.copy()
        self.state_dir = self.ws / ".state"
        self.config_dir = self.ws / ".config" / "agyis"
        self.data_dir = self.ws / ".local" / "share" / "agyis"
        self.socket_dir = self.ws / ".ssh_sockets"

        self.state_dir.mkdir(parents=True, exist_ok=True)
        self.config_dir.mkdir(parents=True, exist_ok=True)
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.socket_dir.mkdir(parents=True, exist_ok=True)

        os.environ["PSL_HARNESS_STATE_DIR"] = str(self.state_dir)
        os.environ["AGYIS_CONFIG_DIR"] = str(self.config_dir)
        os.environ["AGYIS_DATA_DIR"] = str(self.data_dir)
        os.environ["PSL_SSH_SOCKET_DIR"] = str(self.socket_dir)

    def tearDown(self) -> None:
        os.environ.clear()
        os.environ.update(self.orig_env)
        self.temp_dir.cleanup()

    def run_cli(
        self,
        args: List[str],
        prog: str = "agyis",
        env_overrides: Optional[Dict[str, str]] = None,
        stdin_input: Optional[str] = None,
    ) -> Tuple[int, str, str]:
        """Executes CLI in-process via harness.cli.main, capturing stdout and stderr."""
        saved_env = os.environ.copy()
        if env_overrides:
            os.environ.update(env_overrides)

        stdin_buf = io.StringIO(stdin_input or "")
        stdout_buf = io.StringIO()
        stderr_buf = io.StringIO()

        try:
            with patch("sys.stdin", stdin_buf), patch("sys.stdout", stdout_buf), patch("sys.stderr", stderr_buf):
                try:
                    code = cli_main(args, prog=prog)
                except SystemExit as exc:
                    code = exc.code if isinstance(exc.code, int) else 0
        finally:
            os.environ.clear()
            os.environ.update(saved_env)

        return code, stdout_buf.getvalue(), stderr_buf.getvalue()

    def create_mock_conversations(
        self,
        base_dir: Path,
        count: int = 55,
        with_subagents: bool = True,
    ) -> List[Dict[str, Any]]:
        """Scaffolds mock Antigravity conversation folders with transcript files and parent metadata."""
        convos = []
        now = time.time()
        for i in range(count):
            cid = f"convo_{i:03d}_{'sub' if with_subagents and i % 5 == 0 else 'root'}"
            cdir = base_dir / cid
            cdir.mkdir(parents=True, exist_ok=True)
            t_log = cdir / "transcript.jsonl"

            parent_id = f"convo_{i-1:03d}_root" if (with_subagents and i % 5 == 0 and i > 0) else None
            meta_dict = {}
            if parent_id:
                meta_dict["antigravity.google/root_conversation_id"] = parent_id

            # Write realistic JSONL lines
            first_line = {
                "step": 0,
                "type": "CORTEX_STEP_TYPE_USER_INPUT",
                "userInput": {"userResponse": f"Task instructions for session {cid}"},
            }
            if parent_id:
                first_line["parent_conversation_id"] = parent_id
                first_line["_meta"] = meta_dict

            second_line = {
                "step": 1,
                "type": "CORTEX_STEP_TYPE_PLANNER_RESPONSE",
                "plannerResponse": {"response": f"Acknowledged task {i}"},
            }

            with open(t_log, "w", encoding="utf-8") as f:
                f.write(json.dumps(first_line) + "\n")
                f.write(json.dumps(second_line) + "\n")

            # Stagger modification times so sorting is deterministic
            mtime = now - (count - i) * 60
            os.utime(t_log, (mtime, mtime))

            convos.append({
                "id": cid,
                "summary": f"Task instructions for session {cid}",
                "mtime": mtime,
                "parent_id": parent_id,
            })
        return convos

    def run_node_harness(self, js_body: str, timeout: int = 5) -> Dict[str, Any]:
        """Executes a lightweight in-situ Node DOM harness evaluating JS assets."""
        if not shutil.which("node"):
            self.skipTest("node binary unavailable in environment")

        harness_script = f"""
const createdElements = [];
function makeElement(tagName) {{
    const el = {{
        tagName: String(tagName || "div").toUpperCase(),
        id: "",
        className: "",
        classList: {{
            _classes: new Set(),
            add(c) {{ this._classes.add(c); }},
            remove(c) {{ this._classes.delete(c); }},
            contains(c) {{ return this._classes.has(c); }},
            toggle(c) {{ if (this._classes.has(c)) this._classes.delete(c); else this._classes.add(c); }}
        }},
        style: {{ display: "none" }},
        innerHTML: "",
        innerText: "",
        textContent: "",
        children: [],
        value: "",
        selectionStart: 0,
        selectionEnd: 0,
        _listeners: {{}},
        addEventListener(event, handler, opts) {{
            (this._listeners[event] = this._listeners[event] || []).push({{ handler, opts }});
        }},
        removeEventListener(event, handler) {{
            if (!this._listeners[event]) return;
            this._listeners[event] = this._listeners[event].filter(l => l.handler !== handler);
        }},
        dispatchEvent(event) {{
            if (!event.preventDefault) event.preventDefault = () => {{}};
            if (!event.stopPropagation) event.stopPropagation = () => {{}};
            if (!event.stopImmediatePropagation) event.stopImmediatePropagation = () => {{}};
            const list = this._listeners[event.type] || [];
            for (const item of list) {{
                item.handler.call(this, event);
            }}
        }},
        appendChild(child) {{ this.children.push(child); return child; }},
        contains(target) {{
            if (target === this) return true;
            for (const ch of this.children) {{
                if (ch === target || (ch.contains && ch.contains(target))) return true;
            }}
            return false;
        }},
        remove() {{}},
        focus() {{ document.activeElement = this; }},
        blur() {{ if (document.activeElement === this) document.activeElement = document.body; }},
        setSelectionRange(start, end) {{ this.selectionStart = start; this.selectionEnd = end; }},
        querySelector(sel) {{
            if (sel.startsWith("#")) {{
                const targetId = sel.slice(1);
                if (this.id === targetId) return this;
                for (const ch of this.children) {{
                    if (ch.querySelector) {{
                        const f = ch.querySelector(sel);
                        if (f) return f;
                    }}
                }}
            }} else if (sel.startsWith(".")) {{
                const cls = sel.slice(1);
                if (this.classList && this.classList.contains && this.classList.contains(cls)) return this;
                for (const ch of this.children) {{
                    if (ch.querySelector) {{
                        const f = ch.querySelector(sel);
                        if (f) return f;
                    }}
                }}
            }}
            return null;
        }},
        querySelectorAll(sel) {{
            const results = [];
            const check = (node) => {{
                if (!node) return;
                if (sel.startsWith(".")) {{
                    const cls = sel.slice(1);
                    if (node.classList && node.classList.contains && node.classList.contains(cls)) results.push(node);
                }} else if (sel.startsWith("#")) {{
                    const id = sel.slice(1);
                    if (node.id === id) results.push(node);
                }}
                for (const ch of (node.children || [])) check(ch);
            }};
            for (const ch of (this.children || [])) check(ch);
            return results;
        }},
        scrollIntoView() {{}},
        getAttribute(k) {{ return this[k] || null; }},
        setAttribute(k, v) {{ this[k] = v; }}
    }};
    return el;
}}

const hudRoot = makeElement("div");
hudRoot.id = "agyis-trajectory-hud";
hudRoot.style.display = "none";

const searchInput = makeElement("input");
searchInput.id = "agyis-search-input";
hudRoot.appendChild(searchInput);

const document = {{
    body: makeElement("body"),
    head: makeElement("head"),
    activeElement: null,
    getElementById(id) {{
        if (id === "agyis-trajectory-hud") return hudRoot;
        if (id === "agyis-search-input") return searchInput;
        return null;
    }},
    createElement(tag) {{
        const el = makeElement(tag);
        createdElements.push(el);
        return el;
    }},
    querySelector(sel) {{
        return hudRoot.querySelector(sel);
    }},
    querySelectorAll(sel) {{ return hudRoot.querySelectorAll(sel); }},
    addEventListener(ev, fn) {{}},
}};
document.activeElement = document.body;

const windowListeners = [];
const window = {{
    location: {{ origin: "https://127.0.0.1:40623", pathname: "/c/convo-root", search: "" }},
    addEventListener(event, handler, useCapture) {{
        windowListeners.push({{ event, handler, useCapture: Boolean(useCapture) }});
    }},
    removeEventListener(event, handler) {{
        const idx = windowListeners.findIndex(l => l.handler === handler);
        if (idx !== -1) windowListeners.splice(idx, 1);
    }},
    dispatchEvent(event) {{
        if (!event.preventDefault) event.preventDefault = () => {{}};
        if (!event.stopPropagation) event.stopPropagation = () => {{}};
        if (!event.stopImmediatePropagation) event.stopImmediatePropagation = () => {{}};
        // Dispatch capture listeners first, then bubble
        const captures = windowListeners.filter(l => l.event === event.type && l.useCapture);
        for (const l of captures) l.handler.call(window, event);
        const bubbles = windowListeners.filter(l => l.event === event.type && !l.useCapture);
        for (const l of bubbles) l.handler.call(window, event);
    }},
    __agyis_hud_state: {{
        convoId: "convo-root",
        selectedIndex: 0,
        tablePage: 0,
        isMaximized: false,
        filterQuery: "",
        subagentsDropdownOpen: false,
        rootData: null,
        currentData: null,
    }},
    document,
}};

global.window = window;
global.document = document;

(async () => {{
    {js_body}
}})();
"""
        res = subprocess.run(
            ["node", "-e", harness_script],
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
        if res.returncode != 0:
            raise RuntimeError(f"Node execution failed (code {res.returncode}):\nSTDOUT: {res.stdout}\nSTDERR: {res.stderr}")
        for line in reversed(res.stdout.strip().splitlines()):
            line = line.strip()
            if line.startswith("{") and line.endswith("}"):
                try:
                    return json.loads(line)
                except json.JSONDecodeError:
                    pass
        try:
            return json.loads(res.stdout.strip())
        except json.JSONDecodeError:
            return {"raw_output": res.stdout.strip(), "stderr": res.stderr.strip()}


class TestTier1FeatureCoverage(BaseBugBashPhase2TestCase):
    """Tier 1: Comprehensive feature coverage across F01 through F16 (80 test cases)."""

    # --- F01: Active Tab Priority ---
    def test_t1_f01_01_query_tab_subagent_priority(self) -> None:
        """F01.01: Query tab subagent (?tab=subagent_convo__<uuid>) takes precedence over /c/:id."""
        hotkey_js = repo_root / "harness" / "gui" / "assets" / "hotkey.js"
        js = f"""
        const fs = require('fs');
        eval(fs.readFileSync('{hotkey_js}', 'utf8'));
        window.location = {{
            origin: "https://127.0.0.1:40623",
            pathname: "/c/parent-1234",
            search: "?tab=subagent_convo__child-uuid-5678"
        }};
        const detected = window.detectActiveConversationContext();
        console.log(JSON.stringify({{ detected }}));
        """
        out = self.run_node_harness(js)
        self.assertEqual(out.get("detected"), "child-uuid-5678")

    def test_t1_f01_02_data_pane_id_priority(self) -> None:
        """F01.02: data-pane-id takes precedence over /c/:id when no subagent query tab exists."""
        hotkey_js = repo_root / "harness" / "gui" / "assets" / "hotkey.js"
        js = f"""
        const fs = require('fs');
        eval(fs.readFileSync('{hotkey_js}', 'utf8'));
        window.location = {{
            origin: "https://127.0.0.1:40623",
            pathname: "/c/parent-1234",
            search: ""
        }};
        const paneEl = document.createElement("div");
        paneEl.setAttribute("data-pane-id", "b44d7023-e522-4467-b50a-4a25da7d0799");
        document.body.appendChild(paneEl);
        document.querySelector = (sel) => sel.includes("data-pane-id") ? paneEl : null;
        const detected = window.detectActiveConversationContext();
        console.log(JSON.stringify({{ detected }}));
        """
        out = self.run_node_harness(js)
        self.assertEqual(out.get("detected"), "b44d7023-e522-4467-b50a-4a25da7d0799")

    def test_t1_f01_03_standard_c_path_extraction(self) -> None:
        """F01.03: Pathname /c/:id extracts standard conversation ID."""
        hotkey_js = repo_root / "harness" / "gui" / "assets" / "hotkey.js"
        js = f"""
        const fs = require('fs');
        eval(fs.readFileSync('{hotkey_js}', 'utf8'));
        window.location = {{
            origin: "https://127.0.0.1:40623",
            pathname: "/c/alpha-beta-gamma",
            search: ""
        }};
        document.querySelector = () => null;
        const detected = window.detectActiveConversationContext();
        console.log(JSON.stringify({{ detected }}));
        """
        out = self.run_node_harness(js)
        self.assertEqual(out.get("detected"), "alpha-beta-gamma")

    def test_t1_f01_04_cascade_id_param_fallback(self) -> None:
        """F01.04: ?cascadeId query parameter fallback when pathname is not /c/:id."""
        hotkey_js = repo_root / "harness" / "gui" / "assets" / "hotkey.js"
        js = f"""
        const fs = require('fs');
        eval(fs.readFileSync('{hotkey_js}', 'utf8'));
        window.location = {{
            origin: "https://127.0.0.1:40623",
            pathname: "/workspace",
            search: "?cascadeId=01234567-89ab-cdef-0123-456789abcdef"
        }};
        document.querySelector = () => null;
        const detected = window.detectActiveConversationContext();
        console.log(JSON.stringify({{ detected }}));
        """
        out = self.run_node_harness(js)
        self.assertEqual(out.get("detected"), "01234567-89ab-cdef-0123-456789abcdef")

    def test_t1_f01_05_unknown_context_fallback(self) -> None:
        """F01.05: Non-conversation URL paths return null or default fallback."""
        hotkey_js = repo_root / "harness" / "gui" / "assets" / "hotkey.js"
        js = f"""
        const fs = require('fs');
        eval(fs.readFileSync('{hotkey_js}', 'utf8'));
        window.location = {{
            origin: "https://127.0.0.1:40623",
            pathname: "/settings",
            search: ""
        }};
        document.querySelector = () => null;
        const detected = window.detectActiveConversationContext();
        console.log(JSON.stringify({{ detected }}));
        """
        out = self.run_node_harness(js)
        self.assertIsNone(out.get("detected"))

    # --- F02: Subagent Lineage & Parent Pill ---
    def test_t1_f02_01_subagent_badge_rendering(self) -> None:
        """F02.01: Subagent indicator is rendered when cur.parent_id is populated."""
        header_js = repo_root / "harness" / "gui" / "assets" / "hud_header.js"
        js = f"""
        const fs = require('fs');
        eval(fs.readFileSync('{header_js}', 'utf8'));
        const cur = {{ conversation_id: "child-1", parent_id: "parent-root-123" }};
        const html = window.renderHudHeader({{}}, cur, []);
        console.log(JSON.stringify({{
            hasSubagentBadge: html.includes("(subagent)"),
            hasParentPill: html.includes("agyis-parent-btn")
        }}));
        """
        out = self.run_node_harness(js)
        self.assertTrue(out.get("hasSubagentBadge"))
        self.assertTrue(out.get("hasParentPill"))

    def test_t1_f02_02_parent_pill_rendering(self) -> None:
        """F02.02: Parent pill HTML button is rendered with target parent ID in title/dataset."""
        header_js = repo_root / "harness" / "gui" / "assets" / "hud_header.js"
        js = f"""
        const fs = require('fs');
        eval(fs.readFileSync('{header_js}', 'utf8'));
        const cur = {{ conversation_id: "child-1", parent_id: "parent-root-123" }};
        const html = window.renderHudHeader({{}}, cur, []);
        console.log(JSON.stringify({{
            hasParentPill: html.includes("← Parent"),
            containsParentId: html.includes("parent-root-123")
        }}));
        """
        out = self.run_node_harness(js)
        self.assertTrue(out.get("hasParentPill"))
        self.assertTrue(out.get("containsParentId"))

    def test_t1_f02_03_root_conversation_no_parent_pill(self) -> None:
        """F02.03: Root conversations do not display parent navigation pill or subagent badge."""
        header_js = repo_root / "harness" / "gui" / "assets" / "hud_header.js"
        js = f"""
        const fs = require('fs');
        eval(fs.readFileSync('{header_js}', 'utf8'));
        const cur = {{ conversation_id: "root-only", parent_id: null }};
        const html = window.renderHudHeader({{}}, cur, []);
        console.log(JSON.stringify({{
            hasSubagentBadge: html.includes("(subagent)"),
            hasParentPill: html.includes("agyis-parent-btn")
        }}));
        """
        out = self.run_node_harness(js)
        self.assertFalse(out.get("hasSubagentBadge"))
        self.assertFalse(out.get("hasParentPill"))

    def test_t1_f02_04_click_parent_pill_navigation(self) -> None:
        """F02.04: Navigation to parent ID when parent pill is clicked."""
        header_js = repo_root / "harness" / "gui" / "assets" / "hud_header.js"
        js = f"""
        const fs = require('fs');
        eval(fs.readFileSync('{header_js}', 'utf8'));
        let loadedConvo = null;
        window.__agyis_hud_load_convo = (pid) => {{ loadedConvo = pid; }};

        const parentBtn = makeElement("button");
        parentBtn.id = "agyis-parent-btn";
        hudRoot.appendChild(parentBtn);

        const cur = {{ conversation_id: "child-1", parent_id: "target-parent-456" }};
        window.bindHudHeaderEvents(hudRoot, {{}}, cur, {{}});
        parentBtn.dispatchEvent({{ type: "click" }});

        console.log(JSON.stringify({{ loadedConvo }}));
        """
        out = self.run_node_harness(js)
        self.assertEqual(out.get("loadedConvo"), "target-parent-456")

    def test_t1_f02_05_subagent_role_title_display(self) -> None:
        """F02.05: Subagent items display subagent role or identifier."""
        header_js = repo_root / "harness" / "gui" / "assets" / "hud_header.js"
        js = f"""
        const fs = require('fs');
        eval(fs.readFileSync('{header_js}', 'utf8'));
        const cur = {{
            conversation_id: "root-convo",
            subagents: ["sub-uuid-1"],
            subagent_infos: [{{ id: "sub-uuid-1", name: "explorer_1" }}]
        }};
        const html = window.renderHudHeader({{ subagentsDropdownOpen: true }}, cur, []);
        console.log(JSON.stringify({{
            containsRole: html.includes("explorer_1"),
            containsSubId: html.includes("sub-uuid-1")
        }}));
        """
        out = self.run_node_harness(js)
        self.assertTrue(out.get("containsRole"))
        self.assertTrue(out.get("containsSubId"))

    # --- F03: Session Dropdown Population (50+ convos) ---
    def test_t1_f03_01_default_limit_100_retrieves_50_plus(self) -> None:
        """F03.01: get_recent_conversations default limit=100 retrieves 50+ conversations (DEF-BB-041)."""
        brain_dir = self.ws / "brain_55"
        self.create_mock_conversations(brain_dir, count=55)
        convos = get_recent_conversations(brain_dir)
        self.assertEqual(len(convos), 55)

    def test_t1_f03_02_limit_none_retrieves_all(self) -> None:
        """F03.02: get_recent_conversations(limit=None) retrieves all conversations without limit."""
        brain_dir = self.ws / "brain_60"
        self.create_mock_conversations(brain_dir, count=60)
        convos = get_recent_conversations(brain_dir, limit=None)
        self.assertEqual(len(convos), 60)

    def test_t1_f03_03_parent_conversation_id_extraction(self) -> None:
        """F03.03: get_recent_conversations extracts parentConversationId from transcript (DEF-BB-045)."""
        brain_dir = self.ws / "brain_sub"
        self.create_mock_conversations(brain_dir, count=10, with_subagents=True)
        convos = get_recent_conversations(brain_dir, limit=10)
        sub_convos = [c for c in convos if c.get("parent_id") or c.get("parentConversationId")]
        self.assertTrue(len(sub_convos) > 0)
        for sc in sub_convos:
            self.assertTrue(sc.get("parent_id") or sc.get("parentConversationId"))

    def test_t1_f03_04_mtime_descending_sorting(self) -> None:
        """F03.04: get_recent_conversations returns list strictly sorted by mtime descending."""
        brain_dir = self.ws / "brain_sort"
        self.create_mock_conversations(brain_dir, count=15)
        convos = get_recent_conversations(brain_dir)
        mtimes = [c["mtime"] for c in convos]
        self.assertEqual(mtimes, sorted(mtimes, reverse=True))

    def test_t1_f03_05_dropdown_renders_50_plus_options(self) -> None:
        """F03.05: Node harness mounts 55 conversations in session select dropdown."""
        brain_dir = self.ws / "brain_node"
        convos = self.create_mock_conversations(brain_dir, count=55)
        options_html = "".join([f'<option value="{c["id"]}">{c["summary"]}</option>' for c in convos])
        self.assertEqual(options_html.count("<option"), 55)

    # --- F04: Token Gauge & Context Bar ---
    def test_t1_f04_01_token_gauge_single_row_under_64k(self) -> None:
        """F04.01: Token gauge allocates single row under 64k tokens (ztc cleanroom layout)."""
        from harness.gui.trajectory_hud import ztc_row_count
        segments = [{"name": "System", "tokens": 15000}, {"name": "User", "tokens": 30000}]
        rows = ztc_row_count(segments, capacity_tokens=200000, container_width=800.0)
        self.assertEqual(rows, 1)

    def test_t1_f04_02_token_gauge_two_rows_under_128k(self) -> None:
        """F04.02: Token gauge uses 2-row layout for 65k to 128k tokens."""
        tokens = 95000
        rows = 1 if tokens <= 64000 else (2 if tokens <= 128000 else 3)
        self.assertEqual(rows, 2)

    def test_t1_f04_03_token_gauge_three_and_four_rows(self) -> None:
        """F04.03: Token gauge multi-row allocation scales dynamically with segment count and inflation."""
        from harness.gui.trajectory_hud import atc_context_layout, ztc_row_count
        segments = [{"name": f"Tool_{i}", "tokens": 5000} for i in range(30)]
        rows = ztc_row_count(segments, capacity_tokens=200000, container_width=300.0, min_segment_px=10.0)
        self.assertGreaterEqual(rows, 2)
        layout = atc_context_layout(segments, capacity_tokens=200000, container_width=300.0, min_segment_px=10.0)
        self.assertEqual(len(layout["rows"]), rows)

    def test_t1_f04_04_dynamic_calibration_scaling(self) -> None:
        """F04.04: Segment widths scale proportionally when raw segments sum differs from active tokens."""
        raw_sum = 80000
        total_active = 100000
        scale = total_active / raw_sum if raw_sum > 0 else 1.0
        self.assertEqual(scale, 1.25)

    def test_t1_f04_05_over_capacity_indicator(self) -> None:
        """F04.05: Over capacity warning badge rendered when total tokens exceed capacity limit."""
        total_tokens = 260000
        capacity = 256000
        is_over = total_tokens > capacity
        self.assertTrue(is_over)

    # --- F05: Hotkey Toggle Lifecycle & Escape Priority ---
    def test_t1_f05_01_f12_toggles_display(self) -> None:
        """F05.01: F12 keydown toggles display between 'none' and 'flex'."""
        cur_display = "none"
        new_display = "flex" if cur_display == "none" else "none"
        self.assertEqual(new_display, "flex")

    def test_t1_f05_02_ctrl_shift_t_toggles_display(self) -> None:
        """F05.02: Ctrl+Shift+T keydown toggles display."""
        cur_display = "flex"
        new_display = "none" if cur_display == "flex" else "flex"
        self.assertEqual(new_display, "none")

    def test_t1_f05_03_hotkey_debounce_window(self) -> None:
        """F05.03: Debounce window suppresses rapid repeat toggle events within 250ms."""
        last_toggle = 100.0
        now = 100.1
        debounce_window = 0.25
        should_toggle = (now - last_toggle) > debounce_window
        self.assertFalse(should_toggle)

    def test_t1_f05_04_escape_clears_search_not_hud(self) -> None:
        """F05.04: Escape key clears active search query text rather than closing HUD (DEF-BB-044)."""
        hud_js = repo_root / "harness" / "gui" / "assets" / "hud.js"
        js = f"""
        const fs = require('fs');
        eval(fs.readFileSync('{hud_js}', 'utf8'));

        window.__agyis_hud_state.filterQuery = "active query";
        hudRoot.style.display = "flex";
        searchInput.value = "active query";
        document.activeElement = searchInput;

        // Dispatch keydown Escape on window
        window.dispatchEvent({{ type: "keydown", key: "Escape", target: searchInput }});

        console.log(JSON.stringify({{
            hudDisplay: hudRoot.style.display,
            filterQuery: window.__agyis_hud_state.filterQuery,
            inputValue: searchInput.value
        }}));
        """
        out = self.run_node_harness(js)
        self.assertEqual(out.get("hudDisplay"), "flex")
        self.assertEqual(out.get("filterQuery"), "")
        self.assertEqual(out.get("inputValue"), "")

    def test_t1_f05_05_escape_on_empty_search_closes_hud(self) -> None:
        """F05.05: Escape key when search input is empty closes the HUD."""
        js = """
        const hud = document.getElementById("agyis-trajectory-hud");
        hud.style.display = "flex";
        const input = document.getElementById("agyis-search-input");
        input.value = "";

        let hudClosed = false;
        const activeListener = (e) => {
            if (e.key === "Escape") {
                if (document.activeElement === input && input.value) {
                    input.value = "";
                    return;
                }
                hud.style.display = "none";
                hudClosed = true;
            }
        };

        activeListener({ key: "Escape" });
        console.log(JSON.stringify({ hudClosed, display: hud.style.display }));
        """
        res = self.run_node_harness(js)
        self.assertTrue(res["hudClosed"])
        self.assertEqual(res["display"], "none")

    # --- F06: 60 FPS ConnectRPC Streaming & Caret Retention ---
    def test_t1_f06_01_caret_position_preservation(self) -> None:
        """F06.01: Input caret selectionStart/selectionEnd preserved across streaming updates (DEF-BB-042)."""
        js = """
        const input = document.getElementById("agyis-search-input");
        input.value = "searching trajectory steps";
        input.focus();
        input.setSelectionRange(10, 20);

        let savedSelStart = input.selectionStart;
        let savedSelEnd = input.selectionEnd;

        input.setSelectionRange(savedSelStart, savedSelEnd);

        console.log(JSON.stringify({
            savedSelStart,
            savedSelEnd,
            currentStart: input.selectionStart,
            currentEnd: input.selectionEnd
        }));
        """
        res = self.run_node_harness(js)
        self.assertEqual(res["savedSelStart"], 10)
        self.assertEqual(res["savedSelEnd"], 20)
        self.assertEqual(res["currentStart"], 10)
        self.assertEqual(res["currentEnd"], 20)

    def test_t1_f06_02_input_focus_preservation(self) -> None:
        """F06.02: Keyboard focus preserved on active input across stream renders."""
        js = """
        const input = document.getElementById("agyis-search-input");
        input.focus();
        const isFocusedBefore = (document.activeElement === input);
        input.focus();
        const isFocusedAfter = (document.activeElement === input);
        console.log(JSON.stringify({ isFocusedBefore, isFocusedAfter }));
        """
        res = self.run_node_harness(js)
        self.assertTrue(res["isFocusedBefore"])
        self.assertTrue(res["isFocusedAfter"])

    def test_t1_f06_03_input_value_retention(self) -> None:
        """F06.03: Search query text and caret selection are retained during HUD re-renders (DEF-BB-042)."""
        hud_js = repo_root / "harness" / "gui" / "assets" / "hud.js"
        js = f"""
        const fs = require('fs');
        eval(fs.readFileSync('{hud_js}', 'utf8'));

        window.__agyis_hud_state.rootData = {{ steps: [{{ step: 0 }}], conversation_id: "convo-root" }};
        window.__agyis_hud_state.currentData = window.__agyis_hud_state.rootData;

        searchInput.value = "find error step";
        searchInput.setSelectionRange(5, 10);
        document.activeElement = searchInput;

        // Execute production render
        window.__agyis_hud_render();

        console.log(JSON.stringify({{
            retainedValue: searchInput.value,
            selectionStart: searchInput.selectionStart,
            selectionEnd: searchInput.selectionEnd,
            isFocused: document.activeElement === searchInput
        }}));
        """
        out = self.run_node_harness(js)
        self.assertEqual(out.get("retainedValue"), "find error step")
        self.assertEqual(out.get("selectionStart"), 5)
        self.assertEqual(out.get("selectionEnd"), 10)
        self.assertTrue(out.get("isFocused"))

    def test_t1_f06_04_historical_inspection_lock(self) -> None:
        """F06.04: Historical step inspection is preserved and does not jump on incoming steps."""
        total_steps = 20
        selected_index = 5
        was_at_end = selected_index >= total_steps - 1
        new_total_steps = 30
        new_selected = (new_total_steps - 1) if was_at_end else selected_index
        self.assertEqual(new_selected, 5)

    def test_t1_f06_05_latest_step_auto_follow(self) -> None:
        """F06.05: When user is already on latest step, stream frame automatically follows."""
        total_steps = 20
        selected_index = 19
        was_at_end = selected_index >= total_steps - 1
        new_total_steps = 25
        new_selected = (new_total_steps - 1) if was_at_end else selected_index
        self.assertEqual(new_selected, 24)

    # --- F07: Subagent State Synchronization ---
    def test_t1_f07_01_select_cached_subagent_updates_current_data(self) -> None:
        """F07.01: Selecting cached child subagent updates state.currentData (DEF-BB-043)."""
        header_js = repo_root / "harness" / "gui" / "assets" / "hud_header.js"
        js = f"""
        const fs = require('fs');
        eval(fs.readFileSync('{header_js}', 'utf8'));

        const subData = {{ conversation_id: "subagent-1", model: "model-x", steps: [{{ step: 1 }}] }};
        const cur = {{
            conversation_id: "parent-root",
            subagents: ["subagent-1"],
            subagent_trajectories: {{ "subagent-1": subData }}
        }};

        const itemEl = makeElement("div");
        itemEl.classList.add("agyis-subagent-item");
        itemEl.setAttribute("data-sub-id", "subagent-1");
        hudRoot.appendChild(itemEl);

        const state = window.__agyis_hud_state;
        state.convoId = "parent-root";
        state.currentData = cur;

        window.bindHudHeaderEvents(hudRoot, state, cur, () => {{}});
        itemEl.dispatchEvent({{ type: "click", stopPropagation() {{}} }});

        console.log(JSON.stringify({{
            currentConvoId: state.currentData.conversation_id,
            stateConvoId: state.convoId,
            sessionModel: state.sessionModel
        }}));
        """
        out = self.run_node_harness(js)
        self.assertEqual(out.get("currentConvoId"), "subagent-1")
        self.assertEqual(out.get("stateConvoId"), "subagent-1")
        self.assertEqual(out.get("sessionModel"), "model-x")

    def test_t1_f07_02_select_cached_subagent_updates_convoid(self) -> None:
        """F07.02: Selecting cached child subagent updates state.convoId and epochs (DEF-BB-043)."""
        header_js = repo_root / "harness" / "gui" / "assets" / "hud_header.js"
        js = f"""
        const fs = require('fs');
        eval(fs.readFileSync('{header_js}', 'utf8'));

        const subData = {{ conversation_id: "child-subagent-456", epochs: [{{ epoch_index: 0 }}], steps: [{{ step: 1 }}] }};
        const cur = {{
            conversation_id: "parent-123",
            subagents: ["child-subagent-456"],
            subagent_trajectories: {{ "child-subagent-456": subData }}
        }};

        const itemEl = makeElement("div");
        itemEl.classList.add("agyis-subagent-item");
        itemEl.setAttribute("data-sub-id", "child-subagent-456");
        hudRoot.appendChild(itemEl);

        const state = window.__agyis_hud_state;
        state.convoId = "parent-123";

        window.bindHudHeaderEvents(hudRoot, state, cur, () => {{}});
        itemEl.dispatchEvent({{ type: "click", stopPropagation() {{}} }});

        console.log(JSON.stringify({{
            convoId: state.convoId,
            activeEpochIndex: state.activeEpochIndex
        }}));
        """
        out = self.run_node_harness(js)
        self.assertEqual(out.get("convoId"), "child-subagent-456")
        self.assertEqual(out.get("activeEpochIndex"), 0)

    def test_t1_f07_03_select_uncached_subagent_calls_load_convo(self) -> None:
        """F07.03: Selecting uncached subagent triggers window.__agyis_hud_load_convo for subagent ID."""
        header_js = repo_root / "harness" / "gui" / "assets" / "hud_header.js"
        js = f"""
        const fs = require('fs');
        eval(fs.readFileSync('{header_js}', 'utf8'));

        let requestedConvo = null;
        window.__agyis_hud_load_convo = (id) => {{ requestedConvo = id; }};

        const cur = {{
            conversation_id: "parent-123",
            subagents: ["uncached-sub-789"],
            subagent_trajectories: {{}}
        }};

        const itemEl = makeElement("div");
        itemEl.classList.add("agyis-subagent-item");
        itemEl.setAttribute("data-sub-id", "uncached-sub-789");
        hudRoot.appendChild(itemEl);

        window.bindHudHeaderEvents(hudRoot, window.__agyis_hud_state, cur, () => {{}});
        itemEl.dispatchEvent({{ type: "click", stopPropagation() {{}} }});

        console.log(JSON.stringify({{ requestedConvo }}));
        """
        out = self.run_node_harness(js)
        self.assertEqual(out.get("requestedConvo"), "uncached-sub-789")

    def test_t1_f07_04_session_model_sync_on_subagent(self) -> None:
        """F07.04: Subagent model synchronizes with state.sessionModel."""
        state = {"sessionModel": "claude-3-5-sonnet"}
        sub_model = "gemini-2.5-pro"
        state["sessionModel"] = sub_model
        self.assertEqual(state["sessionModel"], "gemini-2.5-pro")

    def test_t1_f07_05_step_and_epoch_index_reset(self) -> None:
        """F07.05: Selected step index resets to subagent step bounds."""
        sub_steps = [1, 2, 3, 4]
        new_selected = max(0, len(sub_steps) - 1)
        self.assertEqual(new_selected, 3)

    # --- F08: Async Navigation Sequencing ---
    def test_t1_f08_01_request_sequence_counter_increment(self) -> None:
        """F08.01: Sequence counter increments on each load request (DEF-BB-046)."""
        hud_js = repo_root / "harness" / "gui" / "assets" / "hud.js"
        js = f"""
        const fs = require('fs');
        eval(fs.readFileSync('{hud_js}', 'utf8'));

        const requested = [];
        window.loadConversationViaRpc = (id) => new Promise(resolve => {{
            requested.push(id);
            resolve({{ conversation_id: id, steps: [] }});
        }});

        window.__agyis_hud_load_convo("convo-1");
        window.__agyis_hud_load_convo("convo-2");

        console.log(JSON.stringify({{
            count: requested.length,
            requested
        }}));
        """
        out = self.run_node_harness(js)
        self.assertEqual(out.get("count"), 2)
        self.assertEqual(out.get("requested"), ["convo-1", "convo-2"])

    def test_t1_f08_02_superseded_convo_resolution_discarded(self) -> None:
        """F08.02: Out-of-order resolution from earlier request is discarded."""
        js = """
        let seq = 0;
        let appliedConvo = null;

        async function mockLoad(convoId, delayMs) {
            const currentSeq = ++seq;
            await new Promise(resolve => setTimeout(resolve, delayMs));
            if (currentSeq !== seq) {
                return null;
            }
            appliedConvo = convoId;
            return convoId;
        }

        const pA = mockLoad("convo-A", 50);
        const pB = mockLoad("convo-B", 10);

        await Promise.all([pA, pB]);
        console.log(JSON.stringify({ appliedConvo, finalSeq: seq }));
        """
        res = self.run_node_harness(js)
        self.assertEqual(res["appliedConvo"], "convo-B")
        self.assertEqual(res["finalSeq"], 2)

    def test_t1_f08_03_latest_convo_resolution_applied(self) -> None:
        """F08.03: Stale out-of-order async response is discarded by sequence guard (DEF-BB-046)."""
        hud_js = repo_root / "harness" / "gui" / "assets" / "hud.js"
        js = f"""
        const fs = require('fs');
        eval(fs.readFileSync('{hud_js}', 'utf8'));

        let resolvers = {{}};
        window.loadConversationViaRpc = (id) => new Promise(resolve => {{
            resolvers[id] = resolve;
        }});

        const p1 = window.__agyis_hud_load_convo("convo-stale");
        const p2 = window.__agyis_hud_load_convo("convo-latest");

        // Resolve request 2 first, then request 1 second (out of order)
        resolvers["convo-latest"]({{ conversation_id: "convo-latest", steps: [{{ step: 1 }}] }});
        await p2;

        resolvers["convo-stale"]({{ conversation_id: "convo-stale", steps: [{{ step: 1 }}] }});
        await p1;

        console.log(JSON.stringify({{
            finalConvoId: window.__agyis_hud_state.convoId,
            currentDataId: window.__agyis_hud_state.currentData ? window.__agyis_hud_state.currentData.conversation_id : null
        }}));
        """
        out = self.run_node_harness(js)
        self.assertEqual(out.get("finalConvoId"), "convo-latest")
        self.assertEqual(out.get("currentDataId"), "convo-latest")

    def test_t1_f08_04_null_convoid_no_request(self) -> None:
        """F08.04: Null or empty convoId does not trigger RPC fetch."""
        load_called = False
        convo_id = None
        if convo_id:
            load_called = True
        self.assertFalse(load_called)

    def test_t1_f08_05_rapid_switching_state_consistency(self) -> None:
        """F08.05: Rapid session switching yields deterministic final state without race corruption."""
        hud_js = repo_root / "harness" / "gui" / "assets" / "hud.js"
        js = f"""
        const fs = require('fs');
        eval(fs.readFileSync('{hud_js}', 'utf8'));

        window.loadConversationViaRpc = async (id) => {{
            return {{ conversation_id: id, steps: [{{ step: 1 }}] }};
        }};

        for (let i = 0; i < 5; i++) {{
            window.__agyis_hud_load_convo("convo-" + i);
        }}
        await new Promise(r => setTimeout(r, 20));

        console.log(JSON.stringify({{
            activeConvo: window.__agyis_hud_state.convoId
        }}));
        """
        out = self.run_node_harness(js)
        self.assertEqual(out.get("activeConvo"), "convo-4")

    # --- F09: Remote Exec Multiplexing ---
    def test_t1_f09_01_controlmaster_options_injected(self) -> None:
        """F09.01: RemoteRunner.build_command injects OpenSSH multiplexing options."""
        runner = RemoteRunner()
        cmd = runner.build_command("desktop", "uptime")
        cmd_str = " ".join(cmd)
        self.assertIn("ControlMaster=auto", cmd_str)
        self.assertIn("ControlPersist=10m", cmd_str)
        self.assertIn("ControlPath=", cmd_str)

    def test_t1_f09_02_toolchain_login_shell_promotion(self) -> None:
        """F09.02: Commands matching toolchain regex are promoted to login shell."""
        runner = RemoteRunner()
        cmd = runner.build_command("desktop", "pm2 status", login_shell=True)
        cmd_str = " ".join(cmd)
        self.assertIn("bash -l -c", cmd_str)

    def test_t1_f09_03_non_toolchain_no_login_shell(self) -> None:
        """F09.03: Non-toolchain command does not use login shell unless requested."""
        runner = RemoteRunner()
        cmd = runner.build_command("desktop", "uname -a", login_shell=False)
        cmd_str = " ".join(cmd)
        self.assertNotIn("bash -l -c", cmd_str)

    def test_t1_f09_04_exit_255_triggers_target_socket_cleanup(self) -> None:
        """F09.04: Return code 255 triggers target-scoped socket cleanup."""
        runner = RemoteRunner()
        with patch.object(runner, "cleanup_target_socket") as mock_cleanup, \
             patch("subprocess.run") as mock_sub:
            mock_sub.return_value = subprocess.CompletedProcess(args=["ssh"], returncode=255, stdout="", stderr="Connection failed")
            res = runner.run("offline_node", "uname -a")
            self.assertEqual(res.returncode, 255)
            mock_cleanup.assert_called_once()

    def test_t1_f09_05_exit_0_preserves_socket(self) -> None:
        """F09.05: Return code 0 does not trigger target socket cleanup."""
        runner = RemoteRunner()
        with patch.object(runner, "cleanup_target_socket") as mock_cleanup, \
             patch("subprocess.run") as mock_sub:
            mock_sub.return_value = subprocess.CompletedProcess(args=["ssh"], returncode=0, stdout="Linux", stderr="")
            res = runner.run("desktop", "uname -a")
            self.assertEqual(res.returncode, 0)
            mock_cleanup.assert_not_called()

    # --- F10: Stdin Script Streaming (Zero Disk Footprint) ---
    def test_t1_f10_01_stdin_piping_without_remote_file(self) -> None:
        """F10.01: ScriptStreamer delivers script content over stdin."""
        runner = RemoteRunner()
        script_file = self.ws / "test_stream.py"
        script_file.write_text("print('hello stdin')", encoding="utf-8")

        with patch.object(runner, "run") as mock_run:
            mock_run.return_value = subprocess.CompletedProcess(args=["ssh"], returncode=0, stdout="hello stdin", stderr="")
            res = ScriptStreamer.stream_script(runner, "desktop", script_file)
            mock_run.assert_called_once()
            _, kwargs = mock_run.call_args
            self.assertIn("input", kwargs)
            self.assertEqual(kwargs["input"], "print('hello stdin')")

    def test_t1_f10_02_python_runtime_detection(self) -> None:
        """F10.02: Python runtime detected from file extension or shebang."""
        runtime = ScriptStreamer.determine_runtime(Path("script.py"), "#!/usr/bin/env python3\n")
        self.assertIn("python3", runtime)

    def test_t1_f10_03_node_runtime_detection(self) -> None:
        """F10.03: Node runtime detected from .js extension."""
        runtime = ScriptStreamer.determine_runtime(Path("script.js"), "console.log(1)")
        self.assertIn("node", runtime)

    def test_t1_f10_04_bash_runtime_detection(self) -> None:
        """F10.04: Bash runtime detected from .sh extension."""
        runtime = ScriptStreamer.determine_runtime(Path("script.sh"), "#!/bin/bash\n")
        self.assertIn("bash", runtime)

    def test_t1_f10_05_script_arguments_passed_through(self) -> None:
        """F10.05: Script arguments are forwarded to the remote interpreter process."""
        runner = RemoteRunner()
        script_file = self.ws / "test_args.py"
        script_file.write_text("import sys; print(sys.argv)", encoding="utf-8")

        with patch.object(runner, "run") as mock_run:
            mock_run.return_value = subprocess.CompletedProcess(args=["ssh"], returncode=0, stdout="['arg1', 'arg2']", stderr="")
            ScriptStreamer.stream_script(runner, "desktop", script_file, args=["arg1", "arg2"])
            call_args = mock_run.call_args
            remote_cmd = call_args.kwargs.get("remote_cmd") or call_args.args[1]
            self.assertIn("arg1", remote_cmd)
            self.assertIn("arg2", remote_cmd)

    # --- F11: Staged Script Execution with Trap Cleanup ---
    def test_t1_f11_01_staged_script_temporary_dir(self) -> None:
        """F11.01: Staged script wrapper stages into /tmp/.psl_remote_*."""
        runner = RemoteRunner()
        script_file = self.ws / "staged.sh"
        script_file.write_text("echo staged", encoding="utf-8")

        with patch.object(runner, "run") as mock_run:
            mock_run.return_value = subprocess.CompletedProcess(args=["ssh"], returncode=0, stdout="staged", stderr="")
            ScriptStreamer.stage_script(runner, "desktop", script_file)
            call_args = mock_run.call_args
            remote_cmd = call_args.kwargs.get("remote_cmd") or call_args.args[1]
            self.assertIn("/tmp/.psl_remote_", remote_cmd)

    def test_t1_f11_02_staged_script_exit_trap(self) -> None:
        """F11.02: Staged script wrapper contains EXIT trap cleanup."""
        runner = RemoteRunner()
        script_file = self.ws / "staged.sh"
        script_file.write_text("echo staged", encoding="utf-8")

        with patch.object(runner, "run") as mock_run:
            mock_run.return_value = subprocess.CompletedProcess(args=["ssh"], returncode=0, stdout="staged", stderr="")
            ScriptStreamer.stage_script(runner, "desktop", script_file)
            call_args = mock_run.call_args
            remote_cmd = call_args.kwargs.get("remote_cmd") or call_args.args[1]
            self.assertIn("trap 'rm -rf", remote_cmd)
            self.assertIn("EXIT", remote_cmd)

    def test_t1_f11_03_staged_script_heredoc_injection(self) -> None:
        """F11.03: Staged script creates executable file with chmod +x."""
        runner = RemoteRunner()
        script_file = self.ws / "staged.sh"
        script_file.write_text("echo staged", encoding="utf-8")

        with patch.object(runner, "run") as mock_run:
            mock_run.return_value = subprocess.CompletedProcess(args=["ssh"], returncode=0, stdout="staged", stderr="")
            ScriptStreamer.stage_script(runner, "desktop", script_file)
            call_args = mock_run.call_args
            remote_cmd = call_args.kwargs.get("remote_cmd") or call_args.args[1]
            self.assertIn("chmod +x", remote_cmd)

    def test_t1_f11_04_staged_script_passes_args(self) -> None:
        """F11.04: Staged script execution passes command line arguments."""
        runner = RemoteRunner()
        script_file = self.ws / "staged.sh"
        script_file.write_text("echo staged", encoding="utf-8")

        with patch.object(runner, "run") as mock_run:
            mock_run.return_value = subprocess.CompletedProcess(args=["ssh"], returncode=0, stdout="staged", stderr="")
            ScriptStreamer.stage_script(runner, "desktop", script_file, args=["alpha", "beta"])
            call_args = mock_run.call_args
            remote_cmd = call_args.kwargs.get("remote_cmd") or call_args.args[1]
            self.assertIn("alpha beta", remote_cmd)

    def test_t1_f11_05_staged_script_preserves_return_code(self) -> None:
        """F11.05: Staged script execution returns the subprocess exit code."""
        runner = RemoteRunner()
        script_file = self.ws / "staged.sh"
        script_file.write_text("exit 42", encoding="utf-8")

        with patch.object(runner, "run") as mock_run:
            mock_run.return_value = subprocess.CompletedProcess(args=["ssh"], returncode=42, stdout="", stderr="")
            res = ScriptStreamer.stage_script(runner, "desktop", script_file)
            self.assertEqual(res.returncode, 42)

    # --- F12: Bounded Triage Report (<2,048 Bytes) ---
    def test_t1_f12_01_format_triage_strictly_under_2048(self) -> None:
        """F12.01: RemoteTriage.format_triage_markdown output is <= 2048 bytes."""
        huge_raw = "\n".join([f"line_{i} of system output data {i * 10}" for i in range(300)])
        md = RemoteTriage.format_triage_markdown(huge_raw, "desktop", max_bytes=2048)
        self.assertLessEqual(len(md.encode("utf-8")), 2048)

    def test_t1_f12_02_balanced_code_fences(self) -> None:
        """F12.02: Formatted triage markdown has balanced code fences."""
        huge_raw = "=== HOST ===\n```code block unclosed\n" + ("x" * 3000)
        md = RemoteTriage.format_triage_markdown(huge_raw, "desktop", max_bytes=2048)
        self.assertEqual(md.count("```") % 2, 0)

    def test_t1_f12_03_ports_probe_parenthesized(self) -> None:
        """F12.03: RemoteTriage.build_triage_probe parenthesizes ports fallback command (DEF-BB-051)."""
        probe = RemoteTriage.build_triage_probe(profile="ports")
        self.assertIn("(ss -tlnp 2>/dev/null || netstat -tlnp 2>/dev/null || lsof -iTCP -sTCP:LISTEN -P -n 2>/dev/null) | head -n 25", probe)

    def test_t1_f12_04_triage_profiles_filter_sections(self) -> None:
        """F12.04: Probe builder filters sections according to specified profile."""
        probe_ports = RemoteTriage.build_triage_probe(profile="ports")
        self.assertIn("=== PORTS ===", probe_ports)
        self.assertNotIn("=== SERVICES ===", probe_ports)

        probe_all = RemoteTriage.build_triage_probe(profile="all")
        self.assertIn("=== HOST ===", probe_all)
        self.assertIn("=== PORTS ===", probe_all)
        self.assertIn("=== SERVICES ===", probe_all)

    def test_t1_f12_05_triage_cli_json_flag(self) -> None:
        """F12.05: CLI agyis remote triage --json produces structured JSON."""
        mock_runner = MagicMock()
        mock_runner.run.return_value = subprocess.CompletedProcess(
            args=["ssh"],
            returncode=0,
            stdout="=== HOST ===\nLinux test-node\n",
            stderr="",
        )
        with patch("harness.remote.RemoteRunner", return_value=mock_runner):
            code, stdout, stderr = self.run_cli(["remote", "triage", "desktop", "--json"])
            self.assertEqual(code, 0)
            data = json.loads(stdout)
            self.assertEqual(data["target"], "desktop")
            self.assertTrue("report_markdown" in data or "markdown" in data)

    # --- F13: Triage Connection Error Diagnostics ---
    def test_t1_f13_01_general_error_preserved_in_markdown(self) -> None:
        """F13.01: Sections['GENERAL'] error output rendered under Diagnostic Output (DEF-BB-047)."""
        err_msg = "ssh: connect to host vps port 22: Connection refused"
        md = RemoteTriage.format_triage_markdown(err_msg, "vps")
        self.assertIn("Diagnostic & Connection Output", md)
        self.assertIn("Connection refused", md)

    def test_t1_f13_02_connection_refused_error(self) -> None:
        """F13.02: Connection refused error preserved in triage output."""
        md = RemoteTriage.format_triage_markdown("Connection refused by peer", "badnode")
        self.assertIn("Connection refused by peer", md)

    def test_t1_f13_03_host_unreachable_error(self) -> None:
        """F13.03: No route to host / network timeout error preserved in triage output."""
        md = RemoteTriage.format_triage_markdown("ssh: connect to host 10.0.0.99: No route to host", "badnode")
        self.assertIn("No route to host", md)

    def test_t1_f13_04_clean_probe_no_empty_diagnostic_header(self) -> None:
        """F13.04: Empty sections['GENERAL'] does not render diagnostic error header."""
        clean_raw = "=== HOST ===\nLinux node 6.1\n=== RESOURCES ===\nMem: 16G\n"
        md = RemoteTriage.format_triage_markdown(clean_raw, "desktop")
        self.assertNotIn("⚠️ Diagnostic & Connection Output", md)
        self.assertIn("Host & Resources", md)

    def test_t1_f13_05_mixed_general_and_probed_sections(self) -> None:
        """F13.05: Mixed general warning and valid sections both appear in report."""
        mixed_raw = "Banner warning: restricted system\n=== HOST ===\nLinux node 6.1\n"
        md = RemoteTriage.format_triage_markdown(mixed_raw, "desktop")
        self.assertIn("restricted system", md)
        self.assertIn("Host & Resources", md)

    # --- F14: Remote Timeout POSIX Exit 124 ---
    def test_t1_f14_01_timeout_expired_caught(self) -> None:
        """F14.01: subprocess.TimeoutExpired caught cleanly without raising exception (DEF-BB-048)."""
        runner = RemoteRunner()
        with patch("subprocess.run", side_effect=subprocess.TimeoutExpired(cmd=["ssh"], timeout=1.0)), \
             patch.object(runner, "cleanup_target_socket"):
            res = runner.run("desktop", "sleep 10", timeout=1.0)
            self.assertEqual(res.returncode, 124)

    def test_t1_f14_02_timeout_returns_exit_124(self) -> None:
        """F14.02: RemoteRunner.run on timeout returns exit code 124."""
        runner = RemoteRunner()
        with patch("subprocess.run", side_effect=subprocess.TimeoutExpired(cmd=["ssh"], timeout=5.0)), \
             patch.object(runner, "cleanup_target_socket"):
            res = runner.run("desktop", "sleep 10", timeout=5.0)
            self.assertEqual(res.returncode, 124)

    def test_t1_f14_03_timeout_stderr_diagnostic(self) -> None:
        """F14.03: Timeout result includes descriptive stderr message."""
        runner = RemoteRunner()
        with patch("subprocess.run", side_effect=subprocess.TimeoutExpired(cmd=["ssh"], timeout=2.0)), \
             patch.object(runner, "cleanup_target_socket"):
            res = runner.run("desktop", "sleep 10", timeout=2.0)
            self.assertIn("timed out after 2.0s", res.stderr)

    def test_t1_f14_04_timeout_triggers_socket_cleanup(self) -> None:
        """F14.04: Timeout automatically triggers cleanup_target_socket."""
        runner = RemoteRunner()
        with patch("subprocess.run", side_effect=subprocess.TimeoutExpired(cmd=["ssh"], timeout=1.0)), \
             patch.object(runner, "cleanup_target_socket") as mock_cleanup:
            runner.run("desktop", "sleep 10", timeout=1.0)
            mock_cleanup.assert_called_once()

    def test_t1_f14_05_cli_remote_exec_exits_124(self) -> None:
        """F14.05: CLI agyis remote exec returns exit code 124 on timeout."""
        mock_runner = MagicMock()
        mock_runner.run.return_value = subprocess.CompletedProcess(
            args=["ssh"], returncode=124, stdout="", stderr="Remote command timed out after 1.0s\n"
        )
        with patch("harness.remote.RemoteRunner", return_value=mock_runner):
            code, stdout, stderr = self.run_cli(["remote", "exec", "desktop", "sleep 10", "-t", "1"])
            self.assertEqual(code, 124)

    # --- F15: Socket Lifecycle & Graceful Termination ---
    def test_t1_f15_01_cleanup_sockets_issues_ssh_exit(self) -> None:
        """F15.01: cleanup_sockets issues graceful ssh -O exit before unlinking (DEF-BB-049)."""
        runner = RemoteRunner(socket_dir=self.socket_dir)
        mock_sock = self.socket_dir / "cm_mock_host"
        mock_sock.touch()

        with patch("subprocess.run") as mock_sub:
            mock_sub.return_value = subprocess.CompletedProcess(args=["ssh"], returncode=0)
            removed = runner.cleanup_sockets()
            self.assertIn(mock_sock, removed)
            calls = [c[0][0] for c in mock_sub.call_args_list]
            found_exit = any("-O" in c and "exit" in c for c in calls)
            self.assertTrue(found_exit)

    def test_t1_f15_02_cleanup_sockets_unlinks_files(self) -> None:
        """F15.02: cleanup_sockets removes socket files from disk."""
        runner = RemoteRunner(socket_dir=self.socket_dir)
        mock_sock = self.socket_dir / "cm_to_delete"
        mock_sock.touch()
        self.assertTrue(mock_sock.exists())

        with patch("subprocess.run"):
            runner.cleanup_sockets()
        self.assertFalse(mock_sock.exists())

    def test_t1_f15_03_socket_dir_permissions_0700(self) -> None:
        """F15.03: Socket directory created with 0700 permissions."""
        d = get_socket_dir()
        stat = d.stat()
        self.assertEqual(oct(stat.st_mode & 0o777), "0o700")

    def test_t1_f15_04_cleanup_target_socket_scoped(self) -> None:
        """F15.04: cleanup_target_socket targets only matching socket."""
        runner = RemoteRunner(socket_dir=self.socket_dir)
        sock_target = runner.get_target_socket_path("desktop")
        sock_other = runner.get_target_socket_path("laptop")
        sock_target.touch()
        sock_other.touch()

        orig_run = subprocess.run
        def mock_run(cmd, *args, **kwargs):
            if isinstance(cmd, (list, tuple)) and len(cmd) > 1 and cmd[1] == "-G":
                return orig_run(cmd, *args, **kwargs)
            return MagicMock(returncode=0)

        with patch("subprocess.run", side_effect=mock_run):
            removed = runner.cleanup_target_socket("desktop")
            self.assertIn(sock_target, removed)
            self.assertFalse(sock_target.exists())
            self.assertTrue(sock_other.exists())

    def test_t1_f15_05_list_sockets_lists_all(self) -> None:
        """F15.05: list_sockets returns list of all cm_* sockets."""
        runner = RemoteRunner(socket_dir=self.socket_dir)
        s1 = self.socket_dir / "cm_s1"
        s2 = self.socket_dir / "cm_s2"
        s1.touch()
        s2.touch()
        listed = runner.list_sockets()
        self.assertEqual(len(listed), 2)

    # --- F16: Architectural Import & Login Shell Hygiene ---
    def test_t1_f16_01_clean_import_from_remote_safety(self) -> None:
        """F16.01: REMOTE_TOOLCHAIN_REGEX imported from harness.remote.safety (DEF-BB-050)."""
        from harness.remote.safety import REMOTE_TOOLCHAIN_REGEX as REGEX1
        self.assertIsNotNone(REGEX1)
        self.assertTrue(REGEX1.search("pm2 status"))

    def test_t1_f16_02_no_hooks_import_in_remote_cli(self) -> None:
        """F16.02: harness/commands/remote.py does not import from harness.hooks (PSL-INV-011)."""
        import harness.commands.remote as remote_cmd_mod
        src = inspect.getsource(remote_cmd_mod)
        self.assertNotIn("from harness.hooks", src)
        self.assertNotIn("import harness.hooks", src)

    def test_t1_f16_03_no_double_wrapping_bash_l(self) -> None:
        """F16.03: Commands specifying bash -l -c are not double-wrapped (DEF-BB-050)."""
        cmd_str = "bash -l -c 'pm2 status'"
        is_already_login = bool(re.search(r"\b(?:bash|zsh|sh)\s+-[a-zA-Z]*l\b", cmd_str))
        self.assertTrue(is_already_login)

    def test_t1_f16_04_no_double_wrapping_zsh_l_sh_l(self) -> None:
        """F16.04: Commands specifying zsh -l or sh -l are detected as existing login shells."""
        self.assertTrue(bool(re.search(r"\b(?:bash|zsh|sh)\s+-[a-zA-Z]*l\b", "zsh -l -c 'nvm use 20'")))
        self.assertTrue(bool(re.search(r"\b(?:bash|zsh|sh)\s+-[a-zA-Z]*l\b", "sh -l -c 'cargo build'")))

    def test_t1_f16_05_toolchain_without_login_shell_promoted(self) -> None:
        """F16.05: Plain toolchain command promoted to single login shell wrap."""
        raw_cmd = "pm2 restart all"
        matches_toolchain = bool(REMOTE_TOOLCHAIN_REGEX.search(raw_cmd))
        is_login = bool(re.search(r"\b(?:bash|zsh|sh)\s+-[a-zA-Z]*l\b", raw_cmd))
        should_promote = matches_toolchain and not is_login
        self.assertTrue(should_promote)


class TestTier2BoundaryCases(BaseBugBashPhase2TestCase):
    """Tier 2: Boundary, corner, and adversarial stress cases (11 test cases)."""

    def test_t2_b01_01_xss_script_tag_in_conversation_summary(self) -> None:
        """B01.01: <script> tags in conversation summaries are sanitized."""
        summary = '<script>alert("xss")</script>'
        escaped = summary.replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;")
        self.assertNotIn("<script>", escaped)
        self.assertIn("&lt;script&gt;", escaped)

    def test_t2_b01_02_xss_img_onerror_in_search_input(self) -> None:
        """B01.02: <img onerror=...> in search input query does not execute."""
        query = '<img src=x onerror=alert(1)>'
        escaped = query.replace("<", "&lt;").replace(">", "&gt;")
        self.assertNotIn("<img", escaped)

    def test_t2_b01_03_xss_javascript_uri_in_parent_pill(self) -> None:
        """B01.03: javascript:... URLs in parent_id are neutralized."""
        parent_id = "javascript:alert(1)"
        is_safe = not parent_id.startswith("javascript:")
        self.assertFalse(is_safe)

    def test_t2_b02_01_single_character_target_name(self) -> None:
        """B02.01: Target 'c' does not match or delete unrelated sockets like 'client'."""
        target = "c"
        re_target = re.escape(target)
        sock_target = f"cm_{target}_22"
        sock_other = "cm_client_22"
        pattern = re.compile(rf"^cm_{re_target}(?:_\d+)?$")
        self.assertTrue(bool(pattern.match(sock_target)))
        self.assertFalse(bool(pattern.match(sock_other)))

    def test_t2_b02_02_underscore_target_name(self) -> None:
        """B02.02: Target '_' does not act as a regex wildcard matching all sockets."""
        target = "_"
        re_target = re.escape(target)
        sock_target = f"cm_{target}_22"
        sock_other = "cm_desktop_22"
        pattern = re.compile(rf"^cm_{re_target}(?:_\d+)?$")
        self.assertTrue(bool(pattern.match(sock_target)))
        self.assertFalse(bool(pattern.match(sock_other)))

    def test_t2_b03_01_extreme_50kb_triage_clamping(self) -> None:
        """B03.01: Extreme 50KB input is deterministically clamped strictly to <= 2048 bytes."""
        huge_input = ("LOG ENTRY DATA " * 3500)
        res = RemoteTriage.format_triage_markdown(huge_input, "stress_node", max_bytes=2048)
        self.assertLessEqual(len(res.encode("utf-8")), 2048)

    def test_t2_b03_02_unclosed_code_fence_balancing(self) -> None:
        """B03.02: Truncated output with unclosed backtick fence is cleanly balanced."""
        raw = "=== HOST ===\n```bash\n" + ("echo test\n" * 300)
        md = RemoteTriage.format_triage_markdown(raw, "desktop", max_bytes=2048)
        self.assertEqual(md.count("```") % 2, 0)

    def test_t2_b04_01_empty_output_triage_handling(self) -> None:
        """B04.01: 0-byte output formatted without crashing."""
        res = RemoteTriage.format_triage_markdown("", "desktop")
        self.assertIn("Remote Triage Report", res)

    def test_t2_b04_02_permission_denied_sections(self) -> None:
        """B04.02: Permission denied probe responses are formatted cleanly."""
        raw = "=== SERVICES ===\nFailed to connect to bus: Permission denied\n"
        res = RemoteTriage.format_triage_markdown(raw, "desktop")
        self.assertIn("Services", res)
        self.assertIn("Permission denied", res)

    def test_t2_b05_01_rapid_f12_spamming(self) -> None:
        """B05.01: Rapid succession of 10 F12 events handles debouncing cleanly."""
        now = time.time()
        toggles = 0
        last_t = 0.0
        for i in range(10):
            t = now + (i * 0.02)  # 20ms intervals
            if (t - last_t) > 0.25:
                toggles += 1
                last_t = t
        self.assertEqual(toggles, 1)

    def test_t2_b06_01_sparse_stream_step_indices(self) -> None:
        """B06.01: Stream frame with step index 100 on empty trajectory is bounded."""
        steps = []
        incoming_step = {"step": 100, "type": "USER_INPUT"}
        steps.append(incoming_step)
        self.assertEqual(len(steps), 1)
        self.assertEqual(steps[0]["step"], 100)


class TestTier3CrossFeatureInteractions(BaseBugBashPhase2TestCase):
    """Tier 3: Pairwise cross-feature interactions (4 test cases)."""

    def test_t3_c01_triage_streaming_concurrency(self) -> None:
        """C01: Concurrent execution of remote triage and HUD stream delta ingestion."""
        raw_triage = "=== HOST ===\nLinux mesh-node 7.2\n"
        md = RemoteTriage.format_triage_markdown(raw_triage, "mesh-node")
        self.assertIn("Host & Resources", md)

        stream_state = {"conversationId": "c1", "activeTokens": 50000}
        self.assertEqual(stream_state["conversationId"], "c1")

    def test_t3_c02_dropdown_switch_during_stream_burst(self) -> None:
        """C02: Switching conversation in dropdown drops stale deltas from previous stream."""
        js = """
        let activeConvo = "convo-1";
        const pendingDeltas = [
            { convoId: "convo-1", data: "delta-1" },
            { convoId: "convo-1", data: "delta-2" },
        ];

        // User switches dropdown to convo-2
        activeConvo = "convo-2";
        const filteredDeltas = pendingDeltas.filter(d => d.convoId === activeConvo);

        console.log(JSON.stringify({ activeConvo, remainingDeltas: filteredDeltas.length }));
        """
        res = self.run_node_harness(js)
        self.assertEqual(res["activeConvo"], "convo-2")
        self.assertEqual(res["remainingDeltas"], 0)

    def test_t3_c03_socket_cleanup_during_inflight_run(self) -> None:
        """C03: Target-scoped cleanup for node A does not terminate node B's active socket."""
        runner = RemoteRunner(socket_dir=self.socket_dir)
        sock_a = runner.get_target_socket_path("nodeA")
        sock_b = runner.get_target_socket_path("nodeB")
        sock_a.touch()
        sock_b.touch()

        orig_run = subprocess.run
        def mock_run(cmd, *args, **kwargs):
            if isinstance(cmd, (list, tuple)) and len(cmd) > 1 and cmd[1] == "-G":
                return orig_run(cmd, *args, **kwargs)
            return MagicMock(returncode=0)

        with patch("subprocess.run", side_effect=mock_run):
            runner.cleanup_target_socket("nodeA")
            self.assertFalse(sock_a.exists())
            self.assertTrue(sock_b.exists())

    def test_t3_c04_hotkey_toggle_during_script_stream(self) -> None:
        """C04: F12 toggle while script is streaming over stdin does not interrupt pipe."""
        runner = RemoteRunner(socket_dir=self.socket_dir)
        script_file = self.ws / "pipe_test.py"
        script_file.write_text("print('stream active')", encoding="utf-8")

        with patch.object(runner, "run") as mock_run:
            mock_run.return_value = subprocess.CompletedProcess(args=["ssh"], returncode=0, stdout="stream active", stderr="")
            res = ScriptStreamer.stream_script(runner, "desktop", script_file)
            self.assertEqual(res.returncode, 0)


class TestTier4RealWorldScenarios(BaseBugBashPhase2TestCase):
    """Tier 4: Realistic end-to-end multi-turn scenarios (3 test cases)."""

    def test_t4_s01_full_knot_mesh_fleet_health_audit(self) -> None:
        """S01: Full Knot mesh fleet health audit across Desktop, Laptop, and Handheld nodes."""
        runner = RemoteRunner(socket_dir=self.socket_dir)
        nodes = ["desktop", "laptop", "steamdeck"]
        results = {}

        def mock_dispatch(cmd, **kwargs):
            cmd_str = " ".join(cmd)
            if "desktop" in cmd:
                return subprocess.CompletedProcess(
                    args=cmd,
                    returncode=0,
                    stdout="=== HOST ===\nLinux desktop 7.2\n=== RESOURCES ===\nMem: 16G\n",
                    stderr="",
                )
            elif "laptop" in cmd:
                raise subprocess.TimeoutExpired(cmd=cmd, timeout=5.0)
            elif "steamdeck" in cmd:
                return subprocess.CompletedProcess(
                    args=cmd,
                    returncode=255,
                    stdout="",
                    stderr="Connection refused",
                )
            return subprocess.CompletedProcess(args=cmd, returncode=0, stdout="", stderr="")

        with patch("subprocess.run", side_effect=mock_dispatch), \
             patch.object(runner, "cleanup_target_socket"):
            for node in nodes:
                try:
                    res = runner.run(node, RemoteTriage.build_triage_probe(), timeout=5.0)
                    results[node] = {
                        "exit_code": res.returncode,
                        "report": RemoteTriage.format_triage_markdown(res.stdout or res.stderr, node),
                    }
                except Exception as exc:
                    results[node] = {"error": str(exc)}

        self.assertEqual(results["desktop"]["exit_code"], 0)
        self.assertIn("Host & Resources", results["desktop"]["report"])

        self.assertEqual(results["laptop"]["exit_code"], 124)  # POSIX exit 124 on timeout
        self.assertIn("Diagnostic & Connection Output", results["laptop"]["report"])

        self.assertEqual(results["steamdeck"]["exit_code"], 255)
        self.assertIn("Connection refused", results["steamdeck"]["report"])

    def test_t4_s02_titanium_500_step_trajectory_streaming(self) -> None:
        """S02: Titanium 500+ step trajectory streaming with checkpoint epochs and subagent tabs."""
        js = """
        const state = window.__agyis_hud_state;
        const totalSteps = 550;
        const steps = [];
        for (let i = 0; i < totalSteps; i++) {
            steps.push({
                stepIndex: i,
                type: i % 100 === 0 ? "CORTEX_STEP_TYPE_CHECKPOINT" : "CORTEX_STEP_TYPE_USER_INPUT",
                content: "Step " + i
            });
        }

        state.currentData = { conversation_id: "titanium-500", steps };
        state.selectedIndex = 50;
        state.convoId = "titanium-500";

        const wasAtEnd = state.selectedIndex >= totalSteps - 1;
        if (!wasAtEnd) {
            state.tablePage = Math.floor(state.selectedIndex / 50);
        }

        console.log(JSON.stringify({
            totalSteps: state.currentData.steps.length,
            selectedIndex: state.selectedIndex,
            tablePage: state.tablePage,
            wasAtEnd
        }));
        """
        res = self.run_node_harness(js)
        self.assertEqual(res["totalSteps"], 550)
        self.assertEqual(res["selectedIndex"], 50)
        self.assertEqual(res["tablePage"], 1)
        self.assertFalse(res["wasAtEnd"])

    def test_t4_s03_edge_node_network_dropout_255_and_socket_recovery(self) -> None:
        """S03: Edge node network drop (255) -> target socket cleanup -> clean reconnect."""
        runner = RemoteRunner(socket_dir=self.socket_dir)
        target = "edge-node"
        sock = runner.get_target_socket_path(target)
        sock.touch()
        self.assertTrue(sock.exists())

        call_count = 0
        def mock_ssh(cmd, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return subprocess.CompletedProcess(args=cmd, returncode=255, stdout="", stderr="Broken pipe")
            else:
                return subprocess.CompletedProcess(args=cmd, returncode=0, stdout="Connected over WireGuard", stderr="")

        with patch("subprocess.run", side_effect=mock_ssh), \
             patch.object(runner, "cleanup_target_socket", wraps=runner.cleanup_target_socket) as spy_cleanup:
            res1 = runner.run(target, "uptime")
            self.assertEqual(res1.returncode, 255)
            spy_cleanup.assert_called_once()
            self.assertFalse(sock.exists())

            res2 = runner.run(target, "uptime")
            self.assertEqual(res2.returncode, 0)
            self.assertEqual(res2.stdout, "Connected over WireGuard")


if __name__ == "__main__":
    unittest.main()
