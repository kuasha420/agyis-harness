#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Arafat Zahan (@kuasha420)
# Corporate Stewardship & Infrastructure: Purrfect Software Limited (PSL)
# Governed by: ICARO-42/b Ordinance (Company-Supported Personal IP Framework)

"""
Hermetic verification suite for Wave 1.3 Track 3:
- Antigravity 2.35.2 HUD ConnectRPC pagination (`stepOffset` & `generatorMetadataOffset`)
- Model context window & tool catalog parity
- Split-pane `"pane-1"` / `"pane-2"` & `bgtask__` / `side_question__` routing
- Orbital Aegis HUD theme refresh & `logo.svg` shield mark
- Standalone HTTP :40624 playback shell & allowlisted `/assets/` endpoint
- Compaction `CHECKPOINT` overflow exclusion/clamping + IDE surface launcher/CDP/systemd
"""

from __future__ import annotations

import importlib.resources
import json
import os
from pathlib import Path
import re
import shutil
import socket
import subprocess
import tempfile
import unittest
from unittest.mock import patch
import urllib.error
import urllib.request

from harness.gui.cdp import get_default_devtools_port_file
from harness.gui.launcher import (
    detect_antigravity_without_cdp,
    format_cdp_restart_instructions,
    install_cdp_launcher,
)
from harness.gui.server import start_trajectory_server
from harness.gui.systemd import generate_gui_systemd_path_unit
from harness.gui import trajectory_catalog
from harness.gui.trajectory_hud import (
    atc_context_layout,
    build_trajectory_hud_script,
    load_conversation_trajectory,
    xtc_segment_width,
    ytc_layout_pass,
    ztc_row_count,
)
from harness.telemetry.extractor import extract_session


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


