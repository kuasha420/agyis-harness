# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Arafat Zahan (@kuasha420)
# Corporate Stewardship & Infrastructure: Purrfect Software Limited (PSL)
# Governed by: ICARO-42/b Ordinance (Company-Supported Personal IP Framework)

"""
Dynamic Trajectory HTTP Server (ADR-014 / PSL-INV-007).
Serves live conversation trajectory data and recent conversation lists over HTTP
for offline/headless trajectory playback and external browser inspection.

Note (D1-MIN-01): Port 40624 HTTP server is reserved for offline/headless playback only;
the live in-situ Electron HUD connects to ConnectRPC port 40623 directly.
"""

from __future__ import annotations

from collections import OrderedDict
import http.server
import json
import logging
import os
from pathlib import Path
import socket
import subprocess
import sys
import threading
import time
from typing import Any, Dict, Optional, Tuple
import urllib.error
import urllib.parse
import urllib.request

from harness.gui.trajectory_hud import (
    get_recent_conversations,
    load_conversation_trajectory,
)
from harness.trajectory.transcript_reader import find_transcript_path
from harness.utils.context import get_active_brain_dir

DEFAULT_TRAJECTORY_PORT = 40624
DEFAULT_HOST = "127.0.0.1"

logger = logging.getLogger("harness.gui.server")

# Bounded, thread-safe trajectory cache:
# cache_key -> (mtime_ns, size, sibling_mtime_ns, sibling_size, trajectory_data)
_MAX_TRAJECTORY_CACHE_SIZE = 32
_MAX_TRAJECTORY_CACHE_BYTES = 64 * 1024 * 1024
_TRAJECTORY_CACHE_LOCK = threading.Lock()
_TRAJECTORY_CACHE: "OrderedDict[str, Tuple[int, int, int, int, Dict[str, Any]]]" = OrderedDict()

_ALLOWED_LOOPBACK_HOSTS = frozenset({"127.0.0.1", "localhost", "::1"})


def _is_allowed_origin(origin: str) -> bool:
    """Returns True only for localhost, 127.0.0.1, [::1], vscode-file://, or file:// origins."""
    if not origin:
        return False
    try:
        parsed = urllib.parse.urlparse(origin)
    except ValueError:
        return False
    scheme = (parsed.scheme or "").lower()
    if scheme in ("vscode-file", "file"):
        return True
    if scheme in ("http", "https"):
        host = (parsed.hostname or "").lower()
        return host in _ALLOWED_LOOPBACK_HOSTS
    return False


def _resolve_brain_dir(brain_dir: Optional[Path] = None) -> Path:
    """Resolves active brain directory using canonical Antigravity/Gemini/Agyis env vars."""
    if brain_dir is not None:
        return Path(brain_dir)
    for key in ("ANTIGRAVITY_BRAIN_DIR", "ANTIGRAVITY_APP_DATA_DIR", "GEMINI_BRAIN_DIR"):
        if (os.environ.get(key) or "").strip():
            return get_active_brain_dir(None)
    env_agyis = (os.environ.get("AGYIS_BRAIN_DIR") or "").strip()
    if env_agyis:
        return Path(env_agyis)
    return get_active_brain_dir(None)


def _validate_convo_id(convo_id: str, base_brain: Path) -> str:
    """Validates decoded conversation ID against directory traversal outside base_brain."""
    cleaned = convo_id.strip()
    if (
        not cleaned
        or cleaned in (".", "..")
        or "/" in cleaned
        or "\\" in cleaned
        or "\x00" in cleaned
        or ".." in cleaned
    ):
        raise ValueError(f"Invalid conversation id: {convo_id!r}")
    resolved_base = base_brain.resolve()
    resolved_target = (resolved_base / cleaned).resolve()
    if resolved_target == resolved_base or not resolved_target.is_relative_to(resolved_base):
        raise ValueError(f"Conversation path escapes brain directory: {convo_id!r}")
    return cleaned


