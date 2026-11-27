# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Arafat Zahan (@kuasha420)
# Corporate Stewardship & Infrastructure: Purrfect Software Limited (PSL)
# Governed by: ICARO-42/b Ordinance (Company-Supported Personal IP Framework)

"""
Hermetic unit and integration tests for harness/commands/gui.py and 'agyis gui' CLI (ADR-014 / ADR-015).
"""

from __future__ import annotations

import argparse
import contextlib
import importlib.resources
import io
import json
import os
from pathlib import Path
import re
import shutil
import socket
import struct
import subprocess
import tempfile
import unittest
from unittest.mock import MagicMock, patch

from harness.cli import build_parser
from harness.commands.gui import (
    CDPConnectionError,
    CDPError,
    CDPTargetNotFoundError,
    CDPTimeoutError,
    CDPWebSocketClient,
    build_hotkey_script,
    cmd_gui,
    discover_language_server_endpoint,
    find_page_target,
    format_devtools_urls,
    generate_gui_systemd_path_unit,
    generate_gui_systemd_service_unit,
    get_cdp_targets,
    get_devtools_active_port,
    handle_gui_service_command,
    inject_trajectory_debug,
)
from harness.gui.trajectory_hud import (
    atc_context_layout,
    build_trajectory_hud_script,
    estimate_tokens,
    get_recent_conversations,
    load_conversation_trajectory,
    xtc_segment_width,
    ytc_layout_pass,
    ztc_row_count,
)


class TestDevToolsPortResolution(unittest.TestCase):
    """Tests resolution and parsing of DevToolsActivePort file."""

    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.port_file = Path(self.temp_dir.name) / "DevToolsActivePort"

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def test_get_devtools_active_port_valid(self) -> None:
        self.port_file.write_text("46391\n/devtools/browser/abc-123\n", encoding="utf-8")
        port, browser_path = get_devtools_active_port(self.port_file)
        self.assertEqual(port, 46391)
        self.assertEqual(browser_path, "/devtools/browser/abc-123")

    def test_get_devtools_active_port_single_line(self) -> None:
        self.port_file.write_text("9222\n", encoding="utf-8")
        port, browser_path = get_devtools_active_port(self.port_file)
        self.assertEqual(port, 9222)
        self.assertEqual(browser_path, "")

    def test_get_devtools_active_port_missing_file(self) -> None:
        missing = Path(self.temp_dir.name) / "nonexistent"
        with self.assertRaises(FileNotFoundError):
            get_devtools_active_port(missing)

    def test_get_devtools_active_port_empty_file(self) -> None:
        self.port_file.write_text("", encoding="utf-8")
        with self.assertRaises(ValueError):
            get_devtools_active_port(self.port_file)

    def test_get_devtools_active_port_invalid_int(self) -> None:
        self.port_file.write_text("not_a_port\n/browser\n", encoding="utf-8")
        with self.assertRaises(ValueError):
            get_devtools_active_port(self.port_file)

    def test_get_devtools_active_port_out_of_range(self) -> None:
        self.port_file.write_text("70000\n/browser\n", encoding="utf-8")
        with self.assertRaises(ValueError):
            get_devtools_active_port(self.port_file)

        self.port_file.write_text("0\n/browser\n", encoding="utf-8")
        with self.assertRaises(ValueError):
            get_devtools_active_port(self.port_file)


class TestCDPTargetDiscovery(unittest.TestCase):
    """Tests querying and filtering of CDP targets."""

    @patch("urllib.request.urlopen")
    def test_get_cdp_targets_success(self, mock_urlopen: MagicMock) -> None:
        sample_targets = [
            {"id": "1", "type": "page", "title": "Antigravity", "url": "https://127.0.0.1:37277/"},
            {"id": "2", "type": "worker", "title": "", "url": ""},
        ]
        mock_resp = MagicMock()
        mock_resp.read.return_value = json.dumps(sample_targets).encode("utf-8")
        mock_urlopen.return_value.__enter__.return_value = mock_resp

        targets = get_cdp_targets(46391)
        self.assertEqual(len(targets), 2)
        self.assertEqual(targets[0]["id"], "1")

    @patch("urllib.request.urlopen")
    def test_get_cdp_targets_non_list_response(self, mock_urlopen: MagicMock) -> None:
        mock_resp = MagicMock()
        mock_resp.read.return_value = json.dumps({"error": "not a list"}).encode("utf-8")
        mock_urlopen.return_value.__enter__.return_value = mock_resp

        targets = get_cdp_targets(46391)
        self.assertEqual(targets, [])

    @patch("urllib.request.urlopen")
    def test_get_cdp_targets_connection_error(self, mock_urlopen: MagicMock) -> None:
        mock_urlopen.side_effect = OSError("Connection refused")
        with self.assertRaises(CDPConnectionError):
            get_cdp_targets(46391)

    def test_find_page_target_prefers_antigravity(self) -> None:
        targets = [
            {"id": "1", "type": "worker", "title": ""},
            {"id": "2", "type": "page", "title": "Other Window", "url": "chrome://newtab"},
            {"id": "3", "type": "page", "title": "Project - Antigravity", "url": "https://127.0.0.1:37277/c/123"},
        ]
        page = find_page_target(targets)
        self.assertIsNotNone(page)
        self.assertEqual(page["id"], "3")

    def test_find_page_target_prefers_webview_url(self) -> None:
        targets = [
            {"id": "1", "type": "page", "title": "DevTools", "url": "devtools://devtools/bundled/inspector.html"},
            {"id": "2", "type": "page", "title": "Workspace", "url": "https://127.0.0.1:37277/"},
        ]
        page = find_page_target(targets)
        self.assertIsNotNone(page)
        self.assertEqual(page["id"], "2")

    def test_find_page_target_none_when_empty(self) -> None:
        self.assertIsNone(find_page_target([]))
        self.assertIsNone(find_page_target([{"type": "worker"}]))

    def test_find_page_target_skips_about_blank(self) -> None:
        targets = [
            {"id": "1", "type": "page", "title": "", "url": "about:blank"},
            {"id": "2", "type": "page", "title": "Antigravity Active", "url": "https://127.0.0.1:37277/"},
        ]
        page = find_page_target(targets)
        self.assertIsNotNone(page)
        self.assertEqual(page["id"], "2")

    def test_find_page_target_returns_none_if_only_about_blank(self) -> None:
        targets = [
            {"id": "1", "type": "page", "title": "", "url": "about:blank"},
            {"id": "2", "type": "page", "title": "Blank Tab", "url": "about:blank#demo"},
        ]
        page = find_page_target(targets)
        self.assertIsNone(page)

    def test_find_page_target_skips_data_urls(self) -> None:
        targets = [
            {"id": "1", "type": "page", "title": "", "url": "data:text/html;charset=utf-8,%3Csvg%20class=%22logo%22%3E"},
            {"id": "2", "type": "page", "title": "Antigravity Main", "url": "https://127.0.0.1:37277/"},
        ]
        page = find_page_target(targets)
        self.assertIsNotNone(page)
        self.assertEqual(page["id"], "2")

    def test_find_page_target_prefers_conversation_route_over_root(self) -> None:
        targets = [
            {"id": "1", "type": "page", "title": "Antigravity Splash", "url": "https://127.0.0.1:37277/"},
            {"id": "2", "type": "page", "title": "Project - Antigravity", "url": "https://127.0.0.1:37277/c/test-convo-123"},
        ]
        page = find_page_target(targets)
        self.assertIsNotNone(page)
        self.assertEqual(page["id"], "2")


class TestCDPWebSocketClientFraming(unittest.TestCase):
    """Tests RFC 6455 client framing and JSON-RPC dispatch with mocked sockets."""

    def test_handshake_and_evaluate_success(self) -> None:
        mock_sock = MagicMock()

        # Step 1: Handshake response (Chromium style 101 WebSocket Protocol Handshake)
        handshake_resp = (
            b"HTTP/1.1 101 WebSocket Protocol Handshake\r\n"
            b"Upgrade: WebSocket\r\n"
            b"Connection: Upgrade\r\n"
            b"Sec-WebSocket-Accept: s3pPLMBiTxaQ9kYGzzhZRbK+xOo=\r\n\r\n"
        )

        # Step 2: CDP Runtime.evaluate response frame
        cdp_payload = json.dumps({
            "id": 1,
            "result": {
                "result": {"type": "object", "value": {"success": True}}
            }
        }).encode("utf-8")

        # Construct unmasked server text frame: 0x81, len
        frame_header = bytes([0x81, len(cdp_payload)])
        frame_bytes = frame_header + cdp_payload

        mock_sock.recv.side_effect = [handshake_resp, frame_bytes]

        with patch("socket.create_connection", return_value=mock_sock):
            client = CDPWebSocketClient(timeout=2.0)
            client.connect("ws://127.0.0.1:46391/devtools/page/123")
            res = client.evaluate("1 + 1")
            self.assertEqual(res, {"success": True})

        # Verify sent frame has mask bit set (0x80)
        send_calls = mock_sock.sendall.call_args_list
        self.assertTrue(len(send_calls) >= 2)  # Handshake + evaluate frame
        frame_sent = send_calls[1][0][0]
        self.assertEqual(frame_sent[0], 0x81)
        self.assertTrue(bool(frame_sent[1] & 0x80))

    def test_handshake_accepts_standard_switching_protocols(self) -> None:
        mock_sock = MagicMock()
        handshake_resp = b"HTTP/1.1 101 Switching Protocols\r\nUpgrade: websocket\r\nConnection: Upgrade\r\n\r\n"
        mock_sock.recv.return_value = handshake_resp

        with patch("socket.create_connection", return_value=mock_sock):
            client = CDPWebSocketClient()
            client.connect("ws://127.0.0.1:46391/devtools/page/123")
            self.assertIsNotNone(client.sock)
            client.close()

    def test_handshake_rejects_non_101(self) -> None:
        mock_sock = MagicMock()
        mock_sock.recv.return_value = b"HTTP/1.1 404 Not Found\r\n\r\n"

        with patch("socket.create_connection", return_value=mock_sock):
            client = CDPWebSocketClient()
            with self.assertRaises(CDPConnectionError):
                client.connect("ws://127.0.0.1:46391/devtools/page/123")

    def test_handshake_timeout_raises_exception(self) -> None:
        mock_sock = MagicMock()
        mock_sock.recv.side_effect = socket.timeout("Timed out")

        with patch("socket.create_connection", return_value=mock_sock):
            client = CDPWebSocketClient()
            with self.assertRaises(CDPTimeoutError):
                client.connect("ws://127.0.0.1:46391/devtools/page/123")

    def test_evaluate_cdp_error_raises_exception(self) -> None:
        mock_sock = MagicMock()
        handshake_resp = b"HTTP/1.1 101 Switching Protocols\r\n\r\n"
        error_payload = json.dumps({
            "id": 1,
            "error": {"code": -32000, "message": "Cannot evaluate on closed target"}
        }).encode("utf-8")
        frame_bytes = bytes([0x81, len(error_payload)]) + error_payload
        mock_sock.recv.side_effect = [handshake_resp, frame_bytes]

        with patch("socket.create_connection", return_value=mock_sock):
            client = CDPWebSocketClient()
            client.connect("ws://127.0.0.1:46391/devtools/page/123")
            with self.assertRaises(CDPError):
                client.evaluate("invalid()")

    def test_evaluate_exception_details_raises_exception(self) -> None:
        mock_sock = MagicMock()
        handshake_resp = b"HTTP/1.1 101 Switching Protocols\r\n\r\n"
        exc_payload = json.dumps({
            "id": 1,
            "result": {
                "result": {"type": "undefined"},
                "exceptionDetails": {"text": "ReferenceError: foo is not defined"}
            }
        }).encode("utf-8")
        frame_bytes = bytes([0x81, len(exc_payload)]) + exc_payload
        mock_sock.recv.side_effect = [handshake_resp, frame_bytes]

        with patch("socket.create_connection", return_value=mock_sock):
            client = CDPWebSocketClient()
            client.connect("ws://127.0.0.1:46391/devtools/page/123")
            with self.assertRaises(CDPError) as ctx:
                client.evaluate("foo()")
            self.assertIn("ReferenceError", str(ctx.exception))

    def test_extended_length_framing_16bit(self) -> None:
        mock_sock = MagicMock()
        client = CDPWebSocketClient()
        client.sock = mock_sock

        # Payload length between 126 and 65535
        payload = b"X" * 300
        client.send_frame(0x1, payload)

        call_arg = mock_sock.sendall.call_args[0][0]
        # Byte 0: 0x81
        self.assertEqual(call_arg[0], 0x81)
        # Byte 1: 0x80 | 126 = 254
        self.assertEqual(call_arg[1], 0x80 | 126)
        # Bytes 2-3: 16-bit big endian length
        unpacked_len = struct.unpack(">H", call_arg[2:4])[0]
        self.assertEqual(unpacked_len, 300)

    def test_extended_length_framing_64bit(self) -> None:
        mock_sock = MagicMock()
        client = CDPWebSocketClient()
        client.sock = mock_sock

        # Payload length > 65535
        payload = b"Y" * 70000
        client.send_frame(0x1, payload)

        call_arg = mock_sock.sendall.call_args[0][0]
        # Byte 0: 0x81
        self.assertEqual(call_arg[0], 0x81)
        # Byte 1: 0x80 | 127 = 255
        self.assertEqual(call_arg[1], 0x80 | 127)
        # Bytes 2-9: 64-bit big endian length
        unpacked_len = struct.unpack(">Q", call_arg[2:10])[0]
        self.assertEqual(unpacked_len, 70000)

    def test_recv_server_ping_replies_pong(self) -> None:
        mock_sock = MagicMock()
        client = CDPWebSocketClient()
        client.sock = mock_sock

        # Server sends Ping (0x89, length 4, "ping"), followed by text frame
        ping_frame = bytes([0x89, 4]) + b"ping"
        text_payload = json.dumps({"id": 1, "result": {"result": {"value": 42}}}).encode("utf-8")
        text_frame = bytes([0x81, len(text_payload)]) + text_payload

        mock_sock.recv.side_effect = [ping_frame, text_frame]

        msg = client.recv_message(expected_id=1)
        self.assertEqual(msg["result"]["result"]["value"], 42)

        # Assert Pong was sent (0x8A)
        send_calls = mock_sock.sendall.call_args_list
        pong_frame = send_calls[0][0][0]
        self.assertEqual(pong_frame[0], 0x8A)

    def test_recv_server_close_frame_raises(self) -> None:
        mock_sock = MagicMock()
        client = CDPWebSocketClient()
        client.sock = mock_sock

        close_frame = bytes([0x88, 0])
        mock_sock.recv.return_value = close_frame

        with self.assertRaises(CDPConnectionError):
            client.recv_message()


