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
import time
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
    """Identifies the active Antigravity main application page target, skipping about:blank."""
    pages = [
        t for t in targets
        if t.get("type") == "page" and not (t.get("url") or "").startswith("about:blank")
    ]
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

    def send_command(self, method: str, params: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """Sends a CDP JSON-RPC command and waits for its response."""
        self._req_id += 1
        payload: Dict[str, Any] = {
            "id": self._req_id,
            "method": method,
        }
        if params is not None:
            payload["params"] = params
        self.send_json(payload)
        resp = self.recv_message(expected_id=self._req_id)

        if "error" in resp:
            err_msg = resp["error"].get("message", "Unknown CDP error")
            raise CDPError(f"CDP {method} error: {err_msg}")

        return resp.get("result", {})

    def evaluate(self, expression: str, await_promise: bool = True, return_by_value: bool = True) -> Any:
        """Executes a JavaScript expression in the target page context via Runtime.evaluate."""
        result_obj = self.send_command(
            "Runtime.evaluate",
            {
                "expression": expression,
                "awaitPromise": await_promise,
                "returnByValue": return_by_value,
            },
        )
        if result_obj.get("exceptionDetails"):
            details = result_obj["exceptionDetails"]
            text = details.get("text", details) if isinstance(details, dict) else details
            raise CDPError(f"JavaScript evaluation exception: {text}")

        return result_obj.get("result", {}).get("value")

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


def build_hotkey_script() -> str:
    """
    Builds the JavaScript snippet to listen for F12 and Ctrl+Shift+T hotkeys
    and toggle the trajectoryDebugOpen URL parameter.
    """
    return (
        "(() => {\n"
        "  if (window.__agyis_hotkey_installed) return;\n"
        "  window.__agyis_hotkey_installed = true;\n"
        "  window.addEventListener('keydown', (e) => {\n"
        "    const isF12 = e.key === 'F12';\n"
        "    const isCtrlShiftT = (e.ctrlKey || e.metaKey) && e.shiftKey && (e.key === 'T' || e.key === 't');\n"
        "    if (isF12 || isCtrlShiftT) {\n"
        "      e.preventDefault();\n"
        "      e.stopPropagation();\n"
        "      try {\n"
        "        const url = new URL(window.location.href);\n"
        "        const current = url.searchParams.get('trajectoryDebugOpen');\n"
        "        const nextState = current === 'true' ? 'false' : 'true';\n"
        "        url.searchParams.set('trajectoryDebugOpen', nextState);\n"
        "        window.history.pushState({}, '', url.toString());\n"
        "        window.dispatchEvent(new PopStateEvent('popstate'));\n"
        "      } catch (err) {\n"
        "        console.error('Failed to toggle trajectory debug view:', err);\n"
        "      }\n"
        "    }\n"
        "  }, true);\n"
        "})();"
    )


def inject_trajectory_debug(
    client: CDPWebSocketClient,
    flags: Optional[Dict[str, bool]] = None,
    toggle: bool = False,
    open_view: bool = True,
) -> Dict[str, Any]:
    """
    Injects developer custom flag overrides into localStorage, opens or toggles
    Trajectory Debug View, and installs hotkey listeners (F12, Ctrl+Shift+T) surviving page reloads.
    """
    target_flags = flags or DEFAULT_TARGET_FLAGS
    flags_json = json.dumps(target_flags)
    toggle_json = "true" if toggle else "false"
    open_view_json = "true" if open_view else "false"
    hotkey_script = build_hotkey_script()

    # 1. Register with Page.addScriptToEvaluateOnNewDocument to survive page reloads
    try:
        client.send_command("Page.addScriptToEvaluateOnNewDocument", {"source": hotkey_script})
    except Exception:
        # Gracefully handle target environments where Page domain is not active
        pass

    # 2. Evaluate in active document context
    expr = f"""
    (() => {{
        try {{
            // Install hotkey listener immediately on current document
            {hotkey_script}

            // Set developer flags in localStorage with safe try-catch for unhydrated origins
            const key = "{FLAG_OVERRIDES_KEY}";
            let current = {{}};
            try {{
                const raw = localStorage.getItem(key);
                if (raw) {{
                    current = JSON.parse(raw);
                }}
                const targetFlags = {flags_json};
                Object.assign(current, targetFlags);
                localStorage.setItem(key, JSON.stringify(current));
                try {{
                    window.dispatchEvent(new StorageEvent("storage", {{ key: key, newValue: JSON.stringify(current) }}));
                }} catch (_) {{}}
            }} catch (storageErr) {{
                return {{
                    success: false,
                    retry: true,
                    error: (storageErr && storageErr.toString) ? storageErr.toString() : String(storageErr)
                }};
            }}

            // Determine open/toggle state
            const url = new URL(window.location.href);
            const openView = {open_view_json};
            const isToggle = {toggle_json};
            const currentVal = url.searchParams.get("trajectoryDebugOpen");
            let isOpen = currentVal === "true";

            if (openView) {{
                const nextState = isToggle ? (currentVal === "true" ? "false" : "true") : "true";
                url.searchParams.set("trajectoryDebugOpen", nextState);
                window.history.pushState({{}}, "", url.toString());
                window.dispatchEvent(new PopStateEvent("popstate"));
                isOpen = nextState === "true";
            }}

            return {{
                success: true,
                flags: current,
                url: url.toString(),
                open: isOpen,
                hotkey_registered: true
            }};
        }} catch (e) {{
            return {{
                success: false,
                retry: true,
                error: (e && e.toString) ? e.toString() : String(e)
            }};
        }}
    }})()
    """
    res = client.evaluate(expr)
    if isinstance(res, dict) and res.get("success"):
        return res
    if isinstance(res, dict) and "error" in res:
        raise CDPError(f"Failed to inject trajectory debug flags: {res['error']}")
    raise CDPError(f"Failed to inject trajectory debug flags: {res}")


def inject_telemetry_hud(
    client: CDPWebSocketClient,
    tokens: int,
    burn_rate: float = 0.0,
    mins_to_compaction: Optional[float] = None,
    velocity_tier: Optional[str] = None,
    remove: bool = False,
) -> Dict[str, Any]:
    """
    Injects or removes a real-time floating token velocity telemetry HUD in Google Antigravity GUI.
    """
    if remove:
        expr = """
        (() => {
            const el = document.getElementById("agyis-telemetry-hud");
            if (el) {
                el.remove();
                return { success: true, removed: true, injected: false };
            }
            return { success: true, removed: false, injected: false };
        })()
        """
        res = client.evaluate(expr)
        if isinstance(res, dict):
            return res
        return {"success": True, "removed": bool(res), "injected": False}

    tier = (velocity_tier or "SAFE").upper()
    if not velocity_tier:
        if burn_rate >= 4000.0:
            tier = "CRITICAL"
        elif burn_rate >= 2000.0:
            tier = "ELEVATED"
        else:
            tier = "SAFE"

    if tier == "CRITICAL":
        border_color = "#ef4444"
        bg_color = "rgba(40, 16, 16, 0.92)"
        text_color = "#f87171"
        badge_bg = "rgba(239, 68, 68, 0.25)"
    elif tier == "ELEVATED":
        border_color = "#f59e0b"
        bg_color = "rgba(40, 30, 16, 0.92)"
        text_color = "#fbbf24"
        badge_bg = "rgba(245, 158, 11, 0.25)"
    else:
        border_color = "#22c55e"
        bg_color = "rgba(15, 23, 42, 0.92)"
        text_color = "#4ade80"
        badge_bg = "rgba(34, 197, 94, 0.2)"

    rate_str = f"+{int(round(burn_rate)):,} tok/min" if burn_rate > 0 else "+0 tok/min"
    horizon_str = f"~{int(round(mins_to_compaction))}m to 50k" if mins_to_compaction is not None else "Nominal"

    hud_data = {
        "tokens": f"{tokens:,}",
        "burn_rate": rate_str,
        "horizon": horizon_str,
        "tier": tier,
        "border_color": border_color,
        "bg_color": bg_color,
        "text_color": text_color,
        "badge_bg": badge_bg,
    }
    hud_json = json.dumps(hud_data)

    expr = f"""
    (() => {{
        try {{
            const data = {hud_json};
            let hud = document.getElementById("agyis-telemetry-hud");
            if (!hud) {{
                hud = document.createElement("div");
                hud.id = "agyis-telemetry-hud";
                hud.style.position = "fixed";
                hud.style.top = "12px";
                hud.style.right = "16px";
                hud.style.zIndex = "999999";
                hud.style.fontFamily = "-apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, monospace";
                hud.style.fontSize = "11px";
                hud.style.fontWeight = "600";
                hud.style.borderRadius = "8px";
                hud.style.padding = "6px 12px";
                hud.style.boxShadow = "0 4px 12px rgba(0, 0, 0, 0.4)";
                hud.style.display = "flex";
                hud.style.alignItems = "center";
                hud.style.gap = "8px";
                hud.style.pointerEvents = "auto";
                hud.style.cursor = "default";
                hud.style.backdropFilter = "blur(8px)";
                hud.style.transition = "all 0.3s ease";
                document.body.appendChild(hud);
            }}
            hud.style.border = "1px solid " + data.border_color;
            hud.style.backgroundColor = data.bg_color;
            hud.style.color = "#f1f5f9";
            hud.innerHTML = `
                <span style="display:inline-block; width:8px; height:8px; border-radius:50%; background-color:${{data.border_color}};"></span>
                <span>${{data.tokens}} tok</span>
                <span style="color:#94a3b8;">|</span>
                <span style="color:${{data.text_color}};">${{data.burn_rate}}</span>
                <span style="color:#94a3b8;">|</span>
                <span style="color:#cbd5e1;">${{data.horizon}}</span>
                <span style="background-color:${{data.badge_bg}}; color:${{data.text_color}}; padding:2px 6px; border-radius:4px; font-size:10px; text-transform:uppercase;">${{data.tier}}</span>
            `;
            return {{
                success: true,
                removed: false,
                injected: true,
                tokens: data.tokens,
                burn_rate: data.burn_rate,
                tier: data.tier
            }};
        }} catch (err) {{
            return {{
                success: false,
                error: (err && err.toString) ? err.toString() : String(err)
            }};
        }}
    }})()
    """
    res = client.evaluate(expr)
    if isinstance(res, dict) and res.get("success"):
        return res
    if isinstance(res, dict) and "error" in res:
        raise CDPError(f"Failed to inject telemetry HUD: {res['error']}")
    return {"success": True, "removed": False, "injected": True, "tokens": tokens, "burn_rate": burn_rate, "tier": tier}


def cmd_gui(args: argparse.Namespace) -> int:
    """Primary handler for 'agyis gui' subcommand."""
    port_file: Optional[Path] = getattr(args, "port_file", None)
    timeout: float = getattr(args, "timeout", 5.0)
    wait: Optional[float] = getattr(args, "wait", None)
    as_json: bool = getattr(args, "json", False)
    do_devtools: bool = getattr(args, "devtools", False)
    do_trajectory: bool = getattr(args, "trajectory_debug", False)
    do_toggle: bool = getattr(args, "toggle", False)
    no_popup: bool = getattr(args, "no_popup", False)
    verbose: bool = getattr(args, "verbose", False)
    do_hud: bool = getattr(args, "hud", False)
    do_hud_remove: bool = getattr(args, "hud_remove", False)
    hud_result: Optional[Dict[str, Any]] = None

    # Determine default trajectory action
    hud_only = (do_hud or do_hud_remove) and not getattr(args, "trajectory_debug", False) and not getattr(args, "toggle", False)
    if hud_only:
        do_trajectory = False
    elif no_popup and not do_devtools:
        do_trajectory = True
    elif not do_devtools and not do_trajectory and not do_toggle:
        do_trajectory = True
    elif do_toggle:
        do_trajectory = True

    # 1. Inspect Port File, Query Targets, and Connect/Inject with retry budget
    deadline = (time.time() + wait) if (wait is not None and wait > 0) else 0.0

    port: int = 0
    browser_target: str = ""
    targets: List[Dict[str, Any]] = []
    target: Optional[Dict[str, Any]] = None
    trajectory_result: Optional[Dict[str, Any]] = None

    last_phase = "port"  # "port", "connection", "page", "injection"
    last_error: Optional[Exception] = None
    first_pass = True

    while first_pass or time.time() < deadline:
        first_pass = False
        try:
            last_phase = "port"
            port, browser_target = get_devtools_active_port(port_file)

            last_phase = "connection"
            targets = get_cdp_targets(port, timeout=min(timeout, 2.0))

            last_phase = "page"
            cur_target = find_page_target(targets)
            if not cur_target or not cur_target.get("webSocketDebuggerUrl"):
                raise CDPTargetNotFoundError(f"No active Antigravity page target found on 127.0.0.1:{port}")

            if wait is not None and wait > 0:
                target_url = cur_target.get("url", "")
                if target_url.startswith("about:blank") or "127.0.0.1:" not in target_url:
                    raise CDPTargetNotFoundError(f"Page target not fully hydrated ({target_url})")

            target = cur_target

            # 2. Trajectory Debug Injection inside retry loop
            if do_trajectory:
                last_phase = "injection"
                ws_url = target["webSocketDebuggerUrl"]
                client = CDPWebSocketClient(timeout=timeout)
                try:
                    client.connect(ws_url)
                    trajectory_result = inject_trajectory_debug(
                        client,
                        toggle=do_toggle,
                        open_view=(not no_popup),
                    )
                finally:
                    client.close()

            # 3. HUD Injection / Removal
            if do_hud or do_hud_remove:
                last_phase = "injection"
                ws_url = target["webSocketDebuggerUrl"]
                client = CDPWebSocketClient(timeout=timeout)
                try:
                    client.connect(ws_url)
                    if do_hud_remove:
                        hud_result = inject_telemetry_hud(client, tokens=0, remove=True)
                    else:
                        from harness.hooks.token_proximity_guard import (
                            get_active_conversation_token_velocity,
                            get_active_conversation_tokens,
                            get_conversations_dir,
                        )
                        c_id = os.environ.get("ANTIGRAVITY_CONVERSATION_ID") or os.environ.get("CONVERSATION_ID")
                        if not c_id:
                            c_dir = get_conversations_dir()
                            if c_dir.is_dir():
                                dbs = sorted([f for f in c_dir.glob("*.db") if not f.name.endswith(".tmp")], key=lambda f: f.stat().st_mtime, reverse=True)
                                if dbs:
                                    c_id = dbs[0].stem
                        c_id = c_id or "default"
                        vel = get_active_conversation_token_velocity(c_id)
                        t_cnt = vel.get("tokens", 0)
                        if t_cnt <= 0:
                            t_cnt = get_active_conversation_tokens(c_id)
                        hud_result = inject_telemetry_hud(
                            client,
                            tokens=t_cnt,
                            burn_rate=vel.get("burn_rate_tokens_per_min", 0.0),
                            mins_to_compaction=vel.get("mins_to_50k"),
                            velocity_tier=vel.get("velocity_tier"),
                            remove=False,
                        )
                finally:
                    client.close()

            # Successfully completed required actions
            break
        except Exception as exc:
            last_error = exc
            if time.time() < deadline:
                if verbose:
                    sys.stderr.write(f"[agyis gui] Retrying after {last_phase} error: {exc}\n")
                    sys.stderr.flush()
                time.sleep(0.5)
                continue
            break

    success = (trajectory_result is not None) if do_trajectory else ((hud_result is not None) if (do_hud or do_hud_remove) else (target is not None and bool(target.get("webSocketDebuggerUrl"))))

    # Report failure if target not found or injection failed
    if not success or target is None:
        if last_phase == "port":
            is_headless = not os.environ.get("DISPLAY") and not os.environ.get("WAYLAND_DISPLAY")
            if as_json:
                print(json.dumps({
                    "status": "error",
                    "error": "port_file_not_found",
                    "message": str(last_error or "DevTools port file not found"),
                    "headless": is_headless,
                }, indent=2))
            else:
                print(f"❌ Could not resolve Antigravity DevTools port: {last_error or 'DevTools port file not found'}")
                if is_headless:
                    print("   (Host environment appears headless: neither DISPLAY nor WAYLAND_DISPLAY is set)")
                print("   Ensure Google Antigravity Desktop GUI is running.")
            return 1
        elif last_phase == "connection":
            if as_json:
                print(json.dumps({
                    "status": "error",
                    "error": "connection_failed",
                    "port": port,
                    "message": str(last_error or "CDP connection failed"),
                }, indent=2))
            else:
                print(f"❌ Failed to connect to CDP endpoint on 127.0.0.1:{port}: {last_error}")
                print("   The DevToolsActivePort file may be stale from a terminated session.")
            return 1
        elif last_phase == "page":
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
        else:  # last_phase == "injection"
            if as_json:
                print(json.dumps({
                    "status": "error",
                    "error": "injection_failed",
                    "port": port,
                    "message": str(last_error or "CDP injection failed"),
                }, indent=2))
            else:
                print(f"❌ Failed to inject trajectory debug flags via CDP: {last_error}")
            return 1

    urls = format_devtools_urls(port, target)

    # 3. Output Formatting
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
        if hud_result is not None:
            payload["hud"] = hud_result
        print(json.dumps(payload, indent=2))
        return 0

    print("=" * 70)
    print(" 🛡️ Google Antigravity GUI Telemetry & DevTools CDP Controller")
    print("=" * 70)
    print(f" DevTools Port:      {port} (active loopback)")
    print(f" Active Window:      {target.get('title')}")
    print(f" Webview URL:        {target.get('url')}")
    print(f" WebSocket Endpoint: {target.get('webSocketDebuggerUrl')}")

    if hud_result is not None:
        print("-" * 70)
        if do_hud_remove:
            print(" ✔ Real-time telemetry HUD removed from Antigravity GUI.")
        else:
            print(f" ✔ Real-time telemetry HUD injected into Antigravity GUI ({hud_result.get('tokens', '0')} tokens, {hud_result.get('burn_rate', '0 tok/min')}, tier: {hud_result.get('tier', 'SAFE')})")

    if trajectory_result is not None:
        print("-" * 70)
        is_open = trajectory_result.get("open", True)
        if no_popup:
            print(" ✔ Trajectory Debug shortcuts and Command Palette flags primed successfully (modal popup suppressed)")
            print("   • Injected flags: 'enable-trajectory-debug-tools', 'enable-developer-mode'")
            print("   • Command Palette: 'Developer: Trajectory Debug View' is visible")
            print("   • Keyboard hotkey active: [F12] or [Ctrl+Shift+T] directly toggle modal inside Antigravity.")
        else:
            state_str = "unlocked" if is_open else "closed"
            print(f" ✔ Trajectory Debug View {state_str} successfully:")
            print("   • Injected flags: 'enable-trajectory-debug-tools', 'enable-developer-mode'")
            print(f"   • Dispatched URL parameter: ?trajectoryDebugOpen={'true' if is_open else 'false'}")
            print("   • Keyboard hotkey active: [F12] or [Ctrl+Shift+T] directly toggle modal inside Antigravity.")

    if do_devtools or not do_trajectory:
        print("-" * 70)
        print(" DevTools Inspection Guides:")
        print(f"   • Chrome Inspect:       {urls['chrome_inspect_url']}")
        if urls["devtools_frontend_url"]:
            print(f"   • Direct Web Inspector: {urls['devtools_frontend_url']}")
        if urls["bundled_inspector_url"]:
            print(f"   • Bundled URL:          {urls['bundled_inspector_url']}")

    print("-" * 70)
    print(" Quick Controls:")
    print("   • agyis gui          : Open trajectory debug view (default)")
    print("   • agyis gui --no-popup : Prime shortcuts and flags without opening modal")
    print("   • agyis gui --toggle : Toggle open/closed state")
    print("   • In-window hotkey   : Press F12 or Ctrl+Shift+T inside Antigravity")
    print("   • agyis gui --devtools : Display DevTools inspector connection endpoints")
    print("=" * 70)
    return 0
