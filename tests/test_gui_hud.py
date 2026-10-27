# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Arafat Zahan (@kuasha420)
# Corporate Stewardship & Infrastructure: Purrfect Software Limited (PSL)
# Governed by: ICARO-42/b Ordinance (Company-Supported Personal IP Framework)

"""
Hermetic unit tests for Antigravity GUI Telemetry HUD injection via CDP (Issue #68 / Phase 29).
Sub-second benchmark invariant: <0.05s SLA.
"""

from __future__ import annotations

import time
import unittest
from unittest.mock import MagicMock

from harness.commands.gui import CDPError, CDPWebSocketClient, inject_telemetry_hud


class TestGuiTelemetryHud(unittest.TestCase):
    """Hermetic unit tests for inject_telemetry_hud DOM injection and removal."""

    def test_inject_hud_safe_tier(self):
        """Verifies HUD injection expression with SAFE tier styling and nominal parameters."""
        mock_client = MagicMock(spec=CDPWebSocketClient)
        evaluated_scripts = []

        def mock_evaluate(expr, **kwargs):
            evaluated_scripts.append(expr)
            return {
                "success": True,
                "removed": False,
                "injected": True,
                "tokens": "20,000",
                "burn_rate": "+1,200 tok/min",
                "tier": "SAFE",
            }

        mock_client.evaluate.side_effect = mock_evaluate

        start_time = time.monotonic()
        res = inject_telemetry_hud(
            mock_client,
            tokens=20000,
            burn_rate=1200.0,
            mins_to_compaction=25.0,
            velocity_tier="SAFE",
            remove=False,
        )
        elapsed = time.monotonic() - start_time

        self.assertLess(elapsed, 0.05, f"Sub-second SLA exceeded: {elapsed:.4f}s >= 0.05s")
        self.assertTrue(res["success"])
        self.assertFalse(res["removed"])
        self.assertTrue(res["injected"])
        self.assertEqual(res["tier"], "SAFE")

        self.assertEqual(len(evaluated_scripts), 1)
        script = evaluated_scripts[0]
        self.assertIn("agyis-telemetry-hud", script)
        self.assertIn("#22c55e", script, "SAFE tier must use green border (#22c55e)")
        self.assertIn("20,000", script)
        self.assertIn("+1,200 tok/min", script)
        self.assertIn("~25m to 50k", script)

    def test_inject_hud_elevated_tier(self):
        """Verifies HUD injection with ELEVATED tier styling (#f59e0b)."""
        mock_client = MagicMock(spec=CDPWebSocketClient)
        evaluated_scripts = []

        def mock_evaluate(expr, **kwargs):
            evaluated_scripts.append(expr)
            return {
                "success": True,
                "removed": False,
                "injected": True,
                "tokens": "38,420",
                "burn_rate": "+2,500 tok/min",
                "tier": "ELEVATED",
            }

        mock_client.evaluate.side_effect = mock_evaluate

        res = inject_telemetry_hud(
            mock_client,
            tokens=38420,
            burn_rate=2500.0,
            mins_to_compaction=4.6,
            velocity_tier="ELEVATED",
            remove=False,
        )

        self.assertTrue(res["success"])
        self.assertEqual(res["tier"], "ELEVATED")
        script = evaluated_scripts[0]
        self.assertIn("#f59e0b", script, "ELEVATED tier must use amber border (#f59e0b)")
        self.assertIn("+2,500 tok/min", script)
        self.assertIn("~5m to 50k", script)

    def test_inject_hud_critical_tier(self):
        """Verifies HUD injection with CRITICAL tier styling (#ef4444)."""
        mock_client = MagicMock(spec=CDPWebSocketClient)
        evaluated_scripts = []

        def mock_evaluate(expr, **kwargs):
            evaluated_scripts.append(expr)
            return {
                "success": True,
                "removed": False,
                "injected": True,
                "tokens": "46,000",
                "burn_rate": "+4,200 tok/min",
                "tier": "CRITICAL",
            }

        mock_client.evaluate.side_effect = mock_evaluate

        res = inject_telemetry_hud(
            mock_client,
            tokens=46000,
            burn_rate=4200.0,
            mins_to_compaction=0.9,
            velocity_tier="CRITICAL",
            remove=False,
        )

        self.assertTrue(res["success"])
        self.assertEqual(res["tier"], "CRITICAL")
        script = evaluated_scripts[0]
        self.assertIn("#ef4444", script, "CRITICAL tier must use red border (#ef4444)")
        self.assertIn("+4,200 tok/min", script)
        self.assertIn("~1m to 50k", script)

    def test_remove_hud_element(self):
        """Verifies HUD removal script generation and execution."""
        mock_client = MagicMock(spec=CDPWebSocketClient)
        evaluated_scripts = []

        def mock_evaluate(expr, **kwargs):
            evaluated_scripts.append(expr)
            return {"success": True, "removed": True, "injected": False}

        mock_client.evaluate.side_effect = mock_evaluate

        res = inject_telemetry_hud(mock_client, tokens=0, remove=True)

        self.assertTrue(res["success"])
        self.assertTrue(res["removed"])
        self.assertFalse(res["injected"])

        self.assertEqual(len(evaluated_scripts), 1)
        script = evaluated_scripts[0]
        self.assertIn("agyis-telemetry-hud", script)
        self.assertIn("el.remove()", script)

    def test_evaluation_error_raises_cdperror(self):
        """Evaluation failure error returned from page raises CDPError."""
        mock_client = MagicMock(spec=CDPWebSocketClient)
        mock_client.evaluate.return_value = {"success": False, "error": "DOM disconnected"}

        with self.assertRaises(CDPError) as ctx:
            inject_telemetry_hud(mock_client, tokens=1000, remove=False)
        self.assertIn("DOM disconnected", str(ctx.exception))


if __name__ == "__main__":
    unittest.main()
