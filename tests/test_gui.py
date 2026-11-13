# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Arafat Zahan (@kuasha420)
# Corporate Stewardship & Infrastructure: Purrfect Software Limited (PSL)
# Governed by: ICARO-42/b Ordinance (Company-Supported Personal IP Framework)

"""
Hermetic unit and integration tests for harness/commands/gui.py and 'agyis gui' CLI (ADR-014 / ADR-015).
"""

from __future__ import annotations

import argparse
import io
import json
import os
from pathlib import Path
import socket
import struct
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


class TestTrajectoryDebugInjection(unittest.TestCase):
    """Tests injecting flags and triggering URL navigation."""

    def test_inject_trajectory_debug_success(self) -> None:
        mock_client = MagicMock()
        mock_client.evaluate.return_value = {
            "success": True,
            "flags": {"enable-trajectory-debug-tools": True, "enable-developer-mode": True},
            "url": "https://127.0.0.1:37277/?trajectoryDebugOpen=true",
        }

        res = inject_trajectory_debug(mock_client)
        self.assertTrue(res["success"])
        self.assertIn("trajectoryDebugOpen=true", res["url"])

    def test_inject_trajectory_debug_failure(self) -> None:
        mock_client = MagicMock()
        mock_client.evaluate.return_value = {"success": False, "error": "Access denied"}

        with self.assertRaises(CDPError):
            inject_trajectory_debug(mock_client)

    def test_inject_trajectory_debug_retry_on_unhydrated_origin(self) -> None:
        mock_client = MagicMock()
        mock_client.evaluate.return_value = {
            "success": False,
            "retry": True,
            "error": "SecurityError: Failed to read the 'localStorage' property from 'Window': Access is denied for this document.",
        }

        with self.assertRaises(CDPError) as ctx:
            inject_trajectory_debug(mock_client)
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
        mock_client = MagicMock()
        mock_client.evaluate.return_value = {
            "success": True,
            "flags": {"enable-trajectory-debug-tools": True, "enable-developer-mode": True},
            "url": "https://127.0.0.1:37277/?trajectoryDebugOpen=true",
            "open": True,
            "hotkey_registered": True,
        }

        res = inject_trajectory_debug(mock_client, toggle=True)
        self.assertTrue(res["success"])
        self.assertTrue(res["open"])

        # Assert Page.addScriptToEvaluateOnNewDocument was called
        mock_client.send_command.assert_called_once()
        method, params = mock_client.send_command.call_args[0]
        self.assertEqual(method, "Page.addScriptToEvaluateOnNewDocument")
        self.assertIn("source", params)
        self.assertIn("F12", params["source"])
        self.assertIn("agyis-trajectory-hud", params["source"])
        self.assertIn("MutationObserver", params["source"])

    def test_inject_trajectory_debug_toggle_expression(self) -> None:
        mock_client = MagicMock()
        mock_client.evaluate.return_value = {
            "success": True,
            "flags": {},
            "url": "https://127.0.0.1:37277/?trajectoryDebugOpen=false",
            "open": False,
        }
        res = inject_trajectory_debug(mock_client, toggle=True)
        self.assertTrue(res["success"])
        self.assertFalse(res["open"])
        expr = mock_client.evaluate.call_args[0][0]
        self.assertIn('"isToggle": true', expr)
        self.assertIn("agyis-trajectory-hud", expr)

    def test_inject_trajectory_debug_open_view_false(self) -> None:
        mock_client = MagicMock()
        mock_client.evaluate.return_value = {
            "success": True,
            "flags": {"enable-trajectory-debug-tools": True, "enable-developer-mode": True},
            "url": "https://127.0.0.1:37277/",
            "open": False,
            "hotkey_registered": True,
        }
        res = inject_trajectory_debug(mock_client, open_view=False)
        self.assertTrue(res["success"])
        self.assertFalse(res["open"])
        self.assertEqual(res["url"], "https://127.0.0.1:37277/")
        self.assertTrue(res["hotkey_registered"])

        # Verify evaluate expression contains shouldOpen = false
        expr = mock_client.evaluate.call_args[0][0]
        self.assertIn('"shouldOpen": false', expr)
        self.assertIn("agyis-trajectory-hud", expr)
        # Verify Page.addScriptToEvaluateOnNewDocument was still called
        mock_client.send_command.assert_called_once()
        method, params = mock_client.send_command.call_args[0]
        self.assertEqual(method, "Page.addScriptToEvaluateOnNewDocument")
        self.assertIn("F12", params["source"])

    def test_inject_trajectory_debug_with_explicit_convo_id(self) -> None:
        mock_client = MagicMock()
        mock_client.evaluate.return_value = {
            "success": True,
            "flags": {"enable-trajectory-debug-tools": True, "enable-developer-mode": True},
            "url": "https://127.0.0.1:37277/",
            "open": True,
            "hotkey_registered": True,
        }
        # Explicit convo_id supplied: must not raise UnboundLocalError on page_url
        res = inject_trajectory_debug(mock_client, conversation_id="explicit-convo-12345")
        self.assertTrue(res["success"])
        self.assertEqual(res["convo_id"], "explicit-convo-12345")
        self.assertIn("https://127.0.0.1:37277/", res["url"])

    @patch("harness.gui.server.ensure_trajectory_server")
    def test_inject_trajectory_debug_auto_spawns_server(self, mock_ensure_server) -> None:
        mock_client = MagicMock()
        mock_client.evaluate.return_value = {"success": True, "open": True}
        res = inject_trajectory_debug(mock_client, conversation_id="test-spawn-convo")
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
            self.assertIn("Trajectory Debug shortcuts and Command Palette flags primed successfully (modal popup suppressed)", out)
            self.assertIn("Injected flags: 'enable-trajectory-debug-tools', 'enable-developer-mode'", out)
            self.assertIn("Developer: Trajectory Debug View", out)
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

        # Step 1 has thinking text, so TTFT > 0
        self.assertTrue(enriched[1]["thinking_duration_ms"] > 0)

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

        # Active epoch post-checkpoint only (excludes pre-checkpoint 1200+3000+1500 steps)
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
        self.assertIn("top: 38px;", script)
        self.assertIn("height: calc(100vh - 38px) !important;", script)
        self.assertIn("-webkit-app-region: no-drag;", script)
        # Cumulative token sync in JS
        self.assertIn("rawSegmentsSum = segments.reduce", script)
        self.assertIn("activeTokensSum = selectedEpochTotal > 0 ? selectedEpochTotal : rawSegmentsSum", script)