class _StubCDPClient:
    """Lightweight CDPWebSocketClient double avoiding per-test MagicMock bloat."""

    def __init__(self, evaluate_result: object) -> None:
        self._result = evaluate_result
        self.expressions: list[str] = []
        self.sent_commands: list[tuple[str, dict]] = []

    def evaluate(self, expression: str, *args, **kwargs):
        self.expressions.append(expression)
        return self._result

    def send_command(self, method: str, params: dict, *args, **kwargs) -> dict:
        self.sent_commands.append((method, params))
        return {}


class TestTrajectoryDebugInjection(unittest.TestCase):
    """Tests injecting flags and triggering URL navigation."""

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.brain_dir = Path(self._tmp.name)

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def test_inject_trajectory_debug_success(self) -> None:
        client = _StubCDPClient({
            "success": True,
            "flags": {"enable-trajectory-debug-tools": True, "enable-developer-mode": True},
            "url": "https://127.0.0.1:37277/?trajectoryDebugOpen=true",
        })

        with patch("harness.commands.gui.discover_language_server_endpoint", return_value=None), \
             patch("harness.gui.server.ensure_trajectory_server"):
            res = inject_trajectory_debug(client, brain_dir=self.brain_dir)
        self.assertTrue(res["success"])
        self.assertNotIn("trajectoryDebugOpen=true", res["url"])

    def test_inject_trajectory_debug_failure(self) -> None:
        client = _StubCDPClient({"success": False, "error": "Access denied"})

        with patch("harness.commands.gui.discover_language_server_endpoint", return_value=None), \
             patch("harness.gui.server.ensure_trajectory_server"):
            with self.assertRaises(CDPError):
                inject_trajectory_debug(client, brain_dir=self.brain_dir)

    def test_inject_trajectory_debug_retry_on_unhydrated_origin(self) -> None:
        client = _StubCDPClient({
            "success": False,
            "retry": True,
            "error": "SecurityError: Failed to read the 'localStorage' property from 'Window': Access is denied for this document.",
        })

        with patch("harness.commands.gui.discover_language_server_endpoint", return_value=None), \
             patch("harness.gui.server.ensure_trajectory_server"):
            with self.assertRaises(CDPError) as ctx:
                inject_trajectory_debug(client, brain_dir=self.brain_dir)
        self.assertIn("SecurityError", str(ctx.exception))

    def test_build_hotkey_script_contents(self) -> None:
        script = build_hotkey_script()
        self.assertIn("F12", script)
        self.assertIn("isCtrlShiftT", script)
        self.assertIn("agyis-trajectory-hud", script)
        self.assertIn("Escape", script)
        self.assertIn("keydown", script)
        self.assertIn("__agyis_hud_load_convo", script)
        self.assertIn("location.pathname.match", script)
        self.assertIn("__agyis_hud_hotkey_registered", script)

    def test_inject_trajectory_debug_emits_page_add_script_and_hotkey(self) -> None:
        client = _StubCDPClient({
            "success": True,
            "flags": {"enable-trajectory-debug-tools": True, "enable-developer-mode": True},
            "url": "https://127.0.0.1:37277/?trajectoryDebugOpen=true",
            "open": True,
            "hotkey_registered": True,
        })

        with patch("harness.commands.gui.discover_language_server_endpoint", return_value=None), \
             patch("harness.gui.server.ensure_trajectory_server"):
            res = inject_trajectory_debug(client, toggle=True, brain_dir=self.brain_dir)
        self.assertTrue(res["success"])
        self.assertTrue(res["open"])

        self.assertEqual(len(client.sent_commands), 1)
        method, params = client.sent_commands[0]
        self.assertEqual(method, "Page.addScriptToEvaluateOnNewDocument")
        self.assertIn("source", params)
        self.assertIn("F12", params["source"])
        self.assertIn("agyis-trajectory-hud", params["source"])
        self.assertIn("MutationObserver", params["source"])

    def test_inject_trajectory_debug_toggle_expression(self) -> None:
        client = _StubCDPClient({
            "success": True,
            "flags": {},
            "url": "https://127.0.0.1:37277/?trajectoryDebugOpen=false",
            "open": False,
        })
        with patch("harness.commands.gui.discover_language_server_endpoint", return_value=None), \
             patch("harness.gui.server.ensure_trajectory_server"):
            res = inject_trajectory_debug(client, toggle=True, brain_dir=self.brain_dir)
        self.assertTrue(res["success"])
        self.assertFalse(res["open"])
        expr = client.expressions[-1]
        self.assertIn('"isToggle": true', expr)
        self.assertIn("agyis-trajectory-hud", expr)

    def test_inject_trajectory_debug_open_view_false(self) -> None:
        client = _StubCDPClient({
            "success": True,
            "flags": {"enable-trajectory-debug-tools": True, "enable-developer-mode": True},
            "url": "https://127.0.0.1:37277/",
            "open": False,
            "hotkey_registered": True,
        })
        with patch("harness.commands.gui.discover_language_server_endpoint", return_value=None), \
             patch("harness.gui.server.ensure_trajectory_server"):
            res = inject_trajectory_debug(client, open_view=False, brain_dir=self.brain_dir)
        self.assertTrue(res["success"])
        self.assertFalse(res["open"])
        self.assertEqual(res["url"], "https://127.0.0.1:37277/")
        self.assertTrue(res["hotkey_registered"])

        expr = client.expressions[-1]
        self.assertIn('"shouldOpen": false', expr)
        self.assertIn("agyis-trajectory-hud", expr)
        self.assertEqual(len(client.sent_commands), 1)
        method, params = client.sent_commands[0]
        self.assertEqual(method, "Page.addScriptToEvaluateOnNewDocument")
        self.assertIn("F12", params["source"])

    def test_inject_trajectory_debug_with_explicit_convo_id(self) -> None:
        client = _StubCDPClient({
            "success": True,
            "flags": {"enable-trajectory-debug-tools": True, "enable-developer-mode": True},
            "url": "https://127.0.0.1:37277/",
            "open": True,
            "hotkey_registered": True,
        })
        with patch("harness.commands.gui.discover_language_server_endpoint", return_value=None), \
             patch("harness.gui.server.ensure_trajectory_server"):
            res = inject_trajectory_debug(client, conversation_id="explicit-convo-12345", brain_dir=self.brain_dir)
        self.assertTrue(res["success"])
        self.assertEqual(res["convo_id"], "explicit-convo-12345")
        self.assertIn("https://127.0.0.1:37277/", res["url"])

    @patch("harness.gui.server.ensure_trajectory_server")
    def test_inject_trajectory_debug_auto_spawns_server(self, mock_ensure_server) -> None:
        client = _StubCDPClient({"success": True, "open": True})
        with patch("harness.commands.gui.discover_language_server_endpoint", return_value=None):
            res = inject_trajectory_debug(client, conversation_id="test-spawn-convo", brain_dir=self.brain_dir)
        self.assertTrue(res["success"])
        mock_ensure_server.assert_called_once()

    @patch("subprocess.check_output")
    def test_discover_language_server_endpoint(self, mock_subprocess) -> None:
        mock_subprocess.return_value = "LISTEN 0 10 127.0.0.1:46203 0.0.0.0:* users:((\"language_server\",pid=123,fd=4))\n"
        with patch("urllib.request.urlopen") as mock_urlopen:
            mock_resp = MagicMock()
            mock_resp.__enter__.return_value = mock_resp
            mock_urlopen.return_value = mock_resp
            endpoint = discover_language_server_endpoint()
            self.assertIsNotNone(endpoint)
            self.assertEqual(endpoint["port"], 46203)
            self.assertEqual(endpoint["url"], "https://127.0.0.1:46203")

    @patch("subprocess.check_output")
    def test_discover_language_server_endpoint_prioritizes_https(self, mock_subprocess) -> None:
        # Port 40285 listed first (HTTP only, returns 401), Port 42161 listed second (HTTPS ConnectRPC, returns 200)
        mock_subprocess.return_value = (
            "LISTEN 0 8192 127.0.0.1:40285 0.0.0.0:* users:((\"language_server\",pid=123,fd=1))\n"
            "LISTEN 0 8192 127.0.0.1:42161 0.0.0.0:* users:((\"language_server\",pid=123,fd=2))\n"
        )
        import urllib.error

        def fake_urlopen(req, timeout=0.25, context=None):
            url = req.full_url
            if "https://127.0.0.1:42161" in url:
                mock_resp = MagicMock()
                mock_resp.__enter__.return_value = mock_resp
                return mock_resp
            elif "https://127.0.0.1:40285" in url:
                raise urllib.error.URLError("SSL wrong version number")
            elif "http://127.0.0.1:40285" in url:
                raise urllib.error.HTTPError(url, 401, "Unauthorized", {}, None)
            raise urllib.error.URLError("Connection refused")

        with patch("urllib.request.urlopen", side_effect=fake_urlopen):
            endpoint = discover_language_server_endpoint()
            self.assertIsNotNone(endpoint)
            self.assertEqual(endpoint["port"], 42161)
            self.assertEqual(endpoint["proto"], "https")
            self.assertEqual(endpoint["url"], "https://127.0.0.1:42161")

    @patch("subprocess.check_output")
    def test_discover_language_server_endpoint_empty(self, mock_subprocess) -> None:
        mock_subprocess.side_effect = FileNotFoundError()
        endpoint = discover_language_server_endpoint()
        self.assertIsNone(endpoint)


class TestFormatDevToolsUrls(unittest.TestCase):
    """Tests formatting of DevTools inspection URLs."""

    def test_format_devtools_urls(self) -> None:
        target = {
            "id": "PAGE_UUID",
            "title": "Antigravity Workspace",
            "url": "https://127.0.0.1:37277/",
            "webSocketDebuggerUrl": "ws://127.0.0.1:46391/devtools/page/PAGE_UUID",
            "devtoolsFrontendUrl": "/devtools/inspector.html?ws=127.0.0.1:46391/devtools/page/PAGE_UUID",
        }
        urls = format_devtools_urls(46391, target)
        self.assertEqual(urls["port"], "46391")
        self.assertEqual(urls["target_id"], "PAGE_UUID")
        self.assertIn("127.0.0.1:46391", urls["chrome_inspect_url"])
        self.assertEqual(urls["devtools_frontend_url"], "http://127.0.0.1:46391/devtools/inspector.html?ws=127.0.0.1:46391/devtools/page/PAGE_UUID")
        self.assertIn("devtools://devtools/bundled/inspector.html?ws=127.0.0.1:46391/devtools/page/PAGE_UUID", urls["bundled_inspector_url"])


