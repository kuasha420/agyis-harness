# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Arafat Zahan (@kuasha420)
# Corporate Stewardship & Infrastructure: Purrfect Software Limited (PSL)
# Governed by: ICARO-42/b Ordinance (Company-Supported Personal IP Framework)

"""
Google Antigravity Desktop GUI Telemetry & DevTools Controller (ADR-014 / REA-SPEC-ANTIGRAVITY-GUI-DEVTOOLS-2026-10-17).

Provides zero-dependency introspection and runtime control over Google Antigravity's Electron GUI
via the local Chromium DevTools Protocol (CDP) WebSocket:
- Read active port from ~/.config/Antigravity/DevToolsActivePort
- Query active browser targets via http://127.0.0.1:<port>/json
- Standard-library-only RFC 6455 WebSocket client framing
- Runtime.evaluate injection:
  * LocalStorage jetski.developer.customFlagOverrides (enable-trajectory-debug-tools, enable-developer-mode)
  * Window URL searchParams trigger ?trajectoryDebugOpen=true
- Non-invasive DevTools inspector URL formatting and status reporting
"""

from __future__ import annotations

import argparse
import base64
import json
import os
from pathlib import Path
import socket
import struct
import sys
from typing import Any, Dict, List, Optional, Tuple
import urllib.error
import urllib.parse
import urllib.request

DEFAULT_DEVTOOLS_PORT_FILE = Path.home() / ".config" / "Antigravity" / "DevToolsActivePort"
FLAG_OVERRIDES_KEY = "jetski.developer.customFlagOverrides"
DEFAULT_TARGET_FLAGS = {
    "enable-trajectory-debug-tools": True,
    "enable-developer-mode": True,
}


class CDPError(Exception):
    """Base exception for Chromium DevTools Protocol errors."""
    pass


class CDPConnectionError(CDPError):
    """Raised when connecting to CDP HTTP or WebSocket endpoint fails."""
    pass


class CDPTimeoutError(CDPError):
    """Raised when CDP socket or HTTP operation times out."""
    pass


class CDPTargetNotFoundError(CDPError):
    """Raised when no suitable browser target page is found."""
    pass


def get_devtools_active_port(port_file: Optional[Path] = None) -> Tuple[int, str]:
    """
    Reads and parses the active DevTools port file written by Antigravity Electron shell.

    Format:
      Line 1: Integer port (e.g. 46391)
      Line 2: Browser target path (e.g. /devtools/browser/<uuid>)
    """
    target_file = port_file or DEFAULT_DEVTOOLS_PORT_FILE
    if not target_file.exists():
        raise FileNotFoundError(f"DevToolsActivePort file not found at: {target_file}")

    content = target_file.read_text(encoding="utf-8").strip().splitlines()
    if not content:
        raise ValueError(f"DevToolsActivePort file is empty: {target_file}")

    try:
        port = int(content[0].strip())
    except ValueError as exc:
        raise ValueError(f"Invalid port number in {target_file}: {content[0]}") from exc

    if not (1 <= port <= 65535):
        raise ValueError(f"Port number out of valid TCP range [1-65535]: {port}")

    browser_path = content[1].strip() if len(content) > 1 else ""
    return port, browser_path


