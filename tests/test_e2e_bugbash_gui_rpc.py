#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Arafat Zahan (@kuasha420)
# Corporate Stewardship & Infrastructure: Purrfect Software Limited (PSL)
# Governed by: ICARO-42/b Ordinance (Company-Supported Personal IP Framework)

"""
Bug Bash GUI E2E Suite — ConnectRPC Streaming & Live DevTools CDP Controller (F12, F13).
Executes real harness/gui/assets/hud_rpc.js + hotkey.js in Node.js and real
CDPWebSocketClient over RFC 6455 socketpairs and inject_trajectory_debug.
"""

from __future__ import annotations

import importlib.resources
import json
import os
from pathlib import Path
import shutil
import socket
import struct
import subprocess
import tempfile
import unittest
from unittest.mock import patch

from harness.commands.gui import (
    CDPConnectionError,
    CDPError,
    CDPWebSocketClient,
    build_hotkey_script,
    find_page_target,
    get_devtools_active_port,
    inject_trajectory_debug,
)


def _encode_ws_text_frame(payload_obj: dict) -> bytes:
    """Encodes an unmasked RFC 6455 text frame as sent by CDP servers."""
    payload = json.dumps(payload_obj).encode("utf-8")
    n = len(payload)
    if n < 126:
        hdr = bytes([0x81, n])
    elif n <= 0xFFFF:
        hdr = bytes([0x81, 126]) + struct.pack(">H", n)
    else:
        hdr = bytes([0x81, 127]) + struct.pack(">Q", n)
    return hdr + payload


def _read_ws_client_json(sock: socket.socket) -> dict:
    """Reads and unmasks a masked RFC 6455 text frame sent by CDPWebSocketClient."""
    def _exact(k: int) -> bytes:
        buf = bytearray()
        while len(buf) < k:
            chunk = sock.recv(k - len(buf))
            if not chunk:
                raise EOFError("socket closed")
            buf.extend(chunk)
        return bytes(buf)

    hdr = _exact(2)
    plen = hdr[1] & 0x7F
    if plen == 126:
        plen = struct.unpack(">H", _exact(2))[0]
    elif plen == 127:
        plen = struct.unpack(">Q", _exact(8))[0]
    mask = _exact(4)
    masked = _exact(plen)
    raw = bytes(b ^ mask[i % 4] for i, b in enumerate(masked))
    return json.loads(raw.decode("utf-8"))


class _RecordingCDPClient(CDPWebSocketClient):
    """Real CDPWebSocketClient subclass recording commands without mocking evaluate()."""

    def __init__(self, page_url: str) -> None:
        super().__init__(timeout=1.0)
        self.page_url = page_url
        self.commands: list[tuple[str, dict]] = []

    def send_command(self, method: str, params=None):
        self._req_id += 1
        params = params or {}
        self.commands.append((method, params))
        if method == "Runtime.evaluate":
            expr = params.get("expression", "")
            if expr == "window.location.href":
                return {"result": {"value": self.page_url}}
            return {"result": {"value": {"success": True, "open": True}}}
        return {}


