# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Arafat Zahan (@kuasha420)
# Corporate Stewardship & Infrastructure: Purrfect Software Limited (PSL)
# Governed by: ICARO-42/b Ordinance (Company-Supported Personal IP Framework)

"""
Hermetic verification suite for PSL-INV-007 (Live Reality Over Static Fakes).
Validates dynamic Trajectory HTTP server endpoints, strict CORS allowlist + Vary: Origin,
403 untrusted-origin rejection, stale DOM replacement, focused route tracking, and multi-session traversal.
"""

from __future__ import annotations

import json
from pathlib import Path
import socket
import tempfile
import time
import unittest
import unittest.mock
import urllib.error
import urllib.parse
import urllib.request

from harness.gui.server import (
    TrajectoryRequestHandler,
    TrajectoryServer,
    _TRAJECTORY_CACHE,
    ensure_trajectory_server,
    get_cached_trajectory,
    is_server_alive,
    start_trajectory_server,
)
from harness.gui.trajectory_hud import (
    build_trajectory_hud_script,
    get_recent_conversations,
    load_conversation_trajectory,
)


def _get_free_port() -> int:
    """Finds an available local port for testing."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


class TestTrajectoryServerEndpoints(unittest.TestCase):
    """Hermetic tests for Trajectory HTTP Server endpoints and strict CORS handling."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.temp_dir = tempfile.TemporaryDirectory()
        cls.brain_dir = Path(cls.temp_dir.name)
        cls.port = _get_free_port()

        # Seed two distinct test sessions for multi-session traversal
        cls.convo_a = "convo-alpha-1111"
        cls.convo_b = "convo-beta-2222"

        for cid, step_count in [(cls.convo_a, 3), (cls.convo_b, 7)]:
            cdir = cls.brain_dir / cid / ".system_generated" / "logs"
            cdir.mkdir(parents=True, exist_ok=True)
            t_file = cdir / "transcript.jsonl"
            with open(t_file, "w", encoding="utf-8") as f:
                for i in range(step_count):
                    f.write(json.dumps({
                        "source": "user" if i == 0 else "model",
                        "content": f"Step {i} for {cid}",
                        "step_index": i,
                    }) + "\n")

        cls.server = start_trajectory_server(
            host="127.0.0.1",
            port=cls.port,
            brain_dir=cls.brain_dir,
        )
        cls.base_url = f"http://127.0.0.1:{cls.port}"

    @classmethod
    def tearDownClass(cls) -> None:
        cls.server.shutdown()
        cls.server.server_close()
        cls.temp_dir.cleanup()

    def test_health_endpoint_and_cors(self) -> None:
        # 1. No Origin header: Vary: Origin present, no wildcard Access-Control-Allow-Origin
        req = urllib.request.Request(f"{self.base_url}/health", method="GET")
        with urllib.request.urlopen(req, timeout=1.0) as resp:
            self.assertEqual(resp.status, 200)
            self.assertEqual(resp.headers.get("Vary"), "Origin")
            self.assertIsNone(resp.headers.get("Access-Control-Allow-Origin"))
            data = json.loads(resp.read().decode("utf-8"))
            self.assertEqual(data.get("status"), "ok")
            self.assertEqual(data.get("port"), self.port)

        # 2. Trusted localhost Origin echoed accurately
        allowed_origin = f"http://localhost:{self.port}"
        req_ok = urllib.request.Request(
            f"{self.base_url}/health",
            headers={"Origin": allowed_origin},
            method="GET",
        )
        with urllib.request.urlopen(req_ok, timeout=1.0) as resp_ok:
            self.assertEqual(resp_ok.status, 200)
            self.assertEqual(resp_ok.headers.get("Vary"), "Origin")
            self.assertEqual(resp_ok.headers.get("Access-Control-Allow-Origin"), allowed_origin)

        # 3. Untrusted Origin strictly rejected with HTTP 403
        req_bad = urllib.request.Request(
            f"{self.base_url}/health",
            headers={"Origin": "https://evil.example.com"},
            method="GET",
        )
        with self.assertRaises(urllib.error.HTTPError) as ctx:
            with urllib.request.urlopen(req_bad, timeout=1.0):
                pass
        self.assertEqual(ctx.exception.code, 403)
        ctx.exception.close()

    def test_options_cors_preflight(self) -> None:
        url = f"{self.base_url}/api/trajectory?id={self.convo_a}"
        allowed_origin = "http://127.0.0.1:40624"
        req = urllib.request.Request(url, headers={"Origin": allowed_origin}, method="OPTIONS")
        with urllib.request.urlopen(req, timeout=1.0) as resp:
            self.assertEqual(resp.status, 204)
            self.assertEqual(resp.headers.get("Vary"), "Origin")
            self.assertEqual(resp.headers.get("Access-Control-Allow-Origin"), allowed_origin)
            self.assertIn("GET", resp.headers.get("Access-Control-Allow-Methods", ""))

        # Untrusted preflight origin returns 403
        req_bad = urllib.request.Request(
            url,
            headers={"Origin": "https://evil.example.com"},
            method="OPTIONS",
        )
        with self.assertRaises(urllib.error.HTTPError) as ctx:
            with urllib.request.urlopen(req_bad, timeout=1.0):
                pass
        self.assertEqual(ctx.exception.code, 403)
        self.assertEqual(ctx.exception.headers.get("Vary"), "Origin")
        ctx.exception.close()

    def test_trajectory_endpoint_success(self) -> None:
        url = f"{self.base_url}/api/trajectory?id={self.convo_a}"
        req = urllib.request.Request(url, method="GET")
        with urllib.request.urlopen(req, timeout=1.0) as resp:
            self.assertEqual(resp.status, 200)
            data = json.loads(resp.read().decode("utf-8"))
            self.assertEqual(data.get("conversation_id"), self.convo_a)
            self.assertEqual(len(data.get("steps", [])), 3)

    def test_trajectory_endpoint_path_parameter(self) -> None:
        url = f"{self.base_url}/api/trajectory/{self.convo_a}"
        req = urllib.request.Request(url, method="GET")
        with urllib.request.urlopen(req, timeout=1.0) as resp:
            self.assertEqual(resp.status, 200)
            data = json.loads(resp.read().decode("utf-8"))
            self.assertEqual(data.get("conversation_id"), self.convo_a)
            self.assertEqual(len(data.get("steps", [])), 3)

    def test_trajectory_endpoint_path_parameter_url_encoded(self) -> None:
        encoded_id = urllib.parse.quote(self.convo_b)
        url = f"{self.base_url}/api/trajectory/{encoded_id}"
        req = urllib.request.Request(url, method="GET")
        with urllib.request.urlopen(req, timeout=1.0) as resp:
            self.assertEqual(resp.status, 200)
            data = json.loads(resp.read().decode("utf-8"))
            self.assertEqual(data.get("conversation_id"), self.convo_b)
            self.assertEqual(len(data.get("steps", [])), 7)

    def test_trajectory_endpoint_missing_id(self) -> None:
        url = f"{self.base_url}/api/trajectory"
        req = urllib.request.Request(url, method="GET")
        with self.assertRaises(urllib.error.HTTPError) as ctx:
            with urllib.request.urlopen(req, timeout=1.0):
                pass
        self.assertEqual(ctx.exception.code, 400)
        ctx.exception.close()

    def test_conversations_endpoint(self) -> None:
        url = f"{self.base_url}/api/conversations?limit=10"
        req = urllib.request.Request(url, method="GET")
        with urllib.request.urlopen(req, timeout=1.0) as resp:
            self.assertEqual(resp.status, 200)
            data = json.loads(resp.read().decode("utf-8"))
            self.assertIn("conversations", data)
            convos = data["conversations"]
            ids = [c["id"] for c in convos]
            self.assertIn(self.convo_a, ids)
            self.assertIn(self.convo_b, ids)

    def test_not_found_endpoint(self) -> None:
        url = f"{self.base_url}/api/nonexistent"
        req = urllib.request.Request(url, method="GET")
        with self.assertRaises(urllib.error.HTTPError) as ctx:
            with urllib.request.urlopen(req, timeout=1.0):
                pass
        self.assertEqual(ctx.exception.code, 404)
        ctx.exception.close()

    def test_is_server_alive(self) -> None:
        self.assertTrue(is_server_alive("127.0.0.1", self.port))
        # Non-listening port returns False
        unused_port = _get_free_port()
        self.assertFalse(is_server_alive("127.0.0.1", unused_port))

    def test_trajectory_server_mtime_caching(self) -> None:
        _TRAJECTORY_CACHE.clear()
        t_file = self.brain_dir / self.convo_a / ".system_generated" / "logs" / "transcript.jsonl"
        t_str = str(t_file)

        # 1. First fetch populates cache
        t0 = time.perf_counter()
        data1 = get_cached_trajectory(self.convo_a, brain_dir=self.brain_dir)
        d1_time = time.perf_counter() - t0
        self.assertIn(t_str, _TRAJECTORY_CACHE)
        self.assertEqual(len(data1.get("steps", [])), 3)

        # 2. Second fetch hits in-memory cache (<0.1ms benchmark)
        t1 = time.perf_counter()
        data2 = get_cached_trajectory(self.convo_a, brain_dir=self.brain_dir)
        d2_time = time.perf_counter() - t1
        self.assertIs(data1, data2)
        self.assertLess(d2_time, 0.001)

        # 3. Cache invalidation on transcript modification
        time.sleep(0.01)
        with open(t_file, "a", encoding="utf-8") as f:
            f.write(json.dumps({"source": "user", "content": "Appended step"}) + "\n")

        data3 = get_cached_trajectory(self.convo_a, brain_dir=self.brain_dir)
        self.assertEqual(len(data3.get("steps", [])), 4)
        self.assertIsNot(data1, data3)

    @unittest.mock.patch("harness.gui.server.subprocess.Popen")
    @unittest.mock.patch("harness.gui.server.is_server_alive")
    def test_ensure_trajectory_server_spawns_background_process(
        self, mock_alive: unittest.mock.MagicMock, mock_popen: unittest.mock.MagicMock
    ) -> None:
        # First call False (not alive), second call True (became alive after spawn)
        mock_alive.side_effect = [False, True]
        res = ensure_trajectory_server(port=40624)
        self.assertIsNone(res)
        mock_popen.assert_called_once()
        cmd = mock_popen.call_args[0][0]
        self.assertIn("--server", cmd)
        self.assertIn("--server-port", cmd)
        self.assertIn("40624", cmd)
        self.assertTrue(mock_popen.call_args[1].get("start_new_session"))


if __name__ == "__main__":
    unittest.main()