class TestGuiCommandCLI(unittest.TestCase):
    """Tests CLI argument parsing, execution paths, and output formats for 'agyis gui'."""

    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.port_file = Path(self.temp_dir.name) / "DevToolsActivePort"
        self.port_file.write_text("46391\n/browser\n", encoding="utf-8")

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def test_gui_help_arguments(self) -> None:
        """Verifies 'agyis gui --help' outputs expected flags and exits 0."""
        parser = build_parser()
        with patch("sys.stdout", new_callable=io.StringIO) as mock_out:
            with self.assertRaises(SystemExit) as cm:
                parser.parse_args(["gui", "--help"])
            self.assertEqual(cm.exception.code, 0)
            out = mock_out.getvalue()
            self.assertIn("--devtools", out)
            self.assertIn("--trajectory-debug", out)
            self.assertIn("--toggle", out)
            self.assertIn("--no-popup", out)
            self.assertIn("--wait", out)
            self.assertIn("--port-file", out)
            self.assertIn("--timeout", out)
            self.assertIn("--json", out)

    def test_gui_cli_no_popup_flags(self) -> None:
        """Verifies --no-popup and its aliases --no-open, --setup-only set args.no_popup."""
        parser = build_parser()
        args1 = parser.parse_args(["gui", "--no-popup"])
        self.assertTrue(args1.no_popup)

        args2 = parser.parse_args(["gui", "--no-open"])
        self.assertTrue(args2.no_popup)

        args3 = parser.parse_args(["gui", "--setup-only"])
        self.assertTrue(args3.no_popup)

        args_default = parser.parse_args(["gui"])
        self.assertFalse(args_default.no_popup)

    @patch("harness.commands.gui.get_cdp_targets")
    def test_cmd_gui_devtools_terminal(self, mock_targets: MagicMock) -> None:
        mock_targets.return_value = [
            {
                "id": "PAGE1",
                "type": "page",
                "title": "Antigravity Workspace",
                "url": "https://127.0.0.1:37277/",
                "webSocketDebuggerUrl": "ws://127.0.0.1:46391/devtools/page/PAGE1",
                "devtoolsFrontendUrl": "/devtools/inspector.html?ws=127.0.0.1:46391/devtools/page/PAGE1",
            }
        ]
        args = argparse.Namespace(
            port_file=self.port_file,
            timeout=5.0,
            json=False,
            devtools=True,
            trajectory_debug=False,
        )
        with patch("sys.stdout", new_callable=io.StringIO) as mock_out:
            code = cmd_gui(args)
            self.assertEqual(code, 0)
            out = mock_out.getvalue()
            self.assertIn("46391", out)
            self.assertIn("Antigravity Workspace", out)
            self.assertIn("chrome://inspect/#devices", out)

    @patch("harness.commands.gui.get_cdp_targets")
    def test_cmd_gui_devtools_json(self, mock_targets: MagicMock) -> None:
        mock_targets.return_value = [
            {
                "id": "PAGE1",
                "type": "page",
                "title": "Antigravity Workspace",
                "url": "https://127.0.0.1:37277/",
                "webSocketDebuggerUrl": "ws://127.0.0.1:46391/devtools/page/PAGE1",
                "devtoolsFrontendUrl": "/devtools/inspector.html?ws=127.0.0.1:46391/devtools/page/PAGE1",
            }
        ]
        args = argparse.Namespace(
            port_file=self.port_file,
            timeout=5.0,
            json=True,
            devtools=True,
            trajectory_debug=False,
        )
        with patch("sys.stdout", new_callable=io.StringIO) as mock_out:
            code = cmd_gui(args)
            self.assertEqual(code, 0)
            data = json.loads(mock_out.getvalue())
            self.assertEqual(data["status"], "success")
            self.assertEqual(data["port"], 46391)
            self.assertEqual(data["urls"]["target_id"], "PAGE1")

    @patch("harness.commands.gui.inject_trajectory_debug")
    @patch.object(CDPWebSocketClient, "connect")
    @patch.object(CDPWebSocketClient, "close")
    @patch("harness.commands.gui.get_cdp_targets")
    def test_cmd_gui_trajectory_debug(
        self,
        mock_targets: MagicMock,
        mock_close: MagicMock,
        mock_connect: MagicMock,
        mock_inject: MagicMock,
    ) -> None:
        mock_targets.return_value = [
            {
                "id": "PAGE1",
                "type": "page",
                "title": "Antigravity Workspace",
                "url": "https://127.0.0.1:37277/",
                "webSocketDebuggerUrl": "ws://127.0.0.1:46391/devtools/page/PAGE1",
            }
        ]
        mock_inject.return_value = {"success": True, "url": "https://127.0.0.1:37277/?trajectoryDebugOpen=true"}

        args = argparse.Namespace(
            port_file=self.port_file,
            timeout=5.0,
            json=False,
            devtools=False,
            trajectory_debug=True,
        )
        with patch("sys.stdout", new_callable=io.StringIO) as mock_out:
            code = cmd_gui(args)
            self.assertEqual(code, 0)
            out = mock_out.getvalue()
            self.assertIn("Trajectory Debug View unlocked successfully", out)
            self.assertIn("enable-trajectory-debug-tools", out)

    @patch("harness.commands.gui.inject_trajectory_debug")
    @patch.object(CDPWebSocketClient, "connect")
    @patch.object(CDPWebSocketClient, "close")
    @patch("harness.commands.gui.get_cdp_targets")
    def test_cmd_gui_trajectory_debug_json(
        self,
        mock_targets: MagicMock,
        mock_close: MagicMock,
        mock_connect: MagicMock,
        mock_inject: MagicMock,
    ) -> None:
        mock_targets.return_value = [
            {
                "id": "PAGE1",
                "type": "page",
                "title": "Antigravity Workspace",
                "url": "https://127.0.0.1:37277/",
                "webSocketDebuggerUrl": "ws://127.0.0.1:46391/devtools/page/PAGE1",
            }
        ]
        mock_inject.return_value = {"success": True, "url": "https://127.0.0.1:37277/?trajectoryDebugOpen=true"}

        args = argparse.Namespace(
            port_file=self.port_file,
            timeout=5.0,
            json=True,
            devtools=False,
            trajectory_debug=True,
        )
        with patch("sys.stdout", new_callable=io.StringIO) as mock_out:
            code = cmd_gui(args)
            self.assertEqual(code, 0)
            data = json.loads(mock_out.getvalue())
            self.assertEqual(data["status"], "success")
            self.assertIn("trajectory_debug", data)

    def test_cmd_gui_missing_port_file(self) -> None:
        args = argparse.Namespace(
            port_file=Path("/nonexistent/DevToolsActivePort"),
            timeout=5.0,
            json=False,
            devtools=True,
            trajectory_debug=False,
        )
        with patch("sys.stdout", new_callable=io.StringIO) as mock_out:
            code = cmd_gui(args)
            self.assertEqual(code, 1)
            self.assertIn("Could not resolve Antigravity DevTools port", mock_out.getvalue())

    def test_cmd_gui_missing_port_file_json(self) -> None:
        args = argparse.Namespace(
            port_file=Path("/nonexistent/DevToolsActivePort"),
            timeout=5.0,
            json=True,
            devtools=True,
            trajectory_debug=False,
        )
        with patch("sys.stdout", new_callable=io.StringIO) as mock_out:
            code = cmd_gui(args)
            self.assertEqual(code, 1)
            data = json.loads(mock_out.getvalue())
            self.assertEqual(data["status"], "error")
            self.assertEqual(data["error"], "port_file_not_found")

    @patch("harness.commands.gui.get_cdp_targets")
    def test_cmd_gui_connection_failed(self, mock_targets: MagicMock) -> None:
        mock_targets.side_effect = CDPConnectionError("Connection refused")
        args = argparse.Namespace(
            port_file=self.port_file,
            timeout=5.0,
            json=False,
            devtools=True,
            trajectory_debug=False,
        )
        with patch("sys.stdout", new_callable=io.StringIO) as mock_out:
            code = cmd_gui(args)
            self.assertEqual(code, 1)
            self.assertIn("Failed to connect to CDP endpoint", mock_out.getvalue())
            self.assertIn("stale", mock_out.getvalue())

    @patch("harness.commands.gui.get_cdp_targets")
    def test_cmd_gui_no_page_target(self, mock_targets: MagicMock) -> None:
        mock_targets.return_value = [{"id": "WORKER", "type": "worker"}]
        args = argparse.Namespace(
            port_file=self.port_file,
            timeout=5.0,
            json=False,
            devtools=True,
            trajectory_debug=False,
        )
        with patch("sys.stdout", new_callable=io.StringIO) as mock_out:
            code = cmd_gui(args)
            self.assertEqual(code, 1)
            self.assertIn("No active Antigravity page target found", mock_out.getvalue())

    @patch("harness.commands.gui.inject_trajectory_debug")
    @patch.object(CDPWebSocketClient, "connect")
    @patch.object(CDPWebSocketClient, "close")
    @patch("harness.commands.gui.get_cdp_targets")
    def test_cmd_gui_injection_failed(
        self,
        mock_targets: MagicMock,
        mock_close: MagicMock,
        mock_connect: MagicMock,
        mock_inject: MagicMock,
    ) -> None:
        mock_targets.return_value = [
            {
                "id": "PAGE1",
                "type": "page",
                "title": "Antigravity Workspace",
                "url": "https://127.0.0.1:37277/",
                "webSocketDebuggerUrl": "ws://127.0.0.1:46391/devtools/page/PAGE1",
            }
        ]
        mock_inject.side_effect = CDPError("Evaluation rejected")

        args = argparse.Namespace(
            port_file=self.port_file,
            timeout=5.0,
            json=False,
            devtools=False,
            trajectory_debug=True,
        )
        with patch("sys.stdout", new_callable=io.StringIO) as mock_out:
            code = cmd_gui(args)
            self.assertEqual(code, 1)
            self.assertIn("Failed to inject trajectory debug flags via CDP", mock_out.getvalue())

    @patch("harness.commands.gui.inject_trajectory_debug")
    @patch.object(CDPWebSocketClient, "connect")
    @patch.object(CDPWebSocketClient, "close")
    @patch("harness.commands.gui.get_cdp_targets")
    def test_cmd_gui_bare_default_triggers_trajectory_debug(
        self,
        mock_targets: MagicMock,
        mock_close: MagicMock,
        mock_connect: MagicMock,
        mock_inject: MagicMock,
    ) -> None:
        mock_targets.return_value = [
            {
                "id": "PAGE1",
                "type": "page",
                "title": "Antigravity Workspace",
                "url": "https://127.0.0.1:37277/",
                "webSocketDebuggerUrl": "ws://127.0.0.1:46391/devtools/page/PAGE1",
            }
        ]
        mock_inject.return_value = {
            "success": True,
            "url": "https://127.0.0.1:37277/?trajectoryDebugOpen=true",
            "open": True,
        }
        # Zero action flags provided -> defaults to trajectory debug
        args = argparse.Namespace(
            port_file=self.port_file,
            timeout=5.0,
            wait=0.0,
            json=False,
            devtools=False,
            trajectory_debug=False,
            toggle=False,
        )
        with patch("sys.stdout", new_callable=io.StringIO) as mock_out:
            code = cmd_gui(args)
            self.assertEqual(code, 0)
            mock_inject.assert_called_once_with(unittest.mock.ANY, toggle=False, open_view=True)
            out = mock_out.getvalue()
            self.assertIn("Trajectory Debug View unlocked successfully", out)

    @patch("harness.commands.gui.inject_trajectory_debug")
    @patch.object(CDPWebSocketClient, "connect")
    @patch.object(CDPWebSocketClient, "close")
    @patch("harness.commands.gui.get_cdp_targets")
    def test_cmd_gui_toggle_routing(
        self,
        mock_targets: MagicMock,
        mock_close: MagicMock,
        mock_connect: MagicMock,
        mock_inject: MagicMock,
    ) -> None:
        mock_targets.return_value = [
            {
                "id": "PAGE1",
                "type": "page",
                "title": "Antigravity Workspace",
                "url": "https://127.0.0.1:37277/",
                "webSocketDebuggerUrl": "ws://127.0.0.1:46391/devtools/page/PAGE1",
            }
        ]
        mock_inject.return_value = {
            "success": True,
            "url": "https://127.0.0.1:37277/?trajectoryDebugOpen=false",
            "open": False,
        }
        args = argparse.Namespace(
            port_file=self.port_file,
            timeout=5.0,
            wait=0.0,
            json=False,
            devtools=False,
            trajectory_debug=False,
            toggle=True,
        )
        with patch("sys.stdout", new_callable=io.StringIO) as mock_out:
            code = cmd_gui(args)
            self.assertEqual(code, 0)
            mock_inject.assert_called_once_with(unittest.mock.ANY, toggle=True, open_view=True)
            out = mock_out.getvalue()
            self.assertIn("Trajectory Debug View closed successfully", out)

    @patch("harness.commands.gui.inject_trajectory_debug")
    @patch.object(CDPWebSocketClient, "connect")
    @patch.object(CDPWebSocketClient, "close")
    @patch("harness.commands.gui.get_cdp_targets")
    def test_cmd_gui_no_popup_terminal(
        self,
        mock_targets: MagicMock,
        mock_close: MagicMock,
        mock_connect: MagicMock,
        mock_inject: MagicMock,
    ) -> None:
        mock_targets.return_value = [
            {
                "id": "PAGE1",
                "type": "page",
                "title": "Antigravity Workspace",
                "url": "https://127.0.0.1:37277/",
                "webSocketDebuggerUrl": "ws://127.0.0.1:46391/devtools/page/PAGE1",
            }
        ]
        mock_inject.return_value = {
            "success": True,
            "url": "https://127.0.0.1:37277/",
            "open": False,
            "flags": {"enable-trajectory-debug-tools": True, "enable-developer-mode": True},
            "hotkey_registered": True,
        }

        args = argparse.Namespace(
            port_file=self.port_file,
            timeout=5.0,
            wait=0.0,
            json=False,
            devtools=False,
            trajectory_debug=False,
            toggle=False,
            no_popup=True,
        )
        with patch("sys.stdout", new_callable=io.StringIO) as mock_out:
            code = cmd_gui(args)
            self.assertEqual(code, 0)
            mock_inject.assert_called_once_with(unittest.mock.ANY, toggle=False, open_view=False)
            out = mock_out.getvalue()
            self.assertIn("In-Situ Trajectory Debug HUD shortcuts primed successfully (modal popup suppressed)", out)
            self.assertIn("Best-effort flags written: 'enable-trajectory-debug-tools', 'enable-developer-mode'", out)
            self.assertNotIn("Developer: Trajectory Debug View", out)
            self.assertIn("F12", out)

    @patch("harness.commands.gui.inject_trajectory_debug")
    @patch.object(CDPWebSocketClient, "connect")
    @patch.object(CDPWebSocketClient, "close")
    @patch("harness.commands.gui.get_cdp_targets")
    def test_cmd_gui_no_popup_json(
        self,
        mock_targets: MagicMock,
        mock_close: MagicMock,
        mock_connect: MagicMock,
        mock_inject: MagicMock,
    ) -> None:
        mock_targets.return_value = [
            {
                "id": "PAGE1",
                "type": "page",
                "title": "Antigravity Workspace",
                "url": "https://127.0.0.1:37277/",
                "webSocketDebuggerUrl": "ws://127.0.0.1:46391/devtools/page/PAGE1",
            }
        ]
        mock_inject.return_value = {
            "success": True,
            "url": "https://127.0.0.1:37277/",
            "open": False,
            "flags": {"enable-trajectory-debug-tools": True, "enable-developer-mode": True},
            "hotkey_registered": True,
        }

        args = argparse.Namespace(
            port_file=self.port_file,
            timeout=5.0,
            wait=0.0,
            json=True,
            devtools=False,
            trajectory_debug=False,
            toggle=False,
            no_popup=True,
        )
        with patch("sys.stdout", new_callable=io.StringIO) as mock_out:
            code = cmd_gui(args)
            self.assertEqual(code, 0)
            mock_inject.assert_called_once_with(unittest.mock.ANY, toggle=False, open_view=False)
            data = json.loads(mock_out.getvalue())
            self.assertEqual(data["status"], "success")
            self.assertEqual(data["trajectory_debug"]["open"], False)
            self.assertEqual(data["trajectory_debug"]["url"], "https://127.0.0.1:37277/")

    @patch("time.sleep")
    @patch("harness.commands.gui.inject_trajectory_debug")
    @patch.object(CDPWebSocketClient, "connect")
    @patch.object(CDPWebSocketClient, "close")
    @patch("harness.commands.gui.get_cdp_targets")
    @patch("harness.commands.gui.get_devtools_active_port")
    def test_cmd_gui_wait_polling_success(
        self,
        mock_get_port: MagicMock,
        mock_targets: MagicMock,
        mock_close: MagicMock,
        mock_connect: MagicMock,
        mock_inject: MagicMock,
        mock_sleep: MagicMock,
    ) -> None:
        # Simulate port file not ready on first call, then ready on second call
        mock_get_port.side_effect = [
            FileNotFoundError("DevToolsActivePort not found"),
            (46391, "/browser/path"),
        ]
        mock_targets.return_value = [
            {
                "id": "PAGE1",
                "type": "page",
                "title": "Antigravity Workspace",
                "url": "https://127.0.0.1:37277/",
                "webSocketDebuggerUrl": "ws://127.0.0.1:46391/devtools/page/PAGE1",
            }
        ]
        mock_inject.return_value = {
            "success": True,
            "url": "https://127.0.0.1:37277/?trajectoryDebugOpen=true",
            "open": True,
        }
        args = argparse.Namespace(
            port_file=self.port_file,
            timeout=5.0,
            wait=2.0,
            json=False,
            devtools=False,
            trajectory_debug=False,
            toggle=False,
        )
        with patch("sys.stdout", new_callable=io.StringIO) as mock_out:
            code = cmd_gui(args)
            self.assertEqual(code, 0)
            self.assertEqual(mock_get_port.call_count, 2)

    @patch("time.sleep")
    @patch("time.time")
    @patch("harness.commands.gui.get_devtools_active_port")
    def test_cmd_gui_wait_polling_timeout(
        self,
        mock_get_port: MagicMock,
        mock_time: MagicMock,
        mock_sleep: MagicMock,
    ) -> None:
        # Mock time.time: start time = 100.0, loop check = 105.0 (> 100.0 + 2.0)
        mock_time.side_effect = [100.0, 105.0]
        mock_get_port.side_effect = FileNotFoundError("DevToolsActivePort not found")

        args = argparse.Namespace(
            port_file=self.port_file,
            timeout=5.0,
            wait=2.0,
            json=False,
            devtools=False,
            trajectory_debug=False,
            toggle=False,
        )
        with patch("sys.stdout", new_callable=io.StringIO) as mock_out:
            code = cmd_gui(args)
            self.assertEqual(code, 1)
            self.assertIn("Could not resolve Antigravity DevTools port", mock_out.getvalue())

    @patch("time.sleep")
    @patch("harness.commands.gui.inject_trajectory_debug")
    @patch.object(CDPWebSocketClient, "connect")
    @patch.object(CDPWebSocketClient, "close")
    @patch("harness.commands.gui.get_cdp_targets")
    def test_cmd_gui_wait_skips_about_blank_until_active(
        self,
        mock_targets: MagicMock,
        mock_close: MagicMock,
        mock_connect: MagicMock,
        mock_inject: MagicMock,
        mock_sleep: MagicMock,
    ) -> None:
        # First poll: only about:blank target. Second poll: active 127.0.0.1 target.
        mock_targets.side_effect = [
            [{"id": "BLANK", "type": "page", "title": "", "url": "about:blank"}],
            [{
                "id": "APP",
                "type": "page",
                "title": "Antigravity Active",
                "url": "https://127.0.0.1:37277/",
                "webSocketDebuggerUrl": "ws://127.0.0.1:46391/devtools/page/APP",
            }],
        ]
        mock_inject.return_value = {
            "success": True,
            "url": "https://127.0.0.1:37277/?trajectoryDebugOpen=true",
            "open": True,
        }
        args = argparse.Namespace(
            port_file=self.port_file,
            timeout=5.0,
            wait=3.0,
            json=False,
            devtools=False,
            trajectory_debug=False,
            toggle=False,
        )
        with patch("sys.stdout", new_callable=io.StringIO) as mock_out:
            code = cmd_gui(args)
            self.assertEqual(code, 0)
            self.assertEqual(mock_targets.call_count, 2)
            out = mock_out.getvalue()
            self.assertIn("Trajectory Debug View unlocked successfully", out)

    @patch("time.sleep")
    @patch("harness.commands.gui.inject_trajectory_debug")
    @patch.object(CDPWebSocketClient, "connect")
    @patch.object(CDPWebSocketClient, "close")
    @patch("harness.commands.gui.get_cdp_targets")
    def test_cmd_gui_wait_skips_empty_title_splash_until_hydrated(
        self,
        mock_targets: MagicMock,
        mock_close: MagicMock,
        mock_connect: MagicMock,
        mock_inject: MagicMock,
        mock_sleep: MagicMock,
    ) -> None:
        # First poll: empty title splash target. Second poll: hydrated Antigravity window.
        mock_targets.side_effect = [
            [{
                "id": "SPLASH",
                "type": "page",
                "title": "",
                "url": "https://127.0.0.1:37277/",
                "webSocketDebuggerUrl": "ws://127.0.0.1:46391/devtools/page/SPLASH",
            }],
            [{
                "id": "WORKSPACE",
                "type": "page",
                "title": "Project - Antigravity",
                "url": "https://127.0.0.1:37277/c/test-session-42",
                "webSocketDebuggerUrl": "ws://127.0.0.1:46391/devtools/page/WORKSPACE",
            }],
        ]
        mock_inject.return_value = {
            "success": True,
            "url": "https://127.0.0.1:37277/c/test-session-42?trajectoryDebugOpen=true",
            "open": True,
        }
        args = argparse.Namespace(
            port_file=self.port_file,
            timeout=5.0,
            wait=5.0,
            json=False,
            devtools=False,
            trajectory_debug=False,
            toggle=False,
        )
        with patch("sys.stdout", new_callable=io.StringIO) as mock_out:
            code = cmd_gui(args)
            self.assertEqual(code, 0)
            self.assertEqual(mock_targets.call_count, 2)
            out = mock_out.getvalue()
            self.assertIn("Trajectory Debug View unlocked successfully", out)

    @patch("time.sleep")
    @patch("harness.commands.gui.inject_trajectory_debug")
    @patch.object(CDPWebSocketClient, "connect")
    @patch.object(CDPWebSocketClient, "close")
    @patch("harness.commands.gui.get_cdp_targets")
    def test_cmd_gui_wait_retries_through_security_error_until_success(
        self,
        mock_targets: MagicMock,
        mock_close: MagicMock,
        mock_connect: MagicMock,
        mock_inject: MagicMock,
        mock_sleep: MagicMock,
    ) -> None:
        mock_targets.return_value = [{
            "id": "PAGE1",
            "type": "page",
            "title": "Antigravity",
            "url": "https://127.0.0.1:37277/",
            "webSocketDebuggerUrl": "ws://127.0.0.1:46391/devtools/page/PAGE1",
        }]
        # Fails twice with SecurityError / unhydrated origin, succeeds on 3rd attempt
        mock_inject.side_effect = [
            CDPError("Failed to inject trajectory debug flags: SecurityError: Access is denied"),
            CDPError("Failed to inject trajectory debug flags: SecurityError: Access is denied"),
            {
                "success": True,
                "url": "https://127.0.0.1:37277/?trajectoryDebugOpen=true",
                "open": True,
            },
        ]
        args = argparse.Namespace(
            port_file=self.port_file,
            timeout=5.0,
            wait=5.0,
            json=False,
            devtools=False,
            trajectory_debug=True,
            toggle=False,
            verbose=True,
        )
        with patch("sys.stdout", new_callable=io.StringIO) as mock_out, \
             patch("sys.stderr", new_callable=io.StringIO) as mock_err:
            code = cmd_gui(args)
            self.assertEqual(code, 0)
            self.assertEqual(mock_inject.call_count, 3)
            self.assertEqual(mock_sleep.call_count, 2)
            mock_sleep.assert_called_with(0.5)
            self.assertIn("Trajectory Debug View unlocked successfully", mock_out.getvalue())
            self.assertIn("Retrying after injection error", mock_err.getvalue())

    @patch("time.sleep")
    @patch("time.time")
    @patch("harness.commands.gui.inject_trajectory_debug")
    @patch.object(CDPWebSocketClient, "connect")
    @patch.object(CDPWebSocketClient, "close")
    @patch("harness.commands.gui.get_cdp_targets")
    def test_cmd_gui_wait_injection_failure_timeout(
        self,
        mock_targets: MagicMock,
        mock_close: MagicMock,
        mock_connect: MagicMock,
        mock_inject: MagicMock,
        mock_time: MagicMock,
        mock_sleep: MagicMock,
    ) -> None:
        mock_targets.return_value = [{
            "id": "PAGE1",
            "type": "page",
            "title": "Antigravity",
            "url": "https://127.0.0.1:37277/",
            "webSocketDebuggerUrl": "ws://127.0.0.1:46391/devtools/page/PAGE1",
        }]
        mock_inject.side_effect = CDPError("SecurityError: Access is denied")
        # Time progression: start=100.0 (deadline=102.0), retry check 1=100.5, loop check 2=101.0, retry check 2=103.0 (>=102.0)
        mock_time.side_effect = [100.0, 100.5, 101.0, 103.0]

        args = argparse.Namespace(
            port_file=self.port_file,
            timeout=5.0,
            wait=2.0,
            json=False,
            devtools=False,
            trajectory_debug=True,
            toggle=False,
        )
        with patch("sys.stdout", new_callable=io.StringIO) as mock_out:
            code = cmd_gui(args)
            self.assertEqual(code, 1)
            self.assertEqual(mock_inject.call_count, 2)
            self.assertEqual(mock_sleep.call_count, 1)
            mock_sleep.assert_called_with(0.5)
            self.assertIn("Failed to inject trajectory debug flags via CDP", mock_out.getvalue())
            self.assertIn("SecurityError", mock_out.getvalue())

    @patch("time.sleep")
    @patch("time.time")
    @patch("harness.commands.gui.inject_trajectory_debug")
    @patch.object(CDPWebSocketClient, "connect")
    @patch.object(CDPWebSocketClient, "close")
    @patch("harness.commands.gui.get_cdp_targets")
    def test_cmd_gui_wait_injection_failure_timeout_json(
        self,
        mock_targets: MagicMock,
        mock_close: MagicMock,
        mock_connect: MagicMock,
        mock_inject: MagicMock,
        mock_time: MagicMock,
        mock_sleep: MagicMock,
    ) -> None:
        mock_targets.return_value = [{
            "id": "PAGE1",
            "type": "page",
            "title": "Antigravity",
            "url": "https://127.0.0.1:37277/",
            "webSocketDebuggerUrl": "ws://127.0.0.1:46391/devtools/page/PAGE1",
        }]
        mock_inject.side_effect = CDPError("SecurityError: Access is denied")
        mock_time.side_effect = [100.0, 105.0]

        args = argparse.Namespace(
            port_file=self.port_file,
            timeout=5.0,
            wait=2.0,
            json=True,
            devtools=False,
            trajectory_debug=True,
            toggle=False,
        )
        with patch("sys.stdout", new_callable=io.StringIO) as mock_out:
            code = cmd_gui(args)
            self.assertEqual(code, 1)
            data = json.loads(mock_out.getvalue())
            self.assertEqual(data["status"], "error")
            self.assertEqual(data["error"], "injection_failed")
            self.assertIn("SecurityError", data["message"])