class TestGUISystemdService(unittest.TestCase):
    """Tests systemd user path and service management for 'agyis gui --service'."""

    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.unit_dir = Path(self.temp_dir.name) / "systemd" / "user"

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def test_generate_gui_systemd_units_content(self) -> None:
        path_unit = generate_gui_systemd_path_unit()
        self.assertIn("PathChanged=%h/.config/Antigravity/DevToolsActivePort", path_unit)
        self.assertIn("Unit=antigravity-trajectory.service", path_unit)

        service_unit = generate_gui_systemd_service_unit()
        self.assertIn("MemoryMax=500M", service_unit)
        self.assertIn("MemoryHigh=300M", service_unit)
        self.assertIn("gui --no-popup --wait 15.0", service_unit)

    @patch("harness.commands.gui._run_gui_systemctl")
    def test_handle_gui_service_lifecycle(self, mock_systemctl: MagicMock) -> None:
        mock_systemctl.return_value = MagicMock(returncode=0, stdout="active", stderr="")

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
        code = handle_gui_service_command(action="status", unit_dir=empty_dir)
        self.assertEqual(code, 1)

    @patch("harness.commands.gui._run_gui_systemctl")
    def test_handle_gui_service_fails_when_systemctl_fails(self, mock_systemctl: MagicMock) -> None:
        mock_systemctl.return_value = MagicMock(returncode=1, stdout="", stderr="Access denied")
        # Install should fail and return 1 when systemctl fails
        code = handle_gui_service_command(action="install", unit_dir=self.unit_dir)
        self.assertEqual(code, 1)

    @patch("shutil.which")
    def test_handle_gui_service_fails_when_systemctl_missing(self, mock_which: MagicMock) -> None:
        mock_which.return_value = None
        code = handle_gui_service_command(action="install", unit_dir=self.unit_dir)
        self.assertEqual(code, 1)

    def test_cli_parser_gui_service_option(self) -> None:
        parser = build_parser()
        args = parser.parse_args(["gui", "--service", "install"])
        self.assertEqual(args.service, "install")

        args_status = parser.parse_args(["gui", "--service", "status"])
        self.assertEqual(args_status.service, "status")