_RPC_PREAMBLE = r"""
const window = {
    location: { origin: "https://127.0.0.1:40623", pathname: "/c/convo-1", search: "" },
    __APP_CONFIG__: {},
    addEventListener() {},
    removeEventListener() {},
};
global.window = window;
const _rafQueue = [];
global.requestAnimationFrame = (cb) => { _rafQueue.push(cb); return _rafQueue.length; };
global.cancelAnimationFrame = () => {};
global.__flushRaf = () => {
    while (_rafQueue.length) {
        const cb = _rafQueue.shift();
        cb(performance.now());
    }
};
global.makeConnectFrame = (flags, objOrStr) => {
    const str = typeof objOrStr === "string" ? objOrStr : JSON.stringify(objOrStr);
    const body = new TextEncoder().encode(str);
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


class TestBugBashGuiRpcAndCdp(unittest.TestCase):
    """Real Node.js ConnectRPC (hud_rpc.js) and real CDPWebSocketClient E2E tests (F12, F13)."""

    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.ws = Path(self.temp_dir.name).resolve()

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def _run_node(self, js_body: str) -> dict:
        node_bin = shutil.which("node")
        if not node_bin:
            self.skipTest("node binary unavailable in PATH")
        script = f"{_RPC_PREAMBLE}\n(async () => {{\n{js_body}\n}})();\n"
        proc = subprocess.run([node_bin, "-e", script], capture_output=True, text=True, timeout=5, check=False)
        self.assertEqual(proc.returncode, 0, f"Node harness failed:\nSTDOUT:{proc.stdout}\nSTDERR:{proc.stderr}")
        lines = [line.strip() for line in proc.stdout.splitlines() if line.strip()]
        return json.loads(lines[-1])

    # --- Feature 12: Live ConnectRPC 60 FPS Streaming (Real hud_rpc.js) ---

    def test_t1_f12_01_02_04_05_connect_client_framing_csrf_and_stream(self) -> None:
        """F12.1, F12.2, F12.4, F12.5: Executes real InSituConnectClient Connect framing, CSRF header, and streaming."""
        stream_path = json.dumps(str(importlib.resources.files("harness.gui.assets").joinpath("hud_stream.js")))
        rpc_path = json.dumps(str(importlib.resources.files("harness.gui.assets").joinpath("hud_rpc.js")))
        res = self._run_node(f"""
        const fs = require('fs');
        eval(fs.readFileSync({stream_path}, 'utf8'));
        eval(fs.readFileSync({rpc_path}, 'utf8'));

        let capturedUrl = null;
        let capturedHeaders = null;
        let capturedBody = null;
        const frames = [
            makeConnectFrame(0x00, {{ update: {{ conversationId: "convo-1", mainTrajectoryUpdate: {{ stepsUpdate: {{ indices: [0], steps: [{{ stepIndex: 0, type: "CORTEX_STEP_TYPE_USER_INPUT", content: "hello" }}], totalLength: 1 }} }} }} }}),
            makeConnectFrame(0x02, {{}})
        ];
        global.fetch = async (url, init) => {{
            capturedUrl = url;
            capturedHeaders = init.headers;
            capturedBody = init.body;
            return makeMockStreamResponse(frames);
        }};

        const client = new window.InSituConnectClient({{ port: 42161, csrfToken: "csrf-secret-xyz" }});
        let seenStates = [];
        await client.streamConversation("convo-1", (st) => {{
            seenStates.push({{ convoId: st.conversationId, steps: st.stepsInSlice.length }});
        }});
        global.__flushRaf();

        const view = new DataView(capturedBody.buffer, capturedBody.byteOffset, 5);
        const envelopeFlags = capturedBody[0];
        const envelopeLen = view.getUint32(1, false);
        const decodedReq = JSON.parse(new TextDecoder().decode(capturedBody.slice(5)));

        console.log(JSON.stringify({{
            port: client.port,
            capturedUrl,
            csrfHeader: capturedHeaders["x-codeium-csrf-token"],
            envelopeFlags,
            envelopeLen,
            bodyLen: capturedBody.length - 5,
            reqConvoId: decodedReq.conversationId,
            seenStates
        }}));
        """)
        self.assertEqual(res["port"], 42161)
        self.assertIn("StreamAgentStateUpdates", res["capturedUrl"])
        self.assertEqual(res["csrfHeader"], "csrf-secret-xyz")
        self.assertEqual(res["envelopeFlags"], 0)
        self.assertEqual(res["envelopeLen"], res["bodyLen"])
        self.assertEqual(res["reqConvoId"], "convo-1")
        self.assertEqual(res["seenStates"], [{"convoId": "convo-1", "steps": 1}])

    def test_t1_f12_03_stream_render_coordinator_raf_batching(self) -> None:
        """F12.3: Real StreamRenderCoordinator coalesces synchronous bursts into a single RAF callback."""
        stream_path = json.dumps(str(importlib.resources.files("harness.gui.assets").joinpath("hud_stream.js")))
        rpc_path = json.dumps(str(importlib.resources.files("harness.gui.assets").joinpath("hud_rpc.js")))
        res = self._run_node(f"""
        const fs = require('fs');
        eval(fs.readFileSync({stream_path}, 'utf8'));
        eval(fs.readFileSync({rpc_path}, 'utf8'));

        let renderCalls = 0;
        let lastStepCount = 0;
        const coord = new window.StreamRenderCoordinator((st) => {{
            renderCalls++;
            lastStepCount = st.stepsInSlice.length;
        }});
        for (let i = 0; i < 5; i++) {{
            coord.ingestUpdate({{
                conversationId: "c-raf",
                mainTrajectoryUpdate: {{ stepsUpdate: {{ indices: [i], steps: [{{ stepIndex: i }}], totalLength: i + 1 }} }}
            }});
        }}
        const beforeRaf = renderCalls;
        global.__flushRaf();
        console.log(JSON.stringify({{ beforeRaf, afterRaf: renderCalls, lastStepCount }}));
        """)
        self.assertEqual(res["beforeRaf"], 0)
        self.assertEqual(res["afterRaf"], 1)
        self.assertEqual(res["lastStepCount"], 5)

    def test_t2_f12_01_to_05_connect_boundaries(self) -> None:
        """F12.B1-B5: Real hud_stream.js + hud_rpc.js handles 100KB Connect frame, AbortController cancel, null delta, burst, empty CSRF."""
        stream_path = json.dumps(str(importlib.resources.files("harness.gui.assets").joinpath("hud_stream.js")))
        rpc_path = json.dumps(str(importlib.resources.files("harness.gui.assets").joinpath("hud_rpc.js")))
        res = self._run_node(f"""
        const fs = require('fs');
        eval(fs.readFileSync({stream_path}, 'utf8'));
        eval(fs.readFileSync({rpc_path}, 'utf8'));

        // B5: Missing CSRF omits header
        let headersNoCsrf = null;
        const bigText = "X".repeat(100000);
        const bigFrame = makeConnectFrame(0x00, {{
            update: {{
                conversationId: "c-big",
                mainTrajectoryUpdate: {{ stepsUpdate: {{ indices: [0], steps: [{{ stepIndex: 0, content: bigText }}], totalLength: 1 }} }}
            }}
        }});
        global.fetch = async (_url, init) => {{
            headersNoCsrf = init.headers;
            return makeMockStreamResponse([bigFrame, makeConnectFrame(0x02, {{}})]);
        }};
        const client = new window.InSituConnectClient({{ port: 40623, csrfToken: "" }});
        let bigContentLen = 0;
        await client.streamConversation("c-big", (st) => {{
            bigContentLen = st.stepsInSlice[0].content.length;
        }});
        global.__flushRaf();

        // B2: Switching conversation aborts prior AbortController signal
        let firstSignal = null;
        global.fetch = (_url, init) => {{
            if (!firstSignal) {{
                firstSignal = init.signal;
                return new Promise(() => {{}}); // stays pending until aborted
            }}
            return Promise.resolve(makeMockStreamResponse([makeConnectFrame(0x02, {{}})]));
        }};
        client.streamConversation("c-first", () => {{}}).catch(() => {{}});
        const abortedBefore = firstSignal.aborted;
        await client.streamConversation("c-second", () => {{}});
        const abortedAfter = firstSignal.aborted;

        // B3 & B4: Null delta ignored; 25 rapid deltas coalesce
        let calls = 0;
        const coord = new window.StreamRenderCoordinator(() => {{ calls++; }});
        coord.ingestUpdate(null);
        global.__flushRaf();
        const afterNull = calls;
        for (let i = 0; i < 25; i++) {{
            coord.ingestUpdate({{ conversationId: "c-burst", mainTrajectoryUpdate: {{ stepsUpdate: {{ indices: [i], steps: [{{ stepIndex: i }}], totalLength: i + 1 }} }} }});
        }}
        global.__flushRaf();

        console.log(JSON.stringify({{
            hasCsrfHeader: Object.prototype.hasOwnProperty.call(headersNoCsrf, "x-codeium-csrf-token"),
            bigContentLen,
            abortedBefore,
            abortedAfter,
            afterNull,
            burstFlushes: calls
        }}));
        """)
        self.assertFalse(res["hasCsrfHeader"])
        self.assertEqual(res["bigContentLen"], 100000)
        self.assertFalse(res["abortedBefore"])
        self.assertTrue(res["abortedAfter"])
        self.assertEqual(res["afterNull"], 0)
        self.assertEqual(res["burstFlushes"], 1)

    # --- Feature 13: Live DevTools CDP Controller (Real CDPWebSocketClient) ---

    def test_t1_f13_01_read_devtools_active_port(self) -> None:
        """F13.1: Reads active port from DevToolsActivePort file."""
        port_file = self.ws / "DevToolsActivePort"
        port_file.write_text("42161\n/devtools/browser/abc-123\n", encoding="utf-8")
        port, path = get_devtools_active_port(port_file)
        self.assertEqual(port, 42161)
        self.assertEqual(path, "/devtools/browser/abc-123")

    def test_t1_f13_02_discover_page_target(self) -> None:
        """F13.2: Finds Antigravity webview page target from CDP JSON targets."""
        mock_targets = [
            {"type": "browser", "title": "Chrome", "webSocketDebuggerUrl": "ws://127.0.0.1:42161/browser"},
            {"type": "page", "title": "Google Antigravity", "url": "https://127.0.0.1:40623/c/123", "webSocketDebuggerUrl": "ws://127.0.0.1:42161/page/1"},
        ]
        target = find_page_target(mock_targets)
        self.assertIsNotNone(target)
        self.assertEqual(target.get("title"), "Google Antigravity")

    def test_t1_f13_03_cdp_evaluate_expression(self) -> None:
        """F13.3: Executes real CDPWebSocketClient.evaluate() over RFC 6455 socketpair."""
        client_sock, peer_sock = socket.socketpair()
        client = CDPWebSocketClient(timeout=1.0)
        client.sock = client_sock
        try:
            peer_sock.sendall(_encode_ws_text_frame({
                "id": 1,
                "result": {"result": {"value": "https://127.0.0.1:40623/c/test-convo"}},
            }))
            res = client.evaluate("window.location.href")
            sent = _read_ws_client_json(peer_sock)
            self.assertEqual(res, "https://127.0.0.1:40623/c/test-convo")
            self.assertEqual(sent["method"], "Runtime.evaluate")
            self.assertEqual(sent["params"]["expression"], "window.location.href")
        finally:
            client.sock = None
            client_sock.close()
            peer_sock.close()

    def test_t1_f13_04_inject_trajectory_debug_flags(self) -> None:
        """F13.4: Real inject_trajectory_debug sends localStorage flags and HUD bundle via CDPWebSocketClient."""
        client = _RecordingCDPClient("https://127.0.0.1:40623/c/test-convo")
        with patch("harness.commands.gui.discover_language_server_endpoint", return_value=None), \
             patch("harness.gui.server.ensure_trajectory_server", return_value=None):
            res = inject_trajectory_debug(
                client,
                flags={"enable-trajectory-debug-tools": True},
                brain_dir=self.ws,
            )
        self.assertTrue(res.get("success"))
        self.assertEqual(res.get("convo_id"), "test-convo")
        methods = [m for m, _ in client.commands]
        self.assertIn("Page.addScriptToEvaluateOnNewDocument", methods)
        eval_exprs = [p["expression"] for m, p in client.commands if m == "Runtime.evaluate"]
        self.assertTrue(any("enable-trajectory-debug-tools" in ex for ex in eval_exprs))
        self.assertTrue(any("agyis-trajectory-hud" in ex for ex in eval_exprs))

    def test_t1_f13_05_hotkey_listener_installation(self) -> None:
        """F13.5: build_hotkey_script produces valid JS with F12 and Ctrl+Shift+T listeners."""
        script = build_hotkey_script()
        self.assertTrue(len(script) > 100)
        self.assertIn("F12", script)
        self.assertIn("Ctrl+Shift+T", script)

    def test_t2_f13_01_to_05_cdp_boundaries(self) -> None:
        """F13.B1-B5: Empty/missing DevToolsActivePort, empty targets, timeout, and real CDPError on exceptionDetails."""
        port_file = self.ws / "DevToolsActivePort"
        port_file.write_text("", encoding="utf-8")
        with self.assertRaises((CDPConnectionError, ValueError)):
            get_devtools_active_port(port_file)

        with self.assertRaises((CDPConnectionError, FileNotFoundError)):
            get_devtools_active_port(self.ws / "nonexistent_port_file")

        self.assertIsNone(find_page_target([]))

        timeout_client = CDPWebSocketClient(timeout=0.1)
        with patch("socket.create_connection", side_effect=socket.timeout):
            with self.assertRaises(CDPConnectionError):
                timeout_client.connect("ws://127.0.0.1:42161/test")

        client_sock, peer_sock = socket.socketpair()
        err_client = CDPWebSocketClient(timeout=1.0)
        err_client.sock = client_sock
        try:
            peer_sock.sendall(_encode_ws_text_frame({
                "id": 1,
                "result": {"exceptionDetails": {"text": "SyntaxError: Unexpected token ("}},
            }))
            with self.assertRaises(CDPError) as ctx:
                err_client.evaluate("invalid(")
            self.assertIn("SyntaxError", str(ctx.exception))
        finally:
            err_client.sock = None
            client_sock.close()
            peer_sock.close()

    # --- Tier 3 & 4 GUI Combinations ---

    def test_t3_c10_subagent_detection_and_connectrpc_stream(self) -> None:
        """C10 (F11 x F12): Real detectActiveConversationContext feeds subagent ID into InSituConnectClient."""
        hotkey_path = json.dumps(str(importlib.resources.files("harness.gui.assets").joinpath("hotkey.js")))
        stream_path = json.dumps(str(importlib.resources.files("harness.gui.assets").joinpath("hud_stream.js")))
        rpc_path = json.dumps(str(importlib.resources.files("harness.gui.assets").joinpath("hud_rpc.js")))
        subagent_id = "22222222-2222-2222-2222-222222222222"
        res = self._run_node(f"""
        const fs = require('fs');
        window.location = {{ origin: "https://127.0.0.1:40623", pathname: "/c/parent-1", search: "?tab=subagent_convo__{subagent_id}" }};
        eval(fs.readFileSync({hotkey_path}, 'utf8'));
        eval(fs.readFileSync({stream_path}, 'utf8'));
        eval(fs.readFileSync({rpc_path}, 'utf8'));

        const activeSub = window.detectActiveConversationContext();
        let streamedId = null;
        global.fetch = async (_url, init) => {{
            streamedId = JSON.parse(new TextDecoder().decode(init.body.slice(5))).conversationId;
            return makeMockStreamResponse([makeConnectFrame(0x02, {{}})]);
        }};
        const client = new window.InSituConnectClient({{ port: 40623 }});
        await client.streamConversation(activeSub, () => {{}});
        console.log(JSON.stringify({{ activeSub, streamedId }}));
        """)
        self.assertEqual(res["activeSub"], subagent_id)
        self.assertEqual(res["streamedId"], subagent_id)

    def test_t3_c11_devtools_cdp_and_spa_route_switch(self) -> None:
        """C11 (F13 x F10): Real CDPWebSocketClient returns routed URL parsed by real hotkey.js."""
        client_sock, peer_sock = socket.socketpair()
        client = CDPWebSocketClient(timeout=1.0)
        client.sock = client_sock
        try:
            peer_sock.sendall(_encode_ws_text_frame({
                "id": 1,
                "result": {"result": {"value": "https://127.0.0.1:40623/c/routed-uuid"}},
            }))
            url = client.evaluate("window.location.href")
        finally:
            client.sock = None
            client_sock.close()
            peer_sock.close()

        hotkey_path = json.dumps(str(importlib.resources.files("harness.gui.assets").joinpath("hotkey.js")))
        res = self._run_node(f"""
        const fs = require('fs');
        const u = new URL({json.dumps(url)});
        window.location = {{ origin: u.origin, pathname: u.pathname, search: u.search }};
        eval(fs.readFileSync({hotkey_path}, 'utf8'));
        console.log(JSON.stringify({{ convoId: window.detectActiveConversationContext() }}));
        """)
        self.assertEqual(res["convoId"], "routed-uuid")

    def test_t3_c14_cdp_controller_and_connectrpc_client(self) -> None:
        """C14 (F13 x F12): Real inject_trajectory_debug injects discovered ConnectRPC port into HUD payload."""
        client = _RecordingCDPClient("https://127.0.0.1:42161/c/convo-1")
        with patch("harness.commands.gui.discover_language_server_endpoint", return_value={"port": 42161, "url": "https://127.0.0.1:42161"}), \
             patch("harness.gui.server.ensure_trajectory_server", return_value=None):
            res = inject_trajectory_debug(client, conversation_id="convo-1", brain_dir=self.ws)
        self.assertTrue(res.get("success"))
        eval_exprs = [p["expression"] for m, p in client.commands if m == "Runtime.evaluate"]
        self.assertTrue(any('"connectRpcPort": 42161' in ex for ex in eval_exprs))

    def test_t4_s07_live_insitu_hud_dogfooding_session(self) -> None:
        """S07: End-to-end inject_trajectory_debug resolves subagent tab and parent_id from real transcript."""
        parent_dir = self.ws / "parent-uuid"
        child_dir = self.ws / "child-uuid"
        parent_dir.mkdir(parents=True)
        child_dir.mkdir(parents=True)
        (parent_dir / "transcript.jsonl").write_text(json.dumps({"source": "user", "content": "parent"}) + "\n", encoding="utf-8")
        (child_dir / "transcript.jsonl").write_text(json.dumps({"source": "user", "content": "child", "parent_conversation_id": "parent-uuid"}) + "\n", encoding="utf-8")

        client = _RecordingCDPClient("https://127.0.0.1:40623/c/parent-uuid?tab=subagent_convo__child-uuid")
        with patch("harness.commands.gui.discover_language_server_endpoint", return_value={"port": 42161, "url": "https://127.0.0.1:42161"}), \
             patch("harness.gui.server.ensure_trajectory_server", return_value=None):
            res = inject_trajectory_debug(client, brain_dir=self.ws)
        self.assertTrue(res.get("success"))
        self.assertEqual(res.get("convo_id"), "child-uuid")
        self.assertEqual(res.get("steps"), 1)
        hud_exprs = [p["expression"] for m, p in client.commands if m == "Runtime.evaluate" and "agyis-trajectory-hud" in p.get("expression", "")]
        self.assertEqual(len(hud_exprs), 1)
        self.assertIn('"parent_id": "parent-uuid"', hud_exprs[0])


if __name__ == "__main__":
    unittest.main()