def get_cached_trajectory(
    convo_id: str,
    brain_dir: Optional[Path] = None,
    parent_id: Optional[str] = None,
) -> Dict[str, Any]:
    """Loads trajectory using thread-safe, bounded mtime/size caching (ADR-014 / PSL-INV-007)."""
    base_brain = _resolve_brain_dir(brain_dir)
    clean_id = _validate_convo_id(convo_id, base_brain)
    clean_parent: Optional[str] = None
    if parent_id is not None and parent_id.strip():
        clean_parent = _validate_convo_id(parent_id, base_brain)

    transcript_path, _ = find_transcript_path(clean_id, brain_dir=base_brain)
    if transcript_path is None:
        convo_dir = base_brain / clean_id
        transcript_path = convo_dir / ".system_generated" / "logs" / "transcript.jsonl"
        if not transcript_path.is_file():
            transcript_path = convo_dir / "transcript.jsonl"

    full_path = transcript_path.with_name("transcript_full.jsonl")
    compact_path = transcript_path.with_name("transcript.jsonl")

    t_path_str = str(transcript_path)
    cache_key = t_path_str if not clean_parent else f"{t_path_str}::parent={clean_parent}"
    if transcript_path.is_file():
        try:
            st = os.stat(transcript_path)
            sibling = compact_path if transcript_path.name == "transcript_full.jsonl" else full_path
            sib_st = os.stat(sibling) if sibling.is_file() else None
            s_mtime = sib_st.st_mtime_ns if sib_st else 0
            s_size = sib_st.st_size if sib_st else 0
            with _TRAJECTORY_CACHE_LOCK:
                cached = _TRAJECTORY_CACHE.get(cache_key)
                if cached is not None:
                    c_mtime, c_size, c_smtime, c_ssize, cached_data = cached
                    if (
                        c_mtime == st.st_mtime_ns
                        and c_size == st.st_size
                        and c_smtime == s_mtime
                        and c_ssize == s_size
                    ):
                        _TRAJECTORY_CACHE.move_to_end(cache_key)
                        return cached_data

            data = load_conversation_trajectory(clean_id, brain_dir=base_brain, parent_id=clean_parent)
            with _TRAJECTORY_CACHE_LOCK:
                _TRAJECTORY_CACHE[cache_key] = (st.st_mtime_ns, st.st_size, s_mtime, s_size, data)
                _TRAJECTORY_CACHE.move_to_end(cache_key)
                while len(_TRAJECTORY_CACHE) > _MAX_TRAJECTORY_CACHE_SIZE or (
                    len(_TRAJECTORY_CACHE) > 1
                    and sum(max(entry[1], entry[3], 1024) * 3 for entry in _TRAJECTORY_CACHE.values()) > _MAX_TRAJECTORY_CACHE_BYTES
                ):
                    _TRAJECTORY_CACHE.popitem(last=False)
            return data
        except OSError:
            pass

    return load_conversation_trajectory(clean_id, brain_dir=base_brain, parent_id=clean_parent)