_Tok = tuple[str, str]
_GLOBAL_TARGETS = frozenset({("IDENT", t) for t in ("window", "global", "globalThis", "self")})
_MEMBER_OPS, _NON_REGEX_OPS = frozenset({("OP", "."), ("OP", "?.")}), frozenset({")", "]", "++", "--"})
_NEST_OPEN, _NEST_CLOSE = frozenset({("OP", "("), ("OP", "["), ("OP", "{")}), frozenset({("OP", ")"), ("OP", "]"), ("OP", "}")})
_SHORT_IDENT_RE = re.compile(r"^[A-Za-z_$][A-Za-z0-9_$]{0,3}$")
_REGEX_WORDS = frozenset({"return", "throw", "case", "typeof", "void", "delete", "await", "yield", "in", "of", "instanceof", "new", "else", "do"})
_TMPL_CHUNK_RE = re.compile(r"(?:\\[\s\S]|\$(?!\{)|[^`\\$])*")
_REGEX_RE = re.compile(r"/(?![/*])(?:\\.|\[(?:\\.|[^\]\\])*\]|[^/\\\[\n])+/[A-Za-z]*")
_TOKEN_RE = re.compile(
    r"(?P<WS>(?:\s|//[^\n]*|/\*(?:[\s\S]*?\*/|[\s\S]*))+)|(?P<STR>'(?:\\[\s\S]|[^'\\])*'|\"(?:\\[\s\S]|[^\"\\])*\")"
    r"|(?P<NUM>(?:0[xXbBoO][0-9A-Fa-f_]+|\d[\d_]*(?:\.[\d_]*)?(?:[eE][+-]?\d+)?|\.\d[\d_]*)n?)|(?P<IDENT>[A-Za-z_$][A-Za-z0-9_$]*)"
    r"|(?P<OP>===|!==|>>>=|>>>|<<=|>>=|\*\*=|&&=|\|\|=|\?\?=|\.\.\.|\?\.(?!\d)|=>|==|!=|<=|>=|&&|\|\||\?\?|\+\+|--|\*\*|<<|>>|[+\-*/%&|^]=|[()\[\]{}.,:;?~!+\-*/%<>=&|^])"
)


def _advance_special(src: str, idx: int, depth: int, stack: list[int], regex_ok: bool) -> tuple[_Tok | None, int, int, bool] | None:
    """Scan a JS template boundary/resumption or regex literal at idx."""
    ch = src[idx]
    if ch == "`" or (ch == "}" and stack[-1:] == [depth - 1]):
        if ch == "}":
            stack.pop()
            depth -= 1
        m = _TMPL_CHUNK_RE.match(src, idx + 1)
        if src.startswith("${", m.end()):
            stack.append(depth)
            return ("STRING", m.group()), m.end() + 2, depth + 1, True
        return ("STRING", m.group()), min(len(src), m.end() + 1), depth, False
    if regex_ok and ch == "/" and (m := _REGEX_RE.match(src, idx)):
        return None, m.end(), depth, False
    return None


def _emit_token(m: re.Match[str], depth: int, regex_ok: bool, tokens: list[_Tok]) -> tuple[_Tok | None, int, bool]:
    """Convert a _TOKEN_RE match to an optional (kind, text) token and updated state."""
    kind, text = m.lastgroup, m.group()
    if kind in {"WS", "NUM"}:
        return None, depth, (regex_ok if kind == "WS" else False)
    if kind == "STR":
        return ("STRING", text[1:-1]), depth, False
    if kind == "IDENT":
        return ("IDENT", text), depth, text in _REGEX_WORDS and (not tokens or tokens[-1] not in _MEMBER_OPS)
    return ("OP", text), max(0, depth + (text == "{") - (text == "}")), text not in _NON_REGEX_OPS


def _tokenize_js(src: str) -> list[_Tok]:
    """Tokenize JS in a single shallow pass into (kind, text) for IDENT, STRING, and OP."""
    tokens, stack, idx, n, depth, regex_ok = [], [], 0, len(src), 0, True
    while idx < n:
        if special := _advance_special(src, idx, depth, stack, regex_ok):
            tok, idx, depth, regex_ok = special
        elif m := _TOKEN_RE.match(src, idx):
            tok, depth, regex_ok = _emit_token(m, depth, regex_ok, tokens)
            idx = m.end()
        else:
            tok, idx = None, idx + 1
        if tok is not None:
            tokens.append(tok)
    return tokens


def _extract_object_keys(tokens: list[_Tok], idx: int) -> tuple[list[str], int]:
    """Extract top-level property keys from a '{ ... }' span starting after '{'."""
    keys, n, depth, at_key = [], len(tokens), 0, True
    while idx < n:
        tok = tokens[idx]
        if depth == 0:
            if tok == ("OP", "}"):
                return keys, idx + 1
            if at_key:
                nxt = tuple(tokens[idx + 1 : idx + 2])
                if (tok[0] == "IDENT" and nxt in {(("OP", ":"),), (("OP", ","),), (("OP", "}"),), (("OP", "("),)}) or (tok[0] == "STRING" and nxt == (("OP", ":"),)):
                    keys.append(tok[1])
                at_key = False
            else:
                at_key = tok == ("OP", ",")
        depth += (tok in _NEST_OPEN) - (tok in _NEST_CLOSE)
        idx += 1
    return keys, idx


