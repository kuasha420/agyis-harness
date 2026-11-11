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
import importlib.resources
import json
import os
from pathlib import Path
import sys
import time
from typing import Any, Dict, List, Optional, Union

from harness.gui.cdp import (  # noqa: F401
    CDPConnectionError,
    CDPError,
    CDPTargetNotFoundError,
    CDPTimeoutError,
    CDPWebSocketClient,
    DEFAULT_DEVTOOLS_PORT_FILE,
    find_page_target,
    format_devtools_urls,
    get_cdp_targets,
    get_devtools_active_port,
)
from harness.gui.systemd import (  # noqa: F401
    GUI_PATH_UNIT,
    GUI_SERVICE_UNIT,
    _run_gui_systemctl,
    generate_gui_systemd_path_unit,
    generate_gui_systemd_service_unit,
    get_gui_systemd_unit_dir,
    handle_gui_service_command as _systemd_handle_gui_service_command,
)

FLAG_OVERRIDES_KEY = "jetski.developer.customFlagOverrides"
DEFAULT_TARGET_FLAGS = {
    "enable-trajectory-debug-tools": True,
    "enable-developer-mode": True,
}


def _load_gui_asset(name: str) -> str:
    """Loads a GUI JavaScript/CSS asset cleanly from package resources (PSL-INV-011)."""
    return importlib.resources.files("harness.gui.assets").joinpath(name).read_text(encoding="utf-8")


def build_hotkey_script() -> str:
    """
    Loads the JavaScript snippet to listen for F12, Ctrl+Shift+T, and Esc hotkeys
    and directly toggle the In-Situ Trajectory Debug HUD element ('agyis-trajectory-hud').
    """
    return _load_gui_asset("hotkey.js")


def inject_trajectory_debug(
    client: CDPWebSocketClient,
    flags: Optional[Dict[str, bool]] = None,
    toggle: bool = False,
    open_view: bool = True,
    conversation_id: Optional[str] = None,
    brain_dir: Optional[Path] = None,
) -> Dict[str, Any]:
    """
    Injects developer custom flag overrides into localStorage, mounts/toggles
    the In-Situ Trajectory Debug HUD in the Antigravity GUI, and installs hotkey listeners
    (F12, Ctrl+Shift+T, Esc) surviving page reloads (ADR-014 / PSL-INV-007).
    """
    import re
    from harness.gui.trajectory_hud import (
        build_trajectory_hud_script,
        get_recent_conversations,
        load_conversation_trajectory,
    )

    target_flags = flags or DEFAULT_TARGET_FLAGS
    flags_json = json.dumps(target_flags)

    # 1. Resolve active conversation ID from page context or live workspace session
    convo_id = conversation_id
    page_url: Optional[str] = None
    if not convo_id:
        try:
            page_url = client.evaluate("window.location.href")
            if isinstance(page_url, str):
                m = re.search(r"/c/([a-zA-Z0-9_-]+)", page_url)
                if m:
                    convo_id = m.group(1)
        except (CDPError, TimeoutError, OSError):
            pass

    conversations = get_recent_conversations(brain_dir=brain_dir)
    if not convo_id:
        from harness.utils.context import get_active_conversation_id

        active_cid = get_active_conversation_id() if brain_dir is None else "default"
        if active_cid and active_cid != "default":
            convo_id = active_cid
        elif conversations:
            convo_id = str(conversations[0].get("id") or "").strip()
        if not convo_id:
            convo_id = "active-session"

    # 2. Load trajectory data
    trajectory_data = load_conversation_trajectory(convo_id, brain_dir=brain_dir)

    # 3. Build in-situ Trajectory Debug HUD script
    hud_script = build_trajectory_hud_script(
        convo_id=convo_id,
        trajectory_data=trajectory_data,
        conversations=conversations,
        open_view=open_view,
        toggle=toggle,
    )

    # 4. Register hotkey and persistent navigation script with Page.addScriptToEvaluateOnNewDocument
    hotkey_script = build_hotkey_script()
    persistent_script = _load_gui_asset("hotkey_persistent.js").replace("/* __HOTKEY_SCRIPT__ */", hotkey_script)
    try:
        client.send_command("Page.addScriptToEvaluateOnNewDocument", {"source": persistent_script})
    except Exception:
        pass

    # 5. Set developer flags in localStorage for runtime backwards-compatibility
    flags_expr = (
        _load_gui_asset("flags_override.js")
        .replace("__FLAG_KEY__", FLAG_OVERRIDES_KEY)
        .replace("__FLAGS_JSON__", flags_json)
    )
    try:
        client.evaluate(flags_expr)
    except Exception:
        pass

    # 6. Evaluate HUD script in active document
    res = client.evaluate(hud_script)
    if isinstance(res, dict) and not res.get("success", True):
        err = res.get("error", "Unknown evaluation error")
        raise CDPError(f"Failed to inject trajectory debug HUD: {err}")

    is_open = res.get("open", open_view) if isinstance(res, dict) else open_view
    page_url_str = page_url if isinstance(page_url, str) else "https://127.0.0.1:37277/"
    resolved_url = page_url_str
    if is_open and "trajectoryDebugOpen" not in resolved_url:
        delim = "&" if "?" in resolved_url else "?"
        resolved_url = f"{resolved_url}{delim}trajectoryDebugOpen=true"

    return {
        "success": True,
        "flags": target_flags,
        "open": is_open,
        "url": resolved_url,
        "convo_id": convo_id,
        "steps": trajectory_data.get("step_count", 0),
        "hotkey_registered": True,
    }


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
        expr = _load_gui_asset("telemetry_hud.js").replace("__HUD_DATA__", json.dumps({"remove": True}), 1)
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
    horizon_str = f"~{int(round(mins_to_compaction))}m to compaction" if mins_to_compaction is not None else "Nominal"

    hud_data = {
        "remove": False,
        "tokens": f"{tokens:,}",
        "burn_rate": rate_str,
        "horizon": horizon_str,
        "tier": tier,
        "border_color": border_color,
        "bg_color": bg_color,
        "text_color": text_color,
        "badge_bg": badge_bg,
    }
    expr = _load_gui_asset("telemetry_hud.js").replace("__HUD_DATA__", json.dumps(hud_data), 1)
    res = client.evaluate(expr)
    if isinstance(res, dict) and res.get("success"):
        return res
    if isinstance(res, dict) and "error" in res:
        raise CDPError(f"Failed to inject telemetry HUD: {res['error']}")
    return {"success": True, "removed": False, "injected": True, "tokens": tokens, "burn_rate": burn_rate, "tier": tier}


