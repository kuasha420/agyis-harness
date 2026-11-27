# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Arafat Zahan (@kuasha420)
# Corporate Stewardship & Infrastructure: Purrfect Software Limited (PSL)
# Governed by: ICARO-42/b Ordinance (Company-Supported Personal IP Framework)

"""Hermetic verification suite for v1.1.2 Track 6: hooks.json status rendering, burn-rate gating, #101 & #94."""

from __future__ import annotations

import argparse
import io
import json
import os
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import patch

from harness.commands.status import _load_live_hooks_summary, cmd_status
from harness.trajectory.health import resolve_display_velocity_tier
from harness.utils.plan_parser import is_plan_completed, resolve_active_plan


class TestHooksSummaryAndStatusRender(unittest.TestCase):
    """Verifies flat PreInvocation & Stop hook rendering and burn-rate clamping in `agyis status`."""

    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def test_load_live_hooks_summary_parses_real_preinvocation_and_stop(self) -> None:
        """Real harness/hooks/hooks.json renders non-blank PreInvocation and Stop checks."""
        checks, blocks = _load_live_hooks_summary()
        self.assertIn("pre-invocation", checks)
        self.assertIn("verification-fence", checks)

        by_name = {b["name"]: b for b in blocks}
        self.assertIn("psl-compaction-advisory", by_name)
        advisory = by_name["psl-compaction-advisory"]
        self.assertEqual(advisory["events"], ["PreInvocation"])
        self.assertEqual(advisory["checks"], ["pre-invocation"])

        fence = by_name["psl-stop-verification-fence"]
        self.assertIn("Stop", fence["events"])
        self.assertIn("verification-fence", fence["checks"])

    def test_load_live_hooks_summary_custom_flat_and_module_commands(self) -> None:
        """Flat hook entries using -m module or script paths never yield empty check names."""
        custom_hooks = self.root / "hooks.json"
        custom_hooks.write_text(
            json.dumps({
                "custom-pre": {
                    "PreInvocation": [
                        {"type": "command", "command": "python3 -m harness.hooks.pre_invocation_hook", "timeout": 5}
                    ]
                },
                "custom-stop": {
                    "Stop": [
                        {"type": "command", "command": "python3 /opt/hooks/stop_fence.py"}
                    ]
                },
            }),
            encoding="utf-8",
        )
        checks, blocks = _load_live_hooks_summary(hooks_path=custom_hooks)
        self.assertEqual(checks, ["pre-invocation-hook", "stop-fence"])
        self.assertEqual(blocks[0]["checks"], ["pre-invocation-hook"])
        self.assertEqual(blocks[1]["checks"], ["stop-fence"])

    def test_resolve_display_velocity_tier_boundaries(self) -> None:
        """Exhaustive boundary tests for 25% fill and 5.0-minute compaction ETA gate."""
        self.assertEqual(resolve_display_velocity_tier(20_000, 256_000, "CRITICAL", 40.0), "ELEVATED")
        self.assertEqual(resolve_display_velocity_tier(50_000, 1_000_000, "CRITICAL", None), "ELEVATED")
        self.assertEqual(resolve_display_velocity_tier(63_999, 256_000, "CRITICAL", 5.1), "ELEVATED")
        self.assertEqual(resolve_display_velocity_tier(64_000, 256_000, "CRITICAL", 40.0), "CRITICAL")
        self.assertEqual(resolve_display_velocity_tier(20_000, 256_000, "CRITICAL", 5.0), "CRITICAL")
        self.assertEqual(resolve_display_velocity_tier(20_000, 256_000, "ELEVATED", 40.0), "ELEVATED")
        self.assertEqual(resolve_display_velocity_tier(20_000, 256_000, "SAFE", None), "SAFE")
        self.assertEqual(resolve_display_velocity_tier(20_000, 0, "CRITICAL", 40.0), "CRITICAL")

    def test_cmd_status_text_and_json_clamp_low_fill_critical_and_show_preinvocation(self) -> None:
        """`agyis status` renders `pre-invocation` (never blank) and clamps low-fill CRITICAL burn to ELEVATED."""
        conv_dir = self.root / "conversations"
        conv_dir.mkdir(parents=True)
        conv_id = "status-low-fill-burn"
        db_path = conv_dir / f"{conv_id}.db"
        conn = sqlite3.connect(db_path)
        conn.execute("CREATE TABLE steps (idx INTEGER PRIMARY KEY, token_count INTEGER, created_at TEXT)")
        conn.execute("CREATE TABLE gen_metadata (idx INTEGER PRIMARY KEY, data TEXT)")
        # 48,353 / 512,000 = 9.4% fill, +10,000 tok/min -> raw velocity_tier = CRITICAL, ETA ~41m
        conn.execute("INSERT INTO steps VALUES (1, 38353, '2026-11-27 12:00:00')")
        conn.execute("INSERT INTO steps VALUES (2, 48353, '2026-11-27 12:01:00')")
        conn.execute(
            "INSERT INTO gen_metadata VALUES (1, ?)",
            (json.dumps({"chatStartMetadata": {"contextWindowMetadata": {"estimatedTokensUsed": 48353, "maxContextTokens": 512000}}}),),
        )
        conn.commit()
        conn.close()

        env_patch = {
            "AGYIS_CONVERSATIONS_DIR": str(conv_dir),
            "AGYIS_CONVERSATION_ID": conv_id,
            "ANTIGRAVITY_CONVERSATION_ID": conv_id,
            "NO_COLOR": "1",
        }
        with patch.dict(os.environ, env_patch, clear=False), \
             patch("harness.commands.status.DEFAULT_DB", self.root / "missing_telem.db"), \
             patch("harness.telemetry.config.resolve_db_path", return_value=self.root / "missing_telem.db"), \
             patch("harness.subagents.list_active_subagent_statuses", return_value=[]):
            out_txt = io.StringIO()
            with patch("sys.stdout", out_txt):
                rc_txt = cmd_status(argparse.Namespace(json=False, workspace_dir=self.root))
            self.assertEqual(rc_txt, 0)
            rendered = out_txt.getvalue()
            self.assertIn("pre-invocation", rendered)
            self.assertNotIn("●                          (PreInvocation)", rendered)
            self.assertIn("+10,000 tok/min", rendered)
            self.assertIn(" - ELEVATED", rendered)
            self.assertNotIn(" - CRITICAL", rendered)

            out_json = io.StringIO()
            with patch("sys.stdout", out_json):
                rc_json = cmd_status(argparse.Namespace(json=True, workspace_dir=self.root))
            self.assertEqual(rc_json, 0)
            payload = json.loads(out_json.getvalue())
            self.assertIn("pre-invocation", payload["active_hooks"])
            self.assertEqual(payload["token_metrics"]["velocity_tier"], "ELEVATED")
            self.assertAlmostEqual(payload["token_metrics"]["burn_rate_tokens_per_min"], 10000.0, places=1)
            self.assertIsNotNone(payload["token_metrics"]["mins_to_compaction"])


class TestPlanParserStatusActiveAndInProgress(unittest.TestCase):
    """Covers `status: active`, `- [/]`, and `is_plan_completed` with in-progress checkboxes (#94)."""

    def test_in_progress_and_status_active_markers(self) -> None:
        self.assertFalse(is_plan_completed("- [x] Done\n- [/] In progress\n"))
        self.assertTrue(is_plan_completed("- [x] Done\n* [X] Also done\n"))

        with tempfile.TemporaryDirectory() as td:
            ws = Path(td)
            doc = ws / "ARCHITECTURE_REFACTORING_PLAN.md"
            doc.write_text("---\nstatus: active\n---\n\n# Active Architecture Plan\n", encoding="utf-8")
            resolved, src_type = resolve_active_plan(workspace_root=ws, allow_unmarked_root_plans=False)
            self.assertEqual(resolved, doc)
            self.assertEqual(src_type, "workspace_active_plan")


if __name__ == "__main__":
    unittest.main()