def _scan_object_assign_args(tokens: list[_Tok], idx: int) -> list[str]:
    """Collect <=4-char top-level object literal keys passed to Object.assign."""
    found, n, depth, at_arg = [], len(tokens), 0, True
    while idx < n:
        tok = tokens[idx]
        if depth == 0:
            if tok == ("OP", ")"):
                break
            if at_arg and tok == ("OP", "{"):
                keys, idx = _extract_object_keys(tokens, idx + 1)
                found.extend(f"Object.assign:{k}" for k in keys if _SHORT_IDENT_RE.match(k))
                at_arg = False
                continue
            at_arg = tok == ("OP", ",")
        depth += (tok in _NEST_OPEN) - (tok in _NEST_CLOSE)
        idx += 1
    return found


def _match_target_export(span: list[_Tok]) -> str | None:
    """Match 'target.short =' or 'target[\"short\"] =' at start of token span."""
    if len(span) >= 4 and (span[1], span[3]) == (("OP", "."), ("OP", "=")):
        return f"dot:{span[2][1]}" if span[2][0] == "IDENT" and len(span[2][1]) <= 4 else None
    if len(span) >= 5 and (span[1], *span[3:5]) == (("OP", "["), ("OP", "]"), ("OP", "=")):
        return f"bracket:{span[2][1]}" if span[2][0] == "STRING" and _SHORT_IDENT_RE.match(span[2][1]) else None
    return None


def _match_object_export(tokens: list[_Tok], i: int) -> list[str]:
    """Match Object.defineProperty(target, 'short', ...) and Object.assign(target, ...)."""
    span = tokens[i : i + 7]
    if len(span) < 7 or span[:2] != [("IDENT", "Object"), ("OP", ".")] or span[4] not in _GLOBAL_TARGETS or (span[3], span[5]) != (("OP", "("), ("OP", ",")):
        return []
    if (span[2], span[6][0]) == (("IDENT", "defineProperty"), "STRING") and _SHORT_IDENT_RE.match(span[6][1]):
        return [f"defineProperty:{span[6][1]}"]
    return _scan_object_assign_args(tokens, i + 6) if span[2] == ("IDENT", "assign") else []


def _find_short_global_exports(source: str) -> list[str]:
    """Detect <=4-char global exports via dot, bracket, Object.defineProperty, or Object.assign."""
    tokens, offenders = _tokenize_js(source), []
    for i, tok in enumerate(tokens):
        if i > 0 and tokens[i - 1] in _MEMBER_OPS:
            continue
        if tok in _GLOBAL_TARGETS and (hit := _match_target_export(tokens[i : i + 5])):
            offenders.append(hit)
        elif tok == ("IDENT", "Object"):
            offenders.extend(_match_object_export(tokens, i))
    return offenders


