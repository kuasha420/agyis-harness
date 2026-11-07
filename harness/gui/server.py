# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Arafat Zahan (@kuasha420)
# Corporate Stewardship & Infrastructure: Purrfect Software Limited (PSL)
# Governed by: ICARO-42/b Ordinance (Company-Supported Personal IP Framework)

"""
Dynamic Trajectory HTTP Server (ADR-014 / PSL-INV-010).
Serves live conversation trajectory data and recent conversation lists over HTTP
to decouple the In-Situ Trajectory HUD from static point-in-time snapshots.
"""

from __future__ import annotations

import http.server
import json
import logging
import os
from pathlib import Path
import socket
import threading
from typing import Any, Dict, List, Optional
import urllib.parse
import urllib.request

from harness.gui.trajectory_hud import (
    get_recent_conversations,
    load_conversation_trajectory,
)

DEFAULT_TRAJECTORY_PORT = 40624
DEFAULT_HOST = "127.0.0.1"

logger = logging.getLogger("harness.gui.server")


class TrajectoryRequestHandler(http.server.BaseHTTPRequestHandler):
    """HTTP request handler providing CORS-enabled trajectory endpoints."""

    brain_dir: Optional[Path] = None

    def log_message(self, format: str, *args: Any) -> None:
        """Suppress standard stderr request noise."""
        pass

    def _send_cors_headers(self) -> None:
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "*")

    def do_OPTIONS(self) -> None:
        self.send_response(204)
        self._send_cors_headers()
        self.end_headers()

    def do_GET(self) -> None:
        parsed_url = urllib.parse.urlparse(self.path)
        path = parsed_url.path
        query = urllib.parse.parse_qs(parsed_url.query)

        if path == "/health":
            payload = {"status": "ok", "port": self.server.server_port}
            self._write_json(200, payload)
            return

        if path == "/api/trajectory":
            convo_ids = query.get("id") or query.get("conversation_id")
            if not convo_ids or not convo_ids[0].strip():
                self._write_json(400, {"error": "Missing required query parameter: id"})
                return

            convo_id = convo_ids[0].strip()
            parent_ids = query.get("parent_id")
            parent_id = parent_ids[0].strip() if parent_ids else None

            try:
                data = load_conversation_trajectory(
                    convo_id,
                    brain_dir=self.brain_dir,
                    parent_id=parent_id,
                )
                self._write_json(200, data)
            except Exception as exc:
                self._write_json(500, {"error": str(exc), "convo_id": convo_id})
            return

        if path == "/api/conversations":
            limit_val = 30
            if "limit" in query:
                try:
                    limit_val = int(query["limit"][0])
                except (ValueError, IndexError):
                    limit_val = 30

            try:
                convos = get_recent_conversations(brain_dir=self.brain_dir, limit=limit_val)
                self._write_json(200, {"conversations": convos, "count": len(convos)})
            except Exception as exc:
                self._write_json(500, {"error": str(exc)})
            return

        self._write_json(404, {"error": "Not Found", "path": path})

    def _write_json(self, status_code: int, data: Any) -> None:
        encoded = json.dumps(data).encode("utf-8")
        self.send_response(status_code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(encoded)))
        self._send_cors_headers()
        self.end_headers()
        self.wfile.write(encoded)


class TrajectoryServer(http.server.ThreadingHTTPServer):
    """Threading HTTP server configured for trajectory servicing."""
    daemon_threads = True
    allow_reuse_address = True

    def __init__(
        self,
        server_address: tuple[str, int],
        RequestHandlerClass: type[TrajectoryRequestHandler] = TrajectoryRequestHandler,
        brain_dir: Optional[Path] = None,
    ):
        self.brain_dir = brain_dir
        # Subclass request handler to pass brain_dir
        class ConfiguredHandler(RequestHandlerClass):
            brain_dir = self.brain_dir

        super().__init__(server_address, ConfiguredHandler)


def is_server_alive(host: str = DEFAULT_HOST, port: int = DEFAULT_TRAJECTORY_PORT, timeout: float = 0.5) -> bool:
    """Checks if the Trajectory HTTP server is responding to /health."""
    url = f"http://{host}:{port}/health"
    try:
        req = urllib.request.Request(url, method="GET")
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            if resp.status == 200:
                data = json.loads(resp.read().decode("utf-8"))
                return data.get("status") == "ok"
    except (urllib.error.URLError, socket.timeout, TimeoutError, OSError, ValueError):
        pass
    return False


def start_trajectory_server(
    host: str = DEFAULT_HOST,
    port: int = DEFAULT_TRAJECTORY_PORT,
    brain_dir: Optional[Path] = None,
) -> TrajectoryServer:
    """Creates and starts the TrajectoryServer on a background daemon thread."""
    server = TrajectoryServer((host, port), RequestHandlerClass=TrajectoryRequestHandler, brain_dir=brain_dir)
    thread = threading.Thread(target=server.serve_forever, daemon=True, name="AgyisTrajectoryServer")
    thread.start()
    return server


def ensure_trajectory_server(
    host: str = DEFAULT_HOST,
    port: int = DEFAULT_TRAJECTORY_PORT,
    brain_dir: Optional[Path] = None,
) -> Optional[TrajectoryServer]:
    """Ensures that the trajectory server is alive; starts one if not."""
    if is_server_alive(host=host, port=port):
        return None
    try:
        return start_trajectory_server(host=host, port=port, brain_dir=brain_dir)
    except OSError:
        # May have raced with another process binding the port
        if is_server_alive(host=host, port=port):
            return None
        raise