class TestCheckpointEpochPartitioning(unittest.TestCase):
    """Tests trajectory partitioning into epochs based on CHECKPOINT steps (ADR-014 / PSL-INV-010)."""

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

    def test_epoch_partitioning_no_checkpoints(self) -> None:
        convo_id = "convo-no-cp"
        steps = [{"source": "user", "content": f"msg {i}"} for i in range(5)]
        self._create_convo_transcript(convo_id, steps)

        data = load_conversation_trajectory(convo_id, brain_dir=self.brain_dir)
        epochs = data.get("epochs", [])
        self.assertEqual(len(epochs), 1)
        self.assertEqual(epochs[0]["epoch_index"], 0)
        self.assertEqual(epochs[0]["start_index"], 0)
        self.assertEqual(epochs[0]["end_index"], 4)
        self.assertEqual(epochs[0]["step_count"], 5)
        self.assertFalse(epochs[0]["has_checkpoint"])

    def test_epoch_partitioning_single_checkpoint(self) -> None:
        convo_id = "convo-single-cp"
        steps = []
        for i in range(10):
            if i == 4:
                steps.append({"type": "CHECKPOINT", "compaction_summary": "Compacted at 4"})
            else:
                steps.append({"source": "model", "content": f"Step {i}"})
        self._create_convo_transcript(convo_id, steps)

        data = load_conversation_trajectory(convo_id, brain_dir=self.brain_dir)
        epochs = data.get("epochs", [])
        self.assertEqual(len(epochs), 2)

        # Epoch 0: step 0 to step 4 (inclusive)
        self.assertEqual(epochs[0]["epoch_index"], 0)
        self.assertEqual(epochs[0]["start_index"], 0)
        self.assertEqual(epochs[0]["end_index"], 4)
        self.assertEqual(epochs[0]["step_count"], 5)
        self.assertTrue(epochs[0]["has_checkpoint"])
        self.assertEqual(epochs[0]["summary"], "Compacted at 4")

        # Epoch 1: step 4 to step 9 (inclusive)
        self.assertEqual(epochs[1]["epoch_index"], 1)
        self.assertEqual(epochs[1]["start_index"], 4)
        self.assertEqual(epochs[1]["end_index"], 9)
        self.assertEqual(epochs[1]["step_count"], 6)
        self.assertTrue(epochs[1]["has_checkpoint"])

    def test_epoch_partitioning_multiple_checkpoints(self) -> None:
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
        epochs = data.get("epochs", [])
        self.assertEqual(len(epochs), 3)

        self.assertEqual(epochs[0]["start_index"], 0)
        self.assertEqual(epochs[0]["end_index"], 3)
        self.assertEqual(epochs[0]["step_count"], 4)

        self.assertEqual(epochs[1]["start_index"], 3)
        self.assertEqual(epochs[1]["end_index"], 7)
        self.assertEqual(epochs[1]["step_count"], 5)

        self.assertEqual(epochs[2]["start_index"], 7)
        self.assertEqual(epochs[2]["end_index"], 11)
        self.assertEqual(epochs[2]["step_count"], 5)

    def test_epoch_partitioning_last_step_checkpoint(self) -> None:
        convo_id = "convo-last-cp"
        steps = []
        for i in range(5):
            if i == 4:
                steps.append({"type": "CHECKPOINT", "compaction_summary": "Summary at end"})
            else:
                steps.append({"source": "user", "content": f"msg {i}"})
        self._create_convo_transcript(convo_id, steps)

        data = load_conversation_trajectory(convo_id, brain_dir=self.brain_dir)
        epochs = data.get("epochs", [])
        self.assertEqual(len(epochs), 1)
        self.assertEqual(epochs[0]["start_index"], 0)
        self.assertEqual(epochs[0]["end_index"], 4)
        self.assertEqual(epochs[0]["step_count"], 5)
        self.assertTrue(epochs[0]["has_checkpoint"])

    def test_epoch_partitioning_empty(self) -> None:
        convo_id = "convo-empty"
        self._create_convo_transcript(convo_id, [])

        data = load_conversation_trajectory(convo_id, brain_dir=self.brain_dir)
        self.assertEqual(data.get("epochs", []), [])


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
            "epochs": [
                {"epoch_index": 0, "start_index": 0, "end_index": 1, "step_count": 2, "has_checkpoint": False, "summary": "Initial"}
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

    def test_hud_script_contains_epoch_switcher(self) -> None:
        sample_data = {"conversation_id": "test-ep", "steps": []}
        script = build_trajectory_hud_script("test-ep", sample_data, [], open_view=True)

        self.assertIn("agyis-epoch-prev", script)
        self.assertIn("agyis-epoch-next", script)
        self.assertIn("Prev Epoch", script)
        self.assertIn("Next Epoch", script)

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
        """BUILD-TOGGLE-LATEST-EPOCH-STEP-PAGE-001: Assert syncToLatestState exists and is called across entrypoints."""
        sample_data = {
            "conversation_id": "test-sync-latest",
            "steps": [{"step_index": i, "type": "USER_PROMPT"} for i in range(105)],
            "epochs": [
                {"epoch_index": 0, "start_index": 0, "end_index": 49},
                {"epoch_index": 1, "start_index": 50, "end_index": 99},
                {"epoch_index": 2, "start_index": 100, "end_index": 104},
            ],
        }
        script = build_trajectory_hud_script("test-sync-latest", sample_data, [], open_view=True, toggle=True)

        # 1. Assert helper function is defined
        self.assertIn("function syncToLatestState(state)", script)
        self.assertIn("state.activeEpochIndex = epochs.length > 0 ? epochs.length - 1 : -1;", script)
        self.assertIn("state.selectedIndex = Math.max(0, steps.length - 1);", script)
        self.assertIn("const totalPages = Math.max(1, Math.ceil(totalSteps / pageSize));", script)
        self.assertIn("state.tablePage = totalPages - 1;", script)

        # 2. Assert toggle branch calls syncToLatestState
        self.assertIn("if (existingHud && isToggle)", script)
        self.assertIn("syncToLatestState(state);", script)
        self.assertIn("if (typeof renderHud === \"function\") renderHud();", script)

        # 3. Assert initial state initialization sets latest epoch, step, and table page and syncs
        self.assertIn("window.__agyis_hud_state = {", script)
        self.assertIn("activeEpochIndex: epochs.length > 0 ? epochs.length - 1 : -1,", script)
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
        """BUILD-TOGGLE-LATEST-EPOCH-STEP-PAGE-001: Execute syncToLatestState in node to assert exact runtime behavior."""
        import subprocess

        js_harness = """
        function syncToLatestState(state) {
            if (!state || !state.currentData) return;
            const steps = state.currentData.steps || [];
            const epochs = state.currentData.epochs || [];

            // 1. Show latest epoch
            state.activeEpochIndex = epochs.length > 0 ? epochs.length - 1 : -1;

            // 2. Select latest step
            state.selectedIndex = Math.max(0, steps.length - 1);

            // 3. Show latest 50 steps on steps list (last table page)
            const totalSteps = steps.length;
            const pageSize = 50;
            const totalPages = Math.max(1, Math.ceil(totalSteps / pageSize));
            state.tablePage = totalPages - 1;
        }

        const cases = [
            // Case 0: Empty trajectory
            { currentData: { steps: [], epochs: [] } },
            // Case 1: 30 steps (single page, 1 epoch)
            { currentData: { steps: new Array(30).fill({}), epochs: [{ epoch_index: 0 }] } },
            // Case 2: 50 steps (exact 1 page boundary)
            { currentData: { steps: new Array(50).fill({}), epochs: [{ epoch_index: 0 }] } },
            // Case 3: 51 steps (page 1)
            { currentData: { steps: new Array(51).fill({}), epochs: [{ epoch_index: 0 }, { epoch_index: 1 }] } },
            // Case 4: 120 steps across 3 epochs (page 2, last step 119, epoch 2)
            { currentData: { steps: new Array(120).fill({}), epochs: [{ epoch_index: 0 }, { epoch_index: 1 }, { epoch_index: 2 }] } }
        ];

        const results = cases.map(st => {
            syncToLatestState(st);
            return {
                activeEpochIndex: st.activeEpochIndex,
                selectedIndex: st.selectedIndex,
                tablePage: st.tablePage
            };
        });

        console.log(JSON.stringify(results));
        """
        try:
            res = subprocess.run(["node", "-e", js_harness], capture_output=True, text=True, check=True)
            results = json.loads(res.stdout.strip())
            # Case 0: Empty
            self.assertEqual(results[0], {"activeEpochIndex": -1, "selectedIndex": 0, "tablePage": 0})
            # Case 1: 30 steps
            self.assertEqual(results[1], {"activeEpochIndex": 0, "selectedIndex": 29, "tablePage": 0})
            # Case 2: 50 steps
            self.assertEqual(results[2], {"activeEpochIndex": 0, "selectedIndex": 49, "tablePage": 0})
            # Case 3: 51 steps
            self.assertEqual(results[3], {"activeEpochIndex": 1, "selectedIndex": 50, "tablePage": 1})
            # Case 4: 120 steps
            self.assertEqual(results[4], {"activeEpochIndex": 2, "selectedIndex": 119, "tablePage": 2})
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
        self.assertIn("Jump to Previous Epoch", script)
        self.assertIn("agyis-jump-prev-epoch", script)

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


if __name__ == "__main__":
    unittest.main()