class TestTrajectoryHUDDataModel(unittest.TestCase):
    """Tests data modeling, timing metrics extraction, and subagent pre-bundling."""

    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.brain_dir = Path(self.temp_dir.name)

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def test_subagent_prebundling_and_parent_traversal(self) -> None:
        parent_id = "parent-1111-2222-3333-444444444444"
        child_id = "child-aaaa-bbbb-cccc-dddddddddddd"

        parent_dir = self.brain_dir / parent_id
        parent_logs = parent_dir / ".system_generated" / "logs"
        parent_logs.mkdir(parents=True, exist_ok=True)

        child_dir = self.brain_dir / child_id
        child_logs = child_dir / ".system_generated" / "logs"
        child_logs.mkdir(parents=True, exist_ok=True)

        # Parent transcript invokes child
        parent_transcript = parent_logs / "transcript.jsonl"
        parent_steps = [
            {"source": "user", "content": "Start task"},
            {
                "source": "model",
                "thinking": "Invoking specialist subagent...",
                "tool_calls": [{
                    "name": "invoke_subagent",
                    "args": {"agent_role": "builder", "objective": "Build feature"},
                    "output": f"Spawned child conversationId: {child_id}",
                }],
            },
        ]
        with open(parent_transcript, "w", encoding="utf-8") as f:
            for s in parent_steps:
                f.write(json.dumps(s) + "\n")

        # Child transcript has steps
        child_transcript = child_logs / "transcript.jsonl"
        child_steps = [
            {"source": "user", "content": f"Execute child task for {parent_id}"},
            {
                "source": "model",
                "content": "Child execution complete",
                "thinking": "Analyzing codebase...",
                "tool_calls": [{"name": "run_command", "args": {"CommandLine": "ls"}}],
            },
        ]
        with open(child_transcript, "w", encoding="utf-8") as f:
            for s in child_steps:
                f.write(json.dumps(s) + "\n")

        # Load parent trajectory
        parent_data = load_conversation_trajectory(parent_id, brain_dir=self.brain_dir)
        self.assertEqual(parent_data["conversation_id"], parent_id)
        self.assertIn(child_id, parent_data["subagents"])
        self.assertIn(child_id, parent_data["subagent_trajectories"])

        # Child trajectory pre-bundled in-memory
        child_prebundled = parent_data["subagent_trajectories"][child_id]
        self.assertEqual(child_prebundled["conversation_id"], child_id)
        self.assertEqual(len(child_prebundled["steps"]), 2)

        # Load child trajectory directly and check parent traversal
        child_data = load_conversation_trajectory(child_id, brain_dir=self.brain_dir)
        self.assertEqual(child_data["parent_id"], parent_id)

    def test_step_timing_metrics_and_cortex_types(self) -> None:
        convo_id = "test-timing-1234"
        convo_dir = self.brain_dir / convo_id / ".system_generated" / "logs"
        convo_dir.mkdir(parents=True, exist_ok=True)
        transcript = convo_dir / "transcript.jsonl"

        steps = [
            {"source": "user", "content": "Please implement feature"},
            {"source": "model", "thinking": "Thinking deeply about architecture...", "content": "Here is the plan"},
            {"source": "model", "tool_calls": [{"name": "run_command", "args": {"CommandLine": "pytest"}}]},
            {"source": "model", "tool_calls": [{"name": "view_file", "args": {"AbsolutePath": "/file.py"}}]},
            {"source": "model", "tool_calls": [{"name": "replace_file_content", "args": {"TargetFile": "/file.py"}}]},
        ]
        with open(transcript, "w", encoding="utf-8") as f:
            for s in steps:
                f.write(json.dumps(s) + "\n")

        data = load_conversation_trajectory(convo_id, brain_dir=self.brain_dir)
        enriched = data["steps"]
        self.assertEqual(len(enriched), 5)

        # Assert Cortex type mapping
        self.assertEqual(enriched[0]["type"], "USER_INPUT")
        self.assertEqual(enriched[1]["type"], "PLANNER_RESPONSE")
        self.assertEqual(enriched[2]["type"], "RUN_COMMAND")
        self.assertEqual(enriched[3]["type"], "VIEW_FILE")
        self.assertEqual(enriched[4]["type"], "REPLACE_FILE_CONTENT")

        # Assert timing and size metrics
        for s in enriched:
            self.assertIn("thinking_duration_ms", s)
            self.assertIn("streaming_duration_ms", s)
            self.assertIn("total_duration_ms", s)
            self.assertIn("size_bytes", s)
            self.assertTrue(s["size_bytes"] > 0)

        # Honest telemetry: without duration fields or timestamps, thinking_duration_ms stays 0
        self.assertEqual(enriched[1]["thinking_duration_ms"], 0)
        self.assertEqual(enriched[1]["streaming_duration_ms"], 0)

    def test_step_timing_computed_from_explicit_durations_and_timestamps(self) -> None:
        convo_id = "test-timing-explicit"
        convo_dir = self.brain_dir / convo_id / ".system_generated" / "logs"
        convo_dir.mkdir(parents=True, exist_ok=True)
        transcript = convo_dir / "transcript.jsonl"
        steps = [
            {
                "source": "model",
                "thinking": "Reasoning...",
                "content": "Done",
                "thinkingDuration": {"seconds": 1, "nanos": 250000000},
                "streamingDuration": {"seconds": 0, "nanos": 500000000},
            },
            {
                "source": "model",
                "content": "Timestamped",
                "createdAt": "2026-11-24T10:00:00.000Z",
                "viewableAt": "2026-11-24T10:00:00.400Z",
                "completedAt": "2026-11-24T10:00:01.000Z",
            },
        ]
        with open(transcript, "w", encoding="utf-8") as f:
            for s in steps:
                f.write(json.dumps(s) + "\n")

        enriched = load_conversation_trajectory(convo_id, brain_dir=self.brain_dir)["steps"]
        self.assertEqual(enriched[0]["thinking_duration_ms"], 1250)
        self.assertEqual(enriched[0]["streaming_duration_ms"], 500)
        self.assertEqual(enriched[0]["total_duration_ms"], 1750)
        self.assertEqual(enriched[1]["thinking_duration_ms"], 400)
        self.assertEqual(enriched[1]["streaming_duration_ms"], 600)
        self.assertEqual(enriched[1]["total_duration_ms"], 1000)

    def test_context_window_token_breakdown(self) -> None:
        convo_id = "test-tokens-5678"
        convo_dir = self.brain_dir / convo_id / ".system_generated" / "logs"
        convo_dir.mkdir(parents=True, exist_ok=True)
        transcript = convo_dir / "transcript.jsonl"

        steps = [
            {"source": "user", "content": "Hello", "input_tokens": 1500, "output_tokens": 200},
            {"source": "model", "content": "Response", "input_tokens": 2500, "output_tokens": 300},
        ]
        with open(transcript, "w", encoding="utf-8") as f:
            for s in steps:
                f.write(json.dumps(s) + "\n")

        data = load_conversation_trajectory(convo_id, brain_dir=self.brain_dir)
        breakdown = data["token_breakdown"]
        self.assertIn("system_prompt", breakdown)
        self.assertIn("tool_defs", breakdown)
        self.assertIn("checkpoint", breakdown)
        self.assertIn("user", breakdown)
        self.assertIn("model", breakdown)
        self.assertIn("tool", breakdown)
        self.assertIn("system", breakdown)

    def test_build_trajectory_hud_script_generation(self) -> None:
        script = build_trajectory_hud_script(
            convo_id="convo-abc",
            trajectory_data={"conversation_id": "convo-abc", "steps": []},
            conversations=[{"id": "convo-abc", "mtime": 1700000000}],
            open_view=True,
            toggle=False,
        )
        self.assertIn("agyis-trajectory-hud", script)
        self.assertIn("convo-abc", script)
        self.assertIn("Side-by-Side", script)
        self.assertIn("Stacked", script)
        self.assertIn("context-cell-selected", script)
        self.assertIn("EXEC", script)
        self.assertIn("INV", script)
        self.assertIn("SIZE", script)
        self.assertIn("existingHud.remove()", script)
        self.assertIn("window.__agyis_hud_load_convo", script)
        self.assertIn("agyis-refresh-btn", script)
        # Verify Activity mode packed horizontal lanes
        self.assertIn("agyis-timeline-lane-row", script)
        self.assertIn("Model &amp; Thinking", script.replace("&", "&amp;"))
        self.assertIn("Terminal Execution", script)
        self.assertIn("Files &amp; Code", script.replace("&", "&amp;"))

        # Verify dynamic connectRpcPort and connectRpcUrl injection
        script_with_port = build_trajectory_hud_script(
            convo_id="convo-abc",
            trajectory_data={"conversation_id": "convo-abc", "steps": []},
            conversations=[],
            open_view=True,
            connect_rpc_port=46203,
            connect_rpc_url="https://127.0.0.1:46203",
        )
        self.assertIn('"connectRpcPort": 46203', script_with_port)
        self.assertIn('"connectRpcUrl": "https://127.0.0.1:46203"', script_with_port)
        self.assertIn("agyis-tl-zoom-in", script)
        self.assertIn("agyis-tl-zoom-out", script)
        self.assertIn("agyis-layout-side", script)
        self.assertIn("agyis-layout-stack", script)
        self.assertIn("agyis-subagent-item", script)

    def test_default_256k_context_capacity(self) -> None:
        convo_id = "test-256k-cap"
        convo_dir = self.brain_dir / convo_id / ".system_generated" / "logs"
        convo_dir.mkdir(parents=True, exist_ok=True)
        transcript = convo_dir / "transcript.jsonl"
        transcript.write_text(json.dumps({"source": "user", "content": "hi"}) + "\n", encoding="utf-8")

        # Default 256k
        data = load_conversation_trajectory(convo_id, brain_dir=self.brain_dir)
        self.assertEqual(data["max_context_tokens"], 256000)

        # Explicit in transcript
        convo_meta_id = "test-meta-cap"
        meta_dir = self.brain_dir / convo_meta_id / ".system_generated" / "logs"
        meta_dir.mkdir(parents=True, exist_ok=True)
        meta_transcript = meta_dir / "transcript.jsonl"
        meta_transcript.write_text(
            json.dumps({
                "source": "system",
                "chatStartMetadata": {"contextWindowMetadata": {"maxContextTokens": 1000000}},
            }) + "\n",
            encoding="utf-8",
        )
        data_meta = load_conversation_trajectory(convo_meta_id, brain_dir=self.brain_dir)
        self.assertEqual(data_meta["max_context_tokens"], 1000000)

    def test_character_token_estimation_ratio(self) -> None:
        self.assertEqual(estimate_tokens(35), 10)
        self.assertEqual(estimate_tokens(7), 2)
        self.assertEqual(estimate_tokens(0), 0)

        convo_id = "test-token-est"
        convo_dir = self.brain_dir / convo_id / ".system_generated" / "logs"
        convo_dir.mkdir(parents=True, exist_ok=True)
        transcript = convo_dir / "transcript.jsonl"
        text_70 = "a" * 70
        transcript.write_text(json.dumps({"source": "user", "content": text_70}) + "\n", encoding="utf-8")
        data = load_conversation_trajectory(convo_id, brain_dir=self.brain_dir)
        self.assertEqual(data["steps"][0]["tokens"], 20)

    def test_compaction_summary_extraction_and_checkpoint_accounting(self) -> None:
        convo_id = "test-compaction"
        convo_dir = self.brain_dir / convo_id / ".system_generated" / "logs"
        convo_dir.mkdir(parents=True, exist_ok=True)
        transcript = convo_dir / "transcript.jsonl"
        steps = [
            {"source": "user", "content": "Initial prompt"},
            {
                "source": "system",
                "content": "<CONTEXT_SUMMARY>Compacted memory state from prior turns</CONTEXT_SUMMARY>",
                "input_tokens": 500,
                "output_tokens": 100,
            },
        ]
        with open(transcript, "w", encoding="utf-8") as f:
            for s in steps:
                f.write(json.dumps(s) + "\n")

        data = load_conversation_trajectory(convo_id, brain_dir=self.brain_dir)
        self.assertEqual(data["steps"][1]["type"], "CHECKPOINT")
        self.assertEqual(data["steps"][1]["compaction_summary"], "Compacted memory state from prior turns")
        self.assertGreater(data["token_breakdown"]["checkpoint"], 0)

    def test_cleanroom_atc_sizing_math(self) -> None:
        # 1. Minimum segment clamp (xtc)
        w = xtc_segment_width(segment_tokens=1, px_per_token=0.001, min_segment_px=2.0)
        self.assertEqual(w, 2.0)

        # 2. Layout pass metrics (ytc)
        segments = [
            {"id": "sys", "tokens": 1000},
            {"id": "user", "tokens": 500},
            {"id": "step-1", "tokens": 10},
        ]
        metrics = ytc_layout_pass(segments, capacity_tokens=10000, container_width=1000.0, min_segment_px=2.0)
        self.assertAlmostEqual(metrics["px_per_token"], 0.1)
        self.assertGreater(metrics["capacity_px"], 0)

        # 3. Dynamic multi-row layout (Atc)
        layout = atc_context_layout(segments, capacity_tokens=10000, container_width=1000.0, min_segment_px=2.0)
        self.assertIn("rows", layout)
        self.assertGreater(len(layout["rows"]), 0)
        first_row = layout["rows"][0]
        self.assertTrue(any(c["segment"] is None for c in first_row))
        for cell in first_row:
            self.assertGreaterEqual(cell["start_fraction"], 0.0)
            self.assertLessEqual(cell["start_fraction"] + cell["width_fraction"], 1.0001)

    def test_build_trajectory_hud_script_2_26_0_parity(self) -> None:
        script = build_trajectory_hud_script(
            convo_id="convo-abc",
            trajectory_data={"conversation_id": "convo-abc", "steps": []},
            conversations=[{"id": "convo-abc", "mtime": 1700000000}],
            open_view=True,
            toggle=False,
        )
        self.assertIn("Context Window", script)
        self.assertIn("Timeline", script)
        self.assertIn("256000", script)
        self.assertIn("Unused capacity:", script)
        self.assertIn("scrollIntoView", script)
        self.assertIn("function Atc", script)

    def test_cumulative_context_token_accounting(self) -> None:
        convo_id = "test-cumulative-tokens"
        convo_dir = self.brain_dir / convo_id / ".system_generated" / "logs"
        convo_dir.mkdir(parents=True, exist_ok=True)
        transcript = convo_dir / "transcript.jsonl"
        steps = [
            {"source": "user", "content": "Question 1", "tokens": 1200},
            {"source": "model", "content": "Answer 1", "tokens": 3000},
            {"source": "model", "type": "TOOL_CALL", "tool_calls": [{"name": "run_command"}], "tokens": 1500},
            {"source": "system", "content": "<summary>Compact</summary>", "type": "CHECKPOINT", "tokens": 2000},
            {"source": "user", "content": "Question 2", "output_tokens": 500},  # delta only
        ]
        with open(transcript, "w", encoding="utf-8") as f:
            for s in steps:
                f.write(json.dumps(s) + "\n")

        data = load_conversation_trajectory(convo_id, brain_dir=self.brain_dir)
        total_tokens = data["total_tokens"]
        breakdown = data["token_breakdown"]

        # Active checkpoint window post-checkpoint only (excludes pre-checkpoint 1200+3000+1500 steps)
        self.assertEqual(total_tokens, 2500)
        self.assertEqual(sum(breakdown.values()), total_tokens)
        self.assertEqual(breakdown["checkpoint"], 2000)
        self.assertEqual(breakdown["user"], 500)
        self.assertEqual(breakdown["tool"], 0)
        self.assertEqual(breakdown["system_prompt"], 0)
        self.assertEqual(breakdown["tool_defs"], 0)
        self.assertEqual(breakdown["unattributed"], 0)

    def test_hud_css_titlebar_offset_and_no_drag(self) -> None:
        script = build_trajectory_hud_script(
            convo_id="convo-hud-fix",
            trajectory_data={"conversation_id": "convo-hud-fix", "steps": []},
            conversations=[],
            open_view=True,
            toggle=False,
        )
        # Titlebar clipping fix assertions
        self.assertIn("top: var(--pane-titlebar-height, 40px);", script)
        self.assertIn("height: calc(100vh - var(--pane-titlebar-height, 40px)) !important;", script)
        self.assertIn("-webkit-app-region: no-drag;", script)
        # Cumulative token sync in JS
        self.assertIn("rawSegmentsSum = segments.reduce", script)
        self.assertIn("activeTokensSum = selectedCheckpointTotal > 0 ? selectedCheckpointTotal : rawSegmentsSum", script)

    def test_hud_assets_do_not_clobber_minified_globals(self) -> None:
        """Regression: HUD injection must never export short Closure-minified globals (e.g. xtc/ytc/ztc/Atc)."""
        assets_dir = importlib.resources.files("harness.gui.assets")
        js_entries = sorted(
            (entry for entry in assets_dir.iterdir() if entry.name.endswith(".js")),
            key=lambda entry: entry.name,
        )
        self.assertGreaterEqual(len(js_entries), 13)

        offenders = []
        for entry in js_entries:
            for finding in _find_short_global_exports(entry.read_text(encoding="utf-8")):
                offenders.append(f"{entry.name}: {finding}")

        self.assertEqual(
            offenders,
            [],
            f"HUD JS assets must not export <=4-char globals that can collide with Antigravity minified code: {offenders}",
        )

        script = build_trajectory_hud_script(
            convo_id="convo-no-clobber",
            trajectory_data={"conversation_id": "convo-no-clobber", "steps": []},
            conversations=[],
            open_view=False,
            toggle=False,
        )
        compiled_offenders = _find_short_global_exports(script)
        self.assertEqual(
            compiled_offenders,
            [],
            f"Compiled HUD script must not export <=4-char globals: {compiled_offenders}",
        )

    def test_short_global_export_scanner_edge_cases(self) -> None:
        """Verify _find_short_global_exports handles strings/templates/regexes/members and catches exports."""
        cases = [
            ("string_dot", 'const s = "window.xtc = 1";', []),
            ("string_assign", "const s = 'Object.assign(global, { xtc: 1 })';", []),
            ("template_static", "const t = `global.xtc = 1`;", []),
            ("regex_literal", "const r = /window.xtc=1/;", []),
            ("member_chain_dot", "obj.global.xtc = 1;", []),
            ("member_chain_bracket", 'foo.self["xtc"] = 1;', []),
            ("equality_check", "if (window.xtc == 1 || window.ytc === 2) {}", []),
            ("value_shorthand_fp", "Object.assign(window, { longName: xtc });", []),
            ("spaced_dot", "window . xtc = 1;", ["dot:xtc"]),
            ("newline_dot", "window\n  .xtc = 1;", ["dot:xtc"]),
            ("assign_after_void_regex", "Object.assign(window, void /)/, { xtc: 1 });", ["Object.assign:xtc"]),
            ("assign_shorthand", "Object.assign(global, { xtc });", ["Object.assign:xtc"]),
            ("bracket_assign", 'window["xtc"] = 1;', ["bracket:xtc"]),
            ("define_property", 'Object.defineProperty(globalThis, "Atc", { value: 1 });', ["defineProperty:Atc"]),
            ("template_interp_export", "const t = `${window.xtc = 1}`;", ["dot:xtc"]),
        ]
        for label, snippet, expected in cases:
            with self.subTest(case=label):
                self.assertEqual(_find_short_global_exports(snippet), expected)

    def test_hud_script_vm_preserves_minified_globals(self) -> None:
        """Black-box Node VM verification that executing compiled HUD script preserves xtc/ytc/ztc/Atc."""
        if (node_bin := shutil.which("node")) is None:
            self.skipTest("node binary not found; skipping Node VM runtime verification")
        trajectory = {
            "conversation_id": "convo-vm-no-clobber", "model": "claude-sonnet-4", "total_tokens": 12500, "max_context_tokens": 200000,
            "steps": [{"step_index": 0, "type": "USER_INPUT", "content": "Hello", "tokens": 500}, {"step_index": 1, "type": "PLANNER_RESPONSE", "content": "World", "tokens": 2000}],
            "checkpoints": [{"checkpoint_index": 0, "start_index": 0, "end_index": 1, "step_count": 2, "total_tokens": 12500}],
            "system_prompt_slices": [{"name": "identity", "tag": "identity", "tokens": 4000}],
            "tool_def_slices": [{"name": "run_command", "tokens": 6000}],
        }
        script = build_trajectory_hud_script(
            convo_id="convo-vm-no-clobber", trajectory_data=trajectory,
            conversations=[{"conversation_id": "convo-vm-no-clobber", "summary": "VM Test", "step_count": 2}], open_view=True, toggle=False,
        )
        node_vm_harness = r"""
const fs = require("fs"), vm = require("vm");
const noop = () => {}, empty = () => [], nil = () => null, byId = new Map();
const makeEl = (tag) => ({
    tagName: String(tag || "div").toUpperCase(), id: "", className: "", textContent: "", _html: "",
    get innerHTML() { return this._html; }, set innerHTML(v) { this._html = String(v ?? ""); },
    value: "", style: {}, children: [], parentNode: null, clientWidth: 1000, clientHeight: 700, dataset: {},
    classList: { add: noop, remove: noop, toggle: noop, contains: () => false },
    setAttribute: noop, getAttribute: nil, removeAttribute: noop, querySelector: nil, querySelectorAll: empty,
    addEventListener: noop, removeEventListener: noop, focus: noop, setSelectionRange: noop, scrollIntoView: noop,
    contains(o) { return o === this || this.children.includes(o); },
    appendChild(c) { if (c) { c.parentNode = this; this.children.push(c); if (c.id) byId.set(c.id, c); } return c; },
    removeChild(c) { const i = this.children.indexOf(c); if (i !== -1) this.children.splice(i, 1); if (c && c.id && byId.get(c.id) === c) byId.delete(c.id); return c; },
    remove() { if (this.id && byId.get(this.id) === this) byId.delete(this.id); },
});
const document = { head: makeEl("head"), body: makeEl("body"), activeElement: null, getElementById: (id) => byId.get(id) || null, createElement: makeEl, querySelector: nil, querySelectorAll: empty, addEventListener: noop, removeEventListener: noop };
const sentinels = { xtc() { return "x"; }, ytc() { return "y"; }, ztc() { return "z"; }, Atc() { return "A"; } }, consoleErrors = [];
const sandbox = {
    document, innerWidth: 1280, innerHeight: 800, addEventListener: noop, removeEventListener: noop, dispatchEvent: () => true,
    location: { hostname: "127.0.0.1", protocol: "http:", origin: "http://127.0.0.1:40624", pathname: "/", search: "" },
    history: { pushState: noop, replaceState: noop }, localStorage: { getItem: nil, setItem: noop, removeItem: noop },
    navigator: { clipboard: { writeText: async () => {} } }, CSS: { escape: String }, URLSearchParams, AbortController, TextEncoder, TextDecoder,
    Event: typeof Event !== "undefined" ? Event : function Event(t) { this.type = t; }, crypto: globalThis.crypto,
    MutationObserver: class { observe() {} disconnect() {} }, requestAnimationFrame: () => 1, cancelAnimationFrame: noop,
    fetch: async () => ({ ok: false, status: 503, json: async () => null }),
    console: { log: noop, warn: noop, error: (...a) => consoleErrors.push(a.map(String).join(" ")) },
    __AGYIS_SENTINELS__: sentinels, ...sentinels,
};
sandbox.window = sandbox.global = sandbox.globalThis = sandbox.self = sandbox;
vm.createContext(sandbox);
const preShort = new Set(vm.runInContext("Object.getOwnPropertyNames(globalThis)", sandbox).filter((k) => k.length <= 4));
const runResult = vm.runInContext(fs.readFileSync(0, "utf8"), sandbox);
const addedShortGlobals = vm.runInContext("Object.getOwnPropertyNames(globalThis)", sandbox).filter((k) => k.length <= 4 && !preShort.has(k));
const vmState = vm.runInContext(`(() => {
    const names = ["xtc", "ytc", "ztc", "Atc"], targets = [window, global, globalThis, self], ns = globalThis.__agyis_context_bar;
    return {
        sentinelsIntact: names.every((n) => targets.every((t) => t[n] === __AGYIS_SENTINELS__[n])),
        nsExportsCallable: Boolean(ns && typeof ns === "object" && names.every((n) => typeof ns[n] === "function" && ns[n] !== __AGYIS_SENTINELS__[n])),
        atcSample: ns ? ns.Atc([{ id: "s1", tokens: 100 }], 1000, 500) : null,
        hudGlobalsOk: typeof globalThis.renderContextBar === "function" && typeof globalThis.extractGranularSegments === "function" && typeof globalThis.bindContextBarEvents === "function",
    };
})()`, sandbox);
const hud = document.getElementById("agyis-trajectory-hud");
console.log(JSON.stringify({ success: Boolean(runResult && runResult.success), consoleErrors, addedShortGlobals, mounted: Boolean(hud && hud.innerHTML.includes("agyis-context-bar")), ...vmState }));
"""
        proc = subprocess.run([node_bin, "-e", node_vm_harness], input=script, capture_output=True, text=True, timeout=5, check=True)
        observed = json.loads(proc.stdout.strip())
        self.assertTrue(observed["success"])
        self.assertEqual(observed["consoleErrors"], [])
        self.assertTrue(observed["mounted"])
        self.assertTrue(observed["sentinelsIntact"])
        self.assertEqual(observed["addedShortGlobals"], [])
        self.assertTrue(observed["nsExportsCallable"])
        self.assertTrue(observed["hudGlobalsOk"])
        self.assertEqual(observed["atcSample"]["rowCount"], 1)
        self.assertEqual(observed["atcSample"]["pxPerToken"], 0.5)
        self.assertAlmostEqual(observed["atcSample"]["rows"][0][0]["widthFraction"], 0.1)
        self.assertEqual(observed["atcSample"]["rows"][0][0]["sliceTokens"], 100)