class TestGuiV235ParityAndOrbitalAegis(unittest.TestCase):
    """Sub-second hermetic verification of 2.35.2 parity and Orbital Aegis HUD refresh."""

    def _run_node(self, script: str) -> dict:
        node_bin = shutil.which("node")
        if not node_bin:
            self.skipTest("node binary unavailable")
        proc = subprocess.run([node_bin, "-"], input=script, capture_output=True, text=True, timeout=5, check=False)
        self.assertEqual(proc.returncode, 0, f"Node failed:\nSTDOUT:{proc.stdout}\nSTDERR:{proc.stderr}")
        return json.loads(proc.stdout.strip().splitlines()[-1])

    def test_step_offset_and_generator_metadata_pagination_in_node(self) -> None:
        assets = importlib.resources.files("harness.gui.assets")
        stream_js = assets.joinpath("hud_stream.js").read_text(encoding="utf-8")
        rpc_js = assets.joinpath("hud_rpc.js").read_text(encoding="utf-8")
        out = self._run_node(
            "global.window = { location: { origin: 'https://127.0.0.1:40623' } };\n"
            + stream_js + "\n" + rpc_js
            + r"""
const stepCalls = [];
const genCalls = [];
const allSteps = Array.from({ length: 600 }, (_, i) => ({
    stepIndex: i,
    type: i === 0 ? "CORTEX_STEP_TYPE_USER_INPUT" : "CORTEX_STEP_TYPE_PLANNER_RESPONSE",
    content: "step-" + i,
}));
const allGen = Array.from({ length: 600 }, (_, i) => ({
    stepIndex: i,
    model: "gemini-4-carbon",
    chatStartMetadata: { contextWindowMetadata: { maxContextTokens: 512000, estimatedTokensUsed: 1000 + i } },
}));
global.fetch = async (url, init) => {
    const body = init && init.body ? JSON.parse(init.body) : {};
    if (url.endsWith("/GetCascadeTrajectorySteps")) {
        stepCalls.push(body);
        const off = body.stepOffset || 0;
        return { ok: true, status: 200, async json() { return { steps: allSteps.slice(off, off + 500), totalLength: 600 }; } };
    }
    if (url.endsWith("/GetCascadeTrajectoryGeneratorMetadata")) {
        genCalls.push(body);
        const off = body.generatorMetadataOffset || 0;
        return { ok: true, status: 200, async json() { return { generatorMetadata: allGen.slice(off, off + 500), totalLength: 600 }; } };
    }
    if (url.endsWith("/GetCascadeTrajectoryExecutorMetadatas")) {
        return { ok: false, status: 404, async json() { return {}; } };
    }
    return { ok: true, status: 200, async json() { return {}; } };
};
(async () => {
    const traj = await window.loadConversationViaRpc("convo-600");
    const streamSeen = [];
    const client = new window.InSituConnectClient();
    const coord = new window.StreamRenderCoordinator((s) => streamSeen.push(s));
    await client._fetchRemainingStreamSlice("convo-600", coord, 500, 600, null);
    console.log(JSON.stringify({
        stepCount: traj.steps.length,
        maxCtx: traj.max_context_tokens,
        stepOffsets: stepCalls.map(c => c.stepOffset),
        genOffsets: genCalls.map(c => c.generatorMetadataOffset),
        usedLegacyStartIdx: stepCalls.some(c => "startIndex" in c || "endIndexExclusive" in c),
        lastGenToken: traj.total_tokens,
    }));
})();
"""
        )
        self.assertEqual(out["stepCount"], 600)
        self.assertEqual(out["maxCtx"], 512000)
        self.assertEqual(out["stepOffsets"], [0, 500, 500])
        self.assertEqual(out["genOffsets"], [0, 500])
        self.assertFalse(out["usedLegacyStartIdx"])

    def test_v2352_models_and_tools_parity(self) -> None:
        self.assertIs(atc_context_layout, trajectory_catalog.atc_context_layout)
        self.assertIs(xtc_segment_width, trajectory_catalog.xtc_segment_width)
        self.assertIs(ytc_layout_pass, trajectory_catalog.ytc_layout_pass)
        self.assertIs(ztc_row_count, trajectory_catalog.ztc_row_count)

        assets = importlib.resources.files("harness.gui.assets")
        stream_js = assets.joinpath("hud_stream.js").read_text(encoding="utf-8")
        rpc_js = assets.joinpath("hud_rpc.js").read_text(encoding="utf-8")
        out = self._run_node(
            "global.window = {};\n"
            + stream_js + "\n" + rpc_js
            + r"""
const infer = window.__agyis_utils.inferModelContextWindow;
const v235Tools = [
    "update_focus", "update_steps", "enter_plan_mode", "exit_plan_mode",
    "ask_question", "search_marketplace", "list_plugin_accounts",
    "call_mcp_tool", "list_resources", "read_resource",
];
const traj = window.buildHudTrajectoryData(
    "v2352-tools",
    v235Tools.map((name, i) => ({ stepIndex: i, type: "TOOL_CALL", tool_calls: [{ name }] })),
    [], [], null
);
console.log(JSON.stringify({
    windows: {
        carbon: infer("gemini-4-carbon"),
        orch: infer("gemini-pro-orchestrator-neon"),
        orchDisplay: infer("Orchestrator (Carbon)"),
        coord: infer("gemini-pro-coordinator"),
        opus55: infer("claude-opus-5-5"),
        sonnet55: infer("claude-sonnet-5.5"),
        sonnet46: infer("claude-sonnet-4-6"),
        gptOss: infer("gpt-oss-120b"),
        oneM: infer("gemini-1m"),
    },
    mappedTypes: traj.steps.map(s => s.type),
}));
"""
        )
        self.assertEqual(out["windows"], {
            "carbon": 512000, "orch": 512000, "orchDisplay": 512000, "coord": 512000,
            "opus55": 840000, "sonnet55": 840000, "sonnet46": 160000, "gptOss": 80000, "oneM": 1000000,
        })
        self.assertEqual(out["mappedTypes"], [
            "UPDATE_FOCUS", "UPDATE_STEPS", "ENTER_PLAN_MODE", "EXIT_PLAN_MODE",
            "ASK_QUESTION", "SEARCH_MARKETPLACE", "LIST_PLUGIN_ACCOUNTS",
            "CALL_MCP_TOOL", "LIST_RESOURCES", "READ_RESOURCE",
        ])

        with tempfile.TemporaryDirectory() as tmp:
            brain = Path(tmp)
            log_dir = brain / "py-v2352" / ".system_generated" / "logs"
            log_dir.mkdir(parents=True)
            steps = [{"step_index": i, "tool_calls": [{"name": name}]} for i, name in enumerate([
                "update_focus", "update_steps", "enter_plan_mode", "exit_plan_mode",
                "ask_question", "search_marketplace", "list_plugin_accounts",
                "call_mcp_tool", "list_resources", "read_resource",
            ])]
            (log_dir / "transcript.jsonl").write_text("\n".join(json.dumps(s) for s in steps) + "\n", encoding="utf-8")
            py_traj = load_conversation_trajectory("py-v2352", brain_dir=brain)
            self.assertEqual([s["type"] for s in py_traj["steps"]], out["mappedTypes"])

    def test_split_pane_and_tab_token_resolution_in_node(self) -> None:
        assets = importlib.resources.files("harness.gui.assets")
        hotkey_js = assets.joinpath("hotkey.js").read_text(encoding="utf-8")
        hud_js = assets.joinpath("hud.js").read_text(encoding="utf-8")
        out = self._run_node(
            """
let activePane = null;
global.document = {
    getElementById() { return null; },
    createElement() { return { id: "", style: {}, appendChild() {}, remove() {} }; },
    head: { appendChild() {} },
    body: { appendChild() {} },
    querySelector(sel) { return sel.includes("data-pane-id") ? activePane : null; },
    querySelectorAll() { return []; },
    addEventListener() {}, removeEventListener() {},
};
global.window = {
    location: { origin: "https://127.0.0.1:40623", pathname: "/c/alpha+beta", search: "" },
    addEventListener() {}, removeEventListener() {},
};
"""
            + hotkey_js
            + "\n"
            + hud_js
            + r"""
activePane = { getAttribute(k) { return k === "data-pane-id" ? "pane-2" : null; } };
const pane2 = window.detectActiveConversationContext();
const hudPane2 = window.__agyis_extract_convo_id();
window.location.search = "?tab=bgtask__task-xyz";
const bgTask = window.detectActiveConversationContext();
window.location.search = "?tab=side_question__sq-42";
const sideQ = window.detectActiveConversationContext();
activePane = { getAttribute(k) { return k === "data-pane-id" ? "pane-1" : (k === "data-conversation-id" ? "convo-attr-9" : null); } };
const paneAttr = window.detectActiveConversationContext();
window.location.search = "?tab=subagent_convo__sub-101";
const subWin = window.detectActiveConversationContext();
console.log(JSON.stringify({ pane2, hudPane2, bgTask, sideQ, paneAttr, subWin }));
"""
        )
        self.assertEqual(out, {
            "pane2": "beta",
            "hudPane2": "beta",
            "bgTask": "beta",
            "sideQ": "beta",
            "paneAttr": "convo-attr-9",
            "subWin": "sub-101",
        })

    def test_orbital_aegis_assets_and_deterministic_inspector_ids(self) -> None:
        assets = importlib.resources.files("harness.gui.assets")
        banned = re.compile(
            r"#(?:18181b|121214|141416|202023|27272a|3f3f46|71717a|a1a1aa|f4f4f5|fbbf24|eab308|f59e0b|ef4444|38bdf8|22c55e)\b"
            r"|Roboto|transition:\s*all|Math\.random",
            re.IGNORECASE,
        )
        for name in (
            "hud_styles.css", "hud_theme.js", "hud_utils.js", "hud_header.js", "hud_context_bar.js",
            "hud_timeline.js", "hud_inspector.js", "hud_deck.js", "hud_stream.js", "telemetry_hud.js",
            "playback_shell.html", "playback_boot.js",
        ):
            txt = assets.joinpath(name).read_text(encoding="utf-8")
            self.assertIsNone(banned.search(txt), f"Legacy token/style found in {name}: {banned.search(txt)}")

        css = assets.joinpath("hud_styles.css").read_text(encoding="utf-8")
        self.assertIn("var(--pane-titlebar-height, 40px)", css)
        self.assertIn("Instrument Sans", css)
        self.assertIn("JetBrains Mono", css)

        telem = assets.joinpath("telemetry_hud.js").read_text(encoding="utf-8")
        self.assertIn('hud.style.top = "44px"', telem)
        self.assertIn("agyis-telemetry-edge", telem)

        script = build_trajectory_hud_script("oa-1", {"conversation_id": "oa-1", "steps": []}, [])
        self.assertIn("renderShieldMarkSvg", script)
        self.assertIn("SHIELD_MARK_SVG", script)

        theme_js = assets.joinpath("hud_theme.js").read_text(encoding="utf-8")
        utils_js = assets.joinpath("hud_utils.js").read_text(encoding="utf-8")
        header_js = assets.joinpath("hud_header.js").read_text(encoding="utf-8")
        insp_js = assets.joinpath("hud_inspector.js").read_text(encoding="utf-8")
        out = self._run_node(
            "global.window = {};\n"
            + theme_js + "\n" + utils_js + "\n" + header_js + "\n" + insp_js + "\n"
            + r"""
const headerHtml = window.renderHudHeader({ layoutOrientation: "horizontal" }, { conversation_id: "oa-1", steps: [] }, []);
const html1 = window.renderMarkdownPreview("```py\nprint(1)\n```\n\n```js\nconsole.log(2)\n```");
console.log(JSON.stringify({
    has1: html1.includes('id="agyis-code-1"'),
    has2: html1.includes('id="agyis-code-2"'),
    hasShieldEdge: headerHtml.includes('id="agyis-hud-edge"'),
    hasShieldBody: headerHtml.includes('id="agyis-hud-body"'),
}));
"""
        )
        self.assertTrue(out["has1"])
        self.assertTrue(out["has2"])
        self.assertTrue(out["hasShieldEdge"])
        self.assertTrue(out["hasShieldBody"])

    def test_playback_server_shell_and_assets_allowlist(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            brain = Path(tmp)
            log_dir = brain / "playback-1" / ".system_generated" / "logs"
            log_dir.mkdir(parents=True)
            (log_dir / "transcript.jsonl").write_text(json.dumps({"source": "user", "content": "Hello"}) + "\n", encoding="utf-8")
            port = _free_port()
            srv = start_trajectory_server(host="127.0.0.1", port=port, brain_dir=brain, poll_interval=0.05)
            try:
                base = f"http://127.0.0.1:{port}"
                with urllib.request.urlopen(f"{base}/", timeout=1.0) as resp:
                    self.assertEqual(resp.status, 200)
                    self.assertIn("text/html", resp.headers.get("Content-Type", ""))
                    html = resp.read().decode("utf-8")
                    self.assertIn("Agyis Trajectory Playback", html)
                    self.assertIn("/assets/playback_boot.js", html)

                with urllib.request.urlopen(f"{base}/assets/hud_styles.css", timeout=1.0) as resp:
                    self.assertEqual(resp.status, 200)
                    self.assertIn("text/css", resp.headers.get("Content-Type", ""))
                    self.assertIn("var(--pane-titlebar-height, 40px)", resp.read().decode("utf-8"))

                with urllib.request.urlopen(f"{base}/assets/playback_boot.js", timeout=1.0) as resp:
                    self.assertEqual(resp.status, 200)
                    self.assertIn("javascript", resp.headers.get("Content-Type", ""))
                for new_asset in ("hud_utils.js", "hud_stream.js"):
                    with urllib.request.urlopen(f"{base}/assets/{new_asset}", timeout=1.0) as resp:
                        self.assertEqual(resp.status, 200)
                        self.assertIn("javascript", resp.headers.get("Content-Type", ""))

                for bad_path in ("/assets/../../pyproject.toml", "/assets/%2e%2e/pyproject.toml", "/assets/hud.js", "/assets/__init__.py"):
                    with self.assertRaises(urllib.error.HTTPError) as ctx:
                        urllib.request.urlopen(f"{base}{bad_path}", timeout=1.0)
                    self.assertEqual(ctx.exception.code, 404)
                    ctx.exception.close()
            finally:
                srv.shutdown()
                srv.server_close()

        assets = importlib.resources.files("harness.gui.assets")
        pb_assets = "\n".join(
            assets.joinpath(n).read_text(encoding="utf-8")
            for n in (
                "hud_theme.js", "hud_utils.js", "hud_header.js", "hud_context_bar.js",
                "hud_timeline.js", "hud_inspector.js", "hud_deck.js", "hud_stream.js", "hud_rpc.js", "playback_boot.js",
            )
        )
        out = self._run_node(
            """
const els = {};
const mk = (id) => ({
    id, style: {}, value: "", innerHTML: "", textContent: "", className: "",
    addEventListener() {}, querySelector() { return null; }, querySelectorAll() { return []; },
});
els["agyis-trajectory-hud"] = mk("agyis-trajectory-hud");
els["agyis-playback-convo"] = mk("agyis-playback-convo");
els["agyis-playback-status"] = mk("agyis-playback-status");
global.document = {
    readyState: "complete",
    getElementById: (id) => els[id] || null,
    addEventListener() {},
};
global.window = {
    innerWidth: 1280,
    location: { origin: "http://127.0.0.1:40624", pathname: "/", search: "" },
    addEventListener() {},
};
global.fetch = async (url) => {
    if (url.startsWith("/api/conversations")) {
        return { ok: true, status: 200, async json() { return { conversations: [{ id: "pb-1", summary: "Playback 1", mtime: 1 }] }; } };
    }
    if (url.startsWith("/api/trajectory")) {
        return { ok: true, status: 200, async json() {
            return {
                conversation_id: "pb-1", model: "gemini-4-carbon", total_tokens: 1200, max_context_tokens: 512000,
                steps: [{ step_index: 0, type: "USER_INPUT", content: "hi", tokens: 200 }],
                checkpoints: [{ checkpoint_index: 0, start_index: 0, end_index: 0, total_tokens: 1200, token_breakdown: { user: 200 } }],
                token_breakdown: { user: 200 },
            };
        } };
    }
    return { ok: false, status: 404 };
};
"""
            + pb_assets
            + r"""
(async () => {
    await new Promise(r => setTimeout(r, 25));
    const hudHtml = els["agyis-trajectory-hud"].innerHTML;
    console.log(JSON.stringify({
        mounted: hudHtml.includes("Trajectory Debug View") && hudHtml.includes("Context Window"),
        statusText: els["agyis-playback-status"].textContent,
        convoId: window.__agyis_hud_state && window.__agyis_hud_state.convoId,
    }));
})();
"""
        )
        self.assertTrue(out["mounted"])
        self.assertIn("1,200 tok", out["statusText"])
        self.assertEqual(out["convoId"], "pb-1")

    def test_checkpoint_overflow_clamping_hud_and_extractor(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            brain = Path(tmp)
            log_dir = brain / "cp-clamp-1" / ".system_generated" / "logs"
            log_dir.mkdir(parents=True)
            t_file = log_dir / "transcript.jsonl"
            steps = [
                {"step_index": 0, "type": "USER_INPUT", "model": "gemini-4-carbon", "content": "Using gemini-4-carbon", "input_tokens": 12000},
                {
                    "step_index": 1,
                    "type": "CHECKPOINT",
                    "checkpoint": {"sessionSummary": "Compacted pre-overflow state"},
                    "metadata": {
                        "retryInfos": [{"usage": {"cacheReadTokens": 551417, "inputTokens": 12000}}],
                        "modelUsage": {"inputTokens": 12000, "cacheReadTokens": 551417},
                    },
                },
                {"step_index": 2, "type": "USER_INPUT", "content": "Continue post-compaction", "output_tokens": 4500},
            ]
            t_file.write_text("\n".join(json.dumps(s) for s in steps) + "\n", encoding="utf-8")

            traj = load_conversation_trajectory("cp-clamp-1", brain_dir=brain)
            self.assertEqual(traj["max_context_tokens"], 512000)
            self.assertLess(traj["total_tokens"], 512000)
            self.assertLessEqual(traj["utilization_pct"], 100.0)

            extracted = extract_session(t_file)
            self.assertIsNotNone(extracted)
            s_row, _, _, _ = extracted
            self.assertEqual(s_row["max_context_tokens"], 512000)
            self.assertEqual(s_row["peak_context_tokens"], 12000)

    def test_launcher_cdp_and_systemd_v235_ide_surface(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            desktop_path = root / "share" / "applications" / "antigravity.desktop"
            res = install_cdp_launcher(desktop_path=desktop_path, system_desktop_path=root / "missing.desktop")
            self.assertTrue(res["success"])
            self.assertIsNotNone(res.get("icon_path"))
            icon_file = Path(res["icon_path"])
            self.assertTrue(icon_file.is_file())
            self.assertIn("<svg", icon_file.read_text(encoding="utf-8"))

            msg = "\n".join(format_cdp_restart_instructions([{"pid": 42}]))
            self.assertIn("Antigravity v2.34+", msg)

            proc_dir = root / "proc"
            (proc_dir / "201").mkdir(parents=True)
            (proc_dir / "201" / "cmdline").write_bytes(b"/opt/antigravity-ide/antigravity-ide\x00--no-sandbox\x00")
            self.assertEqual(detect_antigravity_without_cdp(proc_root=proc_dir, include_ide=False), [])
            self.assertEqual([p["pid"] for p in detect_antigravity_without_cdp(proc_root=proc_dir, include_ide=True)], [201])

            with patch.dict(os.environ, {"XDG_CONFIG_HOME": str(root / "xdg")}, clear=False):
                self.assertEqual(
                    get_default_devtools_port_file(surface="antigravity-ide"),
                    root / "xdg" / "Antigravity IDE" / "DevToolsActivePort",
                )
                unit = generate_gui_systemd_path_unit(surface="antigravity-ide")
                self.assertIn("Antigravity IDE/DevToolsActivePort", unit)

    def test_checkpoint_navigation_selection_rpc_timeline_and_playback_regression_in_node(self) -> None:
        """Consolidated sub-second Node VM verification of all 14 RCA regressions across Electron HUD & :40624 playback."""
        node_bin = shutil.which("node")
        if not node_bin:
            self.skipTest("node binary unavailable")

        with tempfile.TemporaryDirectory() as tmp:
            brain = Path(tmp)
            convo_id = "repro-checkpoints"
            log_dir = brain / convo_id / ".system_generated" / "logs"
            log_dir.mkdir(parents=True)
            raw_steps = []
            for i in range(120):
                if i == 40:
                    raw_steps.append({
                        "step_index": i,
                        "type": "CHECKPOINT",
                        "checkpoint": {"checkpointIndex": 0, "sessionSummary": "Checkpoint at step 40"},
                        "metadata": {"retryInfos": [{"usage": {"cacheReadTokens": 190000, "inputTokens": 9000}}]},
                    })
                elif i == 80:
                    raw_steps.append({
                        "step_index": i,
                        "type": "CHECKPOINT",
                        "checkpoint": {"checkpointIndex": 1, "sessionSummary": "Checkpoint at step 80"},
                        "metadata": {"retryInfos": [{"usage": {"cacheReadTokens": 210000, "inputTokens": 11000}}]},
                    })
                elif i == 20:
                    raw_steps.append({
                        "step_index": i,
                        "type": "PLANNER_RESPONSE",
                        "content": "read_file /tmp/notes.md",
                        "tokens": 120,
                        "timestamp": "2026-11-26T10:00:20Z",
                    })
                elif i == 35:
                    raw_steps.append({
                        "step_index": i,
                        "source": "model",
                        "content": "Running build",
                        "tool_calls": [{"name": "run_command", "args": {"CommandLine": "toolneedle"}}],
                        "tokens": 135,
                        "timestamp": "2026-11-26T10:00:35Z",
                    })
                elif i == 50:
                    raw_steps.append({
                        "step_index": i,
                        "type": "PLANNER_RESPONSE",
                        "thinking": "Deep reasoning on step 50",
                        "content": "Answer 50",
                        "tokens": 150,
                        "timestamp": "2026-11-26T10:00:50Z",
                    })
                else:
                    raw_steps.append({
                        "step_index": i,
                        "source": "user" if i % 4 == 0 else "model",
                        "content": f"Step content {i} " + ("alpha " if i in (10, 60, 110) else ""),
                        "tokens": 100 + i,
                        "timestamp": f"2026-11-26T10:{i // 60:02d}:{i % 60:02d}Z",
                    })
            (log_dir / "transcript.jsonl").write_text("\n".join(json.dumps(s) for s in raw_steps) + "\n", encoding="utf-8")
            traj = load_conversation_trajectory(convo_id, brain_dir=brain)

        self.assertEqual(traj["steps"][40]["checkpoint_index"], 0)
        self.assertEqual(traj["steps"][80]["checkpoint_index"], 1)

        hud_script = build_trajectory_hud_script(
            convo_id="repro-checkpoints",
            trajectory_data=traj,
            conversations=[{"id": "repro-checkpoints", "summary": "Repro", "mtime": 1700000000}],
            open_view=True,
            toggle=False,
        )
        assets = importlib.resources.files("harness.gui.assets")
        pb_script = "\n".join(
            assets.joinpath(name).read_text(encoding="utf-8")
            for name in (
                "hud_theme.js", "hud_utils.js", "hud_header.js", "hud_context_bar.js",
                "hud_timeline.js", "hud_inspector.js", "hud_deck.js", "hud_stream.js", "hud_rpc.js", "playback_boot.js",
            )
        )

        # Compact Node VM harness with full HTML-parsing DOM for both Electron HUD and :40624 playback
        node_driver = r"""
const fs = require("fs");
const vm = require("vm");
const bundle = JSON.parse(fs.readFileSync(0, "utf8"));

function createDomSandbox(initialPath) {
    const scrollCalls = [];
    const rafQueue = [];
    const winListeners = [];
    const realSetTimeout = setTimeout;
    const VOID_TAGS = new Set(["INPUT", "BR", "HR", "IMG", "META", "LINK", "PATH", "LINE", "RECT", "CIRCLE", "POLYGON", "STOP"]);
    let doc = null;
    class FakeEl {
        constructor(tag) {
            this.tagName = String(tag || "div").toUpperCase();
            this.id = ""; this.className = ""; this.parentNode = null;
            this.style = { display: "flex", transform: "" };
            this._innerHTML = ""; this._textContent = undefined; this.children = [];
            this.value = ""; this.selectionStart = 0; this.selectionEnd = 0;
            this.scrollTop = 0; this.scrollLeft = 0; this.clientWidth = 1000; this.clientHeight = 600;
            this.open = false; this.disabled = false; this._attrs = null; this._listeners = null; this._classes = null;
            this.classList = {
                add: (c) => { (this._classes || (this._classes = new Set())).add(c); },
                remove: (c) => { if (this._classes) this._classes.delete(c); },
                contains: (c) => Boolean(this._classes && this._classes.has(c)),
                toggle: (c) => { const s = this._classes || (this._classes = new Set()); if (s.has(c)) s.delete(c); else s.add(c); },
            };
        }
        get innerHTML() { return this._innerHTML; }
        set innerHTML(v) { this._innerHTML = String(v ?? ""); this._textContent = undefined; parseHtml(this._innerHTML, this); }
        get textContent() { return this._textContent !== undefined ? this._textContent : this._innerHTML.replace(/<[^>]+>/g, ""); }
        set textContent(v) { this._textContent = String(v ?? ""); this._innerHTML = this._textContent; }
        addEventListener(t, h, o) { const l = this._listeners || (this._listeners = {}); (l[t] = l[t] || []).push({ handler: h, opts: o }); }
        removeEventListener(t, h) { if (this._listeners && this._listeners[t]) this._listeners[t] = this._listeners[t].filter(l => l.handler !== h); }
        dispatchEvent(ev) {
            if (!ev.preventDefault) ev.preventDefault = () => {};
            if (!ev.stopPropagation) ev.stopPropagation = () => {};
            if (!ev.stopImmediatePropagation) ev.stopImmediatePropagation = () => {};
            if (this._listeners && this._listeners[ev.type]) for (const item of this._listeners[ev.type]) item.handler.call(this, ev);
        }
        appendChild(ch) {
            if (ch.parentNode && ch.parentNode !== this) ch.parentNode.children = ch.parentNode.children.filter(c => c !== ch);
            ch.parentNode = this; this.children.push(ch); return ch;
        }
        remove() { if (this.parentNode) { this.parentNode.children = this.parentNode.children.filter(c => c !== this); this.parentNode = null; } }
        contains(t) { return t === this || this.children.some(ch => ch === t || ch.contains(t)); }
        focus() { doc.activeElement = this; }
        blur() { if (doc.activeElement === this) doc.activeElement = doc.body; }
        setSelectionRange(s, e) { this.selectionStart = s; this.selectionEnd = e; }
        getAttribute(k) { return this._attrs && Object.prototype.hasOwnProperty.call(this._attrs, k) ? this._attrs[k] : null; }
        setAttribute(k, v) { (this._attrs || (this._attrs = {}))[k] = String(v); if (k === "id") this.id = String(v); if (k === "open") this.open = true; }
        removeAttribute(k) { if (this._attrs) delete this._attrs[k]; if (k === "open") this.open = false; if (k === "disabled") this.disabled = false; }
        scrollIntoView(opts) { scrollCalls.push({ id: this.id, className: this.className, dataIndex: this.getAttribute("data-index"), dataStepIndex: this.getAttribute("data-step-index"), opts }); }
        querySelector(sel) { return this._query(sel, 1)[0] || null; }
        querySelectorAll(sel) { return this._query(sel, 0); }
        _query(sel, limit) {
            const out = [];
            const specs = sel.split(/\s+/).filter(Boolean).map((part) => {
                let rem = part;
                const attrs = [], clss = [];
                let idM = null;
                rem = rem.replace(/\[([^\]=]+)(?:="([^"]*)")?\]/g, (_, k, v) => { attrs.push([k, v]); return ""; });
                rem = rem.replace(/\.([a-zA-Z0-9_-]+)/g, (_, c) => { clss.push(c); return ""; });
                rem = rem.replace(/#([a-zA-Z0-9_-]+)/g, (_, id) => { idM = id; return ""; });
                return { tag: rem ? rem.toUpperCase() : null, idM, clss, attrs };
            });
            const matchSpec = (node, sp) => {
                if (sp.idM && node.id !== sp.idM) return false;
                if (sp.tag && node.tagName !== sp.tag) return false;
                for (let i = 0; i < sp.clss.length; i++) if (!node._classes || !node._classes.has(sp.clss[i])) return false;
                for (let i = 0; i < sp.attrs.length; i++) {
                    const [k, v] = sp.attrs[i], act = node.getAttribute(k);
                    if (v === undefined ? act === null : act !== v) return false;
                }
                return true;
            };
            const lastIdx = specs.length - 1, ancs = [this];
            const walk = (node) => {
                if (limit && out.length >= limit) return;
                if (lastIdx === 0) { if (matchSpec(node, specs[0])) { out.push(node); if (limit && out.length >= limit) return; } }
                else if (matchSpec(node, specs[lastIdx])) {
                    let ai = ancs.length - 1, pi = lastIdx - 1;
                    while (pi >= 0 && ai >= 0) { if (matchSpec(ancs[ai], specs[pi])) pi--; ai--; }
                    if (pi < 0) { out.push(node); if (limit && out.length >= limit) return; }
                }
                if (node.children.length) {
                    ancs.push(node);
                    for (let i = 0; i < node.children.length; i++) { walk(node.children[i]); if (limit && out.length >= limit) break; }
                    ancs.pop();
                }
            };
            for (let i = 0; i < this.children.length; i++) { walk(this.children[i]); if (limit && out.length >= limit) break; }
            return out;
        }
    }
    const makeEl = (tag) => new FakeEl(tag);
    const parseAttrs = (attrStr, el) => {
        if (!attrStr) return;
        let am;
        if (attrStr.includes("id=")) { am = /\bid=["']([^"']*)["']/.exec(attrStr); if (am) { el.id = am[1]; (el._attrs || (el._attrs = {})).id = am[1]; } }
        if (attrStr.includes("class=")) { am = /\bclass=["']([^"']*)["']/.exec(attrStr); if (am) { el.className = am[1]; (el._attrs || (el._attrs = {})).class = am[1]; const cs = el._classes || (el._classes = new Set()); for (const c of am[1].split(/\s+/)) if (c) cs.add(c); } }
        if (attrStr.includes("data-")) {
            const dr = /\b(data-[a-zA-Z0-9_-]+)=["']([^"']*)["']/g;
            while ((am = dr.exec(attrStr)) !== null) (el._attrs || (el._attrs = {}))[am[1]] = am[2];
        }
        if (attrStr.includes("value=")) { am = /\bvalue=["']([^"']*)["']/.exec(attrStr); if (am) { el.value = am[1]; (el._attrs || (el._attrs = {})).value = am[1]; } }
        if (/\bopen(?=\s|$)/.test(attrStr)) { el.open = true; (el._attrs || (el._attrs = {})).open = ""; }
        if (/\bdisabled(?=\s|$)/.test(attrStr)) { el.disabled = true; (el._attrs || (el._attrs = {})).disabled = ""; }
    };
    const parseHtml = (html, parent) => {
        parent.children = [];
        const stack = [parent];
        const tagRe = /<\/?([a-zA-Z0-9-]+)([^>]*)>/g;
        let m;
        while ((m = tagRe.exec(html)) !== null) {
            const full = m[0], tag = m[1].toUpperCase(), attrStr = m[2] || "";
            if (full.startsWith("</")) {
                if (stack.length > 1) {
                    const closed = stack.pop();
                    closed._innerHTML = html.slice(closed._contentStart, m.index);
                    closed._textContent = undefined;
                }
                continue;
            }
            const selfClose = full.endsWith("/>") || VOID_TAGS.has(tag);
            const el = new FakeEl(tag);
            el._contentStart = m.index + full.length;
            parseAttrs(attrStr, el);
            const top = stack[stack.length - 1];
            el.parentNode = top; top.children.push(el);
            if (!selfClose) stack.push(el);
        }
    };
    doc = {
        head: makeEl("head"), body: makeEl("body"), activeElement: null, readyState: "complete",
        getElementById(id) { return this.head.querySelector("#" + id) || this.body.querySelector("#" + id); },
        createElement: makeEl,
        querySelector(sel) { return this.body.querySelector(sel) || this.head.querySelector(sel); },
        querySelectorAll(sel) { return this.body.querySelectorAll(sel); },
        addEventListener() {}, removeEventListener() {},
    };
    doc.activeElement = doc.body;
    const sandbox = {
        document: doc, innerWidth: 1280, innerHeight: 800,
        location: { origin: "https://127.0.0.1:40623", pathname: initialPath, search: "" },
        history: { pushState() {}, replaceState() {} },
        localStorage: { getItem() { return null; }, setItem() {}, removeItem() {} },
        CSS: { escape: (s) => String(s ?? "").replace(/([^\w-])/g, "\\$1") },
        Event: class Event { constructor(t) { this.type = t; } },
        URLSearchParams, AbortController, TextEncoder, TextDecoder, crypto: globalThis.crypto,
        console, setTimeout: (fn, ms) => realSetTimeout(fn, ms >= 100 ? 10 : ms), clearTimeout, setInterval, clearInterval, Promise,
        requestAnimationFrame: (cb) => { rafQueue.push(cb); return rafQueue.length; },
        cancelAnimationFrame: () => {},
        fetch: async () => ({ ok: false, status: 503, async json() { return null; } }),
        addEventListener(t, h, cap) { winListeners.push({ t, h, cap: Boolean(cap) }); },
        removeEventListener(t, h) { const i = winListeners.findIndex(x => x.t === t && x.h === h); if (i !== -1) winListeners.splice(i, 1); },
        dispatchEvent(ev) {
            if (!ev.preventDefault) ev.preventDefault = () => {};
            if (!ev.stopPropagation) ev.stopPropagation = () => {};
            if (!ev.stopImmediatePropagation) ev.stopImmediatePropagation = () => {};
            for (const l of winListeners.filter(x => x.t === ev.type && x.cap)) l.h.call(sandbox, ev);
            for (const l of winListeners.filter(x => x.t === ev.type && !x.cap)) l.h.call(sandbox, ev);
        },
        __scrollCalls: scrollCalls,
        __flushRaf: () => { while (rafQueue.length) rafQueue.shift()(0); },
    };
    sandbox.window = sandbox.global = sandbox.globalThis = sandbox.self = sandbox;
    vm.createContext(sandbox);
    return { sandbox, doc, makeEl, scrollCalls };
}

(async () => {
    // --- Context A: Electron HUD ---
    const { sandbox: sA, doc: docA, scrollCalls: callsA } = createDomSandbox("/c/repro-checkpoints");
    vm.runInContext(bundle.hudScript, sA);
    const hud = docA.getElementById("agyis-trajectory-hud");
    const st = sA.__agyis_hud_state;

    // 1 & 2: Click CHECKPOINT #80 in Window 2 (stays in 2), then move to Window 1 and click CHECKPOINT #40 (stays in 1)
    const cpBefore80 = st.activeCheckpointIndex;
    hud.querySelector('.agyis-context-segment[data-step-index="80"]').dispatchEvent({ type: "click" });
    const cpAfterClick80 = st.activeCheckpointIndex;
    hud.querySelector("#agyis-checkpoint-prev").dispatchEvent({ type: "click" });
    hud.querySelector('.agyis-context-segment[data-step-index="40"]').dispatchEvent({ type: "click" });
    const cpAfterClick40 = st.activeCheckpointIndex;

    // 3: Check disabled Jump-to-Previous when activeCheckpointIndex === 0, then Next Checkpoint -> 1
    st.activeCheckpointIndex = 0; st.selectedIndex = 0;
    sA.__agyis_hud_render();
    const prevBtnDisabledAt0 = hud.querySelector("#agyis-checkpoint-prev").disabled;
    hud.querySelector("#agyis-checkpoint-next").dispatchEvent({ type: "click" });
    const cpAfterNextBtn = st.activeCheckpointIndex;

    // Check Jump-to-Previous disabled on CHECKPOINT at Window 0
    const cp0JumpDisabled = sA.buildInspectorHtml({ step_index: 0, type: "CHECKPOINT", content: "cp0" }, { activeCheckpointIndex: 0, activeTab: "step" }, {}).includes("disabled");

    // 4 & 7: From Window 2 (step 100), click Prev Checkpoint -> Window 1 & page 0 + row in DOM
    st.tablePage = 2; sA.__agyis_hud_render();
    hud.querySelector('.agyis-step-grid-item[data-index="100"]').dispatchEvent({ type: "click" });
    const cpWhen100 = st.activeCheckpointIndex;
    hud.querySelector("#agyis-checkpoint-prev").dispatchEvent({ type: "click" });
    const cpAfterPrevFrom2 = st.activeCheckpointIndex;
    hud.querySelector("#agyis-checkpoint-prev").dispatchEvent({ type: "click" });
    const pageAfterCpPrev0 = st.tablePage;
    const selectedRowInDom = Boolean(hud.querySelector(`.agyis-step-grid-item[data-index="${st.selectedIndex}"]`));

    // 5: Jump to Previous Checkpoint card button from Window 2 while at #80 -> Window 1
    st.activeCheckpointIndex = 2; st.selectedIndex = 80; sA.__agyis_hud_render();
    hud.querySelector("#agyis-jump-prev-checkpoint").dispatchEvent({ type: "click" });
    const cpAfterJumpPrev = st.activeCheckpointIndex;

    // 6: Stream update while inspecting #80 in Window 2 + details/inspector scroll preservation on step 50
    const makeFrame = (flags, obj) => {
        const b = new TextEncoder().encode(JSON.stringify(obj)), u = new Uint8Array(5 + b.length);
        u[0] = flags; new DataView(u.buffer).setUint32(1, b.length, false); u.set(b, 5); return u;
    };
    let streamCount = 121;
    sA.fetch = async (url) => {
        if (url.includes("StreamAgentStateUpdates")) {
            const stepsArr = st.rootData.steps.map((s, idx) => ({
                stepIndex: idx,
                type: s.type === "CHECKPOINT" ? "CORTEX_STEP_TYPE_CHECKPOINT" : "CORTEX_STEP_TYPE_USER_INPUT",
                content: s.content || "", thinking: s.thinking || "",
                checkpoint: s.type === "CHECKPOINT" ? { sessionSummary: s.compaction_summary || "cp" } : undefined,
            }));
            for (let x = 120; x < streamCount; x++) stepsArr.push({ stepIndex: x, type: "CORTEX_STEP_TYPE_USER_INPUT", content: "new " + x });
            const frames = [makeFrame(0x00, { update: { conversationId: "repro-checkpoints", mainTrajectoryUpdate: { stepsUpdate: { indices: stepsArr.map((_, i) => i), steps: stepsArr, totalLength: stepsArr.length } } } }), makeFrame(0x02, {})];
            let fi = 0;
            return { ok: true, status: 200, body: { getReader: () => ({ async read() { return fi < frames.length ? { done: false, value: frames[fi++] } : { done: true }; } }) } };
        }
        return { ok: false, status: 404, async json() { return null; } };
    };
    st.currentData = JSON.parse(JSON.stringify(st.rootData));
    st.activeCheckpointIndex = 2; st.selectedIndex = 80;
    sA.__agyis_hud_start_stream("repro-checkpoints");
    await new Promise(r => setTimeout(r, 2)); sA.__flushRaf();
    const cpAfterStreamAt80 = st.activeCheckpointIndex;

    // Select step 50, collapse <details> + scroll inspector, receive stream tick
    st.selectedIndex = 50; st.activeCheckpointIndex = 1; sA.__agyis_hud_render();
    const det50 = hud.querySelector("details.agyis-thinking-block");
    det50.open = false; det50.removeAttribute("open");
    hud.querySelector("#agyis-inspector-body").scrollTop = 210;
    streamCount = 122;
    sA.__agyis_hud_start_stream("repro-checkpoints");
    await new Promise(r => setTimeout(r, 2)); sA.__flushRaf();
    const thinkingOpenAfterStream = hud.querySelector("details.agyis-thinking-block").open;
    const inspScrollAfterStream = hud.querySelector("#agyis-inspector-body").scrollTop;

    // 8 & Timeline 5D: Timeline scrollTop/Left + scrollIntoView + untimestamped CHECKPOINT x0 > 0 + exclusive Activity lane
    st.mainDeckTab = "timeline"; st.timelineMode = "steps"; sA.__agyis_hud_render();
    const tlHtml = hud.innerHTML;
    const cpBarMatch = tlHtml.match(/#40[\s\S]*?agyis-timeline-step-bar"[^>]*style="[^"]*left:\s*([\d.]+)px/);
    const cp40LeftPx = cpBarMatch ? parseFloat(cpBarMatch[1]) : -1;
    st.timelineMode = "activity"; sA.__agyis_hud_render();
    const actHtml = hud.innerHTML;
    const filesLaneHasZero = actHtml.includes("Files &amp; Code") || actHtml.includes("Files & Code") ? /Files &(?:amp;)? Code<\/span>[\s\S]*?\(0\)/.test(actHtml) : false;
    st.timelineMode = "steps"; sA.__agyis_hud_render();
    const tlWrapBefore = hud.querySelector(".agyis-timeline-scroll-wrap");
    tlWrapBefore.scrollTop = 450; tlWrapBefore.scrollLeft = 200;
    callsA.length = 0;
    hud.querySelector('.agyis-timeline-step-row[data-step-index="85"]').dispatchEvent({ type: "click" });
    const tlWrapAfter = hud.querySelector(".agyis-timeline-scroll-wrap");
    const tlScrollTopAfter = tlWrapAfter.scrollTop, tlScrollLeftAfter = tlWrapAfter.scrollLeft;
    const tlLastScroll = callsA[callsA.length - 1] || {};

    // 9: Step grid scrollTop + instant scrollIntoView (no behavior:"smooth")
    st.mainDeckTab = "context"; st.tablePage = 0; sA.__agyis_hud_render();
    hud.querySelector(".agyis-step-grid-body").scrollTop = 320;
    callsA.length = 0;
    hud.querySelector('.agyis-step-grid-item[data-index="15"]').dispatchEvent({ type: "click" });
    const gridScrollTopAfter = hud.querySelector(".agyis-step-grid-body").scrollTop;
    const gridLastScroll = callsA[callsA.length - 1] || {};

    // 10: Search debounce/caret/first-Enter/filter-aware j/k/next/modifier-guard/Esc/Clear/compaction_summary
    const si = hud.querySelector("#agyis-search-input");
    si.focus(); si.value = "alpha"; si.setSelectionRange(2, 2);
    si.dispatchEvent({ type: "input", target: si });
    await new Promise(r => setTimeout(r, 18));
    const searchInitMatchIdx = st.currentMatchIdx;
    const searchCounterBeforeEnter = hud.querySelector(".agyis-hud-search-counter")._innerHTML;
    const caretAfterInput = [hud.querySelector("#agyis-search-input").selectionStart, hud.querySelector("#agyis-search-input").selectionEnd];
    hud.querySelector("#agyis-search-input").dispatchEvent({ type: "keydown", key: "Enter", shiftKey: false });
    const firstEnterSelected = st.selectedIndex;
    sA.dispatchEvent({ type: "keydown", key: "j", target: docA.body });
    const afterFilterJ = st.selectedIndex;
    sA.dispatchEvent({ type: "keydown", key: "ArrowDown", ctrlKey: true, target: docA.body });
    const afterCtrlArrow = st.selectedIndex;
    hud.querySelector("#agyis-step-next").dispatchEvent({ type: "click" });
    const afterFilterNextBtn = st.selectedIndex;
    sA.dispatchEvent({ type: "keydown", key: "k", target: docA.body });
    const afterFilterK = st.selectedIndex;
    hud.querySelector("#agyis-search-clear").dispatchEvent({ type: "click" });
    const pageAfterClearSearch = st.tablePage;
    const matchIdxAfterClear = st.currentMatchIdx;

    // Search compaction_summary
    st.filterQuery = "Checkpoint at step 80"; sA.__agyis_hud_render();
    const cpSummaryMatches = st.searchMatchIndices.slice();
    st.filterQuery = ""; sA.__agyis_hud_render();

    // 11: Hover cleanup across segment click
    st.activeCheckpointIndex = 2; sA.__agyis_hud_render();
    const seg90 = hud.querySelector('.agyis-context-segment[data-step-index="90"]');
    seg90.dispatchEvent({ type: "mouseenter" });
    const hoveredBeforeClick = st.hoveredItemKey;
    seg90.dispatchEvent({ type: "click" });
    const hoveredAfterClick = st.hoveredItemKey;

    // 12: ConnectRPC buildHudTrajectoryData parity (23, retryInfos, cumulative reset, sparse gm.stepIndex, Option B)
    const rpcTraj = sA.buildHudTrajectoryData("rpc-cp", [
        { stepIndex: 1000, type: "CORTEX_STEP_TYPE_USER_INPUT", content: "hi", tokens: 80 },
        { stepIndex: 1001, type: 23, checkpoint: { checkpointIndex: 0, sessionSummary: "cp1" } },
        { stepIndex: 1002, type: "CORTEX_STEP_TYPE_USER_INPUT", content: "mid", tokens: 40 },
        { stepIndex: 1003, type: "CORTEX_STEP_TYPE_CHECKPOINT", checkpoint: { checkpointIndex: 1, sessionSummary: "cp2" }, metadata: { retryInfos: [{ usage: { cacheReadTokens: 50000, inputTokens: 3000 } }] } },
        { stepIndex: 1004, type: "CORTEX_STEP_TYPE_USER_INPUT", content: "late", tokens: 25 },
    ], [{ stepIndex: 1002, chatStartMetadata: { contextWindowMetadata: { estimatedTokensUsed: 12345 } } }], [], null);

    // 13 (Electron HUD): Refresh preserves cursor on same convo when not at end
    st.selectedIndex = 75;
    sA.loadConversationViaRpc = async () => JSON.parse(JSON.stringify(st.rootData));
    hud.querySelector("#agyis-refresh-btn").dispatchEvent({ type: "click" });
    await new Promise(r => setTimeout(r, 2));
    const hudRefreshSelected = st.selectedIndex;

    // --- Context B: :40624 Playback Shell ---
    const { sandbox: sB, doc: docB, makeEl: makeElB } = createDomSandbox("/");
    const pbHud = makeElB("div"); pbHud.id = "agyis-trajectory-hud"; docB.body.appendChild(pbHud);
    const pbSel = makeElB("select"); pbSel.id = "agyis-playback-convo"; docB.body.appendChild(pbSel);
    const pbStatus = makeElB("span"); pbStatus.id = "agyis-playback-status"; docB.body.appendChild(pbStatus);
    const pbReload = makeElB("button"); pbReload.id = "agyis-playback-reload"; docB.body.appendChild(pbReload);
    const pbLive = makeElB("input"); pbLive.id = "agyis-playback-live"; docB.body.appendChild(pbLive);
    let pbPayload = JSON.parse(JSON.stringify(bundle.traj));
    sB.fetch = async (url) => {
        if (url.startsWith("/api/conversations")) return { ok: true, status: 200, async json() { return { conversations: [{ id: "repro-checkpoints", summary: "Repro" }] }; } };
        if (url.startsWith("/api/trajectory")) return { ok: true, status: 200, async json() { return JSON.parse(JSON.stringify(pbPayload)); } };
        return { ok: false, status: 404 };
    };
    vm.runInContext(bundle.pbScript, sB);
    await new Promise(r => setTimeout(r, 4));
    const stB = sB.__agyis_hud_state;
    const pbCpBefore80 = stB.activeCheckpointIndex;
    pbHud.querySelector('.agyis-context-segment[data-step-index="80"]').dispatchEvent({ type: "click" });
    const pbCpAfter80 = stB.activeCheckpointIndex;
    const pbTablePageAfter80 = stB.tablePage;

    // Search over tool_calls in :40624
    stB.filterQuery = "toolneedle"; sB.__agyis_hud_render();
    const pbToolMatches = stB.searchMatchIndices.slice();
    stB.filterQuery = ""; sB.__agyis_hud_render();

    // Refresh button preserves cursor in :40624
    stB.tablePage = 2; sB.__agyis_hud_render();
    pbHud.querySelector('.agyis-step-grid-item[data-index="105"]').dispatchEvent({ type: "click" });
    pbHud.querySelector("#agyis-refresh-btn").dispatchEvent({ type: "click" });
    await new Promise(r => setTimeout(r, 2));
    const pbSelAfterRefresh = stB.selectedIndex;

    // Keyboard nav k works & Esc does NOT hide playback HUD
    sB.dispatchEvent({ type: "keydown", key: "k", target: docB.body });
    const pbSelAfterK = stB.selectedIndex;
    sB.dispatchEvent({ type: "keydown", key: "Escape", target: docB.body });
    const pbHudDisplayAfterEsc = pbHud.style.display;

    // Live reload wasAtEnd tail-follow
    pbHud.querySelector('.agyis-step-grid-item[data-index="119"]').dispatchEvent({ type: "click" });
    const extraStep = { step_index: 120, type: "USER_INPUT", content: "tail 120", tokens: 50 };
    pbPayload.steps.push(extraStep);
    pbPayload.checkpoints[2].end_index = 120;
    await sB.__agyis_hud_load_convo("repro-checkpoints", true);
    const pbSelAfterLiveTail = stB.selectedIndex;

    console.log(JSON.stringify({
        cpBefore80, cpAfterClick80, cpAfterClick40, prevBtnDisabledAt0, cpAfterNextBtn, cp0JumpDisabled,
        cpWhen100, cpAfterPrevFrom2, pageAfterCpPrev0, selectedRowInDom, cpAfterJumpPrev,
        cpAfterStreamAt80, thinkingOpenAfterStream, inspScrollAfterStream,
        cp40LeftPx, filesLaneHasZero, tlScrollTopAfter, tlScrollLeftAfter, tlLastScroll,
        gridScrollTopAfter, gridLastScroll,
        searchInitMatchIdx, searchCounterBeforeEnter, caretAfterInput, firstEnterSelected,
        afterFilterJ, afterCtrlArrow, afterFilterNextBtn, afterFilterK, pageAfterClearSearch, matchIdxAfterClear, cpSummaryMatches,
        hoveredBeforeClick, hoveredAfterClick,
        rpcCpLen: rpcTraj.checkpoints.length,
        rpcCp0: [rpcTraj.checkpoints[0].start_index, rpcTraj.checkpoints[0].end_index, rpcTraj.checkpoints[0].has_checkpoint, rpcTraj.checkpoints[0].summary],
        rpcCp1: [rpcTraj.checkpoints[1].start_index, rpcTraj.checkpoints[1].end_index, rpcTraj.checkpoints[1].summary, rpcTraj.checkpoints[1].total_tokens],
        rpcType1: rpcTraj.steps[1].type,
        rpcCacheRead3: rpcTraj.steps[3].cacheReadTokens,
        rpcCum3: rpcTraj.steps[3].cumulative_tokens,
        rpcTok3: rpcTraj.steps[3].tokens,
        hudRefreshSelected,
        pbCpBefore80, pbCpAfter80, pbTablePageAfter80, pbToolMatches, pbSelAfterRefresh, pbSelAfterK, pbHudDisplayAfterEsc, pbSelAfterLiveTail,
    }));
})();
"""
        proc = subprocess.run(
            [node_bin, "-e", node_driver],
            input=json.dumps({"hudScript": hud_script, "pbScript": pb_script, "traj": traj}),
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        )
        self.assertEqual(proc.returncode, 0, f"Node regression failed:\nSTDOUT:{proc.stdout}\nSTDERR:{proc.stderr}")
        out = json.loads(proc.stdout.strip().splitlines()[-1])

        # Fix 1: CHECKPOINT jump-back, Prev/Next Checkpoint, Jump to Previous, Stream tick
        self.assertEqual(out["cpBefore80"], 2)
        self.assertEqual(out["cpAfterClick80"], 2)
        self.assertEqual(out["cpAfterClick40"], 1)
        self.assertTrue(out["prevBtnDisabledAt0"])
        self.assertEqual(out["cpAfterNextBtn"], 1)
        self.assertTrue(out["cp0JumpDisabled"])
        self.assertEqual(out["cpWhen100"], 2)
        self.assertEqual(out["cpAfterPrevFrom2"], 1)
        self.assertEqual(out["cpAfterJumpPrev"], 1)
        self.assertEqual(out["cpAfterStreamAt80"], 2)
        # Fix 2: Pagination sync
        self.assertEqual(out["pageAfterCpPrev0"], 0)
        self.assertTrue(out["selectedRowInDom"])
        # Fix 3: Scroll & <details> preservation + instant scrollIntoView
        self.assertFalse(out["thinkingOpenAfterStream"])
        self.assertEqual(out["inspScrollAfterStream"], 210)
        self.assertEqual(out["tlScrollTopAfter"], 450)
        self.assertEqual(out["tlScrollLeftAfter"], 200)
        self.assertEqual(out["tlLastScroll"]["dataStepIndex"], "85")
        self.assertEqual(out["tlLastScroll"]["opts"], {"block": "nearest", "inline": "nearest"})
        self.assertEqual(out["gridScrollTopAfter"], 320)
        self.assertEqual(out["gridLastScroll"]["opts"], {"block": "nearest", "inline": "nearest"})
        # Fix 5D: Timeline interpolation & exclusive Activity lane
        self.assertGreater(out["cp40LeftPx"], 0.0)
        self.assertTrue(out["filesLaneHasZero"])
        # Fix 4: Search init/caret/first-Enter/filter-nav/clear/compaction_summary/modifier guard
        self.assertEqual(out["searchInitMatchIdx"], -1)
        self.assertEqual(out["searchCounterBeforeEnter"], "-/3")
        self.assertEqual(out["caretAfterInput"], [2, 2])
        self.assertEqual(out["firstEnterSelected"], 10)
        self.assertEqual(out["afterFilterJ"], 60)
        self.assertEqual(out["afterCtrlArrow"], 60)
        self.assertEqual(out["afterFilterNextBtn"], 110)
        self.assertEqual(out["afterFilterK"], 60)
        self.assertEqual(out["pageAfterClearSearch"], 1)
        self.assertEqual(out["matchIdxAfterClear"], -1)
        self.assertEqual(out["cpSummaryMatches"], [80])
        # Fix 5A: Sticky hover cleared
        self.assertEqual(out["hoveredBeforeClick"], "step-90")
        self.assertIsNone(out["hoveredAfterClick"])
        # Fix 5B: ConnectRPC parity & Option B disjoint windows
        self.assertEqual(out["rpcCpLen"], 3)
        self.assertEqual(out["rpcCp0"], [0, 0, False, "Initial Trajectory"])
        self.assertEqual(out["rpcCp1"], [1, 2, "cp1", 12345])
        self.assertEqual(out["rpcType1"], "CHECKPOINT")
        self.assertEqual(out["rpcCacheRead3"], 50000)
        self.assertEqual(out["rpcCum3"], out["rpcTok3"])
        # Fix 5C: Refresh & :40624 Playback parity
        self.assertEqual(out["hudRefreshSelected"], 75)
        self.assertEqual(out["pbCpBefore80"], 2)
        self.assertEqual(out["pbCpAfter80"], 2)
        self.assertEqual(out["pbTablePageAfter80"], 1)
        self.assertEqual(out["pbToolMatches"], [35])
        self.assertEqual(out["pbSelAfterRefresh"], 105)
        self.assertEqual(out["pbSelAfterK"], 104)
        self.assertNotEqual(out["pbHudDisplayAfterEsc"], "none")
        self.assertEqual(out["pbSelAfterLiveTail"], 120)


if __name__ == "__main__":
    unittest.main()
