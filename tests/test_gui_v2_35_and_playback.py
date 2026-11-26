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
        rpc_js = importlib.resources.files("harness.gui.assets").joinpath("hud_rpc.js").read_text(encoding="utf-8")
        out = self._run_node(
            "global.window = { location: { origin: 'https://127.0.0.1:40623' } };\n"
            + rpc_js
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

        rpc_js = importlib.resources.files("harness.gui.assets").joinpath("hud_rpc.js").read_text(encoding="utf-8")
        out = self._run_node(
            "global.window = {};\n"
            + rpc_js
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
            "hud_styles.css", "hud_theme.js", "hud_header.js", "hud_context_bar.js",
            "hud_timeline.js", "hud_inspector.js", "hud_deck.js", "telemetry_hud.js",
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
        header_js = assets.joinpath("hud_header.js").read_text(encoding="utf-8")
        insp_js = assets.joinpath("hud_inspector.js").read_text(encoding="utf-8")
        out = self._run_node(
            "global.window = {};\n"
            + theme_js + "\n" + header_js + "\n" + insp_js + "\n"
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
            srv = start_trajectory_server(host="127.0.0.1", port=port, brain_dir=brain)
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

                for bad_path in ("/assets/../../pyproject.toml", "/assets/%2e%2e/pyproject.toml", "/assets/hud.js", "/assets/__init__.py"):
                    with self.assertRaises(urllib.error.HTTPError) as ctx:
                        urllib.request.urlopen(f"{base}{bad_path}", timeout=1.0)
                    self.assertEqual(ctx.exception.code, 404)
                    ctx.exception.close()
            finally:
                srv.shutdown()
                srv.server_close()

        assets = importlib.resources.files("harness.gui.assets")
        boot_js = assets.joinpath("playback_boot.js").read_text(encoding="utf-8")
        theme_js = assets.joinpath("hud_theme.js").read_text(encoding="utf-8")
        header_js = assets.joinpath("hud_header.js").read_text(encoding="utf-8")
        ctx_js = assets.joinpath("hud_context_bar.js").read_text(encoding="utf-8")
        tl_js = assets.joinpath("hud_timeline.js").read_text(encoding="utf-8")
        insp_js = assets.joinpath("hud_inspector.js").read_text(encoding="utf-8")
        deck_js = assets.joinpath("hud_deck.js").read_text(encoding="utf-8")
        rpc_js = assets.joinpath("hud_rpc.js").read_text(encoding="utf-8")
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
                epochs: [{ epoch_index: 0, start_index: 0, end_index: 0, total_tokens: 1200, token_breakdown: { user: 200 } }],
                token_breakdown: { user: 200 },
            };
        } };
    }
    return { ok: false, status: 404 };
};
"""
            + "\n".join((theme_js, header_js, ctx_js, tl_js, insp_js, deck_js, rpc_js, boot_js))
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


if __name__ == "__main__":
    unittest.main()