class TestGUISystemdService(unittest.TestCase):
    """Tests systemd user path and service management for 'agyis gui --service'."""

    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.unit_dir = Path(self.temp_dir.name) / "systemd" / "user"

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def test_generate_gui_systemd_units_content(self) -> None:
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("XDG_CONFIG_HOME", None)
            path_unit = generate_gui_systemd_path_unit()
        self.assertIn("PathChanged=%h/.config/Antigravity/DevToolsActivePort", path_unit)
        self.assertIn("Unit=antigravity-trajectory.service", path_unit)

        with patch.dict(os.environ, {"XDG_CONFIG_HOME": "/tmp/custom-xdg"}, clear=False):
            xdg_path_unit = generate_gui_systemd_path_unit()
        self.assertIn("PathChanged=/tmp/custom-xdg/Antigravity/DevToolsActivePort", xdg_path_unit)

        service_unit = generate_gui_systemd_service_unit()
        self.assertIn("MemoryMax=500M", service_unit)
        self.assertIn("MemoryHigh=300M", service_unit)
        self.assertIn("gui --no-popup --wait 15.0", service_unit)

    @patch("harness.commands.gui._run_gui_systemctl")
    def test_handle_gui_service_lifecycle(self, mock_systemctl: MagicMock) -> None:
        mock_systemctl.return_value = MagicMock(returncode=0, stdout="active", stderr="")

        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            # 1. Install
            code = handle_gui_service_command(action="install", unit_dir=self.unit_dir)
            self.assertEqual(code, 0)
            path_file = self.unit_dir / "antigravity-trajectory.path"
            service_file = self.unit_dir / "antigravity-trajectory.service"
            self.assertTrue(path_file.exists())
            self.assertTrue(service_file.exists())

            # 2. Status
            code_status = handle_gui_service_command(action="status", unit_dir=self.unit_dir)
            self.assertEqual(code_status, 0)

            # 3. Start
            code_start = handle_gui_service_command(action="start", unit_dir=self.unit_dir)
            self.assertEqual(code_start, 0)

            # 4. Stop
            code_stop = handle_gui_service_command(action="stop", unit_dir=self.unit_dir)
            self.assertEqual(code_stop, 0)

            # 5. Uninstall
            code_uninstall = handle_gui_service_command(action="uninstall", unit_dir=self.unit_dir)
            self.assertEqual(code_uninstall, 0)
            self.assertFalse(path_file.exists())
            self.assertFalse(service_file.exists())

    def test_handle_gui_service_status_when_not_installed(self) -> None:
        empty_dir = Path(self.temp_dir.name) / "empty"
        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            code = handle_gui_service_command(action="status", unit_dir=empty_dir)
        self.assertEqual(code, 1)

    @patch("harness.commands.gui._run_gui_systemctl")
    def test_handle_gui_service_fails_when_systemctl_fails(self, mock_systemctl: MagicMock) -> None:
        mock_systemctl.return_value = MagicMock(returncode=1, stdout="", stderr="Access denied")
        # Install should fail and return 1 when systemctl fails
        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            code = handle_gui_service_command(action="install", unit_dir=self.unit_dir)
        self.assertEqual(code, 1)

    @patch("shutil.which")
    def test_handle_gui_service_fails_when_systemctl_missing(self, mock_which: MagicMock) -> None:
        mock_which.return_value = None
        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            code = handle_gui_service_command(action="install", unit_dir=self.unit_dir)
        self.assertEqual(code, 1)

    def test_cli_parser_gui_service_option(self) -> None:
        parser = build_parser()
        args = parser.parse_args(["gui", "--service", "install"])
        self.assertEqual(args.service, "install")

        args_status = parser.parse_args(["gui", "--service", "status"])
        self.assertEqual(args_status.service, "status")


class TestCheckpointPartitioning(unittest.TestCase):
    """Tests disjoint Option B trajectory partitioning into checkpoint windows (ADR-014 / PSL-INV-007)."""

    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.brain_dir = Path(self.temp_dir.name)

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def _create_convo_transcript(self, convo_id: str, steps: list[dict]) -> None:
        log_dir = self.brain_dir / convo_id / ".system_generated" / "logs"
        log_dir.mkdir(parents=True, exist_ok=True)
        t_file = log_dir / "transcript.jsonl"
        with open(t_file, "w", encoding="utf-8") as f:
            for s in steps:
                f.write(json.dumps(s) + "\n")

    def test_checkpoint_partitioning_no_checkpoints(self) -> None:
        convo_id = "convo-no-cp"
        steps = [{"source": "user", "content": f"msg {i}"} for i in range(5)]
        self._create_convo_transcript(convo_id, steps)

        data = load_conversation_trajectory(convo_id, brain_dir=self.brain_dir)
        checkpoints = data.get("checkpoints", [])
        self.assertEqual(len(checkpoints), 1)
        self.assertEqual(checkpoints[0]["checkpoint_index"], 0)
        self.assertEqual(checkpoints[0]["start_index"], 0)
        self.assertEqual(checkpoints[0]["end_index"], 4)
        self.assertEqual(checkpoints[0]["step_count"], 5)
        self.assertFalse(checkpoints[0]["has_checkpoint"])
        self.assertEqual(checkpoints[0]["summary"], "Initial Trajectory")
        self.assertEqual(data["checkpoint_index"], 0)
        self.assertEqual(data["checkpoint_steps"], 5)

    def test_checkpoint_partitioning_single_checkpoint(self) -> None:
        convo_id = "convo-single-cp"
        steps = []
        for i in range(10):
            if i == 4:
                steps.append({"type": "CHECKPOINT", "compaction_summary": "Compacted at 4"})
            else:
                steps.append({"source": "model", "content": f"Step {i}"})
        self._create_convo_transcript(convo_id, steps)

        data = load_conversation_trajectory(convo_id, brain_dir=self.brain_dir)
        checkpoints = data.get("checkpoints", [])
        self.assertEqual(len(checkpoints), 2)

        # Window 0: steps 0..3 (disjoint pre-checkpoint Initial Trajectory)
        self.assertEqual(checkpoints[0]["checkpoint_index"], 0)
        self.assertEqual(checkpoints[0]["start_index"], 0)
        self.assertEqual(checkpoints[0]["end_index"], 3)
        self.assertEqual(checkpoints[0]["step_count"], 4)
        self.assertFalse(checkpoints[0]["has_checkpoint"])
        self.assertEqual(checkpoints[0]["summary"], "Initial Trajectory")

        # Window 1: steps 4..9 (checkpoint c0..N-1)
        self.assertEqual(checkpoints[1]["checkpoint_index"], 1)
        self.assertEqual(checkpoints[1]["start_index"], 4)
        self.assertEqual(checkpoints[1]["end_index"], 9)
        self.assertEqual(checkpoints[1]["step_count"], 6)
        self.assertTrue(checkpoints[1]["has_checkpoint"])
        self.assertEqual(checkpoints[1]["summary"], "Compacted at 4")
        self.assertEqual(data["checkpoint_index"], 1)
        self.assertEqual(data["checkpoint_steps"], 6)

    def test_checkpoint_partitioning_multiple_checkpoints(self) -> None:
        convo_id = "convo-multi-cp"
        steps = []
        for i in range(12):
            if i == 3:
                steps.append({"type": "CHECKPOINT", "compaction_summary": "First summary"})
            elif i == 7:
                steps.append({"type": "CHECKPOINT", "compaction_summary": "Second summary"})
            else:
                steps.append({"source": "model", "content": f"Step {i}"})
        self._create_convo_transcript(convo_id, steps)

        data = load_conversation_trajectory(convo_id, brain_dir=self.brain_dir)
        checkpoints = data.get("checkpoints", [])
        self.assertEqual(len(checkpoints), 3)

        self.assertEqual((checkpoints[0]["start_index"], checkpoints[0]["end_index"]), (0, 2))
        self.assertEqual(checkpoints[0]["step_count"], 3)
        self.assertFalse(checkpoints[0]["has_checkpoint"])
        self.assertEqual(checkpoints[0]["summary"], "Initial Trajectory")

        self.assertEqual((checkpoints[1]["start_index"], checkpoints[1]["end_index"]), (3, 6))
        self.assertEqual(checkpoints[1]["step_count"], 4)
        self.assertTrue(checkpoints[1]["has_checkpoint"])
        self.assertEqual(checkpoints[1]["summary"], "First summary")

        self.assertEqual((checkpoints[2]["start_index"], checkpoints[2]["end_index"]), (7, 11))
        self.assertEqual(checkpoints[2]["step_count"], 5)
        self.assertTrue(checkpoints[2]["has_checkpoint"])
        self.assertEqual(checkpoints[2]["summary"], "Second summary")

    def test_checkpoint_partitioning_first_step_checkpoint(self) -> None:
        convo_id = "convo-first-cp"
        steps = [
            {"type": "CHECKPOINT", "compaction_summary": "Compacted at start"},
            {"source": "user", "content": "msg 1"},
            {"source": "model", "content": "reply 2"},
        ]
        self._create_convo_transcript(convo_id, steps)

        data = load_conversation_trajectory(convo_id, brain_dir=self.brain_dir)
        checkpoints = data.get("checkpoints", [])
        self.assertEqual(len(checkpoints), 1)
        self.assertEqual((checkpoints[0]["start_index"], checkpoints[0]["end_index"]), (0, 2))
        self.assertEqual(checkpoints[0]["step_count"], 3)
        self.assertTrue(checkpoints[0]["has_checkpoint"])
        self.assertEqual(checkpoints[0]["summary"], "Compacted at start")
        self.assertEqual(data["checkpoint_index"], 0)

    def test_checkpoint_partitioning_last_step_checkpoint(self) -> None:
        convo_id = "convo-last-cp"
        steps = []
        for i in range(5):
            if i == 4:
                steps.append({"type": "CHECKPOINT", "compaction_summary": "Summary at end"})
            else:
                steps.append({"source": "user", "content": f"msg {i}"})
        self._create_convo_transcript(convo_id, steps)

        data = load_conversation_trajectory(convo_id, brain_dir=self.brain_dir)
        checkpoints = data.get("checkpoints", [])
        self.assertEqual(len(checkpoints), 2)
        self.assertEqual((checkpoints[0]["start_index"], checkpoints[0]["end_index"]), (0, 3))
        self.assertEqual(checkpoints[0]["step_count"], 4)
        self.assertFalse(checkpoints[0]["has_checkpoint"])
        self.assertEqual((checkpoints[1]["start_index"], checkpoints[1]["end_index"]), (4, 4))
        self.assertEqual(checkpoints[1]["step_count"], 1)
        self.assertTrue(checkpoints[1]["has_checkpoint"])
        self.assertEqual(checkpoints[1]["summary"], "Summary at end")
        self.assertEqual(data["checkpoint_index"], 1)

    def test_checkpoint_partitioning_empty(self) -> None:
        convo_id = "convo-empty"
        self._create_convo_transcript(convo_id, [])

        data = load_conversation_trajectory(convo_id, brain_dir=self.brain_dir)
        self.assertEqual(data.get("checkpoints", []), [])
        self.assertEqual(data["checkpoint_index"], 0)


