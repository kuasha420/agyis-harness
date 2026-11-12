# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Arafat Zahan (@kuasha420)
# Corporate Stewardship & Infrastructure: Purrfect Software Limited (PSL)
# Governed by: ICARO-42/b Ordinance (Company-Supported Personal IP Framework)

"""
Hermetic verification suite for PSL-INV-010 (Anti-Vibe-Coding & Dynamic Lifecycle Invariant).
Validates dynamic Trajectory HTTP server endpoints, CORS headers, stale DOM replacement,
focused route tracking, and multi-session traversal.
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
    """Hermetic tests for Trajectory HTTP Server endpoints and CORS handling."""

    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.brain_dir = Path(self.temp_dir.name)
        self.port = _get_free_port()

        # Seed two distinct test sessions for multi-session traversal
        self.convo_a = "convo-alpha-1111"
        self.convo_b = "convo-beta-2222"

        for cid, step_count in [(self.convo_a, 3), (self.convo_b, 7)]:
            cdir = self.brain_dir / cid / ".system_generated" / "logs"
            cdir.mkdir(parents=True, exist_ok=True)
            t_file = cdir / "transcript.jsonl"
            with open(t_file, "w", encoding="utf-8") as f:
                for i in range(step_count):
                    f.write(json.dumps({
                        "source": "user" if i == 0 else "model",
                        "content": f"Step {i} for {cid}",
                        "step_index": i,
                    }) + "\n")

        self.server = start_trajectory_server(
            host="127.0.0.1",
            port=self.port,
            brain_dir=self.brain_dir,
        )
        self.base_url = f"http://127.0.0.1:{self.port}"

    def tearDown(self) -> None:
        self.server.shutdown()
        self.server.server_close()
        self.temp_dir.cleanup()

    def test_health_endpoint_and_cors(self) -> None:
        url = f"{self.base_url}/health"
        req = urllib.request.Request(url, method="GET")
        with urllib.request.urlopen(req, timeout=1.0) as resp:
            self.assertEqual(resp.status, 200)
            self.assertEqual(resp.headers.get("Access-Control-Allow-Origin"), "*")
            data = json.loads(resp.read().decode("utf-8"))
            self.assertEqual(data.get("status"), "ok")
            self.assertEqual(data.get("port"), self.port)

    def test_options_cors_preflight(self) -> None:
        url = f"{self.base_url}/api/trajectory?id={self.convo_a}"
        req = urllib.request.Request(url, method="OPTIONS")
        with urllib.request.urlopen(req, timeout=1.0) as resp:
            self.assertEqual(resp.status, 204)
            self.assertEqual(resp.headers.get("Access-Control-Allow-Origin"), "*")
            self.assertIn("GET", resp.headers.get("Access-Control-Allow-Methods", ""))

    def test_trajectory_endpoint_success(self) -> None:
        url = f"{self.base_url}/api/trajectory?id={self.convo_a}"
        req = urllib.request.Request(url, method="GET")
        with urllib.request.urlopen(req, timeout=1.0) as resp:
            self.assertEqual(resp.status, 200)
            data = json.loads(resp.read().decode("utf-8"))
            self.assertEqual(data.get("conversation_id"), self.convo_a)
            self.assertEqual(len(data.get("steps", [])), 3)

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


class TestMultiSessionDynamicTraversal(unittest.TestCase):
    """Tests multi-session trajectory retrieval and route switching (PSL-INV-010)."""

    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.brain_dir = Path(self.temp_dir.name)

        self.convo_1 = "session-first-1111"
        self.convo_2 = "session-second-2222"

        for cid, count in [(self.convo_1, 2), (self.convo_2, 6)]:
            p = self.brain_dir / cid / ".system_generated" / "logs"
            p.mkdir(parents=True, exist_ok=True)
            with open(p / "transcript.jsonl", "w", encoding="utf-8") as f:
                for i in range(count):
                    f.write(json.dumps({"source": "user", "content": f"msg {i}"}) + "\n")

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def test_distinct_trajectories_loaded(self) -> None:
        t1 = load_conversation_trajectory(self.convo_1, brain_dir=self.brain_dir)
        t2 = load_conversation_trajectory(self.convo_2, brain_dir=self.brain_dir)

        self.assertEqual(t1["conversation_id"], self.convo_1)
        self.assertEqual(t2["conversation_id"], self.convo_2)
        self.assertEqual(len(t1["steps"]), 2)
        self.assertEqual(len(t2["steps"]), 6)

    def test_recent_conversations_discovers_all(self) -> None:
        convos = get_recent_conversations(brain_dir=self.brain_dir)
        ids = {c["id"] for c in convos}
        self.assertIn(self.convo_1, ids)
        self.assertIn(self.convo_2, ids)


class TestAntiVibeScriptDOMReplacement(unittest.TestCase):
    """Tests that generated HUD script implements PSL-INV-010 stale DOM replacement & route tracking."""

    def test_script_contains_dom_invalidation(self) -> None:
        script = build_trajectory_hud_script(
            convo_id="test-session",
            trajectory_data={"conversation_id": "test-session", "steps": []},
            conversations=[],
            open_view=True,
            toggle=False,
        )

        # 1. Stale DOM replacement check
        self.assertIn("existingHud.remove()", script)
        self.assertIn("existingStyles.remove()", script)

        # Stale styles must be purged BEFORE fresh styles are created
        idx_stale_remove = script.index("existingStyles.remove()")
        idx_style_create = script.index("document.createElement(\"style\")")
        self.assertLess(idx_stale_remove, idx_style_create, "Stale styles must be purged BEFORE fresh styles are created")

        # 2. Dynamic ConnectRPC loader definition
        self.assertIn("window.__agyis_hud_load_convo = async function", script)
        self.assertIn("GetCascadeTrajectorySteps", script)
        self.assertIn("GetCascadeTrajectoryGeneratorMetadata", script)

        # 3. Route sensitivity
        self.assertIn("window.location.pathname.match", script)

        # 4. Refresh button and event listener
        self.assertIn("agyis-refresh-btn", script)
        self.assertIn("agyis-convo-select", script)

        # 5. Hotkey registration check (unified flag)
        self.assertIn("window.__agyis_hud_hotkey_registered", script)

    def test_script_contains_dynamic_atc_and_main_deck_tabs(self) -> None:
        script = build_trajectory_hud_script(
            convo_id="test-session-256k",
            trajectory_data={"conversation_id": "test-session-256k", "steps": []},
            conversations=[],
            open_view=True,
            toggle=False,
        )
        # Anti-vibe check: dynamic sizing functions must be defined rather than static hardcoding
        self.assertIn("function Atc", script)
        self.assertIn("function xtc", script)
        self.assertIn("function ytc", script)
        self.assertIn("Context Window", script)
        self.assertIn("Timeline", script)
        self.assertIn("minSegmentPx", script)
        self.assertIn("rawSegmentsSum = segments.reduce", script)
        self.assertIn("-webkit-app-region: no-drag;", script)
        self.assertIn("height: calc(100vh - 38px)", script)

    def test_script_contains_native_connectrpc_services(self) -> None:
        script = build_trajectory_hud_script(
            convo_id="test-connectrpc",
            trajectory_data={"conversation_id": "test-connectrpc", "steps": []},
            conversations=[],
            open_view=True,
            toggle=False,
        )
        # Authoritative ConnectRPC services & headers
        self.assertIn("LanguageServerService/GetCascadeTrajectory", script)
        self.assertIn("LanguageServerService/GetCascadeTrajectorySteps", script)
        self.assertIn("LanguageServerService/GetCascadeTrajectoryGeneratorMetadata", script)
        self.assertIn("LanguageServerService/GetCascadeTrajectoryExecutorMetadatas", script)
        self.assertIn("x-codeium-csrf-token", script)
        self.assertIn("Connect-Protocol-Version", script)
        self.assertIn("CORTEX_STEP_TYPE_", script)
        self.assertIn("fallbackData", script)


class TestPSLINV010RuleCodification(unittest.TestCase):
    """Tests that PSL-INV-010 is formally codified across all rules and agent personas."""

    def test_rules_codify_psl_inv_010(self) -> None:
        root_dir = Path(__file__).resolve().parents[1]

        rule_files = [
            root_dir / "rules" / "GLOBAL_AGENTS.md",
            root_dir / "rules" / "AGENTS.md",
            root_dir / ".agents" / "rules" / "AGENTS.md",
        ]
        for rf in rule_files:
            self.assertTrue(rf.is_file(), f"Rule file missing: {rf}")
            content = rf.read_text(encoding="utf-8")
            self.assertIn("PSL-INV-010", content, f"PSL-INV-010 missing in {rf}")

    def test_personas_codify_psl_inv_010(self) -> None:
        root_dir = Path(__file__).resolve().parents[1]

        personas = [
            root_dir / "harness" / "agents" / "agyis_builder.md",
            root_dir / "harness" / "agents" / "agyis_reviewer.md",
            root_dir / "harness" / "agents" / "agyis_auditor.md",
            root_dir / "harness" / "agents" / "agyis_custodian.md",
            root_dir / ".agents" / "agents" / "agyis_builder.md",
            root_dir / ".agents" / "agents" / "agyis_reviewer.md",
            root_dir / ".agents" / "agents" / "agyis_auditor.md",
            root_dir / ".agents" / "agents" / "agyis_custodian.md",
        ]
        for pf in personas:
            self.assertTrue(pf.is_file(), f"Persona file missing: {pf}")
            content = pf.read_text(encoding="utf-8")
            self.assertIn("PSL-INV-010", content, f"PSL-INV-010 missing in {pf}")


if __name__ == "__main__":
    unittest.main()