def handle_gui_service_command(
    action: str,
    json_output: bool = False,
    unit_dir: Optional[Union[str, Path]] = None,
    working_dir: Optional[Union[str, Path]] = None,
) -> int:
    """Manage systemd user path and service units for Trajectory Debug HUD."""
    return _systemd_handle_gui_service_command(
        action=action,
        json_output=json_output,
        unit_dir=unit_dir,
        working_dir=working_dir,
        run_systemctl=_run_gui_systemctl,
    )


def cmd_gui(args: argparse.Namespace) -> int:
    """Primary handler for 'agyis gui' subcommand.
    
    Note (D1-MIN-01): The --server option (port 40624) starts an HTTP API server
    reserved for offline/headless playback and external browser inspection.
    The in-situ Electron HUD operates via ConnectRPC port 40623 directly.
    """
    if getattr(args, "server", False):
        from harness.gui.server import TrajectoryServer, TrajectoryRequestHandler, DEFAULT_TRAJECTORY_PORT, DEFAULT_HOST
        server_port = getattr(args, "server_port", None) or DEFAULT_TRAJECTORY_PORT
        server = TrajectoryServer((DEFAULT_HOST, server_port), RequestHandlerClass=TrajectoryRequestHandler)
        if not getattr(args, "json", False):
            print(f"● Trajectory API server (offline/headless playback) listening on http://{DEFAULT_HOST}:{server_port}")
        else:
            print(json.dumps({"status": "running", "host": DEFAULT_HOST, "port": server_port, "mode": "offline_playback"}))
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            pass
        finally:
            server.server_close()
        return 0

    service_action: Optional[str] = getattr(args, "service", None)
    if service_action:
        return handle_gui_service_command(
            action=service_action,
            json_output=getattr(args, "json", False),
        )

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

                # If waiting and page title is still empty (splash phase), await window hydration
                target_title = (cur_target.get("title") or "").strip()
                if not target_title and (deadline - time.time()) > 2.0:
                    raise CDPTargetNotFoundError(
                        f"Page target title not yet populated ({target_url}), awaiting window hydration"
                    )

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
                        from harness.utils.context import get_active_conversation_id

                        c_id = get_active_conversation_id() or os.environ.get("CONVERSATION_ID")
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
                        mins_left = vel.get("mins_to_compaction")
                        if mins_left is None:
                            mins_left = vel.get("mins_to_50k")
                        hud_result = inject_telemetry_hud(
                            client,
                            tokens=t_cnt,
                            burn_rate=vel.get("burn_rate_tokens_per_min", 0.0),
                            mins_to_compaction=mins_left,
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
            convo_label = trajectory_result.get("convo_id", "active")
            step_count = trajectory_result.get("steps", 0)
            print(f" ✔ Trajectory Debug View {state_str} successfully (In-Situ HUD, {step_count} steps, conversation: {convo_label[:12]}...):")
            print("   • Cleanroom HUD mounted into Antigravity Electron DOM")
            print("   • Injected flags: 'enable-trajectory-debug-tools', 'enable-developer-mode'")
            print("   • Keyboard hotkey active: [F12], [Ctrl+Shift+T], or [Esc] to toggle/close")
            print("   • Arrow keys: [Left] / [Right] navigate step cards")

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