def get_cdp_targets(port: int, host: str = "127.0.0.1", timeout: float = 5.0) -> List[Dict[str, Any]]:
    """Queries http://<host>:<port>/json to retrieve active browser targets."""
    url = f"http://{host}:{port}/json"
    req = urllib.request.Request(url, headers={"User-Agent": "Agyis-CDP-Client"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            data = resp.read().decode("utf-8")
            parsed = json.loads(data)
            if isinstance(parsed, list):
                return parsed
            return []
    except (urllib.error.URLError, TimeoutError, OSError, json.JSONDecodeError) as exc:
        raise CDPConnectionError(f"Failed to query CDP targets at {url}: {exc}") from exc


def find_page_target(targets: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    """Identifies the active Antigravity main application page target."""
    pages = [t for t in targets if t.get("type") == "page"]
    if not pages:
        return None

    # Prefer window with Antigravity title or active webview URL
    for p in pages:
        title = p.get("title", "")
        url = p.get("url", "")
        if "Antigravity" in title or ("127.0.0.1" in url and not url.startswith("devtools://")):
            return p

    return pages[0]


class CDPWebSocketClient:
    """
    Minimal RFC 6455 WebSocket client using strictly Python standard library.
    Implements client-to-server 4-byte masking, variable length encoding, and JSON-RPC over CDP.
    """

    def __init__(self, timeout: float = 5.0) -> None:
        self.timeout = timeout
        self.sock: Optional[socket.socket] = None
        self._buffer = bytearray()
        self._req_id = 0

    def connect(self, ws_url: str) -> None:
        """Establishes TCP connection and performs RFC 6455 WebSocket handshake."""
        parsed = urllib.parse.urlparse(ws_url)
        host = parsed.hostname or "127.0.0.1"
        port = parsed.port or 80
        path = parsed.path or "/"

        try:
            self.sock = socket.create_connection((host, port), timeout=self.timeout)
        except (OSError, TimeoutError) as exc:
            raise CDPConnectionError(f"Could not connect to WebSocket at {host}:{port}: {exc}") from exc

        # RFC 6455 handshake
        key = base64.b64encode(os.urandom(16)).decode("ascii")
        handshake_req = (
            f"GET {path} HTTP/1.1\r\n"
            f"Host: {host}:{port}\r\n"
            f"Upgrade: websocket\r\n"
            f"Connection: Upgrade\r\n"
            f"Sec-WebSocket-Key: {key}\r\n"
            f"Sec-WebSocket-Version: 13\r\n\r\n"
        )
        try:
            self.sock.sendall(handshake_req.encode("ascii"))
        except OSError as exc:
            self.close()
            raise CDPConnectionError(f"Failed to send WebSocket handshake: {exc}") from exc

        # Read response headers until \r\n\r\n
        buf = bytearray()
        while b"\r\n\r\n" not in buf:
            try:
                chunk = self.sock.recv(4096)
            except (socket.timeout, TimeoutError) as exc:
                self.close()
                raise CDPTimeoutError("Timeout waiting for WebSocket handshake response") from exc
            except OSError as exc:
                self.close()
                raise CDPConnectionError(f"Error during WebSocket handshake: {exc}") from exc

            if not chunk:
                self.close()
                raise CDPConnectionError("Socket closed prematurely during WebSocket handshake")
            buf.extend(chunk)

        header_bytes, _, remaining = buf.partition(b"\r\n\r\n")
        self._buffer.extend(remaining)

        status_line = header_bytes.split(b"\r\n")[0].decode("ascii", errors="replace")
        # Validate status line has 101 status code (e.g. 'HTTP/1.1 101 WebSocket Protocol Handshake' or '101 Switching Protocols')
        parts = status_line.split()
        if len(parts) < 2 or parts[1] != "101":
            self.close()
            raise CDPConnectionError(f"WebSocket upgrade rejected by server: {status_line}")

    def _recv_exact(self, num_bytes: int) -> bytes:
        """Reads exactly num_bytes from internal buffer or socket."""
        if self.sock is None:
            raise CDPConnectionError("Socket is not connected")

        while len(self._buffer) < num_bytes:
            try:
                chunk = self.sock.recv(max(4096, num_bytes - len(self._buffer)))
            except (socket.timeout, TimeoutError) as exc:
                raise CDPTimeoutError("Socket read timed out") from exc
            except OSError as exc:
                raise CDPConnectionError(f"Socket read error: {exc}") from exc

            if not chunk:
                raise CDPConnectionError("Socket connection closed by remote peer")
            self._buffer.extend(chunk)

        res = bytes(self._buffer[:num_bytes])
        del self._buffer[:num_bytes]
        return res

    def send_frame(self, opcode: int, payload: bytes) -> None:
        """Encodes and sends an RFC 6455 masked frame to the server."""
        if self.sock is None:
            raise CDPConnectionError("Socket is not connected")

        length = len(payload)
        mask = os.urandom(4)
        masked_payload = bytes(b ^ mask[i % 4] for i, b in enumerate(payload))

        # FIN=1 (0x80) | opcode
        b0 = 0x80 | (opcode & 0x0F)

        # MASK=1 (0x80) | length
        if length < 126:
            header = bytes([b0, 0x80 | length]) + mask
        elif length <= 0xFFFF:
            header = bytes([b0, 0x80 | 126]) + struct.pack(">H", length) + mask
        else:
            header = bytes([b0, 0x80 | 127]) + struct.pack(">Q", length) + mask

        try:
            self.sock.sendall(header + masked_payload)
        except OSError as exc:
            raise CDPConnectionError(f"Failed to send WebSocket frame: {exc}") from exc

    def send_json(self, payload: Dict[str, Any]) -> None:
        """Serializes payload to JSON and sends as an RFC 6455 text frame (opcode 0x1)."""
        data = json.dumps(payload).encode("utf-8")
        self.send_frame(0x1, data)

    def recv_message(self, expected_id: Optional[int] = None) -> Dict[str, Any]:
        """Reads and decodes WebSocket frames until a JSON message matching expected_id arrives."""
        message_payload = bytearray()
        current_opcode: Optional[int] = None

        while True:
            hdr = self._recv_exact(2)
            fin = bool(hdr[0] & 0x80)
            opcode = hdr[0] & 0x0F
            if opcode != 0x0:
                current_opcode = opcode

            has_mask = bool(hdr[1] & 0x80)
            payload_len = hdr[1] & 0x7F

            if payload_len == 126:
                payload_len = struct.unpack(">H", self._recv_exact(2))[0]
            elif payload_len == 127:
                payload_len = struct.unpack(">Q", self._recv_exact(8))[0]

            mask = self._recv_exact(4) if has_mask else None
            raw_payload = self._recv_exact(payload_len)
            if mask:
                raw_payload = bytes(b ^ mask[i % 4] for i, b in enumerate(raw_payload))

            if current_opcode == 0x8:  # Connection close
                self.close()
                raise CDPConnectionError("Remote server sent WebSocket close frame")
            elif current_opcode == 0x9:  # Ping -> reply Pong
                self.send_frame(0xA, raw_payload)
                continue
            elif current_opcode == 0xA:  # Pong
                continue

            message_payload.extend(raw_payload)
            if fin:
                if current_opcode == 0x1:  # Text frame
                    try:
                        msg = json.loads(message_payload.decode("utf-8"))
                    except (json.JSONDecodeError, UnicodeDecodeError):
                        message_payload.clear()
                        current_opcode = None
                        continue
                    message_payload.clear()
                    current_opcode = None

                    if expected_id is None or msg.get("id") == expected_id:
                        return msg
                else:
                    message_payload.clear()
                    current_opcode = None

    def evaluate(self, expression: str, await_promise: bool = True, return_by_value: bool = True) -> Any:
        """Executes a JavaScript expression in the target page context via Runtime.evaluate."""
        self._req_id += 1
        payload = {
            "id": self._req_id,
            "method": "Runtime.evaluate",
            "params": {
                "expression": expression,
                "awaitPromise": await_promise,
                "returnByValue": return_by_value,
            },
        }
        self.send_json(payload)
        resp = self.recv_message(expected_id=self._req_id)

        if "error" in resp:
            err_msg = resp["error"].get("message", "Unknown CDP error")
            raise CDPError(f"CDP Runtime.evaluate error: {err_msg}")

        result_obj = resp.get("result", {}).get("result", {})
        if resp.get("result", {}).get("exceptionDetails"):
            details = resp["result"]["exceptionDetails"]
            raise CDPError(f"JavaScript evaluation exception: {details.get('text', details)}")

        return result_obj.get("value")

    def close(self) -> None:
        """Closes the active WebSocket connection."""
        if self.sock is not None:
            try:
                self.send_frame(0x8, b"")
            except (OSError, CDPError):
                pass
            try:
                self.sock.close()
            except OSError:
                pass
            self.sock = None
        self._buffer.clear()

    def __enter__(self) -> "CDPWebSocketClient":
        return self

    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        self.close()


def format_devtools_urls(port: int, target: Dict[str, Any]) -> Dict[str, str]:
    """Generates standardized inspection and debugging URLs for the active target."""
    ws_url = target.get("webSocketDebuggerUrl", "")
    ws_endpoint = ws_url.replace("ws://", "").replace("wss://", "")
    frontend_path = target.get("devtoolsFrontendUrl", "")
    frontend_url = f"http://127.0.0.1:{port}{frontend_path}" if frontend_path else ""

    return {
        "port": str(port),
        "target_id": target.get("id", ""),
        "title": target.get("title", ""),
        "target_url": target.get("url", ""),
        "websocket_debugger_url": ws_url,
        "devtools_frontend_url": frontend_url,
        "bundled_inspector_url": f"devtools://devtools/bundled/inspector.html?ws={ws_endpoint}" if ws_endpoint else "",
        "chrome_inspect_url": f"chrome://inspect/#devices (configure network target 127.0.0.1:{port})",
    }


def inject_trajectory_debug(client: CDPWebSocketClient, flags: Optional[Dict[str, bool]] = None) -> Dict[str, Any]:
    """
    Injects developer custom flag overrides into localStorage and pops open Trajectory Debug View.
    """
    target_flags = flags or DEFAULT_TARGET_FLAGS
    flags_json = json.dumps(target_flags)

    expr = f"""
    (() => {{
        try {{
            const key = "{FLAG_OVERRIDES_KEY}";
            let current = {{}};
            try {{
                current = JSON.parse(localStorage.getItem(key) || "{{}}");
            }} catch (_) {{}}
            const targetFlags = {flags_json};
            Object.assign(current, targetFlags);
            localStorage.setItem(key, JSON.stringify(current));

            const url = new URL(window.location.href);
            url.searchParams.set("trajectoryDebugOpen", "true");
            window.history.pushState({{}}, "", url.toString());
            window.dispatchEvent(new PopStateEvent("popstate"));
            return {{
                success: true,
                flags: current,
                url: url.toString()
            }};
        }} catch (e) {{
            return {{
                success: false,
                error: String(e)
            }};
        }}
    }})()
    """
    res = client.evaluate(expr)
    if isinstance(res, dict) and res.get("success"):
        return res
    raise CDPError(f"Failed to inject trajectory debug flags: {res}")


def cmd_gui(args: argparse.Namespace) -> int:
    """Primary handler for 'agyis gui' subcommand."""
    port_file: Optional[Path] = getattr(args, "port_file", None)
    timeout: float = getattr(args, "timeout", 5.0)
    as_json: bool = getattr(args, "json", False)
    do_devtools: bool = getattr(args, "devtools", False)
    do_trajectory: bool = getattr(args, "trajectory_debug", False)

    # 1. Inspect Port File
    try:
        port, browser_target = get_devtools_active_port(port_file)
    except Exception as exc:
        is_headless = not os.environ.get("DISPLAY") and not os.environ.get("WAYLAND_DISPLAY")
        if as_json:
            print(json.dumps({
                "status": "error",
                "error": "port_file_not_found",
                "message": str(exc),
                "headless": is_headless,
            }, indent=2))
        else:
            print(f"❌ Could not resolve Antigravity DevTools port: {exc}")
            if is_headless:
                print("   (Host environment appears headless: neither DISPLAY nor WAYLAND_DISPLAY is set)")
            print("   Ensure Google Antigravity Desktop GUI is running.")
        return 1

    # 2. Query CDP Targets
    try:
        targets = get_cdp_targets(port, timeout=timeout)
    except Exception as exc:
        if as_json:
            print(json.dumps({
                "status": "error",
                "error": "connection_failed",
                "port": port,
                "message": str(exc),
            }, indent=2))
        else:
            print(f"❌ Failed to connect to CDP endpoint on 127.0.0.1:{port}: {exc}")
            print("   The DevToolsActivePort file may be stale from a terminated session.")
        return 1

    # 3. Locate Page Target
    target = find_page_target(targets)
    if not target or not target.get("webSocketDebuggerUrl"):
        if as_json:
            print(json.dumps({
                "status": "error",
                "error": "no_page_target",
                "port": port,
                "target_count": len(targets),
            }, indent=2))
        else:
            print(f"❌ No active Antigravity page target found on 127.0.0.1:{port}.")
        return 1

    urls = format_devtools_urls(port, target)
    trajectory_result = None

    # 4. Trajectory Debug Injection
    if do_trajectory:
        ws_url = target["webSocketDebuggerUrl"]
        client = CDPWebSocketClient(timeout=timeout)
        try:
            client.connect(ws_url)
            trajectory_result = inject_trajectory_debug(client)
        except Exception as exc:
            if as_json:
                print(json.dumps({
                    "status": "error",
                    "error": "injection_failed",
                    "port": port,
                    "message": str(exc),
                }, indent=2))
            else:
                print(f"❌ Failed to inject trajectory debug flags via CDP: {exc}")
            return 1
        finally:
            client.close()

    # 5. Output Formatting
    if as_json:
        payload: Dict[str, Any] = {
            "status": "success",
            "port": port,
            "browser_target": browser_target,
            "target": target,
            "urls": urls,
        }
        if trajectory_result is not None:
            payload["trajectory_debug"] = trajectory_result
        print(json.dumps(payload, indent=2))
        return 0

    print("=" * 70)
    print(" 🛡️ Google Antigravity GUI Telemetry & DevTools CDP Controller")
    print("=" * 70)
    print(f" DevTools Port:      {port} (active loopback)")
    print(f" Active Window:      {target.get('title')}")
    print(f" Webview URL:        {target.get('url')}")
    print(f" WebSocket Endpoint: {target.get('webSocketDebuggerUrl')}")

    if trajectory_result is not None:
        print("-" * 70)
        print(" ✔ Trajectory Debug View unlocked successfully:")
        print("   • Injected flags: 'enable-trajectory-debug-tools', 'enable-developer-mode'")
        print("   • Dispatched URL parameter: ?trajectoryDebugOpen=true")
        print("   • Trajectory modal is now open on your desktop GUI.")

    if do_devtools or not do_trajectory:
        print("-" * 70)
        print(" DevTools Inspection Guides:")
        print(f"   • Chrome Inspect:       {urls['chrome_inspect_url']}")
        if urls["devtools_frontend_url"]:
            print(f"   • Direct Web Inspector: {urls['devtools_frontend_url']}")
        if urls["bundled_inspector_url"]:
            print(f"   • Bundled URL:          {urls['bundled_inspector_url']}")
        print("-" * 70)
        print(" CLI Usage Tip:")
        print("   • agyis gui --trajectory-debug : Open context breakdown & trajectory view")
        print("   • agyis gui --devtools         : Display DevTools inspector connection endpoints")
        print("   • agyis gui --json             : Emit structured JSON for automation")
    print("=" * 70)
    return 0