class TestDynamic4RowContextBarAndPrettifiedInspector(unittest.TestCase):
    """Tests dynamic 4-row 64k context bar and upgraded markdown inspector in HUD script."""

    def test_hud_script_contains_dynamic_4_row_logic(self) -> None:
        sample_data = {
            "conversation_id": "test-4row",
            "steps": [
                {"step_index": 0, "type": "USER_INPUT", "tokens": 4000, "content": "Hello"},
                {"step_index": 1, "type": "MODEL_OUTPUT", "tokens": 12000, "content": "World"},
            ],
            "max_context_tokens": 256000,
            "checkpoints": [
                {"checkpoint_index": 0, "start_index": 0, "end_index": 1, "step_count": 2, "has_checkpoint": False, "summary": "Initial"}
            ],
        }
        script = build_trajectory_hud_script(
            convo_id="test-4row",
            trajectory_data=sample_data,
            conversations=[],
            open_view=True,
            toggle=False,
        )

        # 4-row dynamic calculation & capacity definitions
        self.assertIn("ROW_CAPACITY = Math.max(64000, Math.ceil(maxTokens / 4))", script)
        self.assertIn("Math.min(4, Math.max(1, Math.ceil(activeTokensSum / ROW_CAPACITY)))", script)
        self.assertIn("agyis-context-row-wrap", script)
        self.assertIn("agyis-context-row-label", script)
        self.assertIn("agyis-context-row-track", script)
        self.assertIn("Math.round((rIdx * ROW_CAPACITY) / 1000)", script)

    def test_hud_script_contains_checkpoint_switcher(self) -> None:
        sample_data = {"conversation_id": "test-cp", "steps": []}
        script = build_trajectory_hud_script("test-cp", sample_data, [], open_view=True)

        self.assertIn("agyis-checkpoint-prev", script)
        self.assertIn("agyis-checkpoint-next", script)
        self.assertIn("Prev Checkpoint", script)
        self.assertIn("Next Checkpoint", script)

    def test_hud_script_contains_pagination_and_debouncing(self) -> None:
        sample_data = {"conversation_id": "test-page", "steps": []}
        script = build_trajectory_hud_script("test-page", sample_data, [], open_view=True)

        self.assertIn("pageSize = 50", script)
        self.assertIn("agyis-page-prev", script)
        self.assertIn("agyis-page-next", script)
        self.assertIn("agyis-page-jump-selected", script)
        self.assertIn("searchDebounceTimer", script)
        self.assertIn("setTimeout", script)
        self.assertIn("150", script)

    def test_hud_script_contains_sync_to_latest_state(self) -> None:
        """BUILD-TOGGLE-LATEST-CHECKPOINT-STEP-PAGE-001: Assert syncToLatestState exists and is called across entrypoints."""
        sample_data = {
            "conversation_id": "test-sync-latest",
            "steps": [{"step_index": i, "type": "USER_PROMPT"} for i in range(105)],
            "checkpoints": [
                {"checkpoint_index": 0, "start_index": 0, "end_index": 49},
                {"checkpoint_index": 1, "start_index": 50, "end_index": 99},
                {"checkpoint_index": 2, "start_index": 100, "end_index": 104},
            ],
        }
        script = build_trajectory_hud_script("test-sync-latest", sample_data, [], open_view=True, toggle=True)

        # 1. Assert helper function is defined
        self.assertIn("function syncToLatestState(state)", script)
        self.assertIn("state.activeCheckpointIndex = checkpoints.length > 0 ? checkpoints.length - 1 : -1;", script)
        self.assertIn("state.selectedIndex = Math.max(0, steps.length - 1);", script)
        self.assertIn("const totalPages = Math.max(1, Math.ceil(totalSteps / pageSize));", script)
        self.assertIn("state.tablePage = totalPages - 1;", script)

        # 2. Assert toggle branch calls syncToLatestState
        self.assertIn("if (existingHud && isToggle)", script)
        self.assertIn("syncToLatestState(state);", script)
        self.assertIn("if (typeof renderHud === \"function\") renderHud();", script)

        # 3. Assert initial state initialization sets latest checkpoint, step, and table page and syncs
        self.assertIn("window.__agyis_hud_state = {", script)
        self.assertIn("activeCheckpointIndex: checkpoints.length > 0 ? checkpoints.length - 1 : -1,", script)
        self.assertIn("tablePage: Math.max(0, Math.ceil(steps.length / 50) - 1),", script)
        self.assertIn("syncToLatestState(window.__agyis_hud_state);", script)

        # 4. Assert __agyis_hud_load_convo calls syncToLatestState(state)
        self.assertIn("window.__agyis_hud_load_convo", script)
        self.assertIn("syncToLatestState(state);", script)

        # 5. Assert hotkey listener syncs to latest state
        self.assertIn("window.__agyis_hud_active_listener", script)

        # 6. Assert scrollIntoView on selected step element and display timing
        self.assertIn("selEl.scrollIntoView({ block: \"nearest\" })", script)
        # Verify display timing: display flex is set before scrollIntoView
        display_pos = script.find('existingHud.style.display = isHidden ? "flex" : "none";')
        scroll_pos = script.find('selEl.scrollIntoView({ block: "nearest" });')
        self.assertTrue(display_pos != -1 and scroll_pos != -1 and display_pos < scroll_pos)

    def test_sync_to_latest_state_node_evaluation(self) -> None:
        """BUILD-TOGGLE-LATEST-CHECKPOINT-STEP-PAGE-001: Execute real hud_utils.js syncToLatestState in node."""
        import subprocess

        utils_js = importlib.resources.files("harness.gui.assets").joinpath("hud_utils.js").read_text(encoding="utf-8")
        js_harness = (
            "global.window = {};\n"
            + utils_js
            + """
        const cases = [
            { currentData: { steps: [], checkpoints: [] } },
            { currentData: { steps: new Array(30).fill({}), checkpoints: [{ checkpoint_index: 0 }] } },
            { currentData: { steps: new Array(50).fill({}), checkpoints: [{ checkpoint_index: 0 }] } },
            { currentData: { steps: new Array(51).fill({}), checkpoints: [{ checkpoint_index: 0 }, { checkpoint_index: 1 }] } },
            { currentData: { steps: new Array(220).fill({}), checkpoints: [{ checkpoint_index: 0 }, { checkpoint_index: 1 }, { checkpoint_index: 2 }] } }
        ];

        const results = cases.map(st => {
            window.__agyis_utils.syncToLatestState(st);
            return {
                activeCheckpointIndex: st.activeCheckpointIndex,
                selectedIndex: st.selectedIndex,
                tablePage: st.tablePage,
                timelinePage: st.timelinePage
            };
        });

        console.log(JSON.stringify(results));
        """
        )
        try:
            res = subprocess.run(["node", "-e", js_harness], capture_output=True, text=True, check=True)
            results = json.loads(res.stdout.strip())
            self.assertEqual(results[0], {"activeCheckpointIndex": -1, "selectedIndex": 0, "tablePage": 0, "timelinePage": 0})
            self.assertEqual(results[1], {"activeCheckpointIndex": 0, "selectedIndex": 29, "tablePage": 0, "timelinePage": 0})
            self.assertEqual(results[2], {"activeCheckpointIndex": 0, "selectedIndex": 49, "tablePage": 0, "timelinePage": 0})
            self.assertEqual(results[3], {"activeCheckpointIndex": 1, "selectedIndex": 50, "tablePage": 1, "timelinePage": 0})
            self.assertEqual(results[4], {"activeCheckpointIndex": 2, "selectedIndex": 219, "tablePage": 4, "timelinePage": 1})
        except FileNotFoundError:
            pass

    def test_hud_script_contains_prettified_inspector_features(self) -> None:
        sample_data = {"conversation_id": "test-insp", "steps": []}
        script = build_trajectory_hud_script("test-insp", sample_data, [], open_view=True)

        # Thought Process disclosure block
        self.assertIn("Thought Process", script)
        self.assertIn("agyis-thinking-block", script)
        # XML Callouts
        self.assertIn("agyis-xml-callout", script)
        self.assertIn("USER_REQUEST", script)
        self.assertIn("CONTEXT_SUMMARY", script)
        self.assertIn("SYSTEM_MESSAGE", script)
        # GitHub Alerts
        self.assertIn("agyis-github-alert", script)
        self.assertIn("NOTE", script)
        self.assertIn("WARNING", script)
        # Code Copy Buttons & JSON parsing
        self.assertIn("agyis-copy-code-btn", script)
        self.assertIn("JSON.parse", script)

    def test_hud_script_cleanroom_parity_features(self) -> None:
        sample_data = {
            "conversation_id": "test-parity",
            "steps": [
                {
                    "step_index": 0,
                    "type": "RUN_COMMAND",
                    "command": "python3 test.py",
                    "exitCode": 0,
                    "output": "PASS",
                },
                {
                    "step_index": 1,
                    "type": "CHECKPOINT",
                    "sessionSummary": "Compacted 10k tokens",
                    "cacheReadTokens": 10000,
                    "checkpointInputTokens": 2000,
                },
            ],
            "system_prompt_slices": [
                {"name": "Identity", "tokens": 400, "color": "#6366f1"},
                {"name": "Guidelines", "tokens": 300, "color": "#e879f9"},
            ],
            "tool_def_slices": [
                {"name": "Filesystem Tools", "tokens": 200, "color": "#06b6d4"},
                {"name": "Terminal Tools", "tokens": 150, "color": "#0891b2"},
            ],
        }
        script = build_trajectory_hud_script("test-parity", sample_data, [], open_view=True)

        # Context Window Granular Slices
        self.assertIn("system_prompt_slices", script)
        self.assertIn("tool_def_slices", script)
        self.assertIn("Filesystem Tools", script)
        self.assertIn("Terminal Tools", script)
        self.assertIn("#06b6d4", script)
        self.assertIn("#0891b2", script)

        # Step Inspector Specialized Cards
        self.assertIn("agyis-terminal-card", script)
        self.assertIn("agyis-file-card", script)
        self.assertIn("agyis-diff-card", script)
        self.assertIn("agyis-subagent-card", script)
        self.assertIn("agyis-checkpoint-card", script)
        self.assertIn("Compaction Checkpoint", script)
        self.assertIn("Jump to Previous Checkpoint", script)
        self.assertIn("agyis-jump-prev-checkpoint", script)

        # Timing Header Guard
        self.assertIn("isModelStep && totalDurationMs > 0", script)

        # Invocation & Execution Polish
        self.assertIn("No tool calls executed in this step", script)
        self.assertIn("Status Transitions", script)
        self.assertIn("Model Usage Metrics", script)


class TestCleanroomAntigravityParityUpgrades(unittest.TestCase):
    """Hermetic tests for Cleanroom Antigravity Trajectory Debug View parity upgrades."""

    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.brain_dir = Path(self.temp_dir.name)

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def test_native_tool_step_unpacking(self) -> None:
        convo_id = "test-cortex-unpacking"
        convo_dir = self.brain_dir / convo_id / ".system_generated" / "logs"
        convo_dir.mkdir(parents=True, exist_ok=True)
        transcript = convo_dir / "transcript.jsonl"

        steps_data = [
            # 1. runCommand step
            {
                "step_index": 0,
                "runCommand": {
                    "commandLine": "ls -la",
                    "exitCode": 0,
                    "combinedOutput": {"full": "total 42\ndrwxr-xr-x"},
                    "cwd": "/workspace",
                },
            },
            # 2. viewFile step
            {
                "step_index": 1,
                "viewFile": {
                    "absolutePathUri": "/workspace/main.py",
                    "content": "def main():\n    pass\n",
                    "endLine": 2,
                },
            },
            # 3. codeAction step
            {
                "step_index": 2,
                "codeAction": {
                    "actionSpec": {
                        "editFile": {"path": {"absoluteUri": "/workspace/lib.py"}}
                    },
                    "actionResult": {
                        "edit": {
                            "diff": {
                                "unifiedDiff": {
                                    "lines": [
                                        {"text": "--- a/lib.py", "type": "NORMAL"},
                                        {"text": "+++ b/lib.py", "type": "NORMAL"},
                                        {"text": "+def foo():", "type": "INSERTION"},
                                    ]
                                }
                            }
                        }
                    },
                },
            },
            # 4. invokeSubagent step
            {
                "step_index": 3,
                "invokeSubagent": {
                    "subagents": [
                        {
                            "typeName": "SecurityAuditor",
                            "role": "Auditor",
                            "initialPrompt": "Audit authentication token handling",
                        }
                    ]
                },
            },
            # 5. checkpoint step
            {
                "step_index": 4,
                "checkpoint": {
                    "sessionSummary": "Compacted 50 steps into high-density state",
                },
                "metadata": {
                    "retryInfos": [
                        {
                            "usage": {
                                "cacheReadTokens": 185000,
                                "inputTokens": 12000,
                            }
                        }
                    ]
                },
            },
            # 6. toolCall step with argumentsJson
            {
                "step_index": 5,
                "metadata": {
                    "toolCall": {
                        "id": "tc-call-1",
                        "name": "run_command",
                        "argumentsJson": json.dumps({"command": "cargo test", "timeout": 30}),
                    }
                },
            },
        ]

        with open(transcript, "w", encoding="utf-8") as f:
            for s in steps_data:
                f.write(json.dumps(s) + "\n")

        traj = load_conversation_trajectory(convo_id, brain_dir=self.brain_dir)
        steps = traj["steps"]
        self.assertEqual(len(steps), 6)

        # Assert runCommand unpacking
        s0 = steps[0]
        self.assertEqual(s0["type"], "RUN_COMMAND")
        self.assertEqual(s0["command"], "ls -la")
        self.assertEqual(s0["exitCode"], 0)
        self.assertIn("total 42", s0["output"])
        self.assertEqual(s0["cwd"], "/workspace")

        # Assert viewFile unpacking
        s1 = steps[1]
        self.assertEqual(s1["type"], "VIEW_FILE")
        self.assertEqual(s1["filePath"], "/workspace/main.py")
        self.assertIn("def main():", s1["fileContent"])
        self.assertEqual(s1["endLine"], 2)

        # Assert codeAction unpacking
        s2 = steps[2]
        self.assertEqual(s2["type"], "CODE_ACTION")
        self.assertEqual(s2["filePath"], "/workspace/lib.py")
        self.assertEqual(len(s2["diffLines"]), 3)
        self.assertEqual(s2["diffLines"][2]["text"], "+def foo():")

        # Assert invokeSubagent unpacking
        s3 = steps[3]
        self.assertEqual(s3["type"], "INVOKE_SUBAGENT")
        self.assertIsNotNone(s3["subagent"])
        self.assertEqual(s3["subagent"]["typeName"], "SecurityAuditor")
        self.assertEqual(s3["subagent"]["role"], "Auditor")

        # Assert checkpoint unpacking
        s4 = steps[4]
        self.assertEqual(s4["type"], "CHECKPOINT")
        self.assertIn("Compacted 50 steps", s4["sessionSummary"])
        self.assertEqual(s4["cacheReadTokens"], 185000)
        self.assertEqual(s4["checkpointInputTokens"], 12000)

        # Assert toolCall argumentsJson unpacking
        s5 = steps[5]
        self.assertEqual(len(s5["tool_calls"]), 1)
        self.assertEqual(s5["tool_calls"][0]["name"], "run_command")
        self.assertEqual(s5["tool_calls"][0]["args"]["command"], "cargo test")
        self.assertEqual(s5["tool_calls"][0]["args"]["timeout"], 30)

    def test_granular_slices_generation(self) -> None:
        convo_id = "test-slices"
        convo_dir = self.brain_dir / convo_id / ".system_generated" / "logs"
        convo_dir.mkdir(parents=True, exist_ok=True)
        transcript = convo_dir / "transcript.jsonl"

        with open(transcript, "w", encoding="utf-8") as f:
            f.write(json.dumps({"source": "user", "content": "Test prompt"}) + "\n")

        traj = load_conversation_trajectory(convo_id, brain_dir=self.brain_dir)

        # Unmeasured transcripts must return empty slice lists rather than synthetic guesses
        self.assertEqual(traj.get("system_prompt_slices", []), [])
        self.assertEqual(traj.get("tool_def_slices", []), [])

        # Measured chatModel prompt tags + tool definitions produce full granular slices
        measured_id = f"{convo_id}_measured"
        measured_dir = self.brain_dir / measured_id
        measured_dir.mkdir(parents=True, exist_ok=True)
        measured_step = {
            "source": "model",
            "content": "Measured response",
            "chatModel": {
                "systemPrompt": (
                    "<identity>Agent ID system text</identity>"
                    "<guidelines>Strict engineering rules</guidelines>"
                    "<messaging>Inter-agent messaging spec</messaging>"
                    "<artifacts>Artifact directory rules</artifacts>"
                ),
                "tools": [
                    {"name": "read_file", "description": "Read disk files"},
                    {"name": "run_command", "description": "Execute bash command"},
                    {"name": "invoke_subagent", "description": "Spawn subagent"},
                    {"name": "schedule", "description": "Cron timer"},
                ],
            },
        }
        (measured_dir / "transcript.jsonl").write_text(json.dumps(measured_step) + "\n", encoding="utf-8")
        measured_traj = load_conversation_trajectory(measured_id, brain_dir=self.brain_dir)

        sys_slices = measured_traj.get("system_prompt_slices", [])
        self.assertTrue(len(sys_slices) >= 4)
        slice_names = [sl["name"] for sl in sys_slices]
        self.assertIn("Identity", slice_names)
        self.assertIn("Guidelines", slice_names)
        self.assertIn("Messaging", slice_names)

        tool_slices = measured_traj.get("tool_def_slices", [])
        self.assertEqual(len(tool_slices), 4)
        tool_names = [sl["name"] for sl in tool_slices]
        self.assertIn("Filesystem Tools", tool_names)
        self.assertIn("Terminal Tools", tool_names)
        self.assertIn("Subagents", tool_names)
        self.assertIn("Automation & Tasks", tool_names)


if __name__ == "__main__":
    unittest.main()
