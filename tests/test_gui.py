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
    find_page_target,
    format_devtools_urls,
    get_cdp_targets,
    get_devtools_active_port,
    inject_trajectory_debug,
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

    def test_build_hotkey_script_contents(self) -> None:
        script = build_hotkey_script()
        self.assertIn("F12", script)
        self.assertIn("isCtrlShiftT", script)
        self.assertIn("trajectoryDebugOpen", script)
        self.assertIn("popstate", script)
        self.assertIn("keydown", script)

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
        self.assertIn("trajectoryDebugOpen", params["source"])

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
        self.assertIn("const isToggle = true;", expr)
        self.assertIn('const nextState = isToggle ? (currentVal === "true" ? "false" : "true") : "true";', expr)


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
            self.assertIn("--wait", out)
            self.assertIn("--port-file", out)
            self.assertIn("--timeout", out)
            self.assertIn("--json", out)

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
            mock_inject.assert_called_once_with(unittest.mock.ANY, toggle=False)
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
            mock_inject.assert_called_once_with(unittest.mock.ANY, toggle=True)
            out = mock_out.getvalue()
            self.assertIn("Trajectory Debug View closed successfully", out)

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


if __name__ == "__main__":
    unittest.main()