class TrajectoryRequestHandler(http.server.BaseHTTPRequestHandler):
    """HTTP request handler providing restricted-origin trajectory endpoints."""

    brain_dir: Optional[Path] = None

    def log_message(self, format: str, *args: Any) -> None:
        """Suppress standard stderr request noise."""
        pass

    def _request_origin(self) -> str:
        return (self.headers.get("Origin") or "").strip() if self.headers else ""

    def _send_cors_headers(self) -> None:
        origin = self._request_origin()
        self.send_header("Vary", "Origin")
        if _is_allowed_origin(origin):
            self.send_header("Access-Control-Allow-Origin", origin)
        self.send_header("Access-Control-Allow-Methods", "GET, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")

    def _reject_disallowed_origin(self) -> bool:
        origin = self._request_origin()
        if origin and not _is_allowed_origin(origin):
            self._write_json(403, {"error": "Origin not allowed"})
            return True
        return False

    def do_OPTIONS(self) -> None:
        origin = self._request_origin()
        if origin and not _is_allowed_origin(origin):
            self.send_response(403)
            self.send_header("Vary", "Origin")
            self.end_headers()
            return
        self.send_response(204)
        self._send_cors_headers()
        self.end_headers()

    def do_GET(self) -> None:
        if self._reject_disallowed_origin():
            return

        parsed_url = urllib.parse.urlparse(self.path)
        path = parsed_url.path
        query = urllib.parse.parse_qs(parsed_url.query)

        if path == "/health":
            payload = {"status": "ok", "port": self.server.server_port}
            self._write_json(200, payload)
            return

        if path == "/api/trajectory" or path.startswith("/api/trajectory/"):
            convo_id = ""
            if path.startswith("/api/trajectory/"):
                raw_suffix = path[len("/api/trajectory/"):]
                if raw_suffix.endswith("/") and raw_suffix.count("/") == 1:
                    raw_suffix = raw_suffix[:-1]
                convo_id = urllib.parse.unquote(raw_suffix).strip()
            if not convo_id:
                convo_ids = query.get("id") or query.get("conversation_id")
                if convo_ids and convo_ids[0].strip():
                    convo_id = urllib.parse.unquote(convo_ids[0]).strip()

            if not convo_id:
                self._write_json(400, {"error": "Missing required query or path parameter: id"})
                return

            parent_ids = query.get("parent_id")
            parent_id = urllib.parse.unquote(parent_ids[0]).strip() if (parent_ids and parent_ids[0].strip()) else None

            base_brain = _resolve_brain_dir(self.brain_dir)
            try:
                _validate_convo_id(convo_id, base_brain)
                if parent_id is not None:
                    _validate_convo_id(parent_id, base_brain)
            except ValueError as exc:
                self._write_json(400, {"error": str(exc)})
                return

            try:
                data = get_cached_trajectory(
                    convo_id,
                    brain_dir=base_brain,
                    parent_id=parent_id,
                )
                self._write_json(200, data)
            except ValueError as exc:
                self._write_json(400, {"error": str(exc), "convo_id": convo_id})
            except Exception as exc:
                self._write_json(500, {"error": str(exc), "convo_id": convo_id})
            return

        if path == "/api/conversations":
            limit_val = 30
            if "limit" in query:
                try:
                    limit_val = max(1, min(500, int(query["limit"][0])))
                except (ValueError, IndexError):
                    limit_val = 30

            try:
                base_brain = _resolve_brain_dir(self.brain_dir)
                convos = get_recent_conversations(brain_dir=base_brain, limit=limit_val)
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
        self.brain_dir = _resolve_brain_dir(brain_dir) if (
            brain_dir is not None
            or any(
                (os.environ.get(k) or "").strip()
                for k in ("ANTIGRAVITY_BRAIN_DIR", "ANTIGRAVITY_APP_DATA_DIR", "GEMINI_BRAIN_DIR", "AGYIS_BRAIN_DIR")
            )
        ) else None

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
    """Ensures that the trajectory server is alive; starts one as detached background process if not."""
    if is_server_alive(host=host, port=port):
        return None

    cmd = [sys.executable, "-m", "harness.cli", "gui", "--server", "--server-port", str(port)]
    env = os.environ.copy()
    if brain_dir is not None:
        env["ANTIGRAVITY_BRAIN_DIR"] = str(brain_dir)
        env["AGYIS_BRAIN_DIR"] = str(brain_dir)
    try:
        subprocess.Popen(cmd, start_new_session=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, env=env)
        for _ in range(10):
            time.sleep(0.05)
            if is_server_alive(host=host, port=port):
                return None
    except (OSError, subprocess.SubprocessError) as exc:
        logger.warning(f"Failed to spawn detached background trajectory server: {exc}")

    try:
        return start_trajectory_server(host=host, port=port, brain_dir=brain_dir)
    except OSError:
        # May have raced with another process binding the port
        if is_server_alive(host=host, port=port):
            return None
        raise
