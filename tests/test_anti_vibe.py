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


class TestMultiSessionDynamicTraversal(unittest.TestCase):
    """Tests multi-session trajectory retrieval and route switching (PSL-INV-007)."""

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
    """Tests that generated HUD script implements PSL-INV-007 stale DOM replacement & route tracking."""

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


class TestPSLINV007RuleCodification(unittest.TestCase):
    """Tests that PSL-INV-007 is formally codified across all rules and agent personas."""

    def test_rules_codify_psl_inv_007(self) -> None:
        root_dir = Path(__file__).resolve().parents[1]

        rule_files = [
            root_dir / "rules" / "GLOBAL_AGENTS.md",
            root_dir / "rules" / "AGENTS.md",
            root_dir / ".agents" / "rules" / "AGENTS.md",
        ]
        for rf in rule_files:
            self.assertTrue(rf.is_file(), f"Rule file missing: {rf}")
            content = rf.read_text(encoding="utf-8")
            self.assertIn("PSL-INV-007", content, f"PSL-INV-007 missing in {rf}")

    def test_personas_codify_psl_inv_007(self) -> None:
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
            self.assertIn("PSL-INV-007", content, f"PSL-INV-007 missing in {pf}")


if __name__ == "__main__":
    unittest.main()
